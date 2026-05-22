from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.live_probes import (
    ProviderRuntimeProbeRecord,
    ProviderRuntimeProbeResponse,
)
from nutmeg.providers.runtime_monitoring import (
    COUNT_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
    INSERT_PROVIDER_RUNTIME_INCIDENT_REPORT_QUERY,
    INSERT_PROVIDER_RUNTIME_SNAPSHOT_QUERY,
    LIST_LATEST_PROVIDER_RUNTIME_SNAPSHOTS_QUERY,
    LIST_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
    PRUNE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
    SUMMARIZE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
    UPDATE_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_QUERY,
    UPDATE_PROVIDER_RUNTIME_INCIDENT_STATUS_QUERY,
    PostgresProviderRuntimeMonitoringRepository,
    ProviderRuntimeIncidentReportInput,
    ProviderRuntimeIncidentReportRecord,
    build_provider_runtime_incident_notification_decision,
    build_provider_runtime_monitoring_alerts,
    provider_runtime_alert_level,
    provider_runtime_snapshot_inputs_from_probe_response,
)


class FakeProviderRuntimeMonitoringDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_PROVIDER_RUNTIME_SNAPSHOT_QUERY:
            return _snapshot_row(
                provider_name=params["provider_name"],
                capability=params["capability"],
                probe_status=params["probe_status"],
                key_configured=params["key_configured"],
                live_probe=params["live_probe"],
                latency_ms=params["latency_ms"],
                error_rate=params["error_rate"],
                metadata_json=params["metadata_json"],
                observed_at=params["observed_at"],
            )
        if query == INSERT_PROVIDER_RUNTIME_INCIDENT_REPORT_QUERY:
            return _incident_row(
                alert_level=params["alert_level"],
                alert_count=params["alert_count"],
                snapshot_count=params["snapshot_count"],
                summary_json=params["summary_json"],
                alerts_json=params["alerts_json"],
                thresholds_json=params["thresholds_json"],
                source=params["source"],
                created_by=params["created_by"],
                metadata_json=params["metadata_json"],
            )
        if query == PRUNE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY:
            return {"deleted_count": 2}
        if query == COUNT_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY:
            return {"total_count": 3}
        if query == SUMMARIZE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY:
            return _incident_summary_row(lookback_days=params["lookback_days"])
        if query == UPDATE_PROVIDER_RUNTIME_INCIDENT_STATUS_QUERY:
            return _incident_row(
                incident_status=params["incident_status"],
                acknowledged_by=params["updated_by"],
                resolved_by=params["updated_by"],
                resolution_note=params["resolution_note"],
            )
        if query == UPDATE_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_QUERY:
            return _incident_row(
                notification_status=params["notification_status"],
                notification_payload_json=params["notification_payload_json"],
            )
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_LATEST_PROVIDER_RUNTIME_SNAPSHOTS_QUERY:
            return [_snapshot_row()]
        if query == LIST_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY:
            return [_incident_row()]
        raise AssertionError(f"unexpected query: {query}")


def test_provider_runtime_monitoring_repository_records_and_lists_snapshots() -> None:
    checked_at = datetime(2026, 5, 9, 2, 30, tzinfo=UTC)
    response = ProviderRuntimeProbeResponse(
        items=[
            ProviderRuntimeProbeRecord(
                provider_name="the-odds-api",
                capability="odds",
                key_configured=True,
                status="rate_limited",
                live_probe=True,
                safe_to_call_real_provider=True,
                message="Provider returned a rate limit response.",
                observed_count=None,
                latency_ms=124,
                metadata={"probe": "sports", "rate_limit_remaining": 0},
                notes=["secret_value_not_exposed"],
                checked_at_utc=checked_at,
            )
        ],
        live_probe=True,
        generated_at_utc=checked_at,
    )
    snapshots = provider_runtime_snapshot_inputs_from_probe_response(response)
    database = FakeProviderRuntimeMonitoringDatabase()
    repository = PostgresProviderRuntimeMonitoringRepository(database)

    records = repository.record_snapshots(snapshots)
    latest = repository.list_latest_by_provider(limit=5)

    params = database.fetch_one_calls[0][1]
    assert database.fetch_one_calls[0][0] == INSERT_PROVIDER_RUNTIME_SNAPSHOT_QUERY
    assert params["provider_name"] == "the-odds-api"
    assert params["probe_status"] == "rate_limited"
    assert params["latency_ms"] == 124
    assert params["error_rate"] == 1.0
    assert params["failure_count"] == 1
    assert params["rate_limit_remaining"] == 0
    assert params["fallback_used"] is True
    assert params["next_action"] == "review_provider_plan_limit"
    assert "secret_value_not_exposed" in str(params["metadata_json"])
    assert "token" not in str(params["metadata_json"]).lower()
    assert records[0].provider_name == "the-odds-api"
    assert records[0].probe_status == "rate_limited"
    assert latest[0].provider_runtime_snapshot_id == 42
    assert database.fetch_all_calls == [
        (LIST_LATEST_PROVIDER_RUNTIME_SNAPSHOTS_QUERY, {"limit": 5})
    ]


