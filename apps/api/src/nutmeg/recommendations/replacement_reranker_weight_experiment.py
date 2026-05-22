from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)

PREMATCH_RERANKER_FEATURES = (
    "replacement_probability",
    "replacement_decimal_odds",
    "replacement_model_edge",
    "replacement_score",
    "replacement_quality_score",
    "simulated_hit_probability",
    "simulated_roi",
    "simulated_risk_score",
    "replacement_rank",
)

LEAKAGE_EXCLUDED_FIELDS = (
    "replacement_leg_actual_hit",
    "simulated_actual_hit",
    "simulated_actual_return",
    "simulated_profit_loss",
    "actual_return_delta",
    "profit_loss_delta",
    "decision",
)


class HistoricalReplacementRerankerProfile(BaseModel):
    profile_id: str
    description: str = ""
    probability_weight: float = Field(default=0.0, ge=0.0)
    decimal_odds_weight: float = Field(default=0.0, ge=0.0)
    model_edge_weight: float = Field(default=0.0, ge=0.0)
    candidate_score_weight: float = Field(default=0.0, ge=0.0)
    replacement_quality_weight: float = Field(default=0.0, ge=0.0)
    hit_probability_weight: float = Field(default=0.0, ge=0.0)
    roi_weight: float = Field(default=0.0, ge=0.0)
    risk_penalty_weight: float = Field(default=0.0, ge=0.0)
    rank_penalty_weight: float = Field(default=0.0, ge=0.0)
    min_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    min_model_edge: float | None = None
    max_risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    use_current_model_top: bool = False


class HistoricalReplacementRerankerWeightExperimentOptions(BaseModel):
    profiles: tuple[HistoricalReplacementRerankerProfile, ...] = Field(
        default_factory=lambda: default_historical_replacement_reranker_profiles()
    )
    min_actual_best_profit_loss_delta: float = 0.0
    min_profit_loss_gap: float = 0.0
    min_candidate_hit_probability_delta_vs_model_top: float | None = None
    min_evaluated_item_count: int = Field(default=5, ge=1)
    max_hit_probability_regression_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    min_average_profit_loss_delta_vs_model_top: float = 0.0
    max_report_items: int = Field(default=50, ge=1, le=500)


class HistoricalReplacementRerankerExperimentItem(BaseModel):
    profile_id: str
    item_key: str
    competition_id: str
    slice_id: str
    removed_fixture_id: str
    removed_outcome: str
    reranked_replacement_fixture_id: str
    reranked_replacement_outcome: str
    reranked_replacement_rank: int = Field(ge=1)
    reranker_score: float
    model_top_replacement_fixture_id: str
    model_top_replacement_outcome: str
    model_top_replacement_rank: int = Field(ge=1)
    actual_best_replacement_fixture_id: str
    actual_best_replacement_outcome: str
    actual_best_replacement_rank: int = Field(ge=1)
    selected_model_top: bool
    selected_actual_best: bool
    simulated_actual_hit: bool
    replacement_leg_actual_hit: bool
    profit_loss_delta: float
    profit_loss_delta_vs_model_top: float
    hit_probability_delta_vs_model_top: float
    roi_delta_vs_model_top: float
    risk_score_delta_vs_model_top: float
    probability_delta_vs_model_top: float
    decimal_odds_delta_vs_model_top: float | None = None
    model_edge_delta_vs_model_top: float
    score_delta_vs_model_top: float
    quality_score_delta_vs_model_top: float
    hit_probability_regressed: bool
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementRerankerProfileSummary(BaseModel):
    profile_id: str
    description: str = ""
    status: str
    status_reasons: list[str] = Field(default_factory=list)
    used_feature_names: list[str] = Field(default_factory=list)
    evaluated_item_count: int = Field(ge=0)
    selected_model_top_count: int = Field(ge=0)
    selected_actual_best_count: int = Field(ge=0)
    improvement_count_vs_model_top: int = Field(ge=0)
    harm_count_vs_model_top: int = Field(ge=0)
    unchanged_count_vs_model_top: int = Field(ge=0)
    simulated_actual_hit_count: int = Field(ge=0)
    replacement_leg_actual_hit_count: int = Field(ge=0)
    hit_probability_regression_count: int = Field(ge=0)
    hit_probability_guard_filtered_count: int = Field(default=0, ge=0)
    actual_best_capture_rate: float | None = None
    improvement_rate_vs_model_top: float | None = None
    harm_rate_vs_model_top: float | None = None
    simulated_actual_hit_rate: float | None = None
    replacement_leg_actual_hit_rate: float | None = None
    hit_probability_regression_rate: float | None = None
    average_reranker_score: float | None = None
    average_selected_rank: float | None = None
    average_profit_loss_delta: float | None = None
    average_profit_loss_delta_vs_model_top: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    average_roi_delta_vs_model_top: float | None = None
    average_risk_score_delta_vs_model_top: float | None = None


