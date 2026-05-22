from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

ProviderSyncStatus = Literal["running", "completed", "failed"]

INSERT_RAW_PROVIDER_PAYLOAD_QUERY = """
INSERT INTO raw_provider_payloads (
  provider,
  endpoint,
  request_hash,
  entity_type,
  entity_id_hint,
  response_json
) VALUES (
  %(provider)s,
  %(endpoint)s,
  %(request_hash)s,
  %(entity_type)s,
  %(entity_id_hint)s,
  %(response_json)s::jsonb
)
RETURNING payload_id, fetched_at
"""

START_PROVIDER_SYNC_RUN_QUERY = """
INSERT INTO provider_sync_runs (
  provider_name,
  capability,
  status,
  metadata_json
) VALUES (
  %(provider_name)s,
  %(capability)s,
  'running',
  %(metadata_json)s::jsonb
)
RETURNING
  provider_sync_run_id,
  provider_name,
  capability,
  status,
  started_at,
  completed_at,
  duration_ms,
  entity_count,
  error_message,
  metadata_json
"""

COMPLETE_PROVIDER_SYNC_RUN_QUERY = """
UPDATE provider_sync_runs
SET
  status = 'completed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  entity_count = %(entity_count)s,
  error_message = NULL,
  metadata_json = %(metadata_json)s::jsonb
WHERE provider_sync_run_id = %(provider_sync_run_id)s
RETURNING
  provider_sync_run_id,
  provider_name,
  capability,
  status,
  started_at,
  completed_at,
  duration_ms,
  entity_count,
  error_message,
  metadata_json
"""

FAIL_PROVIDER_SYNC_RUN_QUERY = """
UPDATE provider_sync_runs
SET
  status = 'failed',
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  error_message = %(error_message)s,
  metadata_json = %(metadata_json)s::jsonb
WHERE provider_sync_run_id = %(provider_sync_run_id)s
RETURNING
  provider_sync_run_id,
  provider_name,
  capability,
  status,
  started_at,
  completed_at,
  duration_ms,
  entity_count,
  error_message,
  metadata_json
"""


class ProviderWriteDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one mapping row."""


class StoredRawProviderPayload(BaseModel):
    payload_id: int = Field(gt=0)
    provider: str
    endpoint: str
    request_hash: str
    entity_type: str | None = None
    entity_id_hint: str | None = None
    fetched_at: datetime


class ProviderSyncRunRecord(BaseModel):
    provider_sync_run_id: int = Field(gt=0)
    provider_name: str
    capability: str
    status: ProviderSyncStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    entity_count: int = Field(ge=0)
    error_message: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PostgresProviderRawPayloadRepository:
    def __init__(self, database: ProviderWriteDatabaseExecutor) -> None:
        self.database = database

    def save_raw_payload(
        self,
        *,
        provider: str,
        endpoint: str,
        request_params: Mapping[str, object],
        response_json: Mapping[str, object],
        entity_type: str | None = None,
        entity_id_hint: str | None = None,
    ) -> StoredRawProviderPayload:
        request_hash = stable_request_hash(endpoint=endpoint, request_params=request_params)
        row = _required_row(
            self.database.fetch_one(
                INSERT_RAW_PROVIDER_PAYLOAD_QUERY,
                {
                    "provider": provider,
                    "endpoint": endpoint,
                    "request_hash": request_hash,
                    "entity_type": entity_type,
                    "entity_id_hint": entity_id_hint,
                    "response_json": _json(dict(response_json)),
                },
            )
        )
        return StoredRawProviderPayload(
            payload_id=_int(row["payload_id"]),
            provider=provider,
            endpoint=endpoint,
            request_hash=request_hash,
            entity_type=entity_type,
            entity_id_hint=entity_id_hint,
            fetched_at=_datetime(row["fetched_at"]),
        )


class PostgresProviderSyncRunRepository:
    def __init__(self, database: ProviderWriteDatabaseExecutor) -> None:
        self.database = database

    def start_sync_run(
        self,
        *,
        provider_name: str,
        capability: str,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord:
        row = _required_row(
            self.database.fetch_one(
                START_PROVIDER_SYNC_RUN_QUERY,
                {
                    "provider_name": provider_name,
                    "capability": capability,
                    "metadata_json": _json(dict(metadata_json or {})),
                },
            )
        )
        return _sync_run_record_from_row(row)

    def complete_sync_run(
        self,
        *,
        provider_sync_run_id: int,
        entity_count: int,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord:
        row = _required_row(
            self.database.fetch_one(
                COMPLETE_PROVIDER_SYNC_RUN_QUERY,
                {
                    "provider_sync_run_id": provider_sync_run_id,
                    "entity_count": entity_count,
                    "metadata_json": _json(dict(metadata_json or {})),
                },
            )
        )
        return _sync_run_record_from_row(row)

    def fail_sync_run(
        self,
        *,
        provider_sync_run_id: int,
        error_message: str,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncRunRecord:
        row = _required_row(
            self.database.fetch_one(
                FAIL_PROVIDER_SYNC_RUN_QUERY,
                {
                    "provider_sync_run_id": provider_sync_run_id,
                    "error_message": error_message[:500],
                    "metadata_json": _json(dict(metadata_json or {})),
                },
            )
        )
        return _sync_run_record_from_row(row)


def stable_request_hash(*, endpoint: str, request_params: Mapping[str, object]) -> str:
    payload = _json({"endpoint": endpoint, "params": dict(sorted(request_params.items()))})
    return sha256(payload.encode("utf-8")).hexdigest()


def _sync_run_record_from_row(row: DatabaseRow) -> ProviderSyncRunRecord:
    return ProviderSyncRunRecord(
        provider_sync_run_id=_int(row["provider_sync_run_id"]),
        provider_name=str(row["provider_name"]),
        capability=str(row["capability"]),
        status=_status(row["status"]),
        started_at=_datetime(row["started_at"]),
        completed_at=_optional_datetime(row["completed_at"]),
        duration_ms=_optional_int(row["duration_ms"]),
        entity_count=_int(row["entity_count"]),
        error_message=_optional_str(row["error_message"]),
        metadata_json=_object_mapping(row["metadata_json"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_value(value: object) -> object:
    if isinstance(value, str):
        return loads(value)
    return value


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    return int(str(value))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _status(value: object) -> ProviderSyncStatus:
    text = str(value)
    if text not in {"running", "completed", "failed"}:
        raise ValueError(f"unsupported provider sync status: {text}")
    return cast(ProviderSyncStatus, text)


def _object_mapping(value: object) -> dict[str, object]:
    parsed = _json_value(value)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object")
    return {str(key): item for key, item in parsed.items()}
