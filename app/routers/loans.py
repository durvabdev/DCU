from decimal import InvalidOperation
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_

from app.middleware import csrf_forbidden
from app.models import Account, Member
from app.security import require_csrf
from app.templating import render
from app.utils import next_account_id, parse_amount_to_cents

router = APIRouter()


def _search_members(db, term: str) -> list[Member]:
    like = f"%{term}%"
    full_name = func.lower(Member.first_name + " " + Member.last_name)
    return (
        db.query(Member)
        .filter(
            or_(
                Member.id == term,
                Member.first_name.ilike(like),
                Member.last_name.ilike(like),
                full_name.like(term.lower()),
                full_name.like(f"%{term.lower()}%"),
            )
        )
        .order_by(Member.last_name, Member.first_name, Member.id)
        .all()
    )


@router.get("/loans/new")
async def loan_search(request: Request):
    db = request.state.db
    submitted = "q" in request.query_params
    term = (request.query_params.get("q") or "").strip()
    error = None
    results: list[Member] = []
    if submitted and not term:
        error = "Enter a member ID or name to search."
    elif submitted:
        results = _search_members(db, term)
    return render(
        request,
        "loan_search.html",
        term=term,
        submitted=submitted,
        error=error,
        results=results,
    )


@router.get("/loans/new/{member_id}")
async def loan_new_form(request: Request, member_id: str):
    db = request.state.db
    member = db.get(Member, member_id)
    if member is None:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Member not found",
            message="No member exists with that ID.",
        )
    if member.status != "active":
        return render(
            request,
            "error.html",
            status_code=403,
            title="Member is not active",
            message="New loans can only be opened for active members.",
        )
    opened = (request.query_params.get("opened") or "").strip()
    flash = None
    if opened:
        flash = f"Account opened. {opened}"
    return render(
        request,
        "loan_new.html",
        member=member,
        outstanding_balance="",
        errors=[],
        flash=flash,
        opened=opened or None,
    )


@router.post("/loans/new/{member_id}")
async def loan_new_submit(request: Request, member_id: str):
    db = request.state.db
    member = db.get(Member, member_id)
    if member is None:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Member not found",
            message="No member exists with that ID.",
        )
    if member.status != "active":
        return render(
            request,
            "error.html",
            status_code=403,
            title="Member is not active",
            message="New loans can only be opened for active members.",
        )
    form = await request.form()
    row = request.state.portal_session
    if row is None or not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)

    outstanding_balance = (form.get("outstanding_balance") or "").strip()
    errors: list[str] = []
    balance_cents = 0
    if not outstanding_balance:
        errors.append("Outstanding balance is required.")
    else:
        try:
            balance_cents = parse_amount_to_cents(outstanding_balance)
            if balance_cents < 0:
                errors.append("Outstanding balance must be zero or greater.")
        except (InvalidOperation, ValueError):
            errors.append("Enter a valid outstanding balance.")

    if errors:
        return render(
            request,
            "loan_new.html",
            member=member,
            outstanding_balance=outstanding_balance,
            errors=errors,
        )

    existing_ids = [row[0] for row in db.query(Account.id).all()]
    account_id = next_account_id(existing_ids, "LN")
    account = Account(
        id=account_id,
        member_id=member.id,
        account_type="loan",
        status="active",
        currency="USD",
        balance_cents=balance_cents,
    )
    db.add(account)
    db.flush()
    return RedirectResponse(
        f"/loans/new/{member.id}?opened={quote(account.id)}",
        status_code=303,
    )
