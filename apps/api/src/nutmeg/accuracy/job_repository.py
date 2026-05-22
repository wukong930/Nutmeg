from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

type AccuracyJobType = Literal[
    "mock_postgres_e2e",
    "dixon_coles_training_backtest",
    "weekly_dixon_coles_training_pipeline",
]
type AccuracyJobRunStatus = Literal["running", "completed", "failed"]

INSERT_ACCURACY_JOB_RUN_QUERY = """
INSERT INTO accuracy_job_runs (
  job_type,
  status,
  reset_requested,
  requested_by,
  metadata_json
) VALUES (
  %(job_type)s,
  'running',
  %(reset_requested)s,
  %(requested_by)s,
  %(metadata_json)s::jsonb
)
RETURNING
  accuracy_job_run_id,
  job_type,
  status,
  reset_requested,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_count,
  evaluation_count,
  calibration_observation_count,
  model_comparison_report_id,
  prediction_snapshot_ids_json,
  evaluation_ids_json,
  error_message,
  metadata_json
"""

COMPLETE_ACCURACY_JOB_RUN_QUERY = """
UPDATE accuracy_job_runs
SET
  status = 'completed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  fixture_count = %(fixture_count)s,
  evaluation_count = %(evaluation_count)s,
  calibration_observation_count = %(calibration_observation_count)s,
  model_comparison_report_id = %(model_comparison_report_id)s,
  prediction_snapshot_ids_json = %(prediction_snapshot_ids_json)s::jsonb,
  evaluation_ids_json = %(evaluation_ids_json)s::jsonb,
  error_message = NULL
WHERE accuracy_job_run_id = %(accuracy_job_run_id)s
RETURNING
  accuracy_job_run_id,
  job_type,
  status,
  reset_requested,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_count,
  evaluation_count,
  calibration_observation_count,
  model_comparison_report_id,
  prediction_snapshot_ids_json,
  evaluation_ids_json,
  error_message,
  metadata_json
"""

FAIL_ACCURACY_JOB_RUN_QUERY = """
UPDATE accuracy_job_runs
SET
  status = 'failed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  error_message = %(error_message)s
WHERE accuracy_job_run_id = %(accuracy_job_run_id)s
RETURNING
  accuracy_job_run_id,
  job_type,
  status,
  reset_requested,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_count,
  evaluation_count,
  calibration_observation_count,
  model_comparison_report_id,
  prediction_snapshot_ids_json,
  evaluation_ids_json,
  error_message,
  metadata_json
"""

LIST_ACCURACY_JOB_RUNS_QUERY = """
SELECT
  accuracy_job_run_id,
  job_type,
  status,
  reset_requested,
  requested_by,
  started_at,
  completed_at,
  duration_ms,
  fixture_count,
  evaluation_count,
  calibration_observation_count,
  model_comparison_report_id,
  prediction_snapshot_ids_json,
  evaluation_ids_json,
  error_message,
  metadata_json
FROM accuracy_job_runs
ORDER BY started_at DESC, accuracy_job_run_id DESC
LIMIT %(limit)s
"""


