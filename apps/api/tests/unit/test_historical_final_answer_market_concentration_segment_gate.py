from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.historical_final_answer_market_concentration_admission_gate import (
    HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions,
    build_historical_final_answer_market_concentration_admission_gate,
)
from nutmeg.recommendations.historical_final_answer_market_concentration_admission_gate import (
    main as admission_gate_main,
)
from nutmeg.recommendations.historical_final_answer_market_concentration_audit import (
    HistoricalFinalAnswerMarketConcentrationAuditReport,
    HistoricalFinalAnswerMarketConcentrationSlice,
)
from nutmeg.recommendations.historical_final_answer_market_concentration_segment_gate import (
    HistoricalFinalAnswerMarketConcentrationSegmentGateOptions,
    build_historical_final_answer_market_concentration_segment_gate,
)
from nutmeg.recommendations.historical_final_answer_market_concentration_segment_gate import (
    main as segment_gate_main,
)


def test_segment_gate_promotes_only_passing_segments() -> None:
    report = build_historical_final_answer_market_concentration_segment_gate(
        [
            _audit_report(
                "2x1",
                passed=False,
                failed_checks=["roi_delta", "profit_loss_delta"],
                roi_delta=-0.01,
                profit_loss_delta=-4.2,
            ),
            _audit_report("3x1", passed=True),
        ],
        report_paths=("reports/2x1.json", "reports/3x1.json"),
    )

    assert report.passed is True
    assert report.status == "passed"
    assert report.promoted_pass_types == ["3x1"]
    assert report.blocked_pass_types == ["2x1"]
    blocked = report.decisions[0]
    assert blocked.decision == "block_segment"
    assert blocked.reason_codes == ["blocked_by_roi_profit_loss_no_harm_gate"]
    promoted = report.decisions[1]
    assert promoted.decision == "promote_candidate"
    assert promoted.reason_codes == ["segment_gate_passed"]
    assert promoted.constraint_profile_id == (
        "max_outcomes_per_fixture=2|min_marginal_quality_gain=0"
    )


def test_segment_gate_can_require_all_segments_to_pass() -> None:
    report = build_historical_final_answer_market_concentration_segment_gate(
        [
            _audit_report(
                "2x1",
                passed=False,
                failed_checks=["roi_delta"],
                roi_delta=-0.01,
            ),
            _audit_report("3x1", passed=True),
        ],
        options=HistoricalFinalAnswerMarketConcentrationSegmentGateOptions(
            require_all_segments_passed=True,
        ),
    )

    assert report.passed is False
    assert report.status == "failed"
    assert "segment_gate:one_or_more_segments_blocked" in report.warnings


