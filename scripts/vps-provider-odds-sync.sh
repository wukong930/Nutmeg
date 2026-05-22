#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
MAX_MAPPINGS="${NUTMEG_ODDS_SYNC_MAX_MAPPINGS:-50}"
APPROVAL_NOTE="${NUTMEG_ODDS_SYNC_APPROVAL_NOTE:-operator approved mapped odds commit via make provider-odds-sync-vps}"

ssh -o BatchMode=yes "$TARGET" bash -s -- "$REMOTE_DIR" "$MAX_MAPPINGS" "$APPROVAL_NOTE" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
MAX_MAPPINGS="$2"
APPROVAL_NOTE="$3"
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
  "provider-odds-sync" \
  "$RUN_STARTED_AT"

python3 - "$ADMIN_TOKEN" "$MAX_MAPPINGS" "$APPROVAL_NOTE" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from scripts.provider_request_helpers import (
    record_provider_ops_run,
    request_json as provider_request_json,
)

admin_token = sys.argv[1]
max_mappings = int(sys.argv[2])
approval_note = sys.argv[3]
base_url = "http://127.0.0.1:18000/api/v1"
started_at = datetime.now(UTC)


def request_json(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return provider_request_json(
        base_url,
        path,
        admin_token=admin_token,
        payload=payload,
        timeout_seconds=120,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


response = request_json(
    "/providers/the-odds-api/sync/mapped-event-odds",
    {
        "canonical_competition_id": "EPL",
        "sport_key": "soccer_epl",
        "regions": "eu",
        "markets": "h2h,spreads",
        "min_mapping_confidence": 0.82,
        "max_mappings": max_mappings,
        "max_snapshot_lag_hours": 24,
        "include_coverage": True,
        "dry_run": False,
        "operator_approved": True,
        "operator_approval_note": approval_note[:500],
    },
)
result = response["result"]
require(int(result["mapping_count"]) >= 1, "no The Odds API fixture mappings available")
require(int(result["fetched_event_count"]) >= 1, "The Odds API returned no mapped events")
require(int(result["normalized_odds_count"]) >= 1, "no odds were normalized")
require(int(result["odds_snapshot_count"]) >= 1, "no odds snapshots were persisted")
require(
    "1x2" in result["market_types"],
    "1X2 market odds were not present in the mapped odds sync",
)

coverage = response.get("coverage") or {}
print(
    "provider_odds_sync_ok "
    f"mappings={result['mapping_count']} "
    f"fetched_events={result['fetched_event_count']} "
    f"synced_events={result['synced_event_count']} "
    f"normalized_odds={result['normalized_odds_count']} "
    f"persisted_snapshots={result['odds_snapshot_count']} "
    f"inserted_snapshots={result['inserted_snapshot_count']} "
    f"updated_snapshots={result['updated_snapshot_count']} "
    f"coverage_snapshots={coverage.get('odds_snapshot_count', 0)} "
    f"coverage_1x2={coverage.get('one_x_two_coverage', 0)} "
    f"coverage_handicap={coverage.get('handicap_coverage', 0)}"
)
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="provider-odds-sync",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "mappings": result["mapping_count"],
        "fetched_events": result["fetched_event_count"],
        "normalized_odds": result["normalized_odds_count"],
        "persisted_snapshots": result["odds_snapshot_count"],
    },
    output_excerpt="provider_odds_sync_ok",
)
PY
REMOTE
