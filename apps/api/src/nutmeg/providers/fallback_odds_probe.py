from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field, SecretStr

from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.providers.mapping_repository import (
    PostgresProviderEntityMappingRepository,
    ProviderEntityMappingRecord,
)
from nutmeg.providers.mock_dry_run import (
    MOCK_PROVIDER_DRY_RUN_TOKEN,
    MOCK_PROVIDER_DRY_RUN_WARNING,
    MockSportMonksDryRunTransport,
    should_use_mock_provider_dry_run,
)
from nutmeg.providers.odds_coverage import (
    OddsCoverageGapItem,
    OddsCoverageGapReport,
    PostgresOddsCoverageRepository,
)
from nutmeg.providers.sportmonks import (
    SportMonksAdapter,
    SportMonksAdapterError,
    SportMonksConfig,
    SportMonksHttpError,
    normalize_odds,
)

FallbackOddsProbeStatus = Literal[
    "mapping_missing",
    "mapped_probe_ready",
    "covered",
    "mapped_no_supported_odds",
    "not_configured",
    "provider_auth_failed",
    "provider_limited",
    "provider_rate_limited",
    "provider_unavailable",
    "adapter_planned",
]


class OddsGapReportReader(Protocol):
    def build_gap_report(
        self,
        *,
        competition_id: str,
        provider: str,
        as_of_time_utc: datetime,
        window_days: int,
        max_snapshot_lag_hours: int,
        limit: int,
    ) -> OddsCoverageGapReport: ...


class FallbackFixtureMappingReader(Protocol):
    def list_mappings(
        self,
        *,
        provider: str | None = None,
        entity_type: str | None = None,
        canonical_entity_id: str | None = None,
        limit: int = 100,
    ) -> object: ...


class SportMonksFallbackOddsProbeItem(BaseModel):
    fixture_id: str
    competition_id: str
    kickoff_time_utc: datetime
    home_team_name: str
    away_team_name: str
    primary_provider: str
    fallback_provider: str = "sportmonks"
    status: FallbackOddsProbeStatus
    can_recover_gap: bool
    provider_fixture_id: str | None = None
    provider_mapping_id: int | None = Field(default=None, gt=0)
    provider_mapping_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provider_key_configured: bool
    live_provider_probe: bool
    normalized_odds_count: int = Field(default=0, ge=0)
    bookmaker_count: int = Field(default=0, ge=0)
    market_types: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_action: str


