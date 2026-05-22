from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
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
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
    load_short_odds_runtime_rule_set,
)

type HistoricalShortOddsRuntimeShadowReplayStatus = Literal[
    "shadow_replay_passed",
    "shadow_replay_failed",
    "disabled",
    "no_rules",
]
type HistoricalShortOddsRuntimeShadowReplayCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]

__all__ = [
    "HistoricalShortOddsRuntimeShadowReplayCheck",
    "HistoricalShortOddsRuntimeShadowReplayFinalAnswer",
    "HistoricalShortOddsRuntimeShadowReplayOptions",
    "HistoricalShortOddsRuntimeShadowReplayReport",
    "ShortOddsRuntimeReplacementRule",
    "ShortOddsRuntimeRuleSet",
    "build_historical_short_odds_runtime_shadow_replay_report",
    "load_short_odds_runtime_rule_set",
    "main",
]


class HistoricalShortOddsRuntimeShadowReplayOptions(BaseModel):
    enable_shadow_replay: bool = False
    rule_ids: tuple[str, ...] = ()
    min_final_answer_count: int = Field(default=30, ge=1)
    min_changed_final_answer_count: int = Field(default=5, ge=0)
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_original: int | None = Field(default=None, ge=0)
    min_average_hit_probability_delta_vs_original: float = -0.02
    min_candidate_hit_probability_delta_vs_original: float | None = None
    require_no_production_change: bool = True
    max_report_items: int = Field(default=80, ge=1, le=500)


class HistoricalShortOddsRuntimeShadowReplayCheck(BaseModel):
    name: str
    status: HistoricalShortOddsRuntimeShadowReplayCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalShortOddsRuntimeShadowReplayFinalAnswer(BaseModel):
    final_answer_key: str
    slice_id: str
    competition_id: str
    final_answer_scenario_key: str
    pass_type: str
    mode: str
    baseline_actual_hit: bool
    shadow_actual_hit: bool
    final_answer_hit_delta: int
    baseline_profit_loss: float
    shadow_profit_loss: float
    profit_loss_delta: float
    baseline_hit_probability: float = Field(ge=0.0, le=1.0)
    shadow_hit_probability: float = Field(ge=0.0, le=1.0)
    hit_probability_delta: float
    stake: float = Field(ge=0.0)
    changed_by_shadow: bool
    harmed_final_hit_vs_original: bool = False
    harmed_profit_loss_vs_original: bool
    rule_id: str | None = None
    removed_fixture_id: str | None = None
    removed_outcome: str | None = None
    replacement_fixture_id: str | None = None
    replacement_outcome: str | None = None
    replacement_rank: int | None = Field(default=None, ge=1)
    replacement_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalShortOddsRuntimeShadowReplayReport(BaseModel):
    report_key: str
    status: HistoricalShortOddsRuntimeShadowReplayStatus
    passed: bool
    source_audit_report_key: str
    source_rule_profile_version: str
    rule_count: int = Field(ge=0)
    enabled_rule_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    baseline_final_answer_hit_count: int = Field(ge=0)
    shadow_final_answer_hit_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    baseline_final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    shadow_final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    final_answer_hit_rate_delta: float | None = None
    baseline_profit_loss: float
    shadow_profit_loss: float
    profit_loss_delta: float
    baseline_roi: float | None = None
    shadow_roi: float | None = None
    roi_delta: float | None = None
    total_stake: float = Field(ge=0.0)
    harm_count_vs_original: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalShortOddsRuntimeShadowReplayCheck] = Field(
        default_factory=list
    )
    rule_set_json: dict[str, object] = Field(default_factory=dict)
    changed_items: list[HistoricalShortOddsRuntimeShadowReplayFinalAnswer] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _BaselineFinalAnswer(BaseModel):
    final_answer_key: str
    slice_id: str
    competition_id: str
    final_answer_scenario_key: str
    pass_type: str
    mode: str
    actual_hit: bool
    profit_loss: float
    hit_probability: float = Field(ge=0.0, le=1.0)
    stake: float = Field(ge=0.0)
    source_item_key: str


class _ReplacementOverride(BaseModel):
    final_answer_key: str
    rule_id: str
    item_key: str
    removed_fixture_id: str
    removed_outcome: str
    replacement: HistoricalCandidateReplacementSimulation


