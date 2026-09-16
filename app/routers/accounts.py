from __future__ import annotations

import asyncio
from decimal import InvalidOperation
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.middleware import csrf_forbidden
from app.models import Account, Transaction
from app.security import require_csrf
from app.templating import render
from app.utils import (
    PAGE_SIZE,
    apply_balance_delta,
    format_money,
    next_transaction_id,
    parse_amount_to_cents,
    parse_date,
    utcnow,
)

router = APIRouter()


def _filter_query_string(params: dict[str, str]) -> str:
    cleaned = {key: value for key, value in params.items() if value and key != "page"}
    return urlencode(cleaned)


def _account_not_found(request: Request):
    return render(
        request,
        "error.html",
        status_code=404,
        title="Account not found",
        message="No account exists with that ID.",
    )


def _account_inactive_forbidden(request: Request):
    return render(
        request,
        "error.html",
        status_code=403,
        title="Account is not active",
        message="Credits and debits can only be posted on active accounts.",
    )


def _load_account(db, account_id: str) -> Account | None:
    return (
        db.query(Account)
        .options(joinedload(Account.member))
        .filter(Account.id == account_id)
        .one_or_none()
    )


def _is_deposit(account: Account) -> bool:
    return account.account_type in {"checking", "savings"}


def _would_overdraft(account: Account, direction: str, amount_cents: int) -> bool:
    if not _is_deposit(account) or direction != "debit":
        return False
    proposed = apply_balance_delta(
        account.balance_cents, account.account_type, direction, amount_cents
    )
    return proposed < 0


def _post_leg(
    db,
    account: Account,
    *,
    direction: str,
    amount_cents: int,
    description: str,
    existing_ids: list[str],
) -> Transaction:
    txn_id = next_transaction_id(existing_ids, account.id)
    existing_ids.append(txn_id)
    transaction = Transaction(
        id=txn_id,
        account_id=account.id,
        posted_on=utcnow().date(),
        description=description,
        amount_cents=amount_cents,
        direction=direction,
        status="posted",
        currency=account.currency,
    )
    account.balance_cents = apply_balance_delta(
        account.balance_cents, account.account_type, direction, amount_cents
    )
    db.add(transaction)
    return transaction


def _render_adjust_form(
    request: Request,
    *,
    account: Account,
    operation: str,
    method: str = "cheque",
    cheque_number: str = "",
    amount: str = "",
    counterparty_id: str = "",
    errors: list[str] | None = None,
):
    return render(
        request,
        "account_adjust.html",
        account=account,
        member=account.member,
        operation=operation,
        method=method,
        cheque_number=cheque_number,
        amount=amount,
        counterparty_id=counterparty_id,
        errors=errors or [],
    )


def _parse_adjust_form(form) -> tuple[str, str, str, str, list[str], int | None]:
    method = (form.get("method") or "").strip()
    cheque_number = (form.get("cheque_number") or "").strip()
    amount_raw = (form.get("amount") or "").strip()
    counterparty_id = (form.get("counterparty_id") or "").strip()
    errors: list[str] = []
    amount_cents: int | None = None

    if method not in {"cheque", "transfer"}:
        errors.append("Select cheque or transfer.")
        method = "cheque"

    if not amount_raw:
        errors.append("Amount is required.")
    else:
        try:
            amount_cents = parse_amount_to_cents(amount_raw)
            if amount_cents <= 0:
                errors.append("Amount must be greater than zero.")
                amount_cents = None
        except (InvalidOperation, ValueError):
            errors.append("Enter a valid amount.")

    if method == "cheque":
        if not cheque_number:
            errors.append("Cheque number is required.")
    elif method == "transfer":
        if not counterparty_id:
            errors.append("Counterparty account ID is required.")

    return method, cheque_number, amount_raw, counterparty_id, errors, amount_cents


@router.get("/accounts")
async def account_search(request: Request):
    db = request.state.db
    submitted = "q" in request.query_params
    term = (request.query_params.get("q") or "").strip()
    error = None
    results: list[Account] = []
    if submitted and not term:
        error = "Enter an account ID to search."
    elif submitted:
        like = f"%{term}%"
        results = (
            db.query(Account)
            .options(joinedload(Account.member))
            .filter(or_(Account.id == term, Account.id.ilike(like)))
            .order_by(Account.id)
            .all()
        )
    return render(
        request,
        "account_search.html",
        term=term,
        submitted=submitted,
        error=error,
        results=results,
    )


