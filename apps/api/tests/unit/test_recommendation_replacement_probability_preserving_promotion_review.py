from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.replacement_probability_preserving_promotion_review import (
    _options_from_args,
    _parse_args,
    build_historical_replacement_probability_preserving_promotion_review_report,
    load_historical_replacement_probability_preserving_promotion_review_report,
    main,
)
from nutmeg.recommendations.replacement_probability_preserving_runtime_dry_run import (
    HistoricalReplacementProbabilityPreservingRuntimeDryRunReport,
)


def test_probability_preserving_promotion_review_is_ready_for_shadow_candidate() -> None:
    report = build_historical_replacement_probability_preserving_promotion_review_report(
        _runtime_dry_run_report()
    )

    assert report.status == "promotion_review_ready"
    assert report.promotion_review_allowed is True
    assert report.production_recommendation_allowed is False
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert report.candidate_rule_count == 1
    assert report.allowed_competition_ids == [
        "ENG_CHAMPIONSHIP",
        "ESP_SEGUNDA_DIVISION",
        "FRA_LIGUE_2",
        "GER_2_BUNDESLIGA",
        "ITA_SERIE_B",
    ]
    assert report.review_profile_json["dry_run_only"] is True
    assert report.review_profile_json["rules"]
    assert all(check.status == "passed" for check in report.checks)


def test_probability_preserving_promotion_review_blocks_failed_runtime_dry_run() -> None:
    dry_run = _runtime_dry_run_report().model_copy(
        update={
            "status": "runtime_dry_run_watchlist",
            "shadow_runtime_candidate_allowed": False,
            "harm_count_vs_original": 1,
            "final_hit_harm_count_vs_original": 1,
            "profit_loss_harm_count_vs_original": 1,
        }
    )

    report = build_historical_replacement_probability_preserving_promotion_review_report(
        dry_run
    )

    assert report.status == "blocked"
    assert report.promotion_review_allowed is False
    assert report.candidate_rule_count == 0
    assert report.review_profile_json["rules"] == []
    assert "runtime_dry_run_status" in report.blockers
    assert "harm_count_vs_original" in report.blockers


def test_probability_preserving_promotion_review_watchlists_missing_original_hit_guard() -> None:
    dry_run = _runtime_dry_run_report()
    profile = dict(dry_run.runtime_proposal_profile_set_json)
    rule = dict(profile["rules"][0])  # type: ignore[index]
    constraints = dict(rule["constraints_json"])  # type: ignore[index]
    constraints.pop("exclude_original_hit_harm")
    rule["constraints_json"] = constraints
    profile["rules"] = [rule]

    report = build_historical_replacement_probability_preserving_promotion_review_report(
        dry_run.model_copy(update={"runtime_proposal_profile_set_json": profile})
    )

    assert report.status == "promotion_review_watchlist"
    assert "exclude_original_hit_harm_constraint" in report.blockers
    assert report.production_recommendation_allowed is False


def test_probability_preserving_promotion_review_cli_options_and_main(
    tmp_path: Path,
) -> None:
    dry_run_path = tmp_path / "runtime_dry_run.json"
    report_path = tmp_path / "review_report.json"
    profile_path = tmp_path / "review_profile.json"
    dry_run_path.write_text(
        f"{_runtime_dry_run_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--runtime-dry-run-report",
            str(dry_run_path),
            "--report-output-path",
            str(report_path),
            "--profile-output-path",
            str(profile_path),
            "--review-id",
            "unit-review",
            "--reviewed-profile-version",
            "unit-profile",
            "--min-final-answer-count",
            "99",
            "--min-changed-final-answer-count",
            "13",
            "--min-active-surface-count",
            "8",
            "--min-active-competition-fold-count",
            "5",
            "--min-active-season-fold-count",
            "5",
            "--min-active-rolling-fold-count",
            "13",
            "--allow-public-response-change",
        ]
    )
    options = _options_from_args(args)

    assert options.review_id == "unit-review"
    assert options.reviewed_profile_version == "unit-profile"
    assert options.min_final_answer_count == 99
    assert options.require_no_public_response_change is False

    main(
        [
            "--runtime-dry-run-report",
            str(dry_run_path),
            "--report-output-path",
            str(report_path),
            "--profile-output-path",
            str(profile_path),
            "--reviewed-profile-version",
            "unit-profile",
            "--min-final-answer-count",
            "99",
            "--min-changed-final-answer-count",
            "13",
            "--min-active-surface-count",
            "8",
            "--min-active-competition-fold-count",
            "5",
            "--min-active-season-fold-count",
            "5",
            "--min-active-rolling-fold-count",
            "13",
        ]
    )

    saved = load_historical_replacement_probability_preserving_promotion_review_report(
        report_path
    )
    assert saved.status == "promotion_review_ready"
    assert profile_path.exists()


def _runtime_dry_run_report() -> HistoricalReplacementProbabilityPreservingRuntimeDryRunReport:
    return HistoricalReplacementProbabilityPreservingRuntimeDryRunReport(
        report_key="historical_replacement_probability_preserving_runtime_dry_run:test",
        status="runtime_dry_run_passed",
        shadow_runtime_candidate_allowed=True,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        source_audit_report_key="audit:test",
        source_grid_report_key="grid:test",
        source_surface_replay_report_key="surface:test",
        source_admission_report_key="admission:test",
        selected_candidate_key="replacement_probability_preserving_candidate:test",
        selected_candidate_status="accepted",
        generated_runtime_shadow_replay_report_key="runtime-shadow:test",
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
        runtime_proposal_profile_set_json=_profile_set_json(),
        runtime_shadow_replay_summary_json={
            "report_key": "runtime-shadow:test",
            "status": "shadow_replay_passed",
            "passed": True,
        },
        changed_items_json=[],
        warnings=[],
        summary_json={},
    )


def _profile_set_json() -> dict[str, object]:
    return {
        "profile_version": "runtime-dry-run-v1",
        "dry_run_only": True,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "rules": [
            {
                "rule_id": "probability_preserving_runtime_dry_run:test",
                "profile_id": "nearest_model_top_probability",
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
            }
        ],
        "notes": ["dry_run_only"],
    }
