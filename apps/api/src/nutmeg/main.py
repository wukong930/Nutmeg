import uvicorn
from fastapi import FastAPI

from nutmeg.api.router import api_router
from nutmeg.config import get_settings
from nutmeg.v4.api import v4_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Nutmeg API",
        version="0.1.0",
        description="Milestone 1 backend skeleton for Nutmeg V2.",
    )
    app.state.settings = settings
    # Legacy V1 routes (preserved during migration)
    app.include_router(api_router, prefix="/api/v1")
    # V4 routes (production-track redesign; uses the trained artifact)
    app.include_router(v4_router, prefix="/api")
    return app


app = create_app()


def run() -> None:
    uvicorn.run("nutmeg.main:app", host="0.0.0.0", port=8000, reload=True)
