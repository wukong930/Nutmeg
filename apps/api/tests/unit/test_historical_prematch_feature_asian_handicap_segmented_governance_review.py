from __future__ import annotations

from pathlib import Path

from nutmeg.accuracy import (
    HistoricalPrematchFeatureAsianHandicapSegmentDecision,
    HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport,
    HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewOptions,
    build_historical_prematch_feature_asian_handicap_segmented_governance_review_report,
    load_historical_prematch_feature_asian_handicap_segmented_governance_review_report,
)
from nutmeg.accuracy.historical_prematch_feature_asian_handicap_segmented_governance_review import (
    _options_from_args,
    _parse_args,
    main,
)


def test_asian_handicap_segmented_governance_review_is_ready_for_clean_admission() -> None:
    source = _segmented_admission_report()

    report = build_historical_prematch_feature_asian_handicap_segmented_governance_review_report(
        [source],
        options=HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewOptions(
            min_calibration_sample_expansion_applied_count=2,
        ),
    )

    assert report.status == "governance_ready"
    assert report.governance_review_ready is True
    assert report.internal_review_only is True
    assert report.production_recommendation_allowed is False
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert report.accepted_segment_count == 3
    assert report.fallback_segment_count == 2
    assert report.calibration_sample_expansion_applied_count == 2
    assert report.accepted_validation_count == 140
    assert report.staged_profile_json["dry_run_only"] is True
    assert len(report.staged_profile_json["accepted_segments"]) == 3
    assert all(check.status == "passed" for check in report.checks)


def test_asian_handicap_segmented_governance_review_watchlists_metric_regression() -> None:
    source = _segmented_admission_report(
        accepted_segment_deltas_json={
            "hit_rate_delta": 0.0,
            "brier_score_delta": 0.0001,
            "log_loss_delta": -0.0002,
            "expected_calibration_error_delta": -0.0001,
            "average_actual_probability_delta": 0.0001,
        }
    )

    report = build_historical_prematch_feature_asian_handicap_segmented_governance_review_report(
        [source]
    )

    assert report.status == "watchlist"
    assert report.governance_review_ready is False
    assert "accepted_brier_score_delta" in report.blockers
    assert report.production_recommendation_changed is False


def test_asian_handicap_segmented_governance_review_blocks_runtime_surface_change() -> None:
    source = _segmented_admission_report().model_copy(
        update={
            "default_path_isolated": False,
            "production_recommendation_changed": True,
            "public_response_changed": True,
        }
    )

    report = build_historical_prematch_feature_asian_handicap_segmented_governance_review_report(
        [source]
    )

    assert report.status == "blocked"
    assert report.governance_review_ready is False
    assert "default_path_isolated" in report.blockers
    assert "production_recommendation_changed" in report.blockers
    assert "public_response_changed" in report.blockers


def test_asian_handicap_segmented_governance_review_cli_options_and_main(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "segmented_admission.json"
    output_path = tmp_path / "governance_review.json"
    source_path.write_text(
        f"{_segmented_admission_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--segmented-admission-report",
            str(source_path),
            "--output-path",
            str(output_path),
            "--review-id",
            "unit-governance-review",
            "--min-source-admission-count",
            "1",
            "--min-ready-admission-count",
            "1",
            "--min-accepted-segment-count",
            "3",
            "--max-fallback-segment-count",
            "2",
            "--min-calibration-sample-expansion-applied-count",
            "2",
            "--allow-source-admission-not-accepted",
            "--allow-segmented-candidate-model-not-allowed",
            "--allow-non-internal-review-profile",
        ]
    )
    options = _options_from_args(args)

    assert options.review_id == "unit-governance-review"
    assert options.min_calibration_sample_expansion_applied_count == 2
    assert options.require_all_source_admissions_accepted is False
    assert options.require_segmented_candidate_model_allowed is False
    assert options.require_internal_review_only_profile is False

    main(
        [
            "--segmented-admission-report",
            str(source_path),
            "--output-path",
            str(output_path),
            "--review-id",
            "unit-governance-review",
            "--min-calibration-sample-expansion-applied-count",
            "2",
        ]
    )

    saved = (
        load_historical_prematch_feature_asian_handicap_segmented_governance_review_report(
            output_path
        )
    )
    assert saved.status == "governance_ready"
    assert saved.review_id == "unit-governance-review"


