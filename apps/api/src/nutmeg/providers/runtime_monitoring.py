from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.live_probes import (
    ProviderRuntimeProbeRecord,
    ProviderRuntimeProbeResponse,
    ProviderRuntimeProbeStatus,
)

type ProviderRuntimeSnapshotStatus = ProviderRuntimeProbeStatus

ProviderRuntimeMonitorNextAction = Literal[
    "no_action",
    "configure_runtime_key",
    "review_provider_plan_limit",
    "check_provider_credentials",
    "retry_after_provider_recovery",
    "adapter_not_ready",
]

ProviderRuntimeAlertSeverity = Literal["P0", "P1", "P2"]
ProviderRuntimeAlertLevel = Literal["ok", "P0", "P1", "P2"]
ProviderRuntimeIncidentStatus = Literal["open", "acknowledged", "resolved", "ignored"]
ProviderRuntimeIncidentNotificationStatus = Literal[
    "not_configured",
    "queued",
    "sent",
    "skipped",
    "failed",
]
ProviderRuntimeIncidentNotificationAdapter = Literal["provider_ops", "webhook"]

INSERT_PROVIDER_RUNTIME_SNAPSHOT_QUERY = """
INSERT INTO provider_runtime_snapshots (
  provider_name,
  capability,
  probe_status,
  key_configured,
  live_probe,
  safe_to_call_real_provider,
  latency_ms,
  error_rate,
  success_count,
  failure_count,
  rate_limit_remaining,
  quota_window,
  fallback_used,
  message,
  next_action,
  metadata_json,
  observed_at
) VALUES (
  %(provider_name)s,
  %(capability)s,
  %(probe_status)s,
  %(key_configured)s,
  %(live_probe)s,
  %(safe_to_call_real_provider)s,
  %(latency_ms)s,
  %(error_rate)s,
  %(success_count)s,
  %(failure_count)s,
  %(rate_limit_remaining)s,
  %(quota_window)s,
  %(fallback_used)s,
  %(message)s,
  %(next_action)s,
  %(metadata_json)s::jsonb,
  %(observed_at)s
)
RETURNING
  provider_runtime_snapshot_id,
  provider_name,
  capability,
  probe_status,
  key_configured,
  live_probe,
  safe_to_call_real_provider,
  latency_ms,
  error_rate,
  success_count,
  failure_count,
  rate_limit_remaining,
  quota_window,
  fallback_used,
  message,
  next_action,
  metadata_json,
  observed_at
"""

LIST_PROVIDER_RUNTIME_SNAPSHOTS_QUERY = """
SELECT
  provider_runtime_snapshot_id,
  provider_name,
  capability,
  probe_status,
  key_configured,
  live_probe,
  safe_to_call_real_provider,
  latency_ms,
  error_rate,
  success_count,
  failure_count,
  rate_limit_remaining,
  quota_window,
  fallback_used,
  message,
  next_action,
  metadata_json,
  observed_at
FROM provider_runtime_snapshots
ORDER BY observed_at DESC, provider_runtime_snapshot_id DESC
LIMIT %(limit)s
"""

LIST_LATEST_PROVIDER_RUNTIME_SNAPSHOTS_QUERY = """
WITH ranked_snapshots AS (
  SELECT
    provider_runtime_snapshot_id,
    provider_name,
    capability,
    probe_status,
    key_configured,
    live_probe,
    safe_to_call_real_provider,
    latency_ms,
    error_rate,
    success_count,
    failure_count,
    rate_limit_remaining,
    quota_window,
    fallback_used,
    message,
    next_action,
    metadata_json,
    observed_at,
    ROW_NUMBER() OVER (
      PARTITION BY provider_name, capability
      ORDER BY observed_at DESC, provider_runtime_snapshot_id DESC
    ) AS snapshot_rank
  FROM provider_runtime_snapshots
)
SELECT
  provider_runtime_snapshot_id,
  provider_name,
  capability,
  probe_status,
  key_configured,
  live_probe,
  safe_to_call_real_provider,
  latency_ms,
  error_rate,
  success_count,
  failure_count,
  rate_limit_remaining,
  quota_window,
  fallback_used,
  message,
  next_action,
  metadata_json,
  observed_at
FROM ranked_snapshots
WHERE snapshot_rank = 1
ORDER BY provider_name, capability
LIMIT %(limit)s
"""

INSERT_PROVIDER_RUNTIME_INCIDENT_REPORT_QUERY = """
INSERT INTO provider_runtime_incident_reports (
  alert_level,
  alert_count,
  snapshot_count,
  summary_json,
  alerts_json,
  thresholds_json,
  source,
  created_by,
  metadata_json
) VALUES (
  %(alert_level)s,
  %(alert_count)s,
  %(snapshot_count)s,
  %(summary_json)s::jsonb,
  %(alerts_json)s::jsonb,
  %(thresholds_json)s::jsonb,
  %(source)s,
  %(created_by)s,
  %(metadata_json)s::jsonb
)
RETURNING
  provider_runtime_incident_report_id,
  alert_level,
  alert_count,
  snapshot_count,
  summary_json,
  alerts_json,
  thresholds_json,
  source,
  created_by,
  metadata_json,
  incident_status,
  acknowledged_by,
  acknowledged_at,
  resolved_by,
  resolved_at,
  resolution_note,
  notification_status,
  notification_payload_json,
  updated_at,
  created_at
"""