@router.get("/accounts/{account_id}")
async def account_details(request: Request, account_id: str):
    db = request.state.db
    account = db.get(Account, account_id)
    if account is None:
        return _account_not_found(request)

    flags = request.state.flags
    session_row = request.state.portal_session
    if flags.get("slow_seconds"):
        try:
            seconds = min(int(flags["slow_seconds"]), 30)
        except (TypeError, ValueError):
            seconds = 0
        flags["slow_seconds"] = None
        from app.security import save_flags

        save_flags(session_row, flags)
        if seconds > 0:
            await asyncio.sleep(seconds)

    start_raw = (request.query_params.get("start_date") or "").strip()
    end_raw = (request.query_params.get("end_date") or "").strip()
    min_amount_raw = (request.query_params.get("min_amount") or "").strip()
    q_raw = (request.query_params.get("q") or "").strip()
    direction = (request.query_params.get("direction") or "all").strip() or "all"
    page_raw = request.query_params.get("page") or "1"

    errors: list[str] = []
    start_date = end_date = None
    min_cents = None
    try:
        start_date = parse_date(start_raw) if start_raw else None
    except ValueError:
        errors.append("Enter a valid start date.")
    try:
        end_date = parse_date(end_raw) if end_raw else None
    except ValueError:
        errors.append("Enter a valid end date.")
    if start_date and end_date and start_date > end_date:
        errors.append("End date must be on or after the start date.")
    if min_amount_raw:
        try:
            min_cents = parse_amount_to_cents(min_amount_raw)
            if min_cents < 0:
                errors.append("Enter a valid amount.")
                min_cents = None
        except (InvalidOperation, ValueError):
            errors.append("Enter a valid amount.")
    if direction not in {"all", "debit", "credit"}:
        direction = "all"
    try:
        page = max(int(page_raw), 1)
    except ValueError:
        page = 1

    retry_query = _filter_query_string(
        {
            "start_date": start_raw,
            "end_date": end_raw,
            "min_amount": min_amount_raw,
            "q": q_raw,
            "direction": direction if direction != "all" else "",
            "page": str(page) if page > 1 else "",
        }
    )
    retry_url = f"/accounts/{account.id}"
    if retry_query:
        retry_url = f"{retry_url}?{retry_query}"

    if flags.get("temp_error_next"):
        flags["temp_error_next"] = False
        from app.security import save_flags

        save_flags(session_row, flags)
        return render(
            request,
            "account.html",
            account=account,
            member=account.member,
            errors=[],
            temp_error=True,
            retry_url=retry_url,
            start_date=start_raw,
            end_date=end_raw,
            min_amount=min_amount_raw,
            q=q_raw,
            direction=direction,
            transactions=[],
            total=0,
            page=1,
            page_count=1,
            apply_label="Search Transactions" if flags.get("rename_apply_filters") else "Apply Filters",
            filter_query="",
            range_start=0,
            range_end=0,
            flash=None,
        )

    query = db.query(Transaction).filter(Transaction.account_id == account.id)
    if not errors:
        if start_date:
            query = query.filter(Transaction.posted_on >= start_date)
        if end_date:
            query = query.filter(Transaction.posted_on <= end_date)
        if min_cents is not None:
            query = query.filter(Transaction.amount_cents > min_cents)
        if q_raw:
            like = f"%{q_raw}%"
            query = query.filter(
                or_(
                    Transaction.id == q_raw,
                    Transaction.description.ilike(like),
                )
            )
        if direction in {"debit", "credit"}:
            query = query.filter(Transaction.direction == direction)

    total = query.count() if not errors else 0
    page_count = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    if page > page_count:
        page = page_count
    offset = (page - 1) * PAGE_SIZE
    transactions = []
    if not errors:
        transactions = (
            query.order_by(Transaction.posted_on.desc(), Transaction.id.desc())
            .offset(offset)
            .limit(PAGE_SIZE)
            .all()
        )

    filter_query = _filter_query_string(
        {
            "start_date": start_raw,
            "end_date": end_raw,
            "min_amount": min_amount_raw,
            "q": q_raw,
            "direction": direction if direction != "all" else "",
        }
    )
    range_start = offset + 1 if total and not errors else 0
    range_end = min(offset + len(transactions), total) if not errors else 0

    return render(
        request,
        "account.html",
        account=account,
        member=account.member,
        errors=errors,
        temp_error=False,
        retry_url=retry_url,
        start_date=start_raw,
        end_date=end_raw,
        min_amount=min_amount_raw,
        q=q_raw,
        direction=direction,
        transactions=transactions,
        total=0 if errors else total,
        page=page,
        page_count=page_count,
        apply_label="Search Transactions" if flags.get("rename_apply_filters") else "Apply Filters",
        filter_query=filter_query,
        range_start=range_start,
        range_end=range_end,
        flash=request.query_params.get("flash"),
    )


@router.get("/accounts/{account_id}/credit")
async def account_credit_form(request: Request, account_id: str):
    account = _load_account(request.state.db, account_id)
    if account is None:
        return _account_not_found(request)
    if account.status != "active":
        return _account_inactive_forbidden(request)
    return _render_adjust_form(request, account=account, operation="credit")


