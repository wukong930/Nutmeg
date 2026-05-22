from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.competition_profiles import (
    CompetitionRecommendationProfile,
    CompetitionRecommendationProfileSet,
)
from nutmeg.recommendations.replacement_short_odds_runtime_profile_activation import (
    HistoricalShortOddsRuntimeProfileActivationOptions,
    _options_from_args,
    _parse_args,
    build_historical_short_odds_runtime_profile_activation_report,
    main,
)


def test_short_odds_runtime_profile_activation_builds_artifact() -> None:
    report = build_historical_short_odds_runtime_profile_activation_report(
        current_profile_set=_current_profile_set(),
        candidate_runtime_profile=_candidate_runtime_profile(),
        runtime_profile_promotion_report=_promotion_report(),
        candidate_runtime_shadow_replay_report=_candidate_runtime_shadow_replay_report(),
        options=HistoricalShortOddsRuntimeProfileActivationOptions(
            activated_profile_version="activated-profile-v1"
        ),
    )

    assert report.status == "activation_ready"
    assert report.activation_ready is True
    assert report.candidate_rule_count == 1
    assert report.allowed_competition_ids == [
        "EPL",
        "FRA_LIGUE_1",
        "GER_BUNDESLIGA",
        "ITA_SERIE_A",
    ]
    assert report.default_profile_written is False
    assert all(check.status == "passed" for check in report.checks)
    assert report.activated_profile_json["profile_version"] == "activated-profile-v1"
    assert report.activated_profile_json["base_profile_version"] == "current-v1"
    assert report.activated_profile_json["candidate_profile_version"] == (
        "candidate-profile-v1"
    )
    assert report.activated_profile_json["short_odds_replacement_rules"]
    assert report.activated_profile_json["source_report_keys"] == {
        "production_proposal": "production-proposal:test",
        "promotion_smoke": "promotion-smoke:test",
        "runtime_shadow_replay": "runtime-shadow:test",
        "post_promotion_runtime_shadow_replay": "post-runtime-shadow:test",
        "rolling_admission": "rolling-admission:test",
        "runtime_profile_promotion": "runtime-profile-promotion:test",
        "candidate_runtime_shadow_replay": "candidate-runtime-shadow:test",
    }


def test_short_odds_runtime_profile_activation_blocks_existing_default_rules() -> None:
    current_profile = _current_profile_set().model_dump(mode="json")
    current_profile["short_odds_replacement_rules"] = [_rule()]

    report = build_historical_short_odds_runtime_profile_activation_report(
        current_profile_set=current_profile,
        candidate_runtime_profile=_candidate_runtime_profile(),
        runtime_profile_promotion_report=_promotion_report(),
        candidate_runtime_shadow_replay_report=_candidate_runtime_shadow_replay_report(),
    )

    assert report.status == "blocked"
    assert report.activation_ready is False
    assert "current_profile_has_no_short_odds_rules" in report.blockers
    assert report.activated_profile_json["short_odds_replacement_rules"] == []


def test_short_odds_runtime_profile_activation_blocks_candidate_final_hit_harm() -> None:
    replay_report = _candidate_runtime_shadow_replay_report()
    replay_report["final_hit_harm_count_vs_original"] = 1

    report = build_historical_short_odds_runtime_profile_activation_report(
        current_profile_set=_current_profile_set(),
        candidate_runtime_profile=_candidate_runtime_profile(),
        runtime_profile_promotion_report=_promotion_report(),
        candidate_runtime_shadow_replay_report=replay_report,
    )

    assert report.status == "blocked"
    assert "candidate_runtime_final_hit_harm_count_vs_original" in report.blockers


def test_short_odds_runtime_profile_activation_cli_writes_outputs(
    tmp_path: Path,
) -> None:
    current_path = tmp_path / "current_profiles.json"
    candidate_path = tmp_path / "candidate_profile.json"
    promotion_path = tmp_path / "promotion.json"
    replay_path = tmp_path / "candidate_replay.json"
    activated_profile_output_path = tmp_path / "activated_profile.json"
    report_output_path = tmp_path / "activation_report.json"
    current_path.write_text(
        _json(_current_profile_set().model_dump(mode="json")),
        encoding="utf-8",
    )
    candidate_path.write_text(_json(_candidate_runtime_profile()), encoding="utf-8")
    promotion_path.write_text(_json(_promotion_report()), encoding="utf-8")
    replay_path.write_text(
        _json(_candidate_runtime_shadow_replay_report()),
        encoding="utf-8",
    )

    main(
        [
            "--current-profile-path",
            str(current_path),
            "--candidate-runtime-profile",
            str(candidate_path),
            "--runtime-profile-promotion-report",
            str(promotion_path),
            "--candidate-runtime-shadow-replay-report",
            str(replay_path),
            "--activated-profile-output-path",
            str(activated_profile_output_path),
            "--report-output-path",
            str(report_output_path),
            "--activated-profile-version",
            "activated-profile-cli-v1",
        ]
    )

    activated_profile = loads(
        activated_profile_output_path.read_text(encoding="utf-8")
    )
    activation_report = loads(report_output_path.read_text(encoding="utf-8"))

    assert activated_profile["profile_version"] == "activated-profile-cli-v1"
    assert activated_profile["short_odds_replacement_rules"]
    assert activated_profile["default_profile_written"] is False
    assert activation_report["status"] == "activation_ready"
    assert activation_report["default_profile_written"] is False


