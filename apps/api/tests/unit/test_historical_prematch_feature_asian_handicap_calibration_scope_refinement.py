from __future__ import annotations

from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions,
    HistoricalPrematchFeatureAsianHandicapRoleCandidate,
    HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision,
    HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    build_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report,
    load_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report,
)
from nutmeg.accuracy.historical_prematch_feature_asian_handicap_calibration_scope_refinement import (  # noqa: E501
    _options_from_args,
    _parse_args,
    main,
)


def test_asian_handicap_calibration_scope_refinement_accepts_clean_scope() -> None:
    source = _role_search_report(
        role_search_id="BUNDESLIGA",
        ece_delta=0.00003,
        status="watchlist",
        passed_non_regression_gate=False,
    )
    scope = _role_search_report(
        role_search_id="BUNDESLIGA_min_bucket_20",
        min_bucket_sample_size=20,
        ece_delta=-0.00002,
        status="accepted",
        passed_non_regression_gate=True,
    )

    report = build_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report(
        _refinement_report(),
        source,
        [scope],
        options=HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions(
            target_segment_id="BUNDESLIGA",
        ),
    )

    assert report.status == "scope_ready"
    assert report.calibration_scope_ready is True
    assert report.activation_allowed is False
    assert report.source_expected_calibration_error_delta == 0.00003
    assert report.selected_expected_calibration_error_delta == -0.00002
    assert report.selected_min_bucket_sample_size == 20
    assert report.scope_alternatives[0].same_candidate_parameters is True
    assert report.default_path_isolated is True
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False


def test_asian_handicap_calibration_scope_refinement_shadows_uncleared_ece() -> None:
    source = _role_search_report(
        role_search_id="BUNDESLIGA",
        ece_delta=0.00003,
        status="watchlist",
        passed_non_regression_gate=False,
    )
    scope = _role_search_report(
        role_search_id="BUNDESLIGA_min_bucket_20",
        min_bucket_sample_size=20,
        ece_delta=0.00001,
        status="watchlist",
        passed_non_regression_gate=False,
    )

    report = build_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report(
        _refinement_report(),
        source,
        [scope],
        options=HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions(
            target_segment_id="BUNDESLIGA",
        ),
    )

    assert report.status == "shadow_only"
    assert report.calibration_scope_ready is False
    assert (
        "asian_handicap_calibration_scope_refinement:failed_check:"
        "selected_expected_calibration_error_delta"
    ) in report.warnings


def test_asian_handicap_calibration_scope_refinement_blocks_default_path_change() -> None:
    source = _role_search_report(
        role_search_id="BUNDESLIGA",
        ece_delta=0.00003,
        status="watchlist",
        passed_non_regression_gate=False,
    )
    scope = _role_search_report(
        role_search_id="BUNDESLIGA_min_bucket_20",
        min_bucket_sample_size=20,
        ece_delta=-0.00002,
        status="accepted",
        passed_non_regression_gate=True,
    )

    report = build_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report(
        _refinement_report(default_path_isolated=False),
        source,
        [scope],
        options=HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions(
            target_segment_id="BUNDESLIGA",
        ),
    )

    assert report.status == "blocked"
    assert (
        "asian_handicap_calibration_scope_refinement:failed_check:"
        "default_path_isolated"
    ) in report.warnings


def test_asian_handicap_calibration_scope_refinement_cli_writes_report(
    tmp_path: Path,
) -> None:
    refinement_path = tmp_path / "refinement.json"
    source_path = tmp_path / "source.json"
    scope_path = tmp_path / "scope.json"
    output_path = tmp_path / "scope-refinement.json"
    refinement_path.write_text(
        f"{_refinement_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    source_path.write_text(
        _role_search_json(
            role_search_id="BUNDESLIGA",
            ece_delta=0.00003,
            status="watchlist",
            passed_non_regression_gate=False,
        ),
        encoding="utf-8",
    )
    scope_path.write_text(
        _role_search_json(
            role_search_id="BUNDESLIGA_min_bucket_20",
            min_bucket_sample_size=20,
            ece_delta=-0.00002,
            status="accepted",
            passed_non_regression_gate=True,
        ),
        encoding="utf-8",
    )

    main(
        [
            str(refinement_path),
            str(source_path),
            str(scope_path),
            "--experiment-id",
            "ah-calibration-scope-cli-test",
            "--target-segment-id",
            "BUNDESLIGA",
            "--output-path",
            str(output_path),
        ]
    )

    loaded = (
        load_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report(
            output_path
        )
    )
    assert loaded.status == "scope_ready"
    assert loaded.experiment_id == "ah-calibration-scope-cli-test"


def test_asian_handicap_calibration_scope_refinement_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "refinement.json",
            "source.json",
            "scope.json",
            "--experiment-id",
            "ah-calibration-scope-args-test",
            "--target-segment-id",
            "BUNDESLIGA",
            "--min-scope-report-count",
            "2",
            "--min-validation-count",
            "50",
            "--min-hit-rate-delta",
            "-0.01",
            "--max-brier-score-delta",
            "0.01",
            "--max-log-loss-delta",
            "0.02",
            "--max-expected-calibration-error-delta",
            "0.03",
            "--allow-refinement-not-ready",
            "--allow-non-scope-refinement-action",
            "--allow-source-calibration-not-regressed",
            "--allow-candidate-parameter-drift",
            "--allow-unchanged-scope",
            "--allow-default-path-change",
            "--allow-production-change",
            "--allow-public-response-change",
        ]
    )

    options = _options_from_args(args)

    assert options.experiment_id == "ah-calibration-scope-args-test"
    assert options.target_segment_id == "BUNDESLIGA"
    assert options.min_scope_report_count == 2
    assert options.min_validation_count == 50
    assert options.min_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.01
    assert options.max_log_loss_delta == 0.02
    assert options.max_expected_calibration_error_delta == 0.03
    assert options.require_refinement_ready is False
    assert options.require_refinement_action is False
    assert options.require_source_calibration_regression is False
    assert options.require_same_candidate_parameters is False
    assert options.require_scope_change is False
    assert options.require_no_default_path_change is False
    assert options.require_no_production_change is False
    assert options.require_no_public_response_change is False


