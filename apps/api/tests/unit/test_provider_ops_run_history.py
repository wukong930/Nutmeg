from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.governance.run_history import (
    INSERT_PROVIDER_OPS_RUN_HISTORY_QUERY,
    LIST_PROVIDER_OPS_RUN_HISTORY_QUERY,
    PostgresProviderOpsRunHistoryRepository,
    ProviderOpsRunHistoryInput,
)


class FakeProviderOpsRunHistoryDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_PROVIDER_OPS_RUN_HISTORY_QUERY:
            return _run_history_row(
                run_name=params["run_name"],
                status=params["status"],
                duration_ms=params["duration_ms"],
                summary_json=params["summary_json"],
                output_excerpt=params["output_excerpt"],
            )
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PROVIDER_OPS_RUN_HISTORY_QUERY:
            return [_run_history_row()]
        raise AssertionError(f"unexpected query: {query}")


def test_provider_ops_run_history_repository_records_and_lists_runs() -> None:
    database = FakeProviderOpsRunHistoryDatabase()
    repository = PostgresProviderOpsRunHistoryRepository(database)

    record = repository.record_run(
        ProviderOpsRunHistoryInput(
            run_name="provider-runtime-monitoring",
            run_type="cron",
            source="vps",
            status="success",
            operator_name="provider-runtime-monitor",
            started_at=datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
            completed_at=datetime(2026, 5, 9, 1, 1, tzinfo=UTC),
            duration_ms=60000,
            exit_code=0,
            summary_json={"alert_level": "ok", "secret_value_not_exposed": True},
            output_excerpt="provider_runtime_monitoring_alert_level ok",
            metadata_json={"cron": True},
        )
    )
    records = repository.list_latest(limit=5)

    assert database.fetch_one_calls[0][0] == INSERT_PROVIDER_OPS_RUN_HISTORY_QUERY
    params = database.fetch_one_calls[0][1]
    assert params["run_name"] == "provider-runtime-monitoring"
    assert params["status"] == "success"
    assert params["duration_ms"] == 60000
    assert params["summary_json"] == (
        '{"alert_level":"ok","secret_value_not_exposed":true}'
    )
    assert record.run_name == "provider-runtime-monitoring"
    assert record.status == "success"
    assert record.duration_ms == 60000
    assert records[0].run_name == "provider-sync-dry-run"
    assert database.fetch_all_calls == [(LIST_PROVIDER_OPS_RUN_HISTORY_QUERY, {"limit": 5})]


def _run_history_row(
    *,
    run_name: object = "provider-sync-dry-run",
    status: object = "success",
    duration_ms: object = 1200,
    summary_json: object = '{"mode":"real_provider_fixture_probe"}',
    output_excerpt: object = "provider_sync_dry_run_ok",
) -> DatabaseRow:
    return {
        "provider_ops_run_id": 42,
        "run_name": run_name,
        "run_type": "vps_helper",
        "source": "vps",
        "status": status,
        "operator_name": "nutmeg-vps-helper",
        "started_at": datetime(2026, 5, 9, 1, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 5, 9, 1, 1, tzinfo=UTC),
        "duration_ms": duration_ms,
        "exit_code": 0,
        "summary_json": summary_json,
        "output_excerpt": output_excerpt,
        "metadata_json": '{"secret_value_not_exposed":true}',
        "created_at": datetime(2026, 5, 9, 1, 1, tzinfo=UTC),
    }