def test_segment_gate_cli_writes_summary(tmp_path: Path) -> None:
    blocked_path = tmp_path / "2x1.json"
    promoted_path = tmp_path / "3x1.json"
    output_path = tmp_path / "segment_gate.json"
    blocked_path.write_text(
        _audit_report(
            "2x1",
            passed=False,
            failed_checks=["profit_loss_delta"],
            profit_loss_delta=-3.0,
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    promoted_path.write_text(
        _audit_report("3x1", passed=True).model_dump_json(indent=2),
        encoding="utf-8",
    )

    segment_gate_main(
        [
            str(blocked_path),
            str(promoted_path),
            "--output-path",
            str(output_path),
            "--no-fail-process",
        ]
    )

    output = output_path.read_text(encoding="utf-8")
    assert "historical_final_answer_market_concentration_segment_gate" in output
    assert "promote_candidate" in output
    assert "block_segment" in output


def test_admission_gate_uses_segment_gate_promoted_pass_types() -> None:
    segment_gate = build_historical_final_answer_market_concentration_segment_gate(
        [
            _audit_report(
                "2x1",
                passed=False,
                failed_checks=["roi_delta", "profit_loss_delta"],
                roi_delta=-0.01,
                profit_loss_delta=-4.2,
            ),
            _audit_report("3x1", passed=True),
            _audit_report(
                "4x1",
                passed=False,
                failed_checks=["profit_loss_delta"],
                profit_loss_delta=-22.0,
            ),
        ],
    )
    smoke_report = _audit_report("3x1", passed=True)
    smoke_report.summary_json = {
        "dynamic_mix_final_answer_lane_effective_pass_types": ["3x1"],
        "failed_checks": [],
    }

    report = build_historical_final_answer_market_concentration_admission_gate(
        segment_gate,
        bounded_admission_report=smoke_report,
        options=HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions(
            requested_pass_types=("2x1", "3x1", "4x1"),
            require_bounded_admission_smoke=True,
            min_bounded_smoke_slice_count=30,
            min_bounded_smoke_dynamic_mixed_final_answer_count=1,
            min_bounded_smoke_multiple_choice_final_answer_count=1,
        ),
    )

    assert report.passed is True
    assert report.status == "passed"
    assert report.admitted_pass_types == ["3x1"]
    assert report.blocked_pass_types == ["2x1", "4x1"]
    assert report.effective_pass_types == ["3x1"]
    assert report.summary_json["failed_checks"] == []


def test_admission_gate_fails_when_smoke_runs_blocked_pass_type() -> None:
    segment_gate = build_historical_final_answer_market_concentration_segment_gate(
        [
            _audit_report(
                "2x1",
                passed=False,
                failed_checks=["roi_delta"],
                roi_delta=-0.01,
            ),
            _audit_report("3x1", passed=True),
        ],
    )
    smoke_report = _audit_report("3x1", passed=True)
    smoke_report.summary_json = {
        "dynamic_mix_final_answer_lane_effective_pass_types": ["2x1", "3x1"],
        "failed_checks": [],
    }

    report = build_historical_final_answer_market_concentration_admission_gate(
        segment_gate,
        bounded_admission_report=smoke_report,
        options=HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions(
            requested_pass_types=("2x1", "3x1"),
            require_bounded_admission_smoke=True,
        ),
    )

    assert report.passed is False
    assert "bounded_admission_smoke_effective_pass_types" in report.summary_json[
        "failed_checks"
    ]


def test_admission_gate_cli_writes_summary(tmp_path: Path) -> None:
    segment_gate_path = tmp_path / "segment_gate.json"
    smoke_path = tmp_path / "smoke.json"
    output_path = tmp_path / "admission_gate.json"
    segment_gate = build_historical_final_answer_market_concentration_segment_gate(
        [
            _audit_report(
                "2x1",
                passed=False,
                failed_checks=["profit_loss_delta"],
                profit_loss_delta=-3.0,
            ),
            _audit_report("3x1", passed=True),
        ],
    )
    smoke_report = _audit_report("3x1", passed=True)
    smoke_report.summary_json = {
        "dynamic_mix_final_answer_lane_effective_pass_types": ["3x1"],
        "failed_checks": [],
    }
    segment_gate_path.write_text(segment_gate.model_dump_json(indent=2), encoding="utf-8")
    smoke_path.write_text(smoke_report.model_dump_json(indent=2), encoding="utf-8")

    admission_gate_main(
        [
            "--segment-gate-report-path",
            str(segment_gate_path),
            "--bounded-admission-report-path",
            str(smoke_path),
            "--requested-pass-types",
            "2x1,3x1",
            "--require-bounded-admission-smoke",
            "--output-path",
            str(output_path),
            "--no-fail-process",
        ]
    )

    output = output_path.read_text(encoding="utf-8")
    assert "historical_final_answer_market_concentration_admission_gate" in output
    assert '"effective_pass_types": [\n    "3x1"\n  ]' in output


def test_constraint_profile_admission_can_admit_constrained_pass_type() -> None:
    segment_gate = build_historical_final_answer_market_concentration_segment_gate(
        [
            _audit_report(
                "2x1",
                passed=False,
                failed_checks=["profit_loss_delta"],
                profit_loss_delta=-3.0,
            ),
            _audit_report(
                "2x1",
                passed=True,
                max_outcomes_per_fixture=1,
            ),
            _audit_report("3x1", passed=True),
        ],
    )

    report = build_historical_final_answer_market_concentration_admission_gate(
        segment_gate,
        options=HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions(
            requested_pass_types=("2x1", "3x1"),
            constraint_profile_admission=True,
            min_admitted_pass_type_count=2,
        ),
    )

    assert report.passed is True
    assert report.effective_pass_types == ["2x1", "3x1"]
    assert any(
        profile["pass_type"] == "2x1"
        and profile["constraint_profile_json"]["max_outcomes_per_fixture"] == 1
        for profile in report.effective_constraint_profiles
    )
    assert "2x1" in report.blocked_pass_types


def _audit_report(
    pass_type: str,
    *,
    passed: bool,
    failed_checks: list[str] | None = None,
    roi_delta: float = 0.01,
    profit_loss_delta: float = 4.0,
    max_outcomes_per_fixture: int | None = None,
    min_marginal_quality_gain: float | None = None,
) -> HistoricalFinalAnswerMarketConcentrationAuditReport:
    status = "passed" if passed else "failed"
    checks = failed_checks or []
    return HistoricalFinalAnswerMarketConcentrationAuditReport(
        report_key=f"report:{pass_type}",
        audit_id="unit",
        status=status,
        passed=passed,
        suite_key=f"suite:{pass_type}",
        suite_status="improved" if passed else "mixed",
        slice_count=210,
        comparison_count=210,
        final_answer_count=210,
        market_type_count=2,
        market_type_counts={"cn_handicap_1x2": 210, "european_handicap_1x2": 180},
        market_type_rates={"cn_handicap_1x2": 1.0, "european_handicap_1x2": 0.86},
        single_market_final_answer_count=30,
        single_market_final_answer_rate=30 / 210,
        single_market_type_counts={"cn_handicap_1x2": 30},
        single_market_type_rates={"cn_handicap_1x2": 30 / 210},
        dominant_single_market_type="cn_handicap_1x2",
        dominant_single_market_count=30,
        dominant_single_market_rate=30 / 210,
        market_concentration_hhi=0.02,
        dynamic_mixed_final_answer_count=180,
        dynamic_mixed_final_answer_rate=180 / 210,
        handicap_final_answer_count=210,
        correct_score_final_answer_count=0,
        multiple_choice_final_answer_count=20,
        candidate_final_hit_rate=0.65,
        candidate_roi=0.04,
        candidate_profit_loss=20.0,
        aggregate_deltas_json={
            "final_hit_rate_delta": 0.02,
            "roi_delta": roi_delta,
            "profit_loss_delta": profit_loss_delta,
            "brier_score_delta": -0.01,
            "log_loss_delta": -0.01,
            "mean_calibration_error_delta": -0.01,
        },
        checks=[],
        single_market_slice_samples=[],
        dynamic_mixed_slice_samples=[
            HistoricalFinalAnswerMarketConcentrationSlice(
                slice_id=f"slice:{pass_type}",
                final_answer_present=True,
                final_answer_changed=False,
                market_types=["cn_handicap_1x2", "european_handicap_1x2"],
                dynamic_mixed_market=True,
                pass_type=pass_type,
                mode="multiple",
                selected_candidate_count=int(pass_type.split("x", maxsplit=1)[0]),
            )
        ],
        warnings=[],
        summary_json=_summary_json(
            failed_checks=checks,
            max_outcomes_per_fixture=max_outcomes_per_fixture,
            min_marginal_quality_gain=min_marginal_quality_gain,
        ),
    )


def _summary_json(
    *,
    failed_checks: list[str],
    max_outcomes_per_fixture: int | None,
    min_marginal_quality_gain: float | None,
) -> dict[str, object]:
    summary: dict[str, object] = {"failed_checks": failed_checks}
    if max_outcomes_per_fixture is not None:
        summary["max_outcomes_per_fixture"] = max_outcomes_per_fixture
    if min_marginal_quality_gain is not None:
        summary["min_marginal_quality_gain"] = min_marginal_quality_gain
    return summary