def _refinement_report(
    *,
    default_path_isolated: bool = True,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport:
    decision = HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision(
        segment_id="BUNDESLIGA",
        source_status="baseline_fallback",
        recommended_action="calibration_scope_refinement",
        refinement_candidate=True,
        validation_count=54,
        selected_candidate_id="candidate:BUNDESLIGA",
        selected_candidate_status="watchlist",
        blocker_categories=["calibration_regression"],
        failure_reasons=["expected_calibration_error_delta_above_maximum"],
        hit_rate_delta=0.0,
        brier_score_delta=-0.0002,
        log_loss_delta=-0.0003,
        expected_calibration_error_delta=0.00003,
    )
    return HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport(
        report_key="historical_prematch_feature_asian_handicap_segment_refinement:test",
        status="refinement_ready",
        refinement_id="ah-refinement-test",
        source_report_key="historical_prematch_feature_asian_handicap_segmented_admission:test",
        source_status="shadow_only",
        source_segment_count=1,
        refinement_candidate_count=1,
        baseline_fallback_segment_count=0,
        calibration_sample_expansion_count=0,
        calibration_scope_refinement_count=1,
        line_transform_enrichment_count=0,
        retained_candidate_segment_count=0,
        blocker_category_counts={"calibration_regression": 1},
        recommended_action_counts={"calibration_scope_refinement": 1},
        top_refinement_segment_ids=["BUNDESLIGA"],
        default_path_isolated=default_path_isolated,
        production_recommendation_changed=False,
        public_response_changed=False,
        decisions=[decision],
    )


def _role_search_report(
    *,
    role_search_id: str,
    min_bucket_sample_size: int = 30,
    bucket_size: float = 0.1,
    ece_delta: float | None,
    status: str,
    passed_non_regression_gate: bool,
) -> HistoricalPrematchFeatureAsianHandicapRoleSearchReport:
    candidate = _candidate(
        role_search_id=role_search_id,
        ece_delta=ece_delta,
        status=status,
        passed_non_regression_gate=passed_non_regression_gate,
    )
    return HistoricalPrematchFeatureAsianHandicapRoleSearchReport(
        report_key=f"prematch_feature_asian_handicap_role_search:{role_search_id}",
        status="generated",
        role_search_id=role_search_id,
        baseline_label="baseline",
        candidate_label="candidate",
        baseline_slice_count=5,
        candidate_slice_count=5,
        baseline_fixture_count=120,
        candidate_fixture_count=120,
        candidate_count=1,
        accepted_nonzero_candidate_count=1 if status == "accepted" else 0,
        control_passed_candidate_count=0,
        watchlist_candidate_count=1 if status == "watchlist" else 0,
        best_candidate=candidate,
        best_accepted_candidate=candidate if status == "accepted" else None,
        best_effective_candidate=candidate,
        best_control_candidate=None,
        candidates=[candidate],
        warnings=[] if status == "accepted" else ["no_accepted_nonzero_candidate"],
        summary_json={
            "shadow_only": True,
            "poisson_options": {
                "bucket_size": bucket_size,
                "min_bucket_sample_size": min_bucket_sample_size,
            },
        },
    )


def _role_search_json(
    *,
    role_search_id: str,
    min_bucket_sample_size: int = 30,
    bucket_size: float = 0.1,
    ece_delta: float | None,
    status: str,
    passed_non_regression_gate: bool,
) -> str:
    return (
        _role_search_report(
            role_search_id=role_search_id,
            min_bucket_sample_size=min_bucket_sample_size,
            bucket_size=bucket_size,
            ece_delta=ece_delta,
            status=status,
            passed_non_regression_gate=passed_non_regression_gate,
        ).model_dump_json(indent=2)
        + "\n"
    )


def _candidate(
    *,
    role_search_id: str,
    ece_delta: float | None,
    status: str,
    passed_non_regression_gate: bool,
) -> HistoricalPrematchFeatureAsianHandicapRoleCandidate:
    return HistoricalPrematchFeatureAsianHandicapRoleCandidate(
        rank=1,
        candidate_id=f"{role_search_id}:candidate",
        status=status,
        comparison_report_key=f"comparison:{role_search_id}",
        baseline_report_key=f"baseline:{role_search_id}",
        candidate_report_key=f"candidate:{role_search_id}",
        asian_handicap_movement_weight=0.05,
        min_asian_handicap_probability_delta=0.04,
        asian_handicap_line_movement_weight=0.05,
        min_asian_handicap_line_delta=0.0,
        asian_handicap_line_movement_scale=2.0,
        effective_asian_handicap_role=True,
        baseline_validation_count=54,
        candidate_validation_count=54,
        candidate_asian_handicap_feature_coverage=1.0,
        passed_non_regression_gate=passed_non_regression_gate,
        ranking_score=-0.001,
        metric_deltas_json={
            "hit_rate": {"delta": 0.0},
            "brier_score": {"delta": -0.0002},
            "log_loss": {"delta": -0.0003},
            "expected_calibration_error": {"delta": ece_delta},
            "average_actual_probability": {"delta": 0.0001},
        },
        warnings=[],
    )
