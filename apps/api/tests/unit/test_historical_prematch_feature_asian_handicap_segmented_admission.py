from __future__ import annotations

from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport,
    HistoricalPrematchFeatureAsianHandicapRoleCandidate,
    HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions,
    build_historical_prematch_feature_asian_handicap_segmented_admission_report,
    load_historical_prematch_feature_asian_handicap_segmented_admission_report,
)
from nutmeg.accuracy.historical_prematch_feature_asian_handicap_segmented_admission import (
    _options_from_args,
    _parse_args,
    main,
)


def test_asian_handicap_segmented_admission_accepts_clean_segment_with_fallback() -> None:
    good_report = _role_search_report(segment_id="GOOD")
    bad_report = _role_search_report(
        segment_id="BAD",
        accepted_nonzero_candidate_count=0,
        best_accepted_candidate=None,
        best_effective_candidate=_candidate(
            status="watchlist",
            brier_delta=0.002,
            log_loss_delta=0.003,
            passed_non_regression_gate=False,
        ),
    )

    report = build_historical_prematch_feature_asian_handicap_segmented_admission_report(
        [good_report, bad_report],
        options=HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions(
            min_source_report_count=2,
            min_accepted_segment_count=1,
            min_accepted_validation_count=100,
            min_segment_validation_count=80,
        ),
    )
    decisions = {decision.segment_id: decision for decision in report.decisions}

    assert report.status == "accepted"
    assert report.segmented_candidate_model_allowed is True
    assert report.default_path_isolated is True
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert report.accepted_segment_count == 1
    assert report.fallback_segment_count == 1
    assert report.accepted_segment_ids == ["GOOD"]
    assert decisions["GOOD"].status == "accepted"
    assert decisions["GOOD"].asian_handicap_line_movement_transform == "linear"
    assert decisions["BAD"].status == "baseline_fallback"
    assert "brier_score_delta_above_maximum" in decisions["BAD"].failure_reasons


def test_asian_handicap_segmented_admission_keeps_missing_calibration_shadow_only() -> None:
    source_report = _role_search_report(
        segment_id="MISSING_ECE",
        best_accepted_candidate=_candidate(ece_delta=None),
    )

    report = build_historical_prematch_feature_asian_handicap_segmented_admission_report(
        [source_report],
        options=HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions(
            min_accepted_validation_count=80,
            min_segment_validation_count=80,
        ),
    )

    assert report.status == "shadow_only"
    assert report.segmented_candidate_model_allowed is False
    assert report.accepted_segment_count == 0
    assert report.shadow_segment_count == 1
    assert report.decisions[0].status == "shadow_only"
    assert (
        "expected_calibration_error_delta_missing"
        in report.decisions[0].failure_reasons
    )
    assert (
        "asian_handicap_segmented_admission:failed_check:accepted_segment_count"
        in report.warnings
    )


def test_asian_handicap_segmented_admission_uses_measurement_ready_calibration_sample() -> None:
    source_report = _role_search_report(
        segment_id="SERIE_A",
        best_accepted_candidate=_candidate(ece_delta=None),
    )

    report = build_historical_prematch_feature_asian_handicap_segmented_admission_report(
        [source_report],
        calibration_sample_expansion_reports=[
            _calibration_sample_expansion_report(source_report)
        ],
        options=HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions(
            min_accepted_validation_count=80,
            min_segment_validation_count=80,
        ),
    )

    assert report.status == "accepted"
    assert report.segmented_candidate_model_allowed is True
    assert report.accepted_segment_count == 1
    assert report.calibration_sample_expansion_report_count == 1
    assert report.calibration_sample_expansion_applied_count == 1
    assert report.decisions[0].status == "accepted"
    assert report.decisions[0].calibration_sample_expansion_applied is True
    assert report.decisions[0].expected_calibration_error_delta == -0.00006
    assert "expected_calibration_error_delta_missing" not in report.decisions[
        0
    ].failure_reasons


