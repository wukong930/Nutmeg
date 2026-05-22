from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    HistoricalProbabilityCalibrationProfileGateReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_model_quality_gate import (
    HistoricalProbabilityCalibrationProfileModelQualityGateOptions,
    _options_from_args,
    _parse_args,
    build_historical_probability_calibration_profile_model_quality_gate_report,
    load_historical_probability_calibration_profile_model_quality_gate_report,
)


def test_model_quality_gate_accepts_shadow_probability_improvement() -> None:
    report = build_historical_probability_calibration_profile_model_quality_gate_report(
        _profile_gate_report(),
        options=HistoricalProbabilityCalibrationProfileModelQualityGateOptions(
            min_selected_competition_count=2,
            min_adjusted_slice_count=4,
            min_adjusted_fixture_count=90,
        ),
    )

    assert report.status == "model_quality_ready"
    assert report.model_quality_gate_passed is True
    assert report.final_answer_changed_count == 0
    assert report.brier_score_delta == -0.013
    assert report.log_loss_delta == -0.027
    assert report.mean_calibration_error_delta == -0.008
    assert report.summary_json["profile_gate_quality_gate_passed"] is False
    assert not [check for check in report.checks if check.status == "failed"]


def test_model_quality_gate_blocks_probability_regression() -> None:
    report = build_historical_probability_calibration_profile_model_quality_gate_report(
        _profile_gate_report(
            aggregate_deltas_json={
                "final_answer_changed_count": 0,
                "final_hit_count_delta": 0,
                "final_hit_rate_delta": 0.0,
                "roi_delta": 0.0,
                "profit_loss_delta": 0.0,
                "brier_score_delta": 0.001,
                "log_loss_delta": -0.001,
                "mean_calibration_error_delta": -0.001,
            }
        )
    )

    assert report.status == "blocked"
    assert report.model_quality_gate_passed is False
    assert "brier_score_delta" in report.summary_json["failed_checks"]


def test_model_quality_gate_blocks_unexpected_final_answer_change() -> None:
    report = build_historical_probability_calibration_profile_model_quality_gate_report(
        _profile_gate_report(
            aggregate_deltas_json={
                "final_answer_changed_count": 1,
                "final_hit_count_delta": 0,
                "final_hit_rate_delta": 0.0,
                "roi_delta": 0.0,
                "profit_loss_delta": 0.0,
                "brier_score_delta": -0.001,
                "log_loss_delta": -0.001,
                "mean_calibration_error_delta": -0.001,
            }
        )
    )

    assert report.status == "blocked"
    assert "final_answer_changed_count" in report.summary_json["failed_checks"]


def test_model_quality_gate_cli_options_map_thresholds() -> None:
    args = _parse_args(
        [
            "--profile-gate-report",
            "profile_gate.json",
            "--gate-id",
            "calibration-model-quality-test",
            "--allow-non-shadow-profile-gate",
            "--allow-non-improved-suite-status",
            "--min-selected-competition-count",
            "2",
            "--min-adjusted-slice-count",
            "3",
            "--min-adjusted-fixture-count",
            "24",
            "--max-skipped-fixture-count",
            "1",
            "--max-final-answer-changed-count",
            "2",
            "--min-final-answer-hit-count-delta",
            "1",
            "--min-final-answer-hit-rate-delta",
            "0.01",
            "--min-roi-delta",
            "0.02",
            "--min-profit-loss-delta",
            "3.0",
            "--max-brier-score-delta",
            "0.0",
            "--max-log-loss-delta",
            "0.0",
            "--max-mean-calibration-error-delta",
            "0.0",
        ]
    )

    options = _options_from_args(args)

    assert args.profile_gate_report == Path("profile_gate.json")
    assert options.gate_id == "calibration-model-quality-test"
    assert options.require_shadow_only is False
    assert options.require_suite_status_improved is False
    assert options.min_selected_competition_count == 2
    assert options.min_adjusted_slice_count == 3
    assert options.min_adjusted_fixture_count == 24
    assert options.max_skipped_fixture_count == 1
    assert options.max_final_answer_changed_count == 2
    assert options.min_final_answer_hit_count_delta == 1
    assert options.min_final_answer_hit_rate_delta == 0.01
    assert options.min_roi_delta == 0.02
    assert options.min_profit_loss_delta == 3.0


def test_model_quality_gate_loads_report(tmp_path: Path) -> None:
    gate_report = build_historical_probability_calibration_profile_model_quality_gate_report(
        _profile_gate_report()
    )
    report_path = tmp_path / "model_quality_gate.json"
    report_path.write_text(gate_report.model_dump_json(), encoding="utf-8")

    loaded = load_historical_probability_calibration_profile_model_quality_gate_report(
        report_path
    )

    assert loaded.report_key == gate_report.report_key
    assert loaded.status == "model_quality_ready"


def _profile_gate_report(
    *,
    aggregate_deltas_json: dict[str, object] | None = None,
) -> HistoricalProbabilityCalibrationProfileGateReport:
    deltas = aggregate_deltas_json or {
        "final_answer_changed_count": 0,
        "final_hit_count_delta": 0,
        "final_hit_rate_delta": 0.0,
        "roi_delta": 0.0,
        "profit_loss_delta": 0.0,
        "brier_score_delta": -0.013,
        "log_loss_delta": -0.027,
        "mean_calibration_error_delta": -0.008,
    }
    return HistoricalProbabilityCalibrationProfileGateReport.model_validate(
        {
            "report_key": "historical_probability_calibration_profile_gate:test",
            "status": "generated",
            "gate_id": "probability-calibration-profile-gate-shadow-v3.1",
            "transform_report_key": "historical_probability_calibration_transform:test",
            "selected_competition_ids": ["EPL", "LA_LIGA"],
            "rejected_competition_ids": ["LIGUE_1"],
            "baseline_slice_count": 4,
            "adjusted_slice_count": 4,
            "adjusted_fixture_count": 96,
            "skipped_fixture_count": 0,
            "suite": None,
            "quality_gate": None,
            "passed_final_answer_gate": False,
            "warnings": [
                "historical_suite_quality_gate:failed_check:final_answer_changed_count"
            ],
            "summary_json": {
                "shadow_only": True,
                "suite_status": "improved",
                "quality_gate_passed": False,
                "passed_final_answer_gate": False,
                "aggregate_deltas_json": deltas,
            },
        }
    )
