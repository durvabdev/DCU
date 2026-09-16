from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_

from app.middleware import csrf_forbidden
from app.models import Account, Member
from app.security import require_csrf
from app.templating import render
from app.utils import next_account_id

router = APIRouter()


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
    return RedirectResponse(f"/accounts/{account.id}", status_code=303)
