#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
SOURCE_COMPETITION_ID="${NUTMEG_API_FOOTBALL_MAPPING_SOURCE_COMPETITION_ID:-PL}"
CANONICAL_COMPETITION_ID="${NUTMEG_API_FOOTBALL_MAPPING_CANONICAL_COMPETITION_ID:-EPL}"
SOURCE_SEASON="${NUTMEG_API_FOOTBALL_MAPPING_SOURCE_SEASON:-2025}"
API_FOOTBALL_LEAGUE_ID="${NUTMEG_API_FOOTBALL_MAPPING_LEAGUE_ID:-39}"
API_FOOTBALL_SEASON="${NUTMEG_API_FOOTBALL_MAPPING_SEASON:-2025}"
MAX_PROVIDER_FIXTURES="${NUTMEG_API_FOOTBALL_MAPPING_MAX_PROVIDER_FIXTURES:-500}"
COMMIT="${NUTMEG_API_FOOTBALL_MAPPING_COMMIT:-false}"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" \
  "$SOURCE_COMPETITION_ID" \
  "$CANONICAL_COMPETITION_ID" \
  "$SOURCE_SEASON" \
  "$API_FOOTBALL_LEAGUE_ID" \
  "$API_FOOTBALL_SEASON" \
  "$MAX_PROVIDER_FIXTURES" \
  "$COMMIT" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
SOURCE_COMPETITION_ID="$2"
CANONICAL_COMPETITION_ID="$3"
SOURCE_SEASON="$4"
API_FOOTBALL_LEAGUE_ID="$5"
API_FOOTBALL_SEASON="$6"
MAX_PROVIDER_FIXTURES="$7"
COMMIT="$8"
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
  "api-football-mapping-bootstrap" \
  "$RUN_STARTED_AT"

python3 - \
  "$ADMIN_TOKEN" \
  "$SOURCE_COMPETITION_ID" \
  "$CANONICAL_COMPETITION_ID" \
  "$SOURCE_SEASON" \
  "$API_FOOTBALL_LEAGUE_ID" \
  "$API_FOOTBALL_SEASON" \
  "$MAX_PROVIDER_FIXTURES" \
  "$COMMIT" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from scripts.provider_request_helpers import (
    record_provider_ops_run,
    request_json as provider_request_json,
    request_json_with_status as provider_request_json_with_status,
)

admin_token = sys.argv[1]
source_competition_id = sys.argv[2]
canonical_competition_id = sys.argv[3]
source_season = sys.argv[4]
api_football_league_id = sys.argv[5]
api_football_season = sys.argv[6]
max_provider_fixtures = int(sys.argv[7])
commit = sys.argv[8].lower() in {"1", "true", "yes", "y"}
base_url = "http://127.0.0.1:18000/api/v1"
started_at = datetime.now(UTC)


def request_json_with_status(
    path: str,
    payload: dict[str, object] | None = None,
) -> tuple[dict[str, object], int]:
    return provider_request_json_with_status(
        base_url,
        path,
        admin_token=admin_token,
        payload=payload,
        timeout_seconds=120,
    )


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


fixture_count = 0
if commit:
    fixture_sync = request_json(
        "/providers/football-data.org/sync/fixtures",
        {
            "provider_competition_id": source_competition_id,
            "canonical_competition_id": canonical_competition_id,
            "season": source_season,
            "dry_run": False,
        },
    )
    canonical_write = fixture_sync.get("canonical_write") or {}
    fixture_count = int(canonical_write.get("fixtures") or 0)
    require(fixture_count >= 1, "football-data.org fixture commit did not persist fixtures")

bootstrap, bootstrap_status = request_json_with_status(
    "/providers/mappings/bootstrap/api-football-fixtures",
    {
        "source_provider_competition_id": source_competition_id,
        "canonical_competition_id": canonical_competition_id,
        "source_season": source_season,
        "api_football_league_id": api_football_league_id,
        "api_football_season": api_football_season,
        "kickoff_tolerance_minutes": 180,
        "min_confidence": 0.82,
        "max_provider_fixtures": max_provider_fixtures,
        "dry_run": not commit,
    },
)
if bootstrap_status >= 400:
    print(
        "api_football_mapping_bootstrap_skipped "
        f"reason=provider_unavailable_or_plan_limited "
        f"status={bootstrap_status} "
        f"dry_run={str(not commit).lower()}"
    )
    completed_at = datetime.now(UTC)
    record_provider_ops_run(
        base_url,
        admin_token=admin_token,
        run_name="api-football-mapping-bootstrap",
        status="skipped",
        started_at_utc=started_at,
        completed_at_utc=completed_at,
        duration_ms=int((completed_at - started_at).total_seconds() * 1000),
        summary_json={
            "dry_run": not commit,
            "status": bootstrap_status,
            "reason": "provider_unavailable_or_plan_limited",
        },
        output_excerpt="api_football_mapping_bootstrap_skipped",
    )
    raise SystemExit(0)

result = bootstrap["result"]
matched_count = int(result["matched_count"])
persisted_count = int(result["persisted_count"])
ambiguous_count = int(result["ambiguous_count"])
if commit:
    require(matched_count >= 1, "API-Football fixture bootstrap found no matches")
    require(persisted_count >= 1, "API-Football fixture bootstrap persisted no mappings")
    require(ambiguous_count == 0, "API-Football fixture bootstrap produced ambiguous matches")

print(
    "api_football_mapping_bootstrap_ok "
    f"dry_run={str(not commit).lower()} "
    f"fixtures={fixture_count} "
    f"provider_fixtures={result['provider_fixture_count']} "
    f"provider_source={result['provider_fixture_source']} "
    f"matched={matched_count} "
    f"persisted={persisted_count} "
    f"ambiguous={ambiguous_count} "
    f"unmatched_canonical={result['unmatched_canonical_fixture_count']} "
    f"warnings={len(result['warnings'])}"
)
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="api-football-mapping-bootstrap",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "dry_run": not commit,
        "fixtures": fixture_count,
        "matched": matched_count,
        "persisted": persisted_count,
        "ambiguous": ambiguous_count,
        "warnings": len(result["warnings"]),
    },
    output_excerpt="api_football_mapping_bootstrap_ok",
)
PY
REMOTE
