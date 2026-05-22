from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_runtime_admission as admission,
)
from nutmeg.recommendations.historical_final_answer_selection_value_signal_runtime_replay import (
    HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_model_quality_gate import (
    HistoricalProbabilityCalibrationProfileModelQualityGateReport,
)


def test_selection_value_signal_runtime_admission_accepts_positive_roi() -> None:
    report = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            _runtime_replay(candidate_roi=0.04)
        )
    )

    assert report.status == "accepted"
    assert report.production_recommendation_allowed is True
    assert report.holdout_allowed is True
    assert all(check.status == "passed" for check in report.checks)
    assert report.decision_payload_json["default_recommendation_path_changed"] is False


def test_selection_value_signal_runtime_admission_holdout_only_for_negative_roi() -> None:
    report = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            _runtime_replay(candidate_roi=-0.03)
        )
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "holdout_only"
    assert report.production_recommendation_allowed is False
    assert report.holdout_allowed is True
    assert failed_checks == {"candidate_roi"}
    assert "selection_value_signal_runtime_admission:holdout_only" in report.warnings


def test_selection_value_signal_runtime_admission_rejects_harmful_movement() -> None:
    report = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            _runtime_replay(
                candidate_roi=0.04,
                harmful_movement_count=1,
                final_hit_harm_count=1,
            )
        )
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.production_recommendation_allowed is False
    assert report.holdout_allowed is False
    assert "harmful_movement_count" in failed_checks
    assert "final_hit_harm_count_vs_baseline" in failed_checks


def test_selection_value_signal_runtime_admission_uses_model_quality_guardrail() -> None:
    report = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            _runtime_replay(candidate_roi=0.04),
            probability_calibration_model_quality_gate=_model_quality_gate(),
            options=admission.HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions(
                require_probability_calibration_model_quality_gate=True,
                min_probability_calibration_model_quality_selected_competition_count=4,
                min_probability_calibration_model_quality_adjusted_fixture_count=96,
                max_probability_calibration_model_quality_final_answer_changed_count=0,
            ),
        )
    )

    assert report.status == "accepted"
    assert report.probability_calibration_model_quality_gate_present is True
    assert report.probability_calibration_model_quality_gate_ready is True
    assert (
        report.summary_json["probability_calibration_model_quality_gate_report_key"]
        == "historical_probability_calibration_profile_model_quality_gate:test"
    )
    assert (
        report.decision_payload_json[
            "requires_probability_calibration_model_quality_gate"
        ]
        is True
    )


def test_selection_value_signal_runtime_admission_blocks_missing_model_quality_guardrail() -> None:
    report = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            _runtime_replay(candidate_roi=0.04),
            options=admission.HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions(
                require_probability_calibration_model_quality_gate=True,
            ),
        )
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.holdout_allowed is False
    assert "probability_calibration_model_quality_gate_present" in failed_checks