def test_asian_handicap_segmented_admission_ignores_activation_calibration_sample() -> None:
    source_report = _role_search_report(
        segment_id="SERIE_A",
        best_accepted_candidate=_candidate(ece_delta=None),
    )

    report = build_historical_prematch_feature_asian_handicap_segmented_admission_report(
        [source_report],
        calibration_sample_expansion_reports=[
            _calibration_sample_expansion_report(source_report, activation_allowed=True)
        ],
        options=HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions(
            min_accepted_validation_count=80,
            min_segment_validation_count=80,
        ),
    )

    assert report.status == "shadow_only"
    assert report.calibration_sample_expansion_applied_count == 0
    assert report.decisions[0].calibration_sample_expansion_applied is False
    assert (
        "expected_calibration_error_delta_missing"
        in report.decisions[0].failure_reasons
    )


def test_asian_handicap_segmented_admission_cli_writes_report(tmp_path: Path) -> None:
    source_path = tmp_path / "segment.json"
    output_path = tmp_path / "segmented.json"
    source_path.write_text(
        f"{_role_search_report(segment_id='CLI').model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--segment-role-search-report",
            str(source_path),
            "--admission-id",
            "ah-segmented-cli-test",
            "--min-accepted-validation-count",
            "80",
            "--output-path",
            str(output_path),
        ]
    )

    loaded = (
        load_historical_prematch_feature_asian_handicap_segmented_admission_report(
            output_path
        )
    )
    assert loaded.status == "accepted"
    assert loaded.admission_id == "ah-segmented-cli-test"
    assert loaded.accepted_segment_ids == ["CLI"]


def test_asian_handicap_segmented_admission_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--segment-role-search-report",
            "segment.json",
            "--calibration-sample-expansion-report",
            "expansion.json",
            "--admission-id",
            "ah-segmented-args-test",
            "--min-source-report-count",
            "2",
            "--min-accepted-segment-count",
            "2",
            "--min-accepted-validation-count",
            "180",
            "--min-candidate-count",
            "32",
            "--min-accepted-nonzero-candidate-count",
            "2",
            "--min-segment-validation-count",
            "60",
            "--min-selected-effective-weight",
            "0.02",
            "--min-selected-line-movement-weight",
            "0.03",
            "--min-hit-rate-delta",
            "-0.01",
            "--max-brier-score-delta",
            "0.01",
            "--max-log-loss-delta",
            "0.02",
            "--max-expected-calibration-error-delta",
            "0.03",
            "--min-average-actual-probability-delta",
            "-0.04",
            "--max-warning-count",
            "3",
            "--allow-source-not-generated",
            "--allow-source-not-shadow-only",
            "--allow-selected-candidate-not-accepted",
            "--allow-missing-calibration-delta",
            "--allow-default-path-not-isolated",
            "--allow-production-change",
            "--allow-public-response-change",
        ]
    )

    options = _options_from_args(args)

    assert args.calibration_sample_expansion_reports == [Path("expansion.json")]
    assert options.admission_id == "ah-segmented-args-test"
    assert options.min_source_report_count == 2
    assert options.min_accepted_segment_count == 2
    assert options.min_accepted_validation_count == 180
    assert options.min_candidate_count == 32
    assert options.min_accepted_nonzero_candidate_count == 2
    assert options.min_segment_validation_count == 60
    assert options.min_selected_effective_weight == 0.02
    assert options.min_selected_line_movement_weight == 0.03
    assert options.min_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.01
    assert options.max_log_loss_delta == 0.02
    assert options.max_expected_calibration_error_delta == 0.03
    assert options.min_average_actual_probability_delta == -0.04
    assert options.max_warning_count == 3
    assert options.require_source_status_generated is False
    assert options.require_source_shadow_only is False
    assert options.require_selected_candidate_accepted is False
    assert options.require_expected_calibration_error_delta is False
    assert options.require_default_path_isolated is False
    assert options.require_no_production_change is False
    assert options.require_no_public_response_change is False


