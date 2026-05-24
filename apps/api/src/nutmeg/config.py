"""Application settings.

Reads env vars with the `NUTMEG_` prefix; auto-loads from a project-root
`.env` file (gitignored) on startup. CLI tools that depend on third-party
credentials (V6 W1+ API-Football) should call ``get_settings()`` and read
fields rather than touching ``os.environ`` directly so the .env fallback
works uniformly.

V4 / V5 modules that pre-date this (e.g. `nutmeg.v4.api.routes` reading
`NUTMEG_V4_ARTIFACT_PATH` via os.environ.get) continue to work because
the .env values are also exported to os.environ on import.
"""
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


# Eagerly load .env into os.environ so legacy os.environ.get() readers
# in v4 modules pick up the values too. Idempotent; no-op if .env absent.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NUTMEG_", env_file=".env", extra="ignore")

    env: str = "local"
    competition_config_dir: str = "configs/competitions"
    v4_artifact_path: str = "data/v4_model"
    v4_observation_db: str = "data/v4_observation.db"
    log_level: str = "INFO"

    # V6 W1: API-Football credentials. Stored in `.env` (gitignored) only;
    # never commit. The key is sent as `x-apisports-key` header on each
    # request to api_football_base_url.
    api_football_key: str | None = None
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_timeout_seconds: float = 15.0

    # post-v9 P1#20: The Odds API ($30/mo Starter tier). Used by
    # nutmeg.v4.data.sources.odds_api to backfill UCL/UEL historical
    # closing odds — the data set V8 W4 documented API-Football couldn't
    # provide. Sent as `?apiKey=...` query param (not header).
    odds_api_key: str | None = None
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    odds_api_timeout_seconds: float = 20.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
