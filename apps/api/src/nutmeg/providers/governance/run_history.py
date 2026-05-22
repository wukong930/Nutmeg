from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

type ProviderOpsRunStatus = Literal["success", "failure", "skipped"]

INSERT_PROVIDER_OPS_RUN_HISTORY_QUERY = """
INSERT INTO provider_ops_run_history (
  run_name,
  run_type,
  source,
  status,
  operator_name,
  started_at,
  completed_at,
  duration_ms,
  exit_code,
  summary_json,
  output_excerpt,
  metadata_json
) VALUES (
  %(run_name)s,
  %(run_type)s,
  %(source)s,
  %(status)s,
  %(operator_name)s,
  %(started_at)s,
  %(completed_at)s,
  %(duration_ms)s,
  %(exit_code)s,
  %(summary_json)s::jsonb,
  %(output_excerpt)s,
  %(metadata_json)s::jsonb
)
RETURNING
  provider_ops_run_id,
  run_name,
  run_type,
  source,
  status,
  operator_name,
  started_at,
  completed_at,
  duration_ms,
  exit_code,
  summary_json,
  output_excerpt,
  metadata_json,
  created_at
"""

LIST_PROVIDER_OPS_RUN_HISTORY_QUERY = """
SELECT
  provider_ops_run_id,
  run_name,
  run_type,
  source,
  status,
  operator_name,
  started_at,
  completed_at,
  duration_ms,
  exit_code,
  summary_json,
  output_excerpt,
  metadata_json,
  created_at
FROM provider_ops_run_history
ORDER BY created_at DESC, provider_ops_run_id DESC
LIMIT %(limit)s
"""


class ProviderOpsRunHistoryDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class ProviderOpsRunHistoryInput(BaseModel):
    run_name: str = Field(min_length=1, max_length=120)
    run_type: str = Field(default="vps_helper", min_length=1, max_length=80)
    source: str = Field(default="vps", min_length=1, max_length=120)
    status: ProviderOpsRunStatus = "success"
    operator_name: str | None = Field(default=None, max_length=120)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    exit_code: int | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)
    output_excerpt: str | None = Field(default=None, max_length=2000)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderOpsRunHistoryRecord(BaseModel):
    provider_ops_run_id: int = Field(gt=0)
    run_name: str
    run_type: str
    source: str
    status: ProviderOpsRunStatus
    operator_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    exit_code: int | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)
    output_excerpt: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class PostgresProviderOpsRunHistoryRepository:
    def __init__(self, database: ProviderOpsRunHistoryDatabase) -> None:
        self.database = database

    def record_run(
        self,
        run: ProviderOpsRunHistoryInput,
    ) -> ProviderOpsRunHistoryRecord:
        row = self.database.fetch_one(
            INSERT_PROVIDER_OPS_RUN_HISTORY_QUERY,
            {
                "run_name": run.run_name[:120],
                "run_type": run.run_type[:80],
                "source": run.source[:120],
                "status": run.status,
                "operator_name": _optional_text(run.operator_name),
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "duration_ms": run.duration_ms,
                "exit_code": run.exit_code,
                "summary_json": _json(run.summary_json),
                "output_excerpt": _optional_text(run.output_excerpt, max_length=2000),
                "metadata_json": _json(run.metadata_json),
            },
        )
        if row is None:
            raise ValueError("expected provider ops run history RETURNING row")
        return _run_history_record_from_row(row)

    def list_latest(
        self,
        *,
        limit: int = 20,
    ) -> list[ProviderOpsRunHistoryRecord]:
        rows = self.database.fetch_all(
            LIST_PROVIDER_OPS_RUN_HISTORY_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_run_history_record_from_row(row) for row in rows]


def _run_history_record_from_row(row: DatabaseRow) -> ProviderOpsRunHistoryRecord:
    return ProviderOpsRunHistoryRecord(
        provider_ops_run_id=_int(row["provider_ops_run_id"]),
        run_name=str(row["run_name"]),
        run_type=str(row["run_type"]),
        source=str(row["source"]),
        status=_run_status(row["status"]),
        operator_name=_optional_text(row["operator_name"]),
        started_at=_optional_datetime(row["started_at"]),
        completed_at=_optional_datetime(row["completed_at"]),
        duration_ms=_optional_int(row["duration_ms"]),
        exit_code=_optional_int(row["exit_code"]),
        summary_json=_object_mapping(row["summary_json"]),
        output_excerpt=_optional_text(row["output_excerpt"], max_length=2000),
        metadata_json=_object_mapping(row["metadata_json"]),
        created_at=_datetime(row["created_at"]),
    )


def _run_status(value: object) -> ProviderOpsRunStatus:
    status = str(value)
    if status not in {"success", "failure", "skipped"}:
        raise ValueError(f"unsupported provider ops run status: {status}")
    return cast(ProviderOpsRunStatus, status)


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _parse_json(value: object) -> object:
    if isinstance(value, str):
        return loads(value)
    return value


def _object_mapping(value: object) -> dict[str, object]:
    parsed = _parse_json(value)
    if not isinstance(parsed, dict):
        return {}
    return {str(key): item for key, item in parsed.items()}


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_text(value: object, *, max_length: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_length] or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    return int(str(value))
