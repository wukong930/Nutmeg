from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from nutmeg.config import Settings
from nutmeg.providers.api_football.adapter import (
    ApiFootballAdapter,
    ApiFootballAdapterError,
    ApiFootballConfig,
    ApiFootballHttpError,
    ApiFootballPlanLimitError,
)
from nutmeg.providers.football_data_org.adapter import (
    FootballDataOrgAdapter,
    FootballDataOrgAdapterError,
    FootballDataOrgConfig,
    FootballDataOrgHttpError,
)
from nutmeg.providers.sportmonks.adapter import (
    SportMonksAdapter,
    SportMonksAdapterError,
    SportMonksConfig,
    SportMonksHttpError,
)
from nutmeg.providers.the_odds_api.adapter import (
    TheOddsApiAdapter,
    TheOddsApiAdapterError,
    TheOddsApiConfig,
    TheOddsApiHttpError,
)

ProviderRuntimeProbeStatus = Literal[
    "not_configured",
    "key_configured",
    "ok",
    "limited",
    "auth_failed",
    "rate_limited",
    "unavailable",
    "adapter_planned",
]


class ProviderRuntimeProbeRecord(BaseModel):
    provider_name: str
    capability: str
    key_configured: bool
    status: ProviderRuntimeProbeStatus
    live_probe: bool
    safe_to_call_real_provider: bool
    message: str
    observed_count: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    checked_at_utc: datetime


class ProviderRuntimeProbeResponse(BaseModel):
    items: list[ProviderRuntimeProbeRecord]
    live_probe: bool
    generated_at_utc: datetime
    stale: bool = False
    fallback_used: bool = False


def build_provider_runtime_probe_response(
    settings: Settings,
    *,
    live: bool = False,
    generated_at_utc: datetime | None = None,
) -> ProviderRuntimeProbeResponse:
    checked_at = generated_at_utc or datetime.now(UTC)
    return ProviderRuntimeProbeResponse(
        items=[
            _timed_probe(
                lambda: _football_data_probe(
                    settings,
                    live=live,
                    checked_at=checked_at,
                )
            ),
            _timed_probe(
                lambda: _the_odds_api_probe(
                    settings,
                    live=live,
                    checked_at=checked_at,
                )
            ),
            _timed_probe(
                lambda: _sportmonks_probe(
                    settings,
                    live=live,
                    checked_at=checked_at,
                )
            ),
            _timed_probe(
                lambda: _api_football_probe(
                    settings,
                    live=live,
                    checked_at=checked_at,
                )
            ),
        ],
        live_probe=live,
        generated_at_utc=checked_at,
    )


def _timed_probe(
    factory: Callable[[], ProviderRuntimeProbeRecord],
) -> ProviderRuntimeProbeRecord:
    started = perf_counter()
    record = factory()
    latency_ms = max(0, int((perf_counter() - started) * 1000))
    return record.model_copy(update={"latency_ms": latency_ms})


def _football_data_probe(
    settings: Settings,
    *,
    live: bool,
    checked_at: datetime,
) -> ProviderRuntimeProbeRecord:
    if not settings.football_data_api_key:
        return _not_configured_record(
            provider_name="football-data.org",
            capability="fixtures_results",
            live=live,
            checked_at=checked_at,
            message="football-data.org key is not configured.",
        )
    if not live:
        return _key_presence_record(
            provider_name="football-data.org",
            capability="fixtures_results",
            checked_at=checked_at,
        )

    adapter = FootballDataOrgAdapter(
        FootballDataOrgConfig(
            api_token=SecretStr(settings.football_data_api_key),
            base_url=settings.football_data_api_base_url,
            timeout_seconds=settings.football_data_api_timeout_seconds,
        )
    )
    try:
        teams = adapter.fetch_competition_teams("PL", season="2025")
    except FootballDataOrgHttpError as exc:
        return _http_error_record(
            provider_name="football-data.org",
            capability="fixtures_results",
            status_code=exc.status_code,
            checked_at=checked_at,
        )
    except FootballDataOrgAdapterError:
        return _unavailable_record(
            provider_name="football-data.org",
            capability="fixtures_results",
            checked_at=checked_at,
        )

    return ProviderRuntimeProbeRecord(
        provider_name="football-data.org",
        capability="fixtures_results",
        key_configured=True,
        status="ok",
        live_probe=True,
        safe_to_call_real_provider=True,
        message="football-data.org EPL team probe succeeded.",
        observed_count=len(teams),
        metadata={"competition": "PL", "season": "2025", "probe": "teams"},
        notes=["secret_value_not_exposed", "low_cost_provider_probe"],
        checked_at_utc=checked_at,
    )


