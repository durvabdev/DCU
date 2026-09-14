from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from app.middleware import csrf_forbidden
from app.models import InvestigationNote, Transaction
from app.security import load_flags, new_token, require_csrf, save_flags
from app.templating import render
from app.utils import NOTE_CATEGORIES, utcnow

router = APIRouter()


def _save_note(db, transaction_id: str, author_id: str, body: str, category: str, token: str):
    existing = db.execute(
        select(InvestigationNote).where(InvestigationNote.idempotency_token == token)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    count = db.scalar(select(func.count()).select_from(InvestigationNote)) or 0
    note = InvestigationNote(
        id=f"NT-{count + 1:06d}",
        transaction_id=transaction_id,
        author_id=author_id,
        body=body,
        category=category,
        created_at=utcnow(),
        idempotency_token=token,
    )
    db.add(note)
    db.flush()
    return note, True


def _pending_from_session(flags: dict, transaction_id: str) -> dict | None:
    pending = flags.get("pending_note") or None
    if not pending or pending.get("transaction_id") != transaction_id:
        return None
    return pending


@router.get("/transactions/{transaction_id}/notes/new")
async def note_form(request: Request, transaction_id: str):
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
    if transaction.account.status != "active":
        return render(
            request,
            "error.html",
            status_code=403,
            title="Account is not active",
            message="Investigation notes cannot be added on an inactive account.",
        )

    flags = load_flags(request.state.portal_session)
    pending = _pending_from_session(flags, transaction_id)
    if pending is None:
        pending = {
            "transaction_id": transaction_id,
            "idempotency_token": new_token(),
            "body": "",
            "category": NOTE_CATEGORIES[0],
        }
        flags["pending_note"] = pending
        save_flags(request.state.portal_session, flags)

    return_to = request.query_params.get("return_to") or pending.get("return_to") or ""
    pending["return_to"] = return_to
    flags["pending_note"] = pending
    save_flags(request.state.portal_session, flags)

    return render(
        request,
        "note_form.html",
        transaction=transaction,
        account=transaction.account,
        member=transaction.account.member,
        token=pending["idempotency_token"],
        body=pending.get("body") or "",
        category=pending.get("category") or NOTE_CATEGORIES[0],
        categories=NOTE_CATEGORIES,
        errors=[],
        return_to=return_to,
    )


@router.post("/transactions/{transaction_id}/notes/review")
async def note_review(request: Request, transaction_id: str):
    db = request.state.db
    form = await request.form()
    row = request.state.portal_session
    if not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Transaction not found",
            message="No transaction exists with that ID.",
        )
    if transaction.account.status != "active":
        return render(
            request,
            "error.html",
            status_code=403,
            title="Account is not active",
            message="Investigation notes cannot be added on an inactive account.",
        )

    flags = load_flags(row)
    pending = _pending_from_session(flags, transaction_id) or {}
    token = form.get("idempotency_token") or pending.get("idempotency_token") or new_token()
    body = (form.get("body") or "").strip()
    category = (form.get("category") or "").strip()
    return_to = form.get("return_to") or pending.get("return_to") or ""
    errors = []
    if not body:
        errors.append("Enter an investigation note.")
    elif len(body) > 1000:
        errors.append("Investigation notes cannot exceed 1,000 characters.")
    if category not in NOTE_CATEGORIES:
        errors.append("Select a valid category.")

    pending = {
        "transaction_id": transaction_id,
        "idempotency_token": token,
        "body": body,
        "category": category,
        "return_to": return_to,
    }
    flags["pending_note"] = pending
    save_flags(row, flags)

    if errors:
        return render(
            request,
            "note_form.html",
            transaction=transaction,
            account=transaction.account,
            member=transaction.account.member,
            token=token,
            body=body,
            category=category or NOTE_CATEGORIES[0],
            categories=NOTE_CATEGORIES,
            errors=errors,
            return_to=return_to,
        )

    return render(
        request,
        "note_review.html",
        transaction=transaction,
        account=transaction.account,
        member=transaction.account.member,
        token=token,
        body=body,
        category=category,
        return_to=return_to,
    )


@router.post("/transactions/{transaction_id}/notes/confirm")
async def note_confirm(request: Request, transaction_id: str):
    db = request.state.db
    form = await request.form()
    row = request.state.portal_session
    if not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Transaction not found",
            message="No transaction exists with that ID.",
        )

    flags = load_flags(row)
    pending = _pending_from_session(flags, transaction_id)
    token = form.get("idempotency_token") or (pending or {}).get("idempotency_token")
    body = (form.get("body") or (pending or {}).get("body") or "").strip()
    category = (form.get("category") or (pending or {}).get("category") or "").strip()
    return_to = form.get("return_to") or (pending or {}).get("return_to") or ""
    if not token or not body or category not in NOTE_CATEGORIES:
        return RedirectResponse(f"/transactions/{transaction_id}/notes/new", status_code=303)

    note, _created = _save_note(
        db,
        transaction_id=transaction_id,
        author_id=request.state.employee.id,
        body=body,
        category=category,
        token=token,
    )

    if flags.get("uncertain_note_next"):
        flags["uncertain_note_next"] = False
        flags["pending_note"] = {
            "transaction_id": transaction_id,
            "idempotency_token": token,
            "body": body,
            "category": category,
            "return_to": return_to,
        }
        save_flags(row, flags)
        return render(
            request,
            "note_interrupted.html",
            transaction=transaction,
            account=transaction.account,
            member=transaction.account.member,
            note=note,
            token=token,
            body=body,
            category=category,
            return_to=return_to,
        )

    flags["pending_note"] = None
    save_flags(row, flags)
    return RedirectResponse(
        f"/transactions/{transaction_id}/notes/{note.id}/success",
        status_code=303,
    )


@router.get("/transactions/{transaction_id}/notes/{note_id}/success")
async def note_success(request: Request, transaction_id: str, note_id: str):
    db = request.state.db
    note = db.get(InvestigationNote, note_id)
    transaction = db.get(Transaction, transaction_id)
    if note is None or transaction is None or note.transaction_id != transaction_id:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Note not found",
            message="That investigation note could not be found.",
        )
    return render(
        request,
        "note_success.html",
        note=note,
        transaction=transaction,
        account=transaction.account,
        member=transaction.account.member,
    )
