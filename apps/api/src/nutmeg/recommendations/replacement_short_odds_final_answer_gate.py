from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
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
from nutmeg.recommendations.replacement_short_odds_competition_gate import (
    HistoricalShortOddsCompetitionGateReport,
)
from nutmeg.recommendations.replacement_short_odds_shadow_rerank import (
    HistoricalShortOddsShadowRerankItem,
    HistoricalShortOddsShadowRerankOptions,
    HistoricalShortOddsShadowRerankProfile,
    HistoricalShortOddsShadowRerankReport,
    HistoricalShortOddsShadowSelectionRule,
    build_historical_short_odds_shadow_rerank_report,
)

type HistoricalShortOddsFinalAnswerSelectionRule = Literal[
    "highest_candidate_hit_probability",
    "highest_decimal_odds_delta",
]

type HistoricalShortOddsFinalAnswerGateDecision = Literal[
    "final_answer_shadow_candidate",
    "shadow_watchlist",
    "rejected",
]


class HistoricalShortOddsFinalAnswerGateOptions(BaseModel):
    profile_id: str = "max_short_odds_within_deficit_v1"
    ready_competition_ids: tuple[str, ...] = ()
    selection_rule: HistoricalShortOddsFinalAnswerSelectionRule = (
        "highest_candidate_hit_probability"
    )
    shadow_selection_rule: HistoricalShortOddsShadowSelectionRule = (
        "max_short_odds_within_deficit"
    )
    max_replacements_per_final_answer: int = Field(default=1, ge=1, le=1)
    min_changed_final_answer_count: int = Field(default=5, ge=1)
    min_final_answer_hit_delta_count_vs_original: int = 0
    min_profit_loss_delta_vs_original: float = 0.0
    min_average_hit_probability_delta_vs_original: float = -0.02
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    min_item_hit_probability_delta_vs_original: float | None = None
    exclude_original_hit_harm: bool = False
    min_replacement_probability: float = Field(default=0.55, ge=0.0, le=1.0)
    min_replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_replacement_decimal_odds: float = Field(default=1.75, gt=1.0)
    min_candidate_hit_probability_delta_vs_model_top: float = -0.015
    max_candidate_hit_probability_delta_vs_model_top: float = 0.0
    min_decimal_odds_delta_vs_model_top: float = 0.0
    max_report_items: int = Field(default=80, ge=1, le=500)


