from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.middleware import csrf_forbidden
from app.security import (
    create_session,
    invalidate_session,
    require_csrf,
    safe_next_url,
    set_session_cookie,
    verify_password,
)
from app.templating import render
from app.models import Employee

router = APIRouter()


@router.get("/login")
async def login_form(request: Request):
    settings = request.app.state.settings
    db = request.state.db
    if request.state.employee is not None:
        return RedirectResponse(safe_next_url(request.query_params.get("next")), status_code=303)
    row = request.state.portal_session
    if row is None:
        row = create_session(db, settings, None)
        request.state.portal_session = row
        request.state.csrf_token = row.csrf_token
    response = render(
        request,
        "login.html",
        error=None,
        next_url=request.query_params.get("next") or "/",
    )
    set_session_cookie(response, row.id, settings)
    return response


@router.post("/login")
async def login_submit(request: Request):
    settings = request.app.state.settings
    db = request.state.db
    form = await request.form()
    row = request.state.portal_session
    if row is None:
        row = create_session(db, settings, None)
        request.state.portal_session = row
        request.state.csrf_token = row.csrf_token
    if not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)

    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    next_url = safe_next_url(form.get("next") or request.query_params.get("next"))
    employee = db.query(Employee).filter(Employee.username == username).one_or_none()
    if employee is None or not verify_password(password, employee.password_hash):
        response = render(
            request,
            "login.html",
            error="The username or password is incorrect.",
            next_url=next_url,
        )
        set_session_cookie(response, row.id, settings)
        return response

    row.employee_id = employee.id
    from app.security import new_token

    row.csrf_token = new_token()
    request.state.employee = employee
    request.state.csrf_token = row.csrf_token
    response = RedirectResponse(next_url, status_code=303)
    set_session_cookie(response, row.id, settings)
    return response


@router.post("/logout")
async def logout(request: Request):
    db = request.state.db
    form = await request.form()
    row = request.state.portal_session
    if row is None or not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)
    invalidate_session(db, row)
    response = RedirectResponse("/login", status_code=303)
    from app.security import clear_session_cookie

    clear_session_cookie(response)
    return response