def test_selection_value_signal_runtime_admission_blocks_model_quality_regression() -> None:
    report = (
        admission.build_historical_final_answer_selection_value_signal_runtime_admission_report(
            _runtime_replay(candidate_roi=0.04),
            probability_calibration_model_quality_gate=_model_quality_gate(
                status="blocked",
                model_quality_gate_passed=False,
                selected_competition_ids=["EPL"],
                adjusted_fixture_count=12,
                final_answer_changed_count=2,
                brier_score_delta=0.01,
                log_loss_delta=0.02,
                mean_calibration_error_delta=0.03,
            ),
            options=admission.HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions(
                require_probability_calibration_model_quality_gate=True,
                min_probability_calibration_model_quality_selected_competition_count=4,
                min_probability_calibration_model_quality_adjusted_fixture_count=96,
            ),
        )
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert {
        "probability_calibration_model_quality_gate_ready",
        "probability_calibration_model_quality_selected_competition_count",
        "probability_calibration_model_quality_adjusted_fixture_count",
        "probability_calibration_model_quality_final_answer_changed_count",
        "probability_calibration_model_quality_brier_score_delta",
        "probability_calibration_model_quality_log_loss_delta",
        "probability_calibration_model_quality_calibration_error_delta",
    }.issubset(failed_checks)


def test_selection_value_signal_runtime_admission_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "runtime_replay.json"
    model_quality_path = tmp_path / "model_quality_gate.json"
    output_path = tmp_path / "admission.json"
    source_path.write_text(
        f"{_runtime_replay(candidate_roi=-0.03).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    model_quality_path.write_text(
        f"{_model_quality_gate().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = admission._parse_args(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--min-rule-count",
            "1",
            "--min-selected-rule-count",
            "1",
            "--max-selected-rule-count",
            "1",
            "--min-final-answer-count",
            "100",
            "--min-changed-final-answer-count",
            "1",
            "--min-affected-leg-count",
            "1",
            "--min-positive-movement-count",
            "1",
            "--max-harmful-movement-count",
            "0",
            "--max-probability-quality-harm-movement-count",
            "0",
            "--min-final-answer-hit-delta-count",
            "0",
            "--min-roi-delta",
            "0.0",
            "--min-profit-loss-delta",
            "0.0",
            "--min-candidate-roi",
            "0.0",
            "--max-brier-score-delta",
            "0.0",
            "--max-log-loss-delta",
            "0.0",
            "--max-mean-calibration-error-delta",
            "0.0",
            "--max-final-hit-harm-count-vs-baseline",
            "0",
            "--max-profit-loss-harm-count-vs-baseline",
            "0",
            "--probability-calibration-model-quality-gate-report",
            str(model_quality_path),
            "--require-probability-calibration-model-quality-gate",
            "--allow-probability-calibration-model-quality-not-ready",
            "--min-probability-calibration-model-quality-selected-competition-count",
            "4",
            "--min-probability-calibration-model-quality-adjusted-fixture-count",
            "96",
            "--max-probability-calibration-model-quality-final-answer-changed-count",
            "0",
            "--max-probability-calibration-model-quality-brier-score-delta",
            "0.01",
            "--max-probability-calibration-model-quality-log-loss-delta",
            "0.02",
            "--max-probability-calibration-model-quality-calibration-error-delta",
            "0.03",
            "--allow-runtime-replay-not-allowed",
            "--allow-holdout-replay-not-allowed",
            "--allow-runtime-replay-non-passed-status",
            "--allow-production-change",
            "--allow-public-response-change",
            "--no-fail-process",
        ]
    )
    options = admission._options_from_args(args)

    assert options.min_candidate_roi == 0.0
    assert options.require_probability_calibration_model_quality_gate is True
    assert options.require_probability_calibration_model_quality_ready is False
    assert (
        options.min_probability_calibration_model_quality_selected_competition_count
        == 4
    )
    assert options.min_probability_calibration_model_quality_adjusted_fixture_count == 96
    assert (
        options.max_probability_calibration_model_quality_final_answer_changed_count
        == 0
    )
    assert options.max_probability_calibration_model_quality_brier_score_delta == 0.01
    assert options.max_probability_calibration_model_quality_log_loss_delta == 0.02
    assert (
        options.max_probability_calibration_model_quality_calibration_error_delta
        == 0.03
    )
    assert options.require_runtime_replay_allowed is False
    assert options.require_holdout_replay_allowed is False
    assert options.require_runtime_replay_passed_status is False
    assert options.require_no_production_change is False
    assert options.require_no_public_response_change is False

    admission.main(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--probability-calibration-model-quality-gate-report",
            str(model_quality_path),
            "--require-probability-calibration-model-quality-gate",
            "--min-candidate-roi",
            "0.0",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "holdout_only"
    assert payload["production_recommendation_allowed"] is False
    assert payload["holdout_allowed"] is True
    assert payload["source_runtime_replay_report_key"] == (
        "historical_final_answer_selection_value_signal_runtime_replay:test"
    )


def _runtime_replay(
    *,
    candidate_roi: float,
    harmful_movement_count: int = 0,
    final_hit_harm_count: int = 0,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport:
    status = (
        "shadow_replay_failed"
        if harmful_movement_count or final_hit_harm_count
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
        candidate_final_answer_hit_count=127 - final_hit_harm_count,
        final_answer_hit_delta_count=0 - final_hit_harm_count,
        final_answer_hit_rate_delta=0.0,
        baseline_roi=-0.04,
        candidate_roi=candidate_roi,
        roi_delta=0.01,
        profit_loss_delta=4.0,
        brier_score_delta=-0.001,
        log_loss_delta=-0.002,
        mean_calibration_error_delta=-0.003,
        final_hit_harm_count_vs_baseline=final_hit_harm_count,
        profit_loss_harm_count_vs_baseline=0,
    )


def _model_quality_gate(
    *,
    status: str = "model_quality_ready",
    model_quality_gate_passed: bool = True,
    selected_competition_ids: list[str] | None = None,
    adjusted_fixture_count: int = 96,
    final_answer_changed_count: int = 0,
    brier_score_delta: float | None = -0.01,
    log_loss_delta: float | None = -0.02,
    mean_calibration_error_delta: float | None = -0.01,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateReport:
    return HistoricalProbabilityCalibrationProfileModelQualityGateReport.model_validate(
        {
            "report_key": (
                "historical_probability_calibration_profile_model_quality_gate:test"
            ),
            "status": status,
            "gate_id": "selection-value-model-quality-test",
            "profile_gate_report_key": (
                "historical_probability_calibration_profile_gate:test"
            ),
            "model_quality_gate_passed": model_quality_gate_passed,
            "selected_competition_ids": selected_competition_ids
            or ["BUNDESLIGA", "EPL", "LA_LIGA", "SERIE_A"],
            "adjusted_slice_count": 4,
            "adjusted_fixture_count": adjusted_fixture_count,
            "skipped_fixture_count": 0,
            "final_answer_changed_count": final_answer_changed_count,
            "final_answer_hit_count_delta": 0,
            "final_answer_hit_rate_delta": 0.0,
            "roi_delta": 0.0,
            "profit_loss_delta": 0.0,
            "brier_score_delta": brier_score_delta,
            "log_loss_delta": log_loss_delta,
            "mean_calibration_error_delta": mean_calibration_error_delta,
            "checks": [],
            "warnings": [],
            "summary_json": {
                "report_key": (
                    "historical_probability_calibration_profile_model_quality_gate:test"
                ),
                "status": status,
            },
        }
    )
