#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
COMPETITION_ID="${NUTMEG_FALLBACK_ODDS_PROBE_COMPETITION_ID:-EPL}"
PRIMARY_PROVIDER="${NUTMEG_FALLBACK_ODDS_PROBE_PRIMARY_PROVIDER:-the-odds-api}"
WINDOW_DAYS="${NUTMEG_FALLBACK_ODDS_PROBE_WINDOW_DAYS:-90}"
MAX_SNAPSHOT_LAG_HOURS="${NUTMEG_FALLBACK_ODDS_PROBE_MAX_SNAPSHOT_LAG_HOURS:-168}"
AS_OF_DAYS_AHEAD="${NUTMEG_FALLBACK_ODDS_PROBE_AS_OF_DAYS_AHEAD:-90}"
LIMIT="${NUTMEG_FALLBACK_ODDS_PROBE_LIMIT:-50}"
LIVE_PROVIDER_PROBE="${NUTMEG_FALLBACK_ODDS_PROBE_LIVE:-false}"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" \
  "$COMPETITION_ID" \
  "$PRIMARY_PROVIDER" \
  "$WINDOW_DAYS" \
  "$MAX_SNAPSHOT_LAG_HOURS" \
  "$AS_OF_DAYS_AHEAD" \
  "$LIMIT" \
  "$LIVE_PROVIDER_PROBE" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
COMPETITION_ID="$2"
PRIMARY_PROVIDER="$3"
WINDOW_DAYS="$4"
MAX_SNAPSHOT_LAG_HOURS="$5"
AS_OF_DAYS_AHEAD="$6"
LIMIT="$7"
LIVE_PROVIDER_PROBE="$8"
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
  "provider-fallback-odds-probe" \
  "$RUN_STARTED_AT"

python3 - \
  "$ADMIN_TOKEN" \
  "$COMPETITION_ID" \
  "$PRIMARY_PROVIDER" \
  "$WINDOW_DAYS" \
  "$MAX_SNAPSHOT_LAG_HOURS" \
  "$AS_OF_DAYS_AHEAD" \
  "$LIMIT" \
  "$LIVE_PROVIDER_PROBE" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sys

from scripts.provider_request_helpers import record_provider_ops_run, request_json

admin_token = sys.argv[1]
competition_id = sys.argv[2]
primary_provider = sys.argv[3]
window_days = int(sys.argv[4])
max_snapshot_lag_hours = int(sys.argv[5])
as_of_days_ahead = int(sys.argv[6])
limit = int(sys.argv[7])
live_provider_probe = sys.argv[8].strip().lower() in {"1", "true", "yes"}
base_url = "http://127.0.0.1:18000/api/v1"
started_at = datetime.now(UTC)
as_of_time = (datetime.now(UTC) + timedelta(days=as_of_days_ahead)).isoformat()

payload = {
    "competition_id": competition_id,
    "primary_provider": primary_provider,
    "window_days": window_days,
    "max_snapshot_lag_hours": max_snapshot_lag_hours,
    "limit": limit,
    "as_of_time_utc": as_of_time,
    "live_provider_probe": live_provider_probe,
}
response = request_json(
    base_url,
    "/providers/odds/fallback-probe/sportmonks",
    admin_token=admin_token,
    payload=payload,
    timeout_seconds=120,
)
result = response["result"]
print(
    "sportmonks_fallback_odds_probe "
    f"competition={result['competition_id']} "
    f"primary={result['primary_provider']} "
    f"fallback={result['fallback_provider']} "
    f"live={str(result['live_provider_probe']).lower()} "
    f"key_configured={str(result['provider_key_configured']).lower()} "
    f"checked={result['checked_gap_count']} "
    f"event_unavailable={result['provider_event_unavailable_count']} "
    f"mapped={result['mapped_fallback_count']} "
    f"probed={result['probed_fixture_count']} "
    f"recoverable={result['recoverable_fixture_count']} "
    f"normalized_odds={result['normalized_odds_count']} "
    f"bookmakers={result['bookmaker_count']}"
)
for item in result["items"][:10]:
    warnings = ",".join(item["warnings"]) or "none"
    market_types = ",".join(item["market_types"]) or "none"
    print(
        "fallback_probe_item "
        f"fixture={item['fixture_id']} "
        f"teams={item['home_team_name']}vs{item['away_team_name']} "
        f"status={item['status']} "
        f"mapping={item['provider_fixture_id'] or 'missing'} "
        f"recoverable={str(item['can_recover_gap']).lower()} "
        f"odds={item['normalized_odds_count']} "
        f"markets={market_types} "
        f"warnings={warnings} "
        f"action={item['recommended_action']}"
    )
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="provider-fallback-odds-probe",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "competition": result["competition_id"],
        "primary": result["primary_provider"],
        "fallback": result["fallback_provider"],
        "checked": result["checked_gap_count"],
        "mapped": result["mapped_fallback_count"],
        "recoverable": result["recoverable_fixture_count"],
    },
    output_excerpt="sportmonks_fallback_odds_probe",
)
PY
REMOTE
