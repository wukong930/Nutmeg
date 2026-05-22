from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsReplacementRuleManifestOptions,
    build_short_odds_replacement_rule_manifest_report,
    load_short_odds_runtime_rule_set,
    main,
)


def test_short_odds_rule_manifest_loads_staged_profile_and_checks_ready(
    tmp_path: Path,
) -> None:
    path = tmp_path / "staged_profile.json"
    path.write_text(_json({"staged_profile_json": _rule_profile()}), encoding="utf-8")

    rule_set = load_short_odds_runtime_rule_set(path, enable_shadow_replay=True)
    report = build_short_odds_replacement_rule_manifest_report(
        rule_set,
        options=ShortOddsReplacementRuleManifestOptions(
            min_rule_count=1,
            min_allowed_competition_count=2,
        ),
    )

    assert rule_set.profile_version == "short-odds-manifest-test"
    assert rule_set.shadow_replay_enabled is True
    assert rule_set.rules[0].constraints().min_replacement_probability == 0.55
    assert rule_set.rules[0].allows_competition("EPL") is True
    assert rule_set.rules[0].allows_competition("ESP_LA_LIGA") is False
    assert report.status == "ready"
    assert report.ready is True
    assert report.rule_count == 1
    assert report.selected_rule_count == 1
    assert report.enabled_rule_count == 1
    assert report.allowed_competition_ids == ["EPL", "FRA_LIGUE_1"]
    assert report.excluded_competition_ids == ["ESP_LA_LIGA"]
    assert report.selection_rules == ["highest_candidate_hit_probability"]
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert not report.blockers
    assert all(check.status == "passed" for check in report.checks)
    selected_rule = report.selected_rules_json[0]
    evidence = selected_rule["evidence_json"]
    assert isinstance(evidence, dict)
    assert evidence["runtime_shadow_replay_passed"] is True


def test_short_odds_rule_manifest_blocks_overlap_and_missing_harm_guard(
    tmp_path: Path,
) -> None:
    profile = _rule_profile()
    rules = profile["short_odds_replacement_rules"]
    assert isinstance(rules, list)
    rule = rules[0]
    assert isinstance(rule, dict)
    rule["excluded_competition_ids"] = ["EPL"]
    constraints = rule["constraints_json"]
    assert isinstance(constraints, dict)
    constraints.pop("max_final_hit_harm_count_vs_original")
    path = tmp_path / "blocked_profile.json"
    path.write_text(_json(profile), encoding="utf-8")

    report = build_short_odds_replacement_rule_manifest_report(
        load_short_odds_runtime_rule_set(path),
        options=ShortOddsReplacementRuleManifestOptions(),
    )

    assert report.status == "blocked"
    assert report.ready is False
    assert "allowed_excluded_competition_disjoint" in report.blockers
    assert "max_final_hit_harm_count_vs_original_zero" in report.blockers
    assert any(
        warning.endswith("allowed_excluded_competition_disjoint")
        for warning in report.warnings
    )


def test_short_odds_rule_manifest_cli_writes_report(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    output_path = tmp_path / "manifest.json"
    profile_path.write_text(_json(_rule_profile()), encoding="utf-8")

    main(
        [
            "--rule-profile",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--min-rule-count",
            "1",
            "--min-allowed-competition-count",
            "2",
            "--rule-ids",
            "short_odds_final_answer_replacement_v1",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["ready"] is True
    assert payload["summary_json"]["selected_rule_count"] == 1
    assert payload["summary_json"]["public_response_changed"] is False


def _rule_profile() -> dict[str, object]:
    return {
        "profile_version": "short-odds-manifest-test",
        "calculation_basis": "short_odds_replacement_rule_manifest_test",
        "short_odds_replacement_rules": [
            {
                "rule_id": "short_odds_final_answer_replacement_v1",
                "profile_id": "max_short_odds_within_deficit_v1",
                "proposed_profile_version": "proposal-test",
                "proposed_production_enabled": True,
                "production_recommendation_changed": False,
                "allowed_competition_ids": ["EPL", "FRA_LIGUE_1"],
                "excluded_competition_ids": ["ESP_LA_LIGA"],
                "selection_rule": "highest_candidate_hit_probability",
                "constraints_json": {
                    "selection_rule": "highest_candidate_hit_probability",
                    "max_replacements_per_final_answer": 1,
                    "min_replacement_probability": 0.55,
                    "max_replacement_decimal_odds": 1.75,
                    "min_candidate_hit_probability_delta_vs_model_top": -0.015,
                    "max_candidate_hit_probability_delta_vs_model_top": 0.0,
                    "min_decimal_odds_delta_vs_model_top": 0.0,
                    "min_average_hit_probability_delta_vs_original": -0.02,
                    "min_candidate_hit_probability_delta_vs_original": -0.025,
                    "max_harm_count_vs_original": 0,
                    "max_final_hit_harm_count_vs_original": 0,
                    "max_profit_loss_harm_count_vs_original": 0,
                },
                "source_report_keys": {
                    "suite_gate": "suite:test",
                    "final_answer_gate": "final-answer:test",
                    "audit": "audit:test",
                    "competition_gate": "competition:test",
                    "generated_shadow": "shadow:test",
                    "runtime_shadow_replay": "runtime-shadow:test",
                    "rolling_admission": "rolling:test",
                },
                "evidence_json": {
                    "runtime_shadow_replay_passed": True,
                    "rolling_admission_accepted": True,
                    "rolling_admission_production_allowed": True,
                },
                "rollback_conditions": [
                    "disable_if_runtime_shadow_replay_report_missing_or_failed",
                    "disable_if_rolling_admission_report_missing_or_failed",
                ],
                "notes": [
                    "Rule remains internal and must not be exposed as user-facing text."
                ],
            }
        ],
    }


def _json(value: object) -> str:
    return f"{dumps(value, indent=2)}\n"