def build_historical_short_odds_runtime_shadow_replay_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    options: HistoricalShortOddsRuntimeShadowReplayOptions | None = None,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    resolved_options = options or HistoricalShortOddsRuntimeShadowReplayOptions()
    resolved_rule_set = rule_set.model_copy(
        update={"shadow_replay_enabled": resolved_options.enable_shadow_replay}
    )
    warnings = list(audit_report.warnings)
    selected_rules = _selected_rules(resolved_rule_set, options=resolved_options)
    baseline_answers = _baseline_final_answers(audit_report, warnings=warnings)
    if not resolved_options.enable_shadow_replay:
        warnings.append("short_odds_runtime_shadow_replay:disabled_by_feature_flag")
        return _report(
            audit_report,
            rule_set=resolved_rule_set,
            suite_answers=_suite_answers_from_baseline(baseline_answers, overrides={}),
            selected_rules=selected_rules,
            checks=[],
            status="disabled",
            passed=False,
            warnings=warnings,
            options=resolved_options,
        )
    if not selected_rules:
        warnings.append("short_odds_runtime_shadow_replay:no_enabled_rules")
        return _report(
            audit_report,
            rule_set=resolved_rule_set,
            suite_answers=_suite_answers_from_baseline(baseline_answers, overrides={}),
            selected_rules=selected_rules,
            checks=[],
            status="no_rules",
            passed=False,
            warnings=warnings,
            options=resolved_options,
        )

    overrides = _selected_overrides(
        audit_report.items,
        rules=selected_rules,
        options=resolved_options,
    )
    suite_answers = _suite_answers_from_baseline(baseline_answers, overrides=overrides)
    checks = _checks(
        suite_answers,
        rule_set=resolved_rule_set,
        selected_rules=selected_rules,
        options=resolved_options,
    )
    passed = all(check.status != "failed" for check in checks)
    status: HistoricalShortOddsRuntimeShadowReplayStatus = (
        "shadow_replay_passed" if passed else "shadow_replay_failed"
    )
    return _report(
        audit_report,
        rule_set=resolved_rule_set,
        suite_answers=suite_answers,
        selected_rules=selected_rules,
        checks=checks,
        status=status,
        passed=passed,
        warnings=warnings,
        options=resolved_options,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    options = _options_from_args(args)
    rule_set = load_short_odds_runtime_rule_set(
        args.rule_profile,
        enable_shadow_replay=options.enable_shadow_replay,
    )
    report = build_historical_short_odds_runtime_shadow_replay_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        rule_set=rule_set,
        options=options,
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
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


def _selected_rules(
    rule_set: ShortOddsRuntimeRuleSet,
    *,
    options: HistoricalShortOddsRuntimeShadowReplayOptions,
) -> list[ShortOddsRuntimeReplacementRule]:
    rule_ids = set(options.rule_ids)
    return [
        rule
        for rule in rule_set.rules
        if rule.proposed_production_enabled
        and not rule.production_recommendation_changed
        and (not rule_ids or rule.rule_id in rule_ids)
    ]


def _baseline_final_answers(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    warnings: list[str],
) -> list[_BaselineFinalAnswer]:
    by_key: dict[str, _BaselineFinalAnswer] = {}
    for audit_item in audit_report.items:
        final_answer_key = _final_answer_key(audit_item)
        baseline = _BaselineFinalAnswer(
            final_answer_key=final_answer_key,
            slice_id=audit_item.slice_id,
            competition_id=audit_item.competition_id,
            final_answer_scenario_key=audit_item.final_answer_scenario_key,
            pass_type=audit_item.pass_type,
            mode=str(audit_item.mode),
            actual_hit=audit_item.final_answer_actual_hit,
            profit_loss=audit_item.original_profit_loss,
            hit_probability=audit_item.original_hit_probability,
            stake=_stake_from_audit_item(audit_item),
            source_item_key=audit_item.item_key,
        )
        existing = by_key.get(final_answer_key)
        if existing is not None:
            if existing.model_dump(exclude={"source_item_key"}) != baseline.model_dump(
                exclude={"source_item_key"}
            ):
                warnings.append(
                    "short_odds_runtime_shadow_replay:inconsistent_final_answer:"
                    f"{final_answer_key}"
                )
            continue
        by_key[final_answer_key] = baseline
    return sorted(by_key.values(), key=lambda item: item.final_answer_key)


def _selected_overrides(
    audit_items: Sequence[HistoricalCandidateMarginalAuditItem],
    *,
    rules: Sequence[ShortOddsRuntimeReplacementRule],
    options: HistoricalShortOddsRuntimeShadowReplayOptions,
) -> dict[str, _ReplacementOverride]:
    grouped: dict[str, list[_ReplacementOverride]] = {}
    for audit_item in audit_items:
        for rule in rules:
            replacement = _replacement_for_rule(
                audit_item,
                rule=rule,
                options=options,
            )
            if replacement is None:
                continue
            final_answer_key = _final_answer_key(audit_item)
            grouped.setdefault(final_answer_key, []).append(
                _ReplacementOverride(
                    final_answer_key=final_answer_key,
                    rule_id=rule.rule_id,
                    item_key=audit_item.item_key,
                    removed_fixture_id=audit_item.selected_fixture_id,
                    removed_outcome=audit_item.selected_outcome,
                    replacement=replacement,
                )
            )
    return {
        key: _select_override(overrides)
        for key, overrides in grouped.items()
        if overrides
    }


def _replacement_for_rule(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    rule: ShortOddsRuntimeReplacementRule,
    options: HistoricalShortOddsRuntimeShadowReplayOptions,
) -> HistoricalCandidateReplacementSimulation | None:
    if rule.allowed_competition_ids and (
        audit_item.competition_id not in rule.allowed_competition_ids
    ):
        return None
    if audit_item.competition_id in rule.excluded_competition_ids:
        return None
    model_top = audit_item.model_top_replacement
    if model_top is None:
        return None
    qualified = [
        replacement
        for replacement in audit_item.replacement_candidates
        if not _same_replacement(replacement, model_top)
        and _passes_rule_constraints(
            replacement,
            model_top=model_top,
            audit_item=audit_item,
            rule=rule,
            options=options,
        )
    ]
    if not qualified:
        return None
    if rule.profile_id == "max_short_odds_within_deficit_v1":
        return max(
            qualified,
            key=lambda replacement: (
                replacement.replacement_decimal_odds or 0.0,
                -_hit_probability_delta(replacement, model_top),
                replacement.replacement_model_edge,
                replacement.replacement_quality_score,
                -replacement.replacement_rank,
            ),
        )
    if rule.profile_id in {
        "max_model_edge_within_deficit",
        "max_model_edge_within_deficit_v1",
    }:
        return max(
            qualified,
            key=lambda replacement: (
                replacement.replacement_model_edge,
                replacement.replacement_decimal_odds or 0.0,
                replacement.replacement_quality_score,
                replacement.simulated_hit_probability,
                -replacement.replacement_rank,
            ),
        )
    if rule.profile_id in {
        "probability_preserving_model_edge",
        "probability_preserving_model_edge_v1",
    }:
        return max(
            qualified,
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
    if rule.profile_id in {
        "probability_preserving_quality_score",
        "probability_preserving_quality_score_v1",
    }:
        return max(
            qualified,
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
        qualified,
        key=lambda replacement: (
            replacement.simulated_hit_probability,
            replacement.replacement_decimal_odds or 0.0,
            replacement.replacement_model_edge,
            replacement.replacement_quality_score,
            -replacement.replacement_rank,
        ),
    )


def _passes_rule_constraints(
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    model_top: HistoricalCandidateReplacementSimulation,
    audit_item: HistoricalCandidateMarginalAuditItem,
    rule: ShortOddsRuntimeReplacementRule,
    options: HistoricalShortOddsRuntimeShadowReplayOptions,
) -> bool:
    constraints = rule.constraints_json
    if replacement.replacement_decimal_odds is None:
        return False
    if model_top.replacement_decimal_odds is None:
        return False
    min_probability = _float(
        constraints.get("min_replacement_probability"),
        fallback=0.55,
    )
    max_odds = _float(
        constraints.get("max_replacement_decimal_odds"),
        fallback=1.75,
    )
    min_hit_delta = _float(
        constraints.get("min_candidate_hit_probability_delta_vs_model_top"),
        fallback=-0.015,
    )
    max_hit_delta = _float(
        constraints.get("max_candidate_hit_probability_delta_vs_model_top"),
        fallback=0.0,
    )
    min_odds_delta = _float(
        constraints.get("min_decimal_odds_delta_vs_model_top"),
        fallback=0.0,
    )
    min_original_hit_delta = _optional_float(
        constraints.get("min_candidate_hit_probability_delta_vs_original")
    )
    if min_original_hit_delta is None:
        min_original_hit_delta = options.min_candidate_hit_probability_delta_vs_original
    exclude_original_hit_harm = bool(
        constraints.get("exclude_original_hit_harm", False)
    )
    if (
        exclude_original_hit_harm
        and audit_item.final_answer_actual_hit
        and not replacement.simulated_actual_hit
    ):
        return False
    if replacement.replacement_probability < min_probability:
        return False
    if replacement.replacement_decimal_odds > max_odds:
        return False
    hit_delta = _hit_probability_delta(replacement, model_top)
    if hit_delta < min_hit_delta or hit_delta > max_hit_delta:
        return False
    original_hit_delta = (
        replacement.simulated_hit_probability - audit_item.original_hit_probability
    )
    if (
        min_original_hit_delta is not None
        and original_hit_delta < min_original_hit_delta
    ):
        return False
    odds_delta = replacement.replacement_decimal_odds - model_top.replacement_decimal_odds
    return odds_delta >= min_odds_delta


def _select_override(
    overrides: Sequence[_ReplacementOverride],
) -> _ReplacementOverride:
    return max(
        overrides,
        key=lambda override: (
            override.replacement.simulated_hit_probability,
            override.replacement.replacement_decimal_odds or 0.0,
            override.replacement.replacement_model_edge,
            override.replacement.replacement_quality_score,
            override.item_key,
        ),
    )


def _suite_answers_from_baseline(
    baseline_answers: Sequence[_BaselineFinalAnswer],
    *,
    overrides: Mapping[str, _ReplacementOverride],
) -> list[HistoricalShortOddsRuntimeShadowReplayFinalAnswer]:
    return [
        _suite_answer_from_baseline(
            baseline,
            override=overrides.get(baseline.final_answer_key),
        )
        for baseline in baseline_answers
    ]


def _suite_answer_from_baseline(
    baseline: _BaselineFinalAnswer,
    *,
    override: _ReplacementOverride | None,
) -> HistoricalShortOddsRuntimeShadowReplayFinalAnswer:
    shadow_actual_hit = baseline.actual_hit
    shadow_profit_loss = baseline.profit_loss
    shadow_hit_probability = baseline.hit_probability
    rule_id: str | None = None
    removed_fixture_id: str | None = None
    removed_outcome: str | None = None
    replacement_fixture_id: str | None = None
    replacement_outcome: str | None = None
    replacement_rank: int | None = None
    replacement_probability: float | None = None
    replacement_decimal_odds: float | None = None
    changed = False
    if override is not None:
        replacement = override.replacement
        shadow_actual_hit = replacement.simulated_actual_hit
        shadow_profit_loss = replacement.simulated_profit_loss
        shadow_hit_probability = replacement.simulated_hit_probability
        rule_id = override.rule_id
        removed_fixture_id = override.removed_fixture_id
        removed_outcome = override.removed_outcome
        replacement_fixture_id = replacement.replacement_fixture_id
        replacement_outcome = replacement.replacement_outcome
        replacement_rank = replacement.replacement_rank
        replacement_probability = replacement.replacement_probability
        replacement_decimal_odds = replacement.replacement_decimal_odds
        changed = True
    profit_delta = shadow_profit_loss - baseline.profit_loss
    hit_probability_delta = shadow_hit_probability - baseline.hit_probability
    final_answer_hit_delta = int(shadow_actual_hit) - int(baseline.actual_hit)
    return HistoricalShortOddsRuntimeShadowReplayFinalAnswer(
        final_answer_key=baseline.final_answer_key,
        slice_id=baseline.slice_id,
        competition_id=baseline.competition_id,
        final_answer_scenario_key=baseline.final_answer_scenario_key,
        pass_type=baseline.pass_type,
        mode=baseline.mode,
        baseline_actual_hit=baseline.actual_hit,
        shadow_actual_hit=shadow_actual_hit,
        final_answer_hit_delta=final_answer_hit_delta,
        baseline_profit_loss=baseline.profit_loss,
        shadow_profit_loss=shadow_profit_loss,
        profit_loss_delta=profit_delta,
        baseline_hit_probability=baseline.hit_probability,
        shadow_hit_probability=shadow_hit_probability,
        hit_probability_delta=hit_probability_delta,
        stake=baseline.stake,
        changed_by_shadow=changed,
        harmed_final_hit_vs_original=final_answer_hit_delta < 0,
        harmed_profit_loss_vs_original=profit_delta < 0,
        rule_id=rule_id,
        removed_fixture_id=removed_fixture_id,
        removed_outcome=removed_outcome,
        replacement_fixture_id=replacement_fixture_id,
        replacement_outcome=replacement_outcome,
        replacement_rank=replacement_rank,
        replacement_probability=replacement_probability,
        replacement_decimal_odds=replacement_decimal_odds,
        summary_json={
            "calculation_basis": "historical_short_odds_runtime_shadow_item_v3_1",
            "production_recommendation_changed": False,
            "public_response_changed": False,
        },
    )


def _checks(
    items: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    options: HistoricalShortOddsRuntimeShadowReplayOptions,
) -> list[HistoricalShortOddsRuntimeShadowReplayCheck]:
    checks = [
        _boolean_check(
            name="shadow_replay_enabled",
            actual=rule_set.shadow_replay_enabled,
            expected=True,
            detail="shadow replay must be enabled explicitly",
        ),
        _minimum_check(
            name="enabled_rule_count",
            actual=len(selected_rules),
            threshold=1,
            detail="at least one enabled runtime rule is required",
        ),
        _minimum_check(
            name="final_answer_count",
            actual=len(items),
            threshold=options.min_final_answer_count,
            detail="shadow replay should include enough final answers",
        ),
        _minimum_check(
            name="changed_final_answer_count",
            actual=sum(1 for item in items if item.changed_by_shadow),
            threshold=options.min_changed_final_answer_count,
            detail="shadow replay should affect enough final answers",
        ),
        _minimum_check(
            name="final_answer_hit_rate_delta",
            actual=_hit_rate_delta(items),
            threshold=options.min_final_answer_hit_rate_delta,
            detail="shadow replay final-answer hit rate should not regress",
        ),
        _minimum_check(
            name="roi_delta",
            actual=_roi_delta(items),
            threshold=options.min_roi_delta,
            detail="shadow replay ROI should not regress",
        ),
        _minimum_check(
            name="profit_loss_delta",
            actual=sum(item.profit_loss_delta for item in items),
            threshold=options.min_profit_loss_delta,
            detail="shadow replay profit/loss should not regress",
        ),
        _maximum_check(
            name="harm_count_vs_original",
            actual=_profit_loss_harm_count(items),
            threshold=options.max_harm_count_vs_original,
            detail=(
                "compatibility check: shadow replay should not reduce final-answer "
                "profit/loss"
            ),
        ),
        _maximum_check(
            name="final_hit_harm_count_vs_original",
            actual=_final_hit_harm_count(items),
            threshold=_final_hit_harm_threshold(options),
            detail="shadow replay should not turn original hits into misses",
        ),
        _maximum_check(
            name="profit_loss_harm_count_vs_original",
            actual=_profit_loss_harm_count(items),
            threshold=_profit_loss_harm_threshold(options),
            detail="shadow replay should not reduce original final-answer profit/loss",
        ),
        _minimum_check(
            name="average_hit_probability_delta_vs_original",
            actual=_average_changed_hit_probability_delta(items),
            threshold=options.min_average_hit_probability_delta_vs_original,
            detail="expected hit-probability tolerance should remain bounded",
        ),
        _boolean_check(
            name="no_public_response_change",
            actual=True,
            expected=True,
            detail="runtime shadow replay must not change public response",
        ),
    ]
    if options.require_no_production_change:
        checks.append(
            _boolean_check(
                name="no_production_recommendation_change",
                actual=not any(
                    rule.production_recommendation_changed for rule in selected_rules
                ),
                expected=True,
                detail="runtime shadow replay must not change production recommendations",
            )
        )
    return checks


def _report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    suite_answers: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    checks: Sequence[HistoricalShortOddsRuntimeShadowReplayCheck],
    status: HistoricalShortOddsRuntimeShadowReplayStatus,
    passed: bool,
    warnings: Sequence[str],
    options: HistoricalShortOddsRuntimeShadowReplayOptions,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    changed_items = sorted(
        (item for item in suite_answers if item.changed_by_shadow),
        key=lambda item: (
            item.profit_loss_delta,
            item.final_answer_hit_delta,
            item.final_answer_key,
        ),
        reverse=True,
    )[: options.max_report_items]
    total_stake = sum(item.stake for item in suite_answers)
    baseline_profit_loss = sum(item.baseline_profit_loss for item in suite_answers)
    shadow_profit_loss = sum(item.shadow_profit_loss for item in suite_answers)
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_runtime_shadow_replay_v3_1",
        "status": status,
        "passed": passed,
        "source_audit_report_key": audit_report.report_key,
        "source_rule_profile_version": rule_set.profile_version,
        "rule_count": len(rule_set.rules),
        "enabled_rule_count": len(selected_rules),
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": options.model_dump(mode="json"),
        "warnings": list(warnings),
    }
    report_key = _report_key(summary, checks, changed_items)
    return HistoricalShortOddsRuntimeShadowReplayReport(
        report_key=report_key,
        status=status,
        passed=passed,
        source_audit_report_key=audit_report.report_key,
        source_rule_profile_version=rule_set.profile_version,
        rule_count=len(rule_set.rules),
        enabled_rule_count=len(selected_rules),
        final_answer_count=len(suite_answers),
        changed_final_answer_count=sum(
            1 for item in suite_answers if item.changed_by_shadow
        ),
        baseline_final_answer_hit_count=sum(
            1 for item in suite_answers if item.baseline_actual_hit
        ),
        shadow_final_answer_hit_count=sum(
            1 for item in suite_answers if item.shadow_actual_hit
        ),
        final_answer_hit_delta_count=sum(
            item.final_answer_hit_delta for item in suite_answers
        ),
        baseline_final_answer_hit_rate=_ratio(
            sum(1 for item in suite_answers if item.baseline_actual_hit),
            len(suite_answers),
        ),
        shadow_final_answer_hit_rate=_ratio(
            sum(1 for item in suite_answers if item.shadow_actual_hit),
            len(suite_answers),
        ),
        final_answer_hit_rate_delta=_hit_rate_delta(suite_answers),
        baseline_profit_loss=baseline_profit_loss,
        shadow_profit_loss=shadow_profit_loss,
        profit_loss_delta=shadow_profit_loss - baseline_profit_loss,
        baseline_roi=_roi(profit_loss=baseline_profit_loss, stake=total_stake),
        shadow_roi=_roi(profit_loss=shadow_profit_loss, stake=total_stake),
        roi_delta=_roi_delta(suite_answers),
        total_stake=total_stake,
        harm_count_vs_original=sum(
            1 for item in suite_answers if item.harmed_profit_loss_vs_original
        ),
        final_hit_harm_count_vs_original=_final_hit_harm_count(suite_answers),
        profit_loss_harm_count_vs_original=_profit_loss_harm_count(suite_answers),
        average_hit_probability_delta_vs_original=(
            _average_changed_hit_probability_delta(suite_answers)
        ),
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=list(checks),
        rule_set_json=rule_set.model_dump(mode="json"),
        changed_items=changed_items,
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _final_answer_key(item: HistoricalCandidateMarginalAuditItem) -> str:
    return f"{item.slice_id}:{item.final_answer_scenario_key}"


def _stake_from_audit_item(item: HistoricalCandidateMarginalAuditItem) -> float:
    stake = item.original_actual_return - item.original_profit_loss
    if stake >= 0:
        return stake
    if item.original_roi != 0:
        return abs(item.original_profit_loss / item.original_roi)
    return 0.0


def _same_replacement(
    left: HistoricalCandidateReplacementSimulation,
    right: HistoricalCandidateReplacementSimulation,
) -> bool:
    return (
        left.replacement_fixture_id == right.replacement_fixture_id
        and left.replacement_outcome == right.replacement_outcome
    )


def _hit_probability_delta(
    replacement: HistoricalCandidateReplacementSimulation,
    model_top: HistoricalCandidateReplacementSimulation,
) -> float:
    return replacement.simulated_hit_probability - model_top.simulated_hit_probability


def _hit_probability_delta_bucket(delta: float) -> float:
    if delta >= -0.005:
        return 3.0
    if delta >= -0.015:
        return 2.0
    if delta >= -0.03:
        return 1.0
    return 0.0


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> HistoricalShortOddsRuntimeShadowReplayCheck:
    return HistoricalShortOddsRuntimeShadowReplayCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalShortOddsRuntimeShadowReplayCheck:
    if actual is None:
        return HistoricalShortOddsRuntimeShadowReplayCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRuntimeShadowReplayCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalShortOddsRuntimeShadowReplayCheck:
    if actual is None:
        return HistoricalShortOddsRuntimeShadowReplayCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRuntimeShadowReplayCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Load short-odds runtime rules and run gated shadow replay."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--enable-shadow-replay", action="store_true")
    parser.add_argument(
        "--rule-ids",
        default="",
        help="Comma-separated rule ids. Empty means all enabled rules.",
    )
    parser.add_argument("--min-final-answer-count", type=int, default=30)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=5)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-final-hit-harm-count-vs-original", type=int)
    parser.add_argument("--max-profit-loss-harm-count-vs-original", type=int)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument(
        "--min-candidate-hit-probability-delta-vs-original",
        type=float,
        default=None,
        help=(
            "Optional candidate-level floor against the current final-answer hit "
            "probability before final-answer override arbitration."
        ),
    )
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-items", type=int, default=80)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalShortOddsRuntimeShadowReplayOptions:
    return HistoricalShortOddsRuntimeShadowReplayOptions(
        enable_shadow_replay=args.enable_shadow_replay,
        rule_ids=_csv_values(args.rule_ids),
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_final_answer_hit_rate_delta=args.min_final_answer_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            args.max_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            args.max_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        min_candidate_hit_probability_delta_vs_original=(
            args.min_candidate_hit_probability_delta_vs_original
        ),
        require_no_production_change=not args.allow_production_change,
        max_report_items=args.max_report_items,
    )


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _hit_rate_delta(
    items: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
) -> float | None:
    baseline = _ratio(sum(1 for item in items if item.baseline_actual_hit), len(items))
    shadow = _ratio(sum(1 for item in items if item.shadow_actual_hit), len(items))
    if baseline is None or shadow is None:
        return None
    return shadow - baseline


