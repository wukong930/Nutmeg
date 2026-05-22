from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field, SecretStr

from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.providers.conflicts import (
    PostgresProviderObservationRepository,
    ProviderObservation,
)
from nutmeg.providers.mock_dry_run import (
    MOCK_PROVIDER_DRY_RUN_TOKEN,
    MOCK_PROVIDER_DRY_RUN_WARNING,
    MockTheOddsApiDryRunTransport,
    should_use_mock_provider_dry_run,
)
from nutmeg.providers.odds_repository import (
    OddsSnapshotWriteSummary,
    PostgresOddsSnapshotRepository,
)
from nutmeg.providers.repository import (
    PostgresProviderRawPayloadRepository,
    PostgresProviderSyncRunRepository,
    ProviderSyncRunRecord,
    StoredRawProviderPayload,
)
from nutmeg.providers.sync import ProviderObservationWriter, RawPayloadWriter, SyncRunWriter
from nutmeg.providers.the_odds_api import (
    NormalizedOddsSnapshot,
    TheOddsApiAdapter,
    TheOddsApiConfig,
    normalize_event_odds,
)


class OddsSnapshotWriter(Protocol):
    def save_the_odds_api_event_odds(
        self,
        snapshots: list[NormalizedOddsSnapshot],
        *,
        canonical_fixture_id: str,
        provider_event_id: str,
        payload_id: int,
    ) -> OddsSnapshotWriteSummary: ...


class TheOddsApiEventOddsFetchResult(BaseModel):
    endpoint: str
    request_params: dict[str, object] = Field(default_factory=dict)
    payload: dict[str, object] = Field(default_factory=dict)
    snapshots: list[NormalizedOddsSnapshot] = Field(default_factory=list)