def test_provider_runtime_monitoring_alerts_cover_rate_limits_and_latency() -> None:
    checked_at = datetime(2026, 5, 9, 2, 30, tzinfo=UTC)
    response = ProviderRuntimeProbeResponse(
        items=[
            ProviderRuntimeProbeRecord(
                provider_name="the-odds-api",
                capability="odds",
                key_configured=True,
                status="rate_limited",
                live_probe=True,
                safe_to_call_real_provider=False,
                message="Provider rate limit was reached during the live probe.",
                latency_ms=5600,
                metadata={"rate_limit_remaining": 0},
                notes=["secret_value_not_exposed"],
                checked_at_utc=checked_at,
            ),
            ProviderRuntimeProbeRecord(
                provider_name="sportmonks",
                capability="lineups_injuries",
                key_configured=False,
                status="not_configured",
                live_probe=False,
                safe_to_call_real_provider=False,
                message="SportMonks key is not configured.",
                latency_ms=3,
                metadata={},
                notes=["secret_value_not_exposed"],
                checked_at_utc=checked_at,
            ),
        ],
        live_probe=True,
        generated_at_utc=checked_at,
    )
    snapshots = provider_runtime_snapshot_inputs_from_probe_response(response)

    alerts = build_provider_runtime_monitoring_alerts(snapshots)

    alert_ids = {alert.alert_id for alert in alerts}
    assert provider_runtime_alert_level(alerts) == "P1"
    assert "the-odds-api_provider_error_rate" in alert_ids
    assert "the-odds-api_provider_latency_p1" in alert_ids
    assert "provider_fallback_usage_high" in alert_ids
    assert any(alert.metric == "provider_runtime_readiness" for alert in alerts)
    assert "token" not in str([alert.model_dump() for alert in alerts]).lower()


def test_provider_runtime_monitoring_repository_records_incident_reports() -> None:
    database = FakeProviderRuntimeMonitoringDatabase()
    repository = PostgresProviderRuntimeMonitoringRepository(database)

    report = repository.record_incident_report(
        ProviderRuntimeIncidentReportInput(
            alert_level="P1",
            alert_count=2,
            snapshot_count=4,
            summary_json={"provider_count": 4, "degraded_count": 2},
            alerts_json=[
                {
                    "alert_id": "provider_fallback_usage_high",
                    "severity": "P1",
                    "metric": "fallback_model_usage_rate",
                }
            ],
            thresholds_json={"fallback_usage_rate_p1": 0.5},
            source="vps_cron",
            created_by="provider-runtime-monitor",
            metadata_json={"secret_value_not_exposed": True},
        )
    )
    reports = repository.list_incident_reports(
        limit=3,
        offset=6,
        incident_status="open",
        alert_level="P1",
        notification_status="not_configured",
        source="vps_cron",
    )
    total_count = repository.count_incident_reports(
        incident_status="open",
        alert_level="P1",
        notification_status="not_configured",
        source="vps_cron",
    )
    resolved_report = repository.update_incident_status(
        provider_runtime_incident_report_id=77,
        incident_status="resolved",
        updated_by="ops-reviewer",
        resolution_note="Provider recovered after plan review.",
    )
    deleted_count = repository.prune_incident_reports(retention_days=90)

    params = database.fetch_one_calls[0][1]
    assert database.fetch_one_calls[0][0] == INSERT_PROVIDER_RUNTIME_INCIDENT_REPORT_QUERY
    assert params["alert_level"] == "P1"
    assert params["alert_count"] == 2
    assert params["snapshot_count"] == 4
    assert params["source"] == "vps_cron"
    assert "secret_value_not_exposed" in str(params["metadata_json"])
    assert "token" not in str(params).lower()
    assert report.alert_level == "P1"
    assert report.incident_status == "open"
    assert reports[0].provider_runtime_incident_report_id == 77
    assert reports[0].alerts_json[0]["alert_id"] == "provider_fallback_usage_high"
    assert total_count == 3
    assert resolved_report.incident_status == "resolved"
    assert resolved_report.resolved_by == "ops-reviewer"
    assert resolved_report.resolution_note == "Provider recovered after plan review."
    assert deleted_count == 2
    assert database.fetch_one_calls[1] == (
        COUNT_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
        {
            "incident_status": "open",
            "alert_level": "P1",
            "notification_status": "not_configured",
            "source": "vps_cron",
        },
    )
    assert database.fetch_one_calls[2] == (
        UPDATE_PROVIDER_RUNTIME_INCIDENT_STATUS_QUERY,
        {
            "provider_runtime_incident_report_id": 77,
            "incident_status": "resolved",
            "updated_by": "ops-reviewer",
            "resolution_note": "Provider recovered after plan review.",
        },
    )
    assert database.fetch_one_calls[3] == (
        PRUNE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
        {"retention_days": 90},
    )
    assert database.fetch_all_calls == [
        (
            LIST_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
            {
                "limit": 3,
                "offset": 6,
                "incident_status": "open",
                "alert_level": "P1",
                "notification_status": "not_configured",
                "source": "vps_cron",
            },
        )
    ]


