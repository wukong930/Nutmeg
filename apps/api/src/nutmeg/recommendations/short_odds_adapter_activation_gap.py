from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
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
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayFinalAnswer,
    HistoricalShortOddsRuntimeShadowReplayOptions,
    HistoricalShortOddsRuntimeShadowReplayReport,
    build_historical_short_odds_runtime_shadow_replay_report,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
    load_short_odds_runtime_rule_set,
)

type ShortOddsAdapterActivationGapStatus = Literal[
    "activation_candidate_found",
    "no_activation_candidate",
    "no_rules",
    "no_audit_items",
]


class ShortOddsAdapterActivationGapOptions(BaseModel):
    rule_ids: tuple[str, ...] = ()
    probe_competition_ids: tuple[str, ...] = ()
    min_probe_changed_final_answer_count: int = Field(default=1, ge=0)
    min_probe_final_answer_hit_rate_delta: float = 0.0
    min_probe_roi_delta: float = 0.0
    min_probe_profit_loss_delta: float = 0.0
    max_probe_harm_count_vs_original: int = Field(default=0, ge=0)
    max_probe_final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    max_probe_profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    min_probe_average_hit_probability_delta_vs_original: float = -0.02
    max_report_items: int = Field(default=50, ge=1, le=500)


class ShortOddsAdapterActivationGapRuleSummary(BaseModel):
    rule_id: str
    profile_id: str
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    audited_item_count: int = Field(ge=0)
    audited_replacement_candidate_count: int = Field(ge=0)
    qualified_item_count: int = Field(ge=0)
    qualified_replacement_count: int = Field(ge=0)
    item_reason_counts: dict[str, int] = Field(default_factory=dict)
    candidate_reason_counts: dict[str, int] = Field(default_factory=dict)
    competition_item_counts: dict[str, int] = Field(default_factory=dict)
    competition_reason_counts: dict[str, dict[str, int]] = Field(default_factory=dict)


class ShortOddsAdapterActivationGapReport(BaseModel):
    report_key: str
    status: ShortOddsAdapterActivationGapStatus
    activation_candidate_found: bool
    source_audit_report_key: str
    source_rule_profile_version: str
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    audit_final_answer_count: int = Field(ge=0)
    audit_item_count: int = Field(ge=0)
    audit_competition_ids: list[str] = Field(default_factory=list)
    current_qualified_item_count: int = Field(ge=0)
    current_qualified_replacement_count: int = Field(ge=0)
    current_item_reason_counts: dict[str, int] = Field(default_factory=dict)
    current_candidate_reason_counts: dict[str, int] = Field(default_factory=dict)
    current_rule_summaries: list[ShortOddsAdapterActivationGapRuleSummary] = (
        Field(default_factory=list)
    )
    probe_competition_ids: list[str] = Field(default_factory=list)
    probe_qualified_item_count: int = Field(ge=0)
    probe_qualified_replacement_count: int = Field(ge=0)
    probe_item_reason_counts: dict[str, int] = Field(default_factory=dict)
    probe_candidate_reason_counts: dict[str, int] = Field(default_factory=dict)
    probe_rule_summaries: list[ShortOddsAdapterActivationGapRuleSummary] = (
        Field(default_factory=list)
    )
    probe_shadow_replay_status: str | None = None
    probe_shadow_replay_passed: bool | None = None
    probe_changed_final_answer_count: int = Field(default=0, ge=0)
    probe_final_answer_hit_rate_delta: float | None = None
    probe_roi_delta: float | None = None
    probe_profit_loss_delta: float = 0.0
    probe_harm_count_vs_original: int = Field(default=0, ge=0)
    probe_final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    probe_profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    probe_average_hit_probability_delta_vs_original: float | None = None
    probe_changed_competition_counts: dict[str, int] = Field(default_factory=dict)
    probe_changed_items: list[HistoricalShortOddsRuntimeShadowReplayFinalAnswer] = (
        Field(default_factory=list)
    )
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _ActivationGapTally(BaseModel):
    rule_summaries: list[ShortOddsAdapterActivationGapRuleSummary]
    qualified_item_count: int = Field(ge=0)
    qualified_replacement_count: int = Field(ge=0)
    item_reason_counts: dict[str, int] = Field(default_factory=dict)
    candidate_reason_counts: dict[str, int] = Field(default_factory=dict)


