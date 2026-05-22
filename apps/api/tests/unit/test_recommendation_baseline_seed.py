from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.predictions.repository import INSERT_MARKET_PREDICTION_QUERY
from nutmeg.recommendations.baseline_seed import (
    INSERT_BASELINE_ODDS_SNAPSHOT_QUERY,
    UPSERT_BASELINE_RESULT_QUERY,
    RecommendationBaselineSeedOptions,
    _baseline_fixtures,
    _options_from_args,
    _parse_args,
    run_recommendation_baseline_seed,
)


class FakeBaselineSeedDatabase:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.next_id = 1

    def execute(self, query: str, params: QueryParams) -> None:
        self.execute_calls.append((query, params))

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        row_id = self.next_id
        self.next_id += 1
        return _returning_row(row_id, params=params)


def test_baseline_seed_writes_full_deterministic_fixture_chain() -> None:
    database = FakeBaselineSeedDatabase()

    result = run_recommendation_baseline_seed(
        database,
        options=RecommendationBaselineSeedOptions(
            as_of_time_utc=datetime(2026, 5, 12, 0, 0, tzinfo=UTC),
        ),
    )

    assert result.fixture_count == 8
    assert result.profile == "happy_path"
    assert len(result.feature_snapshot_ids) == 8
    assert len(result.prediction_snapshot_ids) == 8
    assert result.odds_snapshot_count == 24
    assert result.result_count == 8
    assert result.summary_json["profile"] == "happy_path"
    assert result.summary_json["odds_scope"] == "1x2_only"
    assert any(
        "DELETE FROM recommendation_run_evaluations" in query
        for query, _params in database.execute_calls
    )
    odds_calls = [
        params
        for query, params in database.fetch_one_calls
        if query == INSERT_BASELINE_ODDS_SNAPSHOT_QUERY
    ]
    assert len(odds_calls) == 24
    assert {params["market_type"] for params in odds_calls} == {"1x2"}
    assert {params["provider"] for params in odds_calls} == {
        "deterministic-baseline"
    }


def test_baseline_seed_can_skip_reset() -> None:
    database = FakeBaselineSeedDatabase()

    result = run_recommendation_baseline_seed(
        database,
        options=RecommendationBaselineSeedOptions(reset=False),
    )

    assert result.reset is False
    assert database.execute_calls == []
    assert result.fixture_ids[0] == "bench_v3_001"


def test_baseline_seed_mixed_profile_writes_regression_outcomes() -> None:
    database = FakeBaselineSeedDatabase()

    result = run_recommendation_baseline_seed(
        database,
        options=RecommendationBaselineSeedOptions(profile="mixed_outcomes"),
    )

    assert result.profile == "mixed_outcomes"
    assert result.fixture_count == 8
    assert result.odds_snapshot_count == 24
    assert result.summary_json["profile"] == "mixed_outcomes"
    result_calls = {
        str(params["fixture_id"]): params["result_1x2"]
        for query, params in database.fetch_one_calls
        if query == UPSERT_BASELINE_RESULT_QUERY
    }
    assert result_calls["bench_v3_001"] == "home_win"
    assert result_calls["bench_v3_003"] == "away_win"
    assert result_calls["bench_v3_004"] == "draw"
    assert result_calls["bench_v3_005"] == "home_win"
    assert result_calls["bench_v3_006"] == "draw"
    assert result_calls["bench_v3_007"] == "home_win"


def test_baseline_seed_profiles_cover_core_edge_cases() -> None:
    upset = {
        fixture.fixture_id: fixture
        for fixture in _baseline_fixtures(profile="upset_stress")
    }
    assert upset["bench_v3_001"].actual_1x2 == "draw"
    assert upset["bench_v3_003"].actual_1x2 == "draw"
    assert upset["bench_v3_004"].actual_1x2 == "away_win"

    adverse_odds = {
        fixture.fixture_id: fixture
        for fixture in _baseline_fixtures(profile="adverse_odds")
    }
    assert adverse_odds["bench_v3_001"].actual_1x2 == "home_win"
    assert adverse_odds["bench_v3_001"].odds_anchor_outcome == "draw"
    assert adverse_odds["bench_v3_003"].actual_1x2 == "away_win"
    assert adverse_odds["bench_v3_003"].odds_anchor_outcome == "draw"

    low_quality = {
        fixture.fixture_id: fixture
        for fixture in _baseline_fixtures(profile="low_quality_filter")
    }
    assert low_quality["bench_v3_001"].data_quality_score < 50.0
    assert low_quality["bench_v3_003"].data_quality_score < 50.0
    assert low_quality["bench_v3_002"].data_quality_score >= 50.0

    missing_result = {
        fixture.fixture_id: fixture
        for fixture in _baseline_fixtures(profile="missing_result")
    }
    assert missing_result["bench_v3_004"].actual_1x2 is None
    assert missing_result["bench_v3_004"].odds_anchor_outcome == "home_win"
    assert missing_result["bench_v3_008"].actual_1x2 is None