class HistoricalShortOddsFinalAnswerGateItem(BaseModel):
    final_answer_key: str
    profile_id: str
    selection_rule: HistoricalShortOddsFinalAnswerSelectionRule
    item_key: str
    slice_id: str
    competition_id: str
    final_answer_scenario_key: str
    pass_type: str
    mode: str
    removed_fixture_id: str
    removed_outcome: str
    replacement_fixture_id: str
    replacement_outcome: str
    replacement_rank: int = Field(ge=1)
    original_actual_hit: bool
    shadow_actual_hit: bool
    final_answer_hit_delta_vs_original: int
    original_profit_loss: float
    shadow_profit_loss: float
    profit_loss_delta_vs_original: float
    original_hit_probability: float = Field(ge=0.0, le=1.0)
    shadow_hit_probability: float = Field(ge=0.0, le=1.0)
    hit_probability_delta_vs_original: float
    replacement_hit_probability_delta_vs_model_top: float
    decimal_odds_delta_vs_model_top: float | None = None
    model_edge_delta_vs_model_top: float
    quality_score_delta_vs_model_top: float
    expected_hit_probability_regressed_vs_original: bool
    harmed_profit_loss_vs_original: bool
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalShortOddsFinalAnswerGateReport(BaseModel):
    report_key: str
    status: str
    decision: HistoricalShortOddsFinalAnswerGateDecision
    decision_reasons: list[str] = Field(default_factory=list)
    source_audit_report_key: str
    source_competition_gate_report_key: str
    generated_shadow_report_key: str
    profile_id: str
    ready_competition_ids: list[str] = Field(default_factory=list)
    isolated_competition_ids: list[str] = Field(default_factory=list)
    candidate_replacement_option_count: int = Field(default=0, ge=0)
    original_safe_replacement_option_count: int = Field(default=0, ge=0)
    original_safe_excluded_count: int = Field(default=0, ge=0)
    original_safe_exclusion_counts_json: dict[str, int] = Field(default_factory=dict)
    changed_final_answer_count: int = Field(ge=0)
    original_final_answer_hit_count: int = Field(ge=0)
    shadow_final_answer_hit_count: int = Field(ge=0)
    final_answer_hit_delta_count_vs_original: int
    original_profit_loss: float
    shadow_profit_loss: float
    profit_loss_delta_vs_original: float
    improvement_count_vs_original: int = Field(ge=0)
    harm_count_vs_original: int = Field(ge=0)
    expected_hit_probability_regression_count_vs_original: int = Field(ge=0)
    average_profit_loss_delta_vs_original: float | None = None
    average_hit_probability_delta_vs_original: float | None = None
    production_recommendation_changed: bool = False
    items: list[HistoricalShortOddsFinalAnswerGateItem] = Field(default_factory=list)
    top_improvement_items: list[HistoricalShortOddsFinalAnswerGateItem] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_short_odds_final_answer_gate_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    *,
    options: HistoricalShortOddsFinalAnswerGateOptions | None = None,
) -> HistoricalShortOddsFinalAnswerGateReport:
    resolved_options = options or HistoricalShortOddsFinalAnswerGateOptions()
    ready_competition_ids = _ready_competition_ids(
        competition_gate_report,
        options=resolved_options,
    )
    warnings = list(audit_report.warnings) + list(competition_gate_report.warnings)
    if not ready_competition_ids:
        warnings.append("short_odds_final_answer_gate:no_ready_competitions")

    shadow_report = _build_shadow_report(
        audit_report,
        ready_competition_ids=ready_competition_ids,
        options=resolved_options,
    )
    audit_items_by_key = {item.item_key: item for item in audit_report.items}
    replacement_options = [
        replacement_option
        for replacement_option in (
            _replacement_option_from_shadow_item(
                shadow_item,
                audit_items_by_key=audit_items_by_key,
            )
            for shadow_item in shadow_report.items
            if shadow_item.profile_id == resolved_options.profile_id
            and not shadow_item.selected_model_top
        )
        if replacement_option is not None
    ]
    original_safe_options, original_safe_exclusion_counts = (
        _original_safe_replacement_options(
            replacement_options,
            options=resolved_options,
        )
    )
    if replacement_options and not original_safe_options:
        warnings.append("short_odds_final_answer_gate:no_original_safe_options")
    if original_safe_exclusion_counts:
        warnings.append("short_odds_final_answer_gate:original_safe_subset_applied")
    selected_items = _selected_final_answer_items(
        original_safe_options,
        selection_rule=resolved_options.selection_rule,
    )
    if not selected_items:
        warnings.append("short_odds_final_answer_gate:no_changed_final_answers")

    decision, decision_reasons = _decision_for_report(
        selected_items,
        options=resolved_options,
    )
    report_items = sorted(
        selected_items,
        key=lambda item: (
            item.profit_loss_delta_vs_original,
            item.final_answer_hit_delta_vs_original,
            -abs(item.hit_probability_delta_vs_original),
            item.final_answer_key,
        ),
        reverse=True,
    )[: resolved_options.max_report_items]
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_final_answer_gate_v3_1",
        "source_audit_report_key": audit_report.report_key,
        "source_competition_gate_report_key": competition_gate_report.report_key,
        "generated_shadow_report_key": shadow_report.report_key,
        "profile_id": resolved_options.profile_id,
        "ready_competition_ids": ready_competition_ids,
        "isolated_competition_ids": competition_gate_report.isolated_competition_ids,
        "selection_rule": resolved_options.selection_rule,
        "candidate_replacement_option_count": len(replacement_options),
        "original_safe_replacement_option_count": len(original_safe_options),
        "original_safe_exclusion_counts": original_safe_exclusion_counts,
        "max_replacements_per_final_answer": (
            resolved_options.max_replacements_per_final_answer
        ),
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, report_items)
    return HistoricalShortOddsFinalAnswerGateReport(
        report_key=report_key,
        status="generated",
        decision=decision,
        decision_reasons=decision_reasons,
        source_audit_report_key=audit_report.report_key,
        source_competition_gate_report_key=competition_gate_report.report_key,
        generated_shadow_report_key=shadow_report.report_key,
        profile_id=resolved_options.profile_id,
        ready_competition_ids=list(ready_competition_ids),
        isolated_competition_ids=competition_gate_report.isolated_competition_ids,
        candidate_replacement_option_count=len(replacement_options),
        original_safe_replacement_option_count=len(original_safe_options),
        original_safe_excluded_count=(
            len(replacement_options) - len(original_safe_options)
        ),
        original_safe_exclusion_counts_json=original_safe_exclusion_counts,
        changed_final_answer_count=len(selected_items),
        original_final_answer_hit_count=sum(
            1 for item in selected_items if item.original_actual_hit
        ),
        shadow_final_answer_hit_count=sum(
            1 for item in selected_items if item.shadow_actual_hit
        ),
        final_answer_hit_delta_count_vs_original=sum(
            item.final_answer_hit_delta_vs_original for item in selected_items
        ),
        original_profit_loss=sum(item.original_profit_loss for item in selected_items),
        shadow_profit_loss=sum(item.shadow_profit_loss for item in selected_items),
        profit_loss_delta_vs_original=sum(
            item.profit_loss_delta_vs_original for item in selected_items
        ),
        improvement_count_vs_original=sum(
            1 for item in selected_items if item.profit_loss_delta_vs_original > 0
        ),
        harm_count_vs_original=sum(
            1 for item in selected_items if item.harmed_profit_loss_vs_original
        ),
        expected_hit_probability_regression_count_vs_original=sum(
            1
            for item in selected_items
            if item.expected_hit_probability_regressed_vs_original
        ),
        average_profit_loss_delta_vs_original=_average(
            item.profit_loss_delta_vs_original for item in selected_items
        ),
        average_hit_probability_delta_vs_original=_average(
            item.hit_probability_delta_vs_original for item in selected_items
        ),
        production_recommendation_changed=False,
        items=report_items,
        top_improvement_items=_top_improvement_items(selected_items),
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_short_odds_competition_gate_report(
    path: Path,
) -> HistoricalShortOddsCompetitionGateReport:
    return HistoricalShortOddsCompetitionGateReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    audit_report = load_historical_candidate_marginal_audit_report(args.audit_report)
    competition_gate_report = load_historical_short_odds_competition_gate_report(
        args.competition_gate_report
    )
    report = build_historical_short_odds_final_answer_gate_report(
        audit_report,
        competition_gate_report,
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


def _ready_competition_ids(
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    *,
    options: HistoricalShortOddsFinalAnswerGateOptions,
) -> tuple[str, ...]:
    if options.ready_competition_ids:
        return options.ready_competition_ids
    if competition_gate_report.best_profile_set is not None:
        return tuple(competition_gate_report.best_profile_set.ready_competition_ids)
    return tuple(competition_gate_report.ready_competition_ids)


def _build_shadow_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    ready_competition_ids: Sequence[str],
    options: HistoricalShortOddsFinalAnswerGateOptions,
) -> HistoricalShortOddsShadowRerankReport:
    profile = HistoricalShortOddsShadowRerankProfile(
        profile_id=options.profile_id,
        description=(
            "Final-answer gate regenerated replacement shadow profile using "
            f"{options.shadow_selection_rule}."
        ),
        selection_rule=options.shadow_selection_rule,
    )
    return build_historical_short_odds_shadow_rerank_report(
        audit_report,
        options=HistoricalShortOddsShadowRerankOptions(
            profiles=(profile,),
            focus_competition_ids=tuple(ready_competition_ids),
            min_actual_best_profit_loss_delta=0.0,
            min_profit_loss_gap=0.0,
            min_replacement_probability=options.min_replacement_probability,
            min_replacement_decimal_odds=options.min_replacement_decimal_odds,
            max_replacement_decimal_odds=options.max_replacement_decimal_odds,
            min_candidate_hit_probability_delta_vs_model_top=(
                options.min_candidate_hit_probability_delta_vs_model_top
            ),
            max_candidate_hit_probability_delta_vs_model_top=(
                options.max_candidate_hit_probability_delta_vs_model_top
            ),
            min_decimal_odds_delta_vs_model_top=(
                options.min_decimal_odds_delta_vs_model_top
            ),
            min_evaluated_item_count=1,
            max_harm_count_vs_model_top=0,
            max_report_items=500,
        ),
    )


def _replacement_option_from_shadow_item(
    shadow_item: HistoricalShortOddsShadowRerankItem,
    *,
    audit_items_by_key: dict[str, HistoricalCandidateMarginalAuditItem],
) -> HistoricalShortOddsFinalAnswerGateItem | None:
    item_key = shadow_item.item_key
    audit_item = audit_items_by_key.get(item_key)
    if audit_item is None:
        return None
    replacement = _matching_replacement(audit_item, shadow_item=shadow_item)
    if replacement is None:
        return None
    final_answer_hit_delta = int(replacement.simulated_actual_hit) - int(
        audit_item.final_answer_actual_hit
    )
    profit_loss_delta = replacement.simulated_profit_loss - audit_item.original_profit_loss
    hit_probability_delta = (
        replacement.simulated_hit_probability - audit_item.original_hit_probability
    )
    final_answer_key = (
        f"{audit_item.slice_id}:{audit_item.final_answer_scenario_key}"
    )
    return HistoricalShortOddsFinalAnswerGateItem(
        final_answer_key=final_answer_key,
        profile_id=shadow_item.profile_id,
        selection_rule="highest_candidate_hit_probability",
        item_key=audit_item.item_key,
        slice_id=audit_item.slice_id,
        competition_id=audit_item.competition_id,
        final_answer_scenario_key=audit_item.final_answer_scenario_key,
        pass_type=audit_item.pass_type,
        mode=str(audit_item.mode),
        removed_fixture_id=audit_item.selected_fixture_id,
        removed_outcome=audit_item.selected_outcome,
        replacement_fixture_id=replacement.replacement_fixture_id,
        replacement_outcome=replacement.replacement_outcome,
        replacement_rank=replacement.replacement_rank,
        original_actual_hit=audit_item.final_answer_actual_hit,
        shadow_actual_hit=replacement.simulated_actual_hit,
        final_answer_hit_delta_vs_original=final_answer_hit_delta,
        original_profit_loss=audit_item.original_profit_loss,
        shadow_profit_loss=replacement.simulated_profit_loss,
        profit_loss_delta_vs_original=profit_loss_delta,
        original_hit_probability=audit_item.original_hit_probability,
        shadow_hit_probability=replacement.simulated_hit_probability,
        hit_probability_delta_vs_original=hit_probability_delta,
        replacement_hit_probability_delta_vs_model_top=(
            shadow_item.hit_probability_delta_vs_model_top
        ),
        decimal_odds_delta_vs_model_top=shadow_item.decimal_odds_delta_vs_model_top,
        model_edge_delta_vs_model_top=shadow_item.model_edge_delta_vs_model_top,
        quality_score_delta_vs_model_top=shadow_item.quality_score_delta_vs_model_top,
        expected_hit_probability_regressed_vs_original=hit_probability_delta < 0,
        harmed_profit_loss_vs_original=profit_loss_delta < 0,
        reason_codes=_reason_codes(
            final_answer_hit_delta=final_answer_hit_delta,
            profit_loss_delta=profit_loss_delta,
            hit_probability_delta=hit_probability_delta,
        ),
        summary_json={
            "calculation_basis": "historical_short_odds_final_answer_gate_item_v3_1",
            "source_shadow_item_key": audit_item.item_key,
            "replacement_decimal_odds": replacement.replacement_decimal_odds,
            "replacement_probability": replacement.replacement_probability,
            "replacement_model_edge": replacement.replacement_model_edge,
            "production_recommendation_changed": False,
        },
    )


def _matching_replacement(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    shadow_item: HistoricalShortOddsShadowRerankItem,
) -> HistoricalCandidateReplacementSimulation | None:
    fixture_id = shadow_item.shadow_replacement_fixture_id
    outcome = shadow_item.shadow_replacement_outcome
    for replacement in audit_item.replacement_candidates:
        if (
            replacement.replacement_fixture_id == fixture_id
            and replacement.replacement_outcome == outcome
        ):
            return replacement
    return None


def _selected_final_answer_items(
    replacement_options: Sequence[HistoricalShortOddsFinalAnswerGateItem],
    *,
    selection_rule: HistoricalShortOddsFinalAnswerSelectionRule,
) -> list[HistoricalShortOddsFinalAnswerGateItem]:
    grouped: dict[str, list[HistoricalShortOddsFinalAnswerGateItem]] = {}
    for replacement_option in replacement_options:
        grouped.setdefault(replacement_option.final_answer_key, []).append(
            replacement_option
        )
    selected: list[HistoricalShortOddsFinalAnswerGateItem] = []
    for options in grouped.values():
        item = max(options, key=lambda option: _selection_key(option, selection_rule))
        selected.append(
            item.model_copy(update={"selection_rule": selection_rule})
        )
    return selected


def _original_safe_replacement_options(
    replacement_options: Sequence[HistoricalShortOddsFinalAnswerGateItem],
    *,
    options: HistoricalShortOddsFinalAnswerGateOptions,
) -> tuple[list[HistoricalShortOddsFinalAnswerGateItem], dict[str, int]]:
    kept: list[HistoricalShortOddsFinalAnswerGateItem] = []
    exclusion_counts = {
        "item_hit_probability_delta_vs_original_below_threshold": 0,
        "original_hit_harm_excluded": 0,
    }
    for replacement_option in replacement_options:
        excluded = False
        if (
            options.min_item_hit_probability_delta_vs_original is not None
            and replacement_option.hit_probability_delta_vs_original
            < options.min_item_hit_probability_delta_vs_original
        ):
            exclusion_counts[
                "item_hit_probability_delta_vs_original_below_threshold"
            ] += 1
            excluded = True
        if (
            options.exclude_original_hit_harm
            and replacement_option.final_answer_hit_delta_vs_original < 0
        ):
            exclusion_counts["original_hit_harm_excluded"] += 1
            excluded = True
        if not excluded:
            kept.append(replacement_option)
    return (
        kept,
        {key: value for key, value in exclusion_counts.items() if value > 0},
    )


def _selection_key(
    item: HistoricalShortOddsFinalAnswerGateItem,
    selection_rule: HistoricalShortOddsFinalAnswerSelectionRule,
) -> tuple[float, float, float, float, str]:
    if selection_rule == "highest_decimal_odds_delta":
        return (
            item.decimal_odds_delta_vs_model_top or 0.0,
            item.shadow_hit_probability,
            item.model_edge_delta_vs_model_top,
            item.quality_score_delta_vs_model_top,
            item.item_key,
        )
    return (
        item.shadow_hit_probability,
        item.decimal_odds_delta_vs_model_top or 0.0,
        item.model_edge_delta_vs_model_top,
        item.quality_score_delta_vs_model_top,
        item.item_key,
    )


def _decision_for_report(
    items: Sequence[HistoricalShortOddsFinalAnswerGateItem],
    *,
    options: HistoricalShortOddsFinalAnswerGateOptions,
) -> tuple[HistoricalShortOddsFinalAnswerGateDecision, list[str]]:
    reasons: list[str] = []
    if len(items) < options.min_changed_final_answer_count:
        reasons.append("changed_final_answer_count_below_threshold")
    hit_delta = sum(item.final_answer_hit_delta_vs_original for item in items)
    if hit_delta < options.min_final_answer_hit_delta_count_vs_original:
        reasons.append("final_answer_hit_delta_below_threshold")
    profit_delta = sum(item.profit_loss_delta_vs_original for item in items)
    if profit_delta <= options.min_profit_loss_delta_vs_original:
        reasons.append("profit_loss_delta_vs_original_below_threshold")
    average_hit_probability_delta = _average(
        item.hit_probability_delta_vs_original for item in items
    )
    if (
        average_hit_probability_delta is None
        or average_hit_probability_delta
        < options.min_average_hit_probability_delta_vs_original
    ):
        reasons.append("average_hit_probability_delta_vs_original_below_threshold")
    harm_count = sum(1 for item in items if item.harmed_profit_loss_vs_original)
    if harm_count > options.max_harm_count_vs_original:
        reasons.append("harm_count_vs_original_above_threshold")
    if not reasons:
        return "final_answer_shadow_candidate", []
    if profit_delta > 0 and hit_delta >= 0:
        return "shadow_watchlist", reasons
    return "rejected", reasons


def _reason_codes(
    *,
    final_answer_hit_delta: int,
    profit_loss_delta: float,
    hit_probability_delta: float,
) -> list[str]:
    reasons: list[str] = []
    if final_answer_hit_delta > 0:
        reasons.append("improved_final_answer_actual_hit_vs_original")
    if final_answer_hit_delta < 0:
        reasons.append("regressed_final_answer_actual_hit_vs_original")
    if profit_loss_delta > 0:
        reasons.append("improved_profit_loss_vs_original")
    if profit_loss_delta < 0:
        reasons.append("harmed_profit_loss_vs_original")
    if hit_probability_delta < 0:
        reasons.append("lower_expected_hit_probability_than_original")
    return reasons


def _top_improvement_items(
    items: Sequence[HistoricalShortOddsFinalAnswerGateItem],
) -> list[HistoricalShortOddsFinalAnswerGateItem]:
    return sorted(
        items,
        key=lambda item: (
            item.profit_loss_delta_vs_original,
            item.final_answer_hit_delta_vs_original,
            item.final_answer_key,
        ),
        reverse=True,
    )[:20]


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Gate ready short-odds replacements at final-answer level."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--competition-gate-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-id", type=str, default="max_short_odds_within_deficit_v1")
    parser.add_argument(
        "--ready-competitions",
        type=str,
        default="",
        help="Comma-separated ready competition ids; empty uses competition gate report.",
    )
    parser.add_argument(
        "--selection-rule",
        choices=("highest_candidate_hit_probability", "highest_decimal_odds_delta"),
        default="highest_candidate_hit_probability",
    )
    parser.add_argument(
        "--shadow-selection-rule",
        choices=(
            "max_short_odds_within_deficit",
            "max_model_edge_within_deficit",
            "nearest_model_top_probability",
            "probability_preserving_model_edge",
            "probability_preserving_quality_score",
        ),
        default="max_short_odds_within_deficit",
    )
    parser.add_argument("--min-changed-final-answer-count", type=int, default=5)
    parser.add_argument(
        "--min-final-answer-hit-delta-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument("--min-profit-loss-delta-vs-original", type=float, default=0.0)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--min-item-hit-probability-delta-vs-original",
        type=float,
        default=None,
        help=(
            "Optional per-item expected hit-probability delta floor against the "
            "original final answer before final-answer selection."
        ),
    )
    parser.add_argument(
        "--exclude-original-hit-harm",
        action="store_true",
        help=(
            "Evaluation-only guard: drop replacements that turn a historically "
            "hit original final answer into a miss."
        ),
    )
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
    parser.add_argument("--max-report-items", type=int, default=80)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalShortOddsFinalAnswerGateOptions:
    return HistoricalShortOddsFinalAnswerGateOptions(
        profile_id=args.profile_id,
        ready_competition_ids=_csv_values(args.ready_competitions),
        selection_rule=args.selection_rule,
        shadow_selection_rule=args.shadow_selection_rule,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_final_answer_hit_delta_count_vs_original=(
            args.min_final_answer_hit_delta_count_vs_original
        ),
        min_profit_loss_delta_vs_original=args.min_profit_loss_delta_vs_original,
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        min_item_hit_probability_delta_vs_original=(
            args.min_item_hit_probability_delta_vs_original
        ),
        exclude_original_hit_harm=args.exclude_original_hit_harm,
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
        max_report_items=args.max_report_items,
    )


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _report_key(
    summary: dict[str, object],
    items: Sequence[HistoricalShortOddsFinalAnswerGateItem],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "items": [
                {
                    "final_answer_key": item.final_answer_key,
                    "item_key": item.item_key,
                    "replacement_fixture_id": item.replacement_fixture_id,
                    "replacement_outcome": item.replacement_outcome,
                }
                for item in items
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_short_odds_final_answer_gate:{digest}"
