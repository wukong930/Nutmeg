#!/usr/bin/env bash
set -euo pipefail

PUBLIC_BASE_URL="${NUTMEG_PUBLIC_BASE_URL:-https://goodmood.mcpup.top}"

python3 - "$PUBLIC_BASE_URL" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys


base_url = sys.argv[1].rstrip("/")


def fail(message: str) -> None:
    raise SystemExit(message)


def request_json(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    return json.loads(fetch(path, payload).decode("utf-8"))


def request_text(path: str) -> str:
    return fetch(path).decode("utf-8", "replace")


def fetch(path: str, payload: dict[str, object] | None = None) -> bytes:
    command = [
        "curl",
        "-fsS",
        "--connect-timeout",
        "15",
        "--max-time",
        "30",
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
    command.append(f"{base_url}{path}")
    return subprocess.check_output(command)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


health = request_json("/api/v1/health")
require(health == {"status": "ok", "service": "nutmeg-api"}, "health check failed")

fixtures = request_json("/api/v1/fixtures")
fixture_items = fixtures.get("items")
require(isinstance(fixture_items, list) and len(fixture_items) >= 3, "fixtures are missing")
first_fixture = fixture_items[0]
require(isinstance(first_fixture, dict), "first fixture has unexpected shape")
fixture_id = first_fixture["fixture_id"]
prediction_brief = first_fixture["prediction"]
require(isinstance(prediction_brief, dict), "prediction brief has unexpected shape")
probability_sum = (
    prediction_brief["p_home"]
    + prediction_brief["p_draw"]
    + prediction_brief["p_away"]
)
require(abs(probability_sum - 1.0) < 1e-6, "fixture probabilities do not sum to 1")
require(bool(prediction_brief["model_version"]), "fixture model version is missing")
require(bool(prediction_brief["prediction_time_utc"]), "fixture prediction time is missing")
require(prediction_brief["data_quality_score"] >= 0, "fixture data quality is missing")

prediction = request_json(f"/api/v1/fixtures/{fixture_id}/prediction")
require(prediction["score_top_n"], "fixture detail score top N is missing")
require("1x2" in prediction["odds_comparison"], "1X2 comparison is missing")
require("asian_handicap" in prediction["odds_comparison"], "Asian handicap is missing")
require(
    prediction["model_metadata"]["model_version"] == prediction_brief["model_version"],
    "model metadata does not match fixture brief",
)

score_grid = request_json(f"/api/v1/fixtures/{fixture_id}/score-grid")
grid_mass = sum(sum(row) for row in score_grid["grid"])
require(abs(grid_mass - 1.0) < 1e-6, "score grid is not normalized")

parlay = request_json(
    "/api/v1/parlays/recommend",
    {
        "date": "2026-05-06",
        "pass_types": ["2x1", "4x1"],
        "strategy": "balanced",
        "unit_stake": 2,
        "max_budget": 20,
        "allow_multiple_outcomes_per_fixture": True,
        "allowed_markets": ["1x2", "cn_handicap_1x2"],
        "exclude_beta_competitions": False,
    },
)
parlay_items = parlay["items"]
require(isinstance(parlay_items, list), "parlay items have unexpected shape")
if parlay_items:
    first_ticket = parlay_items[0]
    require(first_ticket["atomic_bet_count"] >= 1, "atomic bet count is missing")
    require(first_ticket["total_stake"] >= first_ticket["unit_stake"], "total stake is invalid")
    require("hit_probability" in first_ticket, "hit probability is missing")
    require("ev" in first_ticket and "roi" in first_ticket, "EV/ROI are missing")
    require(first_ticket["explanation_json"]["calculation_basis"], "explanation payload is missing")
else:
    warnings = parlay.get("warnings")
    require(isinstance(warnings, list) and warnings, "parlay gating warnings are missing")
    require(
        any(
            "competition_not_ready" in warning
            or "competition_data_quality_d" in warning
            or "competition_data_freshness_low" in warning
            or "odds_unavailable" in warning
            or "odds_market_unavailable" in warning
            or "odds_stale" in warning
            or "lineup_unavailable" in warning
            or "lineup_stale" in warning
            or "injury_unavailable" in warning
            or "injury_stale" in warning
            for warning in warnings
        ),
        "parlay gating reason is missing",
    )

accuracy = request_json(
    "/api/v1/accuracy/summary?model_version=active&competition_id=all&market=all&window=90d"
)
require(accuracy["sample_size"] > 0, "accuracy sample size is missing")
require(accuracy["log_loss"] is not None, "log loss is missing")
require(accuracy["brier_score"] is not None, "Brier score is missing")
require(accuracy["calibration_buckets"], "calibration buckets are missing")
require(accuracy["model_comparisons"], "model comparison payload is missing")

providers = request_json("/api/v1/providers/status")
provider_names = {provider["provider_name"] for provider in providers["providers"]}
require("mock-local" in provider_names, "mock provider authorization is missing")
require("football-data.org" in provider_names, "football-data authorization record is missing")
require("sportmonks" in provider_names, "SportMonks authorization record is missing")
require(providers["competition_readiness"], "competition readiness payload is missing")
require(
    providers["model_promotion_review"]["decision"] in {"shadow_candidate", "keep_experiment"},
    "model promotion review is missing",
)

provider_mappings = request_json("/api/v1/providers/mappings?limit=5")
require(isinstance(provider_mappings["items"], list), "provider mappings payload is invalid")
require(isinstance(provider_mappings["summary"], list), "provider mapping summary is invalid")
provider_mapping_review = request_json(
    "/api/v1/providers/mappings/review",
    {"dry_run": True, "limit": 50},
)
review_result = provider_mapping_review["result"]
require(review_result["dry_run"] is True, "provider mapping review should be dry-run")
require(
    isinstance(review_result["issues"], list),
    "provider mapping review issues payload is invalid",
)
require(
    review_result["checked_mapping_count"] >= 0,
    "provider mapping review checked count is invalid",
)
provider_conflicts = request_json(
    "/api/v1/providers/conflicts/evaluate",
    {"dry_run": True, "limit": 50},
)
conflict_result = provider_conflicts["result"]
require(conflict_result["dry_run"] is True, "provider conflict review should be dry-run")
require(
    isinstance(conflict_result["events"], list),
    "provider conflict events payload is invalid",
)
require(
    isinstance(conflict_result["trusted_priorities"], list)
    and conflict_result["trusted_priorities"],
    "trusted provider priority payload is missing",
)

page_markers = {
    "/dashboard": [
        "今日赛事概率地图",
        "赛事列表",
        "本工具仅提供概率分析与研究参考",
    ],
    f"/fixtures/{fixture_id}": [
        "1X2 胜平负概率",
        "中国竞彩让球",
        "亚洲让球",
        "精确比分属于低概率事件",
    ],
    "/parlays": [
        "Parlay Lab",
        "候选组合",
        "串关会放大波动",
        "不构成投注建议",
    ],
    "/upsets": [
        "冷门观察",
        "不代表冷门一定发生",
        "poisson-m1.0.0",
    ],
    "/accuracy": [
        "Accuracy Lab",
        "Log Loss",
        "Brier Score",
        "按玩法拆分 Log Loss",
    ],
    "/providers": [
        "Provider Ops",
        "Provider 授权状态",
        "Runtime key readiness",
        "Free API application checklist",
        "mock dry-run",
        "赛事准入状态",
        "Provider 映射摘要",
        "Provider 映射审核",
        "Provider Ops Access",
        "Provider Ops Audit Trail",
        "locked audit log",
        "Provider Runtime Monitor",
        "Provider Runtime Incidents",
        "fallback monitor",
        "fallback incidents",
        "active window",
        "Incident filters",
        "Runtime Incident Runbook",
        "active",
        "alert",
        "Admin controls locked",
        "Unlock Provider Ops",
        "Access token",
        "Provider Sync Workflow",
        "Provider Terms Review",
        "Admin controls locked. Unlock Provider Ops to use this audited operation.",
        "Mapped Odds Sync",
        "Prediction Quality Gate",
        "Provider 冲突治理",
        "不包含自动投注能力",
    ],
}

for path, markers in page_markers.items():
    html = request_text(path)
    missing = [marker for marker in markers if marker not in html]
    require(not missing, f"{path} missing markers: {missing}")
    print(f"{path} bytes {len(html)}")

print(f"phase9_acceptance_ok {base_url}")
PY
