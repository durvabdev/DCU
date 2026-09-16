from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_

from app.middleware import csrf_forbidden
from app.models import Account, Member, Transaction
from app.security import require_csrf
from app.templating import render
from app.utils import (
    apply_balance_delta,
    format_money,
    next_account_id,
    next_transaction_id,
    utcnow,
)

router = APIRouter()

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


def _active_checking_accounts(db, member_id: str) -> list[Account]:
    return (
        db.query(Account)
        .filter(
            Account.member_id == member_id,
            Account.status == "active",
            Account.account_type == "checking",
        )
        .order_by(Account.id)
        .all()
    )


def _cheque_book_forbidden(request: Request, member: Member | None):
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
            message="Cheque books can only be ordered for active members.",
        )
    checking = _active_checking_accounts(request.state.db, member.id)
    if not checking:
        return render(
            request,
            "error.html",
            status_code=403,
            title="Cheque books unavailable",
            message="Cheque books require an active checking account.",
        )
    return None


@router.get("/")
async def home(request: Request):
    return render(request, "home.html")


@router.get("/teller")
async def teller_profile(request: Request):
    return render(request, "teller.html")


@router.get("/members")
async def member_search(request: Request):
    db = request.state.db
    submitted = "q" in request.query_params
    term = (request.query_params.get("q") or "").strip()
    error = None
    results: list[Member] = []
    if submitted and not term:
        error = "Enter a member ID or name to search."
    elif submitted:
        like = f"%{term}%"
        full_name = func.lower(Member.first_name + " " + Member.last_name)
        results = (
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
    return render(
        request,
        "search.html",
        term=term,
        submitted=submitted,
        error=error,
        results=results,
    )


@router.get("/members/{member_id}")
async def member_profile(request: Request, member_id: str):
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
    accounts = sorted(member.accounts, key=lambda account: account.id)
    return render(
        request,
        "member.html",
        member=member,
        accounts=accounts,
        flash=request.query_params.get("flash"),
    )


def _validate_member_form(form) -> tuple[dict[str, str], list[str]]:
    values = {
        "first_name": (form.get("first_name") or "").strip(),
        "last_name": (form.get("last_name") or "").strip(),
        "email": (form.get("email") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "street": (form.get("street") or "").strip(),
        "city": (form.get("city") or "").strip(),
        "state": (form.get("state") or "").strip(),
        "postal_code": (form.get("postal_code") or "").strip(),
    }
    errors = [f"{field.replace('_', ' ').title()} is required." for field, value in values.items() if not value]
    return values, errors


@router.get("/members/{member_id}/edit")
async def member_edit_form(request: Request, member_id: str):
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
    return render(request, "member_edit.html", member=member, errors=[])


@router.post("/members/{member_id}/edit")
async def member_edit_submit(request: Request, member_id: str):
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
    form = await request.form()
    row = request.state.portal_session
    if row is None or not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)
    values, errors = _validate_member_form(form)
    if errors:
        member_input = {**values, "id": member.id, "status": member.status}
        return render(request, "member_edit.html", member=member_input, errors=errors)

    for key, value in values.items():
        setattr(member, key, value)
    return RedirectResponse(f"/members/{member.id}?flash=Member+profile+updated.", status_code=303)


@router.get("/members/{member_id}/accounts/new")
async def account_new_form(request: Request, member_id: str):
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
            message="New accounts can only be opened for active members.",
        )
    return render(
        request,
        "account_new.html",
        member=member,
        account_type="checking",
        errors=[],
    )


@router.post("/members/{member_id}/accounts/new")
async def account_new_submit(request: Request, member_id: str):
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
            message="New accounts can only be opened for active members.",
        )
    form = await request.form()
    row = request.state.portal_session
    if row is None or not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)

    account_type = (form.get("account_type") or "checking").strip()
    errors: list[str] = []
    type_map = {"checking": "CK", "savings": "SV"}
    if account_type not in type_map:
        errors.append("Select a valid account type.")

    if errors:
        return render(
            request,
            "account_new.html",
            member=member,
            account_type=account_type,
            errors=errors,
        )

    existing_ids = [row[0] for row in db.query(Account.id).all()]
    account_id = next_account_id(existing_ids, type_map[account_type])
    account = Account(
        id=account_id,
        member_id=member.id,
        account_type=account_type,
        status="active",
        currency="USD",
        balance_cents=0,
    )
    db.add(account)
    db.flush()
    flash = f"Account opened. {account.id}"
    return RedirectResponse(
        f"/members/{member.id}?flash={quote(flash)}",
        status_code=303,
    )


@router.get("/members/{member_id}/cheque-books/new")
async def cheque_book_new_form(request: Request, member_id: str):
    db = request.state.db
    member = db.get(Member, member_id)
    forbidden = _cheque_book_forbidden(request, member)
    if forbidden is not None:
        return forbidden

    fee_accounts = _fee_debit_accounts(db, member.id)
    checking = _active_checking_accounts(db, member.id)
    default_fee_id = checking[0].id if checking else (fee_accounts[0].id if fee_accounts else "")
    return render(
        request,
        "cheque_book_new.html",
        member=member,
        book_type="standard",
        book_types=_cheque_book_type_options(),
        fee_account_id=default_fee_id,
        fee_accounts=fee_accounts,
        errors=[],
    )


@router.post("/members/{member_id}/cheque-books/new")
async def cheque_book_new_submit(request: Request, member_id: str):
    db = request.state.db
    member = db.get(Member, member_id)
    forbidden = _cheque_book_forbidden(request, member)
    if forbidden is not None:
        return forbidden

    form = await request.form()
    row = request.state.portal_session
    if row is None or not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)

    book_type = (form.get("book_type") or "").strip()
    fee_account_id = (form.get("fee_account_id") or "").strip()
    fee_accounts = _fee_debit_accounts(db, member.id)
    fee_account_ids = {item.id for item in fee_accounts}
    checking = _active_checking_accounts(db, member.id)
    default_fee_id = checking[0].id if checking else (fee_accounts[0].id if fee_accounts else "")
    errors: list[str] = []

    type_info = CHEQUE_BOOK_TYPES.get(book_type)
    if type_info is None:
        errors.append("Select a valid cheque book type.")
        book_type = "standard"
        type_info = CHEQUE_BOOK_TYPES[book_type]

    fee_account = None
    if fee_account_id not in fee_account_ids:
        errors.append("Select a valid fee debit account.")
        fee_account_id = default_fee_id
    else:
        fee_account = next(item for item in fee_accounts if item.id == fee_account_id)

    if errors:
        return render(
            request,
            "cheque_book_new.html",
            member=member,
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
            member=member,
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
    flash = (
        f"Cheque book ordered. Debited {format_money(fee_cents)} "
        f"from {fee_account.id}. {transaction.id}"
    )
    return RedirectResponse(
        f"/members/{member.id}?flash={quote(flash)}",
        status_code=303,
    )