class AccuracyJobRunRecord(BaseModel):
    accuracy_job_run_id: int = Field(gt=0)
    job_type: AccuracyJobType
    status: AccuracyJobRunStatus
    reset_requested: bool
    requested_by: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_count: int = Field(ge=0)
    evaluation_count: int = Field(ge=0)
    calibration_observation_count: int = Field(ge=0)
    model_comparison_report_id: int | None = None
    prediction_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    evaluation_ids: list[int] = Field(default_factory=list)
    error_message: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class SyncJobRunDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one mapping row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class PostgresAccuracyJobRunRepository:
    def __init__(self, database: SyncJobRunDatabaseExecutor) -> None:
        self.database = database

    def start_job(
        self,
        *,
        job_type: AccuracyJobType,
        reset_requested: bool,
        requested_by: str | None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> AccuracyJobRunRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_ACCURACY_JOB_RUN_QUERY,
                {
                    "job_type": job_type,
                    "reset_requested": reset_requested,
                    "requested_by": requested_by,
                    "metadata_json": _json(dict(metadata_json or {})),
                },
            )
        )
        return _record_from_row(row)

    def complete_job(
        self,
        *,
        accuracy_job_run_id: int,
        fixture_count: int,
        prediction_snapshot_ids: Mapping[str, int],
        evaluation_ids: Sequence[int],
        calibration_observation_count: int,
        model_comparison_report_id: int | None,
    ) -> AccuracyJobRunRecord:
        row = _required_row(
            self.database.fetch_one(
                COMPLETE_ACCURACY_JOB_RUN_QUERY,
                {
                    "accuracy_job_run_id": accuracy_job_run_id,
                    "fixture_count": fixture_count,
                    "evaluation_count": len(evaluation_ids),
                    "calibration_observation_count": calibration_observation_count,
                    "model_comparison_report_id": model_comparison_report_id,
                    "prediction_snapshot_ids_json": _json(dict(prediction_snapshot_ids)),
                    "evaluation_ids_json": _json(list(evaluation_ids)),
                },
            )
        )
        return _record_from_row(row)

    def fail_job(
        self,
        *,
        accuracy_job_run_id: int,
        error_message: str,
    ) -> AccuracyJobRunRecord:
        row = _required_row(
            self.database.fetch_one(
                FAIL_ACCURACY_JOB_RUN_QUERY,
                {
                    "accuracy_job_run_id": accuracy_job_run_id,
                    "error_message": error_message[:500],
                },
            )
        )
        return _record_from_row(row)

    def list_latest(self, *, limit: int = 10) -> list[AccuracyJobRunRecord]:
        rows = self.database.fetch_all(
            LIST_ACCURACY_JOB_RUNS_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_record_from_row(row) for row in rows]


def _record_from_row(row: DatabaseRow) -> AccuracyJobRunRecord:
    return AccuracyJobRunRecord(
        accuracy_job_run_id=_int(row["accuracy_job_run_id"]),
        job_type=_job_type(row["job_type"]),
        status=_status(row["status"]),
        reset_requested=_bool(row["reset_requested"]),
        requested_by=_optional_str(row["requested_by"]),
        started_at=_datetime(row["started_at"]),
        completed_at=_optional_datetime(row["completed_at"]),
        duration_ms=_optional_int(row["duration_ms"]),
        fixture_count=_int(row["fixture_count"]),
        evaluation_count=_int(row["evaluation_count"]),
        calibration_observation_count=_int(row["calibration_observation_count"]),
        model_comparison_report_id=_optional_int(row["model_comparison_report_id"]),
        prediction_snapshot_ids=_int_mapping(row["prediction_snapshot_ids_json"]),
        evaluation_ids=_int_list(row["evaluation_ids_json"]),
        error_message=_optional_str(row["error_message"]),
        metadata_json=_object_mapping(row["metadata_json"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"))


def _job_type(value: object) -> AccuracyJobType:
    text = str(value)
    if text not in {
        "mock_postgres_e2e",
        "dixon_coles_training_backtest",
        "weekly_dixon_coles_training_pipeline",
    }:
        raise ValueError(f"unsupported accuracy job type: {text}")
    return cast(AccuracyJobType, text)


def _status(value: object) -> AccuracyJobRunStatus:
    text = str(value)
    if text not in {"running", "completed", "failed"}:
        raise ValueError(f"unsupported accuracy job status: {text}")
    return cast(AccuracyJobRunStatus, text)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    raise ValueError(f"expected boolean value, got {type(value).__name__}")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _json_value(value: object) -> object:
    if isinstance(value, str):
        return loads(value)
    return value


def _int_mapping(value: object) -> dict[str, int]:
    parsed = _json_value(value)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object")
    return {str(key): _int(item) for key, item in parsed.items()}


def _int_list(value: object) -> list[int]:
    parsed = _json_value(value)
    if not isinstance(parsed, list):
        raise ValueError("expected JSON array")
    return [_int(item) for item in parsed]


def _object_mapping(value: object) -> dict[str, object]:
    parsed = _json_value(value)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object")
    return {str(key): item for key, item in parsed.items()}
