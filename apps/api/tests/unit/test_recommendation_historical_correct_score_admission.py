from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations import historical_correct_score_admission as admission
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateCheck,
    HistoricalRecommendationSuiteQualityGateResult,
)


def test_correct_score_admission_accepts_no_harm_covered_correct_score() -> None:
    report = admission.build_historical_correct_score_admission_report(
        _source_gate(correct_score_count=4, candidate_roi=0.04)
    )

    assert report.status == "accepted"
    assert report.production_recommendation_allowed is True
    assert report.holdout_allowed is True
    assert all(check.status == "passed" for check in report.checks)
    assert report.decision_payload_json["default_recommendation_path_changed"] is False


def test_correct_score_admission_holds_out_when_correct_score_never_selected() -> None:
    report = admission.build_historical_correct_score_admission_report(
        _source_gate(correct_score_count=0, candidate_roi=0.04)
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "holdout_only"
    assert report.production_recommendation_allowed is False
    assert report.holdout_allowed is True
    assert failed_checks == {"candidate_correct_score_final_answer_count"}
    assert "correct_score_admission:holdout_only" in report.warnings


def test_correct_score_admission_rejects_no_harm_regression() -> None:
    report = admission.build_historical_correct_score_admission_report(
        _source_gate(
            correct_score_count=4,
            candidate_roi=0.04,
            roi_delta=-0.02,
            brier_score_delta=0.01,
        )
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.production_recommendation_allowed is False
    assert report.holdout_allowed is False
    assert {"roi_delta", "brier_score_delta"}.issubset(failed_checks)


def test_correct_score_admission_prefers_correct_score_profile_reference_deltas() -> None:
    report = admission.build_historical_correct_score_admission_report(
        _source_gate(
            correct_score_count=4,
            candidate_roi=0.04,
            profile_reference_correct_score_disabled=True,
            profile_reference_deltas={
                "final_hit_rate_delta": -0.01,
                "roi_delta": -0.02,
                "profit_loss_delta": -3.0,
                "brier_score_delta": 0.01,
                "log_loss_delta": 0.02,
                "mean_calibration_error_delta": 0.03,
            },
        )
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.no_harm_delta_basis == "profile_reference_deltas"
    assert report.summary_json["no_harm_delta_basis"] == "profile_reference_deltas"
    assert {
        "final_hit_rate_delta",
        "roi_delta",
        "profit_loss_delta",
        "brier_score_delta",
        "log_loss_delta",
        "mean_calibration_error_delta",
    }.issubset(failed_checks)


def test_correct_score_admission_cli_options_loader_and_main(tmp_path: Path) -> None:
    source_path = tmp_path / "source_gate.json"
    output_path = tmp_path / "admission.json"
    source_path.write_text(
        f"{_source_gate(correct_score_count=0, candidate_roi=0.04).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = admission._parse_args(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--min-slice-count",
            "10",
            "--min-comparison-count",
            "10",
            "--min-final-hit-sample-size",
            "10",
            "--min-candidate-final-hit-coverage-ratio",
            "1.0",
            "--min-candidate-final-hit-rate",
            "0.5",
            "--min-candidate-roi",
            "0.0",
            "--min-candidate-correct-score-final-answer-count",
            "1",
            "--min-candidate-correct-score-final-answer-rate",
            "0.01",
            "--min-final-hit-rate-delta",
            "0.0",
            "--min-roi-delta",
            "0.0",
            "--min-profit-loss-delta",
            "0.0",
            "--max-brier-score-delta",
            "0.0",
            "--max-log-loss-delta",
            "0.0",
            "--max-mean-calibration-error-delta",
            "0.0",
            "--max-failed-check-count",
            "0",
            "--allow-source-gate-failed",
            "--fail-on-suite-statuses",
            "regressed,mixed",
            "--allow-production-change",
            "--allow-public-response-change",
            "--no-fail-process",
        ]
    )
    options = admission._options_from_args(args)

    assert options.min_slice_count == 10
    assert options.min_candidate_final_hit_rate == 0.5
    assert options.min_candidate_correct_score_final_answer_rate == 0.01
    assert options.require_source_gate_passed is False
    assert options.fail_on_suite_statuses == ("regressed", "mixed")
    assert options.require_no_production_change is False
    assert options.require_no_public_response_change is False

    admission.main(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "holdout_only"
    assert payload["production_recommendation_allowed"] is False
    assert payload["holdout_allowed"] is True
    assert payload["source_gate_key"] == "historical_recommendation_suite_gate:test"


def _source_gate(
    *,
    correct_score_count: int,
    candidate_roi: float,
    roi_delta: float = 0.01,
    brier_score_delta: float = -0.01,
    profile_reference_correct_score_disabled: bool = False,
    profile_reference_deltas: dict[str, float] | None = None,
) -> HistoricalRecommendationSuiteQualityGateResult:
    comparison_count = 100
    aggregate_deltas = {
        "final_hit_rate_delta": 0.01,
        "roi_delta": roi_delta,
        "profit_loss_delta": 5.0,
        "brier_score_delta": brier_score_delta,
        "log_loss_delta": -0.01,
        "mean_calibration_error_delta": -0.01,
    }
    return HistoricalRecommendationSuiteQualityGateResult(
        gate_key="historical_recommendation_suite_gate:test",
        status="passed",
        passed=True,
        suite_key="historical_recommendation_suite:test",
        suite_status="improved",
        checks=[
            HistoricalRecommendationSuiteQualityGateCheck(
                name="source",
                status="passed",
                actual=True,
                threshold=True,
                detail="source gate passed",
            )
        ],
        aggregate_deltas_json=aggregate_deltas,
        summary_json={
            "status": "passed",
            "suite_status": "improved",
            "slice_count": 100,
            "comparison_count": comparison_count,
            "candidate_final_hit_sample_size": 100,
            "candidate_final_hit_coverage_ratio": 1.0,
            "candidate_final_hit_rate": 0.65,
            "candidate_roi": candidate_roi,
            "candidate_correct_score_final_answer_count": correct_score_count,
            "profile_reference_correct_score_final_answer_lane_disabled": (
                profile_reference_correct_score_disabled
            ),
            "profile_reference_deltas": profile_reference_deltas or {},
            "aggregate_deltas": aggregate_deltas,
            "failed_checks": [],
        },
    )