def _the_odds_api_probe(
    settings: Settings,
    *,
    live: bool,
    checked_at: datetime,
) -> ProviderRuntimeProbeRecord:
    if not settings.the_odds_api_key:
        return _not_configured_record(
            provider_name="the-odds-api",
            capability="odds",
            live=live,
            checked_at=checked_at,
            message="The Odds API key is not configured.",
        )
    if not live:
        return _key_presence_record(
            provider_name="the-odds-api",
            capability="odds",
            checked_at=checked_at,
        )

    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(
            api_key=SecretStr(settings.the_odds_api_key),
            base_url=settings.the_odds_api_base_url,
            timeout_seconds=settings.the_odds_api_timeout_seconds,
        )
    )
    try:
        sports = adapter.fetch_sports(include_all=False)
    except TheOddsApiHttpError as exc:
        return _http_error_record(
            provider_name="the-odds-api",
            capability="odds",
            status_code=exc.status_code,
            checked_at=checked_at,
        )
    except TheOddsApiAdapterError:
        return _unavailable_record(
            provider_name="the-odds-api",
            capability="odds",
            checked_at=checked_at,
        )

    sport_keys = {
        str(item.get("key")) for item in sports if isinstance(item.get("key"), str)
    }
    soccer_epl_available = "soccer_epl" in sport_keys
    return ProviderRuntimeProbeRecord(
        provider_name="the-odds-api",
        capability="odds",
        key_configured=True,
        status="ok",
        live_probe=True,
        safe_to_call_real_provider=True,
        message="The Odds API sports probe succeeded.",
        observed_count=len(sports),
        metadata={
            "probe": "sports",
            "soccer_epl_available": soccer_epl_available,
        },
        notes=["secret_value_not_exposed", "soccer_epl_may_be_plan_limited"],
        checked_at_utc=checked_at,
    )


def _sportmonks_probe(
    settings: Settings,
    *,
    live: bool,
    checked_at: datetime,
) -> ProviderRuntimeProbeRecord:
    if not settings.sportmonks_api_key:
        return _not_configured_record(
            provider_name="sportmonks",
            capability="lineups_injuries",
            live=live,
            checked_at=checked_at,
            message="SportMonks key is not configured.",
        )
    if not live:
        return _key_presence_record(
            provider_name="sportmonks",
            capability="lineups_injuries",
            checked_at=checked_at,
        )

    adapter = SportMonksAdapter(
        SportMonksConfig(
            api_token=SecretStr(settings.sportmonks_api_key),
            base_url=settings.sportmonks_api_base_url,
            timeout_seconds=settings.sportmonks_api_timeout_seconds,
        )
    )
    try:
        competitions = adapter.fetch_competitions()
    except SportMonksHttpError as exc:
        return _http_error_record(
            provider_name="sportmonks",
            capability="lineups_injuries",
            status_code=exc.status_code,
            checked_at=checked_at,
        )
    except SportMonksAdapterError:
        return _unavailable_record(
            provider_name="sportmonks",
            capability="lineups_injuries",
            checked_at=checked_at,
        )

    return ProviderRuntimeProbeRecord(
        provider_name="sportmonks",
        capability="lineups_injuries",
        key_configured=True,
        status="ok",
        live_probe=True,
        safe_to_call_real_provider=True,
        message="SportMonks league probe succeeded.",
        observed_count=len(competitions),
        metadata={"probe": "football_leagues"},
        notes=["secret_value_not_exposed", "trial_plan_may_limit_fixture_detail"],
        checked_at_utc=checked_at,
    )


