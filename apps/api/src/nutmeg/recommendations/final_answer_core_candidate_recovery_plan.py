from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_prefilter as roi_prefilter,
)
from nutmeg.recommendations import (
    quality_signal_diagnostics as diagnostics,
)

QualitySignalDiagnosticReport = diagnostics.HistoricalQualitySignalDiagnosticReport
QualitySignalGroup = diagnostics.HistoricalQualitySignalGroup
SelectionValuePrefilterReport = (
    roi_prefilter.HistoricalFinalAnswerSelectionValueSignalRoiFloorPrefilterReport
)

type FinalAnswerCoreCandidateRecoveryPlanStatus = Literal[
    "plan_ready",
    "no_searchable_candidate_groups",
]
type FinalAnswerCoreCandidateRecoveryDecision = Literal[
    "search_candidate",
    "blocked_prior_evidence",
]


class FinalAnswerCoreCandidateRecoveryPlanOptions(BaseModel):
    min_group_final_answer_count: int = Field(default=5, ge=1)
    max_plan_items: int = Field(default=8, ge=1, le=64)
    include_global_groups: bool = False
    block_prior_evidence: bool = True
    strength_values: tuple[float, ...] = (0.04, 0.08, 0.12)
    severe_strength_values: tuple[float, ...] = (0.08, 0.12, 0.24)
    severe_roi_threshold: float = -0.20
    max_decimal_odds_ceiling: float = Field(default=20.0, gt=1.0)
    prior_overlap_min_probability_ratio: float = Field(default=0.50, ge=0.0, le=1.0)
    prior_overlap_min_odds_ratio: float = Field(default=0.50, ge=0.0, le=1.0)


class FinalAnswerCoreCandidateRecoveryPriorEvidence(BaseModel):
    report_key: str
    status: str | None = None
    passed: bool | None = None
    suite_status: str | None = None
    signature: str | None = None
    competition_ids: tuple[str, ...] = ()
    probability_min: float | None = None
    probability_max: float | None = None
    min_decimal_odds: float | None = None
    max_decimal_odds: float | None = None
    max_model_edge: float | None = None
    penalty_strength: float | None = None
    candidate_roi: float | None = None
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None


class FinalAnswerCoreCandidateRecoveryPlanItem(BaseModel):
    rank: int = Field(ge=1)
    decision: FinalAnswerCoreCandidateRecoveryDecision
    source_group_key: str
    source_group_type: str
    source_label: str
    priority_score: float
    block_reasons: list[str] = Field(default_factory=list)
    prior_evidence_keys: list[str] = Field(default_factory=list)
    candidate_family: str = "final_answer_quality_signal_value_guard"
    competition_ids: tuple[str, ...] = ()
    probability_min: float = Field(ge=0.0, le=1.0)
    probability_max: float = Field(ge=0.0, le=1.0)
    min_decimal_odds: float = Field(gt=1.0)
    max_decimal_odds: float = Field(gt=1.0)
    max_model_edge: float
    strength_values: tuple[float, ...]
    source_final_answer_count: int = Field(ge=0)
    source_final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    source_roi: float | None = None
    source_profit_loss: float
    source_average_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    source_average_decimal_odds: float | None = Field(default=None, gt=1.0)
    source_average_model_edge: float | None = None
    recommended_grid_args: dict[str, object] = Field(default_factory=dict)