LIST_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY = """
SELECT
  provider_runtime_incident_report_id,
  alert_level,
  alert_count,
  snapshot_count,
  summary_json,
  alerts_json,
  thresholds_json,
  source,
  created_by,
  metadata_json,
  incident_status,
  acknowledged_by,
  acknowledged_at,
  resolved_by,
  resolved_at,
  resolution_note,
  notification_status,
  notification_payload_json,
  updated_at,
  created_at
FROM provider_runtime_incident_reports
WHERE (%(incident_status)s::text IS NULL OR incident_status = %(incident_status)s)
  AND (%(alert_level)s::text IS NULL OR alert_level = %(alert_level)s)
  AND (
    %(notification_status)s::text IS NULL
    OR notification_status = %(notification_status)s
  )
  AND (%(source)s::text IS NULL OR source = %(source)s)
ORDER BY created_at DESC, provider_runtime_incident_report_id DESC
LIMIT %(limit)s
OFFSET %(offset)s
"""

COUNT_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY = """
SELECT COUNT(*) AS total_count
FROM provider_runtime_incident_reports
WHERE (%(incident_status)s::text IS NULL OR incident_status = %(incident_status)s)
  AND (%(alert_level)s::text IS NULL OR alert_level = %(alert_level)s)
  AND (
    %(notification_status)s::text IS NULL
    OR notification_status = %(notification_status)s
  )
  AND (%(source)s::text IS NULL OR source = %(source)s)
"""

SUMMARIZE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY = """
WITH params AS (
  SELECT
    %(lookback_days)s::int AS lookback_days,
    CURRENT_DATE - ((%(lookback_days)s::int - 1) * INTERVAL '1 day') AS start_date
),
days AS (
  SELECT generate_series(
    (SELECT start_date FROM params)::date,
    CURRENT_DATE,
    INTERVAL '1 day'
  )::date AS bucket_date
),
scoped AS (
  SELECT
    alert_level,
    incident_status,
    notification_status,
    created_at,
    resolved_at
  FROM provider_runtime_incident_reports
  WHERE created_at >= (SELECT start_date FROM params)
),
aggregates AS (
  SELECT
    COUNT(*) AS total_count,
    COUNT(*) FILTER (WHERE incident_status = 'open') AS open_count,
    COUNT(*) FILTER (WHERE incident_status = 'acknowledged') AS acknowledged_count,
    COUNT(*) FILTER (WHERE incident_status = 'resolved') AS resolved_count,
    COUNT(*) FILTER (WHERE incident_status = 'ignored') AS ignored_count,
    COUNT(*) FILTER (WHERE incident_status IN ('open', 'acknowledged')) AS active_count,
    COUNT(*) FILTER (WHERE alert_level = 'P0') AS p0_count,
    COUNT(*) FILTER (WHERE alert_level = 'P1') AS p1_count,
    COUNT(*) FILTER (WHERE alert_level = 'P2') AS p2_count,
    COUNT(*) FILTER (WHERE notification_status = 'failed') AS notification_failed_count,
    MAX(created_at) AS latest_created_at,
    AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 60.0)
      FILTER (WHERE resolved_at IS NOT NULL) AS mean_time_to_resolve_minutes
  FROM scoped
),
trend AS (
  SELECT
    COALESCE(
      jsonb_agg(
        jsonb_build_object(
          'bucket_date', days.bucket_date::text,
          'total_count', COALESCE(buckets.total_count, 0),
          'open_count', COALESCE(buckets.open_count, 0),
          'acknowledged_count', COALESCE(buckets.acknowledged_count, 0),
          'resolved_count', COALESCE(buckets.resolved_count, 0),
          'ignored_count', COALESCE(buckets.ignored_count, 0),
          'active_count', COALESCE(buckets.active_count, 0),
          'p0_count', COALESCE(buckets.p0_count, 0),
          'p1_count', COALESCE(buckets.p1_count, 0),
          'p2_count', COALESCE(buckets.p2_count, 0),
          'notification_failed_count',
            COALESCE(buckets.notification_failed_count, 0)
        )
        ORDER BY days.bucket_date
      ),
      '[]'::jsonb
    ) AS trend_buckets_json
  FROM days
  LEFT JOIN (
    SELECT
      created_at::date AS bucket_date,
      COUNT(*) AS total_count,
      COUNT(*) FILTER (WHERE incident_status = 'open') AS open_count,
      COUNT(*) FILTER (WHERE incident_status = 'acknowledged') AS acknowledged_count,
      COUNT(*) FILTER (WHERE incident_status = 'resolved') AS resolved_count,
      COUNT(*) FILTER (WHERE incident_status = 'ignored') AS ignored_count,
      COUNT(*) FILTER (
        WHERE incident_status IN ('open', 'acknowledged')
      ) AS active_count,
      COUNT(*) FILTER (WHERE alert_level = 'P0') AS p0_count,
      COUNT(*) FILTER (WHERE alert_level = 'P1') AS p1_count,
      COUNT(*) FILTER (WHERE alert_level = 'P2') AS p2_count,
      COUNT(*) FILTER (
        WHERE notification_status = 'failed'
      ) AS notification_failed_count
    FROM scoped
    GROUP BY created_at::date
  ) buckets ON buckets.bucket_date = days.bucket_date
)
SELECT
  params.lookback_days,
  aggregates.total_count,
  aggregates.open_count,
  aggregates.acknowledged_count,
  aggregates.resolved_count,
  aggregates.ignored_count,
  aggregates.active_count,
  aggregates.p0_count,
  aggregates.p1_count,
  aggregates.p2_count,
  aggregates.notification_failed_count,
  aggregates.latest_created_at,
  aggregates.mean_time_to_resolve_minutes,
  trend.trend_buckets_json
FROM params
CROSS JOIN aggregates
CROSS JOIN trend
"""

