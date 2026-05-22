from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.config import Settings

ProviderDryRunMode = Literal["local_only", "mock_sample", "real_provider", "blocked"]
ProviderCommitMode = Literal["not_applicable", "ready", "blocked"]
ProviderAdapterStatus = Literal["supported_now", "adapter_planned"]
ProviderFreeTierFit = Literal["good_for_first_dry_run", "trial_required", "limited_for_soccer"]


class ProviderRuntimeCredentialRecord(BaseModel):
    provider_name: str
    capabilities: list[str] = Field(default_factory=list)
    api_key_env_var: str | None = None
    runtime_env_var: str | None = None
    key_configured: bool
    dry_run_mode: ProviderDryRunMode
    commit_mode: ProviderCommitMode
    safe_to_call_real_provider: bool
    mock_dry_run_enabled: bool
    requires_api_key_for_commit: bool
    next_action: str
    notes: list[str] = Field(default_factory=list)


class ProviderRuntimeCredentialResponse(BaseModel):
    items: list[ProviderRuntimeCredentialRecord]
    mock_dry_run_enabled: bool
    generated_at_utc: datetime
    stale: bool = False
    fallback_used: bool = False


class ProviderApiKeyChecklistItem(BaseModel):
    provider_name: str
    nutmeg_role: str
    priority: int = Field(ge=1)
    adapter_status: ProviderAdapterStatus
    required_env_var: str
    key_configured: bool
    apply_url: str
    docs_url: str
    official_free_tier_note: str
    free_tier_fit: ProviderFreeTierFit
    operator_action: str
    source_checked_at_utc: datetime


class ProviderApiKeyChecklistResponse(BaseModel):
    items: list[ProviderApiKeyChecklistItem]
    generated_at_utc: datetime
    stale: bool = False
    fallback_used: bool = False


def build_provider_runtime_credential_response(
    settings: Settings,
    *,
    generated_at_utc: datetime | None = None,
) -> ProviderRuntimeCredentialResponse:
    return ProviderRuntimeCredentialResponse(
        items=[
            _mock_local_record(settings),
            _external_provider_record(
                provider_name="football-data.org",
                capabilities=["competitions", "seasons", "fixtures", "results"],
                api_key_env_var="FOOTBALL_DATA_API_KEY",
                runtime_env_var="NUTMEG_FOOTBALL_DATA_API_KEY",
                api_key=settings.football_data_api_key,
                settings=settings,
            ),
            _external_provider_record(
                provider_name="the-odds-api",
                capabilities=["odds"],
                api_key_env_var="THE_ODDS_API_KEY",
                runtime_env_var="NUTMEG_THE_ODDS_API_KEY",
                api_key=settings.the_odds_api_key,
                settings=settings,
            ),
            _external_provider_record(
                provider_name="api-football",
                capabilities=["competitions", "seasons", "fixtures", "results"],
                api_key_env_var="API_FOOTBALL_API_KEY",
                runtime_env_var="NUTMEG_API_FOOTBALL_API_KEY",
                api_key=settings.api_football_api_key,
                settings=settings,
            ),
            _external_provider_record(
                provider_name="sportmonks",
                capabilities=["fixtures", "results", "odds", "lineups", "injuries"],
                api_key_env_var="SPORTMONKS_API_KEY",
                runtime_env_var="NUTMEG_SPORTMONKS_API_KEY",
                api_key=settings.sportmonks_api_key,
                settings=settings,
            ),
        ],
        mock_dry_run_enabled=settings.provider_sync_mock_dry_run_enabled,
        generated_at_utc=generated_at_utc or datetime.now(UTC),
    )


