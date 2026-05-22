import uvicorn
from fastapi import FastAPI

from nutmeg.config import get_settings
from nutmeg.v4.api import v4_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Nutmeg API",
        version="0.5.0",
        description="Nutmeg V5 — GBM-lambda + Dixon-Coles football prediction backend.",
    )
    app.state.settings = settings
    app.include_router(v4_router, prefix="/api")
    return app


app = create_app()


def run() -> None:
    uvicorn.run("nutmeg.main:app", host="0.0.0.0", port=8000, reload=True)