class HistoricalReplacementRerankerWeightExperimentReport(BaseModel):
    report_key: str
    status: str
    source_audit_report_key: str
    eligible_item_count: int = Field(ge=0)
    profile_count: int = Field(ge=0)
    candidate_hit_probability_guard_filtered_count: int = Field(default=0, ge=0)
    best_profile_id: str | None = None
    baseline_profile_id: str = "current_quality_baseline"
    pre_match_feature_names: list[str] = Field(default_factory=list)
    leakage_excluded_fields: list[str] = Field(default_factory=list)
    profile_summaries: list[HistoricalReplacementRerankerProfileSummary] = Field(
        default_factory=list
    )
    items: list[HistoricalReplacementRerankerExperimentItem] = Field(
        default_factory=list
    )
    top_improvement_items: list[HistoricalReplacementRerankerExperimentItem] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def default_historical_replacement_reranker_profiles() -> tuple[
    HistoricalReplacementRerankerProfile,
    ...,
]:
    return (
        HistoricalReplacementRerankerProfile(
            profile_id="current_quality_baseline",
            description="Current model-top replacement from the marginal audit.",
            use_current_model_top=True,
        ),
        HistoricalReplacementRerankerProfile(
            profile_id="quality_edge_blend_v1",
            description="Blend current quality with model edge and mild odds value.",
            replacement_quality_weight=0.34,
            hit_probability_weight=0.18,
            candidate_score_weight=0.14,
            model_edge_weight=0.18,
            decimal_odds_weight=0.10,
            roi_weight=0.06,
            risk_penalty_weight=0.08,
            rank_penalty_weight=0.03,
        ),
        HistoricalReplacementRerankerProfile(
            profile_id="edge_value_v1",
            description="Lift model edge and price while keeping a probability floor.",
            replacement_quality_weight=0.20,
            hit_probability_weight=0.12,
            probability_weight=0.08,
            model_edge_weight=0.30,
            decimal_odds_weight=0.20,
            roi_weight=0.10,
            risk_penalty_weight=0.06,
            rank_penalty_weight=0.02,
            min_probability=0.25,
        ),
        HistoricalReplacementRerankerProfile(
            profile_id="odds_tempered_value_v1",
            description="Allow higher prices without fully abandoning model quality.",
            replacement_quality_weight=0.24,
            hit_probability_weight=0.14,
            candidate_score_weight=0.10,
            model_edge_weight=0.18,
            decimal_odds_weight=0.24,
            roi_weight=0.10,
            risk_penalty_weight=0.06,
            rank_penalty_weight=0.02,
            min_probability=0.22,
        ),
        HistoricalReplacementRerankerProfile(
            profile_id="probability_guarded_value_v1",
            description="Value profile with stricter hit-probability protection.",
            replacement_quality_weight=0.30,
            hit_probability_weight=0.24,
            probability_weight=0.16,
            model_edge_weight=0.16,
            decimal_odds_weight=0.08,
            roi_weight=0.06,
            risk_penalty_weight=0.10,
            rank_penalty_weight=0.03,
            min_probability=0.35,
            max_risk_score=0.70,
        ),
    )


