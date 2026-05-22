from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.governance.ops_audit import (
    INSERT_PROVIDER_OPS_AUDIT_EVENT_QUERY,
    LIST_PROVIDER_OPS_AUDIT_EVENTS_QUERY,
    PostgresProviderOpsAuditEventRepository,
    ProviderOpsAuditEventInput,
)


class FakeProviderOpsAuditDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_PROVIDER_OPS_AUDIT_EVENT_QUERY:
            return _audit_event_row(
                event_type=params["event_type"],
                operator_name=params["operator_name"],
                outcome=params["outcome"],
                request_path=params["request_path"],
                metadata_json=params["metadata_json"],
            )
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_OPS_AUDIT_EVENTS_QUERY:
            return [_audit_event_row()]
        raise AssertionError(f"unexpected query: {query}")


def test_provider_ops_audit_repository_records_and_lists_events_without_secret_values() -> None:
    database = FakeProviderOpsAuditDatabase()
    repository = PostgresProviderOpsAuditEventRepository(database)

    record = repository.record_event(
        ProviderOpsAuditEventInput(
            event_type="provider_ops_unlock",
            operator_name="ops-reviewer",
            outcome="success",
            request_path="/providers",
            metadata_json={"reason": "manual unlock", "secret_token": "[redacted]"},
        )
    )
    records = repository.list_latest(limit=5)

    assert database.fetch_one_calls[0][0] == INSERT_PROVIDER_OPS_AUDIT_EVENT_QUERY
    params = database.fetch_one_calls[0][1]
    assert params["event_type"] == "provider_ops_unlock"
    assert params["operator_name"] == "ops-reviewer"
    assert params["metadata_json"] == (
        '{"reason":"manual unlock","secret_token":"[redacted]"}'
    )
    assert record.event_type == "provider_ops_unlock"
    assert record.operator_name == "ops-reviewer"
    assert record.created_at == datetime(2026, 5, 9, 1, 2, tzinfo=UTC)
    assert records[0].request_path == "/ops/provider-sync/run"
    assert database.fetch_all_calls == [
        (LIST_PROVIDER_OPS_AUDIT_EVENTS_QUERY, {"limit": 5})
    ]


def _audit_event_row(
    *,
    event_type: object = "provider_ops_admin_action",
    operator_name: object = "ops-reviewer",
    outcome: object = "success",
    request_path: object = "/ops/provider-sync/run",
    metadata_json: object = '{"http_status":200}',
) -> DatabaseRow:
    return {
        "provider_ops_audit_event_id": 42,
        "event_type": event_type,
        "operator_name": operator_name,
        "action_surface": "provider_ops",
        "target_type": None,
        "target_id": None,
        "outcome": outcome,
        "request_path": request_path,
        "request_method": "POST",
        "metadata_json": metadata_json,
        "created_at": datetime(2026, 5, 9, 1, 2, tzinfo=UTC),
    }
