from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.recommendation_strategy_promotion_gate import (
    RecommendationStrategyPromotionGateEvidence,
    RecommendationStrategyPromotionGateReport,
)
from nutmeg.recommendations.recommendation_strategy_staged_activation_smoke import (
    RecommendationStrategyStagedActivationSmokeOptions,
    _options_from_args,
    _parse_args,
    build_recommendation_strategy_staged_activation_smoke_report,
    load_recommendation_strategy_staged_activation_smoke_report,
    main,
)


def test_strategy_staged_activation_smoke_is_ready_for_clean_gate() -> None:
    report = build_recommendation_strategy_staged_activation_smoke_report(
        _strategy_gate_report(),
        rule_profile=_rule_profile(),
    )

    assert report.status == "staged_activation_ready"
    assert report.staged_activation_ready is True
    assert report.default_profile_written is False
    assert report.production_recommendation_allowed is False
    assert report.public_response_changed is False
    assert report.selected_rule_count == 1
    assert report.allowed_competition_ids == [
        "ENG_CHAMPIONSHIP",
        "ESP_SEGUNDA_DIVISION",
        "FRA_LIGUE_2",
        "GER_2_BUNDESLIGA",
        "ITA_SERIE_B",
    ]
    assert report.staged_profile_json["staged_only"] is True
    assert report.staged_profile_json["short_odds_replacement_rules"]
    assert all(check.status == "passed" for check in report.checks)


def test_strategy_staged_activation_smoke_blocks_non_dry_run_profile() -> None:
    profile = _rule_profile()
    profile["dry_run_only"] = False

    report = build_recommendation_strategy_staged_activation_smoke_report(
        _strategy_gate_report(),
        rule_profile=profile,
    )

    assert report.status == "blocked"
    assert "profile_dry_run_only" in report.blockers
    assert report.default_profile_written is False


def test_strategy_staged_activation_smoke_watchlists_candidate_mismatch() -> None:
    profile = _rule_profile()
    rule = dict(profile["rules"][0])  # type: ignore[index]
    evidence = dict(rule["evidence_json"])  # type: ignore[index]
    evidence["candidate_key"] = "replacement_probability_preserving_candidate:other"
    rule["evidence_json"] = evidence
    profile["rules"] = [rule]

    report = build_recommendation_strategy_staged_activation_smoke_report(
        _strategy_gate_report(),
        rule_profile=profile,
    )

    assert report.status == "staged_activation_watchlist"
    assert "source_candidate_match" in report.blockers
    assert report.production_recommendation_changed is False


def test_strategy_staged_activation_smoke_relaxes_missing_roi_requirement() -> None:
    gate = _strategy_gate_report().model_copy(update={"minimum_roi_delta": None})

    blocked = build_recommendation_strategy_staged_activation_smoke_report(
        gate,
        rule_profile=_rule_profile(),
    )
    relaxed = build_recommendation_strategy_staged_activation_smoke_report(
        gate,
        rule_profile=_rule_profile(),
        options=RecommendationStrategyStagedActivationSmokeOptions(
            min_minimum_roi_delta=None
        ),
    )

    assert blocked.status == "staged_activation_watchlist"
    assert "minimum_roi_delta" in blocked.blockers
    assert relaxed.status == "staged_activation_ready"


def test_strategy_staged_activation_smoke_cli_options_and_main(tmp_path: Path) -> None:
    gate_path = tmp_path / "strategy_gate.json"
    profile_path = tmp_path / "rule_profile.json"
    report_path = tmp_path / "smoke_report.json"
    staged_profile_path = tmp_path / "staged_profile.json"
    gate_path.write_text(
        f"{_strategy_gate_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    profile_path.write_text(
        f"{_json(_rule_profile())}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--strategy-gate-report",
            str(gate_path),
            "--staged-rule-profile",
            str(profile_path),
            "--report-output-path",
            str(report_path),
            "--staged-profile-output-path",
            str(staged_profile_path),
            "--staged-profile-version",
            "unit-staged-profile",
            "--min-total-final-answer-count",
            "99",
            "--min-total-changed-final-answer-count",
            "13",
            "--min-minimum-active-surface-count",
            "8",
            "--min-minimum-active-competition-fold-count",
            "5",
            "--min-minimum-active-season-fold-count",
            "5",
            "--min-minimum-active-rolling-fold-count",
            "13",
            "--allow-missing-roi-delta",
        ]
    )
    options = _options_from_args(args)

    assert options.staged_profile_version == "unit-staged-profile"
    assert options.min_total_final_answer_count == 99
    assert options.min_minimum_roi_delta is None

    main(
        [
            "--strategy-gate-report",
            str(gate_path),
            "--staged-rule-profile",
            str(profile_path),
            "--report-output-path",
            str(report_path),
            "--staged-profile-output-path",
            str(staged_profile_path),
            "--staged-profile-version",
            "unit-staged-profile",
            "--min-total-final-answer-count",
            "99",
            "--min-total-changed-final-answer-count",
            "13",
            "--min-minimum-active-surface-count",
            "8",
            "--min-minimum-active-competition-fold-count",
            "5",
            "--min-minimum-active-season-fold-count",
            "5",
            "--min-minimum-active-rolling-fold-count",
            "13",
        ]
    )

    saved = load_recommendation_strategy_staged_activation_smoke_report(report_path)
    assert saved.status == "staged_activation_ready"
    assert saved.staged_profile_version == "unit-staged-profile"
    assert staged_profile_path.exists()


