from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from json import loads
from typing import Literal, Protocol, cast

from nutmeg.accuracy.summary import AccuracyEvaluationEvent, CalibrationObservation
from nutmeg.domain.accuracy import (
    CalibrationBucket,
    CalibrationBucketKey,
    ModelComparisonStub,
    ModelVersionMetrics,
)

type QueryParams = Mapping[str, object]
type DatabaseRow = Mapping[str, object]

EVALUATION_EVENTS_QUERY = """
SELECT
  pe.fixture_id,
  f.competition_id,
  c.name AS competition_name,
  ps.model_version,
  ps.prediction_time_utc,
  pe.log_loss_1x2,
  pe.brier_score_1x2,
  pe.actual_result_1x2,
  ps.p_home,
  ps.p_draw,
  ps.p_away,
  pe.error_tags_json
FROM prediction_evaluations pe
JOIN prediction_snapshots ps
  ON ps.prediction_snapshot_id = pe.prediction_snapshot_id
JOIN fixtures f
  ON f.fixture_id = pe.fixture_id
JOIN competitions c
  ON c.competition_id = f.competition_id
WHERE pe.log_loss_1x2 IS NOT NULL
  AND pe.brier_score_1x2 IS NOT NULL
ORDER BY ps.prediction_time_utc DESC, pe.fixture_id ASC
"""

CALIBRATION_BUCKETS_QUERY = """
SELECT
  model_version,
  market_type,
  outcome,
  competition_id,
  bucket_start,
  bucket_end,
  sample_size,
  predicted_probability_sum,
  actual_count
FROM calibration_buckets
ORDER BY model_version, market_type, outcome, competition_id, bucket_start
"""

MODEL_COMPARISONS_QUERY = """
SELECT
  candidate_model_version,
  baseline_model_version,
  candidate_metrics_json,
  baseline_metrics_json,
  decision_stub,
  reasons_json
FROM model_comparison_reports
ORDER BY created_at DESC, comparison_report_id DESC
"""


class SyncDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read-only SQL query and return mapping rows."""


class PostgresAccuracyRepository:
    def __init__(self, database: SyncDatabaseExecutor) -> None:
        self.database = database

    def list_evaluation_events(self) -> list[AccuracyEvaluationEvent]:
        rows = self.database.fetch_all(EVALUATION_EVENTS_QUERY, {})
        return [_evaluation_event_from_row(row) for row in rows]

    def list_calibration_buckets(self) -> list[CalibrationBucket]:
        rows = self.database.fetch_all(CALIBRATION_BUCKETS_QUERY, {})
        return [_calibration_bucket_from_row(row) for row in rows]

    def list_model_comparisons(
        self,
        events: list[AccuracyEvaluationEvent] | None = None,
    ) -> list[ModelComparisonStub]:
        rows = self.database.fetch_all(MODEL_COMPARISONS_QUERY, {})
        return [_model_comparison_from_row(row) for row in rows]


def _evaluation_event_from_row(row: DatabaseRow) -> AccuracyEvaluationEvent:
    actual_result = _str(row["actual_result_1x2"])
    competition_id = _str(row["competition_id"])
    return AccuracyEvaluationEvent(
        fixture_id=_str(row["fixture_id"]),
        competition_id=competition_id,
        competition_name=_str(row["competition_name"]),
        market_type="1x2",
        model_version=_str(row["model_version"]),
        prediction_time_utc=_datetime(row["prediction_time_utc"]),
        log_loss=_float(row["log_loss_1x2"]),
        brier_score=_float(row["brier_score_1x2"]),
        calibration_observations=(
            CalibrationObservation(
                market_type="1x2",
                outcome="home_win",
                predicted_probability=_float(row["p_home"]),
                actual_occurred=actual_result == "home_win",
                competition_id=competition_id,
            ),
            CalibrationObservation(
                market_type="1x2",
                outcome="draw",
                predicted_probability=_float(row["p_draw"]),
                actual_occurred=actual_result == "draw",
                competition_id=competition_id,
            ),
            CalibrationObservation(
                market_type="1x2",
                outcome="away_win",
                predicted_probability=_float(row["p_away"]),
                actual_occurred=actual_result == "away_win",
                competition_id=competition_id,
            ),
        ),
        error_tags=tuple(_json_string_list(row["error_tags_json"])),
    )


def _calibration_bucket_from_row(row: DatabaseRow) -> CalibrationBucket:
    return CalibrationBucket(
        key=CalibrationBucketKey(
            model_version=_str(row["model_version"]),
            market_type=_str(row["market_type"]),
            outcome=_str(row["outcome"]),
            competition_id=_optional_str(row["competition_id"]),
            bucket_start=_float(row["bucket_start"]),
            bucket_end=_float(row["bucket_end"]),
        ),
        sample_size=_int(row["sample_size"]),
        predicted_probability_sum=_float(row["predicted_probability_sum"]),
        actual_count=_int(row["actual_count"]),
    )


def _model_comparison_from_row(row: DatabaseRow) -> ModelComparisonStub:
    candidate_model_version = _str(row["candidate_model_version"])
    baseline_model_version = _str(row["baseline_model_version"])
    return ModelComparisonStub(
        candidate_model_version=candidate_model_version,
        baseline_model_version=baseline_model_version,
        candidate_metrics=_model_metrics_from_json(
            row["candidate_metrics_json"],
            default_model_version=candidate_model_version,
        ),
        baseline_metrics=_model_metrics_from_json(
            row["baseline_metrics_json"],
            default_model_version=baseline_model_version,
        ),
        decision_stub=_decision(row["decision_stub"]),
        reasons=_json_string_list(row["reasons_json"]),
    )


def _model_metrics_from_json(
    value: object,
    *,
    default_model_version: str,
) -> ModelVersionMetrics:
    metrics = _json_object(value)
    return ModelVersionMetrics(
        model_version=str(metrics.get("model_version") or default_model_version),
        sample_size=_int(metrics.get("sample_size", 0)),
        log_loss=_float(metrics.get("log_loss", 0.0)),
        brier_score=_float(metrics.get("brier_score", 0.0)),
        ece=_optional_float(metrics.get("ece")),
        metrics_json=metrics,
    )


def _json_object(value: object) -> dict[str, object]:
    raw = loads(value) if isinstance(value, str) else value
    if not isinstance(raw, Mapping):
        raise ValueError("expected JSON object")
    return {str(key): item for key, item in raw.items()}


def _json_string_list(value: object) -> list[str]:
    raw = loads(value) if isinstance(value, str) else value
    if not isinstance(raw, list):
        raise ValueError("expected JSON array")
    return [str(item) for item in raw]


def _decision(value: object) -> Literal["promote_candidate", "keep_baseline", "needs_review"]:
    decision = _str(value)
    if decision not in {"promote_candidate", "keep_baseline", "needs_review"}:
        raise ValueError(f"unsupported model comparison decision: {decision}")
    return cast(Literal["promote_candidate", "keep_baseline", "needs_review"], decision)


def _str(value: object) -> str:
    if value is None:
        raise ValueError("expected non-null string value")
    return str(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


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


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _float(value)
