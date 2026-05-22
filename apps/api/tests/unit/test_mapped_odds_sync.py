from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from nutmeg.providers.conflicts import ProviderObservation, StoredProviderObservation
from nutmeg.providers.mapped_odds_sync import (
    fetch_normalized_the_odds_api_mapped_event_odds,
    sync_the_odds_api_mapped_event_odds,
)
from nutmeg.providers.mapping_repository import ProviderEntityMappingRecord
from nutmeg.providers.odds_repository import OddsSnapshotWriteSummary
from nutmeg.providers.repository import ProviderSyncRunRecord, StoredRawProviderPayload
from nutmeg.providers.the_odds_api import TheOddsApiAdapter, TheOddsApiConfig


class FakeMappedOddsTransport:
    def get_json(self, path: str, query: dict[str, object]) -> object:
        assert path == "/sports/soccer_epl/odds"
        assert query["apiKey"] == "__redacted__"
        assert query["eventIds"] == "event_1,event_2"
        return [_event_payload("event_1"), _event_payload("event_2")]


class FakeMappedRawPayloadRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[str, Mapping[str, object]]] = []

    def save_raw_payload(
        self,
        *,
        provider: str,
        endpoint: str,
        request_params: Mapping[str, object],
        response_json: Mapping[str, object],
        entity_type: str | None = None,
        entity_id_hint: str | None = None,
    ) -> StoredRawProviderPayload:
        self.saved.append((endpoint, request_params))
        return StoredRawProviderPayload(
            payload_id=100 + len(self.saved),
            provider=provider,
            endpoint=endpoint,
            request_hash=f"hash-{len(self.saved)}",
            entity_type=entity_type,
            entity_id_hint=entity_id_hint,
            fetched_at=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
        )


class FakeMappedSyncRunRepository:
    def __init__(self) -> None:
        self.completed_entity_count: int | None = None
        self.started_metadata: dict[str, object] | None = None
        self.completed_metadata: dict[str, object] | None = None

    def start_sync_run(
        self,
        *,
        provider_name: str,
        capability: str,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord:
        assert provider_name == "the-odds-api"
        assert capability == "mapped_odds"
        self.started_metadata = dict(metadata_json or {})
        return _sync_row(status="running", entity_count=0, metadata=metadata_json or {})

    def complete_sync_run(
        self,
        *,
        provider_sync_run_id: int,
        entity_count: int,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord:
        self.completed_entity_count = entity_count
        self.completed_metadata = dict(metadata_json or {})
        return _sync_row(
            status="completed",
            entity_count=entity_count,
            metadata=metadata_json or {},
            completed_at=datetime(2026, 5, 8, 1, 1, tzinfo=UTC),
            duration_ms=1000,
        )

    def fail_sync_run(
        self,
        *,
        provider_sync_run_id: int,
        error_message: str,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord:
        return _sync_row(
            status="failed",
            entity_count=0,
            metadata=metadata_json or {},
            completed_at=datetime(2026, 5, 8, 1, 1, tzinfo=UTC),
            duration_ms=1000,
            error_message=error_message,
        )


class FakeMappedOddsRepository:
    def __init__(self) -> None:
        self.saved_fixture_ids: list[str] = []

    def save_the_odds_api_event_odds(
        self,
        snapshots: Sequence[object],
        *,
        canonical_fixture_id: str,
        provider_event_id: str,
        payload_id: int,
    ) -> OddsSnapshotWriteSummary:
        self.saved_fixture_ids.append(canonical_fixture_id)
        return OddsSnapshotWriteSummary(
            odds_snapshots=len(snapshots),
            inserted_snapshots=len(snapshots),
            updated_snapshots=0,
            provider_mappings=1,
            bookmaker_count=1,
            market_types=["1x2", "asian_handicap"],
            canonical_fixture_id=canonical_fixture_id,
        )


class FakeMappedObservationRepository:
    def __init__(self) -> None:
        self.saved: list[ProviderObservation] = []

    def save_observations(
        self,
        observations: list[ProviderObservation],
    ) -> list[StoredProviderObservation]:
        self.saved.extend(observations)
        return [
            StoredProviderObservation(
                provider_observation_id=700 + index,
                created_at_utc=datetime(2026, 5, 8, 1, 1, tzinfo=UTC),
                **observation.model_dump(),
            )
            for index, observation in enumerate(observations, start=1)
        ]


def test_fetch_normalized_mapped_event_odds_uses_event_ids_batch() -> None:
    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(api_key="test-key"),
        transport=FakeMappedOddsTransport(),
    )

    result = fetch_normalized_the_odds_api_mapped_event_odds(
        adapter=adapter,
        sport_key="soccer_epl",
        provider_event_ids=["event_1", "event_2"],
        regions="eu",
        markets="h2h,spreads",
    )

    assert result.request_params["eventIds"] == "event_1,event_2"
    assert sorted(result.snapshots_by_provider_event_id) == ["event_1", "event_2"]
    assert sum(len(item) for item in result.snapshots_by_provider_event_id.values()) == 10
    assert result.warnings == []


def test_sync_mapped_event_odds_persists_each_event_payload_and_snapshots() -> None:
    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(api_key="test-key"),
        transport=FakeMappedOddsTransport(),
    )
    raw_payload_repository = FakeMappedRawPayloadRepository()
    sync_run_repository = FakeMappedSyncRunRepository()
    odds_repository = FakeMappedOddsRepository()
    observation_repository = FakeMappedObservationRepository()

    result = sync_the_odds_api_mapped_event_odds(
        adapter=adapter,
        mappings=[
            _mapping("event_1", "fd_fixture_1"),
            _mapping("event_2", "fd_fixture_2"),
        ],
        raw_payload_repository=raw_payload_repository,
        sync_run_repository=sync_run_repository,
        odds_repository=odds_repository,
        observation_repository=observation_repository,
        operator_approved=True,
        operator_approval_note="reviewed mapped fixture batch",
        sport_key="soccer_epl",
        canonical_competition_id="EPL",
        regions="eu",
        markets="h2h,spreads",
        bookmakers=None,
    )

    assert result.sync_run is not None
    assert result.sync_run.status == "completed"
    assert result.mapping_count == 2
    assert result.fetched_event_count == 2
    assert result.synced_event_count == 2
    assert result.normalized_odds_count == 10
    assert result.odds_snapshot_count == 10
    assert result.inserted_snapshot_count == 10
    assert result.updated_snapshot_count == 0
    assert len(result.raw_payloads) == 2
    assert odds_repository.saved_fixture_ids == ["fd_fixture_1", "fd_fixture_2"]
    assert len(observation_repository.saved) == 10
    assert sync_run_repository.completed_entity_count == 10
    assert sync_run_repository.started_metadata is not None
    assert sync_run_repository.started_metadata["operator_approval"] == {
        "approved": True,
        "scope": "mapped_event_odds_commit",
        "note": "reviewed mapped fixture batch",
    }
    assert sync_run_repository.completed_metadata is not None
    assert sync_run_repository.completed_metadata["inserted_snapshot_count"] == 10
    assert sync_run_repository.completed_metadata["operator_approval"] == {
        "approved": True,
        "scope": "mapped_event_odds_commit",
        "note": "reviewed mapped fixture batch",
    }
    assert raw_payload_repository.saved[0][1]["eventIds"] == "event_1"
    assert all("test-key" not in str(params) for _, params in raw_payload_repository.saved)


def test_sync_mapped_event_odds_requires_operator_approval_for_commit() -> None:
    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(api_key="test-key"),
        transport=FakeMappedOddsTransport(),
    )

    with pytest.raises(
        ValueError,
        match="operator approval required for mapped odds commit",
    ):
        sync_the_odds_api_mapped_event_odds(
            adapter=adapter,
            mappings=[_mapping("event_1", "fd_fixture_1")],
            raw_payload_repository=FakeMappedRawPayloadRepository(),
            sync_run_repository=FakeMappedSyncRunRepository(),
            odds_repository=FakeMappedOddsRepository(),
            observation_repository=FakeMappedObservationRepository(),
            sport_key="soccer_epl",
            canonical_competition_id="EPL",
            regions="eu",
            markets="h2h,spreads",
            bookmakers=None,
        )


