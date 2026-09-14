from fastapi import APIRouter, Request
from sqlalchemy import func, or_

from app.models import Member
from app.templating import render

router = APIRouter()


@router.get("/")
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
    return render(request, "member.html", member=member, accounts=accounts)
