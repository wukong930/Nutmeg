from __future__ import annotations

from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions,
    HistoricalPrematchFeatureAsianHandicapRoleCandidate,
    HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision,
    HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    build_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report,
    load_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report,
)
from nutmeg.accuracy.historical_prematch_feature_asian_handicap_calibration_sample_expansion import (  # noqa: E501
    _options_from_args,
    _parse_args,
    _role_search_family_matches,
    main,
)


def test_asian_handicap_calibration_sample_expansion_measures_missing_ece() -> None:
    report = build_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
        _refinement_report(),
        _role_search_report(min_bucket_sample_size=30, ece_delta=None),
        _role_search_report(
            role_search_id="SERIE_A_min_bucket_10",
            min_bucket_sample_size=10,
            ece_delta=-0.00006,
        ),
        options=HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions(
            target_segment_id="SERIE_A",
        ),
    )

    assert report.status == "measurement_ready"
    assert report.calibration_measurement_ready is True
    assert report.activation_allowed is False
    assert report.strict_min_bucket_sample_size == 30
    assert report.relaxed_min_bucket_sample_size == 10
    assert report.strict_expected_calibration_error_delta is None
    assert report.relaxed_expected_calibration_error_delta == -0.00006
    assert report.default_path_isolated is True
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False


def test_asian_handicap_calibration_sample_expansion_shadows_relaxed_ece_regression() -> None:
    report = build_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
        _refinement_report(),
        _role_search_report(min_bucket_sample_size=30, ece_delta=None),
        _role_search_report(
            role_search_id="SERIE_A_min_bucket_10",
            min_bucket_sample_size=10,
            ece_delta=0.00006,
        ),
        options=HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions(
            target_segment_id="SERIE_A",
        ),
    )

    assert report.status == "shadow_only"
    assert report.calibration_measurement_ready is False
    assert (
        "asian_handicap_calibration_sample_expansion:failed_check:"
        "relaxed_expected_calibration_error_delta"
    ) in report.warnings


def test_asian_handicap_calibration_sample_expansion_blocks_default_path_change() -> None:
    report = build_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
        _refinement_report(default_path_isolated=False),
        _role_search_report(min_bucket_sample_size=30, ece_delta=None),
        _role_search_report(
            role_search_id="SERIE_A_min_bucket_10",
            min_bucket_sample_size=10,
            ece_delta=-0.00006,
        ),
        options=HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions(
            target_segment_id="SERIE_A",
        ),
    )

    assert report.status == "blocked"
    assert (
        "asian_handicap_calibration_sample_expansion:failed_check:"
        "default_path_isolated"
    ) in report.warnings


def test_asian_handicap_calibration_sample_expansion_cli_writes_report(
    tmp_path: Path,
) -> None:
    refinement_path = tmp_path / "refinement.json"
    strict_path = tmp_path / "strict.json"
    relaxed_path = tmp_path / "relaxed.json"
    output_path = tmp_path / "expansion.json"
    refinement_path.write_text(
        f"{_refinement_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    strict_path.write_text(
        _role_search_json(min_bucket_sample_size=30, ece_delta=None),
        encoding="utf-8",
    )
    relaxed_path.write_text(
        _role_search_json(
            role_search_id="SERIE_A_min_bucket_10",
            min_bucket_sample_size=10,
            ece_delta=-0.00006,
        ),
        encoding="utf-8",
    )

    main(
        [
            str(refinement_path),
            str(strict_path),
            str(relaxed_path),
            "--experiment-id",
            "ah-calibration-expansion-cli-test",
            "--target-segment-id",
            "SERIE_A",
            "--output-path",
            str(output_path),
        ]
    )

    loaded = (
        load_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
            output_path
        )
    )
    assert loaded.status == "measurement_ready"
    assert loaded.experiment_id == "ah-calibration-expansion-cli-test"


def test_asian_handicap_calibration_sample_expansion_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "refinement.json",
            "strict.json",
            "relaxed.json",
            "--experiment-id",
            "ah-calibration-expansion-args-test",
            "--target-segment-id",
            "SERIE_A",
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
            "--allow-missing-refinement-decision",
            "--allow-non-calibration-refinement-action",
            "--allow-strict-calibration-measurable",
            "--allow-relaxed-calibration-missing",
            "--allow-same-or-higher-bucket-floor",
            "--allow-candidate-parameter-drift",
            "--allow-default-path-change",
            "--allow-production-change",
            "--allow-public-response-change",
        ]
    )

    options = _options_from_args(args)

    assert options.experiment_id == "ah-calibration-expansion-args-test"
    assert options.target_segment_id == "SERIE_A"
    assert options.min_validation_count == 50
    assert options.min_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.01
    assert options.max_log_loss_delta == 0.02
    assert options.max_expected_calibration_error_delta == 0.03
    assert options.require_refinement_ready is False
    assert options.require_refinement_decision is False
    assert options.require_refinement_action is False
    assert options.require_strict_calibration_missing is False
    assert options.require_relaxed_calibration_measurable is False
    assert options.require_relaxed_bucket_floor_lower_than_strict is False
    assert options.require_same_candidate_parameters is False
    assert options.require_no_default_path_change is False
    assert options.require_no_production_change is False
    assert options.require_no_public_response_change is False


def test_asian_handicap_calibration_sample_expansion_matches_real_relaxed_family() -> None:
    assert _role_search_family_matches(
        "football_data_co_uk_serie_a_5_seasons_asian_handicap_line_aware_role_search_v1",
        (
            "football_data_co_uk_serie_a_5_seasons_asian_handicap_line_aware"
            "_min_bucket_10_role_search_v1"
        ),
    )
    assert _role_search_family_matches(
        "football_data_co_uk_ligue_1_5_seasons_asian_handicap_line_transform_enrichment_v1",
        (
            "football_data_co_uk_ligue_1_5_seasons_asian_handicap_line_transform"
            "_enrichment_min_bucket_20_bucket_20_role_search_v1"
        ),
    )


