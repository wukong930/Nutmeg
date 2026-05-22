"""V4 FastAPI routers (core + observation)."""
from fastapi import APIRouter

from nutmeg.v4.api.observation_routes import router as observation_router
from nutmeg.v4.api.routes import clear_artifact_cache, get_artifact
from nutmeg.v4.api.routes import router as core_router


# Composite router that mounts both
v4_router = APIRouter()
v4_router.include_router(core_router)
v4_router.include_router(observation_router)

__all__ = ["v4_router", "core_router", "observation_router",
            "clear_artifact_cache", "get_artifact"]