def _api_football_probe(
    settings: Settings,
    *,
    live: bool,
    checked_at: datetime,
) -> ProviderRuntimeProbeRecord:
    if not settings.api_football_api_key:
        return _not_configured_record(
            provider_name="api-football",
            capability="fixtures_results_candidate",
            live=live,
            checked_at=checked_at,
            message="API-Football key is not configured.",
        )
    if not live:
        return _key_presence_record(
            provider_name="api-football",
            capability="fixtures_results_candidate",
            checked_at=checked_at,
        )

    adapter = ApiFootballAdapter(
        ApiFootballConfig(
            api_key=SecretStr(settings.api_football_api_key),
            base_url=settings.api_football_api_base_url,
            timeout_seconds=settings.api_football_api_timeout_seconds,
        )
    )
    try:
        leagues = adapter.fetch_leagues(
            search="Premier League",
        )
    except ApiFootballPlanLimitError as exc:
        return _plan_limited_record(
            provider_name="api-football",
            capability="fixtures_results_candidate",
            checked_at=checked_at,
            errors=exc.errors,
        )
    except ApiFootballHttpError as exc:
        return _http_error_record(
            provider_name="api-football",
            capability="fixtures_results_candidate",
            status_code=exc.status_code,
            checked_at=checked_at,
        )
    except ApiFootballAdapterError:
        return _unavailable_record(
            provider_name="api-football",
            capability="fixtures_results_candidate",
            checked_at=checked_at,
        )

    return ProviderRuntimeProbeRecord(
        provider_name="api-football",
        capability="fixtures_results_candidate",
        key_configured=True,
        status="ok",
        live_probe=live,
        safe_to_call_real_provider=True,
        message="API-Football EPL league probe succeeded.",
        observed_count=len(leagues),
        metadata={
            "probe": "leagues",
            "search": "Premier League",
        },
        notes=["secret_value_not_exposed", "free_plan_may_limit_rate_or_coverage"],
        checked_at_utc=checked_at,
    )


def _not_configured_record(
    *,
    provider_name: str,
    capability: str,
    live: bool,
    checked_at: datetime,
    message: str,
) -> ProviderRuntimeProbeRecord:
    return ProviderRuntimeProbeRecord(
        provider_name=provider_name,
        capability=capability,
        key_configured=False,
        status="not_configured",
        live_probe=live,
        safe_to_call_real_provider=False,
        message=message,
        notes=["secret_value_not_exposed"],
        checked_at_utc=checked_at,
    )


def _key_presence_record(
    *,
    provider_name: str,
    capability: str,
    checked_at: datetime,
) -> ProviderRuntimeProbeRecord:
    return ProviderRuntimeProbeRecord(
        provider_name=provider_name,
        capability=capability,
        key_configured=True,
        status="key_configured",
        live_probe=False,
        safe_to_call_real_provider=True,
        message="Key is configured; live provider probe was not requested.",
        notes=["secret_value_not_exposed", "key_presence_only"],
        checked_at_utc=checked_at,
    )


def _http_error_record(
    *,
    provider_name: str,
    capability: str,
    status_code: int,
    checked_at: datetime,
) -> ProviderRuntimeProbeRecord:
    status: ProviderRuntimeProbeStatus
    message: str
    if status_code == 401:
        status = "auth_failed"
        message = "Provider rejected the configured key."
    elif status_code == 403:
        status = "limited"
        message = "Provider key is configured, but the probe endpoint is not allowed."
    elif status_code == 429:
        status = "rate_limited"
        message = "Provider rate limit was reached during the live probe."
    else:
        status = "unavailable"
        message = "Provider live probe failed."
    return ProviderRuntimeProbeRecord(
        provider_name=provider_name,
        capability=capability,
        key_configured=True,
        status=status,
        live_probe=True,
        safe_to_call_real_provider=False,
        message=message,
        metadata={"http_status_code": status_code},
        notes=["secret_value_not_exposed"],
        checked_at_utc=checked_at,
    )


def _plan_limited_record(
    *,
    provider_name: str,
    capability: str,
    checked_at: datetime,
    errors: dict[str, object],
) -> ProviderRuntimeProbeRecord:
    return ProviderRuntimeProbeRecord(
        provider_name=provider_name,
        capability=capability,
        key_configured=True,
        status="limited",
        live_probe=True,
        safe_to_call_real_provider=False,
        message=(
            "Provider key is configured, but the requested probe is not allowed "
            "by the current plan."
        ),
        metadata={"provider_errors": errors},
        notes=["secret_value_not_exposed"],
        checked_at_utc=checked_at,
    )


def _unavailable_record(
    *,
    provider_name: str,
    capability: str,
    checked_at: datetime,
) -> ProviderRuntimeProbeRecord:
    return ProviderRuntimeProbeRecord(
        provider_name=provider_name,
        capability=capability,
        key_configured=True,
        status="unavailable",
        live_probe=True,
        safe_to_call_real_provider=False,
        message="Provider live probe could not be completed.",
        notes=["secret_value_not_exposed"],
        checked_at_utc=checked_at,
    )