class TheOddsApiEventOddsSyncResult(BaseModel):
    provider_name: str = "the-odds-api"
    sport_key: str
    provider_event_id: str
    canonical_fixture_id: str
    dry_run: bool = False
    sync_run: ProviderSyncRunRecord | None = None
    raw_payload: StoredRawProviderPayload | None = None
    snapshots: list[NormalizedOddsSnapshot] = Field(default_factory=list)
    odds_write: OddsSnapshotWriteSummary | None = None
    request_params: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def fetch_normalized_the_odds_api_event_odds(
    *,
    adapter: TheOddsApiAdapter,
    sport_key: str,
    provider_event_id: str,
    regions: str,
    markets: str,
    bookmakers: str | None = None,
) -> TheOddsApiEventOddsFetchResult:
    endpoint = f"/sports/{sport_key}/events/{provider_event_id}/odds"
    request_params: dict[str, object] = {
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    if bookmakers is not None:
        request_params["bookmakers"] = bookmakers
    payload = adapter.fetch_event_odds(
        sport_key=sport_key,
        event_id=provider_event_id,
        regions=regions,
        markets=markets,
        odds_format="decimal",
        date_format="iso",
        bookmakers=bookmakers,
    )
    snapshots = normalize_event_odds(payload)
    return TheOddsApiEventOddsFetchResult(
        endpoint=endpoint,
        request_params=request_params,
        payload=payload,
        snapshots=snapshots,
    )


def sync_the_odds_api_event_odds(
    *,
    adapter: TheOddsApiAdapter,
    raw_payload_repository: RawPayloadWriter,
    sync_run_repository: SyncRunWriter,
    odds_repository: OddsSnapshotWriter | None = None,
    observation_repository: ProviderObservationWriter | None = None,
    sport_key: str,
    provider_event_id: str,
    canonical_fixture_id: str,
    regions: str,
    markets: str,
    bookmakers: str | None = None,
) -> TheOddsApiEventOddsSyncResult:
    sync_run = sync_run_repository.start_sync_run(
        provider_name=adapter.provider_name,
        capability="odds",
        metadata_json={
            "sport_key": sport_key,
            "provider_event_id": provider_event_id,
            "canonical_fixture_id": canonical_fixture_id,
            "regions": regions,
            "markets": markets,
            "bookmakers": bookmakers,
        },
    )
    try:
        fetch_result = fetch_normalized_the_odds_api_event_odds(
            adapter=adapter,
            sport_key=sport_key,
            provider_event_id=provider_event_id,
            regions=regions,
            markets=markets,
            bookmakers=bookmakers,
        )
        raw_payload = raw_payload_repository.save_raw_payload(
            provider=adapter.provider_name,
            endpoint=fetch_result.endpoint,
            request_params=fetch_result.request_params,
            response_json=fetch_result.payload,
            entity_type="fixture",
            entity_id_hint=provider_event_id,
        )
        odds_write = None
        if odds_repository is not None:
            odds_write = odds_repository.save_the_odds_api_event_odds(
                fetch_result.snapshots,
                canonical_fixture_id=canonical_fixture_id,
                provider_event_id=provider_event_id,
                payload_id=raw_payload.payload_id,
            )
        if observation_repository is not None:
            observation_repository.save_observations(
                odds_observations_from_snapshots(
                    fetch_result.snapshots,
                    canonical_fixture_id=canonical_fixture_id,
                    payload_id=raw_payload.payload_id,
                )
            )
        completed = sync_run_repository.complete_sync_run(
            provider_sync_run_id=sync_run.provider_sync_run_id,
            entity_count=len(fetch_result.snapshots),
            metadata_json={
                "sport_key": sport_key,
                "provider_event_id": provider_event_id,
                "canonical_fixture_id": canonical_fixture_id,
                "raw_payload_id": raw_payload.payload_id,
                "odds_write": odds_write.model_dump() if odds_write is not None else None,
            },
        )
        return TheOddsApiEventOddsSyncResult(
            sport_key=sport_key,
            provider_event_id=provider_event_id,
            canonical_fixture_id=canonical_fixture_id,
            sync_run=completed,
            raw_payload=raw_payload,
            snapshots=fetch_result.snapshots,
            odds_write=odds_write,
            request_params=fetch_result.request_params,
        )
    except Exception as exc:
        failed = sync_run_repository.fail_sync_run(
            provider_sync_run_id=sync_run.provider_sync_run_id,
            error_message=str(exc),
            metadata_json={
                "sport_key": sport_key,
                "provider_event_id": provider_event_id,
                "canonical_fixture_id": canonical_fixture_id,
            },
        )
        return TheOddsApiEventOddsSyncResult(
            sport_key=sport_key,
            provider_event_id=provider_event_id,
            canonical_fixture_id=canonical_fixture_id,
            sync_run=failed,
            warnings=[str(exc)],
        )


def run_the_odds_api_event_odds_sync(
    settings: Settings,
    *,
    sport_key: str,
    provider_event_id: str,
    canonical_fixture_id: str,
    regions: str,
    markets: str,
    bookmakers: str | None,
    dry_run: bool,
) -> TheOddsApiEventOddsSyncResult:
    use_mock_dry_run = should_use_mock_provider_dry_run(
        dry_run=dry_run,
        enabled=settings.provider_sync_mock_dry_run_enabled,
        api_key=settings.the_odds_api_key,
    )
    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(
            api_key=(
                SecretStr(settings.the_odds_api_key)
                if settings.the_odds_api_key
                else SecretStr(MOCK_PROVIDER_DRY_RUN_TOKEN)
                if use_mock_dry_run
                else None
            ),
            base_url=settings.the_odds_api_base_url,
            timeout_seconds=settings.the_odds_api_timeout_seconds,
        ),
        transport=(
            MockTheOddsApiDryRunTransport(
                sport_key=sport_key,
                provider_event_id=provider_event_id,
            )
            if use_mock_dry_run
            else None
        ),
    )
    if dry_run:
        fetch_result = fetch_normalized_the_odds_api_event_odds(
            adapter=adapter,
            sport_key=sport_key,
            provider_event_id=provider_event_id,
            regions=regions,
            markets=markets,
            bookmakers=bookmakers,
        )
        return TheOddsApiEventOddsSyncResult(
            sport_key=sport_key,
            provider_event_id=provider_event_id,
            canonical_fixture_id=canonical_fixture_id,
            dry_run=True,
            snapshots=fetch_result.snapshots,
            request_params=fetch_result.request_params,
            warnings=[MOCK_PROVIDER_DRY_RUN_WARNING] if use_mock_dry_run else [],
        )

    database = PsycopgSyncDatabaseExecutor(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    return sync_the_odds_api_event_odds(
        adapter=adapter,
        raw_payload_repository=PostgresProviderRawPayloadRepository(database),
        sync_run_repository=PostgresProviderSyncRunRepository(database),
        odds_repository=PostgresOddsSnapshotRepository(database),
        observation_repository=PostgresProviderObservationRepository(database),
        sport_key=sport_key,
        provider_event_id=provider_event_id,
        canonical_fixture_id=canonical_fixture_id,
        regions=regions,
        markets=markets,
        bookmakers=bookmakers,
    )


def odds_observations_from_snapshots(
    snapshots: list[NormalizedOddsSnapshot],
    *,
    canonical_fixture_id: str,
    payload_id: int,
) -> list[ProviderObservation]:
    observations: list[ProviderObservation] = []
    for snapshot in snapshots:
        probability = snapshot.fair_probability or snapshot.raw_implied_probability
        line = "none" if snapshot.line is None else f"{snapshot.line:g}"
        side = "none" if snapshot.side is None else snapshot.side
        observations.append(
            ProviderObservation(
                provider_name=snapshot.provider,
                capability="odds",
                entity_type="fixture",
                canonical_entity_id=canonical_fixture_id,
                provider_entity_id=snapshot.provider_event_id,
                field_name=(
                    f"fair_probability:{snapshot.market_type}:{line}:"
                    f"{side}:{snapshot.outcome}"
                ),
                value=f"{probability:.6f}",
                observed_at_utc=snapshot.snapshot_time_utc,
                payload_id=payload_id,
                metadata_json={
                    "bookmaker": snapshot.bookmaker,
                    "market_key": snapshot.market_key,
                    "decimal_odds": snapshot.decimal_odds,
                },
            )
        )
    return observations
