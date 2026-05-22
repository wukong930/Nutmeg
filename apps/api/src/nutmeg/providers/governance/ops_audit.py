from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

type ProviderOpsAuditOutcome = Literal["success", "failure", "blocked"]

INSERT_PROVIDER_OPS_AUDIT_EVENT_QUERY = """
INSERT INTO provider_ops_audit_events (
  event_type,
  operator_name,
  action_surface,
  target_type,
  target_id,
  outcome,
  request_path,
  request_method,
  metadata_json
) VALUES (
  %(event_type)s,
  %(operator_name)s,
  %(action_surface)s,
  %(target_type)s,
  %(target_id)s,
  %(outcome)s,
  %(request_path)s,
  %(request_method)s,
  %(metadata_json)s::jsonb
)
RETURNING
  provider_ops_audit_event_id,
  event_type,
  operator_name,
  action_surface,
  target_type,
  target_id,
  outcome,
  request_path,
  request_method,
  metadata_json,
  created_at
"""

LIST_PROVIDER_OPS_AUDIT_EVENTS_QUERY = """
SELECT
  provider_ops_audit_event_id,
  event_type,
  operator_name,
  action_surface,
  target_type,
  target_id,
  outcome,
  request_path,
  request_method,
  metadata_json,
  created_at
FROM provider_ops_audit_events
ORDER BY created_at DESC, provider_ops_audit_event_id DESC
LIMIT %(limit)s
"""


class ProviderOpsAuditDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class ProviderOpsAuditEventInput(BaseModel):
    event_type: str = Field(min_length=1, max_length=120)
    operator_name: str | None = Field(default=None, max_length=120)
    action_surface: str = Field(default="provider_ops", min_length=1, max_length=120)
    target_type: str | None = Field(default=None, max_length=120)
    target_id: str | None = Field(default=None, max_length=240)
    outcome: ProviderOpsAuditOutcome = "success"
    request_path: str | None = Field(default=None, max_length=500)
    request_method: str | None = Field(default=None, max_length=16)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderOpsAuditEventRecord(BaseModel):
    provider_ops_audit_event_id: int = Field(gt=0)
    event_type: str
    operator_name: str | None = None
    action_surface: str
    target_type: str | None = None
    target_id: str | None = None
    outcome: ProviderOpsAuditOutcome
    request_path: str | None = None
    request_method: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class PostgresProviderOpsAuditEventRepository:
    def __init__(self, database: ProviderOpsAuditDatabase) -> None:
        self.database = database

    def record_event(
        self,
        event: ProviderOpsAuditEventInput,
    ) -> ProviderOpsAuditEventRecord:
        row = self.database.fetch_one(
            INSERT_PROVIDER_OPS_AUDIT_EVENT_QUERY,
            {
                "event_type": event.event_type,
                "operator_name": _optional_text(event.operator_name),
                "action_surface": event.action_surface,
                "target_type": _optional_text(event.target_type),
                "target_id": _optional_text(event.target_id),
                "outcome": event.outcome,
                "request_path": _optional_text(event.request_path),
                "request_method": _optional_text(event.request_method),
                "metadata_json": _json(event.metadata_json),
            },
        )
        if row is None:
            raise ValueError("expected provider ops audit event RETURNING row")
        return _audit_event_record_from_row(row)

    def list_latest(
        self,
        *,
        limit: int = 20,
    ) -> list[ProviderOpsAuditEventRecord]:
        rows = self.database.fetch_all(
            LIST_PROVIDER_OPS_AUDIT_EVENTS_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_audit_event_record_from_row(row) for row in rows]


def _audit_event_record_from_row(row: DatabaseRow) -> ProviderOpsAuditEventRecord:
    return ProviderOpsAuditEventRecord(
        provider_ops_audit_event_id=_int(row["provider_ops_audit_event_id"]),
        event_type=str(row["event_type"]),
        operator_name=_optional_text(row["operator_name"]),
        action_surface=str(row["action_surface"]),
        target_type=_optional_text(row["target_type"]),
        target_id=_optional_text(row["target_id"]),
        outcome=_audit_outcome(row["outcome"]),
        request_path=_optional_text(row["request_path"]),
        request_method=_optional_text(row["request_method"]),
        metadata_json=_object_mapping(row["metadata_json"]),
        created_at=_datetime(row["created_at"]),
    )


def _audit_outcome(value: object) -> ProviderOpsAuditOutcome:
    outcome = str(value)
    if outcome not in {"success", "failure", "blocked"}:
        raise ValueError(f"unsupported provider ops audit outcome: {outcome}")
    return cast(ProviderOpsAuditOutcome, outcome)


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


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    return int(str(value))
