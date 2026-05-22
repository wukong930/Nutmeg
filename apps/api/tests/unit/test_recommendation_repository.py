from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import loads

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PostgresRecommendationRepository,
    RecommendationCandidateQueryOptions,
    RecommendationGenerationOptions,
    run_recommendation_generation,
)
from nutmeg.recommendations.repository import (
    GET_RECOMMENDATION_RUN_QUERY,
    INSERT_RECOMMENDATION_CANDIDATE_POOL_ITEM_QUERY,
    INSERT_RECOMMENDATION_CANDIDATE_POOL_SNAPSHOT_QUERY,
    INSERT_RECOMMENDATION_CANDIDATE_QUERY,
    INSERT_RECOMMENDATION_LIFECYCLE_EVENT_QUERY,
    INSERT_RECOMMENDATION_LOCKED_LEG_QUERY,
    INSERT_RECOMMENDATION_RUN_QUERY,
    LIST_RECOMMENDATION_CANDIDATES_QUERY,
    LIST_RECOMMENDATION_LIFECYCLE_EVENTS_QUERY,
    LIST_RECOMMENDATION_LOCKED_LEGS_QUERY,
    UPDATE_RECOMMENDATION_LOCKED_LEG_STATUS_QUERY,
    UPDATE_RECOMMENDATION_RUN_LIFECYCLE_QUERY,
)