def test_provider_runtime_monitoring_repository_summarizes_incident_reports() -> None:
    database = FakeProviderRuntimeMonitoringDatabase()
    repository = PostgresProviderRuntimeMonitoringRepository(database)

    summary = repository.summarize_incident_reports(lookback_days=14)

    assert "generate_series" in SUMMARIZE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY
    assert summary.lookback_days == 14
    assert summary.total_count == 3
    assert summary.active_count == 2
    assert summary.p1_count == 2
    assert summary.notification_failed_count == 1
    assert summary.mean_time_to_resolve_minutes == 12.5
    assert summary.trend_buckets[0].bucket_date == "2026-05-08"
    assert summary.trend_buckets[0].active_count == 1
    assert database.fetch_one_calls == [
        (SUMMARIZE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY, {"lookback_days": 14})
    ]


def test_provider_runtime_monitoring_repository_updates_incident_notification() -> None:
    database = FakeProviderRuntimeMonitoringDatabase()
    repository = PostgresProviderRuntimeMonitoringRepository(database)

    report = repository.update_incident_notification(
        provider_runtime_incident_report_id=77,
        notification_status="skipped",
        notification_payload_json={
            "adapter": "provider_ops",
            "reason": "dry_run_external_delivery_skipped",
            "secret_value_not_exposed": True,
        },
    )

    assert report.notification_status == "skipped"
    assert report.notification_payload_json["adapter"] == "provider_ops"
    assert "secret" not in str(report.notification_payload_json).lower().replace(
        "secret_value_not_exposed",
        "",
    )
    assert database.fetch_one_calls == [
        (
            UPDATE_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_QUERY,
            {
                "provider_runtime_incident_report_id": 77,
                "notification_status": "skipped",
                "notification_payload_json": (
                    '{"adapter":"provider_ops","reason":'
                    '"dry_run_external_delivery_skipped",'
                    '"secret_value_not_exposed":true}'
                ),
            },
        )
    ]


def test_provider_runtime_incident_notification_decision_defaults_closed() -> None:
    report = _incident_record()

    decision = build_provider_runtime_incident_notification_decision(
        report,
        enabled=False,
        adapter="provider_ops",
        dry_run=True,
        destination_configured=True,
        operator="provider-runtime-monitor",
    )

    assert decision.notification_status == "not_configured"
    assert decision.notification_payload_json["reason"] == "notification_disabled"
    assert decision.notification_payload_json["external_delivery"] is False
    assert decision.notification_payload_json["secret_value_not_exposed"] is True
    assert "token" not in str(decision.notification_payload_json).lower()


def test_provider_runtime_incident_notification_decision_supports_internal_adapter() -> None:
    report = _incident_record()

    decision = build_provider_runtime_incident_notification_decision(
        report,
        enabled=True,
        adapter="provider_ops",
        dry_run=False,
        destination_configured=True,
        operator="ops-reviewer",
    )

    assert decision.notification_status == "sent"
    assert decision.notification_payload_json["adapter"] == "provider_ops"
    assert (
        decision.notification_payload_json["reason"]
        == "provider_ops_internal_notification_recorded"
    )
    assert decision.notification_payload_json["external_delivery"] is False


def test_provider_runtime_incident_notification_decision_dry_run_skips_webhook() -> None:
    report = _incident_record()

    decision = build_provider_runtime_incident_notification_decision(
        report,
        enabled=True,
        adapter="webhook",
        dry_run=True,
        destination_configured=True,
        operator="ops-reviewer",
    )

    assert decision.notification_status == "skipped"
    assert decision.notification_payload_json["adapter"] == "webhook"
    assert (
        decision.notification_payload_json["reason"]
        == "dry_run_external_delivery_skipped"
    )
    assert "url" not in str(decision.notification_payload_json).lower()