def _roi_delta(
    items: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
) -> float | None:
    stake = sum(item.stake for item in items)
    baseline = _roi(
        profit_loss=sum(item.baseline_profit_loss for item in items),
        stake=stake,
    )
    shadow = _roi(
        profit_loss=sum(item.shadow_profit_loss for item in items),
        stake=stake,
    )
    if baseline is None or shadow is None:
        return None
    return shadow - baseline


def _final_hit_harm_count(
    items: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
) -> int:
    return sum(1 for item in items if item.harmed_final_hit_vs_original)


def _profit_loss_harm_count(
    items: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
) -> int:
    return sum(1 for item in items if item.harmed_profit_loss_vs_original)


def _final_hit_harm_threshold(
    options: HistoricalShortOddsRuntimeShadowReplayOptions,
) -> int:
    return (
        options.max_final_hit_harm_count_vs_original
        if options.max_final_hit_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _profit_loss_harm_threshold(
    options: HistoricalShortOddsRuntimeShadowReplayOptions,
) -> int:
    return (
        options.max_profit_loss_harm_count_vs_original
        if options.max_profit_loss_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _roi(*, profit_loss: float, stake: float) -> float | None:
    if stake <= 0:
        return None
    return profit_loss / stake


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _average_changed_hit_probability_delta(
    items: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
) -> float:
    if not any(item.changed_by_shadow for item in items):
        return 0.0
    return _average(
        item.hit_probability_delta for item in items if item.changed_by_shadow
    ) or 0.0


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _float(value: object, *, fallback: float) -> float:
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalShortOddsRuntimeShadowReplayCheck],
    changed_items: Sequence[HistoricalShortOddsRuntimeShadowReplayFinalAnswer],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "changed_items": [
                    {
                        "final_answer_key": item.final_answer_key,
                        "rule_id": item.rule_id,
                        "replacement_fixture_id": item.replacement_fixture_id,
                        "replacement_outcome": item.replacement_outcome,
                    }
                    for item in changed_items
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_short_odds_runtime_shadow_replay:{digest}"
