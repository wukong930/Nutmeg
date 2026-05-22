from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from json import loads

import pytest

from nutmeg.accuracy.postgres_write_repository import (
    INSERT_BACKTEST_RUN_QUERY,
    INSERT_MODEL_COMPARISON_REPORT_QUERY,
    INSERT_PREDICTION_EVALUATION_QUERY,
    UPSERT_CALIBRATION_BUCKET_QUERY,
    PostgresAccuracyWriteRepository,
)
from nutmeg.accuracy.summary import CalibrationObservation
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.accuracy import (
    BacktestRunSchema,
    DateWindow,
    ModelComparisonStub,
    ModelVersionMetrics,
    PredictionEvaluation,
)
from nutmeg.domain.settlement import OneXTwoOutcome


class FakeWriteDatabase:
    def __init__(self, rows: Sequence[DatabaseRow]) -> None:
        self.rows = list(rows)
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.calls.append((query, params))
        if not self.rows:
            return None
        return self.rows.pop(0)


def test_postgres_write_repository_saves_prediction_evaluation() -> None:
    database = FakeWriteDatabase(
        [{"evaluation_id": 88, "created_at": "2026-05-07T01:00:00+00:00"}]
    )
    repository = PostgresAccuracyWriteRepository(database)

    stored = repository.save_prediction_evaluation(_evaluation())

    query, params = database.calls[0]
    assert query == INSERT_PREDICTION_EVALUATION_QUERY
    assert params["prediction_snapshot_id"] == 42
    assert params["fixture_id"] == "fix_epl_001"
    assert params["actual_result_1x2"] == "draw"
    assert loads(str(params["market_comparison_json"])) == {"closing_gap": 0.04}
    assert loads(str(params["error_tags_json"])) == ["draw_underestimated"]
    assert stored.evaluation_id == 88
    assert stored.evaluation.created_at == datetime(2026, 5, 7, 1, 0, tzinfo=UTC)


def test_postgres_write_repository_rejects_non_numeric_snapshot_id() -> None:
    repository = PostgresAccuracyWriteRepository(
        FakeWriteDatabase([{"evaluation_id": 88, "created_at": datetime.now(tz=UTC)}])
    )
    evaluation = _evaluation().model_copy(update={"prediction_snapshot_id": "snap_42"})

    with pytest.raises(ValueError, match="numeric Postgres id"):
        repository.save_prediction_evaluation(evaluation)


def test_postgres_write_repository_upserts_calibration_observations() -> None:
    database = FakeWriteDatabase(
        [
            {
                "model_version": "poisson-m1.0.0",
                "market_type": "1x2",
                "outcome": "home_win",
                "competition_id": "EPL",
                "bucket_start": Decimal("0.40"),
                "bucket_end": Decimal("0.50"),
                "sample_size": 10,
                "predicted_probability_sum": Decimal("4.30"),
                "actual_count": 4,
            },
            {
                "model_version": "poisson-m1.0.0",
                "market_type": "1x2",
                "outcome": "draw",
                "competition_id": "EPL",
                "bucket_start": Decimal("0.20"),
                "bucket_end": Decimal("0.30"),
                "sample_size": 8,
                "predicted_probability_sum": Decimal("2.00"),
                "actual_count": 3,
            },
        ]
    )
    repository = PostgresAccuracyWriteRepository(database)

    buckets = repository.upsert_calibration_observations(
        [
            CalibrationObservation(
                market_type="1x2",
                outcome="home_win",
                predicted_probability=0.43,
                actual_occurred=False,
                competition_id="EPL",
            ),
            CalibrationObservation(
                market_type="1x2",
                outcome="draw",
                predicted_probability=0.25,
                actual_occurred=True,
                competition_id="EPL",
            ),
        ],
        model_version="poisson-m1.0.0",
    )

    assert [query for query, _ in database.calls] == [
        UPSERT_CALIBRATION_BUCKET_QUERY,
        UPSERT_CALIBRATION_BUCKET_QUERY,
    ]
    assert database.calls[0][1]["bucket_start"] == 0.4
    assert database.calls[0][1]["actual_count"] == 0
    assert database.calls[1][1]["actual_count"] == 1
    assert buckets[1].actual_frequency == pytest.approx(3 / 8)