@router.post("/accounts/{account_id}/credit")
async def account_credit_submit(request: Request, account_id: str):
    return await _submit_adjust(request, account_id, operation="credit")


@router.get("/accounts/{account_id}/debit")
async def account_debit_form(request: Request, account_id: str):
    account = _load_account(request.state.db, account_id)
    if account is None:
        return _account_not_found(request)
    if account.status != "active":
        return _account_inactive_forbidden(request)
    return _render_adjust_form(request, account=account, operation="debit")


@router.post("/accounts/{account_id}/debit")
async def account_debit_submit(request: Request, account_id: str):
    return await _submit_adjust(request, account_id, operation="debit")


async def _submit_adjust(request: Request, account_id: str, *, operation: str):
    db = request.state.db
    account = _load_account(db, account_id)
    if account is None:
        return _account_not_found(request)
    if account.status != "active":
        return _account_inactive_forbidden(request)

    form = await request.form()
    row = request.state.portal_session
    if row is None or not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)

    method, cheque_number, amount_raw, counterparty_id, errors, amount_cents = _parse_adjust_form(
        form
    )
    if errors or amount_cents is None:
        return _render_adjust_form(
            request,
            account=account,
            operation=operation,
            method=method,
            cheque_number=cheque_number,
            amount=amount_raw,
            counterparty_id=counterparty_id,
            errors=errors,
        )

    primary_direction = operation  # "credit" or "debit"
    existing_ids = [row[0] for row in db.query(Transaction.id).all()]

    if method == "cheque":
        if _would_overdraft(account, primary_direction, amount_cents):
            return _render_adjust_form(
                request,
                account=account,
                operation=operation,
                method=method,
                cheque_number=cheque_number,
                amount=amount_raw,
                counterparty_id=counterparty_id,
                errors=["This debit would make the account balance negative."],
            )
        description = f"Cheque {primary_direction} #{cheque_number}"
        txn = _post_leg(
            db,
            account,
            direction=primary_direction,
            amount_cents=amount_cents,
            description=description,
            existing_ids=existing_ids,
        )
        db.flush()
        verb = "Credited" if operation == "credit" else "Debited"
        flash = f"{verb} {format_money(amount_cents)}. {txn.id}"
        return RedirectResponse(
            f"/accounts/{account.id}?flash={quote(flash)}",
            status_code=303,
        )

    # Transfer
    if counterparty_id == account.id:
        return _render_adjust_form(
            request,
            account=account,
            operation=operation,
            method=method,
            cheque_number=cheque_number,
            amount=amount_raw,
            counterparty_id=counterparty_id,
            errors=["Counterparty account must be different from this account."],
        )

    other = db.get(Account, counterparty_id)
    if other is None:
        return _render_adjust_form(
            request,
            account=account,
            operation=operation,
            method=method,
            cheque_number=cheque_number,
            amount=amount_raw,
            counterparty_id=counterparty_id,
            errors=["No account exists with that counterparty ID."],
        )

    if operation == "credit":
        # Money from other → debit other, credit this
        debit_account, credit_account = other, account
    else:
        # Money to other → debit this, credit other
        debit_account, credit_account = account, other

    if _would_overdraft(debit_account, "debit", amount_cents):
        whose = (
            "this account"
            if debit_account.id == account.id
            else f"counterparty account {debit_account.id}"
        )
        return _render_adjust_form(
            request,
            account=account,
            operation=operation,
            method=method,
            cheque_number=cheque_number,
            amount=amount_raw,
            counterparty_id=counterparty_id,
            errors=[f"This transfer would make {whose} balance negative."],
        )

    debit_txn = _post_leg(
        db,
        debit_account,
        direction="debit",
        amount_cents=amount_cents,
        description=f"Transfer to {credit_account.id}",
        existing_ids=existing_ids,
    )
    credit_txn = _post_leg(
        db,
        credit_account,
        direction="credit",
        amount_cents=amount_cents,
        description=f"Transfer from {debit_account.id}",
        existing_ids=existing_ids,
    )
    db.flush()

    verb = "Credited" if operation == "credit" else "Debited"
    flash = (
        f"{verb} {format_money(amount_cents)} via transfer "
        f"({debit_txn.id} / {credit_txn.id})."
    )
    return RedirectResponse(
        f"/accounts/{account.id}?flash={quote(flash)}",
        status_code=303,
    )


@router.get("/transactions/{transaction_id}")
async def transaction_details(request: Request, transaction_id: str):
    db = request.state.db
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Transaction not found",
            message="No transaction exists with that ID.",
        )
    notes = sorted(transaction.notes, key=lambda note: note.created_at, reverse=True)
    return_to = request.query_params.get("return_to") or ""
    return render(
        request,
        "transaction.html",
        transaction=transaction,
        account=transaction.account,
        member=transaction.account.member,
        notes=notes,
        return_to=return_to,
        can_add_note=transaction.account.status == "active",
    )