def build_short_odds_adapter_activation_gap_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    options: ShortOddsAdapterActivationGapOptions | None = None,
) -> ShortOddsAdapterActivationGapReport:
    resolved_options = options or ShortOddsAdapterActivationGapOptions()
    selected_rules = rule_set.selected_rules(
        rule_ids=resolved_options.rule_ids,
        require_proposed_production_enabled=True,
        require_no_production_change=True,
    )
    audit_competition_ids = _audit_competition_ids(audit_report)
    warnings = list(audit_report.warnings)
    if not selected_rules:
        warnings.append("short_odds_adapter_activation_gap:no_enabled_rules")
        return _report(
            status="no_rules",
            audit_report=audit_report,
            rule_set=rule_set,
            selected_rules=selected_rules,
            audit_competition_ids=audit_competition_ids,
            current_tally=_empty_tally(),
            probe_tally=_empty_tally(),
            probe_report=None,
            options=resolved_options,
            warnings=warnings,
        )
    if not audit_report.items:
        warnings.append("short_odds_adapter_activation_gap:no_audit_items")
        return _report(
            status="no_audit_items",
            audit_report=audit_report,
            rule_set=rule_set,
            selected_rules=selected_rules,
            audit_competition_ids=audit_competition_ids,
            current_tally=_empty_tally(),
            probe_tally=_empty_tally(),
            probe_report=None,
            options=resolved_options,
            warnings=warnings,
        )

    current_tally = _activation_gap_tally(
        audit_report.items,
        rules=selected_rules,
    )
    probe_competition_ids = _probe_competition_ids(
        audit_competition_ids,
        options=resolved_options,
    )
    probe_rules = [
        rule.model_copy(update={"allowed_competition_ids": list(probe_competition_ids)})
        for rule in selected_rules
    ]
    probe_rule_set = rule_set.model_copy(
        update={
            "shadow_replay_enabled": True,
            "rules": _replace_selected_rules(rule_set.rules, probe_rules),
        }
    )
    probe_tally = _activation_gap_tally(
        audit_report.items,
        rules=probe_rules,
    )
    probe_report = build_historical_short_odds_runtime_shadow_replay_report(
        audit_report,
        rule_set=probe_rule_set,
        options=_probe_shadow_options(resolved_options),
    )
    status: ShortOddsAdapterActivationGapStatus = (
        "activation_candidate_found"
        if _probe_activation_candidate_found(probe_report, options=resolved_options)
        else "no_activation_candidate"
    )
    return _report(
        status=status,
        audit_report=audit_report,
        rule_set=rule_set,
        selected_rules=selected_rules,
        audit_competition_ids=audit_competition_ids,
        current_tally=current_tally,
        probe_tally=probe_tally,
        probe_report=probe_report,
        options=resolved_options,
        warnings=warnings,
    )


