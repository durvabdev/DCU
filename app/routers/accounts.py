from __future__ import annotations

import asyncio
from decimal import InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_

from app.middleware import csrf_forbidden
from app.models import Account, Transaction
from app.security import require_csrf
from app.templating import render
from app.utils import (
    PAGE_SIZE,
    apply_balance_delta,
    next_transaction_id,
    parse_amount_to_cents,
    parse_date,
    utcnow,
)

router = APIRouter()


def _filter_query_string(params: dict[str, str]) -> str:
    cleaned = {key: value for key, value in params.items() if value and key != "page"}
    return urlencode(cleaned)


# Cheque book order catalog: type key → (label, pages, fee_cents).
CHEQUE_BOOK_TYPES: dict[str, tuple[str, int, int]] = {
    "standard": ("Standard", 25, 1500),
    "business": ("Business", 50, 2500),
    "premium": ("Premium", 100, 4000),
}


def _cheque_book_type_options() -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = []
    for key, (label, pages, fee_cents) in CHEQUE_BOOK_TYPES.items():
        dollars = fee_cents / 100
        options.append((key, f"{label} — {pages} pages (${dollars:.2f})"))
    return options


def _fee_debit_accounts(db, member_id: str) -> list[Account]:
    return (
        db.query(Account)
        .filter(
            Account.member_id == member_id,
            Account.status == "active",
            Account.account_type.in_(("checking", "savings")),
        )
        .order_by(Account.id)
        .all()
    )


def _cheque_book_forbidden(request: Request, account: Account | None):
    if account is None:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Account not found",
            message="No account exists with that ID.",
        )
    if account.account_type != "checking":
        return render(
            request,
            "error.html",
            status_code=403,
            title="Cheque books unavailable",
            message="Cheque books can only be ordered for checking accounts.",
        )
    if account.status != "active":
        return render(
            request,
            "error.html",
            status_code=403,
            title="Account is not active",
            message="Cheque books cannot be ordered on an inactive account.",
        )
    return None


@router.get("/accounts/{account_id}")
async def account_details(request: Request, account_id: str):
    db = request.state.db
    account = db.get(Account, account_id)
    if account is None:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Account not found",
            message="No account exists with that ID.",
        )

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


@router.get("/accounts/{account_id}/cheque-books/new")
async def cheque_book_new_form(request: Request, account_id: str):
    db = request.state.db
    account = db.get(Account, account_id)
    forbidden = _cheque_book_forbidden(request, account)
    if forbidden is not None:
        return forbidden

    fee_accounts = _fee_debit_accounts(db, account.member_id)
    return render(
        request,
        "cheque_book_new.html",
        account=account,
        member=account.member,
        book_type="standard",
        book_types=_cheque_book_type_options(),
        fee_account_id=account.id,
        fee_accounts=fee_accounts,
        errors=[],
    )


@router.post("/accounts/{account_id}/cheque-books/new")
async def cheque_book_new_submit(request: Request, account_id: str):
    db = request.state.db
    account = db.get(Account, account_id)
    forbidden = _cheque_book_forbidden(request, account)
    if forbidden is not None:
        return forbidden

    form = await request.form()
    row = request.state.portal_session
    if row is None or not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)

    book_type = (form.get("book_type") or "").strip()
    fee_account_id = (form.get("fee_account_id") or "").strip()
    fee_accounts = _fee_debit_accounts(db, account.member_id)
    fee_account_ids = {item.id for item in fee_accounts}
    errors: list[str] = []

    type_info = CHEQUE_BOOK_TYPES.get(book_type)
    if type_info is None:
        errors.append("Select a valid cheque book type.")
        book_type = "standard"
        type_info = CHEQUE_BOOK_TYPES[book_type]

    fee_account = None
    if fee_account_id not in fee_account_ids:
        errors.append("Select a valid fee debit account.")
        fee_account_id = account.id if account.id in fee_account_ids else (
            fee_accounts[0].id if fee_accounts else ""
        )
    else:
        fee_account = next(item for item in fee_accounts if item.id == fee_account_id)

    if errors:
        return render(
            request,
            "cheque_book_new.html",
            account=account,
            member=account.member,
            book_type=book_type,
            book_types=_cheque_book_type_options(),
            fee_account_id=fee_account_id,
            fee_accounts=fee_accounts,
            errors=errors,
        )

    label, pages, fee_cents = type_info
    proposed = apply_balance_delta(
        fee_account.balance_cents, fee_account.account_type, "debit", fee_cents
    )
    if proposed < 0:
        return render(
            request,
            "cheque_book_new.html",
            account=account,
            member=account.member,
            book_type=book_type,
            book_types=_cheque_book_type_options(),
            fee_account_id=fee_account_id,
            fee_accounts=fee_accounts,
            errors=["Cheque book fee would make the fee account balance negative."],
        )

    existing_ids = [row[0] for row in db.query(Transaction.id).all()]
    txn_id = next_transaction_id(existing_ids, fee_account.id)
    transaction = Transaction(
        id=txn_id,
        account_id=fee_account.id,
        posted_on=utcnow().date(),
        description=f"Cheque issue — {label} ({pages} pages)",
        amount_cents=fee_cents,
        direction="debit",
        status="posted",
        currency=fee_account.currency,
    )
    fee_account.balance_cents = proposed
    db.add(transaction)
    db.flush()
    return RedirectResponse(f"/transactions/{transaction.id}", status_code=303)