class FinalAnswerCoreCandidateRecoveryPlanReport(BaseModel):
    report_key: str
    status: FinalAnswerCoreCandidateRecoveryPlanStatus
    source_quality_signal_report_key: str
    source_quality_signal_status: str
    source_final_answer_count: int = Field(ge=0)
    source_final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    source_roi: float | None = None
    source_profit_loss: float
    source_selection_value_prefilter_report_key: str | None = None
    source_selection_value_prefilter_status: str | None = None
    prior_evidence_count: int = Field(default=0, ge=0)
    candidate_group_count: int = Field(default=0, ge=0)
    searchable_candidate_group_count: int = Field(default=0, ge=0)
    blocked_prior_evidence_count: int = Field(default=0, ge=0)
    plan_items: list[FinalAnswerCoreCandidateRecoveryPlanItem] = Field(
        default_factory=list
    )
    searchable_plan_items: list[FinalAnswerCoreCandidateRecoveryPlanItem] = Field(
        default_factory=list
    )
    blocked_plan_items: list[FinalAnswerCoreCandidateRecoveryPlanItem] = Field(
        default_factory=list
    )
    recommended_next_search_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _CandidateScope(BaseModel):
    competition_ids: tuple[str, ...] = ()
    probability_min: float = Field(ge=0.0, le=1.0)
    probability_max: float = Field(ge=0.0, le=1.0)
    min_decimal_odds: float = Field(gt=1.0)
    max_decimal_odds: float = Field(gt=1.0)
    max_model_edge: float


