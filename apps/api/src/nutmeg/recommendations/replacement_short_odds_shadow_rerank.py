from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
from math import floor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)

type HistoricalShortOddsShadowSelectionRule = Literal[
    "current_model_top",
    "max_short_odds_within_deficit",
    "max_model_edge_within_deficit",
    "nearest_model_top_probability",
    "probability_preserving_model_edge",
    "probability_preserving_quality_score",
]

type HistoricalShortOddsShadowProfileStatus = Literal[
    "baseline",
    "shadow_candidate",
    "shadow_watchlist",
    "rejected",
]

PREMATCH_SHORT_ODDS_SHADOW_FEATURES = (
    "competition_id",
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

OFFLINE_SHORT_ODDS_SHADOW_EVALUATION_FIELDS = (
    "replacement_leg_actual_hit",
    "simulated_actual_hit",
    "simulated_actual_return",
    "simulated_profit_loss",
    "actual_return_delta",
    "profit_loss_delta",
    "decision",
    "actual_best_replacement",
)

DEFAULT_SHORT_ODDS_SHADOW_COMPETITIONS = (
    "EPL",
    "ESP_LA_LIGA",
    "FRA_LIGUE_1",
    "GER_BUNDESLIGA",
    "ITA_SERIE_A",
)


class HistoricalShortOddsShadowRerankProfile(BaseModel):
    profile_id: str
    description: str = ""
    selection_rule: HistoricalShortOddsShadowSelectionRule


class HistoricalShortOddsShadowRerankOptions(BaseModel):
    profiles: tuple[HistoricalShortOddsShadowRerankProfile, ...] = Field(
        default_factory=lambda: default_historical_short_odds_shadow_profiles()
    )
    focus_competition_ids: tuple[str, ...] = DEFAULT_SHORT_ODDS_SHADOW_COMPETITIONS
    min_actual_best_profit_loss_delta: float = 0.0
    min_profit_loss_gap: float = 0.0
    min_replacement_probability: float = Field(default=0.55, ge=0.0, le=1.0)
    min_replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_replacement_decimal_odds: float = Field(default=1.75, gt=1.0)
    min_candidate_hit_probability_delta_vs_model_top: float = -0.015
    max_candidate_hit_probability_delta_vs_model_top: float = 0.0
    min_decimal_odds_delta_vs_model_top: float = 0.0
    min_evaluated_item_count: int = Field(default=30, ge=1)
    min_simulated_actual_hit_delta_count_vs_model_top: int = 0
    min_replacement_leg_hit_delta_count_vs_model_top: int = 0
    min_average_profit_loss_delta_vs_model_top: float = 0.0
    max_harm_count_vs_model_top: int = Field(default=0, ge=0)
    max_report_items: int = Field(default=80, ge=1, le=500)


class HistoricalShortOddsShadowRerankItem(BaseModel):
    profile_id: str
    selection_rule: HistoricalShortOddsShadowSelectionRule
    item_key: str
    competition_id: str
    slice_id: str
    removed_fixture_id: str
    removed_outcome: str
    shadow_replacement_fixture_id: str
    shadow_replacement_outcome: str
    shadow_replacement_rank: int = Field(ge=1)
    model_top_replacement_fixture_id: str
    model_top_replacement_outcome: str
    model_top_replacement_rank: int = Field(ge=1)
    actual_best_replacement_fixture_id: str
    actual_best_replacement_outcome: str
    actual_best_replacement_rank: int = Field(ge=1)
    qualified_candidate_count: int = Field(ge=0)
    selected_model_top: bool
    selected_actual_best: bool
    simulated_actual_hit: bool
    model_top_simulated_actual_hit: bool
    replacement_leg_actual_hit: bool
    model_top_replacement_leg_actual_hit: bool
    profit_loss_delta_vs_model_top: float
    hit_probability_delta_vs_model_top: float
    roi_delta_vs_model_top: float
    risk_score_delta_vs_model_top: float
    probability_delta_vs_model_top: float
    decimal_odds_delta_vs_model_top: float | None = None
    model_edge_delta_vs_model_top: float
    score_delta_vs_model_top: float
    quality_score_delta_vs_model_top: float
    expected_hit_probability_regressed: bool
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalShortOddsShadowCompetitionSummary(BaseModel):
    competition_id: str
    evaluated_item_count: int = Field(ge=0)
    changed_count_vs_model_top: int = Field(ge=0)
    simulated_actual_hit_delta_count_vs_model_top: int
    replacement_leg_hit_delta_count_vs_model_top: int
    improvement_count_vs_model_top: int = Field(ge=0)
    harm_count_vs_model_top: int = Field(ge=0)
    selected_actual_best_count: int = Field(ge=0)
    average_profit_loss_delta_vs_model_top: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    average_decimal_odds_delta_vs_model_top: float | None = None


class HistoricalShortOddsShadowProfileSummary(BaseModel):
    profile_id: str
    description: str = ""
    selection_rule: HistoricalShortOddsShadowSelectionRule
    status: HistoricalShortOddsShadowProfileStatus
    status_reasons: list[str] = Field(default_factory=list)
    used_feature_names: list[str] = Field(default_factory=list)
    evaluated_item_count: int = Field(ge=0)
    changed_count_vs_model_top: int = Field(ge=0)
    selected_model_top_count: int = Field(ge=0)
    selected_actual_best_count: int = Field(ge=0)
    qualified_candidate_count: int = Field(ge=0)
    improvement_count_vs_model_top: int = Field(ge=0)
    harm_count_vs_model_top: int = Field(ge=0)
    simulated_actual_hit_count: int = Field(ge=0)
    model_top_simulated_actual_hit_count: int = Field(ge=0)
    simulated_actual_hit_delta_count_vs_model_top: int
    replacement_leg_hit_count: int = Field(ge=0)
    model_top_replacement_leg_hit_count: int = Field(ge=0)
    replacement_leg_hit_delta_count_vs_model_top: int
    expected_hit_probability_regression_count: int = Field(ge=0)
    changed_rate_vs_model_top: float | None = None
    selected_actual_best_rate: float | None = None
    simulated_actual_hit_rate: float | None = None
    model_top_simulated_actual_hit_rate: float | None = None
    replacement_leg_hit_rate: float | None = None
    model_top_replacement_leg_hit_rate: float | None = None
    average_qualified_candidate_count: float | None = None
    average_profit_loss_delta_vs_model_top: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    average_roi_delta_vs_model_top: float | None = None
    average_risk_score_delta_vs_model_top: float | None = None
    average_decimal_odds_delta_vs_model_top: float | None = None
    competition_summaries: list[HistoricalShortOddsShadowCompetitionSummary] = Field(
        default_factory=list
    )


class HistoricalShortOddsShadowRerankReport(BaseModel):
    report_key: str
    status: str
    source_audit_report_key: str
    eligible_item_count: int = Field(ge=0)
    profile_count: int = Field(ge=0)
    shadow_candidate_count: int = Field(ge=0)
    shadow_watchlist_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    baseline_profile_id: str = "current_model_top"
    pre_match_feature_names: list[str] = Field(default_factory=list)
    offline_evaluation_fields: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    profile_summaries: list[HistoricalShortOddsShadowProfileSummary] = Field(
        default_factory=list
    )
    items: list[HistoricalShortOddsShadowRerankItem] = Field(default_factory=list)
    top_improvement_items: list[HistoricalShortOddsShadowRerankItem] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def default_historical_short_odds_shadow_profiles() -> tuple[
    HistoricalShortOddsShadowRerankProfile,
    ...,
]:
    return (
        HistoricalShortOddsShadowRerankProfile(
            profile_id="current_model_top",
            description="Current model-top replacement from the marginal audit.",
            selection_rule="current_model_top",
        ),
        HistoricalShortOddsShadowRerankProfile(
            profile_id="max_short_odds_within_deficit_v1",
            description=(
                "Shadow-only profile that selects the highest short price inside "
                "the allowed small/medium expected hit-probability deficit."
            ),
            selection_rule="max_short_odds_within_deficit",
        ),
        HistoricalShortOddsShadowRerankProfile(
            profile_id="max_model_edge_within_deficit_v1",
            description=(
                "Shadow-only profile that prioritizes model edge within the same "
                "short-price and small/medium-deficit corridor."
            ),
            selection_rule="max_model_edge_within_deficit",
        ),
        HistoricalShortOddsShadowRerankProfile(
            profile_id="nearest_probability_within_deficit_v1",
            description=(
                "Shadow-only control profile that stays closest to the model-top "
                "expected hit probability inside the short-price corridor."
            ),
            selection_rule="nearest_model_top_probability",
        ),
        HistoricalShortOddsShadowRerankProfile(
            profile_id="probability_preserving_model_edge_v1",
            description=(
                "Shadow-only profile that first preserves the model-top expected "
                "hit-probability bucket, then chooses better model edge and price."
            ),
            selection_rule="probability_preserving_model_edge",
        ),
        HistoricalShortOddsShadowRerankProfile(
            profile_id="probability_preserving_quality_score_v1",
            description=(
                "Shadow-only profile that first preserves the model-top expected "
                "hit-probability bucket, then chooses the strongest pre-match "
                "quality score, candidate score, edge, and price."
            ),
            selection_rule="probability_preserving_quality_score",
        ),
    )


def build_historical_short_odds_shadow_rerank_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalShortOddsShadowRerankOptions | None = None,
) -> HistoricalShortOddsShadowRerankReport:
    resolved_options = options or HistoricalShortOddsShadowRerankOptions()
    warnings = list(audit_report.warnings)
    eligible_items = [
        item
        for item in audit_report.items
        if _is_eligible_item(item, options=resolved_options)
    ]
    if not eligible_items:
        warnings.append("no_short_odds_shadow_rerank_items")

    items: list[HistoricalShortOddsShadowRerankItem] = []
    for profile in resolved_options.profiles:
        for audit_item in eligible_items:
            items.append(
                _shadow_item_for_profile(
                    audit_item,
                    profile=profile,
                    options=resolved_options,
                )
            )

    profile_summaries = [
        _profile_summary(
            profile,
            [item for item in items if item.profile_id == profile.profile_id],
            options=resolved_options,
        )
        for profile in resolved_options.profiles
    ]
    report_items = sorted(
        items,
        key=lambda item: (
            item.profit_loss_delta_vs_model_top,
            item.selected_actual_best,
            -abs(item.hit_probability_delta_vs_model_top),
            item.item_key,
        ),
        reverse=True,
    )[: resolved_options.max_report_items]
    top_improvement_items = _top_improvement_items(items)
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_shadow_rerank_v3_1",
        "source_audit_report_key": audit_report.report_key,
        "source_item_count": len(audit_report.items),
        "eligible_item_count": len(eligible_items),
        "profile_count": len(resolved_options.profiles),
        "focus_competition_ids": list(resolved_options.focus_competition_ids),
        "pre_match_feature_names": list(PREMATCH_SHORT_ODDS_SHADOW_FEATURES),
        "offline_evaluation_fields": list(
            OFFLINE_SHORT_ODDS_SHADOW_EVALUATION_FIELDS
        ),
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, profile_summaries, report_items)
    return HistoricalShortOddsShadowRerankReport(
        report_key=report_key,
        status="generated",
        source_audit_report_key=audit_report.report_key,
        eligible_item_count=len(eligible_items),
        profile_count=len(resolved_options.profiles),
        shadow_candidate_count=sum(
            1 for summary in profile_summaries if summary.status == "shadow_candidate"
        ),
        shadow_watchlist_count=sum(
            1 for summary in profile_summaries if summary.status == "shadow_watchlist"
        ),
        rejected_count=sum(
            1 for summary in profile_summaries if summary.status == "rejected"
        ),
        pre_match_feature_names=list(PREMATCH_SHORT_ODDS_SHADOW_FEATURES),
        offline_evaluation_fields=list(
            OFFLINE_SHORT_ODDS_SHADOW_EVALUATION_FIELDS
        ),
        production_recommendation_changed=False,
        profile_summaries=profile_summaries,
        items=report_items,
        top_improvement_items=top_improvement_items,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    audit_report = load_historical_candidate_marginal_audit_report(args.audit_report)
    report = build_historical_short_odds_shadow_rerank_report(
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
    options: HistoricalShortOddsShadowRerankOptions,
) -> bool:
    model_top = audit_item.model_top_replacement
    actual_best = audit_item.actual_best_replacement
    if model_top is None or actual_best is None:
        return False
    if not audit_item.replacement_candidates:
        return False
    if options.focus_competition_ids and (
        audit_item.competition_id not in options.focus_competition_ids
    ):
        return False
    if actual_best.profit_loss_delta <= options.min_actual_best_profit_loss_delta:
        return False
    return (
        actual_best.profit_loss_delta - model_top.profit_loss_delta
        > options.min_profit_loss_gap
    )


def _shadow_item_for_profile(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    profile: HistoricalShortOddsShadowRerankProfile,
    options: HistoricalShortOddsShadowRerankOptions,
) -> HistoricalShortOddsShadowRerankItem:
    model_top = audit_item.model_top_replacement
    actual_best = audit_item.actual_best_replacement
    if model_top is None or actual_best is None:
        raise ValueError("shadow rerank item requires model_top and actual_best")
    qualified_candidates = _qualified_candidates(audit_item, options=options)
    shadow_replacement = _select_shadow_replacement(
        model_top,
        qualified_candidates,
        profile=profile,
    )
    selected_model_top = _same_replacement(shadow_replacement, model_top)
    selected_actual_best = _same_replacement(shadow_replacement, actual_best)
    profit_loss_delta_vs_model_top = (
        shadow_replacement.profit_loss_delta - model_top.profit_loss_delta
    )
    hit_probability_delta = _hit_probability_delta(shadow_replacement, model_top)
    return HistoricalShortOddsShadowRerankItem(
        profile_id=profile.profile_id,
        selection_rule=profile.selection_rule,
        item_key=audit_item.item_key,
        competition_id=audit_item.competition_id,
        slice_id=audit_item.slice_id,
        removed_fixture_id=audit_item.selected_fixture_id,
        removed_outcome=audit_item.selected_outcome,
        shadow_replacement_fixture_id=shadow_replacement.replacement_fixture_id,
        shadow_replacement_outcome=shadow_replacement.replacement_outcome,
        shadow_replacement_rank=shadow_replacement.replacement_rank,
        model_top_replacement_fixture_id=model_top.replacement_fixture_id,
        model_top_replacement_outcome=model_top.replacement_outcome,
        model_top_replacement_rank=model_top.replacement_rank,
        actual_best_replacement_fixture_id=actual_best.replacement_fixture_id,
        actual_best_replacement_outcome=actual_best.replacement_outcome,
        actual_best_replacement_rank=actual_best.replacement_rank,
        qualified_candidate_count=len(qualified_candidates),
        selected_model_top=selected_model_top,
        selected_actual_best=selected_actual_best,
        simulated_actual_hit=shadow_replacement.simulated_actual_hit,
        model_top_simulated_actual_hit=model_top.simulated_actual_hit,
        replacement_leg_actual_hit=shadow_replacement.replacement_leg_actual_hit,
        model_top_replacement_leg_actual_hit=model_top.replacement_leg_actual_hit,
        profit_loss_delta_vs_model_top=profit_loss_delta_vs_model_top,
        hit_probability_delta_vs_model_top=hit_probability_delta,
        roi_delta_vs_model_top=shadow_replacement.simulated_roi - model_top.simulated_roi,
        risk_score_delta_vs_model_top=(
            shadow_replacement.simulated_risk_score - model_top.simulated_risk_score
        ),
        probability_delta_vs_model_top=(
            shadow_replacement.replacement_probability
            - model_top.replacement_probability
        ),
        decimal_odds_delta_vs_model_top=_decimal_odds_delta(
            shadow_replacement,
            model_top,
        ),
        model_edge_delta_vs_model_top=(
            shadow_replacement.replacement_model_edge - model_top.replacement_model_edge
        ),
        score_delta_vs_model_top=(
            shadow_replacement.replacement_score - model_top.replacement_score
        ),
        quality_score_delta_vs_model_top=(
            shadow_replacement.replacement_quality_score
            - model_top.replacement_quality_score
        ),
        expected_hit_probability_regressed=hit_probability_delta < 0,
        reason_codes=_reason_codes(
            shadow_replacement,
            model_top=model_top,
            actual_best=actual_best,
            qualified_candidate_count=len(qualified_candidates),
            profit_loss_delta_vs_model_top=profit_loss_delta_vs_model_top,
            hit_probability_delta_vs_model_top=hit_probability_delta,
        ),
        summary_json={
            "used_feature_names": _used_feature_names(profile),
            "offline_evaluation_fields": list(
                OFFLINE_SHORT_ODDS_SHADOW_EVALUATION_FIELDS
            ),
            "selected_probability": audit_item.selected_probability,
            "selected_decimal_odds": audit_item.selected_decimal_odds,
            "selected_model_edge": audit_item.selected_model_edge,
            "model_top_profit_loss_delta": model_top.profit_loss_delta,
            "actual_best_profit_loss_delta": actual_best.profit_loss_delta,
        },
    )


def _qualified_candidates(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    options: HistoricalShortOddsShadowRerankOptions,
) -> list[HistoricalCandidateReplacementSimulation]:
    model_top = audit_item.model_top_replacement
    if model_top is None:
        return []
    return [
        replacement
        for replacement in audit_item.replacement_candidates
        if not _same_replacement(replacement, model_top)
        and _passes_shadow_guards(replacement, model_top=model_top, options=options)
    ]


def _passes_shadow_guards(
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    model_top: HistoricalCandidateReplacementSimulation,
    options: HistoricalShortOddsShadowRerankOptions,
) -> bool:
    if replacement.replacement_decimal_odds is None:
        return False
    if model_top.replacement_decimal_odds is None:
        return False
    if replacement.replacement_probability < options.min_replacement_probability:
        return False
    if (
        options.min_replacement_decimal_odds is not None
        and replacement.replacement_decimal_odds < options.min_replacement_decimal_odds
    ):
        return False
    if replacement.replacement_decimal_odds >= options.max_replacement_decimal_odds:
        return False
    hit_probability_delta = _hit_probability_delta(replacement, model_top)
    if (
        hit_probability_delta
        < options.min_candidate_hit_probability_delta_vs_model_top
    ):
        return False
    if (
        hit_probability_delta
        > options.max_candidate_hit_probability_delta_vs_model_top
    ):
        return False
    decimal_odds_delta = replacement.replacement_decimal_odds - (
        model_top.replacement_decimal_odds
    )
    return decimal_odds_delta >= options.min_decimal_odds_delta_vs_model_top


def _select_shadow_replacement(
    model_top: HistoricalCandidateReplacementSimulation,
    qualified_candidates: Sequence[HistoricalCandidateReplacementSimulation],
    *,
    profile: HistoricalShortOddsShadowRerankProfile,
) -> HistoricalCandidateReplacementSimulation:
    if profile.selection_rule == "current_model_top":
        return model_top
    if not qualified_candidates:
        return model_top
    if profile.selection_rule == "max_short_odds_within_deficit":
        return max(
            qualified_candidates,
            key=lambda replacement: (
                replacement.replacement_decimal_odds or 0.0,
                -_hit_probability_delta(replacement, model_top),
                replacement.replacement_model_edge,
                replacement.replacement_quality_score,
                -replacement.replacement_rank,
            ),
        )
    if profile.selection_rule == "max_model_edge_within_deficit":
        return max(
            qualified_candidates,
            key=lambda replacement: (
                replacement.replacement_model_edge,
                replacement.replacement_decimal_odds or 0.0,
                replacement.replacement_quality_score,
                replacement.simulated_hit_probability,
                -replacement.replacement_rank,
            ),
        )
    if profile.selection_rule == "probability_preserving_model_edge":
        return max(
            qualified_candidates,
            key=lambda replacement: (
                _hit_probability_delta_bucket(
                    _hit_probability_delta(replacement, model_top)
                ),
                replacement.replacement_model_edge,
                replacement.replacement_decimal_odds or 0.0,
                replacement.replacement_quality_score,
                -replacement.replacement_rank,
            ),
        )
    if profile.selection_rule == "probability_preserving_quality_score":
        return max(
            qualified_candidates,
            key=lambda replacement: (
                _hit_probability_delta_bucket(
                    _hit_probability_delta(replacement, model_top)
                ),
                replacement.replacement_quality_score,
                replacement.replacement_score,
                replacement.replacement_model_edge,
                replacement.replacement_decimal_odds or 0.0,
                -replacement.replacement_rank,
            ),
        )
    return max(
        qualified_candidates,
        key=lambda replacement: (
            _hit_probability_delta(replacement, model_top),
            replacement.replacement_decimal_odds or 0.0,
            replacement.replacement_model_edge,
            replacement.replacement_quality_score,
            -replacement.replacement_rank,
        ),
    )


def _profile_summary(
    profile: HistoricalShortOddsShadowRerankProfile,
    items: Sequence[HistoricalShortOddsShadowRerankItem],
    *,
    options: HistoricalShortOddsShadowRerankOptions,
) -> HistoricalShortOddsShadowProfileSummary:
    evaluated_count = len(items)
    changed_count = sum(1 for item in items if not item.selected_model_top)
    selected_actual_best_count = sum(1 for item in items if item.selected_actual_best)
    simulated_actual_hit_count = sum(1 for item in items if item.simulated_actual_hit)
    model_top_simulated_actual_hit_count = sum(
        1 for item in items if item.model_top_simulated_actual_hit
    )
    replacement_leg_hit_count = sum(
        1 for item in items if item.replacement_leg_actual_hit
    )
    model_top_replacement_leg_hit_count = sum(
        1 for item in items if item.model_top_replacement_leg_actual_hit
    )
    simulated_actual_hit_delta = (
        simulated_actual_hit_count - model_top_simulated_actual_hit_count
    )
    replacement_leg_hit_delta = (
        replacement_leg_hit_count - model_top_replacement_leg_hit_count
    )
    harm_count = sum(
        1 for item in items if item.profit_loss_delta_vs_model_top < 0
    )
    improvement_count = sum(
        1 for item in items if item.profit_loss_delta_vs_model_top > 0
    )
    expected_regression_count = sum(
        1 for item in items if item.expected_hit_probability_regressed
    )
    average_profit_delta = _average(
        item.profit_loss_delta_vs_model_top for item in items
    )
    status, status_reasons = _profile_status(
        profile,
        evaluated_count=evaluated_count,
        simulated_actual_hit_delta=simulated_actual_hit_delta,
        replacement_leg_hit_delta=replacement_leg_hit_delta,
        harm_count=harm_count,
        expected_regression_count=expected_regression_count,
        average_profit_delta=average_profit_delta,
        options=options,
    )
    return HistoricalShortOddsShadowProfileSummary(
        profile_id=profile.profile_id,
        description=profile.description,
        selection_rule=profile.selection_rule,
        status=status,
        status_reasons=status_reasons,
        used_feature_names=_used_feature_names(profile),
        evaluated_item_count=evaluated_count,
        changed_count_vs_model_top=changed_count,
        selected_model_top_count=sum(1 for item in items if item.selected_model_top),
        selected_actual_best_count=selected_actual_best_count,
        qualified_candidate_count=sum(
            item.qualified_candidate_count for item in items
        ),
        improvement_count_vs_model_top=improvement_count,
        harm_count_vs_model_top=harm_count,
        simulated_actual_hit_count=simulated_actual_hit_count,
        model_top_simulated_actual_hit_count=model_top_simulated_actual_hit_count,
        simulated_actual_hit_delta_count_vs_model_top=simulated_actual_hit_delta,
        replacement_leg_hit_count=replacement_leg_hit_count,
        model_top_replacement_leg_hit_count=model_top_replacement_leg_hit_count,
        replacement_leg_hit_delta_count_vs_model_top=replacement_leg_hit_delta,
        expected_hit_probability_regression_count=expected_regression_count,
        changed_rate_vs_model_top=_ratio(changed_count, evaluated_count),
        selected_actual_best_rate=_ratio(selected_actual_best_count, evaluated_count),
        simulated_actual_hit_rate=_ratio(simulated_actual_hit_count, evaluated_count),
        model_top_simulated_actual_hit_rate=_ratio(
            model_top_simulated_actual_hit_count,
            evaluated_count,
        ),
        replacement_leg_hit_rate=_ratio(replacement_leg_hit_count, evaluated_count),
        model_top_replacement_leg_hit_rate=_ratio(
            model_top_replacement_leg_hit_count,
            evaluated_count,
        ),
        average_qualified_candidate_count=_average(
            item.qualified_candidate_count for item in items
        ),
        average_profit_loss_delta_vs_model_top=average_profit_delta,
        average_hit_probability_delta_vs_model_top=_average(
            item.hit_probability_delta_vs_model_top for item in items
        ),
        average_roi_delta_vs_model_top=_average(
            item.roi_delta_vs_model_top for item in items
        ),
        average_risk_score_delta_vs_model_top=_average(
            item.risk_score_delta_vs_model_top for item in items
        ),
        average_decimal_odds_delta_vs_model_top=_average(
            item.decimal_odds_delta_vs_model_top for item in items
        ),
        competition_summaries=_competition_summaries(items),
    )


def _competition_summaries(
    items: Sequence[HistoricalShortOddsShadowRerankItem],
) -> list[HistoricalShortOddsShadowCompetitionSummary]:
    by_competition: dict[str, list[HistoricalShortOddsShadowRerankItem]] = {}
    for item in items:
        by_competition.setdefault(item.competition_id, []).append(item)
    summaries: list[HistoricalShortOddsShadowCompetitionSummary] = []
    for competition_id, competition_items in by_competition.items():
        simulated_hit_delta = sum(
            int(item.simulated_actual_hit)
            - int(item.model_top_simulated_actual_hit)
            for item in competition_items
        )
        replacement_leg_hit_delta = sum(
            int(item.replacement_leg_actual_hit)
            - int(item.model_top_replacement_leg_actual_hit)
            for item in competition_items
        )
        summaries.append(
            HistoricalShortOddsShadowCompetitionSummary(
                competition_id=competition_id,
                evaluated_item_count=len(competition_items),
                changed_count_vs_model_top=sum(
                    1 for item in competition_items if not item.selected_model_top
                ),
                simulated_actual_hit_delta_count_vs_model_top=simulated_hit_delta,
                replacement_leg_hit_delta_count_vs_model_top=replacement_leg_hit_delta,
                improvement_count_vs_model_top=sum(
                    1
                    for item in competition_items
                    if item.profit_loss_delta_vs_model_top > 0
                ),
                harm_count_vs_model_top=sum(
                    1
                    for item in competition_items
                    if item.profit_loss_delta_vs_model_top < 0
                ),
                selected_actual_best_count=sum(
                    1 for item in competition_items if item.selected_actual_best
                ),
                average_profit_loss_delta_vs_model_top=_average(
                    item.profit_loss_delta_vs_model_top
                    for item in competition_items
                ),
                average_hit_probability_delta_vs_model_top=_average(
                    item.hit_probability_delta_vs_model_top
                    for item in competition_items
                ),
                average_decimal_odds_delta_vs_model_top=_average(
                    item.decimal_odds_delta_vs_model_top
                    for item in competition_items
                ),
            )
        )
    return sorted(
        summaries,
        key=lambda summary: (
            summary.simulated_actual_hit_delta_count_vs_model_top,
            summary.average_profit_loss_delta_vs_model_top or 0.0,
            summary.evaluated_item_count,
            summary.competition_id,
        ),
        reverse=True,
    )


def _profile_status(
    profile: HistoricalShortOddsShadowRerankProfile,
    *,
    evaluated_count: int,
    simulated_actual_hit_delta: int,
    replacement_leg_hit_delta: int,
    harm_count: int,
    expected_regression_count: int,
    average_profit_delta: float | None,
    options: HistoricalShortOddsShadowRerankOptions,
) -> tuple[HistoricalShortOddsShadowProfileStatus, list[str]]:
    if profile.selection_rule == "current_model_top":
        return "baseline", ["current_model_top_reference"]
    reasons: list[str] = []
    if evaluated_count < options.min_evaluated_item_count:
        reasons.append("sample_size_below_threshold")
    if (
        simulated_actual_hit_delta
        < options.min_simulated_actual_hit_delta_count_vs_model_top
    ):
        reasons.append("simulated_actual_hit_delta_below_threshold")
    if (
        replacement_leg_hit_delta
        < options.min_replacement_leg_hit_delta_count_vs_model_top
    ):
        reasons.append("replacement_leg_hit_delta_below_threshold")
    if (
        average_profit_delta is None
        or average_profit_delta
        <= options.min_average_profit_loss_delta_vs_model_top
    ):
        reasons.append("average_profit_loss_delta_vs_model_top_below_threshold")
    if harm_count > options.max_harm_count_vs_model_top:
        reasons.append("harm_count_vs_model_top_above_threshold")
    if expected_regression_count > 0:
        reasons.append("contains_expected_hit_probability_regression")
    if not reasons:
        return "shadow_candidate", []
    positive_shadow = (
        average_profit_delta is not None
        and average_profit_delta > 0
        and simulated_actual_hit_delta >= 0
        and replacement_leg_hit_delta >= 0
    )
    if positive_shadow:
        return "shadow_watchlist", reasons
    return "rejected", reasons


def _reason_codes(
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    model_top: HistoricalCandidateReplacementSimulation,
    actual_best: HistoricalCandidateReplacementSimulation,
    qualified_candidate_count: int,
    profit_loss_delta_vs_model_top: float,
    hit_probability_delta_vs_model_top: float,
) -> list[str]:
    reasons: list[str] = []
    if qualified_candidate_count == 0:
        reasons.append("no_qualified_short_odds_shadow_candidate")
    if _same_replacement(replacement, model_top):
        reasons.append("kept_model_top")
    else:
        reasons.append("shadow_reranked_away_from_model_top")
    if _same_replacement(replacement, actual_best):
        reasons.append("captured_actual_best_for_evaluation")
    if profit_loss_delta_vs_model_top > 0:
        reasons.append("improved_profit_loss_vs_model_top")
    if profit_loss_delta_vs_model_top < 0:
        reasons.append("harmed_profit_loss_vs_model_top")
    if hit_probability_delta_vs_model_top < 0:
        reasons.append("lower_expected_hit_probability_than_model_top")
    if (
        replacement.replacement_decimal_odds is not None
        and model_top.replacement_decimal_odds is not None
        and replacement.replacement_decimal_odds > model_top.replacement_decimal_odds
    ):
        reasons.append("higher_short_odds_than_model_top")
    return reasons


def _used_feature_names(
    profile: HistoricalShortOddsShadowRerankProfile,
) -> list[str]:
    if profile.selection_rule == "current_model_top":
        return ["current_model_top_reference"]
    feature_names = list(PREMATCH_SHORT_ODDS_SHADOW_FEATURES)
    feature_names.extend(
        [
            "focus_competition_ids_guard",
            "min_replacement_probability_guard",
            "min_replacement_decimal_odds_guard",
            "max_replacement_decimal_odds_guard",
            "candidate_hit_probability_delta_vs_model_top_guard",
            "decimal_odds_delta_vs_model_top_guard",
            profile.selection_rule,
        ]
    )
    return feature_names


def _hit_probability_delta_bucket(
    hit_probability_delta_vs_model_top: float,
    *,
    bucket_width: float = 0.02,
) -> int:
    return floor(hit_probability_delta_vs_model_top / bucket_width)


def _top_improvement_items(
    items: Sequence[HistoricalShortOddsShadowRerankItem],
) -> list[HistoricalShortOddsShadowRerankItem]:
    return sorted(
        items,
        key=lambda item: (
            item.profit_loss_delta_vs_model_top,
            item.selected_actual_best,
            item.simulated_actual_hit,
            item.item_key,
        ),
        reverse=True,
    )[:20]


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run shadow-only short-odds replacement rerank experiments."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--profile-ids",
        type=str,
        default="",
        help="Comma-separated default profile ids to evaluate; empty means all.",
    )
    parser.add_argument(
        "--focus-competitions",
        type=str,
        default=",".join(DEFAULT_SHORT_ODDS_SHADOW_COMPETITIONS),
    )
    parser.add_argument("--min-actual-best-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-gap", type=float, default=0.0)
    parser.add_argument("--min-replacement-probability", type=float, default=0.55)
    parser.add_argument("--min-replacement-decimal-odds", type=float, default=None)
    parser.add_argument("--max-replacement-decimal-odds", type=float, default=1.75)
    parser.add_argument(
        "--min-candidate-hit-probability-delta-vs-model-top",
        type=float,
        default=-0.015,
    )
    parser.add_argument(
        "--max-candidate-hit-probability-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-decimal-odds-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-evaluated-item-count", type=int, default=30)
    parser.add_argument(
        "--min-simulated-actual-hit-delta-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-replacement-leg-hit-delta-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-average-profit-loss-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument("--max-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-report-items", type=int, default=80)
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalShortOddsShadowRerankOptions:
    return HistoricalShortOddsShadowRerankOptions(
        profiles=_selected_profiles(args.profile_ids),
        focus_competition_ids=_csv_values(args.focus_competitions),
        min_actual_best_profit_loss_delta=args.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=args.min_profit_loss_gap,
        min_replacement_probability=args.min_replacement_probability,
        min_replacement_decimal_odds=args.min_replacement_decimal_odds,
        max_replacement_decimal_odds=args.max_replacement_decimal_odds,
        min_candidate_hit_probability_delta_vs_model_top=(
            args.min_candidate_hit_probability_delta_vs_model_top
        ),
        max_candidate_hit_probability_delta_vs_model_top=(
            args.max_candidate_hit_probability_delta_vs_model_top
        ),
        min_decimal_odds_delta_vs_model_top=(
            args.min_decimal_odds_delta_vs_model_top
        ),
        min_evaluated_item_count=args.min_evaluated_item_count,
        min_simulated_actual_hit_delta_count_vs_model_top=(
            args.min_simulated_actual_hit_delta_count_vs_model_top
        ),
        min_replacement_leg_hit_delta_count_vs_model_top=(
            args.min_replacement_leg_hit_delta_count_vs_model_top
        ),
        min_average_profit_loss_delta_vs_model_top=(
            args.min_average_profit_loss_delta_vs_model_top
        ),
        max_harm_count_vs_model_top=args.max_harm_count_vs_model_top,
        max_report_items=args.max_report_items,
    )


def _selected_profiles(
    profile_ids: str,
) -> tuple[HistoricalShortOddsShadowRerankProfile, ...]:
    profiles = default_historical_short_odds_shadow_profiles()
    if not profile_ids:
        return profiles
    requested = {profile_id.strip() for profile_id in profile_ids.split(",")}
    requested.discard("")
    selected = tuple(profile for profile in profiles if profile.profile_id in requested)
    missing = requested - {profile.profile_id for profile in selected}
    if missing:
        raise SystemExit(f"Unknown short-odds shadow profile ids: {sorted(missing)}")
    return selected


def _csv_values(value: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in value.split(",") if item.strip())
    return values


def _same_replacement(
    left: HistoricalCandidateReplacementSimulation,
    right: HistoricalCandidateReplacementSimulation,
) -> bool:
    return (
        left.replacement_fixture_id == right.replacement_fixture_id
        and left.replacement_market_type == right.replacement_market_type
        and left.replacement_outcome == right.replacement_outcome
    )


def _hit_probability_delta(
    left: HistoricalCandidateReplacementSimulation,
    right: HistoricalCandidateReplacementSimulation,
) -> float:
    return left.simulated_hit_probability - right.simulated_hit_probability


def _decimal_odds_delta(
    left: HistoricalCandidateReplacementSimulation,
    right: HistoricalCandidateReplacementSimulation,
) -> float | None:
    if left.replacement_decimal_odds is None or right.replacement_decimal_odds is None:
        return None
    return left.replacement_decimal_odds - right.replacement_decimal_odds


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _report_key(
    summary: dict[str, object],
    profile_summaries: Sequence[HistoricalShortOddsShadowProfileSummary],
    items: Sequence[HistoricalShortOddsShadowRerankItem],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "profile_summaries": [
                profile_summary.model_dump(mode="json")
                for profile_summary in profile_summaries
            ],
            "items": [
                {
                    "profile_id": item.profile_id,
                    "item_key": item.item_key,
                    "shadow_replacement_fixture_id": (
                        item.shadow_replacement_fixture_id
                    ),
                    "shadow_replacement_outcome": item.shadow_replacement_outcome,
                }
                for item in items
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_short_odds_shadow_rerank:{digest}"
