from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from nutmeg.accuracy.local_postgres_runner import (
    DELETE_CALIBRATION_BUCKETS_QUERY,
    DELETE_MODEL_COMPARISONS_QUERY,
    DELETE_PREDICTION_EVALUATIONS_QUERY,
    INSERT_PREDICTION_SNAPSHOT_QUERY,
    INSERT_SCORE_GRID_QUERY,
    UPSERT_COMPETITION_QUERY,
    UPSERT_FIXTURE_QUERY,
    UPSERT_MODEL_VERSION_QUERY,
    UPSERT_RESULT_QUERY,
    UPSERT_TEAM_QUERY,
    run_mock_accuracy_postgres_e2e,
)
from nutmeg.accuracy.postgres_write_repository import (
    INSERT_MODEL_COMPARISON_REPORT_QUERY,
    INSERT_PREDICTION_EVALUATION_QUERY,
    UPSERT_CALIBRATION_BUCKET_QUERY,
)
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.features.repository import INSERT_FEATURE_SNAPSHOT_QUERY


class FakeLocalAccuracyDatabase:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.score_grid_id = 100
        self.feature_snapshot_id = 150
        self.prediction_snapshot_id = 200
        self.evaluation_id = 300
        self.comparison_report_id = 400

    def execute(self, query: str, params: QueryParams) -> None:
        self.execute_calls.append((query, params))

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == UPSERT_MODEL_VERSION_QUERY:
            return {"model_version": params["model_version"]}
        if query == UPSERT_COMPETITION_QUERY:
            return {"competition_id": params["competition_id"]}
        if query == UPSERT_TEAM_QUERY:
            return {"team_id": params["team_id"]}
        if query == UPSERT_FIXTURE_QUERY:
            return {"fixture_id": params["fixture_id"]}
        if query == UPSERT_RESULT_QUERY:
            return {"fixture_id": params["fixture_id"]}
        if query == INSERT_SCORE_GRID_QUERY:
            self.score_grid_id += 1
            return {"score_grid_id": self.score_grid_id}
        if query == INSERT_FEATURE_SNAPSHOT_QUERY:
            self.feature_snapshot_id += 1
            return {"feature_snapshot_id": self.feature_snapshot_id}
        if query == INSERT_PREDICTION_SNAPSHOT_QUERY:
            self.prediction_snapshot_id += 1
            return {"prediction_snapshot_id": self.prediction_snapshot_id}
        if query == INSERT_PREDICTION_EVALUATION_QUERY:
            self.evaluation_id += 1
            return {
                "evaluation_id": self.evaluation_id,
                "created_at": datetime(2026, 5, 8, 0, 0, tzinfo=UTC),
            }
        if query == UPSERT_CALIBRATION_BUCKET_QUERY:
            return _calibration_row(params)
        if query == INSERT_MODEL_COMPARISON_REPORT_QUERY:
            self.comparison_report_id += 1
            return {
                "comparison_report_id": self.comparison_report_id,
                "created_at": datetime(2026, 5, 8, 0, 30, tzinfo=UTC),
            }
        raise AssertionError(f"unexpected query: {query}")


def test_mock_accuracy_postgres_runner_seeds_and_persists_local_loop() -> None:
    database = FakeLocalAccuracyDatabase()

    result = run_mock_accuracy_postgres_e2e(database)

    assert result.fixture_count == 3
    assert set(result.prediction_snapshot_ids) == {
        "fix_epl_001",
        "fix_epl_002",
        "fix_j1_001",
    }
    assert result.evaluation_ids == [301, 302, 303]
    assert result.calibration_observation_count == 9
    assert result.model_comparison_report_id == 401
    assert [query for query, _ in database.execute_calls[:3]] == [
        DELETE_MODEL_COMPARISONS_QUERY,
        DELETE_CALIBRATION_BUCKETS_QUERY,
        DELETE_PREDICTION_EVALUATIONS_QUERY,
    ]
    assert _call_count(database, UPSERT_MODEL_VERSION_QUERY) == 2
    assert _call_count(database, UPSERT_COMPETITION_QUERY) == 3
    assert _call_count(database, UPSERT_TEAM_QUERY) == 6
    assert _call_count(database, UPSERT_FIXTURE_QUERY) == 3
    assert _call_count(database, UPSERT_RESULT_QUERY) == 3
    assert _call_count(database, INSERT_FEATURE_SNAPSHOT_QUERY) == 3
    assert _call_count(database, INSERT_SCORE_GRID_QUERY) == 3
    assert _call_count(database, INSERT_PREDICTION_SNAPSHOT_QUERY) == 3
    assert _call_count(database, INSERT_PREDICTION_EVALUATION_QUERY) == 3
    assert _call_count(database, UPSERT_CALIBRATION_BUCKET_QUERY) == 9
    assert _call_count(database, INSERT_MODEL_COMPARISON_REPORT_QUERY) == 1


def test_mock_accuracy_postgres_runner_can_skip_reset() -> None:
    database = FakeLocalAccuracyDatabase()

    run_mock_accuracy_postgres_e2e(database, reset=False)

    assert database.execute_calls == []


def _call_count(database: FakeLocalAccuracyDatabase, query: str) -> int:
    return sum(1 for called_query, _ in database.fetch_one_calls if called_query == query)


def _calibration_row(params: Mapping[str, object]) -> DatabaseRow:
    return {
        "model_version": params["model_version"],
        "market_type": params["market_type"],
        "outcome": params["outcome"],
        "competition_id": params["competition_id"],
        "bucket_start": params["bucket_start"],
        "bucket_end": params["bucket_end"],
        "sample_size": 1,
        "predicted_probability_sum": params["predicted_probability"],
        "actual_count": params["actual_count"],
    }
