#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
MAX_PROVIDER_EVENTS="${NUTMEG_MAPPING_BOOTSTRAP_MAX_PROVIDER_EVENTS:-500}"

ssh -o BatchMode=yes "$TARGET" bash -s -- "$REMOTE_DIR" "$MAX_PROVIDER_EVENTS" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
MAX_PROVIDER_EVENTS="$2"
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
  "provider-mapping-bootstrap" \
  "$RUN_STARTED_AT"

python3 - "$ADMIN_TOKEN" "$MAX_PROVIDER_EVENTS" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from scripts.provider_request_helpers import (
    record_provider_ops_run,
    request_json as provider_request_json,
)

admin_token = sys.argv[1]
max_provider_events = int(sys.argv[2])
base_url = "http://127.0.0.1:18000/api/v1"
started_at = datetime.now(UTC)


def request_json(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return provider_request_json(
        base_url,
        path,
        admin_token=admin_token,
        payload=payload,
        timeout_seconds=90,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


fixture_sync = request_json(
    "/providers/football-data.org/sync/fixtures",
    {
        "provider_competition_id": "PL",
        "canonical_competition_id": "EPL",
        "season": "2025",
        "dry_run": False,
    },
)
canonical_write = fixture_sync.get("canonical_write") or {}
fixture_count = int(canonical_write.get("fixtures") or 0)
require(fixture_count >= 1, "football-data.org fixture commit did not persist fixtures")

bootstrap = request_json(
    "/providers/mappings/bootstrap/the-odds-api-fixtures",
    {
        "provider_competition_id": "PL",
        "canonical_competition_id": "EPL",
        "season": "2025",
        "sport_key": "soccer_epl",
        "regions": "eu",
        "markets": "h2h",
        "kickoff_tolerance_minutes": 180,
        "min_confidence": 0.82,
        "max_provider_events": max_provider_events,
        "dry_run": False,
    },
)
bootstrap_result = bootstrap["result"]
matched_count = int(bootstrap_result["matched_count"])
persisted_count = int(bootstrap_result["persisted_count"])
require(matched_count >= 1, "The Odds API fixture bootstrap found no matches")
require(persisted_count >= 1, "The Odds API fixture bootstrap persisted no mappings")
require(
    int(bootstrap_result["ambiguous_count"]) == 0,
    "The Odds API fixture bootstrap produced ambiguous matches",
)

mappings = request_json(
    "/providers/mappings?provider=the-odds-api&entity_type=fixture&limit=50"
)
summary_rows = {
    (item["provider"], item["entity_type"]): item
    for item in mappings.get("summary", [])
}
summary = summary_rows.get(("the-odds-api", "fixture"))
require(summary is not None, "The Odds API fixture mapping summary is missing")
require(
    int(summary["mapping_count"]) >= persisted_count,
    "The Odds API fixture mapping summary did not include persisted mappings",
)

review = request_json(
    "/providers/mappings/review",
    {
        "provider": "the-odds-api",
        "entity_type": "fixture",
        "dry_run": True,
        "limit": 1000,
    },
)
require(
    int(review["result"]["critical_count"]) == 0,
    "The Odds API fixture mapping review found critical issues",
)

print(
    "provider_mapping_bootstrap_ok "
    f"fixtures={fixture_count} "
    f"provider_fixtures={bootstrap_result['provider_fixture_count']} "
    f"provider_source={bootstrap_result['provider_fixture_source']} "
    f"matched={matched_count} "
    f"persisted={persisted_count} "
    f"unmatched_canonical={bootstrap_result['unmatched_canonical_fixture_count']} "
    f"review_warnings={review['result']['warning_count']}"
)
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="provider-mapping-bootstrap",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "fixtures": fixture_count,
        "matched": matched_count,
        "persisted": persisted_count,
        "review_warnings": review["result"]["warning_count"],
    },
    output_excerpt="provider_mapping_bootstrap_ok",
)
PY
REMOTE