def test_asian_handicap_calibration_sample_expansion_allows_follow_up_measurement() -> None:
    report = build_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
        _refinement_report(),
        _role_search_report(
            role_search_id="LIGUE_1_line_transform",
            min_bucket_sample_size=30,
            ece_delta=None,
            asian_handicap_line_movement_transform="quarter_step",
        ),
        _role_search_report(
            role_search_id="LIGUE_1_line_transform_min_bucket_20_bucket_20",
            min_bucket_sample_size=20,
            bucket_size=0.2,
            ece_delta=-0.00046,
            asian_handicap_line_movement_transform="quarter_step",
        ),
        options=HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions(
            target_segment_id="LIGUE_1_line_transform",
            require_refinement_decision=False,
            require_refinement_action=False,
        ),
    )

    assert report.status == "measurement_ready"
    assert report.target_segment_id == "LIGUE_1_line_transform"
    assert report.relaxed_bucket_size == 0.2
    assert report.relaxed_expected_calibration_error_delta == -0.00046


def test_asian_handicap_calibration_sample_expansion_rejects_transform_drift() -> None:
    report = build_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
        _refinement_report(),
        _role_search_report(min_bucket_sample_size=30, ece_delta=None),
        _role_search_report(
            role_search_id="SERIE_A_min_bucket_10",
            min_bucket_sample_size=10,
            ece_delta=-0.00006,
            asian_handicap_line_movement_transform="quarter_step",
        ),
        options=HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions(
            target_segment_id="SERIE_A",
        ),
    )

    assert report.status == "shadow_only"
    assert (
        "asian_handicap_calibration_sample_expansion:failed_check:"
        "same_candidate_parameters"
    ) in report.warnings


def _refinement_report(
    *,
    default_path_isolated: bool = True,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport:
    decision = HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision(
        segment_id="SERIE_A",
        source_status="shadow_only",
        recommended_action="calibration_sample_expansion",
        refinement_candidate=True,
        validation_count=42,
        selected_candidate_id="candidate:SERIE_A",
        selected_candidate_status="accepted",
        blocker_categories=["calibration_missing"],
        failure_reasons=["expected_calibration_error_delta_missing"],
        hit_rate_delta=0.0,
        brier_score_delta=-0.00004,
        log_loss_delta=-0.00014,
        expected_calibration_error_delta=None,
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
        calibration_sample_expansion_count=1,
        calibration_scope_refinement_count=0,
        line_transform_enrichment_count=0,
        retained_candidate_segment_count=0,
        blocker_category_counts={"calibration_missing": 1},
        recommended_action_counts={"calibration_sample_expansion": 1},
        top_refinement_segment_ids=["SERIE_A"],
        default_path_isolated=default_path_isolated,
        production_recommendation_changed=False,
        public_response_changed=False,
        decisions=[decision],
    )


def _role_search_report(
    *,
    role_search_id: str = "SERIE_A",
    min_bucket_sample_size: int,
    ece_delta: float | None,
    bucket_size: float = 0.1,
    asian_handicap_line_movement_transform: str = "linear",
) -> HistoricalPrematchFeatureAsianHandicapRoleSearchReport:
    candidate = _candidate(
        role_search_id=role_search_id,
        ece_delta=ece_delta,
        asian_handicap_line_movement_transform=asian_handicap_line_movement_transform,
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
        accepted_nonzero_candidate_count=1,
        control_passed_candidate_count=0,
        watchlist_candidate_count=0,
        best_candidate=candidate,
        best_accepted_candidate=candidate,
        best_effective_candidate=candidate,
        best_control_candidate=None,
        candidates=[candidate],
        warnings=[],
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
    min_bucket_sample_size: int,
    ece_delta: float | None,
    role_search_id: str = "SERIE_A",
) -> str:
    return (
        _role_search_report(
            role_search_id=role_search_id,
            min_bucket_sample_size=min_bucket_sample_size,
            ece_delta=ece_delta,
        ).model_dump_json(indent=2)
        + "\n"
    )


def _candidate(
    *,
    role_search_id: str,
    ece_delta: float | None,
    asian_handicap_line_movement_transform: str = "linear",
) -> HistoricalPrematchFeatureAsianHandicapRoleCandidate:
    return HistoricalPrematchFeatureAsianHandicapRoleCandidate(
        rank=1,
        candidate_id=f"{role_search_id}:candidate",
        status="accepted",
        comparison_report_key=f"comparison:{role_search_id}",
        baseline_report_key=f"baseline:{role_search_id}",
        candidate_report_key=f"candidate:{role_search_id}",
        asian_handicap_movement_weight=0.05,
        min_asian_handicap_probability_delta=0.04,
        asian_handicap_line_movement_weight=0.05,
        min_asian_handicap_line_delta=0.0,
        asian_handicap_line_movement_scale=2.0,
        asian_handicap_line_movement_transform=asian_handicap_line_movement_transform,
        effective_asian_handicap_role=True,
        baseline_validation_count=42,
        candidate_validation_count=42,
        candidate_asian_handicap_feature_coverage=1.0,
        passed_non_regression_gate=True,
        ranking_score=-0.001,
        metric_deltas_json={
            "hit_rate": {"delta": 0.0},
            "brier_score": {"delta": -0.00004},
            "log_loss": {"delta": -0.00014},
            "expected_calibration_error": {"delta": ece_delta},
            "average_actual_probability": {"delta": -0.000001},
        },
        warnings=[],
    )