def build_provider_api_key_checklist_response(
    settings: Settings,
    *,
    generated_at_utc: datetime | None = None,
) -> ProviderApiKeyChecklistResponse:
    checked_at = datetime(2026, 5, 7, tzinfo=UTC)
    return ProviderApiKeyChecklistResponse(
        items=[
            ProviderApiKeyChecklistItem(
                provider_name="football-data.org",
                nutmeg_role="fixtures_results_first_real_dry_run",
                priority=1,
                adapter_status="supported_now",
                required_env_var="NUTMEG_FOOTBALL_DATA_API_KEY",
                key_configured=bool(settings.football_data_api_key),
                apply_url="https://www.football-data.org/client/register",
                docs_url="https://docs.football-data.org/general/v4/policies.html",
                official_free_tier_note=(
                    "Free registered clients are suitable for initial "
                    "fixtures/results dry-runs, subject to request limits."
                ),
                free_tier_fit="good_for_first_dry_run",
                operator_action="apply_free_key_then_set_nutmeg_football_data_api_key",
                source_checked_at_utc=checked_at,
            ),
            ProviderApiKeyChecklistItem(
                provider_name="api-football",
                nutmeg_role="broad_fixture_result_provider_candidate",
                priority=2,
                adapter_status="supported_now",
                required_env_var="NUTMEG_API_FOOTBALL_API_KEY",
                key_configured=bool(settings.api_football_api_key),
                apply_url="https://dashboard.api-football.com/register",
                docs_url="https://www.api-football.com/documentation-v3",
                official_free_tier_note=(
                    "Free API-SPORTS/API-Football access is useful for "
                    "coverage research and fallback fixture mapping dry-runs."
                ),
                free_tier_fit="good_for_first_dry_run",
                operator_action="apply_free_key_then_set_nutmeg_api_football_api_key",
                source_checked_at_utc=checked_at,
            ),
            ProviderApiKeyChecklistItem(
                provider_name="sportmonks",
                nutmeg_role="lineups_injuries_broad_coverage_candidate",
                priority=3,
                adapter_status="supported_now",
                required_env_var="NUTMEG_SPORTMONKS_API_KEY",
                key_configured=bool(settings.sportmonks_api_key),
                apply_url="https://my.sportmonks.com/register",
                docs_url="https://docs.sportmonks.com/football",
                official_free_tier_note=(
                    "SportMonks is typically trial/plan based; use a free "
                    "trial key first for lineup and injury dry-runs."
                ),
                free_tier_fit="trial_required",
                operator_action="apply_trial_key_then_set_nutmeg_sportmonks_api_key",
                source_checked_at_utc=checked_at,
            ),
            ProviderApiKeyChecklistItem(
                provider_name="the-odds-api",
                nutmeg_role="odds_market_snapshot_candidate",
                priority=4,
                adapter_status="supported_now",
                required_env_var="NUTMEG_THE_ODDS_API_KEY",
                key_configured=bool(settings.the_odds_api_key),
                apply_url="https://the-odds-api.com/",
                docs_url="https://the-odds-api.com/liveapi/guides/v4/",
                official_free_tier_note=(
                    "The free tier is useful for API-key plumbing, but current "
                    "free sports coverage may not include soccer EPL odds."
                ),
                free_tier_fit="limited_for_soccer",
                operator_action="apply_free_key_but_expect_soccer_odds_limitations",
                source_checked_at_utc=checked_at,
            ),
        ],
        generated_at_utc=generated_at_utc or datetime.now(UTC),
    )


def _mock_local_record(settings: Settings) -> ProviderRuntimeCredentialRecord:
    return ProviderRuntimeCredentialRecord(
        provider_name="mock-local",
        capabilities=[
            "fixtures",
            "results",
            "odds",
            "lineups",
            "injuries",
        ],
        api_key_env_var=None,
        runtime_env_var=None,
        key_configured=True,
        dry_run_mode="local_only",
        commit_mode="not_applicable",
        safe_to_call_real_provider=False,
        mock_dry_run_enabled=settings.provider_sync_mock_dry_run_enabled,
        requires_api_key_for_commit=False,
        next_action="available_for_deterministic_local_testing",
        notes=[
            "deterministic_local_provider",
            "no_external_request",
        ],
    )


def _external_provider_record(
    *,
    provider_name: str,
    capabilities: list[str],
    api_key_env_var: str,
    runtime_env_var: str,
    api_key: str | None,
    settings: Settings,
) -> ProviderRuntimeCredentialRecord:
    key_configured = bool(api_key)
    if key_configured:
        dry_run_mode: ProviderDryRunMode = "real_provider"
        commit_mode: ProviderCommitMode = "ready"
        next_action = "ready_for_real_provider_dry_run"
        notes = [
            "key_presence_verified",
            "secret_value_not_exposed",
        ]
    elif settings.provider_sync_mock_dry_run_enabled:
        dry_run_mode = "mock_sample"
        commit_mode = "blocked"
        next_action = "apply_api_key_before_real_provider_sync"
        notes = [
            "dry_run_uses_deterministic_sample",
            "commit_sync_requires_api_key",
        ]
    else:
        dry_run_mode = "blocked"
        commit_mode = "blocked"
        next_action = "apply_api_key_before_provider_dry_run"
        notes = [
            "provider_key_missing",
            "mock_dry_run_disabled",
        ]

    return ProviderRuntimeCredentialRecord(
        provider_name=provider_name,
        capabilities=capabilities,
        api_key_env_var=api_key_env_var,
        runtime_env_var=runtime_env_var,
        key_configured=key_configured,
        dry_run_mode=dry_run_mode,
        commit_mode=commit_mode,
        safe_to_call_real_provider=key_configured,
        mock_dry_run_enabled=settings.provider_sync_mock_dry_run_enabled,
        requires_api_key_for_commit=True,
        next_action=next_action,
        notes=notes,
    )