UPDATE_PROVIDER_RUNTIME_INCIDENT_STATUS_QUERY = """
UPDATE provider_runtime_incident_reports
SET
  incident_status = %(incident_status)s,
  acknowledged_by = CASE
    WHEN %(incident_status)s IN ('acknowledged', 'resolved', 'ignored')
      THEN COALESCE(acknowledged_by, %(updated_by)s)
    WHEN %(incident_status)s = 'open'
      THEN NULL
    ELSE acknowledged_by
  END,
  acknowledged_at = CASE
    WHEN %(incident_status)s IN ('acknowledged', 'resolved', 'ignored')
      THEN COALESCE(acknowledged_at, now())
    WHEN %(incident_status)s = 'open'
      THEN NULL
    ELSE acknowledged_at
  END,
  resolved_by = CASE
    WHEN %(incident_status)s IN ('resolved', 'ignored')
      THEN %(updated_by)s
    WHEN %(incident_status)s IN ('open', 'acknowledged')
      THEN NULL
    ELSE resolved_by
  END,
  resolved_at = CASE
    WHEN %(incident_status)s IN ('resolved', 'ignored')
      THEN now()
    WHEN %(incident_status)s IN ('open', 'acknowledged')
      THEN NULL
    ELSE resolved_at
  END,
  resolution_note = %(resolution_note)s,
  updated_at = now()
WHERE provider_runtime_incident_report_id = %(provider_runtime_incident_report_id)s
RETURNING
  provider_runtime_incident_report_id,
  alert_level,
  alert_count,
  snapshot_count,
  summary_json,
  alerts_json,
  thresholds_json,
  source,
  created_by,
  metadata_json,
  incident_status,
  acknowledged_by,
  acknowledged_at,
  resolved_by,
  resolved_at,
  resolution_note,
  notification_status,
  notification_payload_json,
  updated_at,
  created_at
"""

UPDATE_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_QUERY = """
UPDATE provider_runtime_incident_reports
SET
  notification_status = %(notification_status)s,
  notification_payload_json = %(notification_payload_json)s::jsonb,
  updated_at = now()
WHERE provider_runtime_incident_report_id = %(provider_runtime_incident_report_id)s
RETURNING
  provider_runtime_incident_report_id,
  alert_level,
  alert_count,
  snapshot_count,
  summary_json,
  alerts_json,
  thresholds_json,
  source,
  created_by,
  metadata_json,
  incident_status,
  acknowledged_by,
  acknowledged_at,
  resolved_by,
  resolved_at,
  resolution_note,
  notification_status,
  notification_payload_json,
  updated_at,
  created_at
"""

PRUNE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY = """
WITH deleted_reports AS (
  DELETE FROM provider_runtime_incident_reports
  WHERE created_at < now() - (%(retention_days)s::int * INTERVAL '1 day')
  RETURNING 1
)
SELECT COUNT(*) AS deleted_count
FROM deleted_reports
"""


class ProviderRuntimeMonitoringDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one mapping row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read statement and return mapping rows."""


class ProviderRuntimeSnapshotInput(BaseModel):
    provider_name: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    probe_status: ProviderRuntimeSnapshotStatus
    key_configured: bool
    live_probe: bool
    safe_to_call_real_provider: bool
    latency_ms: int | None = Field(default=None, ge=0)
    error_rate: float | None = Field(default=None, ge=0, le=1)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    rate_limit_remaining: int | None = Field(default=None, ge=0)
    quota_window: str | None = None
    fallback_used: bool
    message: str
    next_action: ProviderRuntimeMonitorNextAction
    metadata_json: dict[str, object] = Field(default_factory=dict)
    observed_at: datetime


class ProviderRuntimeSnapshotRecord(BaseModel):
    provider_runtime_snapshot_id: int = Field(gt=0)
    provider_name: str
    capability: str
    probe_status: ProviderRuntimeSnapshotStatus
    key_configured: bool
    live_probe: bool
    safe_to_call_real_provider: bool
    latency_ms: int | None = Field(default=None, ge=0)
    error_rate: float | None = Field(default=None, ge=0, le=1)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    rate_limit_remaining: int | None = Field(default=None, ge=0)
    quota_window: str | None = None
    fallback_used: bool
    message: str
    next_action: ProviderRuntimeMonitorNextAction
    metadata_json: dict[str, object] = Field(default_factory=dict)
    observed_at: datetime


class ProviderRuntimeMonitoringThresholds(BaseModel):
    provider_latency_p2_ms: int = Field(default=1500, ge=0)
    provider_latency_p1_ms: int = Field(default=5000, ge=0)
    provider_error_rate_p1: float = Field(default=1.0, ge=0, le=1)
    provider_plan_limit_p2: float = Field(default=0.5, ge=0, le=1)
    fallback_usage_rate_p1: float = Field(default=0.5, ge=0, le=1)


class ProviderRuntimeMonitoringAlert(BaseModel):
    alert_id: str
    severity: ProviderRuntimeAlertSeverity
    provider_name: str | None = None
    capability: str | None = None
    metric: str
    current_value: float | str | None = None
    threshold: float | str | None = None
    message: str
    recommended_action: str


class ProviderRuntimeIncidentReportInput(BaseModel):
    alert_level: ProviderRuntimeAlertLevel
    alert_count: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)
    summary_json: dict[str, object] = Field(default_factory=dict)
    alerts_json: list[dict[str, object]] = Field(default_factory=list)
    thresholds_json: dict[str, object] = Field(default_factory=dict)
    source: str = Field(default="manual", min_length=1, max_length=120)
    created_by: str = Field(default="nutmeg-ops", min_length=1, max_length=120)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderRuntimeIncidentReportRecord(BaseModel):
    provider_runtime_incident_report_id: int = Field(gt=0)
    alert_level: ProviderRuntimeAlertLevel
    alert_count: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)
    summary_json: dict[str, object] = Field(default_factory=dict)
    alerts_json: list[dict[str, object]] = Field(default_factory=list)
    thresholds_json: dict[str, object] = Field(default_factory=dict)
    source: str
    created_by: str
    metadata_json: dict[str, object] = Field(default_factory=dict)
    incident_status: ProviderRuntimeIncidentStatus = "open"
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    notification_status: ProviderRuntimeIncidentNotificationStatus = "not_configured"
    notification_payload_json: dict[str, object] = Field(default_factory=dict)
    updated_at: datetime | None = None
    created_at: datetime


class ProviderRuntimeIncidentNotificationDecision(BaseModel):
    notification_status: ProviderRuntimeIncidentNotificationStatus
    notification_payload_json: dict[str, object] = Field(default_factory=dict)


class ProviderRuntimeIncidentTrendBucket(BaseModel):
    bucket_date: str = Field(min_length=10)
    total_count: int = Field(ge=0)
    open_count: int = Field(ge=0)
    acknowledged_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    ignored_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    p0_count: int = Field(ge=0)
    p1_count: int = Field(ge=0)
    p2_count: int = Field(ge=0)
    notification_failed_count: int = Field(ge=0)


class ProviderRuntimeIncidentSummary(BaseModel):
    lookback_days: int = Field(ge=1, le=3650)
    total_count: int = Field(ge=0)
    open_count: int = Field(ge=0)
    acknowledged_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)
    ignored_count: int = Field(ge=0)
    active_count: int = Field(ge=0)
    p0_count: int = Field(ge=0)
    p1_count: int = Field(ge=0)
    p2_count: int = Field(ge=0)
    notification_failed_count: int = Field(ge=0)
    latest_created_at: datetime | None = None
    mean_time_to_resolve_minutes: float | None = Field(default=None, ge=0)
    trend_buckets: list[ProviderRuntimeIncidentTrendBucket] = Field(
        default_factory=list
    )


class PostgresProviderRuntimeMonitoringRepository:
    def __init__(self, database: ProviderRuntimeMonitoringDatabase) -> None:
        self.database = database

    def record_snapshot(
        self,
        snapshot: ProviderRuntimeSnapshotInput,
    ) -> ProviderRuntimeSnapshotRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PROVIDER_RUNTIME_SNAPSHOT_QUERY,
                _snapshot_params(snapshot),
            )
        )
        return _snapshot_record_from_row(row)

    def record_snapshots(
        self,
        snapshots: Sequence[ProviderRuntimeSnapshotInput],
    ) -> list[ProviderRuntimeSnapshotRecord]:
        return [self.record_snapshot(snapshot) for snapshot in snapshots]

    def list_recent(self, *, limit: int = 50) -> list[ProviderRuntimeSnapshotRecord]:
        return [
            _snapshot_record_from_row(row)
            for row in self.database.fetch_all(
                LIST_PROVIDER_RUNTIME_SNAPSHOTS_QUERY,
                {"limit": limit},
            )
        ]

    def list_latest_by_provider(
        self,
        *,
        limit: int = 50,
    ) -> list[ProviderRuntimeSnapshotRecord]:
        return [
            _snapshot_record_from_row(row)
            for row in self.database.fetch_all(
                LIST_LATEST_PROVIDER_RUNTIME_SNAPSHOTS_QUERY,
                {"limit": limit},
            )
        ]

    def record_incident_report(
        self,
        report: ProviderRuntimeIncidentReportInput,
    ) -> ProviderRuntimeIncidentReportRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PROVIDER_RUNTIME_INCIDENT_REPORT_QUERY,
                _incident_report_params(report),
            )
        )
        return _incident_report_record_from_row(row)

    def list_incident_reports(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        incident_status: ProviderRuntimeIncidentStatus | None = None,
        alert_level: ProviderRuntimeAlertLevel | None = None,
        notification_status: ProviderRuntimeIncidentNotificationStatus | None = None,
        source: str | None = None,
    ) -> list[ProviderRuntimeIncidentReportRecord]:
        return [
            _incident_report_record_from_row(row)
            for row in self.database.fetch_all(
                LIST_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
                _incident_report_filter_params(
                    limit=limit,
                    offset=offset,
                    incident_status=incident_status,
                    alert_level=alert_level,
                    notification_status=notification_status,
                    source=source,
                ),
            )
        ]

    def count_incident_reports(
        self,
        *,
        incident_status: ProviderRuntimeIncidentStatus | None = None,
        alert_level: ProviderRuntimeAlertLevel | None = None,
        notification_status: ProviderRuntimeIncidentNotificationStatus | None = None,
        source: str | None = None,
    ) -> int:
        row = _required_row(
            self.database.fetch_one(
                COUNT_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
                _incident_report_filter_params(
                    incident_status=incident_status,
                    alert_level=alert_level,
                    notification_status=notification_status,
                    source=source,
                ),
            )
        )
        return _int(row["total_count"])

    def summarize_incident_reports(
        self,
        *,
        lookback_days: int = 30,
    ) -> ProviderRuntimeIncidentSummary:
        row = _required_row(
            self.database.fetch_one(
                SUMMARIZE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
                {"lookback_days": lookback_days},
            )
        )
        return _incident_summary_from_row(row)

    def update_incident_status(
        self,
        *,
        provider_runtime_incident_report_id: int,
        incident_status: ProviderRuntimeIncidentStatus,
        updated_by: str,
        resolution_note: str | None = None,
    ) -> ProviderRuntimeIncidentReportRecord:
        row = self.database.fetch_one(
            UPDATE_PROVIDER_RUNTIME_INCIDENT_STATUS_QUERY,
            {
                "provider_runtime_incident_report_id": (
                    provider_runtime_incident_report_id
                ),
                "incident_status": incident_status,
                "updated_by": updated_by[:120],
                "resolution_note": (
                    resolution_note[:500] if resolution_note is not None else None
                ),
            },
        )
        if row is None:
            raise LookupError("provider runtime incident report not found")
        return _incident_report_record_from_row(row)

    def update_incident_notification(
        self,
        *,
        provider_runtime_incident_report_id: int,
        notification_status: ProviderRuntimeIncidentNotificationStatus,
        notification_payload_json: Mapping[str, object],
    ) -> ProviderRuntimeIncidentReportRecord:
        row = self.database.fetch_one(
            UPDATE_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_QUERY,
            {
                "provider_runtime_incident_report_id": (
                    provider_runtime_incident_report_id
                ),
                "notification_status": notification_status,
                "notification_payload_json": _json(dict(notification_payload_json)),
            },
        )
        if row is None:
            raise LookupError("provider runtime incident report not found")
        return _incident_report_record_from_row(row)

    def prune_incident_reports(self, *, retention_days: int) -> int:
        row = _required_row(
            self.database.fetch_one(
                PRUNE_PROVIDER_RUNTIME_INCIDENT_REPORTS_QUERY,
                {"retention_days": retention_days},
            )
        )
        return _int(row["deleted_count"])


def provider_runtime_snapshot_inputs_from_probe_response(
    response: ProviderRuntimeProbeResponse,
) -> list[ProviderRuntimeSnapshotInput]:
    return [
        provider_runtime_snapshot_input_from_probe_record(item)
        for item in response.items
    ]


def provider_runtime_snapshot_input_from_probe_record(
    record: ProviderRuntimeProbeRecord,
) -> ProviderRuntimeSnapshotInput:
    success_count = 1 if record.status in {"ok", "key_configured"} else 0
    failure_count = (
        1
        if record.status in {"limited", "auth_failed", "rate_limited", "unavailable"}
        else 0
    )
    return ProviderRuntimeSnapshotInput(
        provider_name=record.provider_name,
        capability=record.capability,
        probe_status=record.status,
        key_configured=record.key_configured,
        live_probe=record.live_probe,
        safe_to_call_real_provider=record.safe_to_call_real_provider,
        latency_ms=record.latency_ms,
        error_rate=_error_rate_for_status(record.status),
        success_count=success_count,
        failure_count=failure_count,
        rate_limit_remaining=_optional_int_from_metadata(
            record.metadata,
            "rate_limit_remaining",
        ),
        quota_window=_optional_str_from_metadata(record.metadata, "quota_window"),
        fallback_used=_fallback_used_for_status(record.status),
        message=record.message,
        next_action=_next_action_for_status(record.status),
        metadata_json={
            "probe_metadata": dict(record.metadata),
            "notes": list(record.notes),
            "observed_count": record.observed_count,
            "monitoring_source": "provider_runtime_probe",
            "secret_value_not_exposed": True,
        },
        observed_at=record.checked_at_utc,
    )


def build_provider_runtime_monitoring_alerts(
    snapshots: Sequence[ProviderRuntimeSnapshotInput | ProviderRuntimeSnapshotRecord],
    *,
    thresholds: ProviderRuntimeMonitoringThresholds | None = None,
) -> list[ProviderRuntimeMonitoringAlert]:
    effective_thresholds = thresholds or ProviderRuntimeMonitoringThresholds()
    items = list(snapshots)
    alerts: list[ProviderRuntimeMonitoringAlert] = []
    if items and all(
        item.probe_status in {"auth_failed", "rate_limited", "unavailable"}
        for item in items
    ):
        alerts.append(
            ProviderRuntimeMonitoringAlert(
                alert_id="all_runtime_providers_failed",
                severity="P0",
                metric="provider_error_rate",
                current_value=1.0,
                threshold=effective_thresholds.provider_error_rate_p1,
                message="All configured runtime provider probes are failing.",
                recommended_action="pause_real_provider_operations_and_investigate",
            )
        )

    fallback_usage_rate = _fallback_usage_rate(items)
    if fallback_usage_rate >= effective_thresholds.fallback_usage_rate_p1:
        alerts.append(
            ProviderRuntimeMonitoringAlert(
                alert_id="provider_fallback_usage_high",
                severity="P1",
                metric="fallback_model_usage_rate",
                current_value=round(fallback_usage_rate, 4),
                threshold=effective_thresholds.fallback_usage_rate_p1,
                message="Provider fallback usage is above the configured threshold.",
                recommended_action="review_provider_keys_limits_and_data_coverage",
            )
        )

    for item in items:
        alerts.extend(_snapshot_alerts(item, effective_thresholds))

    return sorted(
        alerts,
        key=lambda alert: (
            _severity_rank(alert.severity),
            alert.provider_name or "",
            alert.capability or "",
            alert.alert_id,
        ),
    )


def provider_runtime_alert_level(
    alerts: Sequence[ProviderRuntimeMonitoringAlert],
) -> ProviderRuntimeAlertLevel:
    severities = {alert.severity for alert in alerts}
    if "P0" in severities:
        return "P0"
    if "P1" in severities:
        return "P1"
    if "P2" in severities:
        return "P2"
    return "ok"


def build_provider_runtime_incident_notification_decision(
    report: ProviderRuntimeIncidentReportRecord,
    *,
    enabled: bool,
    adapter: ProviderRuntimeIncidentNotificationAdapter,
    dry_run: bool,
    destination_configured: bool,
    operator: str,
) -> ProviderRuntimeIncidentNotificationDecision:
    base_payload: dict[str, object] = {
        "adapter": adapter,
        "enabled": enabled,
        "dry_run": dry_run,
        "destination_configured": destination_configured,
        "external_delivery": False,
        "provider_runtime_incident_report_id": (
            report.provider_runtime_incident_report_id
        ),
        "alert_level": report.alert_level,
        "alert_count": report.alert_count,
        "snapshot_count": report.snapshot_count,
        "incident_status": report.incident_status,
        "source": report.source,
        "created_by": report.created_by,
        "operator": operator[:120],
        "secret_value_not_exposed": True,
    }
    if not enabled:
        return _notification_decision(
            "not_configured",
            base_payload,
            reason="notification_disabled",
        )
    if adapter == "webhook" and not destination_configured:
        return _notification_decision(
            "not_configured",
            base_payload,
            reason="webhook_destination_not_configured",
        )
    if dry_run:
        return _notification_decision(
            "skipped",
            base_payload,
            reason="dry_run_external_delivery_skipped",
        )
    if adapter == "provider_ops":
        return _notification_decision(
            "sent",
            base_payload,
            reason="provider_ops_internal_notification_recorded",
        )
    return _notification_decision(
        "queued",
        base_payload,
        reason="webhook_delivery_not_implemented",
    )


def _snapshot_params(snapshot: ProviderRuntimeSnapshotInput) -> dict[str, object]:
    return {
        "provider_name": snapshot.provider_name,
        "capability": snapshot.capability,
        "probe_status": snapshot.probe_status,
        "key_configured": snapshot.key_configured,
        "live_probe": snapshot.live_probe,
        "safe_to_call_real_provider": snapshot.safe_to_call_real_provider,
        "latency_ms": snapshot.latency_ms,
        "error_rate": snapshot.error_rate,
        "success_count": snapshot.success_count,
        "failure_count": snapshot.failure_count,
        "rate_limit_remaining": snapshot.rate_limit_remaining,
        "quota_window": snapshot.quota_window,
        "fallback_used": snapshot.fallback_used,
        "message": snapshot.message[:500],
        "next_action": snapshot.next_action,
        "metadata_json": _json(snapshot.metadata_json),
        "observed_at": snapshot.observed_at,
    }


def _incident_report_params(
    report: ProviderRuntimeIncidentReportInput,
) -> dict[str, object]:
    return {
        "alert_level": report.alert_level,
        "alert_count": report.alert_count,
        "snapshot_count": report.snapshot_count,
        "summary_json": _json(report.summary_json),
        "alerts_json": _json(report.alerts_json),
        "thresholds_json": _json(report.thresholds_json),
        "source": report.source[:120],
        "created_by": report.created_by[:120],
        "metadata_json": _json(report.metadata_json),
    }


def _notification_decision(
    notification_status: ProviderRuntimeIncidentNotificationStatus,
    payload: Mapping[str, object],
    *,
    reason: str,
) -> ProviderRuntimeIncidentNotificationDecision:
    notification_payload = dict(payload)
    notification_payload["reason"] = reason
    return ProviderRuntimeIncidentNotificationDecision(
        notification_status=notification_status,
        notification_payload_json=notification_payload,
    )


def _incident_report_filter_params(
    *,
    limit: int | None = None,
    offset: int | None = None,
    incident_status: ProviderRuntimeIncidentStatus | None = None,
    alert_level: ProviderRuntimeAlertLevel | None = None,
    notification_status: ProviderRuntimeIncidentNotificationStatus | None = None,
    source: str | None = None,
) -> dict[str, object]:
    params: dict[str, object] = {
        "incident_status": incident_status,
        "alert_level": alert_level,
        "notification_status": notification_status,
        "source": source,
    }
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    return params


def _snapshot_record_from_row(row: DatabaseRow) -> ProviderRuntimeSnapshotRecord:
    return ProviderRuntimeSnapshotRecord(
        provider_runtime_snapshot_id=_int(row["provider_runtime_snapshot_id"]),
        provider_name=str(row["provider_name"]),
        capability=str(row["capability"]),
        probe_status=_snapshot_status(row["probe_status"]),
        key_configured=_bool(row["key_configured"]),
        live_probe=_bool(row["live_probe"]),
        safe_to_call_real_provider=_bool(row["safe_to_call_real_provider"]),
        latency_ms=_optional_int(row["latency_ms"]),
        error_rate=_optional_float(row["error_rate"]),
        success_count=_int(row["success_count"]),
        failure_count=_int(row["failure_count"]),
        rate_limit_remaining=_optional_int(row["rate_limit_remaining"]),
        quota_window=_optional_str(row["quota_window"]),
        fallback_used=_bool(row["fallback_used"]),
        message=str(row["message"]),
        next_action=_next_action(row["next_action"]),
        metadata_json=_object_mapping(row["metadata_json"]),
        observed_at=_datetime(row["observed_at"]),
    )


def _incident_report_record_from_row(
    row: DatabaseRow,
) -> ProviderRuntimeIncidentReportRecord:
    return ProviderRuntimeIncidentReportRecord(
        provider_runtime_incident_report_id=_int(
            row["provider_runtime_incident_report_id"]
        ),
        alert_level=_alert_level(row["alert_level"]),
        alert_count=_int(row["alert_count"]),
        snapshot_count=_int(row["snapshot_count"]),
        summary_json=_object_mapping(row["summary_json"]),
        alerts_json=_object_list(row["alerts_json"]),
        thresholds_json=_object_mapping(row["thresholds_json"]),
        source=str(row["source"]),
        created_by=str(row["created_by"]),
        metadata_json=_object_mapping(row["metadata_json"]),
        incident_status=_incident_status(row["incident_status"]),
        acknowledged_by=_optional_str(row["acknowledged_by"]),
        acknowledged_at=_optional_datetime(row["acknowledged_at"]),
        resolved_by=_optional_str(row["resolved_by"]),
        resolved_at=_optional_datetime(row["resolved_at"]),
        resolution_note=_optional_str(row["resolution_note"]),
        notification_status=_incident_notification_status(
            row["notification_status"]
        ),
        notification_payload_json=_object_mapping(row["notification_payload_json"]),
        updated_at=_optional_datetime(row["updated_at"]),
        created_at=_datetime(row["created_at"]),
    )


def _incident_summary_from_row(row: DatabaseRow) -> ProviderRuntimeIncidentSummary:
    return ProviderRuntimeIncidentSummary(
        lookback_days=_int(row["lookback_days"]),
        total_count=_int(row["total_count"]),
        open_count=_int(row["open_count"]),
        acknowledged_count=_int(row["acknowledged_count"]),
        resolved_count=_int(row["resolved_count"]),
        ignored_count=_int(row["ignored_count"]),
        active_count=_int(row["active_count"]),
        p0_count=_int(row["p0_count"]),
        p1_count=_int(row["p1_count"]),
        p2_count=_int(row["p2_count"]),
        notification_failed_count=_int(row["notification_failed_count"]),
        latest_created_at=_optional_datetime(row["latest_created_at"]),
        mean_time_to_resolve_minutes=_optional_float(
            row["mean_time_to_resolve_minutes"]
        ),
        trend_buckets=[
            _incident_trend_bucket_from_mapping(item)
            for item in _object_list(row["trend_buckets_json"])
        ],
    )


def _incident_trend_bucket_from_mapping(
    item: Mapping[str, object],
) -> ProviderRuntimeIncidentTrendBucket:
    return ProviderRuntimeIncidentTrendBucket(
        bucket_date=str(item["bucket_date"]),
        total_count=_int(item.get("total_count", 0)),
        open_count=_int(item.get("open_count", 0)),
        acknowledged_count=_int(item.get("acknowledged_count", 0)),
        resolved_count=_int(item.get("resolved_count", 0)),
        ignored_count=_int(item.get("ignored_count", 0)),
        active_count=_int(item.get("active_count", 0)),
        p0_count=_int(item.get("p0_count", 0)),
        p1_count=_int(item.get("p1_count", 0)),
        p2_count=_int(item.get("p2_count", 0)),
        notification_failed_count=_int(item.get("notification_failed_count", 0)),
    )


def _error_rate_for_status(status: ProviderRuntimeSnapshotStatus) -> float | None:
    if status in {"ok", "key_configured"}:
        return 0.0
    if status == "limited":
        return 0.5
    if status in {"auth_failed", "rate_limited", "unavailable"}:
        return 1.0
    return None


def _fallback_used_for_status(status: ProviderRuntimeSnapshotStatus) -> bool:
    return status not in {"ok", "key_configured"}


def _next_action_for_status(
    status: ProviderRuntimeSnapshotStatus,
) -> ProviderRuntimeMonitorNextAction:
    match status:
        case "ok" | "key_configured":
            return "no_action"
        case "not_configured":
            return "configure_runtime_key"
        case "limited" | "rate_limited":
            return "review_provider_plan_limit"
        case "auth_failed":
            return "check_provider_credentials"
        case "unavailable":
            return "retry_after_provider_recovery"
        case "adapter_planned":
            return "adapter_not_ready"


def _snapshot_alerts(
    snapshot: ProviderRuntimeSnapshotInput | ProviderRuntimeSnapshotRecord,
    thresholds: ProviderRuntimeMonitoringThresholds,
) -> list[ProviderRuntimeMonitoringAlert]:
    alerts: list[ProviderRuntimeMonitoringAlert] = []
    if (
        snapshot.error_rate is not None
        and snapshot.error_rate >= thresholds.provider_error_rate_p1
    ):
        alerts.append(
            ProviderRuntimeMonitoringAlert(
                alert_id=f"{snapshot.provider_name}_provider_error_rate",
                severity="P1",
                provider_name=snapshot.provider_name,
                capability=snapshot.capability,
                metric="provider_error_rate",
                current_value=snapshot.error_rate,
                threshold=thresholds.provider_error_rate_p1,
                message="Provider runtime probe is failing.",
                recommended_action=snapshot.next_action,
            )
        )
    elif (
        snapshot.error_rate is not None
        and snapshot.error_rate >= thresholds.provider_plan_limit_p2
    ):
        alerts.append(
            ProviderRuntimeMonitoringAlert(
                alert_id=f"{snapshot.provider_name}_provider_plan_limit",
                severity="P2",
                provider_name=snapshot.provider_name,
                capability=snapshot.capability,
                metric="provider_error_rate",
                current_value=snapshot.error_rate,
                threshold=thresholds.provider_plan_limit_p2,
                message="Provider runtime probe is partially limited.",
                recommended_action=snapshot.next_action,
            )
        )
    elif snapshot.probe_status in {"not_configured", "adapter_planned"}:
        alerts.append(
            ProviderRuntimeMonitoringAlert(
                alert_id=f"{snapshot.provider_name}_{snapshot.probe_status}",
                severity="P2",
                provider_name=snapshot.provider_name,
                capability=snapshot.capability,
                metric="provider_runtime_readiness",
                current_value=snapshot.probe_status,
                threshold="ok_or_key_configured",
                message="Provider runtime readiness is incomplete.",
                recommended_action=snapshot.next_action,
            )
        )

    if snapshot.latency_ms is not None:
        latency_alert = _latency_alert(snapshot, thresholds)
        if latency_alert is not None:
            alerts.append(latency_alert)
    return alerts


def _latency_alert(
    snapshot: ProviderRuntimeSnapshotInput | ProviderRuntimeSnapshotRecord,
    thresholds: ProviderRuntimeMonitoringThresholds,
) -> ProviderRuntimeMonitoringAlert | None:
    if snapshot.latency_ms is None:
        return None
    if snapshot.latency_ms >= thresholds.provider_latency_p1_ms:
        return ProviderRuntimeMonitoringAlert(
            alert_id=f"{snapshot.provider_name}_provider_latency_p1",
            severity="P1",
            provider_name=snapshot.provider_name,
            capability=snapshot.capability,
            metric="provider_latency",
            current_value=float(snapshot.latency_ms),
            threshold=float(thresholds.provider_latency_p1_ms),
            message="Provider runtime probe latency is very high.",
            recommended_action="review_provider_latency_and_timeout_settings",
        )
    if snapshot.latency_ms >= thresholds.provider_latency_p2_ms:
        return ProviderRuntimeMonitoringAlert(
            alert_id=f"{snapshot.provider_name}_provider_latency_p2",
            severity="P2",
            provider_name=snapshot.provider_name,
            capability=snapshot.capability,
            metric="provider_latency",
            current_value=float(snapshot.latency_ms),
            threshold=float(thresholds.provider_latency_p2_ms),
            message="Provider runtime probe latency is elevated.",
            recommended_action="watch_provider_latency",
        )
    return None


def _fallback_usage_rate(
    snapshots: Sequence[ProviderRuntimeSnapshotInput | ProviderRuntimeSnapshotRecord],
) -> float:
    if not snapshots:
        return 0.0
    return sum(1 for item in snapshots if item.fallback_used) / len(snapshots)


def _severity_rank(severity: ProviderRuntimeAlertSeverity) -> int:
    return {"P0": 0, "P1": 1, "P2": 2}[severity]


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


def _object_mapping(value: object) -> dict[str, object]:
    parsed = _json_value(value)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object")
    return {str(key): item for key, item in parsed.items()}


def _object_list(value: object) -> list[dict[str, object]]:
    parsed = _json_value(value)
    if not isinstance(parsed, list):
        raise ValueError("expected JSON list")
    items: list[dict[str, object]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("expected JSON object list")
        items.append({str(key): value for key, value in item.items()})
    return items


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


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(str(value))


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).lower()
    if text in {"true", "t", "1"}:
        return True
    if text in {"false", "f", "0"}:
        return False
    raise ValueError(f"expected boolean value, got {value!r}")


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


def _optional_int_from_metadata(
    metadata: Mapping[str, object],
    key: str,
) -> int | None:
    if key not in metadata:
        return None
    try:
        return _optional_int(metadata[key])
    except (TypeError, ValueError):
        return None


def _optional_str_from_metadata(
    metadata: Mapping[str, object],
    key: str,
) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    return str(value)


def _snapshot_status(value: object) -> ProviderRuntimeSnapshotStatus:
    text = str(value)
    if text not in {
        "not_configured",
        "key_configured",
        "ok",
        "limited",
        "auth_failed",
        "rate_limited",
        "unavailable",
        "adapter_planned",
    }:
        raise ValueError(f"unsupported provider runtime status: {text}")
    return cast(ProviderRuntimeSnapshotStatus, text)


def _next_action(value: object) -> ProviderRuntimeMonitorNextAction:
    text = str(value)
    if text not in {
        "no_action",
        "configure_runtime_key",
        "review_provider_plan_limit",
        "check_provider_credentials",
        "retry_after_provider_recovery",
        "adapter_not_ready",
    }:
        raise ValueError(f"unsupported provider runtime next action: {text}")
    return cast(ProviderRuntimeMonitorNextAction, text)


def _alert_level(value: object) -> ProviderRuntimeAlertLevel:
    text = str(value)
    if text not in {"ok", "P0", "P1", "P2"}:
        raise ValueError(f"unsupported provider runtime alert level: {text}")
    return cast(ProviderRuntimeAlertLevel, text)


def _incident_status(value: object) -> ProviderRuntimeIncidentStatus:
    text = str(value)
    if text not in {"open", "acknowledged", "resolved", "ignored"}:
        raise ValueError(f"unsupported provider runtime incident status: {text}")
    return cast(ProviderRuntimeIncidentStatus, text)


def _incident_notification_status(
    value: object,
) -> ProviderRuntimeIncidentNotificationStatus:
    text = str(value)
    if text not in {"not_configured", "queued", "sent", "skipped", "failed"}:
        raise ValueError(
            f"unsupported provider runtime incident notification status: {text}"
        )
    return cast(ProviderRuntimeIncidentNotificationStatus, text)