def _role_search_report(
    *,
    segment_id: str,
    accepted_nonzero_candidate_count: int = 1,
    best_accepted_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None
    | object = ...,
    best_effective_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None
    | object = ...,
) -> HistoricalPrematchFeatureAsianHandicapRoleSearchReport:
    accepted_candidate = (
        _candidate()
        if best_accepted_candidate is ...
        else best_accepted_candidate
    )
    effective_candidate = (
        accepted_candidate
        if best_effective_candidate is ...
        else best_effective_candidate
    )
    fallback_candidate = _candidate(status="control_passed", effective_role=False)
    best_candidate = accepted_candidate or effective_candidate or fallback_candidate
    return HistoricalPrematchFeatureAsianHandicapRoleSearchReport(
        report_key=f"prematch_feature_asian_handicap_role_search:{segment_id}",
        status="generated",
        role_search_id=f"role-search:{segment_id}",
        baseline_label="baseline",
        candidate_label="candidate",
        baseline_slice_count=10,
        candidate_slice_count=10,
        baseline_fixture_count=240,
        candidate_fixture_count=240,
        candidate_count=64,
        accepted_nonzero_candidate_count=accepted_nonzero_candidate_count,
        control_passed_candidate_count=4,
        watchlist_candidate_count=1,
        best_candidate=best_candidate,
        best_accepted_candidate=accepted_candidate,
        best_effective_candidate=effective_candidate,
        best_control_candidate=fallback_candidate,
        candidates=[best_candidate],
        warnings=[],
        summary_json={
            "shadow_only": True,
            "segment_id": segment_id,
            "accepted_nonzero_candidate_count": accepted_nonzero_candidate_count,
        },
    )


def _calibration_sample_expansion_report(
    source_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    ece_delta: float | None = -0.00006,
    activation_allowed: bool = False,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport:
    candidate = source_report.best_accepted_candidate
    assert candidate is not None
    return HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport(
        report_key="historical_prematch_feature_asian_handicap_calibration_sample_expansion:test",
        status="measurement_ready",
        experiment_id="ah-calibration-expansion-test",
        target_segment_id=str(source_report.summary_json["segment_id"]),
        source_refinement_report_key=(
            "historical_prematch_feature_asian_handicap_segment_refinement:test"
        ),
        strict_role_search_report_key=source_report.report_key,
        relaxed_role_search_report_key=(
            "prematch_feature_asian_handicap_role_search:relaxed"
        ),
        calibration_measurement_ready=True,
        activation_allowed=activation_allowed,
        default_path_isolated=True,
        production_recommendation_changed=False,
        public_response_changed=False,
        strict_min_bucket_sample_size=30,
        relaxed_min_bucket_sample_size=10,
        strict_bucket_size=0.1,
        relaxed_bucket_size=0.1,
        strict_selected_candidate_id=candidate.candidate_id,
        relaxed_selected_candidate_id=f"{candidate.candidate_id}:relaxed",
        strict_expected_calibration_error_delta=None,
        relaxed_expected_calibration_error_delta=ece_delta,
        relaxed_hit_rate_delta=0.0,
        relaxed_brier_score_delta=-0.00004,
        relaxed_log_loss_delta=-0.00014,
        relaxed_average_actual_probability_delta=0.00001,
        relaxed_validation_count=candidate.candidate_validation_count,
    )


def _candidate(
    *,
    status: str = "accepted",
    validation_count: int = 120,
    hit_delta: float = 0.0,
    brier_delta: float = -0.0002,
    log_loss_delta: float = -0.0003,
    ece_delta: float | None = -0.0001,
    actual_probability_delta: float = 0.0001,
    passed_non_regression_gate: bool = True,
    effective_role: bool = True,
) -> HistoricalPrematchFeatureAsianHandicapRoleCandidate:
    metric_deltas_json: dict[str, object] = {
        "hit_rate": {"delta": hit_delta},
        "brier_score": {"delta": brier_delta},
        "log_loss": {"delta": log_loss_delta},
        "average_actual_probability": {"delta": actual_probability_delta},
        "expected_calibration_error": {"delta": ece_delta},
    }
    return HistoricalPrematchFeatureAsianHandicapRoleCandidate(
        rank=1,
        candidate_id=f"candidate:{status}",
        status=status,
        comparison_report_key=f"comparison:{status}",
        baseline_report_key="baseline:report",
        candidate_report_key="candidate:report",
        asian_handicap_movement_weight=0.05 if effective_role else 0.0,
        min_asian_handicap_probability_delta=0.04,
        asian_handicap_line_movement_weight=0.05 if effective_role else 0.0,
        min_asian_handicap_line_delta=0.0,
        asian_handicap_line_movement_scale=2.0,
        effective_asian_handicap_role=effective_role,
        baseline_validation_count=validation_count,
        candidate_validation_count=validation_count,
        candidate_asian_handicap_feature_coverage=1.0,
        passed_non_regression_gate=passed_non_regression_gate,
        ranking_score=-0.001,
        metric_deltas_json=metric_deltas_json,
        warnings=[],
        summary_json={"status": status},
    )
