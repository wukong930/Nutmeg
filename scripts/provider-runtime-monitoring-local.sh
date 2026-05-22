#!/usr/bin/env bash
set -euo pipefail

REMOTE_DIR="${1:-$(pwd)}"
LIVE_PROBE="${NUTMEG_PROVIDER_RUNTIME_LIVE_PROBE:-false}"
RECORD_INCIDENT="${NUTMEG_PROVIDER_RUNTIME_RECORD_INCIDENT:-true}"
INCIDENT_THRESHOLD="${NUTMEG_PROVIDER_RUNTIME_INCIDENT_THRESHOLD:-P1}"
INCIDENT_SOURCE="${NUTMEG_PROVIDER_RUNTIME_INCIDENT_SOURCE:-vps_cron}"
RETENTION_DAYS="${NUTMEG_PROVIDER_RUNTIME_RETENTION_DAYS:-90}"

cd "$REMOTE_DIR"
mkdir -p logs

if [ ! -f .env ]; then
  echo "Nutmeg .env is missing; run deploy-vps first" >&2
  exit 1
fi

ADMIN_TOKEN="$(awk -F= '$1 == "NUTMEG_ADMIN_API_TOKEN" {print $2}' .env | tail -n 1)"
if [ -z "$ADMIN_TOKEN" ]; then
  echo "NUTMEG_ADMIN_API_TOKEN is missing in Nutmeg .env" >&2
  exit 1
fi
source "$REMOTE_DIR/scripts/provider-ops-run-history.sh"
RUN_STARTED_AT="$(nutmeg_provider_ops_started_at_utc)"
nutmeg_provider_ops_install_failure_trap \
  "http://127.0.0.1:18000/api/v1" \
  "$ADMIN_TOKEN" \
  "provider-runtime-monitoring" \
  "$RUN_STARTED_AT" \
  "cron" \
  "$INCIDENT_SOURCE"

python3 - "$ADMIN_TOKEN" "$LIVE_PROBE" "$RECORD_INCIDENT" "$INCIDENT_THRESHOLD" "$INCIDENT_SOURCE" "$RETENTION_DAYS" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime


admin_token = sys.argv[1]
started_at = datetime.now(UTC)
live_probe = sys.argv[2].lower() == "true"
record_incident = sys.argv[3].lower() == "true"
incident_threshold = sys.argv[4]
incident_source = sys.argv[5]
retention_days = int(sys.argv[6])
base_url = "http://127.0.0.1:18000/api/v1"


def safe_text(value: str) -> str:
    return value.replace(admin_token, "[redacted]").strip()[:500]


def fetch(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    command = [
        "curl",
        "-sS",
        "--connect-timeout",
        "15",
        "--max-time",
        "45",
        "-H",
        f"X-Nutmeg-Admin-Token: {admin_token}",
        "-H",
        "X-Nutmeg-Operator: provider-runtime-monitor",
    ]
    if payload is not None:
        command.extend(
            [
                "-H",
                "Content-Type: application/json",
                "-X",
                "POST",
                "--data",
                json.dumps(payload),
            ]
        )
    command.extend(["-w", "\n%{http_code}", f"{base_url}{path}"])
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "provider_runtime_monitoring_request_failed "
            f"path={path} curl_exit={completed.returncode} "
            f"stderr={safe_text(completed.stderr)}"
        )
    response_body, _, status_code = completed.stdout.rpartition("\n")
    if not status_code.isdigit():
        raise SystemExit(
            "provider_runtime_monitoring_request_failed "
            f"path={path} status=unknown body={safe_text(completed.stdout)}"
        )
    if int(status_code) >= 400:
        raise SystemExit(
            "provider_runtime_monitoring_request_failed "
            f"path={path} status={status_code} body={safe_text(response_body)}"
        )
    return json.loads(response_body)


snapshot = fetch(
    "/providers/runtime/monitoring/snapshot",
    {"live_probe": live_probe},
)
monitoring = fetch("/providers/runtime/monitoring?limit=20")
incident: dict[str, object] | None = None
if record_incident:
    incident = fetch(
        "/providers/runtime/monitoring/incidents",
        {
            "source": incident_source,
            "created_by": "provider-runtime-monitor",
            "record_when_alert_level": incident_threshold,
            "metadata_json": {
                "live_probe": live_probe,
                "secret_value_not_exposed": True,
            },
        },
    )
retention = fetch(
    "/providers/runtime/monitoring/incidents/retention",
    {"retention_days": retention_days},
)

summary = monitoring["summary"]
print("provider_runtime_monitoring_snapshot_items", len(snapshot["items"]))
print("provider_runtime_monitoring_latest_items", len(monitoring["items"]))
print("provider_runtime_monitoring_alert_level", monitoring["alert_level"])
print("provider_runtime_monitoring_alerts", len(monitoring["alerts"]))
print("provider_runtime_monitoring_healthy", summary["healthy_count"])
print("provider_runtime_monitoring_degraded", summary["degraded_count"])
print("provider_runtime_monitoring_rate_limited", summary["rate_limited_count"])
print("provider_runtime_monitoring_fallback", summary["fallback_provider_count"])
if incident is not None:
    print("provider_runtime_incident_recorded", str(incident["recorded"]).lower())
    item = incident.get("item")
    if isinstance(item, dict):
        print(
            "provider_runtime_incident_notification_status",
            item.get("notification_status", "unknown"),
        )
print("provider_runtime_incident_retention_days", retention["retention_days"])
print("provider_runtime_incident_retention_deleted", retention["deleted_count"])
completed_at = datetime.now(UTC)
try:
    fetch(
        "/ops/provider-runs",
        {
            "run_name": "provider-runtime-monitoring",
            "run_type": "cron",
            "source": incident_source,
            "status": "success",
            "operator_name": "provider-runtime-monitor",
            "started_at_utc": started_at.isoformat(),
            "completed_at_utc": completed_at.isoformat(),
            "duration_ms": int((completed_at - started_at).total_seconds() * 1000),
            "exit_code": 0,
            "summary_json": {
                "alert_level": monitoring["alert_level"],
                "alerts": len(monitoring["alerts"]),
                "healthy": summary["healthy_count"],
                "degraded": summary["degraded_count"],
                "incident_recorded": incident["recorded"] if incident else False,
                "retention_deleted": retention["deleted_count"],
            },
            "output_excerpt": (
                "provider_runtime_monitoring_alert_level "
                f"{monitoring['alert_level']}"
            ),
            "metadata_json": {
                "live_probe": live_probe,
                "secret_value_not_exposed": True,
            },
        },
    )
except SystemExit as exc:
    print(
        "provider_ops_run_history_record_failed "
        f"run_name=provider-runtime-monitoring error={safe_text(str(exc))}",
        file=sys.stderr,
    )
PY
