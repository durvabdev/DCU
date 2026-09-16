from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes | None:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, OSError):
        return None


def sign_session_payload(payload: str, secret: str) -> str:
    encoded = _b64url(payload.encode("utf-8"))
    digest = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{digest}"


def unsign_session_payload(value: str | None, secret: str) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None
    encoded, digest = value.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        return None
    raw = _b64url_decode(encoded)
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "id" not in data or "csrf_token" not in data:
        return None
    return data


def session_cookie_value(row: PortalSession, secret: str) -> str:
    payload = json.dumps(
        {
            "id": row.id,
            "employee_id": row.employee_id,
            "csrf_token": row.csrf_token,
            "created_at": _as_utc(row.created_at).isoformat(),
            "expires_at": _as_utc(row.expires_at).isoformat(),
        },
        separators=(",", ":"),
    )
    return sign_session_payload(payload, secret)


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


def set_session_cookie(response, row: PortalSession, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        session_cookie_value(row, settings.session_secret),
        httponly=True,
        samesite="lax",
        secure=os.environ.get("VERCEL") == "1",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        secure=os.environ.get("VERCEL") == "1",
        samesite="lax",
    )


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
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_stored_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def get_session_row(db: Session, request: Request, settings: Settings) -> PortalSession | None:
    data = unsign_session_payload(request.cookies.get(COOKIE_NAME), settings.session_secret)
    if not data:
        return None
    try:
        expires_at = _parse_stored_datetime(str(data["expires_at"]))
        created_at = _parse_stored_datetime(str(data.get("created_at") or data["expires_at"]))
    except (KeyError, TypeError, ValueError):
        return None
    if expires_at <= utcnow():
        row = db.get(PortalSession, data["id"])
        if row is not None:
            db.delete(row)
            db.flush()
        return None

    row = db.get(PortalSession, data["id"])
    employee_id = data.get("employee_id") or None
    csrf_token = str(data["csrf_token"])
    if row is None:
        # Serverless SQLite copies do not keep portal_sessions. Rebuild from the cookie.
        row = PortalSession(
            id=str(data["id"]),
            employee_id=employee_id,
            csrf_token=csrf_token,
            created_at=created_at,
            expires_at=expires_at,
            flags_json=json.dumps(default_flags()),
        )
        db.add(row)
        db.flush()
        return row

    row.employee_id = employee_id
    row.csrf_token = csrf_token
    row.expires_at = expires_at
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
