#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
COMPETITION_ID="${NUTMEG_ODDS_GAP_COMPETITION_ID:-EPL}"
PROVIDER="${NUTMEG_ODDS_GAP_PROVIDER:-the-odds-api}"
WINDOW_DAYS="${NUTMEG_ODDS_GAP_WINDOW_DAYS:-90}"
MAX_SNAPSHOT_LAG_HOURS="${NUTMEG_ODDS_GAP_MAX_SNAPSHOT_LAG_HOURS:-168}"
AS_OF_DAYS_AHEAD="${NUTMEG_ODDS_GAP_AS_OF_DAYS_AHEAD:-90}"
LIMIT="${NUTMEG_ODDS_GAP_LIMIT:-50}"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" \
  "$COMPETITION_ID" \
  "$PROVIDER" \
  "$WINDOW_DAYS" \
  "$MAX_SNAPSHOT_LAG_HOURS" \
  "$AS_OF_DAYS_AHEAD" \
  "$LIMIT" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
COMPETITION_ID="$2"
PROVIDER="$3"
WINDOW_DAYS="$4"
MAX_SNAPSHOT_LAG_HOURS="$5"
AS_OF_DAYS_AHEAD="$6"
LIMIT="$7"
cd "$REMOTE_DIR"

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
  "provider-odds-gap-report" \
  "$RUN_STARTED_AT"

python3 - \
  "$ADMIN_TOKEN" \
  "$COMPETITION_ID" \
  "$PROVIDER" \
  "$WINDOW_DAYS" \
  "$MAX_SNAPSHOT_LAG_HOURS" \
  "$AS_OF_DAYS_AHEAD" \
  "$LIMIT" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
import json
import sys
from datetime import UTC, datetime

from scripts.provider_request_helpers import record_provider_ops_run, request_json

admin_token = sys.argv[1]
competition_id = sys.argv[2]
provider = sys.argv[3]
window_days = int(sys.argv[4])
max_snapshot_lag_hours = int(sys.argv[5])
as_of_days_ahead = int(sys.argv[6])
limit = int(sys.argv[7])
base_url = "http://127.0.0.1:18000/api/v1"
started_at = datetime.now(UTC)
as_of_time = (datetime.now(UTC) + timedelta(days=as_of_days_ahead)).isoformat()
query = urlencode(
    {
        "competition_id": competition_id,
        "provider": provider,
        "window_days": window_days,
        "max_snapshot_lag_hours": max_snapshot_lag_hours,
        "limit": limit,
        "as_of_time_utc": as_of_time,
    }
)
response = request_json(
    base_url,
    f"/providers/odds/gaps?{query}",
    timeout_seconds=120,
)
report = response["report"]
print(
    "provider_odds_gap_report "
    f"competition={report['competition_id']} "
    f"provider={report['provider']} "
    f"fixtures={report['fixture_count']} "
    f"gaps={report['gap_count']} "
    f"no_odds={report['no_odds_count']} "
    f"stale={report['stale_odds_count']} "
    f"event_unavailable={report.get('provider_event_unavailable_count', 0)} "
    f"missing_1x2={report['missing_1x2_count']} "
    f"missing_handicap={report['missing_handicap_count']} "
    f"unmapped={report['unmapped_fixture_count']} "
    f"max_lag_h={report['max_snapshot_lag_hours']}"
)
for item in report["items"][:10]:
    issues = ",".join(item["issue_types"]) or "none"
    mapping = item["provider_event_id"] or "unmapped"
    fallback = ",".join(
        candidate["provider_name"] for candidate in item.get("fallback_candidates", [])
    ) or "none"
    lag = item["latest_snapshot_lag_hours"]
    lag_label = "N/A" if lag is None else f"{float(lag):.1f}h"
    print(
        "gap_item "
        f"fixture={item['fixture_id']} "
        f"kickoff={item['kickoff_time_utc']} "
        f"teams={item['home_team_name']}vs{item['away_team_name']} "
        f"issues={issues} "
        f"mapping={mapping} "
        f"snapshots={item['odds_snapshot_count']} "
        f"lag={lag_label} "
        f"fallback={fallback} "
        f"action={item['recommended_action']}"
    )
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="provider-odds-gap-report",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "competition": report["competition_id"],
        "provider": report["provider"],
        "fixtures": report["fixture_count"],
        "gaps": report["gap_count"],
        "no_odds": report["no_odds_count"],
        "stale": report["stale_odds_count"],
        "unmapped": report["unmapped_fixture_count"],
    },
    output_excerpt="provider_odds_gap_report",
)
PY
REMOTE
