from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.utils import format_datetime, format_money

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.autoescape = True
templates.env.filters["money"] = format_money
templates.env.filters["datetime"] = format_datetime


def render(request: Request, template_name: str, status_code: int = 200, **context):
    context.setdefault("employee", getattr(request.state, "employee", None))
    context.setdefault("csrf_token", getattr(request.state, "csrf_token", ""))
    settings: Settings = request.app.state.settings
    context.setdefault("dev_scenarios_enabled", settings.dev_scenarios_enabled)
    context.setdefault("flash", context.get("flash"))
    context.setdefault("now", datetime.now(timezone.utc))
    return templates.TemplateResponse(
        request,
        template_name,
        context,
        status_code=status_code,
    )
