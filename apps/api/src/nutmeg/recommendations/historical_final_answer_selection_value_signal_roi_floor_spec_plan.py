from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_gap as roi_gap,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_search as value_search,
)

RoiFloorGapReport = (
    roi_gap.HistoricalFinalAnswerSelectionValueSignalRoiFloorGapReport
)
SelectionValueSearchSpec = (
    value_search.HistoricalFinalAnswerSelectionValueSignalSearchSpec
)

type HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanStatus = Literal[
    "plan_ready",
    "source_gap_not_quantified",
    "no_candidate_specs",
]


class HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions(BaseModel):
    movement_classes: tuple[str, ...] = (
        "clean_positive",
        "positive_with_probability_harm",
    )
    movement_score_band: float = Field(default=0.0015, ge=0.0, le=0.20)
    max_specs: int = Field(default=12, ge=1, le=256)
    min_record_profit_loss_delta: float = 0.0


class HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec(BaseModel):
    plan_rank: int = Field(ge=1)
    spec: SelectionValueSearchSpec
    source_candidate_key: str | None = None
    source_candidate_decision: str | None = None
    source_slice_id: str | None = None
    source_fixture_id: str | None = None
    source_outcome: str | None = None
    movement_class: str
    record_profit_loss_delta: float
    record_roi_delta: float | None = None
    record_brier_score_delta: float | None = None
    record_log_loss_delta: float | None = None
    record_mean_calibration_error_delta: float | None = None
    record_probability_quality_harm: bool = False
    contribution_to_gap_ratio: float | None = None
    risk_tags: list[str] = Field(default_factory=list)
    strict_acceptance_requirements: list[str] = Field(default_factory=list)


class HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanStatus
    source_roi_floor_gap_report_key: str
    source_movement_diagnostics_report_key: str | None = None
    source_gap_status: str
    candidate_roi_floor: float
    candidate_roi_gap: float | None = None
    additional_profit_loss_needed: float | None = None
    estimated_additional_clean_positive_movement_count: int | None = None
    movement_classes: list[str] = Field(default_factory=list)
    movement_score_band: float
    source_record_count: int = Field(ge=0)
    qualified_record_count: int = Field(ge=0)
    spec_count: int = Field(ge=0)
    unique_source_record_count: int = Field(ge=0)
    unique_planned_record_profit_loss_delta: float = 0.0
    estimated_gap_coverage_ratio: float | None = None
    planned_specs: list[
        HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec
    ] = Field(default_factory=list)
    recommended_search_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _MovementSpecDraft(BaseModel):
    spec: SelectionValueSearchSpec
    source_candidate_key: str | None = None
    source_candidate_decision: str | None = None
    source_slice_id: str | None = None
    source_fixture_id: str | None = None
    source_outcome: str | None = None
    movement_class: str
    record_profit_loss_delta: float
    record_roi_delta: float | None = None
    record_brier_score_delta: float | None = None
    record_log_loss_delta: float | None = None
    record_mean_calibration_error_delta: float | None = None
    record_probability_quality_harm: bool = False

    @property
    def source_record_key(self) -> str:
        return "|".join(
            [
                self.source_candidate_key or "",
                self.source_slice_id or "",
                self.movement_class,
                f"{self.record_profit_loss_delta:.12f}",
            ]
        )


