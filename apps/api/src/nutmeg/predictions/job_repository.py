from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

type PredictionJobType = Literal[
    "mock_prematch_predictions",
    "canonical_prematch_predictions",
]
type PredictionJobRunStatus = Literal["running", "completed", "failed"]

INSERT_PREDICTION_JOB_RUN_QUERY = """
INSERT INTO prediction_job_runs (
  job_type,
  status,
  dry_run,
  requested_by,
  metadata_json
) VALUES (
  %(job_type)s,
  'running',
  %(dry_run)s,
  %(requested_by)s,
  %(metadata_json)s::jsonb
)
RETURNING
  prediction_job_run_id,
  job_type,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_count,
  generated_count,
  feature_snapshot_ids_json,
  prediction_snapshot_ids_json,
  score_grid_ids_json,
  data_quality_scores_json,
  skipped_fixture_ids_json,
  warnings_json,
  error_message,
  metadata_json
"""

COMPLETE_PREDICTION_JOB_RUN_QUERY = """
UPDATE prediction_job_runs
SET
  status = 'completed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  fixture_count = %(fixture_count)s,
  generated_count = %(generated_count)s,
  feature_snapshot_ids_json = %(feature_snapshot_ids_json)s::jsonb,
  prediction_snapshot_ids_json = %(prediction_snapshot_ids_json)s::jsonb,
  score_grid_ids_json = %(score_grid_ids_json)s::jsonb,
  data_quality_scores_json = %(data_quality_scores_json)s::jsonb,
  skipped_fixture_ids_json = %(skipped_fixture_ids_json)s::jsonb,
  warnings_json = %(warnings_json)s::jsonb,
  error_message = NULL
WHERE prediction_job_run_id = %(prediction_job_run_id)s
RETURNING
  prediction_job_run_id,
  job_type,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_count,
  generated_count,
  feature_snapshot_ids_json,
  prediction_snapshot_ids_json,
  score_grid_ids_json,
  data_quality_scores_json,
  skipped_fixture_ids_json,
  warnings_json,
  error_message,
  metadata_json
"""

FAIL_PREDICTION_JOB_RUN_QUERY = """
UPDATE prediction_job_runs
SET
  status = 'failed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  error_message = %(error_message)s
WHERE prediction_job_run_id = %(prediction_job_run_id)s
RETURNING
  prediction_job_run_id,
  job_type,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_count,
  generated_count,
  feature_snapshot_ids_json,
  prediction_snapshot_ids_json,
  score_grid_ids_json,
  data_quality_scores_json,
  skipped_fixture_ids_json,
  warnings_json,
  error_message,
  metadata_json
"""

LIST_PREDICTION_JOB_RUNS_QUERY = """
SELECT
  prediction_job_run_id,
  job_type,
  status,
  dry_run,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_count,
  generated_count,
  feature_snapshot_ids_json,
  prediction_snapshot_ids_json,
  score_grid_ids_json,
  data_quality_scores_json,
  skipped_fixture_ids_json,
  warnings_json,
  error_message,
  metadata_json
FROM prediction_job_runs
ORDER BY started_at DESC, prediction_job_run_id DESC
LIMIT %(limit)s
"""