def _snapshot_row(
    *,
    provider_name: object = "football-data.org",
    capability: object = "fixtures_results",
    probe_status: object = "key_configured",
    key_configured: object = True,
    live_probe: object = False,
    latency_ms: object = 2,
    error_rate: object = 0,
    metadata_json: object = '{"secret_value_not_exposed":true}',
    observed_at: object = datetime(2026, 5, 9, 2, 30, tzinfo=UTC),
) -> DatabaseRow:
    return {
        "provider_runtime_snapshot_id": 42,
        "provider_name": provider_name,
        "capability": capability,
        "probe_status": probe_status,
        "key_configured": key_configured,
        "live_probe": live_probe,
        "safe_to_call_real_provider": True,
        "latency_ms": latency_ms,
        "error_rate": error_rate,
        "success_count": 1,
        "failure_count": 0,
        "rate_limit_remaining": None,
        "quota_window": None,
        "fallback_used": False,
        "message": "Runtime key is configured.",
        "next_action": "no_action",
        "metadata_json": metadata_json,
        "observed_at": observed_at,
    }


def _incident_row(
    *,
    alert_level: object = "P1",
    alert_count: object = 1,
    snapshot_count: object = 4,
    summary_json: object = '{"provider_count":4}',
    alerts_json: object = '[{"alert_id":"provider_fallback_usage_high"}]',
    thresholds_json: object = '{"fallback_usage_rate_p1":0.5}',
    source: object = "vps_cron",
    created_by: object = "provider-runtime-monitor",
    metadata_json: object = '{"secret_value_not_exposed":true}',
    incident_status: object = "open",
    acknowledged_by: object = None,
    acknowledged_at: object = None,
    resolved_by: object = None,
    resolved_at: object = None,
    resolution_note: object = None,
    notification_status: object = "not_configured",
    notification_payload_json: object = '{"destination":"provider_ops"}',
    updated_at: object = datetime(2026, 5, 9, 3, 35, tzinfo=UTC),
) -> DatabaseRow:
    return {
        "provider_runtime_incident_report_id": 77,
        "alert_level": alert_level,
        "alert_count": alert_count,
        "snapshot_count": snapshot_count,
        "summary_json": summary_json,
        "alerts_json": alerts_json,
        "thresholds_json": thresholds_json,
        "source": source,
        "created_by": created_by,
        "metadata_json": metadata_json,
        "incident_status": incident_status,
        "acknowledged_by": acknowledged_by,
        "acknowledged_at": acknowledged_at,
        "resolved_by": resolved_by,
        "resolved_at": resolved_at,
        "resolution_note": resolution_note,
        "notification_status": notification_status,
        "notification_payload_json": notification_payload_json,
        "updated_at": updated_at,
        "created_at": datetime(2026, 5, 9, 3, 30, tzinfo=UTC),
    }


def _incident_summary_row(*, lookback_days: object = 30) -> DatabaseRow:
    return {
        "lookback_days": lookback_days,
        "total_count": 3,
        "open_count": 1,
        "acknowledged_count": 1,
        "resolved_count": 1,
        "ignored_count": 0,
        "active_count": 2,
        "p0_count": 0,
        "p1_count": 2,
        "p2_count": 1,
        "notification_failed_count": 1,
        "latest_created_at": datetime(2026, 5, 9, 3, 30, tzinfo=UTC),
        "mean_time_to_resolve_minutes": 12.5,
        "trend_buckets_json": (
            "["
            '{"bucket_date":"2026-05-08","total_count":1,'
            '"open_count":1,"acknowledged_count":0,"resolved_count":0,'
            '"ignored_count":0,"active_count":1,"p0_count":0,"p1_count":1,'
            '"p2_count":0,"notification_failed_count":0},'
            '{"bucket_date":"2026-05-09","total_count":2,'
            '"open_count":0,"acknowledged_count":1,"resolved_count":1,'
            '"ignored_count":0,"active_count":1,"p0_count":0,"p1_count":1,'
            '"p2_count":1,"notification_failed_count":1}'
            "]"
        ),
    }


def _incident_record() -> ProviderRuntimeIncidentReportRecord:
    return ProviderRuntimeIncidentReportRecord(
        provider_runtime_incident_report_id=77,
        alert_level="P1",
        alert_count=2,
        snapshot_count=4,
        summary_json={"provider_count": 4},
        alerts_json=[{"alert_id": "provider_fallback_usage_high"}],
        thresholds_json={"fallback_usage_rate_p1": 0.5},
        source="vps_cron",
        created_by="provider-runtime-monitor",
        metadata_json={"secret_value_not_exposed": True},
        incident_status="open",
        notification_status="not_configured",
        notification_payload_json={},
        created_at=datetime(2026, 5, 9, 3, 30, tzinfo=UTC),
    )
