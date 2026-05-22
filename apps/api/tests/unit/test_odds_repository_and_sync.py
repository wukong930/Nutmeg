from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.conflicts import ProviderObservation, StoredProviderObservation
from nutmeg.providers.odds_repository import PostgresOddsSnapshotRepository
from nutmeg.providers.odds_sync import sync_the_odds_api_event_odds
from nutmeg.providers.repository import (
    PostgresProviderRawPayloadRepository,
    PostgresProviderSyncRunRepository,
)
from nutmeg.providers.the_odds_api import (
    TheOddsApiAdapter,
    TheOddsApiConfig,
    normalize_event_odds,
)


class FakeOddsDatabase:
    def __init__(self) -> None:
        self.queries: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.queries.append((query, params))
        if "INSERT INTO raw_provider_payloads" in query:
            return {"payload_id": 31, "fetched_at": datetime(2026, 5, 6, tzinfo=UTC)}
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
            return {"mapping_id": 41}
        if "INSERT INTO odds_snapshots" in query:
            return {
                "odds_snapshot_id": 51,
                "inserted": params.get("payload_id") == 31,
            }
        raise AssertionError(f"unexpected query: {query}")


class FakeOddsTransport:
    def get_json(self, path: str, query: dict[str, object]) -> object:
        assert path == "/sports/soccer_epl/events/event_123/odds"
        assert query["apiKey"] == "__redacted__"
        return _event_payload()


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
                provider_observation_id=800 + index,
                created_at_utc=datetime(2026, 5, 6, 0, 1, tzinfo=UTC),
                **observation.model_dump(),
            )
            for index, observation in enumerate(observations, start=1)
        ]


def test_odds_snapshot_repository_persists_the_odds_api_rows_and_mapping() -> None:
    database = FakeOddsDatabase()
    repository = PostgresOddsSnapshotRepository(database)
    snapshots = normalize_event_odds(_event_payload())

    summary = repository.save_the_odds_api_event_odds(
        snapshots,
        canonical_fixture_id="fix_epl_001",
        provider_event_id="event_123",
        payload_id=31,
    )

    assert summary.odds_snapshots == len(snapshots)
    assert summary.inserted_snapshots == len(snapshots)
    assert summary.updated_snapshots == 0
    assert summary.provider_mappings == 1
    assert summary.bookmaker_count == 1
    assert summary.market_types == ["1x2", "asian_handicap"]
    assert summary.canonical_fixture_id == "fix_epl_001"
    params = [item[1] for item in database.queries]
    assert any(item.get("provider_entity_id") == "event_123" for item in params)
    assert any(item.get("fixture_id") == "fix_epl_001" for item in params)
    assert all("THE_ODDS_API_KEY" not in str(item) for item in params)


def test_the_odds_api_event_odds_sync_saves_raw_payload_and_snapshots() -> None:
    database = FakeOddsDatabase()
    observation_repository = FakeObservationRepository()
    adapter = TheOddsApiAdapter(
        TheOddsApiConfig(api_key="test-key"),
        transport=FakeOddsTransport(),
    )

    result = sync_the_odds_api_event_odds(
        adapter=adapter,
        raw_payload_repository=PostgresProviderRawPayloadRepository(database),
        sync_run_repository=PostgresProviderSyncRunRepository(database),
        odds_repository=PostgresOddsSnapshotRepository(database),
        observation_repository=observation_repository,
        sport_key="soccer_epl",
        provider_event_id="event_123",
        canonical_fixture_id="fix_epl_001",
        regions="eu",
        markets="h2h,spreads",
        bookmakers=None,
    )

    assert result.sync_run is not None
    assert result.sync_run.status == "completed"
    assert result.raw_payload is not None
    assert result.raw_payload.payload_id == 31
    assert len(result.snapshots) == 5
    assert result.odds_write is not None
    assert result.odds_write.odds_snapshots == 5
    assert result.odds_write.inserted_snapshots == 5
    assert result.odds_write.updated_snapshots == 0
    assert result.request_params["oddsFormat"] == "decimal"
    assert len(observation_repository.saved) == 5
    assert observation_repository.saved[0].canonical_entity_id == "fix_epl_001"
    assert observation_repository.saved[0].capability == "odds"
    assert observation_repository.saved[0].payload_id == 31


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
        "provider_sync_run_id": 17,
        "provider_name": "the-odds-api",
        "capability": "odds",
        "status": status,
        "started_at": datetime(2026, 5, 6, tzinfo=UTC),
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "entity_count": entity_count,
        "error_message": error_message,
        "metadata_json": metadata,
    }


def _event_payload() -> dict[str, object]:
    return {
        "id": "event_123",
        "sport_key": "soccer_epl",
        "sport_title": "EPL",
        "commence_time": "2026-05-06T19:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "bookmakers": [
            {
                "key": "pinnacle",
                "last_update": "2026-05-06T07:58:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-05-06T08:00:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.1},
                            {"name": "Draw", "price": 3.2},
                            {"name": "Liverpool", "price": 3.4},
                        ],
                    },
                    {
                        "key": "spreads",
                        "last_update": "2026-05-06T08:01:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 1.91, "point": -0.5},
                            {"name": "Liverpool", "price": 1.93, "point": 0.5},
                        ],
                    },
                ],
            }
        ],
    }