def test_postgres_write_repository_saves_backtest_run() -> None:
    database = FakeWriteDatabase(
        [{"backtest_run_id": 7, "created_at": datetime(2026, 5, 8, 0, 0, tzinfo=UTC)}]
    )
    repository = PostgresAccuracyWriteRepository(database)
    backtest_run = BacktestRunSchema(
        mode="as_of_time",
        model_version="poisson-m1.0.0",
        test_window=DateWindow(start_date=date(2026, 1, 1), end_date=date(2026, 5, 1)),
        competitions=["EPL"],
        as_of_time="T-24h",
    )

    stored = repository.save_backtest_run(
        backtest_run,
        metrics_json={"log_loss": 1.02, "sample_size": 24},
        calibration_json={"ece": 0.04},
        report_uri="reports/backtests/poisson.json",
    )

    query, params = database.calls[0]
    assert query == INSERT_BACKTEST_RUN_QUERY
    assert loads(str(params["test_window_json"])) == {
        "start_date": "2026-01-01",
        "end_date": "2026-05-01",
    }
    assert loads(str(params["competitions_json"])) == ["EPL"]
    assert loads(str(params["metrics_json"]))["sample_size"] == 24
    assert stored.backtest_run_id == 7
    assert stored.report_uri == "reports/backtests/poisson.json"


def test_postgres_write_repository_saves_model_comparison_report() -> None:
    database = FakeWriteDatabase(
        [
            {
                "comparison_report_id": 11,
                "created_at": datetime(2026, 5, 8, 0, 30, tzinfo=UTC),
            }
        ]
    )
    repository = PostgresAccuracyWriteRepository(database)
    comparison = ModelComparisonStub(
        candidate_model_version="dc-v1.5-candidate",
        baseline_model_version="poisson-m1.0.0",
        candidate_metrics=ModelVersionMetrics(
            model_version="dc-v1.5-candidate",
            sample_size=40,
            log_loss=0.96,
            brier_score=0.19,
        ),
        baseline_metrics=ModelVersionMetrics(
            model_version="poisson-m1.0.0",
            sample_size=40,
            log_loss=1.01,
            brier_score=0.21,
        ),
        decision_stub="promote_candidate",
        reasons=["candidate_log_loss_not_worse"],
    )

    stored = repository.save_model_comparison_report(comparison)

    query, params = database.calls[0]
    assert query == INSERT_MODEL_COMPARISON_REPORT_QUERY
    assert params["candidate_model_version"] == "dc-v1.5-candidate"
    assert loads(str(params["candidate_metrics_json"]))["log_loss"] == 0.96
    assert loads(str(params["reasons_json"])) == ["candidate_log_loss_not_worse"]
    assert stored.comparison_report_id == 11


def _evaluation() -> PredictionEvaluation:
    return PredictionEvaluation(
        fixture_id="fix_epl_001",
        prediction_snapshot_id="42",
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        model_version="poisson-m1.0.0",
        feature_version="features-m1.0.0",
        calibration_version="calibration-m1.0.0",
        actual_home_goals=1,
        actual_away_goals=1,
        actual_result_1x2=OneXTwoOutcome.DRAW,
        predicted_result_1x2=OneXTwoOutcome.HOME_WIN,
        actual_result_probability=0.26,
        log_loss_1x2=1.347,
        brier_score_1x2=0.62,
        actual_score_probability=0.09,
        actual_score_rank=3,
        market_comparison_json={"closing_gap": 0.04},
        error_tags=["draw_underestimated"],
        created_at=datetime(2026, 5, 7, 0, 0, tzinfo=UTC),
    )