def _strategy_gate_report() -> RecommendationStrategyPromotionGateReport:
    return RecommendationStrategyPromotionGateReport(
        gate_key="recommendation_strategy_promotion_gate:test",
        status="ready",
        strategy_gate_ready=True,
        strategy_key="probability_preserving_13change_replacement",
        gate_id="probability_preserving_13change_strategy_gate_v1",
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        evidence_count=1,
        ready_evidence_count=1,
        watchlist_evidence_count=0,
        blocked_evidence_count=0,
        selected_candidate_keys=[
            "replacement_probability_preserving_candidate:test",
        ],
        allowed_competition_ids=[
            "ENG_CHAMPIONSHIP",
            "ESP_SEGUNDA_DIVISION",
            "FRA_LIGUE_2",
            "GER_2_BUNDESLIGA",
            "ITA_SERIE_B",
        ],
        total_final_answer_count=99,
        total_changed_final_answer_count=13,
        total_final_answer_hit_delta_count=4,
        total_profit_loss_delta=15.74,
        minimum_roi_delta=0.0403,
        total_harm_count_vs_original=0,
        total_final_hit_harm_count_vs_original=0,
        total_profit_loss_harm_count_vs_original=0,
        minimum_active_surface_count=8,
        total_failed_surface_count=0,
        minimum_active_competition_fold_count=5,
        minimum_active_season_fold_count=5,
        minimum_active_rolling_fold_count=13,
        total_failed_fold_count=0,
        evidence=[_strategy_gate_evidence()],
        checks=[],
        blockers=[],
        warnings=[],
        summary_json={},
    )


def _strategy_gate_evidence() -> RecommendationStrategyPromotionGateEvidence:
    return RecommendationStrategyPromotionGateEvidence(
        report_key="historical_replacement_probability_preserving_promotion_review:test",
        status="promotion_review_ready",
        promotion_review_allowed=True,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        dry_run_only_review_profile=True,
        selected_candidate_key="replacement_probability_preserving_candidate:test",
        source_runtime_dry_run_report_key="runtime-dry-run:test",
        source_grid_report_key="grid:test",
        source_surface_replay_report_key="surface:test",
        source_admission_report_key="admission:test",
        generated_runtime_shadow_replay_report_key="runtime-shadow:test",
        candidate_rule_count=1,
        allowed_competition_ids=[
            "ENG_CHAMPIONSHIP",
            "ESP_SEGUNDA_DIVISION",
            "FRA_LIGUE_2",
            "GER_2_BUNDESLIGA",
            "ITA_SERIE_B",
        ],
        final_answer_count=99,
        changed_final_answer_count=13,
        final_answer_hit_delta_count=4,
        profit_loss_delta=15.74,
        roi_delta=0.0403,
        harm_count_vs_original=0,
        final_hit_harm_count_vs_original=0,
        profit_loss_harm_count_vs_original=0,
        average_hit_probability_delta_vs_original=-0.011,
        active_surface_count=8,
        failed_surface_count=0,
        active_competition_fold_count=5,
        active_season_fold_count=5,
        active_rolling_fold_count=13,
        failed_fold_count=0,
        blocker_count=0,
        blockers=[],
        warning_count=0,
        warnings=[],
    )


def _rule_profile() -> dict[str, object]:
    return {
        "profile_version": "review-profile-v1",
        "calculation_basis": "probability_preserving_replacement_runtime_dry_run_rule_set_v3_1",
        "shadow_replay_enabled": True,
        "dry_run_only": True,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "review_status": "promotion_review_ready",
        "promotion_review_allowed": True,
        "rules": [_rule()],
        "notes": ["dry_run_only", "promotion_review_only"],
    }


def _rule() -> dict[str, object]:
    return {
        "rule_id": "probability_preserving_runtime_dry_run:test",
        "profile_id": "nearest_model_top_probability",
        "proposed_profile_version": "runtime-dry-run-v1",
        "proposed_production_enabled": True,
        "production_recommendation_changed": False,
        "allowed_competition_ids": [
            "ENG_CHAMPIONSHIP",
            "ESP_SEGUNDA_DIVISION",
            "FRA_LIGUE_2",
            "GER_2_BUNDESLIGA",
            "ITA_SERIE_B",
        ],
        "excluded_competition_ids": [],
        "selection_rule": "highest_candidate_hit_probability",
        "constraints_json": {
            "min_replacement_probability": 0.45,
            "max_replacement_decimal_odds": 2.20,
            "min_candidate_hit_probability_delta_vs_model_top": -0.05,
            "min_candidate_hit_probability_delta_vs_original": -0.025,
            "exclude_original_hit_harm": True,
            "max_harm_count_vs_original": 0,
            "max_final_hit_harm_count_vs_original": 0,
            "max_profit_loss_harm_count_vs_original": 0,
        },
        "source_report_keys": {
            "grid": "grid:test",
            "surface_replay": "surface:test",
            "admission": "admission:test",
            "final_answer_gate": "final-answer-gate:test",
        },
        "evidence_json": {
            "dry_run_only": True,
            "candidate_key": "replacement_probability_preserving_candidate:test",
            "changed_final_answer_count": 13,
            "final_answer_hit_delta_count_vs_original": 4,
            "profit_loss_delta_vs_original": 15.74,
            "harm_count_vs_original": 0,
        },
        "rollback_conditions": [
            "disable_if_runtime_dry_run_report_missing_or_failed",
            "disable_if_production_recommendation_changed",
            "disable_if_public_response_changed",
            "disable_if_harm_count_vs_original_exceeds_0",
        ],
        "notes": ["runtime_proposal_dry_run_only"],
    }


def _json(payload: object) -> str:
    import json

    return json.dumps(payload, indent=2)
