from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, Field, SecretStr

from nutmeg.config import Settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.providers.conflicts import (
    PostgresProviderObservationRepository,
)
from nutmeg.providers.mapping_repository import (
    PostgresProviderEntityMappingRepository,
    ProviderEntityMappingRecord,
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
from nutmeg.providers.odds_sync import odds_observations_from_snapshots
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


class FixtureMappingReader(Protocol):
    def list_fixture_mappings_for_competition(
        self,
        *,
        provider: str,
        competition_id: str,
        min_confidence: float,
        limit: int,
    ) -> list[ProviderEntityMappingRecord]: ...


class OddsSnapshotWriter(Protocol):
    def save_the_odds_api_event_odds(
        self,
        snapshots: Sequence[NormalizedOddsSnapshot],
        *,
        canonical_fixture_id: str,
        provider_event_id: str,
        payload_id: int,
    ) -> OddsSnapshotWriteSummary: ...


class TheOddsApiMappedEventOddsFetchResult(BaseModel):
    endpoint: str
    request_params: dict[str, object] = Field(default_factory=dict)
    payloads_by_provider_event_id: dict[str, dict[str, object]] = Field(
        default_factory=dict
    )
    snapshots_by_provider_event_id: dict[str, list[NormalizedOddsSnapshot]] = Field(
        default_factory=dict
    )
    warnings: list[str] = Field(default_factory=list)


class TheOddsApiMappedEventOddsSyncItem(BaseModel):
    provider_event_id: str
    canonical_fixture_id: str
    normalized_odds_count: int = Field(ge=0)
    bookmaker_count: int = Field(ge=0)
    market_types: list[str] = Field(default_factory=list)
    raw_payload: StoredRawProviderPayload | None = None
    odds_write: OddsSnapshotWriteSummary | None = None
    warnings: list[str] = Field(default_factory=list)


class TheOddsApiMappedEventOddsSyncResult(BaseModel):
    provider_name: str = "the-odds-api"
    sport_key: str
    canonical_competition_id: str
    dry_run: bool = False
    mapping_count: int = Field(ge=0)
    fetched_event_count: int = Field(ge=0)
    synced_event_count: int = Field(ge=0)
    normalized_odds_count: int = Field(ge=0)
    odds_snapshot_count: int = Field(ge=0)
    inserted_snapshot_count: int = Field(default=0, ge=0)
    updated_snapshot_count: int = Field(default=0, ge=0)
    bookmaker_count: int = Field(ge=0)
    market_types: list[str] = Field(default_factory=list)
    request_params: dict[str, object] = Field(default_factory=dict)
    sync_run: ProviderSyncRunRecord | None = None
    raw_payloads: list[StoredRawProviderPayload] = Field(default_factory=list)
    items: list[TheOddsApiMappedEventOddsSyncItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def fetch_normalized_the_odds_api_mapped_event_odds(
    *,
    adapter: TheOddsApiAdapter,
    sport_key: str,
    provider_event_ids: Sequence[str],
    regions: str,
    markets: str,
    bookmakers: str | None = None,
) -> TheOddsApiMappedEventOddsFetchResult:
    unique_event_ids = list(dict.fromkeys(provider_event_ids))
    endpoint = f"/sports/{sport_key}/odds"
    request_params: dict[str, object] = {
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
        "eventIds": ",".join(unique_event_ids),
    }
    if bookmakers is not None:
        request_params["bookmakers"] = bookmakers
    if not unique_event_ids:
        return TheOddsApiMappedEventOddsFetchResult(
            endpoint=endpoint,
            request_params=request_params,
            warnings=["no_provider_event_ids"],
        )

    raw_events = adapter.fetch_sport_odds(
        sport_key=sport_key,
        regions=regions,
        markets=markets,
        odds_format="decimal",
        date_format="iso",
        event_ids=",".join(unique_event_ids),
        bookmakers=bookmakers,
    )
    requested_ids = set(unique_event_ids)
    payloads_by_id: dict[str, dict[str, object]] = {}
    snapshots_by_id: dict[str, list[NormalizedOddsSnapshot]] = {}
    warnings: list[str] = []
    for raw_event in raw_events:
        provider_event_id = str(raw_event.get("id") or "")
        if not provider_event_id:
            warnings.append("missing_provider_event_id")
            continue
        if provider_event_id not in requested_ids:
            warnings.append(f"unexpected_provider_event:{provider_event_id}")
            continue
        payloads_by_id[provider_event_id] = raw_event
        try:
            snapshots_by_id[provider_event_id] = normalize_event_odds(raw_event)
        except ValueError as exc:
            snapshots_by_id[provider_event_id] = []
            warnings.append(f"normalize_failed:{provider_event_id}:{exc}")
    for provider_event_id in unique_event_ids:
        if provider_event_id not in payloads_by_id:
            warnings.append(f"missing_provider_event:{provider_event_id}")

    return TheOddsApiMappedEventOddsFetchResult(
        endpoint=endpoint,
        request_params=request_params,
        payloads_by_provider_event_id=payloads_by_id,
        snapshots_by_provider_event_id=snapshots_by_id,
        warnings=warnings,
    )


def sync_the_odds_api_mapped_event_odds(
    *,
    adapter: TheOddsApiAdapter,
    mappings: Sequence[ProviderEntityMappingRecord],
    raw_payload_repository: RawPayloadWriter,
    sync_run_repository: SyncRunWriter,
    sport_key: str,
    canonical_competition_id: str,
    regions: str,
    markets: str,
    bookmakers: str | None = None,
    odds_repository: OddsSnapshotWriter | None = None,
    observation_repository: ProviderObservationWriter | None = None,
    operator_approved: bool = False,
    operator_approval_note: str | None = None,
) -> TheOddsApiMappedEventOddsSyncResult:
    if not operator_approved:
        raise ValueError("operator approval required for mapped odds commit")
    if not mappings:
        return TheOddsApiMappedEventOddsSyncResult(
            sport_key=sport_key,
            canonical_competition_id=canonical_competition_id,
            mapping_count=0,
            fetched_event_count=0,
            synced_event_count=0,
            normalized_odds_count=0,
            odds_snapshot_count=0,
            bookmaker_count=0,
            warnings=["no_provider_fixture_mappings"],
        )

    provider_event_ids = [mapping.provider_entity_id for mapping in mappings]
    approval_metadata = _operator_approval_metadata(
        operator_approved=operator_approved,
        operator_approval_note=operator_approval_note,
    )
    sync_run = sync_run_repository.start_sync_run(
        provider_name=adapter.provider_name,
        capability="mapped_odds",
        metadata_json={
            "sport_key": sport_key,
            "canonical_competition_id": canonical_competition_id,
            "regions": regions,
            "markets": markets,
            "bookmakers": bookmakers,
            "mapping_count": len(mappings),
            "operator_approval": approval_metadata,
        },
    )
    try:
        fetch_result = fetch_normalized_the_odds_api_mapped_event_odds(
            adapter=adapter,
            sport_key=sport_key,
            provider_event_ids=provider_event_ids,
            regions=regions,
            markets=markets,
            bookmakers=bookmakers,
        )
        result = _build_mapped_event_result(
            mappings=mappings,
            fetch_result=fetch_result,
            sport_key=sport_key,
            canonical_competition_id=canonical_competition_id,
            dry_run=False,
            raw_payload_repository=raw_payload_repository,
            odds_repository=odds_repository,
            observation_repository=observation_repository,
        )
        completed = sync_run_repository.complete_sync_run(
            provider_sync_run_id=sync_run.provider_sync_run_id,
            entity_count=result.normalized_odds_count,
            metadata_json={
                "sport_key": sport_key,
                "canonical_competition_id": canonical_competition_id,
                "mapping_count": result.mapping_count,
                "fetched_event_count": result.fetched_event_count,
                "synced_event_count": result.synced_event_count,
                "normalized_odds_count": result.normalized_odds_count,
                "odds_snapshot_count": result.odds_snapshot_count,
                "inserted_snapshot_count": result.inserted_snapshot_count,
                "updated_snapshot_count": result.updated_snapshot_count,
                "warnings": result.warnings[:50],
                "operator_approval": approval_metadata,
            },
        )
        return result.model_copy(update={"sync_run": completed})
    except Exception as exc:
        failed = sync_run_repository.fail_sync_run(
            provider_sync_run_id=sync_run.provider_sync_run_id,
            error_message=str(exc),
            metadata_json={
                "sport_key": sport_key,
                "canonical_competition_id": canonical_competition_id,
                "mapping_count": len(mappings),
                "operator_approval": approval_metadata,
            },
        )
        return TheOddsApiMappedEventOddsSyncResult(
            sport_key=sport_key,
            canonical_competition_id=canonical_competition_id,
            mapping_count=len(mappings),
            fetched_event_count=0,
            synced_event_count=0,
            normalized_odds_count=0,
            odds_snapshot_count=0,
            bookmaker_count=0,
            sync_run=failed,
            warnings=[str(exc)],
        )


def run_the_odds_api_mapped_event_odds_sync(
    settings: Settings,
    *,
    canonical_competition_id: str,
    sport_key: str,
    regions: str,
    markets: str,
    bookmakers: str | None,
    min_mapping_confidence: float,
    max_mappings: int,
    dry_run: bool,
    mapping_reader: FixtureMappingReader | None = None,
    operator_approved: bool = False,
    operator_approval_note: str | None = None,
) -> TheOddsApiMappedEventOddsSyncResult:
    if not dry_run and not operator_approved:
        raise ValueError("operator approval required for mapped odds commit")
    database = PsycopgSyncDatabaseExecutor(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    reader = mapping_reader or PostgresProviderEntityMappingRepository(database)
    mappings = reader.list_fixture_mappings_for_competition(
        provider="the-odds-api",
        competition_id=canonical_competition_id,
        min_confidence=min_mapping_confidence,
        limit=max_mappings,
    )
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
                provider_event_id=mappings[0].provider_entity_id
                if mappings
                else "mock-event-id",
            )
            if use_mock_dry_run
            else None
        ),
    )
    if not mappings:
        return TheOddsApiMappedEventOddsSyncResult(
            sport_key=sport_key,
            canonical_competition_id=canonical_competition_id,
            dry_run=dry_run,
            mapping_count=0,
            fetched_event_count=0,
            synced_event_count=0,
            normalized_odds_count=0,
            odds_snapshot_count=0,
            bookmaker_count=0,
            warnings=["no_provider_fixture_mappings"],
        )
    if dry_run:
        fetch_result = fetch_normalized_the_odds_api_mapped_event_odds(
            adapter=adapter,
            sport_key=sport_key,
            provider_event_ids=[mapping.provider_entity_id for mapping in mappings],
            regions=regions,
            markets=markets,
            bookmakers=bookmakers,
        )
        warnings = list(fetch_result.warnings)
        if use_mock_dry_run:
            warnings.append(MOCK_PROVIDER_DRY_RUN_WARNING)
        return _build_mapped_event_result(
            mappings=mappings,
            fetch_result=fetch_result,
            sport_key=sport_key,
            canonical_competition_id=canonical_competition_id,
            dry_run=True,
            extra_warnings=warnings,
        )

    return sync_the_odds_api_mapped_event_odds(
        adapter=adapter,
        mappings=mappings,
        raw_payload_repository=PostgresProviderRawPayloadRepository(database),
        sync_run_repository=PostgresProviderSyncRunRepository(database),
        odds_repository=PostgresOddsSnapshotRepository(database),
        observation_repository=PostgresProviderObservationRepository(database),
        operator_approved=operator_approved,
        operator_approval_note=operator_approval_note,
        sport_key=sport_key,
        canonical_competition_id=canonical_competition_id,
        regions=regions,
        markets=markets,
        bookmakers=bookmakers,
    )


