#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
TARGET_COMPETITION_NAME="${NUTMEG_SPORTMONKS_DISCOVERY_COMPETITION:-Premier League}"
TARGET_COUNTRY_NAME="${NUTMEG_SPORTMONKS_DISCOVERY_COUNTRY:-England}"
TARGET_SEASON="${NUTMEG_SPORTMONKS_DISCOVERY_SEASON:-2025}"
MIN_COMPETITION_SCORE="${NUTMEG_SPORTMONKS_DISCOVERY_MIN_COMPETITION_SCORE:-0.75}"
MAX_COMPETITION_CANDIDATES="${NUTMEG_SPORTMONKS_DISCOVERY_MAX_COMPETITIONS:-5}"
MAX_SEASON_CANDIDATES="${NUTMEG_SPORTMONKS_DISCOVERY_MAX_SEASONS:-6}"
DISCOVERY_PAYLOAD_B64="$(
  python3 - "$TARGET_COMPETITION_NAME" "$TARGET_COUNTRY_NAME" "$TARGET_SEASON" \
    "$MIN_COMPETITION_SCORE" "$MAX_COMPETITION_CANDIDATES" \
    "$MAX_SEASON_CANDIDATES" <<'PY' | base64 | tr -d '\n'
from __future__ import annotations

import json
import sys

print(
    json.dumps(
        {
            "target_competition_name": sys.argv[1],
            "target_country_name": sys.argv[2],
            "target_season": sys.argv[3],
            "min_competition_score": float(sys.argv[4]),
            "max_competition_candidates": int(sys.argv[5]),
            "max_season_candidates": int(sys.argv[6]),
        }
    )
)
PY
)"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" \
  "$DISCOVERY_PAYLOAD_B64" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
DISCOVERY_PAYLOAD_B64="$2"
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
  "sportmonks-discovery" \
  "$RUN_STARTED_AT"

python3 - \
  "$ADMIN_TOKEN" \
  "$DISCOVERY_PAYLOAD_B64" <<'PY'
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
discovery_payload = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8"))
started_at = datetime.now(UTC)
target_competition_name = str(discovery_payload["target_competition_name"])
target_country_name = str(discovery_payload["target_country_name"])
target_season = str(discovery_payload["target_season"])
max_competition_candidates = int(discovery_payload["max_competition_candidates"])
base_url = "http://127.0.0.1:18000/api/v1"


def request_json(path: str, payload: dict[str, object]) -> dict[str, object]:
    return provider_request_json(
        base_url,
        path,
        admin_token=admin_token,
        payload=payload,
        timeout_seconds=120,
    )


payload = request_json(
    "/providers/sportmonks/discovery/competitions",
    discovery_payload,
)
result = payload["result"]
recommended_competition = result.get("recommended_competition") or {}
recommended_season = result.get("recommended_season") or {}
competition_id = recommended_competition.get("provider_competition_id") or "none"
season_id = recommended_season.get("provider_season_id") or "none"
competition_score = recommended_competition.get("score")
season_score = recommended_season.get("score")

print(
    "sportmonks_competition_discovery_ok "
    f"target={target_competition_name!r} "
    f"country={target_country_name!r} "
    f"season={target_season!r} "
    f"min_score={result['min_competition_score']} "
    f"checked={result['checked_competition_count']} "
    f"candidates={result['candidate_count']} "
    f"recommended_competition_id={competition_id} "
    f"recommended_season_id={season_id} "
    f"competition_score={competition_score} "
    f"season_score={season_score} "
    f"warnings={len(result['warnings'])}"
)
if competition_id != "none" and season_id != "none":
    print(
        "sportmonks_mapping_env "
        f"NUTMEG_SPORTMONKS_MAPPING_COMPETITION_ID={competition_id} "
        f"NUTMEG_SPORTMONKS_MAPPING_SEASON_ID={season_id}"
    )

for candidate in result.get("candidates", [])[:max_competition_candidates]:
    season = candidate.get("recommended_season") or {}
    print(
        "sportmonks_candidate "
        f"competition_id={candidate.get('provider_competition_id')} "
        f"name={candidate.get('name')!r} "
        f"country={candidate.get('country_name')!r} "
        f"score={candidate.get('score')} "
        f"season_id={season.get('provider_season_id', 'none')} "
        f"season_name={season.get('name', 'none')!r} "
        f"season_score={season.get('score', 'none')}"
    )
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="sportmonks-discovery",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "checked": result["checked_competition_count"],
        "candidates": result["candidate_count"],
        "recommended_competition_id": competition_id,
        "recommended_season_id": season_id,
        "warnings": len(result["warnings"]),
    },
    output_excerpt="sportmonks_competition_discovery_ok",
)
PY
REMOTE
