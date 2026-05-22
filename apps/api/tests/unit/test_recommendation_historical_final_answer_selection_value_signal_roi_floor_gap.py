from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_runtime_admission as admission,
)
from nutmeg.recommendations.historical_final_answer_selection_value_signal_roi_floor_gap import (
    build_historical_final_answer_selection_value_signal_roi_floor_gap_report,
    load_historical_final_answer_selection_value_signal_roi_floor_gap_report,
    main,
)
from nutmeg.recommendations.historical_final_answer_selection_value_signal_runtime_replay import (
    HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport,
)


def test_selection_value_signal_roi_floor_gap_quantifies_negative_roi_gap() -> None:
    runtime_replay = _runtime_replay(
        baseline_roi=-0.04,
        candidate_roi=-0.03,
        roi_delta=0.01,
        profit_loss_delta=4.0,
    )
    runtime_admission = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            runtime_replay
        )
    )

    report = build_historical_final_answer_selection_value_signal_roi_floor_gap_report(
        runtime_admission,
        runtime_replay=runtime_replay,
    )

    assert report.status == "gap_quantified"
    assert report.production_recommendation_allowed is False
    assert report.holdout_allowed is True
    assert report.failed_admission_check_names == ["candidate_roi"]
    assert report.candidate_roi_gap == 0.03
    assert report.required_roi_delta_for_floor == 0.04
    assert report.additional_roi_delta_needed == 0.03
    assert report.estimated_total_stake == 400.0
    assert report.baseline_profit_loss_estimate == -16.0
    assert report.candidate_profit_loss_estimate == -12.0
    assert report.required_profit_loss_delta_for_floor == 16.0
    assert report.additional_profit_loss_needed == 12.0
    assert report.average_profit_loss_delta_per_positive_movement == 4.0
    assert report.estimated_additional_clean_positive_movement_count == 3
    assert report.search_guidance_json["default_profile_action"] == "do_not_activate"


def test_selection_value_signal_roi_floor_gap_reports_no_gap_when_admitted() -> None:
    runtime_replay = _runtime_replay(
        baseline_roi=-0.04,
        candidate_roi=0.02,
        roi_delta=0.06,
        profit_loss_delta=24.0,
    )
    runtime_admission = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            runtime_replay
        )
    )

    report = build_historical_final_answer_selection_value_signal_roi_floor_gap_report(
        runtime_admission,
        runtime_replay=runtime_replay,
    )

    assert report.status == "no_gap"
    assert report.production_recommendation_allowed is True
    assert report.candidate_roi_gap == 0.0
    assert report.additional_roi_delta_needed == 0.0
    assert report.estimated_additional_clean_positive_movement_count == 0


def test_selection_value_signal_roi_floor_gap_blocks_rejected_admission() -> None:
    runtime_replay = _runtime_replay(
        baseline_roi=-0.04,
        candidate_roi=-0.03,
        roi_delta=0.01,
        profit_loss_delta=4.0,
        harmful_movement_count=1,
    )
    runtime_admission = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            runtime_replay
        )
    )

    report = build_historical_final_answer_selection_value_signal_roi_floor_gap_report(
        runtime_admission,
        runtime_replay=runtime_replay,
    )

    assert report.status == "blocked"
    assert report.holdout_allowed is False
    assert "harmful_movement_count" in report.failed_admission_check_names
    assert (
        "selection_value_signal_roi_floor_gap:unexpected_admission_failed_check:"
        "harmful_movement_count"
    ) in report.warnings


def test_selection_value_signal_roi_floor_gap_cli_writes_report(tmp_path: Path) -> None:
    runtime_replay = _runtime_replay(
        baseline_roi=-0.04,
        candidate_roi=-0.03,
        roi_delta=0.01,
        profit_loss_delta=4.0,
    )
    runtime_admission = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            runtime_replay
        )
    )
    admission_path = tmp_path / "runtime_admission.json"
    replay_path = tmp_path / "runtime_replay.json"
    output_path = tmp_path / "roi_floor_gap.json"
    admission_path.write_text(
        f"{runtime_admission.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    replay_path.write_text(
        f"{runtime_replay.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            str(admission_path),
            "--runtime-replay-report",
            str(replay_path),
            "--output-path",
            str(output_path),
            "--candidate-roi-floor",
            "0.0",
        ]
    )

    saved = load_historical_final_answer_selection_value_signal_roi_floor_gap_report(
        output_path
    )
    payload = loads(output_path.read_text(encoding="utf-8"))
    assert saved.status == "gap_quantified"
    assert payload["source_runtime_admission_report_key"] == runtime_admission.report_key
    assert payload["source_runtime_replay_report_key"] == runtime_replay.report_key


def _runtime_replay(
    *,
    baseline_roi: float,
    candidate_roi: float,
    roi_delta: float,
    profit_loss_delta: float,
    harmful_movement_count: int = 0,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport:
    status = (
        "shadow_replay_failed"
        if harmful_movement_count
        else "runtime_replay_passed"
    )
    return HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport(
        report_key="historical_final_answer_selection_value_signal_runtime_replay:test",
        status=status,
        runtime_replay_allowed=status == "runtime_replay_passed",
        holdout_replay_allowed=status == "runtime_replay_passed",
        source_rule_profile_version="runtime-profile:test",
        rule_count=1,
        selected_rule_count=1,
        final_answer_count=180,
        changed_final_answer_count=1,
        affected_leg_count=1,
        guard_blocked_option_count=7,
        movement_count=1,
        positive_movement_count=1,
        harmful_movement_count=harmful_movement_count,
        probability_quality_harm_movement_count=0,
        clean_positive_movement_count=1,
        baseline_final_answer_hit_count=127,
        candidate_final_answer_hit_count=127,
        final_answer_hit_delta_count=0,
        final_answer_hit_rate_delta=0.0,
        baseline_roi=baseline_roi,
        candidate_roi=candidate_roi,
        roi_delta=roi_delta,
        profit_loss_delta=profit_loss_delta,
        brier_score_delta=-0.001,
        log_loss_delta=-0.002,
        mean_calibration_error_delta=-0.003,
        final_hit_harm_count_vs_baseline=0,
        profit_loss_harm_count_vs_baseline=0,
    )
