from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.competition_profiles import (
    CompetitionRecommendationProfile,
    CompetitionRecommendationProfileSet,
)
from nutmeg.recommendations.replacement_short_odds_runtime_profile_promotion import (
    HistoricalShortOddsRuntimeProfilePromotionOptions,
    _options_from_args,
    _parse_args,
    build_historical_short_odds_runtime_profile_promotion_report,
    main,
)


def test_short_odds_runtime_profile_promotion_builds_candidate_profile() -> None:
    report = build_historical_short_odds_runtime_profile_promotion_report(
        current_profile_set=_current_profile_set(),
        production_proposal_report=_production_proposal_report(),
        promotion_smoke_report=_promotion_smoke_report(),
        runtime_shadow_replay_report=_runtime_shadow_replay_report(),
        rolling_admission_report=_rolling_admission_report(),
    )

    assert report.status == "promotion_ready"
    assert report.promotion_ready is True
    assert report.candidate_rule_count == 1
    assert report.allowed_competition_ids == [
        "EPL",
        "FRA_LIGUE_1",
        "GER_BUNDESLIGA",
        "ITA_SERIE_A",
    ]
    assert report.runtime_profile_written is False
    assert all(check.status == "passed" for check in report.checks)
    assert report.candidate_runtime_profile_json["short_odds_replacement_rules"]
    assert report.candidate_runtime_profile_json["source_report_keys"] == {
        "production_proposal": "production-proposal:test",
        "promotion_smoke": "promotion-smoke:test",
        "runtime_shadow_replay": "runtime-shadow:test",
        "post_promotion_runtime_shadow_replay": None,
        "rolling_admission": "rolling-admission:test",
        "suite_gate": "suite-gate:test",
        "final_answer_gate": "final-answer-gate:test",
        "audit": "audit:test",
        "competition_gate": "competition-gate:test",
        "generated_shadow": "shadow:test",
    }


def test_short_odds_runtime_profile_promotion_blocks_bad_rolling_admission() -> None:
    report = build_historical_short_odds_runtime_profile_promotion_report(
        current_profile_set=_current_profile_set(),
        production_proposal_report=_production_proposal_report(),
        promotion_smoke_report=_promotion_smoke_report(),
        runtime_shadow_replay_report=_runtime_shadow_replay_report(),
        rolling_admission_report=_rolling_admission_report(accepted=False),
        options=HistoricalShortOddsRuntimeProfilePromotionOptions(
            require_rolling_admission_accepted=True,
        ),
    )

    assert report.status == "blocked"
    assert report.promotion_ready is False
    assert "rolling_admission_accepted" in report.blockers
    assert report.candidate_rule_count == 0
    assert report.candidate_runtime_profile_json["short_odds_replacement_rules"] == []


def test_short_odds_runtime_profile_promotion_blocks_runtime_profit_loss_harm() -> None:
    runtime_report = _runtime_shadow_replay_report()
    runtime_report["profit_loss_harm_count_vs_original"] = 1

    report = build_historical_short_odds_runtime_profile_promotion_report(
        current_profile_set=_current_profile_set(),
        production_proposal_report=_production_proposal_report(),
        promotion_smoke_report=_promotion_smoke_report(),
        runtime_shadow_replay_report=runtime_report,
        rolling_admission_report=_rolling_admission_report(),
    )

    assert report.status == "blocked"
    assert "runtime_profit_loss_harm_count_vs_original" in report.blockers


def test_short_odds_runtime_profile_promotion_cli_writes_outputs(
    tmp_path: Path,
) -> None:
    current_path = tmp_path / "current_profiles.json"
    proposal_path = tmp_path / "proposal.json"
    smoke_path = tmp_path / "smoke.json"
    runtime_path = tmp_path / "runtime.json"
    rolling_path = tmp_path / "rolling.json"
    profile_output_path = tmp_path / "candidate_profile.json"
    report_output_path = tmp_path / "promotion_report.json"
    current_path.write_text(
        _json(_current_profile_set().model_dump(mode="json")),
        encoding="utf-8",
    )
    proposal_path.write_text(_json(_production_proposal_report()), encoding="utf-8")
    smoke_path.write_text(_json(_promotion_smoke_report()), encoding="utf-8")
    runtime_path.write_text(_json(_runtime_shadow_replay_report()), encoding="utf-8")
    rolling_path.write_text(_json(_rolling_admission_report()), encoding="utf-8")

    main(
        [
            "--current-profile-path",
            str(current_path),
            "--production-proposal-report",
            str(proposal_path),
            "--promotion-smoke-report",
            str(smoke_path),
            "--runtime-shadow-replay-report",
            str(runtime_path),
            "--rolling-admission-report",
            str(rolling_path),
            "--profile-output-path",
            str(profile_output_path),
            "--report-output-path",
            str(report_output_path),
            "--promoted-profile-version",
            "runtime-profile-candidate-v1",
        ]
    )

    candidate_profile = loads(profile_output_path.read_text(encoding="utf-8"))
    promotion_report = loads(report_output_path.read_text(encoding="utf-8"))

    assert candidate_profile["profile_version"] == "runtime-profile-candidate-v1"
    assert candidate_profile["short_odds_replacement_rules"]
    assert promotion_report["status"] == "promotion_ready"
    assert promotion_report["runtime_profile_written"] is False