class SportMonksFallbackOddsProbeResult(BaseModel):
    competition_id: str
    primary_provider: str
    fallback_provider: str = "sportmonks"
    live_provider_probe: bool
    provider_key_configured: bool
    checked_gap_count: int = Field(ge=0)
    provider_event_unavailable_count: int = Field(ge=0)
    mapped_fallback_count: int = Field(ge=0)
    probed_fixture_count: int = Field(ge=0)
    recoverable_fixture_count: int = Field(ge=0)
    normalized_odds_count: int = Field(ge=0)
    bookmaker_count: int = Field(ge=0)
    market_types: list[str] = Field(default_factory=list)
    items: list[SportMonksFallbackOddsProbeItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at_utc: datetime


def run_sportmonks_fallback_odds_probe(
    settings: Settings,
    *,
    competition_id: str,
    primary_provider: str = "the-odds-api",
    window_days: int = 90,
    max_snapshot_lag_hours: int = 168,
    limit: int = 50,
    as_of_time_utc: datetime | None = None,
    live_provider_probe: bool = False,
    gap_reader: OddsGapReportReader | None = None,
    mapping_reader: FallbackFixtureMappingReader | None = None,
    adapter: SportMonksAdapter | None = None,
) -> SportMonksFallbackOddsProbeResult:
    generated_at = _aware_utc(as_of_time_utc or datetime.now(UTC))
    reader = gap_reader
    mappings = mapping_reader
    if reader is None or mappings is None:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        reader = reader or PostgresOddsCoverageRepository(database)
        mappings = mappings or PostgresProviderEntityMappingRepository(database)

    gap_report = reader.build_gap_report(
        competition_id=competition_id,
        provider=primary_provider,
        as_of_time_utc=generated_at,
        window_days=window_days,
        max_snapshot_lag_hours=max_snapshot_lag_hours,
        limit=limit,
    )
    candidate_gaps = [
        item
        for item in gap_report.items
        if "provider_event_unavailable" in item.issue_types
    ][:limit]
    provider_key_configured = bool(settings.sportmonks_api_key)
    use_mock_dry_run = should_use_mock_provider_dry_run(
        dry_run=live_provider_probe,
        enabled=settings.provider_sync_mock_dry_run_enabled,
        api_key=settings.sportmonks_api_key,
    )
    probe_adapter = adapter or SportMonksAdapter(
        SportMonksConfig(
            api_token=(
                SecretStr(settings.sportmonks_api_key)
                if settings.sportmonks_api_key
                else SecretStr(MOCK_PROVIDER_DRY_RUN_TOKEN)
                if use_mock_dry_run
                else None
            ),
            base_url=settings.sportmonks_api_base_url,
            timeout_seconds=settings.sportmonks_api_timeout_seconds,
        ),
        transport=(
            MockSportMonksDryRunTransport(
                provider_fixture_id="mock-sportmonks-fixture",
                provider_team_ids=(),
            )
            if use_mock_dry_run
            else None
        ),
    )

    items = [
        _probe_gap_item(
            gap,
            mappings=mappings,
            adapter=probe_adapter,
            primary_provider=primary_provider,
            provider_key_configured=provider_key_configured,
            live_provider_probe=live_provider_probe,
            use_mock_dry_run=use_mock_dry_run,
        )
        for gap in candidate_gaps
    ]
    bookmaker_names = {
        warning.removeprefix("bookmaker:")
        for item in items
        for warning in item.warnings
        if warning.startswith("bookmaker:")
    }
    warnings = []
    if use_mock_dry_run:
        warnings.append(MOCK_PROVIDER_DRY_RUN_WARNING)
    if not candidate_gaps:
        warnings.append("no_provider_event_unavailable_gaps")
    if any(item.status == "mapping_missing" for item in items):
        warnings.append("sportmonks_fixture_mapping_required")

    return SportMonksFallbackOddsProbeResult(
        competition_id=competition_id,
        primary_provider=primary_provider,
        live_provider_probe=live_provider_probe,
        provider_key_configured=provider_key_configured,
        checked_gap_count=len(candidate_gaps),
        provider_event_unavailable_count=gap_report.provider_event_unavailable_count,
        mapped_fallback_count=sum(1 for item in items if item.provider_fixture_id),
        probed_fixture_count=sum(
            1 for item in items if item.live_provider_probe and item.provider_fixture_id
        ),
        recoverable_fixture_count=sum(1 for item in items if item.can_recover_gap),
        normalized_odds_count=sum(item.normalized_odds_count for item in items),
        bookmaker_count=len(bookmaker_names),
        market_types=sorted(
            {
                market_type
                for item in items
                for market_type in item.market_types
            }
        ),
        items=items,
        warnings=list(dict.fromkeys(warnings)),
        generated_at_utc=generated_at,
    )


def _probe_gap_item(
    gap: OddsCoverageGapItem,
    *,
    mappings: FallbackFixtureMappingReader,
    adapter: SportMonksAdapter,
    primary_provider: str,
    provider_key_configured: bool,
    live_provider_probe: bool,
    use_mock_dry_run: bool,
) -> SportMonksFallbackOddsProbeItem:
    mapping = _sportmonks_mapping_for_gap(mappings, gap.fixture_id)
    if mapping is None:
        return _probe_item(
            gap,
            primary_provider=primary_provider,
            status="mapping_missing",
            provider_key_configured=provider_key_configured,
            live_provider_probe=live_provider_probe,
            can_recover_gap=False,
            warnings=["missing_sportmonks_fixture_mapping"],
            recommended_action="bootstrap_sportmonks_fixture_mapping",
        )
    if not live_provider_probe:
        return _probe_item(
            gap,
            primary_provider=primary_provider,
            status="mapped_probe_ready",
            provider_key_configured=provider_key_configured,
            live_provider_probe=False,
            mapping=mapping,
            can_recover_gap=False,
            warnings=["live_provider_probe_disabled"],
            recommended_action="run_live_sportmonks_odds_probe",
        )
    if not provider_key_configured and not use_mock_dry_run:
        return _probe_item(
            gap,
            primary_provider=primary_provider,
            status="not_configured",
            provider_key_configured=False,
            live_provider_probe=True,
            mapping=mapping,
            can_recover_gap=False,
            warnings=["sportmonks_api_key_required"],
            recommended_action="configure_nutmeg_sportmonks_api_key",
        )
    try:
        payload = adapter.fetch_odds(mapping.provider_entity_id)
        snapshots = normalize_odds(
            payload,
            provider_fixture_id=mapping.provider_entity_id,
        )
    except SportMonksHttpError as exc:
        status = _status_for_http_error(exc.status_code)
        return _probe_item(
            gap,
            primary_provider=primary_provider,
            status=status,
            provider_key_configured=provider_key_configured,
            live_provider_probe=True,
            mapping=mapping,
            can_recover_gap=False,
            warnings=[f"sportmonks_http_status:{exc.status_code}"],
            recommended_action="review_sportmonks_key_or_plan_limits",
        )
    except SportMonksAdapterError:
        return _probe_item(
            gap,
            primary_provider=primary_provider,
            status="provider_unavailable",
            provider_key_configured=provider_key_configured,
            live_provider_probe=True,
            mapping=mapping,
            can_recover_gap=False,
            warnings=["sportmonks_provider_unavailable"],
            recommended_action="retry_sportmonks_fallback_probe_later",
        )
    if not snapshots:
        return _probe_item(
            gap,
            primary_provider=primary_provider,
            status="mapped_no_supported_odds",
            provider_key_configured=provider_key_configured,
            live_provider_probe=True,
            mapping=mapping,
            can_recover_gap=False,
            warnings=["no_supported_sportmonks_odds_markets"],
            recommended_action="review_sportmonks_market_payload",
        )
    bookmaker_names = sorted({snapshot.bookmaker for snapshot in snapshots})
    return _probe_item(
        gap,
        primary_provider=primary_provider,
        status="covered",
        provider_key_configured=provider_key_configured,
        live_provider_probe=True,
        mapping=mapping,
        can_recover_gap=True,
        normalized_odds_count=len(snapshots),
        bookmaker_count=len(bookmaker_names),
        market_types=sorted({str(snapshot.market_type) for snapshot in snapshots}),
        warnings=[f"bookmaker:{bookmaker}" for bookmaker in bookmaker_names],
        recommended_action="queue_sportmonks_odds_snapshot_sync_after_operator_review",
    )


def _sportmonks_mapping_for_gap(
    mappings: FallbackFixtureMappingReader,
    fixture_id: str,
) -> ProviderEntityMappingRecord | None:
    result = mappings.list_mappings(
        provider="sportmonks",
        entity_type="fixture",
        canonical_entity_id=fixture_id,
        limit=1,
    )
    items = getattr(result, "items", [])
    first = items[0] if items else None
    return first if isinstance(first, ProviderEntityMappingRecord) else None


def _probe_item(
    gap: OddsCoverageGapItem,
    *,
    primary_provider: str,
    status: FallbackOddsProbeStatus,
    provider_key_configured: bool,
    live_provider_probe: bool,
    can_recover_gap: bool,
    recommended_action: str,
    mapping: ProviderEntityMappingRecord | None = None,
    normalized_odds_count: int = 0,
    bookmaker_count: int = 0,
    market_types: Sequence[str] = (),
    warnings: Sequence[str] = (),
) -> SportMonksFallbackOddsProbeItem:
    return SportMonksFallbackOddsProbeItem(
        fixture_id=gap.fixture_id,
        competition_id=gap.competition_id,
        kickoff_time_utc=gap.kickoff_time_utc,
        home_team_name=gap.home_team_name,
        away_team_name=gap.away_team_name,
        primary_provider=primary_provider,
        status=status,
        can_recover_gap=can_recover_gap,
        provider_fixture_id=mapping.provider_entity_id if mapping is not None else None,
        provider_mapping_id=mapping.mapping_id if mapping is not None else None,
        provider_mapping_confidence=mapping.confidence if mapping is not None else None,
        provider_key_configured=provider_key_configured,
        live_provider_probe=live_provider_probe,
        normalized_odds_count=normalized_odds_count,
        bookmaker_count=bookmaker_count,
        market_types=list(market_types),
        warnings=list(warnings),
        recommended_action=recommended_action,
    )


def _status_for_http_error(status_code: int) -> FallbackOddsProbeStatus:
    if status_code == 401:
        return "provider_auth_failed"
    if status_code == 403:
        return "provider_limited"
    if status_code == 429:
        return "provider_rate_limited"
    return "provider_unavailable"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
