from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

type AccuracyRepositoryMode = Literal["mock", "postgres"]
type ProviderGovernanceRepositoryMode = Literal["mock", "postgres"]
type ParlayRepositoryMode = Literal["mock", "postgres"]
type RecommendationRepositoryMode = Literal["mock", "postgres"]
type ProviderRuntimeIncidentNotificationAdapter = Literal["provider_ops", "webhook"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NUTMEG_", env_file=".env", extra="ignore")

    env: str = "local"
    database_url: str = "postgresql://nutmeg:nutmeg@localhost:5432/nutmeg"
    database_connect_timeout_seconds: int = 3
    redis_url: str = "redis://localhost:6379/0"
    competition_config_dir: str = "configs/competitions"
    accuracy_repository: AccuracyRepositoryMode = "mock"
    accuracy_jobs_enabled: bool = False
    provider_governance_repository: ProviderGovernanceRepositoryMode = "mock"
    parlay_repository: ParlayRepositoryMode = "mock"
    recommendation_repository: RecommendationRepositoryMode = "mock"
    admin_api_token: str | None = None
    provider_sync_enabled: bool = False
    provider_sync_workflow_enabled: bool = False
    provider_sync_mock_dry_run_enabled: bool = False
    prediction_jobs_enabled: bool = False
    prematch_workflow_enabled: bool = False
    football_data_api_key: str | None = None
    football_data_api_base_url: str = "https://api.football-data.org/v4"
    football_data_api_timeout_seconds: int = 10
    api_football_api_key: str | None = None
    api_football_api_base_url: str = "https://v3.football.api-sports.io"
    api_football_api_timeout_seconds: int = 10
    the_odds_api_key: str | None = None
    the_odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    the_odds_api_timeout_seconds: int = 10
    sportmonks_api_key: str | None = None
    sportmonks_api_base_url: str = "https://api.sportmonks.com/v3"
    sportmonks_api_timeout_seconds: int = 10
    provider_runtime_latency_p2_ms: int = Field(default=1500, ge=0)
    provider_runtime_latency_p1_ms: int = Field(default=5000, ge=0)
    provider_runtime_error_rate_p1: float = Field(default=1.0, ge=0.0, le=1.0)
    provider_runtime_plan_limit_p2: float = Field(default=0.5, ge=0.0, le=1.0)
    provider_runtime_fallback_usage_rate_p1: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )
    provider_runtime_incident_retention_days: int = Field(default=90, ge=1, le=3650)
    provider_runtime_incident_notification_enabled: bool = False
    provider_runtime_incident_notification_adapter: (
        ProviderRuntimeIncidentNotificationAdapter
    ) = "provider_ops"
    provider_runtime_incident_notification_dry_run: bool = True
    provider_runtime_incident_notification_webhook_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
