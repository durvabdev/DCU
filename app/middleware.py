from fastapi import Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.models import Employee
from app.security import (
    default_flags,
    get_session_row,
    invalidate_session,
    load_flags,
    redirect_to_login,
)
from app.templating import render


class NoStoreMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            return response
        response.headers["Cache-Control"] = "no-store"
        return response

PUBLIC_PATHS = {"/login"}
PUBLIC_PREFIXES = ("/static", "/favicon.ico")


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


class PortalMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        from app.database import SessionLocal

        settings = request.app.state.settings
        db: Session = SessionLocal()
        request.state.db = db
        request.state.settings = settings
        path = request.url.path

        try:
            if path.startswith("/dev") and not settings.dev_scenarios_enabled:
                request.state.portal_session = None
                request.state.employee = None
                request.state.csrf_token = ""
                request.state.flags = default_flags()
                response = await call_next(request)
                db.commit()
                return response

            row = get_session_row(db, request, settings)
            flags = default_flags()
            employee = None
            if row is not None:
                flags = load_flags(row)
                expire_now = (
                    flags.get("expire_next")
                    and row.employee_id
                    and not _is_public(path)
                    and not (request.method == "GET" and path.startswith("/dev/scenarios"))
                )
                if expire_now:
                    invalidate_session(db, row)
                    db.commit()
                    return redirect_to_login(request)
                if row.employee_id:
                    employee = db.get(Employee, row.employee_id)

            request.state.portal_session = row
            request.state.flags = flags
            request.state.employee = employee
            request.state.csrf_token = row.csrf_token if row else ""

            if not _is_public(path) and employee is None:
                db.commit()
                return redirect_to_login(request)

            response = await call_next(request)
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def csrf_forbidden(request: Request):
    return render(
        request,
        "error.html",
        status_code=403,
        title="Unable to submit form",
        message="This form could not be verified. Return to the previous page and try again.",
    )