class PredictionJobRunRecord(BaseModel):
    prediction_job_run_id: int = Field(gt=0)
    job_type: PredictionJobType
    status: PredictionJobRunStatus
    dry_run: bool
    requested_by: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    feature_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    prediction_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    score_grid_ids: dict[str, int] = Field(default_factory=dict)
    data_quality_scores: dict[str, float] = Field(default_factory=dict)
    skipped_fixture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PredictionJobRunDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one mapping row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class PostgresPredictionJobRunRepository:
    def __init__(self, database: PredictionJobRunDatabaseExecutor) -> None:
        self.database = database

    def start_job(
        self,
        *,
        job_type: PredictionJobType,
        dry_run: bool,
        requested_by: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> PredictionJobRunRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PREDICTION_JOB_RUN_QUERY,
                {
                    "job_type": job_type,
                    "dry_run": dry_run,
                    "requested_by": requested_by,
                    "metadata_json": _json(dict(metadata_json or {})),
                },
            )
        )
        return _record_from_row(row)

    def complete_job(
        self,
        *,
        prediction_job_run_id: int,
        fixture_count: int,
        generated_count: int,
        feature_snapshot_ids: Mapping[str, int],
        prediction_snapshot_ids: Mapping[str, int],
        score_grid_ids: Mapping[str, int],
        data_quality_scores: Mapping[str, float],
        skipped_fixture_ids: Sequence[str],
        warnings: Sequence[str],
    ) -> PredictionJobRunRecord:
        row = _required_row(
            self.database.fetch_one(
                COMPLETE_PREDICTION_JOB_RUN_QUERY,
                {
                    "prediction_job_run_id": prediction_job_run_id,
                    "fixture_count": fixture_count,
                    "generated_count": generated_count,
                    "feature_snapshot_ids_json": _json(dict(feature_snapshot_ids)),
                    "prediction_snapshot_ids_json": _json(
                        dict(prediction_snapshot_ids)
                    ),
                    "score_grid_ids_json": _json(dict(score_grid_ids)),
                    "data_quality_scores_json": _json(dict(data_quality_scores)),
                    "skipped_fixture_ids_json": _json(list(skipped_fixture_ids)),
                    "warnings_json": _json(list(warnings)),
                },
            )
        )
        return _record_from_row(row)

    def fail_job(
        self,
        *,
        prediction_job_run_id: int,
        error_message: str,
    ) -> PredictionJobRunRecord:
        row = _required_row(
            self.database.fetch_one(
                FAIL_PREDICTION_JOB_RUN_QUERY,
                {
                    "prediction_job_run_id": prediction_job_run_id,
                    "error_message": error_message[:500],
                },
            )
        )
        return _record_from_row(row)

    def list_latest(self, *, limit: int = 10) -> list[PredictionJobRunRecord]:
        rows = self.database.fetch_all(
            LIST_PREDICTION_JOB_RUNS_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_record_from_row(row) for row in rows]


def _record_from_row(row: DatabaseRow) -> PredictionJobRunRecord:
    return PredictionJobRunRecord(
        prediction_job_run_id=_int(row["prediction_job_run_id"]),
        job_type=_job_type(row["job_type"]),
        status=_status(row["status"]),
        dry_run=_bool(row["dry_run"]),
        requested_by=_optional_str(row["requested_by"]),
        started_at=_datetime(row["started_at"]),
        completed_at=_optional_datetime(row["completed_at"]),
        duration_ms=_optional_int(row["duration_ms"]),
        fixture_count=_int(row["fixture_count"]),
        generated_count=_int(row["generated_count"]),
        feature_snapshot_ids=_int_mapping(row["feature_snapshot_ids_json"]),
        prediction_snapshot_ids=_int_mapping(row["prediction_snapshot_ids_json"]),
        score_grid_ids=_int_mapping(row["score_grid_ids_json"]),
        data_quality_scores=_float_mapping(row["data_quality_scores_json"]),
        skipped_fixture_ids=_string_list(row["skipped_fixture_ids_json"]),
        warnings=_string_list(row["warnings_json"]),
        error_message=_optional_str(row["error_message"]),
        metadata_json=_object_mapping(row["metadata_json"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _job_type(value: object) -> PredictionJobType:
    text = str(value)
    if text not in {"mock_prematch_predictions", "canonical_prematch_predictions"}:
        raise ValueError(f"unsupported prediction job type: {text}")
    return cast(PredictionJobType, text)


def _status(value: object) -> PredictionJobRunStatus:
    text = str(value)
    if text not in {"running", "completed", "failed"}:
        raise ValueError(f"unsupported prediction job status: {text}")
    return cast(PredictionJobRunStatus, text)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    return int(str(value))


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    return float(str(value))


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "t", "1", "yes"}


def _int_mapping(value: object) -> dict[str, int]:
    raw = _loads(value)
    if not isinstance(raw, dict):
        return {}
    return {str(key): _int(item) for key, item in raw.items()}


def _float_mapping(value: object) -> dict[str, float]:
    raw = _loads(value)
    if not isinstance(raw, dict):
        return {}
    return {str(key): _float(item) for key, item in raw.items()}


def _object_mapping(value: object) -> dict[str, object]:
    raw = _loads(value)
    if not isinstance(raw, dict):
        return {}
    return {str(key): item for key, item in raw.items()}


def _string_list(value: object) -> list[str]:
    raw = _loads(value)
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def _loads(value: object) -> object:
    if isinstance(value, str):
        return loads(value)
    return value