def _mapping(provider_event_id: str, canonical_fixture_id: str) -> ProviderEntityMappingRecord:
    return ProviderEntityMappingRecord(
        mapping_id=1,
        provider="the-odds-api",
        entity_type="fixture",
        provider_entity_id=provider_event_id,
        canonical_entity_id=canonical_fixture_id,
        confidence=0.99,
        created_at_utc=datetime(2026, 5, 8, 0, 0, tzinfo=UTC),
        updated_at_utc=datetime(2026, 5, 8, 0, 0, tzinfo=UTC),
    )


def _sync_row(
    *,
    status: str,
    entity_count: int,
    metadata: Mapping[str, object],
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> ProviderSyncRunRecord:
    return ProviderSyncRunRecord(
        provider_sync_run_id=21,
        provider_name="the-odds-api",
        capability="mapped_odds",
        status=status,  # type: ignore[arg-type]
        started_at=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
        completed_at=completed_at,
        duration_ms=duration_ms,
        entity_count=entity_count,
        error_message=error_message,
        metadata_json=dict(metadata),
    )


def _event_payload(provider_event_id: str) -> dict[str, Any]:
    return {
        "id": provider_event_id,
        "sport_key": "soccer_epl",
        "sport_title": "EPL",
        "commence_time": "2026-05-08T19:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "bookmakers": [
            {
                "key": "pinnacle",
                "last_update": "2026-05-08T07:58:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-05-08T08:00:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.1},
                            {"name": "Draw", "price": 3.2},
                            {"name": "Liverpool", "price": 3.4},
                        ],
                    },
                    {
                        "key": "spreads",
                        "last_update": "2026-05-08T08:01:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 1.91, "point": -0.5},
                            {"name": "Liverpool", "price": 1.93, "point": 0.5},
                        ],
                    },
                ],
            }
        ],
    }
