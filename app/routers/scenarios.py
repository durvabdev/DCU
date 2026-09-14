from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.middleware import csrf_forbidden
from app.security import load_flags, require_csrf, save_flags
from app.seed import reset_with_session
from app.templating import render

router = APIRouter()


@router.get("/dev/scenarios")
async def scenarios_page(request: Request):
    if not request.app.state.settings.dev_scenarios_enabled:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Not found",
            message="The requested page does not exist.",
        )
    flags = load_flags(request.state.portal_session)
    return render(request, "scenarios.html", flags=flags, flash=request.query_params.get("flash"))


@router.post("/dev/scenarios")
async def scenarios_action(request: Request):
    if not request.app.state.settings.dev_scenarios_enabled:
        return render(
            request,
            "error.html",
            status_code=404,
            title="Not found",
            message="The requested page does not exist.",
        )
    db = request.state.db
    form = await request.form()
    row = request.state.portal_session
    if row is None or not require_csrf(request, row, form.get("csrf_token")):
        return csrf_forbidden(request)

    action = form.get("action")
    flags = load_flags(row)
    flash = "Scenario updated."

    if action == "expire":
        flags["expire_next"] = True
        flash = "Session expiry queued. Opening any other member-services page will require sign-in."
    elif action == "slow":
        raw = (form.get("slow_seconds") or "3").strip()
        try:
            seconds = int(raw)
        except ValueError:
            seconds = 0
        if seconds < 1 or seconds > 30:
            flags = load_flags(row)
            return render(
                request,
                "scenarios.html",
                flags=flags,
                flash=None,
                error="Enter a delay between 1 and 30 seconds.",
            )
        flags["slow_seconds"] = seconds
        flash = f"The next transaction search will wait {seconds} seconds before returning."
    elif action == "temp-error":
        flags["temp_error_next"] = True
        flash = "The next transaction search will fail once and offer a Retry action."
    elif action == "ui-variation":
        flags["rename_apply_filters"] = not flags.get("rename_apply_filters")
        if flags["rename_apply_filters"]:
            flash = "Apply Filters will be labeled Search Transactions for this session."
        else:
            flash = "Filter button label restored to Apply Filters."
    elif action == "uncertain-note":
        flags["uncertain_note_next"] = True
        flash = "The next note confirmation will save the note, then show an interrupted response."
    elif action == "reset":
        preserved = reset_with_session(db, row)
        request.state.portal_session = preserved
        request.state.csrf_token = preserved.csrf_token if preserved else ""
        flash = "Demonstration data was deleted and restored from the seed. Scenario flags were cleared."
        return RedirectResponse(f"/dev/scenarios?flash={quote(flash)}", status_code=303)
    else:
        flash = "Choose a scenario control."

    save_flags(row, flags)
    return RedirectResponse(f"/dev/scenarios?flash={quote(flash)}", status_code=303)
