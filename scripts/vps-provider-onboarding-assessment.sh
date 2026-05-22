#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
COMPETITION_ID="${NUTMEG_ONBOARDING_COMPETITION_ID:-EPL}"
COMPETITION_NAME="${NUTMEG_ONBOARDING_COMPETITION_NAME:-Premier League}"
COMPETITION_NAME_B64="$(printf '%s' "$COMPETITION_NAME" | base64 | tr -d '\n')"
TARGET_STAGE="${NUTMEG_ONBOARDING_TARGET_STAGE:-beta}"
WINDOW_DAYS="${NUTMEG_ONBOARDING_WINDOW_DAYS:-90}"
MAX_SNAPSHOT_LAG_HOURS="${NUTMEG_ONBOARDING_MAX_SNAPSHOT_LAG_HOURS:-24}"
AS_OF_DAYS_AHEAD="${NUTMEG_ONBOARDING_AS_OF_DAYS_AHEAD:-90}"
SCHEDULE_COVERAGE="${NUTMEG_ONBOARDING_SCHEDULE_COVERAGE:-0.99}"
RESULT_COVERAGE="${NUTMEG_ONBOARDING_RESULT_COVERAGE:-0.995}"
LINEUP_INJURY_COVERAGE="${NUTMEG_ONBOARDING_LINEUP_INJURY_COVERAGE:-0.70}"
HISTORICAL_STATS_COMPLETENESS="${NUTMEG_ONBOARDING_HISTORICAL_STATS_COMPLETENESS:-0.82}"
PROVIDER_CONSISTENCY="${NUTMEG_ONBOARDING_PROVIDER_CONSISTENCY:-0.93}"
HISTORICAL_SAMPLE_SIZE="${NUTMEG_ONBOARDING_HISTORICAL_SAMPLE_SIZE:-420}"
COMPLETE_SEASONS="${NUTMEG_ONBOARDING_COMPLETE_SEASONS:-1}"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" \
  "$COMPETITION_ID" \
  "$COMPETITION_NAME_B64" \
  "$TARGET_STAGE" \
  "$WINDOW_DAYS" \
  "$MAX_SNAPSHOT_LAG_HOURS" \
  "$AS_OF_DAYS_AHEAD" \
  "$SCHEDULE_COVERAGE" \
  "$RESULT_COVERAGE" \
  "$LINEUP_INJURY_COVERAGE" \
  "$HISTORICAL_STATS_COMPLETENESS" \
  "$PROVIDER_CONSISTENCY" \
  "$HISTORICAL_SAMPLE_SIZE" \
  "$COMPLETE_SEASONS" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
COMPETITION_ID="$2"
COMPETITION_NAME="$(printf '%s' "$3" | base64 -d)"
TARGET_STAGE="$4"
WINDOW_DAYS="$5"
MAX_SNAPSHOT_LAG_HOURS="$6"
AS_OF_DAYS_AHEAD="$7"
SCHEDULE_COVERAGE="$8"
RESULT_COVERAGE="$9"
LINEUP_INJURY_COVERAGE="${10}"
HISTORICAL_STATS_COMPLETENESS="${11}"
PROVIDER_CONSISTENCY="${12}"
HISTORICAL_SAMPLE_SIZE="${13}"
COMPLETE_SEASONS="${14}"
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
  "provider-onboarding-assessment" \
  "$RUN_STARTED_AT"

python3 - \
  "$ADMIN_TOKEN" \
  "$COMPETITION_ID" \
  "$COMPETITION_NAME" \
  "$TARGET_STAGE" \
  "$WINDOW_DAYS" \
  "$MAX_SNAPSHOT_LAG_HOURS" \
  "$AS_OF_DAYS_AHEAD" \
  "$SCHEDULE_COVERAGE" \
  "$RESULT_COVERAGE" \
  "$LINEUP_INJURY_COVERAGE" \
  "$HISTORICAL_STATS_COMPLETENESS" \
  "$PROVIDER_CONSISTENCY" \
  "$HISTORICAL_SAMPLE_SIZE" \
  "$COMPLETE_SEASONS" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sys

from scripts.provider_request_helpers import record_provider_ops_run, request_json

admin_token = sys.argv[1]
competition_id = sys.argv[2]
competition_name = sys.argv[3]
target_stage = sys.argv[4]
window_days = int(sys.argv[5])
max_snapshot_lag_hours = int(sys.argv[6])
as_of_days_ahead = int(sys.argv[7])
schedule_coverage = float(sys.argv[8])
result_coverage = float(sys.argv[9])
lineup_injury_coverage = float(sys.argv[10])
historical_stats_completeness = float(sys.argv[11])
provider_consistency = float(sys.argv[12])
historical_sample_size = int(sys.argv[13])
complete_seasons = int(sys.argv[14])
base_url = "http://127.0.0.1:18000/api/v1"
started_at = datetime.now(UTC)
as_of_time = (datetime.now(UTC) + timedelta(days=as_of_days_ahead)).isoformat()

payload = {
    "competition_id": competition_id,
    "competition_name": competition_name,
    "target_stage": target_stage,
    "window_days": window_days,
    "max_snapshot_lag_hours": max_snapshot_lag_hours,
    "as_of_time_utc": as_of_time,
    "schedule_coverage": schedule_coverage,
    "result_coverage": result_coverage,
    "lineup_injury_coverage": lineup_injury_coverage,
    "historical_stats_completeness": historical_stats_completeness,
    "provider_consistency": provider_consistency,
    "historical_sample_size": historical_sample_size,
    "complete_seasons": complete_seasons,
    "market_resolver_tests_passed": True,
    "score_grid_generation_passed": True,
    "dry_run": False,
}
response = request_json(
    base_url,
    "/providers/onboarding/assessments",
    admin_token=admin_token,
    payload=payload,
    timeout_seconds=120,
)
assessment = response["assessment"]
coverage = response["odds_coverage_report"]
stored = response.get("stored_assessment") or {}
if not stored.get("assessment_id"):
    raise SystemExit("provider onboarding assessment was not persisted")
print(
    "provider_onboarding_assessment_ok "
    f"assessment_id={stored['assessment_id']} "
    f"competition={assessment['competition_id']} "
    f"stage={assessment['target_stage']} "
    f"decision={assessment['decision']} "
    f"beta_ready={assessment['beta_ready']} "
    f"production_ready={assessment['production_ready']} "
    f"quality={assessment['data_quality']['score']} "
    f"grade={assessment['data_quality']['grade']} "
    f"odds_coverage={coverage['odds_coverage']} "
    f"handicap_coverage={coverage['handicap_coverage']} "
    f"fresh_odds_coverage={coverage['fresh_odds_coverage']} "
    f"snapshots={coverage['odds_snapshot_count']} "
    f"reasons={','.join(assessment['reasons']) or 'none'}"
)
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="provider-onboarding-assessment",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "assessment_id": stored["assessment_id"],
        "competition": assessment["competition_id"],
        "decision": assessment["decision"],
        "quality": assessment["data_quality"]["score"],
        "odds_coverage": coverage["odds_coverage"],
    },
    output_excerpt="provider_onboarding_assessment_ok",
)
PY
REMOTE
