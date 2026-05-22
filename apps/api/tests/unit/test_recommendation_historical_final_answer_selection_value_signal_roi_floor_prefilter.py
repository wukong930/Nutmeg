from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_batch_search as batch_search,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_prefilter as prefilter,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_spec_plan as spec_plan,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_search as value_search,
)

_BUILD_REPORT = (
    prefilter
    .build_historical_final_answer_selection_value_signal_roi_floor_prefilter_report
)
_LOAD_REPORT = (
    prefilter
    .load_historical_final_answer_selection_value_signal_roi_floor_prefilter_report
)


def test_roi_floor_prefilter_allows_clean_specs_and_blocks_source_quality_harm() -> None:
    report = _BUILD_REPORT(_plan_report())

    assert report.status == "prefilter_ready"
    assert report.planned_spec_count == 2
    assert report.searchable_spec_count == 1
    assert report.blocked_spec_count == 1
    assert report.searchable_plan_ranks == [1]
    assert report.blocked_plan_ranks == [2]
    assert report.searchable_specs[0].spec_key == "spec_0"
    assert "source_probability_quality_harm" in report.blocked_specs[0].block_reasons
    assert report.recommended_next_batch_json["action"] == "run_strict_batch_search"
    assert report.recommended_next_batch_json["recommended_batch_size"] == 1


def test_roi_floor_prefilter_blocks_previous_execution_and_stops_when_empty() -> None:
    report = _BUILD_REPORT(
        _plan_report(),
        prior_batch_reports=[_prior_batch_report(executed_spec_keys=["spec_0"])],
    )

    assert report.status == "no_searchable_specs"
    assert report.searchable_spec_count == 0
    assert report.blocked_spec_count == 2
    assert report.previously_executed_blocked_count == 1
    assert report.probability_quality_blocked_count == 1
    assert report.blocked_specs[0].block_reasons == ["previously_executed"]
    assert "source_probability_quality_harm" in report.blocked_specs[1].block_reasons
    assert (
        report.recommended_next_batch_json["action"]
        == "stop_selection_value_roi_floor_batch_search"
    )


def test_roi_floor_prefilter_blocks_non_ready_plan() -> None:
    report = _BUILD_REPORT(_plan_report(status="source_gap_not_quantified"))

    assert report.status == "source_plan_not_ready"
    assert report.searchable_spec_count == 0
    assert report.blocked_spec_count == 0
    assert "selection_value_signal_roi_floor_prefilter:plan_not_ready" in (
        report.warnings
    )


def test_roi_floor_prefilter_cli_writes_report(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    prior_batch_path = tmp_path / "batch.json"
    output_path = tmp_path / "prefilter.json"
    plan_path.write_text(
        f"{_plan_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    prior_batch_path.write_text(
        f"{_prior_batch_report(executed_spec_keys=['spec_0']).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    prefilter.main(
        [
            str(plan_path),
            "--prior-batch-report",
            str(prior_batch_path),
            "--output-path",
            str(output_path),
            "--no-fail-process",
        ]
    )

    saved = _LOAD_REPORT(output_path)
    assert saved.status == "no_searchable_specs"
    assert saved.searchable_spec_count == 0
    assert saved.blocked_plan_ranks == [1, 2]


def _plan_report(
    *,
    status: str = "plan_ready",
) -> spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport:
    planned_specs = [
        spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec(
            plan_rank=1,
            spec=_spec("spec_0"),
            movement_class="clean_positive",
            record_profit_loss_delta=4.0,
            record_brier_score_delta=-0.01,
            record_log_loss_delta=-0.01,
            record_mean_calibration_error_delta=-0.01,
            record_probability_quality_harm=False,
            strict_acceptance_requirements=["candidate_roi>=floor"],
        ),
        spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec(
            plan_rank=2,
            spec=_spec("spec_1"),
            movement_class="positive_with_probability_harm",
            record_profit_loss_delta=8.0,
            record_brier_score_delta=0.01,
            record_log_loss_delta=0.01,
            record_mean_calibration_error_delta=0.01,
            record_probability_quality_harm=True,
            strict_acceptance_requirements=["candidate_roi>=floor"],
        ),
    ]
    return spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport(
        report_key="historical_final_answer_selection_value_signal_roi_floor_spec_plan:test",
        status=status,
        source_roi_floor_gap_report_key="gap:test",
        source_gap_status="gap_quantified",
        candidate_roi_floor=0.0,
        movement_score_band=0.0015,
        source_record_count=2,
        qualified_record_count=2,
        spec_count=2,
        unique_source_record_count=2,
        planned_specs=planned_specs,
    )


def _prior_batch_report(
    *,
    executed_spec_keys: list[str],
) -> batch_search.HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchReport:
    return batch_search.HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchReport(
        report_key="historical_final_answer_selection_value_signal_roi_floor_batch_search:test",
        status="batch_search_no_acceptance",
        source_spec_plan_report_key="historical_final_answer_selection_value_signal_roi_floor_spec_plan:test",
        source_spec_plan_status="plan_ready",
        source_roi_floor_gap_report_key="gap:test",
        batch_index=0,
        batch_size=2,
        batch_start=0,
        batch_end=len(executed_spec_keys),
        planned_spec_count=2,
        executed_spec_count=len(executed_spec_keys),
        accepted_count=0,
        rejected_count=len(executed_spec_keys),
        candidate_roi_floor=0.0,
        search_report_json={
            "candidates": [
                {"candidate_key": f"candidate:{key}", "spec": {"spec_key": key}}
                for key in executed_spec_keys
            ]
        },
    )


def _spec(
    spec_key: str,
) -> value_search.HistoricalFinalAnswerSelectionValueSignalSearchSpec:
    return value_search.HistoricalFinalAnswerSelectionValueSignalSearchSpec(
        spec_key=spec_key,
        competition_ids=("ENG_CHAMPIONSHIP",),
        outcomes=("draw",),
        min_decimal_odds=2.5,
        max_decimal_odds=3.33,
        strength=0.32,
    )