class FakeRecommendationDatabase:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = list(rows)
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.next_candidate_id = 101
        self.next_candidate_pool_item_id = 801
        self.run_status = "current"
        self.locked_fixture_ids: list[str] = []
        self.locked_leg_status = "locked"

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_RECOMMENDATION_CANDIDATES_QUERY:
            return self.rows
        if query == LIST_RECOMMENDATION_LOCKED_LEGS_QUERY:
            return [
                {
                    "recommendation_locked_leg_id": 301,
                    "recommendation_run_id": params["recommendation_run_id"],
                    "fixture_id": "fix_a",
                    "market_type": "1x2",
                    "outcome": "home_win",
                    "locked_at_utc": datetime(2026, 5, 9, 11, tzinfo=UTC),
                    "status": self.locked_leg_status,
                    "metadata_json": {"operator": "unit-test"},
                }
            ]
        if query == LIST_RECOMMENDATION_LIFECYCLE_EVENTS_QUERY:
            return [
                {
                    "recommendation_lifecycle_event_id": 501,
                    "recommendation_run_id": params["recommendation_run_id"],
                    "recommendation_key": "rec-key",
                    "from_status": "candidate",
                    "to_status": "current",
                    "reason_code": "recommendation_generated",
                    "event_time_utc": datetime(2026, 5, 9, 10, tzinfo=UTC),
                    "metadata_json": {"source": "unit-test"},
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_RECOMMENDATION_RUN_QUERY:
            return {
                "recommendation_run_id": 77,
                "created_at": datetime(2026, 5, 9, 12, tzinfo=UTC),
            }
        if query == INSERT_RECOMMENDATION_CANDIDATE_QUERY:
            row = {"recommendation_candidate_id": self.next_candidate_id}
            self.next_candidate_id += 1
            return row
        if query == INSERT_RECOMMENDATION_CANDIDATE_POOL_SNAPSHOT_QUERY:
            return {"recommendation_candidate_pool_snapshot_id": 701}
        if query == INSERT_RECOMMENDATION_CANDIDATE_POOL_ITEM_QUERY:
            row = {
                "recommendation_candidate_pool_item_id": (
                    self.next_candidate_pool_item_id
                )
            }
            self.next_candidate_pool_item_id += 1
            return row
        if query == INSERT_RECOMMENDATION_LIFECYCLE_EVENT_QUERY:
            return {"recommendation_lifecycle_event_id": 501}
        if query == GET_RECOMMENDATION_RUN_QUERY:
            return _run_row(status=self.run_status, locked_fixture_ids=self.locked_fixture_ids)
        if query == INSERT_RECOMMENDATION_LOCKED_LEG_QUERY:
            return {"recommendation_locked_leg_id": 301}
        if query == UPDATE_RECOMMENDATION_LOCKED_LEG_STATUS_QUERY:
            self.locked_leg_status = str(params["status"])
            return {
                "recommendation_locked_leg_id": 301,
                "recommendation_run_id": params["recommendation_run_id"],
                "fixture_id": params["fixture_id"],
                "market_type": params["market_type"],
                "outcome": params["outcome"],
                "locked_at_utc": datetime(2026, 5, 9, 11, tzinfo=UTC),
                "status": self.locked_leg_status,
                "metadata_json": {"operator": "unit-test"},
            }
        if query == UPDATE_RECOMMENDATION_RUN_LIFECYCLE_QUERY:
            self.run_status = str(params["status"])
            locked_fixture_ids_json = params["locked_fixture_ids_json"]
            if isinstance(locked_fixture_ids_json, str):
                self.locked_fixture_ids = ["fix_a"] if "fix_a" in locked_fixture_ids_json else []
            return _run_row(status=self.run_status, locked_fixture_ids=self.locked_fixture_ids)
        raise AssertionError(f"unexpected query: {query}")


def test_recommendation_repository_lists_candidates_from_market_predictions() -> None:
    database = FakeRecommendationDatabase(
        [
            _candidate_row("fix_a", 11, 31, "home_win", 0.64, 1.8, 0.56, 0.08),
            _candidate_row("fix_b", 12, 32, "away_win", 0.58, 1.9, 0.52, 0.06),
        ]
    )
    repository = PostgresRecommendationRepository(database)

    candidates = repository.list_candidates(
        options=RecommendationCandidateQueryOptions(
            as_of_time_utc=datetime(2026, 5, 9, 10, tzinfo=UTC),
            allowed_markets=("1x2", "cn_handicap_1x2"),
            min_model_edge=0.02,
        )
    )

    assert [candidate.fixture_id for candidate in candidates] == ["fix_a", "fix_b"]
    assert candidates[0].upset_protection_score == 0.42
    query, params = database.fetch_all_calls[0]
    assert query == LIST_RECOMMENDATION_CANDIDATES_QUERY
    assert params["allowed_markets"] == ["1x2", "cn_handicap_1x2"]
    assert params["min_model_edge"] == 0.02
    assert params["require_odds"] is True


def test_recommendation_generation_builds_dry_run_best_selection() -> None:
    database = FakeRecommendationDatabase(
        [
            _candidate_row("fix_a", 11, 31, "home_win", 0.64, 1.8, 0.56, 0.08),
            _candidate_row("fix_b", 12, 32, "away_win", 0.58, 1.9, 0.52, 0.06),
            _candidate_row("fix_a", 13, 33, "draw", 0.26, 3.4, 0.22, 0.04),
        ]
    )

    result = run_recommendation_generation(
        database,
        options=RecommendationGenerationOptions(
            as_of_time_utc=datetime(2026, 5, 9, 10, tzinfo=UTC),
            pass_type="2x1",
            dry_run=True,
        ),
    )

    assert result.dry_run is True
    assert result.generated_count == 1
    assert result.candidate_count == 3
    assert result.selection is not None
    assert result.selection.fixture_ids == ["fix_a", "fix_b"]
    assert result.stored_run is None
    assert database.fetch_one_calls == []


def test_recommendation_generation_persists_run_candidates_and_lifecycle_event() -> None:
    database = FakeRecommendationDatabase(
        [
            _candidate_row("fix_a", 11, 31, "home_win", 0.64, 1.8, 0.56, 0.08),
            _candidate_row("fix_b", 12, 32, "away_win", 0.58, 1.9, 0.52, 0.06),
        ]
    )

    result = run_recommendation_generation(
        database,
        options=RecommendationGenerationOptions(
            as_of_time_utc=datetime(2026, 5, 9, 10, tzinfo=UTC),
            pass_type="2x1",
            dry_run=False,
            internal_trace_json={
                "strategy_selection": {
                    "requested_strategy": "auto",
                    "selected_strategy": "upset_protection",
                    "source": "governance_overview",
                }
            },
        ),
        repository=PostgresRecommendationRepository(database),
    )

    assert result.stored_run is not None
    assert result.stored_run.recommendation_run_id == 77
    assert result.stored_run.recommendation_candidate_ids == [101, 102]
    assert result.stored_run.recommendation_candidate_pool_snapshot_id == 701
    assert result.stored_run.recommendation_candidate_pool_item_ids == [801, 802]
    assert result.stored_run.recommendation_lifecycle_event_ids == [501]
    assert [query for query, _params in database.fetch_one_calls] == [
        INSERT_RECOMMENDATION_RUN_QUERY,
        INSERT_RECOMMENDATION_CANDIDATE_QUERY,
        INSERT_RECOMMENDATION_CANDIDATE_QUERY,
        INSERT_RECOMMENDATION_CANDIDATE_POOL_SNAPSHOT_QUERY,
        INSERT_RECOMMENDATION_CANDIDATE_POOL_ITEM_QUERY,
        INSERT_RECOMMENDATION_CANDIDATE_POOL_ITEM_QUERY,
        INSERT_RECOMMENDATION_LIFECYCLE_EVENT_QUERY,
    ]
    explanation_json = loads(str(database.fetch_one_calls[0][1]["explanation_json"]))
    assert explanation_json["internal_trace"]["strategy_selection"] == {
        "requested_strategy": "auto",
        "selected_strategy": "upset_protection",
        "source": "governance_overview",
    }
    pool_snapshot_params = database.fetch_one_calls[3][1]
    assert pool_snapshot_params["candidate_count"] == 2
    assert pool_snapshot_params["selected_candidate_count"] == 2
    assert "allowed_markets" in str(pool_snapshot_params["candidate_query_json"])
    pool_item_params = database.fetch_one_calls[4][1]
    assert pool_item_params["fixture_id"] == "fix_a"
    assert pool_item_params["selected"] is True
    assert pool_item_params["model_probability"] == 0.64
    assert pool_item_params["calibrated_probability"] is None
    assert pool_item_params["probability_source"] == "model"
    selected_candidate_params = database.fetch_one_calls[1][1]
    assert selected_candidate_params["model_probability"] == 0.64
    assert selected_candidate_params["probability_source"] == "model"


def test_recommendation_repository_locks_leg_and_records_lifecycle_event() -> None:
    database = FakeRecommendationDatabase([])
    repository = PostgresRecommendationRepository(database)

    result = repository.lock_leg(
        77,
        fixture_id="fix_a",
        market_type="1x2",
        outcome="home_win",
        locked_at_utc=datetime(2026, 5, 9, 11, tzinfo=UTC),
        metadata_json={"operator": "unit-test"},
    )

    assert result.run.status == "locked"
    assert result.run.locked_fixture_ids == ["fix_a"]
    assert result.locked_leg is not None
    assert result.locked_leg.fixture_id == "fix_a"
    assert result.event.from_status == "current"
    assert result.event.to_status == "locked"
    assert [query for query, _params in database.fetch_one_calls] == [
        GET_RECOMMENDATION_RUN_QUERY,
        INSERT_RECOMMENDATION_LOCKED_LEG_QUERY,
        UPDATE_RECOMMENDATION_RUN_LIFECYCLE_QUERY,
        INSERT_RECOMMENDATION_LIFECYCLE_EVENT_QUERY,
    ]


def test_recommendation_repository_releases_leg_and_records_lifecycle_event() -> None:
    database = FakeRecommendationDatabase([])
    database.run_status = "locked"
    database.locked_fixture_ids = ["fix_a"]
    repository = PostgresRecommendationRepository(database)

    result = repository.release_leg(
        77,
        fixture_id="fix_a",
        market_type="1x2",
        outcome="home_win",
        released_at_utc=datetime(2026, 5, 9, 11, 30, tzinfo=UTC),
        metadata_json={"operator": "unit-test"},
    )

    assert result.run.status == "current"
    assert result.run.locked_fixture_ids == []
    assert result.locked_leg is not None
    assert result.locked_leg.status == "released"
    assert result.event.from_status == "locked"
    assert result.event.to_status == "current"
    assert result.event.reason_code == "user_released_leg"
    assert [query for query, _params in database.fetch_one_calls] == [
        GET_RECOMMENDATION_RUN_QUERY,
        UPDATE_RECOMMENDATION_LOCKED_LEG_STATUS_QUERY,
        UPDATE_RECOMMENDATION_RUN_LIFECYCLE_QUERY,
        INSERT_RECOMMENDATION_LIFECYCLE_EVENT_QUERY,
    ]
    assert [query for query, _params in database.fetch_all_calls] == [
        LIST_RECOMMENDATION_LOCKED_LEGS_QUERY,
    ]


def test_recommendation_repository_confirms_manual_status() -> None:
    database = FakeRecommendationDatabase([])
    repository = PostgresRecommendationRepository(database)

    result = repository.transition_run_status(
        77,
        to_status="confirmed_manual",
        event_time_utc=datetime(2026, 5, 9, 11, tzinfo=UTC),
        reason_code="user_confirmed_ticket",
    )

    assert result.run.status == "confirmed_manual"
    assert result.event.from_status == "current"
    assert result.event.to_status == "confirmed_manual"


def test_recommendation_repository_reads_lifecycle_detail() -> None:
    database = FakeRecommendationDatabase([])
    repository = PostgresRecommendationRepository(database)

    detail = repository.get_lifecycle_detail(77)

    assert detail.run.recommendation_run_id == 77
    assert detail.locked_legs[0].fixture_id == "fix_a"
    assert detail.events[0].reason_code == "recommendation_generated"


def _candidate_row(
    fixture_id: str,
    prediction_snapshot_id: int,
    market_prediction_id: int,
    outcome: str,
    probability: float,
    decimal_odds: float,
    market_probability: float,
    model_edge: float,
) -> DatabaseRow:
    return {
        "prediction_snapshot_id": prediction_snapshot_id,
        "fixture_id": fixture_id,
        "prediction_time_utc": datetime(2026, 5, 9, 9, tzinfo=UTC),
        "model_version": "poisson-m1.0.0",
        "data_quality_score": 88,
        "competition_id": "EPL",
        "kickoff_time_utc": datetime(2026, 5, 10, 12, tzinfo=UTC),
        "market_prediction_id": market_prediction_id,
        "market_type": "1x2",
        "line": None,
        "side": None,
        "outcome": outcome,
        "probability": probability,
        "decimal_odds": decimal_odds,
        "market_probability": market_probability,
        "model_edge": model_edge,
        "upset_score": 0.42,
        "favorite_fragility_score": 0.37,
    }


def _run_row(*, status: str, locked_fixture_ids: list[str]) -> DatabaseRow:
    return {
        "recommendation_run_id": 77,
        "run_key": "rec-key",
        "status": status,
        "selected_fixture_ids_json": ["fix_a", "fix_b"],
        "locked_fixture_ids_json": locked_fixture_ids,
        "created_at": datetime(2026, 5, 9, 10, tzinfo=UTC),
    }