def load_historical_final_answer_selection_value_signal_roi_floor_spec_plan_report(
    path: Path | str,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport:
    return (
        HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def build_historical_final_answer_selection_value_signal_roi_floor_spec_plan_report(
    roi_floor_gap_report: RoiFloorGapReport,
    *,
    movement_diagnostics_payload: Mapping[str, object],
    options: (
        HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions | None
    ) = None,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport:
    resolved_options = (
        options or HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions()
    )
    source_record_count = _source_record_count(movement_diagnostics_payload)
    warnings: list[str] = []
    drafts: list[_MovementSpecDraft] = []
    if roi_floor_gap_report.status != "gap_quantified":
        warnings.append("selection_value_signal_roi_floor_spec_plan:gap_not_quantified")
    else:
        drafts = _movement_spec_drafts(
            movement_diagnostics_payload,
            options=resolved_options,
        )
    drafts = _dedupe_and_rank_drafts(drafts)[: resolved_options.max_specs]
    planned_specs = [
        _planned_spec(
            draft,
            rank=index + 1,
            additional_profit_loss_needed=(
                roi_floor_gap_report.additional_profit_loss_needed
            ),
        )
        for index, draft in enumerate(drafts)
    ]
    if not planned_specs and roi_floor_gap_report.status == "gap_quantified":
        warnings.append("selection_value_signal_roi_floor_spec_plan:no_candidate_specs")
    unique_profit_loss = _unique_record_profit_loss(planned_specs)
    gap_coverage_ratio = _gap_coverage_ratio(
        unique_profit_loss,
        roi_floor_gap_report.additional_profit_loss_needed,
    )
    status = _status(roi_floor_gap_report, planned_specs=planned_specs)
    recommended_search = _recommended_search_json(
        options=resolved_options,
        planned_specs=planned_specs,
        candidate_roi_floor=roi_floor_gap_report.candidate_roi_floor,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_roi_floor_spec_plan_v3_1"
        ),
        "status": status,
        "source_roi_floor_gap_report_key": roi_floor_gap_report.report_key,
        "source_movement_diagnostics_report_key": _string(
            movement_diagnostics_payload.get("report_key")
        ),
        "source_gap_status": roi_floor_gap_report.status,
        "candidate_roi_floor": roi_floor_gap_report.candidate_roi_floor,
        "candidate_roi_gap": roi_floor_gap_report.candidate_roi_gap,
        "additional_profit_loss_needed": (
            roi_floor_gap_report.additional_profit_loss_needed
        ),
        "estimated_additional_clean_positive_movement_count": (
            roi_floor_gap_report.estimated_additional_clean_positive_movement_count
        ),
        "movement_classes": list(resolved_options.movement_classes),
        "movement_score_band": resolved_options.movement_score_band,
        "source_record_count": source_record_count,
        "qualified_record_count": len(drafts),
        "spec_count": len(planned_specs),
        "unique_source_record_count": _unique_source_record_count(planned_specs),
        "unique_planned_record_profit_loss_delta": unique_profit_loss,
        "estimated_gap_coverage_ratio": gap_coverage_ratio,
        "warnings": warnings,
    }
    report_key = _report_key(summary, planned_specs, recommended_search)
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport(
        report_key=report_key,
        status=status,
        source_roi_floor_gap_report_key=roi_floor_gap_report.report_key,
        source_movement_diagnostics_report_key=_string(
            movement_diagnostics_payload.get("report_key")
        ),
        source_gap_status=roi_floor_gap_report.status,
        candidate_roi_floor=roi_floor_gap_report.candidate_roi_floor,
        candidate_roi_gap=roi_floor_gap_report.candidate_roi_gap,
        additional_profit_loss_needed=(
            roi_floor_gap_report.additional_profit_loss_needed
        ),
        estimated_additional_clean_positive_movement_count=(
            roi_floor_gap_report.estimated_additional_clean_positive_movement_count
        ),
        movement_classes=list(resolved_options.movement_classes),
        movement_score_band=resolved_options.movement_score_band,
        source_record_count=source_record_count,
        qualified_record_count=len(drafts),
        spec_count=len(planned_specs),
        unique_source_record_count=_unique_source_record_count(planned_specs),
        unique_planned_record_profit_loss_delta=unique_profit_loss,
        estimated_gap_coverage_ratio=gap_coverage_ratio,
        planned_specs=planned_specs,
        recommended_search_json=recommended_search,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_final_answer_selection_value_signal_roi_floor_spec_plan_report(
        roi_gap.load_historical_final_answer_selection_value_signal_roi_floor_gap_report(
            args.roi_floor_gap_report
        ),
        movement_diagnostics_payload=loads(
            args.movement_diagnostics_report.read_text(encoding="utf-8")
        ),
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
    if report.status != "plan_ready" and not args.no_fail_process:
        raise SystemExit(1)


def _movement_spec_drafts(
    payload: Mapping[str, object],
    *,
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions,
) -> list[_MovementSpecDraft]:
    raw_candidates = payload.get("candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    drafts: list[_MovementSpecDraft] = []
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        base_spec = _spec_from_raw(raw_candidate.get("spec"))
        if base_spec is None:
            continue
        raw_diagnostics = raw_candidate.get("movement_diagnostics_json")
        if not isinstance(raw_diagnostics, Mapping):
            continue
        raw_records = raw_diagnostics.get("records")
        records = raw_records if isinstance(raw_records, list) else []
        for raw_record in records:
            drafts.extend(
                _movement_spec_drafts_from_record(
                    raw_record,
                    base_spec=base_spec,
                    raw_candidate=raw_candidate,
                    options=options,
                )
            )
    return drafts


def _movement_spec_drafts_from_record(
    raw_record: object,
    *,
    base_spec: SelectionValueSearchSpec,
    raw_candidate: Mapping[str, object],
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions,
) -> list[_MovementSpecDraft]:
    if not isinstance(raw_record, Mapping):
        return []
    movement_class = _string(raw_record.get("movement_class"))
    if movement_class not in set(options.movement_classes):
        return []
    profit_loss_delta = _optional_float(raw_record.get("profit_loss_delta"))
    if (
        profit_loss_delta is None
        or profit_loss_delta < options.min_record_profit_loss_delta
    ):
        return []
    raw_candidate_snapshot = raw_record.get("candidate")
    if not isinstance(raw_candidate_snapshot, Mapping):
        return []
    raw_selected_candidates = raw_candidate_snapshot.get("selected_candidates")
    selected_candidates = (
        raw_selected_candidates if isinstance(raw_selected_candidates, list) else []
    )
    drafts: list[_MovementSpecDraft] = []
    for raw_leg in selected_candidates:
        if not isinstance(raw_leg, Mapping):
            continue
        if not _movement_leg_matches_spec(raw_leg, base_spec):
            continue
        score = _optional_float(raw_leg.get("score"))
        if score is None:
            continue
        score_min = max(0.0, score - options.movement_score_band)
        score_max = min(1.0, score + options.movement_score_band)
        source_slice_id = _string(raw_record.get("slice_id"))
        source_fixture_id = _string(raw_leg.get("fixture_id"))
        source_outcome = _string(raw_leg.get("outcome"))
        drafts.append(
            _MovementSpecDraft(
                spec=base_spec.model_copy(
                    update={
                        "spec_key": (
                            f"{base_spec.spec_key}:roi_floor_gap_plan:"
                            f"{source_slice_id or 'unknown'}:"
                            f"{source_fixture_id or 'unknown'}:"
                            f"{source_outcome or 'unknown'}:"
                            f"score:{score_min:.4f}-{score_max:.4f}"
                        ),
                        "score_min": score_min,
                        "score_max": score_max,
                    }
                ),
                source_candidate_key=_string(raw_candidate.get("candidate_key")),
                source_candidate_decision=_string(raw_candidate.get("decision")),
                source_slice_id=source_slice_id,
                source_fixture_id=source_fixture_id,
                source_outcome=source_outcome,
                movement_class=movement_class,
                record_profit_loss_delta=profit_loss_delta,
                record_roi_delta=_optional_float(raw_record.get("roi_delta")),
                record_brier_score_delta=_optional_float(
                    raw_record.get("brier_score_delta")
                ),
                record_log_loss_delta=_optional_float(raw_record.get("log_loss_delta")),
                record_mean_calibration_error_delta=_optional_float(
                    raw_record.get("mean_calibration_error_delta")
                ),
                record_probability_quality_harm=_bool(
                    raw_record.get("probability_quality_harm")
                ),
            )
        )
    return drafts


def _planned_spec(
    draft: _MovementSpecDraft,
    *,
    rank: int,
    additional_profit_loss_needed: float | None,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec:
    contribution_ratio = _gap_coverage_ratio(
        draft.record_profit_loss_delta,
        additional_profit_loss_needed,
    )
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec(
        plan_rank=rank,
        spec=draft.spec,
        source_candidate_key=draft.source_candidate_key,
        source_candidate_decision=draft.source_candidate_decision,
        source_slice_id=draft.source_slice_id,
        source_fixture_id=draft.source_fixture_id,
        source_outcome=draft.source_outcome,
        movement_class=draft.movement_class,
        record_profit_loss_delta=draft.record_profit_loss_delta,
        record_roi_delta=draft.record_roi_delta,
        record_brier_score_delta=draft.record_brier_score_delta,
        record_log_loss_delta=draft.record_log_loss_delta,
        record_mean_calibration_error_delta=draft.record_mean_calibration_error_delta,
        record_probability_quality_harm=draft.record_probability_quality_harm,
        contribution_to_gap_ratio=contribution_ratio,
        risk_tags=_risk_tags(draft),
        strict_acceptance_requirements=[
            "candidate_roi>=floor",
            "final_answer_hit_delta_count>=0",
            "profit_loss_delta>=0",
            "brier_score_delta<=0",
            "log_loss_delta<=0",
            "mean_calibration_error_delta<=0",
            "final_hit_harm_count_vs_baseline=0",
            "profit_loss_harm_count_vs_baseline=0",
        ],
    )


def _dedupe_and_rank_drafts(
    drafts: Sequence[_MovementSpecDraft],
) -> list[_MovementSpecDraft]:
    deduped: dict[str, _MovementSpecDraft] = {}
    for draft in drafts:
        key = dumps(draft.spec.model_dump(mode="json"), sort_keys=True)
        deduped.setdefault(key, draft)
    return sorted(deduped.values(), key=_draft_sort_key)


def _draft_sort_key(draft: _MovementSpecDraft) -> tuple[int, float, str]:
    movement_priority = 0 if draft.movement_class == "clean_positive" else 1
    return (
        movement_priority,
        -draft.record_profit_loss_delta,
        draft.spec.spec_key,
    )


def _status(
    roi_floor_gap_report: RoiFloorGapReport,
    *,
    planned_specs: Sequence[HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec],
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanStatus:
    if roi_floor_gap_report.status != "gap_quantified":
        return "source_gap_not_quantified"
    if not planned_specs:
        return "no_candidate_specs"
    return "plan_ready"


def _recommended_search_json(
    *,
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions,
    planned_specs: Sequence[HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec],
    candidate_roi_floor: float,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_roi_floor_spec_plan_search_v3_1"
        ),
        "recommended_batch_size": min(2, len(planned_specs)),
        "max_planned_specs": len(planned_specs),
        "movement_classes": list(options.movement_classes),
        "movement_score_band": options.movement_score_band,
        "strict_thresholds": {
            "min_candidate_roi": candidate_roi_floor,
            "min_final_answer_hit_count_delta": 0,
            "min_profit_loss_delta": 0.0,
            "max_brier_score_delta": 0.0,
            "max_log_loss_delta": 0.0,
            "max_mean_calibration_error_delta": 0.0,
            "max_final_hit_harm_count_vs_baseline": 0,
            "max_profit_loss_harm_count_vs_baseline": 0,
        },
        "notes": [
            "Run planned specs in small batches before any proposal step.",
            "Do not activate default profiles from a spec plan alone.",
        ],
    }


def _risk_tags(draft: _MovementSpecDraft) -> list[str]:
    tags: list[str] = []
    if draft.movement_class != "clean_positive":
        tags.append(f"source_movement_class:{draft.movement_class}")
    if draft.record_probability_quality_harm:
        tags.append("source_probability_quality_harm")
    return tags


def _unique_record_profit_loss(
    planned_specs: Sequence[HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec],
) -> float:
    seen: set[str] = set()
    total = 0.0
    for planned_spec in planned_specs:
        key = _planned_spec_source_record_key(planned_spec)
        if key in seen:
            continue
        seen.add(key)
        total += planned_spec.record_profit_loss_delta
    return total


def _unique_source_record_count(
    planned_specs: Sequence[HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec],
) -> int:
    return len({_planned_spec_source_record_key(planned_spec) for planned_spec in planned_specs})


def _planned_spec_source_record_key(
    planned_spec: HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec,
) -> str:
    return "|".join(
        [
            planned_spec.source_candidate_key or "",
            planned_spec.source_slice_id or "",
            planned_spec.movement_class,
            f"{planned_spec.record_profit_loss_delta:.12f}",
        ]
    )


def _gap_coverage_ratio(
    value: float | None,
    additional_profit_loss_needed: float | None,
) -> float | None:
    if (
        value is None
        or additional_profit_loss_needed is None
        or additional_profit_loss_needed == 0.0
    ):
        return None
    return value / additional_profit_loss_needed


def _source_record_count(payload: Mapping[str, object]) -> int:
    raw_candidates = payload.get("candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    count = 0
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        raw_diagnostics = raw_candidate.get("movement_diagnostics_json")
        if not isinstance(raw_diagnostics, Mapping):
            continue
        raw_records = raw_diagnostics.get("records")
        if isinstance(raw_records, list):
            count += len(raw_records)
    return count


def _spec_from_raw(raw_spec: object) -> SelectionValueSearchSpec | None:
    if not isinstance(raw_spec, Mapping):
        return None
    try:
        return SelectionValueSearchSpec.model_validate(raw_spec)
    except ValueError:
        return None


def _movement_leg_matches_spec(
    raw_leg: Mapping[str, object],
    spec: SelectionValueSearchSpec,
) -> bool:
    outcome = _string(raw_leg.get("outcome"))
    if spec.outcomes and outcome not in set(spec.outcomes):
        return False
    decimal_odds = _optional_float(raw_leg.get("decimal_odds"))
    if decimal_odds is None:
        return False
    if decimal_odds < spec.min_decimal_odds or decimal_odds > spec.max_decimal_odds:
        return False
    probability = _optional_float(raw_leg.get("probability"))
    if probability is None:
        return False
    if probability < spec.probability_min or probability >= spec.probability_max:
        return False
    model_edge = _optional_float(raw_leg.get("model_edge"))
    return not (
        spec.max_model_edge is not None
        and model_edge is not None
        and model_edge >= spec.max_model_edge
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build a bounded selection-value spec plan from an ROI-floor gap report."
        )
    )
    parser.add_argument("roi_floor_gap_report", type=Path)
    parser.add_argument("movement_diagnostics_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--movement-classes",
        default="clean_positive,positive_with_probability_harm",
    )
    parser.add_argument("--movement-score-band", type=float, default=0.0015)
    parser.add_argument("--max-specs", type=int, default=12)
    parser.add_argument("--min-record-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions:
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanOptions(
        movement_classes=tuple(_csv(args.movement_classes)),
        movement_score_band=args.movement_score_band,
        max_specs=args.max_specs,
        min_record_profit_loss_delta=args.min_record_profit_loss_delta,
    )


def _csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _bool(value: object) -> bool:
    return value is True


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _report_key(
    summary: Mapping[str, object],
    planned_specs: Sequence[HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec],
    recommended_search: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "planned_specs": [
                    planned_spec.model_dump(mode="json")
                    for planned_spec in planned_specs
                ],
                "recommended_search": recommended_search,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_selection_value_signal_roi_floor_spec_plan:{digest}"


if __name__ == "__main__":
    main()