def test_baseline_seed_missing_result_profile_skips_result_rows() -> None:
    database = FakeBaselineSeedDatabase()

    result = run_recommendation_baseline_seed(
        database,
        options=RecommendationBaselineSeedOptions(profile="missing_result"),
    )

    assert result.fixture_count == 8
    assert result.odds_snapshot_count == 24
    assert result.result_count == 6
    assert result.missing_result_fixture_ids == ["bench_v3_004", "bench_v3_008"]
    assert result.summary_json["missing_result_fixture_ids"] == [
        "bench_v3_004",
        "bench_v3_008",
    ]
    result_fixture_ids = {
        str(params["fixture_id"])
        for query, params in database.fetch_one_calls
        if query == UPSERT_BASELINE_RESULT_QUERY
    }
    assert "bench_v3_004" not in result_fixture_ids
    assert "bench_v3_008" not in result_fixture_ids
    assert len(result_fixture_ids) == 6


def test_baseline_seed_adverse_odds_profile_reprices_model_favorites() -> None:
    database = FakeBaselineSeedDatabase()

    result = run_recommendation_baseline_seed(
        database,
        options=RecommendationBaselineSeedOptions(profile="adverse_odds"),
    )

    assert result.profile == "adverse_odds"
    assert result.fixture_count == 8
    assert result.odds_snapshot_count == 24
    market_predictions = {
        (str(params["fixture_id"]), str(params["outcome"])): float(params["probability"])
        for query, params in database.fetch_one_calls
        if query == INSERT_MARKET_PREDICTION_QUERY
        and params["market_type"] == "1x2"
    }
    odds = {
        (str(params["fixture_id"]), str(params["outcome"])): float(
            params["fair_probability"]
        )
        for query, params in database.fetch_one_calls
        if query == INSERT_BASELINE_ODDS_SNAPSHOT_QUERY
    }
    assert odds[("bench_v3_001", "home_win")] > market_predictions[
        ("bench_v3_001", "home_win")
    ]
    assert odds[("bench_v3_003", "away_win")] > market_predictions[
        ("bench_v3_003", "away_win")
    ]
    assert odds[("bench_v3_001", "draw")] < market_predictions[
        ("bench_v3_001", "draw")
    ]


def test_baseline_seed_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--as-of-time-utc",
            "2026-05-13T01:30:00Z",
            "--profile",
            "adverse_odds",
            "--no-reset",
            "--database-url",
            "postgresql://example",
            "--connect-timeout-seconds",
            "7",
        ]
    )

    options = _options_from_args(args)

    assert options.as_of_time_utc == datetime(2026, 5, 13, 1, 30, tzinfo=UTC)
    assert options.profile == "adverse_odds"
    assert options.reset is False
    assert args.database_url == "postgresql://example"
    assert args.connect_timeout_seconds == 7


def _returning_row(row_id: int, *, params: Mapping[str, object]) -> DatabaseRow:
    return {
        "competition_id": params.get("competition_id", "BENCH_V3"),
        "team_id": params.get("team_id", f"team-{row_id}"),
        "fixture_id": params.get("fixture_id", f"fixture-{row_id}"),
        "model_version": params.get("model_version", "poisson-v3.1-baseline"),
        "feature_snapshot_id": row_id,
        "score_grid_id": row_id,
        "prediction_snapshot_id": row_id,
        "market_prediction_id": row_id,
        "odds_snapshot_id": row_id,
    }
