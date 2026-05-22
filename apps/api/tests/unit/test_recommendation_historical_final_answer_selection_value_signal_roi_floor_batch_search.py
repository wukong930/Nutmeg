from __future__ import annotations

from pathlib import Path

import pytest

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_batch_search as batch_search,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_spec_plan as spec_plan,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_search as value_search,
)

_BUILD_REPORT = (
    batch_search
    .build_historical_final_answer_selection_value_signal_roi_floor_batch_search_report
)
_LOAD_REPORT = (
    batch_search
    .load_historical_final_answer_selection_value_signal_roi_floor_batch_search_report
)


def test_roi_floor_batch_search_runs_selected_batch_with_strict_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_spec_keys: list[str] = []
    captured_min_candidate_roi: list[float] = []

    def fake_search(
        historical_slices: object,
        *,
        options: value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions,
    ) -> value_search.HistoricalFinalAnswerSelectionValueSignalSearchReport:
        del historical_slices
        captured_spec_keys.extend(spec.spec_key for spec in options.candidate_specs)
        captured_min_candidate_roi.append(options.min_candidate_roi)
        return _search_report(
            accepted=True,
            spec=options.candidate_specs[0],
        )

    monkeypatch.setattr(
        batch_search.value_search,
        "build_historical_final_answer_selection_value_signal_search_report",
        fake_search,
    )

    report = _BUILD_REPORT(
        [],
        plan_report=_plan_report(spec_count=3),
        options=batch_search.HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchOptions(
            batch_index=1,
            batch_size=2,
        ),
    )

    assert report.status == "batch_search_passed"
    assert report.batch_start == 2
    assert report.batch_end == 3
    assert report.executed_spec_count == 1
    assert report.accepted_count == 1
    assert captured_spec_keys == ["spec_2"]
    assert captured_min_candidate_roi == [0.0]
    assert report.strict_thresholds_json["max_brier_score_delta"] == 0.0


def test_roi_floor_batch_search_reports_no_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_search(
        historical_slices: object,
        *,
        options: value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions,
    ) -> value_search.HistoricalFinalAnswerSelectionValueSignalSearchReport:
        del historical_slices
        return _search_report(accepted=False, spec=options.candidate_specs[0])

    monkeypatch.setattr(
        batch_search.value_search,
        "build_historical_final_answer_selection_value_signal_search_report",
        fake_search,
    )

    report = _BUILD_REPORT(
        [],
        plan_report=_plan_report(spec_count=2),
    )

    assert report.status == "batch_search_no_acceptance"
    assert report.executed_spec_count == 2
    assert report.accepted_count == 0
    assert report.rejected_count == 2


def test_roi_floor_batch_search_blocks_non_ready_plan() -> None:
    report = _BUILD_REPORT(
        [],
        plan_report=_plan_report(spec_count=1, status="source_gap_not_quantified"),
    )

    assert report.status == "source_plan_not_ready"
    assert report.executed_spec_count == 0
    assert "selection_value_signal_roi_floor_batch_search:plan_not_ready" in (
        report.warnings
    )


def test_roi_floor_batch_search_cli_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "batch.json"
    plan_path.write_text(
        f"{_plan_report(spec_count=1).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(batch_search, "_historical_slices_from_args", lambda args: [])

    def fake_search(
        historical_slices: object,
        *,
        options: value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions,
    ) -> value_search.HistoricalFinalAnswerSelectionValueSignalSearchReport:
        del historical_slices
        return _search_report(accepted=True, spec=options.candidate_specs[0])

    monkeypatch.setattr(
        batch_search.value_search,
        "build_historical_final_answer_selection_value_signal_search_report",
        fake_search,
    )

    batch_search.main(
        [
            str(plan_path),
            "dummy_slice.json",
            "--output-path",
            str(output_path),
            "--batch-index",
            "0",
            "--batch-size",
            "1",
        ]
    )

    saved = _LOAD_REPORT(output_path)
    assert saved.status == "batch_search_passed"
    assert saved.accepted_count == 1


def _plan_report(
    *,
    spec_count: int,
    status: str = "plan_ready",
) -> spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport:
    planned_specs = [
        spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec(
            plan_rank=index + 1,
            spec=_spec(f"spec_{index}"),
            movement_class="clean_positive",
            record_profit_loss_delta=4.0,
            strict_acceptance_requirements=["candidate_roi>=floor"],
        )
        for index in range(spec_count)
    ]
    return spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport(
        report_key="historical_final_answer_selection_value_signal_roi_floor_spec_plan:test",
        status=status,
        source_roi_floor_gap_report_key="gap:test",
        source_gap_status="gap_quantified",
        candidate_roi_floor=0.0,
        movement_score_band=0.0015,
        source_record_count=spec_count,
        qualified_record_count=spec_count,
        spec_count=spec_count,
        unique_source_record_count=spec_count,
        planned_specs=planned_specs,
    )


def _search_report(
    *,
    accepted: bool,
    spec: value_search.HistoricalFinalAnswerSelectionValueSignalSearchSpec,
) -> value_search.HistoricalFinalAnswerSelectionValueSignalSearchReport:
    candidate = value_search.HistoricalFinalAnswerSelectionValueSignalSearchCandidate(
        candidate_key="candidate:accepted" if accepted else "candidate:rejected",
        decision="accepted" if accepted else "rejected",
        decision_reasons=[] if accepted else ["candidate_roi:below_threshold"],
        spec=spec,
        suite_key="suite:test",
        suite_status="improved",
    )
    return value_search.HistoricalFinalAnswerSelectionValueSignalSearchReport(
        report_key="historical_final_answer_selection_value_signal_search:test",
        baseline_suite_key="suite:baseline",
        baseline_suite_status="unchanged",
        candidate_count=1 if accepted else 2,
        accepted_count=1 if accepted else 0,
        rejected_count=0 if accepted else 2,
        best_candidate=candidate if accepted else None,
        accepted_candidates=[candidate] if accepted else [],
        candidates=[candidate],
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