def test_short_odds_runtime_profile_promotion_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--current-profile-path",
            "current.json",
            "--production-proposal-report",
            "proposal.json",
            "--promotion-smoke-report",
            "smoke.json",
            "--runtime-shadow-replay-report",
            "runtime.json",
            "--post-promotion-runtime-shadow-replay-report",
            "post-runtime.json",
            "--rolling-admission-report",
            "rolling.json",
            "--profile-output-path",
            "profile.json",
            "--report-output-path",
            "report.json",
            "--promoted-profile-version",
            "custom-runtime-profile",
            "--min-allowed-competition-count",
            "2",
            "--min-final-answer-count",
            "12",
            "--min-changed-final-answer-count",
            "4",
            "--min-final-answer-hit-rate-delta",
            "0.01",
            "--min-roi-delta",
            "0.02",
            "--min-profit-loss-delta",
            "0.03",
            "--max-harm-count-vs-original",
            "1",
            "--max-final-hit-harm-count-vs-original",
            "2",
            "--max-profit-loss-harm-count-vs-original",
            "3",
            "--min-average-hit-probability-delta-vs-original",
            "-0.03",
            "--min-rolling-active-competition-fold-count",
            "2",
            "--min-rolling-active-season-fold-count",
            "3",
            "--min-rolling-active-rolling-fold-count",
            "2",
            "--max-rolling-failed-fold-count",
            "1",
            "--allow-non-ready-proposal",
            "--allow-failed-promotion-smoke",
            "--allow-failed-runtime-shadow-replay",
            "--allow-failed-post-promotion-runtime-shadow-replay",
            "--allow-unaccepted-rolling-admission",
            "--allow-existing-short-odds-rules",
            "--allow-runtime-profile-write",
            "--allow-public-response-change",
            "--allow-production-change",
            "--dry-run",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert args.current_profile_path == Path("current.json")
    assert args.profile_output_path == Path("profile.json")
    assert options.promoted_profile_version == "custom-runtime-profile"
    assert options.min_allowed_competition_count == 2
    assert options.min_final_answer_count == 12
    assert options.min_changed_final_answer_count == 4
    assert options.min_final_answer_hit_rate_delta == 0.01
    assert options.min_roi_delta == 0.02
    assert options.min_profit_loss_delta == 0.03
    assert options.max_harm_count_vs_original == 1
    assert options.max_final_hit_harm_count_vs_original == 2
    assert options.max_profit_loss_harm_count_vs_original == 3
    assert options.min_average_hit_probability_delta_vs_original == -0.03
    assert options.min_rolling_active_competition_fold_count == 2
    assert options.min_rolling_active_season_fold_count == 3
    assert options.min_rolling_active_rolling_fold_count == 2
    assert options.max_rolling_failed_fold_count == 1
    assert options.require_production_proposal_ready is False
    assert options.require_promotion_smoke_passed is False
    assert options.require_runtime_shadow_replay_passed is False
    assert options.require_post_promotion_runtime_shadow_replay_passed is False
    assert options.require_rolling_admission_accepted is False
    assert options.require_no_current_short_odds_rules is False
    assert options.require_no_runtime_profile_write is False
    assert options.require_no_public_response_change is False
    assert options.require_no_production_change is False
    assert options.dry_run is True


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


def _production_proposal_report() -> dict[str, object]:
    return {
        "report_key": "production-proposal:test",
        "status": "production_proposal_ready",
        "production_recommendation_allowed": True,
        "shadow_allowed": True,
        "proposal_count": 1,
        "source_suite_gate_report_key": "suite-gate:test",
        "source_final_answer_gate_report_key": "final-answer-gate:test",
        "source_runtime_shadow_replay_report_key": "runtime-shadow:test",
        "source_rolling_admission_report_key": "rolling-admission:test",
        "source_audit_report_key": "audit:test",
        "source_competition_gate_report_key": "competition-gate:test",
        "generated_shadow_report_key": "shadow:test",
        "profile_id": "max_short_odds_within_deficit_v1",
        "ready_competition_ids": [
            "EPL",
            "FRA_LIGUE_1",
            "GER_BUNDESLIGA",
            "ITA_SERIE_A",
        ],
        "isolated_competition_ids": ["ESP_LA_LIGA"],
        "checks": [],
        "proposal_rule": _rule(),
        "proposal_profile_set_json": {"rules": [_rule()]},
        "warnings": [],
        "summary_json": {},
    }