def build_historical_replacement_reranker_weight_experiment_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalReplacementRerankerWeightExperimentOptions | None = None,
) -> HistoricalReplacementRerankerWeightExperimentReport:
    resolved_options = options or HistoricalReplacementRerankerWeightExperimentOptions()
    warnings = list(audit_report.warnings)
    eligible_items = [
        item
        for item in audit_report.items
        if _is_eligible_item(item, options=resolved_options)
    ]
    if not eligible_items:
        warnings.append("no_eligible_replacement_reranker_items")

    items: list[HistoricalReplacementRerankerExperimentItem] = []
    for profile in resolved_options.profiles:
        for audit_item in eligible_items:
            experiment_item = _experiment_item_for_profile(
                audit_item,
                profile=profile,
                options=resolved_options,
            )
            if experiment_item is not None:
                items.append(experiment_item)

    profile_summaries = [
        _profile_summary(
            profile,
            [item for item in items if item.profile_id == profile.profile_id],
            eligible_items=eligible_items,
            options=resolved_options,
        )
        for profile in resolved_options.profiles
    ]
    guard_filtered_count = sum(
        summary.hit_probability_guard_filtered_count
        for summary in profile_summaries
    )
    best_profile_id = _best_profile_id(profile_summaries)
    report_items = sorted(
        items,
        key=lambda item: (
            item.profit_loss_delta_vs_model_top,
            item.selected_actual_best,
            -item.hit_probability_delta_vs_model_top,
            item.item_key,
        ),
        reverse=True,
    )[: resolved_options.max_report_items]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_replacement_reranker_weight_experiment_v3_1"
        ),
        "source_audit_report_key": audit_report.report_key,
        "source_item_count": len(audit_report.items),
        "eligible_item_count": len(eligible_items),
        "profile_count": len(resolved_options.profiles),
        "candidate_hit_probability_guard_filtered_count": guard_filtered_count,
        "best_profile_id": best_profile_id,
        "pre_match_feature_names": list(PREMATCH_RERANKER_FEATURES),
        "leakage_excluded_fields": list(LEAKAGE_EXCLUDED_FIELDS),
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, profile_summaries, report_items)
    return HistoricalReplacementRerankerWeightExperimentReport(
        report_key=report_key,
        status="generated",
        source_audit_report_key=audit_report.report_key,
        eligible_item_count=len(eligible_items),
        profile_count=len(resolved_options.profiles),
        candidate_hit_probability_guard_filtered_count=guard_filtered_count,
        best_profile_id=best_profile_id,
        pre_match_feature_names=list(PREMATCH_RERANKER_FEATURES),
        leakage_excluded_fields=list(LEAKAGE_EXCLUDED_FIELDS),
        profile_summaries=profile_summaries,
        items=report_items,
        top_improvement_items=_top_improvement_items(items),
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    audit_report = load_historical_candidate_marginal_audit_report(args.audit_report)
    report = build_historical_replacement_reranker_weight_experiment_report(
        audit_report,
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


def _is_eligible_item(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    options: HistoricalReplacementRerankerWeightExperimentOptions,
) -> bool:
    model_top = audit_item.model_top_replacement
    actual_best = audit_item.actual_best_replacement
    if model_top is None or actual_best is None:
        return False
    if not audit_item.replacement_candidates:
        return False
    if actual_best.profit_loss_delta <= options.min_actual_best_profit_loss_delta:
        return False
    return (
        actual_best.profit_loss_delta - model_top.profit_loss_delta
        > options.min_profit_loss_gap
    )


def _experiment_item_for_profile(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    profile: HistoricalReplacementRerankerProfile,
    options: HistoricalReplacementRerankerWeightExperimentOptions,
) -> HistoricalReplacementRerankerExperimentItem | None:
    model_top = audit_item.model_top_replacement
    actual_best = audit_item.actual_best_replacement
    if model_top is None or actual_best is None:
        return None
    reranked = _select_replacement_for_profile(
        audit_item,
        profile=profile,
        options=options,
    )
    if reranked is None:
        return None
    max_rank = max(
        replacement.replacement_rank
        for replacement in audit_item.replacement_candidates
    )
    reranker_score = _score_replacement(
        reranked,
        profile=profile,
        max_rank=max_rank,
    )
    selected_model_top = _same_replacement(reranked, model_top)
    selected_actual_best = _same_replacement(reranked, actual_best)
    profit_loss_delta_vs_model_top = (
        reranked.profit_loss_delta - model_top.profit_loss_delta
    )
    hit_probability_delta_vs_model_top = (
        reranked.simulated_hit_probability - model_top.simulated_hit_probability
    )
    reason_codes = _reason_codes(
        reranked,
        model_top=model_top,
        actual_best=actual_best,
        profit_loss_delta_vs_model_top=profit_loss_delta_vs_model_top,
        hit_probability_delta_vs_model_top=hit_probability_delta_vs_model_top,
    )
    return HistoricalReplacementRerankerExperimentItem(
        profile_id=profile.profile_id,
        item_key=audit_item.item_key,
        competition_id=audit_item.competition_id,
        slice_id=audit_item.slice_id,
        removed_fixture_id=audit_item.selected_fixture_id,
        removed_outcome=audit_item.selected_outcome,
        reranked_replacement_fixture_id=reranked.replacement_fixture_id,
        reranked_replacement_outcome=reranked.replacement_outcome,
        reranked_replacement_rank=reranked.replacement_rank,
        reranker_score=reranker_score,
        model_top_replacement_fixture_id=model_top.replacement_fixture_id,
        model_top_replacement_outcome=model_top.replacement_outcome,
        model_top_replacement_rank=model_top.replacement_rank,
        actual_best_replacement_fixture_id=actual_best.replacement_fixture_id,
        actual_best_replacement_outcome=actual_best.replacement_outcome,
        actual_best_replacement_rank=actual_best.replacement_rank,
        selected_model_top=selected_model_top,
        selected_actual_best=selected_actual_best,
        simulated_actual_hit=reranked.simulated_actual_hit,
        replacement_leg_actual_hit=reranked.replacement_leg_actual_hit,
        profit_loss_delta=reranked.profit_loss_delta,
        profit_loss_delta_vs_model_top=profit_loss_delta_vs_model_top,
        hit_probability_delta_vs_model_top=hit_probability_delta_vs_model_top,
        roi_delta_vs_model_top=reranked.simulated_roi - model_top.simulated_roi,
        risk_score_delta_vs_model_top=(
            reranked.simulated_risk_score - model_top.simulated_risk_score
        ),
        probability_delta_vs_model_top=(
            reranked.replacement_probability - model_top.replacement_probability
        ),
        decimal_odds_delta_vs_model_top=_decimal_odds_delta(reranked, model_top),
        model_edge_delta_vs_model_top=(
            reranked.replacement_model_edge - model_top.replacement_model_edge
        ),
        score_delta_vs_model_top=reranked.replacement_score - model_top.replacement_score,
        quality_score_delta_vs_model_top=(
            reranked.replacement_quality_score - model_top.replacement_quality_score
        ),
        hit_probability_regressed=hit_probability_delta_vs_model_top < 0,
        reason_codes=reason_codes,
        summary_json={
            "used_feature_names": _used_feature_names(profile, options=options),
            "leakage_excluded_fields": list(LEAKAGE_EXCLUDED_FIELDS),
            "selected_probability": audit_item.selected_probability,
            "selected_decimal_odds": audit_item.selected_decimal_odds,
            "selected_model_edge": audit_item.selected_model_edge,
            "model_top_profit_loss_delta": model_top.profit_loss_delta,
            "actual_best_profit_loss_delta": actual_best.profit_loss_delta,
        },
    )


def _select_replacement_for_profile(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    profile: HistoricalReplacementRerankerProfile,
    options: HistoricalReplacementRerankerWeightExperimentOptions,
) -> HistoricalCandidateReplacementSimulation | None:
    if profile.use_current_model_top:
        return audit_item.model_top_replacement
    model_top = audit_item.model_top_replacement
    if model_top is None:
        return None
    candidates = [
        replacement
        for replacement in audit_item.replacement_candidates
        if _passes_profile_guards(replacement, profile=profile)
        and _passes_hit_probability_guard(
            replacement,
            model_top=model_top,
            options=options,
        )
    ]
    if not candidates:
        return None
    max_rank = max(replacement.replacement_rank for replacement in candidates)
    return max(
        candidates,
        key=lambda replacement: (
            _score_replacement(replacement, profile=profile, max_rank=max_rank),
            replacement.replacement_quality_score,
            replacement.simulated_hit_probability,
            replacement.simulated_roi,
            -replacement.simulated_risk_score,
            -replacement.replacement_rank,
        ),
    )


def _score_replacement(
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    profile: HistoricalReplacementRerankerProfile,
    max_rank: int,
) -> float:
    if profile.use_current_model_top:
        return replacement.replacement_quality_score
    rank_penalty = _rank_penalty(replacement.replacement_rank, max_rank=max_rank)
    score = (
        profile.probability_weight * replacement.replacement_probability
        + profile.decimal_odds_weight
        * _normalize_decimal_odds(replacement.replacement_decimal_odds)
        + profile.model_edge_weight
        * _normalize_model_edge(replacement.replacement_model_edge)
        + profile.candidate_score_weight * replacement.replacement_score
        + profile.replacement_quality_weight * replacement.replacement_quality_score
        + profile.hit_probability_weight * replacement.simulated_hit_probability
        + profile.roi_weight * _normalize_roi(replacement.simulated_roi)
        - profile.risk_penalty_weight * replacement.simulated_risk_score
        - profile.rank_penalty_weight * rank_penalty
    )
    return _clamp(score)


def _passes_profile_guards(
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    profile: HistoricalReplacementRerankerProfile,
) -> bool:
    if (
        profile.min_probability is not None
        and replacement.replacement_probability < profile.min_probability
    ):
        return False
    if (
        profile.min_model_edge is not None
        and replacement.replacement_model_edge < profile.min_model_edge
    ):
        return False
    return (
        profile.max_risk_score is None
        or replacement.simulated_risk_score <= profile.max_risk_score
    )


def _passes_hit_probability_guard(
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    model_top: HistoricalCandidateReplacementSimulation,
    options: HistoricalReplacementRerankerWeightExperimentOptions,
) -> bool:
    threshold = options.min_candidate_hit_probability_delta_vs_model_top
    if threshold is None:
        return True
    return (
        replacement.simulated_hit_probability - model_top.simulated_hit_probability
        >= threshold
    )


def _profile_summary(
    profile: HistoricalReplacementRerankerProfile,
    items: Sequence[HistoricalReplacementRerankerExperimentItem],
    *,
    eligible_items: Sequence[HistoricalCandidateMarginalAuditItem],
    options: HistoricalReplacementRerankerWeightExperimentOptions,
) -> HistoricalReplacementRerankerProfileSummary:
    evaluated_count = len(items)
    selected_model_top_count = sum(1 for item in items if item.selected_model_top)
    selected_actual_best_count = sum(1 for item in items if item.selected_actual_best)
    improvement_count = sum(
        1 for item in items if item.profit_loss_delta_vs_model_top > 0
    )
    harm_count = sum(1 for item in items if item.profit_loss_delta_vs_model_top < 0)
    unchanged_count = evaluated_count - improvement_count - harm_count
    hit_regression_count = sum(1 for item in items if item.hit_probability_regressed)
    status, status_reasons = _profile_status(
        profile,
        evaluated_count=evaluated_count,
        average_profit_loss_delta_vs_model_top=_average(
            item.profit_loss_delta_vs_model_top for item in items
        ),
        harm_count=harm_count,
        hit_probability_regression_rate=_ratio(
            hit_regression_count,
            evaluated_count,
        ),
        options=options,
    )
    return HistoricalReplacementRerankerProfileSummary(
        profile_id=profile.profile_id,
        description=profile.description,
        status=status,
        status_reasons=status_reasons,
        used_feature_names=_used_feature_names(profile, options=options),
        evaluated_item_count=evaluated_count,
        selected_model_top_count=selected_model_top_count,
        selected_actual_best_count=selected_actual_best_count,
        improvement_count_vs_model_top=improvement_count,
        harm_count_vs_model_top=harm_count,
        unchanged_count_vs_model_top=unchanged_count,
        simulated_actual_hit_count=sum(1 for item in items if item.simulated_actual_hit),
        replacement_leg_actual_hit_count=sum(
            1 for item in items if item.replacement_leg_actual_hit
        ),
        hit_probability_regression_count=hit_regression_count,
        hit_probability_guard_filtered_count=(
            _hit_probability_guard_filtered_count(
                profile,
                eligible_items=eligible_items,
                options=options,
            )
        ),
        actual_best_capture_rate=_ratio(selected_actual_best_count, evaluated_count),
        improvement_rate_vs_model_top=_ratio(improvement_count, evaluated_count),
        harm_rate_vs_model_top=_ratio(harm_count, evaluated_count),
        simulated_actual_hit_rate=_ratio(
            sum(1 for item in items if item.simulated_actual_hit),
            evaluated_count,
        ),
        replacement_leg_actual_hit_rate=_ratio(
            sum(1 for item in items if item.replacement_leg_actual_hit),
            evaluated_count,
        ),
        hit_probability_regression_rate=_ratio(hit_regression_count, evaluated_count),
        average_reranker_score=_average(item.reranker_score for item in items),
        average_selected_rank=_average(item.reranked_replacement_rank for item in items),
        average_profit_loss_delta=_average(item.profit_loss_delta for item in items),
        average_profit_loss_delta_vs_model_top=_average(
            item.profit_loss_delta_vs_model_top for item in items
        ),
        average_hit_probability_delta_vs_model_top=_average(
            item.hit_probability_delta_vs_model_top for item in items
        ),
        average_roi_delta_vs_model_top=_average(
            item.roi_delta_vs_model_top for item in items
        ),
        average_risk_score_delta_vs_model_top=_average(
            item.risk_score_delta_vs_model_top for item in items
        ),
    )


def _profile_status(
    profile: HistoricalReplacementRerankerProfile,
    *,
    evaluated_count: int,
    average_profit_loss_delta_vs_model_top: float | None,
    harm_count: int,
    hit_probability_regression_rate: float | None,
    options: HistoricalReplacementRerankerWeightExperimentOptions,
) -> tuple[str, list[str]]:
    if profile.use_current_model_top:
        return "baseline", ["current_model_top_reference"]
    reasons: list[str] = []
    if evaluated_count < options.min_evaluated_item_count:
        reasons.append("sample_size_below_threshold")
    if (
        average_profit_loss_delta_vs_model_top is None
        or average_profit_loss_delta_vs_model_top
        <= options.min_average_profit_loss_delta_vs_model_top
    ):
        reasons.append("average_profit_loss_delta_vs_model_top_below_threshold")
    if harm_count > 0:
        reasons.append("has_model_top_relative_harm")
    if (
        hit_probability_regression_rate is None
        or hit_probability_regression_rate
        > options.max_hit_probability_regression_rate
    ):
        reasons.append("hit_probability_regression_rate_above_threshold")
    if not reasons:
        return "candidate", []
    if (
        average_profit_loss_delta_vs_model_top is not None
        and average_profit_loss_delta_vs_model_top > 0
    ):
        return "watchlist", reasons
    return "rejected", reasons


def _hit_probability_guard_filtered_count(
    profile: HistoricalReplacementRerankerProfile,
    *,
    eligible_items: Sequence[HistoricalCandidateMarginalAuditItem],
    options: HistoricalReplacementRerankerWeightExperimentOptions,
) -> int:
    if (
        profile.use_current_model_top
        or options.min_candidate_hit_probability_delta_vs_model_top is None
    ):
        return 0
    filtered_count = 0
    for audit_item in eligible_items:
        model_top = audit_item.model_top_replacement
        if model_top is None:
            continue
        filtered_count += sum(
            1
            for replacement in audit_item.replacement_candidates
            if _passes_profile_guards(replacement, profile=profile)
            and not _passes_hit_probability_guard(
                replacement,
                model_top=model_top,
                options=options,
            )
        )
    return filtered_count


def _used_feature_names(
    profile: HistoricalReplacementRerankerProfile,
    *,
    options: HistoricalReplacementRerankerWeightExperimentOptions | None = None,
) -> list[str]:
    if profile.use_current_model_top:
        return ["current_model_top_reference"]
    used: list[str] = []
    weighted_features = (
        ("replacement_probability", profile.probability_weight),
        ("replacement_decimal_odds", profile.decimal_odds_weight),
        ("replacement_model_edge", profile.model_edge_weight),
        ("replacement_score", profile.candidate_score_weight),
        ("replacement_quality_score", profile.replacement_quality_weight),
        ("simulated_hit_probability", profile.hit_probability_weight),
        ("simulated_roi", profile.roi_weight),
        ("simulated_risk_score", profile.risk_penalty_weight),
        ("replacement_rank", profile.rank_penalty_weight),
    )
    for feature_name, weight in weighted_features:
        if weight > 0:
            used.append(feature_name)
    if profile.min_probability is not None:
        used.append("min_probability_guard")
    if profile.min_model_edge is not None:
        used.append("min_model_edge_guard")
    if profile.max_risk_score is not None:
        used.append("max_risk_score_guard")
    if (
        options is not None
        and options.min_candidate_hit_probability_delta_vs_model_top is not None
    ):
        used.append("min_candidate_hit_probability_delta_vs_model_top_guard")
    return used


def _reason_codes(
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    model_top: HistoricalCandidateReplacementSimulation,
    actual_best: HistoricalCandidateReplacementSimulation,
    profit_loss_delta_vs_model_top: float,
    hit_probability_delta_vs_model_top: float,
) -> list[str]:
    reasons: list[str] = []
    if _same_replacement(replacement, model_top):
        reasons.append("kept_model_top")
    else:
        reasons.append("reranked_away_from_model_top")
    if _same_replacement(replacement, actual_best):
        reasons.append("captured_actual_best_for_evaluation")
    if profit_loss_delta_vs_model_top > 0:
        reasons.append("improved_profit_loss_vs_model_top")
    if profit_loss_delta_vs_model_top < 0:
        reasons.append("harmed_profit_loss_vs_model_top")
    if hit_probability_delta_vs_model_top < 0:
        reasons.append("lower_hit_probability_than_model_top")
    if replacement.replacement_probability < model_top.replacement_probability:
        reasons.append("lower_probability_than_model_top")
    if (
        replacement.replacement_decimal_odds is not None
        and model_top.replacement_decimal_odds is not None
        and replacement.replacement_decimal_odds > model_top.replacement_decimal_odds
    ):
        reasons.append("higher_odds_than_model_top")
    return reasons


def _best_profile_id(
    summaries: Sequence[HistoricalReplacementRerankerProfileSummary],
) -> str | None:
    candidates = [
        summary for summary in summaries if summary.status in {"candidate", "watchlist"}
    ]
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda summary: (
            1 if summary.status == "candidate" else 0,
            1 if summary.harm_count_vs_model_top == 0 else 0,
            -(summary.hit_probability_regression_rate or 0.0),
            summary.average_profit_loss_delta_vs_model_top or 0.0,
            summary.actual_best_capture_rate or 0.0,
            summary.profile_id,
        ),
    )
    return best.profile_id


def _top_improvement_items(
    items: Sequence[HistoricalReplacementRerankerExperimentItem],
) -> list[HistoricalReplacementRerankerExperimentItem]:
    return sorted(
        items,
        key=lambda item: (
            item.profit_loss_delta_vs_model_top,
            item.selected_actual_best,
            item.item_key,
        ),
        reverse=True,
    )[:10]


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run pre-match replacement reranker weight experiments."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--profile-ids",
        type=str,
        default="",
        help="Comma-separated default profile ids to evaluate; empty means all.",
    )
    parser.add_argument("--min-actual-best-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-gap", type=float, default=0.0)
    parser.add_argument(
        "--min-candidate-hit-probability-delta-vs-model-top",
        type=float,
    )
    parser.add_argument("--min-evaluated-item-count", type=int, default=5)
    parser.add_argument("--max-hit-probability-regression-rate", type=float, default=0.0)
    parser.add_argument(
        "--min-average-profit-loss-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument("--max-report-items", type=int, default=50)
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementRerankerWeightExperimentOptions:
    profiles = _selected_profiles(args.profile_ids)
    return HistoricalReplacementRerankerWeightExperimentOptions(
        profiles=profiles,
        min_actual_best_profit_loss_delta=args.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=args.min_profit_loss_gap,
        min_candidate_hit_probability_delta_vs_model_top=(
            args.min_candidate_hit_probability_delta_vs_model_top
        ),
        min_evaluated_item_count=args.min_evaluated_item_count,
        max_hit_probability_regression_rate=args.max_hit_probability_regression_rate,
        min_average_profit_loss_delta_vs_model_top=(
            args.min_average_profit_loss_delta_vs_model_top
        ),
        max_report_items=args.max_report_items,
    )


def _selected_profiles(
    profile_ids: str,
) -> tuple[HistoricalReplacementRerankerProfile, ...]:
    profiles = default_historical_replacement_reranker_profiles()
    if not profile_ids:
        return profiles
    requested = {profile_id.strip() for profile_id in profile_ids.split(",")}
    requested.discard("")
    selected = tuple(profile for profile in profiles if profile.profile_id in requested)
    missing = requested - {profile.profile_id for profile in selected}
    if missing:
        raise SystemExit(f"Unknown replacement reranker profile ids: {sorted(missing)}")
    return selected


def _same_replacement(
    left: HistoricalCandidateReplacementSimulation,
    right: HistoricalCandidateReplacementSimulation,
) -> bool:
    return (
        left.replacement_fixture_id == right.replacement_fixture_id
        and left.replacement_market_type == right.replacement_market_type
        and left.replacement_outcome == right.replacement_outcome
    )


def _decimal_odds_delta(
    left: HistoricalCandidateReplacementSimulation,
    right: HistoricalCandidateReplacementSimulation,
) -> float | None:
    if left.replacement_decimal_odds is None or right.replacement_decimal_odds is None:
        return None
    return left.replacement_decimal_odds - right.replacement_decimal_odds


def _normalize_decimal_odds(decimal_odds: float | None) -> float:
    if decimal_odds is None:
        return 0.0
    return _clamp((decimal_odds - 1.0) / 4.0)


def _normalize_model_edge(model_edge: float) -> float:
    return _clamp(0.5 + model_edge * 5.0)


def _normalize_roi(roi: float) -> float:
    return _clamp(0.5 + roi / 2.0)


def _rank_penalty(rank: int, *, max_rank: int) -> float:
    if max_rank <= 1:
        return 0.0
    return _clamp((rank - 1) / (max_rank - 1))


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(max(value, low), high)


def _report_key(
    summary: dict[str, object],
    profile_summaries: Sequence[HistoricalReplacementRerankerProfileSummary],
    items: Sequence[HistoricalReplacementRerankerExperimentItem],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "profile_summaries": [
                summary_item.model_dump(mode="json")
                for summary_item in profile_summaries
            ],
            "items": [
                {
                    "profile_id": item.profile_id,
                    "item_key": item.item_key,
                    "replacement_fixture_id": item.reranked_replacement_fixture_id,
                    "replacement_outcome": item.reranked_replacement_outcome,
                }
                for item in items
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_reranker_weight_experiment:{digest}"