def test_short_odds_runtime_profile_activation_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--current-profile-path",
            "current.json",
            "--candidate-runtime-profile",
            "candidate.json",
            "--runtime-profile-promotion-report",
            "promotion.json",
            "--candidate-runtime-shadow-replay-report",
            "candidate-replay.json",
            "--activated-profile-output-path",
            "activated.json",
            "--report-output-path",
            "report.json",
            "--activated-profile-version",
            "custom-activated-profile",
            "--min-rule-count",
            "2",
            "--min-allowed-competition-count",
            "3",
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
            "--allow-non-ready-promotion",
            "--allow-failed-candidate-replay",
            "--allow-existing-short-odds-rules",
            "--allow-public-response-change",
            "--allow-production-change",
            "--dry-run",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert args.current_profile_path == Path("current.json")
    assert args.activated_profile_output_path == Path("activated.json")
    assert options.activated_profile_version == "custom-activated-profile"
    assert options.min_rule_count == 2
    assert options.min_allowed_competition_count == 3
    assert options.min_final_answer_count == 12
    assert options.min_changed_final_answer_count == 4
    assert options.min_final_answer_hit_rate_delta == 0.01
    assert options.min_roi_delta == 0.02
    assert options.min_profit_loss_delta == 0.03
    assert options.max_harm_count_vs_original == 1
    assert options.max_final_hit_harm_count_vs_original == 2
    assert options.max_profit_loss_harm_count_vs_original == 3
    assert options.min_average_hit_probability_delta_vs_original == -0.03
    assert options.require_promotion_ready is False
    assert options.require_candidate_profile_ready is False
    assert options.require_candidate_runtime_shadow_replay_passed is False
    assert options.require_no_current_short_odds_rules is False
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


def _candidate_runtime_profile(*, promotion_ready: bool = True) -> dict[str, object]:
    return {
        "profile_version": "candidate-profile-v1",
        "calculation_basis": "historical_short_odds_runtime_profile_promotion_v3_1",
        "status": "promotion_ready" if promotion_ready else "blocked",
        "promotion_ready": promotion_ready,
        "base_profile_version": "current-v1",
        "profiles": [],
        "short_odds_replacement_rules": [_rule()],
        "source_report_keys": {
            "production_proposal": "production-proposal:test",
            "promotion_smoke": "promotion-smoke:test",
            "runtime_shadow_replay": "runtime-shadow:test",
            "post_promotion_runtime_shadow_replay": "post-runtime-shadow:test",
            "rolling_admission": "rolling-admission:test",
        },
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "runtime_profile_written": False,
        "notes": ["candidate note"],
    }


def _promotion_report() -> dict[str, object]:
    return {
        "report_key": "runtime-profile-promotion:test",
        "status": "promotion_ready",
        "promotion_ready": True,
        "promoted_profile_version": "candidate-profile-v1",
        "current_profile_version": "current-v1",
        "source_production_proposal_report_key": "production-proposal:test",
        "source_promotion_smoke_report_key": "promotion-smoke:test",
        "source_runtime_shadow_replay_report_key": "runtime-shadow:test",
        "source_post_promotion_runtime_shadow_replay_report_key": (
            "post-runtime-shadow:test"
        ),
        "source_rolling_admission_report_key": "rolling-admission:test",
        "candidate_rule_count": 1,
        "allowed_competition_ids": [
            "EPL",
            "FRA_LIGUE_1",
            "GER_BUNDESLIGA",
            "ITA_SERIE_A",
        ],
        "excluded_competition_ids": ["ESP_LA_LIGA"],
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "runtime_profile_written": False,
        "checks": [],
        "blockers": [],
        "candidate_runtime_profile_json": _candidate_runtime_profile(),
        "warnings": [],
        "summary_json": {},
    }


def _candidate_runtime_shadow_replay_report() -> dict[str, object]:
    return {
        "report_key": "candidate-runtime-shadow:test",
        "status": "shadow_replay_passed",
        "passed": True,
        "source_audit_report_key": "audit:test",
        "source_rule_profile_version": "candidate-profile-v1",
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


def _rule() -> dict[str, object]:
    return {
        "rule_id": "short_odds_final_answer_replacement_v1",
        "profile_id": "max_short_odds_within_deficit_v1",
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
        "rollback_conditions": [
            "disable_if_production_harm_count_vs_original_exceeds_0",
            "disable_if_runtime_shadow_replay_report_missing_or_failed",
            "disable_if_rolling_admission_report_missing_or_failed",
        ],
        "notes": [],
    }


def _json(payload: dict[str, object]) -> str:
    return f"{dumps(payload)}\n"
