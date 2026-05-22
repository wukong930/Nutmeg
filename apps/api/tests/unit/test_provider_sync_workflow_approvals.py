from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.workflow_approvals import (
    INSERT_PROVIDER_SYNC_WORKFLOW_APPROVAL_QUERY,
    LINK_PROVIDER_SYNC_WORKFLOW_APPROVAL_RUN_QUERY,
    LIST_PROVIDER_SYNC_WORKFLOW_APPROVALS_QUERY,
    PostgresProviderSyncWorkflowApprovalRepository,
)


class FakeProviderSyncWorkflowApprovalDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_PROVIDER_SYNC_WORKFLOW_APPROVAL_QUERY:
            return _approval_row(
                provider_sync_workflow_template_id=params[
                    "provider_sync_workflow_template_id"
                ],
                approved_by=params["approved_by"],
                approval_note=params["approval_note"],
                request_payload_json=params["request_payload_json"],
                metadata_json=params["metadata_json"],
            )
        if query == LINK_PROVIDER_SYNC_WORKFLOW_APPROVAL_RUN_QUERY:
            return _approval_row(
                provider_sync_workflow_run_id=params[
                    "provider_sync_workflow_run_id"
                ],
                metadata_json=params["metadata_json"],
            )
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_SYNC_WORKFLOW_APPROVALS_QUERY:
            return [_approval_row()]
        raise AssertionError(f"unexpected query: {query}")


def test_provider_sync_workflow_approval_repository_records_links_and_lists() -> None:
    database = FakeProviderSyncWorkflowApprovalDatabase()
    repository = PostgresProviderSyncWorkflowApprovalRepository(database)

    approval = repository.record_approval(
        approval_type="provider_sync_workflow_dry_run",
        provider_sync_workflow_template_id=701,
        approved_by="admin_api",
        approval_note="reviewed IDs",
        request_payload_json={"dry_run": True, "operator_approved": True},
        metadata_json={"source": "unit_test"},
    )
    linked = repository.link_workflow_run(
        provider_sync_workflow_approval_id=approval.provider_sync_workflow_approval_id,
        provider_sync_workflow_run_id=501,
        metadata_json={"linked_by": "unit_test"},
    )
    records = repository.list_latest(limit=5)

    assert approval.provider_sync_workflow_approval_id == 801
    assert approval.provider_sync_workflow_template_id == 701
    assert approval.approved_by == "admin_api"
    assert approval.request_payload_json["operator_approved"] is True
    assert linked is not None
    assert linked.provider_sync_workflow_run_id == 501
    assert records[0].provider_sync_workflow_approval_id == 801
    assert database.fetch_all_calls == [
        (LIST_PROVIDER_SYNC_WORKFLOW_APPROVALS_QUERY, {"limit": 5})
    ]


def _approval_row(
    *,
    provider_sync_workflow_template_id: object = 701,
    provider_sync_workflow_run_id: object = None,
    approved_by: object = "admin_api",
    approval_note: object = "reviewed IDs",
    request_payload_json: object = '{"dry_run":true,"operator_approved":true}',
    metadata_json: object = '{"source":"unit_test"}',
) -> DatabaseRow:
    return {
        "provider_sync_workflow_approval_id": 801,
        "approval_type": "provider_sync_workflow_dry_run",
        "approval_status": "approved",
        "provider_sync_workflow_template_id": provider_sync_workflow_template_id,
        "provider_sync_workflow_run_id": provider_sync_workflow_run_id,
        "approved_by": approved_by,
        "approved_at": datetime(2026, 5, 8, 5, 1, tzinfo=UTC),
        "approval_note": approval_note,
        "request_payload_json": request_payload_json,
        "metadata_json": metadata_json,
    }
