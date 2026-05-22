"""V5 minimal app settings.

V4 modules read os.environ directly for runtime knobs (e.g. NUTMEG_V4_ARTIFACT_PATH,
NUTMEG_V4_OBSERVATION_DB). This module exists so nutmeg.main can expose a typed
settings object on app.state and so future env vars can be added cleanly.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NUTMEG_", env_file=".env", extra="ignore")

    env: str = "local"
    competition_config_dir: str = "configs/competitions"
    v4_artifact_path: str = "data/v4_model"
    v4_observation_db: str = "data/v4_observation.db"
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
