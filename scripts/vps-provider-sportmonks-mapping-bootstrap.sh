#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
SOURCE_COMPETITION_ID="${NUTMEG_SPORTMONKS_MAPPING_SOURCE_COMPETITION_ID:-PL}"
CANONICAL_COMPETITION_ID="${NUTMEG_SPORTMONKS_MAPPING_CANONICAL_COMPETITION_ID:-EPL}"
SOURCE_SEASON="${NUTMEG_SPORTMONKS_MAPPING_SOURCE_SEASON:-2025}"
TARGET_COMPETITION_NAME="${NUTMEG_SPORTMONKS_MAPPING_TARGET_COMPETITION_NAME:-Premier League}"
TARGET_COUNTRY_NAME="${NUTMEG_SPORTMONKS_MAPPING_TARGET_COUNTRY_NAME:-England}"
TARGET_SEASON="${NUTMEG_SPORTMONKS_MAPPING_TARGET_SEASON:-$SOURCE_SEASON}"
TARGET_PAYLOAD_B64="$(
  python3 - "$TARGET_COMPETITION_NAME" "$TARGET_COUNTRY_NAME" "$TARGET_SEASON" <<'PY'
from __future__ import annotations

import base64
import json
import sys

print(
    base64.b64encode(
        json.dumps(
            {
                "target_competition_name": sys.argv[1],
                "target_country_name": sys.argv[2],
                "target_season": sys.argv[3],
            },
            separators=(",", ":"),
        ).encode("utf-8")
    ).decode("ascii")
)
PY
)"
SPORTMONKS_COMPETITION_ID="${NUTMEG_SPORTMONKS_MAPPING_COMPETITION_ID:-}"
SPORTMONKS_SEASON_ID="${NUTMEG_SPORTMONKS_MAPPING_SEASON_ID:-}"
SPORTMONKS_COMPETITION_ID_ARG="${SPORTMONKS_COMPETITION_ID:-__missing__}"
SPORTMONKS_SEASON_ID_ARG="${SPORTMONKS_SEASON_ID:-__missing__}"
MAX_PROVIDER_FIXTURES="${NUTMEG_SPORTMONKS_MAPPING_MAX_PROVIDER_FIXTURES:-500}"
AUTO_DISCOVERY="${NUTMEG_SPORTMONKS_MAPPING_AUTO_DISCOVERY:-true}"
COMMIT="${NUTMEG_SPORTMONKS_MAPPING_COMMIT:-false}"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" \
  "$SOURCE_COMPETITION_ID" \
  "$CANONICAL_COMPETITION_ID" \
  "$SOURCE_SEASON" \
  "$TARGET_PAYLOAD_B64" \
  "$SPORTMONKS_COMPETITION_ID_ARG" \
  "$SPORTMONKS_SEASON_ID_ARG" \
  "$MAX_PROVIDER_FIXTURES" \
  "$AUTO_DISCOVERY" \
  "$COMMIT" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"; shift
SOURCE_COMPETITION_ID="$1"; shift
CANONICAL_COMPETITION_ID="$1"; shift
SOURCE_SEASON="$1"; shift
TARGET_PAYLOAD_B64="$1"; shift
SPORTMONKS_COMPETITION_ID="$1"; shift
SPORTMONKS_SEASON_ID="$1"; shift
MAX_PROVIDER_FIXTURES="$1"; shift
AUTO_DISCOVERY="$1"; shift
COMMIT="$1"; shift
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
  "sportmonks-mapping-bootstrap" \
  "$RUN_STARTED_AT"

python3 - \
  "$ADMIN_TOKEN" \
  "$SOURCE_COMPETITION_ID" \
  "$CANONICAL_COMPETITION_ID" \
  "$SOURCE_SEASON" \
  "$TARGET_PAYLOAD_B64" \
  "$SPORTMONKS_COMPETITION_ID" \
  "$SPORTMONKS_SEASON_ID" \
  "$MAX_PROVIDER_FIXTURES" \
  "$AUTO_DISCOVERY" \
  "$COMMIT" <<'PY'
from __future__ import annotations

import base64
import json
import sys
from datetime import UTC, datetime

from scripts.provider_request_helpers import (
    record_provider_ops_run,
    request_json as provider_request_json,
)

admin_token = sys.argv[1]
source_competition_id = sys.argv[2]
canonical_competition_id = sys.argv[3]
source_season = sys.argv[4]
target_payload = json.loads(base64.b64decode(sys.argv[5]).decode("utf-8"))
target_competition_name = str(target_payload["target_competition_name"])
target_country_name = str(target_payload["target_country_name"])
target_season = str(target_payload["target_season"])
sportmonks_competition_id = sys.argv[6]
sportmonks_season_id = sys.argv[7]
max_provider_fixtures = int(sys.argv[8])
auto_discovery = sys.argv[9].lower() in {"1", "true", "yes", "y"}
commit = sys.argv[10].lower() in {"1", "true", "yes", "y"}
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

