from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_batch_search as batch_search,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_spec_plan as spec_plan,
)

SpecPlanReport = spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport
PlannedSpec = spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec
BatchSearchReport = (
    batch_search.HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchReport
)

type HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterStatus = Literal[
    "prefilter_ready",
    "no_searchable_specs",
    "source_plan_not_ready",
]
type HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterDecision = Literal[
    "search_allowed",
    "blocked",
]


class HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterOptions(BaseModel):
    block_previously_executed_specs: bool = True
    block_source_probability_quality_harm: bool = True
    max_source_brier_score_delta: float = 0.0
    max_source_log_loss_delta: float = 0.0
    max_source_mean_calibration_error_delta: float = 0.0
    max_searchable_specs: int = Field(default=12, ge=1, le=256)
    recommended_batch_size: int = Field(default=2, ge=1, le=20)


class HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec(BaseModel):
    plan_rank: int = Field(ge=1)
    spec_key: str
    decision: HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterDecision
    block_reasons: list[str] = Field(default_factory=list)
    movement_class: str
    record_probability_quality_harm: bool
    record_brier_score_delta: float | None = None
    record_log_loss_delta: float | None = None
    record_mean_calibration_error_delta: float | None = None
    record_profit_loss_delta: float
    source_slice_id: str | None = None
    source_fixture_id: str | None = None
    source_outcome: str | None = None
    prior_batch_report_keys: list[str] = Field(default_factory=list)
    spec: spec_plan.SelectionValueSearchSpec


class HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterStatus
    source_spec_plan_report_key: str
    source_spec_plan_status: str
    source_roi_floor_gap_report_key: str
    prior_batch_report_keys: list[str] = Field(default_factory=list)
    planned_spec_count: int = Field(ge=0)
    searchable_spec_count: int = Field(ge=0)
    blocked_spec_count: int = Field(ge=0)
    previously_executed_blocked_count: int = Field(ge=0)
    probability_quality_blocked_count: int = Field(ge=0)
    searchable_specs: list[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
    ] = Field(default_factory=list)
    blocked_specs: list[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
    ] = Field(default_factory=list)
    searchable_plan_ranks: list[int] = Field(default_factory=list)
    blocked_plan_ranks: list[int] = Field(default_factory=list)
    decisions: list[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
    ] = Field(default_factory=list)
    recommended_next_batch_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_final_answer_selection_value_signal_roi_floor_prefilter_report(
    path: Path | str,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterReport:
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_final_answer_selection_value_signal_roi_floor_prefilter_report(
    plan_report: SpecPlanReport,
    *,
    prior_batch_reports: Sequence[BatchSearchReport] = (),
    options: (
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterOptions | None
    ) = None,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterReport:
    resolved_options = (
        options or HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterOptions()
    )
    warnings: list[str] = []
    if plan_report.status != "plan_ready":
        warnings.append("selection_value_signal_roi_floor_prefilter:plan_not_ready")
        decisions: list[
            HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
        ] = []
    else:
        prior_spec_keys = _prior_spec_keys(prior_batch_reports)
        decisions = [
            _prefiltered_spec(
                planned_spec,
                prior_spec_keys=prior_spec_keys,
                options=resolved_options,
            )
            for planned_spec in plan_report.planned_specs
        ]
    searchable_specs = [
        decision
        for decision in decisions
        if decision.decision == "search_allowed"
    ][: resolved_options.max_searchable_specs]
    blocked_specs = [
        decision for decision in decisions if decision.decision == "blocked"
    ]
    searchable_plan_ranks = [decision.plan_rank for decision in searchable_specs]
    blocked_plan_ranks = [decision.plan_rank for decision in blocked_specs]
    status = _status(plan_report, searchable_specs=searchable_specs)
    recommended_next_batch = _recommended_next_batch_json(
        searchable_specs,
        options=resolved_options,
    )
    prior_batch_report_keys = [report.report_key for report in prior_batch_reports]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_roi_floor_prefilter_v3_1"
        ),
        "status": status,
        "source_spec_plan_report_key": plan_report.report_key,
        "source_spec_plan_status": plan_report.status,
        "source_roi_floor_gap_report_key": plan_report.source_roi_floor_gap_report_key,
        "prior_batch_report_keys": prior_batch_report_keys,
        "planned_spec_count": plan_report.spec_count,
        "searchable_spec_count": len(searchable_specs),
        "blocked_spec_count": len(blocked_specs),
        "previously_executed_blocked_count": _blocked_reason_count(
            decisions,
            "previously_executed",
        ),
        "probability_quality_blocked_count": _probability_quality_blocked_count(
            decisions
        ),
        "searchable_plan_ranks": searchable_plan_ranks,
        "blocked_plan_ranks": blocked_plan_ranks,
        "recommended_next_batch": recommended_next_batch,
        "warnings": warnings,
    }
    report_key = _report_key(summary, decisions)
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterReport(
        report_key=report_key,
        status=status,
        source_spec_plan_report_key=plan_report.report_key,
        source_spec_plan_status=plan_report.status,
        source_roi_floor_gap_report_key=plan_report.source_roi_floor_gap_report_key,
        prior_batch_report_keys=prior_batch_report_keys,
        planned_spec_count=plan_report.spec_count,
        searchable_spec_count=len(searchable_specs),
        blocked_spec_count=len(blocked_specs),
        previously_executed_blocked_count=_blocked_reason_count(
            decisions,
            "previously_executed",
        ),
        probability_quality_blocked_count=_probability_quality_blocked_count(decisions),
        searchable_specs=searchable_specs,
        blocked_specs=blocked_specs,
        searchable_plan_ranks=searchable_plan_ranks,
        blocked_plan_ranks=blocked_plan_ranks,
        decisions=decisions,
        recommended_next_batch_json=recommended_next_batch,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_final_answer_selection_value_signal_roi_floor_prefilter_report(
        spec_plan.load_historical_final_answer_selection_value_signal_roi_floor_spec_plan_report(
            args.spec_plan_report
        ),
        prior_batch_reports=[
            batch_search.load_historical_final_answer_selection_value_signal_roi_floor_batch_search_report(
                path
            )
            for path in args.prior_batch_report
        ],
        options=_options_from_args(args),
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if report.status != "prefilter_ready" and not args.no_fail_process:
        raise SystemExit(1)


def _prefiltered_spec(
    planned_spec: PlannedSpec,
    *,
    prior_spec_keys: Mapping[str, list[str]],
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterOptions,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec:
    block_reasons: list[str] = []
    prior_batch_keys = prior_spec_keys.get(planned_spec.spec.spec_key, [])
    if options.block_previously_executed_specs and prior_batch_keys:
        block_reasons.append("previously_executed")
    if (
        options.block_source_probability_quality_harm
        and planned_spec.record_probability_quality_harm
    ):
        block_reasons.append("source_probability_quality_harm")
    block_reasons.extend(
        _source_probability_delta_reasons(planned_spec, options=options)
    )
    decision: HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterDecision = (
        "blocked" if block_reasons else "search_allowed"
    )
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec(
        plan_rank=planned_spec.plan_rank,
        spec_key=planned_spec.spec.spec_key,
        decision=decision,
        block_reasons=block_reasons,
        movement_class=planned_spec.movement_class,
        record_probability_quality_harm=planned_spec.record_probability_quality_harm,
        record_brier_score_delta=planned_spec.record_brier_score_delta,
        record_log_loss_delta=planned_spec.record_log_loss_delta,
        record_mean_calibration_error_delta=(
            planned_spec.record_mean_calibration_error_delta
        ),
        record_profit_loss_delta=planned_spec.record_profit_loss_delta,
        source_slice_id=planned_spec.source_slice_id,
        source_fixture_id=planned_spec.source_fixture_id,
        source_outcome=planned_spec.source_outcome,
        prior_batch_report_keys=prior_batch_keys,
        spec=planned_spec.spec,
    )


def _source_probability_delta_reasons(
    planned_spec: PlannedSpec,
    *,
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterOptions,
) -> list[str]:
    reasons: list[str] = []
    if _above(
        planned_spec.record_brier_score_delta,
        options.max_source_brier_score_delta,
    ):
        reasons.append("source_brier_score_delta_above_threshold")
    if _above(
        planned_spec.record_log_loss_delta,
        options.max_source_log_loss_delta,
    ):
        reasons.append("source_log_loss_delta_above_threshold")
    if _above(
        planned_spec.record_mean_calibration_error_delta,
        options.max_source_mean_calibration_error_delta,
    ):
        reasons.append("source_mean_calibration_error_delta_above_threshold")
    return reasons


def _above(value: float | None, threshold: float) -> bool:
    return value is not None and value > threshold


def _prior_spec_keys(
    prior_batch_reports: Sequence[BatchSearchReport],
) -> dict[str, list[str]]:
    spec_keys: dict[str, list[str]] = {}
    for report in prior_batch_reports:
        search_report = report.search_report_json or {}
        raw_candidates = search_report.get("candidates")
        candidates = raw_candidates if isinstance(raw_candidates, list) else []
        for raw_candidate in candidates:
            if not isinstance(raw_candidate, Mapping):
                continue
            raw_spec = raw_candidate.get("spec")
            if not isinstance(raw_spec, Mapping):
                continue
            spec_key = raw_spec.get("spec_key")
            if isinstance(spec_key, str) and spec_key:
                spec_keys.setdefault(spec_key, []).append(report.report_key)
    return spec_keys


def _status(
    plan_report: SpecPlanReport,
    *,
    searchable_specs: Sequence[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
    ],
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterStatus:
    if plan_report.status != "plan_ready":
        return "source_plan_not_ready"
    if not searchable_specs:
        return "no_searchable_specs"
    return "prefilter_ready"


def _recommended_next_batch_json(
    searchable_specs: Sequence[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
    ],
    *,
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterOptions,
) -> dict[str, object]:
    next_specs = list(searchable_specs[: options.recommended_batch_size])
    return {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_roi_floor_prefilter_next_batch_v3_1"
        ),
        "action": (
            "run_strict_batch_search"
            if next_specs
            else "stop_selection_value_roi_floor_batch_search"
        ),
        "recommended_batch_size": len(next_specs),
        "next_plan_ranks": [spec.plan_rank for spec in next_specs],
        "next_spec_keys": [spec.spec_key for spec in next_specs],
        "notes": [
            "Prefilter is advisory for solver cost control.",
            "Strict batch search remains the admission-style evidence source.",
        ],
    }


def _blocked_reason_count(
    decisions: Sequence[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
    ],
    reason: str,
) -> int:
    return sum(1 for decision in decisions if reason in decision.block_reasons)


def _probability_quality_blocked_count(
    decisions: Sequence[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
    ],
) -> int:
    return sum(
        1
        for decision in decisions
        if any(reason.startswith("source_") for reason in decision.block_reasons)
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Prefilter ROI-floor planned specs before expensive search."
    )
    parser.add_argument("spec_plan_report", type=Path)
    parser.add_argument("--prior-batch-report", type=Path, action="append", default=[])
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--allow-previously-executed-specs", action="store_true")
    parser.add_argument("--allow-source-probability-quality-harm", action="store_true")
    parser.add_argument("--max-source-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-source-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-source-mean-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--max-searchable-specs", type=int, default=12)
    parser.add_argument("--recommended-batch-size", type=int, default=2)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterOptions:
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterOptions(
        block_previously_executed_specs=not args.allow_previously_executed_specs,
        block_source_probability_quality_harm=(
            not args.allow_source_probability_quality_harm
        ),
        max_source_brier_score_delta=args.max_source_brier_score_delta,
        max_source_log_loss_delta=args.max_source_log_loss_delta,
        max_source_mean_calibration_error_delta=(
            args.max_source_mean_calibration_error_delta
        ),
        max_searchable_specs=args.max_searchable_specs,
        recommended_batch_size=args.recommended_batch_size,
    )


def _report_key(
    summary: Mapping[str, object],
    decisions: Sequence[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilteredSpec
    ],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "decisions": [
                    decision.model_dump(mode="json") for decision in decisions
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_selection_value_signal_roi_floor_prefilter:{digest}"


if __name__ == "__main__":
    main()
