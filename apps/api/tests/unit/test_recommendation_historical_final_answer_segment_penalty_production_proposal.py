from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.historical_final_answer_segment_penalty_grid import (
    HistoricalFinalAnswerSegmentPenaltyCandidate,
    HistoricalFinalAnswerSegmentPenaltyGridReport,
)
from nutmeg.recommendations.historical_final_answer_segment_penalty_production_proposal import (
    _options_from_args,
    _parse_args,
    build_historical_final_answer_segment_penalty_production_proposal_report,
    load_historical_final_answer_segment_penalty_grid_report,
    load_historical_final_answer_segment_penalty_rolling_admission_report,
    main,
)
from nutmeg.recommendations.historical_final_answer_segment_penalty_rolling_admission import (
    HistoricalFinalAnswerSegmentPenaltyFold,
    HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport,
)


def test_segment_penalty_production_proposal_ready_when_absolute_roi_passes() -> None:
    report = build_historical_final_answer_segment_penalty_production_proposal_report(
        _grid_report(candidate_roi=0.04),
        _rolling_admission_report(),
    )

    assert report.status == "runtime_profile_proposal_ready"
    assert report.runtime_profile_proposal_allowed is True
    assert report.holdout_candidate_allowed is True
    assert report.proposal_count == 1
    assert all(check.status == "passed" for check in report.checks)
    assert report.proposal_rule is not None
    assert report.proposal_rule.proposed_production_enabled is True
    assert report.proposal_rule.holdout_candidate_enabled is True
    assert report.proposal_rule.season_ids == []
    assert report.proposal_rule.min_competition_season_index == 4
    assert report.proposal_rule.constraints_json[
        "final_answer_segment_min_competition_season_index"
    ] == 4
    assert report.proposal_rule.evidence_json["final_answer_hit_delta_count"] == 2
    assert (
        "disable_if_absolute_candidate_roi_below_0.0"
        in report.proposal_rule.rollback_conditions
    )
    assert report.proposal_profile_set_json["final_answer_segment_penalty_rules"]


