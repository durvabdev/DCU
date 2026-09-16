from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.database import init_engine
from app.middleware import NoStoreMiddleware, PortalMiddleware
from app.routers import accounts, auth, loans, members, notes, scenarios
from app.templating import BASE_DIR, render


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    init_engine(settings.database_url)

    app = FastAPI(
        title="Dough Credit Union — Member Services Portal",
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.add_middleware(PortalMiddleware)
    app.add_middleware(NoStoreMiddleware)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    app.include_router(auth.router)
    app.include_router(members.router)
    app.include_router(loans.router)
    app.include_router(accounts.router)
    app.include_router(notes.router)
    app.include_router(scenarios.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return render(
                request,
                "error.html",
                status_code=404,
                title="Not found",
                message="The requested page does not exist.",
            )
        return render(
            request,
            "error.html",
            status_code=exc.status_code,
            title="Request could not be completed",
            message=str(exc.detail) if exc.detail else "Something went wrong.",
        )

    @app.get("/favicon.ico")
    async def favicon():
        return RedirectResponse("/static/favicon.svg", status_code=303)

    return app


app = create_app()
