from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.parlay import (
    MarketPredictionParlayGenerationOptions,
    PostgresParlayRecommendationRepository,
    run_market_prediction_parlay_generation,
)
from nutmeg.parlay.generator import LIST_PARLAY_CANDIDATES_FROM_MARKET_PREDICTIONS_QUERY
from nutmeg.parlay.repository import (
    INSERT_PARLAY_ATOMIC_BET_QUERY,
    INSERT_PARLAY_LEG_QUERY,
    INSERT_PARLAY_RECOMMENDATION_QUERY,
    UPSERT_PARLAY_MODEL_VERSION_QUERY,
)


class FakeParlayGenerationDatabase:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = list(rows)
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.next_leg_id = 101
        self.next_atomic_id = 201

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PARLAY_CANDIDATES_FROM_MARKET_PREDICTIONS_QUERY:
            return self.rows
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == UPSERT_PARLAY_MODEL_VERSION_QUERY:
            return {"model_version": params["model_version"]}
        if query == INSERT_PARLAY_RECOMMENDATION_QUERY:
            return {
                "parlay_recommendation_id": 77,
                "created_at": datetime(2026, 5, 7, 12, tzinfo=UTC),
            }
        if query == INSERT_PARLAY_LEG_QUERY:
            row = {"parlay_leg_id": self.next_leg_id}
            self.next_leg_id += 1
            return row
        if query == INSERT_PARLAY_ATOMIC_BET_QUERY:
            row = {"atomic_bet_id": self.next_atomic_id}
            self.next_atomic_id += 1
            return row
        raise AssertionError(f"unexpected query: {query}")


def test_market_prediction_parlay_generation_builds_dry_run_recommendation() -> None:
    database = FakeParlayGenerationDatabase(
        [
            _candidate_row("fix_a", 11, 31, "home_win", 0.62, 2.1, 0.48, 0.14),
            _candidate_row("fix_b", 12, 32, "away_win", 0.55, 1.95, 0.50, 0.05),
            _candidate_row("fix_a", 13, 33, "draw", 0.25, 3.6, 0.20, 0.05),
        ]
    )

    result = run_market_prediction_parlay_generation(
        database,
        options=_options(dry_run=True),
    )

    assert result.dry_run is True
    assert result.candidate_count == 3
    assert result.generated_count == 1
    assert result.stored_recommendation_ids == []
    assert result.recommendations[0].recommendation.model_version == "poisson-m1.0.0"
    assert result.recommendations[0].evaluation.total_atomic_bets == 1
    assert [candidate.fixture_id for candidate in result.recommendations[0].candidates] == [
        "fix_a",
        "fix_b",
    ]
    query, params = database.fetch_all_calls[0]
    assert query == LIST_PARLAY_CANDIDATES_FROM_MARKET_PREDICTIONS_QUERY
    assert params["allowed_markets"] == ["1x2", "cn_handicap_1x2"]
    assert params["fixture_ids"] is None
    assert database.fetch_one_calls == []


def test_market_prediction_parlay_generation_persists_when_not_dry_run() -> None:
    database = FakeParlayGenerationDatabase(
        [
            _candidate_row("fix_a", 11, 31, "home_win", 0.62, 2.1, 0.48, 0.14),
            _candidate_row("fix_b", 12, 32, "away_win", 0.55, 1.95, 0.50, 0.05),
        ]
    )

    result = run_market_prediction_parlay_generation(
        database,
        options=_options(dry_run=False),
        repository=PostgresParlayRecommendationRepository(database),
    )

    assert result.stored_recommendation_ids == [77]
    assert [query for query, _params in database.fetch_one_calls].count(
        INSERT_PARLAY_RECOMMENDATION_QUERY
    ) == 1


def test_market_prediction_parlay_generation_can_limit_to_workflow_fixtures() -> None:
    database = FakeParlayGenerationDatabase(
        [
            _candidate_row("fix_a", 11, 31, "home_win", 0.62, 2.1, 0.48, 0.14),
            _candidate_row("fix_b", 12, 32, "away_win", 0.55, 1.95, 0.50, 0.05),
        ]
    )

    run_market_prediction_parlay_generation(
        database,
        options=MarketPredictionParlayGenerationOptions(
            as_of_time_utc=datetime(2026, 5, 7, 10, tzinfo=UTC),
            fixture_ids=("fix_a", "fix_b"),
            dry_run=True,
        ),
    )

    _query, params = database.fetch_all_calls[0]
    assert params["fixture_ids"] == ["fix_a", "fix_b"]


def test_market_prediction_parlay_generation_requires_distinct_fixture_candidates() -> None:
    database = FakeParlayGenerationDatabase(
        [
            _candidate_row("fix_a", 11, 31, "home_win", 0.62, 2.1, 0.48, 0.14),
            _candidate_row("fix_a", 13, 33, "draw", 0.25, 3.6, 0.20, 0.05),
        ]
    )

    result = run_market_prediction_parlay_generation(
        database,
        options=_options(dry_run=True),
    )

    assert result.generated_count == 0
    assert result.warnings == ["insufficient_distinct_fixture_candidates"]


def test_market_prediction_parlay_generation_requires_repository_for_commit() -> None:
    database = FakeParlayGenerationDatabase(
        [
            _candidate_row("fix_a", 11, 31, "home_win", 0.62, 2.1, 0.48, 0.14),
            _candidate_row("fix_b", 12, 32, "away_win", 0.55, 1.95, 0.50, 0.05),
        ]
    )

    with pytest.raises(ValueError, match="repository is required"):
        run_market_prediction_parlay_generation(database, options=_options(dry_run=False))


def _options(*, dry_run: bool) -> MarketPredictionParlayGenerationOptions:
    return MarketPredictionParlayGenerationOptions(
        as_of_time_utc=datetime(2026, 5, 7, 10, tzinfo=UTC),
        dry_run=dry_run,
    )


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
        "prediction_time_utc": datetime(2026, 5, 7, 9, tzinfo=UTC),
        "model_version": "poisson-m1.0.0",
        "data_quality_score": 82,
        "competition_id": "EPL",
        "kickoff_time_utc": datetime(2026, 5, 8, 12, tzinfo=UTC),
        "market_prediction_id": market_prediction_id,
        "market_type": "1x2",
        "line": None,
        "side": None,
        "outcome": outcome,
        "probability": probability,
        "decimal_odds": decimal_odds,
        "market_probability": market_probability,
        "odds_snapshot_time_utc": datetime(2026, 5, 7, 9, 30, tzinfo=UTC),
        "model_edge": model_edge,
    }