def load_short_odds_adapter_activation_gap_report(
    path: Path,
) -> ShortOddsAdapterActivationGapReport:
    return ShortOddsAdapterActivationGapReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_short_odds_adapter_activation_gap_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        rule_set=load_short_odds_runtime_rule_set(
            args.rule_profile,
            enable_shadow_replay=True,
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
    if (
        args.require_activation_candidate
        and not report.activation_candidate_found
        and not args.no_fail_process
    ):
        raise SystemExit(1)


def _activation_gap_tally(
    audit_items: Sequence[HistoricalCandidateMarginalAuditItem],
    *,
    rules: Sequence[ShortOddsRuntimeReplacementRule],
) -> _ActivationGapTally:
    rule_summaries = [
        _activation_gap_rule_summary(audit_items, rule=rule) for rule in rules
    ]
    return _ActivationGapTally(
        rule_summaries=rule_summaries,
        qualified_item_count=sum(summary.qualified_item_count for summary in rule_summaries),
        qualified_replacement_count=sum(
            summary.qualified_replacement_count for summary in rule_summaries
        ),
        item_reason_counts=_merge_counts(
            [summary.item_reason_counts for summary in rule_summaries]
        ),
        candidate_reason_counts=_merge_counts(
            [summary.candidate_reason_counts for summary in rule_summaries]
        ),
    )


def _activation_gap_rule_summary(
    audit_items: Sequence[HistoricalCandidateMarginalAuditItem],
    *,
    rule: ShortOddsRuntimeReplacementRule,
) -> ShortOddsAdapterActivationGapRuleSummary:
    item_reasons: Counter[str] = Counter()
    candidate_reasons: Counter[str] = Counter()
    competition_items: Counter[str] = Counter()
    competition_reasons: defaultdict[str, Counter[str]] = defaultdict(Counter)
    audited_replacement_candidate_count = 0
    qualified_item_count = 0
    qualified_replacement_count = 0
    for item in audit_items:
        competition_items[item.competition_id] += 1
        item_reason = _item_level_rejection_reason(item, rule=rule)
        if item_reason is not None:
            item_reasons[item_reason] += 1
            competition_reasons[item.competition_id][item_reason] += 1
            continue
        model_top = item.model_top_replacement
        assert model_top is not None
        if not item.replacement_candidates:
            item_reasons["replacement_candidates_missing"] += 1
            competition_reasons[item.competition_id][
                "replacement_candidates_missing"
            ] += 1
            continue
        item_qualified_count = 0
        for replacement in item.replacement_candidates:
            audited_replacement_candidate_count += 1
            candidate_reason = _candidate_level_rejection_reason(
                item,
                replacement,
                model_top=model_top,
                rule=rule,
            )
            if candidate_reason is None:
                item_qualified_count += 1
                qualified_replacement_count += 1
                candidate_reasons["qualified_replacement"] += 1
                competition_reasons[item.competition_id]["qualified_replacement"] += 1
            else:
                candidate_reasons[candidate_reason] += 1
                competition_reasons[item.competition_id][candidate_reason] += 1
        if item_qualified_count > 0:
            qualified_item_count += 1
        else:
            item_reasons["no_qualified_replacement"] += 1
            competition_reasons[item.competition_id]["no_qualified_replacement"] += 1
    return ShortOddsAdapterActivationGapRuleSummary(
        rule_id=rule.rule_id,
        profile_id=rule.profile_id,
        allowed_competition_ids=list(rule.allowed_competition_ids),
        excluded_competition_ids=list(rule.excluded_competition_ids),
        audited_item_count=len(audit_items),
        audited_replacement_candidate_count=audited_replacement_candidate_count,
        qualified_item_count=qualified_item_count,
        qualified_replacement_count=qualified_replacement_count,
        item_reason_counts=_sorted_counts(item_reasons),
        candidate_reason_counts=_sorted_counts(candidate_reasons),
        competition_item_counts=_sorted_counts(competition_items),
        competition_reason_counts={
            competition_id: _sorted_counts(reasons)
            for competition_id, reasons in sorted(competition_reasons.items())
        },
    )


def _item_level_rejection_reason(
    item: HistoricalCandidateMarginalAuditItem,
    *,
    rule: ShortOddsRuntimeReplacementRule,
) -> str | None:
    if rule.allowed_competition_ids and (
        item.competition_id not in rule.allowed_competition_ids
    ):
        return "competition_not_allowed"
    if item.competition_id in rule.excluded_competition_ids:
        return "competition_excluded"
    if item.model_top_replacement is None:
        return "model_top_missing"
    return None


def _candidate_level_rejection_reason(
    item: HistoricalCandidateMarginalAuditItem,
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    model_top: HistoricalCandidateReplacementSimulation,
    rule: ShortOddsRuntimeReplacementRule,
) -> str | None:
    if _same_replacement(replacement, model_top):
        return "same_as_model_top"
    constraints = rule.constraints()
    if replacement.replacement_decimal_odds is None:
        return "replacement_decimal_odds_missing"
    if model_top.replacement_decimal_odds is None:
        return "model_top_decimal_odds_missing"
    if replacement.replacement_probability < constraints.min_replacement_probability:
        return "replacement_probability_below_floor"
    if replacement.replacement_decimal_odds > constraints.max_replacement_decimal_odds:
        return "replacement_decimal_odds_above_ceiling"
    probability_delta = (
        replacement.replacement_probability - model_top.replacement_probability
    )
    if (
        probability_delta
        < constraints.min_candidate_hit_probability_delta_vs_model_top
        or probability_delta
        > constraints.max_candidate_hit_probability_delta_vs_model_top
    ):
        return "probability_delta_vs_model_top_out_of_range"
    original_hit_delta = (
        replacement.simulated_hit_probability - item.original_hit_probability
    )
    if (
        constraints.min_candidate_hit_probability_delta_vs_original is not None
        and original_hit_delta
        < constraints.min_candidate_hit_probability_delta_vs_original
    ):
        return "hit_probability_delta_vs_original_below_floor"
    odds_delta = replacement.replacement_decimal_odds - model_top.replacement_decimal_odds
    if odds_delta < constraints.min_decimal_odds_delta_vs_model_top:
        return "decimal_odds_delta_vs_model_top_below_floor"
    return None


def _same_replacement(
    first: HistoricalCandidateReplacementSimulation,
    second: HistoricalCandidateReplacementSimulation,
) -> bool:
    return (
        first.replacement_fixture_id == second.replacement_fixture_id
        and first.replacement_market_type == second.replacement_market_type
        and first.replacement_outcome == second.replacement_outcome
    )


def _probe_shadow_options(
    options: ShortOddsAdapterActivationGapOptions,
) -> HistoricalShortOddsRuntimeShadowReplayOptions:
    return HistoricalShortOddsRuntimeShadowReplayOptions(
        enable_shadow_replay=True,
        rule_ids=options.rule_ids,
        min_final_answer_count=1,
        min_changed_final_answer_count=options.min_probe_changed_final_answer_count,
        min_final_answer_hit_rate_delta=options.min_probe_final_answer_hit_rate_delta,
        min_roi_delta=options.min_probe_roi_delta,
        min_profit_loss_delta=options.min_probe_profit_loss_delta,
        max_harm_count_vs_original=options.max_probe_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            options.max_probe_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            options.max_probe_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            options.min_probe_average_hit_probability_delta_vs_original
        ),
        require_no_production_change=True,
        max_report_items=options.max_report_items,
    )


