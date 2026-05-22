from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.competition_profiles import (
    CompetitionRecommendationProfile,
    CompetitionRecommendationProfileSet,
)
from nutmeg.recommendations.replacement_short_odds_promotion_smoke import (
    _options_from_args,
    _parse_args,
    build_historical_short_odds_promotion_smoke_report,
    load_historical_short_odds_production_proposal_report,
    main,
)


def test_short_odds_promotion_smoke_passes_without_runtime_profile_write() -> None:
    report = build_historical_short_odds_promotion_smoke_report(
        current_profile_set=_current_profile_set(),
        production_proposal_report=_production_proposal_report(),
    )

    assert report.passed is True
    assert report.status == "passed"
    assert report.source_proposal_report_key == "short-odds-production-proposal:test"
    assert report.runtime_profile_written is False
    assert report.public_response_changed is False
    assert report.production_recommendation_changed is False
    assert report.allowed_competition_ids == ["EPL", "FRA_LIGUE_1"]
    assert report.excluded_competition_ids == ["ESP_LA_LIGA"]
    assert all(check.status == "passed" for check in report.checks)
    assert report.temporary_profile_set_json["base_profile_version"] == "current-v1"
    assert report.temporary_profile_set_json["short_odds_replacement_rules"]
    assert report.temporary_profile_set_json["runtime_profile_written"] is False
    assert report.public_contract_json == {
        "public_response_changed": False,
        "frontend_changed": False,
        "user_facing_strategy_text": False,
        "ordinary_user_path_changed": False,
        "production_recommendation_changed": False,
    }


