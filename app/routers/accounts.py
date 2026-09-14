from __future__ import annotations

import asyncio
from decimal import InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from app.models import Account, Transaction
from app.templating import render
from app.utils import PAGE_SIZE, parse_amount_to_cents, parse_date

router = APIRouter()


def _filter_query_string(params: dict[str, str]) -> str:
    cleaned = {key: value for key, value in params.items() if value and key != "page"}
    return urlencode(cleaned)


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