def load_quality_signal_diagnostic_report(
    path: Path | str,
) -> QualitySignalDiagnosticReport:
    return QualitySignalDiagnosticReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_final_answer_core_candidate_recovery_plan_report(
    path: Path | str,
) -> FinalAnswerCoreCandidateRecoveryPlanReport:
    return FinalAnswerCoreCandidateRecoveryPlanReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_final_answer_core_candidate_recovery_plan_report(
    quality_signal_report: QualitySignalDiagnosticReport,
    *,
    selection_value_prefilter_report: SelectionValuePrefilterReport | None = None,
    prior_evidence_payloads: Sequence[Mapping[str, object]] = (),
    options: FinalAnswerCoreCandidateRecoveryPlanOptions | None = None,
) -> FinalAnswerCoreCandidateRecoveryPlanReport:
    resolved_options = options or FinalAnswerCoreCandidateRecoveryPlanOptions()
    prior_evidence = [
        evidence
        for payload in prior_evidence_payloads
        for evidence in _prior_evidence_entries_from_payload(payload)
    ]
    prior_by_signature = {
        evidence.signature: evidence
        for evidence in prior_evidence
        if evidence.signature is not None
    }
    candidates = _candidate_items(
        quality_signal_report,
        prior_by_signature=prior_by_signature,
        prior_evidence=prior_evidence,
        options=resolved_options,
    )
    plan_items = candidates[: resolved_options.max_plan_items]
    searchable_items = [
        item for item in plan_items if item.decision == "search_candidate"
    ]
    blocked_items = [
        item for item in plan_items if item.decision == "blocked_prior_evidence"
    ]
    status: FinalAnswerCoreCandidateRecoveryPlanStatus = (
        "plan_ready" if searchable_items else "no_searchable_candidate_groups"
    )
    warnings = _warnings(
        selection_value_prefilter_report=selection_value_prefilter_report,
        searchable_items=searchable_items,
    )
    recommended_next_search = _recommended_next_search_json(searchable_items)
    summary: dict[str, object] = {
        "calculation_basis": "final_answer_core_candidate_recovery_plan_v3_1",
        "status": status,
        "source_quality_signal_report_key": quality_signal_report.report_key,
        "source_quality_signal_status": quality_signal_report.status,
        "source_final_answer_count": quality_signal_report.final_answer_count,
        "source_final_answer_hit_rate": quality_signal_report.final_answer_hit_rate,
        "source_roi": quality_signal_report.roi,
        "source_profit_loss": quality_signal_report.profit_loss,
        "source_selection_value_prefilter_report_key": (
            selection_value_prefilter_report.report_key
            if selection_value_prefilter_report is not None
            else None
        ),
        "source_selection_value_prefilter_status": (
            selection_value_prefilter_report.status
            if selection_value_prefilter_report is not None
            else None
        ),
        "prior_evidence_count": len(prior_evidence),
        "candidate_group_count": len(plan_items),
        "searchable_candidate_group_count": len(searchable_items),
        "blocked_prior_evidence_count": len(blocked_items),
        "recommended_next_search": recommended_next_search,
        "warnings": warnings,
    }
    report_key = _report_key(summary, plan_items)
    return FinalAnswerCoreCandidateRecoveryPlanReport(
        report_key=report_key,
        status=status,
        source_quality_signal_report_key=quality_signal_report.report_key,
        source_quality_signal_status=quality_signal_report.status,
        source_final_answer_count=quality_signal_report.final_answer_count,
        source_final_answer_hit_rate=quality_signal_report.final_answer_hit_rate,
        source_roi=quality_signal_report.roi,
        source_profit_loss=quality_signal_report.profit_loss,
        source_selection_value_prefilter_report_key=(
            selection_value_prefilter_report.report_key
            if selection_value_prefilter_report is not None
            else None
        ),
        source_selection_value_prefilter_status=(
            selection_value_prefilter_report.status
            if selection_value_prefilter_report is not None
            else None
        ),
        prior_evidence_count=len(prior_evidence),
        candidate_group_count=len(plan_items),
        searchable_candidate_group_count=len(searchable_items),
        blocked_prior_evidence_count=len(blocked_items),
        plan_items=plan_items,
        searchable_plan_items=searchable_items,
        blocked_plan_items=blocked_items,
        recommended_next_search_json=recommended_next_search,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_final_answer_core_candidate_recovery_plan_report(
        load_quality_signal_diagnostic_report(args.quality_signal_report),
        selection_value_prefilter_report=(
            roi_prefilter.load_historical_final_answer_selection_value_signal_roi_floor_prefilter_report(
                args.selection_value_prefilter_report
            )
            if args.selection_value_prefilter_report is not None
            else None
        ),
        prior_evidence_payloads=[
            _json_payload(path) for path in args.prior_evidence_report
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
    if report.status != "plan_ready" and not args.no_fail_process:
        raise SystemExit(1)


def _candidate_items(
    quality_signal_report: QualitySignalDiagnosticReport,
    *,
    prior_by_signature: Mapping[
        str,
        FinalAnswerCoreCandidateRecoveryPriorEvidence,
    ],
    prior_evidence: Sequence[FinalAnswerCoreCandidateRecoveryPriorEvidence],
    options: FinalAnswerCoreCandidateRecoveryPlanOptions,
) -> list[FinalAnswerCoreCandidateRecoveryPlanItem]:
    candidates: list[FinalAnswerCoreCandidateRecoveryPlanItem] = []
    for group in quality_signal_report.groups:
        if not _negative_enough(group, options=options):
            continue
        draft = _candidate_item_from_group(
            group,
            prior_by_signature=prior_by_signature,
            prior_evidence=prior_evidence,
            options=options,
        )
        if draft is not None:
            candidates.append(draft)
    deduped = _dedupe_candidate_items(candidates)
    ranked = sorted(
        deduped,
        key=lambda item: (
            item.decision != "search_candidate",
            -item.priority_score,
            item.source_group_key,
        ),
    )
    return [
        item.model_copy(update={"rank": index + 1})
        for index, item in enumerate(ranked)
    ]


def _negative_enough(
    group: QualitySignalGroup,
    *,
    options: FinalAnswerCoreCandidateRecoveryPlanOptions,
) -> bool:
    if group.final_answer_count < options.min_group_final_answer_count:
        return False
    return group.profit_loss < 0.0 and group.roi is not None and group.roi < 0.0


def _candidate_item_from_group(
    group: QualitySignalGroup,
    *,
    prior_by_signature: Mapping[
        str,
        FinalAnswerCoreCandidateRecoveryPriorEvidence,
    ],
    prior_evidence: Sequence[FinalAnswerCoreCandidateRecoveryPriorEvidence],
    options: FinalAnswerCoreCandidateRecoveryPlanOptions,
) -> FinalAnswerCoreCandidateRecoveryPlanItem | None:
    scope = _scope_from_group(group, options=options)
    if scope is None:
        return None
    signature = _signature(
        competition_ids=scope.competition_ids,
        probability_min=scope.probability_min,
        probability_max=scope.probability_max,
        min_decimal_odds=scope.min_decimal_odds,
        max_decimal_odds=scope.max_decimal_odds,
        max_model_edge=scope.max_model_edge,
    )
    exact_prior = prior_by_signature.get(signature)
    overlapping_priors = _overlapping_prior_evidence(
        scope,
        source_group_type=group.group_type,
        prior_evidence=prior_evidence,
        options=options,
    )
    block_reasons: list[str] = []
    prior_evidence_keys: list[str] = []
    if exact_prior is not None and options.block_prior_evidence:
        block_reasons.append("prior_evidence_for_same_candidate_scope")
        prior_evidence_keys.append(exact_prior.report_key)
    for prior in overlapping_priors:
        if prior.report_key in prior_evidence_keys or not options.block_prior_evidence:
            continue
        block_reasons.append("prior_evidence_for_overlapping_candidate_scope")
        prior_evidence_keys.append(prior.report_key)
    decision: FinalAnswerCoreCandidateRecoveryDecision = (
        "blocked_prior_evidence" if block_reasons else "search_candidate"
    )
    strength_values = _strength_values(group, options=options)
    return FinalAnswerCoreCandidateRecoveryPlanItem(
        rank=1,
        decision=decision,
        source_group_key=group.group_key,
        source_group_type=group.group_type,
        source_label=group.label,
        priority_score=_priority_score(group),
        block_reasons=block_reasons,
        prior_evidence_keys=prior_evidence_keys,
        competition_ids=scope.competition_ids,
        probability_min=scope.probability_min,
        probability_max=scope.probability_max,
        min_decimal_odds=scope.min_decimal_odds,
        max_decimal_odds=scope.max_decimal_odds,
        max_model_edge=scope.max_model_edge,
        strength_values=strength_values,
        source_final_answer_count=group.final_answer_count,
        source_final_answer_hit_rate=group.final_answer_hit_rate,
        source_roi=group.roi,
        source_profit_loss=group.profit_loss,
        source_average_probability=group.average_probability,
        source_average_decimal_odds=group.average_decimal_odds,
        source_average_model_edge=group.average_model_edge,
        recommended_grid_args=_recommended_grid_args(
            scope,
            strength_values=strength_values,
        ),
    )


def _scope_from_group(
    group: QualitySignalGroup,
    *,
    options: FinalAnswerCoreCandidateRecoveryPlanOptions,
) -> _CandidateScope | None:
    parts = group.group_key.split(":")
    competition_ids: tuple[str, ...] = ()
    probability_min = 0.0
    probability_max = 1.0
    min_decimal_odds = 1.000001
    max_decimal_odds = options.max_decimal_odds_ceiling
    max_model_edge = 0.0
    if group.group_type == "competition_probability_band" and len(parts) >= 3:
        competition_ids = (parts[1],)
        probability_min, probability_max = _probability_range(parts[2])
    elif group.group_type == "competition_odds_band" and len(parts) >= 3:
        competition_ids = (parts[1],)
        min_decimal_odds, max_decimal_odds = _odds_range(
            parts[2],
            ceiling=options.max_decimal_odds_ceiling,
        )
    elif group.group_type == "competition_model_edge_band" and len(parts) >= 3:
        competition_ids = (parts[1],)
        max_model_edge = _max_model_edge(parts[2])
    elif options.include_global_groups and group.group_type == "probability_band":
        probability_min, probability_max = _probability_range(group.band or "")
    elif options.include_global_groups and group.group_type == "odds_band":
        min_decimal_odds, max_decimal_odds = _odds_range(
            group.band or "",
            ceiling=options.max_decimal_odds_ceiling,
        )
    elif options.include_global_groups and group.group_type == "model_edge_band":
        max_model_edge = _max_model_edge(group.band or "")
    else:
        return None
    if probability_min >= probability_max:
        return None
    if min_decimal_odds > max_decimal_odds:
        return None
    return _CandidateScope(
        competition_ids=competition_ids,
        probability_min=probability_min,
        probability_max=probability_max,
        min_decimal_odds=min_decimal_odds,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
    )


def _probability_range(band: str) -> tuple[float, float]:
    ranges = {
        "very_low": (0.0, 0.35),
        "low": (0.35, 0.50),
        "medium": (0.50, 0.65),
        "high": (0.65, 0.80),
        "very_high": (0.80, 1.0),
    }
    return ranges.get(band, (0.0, 1.0))


def _odds_range(
    band: str,
    *,
    ceiling: float,
) -> tuple[float, float]:
    ranges = {
        "short_price": (1.000001, 1.35),
        "medium_short_price": (1.35, 1.80),
        "medium_price": (1.80, 2.50),
        "long_price": (2.50, 4.00),
        "very_long_price": (4.00, ceiling),
    }
    return ranges.get(band, (1.000001, ceiling))


def _max_model_edge(band: str) -> float:
    if band == "negative_large":
        return -0.05
    if band == "negative":
        return 0.0
    return 0.0


def _priority_score(group: QualitySignalGroup) -> float:
    roi_pressure = abs(group.roi or 0.0) * group.final_answer_count
    return round(max(-group.profit_loss, 0.0) + roi_pressure, 12)


def _strength_values(
    group: QualitySignalGroup,
    *,
    options: FinalAnswerCoreCandidateRecoveryPlanOptions,
) -> tuple[float, ...]:
    if group.roi is not None and group.roi <= options.severe_roi_threshold:
        return options.severe_strength_values
    return options.strength_values


def _dedupe_candidate_items(
    items: Sequence[FinalAnswerCoreCandidateRecoveryPlanItem],
) -> list[FinalAnswerCoreCandidateRecoveryPlanItem]:
    by_signature: dict[str, FinalAnswerCoreCandidateRecoveryPlanItem] = {}
    for item in items:
        signature = _signature(
            competition_ids=item.competition_ids,
            probability_min=item.probability_min,
            probability_max=item.probability_max,
            min_decimal_odds=item.min_decimal_odds,
            max_decimal_odds=item.max_decimal_odds,
            max_model_edge=item.max_model_edge,
        )
        current = by_signature.get(signature)
        if current is None or item.priority_score > current.priority_score:
            by_signature[signature] = item
    return list(by_signature.values())


def _overlapping_prior_evidence(
    scope: _CandidateScope,
    *,
    source_group_type: str,
    prior_evidence: Sequence[FinalAnswerCoreCandidateRecoveryPriorEvidence],
    options: FinalAnswerCoreCandidateRecoveryPlanOptions,
) -> list[FinalAnswerCoreCandidateRecoveryPriorEvidence]:
    overlaps: list[FinalAnswerCoreCandidateRecoveryPriorEvidence] = []
    for prior in prior_evidence:
        if not _same_competition_scope(scope.competition_ids, prior.competition_ids):
            continue
        if not _prior_has_complete_scope(prior):
            continue
        if prior.max_model_edge is not None and prior.max_model_edge > (
            scope.max_model_edge + 1e-12
        ):
            continue
        probability_overlap = _interval_overlap_ratio(
            scope.probability_min,
            scope.probability_max,
            prior.probability_min,
            prior.probability_max,
        )
        odds_overlap = _interval_overlap_ratio(
            scope.min_decimal_odds,
            scope.max_decimal_odds,
            prior.min_decimal_odds,
            prior.max_decimal_odds,
        )
        if source_group_type == "competition_probability_band":
            if probability_overlap >= options.prior_overlap_min_probability_ratio:
                overlaps.append(prior)
        elif source_group_type == "competition_odds_band":
            if odds_overlap >= options.prior_overlap_min_odds_ratio:
                overlaps.append(prior)
        elif (
            source_group_type == "competition_model_edge_band"
            and probability_overlap >= 0.80
            and odds_overlap >= 0.80
        ):
            overlaps.append(prior)
    return overlaps


def _same_competition_scope(
    left: Sequence[str],
    right: Sequence[str],
) -> bool:
    return tuple(left) == tuple(right)


def _prior_has_complete_scope(
    prior: FinalAnswerCoreCandidateRecoveryPriorEvidence,
) -> bool:
    return (
        prior.probability_min is not None
        and prior.probability_max is not None
        and prior.min_decimal_odds is not None
        and prior.max_decimal_odds is not None
        and prior.max_model_edge is not None
    )


def _interval_overlap_ratio(
    min_value: float,
    max_value: float,
    prior_min_value: float | None,
    prior_max_value: float | None,
) -> float:
    if prior_min_value is None or prior_max_value is None:
        return 0.0
    width = max(max_value - min_value, 0.0)
    if width <= 0:
        return 0.0
    overlap = max(0.0, min(max_value, prior_max_value) - max(min_value, prior_min_value))
    return overlap / width


def _prior_evidence_from_payload(
    payload: Mapping[str, object],
) -> FinalAnswerCoreCandidateRecoveryPriorEvidence | None:
    summary = payload.get("summary_json")
    if not isinstance(summary, Mapping):
        summary = payload
    source = _prior_evidence_scope_source(payload, summary)
    competition_ids = _string_tuple(
        source.get("final_answer_quality_signal_competition_ids")
    )
    probability_min = _optional_float(source.get("final_answer_quality_signal_probability_min"))
    probability_max = _optional_float(source.get("final_answer_quality_signal_probability_max"))
    min_decimal_odds = _optional_float(source.get("final_answer_quality_signal_min_decimal_odds"))
    max_decimal_odds = _optional_float(source.get("final_answer_quality_signal_max_decimal_odds"))
    max_model_edge = _optional_float(source.get("final_answer_quality_signal_max_model_edge"))
    if (
        probability_min is None
        or probability_max is None
        or min_decimal_odds is None
        or max_decimal_odds is None
        or max_model_edge is None
    ):
        return None
    signature = _signature(
        competition_ids=competition_ids,
        probability_min=probability_min,
        probability_max=probability_max,
        min_decimal_odds=min_decimal_odds,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
    )
    aggregate_deltas = summary.get("aggregate_deltas")
    if not isinstance(aggregate_deltas, Mapping):
        aggregate_deltas = payload.get("aggregate_deltas_json")
    if not isinstance(aggregate_deltas, Mapping):
        aggregate_deltas = {}
    return FinalAnswerCoreCandidateRecoveryPriorEvidence(
        report_key=_report_key_from_payload(payload),
        status=_optional_string(payload.get("status")),
        passed=_optional_bool(payload.get("passed")),
        suite_status=_optional_string(payload.get("suite_status")),
        signature=signature,
        competition_ids=competition_ids,
        probability_min=probability_min,
        probability_max=probability_max,
        min_decimal_odds=min_decimal_odds,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
        penalty_strength=_optional_float(
            source.get("final_answer_quality_signal_penalty_strength")
        ),
        candidate_roi=_optional_float(source.get("candidate_roi")),
        final_hit_rate_delta=_optional_float(
            aggregate_deltas.get("final_hit_rate_delta")
        ),
        roi_delta=_optional_float(aggregate_deltas.get("roi_delta")),
        profit_loss_delta=_optional_float(aggregate_deltas.get("profit_loss_delta")),
    )


def _prior_evidence_entries_from_payload(
    payload: Mapping[str, object],
) -> list[FinalAnswerCoreCandidateRecoveryPriorEvidence]:
    entries = _prior_evidence_from_profile_payload(payload)
    single_entry = _prior_evidence_from_payload(payload)
    if single_entry is not None:
        entries.append(single_entry)
    return entries


def _prior_evidence_from_profile_payload(
    payload: Mapping[str, object],
) -> list[FinalAnswerCoreCandidateRecoveryPriorEvidence]:
    raw_profiles = payload.get("profiles")
    profiles = raw_profiles if isinstance(raw_profiles, list) else []
    if not profiles:
        return []
    profile_version = _optional_string(payload.get("profile_version")) or "unknown"
    entries: list[FinalAnswerCoreCandidateRecoveryPriorEvidence] = []
    for profile in profiles:
        if not isinstance(profile, Mapping):
            continue
        competition_id = _optional_string(profile.get("competition_id"))
        if competition_id is None:
            continue
        raw_guards = profile.get("final_answer_value_guards")
        guards = raw_guards if isinstance(raw_guards, list) else []
        for index, guard in enumerate(guards, start=1):
            if not isinstance(guard, Mapping):
                continue
            entry = _prior_evidence_from_profile_guard(
                guard,
                competition_id=competition_id,
                profile_version=profile_version,
                guard_index=index,
            )
            if entry is not None:
                entries.append(entry)
    return entries


def _prior_evidence_from_profile_guard(
    guard: Mapping[str, object],
    *,
    competition_id: str,
    profile_version: str,
    guard_index: int,
) -> FinalAnswerCoreCandidateRecoveryPriorEvidence | None:
    probability_min = _optional_float(guard.get("probability_min"))
    probability_max = _optional_float(guard.get("probability_max"))
    min_decimal_odds = _optional_float(guard.get("min_decimal_odds"))
    max_decimal_odds = _optional_float(guard.get("max_decimal_odds"))
    max_model_edge = _optional_float(guard.get("max_model_edge"))
    if max_model_edge is None:
        max_model_edge = 0.0
    if (
        probability_min is None
        or probability_max is None
        or min_decimal_odds is None
        or max_decimal_odds is None
    ):
        return None
    competition_ids = (competition_id,)
    signature = _signature(
        competition_ids=competition_ids,
        probability_min=probability_min,
        probability_max=probability_max,
        min_decimal_odds=min_decimal_odds,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
    )
    source_report_key = _optional_string(guard.get("source_report_key"))
    report_key = (
        f"{source_report_key}:profile_guard:{competition_id}:{guard_index}"
        if source_report_key is not None
        else (
            "competition_profile_guard:"
            f"{profile_version}:{competition_id}:{guard_index}"
        )
    )
    return FinalAnswerCoreCandidateRecoveryPriorEvidence(
        report_key=report_key,
        status="active_profile_guard",
        signature=signature,
        competition_ids=competition_ids,
        probability_min=probability_min,
        probability_max=probability_max,
        min_decimal_odds=min_decimal_odds,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
        penalty_strength=_optional_float(guard.get("penalty_strength")),
    )


def _prior_evidence_scope_source(
    payload: Mapping[str, object],
    summary: Mapping[str, object],
) -> Mapping[str, object]:
    if "final_answer_quality_signal_competition_ids" in summary:
        return summary
    raw_candidates = payload.get("candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    if not candidates:
        return summary
    first_candidate = candidates[0]
    if not isinstance(first_candidate, Mapping):
        return summary
    return {
        "final_answer_quality_signal_competition_ids": first_candidate.get(
            "competition_ids"
        ),
        "final_answer_quality_signal_probability_min": first_candidate.get(
            "probability_min"
        ),
        "final_answer_quality_signal_probability_max": first_candidate.get(
            "probability_max"
        ),
        "final_answer_quality_signal_min_decimal_odds": first_candidate.get(
            "min_decimal_odds"
        ),
        "final_answer_quality_signal_max_decimal_odds": first_candidate.get(
            "max_decimal_odds"
        ),
        "final_answer_quality_signal_max_model_edge": first_candidate.get(
            "max_model_edge"
        ),
        "final_answer_quality_signal_penalty_strength": first_candidate.get(
            "strength"
        ),
        "candidate_roi": first_candidate.get("roi"),
    }


def _report_key_from_payload(payload: Mapping[str, object]) -> str:
    for key in ("report_key", "gate_key", "candidate_key"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return "prior_evidence:unknown"


def _recommended_next_search_json(
    searchable_items: Sequence[FinalAnswerCoreCandidateRecoveryPlanItem],
) -> dict[str, object]:
    if not searchable_items:
        return {
            "action": "review_candidate_surface_or_relax_planner_scope",
            "next_item_rank": None,
        }
    first = searchable_items[0]
    return {
        "action": "run_final_answer_quality_signal_profile_grid",
        "next_item_rank": first.rank,
        "source_group_key": first.source_group_key,
        "candidate_family": first.candidate_family,
        "grid_args": first.recommended_grid_args,
        "acceptance_floor": {
            "min_final_hit_count_delta": 0,
            "min_roi_delta": 0.0,
            "min_profit_loss_delta": 0.0,
            "max_brier_score_delta": 0.0,
            "max_log_loss_delta": 0.0,
            "max_mean_calibration_error_delta": 0.0,
            "max_final_hit_harm_count_vs_baseline": 0,
            "max_profit_loss_harm_count_vs_baseline": 0,
        },
    }


def _recommended_grid_args(
    scope: _CandidateScope,
    *,
    strength_values: Sequence[float],
) -> dict[str, object]:
    return {
        "competition_group": ",".join(scope.competition_ids),
        "probability_min_values": scope.probability_min,
        "probability_max_values": scope.probability_max,
        "min_decimal_odds_values": scope.min_decimal_odds,
        "max_decimal_odds_values": scope.max_decimal_odds,
        "max_model_edge_values": scope.max_model_edge,
        "strength_values": ",".join(f"{value:g}" for value in strength_values),
    }


def _warnings(
    *,
    selection_value_prefilter_report: SelectionValuePrefilterReport | None,
    searchable_items: Sequence[FinalAnswerCoreCandidateRecoveryPlanItem],
) -> list[str]:
    warnings: list[str] = []
    if (
        selection_value_prefilter_report is not None
        and selection_value_prefilter_report.status == "no_searchable_specs"
    ):
        warnings.append("core_candidate_recovery:selection_value_prefilter_exhausted")
    if not searchable_items:
        warnings.append("core_candidate_recovery:no_searchable_candidate_groups")
    return warnings


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Plan the next core final-answer candidate search from diagnostics."
    )
    parser.add_argument("quality_signal_report", type=Path)
    parser.add_argument("--selection-value-prefilter-report", type=Path)
    parser.add_argument("--prior-evidence-report", type=Path, action="append", default=[])
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-group-final-answer-count", type=int, default=5)
    parser.add_argument("--max-plan-items", type=int, default=8)
    parser.add_argument(
        "--include-global-groups",
        action=BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--block-prior-evidence",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--strength-values", default="0.04,0.08,0.12")
    parser.add_argument("--severe-strength-values", default="0.08,0.12,0.24")
    parser.add_argument("--severe-roi-threshold", type=float, default=-0.20)
    parser.add_argument("--max-decimal-odds-ceiling", type=float, default=20.0)
    parser.add_argument("--prior-overlap-min-probability-ratio", type=float, default=0.50)
    parser.add_argument("--prior-overlap-min-odds-ratio", type=float, default=0.50)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> FinalAnswerCoreCandidateRecoveryPlanOptions:
    return FinalAnswerCoreCandidateRecoveryPlanOptions(
        min_group_final_answer_count=args.min_group_final_answer_count,
        max_plan_items=args.max_plan_items,
        include_global_groups=args.include_global_groups,
        block_prior_evidence=args.block_prior_evidence,
        strength_values=_float_tuple(args.strength_values),
        severe_strength_values=_float_tuple(args.severe_strength_values),
        severe_roi_threshold=args.severe_roi_threshold,
        max_decimal_odds_ceiling=args.max_decimal_odds_ceiling,
        prior_overlap_min_probability_ratio=(
            args.prior_overlap_min_probability_ratio
        ),
        prior_overlap_min_odds_ratio=args.prior_overlap_min_odds_ratio,
    )


def _json_payload(path: Path) -> Mapping[str, object]:
    payload = loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, Mapping) else {}


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in value.split(",") if item.strip())


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _signature(
    *,
    competition_ids: Sequence[str],
    probability_min: float,
    probability_max: float,
    min_decimal_odds: float,
    max_decimal_odds: float,
    max_model_edge: float,
) -> str:
    competitions = ",".join(competition_ids)
    return (
        f"competitions:{competitions}|"
        f"prob:{probability_min:.6f}-{probability_max:.6f}|"
        f"odds:{min_decimal_odds:.6f}-{max_decimal_odds:.6f}|"
        f"edge_max:{max_model_edge:.6f}"
    )


def _report_key(
    summary: Mapping[str, object],
    items: Sequence[FinalAnswerCoreCandidateRecoveryPlanItem],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "items": [item.model_dump(mode="json") for item in items],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"final_answer_core_candidate_recovery_plan:{digest}"


if __name__ == "__main__":
    main()