def _probe_activation_candidate_found(
    probe_report: HistoricalShortOddsRuntimeShadowReplayReport,
    *,
    options: ShortOddsAdapterActivationGapOptions,
) -> bool:
    return (
        probe_report.passed
        and probe_report.changed_final_answer_count
        >= options.min_probe_changed_final_answer_count
        and probe_report.harm_count_vs_original <= options.max_probe_harm_count_vs_original
        and probe_report.final_hit_harm_count_vs_original
        <= options.max_probe_final_hit_harm_count_vs_original
        and probe_report.profit_loss_harm_count_vs_original
        <= options.max_probe_profit_loss_harm_count_vs_original
    )


def _report(
    *,
    status: ShortOddsAdapterActivationGapStatus,
    audit_report: HistoricalCandidateMarginalAuditReport,
    rule_set: ShortOddsRuntimeRuleSet,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    audit_competition_ids: Sequence[str],
    current_tally: _ActivationGapTally,
    probe_tally: _ActivationGapTally,
    probe_report: object | None,
    options: ShortOddsAdapterActivationGapOptions,
    warnings: Sequence[str],
) -> ShortOddsAdapterActivationGapReport:
    probe_competition_ids = _probe_competition_ids(
        audit_competition_ids,
        options=options,
    )
    changed_items = (
        list(probe_report.changed_items)
        if probe_report is not None and hasattr(probe_report, "changed_items")
        else []
    )
    probe_changed_competition_counts = _sorted_counts(
        Counter(item.competition_id for item in changed_items)
    )
    summary = {
        "calculation_basis": "short_odds_adapter_activation_gap_v3_1",
        "status": status,
        "activation_candidate_found": status == "activation_candidate_found",
        "source_audit_report_key": audit_report.report_key,
        "source_rule_profile_version": rule_set.profile_version,
        "selected_rule_count": len(selected_rules),
        "audit_final_answer_count": audit_report.final_answer_count,
        "audit_item_count": len(audit_report.items),
        "audit_competition_ids": list(audit_competition_ids),
        "probe_competition_ids": list(probe_competition_ids),
        "current_item_reason_counts": current_tally.item_reason_counts,
        "current_candidate_reason_counts": current_tally.candidate_reason_counts,
        "probe_item_reason_counts": probe_tally.item_reason_counts,
        "probe_candidate_reason_counts": probe_tally.candidate_reason_counts,
        "probe_shadow_replay_status": _probe_attr(probe_report, "status"),
        "probe_shadow_replay_passed": _probe_attr(probe_report, "passed"),
        "probe_changed_final_answer_count": _probe_int(
            probe_report,
            "changed_final_answer_count",
        ),
        "probe_final_answer_hit_rate_delta": _probe_attr(
            probe_report,
            "final_answer_hit_rate_delta",
        ),
        "probe_roi_delta": _probe_attr(probe_report, "roi_delta"),
        "probe_profit_loss_delta": _probe_float(
            probe_report,
            "profit_loss_delta",
        ),
        "probe_harm_count_vs_original": _probe_int(
            probe_report,
            "harm_count_vs_original",
        ),
        "probe_changed_competition_counts": probe_changed_competition_counts,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "warnings": list(warnings),
    }
    report_key = _report_key(summary, current_tally, probe_tally, changed_items)
    return ShortOddsAdapterActivationGapReport(
        report_key=report_key,
        status=status,
        activation_candidate_found=status == "activation_candidate_found",
        source_audit_report_key=audit_report.report_key,
        source_rule_profile_version=rule_set.profile_version,
        rule_count=len(rule_set.rules),
        selected_rule_count=len(selected_rules),
        audit_final_answer_count=audit_report.final_answer_count,
        audit_item_count=len(audit_report.items),
        audit_competition_ids=list(audit_competition_ids),
        current_qualified_item_count=current_tally.qualified_item_count,
        current_qualified_replacement_count=current_tally.qualified_replacement_count,
        current_item_reason_counts=current_tally.item_reason_counts,
        current_candidate_reason_counts=current_tally.candidate_reason_counts,
        current_rule_summaries=current_tally.rule_summaries,
        probe_competition_ids=list(probe_competition_ids),
        probe_qualified_item_count=probe_tally.qualified_item_count,
        probe_qualified_replacement_count=probe_tally.qualified_replacement_count,
        probe_item_reason_counts=probe_tally.item_reason_counts,
        probe_candidate_reason_counts=probe_tally.candidate_reason_counts,
        probe_rule_summaries=probe_tally.rule_summaries,
        probe_shadow_replay_status=_optional_str(_probe_attr(probe_report, "status")),
        probe_shadow_replay_passed=_optional_bool(_probe_attr(probe_report, "passed")),
        probe_changed_final_answer_count=_probe_int(
            probe_report,
            "changed_final_answer_count",
        ),
        probe_final_answer_hit_rate_delta=_optional_float(
            _probe_attr(probe_report, "final_answer_hit_rate_delta")
        ),
        probe_roi_delta=_optional_float(_probe_attr(probe_report, "roi_delta")),
        probe_profit_loss_delta=_probe_float(probe_report, "profit_loss_delta"),
        probe_harm_count_vs_original=_probe_int(
            probe_report,
            "harm_count_vs_original",
        ),
        probe_final_hit_harm_count_vs_original=_probe_int(
            probe_report,
            "final_hit_harm_count_vs_original",
        ),
        probe_profit_loss_harm_count_vs_original=_probe_int(
            probe_report,
            "profit_loss_harm_count_vs_original",
        ),
        probe_average_hit_probability_delta_vs_original=_optional_float(
            _probe_attr(probe_report, "average_hit_probability_delta_vs_original")
        ),
        probe_changed_competition_counts=probe_changed_competition_counts,
        probe_changed_items=changed_items[: options.max_report_items],
        production_recommendation_changed=False,
        public_response_changed=False,
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _replace_selected_rules(
    rules: Sequence[ShortOddsRuntimeReplacementRule],
    replacements: Sequence[ShortOddsRuntimeReplacementRule],
) -> list[ShortOddsRuntimeReplacementRule]:
    by_rule_id = {rule.rule_id: rule for rule in replacements}
    return [by_rule_id.get(rule.rule_id, rule) for rule in rules]


def _probe_competition_ids(
    audit_competition_ids: Sequence[str],
    *,
    options: ShortOddsAdapterActivationGapOptions,
) -> tuple[str, ...]:
    if options.probe_competition_ids:
        return tuple(sorted(set(options.probe_competition_ids)))
    return tuple(audit_competition_ids)


def _audit_competition_ids(
    audit_report: HistoricalCandidateMarginalAuditReport,
) -> list[str]:
    return sorted({item.competition_id for item in audit_report.items})


def _empty_tally() -> _ActivationGapTally:
    return _ActivationGapTally(
        rule_summaries=[],
        qualified_item_count=0,
        qualified_replacement_count=0,
    )


def _merge_counts(counts: Sequence[Mapping[str, int]]) -> dict[str, int]:
    merged: Counter[str] = Counter()
    for count in counts:
        merged.update(count)
    return _sorted_counts(merged)


def _sorted_counts(counter: Mapping[str, int]) -> dict[str, int]:
    return {
        key: value
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    }


def _probe_attr(probe_report: object | None, name: str) -> object | None:
    if probe_report is None:
        return None
    return getattr(probe_report, name, None)


def _probe_int(probe_report: object | None, name: str) -> int:
    value = _probe_attr(probe_report, name)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _probe_float(probe_report: object | None, name: str) -> float:
    value = _probe_attr(probe_report, name)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _optional_bool(value: object | None) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_float(value: object | None) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _optional_str(value: object | None) -> str | None:
    return value if isinstance(value, str) else None


def _report_key(
    summary: Mapping[str, object],
    current_tally: _ActivationGapTally,
    probe_tally: _ActivationGapTally,
    changed_items: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "current_rule_summaries": [
                item.model_dump(mode="json") for item in current_tally.rule_summaries
            ],
            "probe_rule_summaries": [
                item.model_dump(mode="json") for item in probe_tally.rule_summaries
            ],
            "changed_items": [item.model_dump(mode="json") for item in changed_items],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"short_odds_adapter_activation_gap:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Diagnose why the short-odds adapter does or does not activate."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--rule-ids", default="")
    parser.add_argument("--probe-competition-ids", default="")
    parser.add_argument("--min-probe-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-probe-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-probe-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-probe-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-probe-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--max-probe-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-probe-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-probe-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-report-items", type=int, default=50)
    parser.add_argument("--require-activation-candidate", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> ShortOddsAdapterActivationGapOptions:
    return ShortOddsAdapterActivationGapOptions(
        rule_ids=tuple(_csv(args.rule_ids)),
        probe_competition_ids=tuple(_csv(args.probe_competition_ids)),
        min_probe_changed_final_answer_count=args.min_probe_changed_final_answer_count,
        min_probe_final_answer_hit_rate_delta=(
            args.min_probe_final_answer_hit_rate_delta
        ),
        min_probe_roi_delta=args.min_probe_roi_delta,
        min_probe_profit_loss_delta=args.min_probe_profit_loss_delta,
        max_probe_harm_count_vs_original=args.max_probe_harm_count_vs_original,
        max_probe_final_hit_harm_count_vs_original=(
            args.max_probe_final_hit_harm_count_vs_original
        ),
        max_probe_profit_loss_harm_count_vs_original=(
            args.max_probe_profit_loss_harm_count_vs_original
        ),
        min_probe_average_hit_probability_delta_vs_original=(
            args.min_probe_average_hit_probability_delta_vs_original
        ),
        max_report_items=args.max_report_items,
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