def _promotion_smoke_report() -> dict[str, object]:
    return {
        "report_key": "promotion-smoke:test",
        "status": "passed",
        "passed": True,
        "source_proposal_report_key": "production-proposal:test",
        "current_profile_version": "current-v1",
        "promoted_profile_version": "temporary-runtime-profile-v1",
        "current_profile_count": 1,
        "temporary_profile_count": 1,
        "proposed_rule_count": 1,
        "allowed_competition_ids": [
            "EPL",
            "FRA_LIGUE_1",
            "GER_BUNDESLIGA",
            "ITA_SERIE_A",
        ],
        "excluded_competition_ids": ["ESP_LA_LIGA"],
        "production_recommendation_changed": False,
        "runtime_profile_written": False,
        "public_response_changed": False,
        "checks": [],
        "temporary_profile_set_json": {
            "profile_version": "temporary-runtime-profile-v1",
            "profiles": [],
            "short_odds_replacement_rules": [_rule()],
        },
        "public_contract_json": {"public_response_changed": False},
        "warnings": [],
        "summary_json": {},
    }


def _runtime_shadow_replay_report() -> dict[str, object]:
    return {
        "report_key": "runtime-shadow:test",
        "status": "shadow_replay_passed",
        "passed": True,
        "source_audit_report_key": "audit:test",
        "source_rule_profile_version": "temporary-runtime-profile-v1",
        "rule_count": 1,
        "enabled_rule_count": 1,
        "final_answer_count": 30,
        "changed_final_answer_count": 17,
        "baseline_final_answer_hit_count": 20,
        "shadow_final_answer_hit_count": 20,
        "final_answer_hit_delta_count": 0,
        "baseline_final_answer_hit_rate": 20 / 30,
        "shadow_final_answer_hit_rate": 20 / 30,
        "final_answer_hit_rate_delta": 0.0,
        "baseline_profit_loss": 3.0,
        "shadow_profit_loss": 4.0,
        "profit_loss_delta": 1.0,
        "baseline_roi": 0.05,
        "shadow_roi": 0.066,
        "roi_delta": 0.016,
        "total_stake": 60.0,
        "harm_count_vs_original": 0,
        "final_hit_harm_count_vs_original": 0,
        "profit_loss_harm_count_vs_original": 0,
        "average_hit_probability_delta_vs_original": -0.014,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "checks": [],
        "rule_set_json": {},
        "changed_items": [],
        "warnings": [],
        "summary_json": {},
    }


def _rolling_admission_report(*, accepted: bool = True) -> dict[str, object]:
    return {
        "report_key": "rolling-admission:test",
        "status": "accepted" if accepted else "shadow_only",
        "production_recommendation_allowed": accepted,
        "shadow_allowed": True,
        "source_audit_report_key": "audit:test",
        "source_rule_profile_version": "temporary-runtime-profile-v1",
        "overall_runtime_shadow_report_key": "runtime-shadow:test",
        "fold_count": 13,
        "active_fold_count": 13,
        "failed_fold_count": 0 if accepted else 1,
        "active_competition_fold_count": 4,
        "active_season_fold_count": 5,
        "active_rolling_fold_count": 4,
        "checks": [],
        "folds": [],
        "warnings": [],
        "summary_json": {
            "overall_final_answer_hit_rate_delta": 0.0 if accepted else -0.01,
            "overall_roi_delta": 0.016 if accepted else -0.02,
            "overall_profit_loss_delta": 1.0 if accepted else -1.0,
            "overall_harm_count_vs_original": 0 if accepted else 1,
            "overall_final_hit_harm_count_vs_original": 0 if accepted else 1,
            "overall_profit_loss_harm_count_vs_original": 0 if accepted else 1,
            "overall_average_hit_probability_delta_vs_original": -0.014,
        },
    }


def _rule() -> dict[str, object]:
    return {
        "rule_id": "short_odds_final_answer_replacement_v1",
        "profile_id": "max_short_odds_within_deficit_v1",
        "proposed_profile_version": "proposal-profile-v1",
        "proposed_production_enabled": True,
        "production_recommendation_changed": False,
        "allowed_competition_ids": [
            "EPL",
            "FRA_LIGUE_1",
            "GER_BUNDESLIGA",
            "ITA_SERIE_A",
        ],
        "excluded_competition_ids": ["ESP_LA_LIGA"],
        "selection_rule": "highest_candidate_hit_probability",
        "constraints_json": {
            "max_replacements_per_final_answer": 1,
            "min_replacement_probability": 0.55,
            "max_replacement_decimal_odds": 1.75,
            "min_candidate_hit_probability_delta_vs_original": -0.025,
        },
        "source_report_keys": {
            "suite_gate": "suite-gate:test",
            "final_answer_gate": "final-answer-gate:test",
            "audit": "audit:test",
            "competition_gate": "competition-gate:test",
            "generated_shadow": "shadow:test",
            "runtime_shadow_replay": "runtime-shadow:test",
            "rolling_admission": "rolling-admission:test",
        },
        "evidence_json": {},
        "rollback_conditions": [
            "disable_if_production_harm_count_vs_original_exceeds_0",
            "disable_if_runtime_shadow_replay_report_missing_or_failed",
            "disable_if_rolling_admission_report_missing_or_failed",
        ],
        "notes": [],
    }


def _json(payload: dict[str, object]) -> str:
    return f"{dumps(payload)}\n"
