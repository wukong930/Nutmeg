#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"

ssh -o BatchMode=yes "$TARGET" bash -s -- "$REMOTE_DIR" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
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
  "provider-sync-dry-run" \
  "$RUN_STARTED_AT"

python3 - "$ADMIN_TOKEN" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from scripts.provider_request_helpers import record_provider_ops_run, request_json

admin_token = sys.argv[1]
base_url = "http://127.0.0.1:18000/api/v1"
started_at = datetime.now(UTC)


def fetch_json(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return request_json(
        base_url,
        path,
        admin_token=admin_token,
        payload=payload,
        timeout_seconds=45,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


templates = fetch_json("/ops/provider-sync/templates?limit=50")
credentials = fetch_json("/providers/runtime/credentials")
key_checklist = fetch_json("/providers/runtime/api-key-checklist")
live_probes = fetch_json("/providers/runtime/probes?live=true")
checklist_rows = {
    item["provider_name"]: item for item in key_checklist.get("items", [])
}
require(
    checklist_rows["football-data.org"]["free_tier_fit"] == "good_for_first_dry_run",
    "football-data.org free key checklist is missing",
)
require(
    checklist_rows["the-odds-api"]["free_tier_fit"] == "limited_for_soccer",
    "The Odds API soccer limitation marker is missing",
)
credential_rows = {
    item["provider_name"]: item for item in credentials.get("items", [])
}
probe_rows = {
    item["provider_name"]: item for item in live_probes.get("items", [])
}
for provider_name in ("football-data.org", "the-odds-api", "sportmonks"):
    row = credential_rows.get(provider_name)
    require(row is not None, f"{provider_name} runtime credential row is missing")
    require(
        row["dry_run_mode"] in {"mock_sample", "real_provider"},
        f"{provider_name} dry-run mode is not executable",
    )
    require(
        row["commit_mode"] in {"ready", "blocked"},
        f"{provider_name} commit mode is invalid",
    )
    if row["key_configured"]:
        probe = probe_rows.get(provider_name)
        require(probe is not None, f"{provider_name} live probe row is missing")
        require(
            probe["status"] == "ok",
            f"{provider_name} live probe failed with status={probe['status']}",
        )

api_football_checklist = checklist_rows.get("api-football")
require(api_football_checklist is not None, "API-Football checklist row is missing")
if api_football_checklist["key_configured"]:
    api_football_probe = probe_rows.get("api-football")
    require(api_football_probe is not None, "API-Football probe row is missing")
    require(
        api_football_probe["status"] in {"ok", "limited"},
        f"API-Football live probe failed with status={api_football_probe['status']}",
    )

seed_template = next(
    (
        item
        for item in templates.get("items", [])
        if item.get("template_name") == "VPS EPL explicit-ID dry-run"
    ),
    None,
)
require(seed_template is not None, "seed provider sync template is missing")

football_data_real_provider = bool(
    credential_rows["football-data.org"]["key_configured"]
)

payload: dict[str, object] = {
    "dry_run": True,
    "fixture_sync": {
        "provider_competition_id": "PL",
        "canonical_competition_id": "EPL",
        "season": "2025",
    },
    "odds_syncs": [],
    "availability_syncs": [],
    "run_conflict_detection": False,
    "conflict_observation_lookback_hours": 168,
    "conflict_limit": 1000,
    "operator_approved": True,
    "operator_approval_note": (
        "VPS real football-data dry-run with live provider probes"
        if football_data_real_provider
        else "VPS seeded mock dry-run exercise"
    ),
    "provider_sync_workflow_template_id": seed_template[
        "provider_sync_workflow_template_id"
    ],
}

if not football_data_real_provider:
    payload["odds_syncs"] = [
        {
            "sport_key": "soccer_epl",
            "provider_event_id": "event-id",
            "canonical_fixture_id": "fd_fixture_330299",
            "regions": "eu",
            "markets": "h2h,spreads",
        }
    ]
    payload["availability_syncs"] = [
        {
            "provider_fixture_id": "sportmonks-fixture-id",
            "canonical_fixture_id": "fd_fixture_330299",
            "team_mappings": [
                {"provider_team_id": "57", "canonical_team_id": "fd_team_57"},
                {"provider_team_id": "64", "canonical_team_id": "fd_team_64"},
            ],
        }
    ]
    payload["run_conflict_detection"] = True

response = fetch_json("/ops/provider-sync/run", payload)
result = response["result"]
warnings = result.get("warnings", [])
require(result["dry_run"] is True, "workflow was not a dry-run")
require(result["fixture_count"] >= 1, "fixture dry-run sample did not normalize")
if football_data_real_provider:
    require(
        not any("mock_dry_run_sample_used:no_api_key" in warning for warning in warnings),
        "real provider dry-run unexpectedly used mock samples",
    )
else:
    require(result["odds_snapshot_count"] >= 1, "odds dry-run sample did not normalize")
    require(
        result["availability_snapshot_count"] >= 1,
        "availability dry-run sample did not normalize",
    )
    require(
        "fd_fixture_330299" in result["canonical_fixture_ids"],
        "canonical fixture id was not recorded in workflow summary",
    )
    require(
        any("mock_dry_run_sample_used:no_api_key" in warning for warning in warnings),
        "mock dry-run warning marker is missing",
    )

approvals = fetch_json("/ops/provider-sync/approvals?limit=10")
approval_ids = [
    item["provider_sync_workflow_approval_id"]
    for item in approvals.get("items", [])
    if item.get("provider_sync_workflow_run_id")
    == result["provider_sync_workflow_run_id"]
]
require(approval_ids, "operator approval was not linked to the workflow run")

mode = "real_provider_fixture_probe" if football_data_real_provider else "mock_sample"
print(
    "provider_sync_dry_run_ok "
    f"mode={mode} "
    f"run_id={result['provider_sync_workflow_run_id']} "
    f"approval_id={approval_ids[0]} "
    f"fixtures={result['fixture_count']} "
    f"odds={result['odds_snapshot_count']} "
    f"availability={result['availability_snapshot_count']}"
)
completed_at = datetime.now(UTC)
record_provider_ops_run(
    base_url,
    admin_token=admin_token,
    run_name="provider-sync-dry-run",
    started_at_utc=started_at,
    completed_at_utc=completed_at,
    duration_ms=int((completed_at - started_at).total_seconds() * 1000),
    summary_json={
        "mode": mode,
        "run_id": result["provider_sync_workflow_run_id"],
        "fixtures": result["fixture_count"],
        "odds": result["odds_snapshot_count"],
        "availability": result["availability_snapshot_count"],
    },
    output_excerpt="provider_sync_dry_run_ok",
)
PY
REMOTE
