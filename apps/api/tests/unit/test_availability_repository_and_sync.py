from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.availability_repository import PostgresAvailabilitySnapshotRepository
from nutmeg.providers.availability_sync import sync_sportmonks_fixture_availability
from nutmeg.providers.conflicts import ProviderObservation, StoredProviderObservation
from nutmeg.providers.repository import (
    PostgresProviderRawPayloadRepository,
    PostgresProviderSyncRunRepository,
)
from nutmeg.providers.sportmonks import SportMonksAdapter, SportMonksConfig
from nutmeg.providers.sportmonks.normalizer import normalize_injuries, normalize_lineups


class FakeAvailabilityDatabase:
    def __init__(self) -> None:
        self.queries: list[tuple[str, QueryParams]] = []
        self.payload_id = 40

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.queries.append((query, params))
        if "INSERT INTO raw_provider_payloads" in query:
            self.payload_id += 1
            return {"payload_id": self.payload_id, "fetched_at": _now()}
        if "INSERT INTO provider_sync_runs" in query:
            return _sync_row(status="running", entity_count=0, metadata=params["metadata_json"])
        if "status = 'completed'" in query:
            return _sync_row(
                status="completed",
                entity_count=params["entity_count"],
                completed_at=datetime(2026, 5, 6, 0, 1, tzinfo=UTC),
                duration_ms=1000,
                metadata=params["metadata_json"],
            )
        if "status = 'failed'" in query:
            return _sync_row(
                status="failed",
                entity_count=0,
                completed_at=datetime(2026, 5, 6, 0, 1, tzinfo=UTC),
                duration_ms=1000,
                error_message=params["error_message"],
                metadata=params["metadata_json"],
            )
        if "provider_entity_mappings" in query:
            return {"mapping_id": 50}
        if "INSERT INTO lineup_snapshots" in query:
            return {"lineup_snapshot_id": 60}
        if "INSERT INTO player_availability_snapshots" in query:
            return {"availability_snapshot_id": 70}
        raise AssertionError(f"unexpected query: {query}")


class FakeSportMonksAvailabilityTransport:
    def get_json(self, path: str, query: dict[str, object]) -> object:
        assert query["api_token"] == "__redacted__"
        if path == "/football/fixtures/fixture_123/lineups":
            return _lineup_payload()
        if path == "/football/injuries" and query["filters"] == "injuryTeam:team_1":
            return _injury_payload("team_1", "player_11")
        if path == "/football/injuries" and query["filters"] == "injuryTeam:team_2":
            return _injury_payload("team_2", "player_21")
        raise AssertionError(f"unexpected SportMonks call: {path} {query}")


class FakeObservationRepository:
    def __init__(self) -> None:
        self.observations: list[ProviderObservation] = []

    def save_observations(
        self,
        observations: list[ProviderObservation],
    ) -> list[StoredProviderObservation]:
        self.observations.extend(observations)
        return [
            StoredProviderObservation(
                provider_observation_id=index,
                created_at_utc=observation.observed_at_utc,
                **observation.model_dump(),
            )
            for index, observation in enumerate(observations, start=701)
        ]


def test_availability_repository_persists_lineups_injuries_and_mappings() -> None:
    database = FakeAvailabilityDatabase()
    repository = PostgresAvailabilitySnapshotRepository(database)
    lineups = normalize_lineups(
        _lineup_payload(),
        provider_fixture_id="fixture_123",
        snapshot_time_utc=_now(),
    )
    availabilities = normalize_injuries(
        _injury_payload("team_1", "player_11"),
        provider_team_id="team_1",
        provider_fixture_id="fixture_123",
        snapshot_time_utc=_now(),
    )

    summary = repository.save_sportmonks_fixture_availability(
        lineups=lineups,
        availabilities=availabilities,
        canonical_fixture_id="fix_epl_001",
        provider_fixture_id="fixture_123",
        team_mappings={"team_1": "fd_team_57", "team_2": "fd_team_64"},
        lineup_payload_id=41,
        availability_payload_ids={"team_1": 42},
    )

    assert summary.lineup_snapshots == 2
    assert summary.availability_snapshots == 1
    assert summary.provider_mappings == 6
    assert summary.player_mappings == 3
    assert summary.canonical_team_ids == ["fd_team_57", "fd_team_64"]
    params = [item[1] for item in database.queries]
    assert any(item.get("fixture_id") == "fix_epl_001" for item in params)
    assert any(item.get("player_id") == "sm_player_player_10" for item in params)


def test_sportmonks_availability_sync_saves_raw_payloads_and_snapshots() -> None:
    database = FakeAvailabilityDatabase()
    observation_repository = FakeObservationRepository()
    adapter = SportMonksAdapter(
        SportMonksConfig(api_token="test-token"),
        transport=FakeSportMonksAvailabilityTransport(),
    )

    result = sync_sportmonks_fixture_availability(
        adapter=adapter,
        raw_payload_repository=PostgresProviderRawPayloadRepository(database),
        sync_run_repository=PostgresProviderSyncRunRepository(database),
        availability_repository=PostgresAvailabilitySnapshotRepository(database),
        observation_repository=observation_repository,
        provider_fixture_id="fixture_123",
        canonical_fixture_id="fix_epl_001",
        team_mappings={"team_1": "fd_team_57", "team_2": "fd_team_64"},
    )

    assert result.sync_run is not None
    assert result.sync_run.status == "completed"
    assert len(result.raw_payloads) == 3
    assert len(result.lineups) == 2
    assert len(result.availabilities) == 2
    assert result.availability_write is not None
    assert result.availability_write.lineup_snapshots == 2
    assert result.availability_write.availability_snapshots == 2
    assert result.provider_observation_count == 9
    assert len(result.provider_observations) == 9
    assert {observation.capability for observation in observation_repository.observations} == {
        "injuries",
        "lineups",
    }
    assert any(
        observation.field_name
        == "availability:fd_team_57:sm_player_player_11:status"
        for observation in observation_repository.observations
    )
    assert all("test-token" not in str(query_params) for _, query_params in database.queries)


def _lineup_payload() -> dict[str, object]:
    return {
        "data": [
            {
                "fixture_id": "fixture_123",
                "team_id": "team_1",
                "player_id": "player_10",
                "player": {"name": "Home Goalkeeper"},
                "type": "confirmed starting",
                "position": "Goalkeeper",
                "is_starter": True,
            },
            {
                "fixture_id": "fixture_123",
                "team_id": "team_2",
                "player_id": "player_20",
                "player": {"name": "Away Forward"},
                "type": "expected lineup",
                "probability": 0.7,
            },
        ]
    }


def _injury_payload(team_id: str, player_id: str) -> dict[str, object]:
    return {
        "data": [
            {
                "fixture_id": "fixture_123",
                "team_id": team_id,
                "player_id": player_id,
                "player": {"name": f"Player {player_id}"},
                "type": "injury",
                "reason": "Knee",
            }
        ]
    }


def _now() -> datetime:
    return datetime(2026, 5, 6, 9, 0, tzinfo=UTC)


def _sync_row(
    *,
    status: str,
    entity_count: int,
    metadata: object,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "provider_sync_run_id": 23,
        "provider_name": "sportmonks",
        "capability": "lineups_injuries",
        "status": status,
        "started_at": datetime(2026, 5, 6, tzinfo=UTC),
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "entity_count": entity_count,
        "error_message": error_message,
        "metadata_json": metadata,
    }
