from __future__ import annotations

from json import dumps
from pathlib import Path

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_gap as gap,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_spec_plan as spec_plan,
)

_BUILD_REPORT = (
    spec_plan
    .build_historical_final_answer_selection_value_signal_roi_floor_spec_plan_report
)
_LOAD_REPORT = (
    spec_plan
    .load_historical_final_answer_selection_value_signal_roi_floor_spec_plan_report
)


def test_roi_floor_spec_plan_prioritizes_clean_and_quantifies_coverage() -> None:
    report = _BUILD_REPORT(
        _gap_report(),
        movement_diagnostics_payload=_movement_payload(),
    )

    assert report.status == "plan_ready"
    assert report.spec_count == 2
    assert report.source_record_count == 3
    assert report.qualified_record_count == 2
    assert report.unique_source_record_count == 2
    assert report.unique_planned_record_profit_loss_delta == 16.0
    assert report.estimated_gap_coverage_ratio == 1.6
    assert report.planned_specs[0].movement_class == "clean_positive"
    assert report.planned_specs[0].risk_tags == []
    assert report.planned_specs[1].movement_class == "positive_with_probability_harm"
    assert "source_probability_quality_harm" in report.planned_specs[1].risk_tags
    assert report.recommended_search_json["strict_thresholds"] == {
        "min_candidate_roi": 0.0,
        "min_final_answer_hit_count_delta": 0,
        "min_profit_loss_delta": 0.0,
        "max_brier_score_delta": 0.0,
        "max_log_loss_delta": 0.0,
        "max_mean_calibration_error_delta": 0.0,
        "max_final_hit_harm_count_vs_baseline": 0,
        "max_profit_loss_harm_count_vs_baseline": 0,
    }


def test_roi_floor_spec_plan_can_filter_to_clean_positive_only() -> None:
    report = _BUILD_REPORT(
        _gap_report(),
        movement_diagnostics_payload=_movement_payload(),
        options=(
            spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions(
                movement_classes=("clean_positive",)
            )
        ),
    )

    assert report.status == "plan_ready"
    assert report.spec_count == 1
    assert report.planned_specs[0].movement_class == "clean_positive"


def test_roi_floor_spec_plan_blocks_when_gap_not_quantified() -> None:
    report = _BUILD_REPORT(
        _gap_report(status="no_gap"),
        movement_diagnostics_payload=_movement_payload(),
    )

    assert report.status == "source_gap_not_quantified"
    assert report.spec_count == 0
    assert "selection_value_signal_roi_floor_spec_plan:gap_not_quantified" in (
        report.warnings
    )


def test_roi_floor_spec_plan_cli_writes_report(tmp_path: Path) -> None:
    gap_path = tmp_path / "gap.json"
    movement_path = tmp_path / "movement.json"
    output_path = tmp_path / "plan.json"
    gap_path.write_text(
        f"{_gap_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    movement_path.write_text(dumps(_movement_payload(), indent=2), encoding="utf-8")

    spec_plan.main(
        [
            str(gap_path),
            str(movement_path),
            "--output-path",
            str(output_path),
            "--movement-classes",
            "clean_positive,positive_with_probability_harm",
        ]
    )

    saved = _LOAD_REPORT(output_path)
    assert saved.status == "plan_ready"
    assert saved.spec_count == 2


def _gap_report(
    *,
    status: str = "gap_quantified",
) -> gap.HistoricalFinalAnswerSelectionValueSignalRoiFloorGapReport:
    return gap.HistoricalFinalAnswerSelectionValueSignalRoiFloorGapReport(
        report_key="historical_final_answer_selection_value_signal_roi_floor_gap:test",
        status=status,
        production_recommendation_allowed=False,
        holdout_allowed=True,
        source_runtime_admission_report_key="runtime_admission:test",
        source_runtime_admission_status="holdout_only",
        source_runtime_replay_report_key="runtime_replay:test",
        source_runtime_replay_status="runtime_replay_passed",
        source_rule_profile_version="profile:test",
        candidate_roi=-0.02,
        candidate_roi_floor=0.0,
        candidate_roi_gap=0.02,
        baseline_roi=-0.03,
        roi_delta=0.01,
        required_roi_delta_for_floor=0.03,
        additional_roi_delta_needed=0.02,
        profit_loss_delta=5.0,
        estimated_total_stake=500.0,
        additional_profit_loss_needed=10.0,
        final_answer_count=100,
        changed_final_answer_count=1,
        movement_count=1,
        positive_movement_count=1,
        harmful_movement_count=0,
        probability_quality_harm_movement_count=0,
        final_answer_hit_delta_count=0,
        final_hit_harm_count_vs_baseline=0,
        profit_loss_harm_count_vs_baseline=0,
        average_profit_loss_delta_per_positive_movement=5.0,
        estimated_additional_clean_positive_movement_count=2,
        failed_admission_check_names=["candidate_roi"],
    )


def _movement_payload() -> dict[str, object]:
    base_spec = {
        "spec_key": "bucket_value_signal:ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000",
        "competition_ids": ["ENG_CHAMPIONSHIP"],
        "outcomes": ["draw"],
        "probability_min": 0.0,
        "probability_max": 1.0,
        "min_decimal_odds": 2.5,
        "max_decimal_odds": 3.3333333333333335,
        "max_model_edge": None,
        "score_min": 0.0,
        "score_max": 1.0,
        "max_hit_probability_deficit": 0.02,
        "min_option_roi": None,
        "max_option_risk_score": None,
        "strength": 0.32,
        "source_bucket_key": "ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000",
        "source_bucket_search_candidate_key": "bucket:test",
    }
    return {
        "report_key": "historical_final_answer_selection_value_signal_search:test",
        "candidates": [
            {
                "candidate_key": "candidate:test",
                "decision": "rejected",
                "spec": base_spec,
                "movement_diagnostics_json": {
                    "records": [
                        _record("slice_a", "clean_positive", 6.0, 0.504, False),
                        _record(
                            "slice_b",
                            "positive_with_probability_harm",
                            10.0,
                            0.508,
                            True,
                        ),
                        _record("slice_c", "harmful", -4.0, 0.506, True),
                    ]
                },
            }
        ],
    }


def _record(
    slice_id: str,
    movement_class: str,
    profit_loss_delta: float,
    score: float,
    probability_quality_harm: bool,
) -> dict[str, object]:
    return {
        "slice_id": slice_id,
        "movement_class": movement_class,
        "profit_loss_delta": profit_loss_delta,
        "roi_delta": 0.1,
        "brier_score_delta": 0.01 if probability_quality_harm else -0.01,
        "log_loss_delta": 0.01 if probability_quality_harm else -0.01,
        "mean_calibration_error_delta": 0.01 if probability_quality_harm else -0.01,
        "probability_quality_harm": probability_quality_harm,
        "candidate": {
            "selected_candidates": [
                {
                    "fixture_id": f"fixture_{slice_id}",
                    "outcome": "draw",
                    "decimal_odds": 3.2,
                    "probability": 0.31,
                    "model_edge": -0.01,
                    "score": score,
                }
            ]
        },
    }
