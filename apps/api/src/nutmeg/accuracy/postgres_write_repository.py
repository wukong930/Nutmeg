from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from json import dumps
from typing import Protocol

from pydantic import BaseModel

from nutmeg.accuracy.calibration import calibration_bucket_key_for_probability
from nutmeg.accuracy.summary import CalibrationObservation
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.accuracy import (
    BacktestRunSchema,
    CalibrationBucket,
    CalibrationBucketKey,
    ModelComparisonStub,
    PredictionEvaluation,
    StoredBacktestRun,
    StoredModelComparisonReport,
    StoredPredictionEvaluation,
)

INSERT_PREDICTION_EVALUATION_QUERY = """
INSERT INTO prediction_evaluations (
  prediction_snapshot_id,
  fixture_id,
  actual_home_goals,
  actual_away_goals,
  actual_result_1x2,
  log_loss_1x2,
  brier_score_1x2,
  actual_score_probability,
  actual_score_rank,
  market_comparison_json,
  error_tags_json
) VALUES (
  %(prediction_snapshot_id)s,
  %(fixture_id)s,
  %(actual_home_goals)s,
  %(actual_away_goals)s,
  %(actual_result_1x2)s,
  %(log_loss_1x2)s,
  %(brier_score_1x2)s,
  %(actual_score_probability)s,
  %(actual_score_rank)s,
  %(market_comparison_json)s::jsonb,
  %(error_tags_json)s::jsonb
)
RETURNING evaluation_id, created_at
"""

UPSERT_CALIBRATION_BUCKET_QUERY = """
INSERT INTO calibration_buckets (
  model_version,
  market_type,
  outcome,
  competition_id,
  bucket_start,
  bucket_end,
  sample_size,
  predicted_probability_sum,
  actual_count
) VALUES (
  %(model_version)s,
  %(market_type)s,
  %(outcome)s,
  %(competition_id)s,
  %(bucket_start)s,
  %(bucket_end)s,
  1,
  %(predicted_probability)s,
  %(actual_count)s
)
ON CONFLICT (
  model_version,
  market_type,
  outcome,
  competition_id,
  bucket_start,
  bucket_end
) DO UPDATE SET
  sample_size = calibration_buckets.sample_size + 1,
  predicted_probability_sum = (
    calibration_buckets.predicted_probability_sum + EXCLUDED.predicted_probability_sum
  ),
  actual_count = calibration_buckets.actual_count + EXCLUDED.actual_count,
  updated_at = now()
RETURNING
  model_version,
  market_type,
  outcome,
  competition_id,
  bucket_start,
  bucket_end,
  sample_size,
  predicted_probability_sum,
  actual_count
"""

INSERT_BACKTEST_RUN_QUERY = """
INSERT INTO model_backtest_runs (
  model_version,
  mode,
  as_of_time,
  train_window_json,
  validation_window_json,
  test_window_json,
  competitions_json,
  metrics_json,
  calibration_json,
  report_uri
) VALUES (
  %(model_version)s,
  %(mode)s,
  %(as_of_time)s,
  %(train_window_json)s::jsonb,
  %(validation_window_json)s::jsonb,
  %(test_window_json)s::jsonb,
  %(competitions_json)s::jsonb,
  %(metrics_json)s::jsonb,
  %(calibration_json)s::jsonb,
  %(report_uri)s
)
RETURNING backtest_run_id, created_at
"""

INSERT_MODEL_COMPARISON_REPORT_QUERY = """
INSERT INTO model_comparison_reports (
  candidate_model_version,
  baseline_model_version,
  candidate_metrics_json,
  baseline_metrics_json,
  decision_stub,
  reasons_json
) VALUES (
  %(candidate_model_version)s,
  %(baseline_model_version)s,
  %(candidate_metrics_json)s::jsonb,
  %(baseline_metrics_json)s::jsonb,
  %(decision_stub)s,
  %(reasons_json)s::jsonb
)
RETURNING comparison_report_id, created_at
"""


class SyncWriteDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one mapping row."""


class PostgresAccuracyWriteRepository:
    def __init__(self, database: SyncWriteDatabaseExecutor) -> None:
        self.database = database

    def save_prediction_evaluation(
        self,
        evaluation: PredictionEvaluation,
    ) -> StoredPredictionEvaluation:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PREDICTION_EVALUATION_QUERY,
                _prediction_evaluation_params(evaluation),
            )
        )
        return StoredPredictionEvaluation(
            evaluation_id=_int(row["evaluation_id"]),
            evaluation=evaluation.model_copy(
                update={"created_at": _datetime(row["created_at"])}
            ),
        )

    def upsert_calibration_observations(
        self,
        observations: Sequence[CalibrationObservation],
        *,
        model_version: str,
        bucket_size: float = 0.10,
    ) -> list[CalibrationBucket]:
        buckets: list[CalibrationBucket] = []
        for observation in observations:
            key = calibration_bucket_key_for_probability(
                predicted_probability=observation.predicted_probability,
                model_version=model_version,
                market_type=observation.market_type,
                outcome=observation.outcome,
                bucket_size=bucket_size,
                competition_id=observation.competition_id,
            )
            row = _required_row(
                self.database.fetch_one(
                    UPSERT_CALIBRATION_BUCKET_QUERY,
                    {
                        "model_version": key.model_version,
                        "market_type": key.market_type,
                        "outcome": key.outcome,
                        "competition_id": key.competition_id,
                        "bucket_start": key.bucket_start,
                        "bucket_end": key.bucket_end,
                        "predicted_probability": observation.predicted_probability,
                        "actual_count": 1 if observation.actual_occurred else 0,
                    },
                )
            )
            buckets.append(_calibration_bucket_from_row(row))
        return buckets

    def save_backtest_run(
        self,
        backtest_run: BacktestRunSchema,
        *,
        metrics_json: Mapping[str, object],
        calibration_json: Mapping[str, object] | None = None,
        report_uri: str | None = None,
    ) -> StoredBacktestRun:
        metrics = dict(metrics_json)
        calibration = dict(calibration_json or {})
        row = _required_row(
            self.database.fetch_one(
                INSERT_BACKTEST_RUN_QUERY,
                {
                    "model_version": backtest_run.model_version,
                    "mode": backtest_run.mode,
                    "as_of_time": backtest_run.as_of_time,
                    "train_window_json": _json_or_null(backtest_run.train_window),
                    "validation_window_json": _json_or_null(backtest_run.validation_window),
                    "test_window_json": _json(backtest_run.test_window.model_dump(mode="json")),
                    "competitions_json": _json(backtest_run.competitions),
                    "metrics_json": _json(metrics),
                    "calibration_json": _json(calibration),
                    "report_uri": report_uri,
                },
            )
        )
        return StoredBacktestRun(
            backtest_run_id=_int(row["backtest_run_id"]),
            backtest_run=backtest_run,
            metrics_json=metrics,
            calibration_json=calibration,
            report_uri=report_uri,
            created_at=_datetime(row["created_at"]),
        )

    def save_model_comparison_report(
        self,
        comparison: ModelComparisonStub,
    ) -> StoredModelComparisonReport:
        row = _required_row(
            self.database.fetch_one(
                INSERT_MODEL_COMPARISON_REPORT_QUERY,
                {
                    "candidate_model_version": comparison.candidate_model_version,
                    "baseline_model_version": comparison.baseline_model_version,
                    "candidate_metrics_json": _json(
                        comparison.candidate_metrics.model_dump(mode="json")
                    ),
                    "baseline_metrics_json": _json(
                        comparison.baseline_metrics.model_dump(mode="json")
                    ),
                    "decision_stub": comparison.decision_stub,
                    "reasons_json": _json(comparison.reasons),
                },
            )
        )
        return StoredModelComparisonReport(
            comparison_report_id=_int(row["comparison_report_id"]),
            comparison=comparison,
            created_at=_datetime(row["created_at"]),
        )


def _prediction_evaluation_params(evaluation: PredictionEvaluation) -> QueryParams:
    return {
        "prediction_snapshot_id": _optional_int_id(evaluation.prediction_snapshot_id),
        "fixture_id": evaluation.fixture_id,
        "actual_home_goals": evaluation.actual_home_goals,
        "actual_away_goals": evaluation.actual_away_goals,
        "actual_result_1x2": evaluation.actual_result_1x2.value,
        "log_loss_1x2": evaluation.log_loss_1x2,
        "brier_score_1x2": evaluation.brier_score_1x2,
        "actual_score_probability": evaluation.actual_score_probability,
        "actual_score_rank": evaluation.actual_score_rank,
        "market_comparison_json": _json(evaluation.market_comparison_json),
        "error_tags_json": _json(evaluation.error_tags),
    }


def _calibration_bucket_from_row(row: DatabaseRow) -> CalibrationBucket:
    return CalibrationBucket(
        key=CalibrationBucketKey(
            model_version=str(row["model_version"]),
            market_type=str(row["market_type"]),
            outcome=str(row["outcome"]),
            competition_id=_optional_str(row["competition_id"]),
            bucket_start=_float(row["bucket_start"]),
            bucket_end=_float(row["bucket_end"]),
        ),
        sample_size=_int(row["sample_size"]),
        predicted_probability_sum=_float(row["predicted_probability_sum"]),
        actual_count=_int(row["actual_count"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _optional_int_id(value: str | None) -> int | None:
    if value is None:
        return None
    if value.isdecimal():
        return int(value)
    raise ValueError("prediction_snapshot_id must be a numeric Postgres id")


def _json_or_null(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return _json(value.model_dump(mode="json"))
    return _json(value)


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"))


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    raise ValueError(f"expected numeric value, got {type(value).__name__}")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
