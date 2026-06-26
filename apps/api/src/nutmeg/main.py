import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from nutmeg.config import get_settings
from nutmeg.v4.api import v4_router
from nutmeg.v4.api.admin import admin_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Nutmeg API",
        version="0.5.0",
        description="Nutmeg V5 — GBM-lambda + Dixon-Coles football prediction backend.",
    )
    app.state.settings = settings
    app.include_router(v4_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")  # 个人中心 — /api/v4/admin/*

    # V10 W1 polish: convenience redirects so visiting the bare host
    # lands on the dashboard instead of a 404. Without this, users see
    # a confusing "Not Found" at http://localhost:8000/.
    @app.get("/", include_in_schema=False)
    def _root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/api/v4/dashboard", status_code=302)

    @app.get("/favicon.ico", include_in_schema=False)
    def _favicon_redirect() -> RedirectResponse:
        # Reuse the SVG icon already served at /api/v4/icon.svg (P1#14)
        return RedirectResponse(url="/api/v4/icon.svg", status_code=302)

    return app


app = create_app()


def run() -> None:
    uvicorn.run("nutmeg.main:app", host="0.0.0.0", port=8000, reload=True)
