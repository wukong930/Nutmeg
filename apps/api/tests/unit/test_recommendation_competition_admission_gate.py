from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.competition_admission_gate import (
    CompetitionAdmissionGateOptions,
    _options_from_args,
    _parse_args,
    build_competition_admission_gate_report,
    main,
)


def test_competition_admission_gate_accepts_passing_final_answer_evidence() -> None:
    report = build_competition_admission_gate_report(
        final_answer_gate_report=_final_answer_gate_summary(
            passed=True,
            suite_status="unchanged",
            final_hit_sample_size=35,
            final_hit_rate=0.60,
            roi=0.02,
            worst_competition_roi=-0.20,
            final_hit_rate_delta=0.0,
        ),
        options=CompetitionAdmissionGateOptions(min_final_hit_sample_size=35),
        feature_learning_report=_feature_learning_summary(
            brier_delta=-0.001,
            log_loss_delta=-0.001,
            ece_delta=-0.001,
        ),
    )

    assert report.decision == "accepted"
    assert report.production_recommendation_allowed is True
    assert report.training_pool_allowed is True
    assert report.blockers == []
    assert report.warnings == []


def test_competition_admission_gate_keeps_failed_but_sufficient_suite_shadow_only() -> None:
    report = build_competition_admission_gate_report(
        final_answer_gate_report=_final_answer_gate_summary(
            passed=False,
            suite_status="mixed",
            final_hit_sample_size=35,
            final_hit_rate=0.43,
            roi=-0.15,
            worst_competition_roi=-1.0,
            final_hit_rate_delta=-0.11,
            failed_checks=("candidate_final_hit_rate", "competition_candidate_roi"),
        ),
        options=CompetitionAdmissionGateOptions(min_final_hit_sample_size=35),
        feature_learning_report=_feature_learning_summary(
            brier_delta=-0.001,
            log_loss_delta=-0.001,
            ece_delta=0.001,
        ),
    )

    assert report.decision == "shadow_only"
    assert report.production_recommendation_allowed is False
    assert report.training_pool_allowed is False
    assert report.shadow_allowed is True
    assert "final_answer_gate_not_passed" in report.blockers
    assert "candidate_final_hit_rate_below_threshold" in report.blockers
    assert "competition_roi_below_threshold" in report.blockers
    assert "feature_expected_calibration_error_regressed" in report.warnings


def test_competition_admission_gate_can_block_feature_regression_to_shadow_only() -> None:
    report = build_competition_admission_gate_report(
        final_answer_gate_report=_final_answer_gate_summary(
            passed=True,
            suite_status="unchanged",
            final_hit_sample_size=40,
            final_hit_rate=0.62,
            roi=0.02,
            worst_competition_roi=-0.10,
            final_hit_rate_delta=0.0,
        ),
        options=CompetitionAdmissionGateOptions(
            min_final_hit_sample_size=35,
            allow_feature_metric_regression_for_shadow=False,
        ),
        feature_learning_report=_feature_learning_summary(
            brier_delta=-0.001,
            log_loss_delta=-0.001,
            ece_delta=0.001,
        ),
    )

    assert report.decision == "shadow_only"
    assert report.production_recommendation_allowed is False
    assert report.training_pool_allowed is False
    assert report.shadow_allowed is True
    assert report.blockers == []
    assert report.warnings == ["feature_expected_calibration_error_regressed"]


def test_competition_admission_gate_rejects_insufficient_final_answer_sample() -> None:
    report = build_competition_admission_gate_report(
        final_answer_gate_report=_final_answer_gate_summary(
            passed=False,
            suite_status="unchanged",
            final_hit_sample_size=3,
            final_hit_rate=0.33,
            roi=0.70,
            worst_competition_roi=-1.0,
            final_hit_rate_delta=0.0,
        ),
        options=CompetitionAdmissionGateOptions(min_final_hit_sample_size=35),
    )

    assert report.decision == "rejected"
    assert report.shadow_allowed is False
    assert "final_hit_sample_size_below_threshold" in report.blockers


def test_competition_admission_gate_cli_writes_report(tmp_path: Path) -> None:
    final_gate_path = tmp_path / "final_gate.json"
    feature_path = tmp_path / "feature.json"
    output_path = tmp_path / "admission.json"
    final_gate_path.write_text(
        _json(
            _final_answer_gate_summary(
                passed=False,
                suite_status="mixed",
                final_hit_sample_size=35,
                final_hit_rate=0.43,
                roi=-0.15,
                worst_competition_roi=-1.0,
                final_hit_rate_delta=-0.11,
            )
        ),
        encoding="utf-8",
    )
    feature_path.write_text(
        _json(
            _feature_learning_summary(
                brier_delta=-0.001,
                log_loss_delta=-0.001,
                ece_delta=0.001,
            )
        ),
        encoding="utf-8",
    )

    main(
        [
            "--final-answer-gate-report",
            str(final_gate_path),
            "--feature-learning-report",
            str(feature_path),
            "--output-path",
            str(output_path),
            "--min-final-hit-sample-size",
            "35",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["decision"] == "shadow_only"
    assert payload["summary_json"]["feature_expected_calibration_error_delta"] == 0.001


def test_competition_admission_gate_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--final-answer-gate-report",
            "gate.json",
            "--gate-id",
            "custom",
            "--min-final-hit-sample-size",
            "40",
            "--min-final-hit-rate",
            "0.62",
            "--min-roi",
            "-0.10",
            "--min-competition-roi",
            "-0.25",
            "--min-final-hit-rate-delta",
            "0.01",
            "--max-feature-brier-delta",
            "0.02",
            "--max-feature-log-loss-delta",
            "0.03",
            "--max-feature-ece-delta",
            "0.04",
            "--block-feature-regression",
        ]
    )

    options = _options_from_args(args)

    assert options.gate_id == "custom"
    assert options.min_final_hit_sample_size == 40
    assert options.min_final_hit_rate == 0.62
    assert options.min_roi == -0.10
    assert options.min_competition_roi == -0.25
    assert options.min_final_hit_rate_delta == 0.01
    assert options.max_feature_brier_delta == 0.02
    assert options.max_feature_log_loss_delta == 0.03
    assert options.max_feature_ece_delta == 0.04
    assert options.allow_feature_metric_regression_for_shadow is False


def _final_answer_gate_summary(
    *,
    passed: bool,
    suite_status: str,
    final_hit_sample_size: int,
    final_hit_rate: float,
    roi: float,
    worst_competition_roi: float,
    final_hit_rate_delta: float,
    failed_checks: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "summary_json": {
            "gate_key": "historical_recommendation_suite_quality_gate:test",
            "passed": passed,
            "suite_status": suite_status,
            "candidate_final_hit_sample_size": final_hit_sample_size,
            "candidate_final_hit_rate": final_hit_rate,
            "candidate_roi": roi,
            "worst_competition_candidate_roi": worst_competition_roi,
            "aggregate_deltas": {"final_hit_rate_delta": final_hit_rate_delta},
            "failed_checks": list(failed_checks),
        }
    }


def _feature_learning_summary(
    *,
    brier_delta: float,
    log_loss_delta: float,
    ece_delta: float,
) -> dict[str, object]:
    return {
        "summary_json": {
            "report_key": "historical_prematch_feature_parameter_learning:test",
            "overall_validation_deltas_json": {
                "brier_score_delta": brier_delta,
                "log_loss_delta": log_loss_delta,
                "expected_calibration_error_delta": ece_delta,
            },
        }
    }


def _json(payload: dict[str, object]) -> str:
    return f"{dumps(payload)}\n"
