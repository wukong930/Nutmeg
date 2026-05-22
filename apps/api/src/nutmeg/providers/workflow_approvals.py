from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

type ProviderSyncWorkflowApprovalStatus = Literal["approved", "superseded", "revoked"]

INSERT_PROVIDER_SYNC_WORKFLOW_APPROVAL_QUERY = """
INSERT INTO provider_sync_workflow_operator_approvals (
  approval_type,
  approval_status,
  provider_sync_workflow_template_id,
  approved_by,
  approval_note,
  request_payload_json,
  metadata_json
) VALUES (
  %(approval_type)s,
  %(approval_status)s,
  %(provider_sync_workflow_template_id)s,
  %(approved_by)s,
  %(approval_note)s,
  %(request_payload_json)s::jsonb,
  %(metadata_json)s::jsonb
)
RETURNING
  provider_sync_workflow_approval_id,
  approval_type,
  approval_status,
  provider_sync_workflow_template_id,
  provider_sync_workflow_run_id,
  approved_by,
  approved_at,
  approval_note,
  request_payload_json,
  metadata_json
"""

LINK_PROVIDER_SYNC_WORKFLOW_APPROVAL_RUN_QUERY = """
UPDATE provider_sync_workflow_operator_approvals
SET
  provider_sync_workflow_run_id = %(provider_sync_workflow_run_id)s,
  metadata_json = metadata_json || %(metadata_json)s::jsonb
WHERE provider_sync_workflow_approval_id = %(provider_sync_workflow_approval_id)s
RETURNING
  provider_sync_workflow_approval_id,
  approval_type,
  approval_status,
  provider_sync_workflow_template_id,
  provider_sync_workflow_run_id,
  approved_by,
  approved_at,
  approval_note,
  request_payload_json,
  metadata_json
"""

LIST_PROVIDER_SYNC_WORKFLOW_APPROVALS_QUERY = """
SELECT
  provider_sync_workflow_approval_id,
  approval_type,
  approval_status,
  provider_sync_workflow_template_id,
  provider_sync_workflow_run_id,
  approved_by,
  approved_at,
  approval_note,
  request_payload_json,
  metadata_json
FROM provider_sync_workflow_operator_approvals
ORDER BY approved_at DESC, provider_sync_workflow_approval_id DESC
LIMIT %(limit)s
"""


class ProviderSyncWorkflowApprovalDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class ProviderSyncWorkflowApprovalRecord(BaseModel):
    provider_sync_workflow_approval_id: int = Field(gt=0)
    approval_type: str = Field(min_length=1)
    approval_status: ProviderSyncWorkflowApprovalStatus = "approved"
    provider_sync_workflow_template_id: int | None = Field(default=None, gt=0)
    provider_sync_workflow_run_id: int | None = Field(default=None, gt=0)
    approved_by: str | None = None
    approved_at: datetime
    approval_note: str | None = None
    request_payload_json: dict[str, object] = Field(default_factory=dict)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PostgresProviderSyncWorkflowApprovalRepository:
    def __init__(self, database: ProviderSyncWorkflowApprovalDatabase) -> None:
        self.database = database

    def record_approval(
        self,
        *,
        approval_type: str,
        provider_sync_workflow_template_id: int | None,
        approved_by: str | None,
        approval_note: str | None,
        request_payload_json: Mapping[str, object],
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncWorkflowApprovalRecord:
        row = self.database.fetch_one(
            INSERT_PROVIDER_SYNC_WORKFLOW_APPROVAL_QUERY,
            {
                "approval_type": approval_type,
                "approval_status": "approved",
                "provider_sync_workflow_template_id": (
                    provider_sync_workflow_template_id
                ),
                "approved_by": approved_by,
                "approval_note": approval_note,
                "request_payload_json": _json(dict(request_payload_json)),
                "metadata_json": _json(dict(metadata_json or {})),
            },
        )
        if row is None:
            raise ValueError("expected provider sync workflow approval RETURNING row")
        return _approval_record_from_row(row)

    def link_workflow_run(
        self,
        *,
        provider_sync_workflow_approval_id: int,
        provider_sync_workflow_run_id: int,
        metadata_json: Mapping[str, object] | None = None,
    ) -> ProviderSyncWorkflowApprovalRecord | None:
        row = self.database.fetch_one(
            LINK_PROVIDER_SYNC_WORKFLOW_APPROVAL_RUN_QUERY,
            {
                "provider_sync_workflow_approval_id": (
                    provider_sync_workflow_approval_id
                ),
                "provider_sync_workflow_run_id": provider_sync_workflow_run_id,
                "metadata_json": _json(dict(metadata_json or {})),
            },
        )
        if row is None:
            return None
        return _approval_record_from_row(row)

    def list_latest(
        self,
        *,
        limit: int = 10,
    ) -> list[ProviderSyncWorkflowApprovalRecord]:
        rows = self.database.fetch_all(
            LIST_PROVIDER_SYNC_WORKFLOW_APPROVALS_QUERY,
            {"limit": max(1, min(limit, 100))},
        )
        return [_approval_record_from_row(row) for row in rows]


def _approval_record_from_row(row: DatabaseRow) -> ProviderSyncWorkflowApprovalRecord:
    return ProviderSyncWorkflowApprovalRecord(
        provider_sync_workflow_approval_id=_int(
            row["provider_sync_workflow_approval_id"]
        ),
        approval_type=str(row["approval_type"]),
        approval_status=_approval_status(row["approval_status"]),
        provider_sync_workflow_template_id=_optional_int(
            row["provider_sync_workflow_template_id"]
        ),
        provider_sync_workflow_run_id=_optional_int(
            row["provider_sync_workflow_run_id"]
        ),
        approved_by=_optional_str(row["approved_by"]),
        approved_at=_datetime(row["approved_at"]),
        approval_note=_optional_str(row["approval_note"]),
        request_payload_json=_object_mapping(row["request_payload_json"]),
        metadata_json=_object_mapping(row["metadata_json"]),
    )


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


def _approval_status(value: object) -> ProviderSyncWorkflowApprovalStatus:
    status = str(value)
    if status not in {"approved", "superseded", "revoked"}:
        return "approved"
    return cast(ProviderSyncWorkflowApprovalStatus, status)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    return int(str(value))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
