from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.canonical_repository import CanonicalFixtureWriteSummary
from nutmeg.providers.conflicts import ProviderObservation, StoredProviderObservation
from nutmeg.providers.football_data_org import FootballDataOrgAdapter
from nutmeg.providers.football_data_org.normalizer import NormalizedFixture
from nutmeg.providers.repository import (
    PostgresProviderRawPayloadRepository,
    PostgresProviderSyncRunRepository,
    stable_request_hash,
)
from nutmeg.providers.sync import sync_football_data_fixtures


class FakeDatabase:
    def __init__(self) -> None:
        self.queries: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.queries.append((query, params))
        if "INSERT INTO raw_provider_payloads" in query:
            return {"payload_id": 11, "fetched_at": datetime(2026, 5, 6, tzinfo=UTC)}
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
        raise AssertionError(f"unexpected query: {query}")


class FakeTransport:
    def get_json(
        self,
        path: str,
        query: dict[str, object],
        require_token: bool,
    ) -> dict[str, object]:
        return {
            "filters": query,
            "matches": [
                {
                    "id": 330299,
                    "utcDate": "2026-05-06T19:00:00Z",
                    "status": "SCHEDULED",
                    "matchday": 34,
                    "competition": {"id": 2021, "code": "PL", "name": "Premier League"},
                    "season": {"id": 2025},
                    "homeTeam": {"id": 57, "name": "Arsenal FC", "tla": "ARS"},
                    "awayTeam": {"id": 64, "name": "Liverpool FC", "tla": "LIV"},
                    "score": {"fullTime": {"home": None, "away": None}},
                }
            ],
        }


class FakeCanonicalRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def upsert_fixtures(
        self,
        fixtures: list[NormalizedFixture],
        *,
        canonical_competition_id: str,
        season: str,
        provider_competition_id: str | None = None,
        competition_metadata: object | None = None,
    ) -> CanonicalFixtureWriteSummary:
        self.calls.append(
            {
                "fixture_count": len(fixtures),
                "canonical_competition_id": canonical_competition_id,
                "season": season,
                "provider_competition_id": provider_competition_id,
                "competition_metadata": competition_metadata,
            }
        )
        return CanonicalFixtureWriteSummary(
            competitions=1,
            seasons=1,
            teams=2,
            fixtures=len(fixtures),
            provider_mappings=5,
            canonical_fixture_ids=["fd_fixture_330299"],
        )


class FakeObservationRepository:
    def __init__(self) -> None:
        self.saved: list[ProviderObservation] = []

    def save_observations(
        self,
        observations: list[ProviderObservation],
    ) -> list[StoredProviderObservation]:
        self.saved.extend(observations)
        return [
            StoredProviderObservation(
                provider_observation_id=900 + index,
                created_at_utc=datetime(2026, 5, 6, 0, 1, tzinfo=UTC),
                **observation.model_dump(),
            )
            for index, observation in enumerate(observations, start=1)
        ]


def test_raw_payload_repository_stores_hash_and_secret_free_json() -> None:
    database = FakeDatabase()
    repository = PostgresProviderRawPayloadRepository(database)

    stored = repository.save_raw_payload(
        provider="football-data.org",
        endpoint="/competitions/PL/matches",
        request_params={"season": "2025"},
        response_json={"matches": []},
        entity_type="competition",
        entity_id_hint="PL",
    )

    assert stored.payload_id == 11
    assert stored.request_hash == stable_request_hash(
        endpoint="/competitions/PL/matches",
        request_params={"season": "2025"},
    )
    params = database.queries[0][1]
    assert "FOOTBALL_DATA_API_KEY" not in str(params["response_json"])


def test_provider_sync_repository_records_start_complete_and_fail() -> None:
    database = FakeDatabase()
    repository = PostgresProviderSyncRunRepository(database)

    started = repository.start_sync_run(
        provider_name="football-data.org",
        capability="fixtures",
        metadata_json={"competition_id": "PL"},
    )
    completed = repository.complete_sync_run(
        provider_sync_run_id=started.provider_sync_run_id,
        entity_count=2,
        metadata_json={"raw_payload_id": 11},
    )
    failed = repository.fail_sync_run(
        provider_sync_run_id=started.provider_sync_run_id,
        error_message="boom",
        metadata_json={"competition_id": "PL"},
    )

    assert started.status == "running"
    assert completed.status == "completed"
    assert completed.entity_count == 2
    assert failed.status == "failed"
    assert failed.error_message == "boom"


def test_football_data_fixture_sync_saves_raw_payload_and_normalizes_matches() -> None:
    database = FakeDatabase()
    result = sync_football_data_fixtures(
        adapter=FootballDataOrgAdapter(transport=FakeTransport()),
        raw_payload_repository=PostgresProviderRawPayloadRepository(database),
        sync_run_repository=PostgresProviderSyncRunRepository(database),
        competition_id="PL",
        season="2025",
    )

    assert result.sync_run.status == "completed"
    assert result.raw_payload is not None
    assert result.raw_payload.payload_id == 11
    assert len(result.fixtures) == 1
    assert result.fixtures[0].provider_entity_id == "330299"
    assert result.fixtures[0].status == "scheduled"
    assert result.fixtures[0].home_team.canonical_hint == "ARS"
    assert result.canonical_write is None


def test_football_data_fixture_sync_can_persist_canonical_entities() -> None:
    database = FakeDatabase()
    canonical_repository = FakeCanonicalRepository()
    observation_repository = FakeObservationRepository()

    result = sync_football_data_fixtures(
        adapter=FootballDataOrgAdapter(transport=FakeTransport()),
        raw_payload_repository=PostgresProviderRawPayloadRepository(database),
        sync_run_repository=PostgresProviderSyncRunRepository(database),
        canonical_repository=canonical_repository,
        observation_repository=observation_repository,
        competition_id="PL",
        canonical_competition_id="EPL",
        season="2025",
    )

    assert result.sync_run is not None
    assert result.sync_run.status == "completed"
    assert result.canonical_competition_id == "EPL"
    assert result.canonical_write is not None
    assert result.canonical_write.fixtures == 1
    assert result.canonical_write.canonical_fixture_ids == ["fd_fixture_330299"]
    assert canonical_repository.calls == [
        {
            "fixture_count": 1,
            "canonical_competition_id": "EPL",
            "season": "2025",
            "provider_competition_id": "PL",
            "competition_metadata": None,
        }
    ]
    assert {
        (observation.capability, observation.field_name)
        for observation in observation_repository.saved
    } == {
        ("fixtures", "kickoff_time_utc"),
        ("fixtures", "status"),
        ("fixtures", "home_team_provider_id"),
        ("fixtures", "away_team_provider_id"),
    }
    assert observation_repository.saved[0].canonical_entity_id == "fd_fixture_330299"
    assert observation_repository.saved[0].payload_id == 11


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
        "provider_sync_run_id": 7,
        "provider_name": "football-data.org",
        "capability": "fixtures",
        "status": status,
        "started_at": datetime(2026, 5, 6, tzinfo=UTC),
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "entity_count": entity_count,
        "error_message": error_message,
        "metadata_json": metadata,
    }