use_auto_backfill = (
    auto_discovery
    or sportmonks_competition_id == "__missing__"
    or sportmonks_season_id == "__missing__"
)
if use_auto_backfill:
    bootstrap = request_json(
        "/providers/mappings/backfill/sportmonks-fixtures",
        {
            "source_provider_competition_id": source_competition_id,
            "canonical_competition_id": canonical_competition_id,
            "source_season": source_season,
            "target_competition_name": target_competition_name,
            "target_country_name": target_country_name,
            "target_season": target_season,
            "kickoff_tolerance_minutes": 180,
            "min_confidence": 0.82,
            "max_provider_fixtures": max_provider_fixtures,
            "dry_run": not commit,
        },
    )
    backfill = bootstrap["result"]
    if backfill["status"] == "skipped":
        print(
            "sportmonks_mapping_bootstrap_skipped "
            "reason=auto_discovery_missing_recommendation "
            f"dry_run={str(not commit).lower()} "
            f"warnings={len(backfill['warnings'])}"
        )
        completed_at = datetime.now(UTC)
        record_provider_ops_run(
            base_url,
            admin_token=admin_token,
            run_name="sportmonks-mapping-bootstrap",
            status="skipped",
            started_at_utc=started_at,
            completed_at_utc=completed_at,
            duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            summary_json={
                "dry_run": not commit,
                "reason": "auto_discovery_missing_recommendation",
                "warnings": len(backfill["warnings"]),
            },
            output_excerpt="sportmonks_mapping_bootstrap_skipped",
        )
        raise SystemExit(0)
    result = backfill["bootstrap"]
    require(isinstance(result, dict), "SportMonks backfill did not return bootstrap result")
    sportmonks_competition_id = backfill["recommended_competition_id"] or "unknown"
    sportmonks_season_id = backfill["recommended_season_id"] or "unknown"
else:
    bootstrap = request_json(
        "/providers/mappings/bootstrap/sportmonks-fixtures",
        {
            "source_provider_competition_id": source_competition_id,
            "canonical_competition_id": canonical_competition_id,
            "source_season": source_season,
            "sportmonks_competition_id": sportmonks_competition_id,
            "sportmonks_season": sportmonks_season_id,
            "kickoff_tolerance_minutes": 180,
            "min_confidence": 0.82,
            "max_provider_fixtures": max_provider_fixtures,
            "dry_run": not commit,
        },
    )
    result = bootstrap["result"]
matched_count = int(result["matched_count"])
persisted_count = int(result["persisted_count"])
ambiguous_count = int(result["ambiguous_count"])
if commit:
    require(matched_count >= 1, "SportMonks fixture bootstrap found no matches")
    require(persisted_count >= 1, "SportMonks fixture bootstrap persisted no mappings")
    require(ambiguous_count == 0, "SportMonks fixture bootstrap produced ambiguous matches")

review_warnings = 0
if commit:
    review = request_json(
        "/providers/mappings/review",
        {
            "provider": "sportmonks",
            "entity_type": "fixture",
            "dry_run": True,
            "limit": 1000,
        },
    )
    require(
        int(review["result"]["critical_count"]) == 0,
        "SportMonks fixture mapping review found critical issues",
    )
    review_warnings = int(review["result"]["warning_count"])

print(
    "sportmonks_mapping_bootstrap_ok "
    f"mode={'auto' if use_auto_backfill else 'explicit'} "
    f"dry_run={str(not commit).lower()} "
    f"fixtures={fixture_count} "
    f"competition_id={sportmonks_competition_id} "
    f"season_id={sportmonks_season_id} "
    f"provider_fixtures={result['provider_fixture_count']} "
    f"provider_source={result['provider_fixture_source']} "
    f"matched={matched_count} "
    f"persisted={persisted_count} "
    f"ambiguous={ambiguous_count} "
    f"unmatched_canonical={result['unmatched_canonical_fixture_count']} "
    f"warnings={len(result['warnings'])} "
    f"review_warnings={review_warnings}"
)
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="sportmonks-mapping-bootstrap",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "dry_run": not commit,
        "fixtures": fixture_count,
        "matched": matched_count,
        "persisted": persisted_count,
        "ambiguous": ambiguous_count,
        "auto_discovery": use_auto_backfill,
        "competition_id": sportmonks_competition_id,
        "season_id": sportmonks_season_id,
        "warnings": len(result["warnings"]),
    },
    output_excerpt="sportmonks_mapping_bootstrap_ok",
)
PY
REMOTE
