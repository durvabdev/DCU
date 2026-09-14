from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import quote, urlparse

import bcrypt
from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Employee, PortalSession
from app.utils import utcnow

COOKIE_NAME = "msp_session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def sign_session_id(session_id: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), session_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{session_id}.{digest}"


def unsign_session_id(value: str | None, secret: str) -> str | None:
    if not value or "." not in value:
        return None
    session_id, digest = value.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), session_id.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        return None
    return session_id


def new_token() -> str:
    return secrets.token_urlsafe(32)


def default_flags() -> dict[str, Any]:
    return {
        "expire_next": False,
        "slow_seconds": None,
        "temp_error_next": False,
        "rename_apply_filters": False,
        "uncertain_note_next": False,
        "pending_note": None,
    }


def load_flags(row: PortalSession) -> dict[str, Any]:
    flags = default_flags()
    try:
        stored = json.loads(row.flags_json or "{}")
    except json.JSONDecodeError:
        stored = {}
    flags.update(stored)
    return flags


def save_flags(row: PortalSession, flags: dict[str, Any]) -> None:
    row.flags_json = json.dumps(flags)


def set_session_cookie(response, session_id: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        sign_session_id(session_id, settings.session_secret),
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def create_session(db: Session, settings: Settings, employee_id: str | None = None) -> PortalSession:
    now = utcnow()
    row = PortalSession(
        id=new_token(),
        employee_id=employee_id,
        csrf_token=new_token(),
        created_at=now,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        flags_json=json.dumps(default_flags()),
    )
    db.add(row)
    db.flush()
    return row


def _as_utc(value):
    from datetime import timezone

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_session_row(db: Session, request: Request, settings: Settings) -> PortalSession | None:
    raw = request.cookies.get(COOKIE_NAME)
    session_id = unsign_session_id(raw, settings.session_secret)
    if not session_id:
        return None
    row = db.get(PortalSession, session_id)
    if row is None:
        return None
    if _as_utc(row.expires_at) <= utcnow():
        db.delete(row)
        db.flush()
        return None
    return row


def invalidate_session(db: Session, row: PortalSession | None) -> None:
    if row is not None:
        db.delete(row)
        db.flush()


def login_redirect_url(request: Request) -> str:
    if request.method == "GET":
        next_url = str(request.url.replace(scheme="", netloc=""))
        if not next_url.startswith("/"):
            next_url = request.url.path
        if next_url.startswith("/login"):
            next_url = "/"
        return f"/login?next={quote(next_url, safe='/?=&')}"

    referer = request.headers.get("referer") or ""
    parsed = urlparse(referer)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if not path.startswith("/") or path.startswith("/login") or path.startswith("//"):
        path = "/"
    return f"/login?next={quote(path, safe='/?=&')}"


def safe_next_url(value: str | None) -> str:
    if not value:
        return "/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return "/"
    path = parsed.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    if path.startswith("/login"):
        return "/"
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path


def redirect_to_login(request: Request) -> RedirectResponse:
    response = RedirectResponse(login_redirect_url(request), status_code=303)
    clear_session_cookie(response)
    return response


def require_csrf(request: Request, session_row: PortalSession, form_token: str | None) -> bool:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return True
    if not form_token:
        return False
    return hmac.compare_digest(form_token, session_row.csrf_token)


def attach_session_state(
    request: Request,
    db: Session,
    settings: Settings,
    *,
    allow_anonymous: bool = False,
) -> RedirectResponse | None:
    row = get_session_row(db, request, settings)
    if row is not None:
        flags = load_flags(row)
        if flags.get("expire_next") and row.employee_id:
            invalidate_session(db, row)
            request.state.portal_session = None
            request.state.employee = None
            request.state.csrf_token = ""
            request.state.flags = default_flags()
            return redirect_to_login(request)
        request.state.portal_session = row
        request.state.csrf_token = row.csrf_token
        request.state.flags = flags
        request.state.employee = db.get(Employee, row.employee_id) if row.employee_id else None
        if request.state.employee is None and not allow_anonymous:
            return redirect_to_login(request)
        return None

    request.state.portal_session = None
    request.state.employee = None
    request.state.csrf_token = ""
    request.state.flags = default_flags()
    if allow_anonymous:
        return None
    return redirect_to_login(request)