def test_short_odds_promotion_smoke_fails_when_allowed_and_excluded_overlap() -> None:
    proposal = _production_proposal_report(
        allowed_competitions=["EPL", "ESP_LA_LIGA"],
        excluded_competitions=["ESP_LA_LIGA"],
    )

    report = build_historical_short_odds_promotion_smoke_report(
        current_profile_set=_current_profile_set(),
        production_proposal_report=proposal,
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.passed is False
    assert report.status == "failed"
    assert "allowed_excluded_disjoint" in failed_checks
    assert "short_odds_promotion_smoke:failed" in report.warnings


def test_short_odds_promotion_smoke_fails_when_current_profile_already_has_rule() -> None:
    current = _current_profile_set().model_dump(mode="json")
    current["short_odds_replacement_rules"] = [{"rule_id": "existing"}]

    report = build_historical_short_odds_promotion_smoke_report(
        current_profile_set=current,
        production_proposal_report=_production_proposal_report(),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.passed is False
    assert "current_profile_has_no_short_odds_rules" in failed_checks


def test_short_odds_promotion_smoke_fails_without_rolling_admission_evidence() -> None:
    proposal = _production_proposal_report()
    assert isinstance(proposal["proposal_rule"], dict)
    rule = proposal["proposal_rule"]
    assert isinstance(rule, dict)
    source_report_keys = rule["source_report_keys"]
    assert isinstance(source_report_keys, dict)
    evidence = rule["evidence_json"]
    assert isinstance(evidence, dict)
    source_report_keys.pop("rolling_admission")
    evidence["rolling_admission_accepted"] = False
    proposal["source_rolling_admission_report_key"] = None

    report = build_historical_short_odds_promotion_smoke_report(
        current_profile_set=_current_profile_set(),
        production_proposal_report=proposal,
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.passed is False
    assert "rule_0_rolling_admission_accepted_evidence" in failed_checks
    assert "rule_0_source_report_keys_present" in failed_checks


def test_short_odds_promotion_smoke_blocks_runtime_final_hit_harm_evidence() -> None:
    proposal = _production_proposal_report()
    assert isinstance(proposal["proposal_rule"], dict)
    rule = proposal["proposal_rule"]
    evidence = rule["evidence_json"]
    assert isinstance(evidence, dict)
    evidence["runtime_final_hit_harm_count_vs_original"] = 1

    report = build_historical_short_odds_promotion_smoke_report(
        current_profile_set=_current_profile_set(),
        production_proposal_report=proposal,
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.passed is False
    assert "rule_0_runtime_final_hit_harm_count_evidence" in failed_checks


def test_short_odds_promotion_smoke_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    current_path = tmp_path / "profiles.json"
    proposal_path = tmp_path / "proposal.json"
    output_path = tmp_path / "smoke.json"
    current_path.write_text(
        _json(_current_profile_set().model_dump(mode="json")),
        encoding="utf-8",
    )
    proposal_path.write_text(_json(_production_proposal_report()), encoding="utf-8")

    args = _parse_args(
        [
            "--current-profile-path",
            str(current_path),
            "--production-proposal-report",
            str(proposal_path),
            "--output-path",
            str(output_path),
            "--promoted-profile-version",
            "custom-smoke-version",
            "--min-allowed-competition-count",
            "2",
            "--max-replacements-per-final-answer",
            "1",
            "--min-replacement-probability",
            "0.6",
            "--max-replacement-decimal-odds",
            "1.8",
            "--min-average-hit-probability-delta-vs-original",
            "-0.03",
            "--min-candidate-hit-probability-delta-vs-original",
            "-0.025",
                "--max-harm-count-vs-original",
                "1",
                "--max-final-hit-harm-count-vs-original",
                "2",
                "--max-profit-loss-harm-count-vs-original",
                "3",
                "--min-rolling-active-competition-fold-count",
            "2",
            "--min-rolling-active-season-fold-count",
            "3",
            "--min-rolling-active-rolling-fold-count",
            "2",
            "--max-rolling-failed-fold-count",
            "1",
            "--allow-non-ready-proposal",
            "--allow-production-blocked-proposal",
            "--allow-runtime-profile-write",
            "--allow-public-strategy-exposure",
            "--allow-existing-short-odds-rules",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert args.current_profile_path == current_path
    assert args.production_proposal_report == proposal_path
    assert args.output_path == output_path
    assert options.promoted_profile_version == "custom-smoke-version"
    assert options.min_allowed_competition_count == 2
    assert options.min_replacement_probability == 0.6
    assert options.max_replacement_decimal_odds == 1.8
    assert options.min_average_hit_probability_delta_vs_original == -0.03
    assert options.min_candidate_hit_probability_delta_vs_original == -0.025
    assert options.max_harm_count_vs_original == 1
    assert options.max_final_hit_harm_count_vs_original == 2
    assert options.max_profit_loss_harm_count_vs_original == 3
    assert options.min_rolling_active_competition_fold_count == 2
    assert options.min_rolling_active_season_fold_count == 3
    assert options.min_rolling_active_rolling_fold_count == 2
    assert options.max_rolling_failed_fold_count == 1
    assert options.require_production_proposal_ready is False
    assert options.require_production_allowed is False
    assert options.require_no_runtime_profile_write is False
    assert options.require_no_public_strategy_exposure is False
    assert options.require_no_existing_short_odds_rules is False
    assert load_historical_short_odds_production_proposal_report(
        proposal_path
    ).report_key == "short-odds-production-proposal:test"

    main(
        [
            "--current-profile-path",
            str(current_path),
            "--production-proposal-report",
            str(proposal_path),
            "--output-path",
            str(output_path),
            "--min-allowed-competition-count",
            "2",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["runtime_profile_written"] is False


def _current_profile_set() -> CompetitionRecommendationProfileSet:
    return CompetitionRecommendationProfileSet(
        profile_version="current-v1",
        profiles=[
            CompetitionRecommendationProfile(
                competition_id="EPL",
                final_answer_score_adjustments={"5x1:single": 0.1},
            )
        ],
        notes=["existing profile note"],
    )


def _production_proposal_report(
    *,
    allowed_competitions: list[str] | None = None,
    excluded_competitions: list[str] | None = None,
) -> dict[str, object]:
    allowed = allowed_competitions or ["EPL", "FRA_LIGUE_1"]
    excluded = excluded_competitions or ["ESP_LA_LIGA"]
    rule = {
        "rule_id": "short_odds_final_answer_replacement_v1",
        "profile_id": "max_short_odds_within_deficit_v1",
        "proposed_profile_version": "proposal-profile-v1",
        "proposed_production_enabled": True,
        "production_recommendation_changed": False,
        "allowed_competition_ids": allowed,
        "excluded_competition_ids": excluded,
        "selection_rule": "highest_candidate_hit_probability",
        "constraints_json": {
            "selection_rule": "highest_candidate_hit_probability",
            "max_replacements_per_final_answer": 1,
            "min_replacement_probability": 0.55,
            "max_replacement_decimal_odds": 1.75,
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
            "rolling_admission": "rolling-admission:test",
        },
        "evidence_json": {
            "harm_count_vs_original": 0,
            "final_hit_harm_count_vs_original": 0,
            "profit_loss_harm_count_vs_original": 0,
            "final_answer_hit_rate_delta": 0.05,
            "roi_delta": 0.1,
            "profit_loss_delta": 2.0,
            "runtime_shadow_replay_passed": True,
            "runtime_harm_count_vs_original": 0,
            "runtime_final_hit_harm_count_vs_original": 0,
            "runtime_profit_loss_harm_count_vs_original": 0,
            "rolling_admission_accepted": True,
            "rolling_failed_fold_count": 0,
            "rolling_active_competition_fold_count": 4,
            "rolling_active_season_fold_count": 5,
            "rolling_active_rolling_fold_count": 4,
            "rolling_overall_final_answer_hit_rate_delta": 0.0,
            "rolling_overall_roi_delta": 0.016,
            "rolling_overall_profit_loss_delta": 1.0,
            "rolling_overall_harm_count_vs_original": 0,
            "rolling_overall_final_hit_harm_count_vs_original": 0,
            "rolling_overall_profit_loss_harm_count_vs_original": 0,
            "rolling_overall_average_hit_probability_delta_vs_original": -0.014,
        },
        "rollback_conditions": [
            "disable_if_production_harm_count_vs_original_exceeds_0",
            "disable_if_production_final_hit_harm_count_vs_original_exceeds_0",
            "disable_if_production_profit_loss_harm_count_vs_original_exceeds_0",
            "disable_if_runtime_shadow_replay_report_missing_or_failed",
            "disable_if_rolling_admission_report_missing_or_failed",
            "disable_if_any_isolated_competition_enters_allowed_set",
            "disable_if_source_report_key_mismatch_or_missing",
        ],
        "notes": [],
    }
    return {
        "report_key": "short-odds-production-proposal:test",
        "status": "production_proposal_ready",
        "production_recommendation_allowed": True,
        "shadow_allowed": True,
        "proposal_count": 1,
        "source_suite_gate_report_key": "suite:test",
        "source_final_answer_gate_report_key": "final-answer:test",
        "source_runtime_shadow_replay_report_key": "runtime-shadow:test",
        "source_rolling_admission_report_key": "rolling-admission:test",
        "source_audit_report_key": "audit:test",
        "source_competition_gate_report_key": "competition:test",
        "generated_shadow_report_key": "shadow:test",
        "profile_id": "max_short_odds_within_deficit_v1",
        "ready_competition_ids": allowed,
        "isolated_competition_ids": excluded,
        "checks": [],
        "proposal_rule": rule,
        "proposal_profile_set_json": {
            "profile_version": "proposal-profile-v1",
            "calculation_basis": "historical_short_odds_production_proposal_v3_1",
            "status": "production_proposal_ready",
            "production_recommendation_allowed": True,
            "shadow_allowed": True,
            "production_recommendation_changed": False,
            "rules": [rule],
        },
        "warnings": [],
        "summary_json": {},
    }


def _json(payload: dict[str, object]) -> str:
    return f"{dumps(payload)}\n"
