from __future__ import annotations

from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPrematchFeatureAsianHandicapSegmentDecision,
    HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport,
    HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions,
    build_historical_prematch_feature_asian_handicap_segment_refinement_report,
    load_historical_prematch_feature_asian_handicap_segment_refinement_report,
)
from nutmeg.accuracy.historical_prematch_feature_asian_handicap_segment_refinement import (
    _options_from_args,
    _parse_args,
    main,
)


def test_asian_handicap_segment_refinement_prioritizes_missing_calibration() -> None:
    report = build_historical_prematch_feature_asian_handicap_segment_refinement_report(
        _segmented_report(
            [
                _decision(
                    segment_id="SERIE_A",
                    source_status="shadow_only",
                    brier_delta=-0.00004,
                    log_loss_delta=-0.00014,
                    ece_delta=None,
                    failure_reasons=["expected_calibration_error_delta_missing"],
                )
            ]
        ),
        options=HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions(
            min_promising_validation_count=40,
        ),
    )

    assert report.status == "refinement_ready"
    assert report.refinement_candidate_count == 1
    assert report.calibration_sample_expansion_count == 1
    assert report.top_refinement_segment_ids == ["SERIE_A"]
    assert report.decisions[0].recommended_action == "calibration_sample_expansion"
    assert report.default_path_isolated is True
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False


def test_asian_handicap_segment_refinement_separates_quality_and_calibration_regression() -> None:
    report = build_historical_prematch_feature_asian_handicap_segment_refinement_report(
        _segmented_report(
            [
                _decision(
                    segment_id="BUNDESLIGA",
                    source_status="baseline_fallback",
                    brier_delta=-0.0002,
                    log_loss_delta=-0.0002,
                    ece_delta=0.00003,
                    failure_reasons=[
                        "expected_calibration_error_delta_above_maximum",
                    ],
                ),
                _decision(
                    segment_id="EPL",
                    source_status="baseline_fallback",
                    brier_delta=0.0001,
                    log_loss_delta=0.0002,
                    ece_delta=-0.00001,
                    failure_reasons=[
                        "brier_score_delta_above_maximum",
                        "log_loss_delta_above_maximum",
                    ],
                ),
            ]
        ),
    )
    decisions = {decision.segment_id: decision for decision in report.decisions}

    assert report.status == "refinement_ready"
    assert decisions["BUNDESLIGA"].recommended_action == "calibration_scope_refinement"
    assert decisions["EPL"].recommended_action == "line_transform_enrichment"
    assert report.calibration_scope_refinement_count == 1
    assert report.line_transform_enrichment_count == 1
    assert report.blocker_category_counts["calibration_regression"] == 1
    assert report.blocker_category_counts["probability_quality_regression"] == 1


def test_asian_handicap_segment_refinement_blocks_on_default_path_change() -> None:
    report = build_historical_prematch_feature_asian_handicap_segment_refinement_report(
        _segmented_report(
            [
                _decision(
                    segment_id="SERIE_A",
                    source_status="shadow_only",
                    ece_delta=None,
                    failure_reasons=["expected_calibration_error_delta_missing"],
                )
            ],
            default_path_isolated=False,
        )
    )

    assert report.status == "blocked"
    assert "asian_handicap_segment_refinement:failed_check:default_path_isolated" in (
        report.warnings
    )


def test_asian_handicap_segment_refinement_cli_writes_report(tmp_path: Path) -> None:
    source_path = tmp_path / "segmented.json"
    output_path = tmp_path / "refinement.json"
    source_path.write_text(
        f"{_segmented_report([_decision(segment_id='SERIE_A')]).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            str(source_path),
            "--refinement-id",
            "ah-segment-refinement-cli-test",
            "--output-path",
            str(output_path),
        ]
    )

    loaded = load_historical_prematch_feature_asian_handicap_segment_refinement_report(
        output_path
    )
    assert loaded.status == "refinement_ready"
    assert loaded.refinement_id == "ah-segment-refinement-cli-test"


def test_asian_handicap_segment_refinement_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "segmented.json",
            "--refinement-id",
            "ah-segment-refinement-args-test",
            "--min-refinement-candidate-count",
            "2",
            "--min-promising-validation-count",
            "50",
            "--min-hit-rate-delta",
            "-0.01",
            "--max-brier-score-delta",
            "0.01",
            "--max-log-loss-delta",
            "0.02",
            "--max-expected-calibration-error-delta",
            "0.03",
            "--allow-default-path-not-isolated",
            "--allow-production-change",
            "--allow-public-response-change",
        ]
    )

    options = _options_from_args(args)

    assert options.refinement_id == "ah-segment-refinement-args-test"
    assert options.min_refinement_candidate_count == 2
    assert options.min_promising_validation_count == 50
    assert options.min_hit_rate_delta == -0.01
    assert options.max_brier_score_delta == 0.01
    assert options.max_log_loss_delta == 0.02
    assert options.max_expected_calibration_error_delta == 0.03
    assert options.require_default_path_isolated is False
    assert options.require_no_production_change is False
    assert options.require_no_public_response_change is False


def _segmented_report(
    decisions: list[HistoricalPrematchFeatureAsianHandicapSegmentDecision],
    *,
    default_path_isolated: bool = True,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport:
    return HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport(
        report_key="historical_prematch_feature_asian_handicap_segmented_admission:test",
        status="shadow_only",
        segmented_candidate_model_allowed=False,
        shadow_allowed=True,
        default_path_isolated=default_path_isolated,
        production_recommendation_changed=False,
        public_response_changed=False,
        admission_id="ah-segmented-test",
        source_report_count=len(decisions),
        accepted_segment_count=sum(1 for item in decisions if item.status == "accepted"),
        shadow_segment_count=sum(1 for item in decisions if item.status == "shadow_only"),
        fallback_segment_count=sum(
            1 for item in decisions if item.status == "baseline_fallback"
        ),
        rejected_segment_count=sum(1 for item in decisions if item.status == "rejected"),
        accepted_validation_count=0,
        shadow_validation_count=sum(
            item.validation_count for item in decisions if item.status == "shadow_only"
        ),
        fallback_validation_count=sum(
            item.validation_count
            for item in decisions
            if item.status == "baseline_fallback"
        ),
        accepted_segment_deltas_json={},
        decisions=decisions,
    )


def _decision(
    *,
    segment_id: str,
    source_status: str = "shadow_only",
    validation_count: int = 42,
    brier_delta: float = -0.00004,
    log_loss_delta: float = -0.00014,
    hit_delta: float = 0.0,
    ece_delta: float | None = None,
    failure_reasons: list[str] | None = None,
) -> HistoricalPrematchFeatureAsianHandicapSegmentDecision:
    return HistoricalPrematchFeatureAsianHandicapSegmentDecision(
        segment_id=segment_id,
        source_report_key=f"source:{segment_id}",
        source_role_search_id=f"role-search:{segment_id}",
        status=source_status,
        selected_candidate_id=f"candidate:{segment_id}",
        selected_candidate_status="accepted",
        accepted_nonzero_candidate_count=1,
        candidate_count=1,
        validation_count=validation_count,
        asian_handicap_movement_weight=0.05,
        min_asian_handicap_probability_delta=0.04,
        asian_handicap_line_movement_weight=0.05,
        min_asian_handicap_line_delta=0.0,
        hit_rate_delta=hit_delta,
        brier_score_delta=brier_delta,
        log_loss_delta=log_loss_delta,
        expected_calibration_error_delta=ece_delta,
        average_actual_probability_delta=0.0,
        failure_reasons=(
            failure_reasons or ["expected_calibration_error_delta_missing"]
        ),
    )