def _operator_approval_metadata(
    *,
    operator_approved: bool,
    operator_approval_note: str | None,
) -> dict[str, object]:
    return {
        "approved": operator_approved,
        "scope": "mapped_event_odds_commit",
        "note": operator_approval_note,
    }


def _build_mapped_event_result(
    *,
    mappings: Sequence[ProviderEntityMappingRecord],
    fetch_result: TheOddsApiMappedEventOddsFetchResult,
    sport_key: str,
    canonical_competition_id: str,
    dry_run: bool,
    raw_payload_repository: RawPayloadWriter | None = None,
    odds_repository: OddsSnapshotWriter | None = None,
    observation_repository: ProviderObservationWriter | None = None,
    extra_warnings: Sequence[str] = (),
) -> TheOddsApiMappedEventOddsSyncResult:
    items: list[TheOddsApiMappedEventOddsSyncItem] = []
    raw_payloads: list[StoredRawProviderPayload] = []
    warnings = list(dict.fromkeys([*fetch_result.warnings, *extra_warnings]))
    for mapping in mappings:
        provider_event_id = mapping.provider_entity_id
        payload = fetch_result.payloads_by_provider_event_id.get(provider_event_id)
        snapshots = fetch_result.snapshots_by_provider_event_id.get(provider_event_id, [])
        item_warnings: list[str] = []
        raw_payload = None
        odds_write = None
        if payload is None:
            item_warnings.append("provider_event_not_returned")
        elif not dry_run and raw_payload_repository is not None:
            raw_payload = raw_payload_repository.save_raw_payload(
                provider="the-odds-api",
                endpoint=fetch_result.endpoint,
                request_params=_event_request_params(
                    fetch_result.request_params,
                    provider_event_id=provider_event_id,
                ),
                response_json=payload,
                entity_type="fixture",
                entity_id_hint=provider_event_id,
            )
            raw_payloads.append(raw_payload)
            if odds_repository is not None:
                odds_write = odds_repository.save_the_odds_api_event_odds(
                    snapshots,
                    canonical_fixture_id=mapping.canonical_entity_id,
                    provider_event_id=provider_event_id,
                    payload_id=raw_payload.payload_id,
                )
            if observation_repository is not None and snapshots:
                observation_repository.save_observations(
                    odds_observations_from_snapshots(
                        snapshots,
                        canonical_fixture_id=mapping.canonical_entity_id,
                        payload_id=raw_payload.payload_id,
                    )
                )
        if payload is not None and not snapshots:
            item_warnings.append("no_supported_odds_markets")
        items.append(
            TheOddsApiMappedEventOddsSyncItem(
                provider_event_id=provider_event_id,
                canonical_fixture_id=mapping.canonical_entity_id,
                normalized_odds_count=len(snapshots),
                bookmaker_count=len({snapshot.bookmaker for snapshot in snapshots}),
                market_types=sorted({str(snapshot.market_type) for snapshot in snapshots}),
                raw_payload=raw_payload,
                odds_write=odds_write,
                warnings=item_warnings,
            )
        )
    normalized_odds_count = sum(item.normalized_odds_count for item in items)
    odds_snapshot_count = sum(
        item.odds_write.odds_snapshots
        for item in items
        if item.odds_write is not None
    )
    inserted_snapshot_count = sum(
        item.odds_write.inserted_snapshots
        for item in items
        if item.odds_write is not None
    )
    updated_snapshot_count = sum(
        item.odds_write.updated_snapshots
        for item in items
        if item.odds_write is not None
    )
    bookmaker_names = {
        snapshot.bookmaker
        for snapshots in fetch_result.snapshots_by_provider_event_id.values()
        for snapshot in snapshots
    }
    market_types = sorted(
        {
            str(snapshot.market_type)
            for snapshots in fetch_result.snapshots_by_provider_event_id.values()
            for snapshot in snapshots
        }
    )
    return TheOddsApiMappedEventOddsSyncResult(
        sport_key=sport_key,
        canonical_competition_id=canonical_competition_id,
        dry_run=dry_run,
        mapping_count=len(mappings),
        fetched_event_count=len(fetch_result.payloads_by_provider_event_id),
        synced_event_count=sum(1 for item in items if item.normalized_odds_count > 0),
        normalized_odds_count=normalized_odds_count,
        odds_snapshot_count=odds_snapshot_count,
        inserted_snapshot_count=inserted_snapshot_count,
        updated_snapshot_count=updated_snapshot_count,
        bookmaker_count=len(bookmaker_names),
        market_types=market_types,
        request_params=fetch_result.request_params,
        raw_payloads=raw_payloads,
        items=items,
        warnings=warnings,
    )


def _event_request_params(
    request_params: Mapping[str, object],
    *,
    provider_event_id: str,
) -> dict[str, object]:
    params = dict(request_params)
    params["eventIds"] = provider_event_id
    return params