def test_segment_penalty_production_proposal_holdout_only_when_roi_floor_fails() -> None:
    report = build_historical_final_answer_segment_penalty_production_proposal_report(
        _grid_report(candidate_roi=-0.015),
        _rolling_admission_report(),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "holdout_only"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is True
    assert failed_checks == {"candidate_roi"}
    assert report.proposal_rule is not None
    assert report.proposal_rule.proposed_production_enabled is False
    assert report.proposal_rule.holdout_candidate_enabled is True
    assert (
        "final_answer_segment_penalty_production_proposal:holdout_only"
        in report.warnings
    )


def test_segment_penalty_production_proposal_blocks_hindsight_season_ids() -> None:
    report = build_historical_final_answer_segment_penalty_production_proposal_report(
        _grid_report(candidate_roi=0.04, season_ids=("2023-2024",)),
        _rolling_admission_report(),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is False
    assert "explicit_season_ids_absent" in failed_checks
    assert report.proposal_rule is None


def test_segment_penalty_production_proposal_blocks_failed_rolling_admission() -> None:
    report = build_historical_final_answer_segment_penalty_production_proposal_report(
        _grid_report(candidate_roi=0.04),
        _rolling_admission_report(accepted=False),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is False
    assert "rolling_admission_status" in failed_checks
    assert "failed_fold_count" in failed_checks
    assert report.proposal_rule is None


def test_segment_penalty_production_proposal_blocks_profit_loss_harm() -> None:
    report = build_historical_final_answer_segment_penalty_production_proposal_report(
        _grid_report(candidate_roi=0.04),
        _rolling_admission_report(profit_loss_harm_count=1),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is False
    assert "profit_loss_harm_count_vs_baseline" in failed_checks
    assert report.proposal_rule is None


def test_segment_penalty_production_proposal_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    grid_path = tmp_path / "grid.json"
    rolling_path = tmp_path / "rolling.json"
    output_path = tmp_path / "proposal.json"
    profile_path = tmp_path / "profile.json"
    grid_path.write_text(
        f"{_grid_report(candidate_roi=0.04).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    rolling_path.write_text(
        f"{_rolling_admission_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--grid-report",
            str(grid_path),
            "--rolling-admission-report",
            str(rolling_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_path),
            "--proposal-id",
            "custom-segment-rule",
            "--proposed-profile-version",
            "custom-segment-profile",
            "--min-final-answer-count",
            "20",
            "--min-changed-final-answer-count",
            "2",
            "--min-penalty-option-count",
            "2",
            "--min-final-answer-hit-count-delta",
            "1",
            "--min-final-answer-hit-rate-delta",
            "0.01",
            "--min-roi-delta",
            "0.02",
            "--min-profit-loss-delta",
            "1.0",
            "--min-candidate-roi",
            "0.01",
            "--max-brier-score-delta",
            "0.01",
            "--max-log-loss-delta",
            "0.01",
            "--max-mean-calibration-error-delta",
            "0.01",
            "--max-harm-count-vs-baseline",
            "1",
            "--max-final-hit-harm-count-vs-baseline",
            "2",
            "--max-profit-loss-harm-count-vs-baseline",
            "3",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-fold-count",
            "2",
            "--min-active-rolling-fold-count",
            "2",
            "--max-failed-fold-count",
            "0",
            "--allow-rejected-grid-candidate",
            "--allow-unaccepted-rolling-admission",
            "--allow-non-regime-filter",
            "--allow-explicit-season-ids",
            "--allow-source-key-mismatch",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert options.proposal_id == "custom-segment-rule"
    assert options.proposed_profile_version == "custom-segment-profile"
    assert options.min_final_answer_count == 20
    assert options.min_changed_final_answer_count == 2
    assert options.min_penalty_option_count == 2
    assert options.min_final_answer_hit_count_delta == 1
    assert options.min_final_answer_hit_rate_delta == 0.01
    assert options.min_roi_delta == 0.02
    assert options.min_profit_loss_delta == 1.0
    assert options.min_candidate_roi == 0.01
    assert options.max_brier_score_delta == 0.01
    assert options.max_log_loss_delta == 0.01
    assert options.max_mean_calibration_error_delta == 0.01
    assert options.max_harm_count_vs_baseline == 1
    assert options.max_final_hit_harm_count_vs_baseline == 2
    assert options.max_profit_loss_harm_count_vs_baseline == 3
    assert options.require_grid_candidate_accepted is False
    assert options.require_rolling_admission_accepted is False
    assert options.require_forward_safe_regime_filter is False
    assert options.require_no_explicit_season_ids is False
    assert options.require_source_key_linkage is False
    assert load_historical_final_answer_segment_penalty_grid_report(
        grid_path
    ).report_key == "segment-grid:test"
    assert load_historical_final_answer_segment_penalty_rolling_admission_report(
        rolling_path
    ).report_key == "segment-rolling:test"

    main(
        [
            "--grid-report",
            str(grid_path),
            "--rolling-admission-report",
            str(rolling_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_path),
            "--min-changed-final-answer-count",
            "2",
            "--min-penalty-option-count",
            "2",
            "--min-candidate-roi",
            "0.01",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    profile = loads(profile_path.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_profile_proposal_ready"
    assert payload["runtime_profile_proposal_allowed"] is True
    assert profile["final_answer_segment_penalty_rules"][0]["rule_id"] == (
        "final_answer_segment_penalty_regime_v1"
    )


def _grid_report(
    *,
    candidate_roi: float,
    season_ids: tuple[str, ...] = (),
) -> HistoricalFinalAnswerSegmentPenaltyGridReport:
    candidate = HistoricalFinalAnswerSegmentPenaltyCandidate(
        candidate_key="segment-candidate:test",
        status="accepted",
        pass_types=("3x1",),
        modes=("single",),
        competition_ids=("GER_BUNDESLIGA",),
        season_ids=season_ids,
        min_competition_season_index=4,
        strength=0.02,
        suite_key="candidate-suite:test",
        suite_status="unchanged",
        penalty_option_count=2,
        final_hit_sample_size=30,
        final_hit_count=25,
        final_hit_rate=25 / 30,
        roi=candidate_roi,
        profit_loss=2.4,
        brier_score=0.12,
        log_loss=0.42,
        mean_calibration_error=0.08,
        final_answer_changed_count=2,
        objective_improvement_satisfied=True,
        objective_improvement_metric_codes=[
            "final_hit_count_delta",
            "roi_delta",
            "profit_loss_delta",
        ],
    )
    return HistoricalFinalAnswerSegmentPenaltyGridReport(
        report_key="segment-grid:test",
        status="generated",
        slice_count=30,
        fixture_count=300,
        prediction_count=900,
        total_grid_candidate_count=1,
        candidate_count=1,
        accepted_count=1,
        rejected_count=0,
        baseline_suite_key="baseline-suite:test",
        baseline_suite_status="unchanged",
        candidates=[candidate],
        accepted_candidates=[candidate],
        best_candidate=candidate,
    )


def _rolling_admission_report(
    *,
    accepted: bool = True,
    final_hit_harm_count: int = 0,
    profit_loss_harm_count: int = 0,
) -> HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport:
    return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport(
        report_key="segment-rolling:test",
        status="accepted" if accepted else "shadow_only",
        candidate_profile_allowed=accepted,
        shadow_allowed=True,
        source_grid_report_key="segment-grid:test",
        source_candidate_key="segment-candidate:test",
        candidate_summary_json={},
        overall_fold=HistoricalFinalAnswerSegmentPenaltyFold(
            fold_id="overall:all",
            fold_type="overall",
            status="passed" if accepted else "failed",
            source_slice_ids=["slice-1"],
            final_answer_count=30,
            penalty_option_count=2,
            changed_final_answer_count=2,
            baseline_final_answer_hit_count=23,
            candidate_final_answer_hit_count=25 if accepted else 22,
            final_answer_hit_delta_count=2 if accepted else -1,
            final_answer_hit_rate_delta=2 / 30 if accepted else -1 / 30,
            roi_delta=0.07 if accepted else -0.02,
            profit_loss_delta=4.2 if accepted else -1.0,
            brier_score_delta=-0.03 if accepted else 0.01,
            log_loss_delta=-0.07 if accepted else 0.01,
            mean_calibration_error_delta=-0.04 if accepted else 0.01,
            harm_count_vs_baseline=final_hit_harm_count if accepted else 1,
            final_hit_harm_count_vs_baseline=(
                final_hit_harm_count if accepted else 1
            ),
            profit_loss_harm_count_vs_baseline=(
                profit_loss_harm_count if accepted else 1
            ),
            improvement_count_vs_baseline=2 if accepted else 0,
        ),
        fold_count=5,
        active_fold_count=5,
        failed_fold_count=0 if accepted else 1,
        active_competition_fold_count=1,
        active_season_fold_count=2,
        active_rolling_fold_count=2,
        checks=[],
        folds=[],
    )