def _segmented_admission_report(
    *,
    accepted_segment_deltas_json: dict[str, object] | None = None,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport:
    deltas = accepted_segment_deltas_json or {
        "hit_rate_delta": 0.0,
        "brier_score_delta": -0.001,
        "log_loss_delta": -0.0014,
        "expected_calibration_error_delta": -0.0003,
        "average_actual_probability_delta": 0.0002,
    }
    return HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport(
        report_key="historical_prematch_feature_asian_handicap_segmented_admission:test",
        status="accepted",
        segmented_candidate_model_allowed=True,
        shadow_allowed=True,
        default_path_isolated=True,
        production_recommendation_changed=False,
        public_response_changed=False,
        admission_id="unit-segmented-admission",
        source_report_count=5,
        accepted_segment_count=3,
        shadow_segment_count=0,
        fallback_segment_count=2,
        rejected_segment_count=0,
        calibration_sample_expansion_report_count=2,
        calibration_sample_expansion_applied_count=2,
        accepted_validation_count=140,
        shadow_validation_count=0,
        fallback_validation_count=98,
        accepted_segment_deltas_json=deltas,
        accepted_segment_ids=["EPL", "LIGUE_1", "SERIE_A"],
        fallback_segment_ids=["LA_LIGA", "BUNDESLIGA"],
        shadow_segment_ids=[],
        rejected_segment_ids=[],
        decisions=[
            _decision("EPL", validation_count=50),
            _decision(
                "LIGUE_1",
                validation_count=48,
                transform="quarter_step",
                calibration_sample_expansion_applied=True,
            ),
            _decision(
                "SERIE_A",
                validation_count=42,
                calibration_sample_expansion_applied=True,
            ),
            _decision("LA_LIGA", status="baseline_fallback", validation_count=44),
            _decision("BUNDESLIGA", status="baseline_fallback", validation_count=54),
        ],
        checks=[],
        warnings=["asian_handicap_segmented_admission:accepted"],
        decision_payload_json={},
        summary_json={},
    )


def _decision(
    segment_id: str,
    *,
    status: str = "accepted",
    validation_count: int,
    transform: str = "linear",
    calibration_sample_expansion_applied: bool = False,
) -> HistoricalPrematchFeatureAsianHandicapSegmentDecision:
    return HistoricalPrematchFeatureAsianHandicapSegmentDecision(
        segment_id=segment_id,
        source_report_key=f"role-search-report:{segment_id}",
        source_role_search_id=f"role-search:{segment_id}",
        status=status,
        selected_candidate_id=f"candidate:{segment_id}",
        selected_candidate_status="accepted" if status == "accepted" else "watchlist",
        accepted_nonzero_candidate_count=1 if status == "accepted" else 0,
        candidate_count=24,
        validation_count=validation_count,
        asian_handicap_movement_weight=0.05,
        min_asian_handicap_probability_delta=0.04,
        asian_handicap_line_movement_weight=0.05,
        min_asian_handicap_line_delta=0.0,
        asian_handicap_line_movement_transform=transform,
        hit_rate_delta=0.0,
        brier_score_delta=-0.001,
        log_loss_delta=-0.001,
        expected_calibration_error_delta=-0.0001,
        average_actual_probability_delta=0.0001,
        calibration_sample_expansion_report_key=(
            f"calibration:{segment_id}" if calibration_sample_expansion_applied else None
        ),
        calibration_sample_expansion_applied=calibration_sample_expansion_applied,
        failure_reasons=[] if status == "accepted" else ["hit_rate_delta_below_minimum"],
        warning_codes=[],
        summary_json={},
    )
