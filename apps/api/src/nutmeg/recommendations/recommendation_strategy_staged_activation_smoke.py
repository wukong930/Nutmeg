from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.recommendation_strategy_promotion_gate import (
    RecommendationStrategyPromotionGateReport,
    load_recommendation_strategy_promotion_gate_report,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
)

type RecommendationStrategyStagedActivationSmokeStatus = Literal[
    "staged_activation_ready",
    "staged_activation_watchlist",
    "blocked",
]
type RecommendationStrategyStagedActivationSmokeCheckStatus = Literal[
    "passed",
    "failed",
]


class RecommendationStrategyStagedActivationSmokeOptions(BaseModel):
    staged_profile_version: str = (
        "v3_1_probability_preserving_replacement_staged_activation_smoke"
    )
    min_rule_count: int = Field(default=1, ge=1)
    min_allowed_competition_count: int = Field(default=5, ge=0)
    min_total_final_answer_count: int = Field(default=30, ge=1)
    min_total_changed_final_answer_count: int = Field(default=1, ge=0)
    min_total_final_answer_hit_delta_count: int = 0
    min_total_profit_loss_delta: float = 0.0
    min_minimum_roi_delta: float | None = 0.0
    max_total_harm_count_vs_original: int = Field(default=0, ge=0)
    max_total_final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    max_total_profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    min_minimum_active_surface_count: int = Field(default=1, ge=0)
    max_total_failed_surface_count: int = Field(default=0, ge=0)
    min_minimum_active_competition_fold_count: int = Field(default=1, ge=0)
    min_minimum_active_season_fold_count: int = Field(default=1, ge=0)
    min_minimum_active_rolling_fold_count: int = Field(default=1, ge=0)
    max_total_failed_fold_count: int = Field(default=0, ge=0)
    require_strategy_gate_ready: bool = True
    require_profile_dry_run_only: bool = True
    require_profile_promotion_review_allowed: bool = True
    require_profile_review_ready: bool = True
    require_no_default_profile_write: bool = True
    require_no_production_allowed: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True
    require_no_allowed_excluded_overlap: bool = True
    require_rules_enabled: bool = True
    require_rule_no_production_change: bool = True
    require_no_harm_constraints: bool = True
    require_exclude_original_hit_harm: bool = True
    require_source_candidate_match: bool = True
    require_source_chain_complete: bool = True


class RecommendationStrategyStagedActivationSmokeCheck(BaseModel):
    name: str
    status: RecommendationStrategyStagedActivationSmokeCheckStatus
    actual: float | int | str | bool | list[str] | None = None
    threshold: float | int | str | bool | list[str] | None = None
    detail: str


class RecommendationStrategyStagedActivationSmokeReport(BaseModel):
    report_key: str
    status: RecommendationStrategyStagedActivationSmokeStatus
    staged_activation_ready: bool
    staged_profile_version: str
    source_strategy_gate_key: str
    source_strategy_key: str
    source_gate_id: str
    source_promotion_review_report_keys: list[str] = Field(default_factory=list)
    source_selected_candidate_keys: list[str] = Field(default_factory=list)
    rule_profile_version: str
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    total_final_answer_count: int = Field(ge=0)
    total_changed_final_answer_count: int = Field(ge=0)
    total_final_answer_hit_delta_count: int
    total_profit_loss_delta: float
    minimum_roi_delta: float | None = None
    total_harm_count_vs_original: int = Field(ge=0)
    total_final_hit_harm_count_vs_original: int = Field(ge=0)
    total_profit_loss_harm_count_vs_original: int = Field(ge=0)
    minimum_active_surface_count: int = Field(ge=0)
    total_failed_surface_count: int = Field(ge=0)
    minimum_active_competition_fold_count: int = Field(ge=0)
    minimum_active_season_fold_count: int = Field(ge=0)
    minimum_active_rolling_fold_count: int = Field(ge=0)
    total_failed_fold_count: int = Field(ge=0)
    default_profile_write_requested: bool = False
    default_profile_written: bool = False
    production_recommendation_allowed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[RecommendationStrategyStagedActivationSmokeCheck] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    staged_profile_json: dict[str, object] = Field(default_factory=dict)
    public_contract_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_recommendation_strategy_staged_activation_smoke_report(
    strategy_gate_report: RecommendationStrategyPromotionGateReport,
    *,
    rule_profile: Mapping[str, object],
    options: RecommendationStrategyStagedActivationSmokeOptions | None = None,
) -> RecommendationStrategyStagedActivationSmokeReport:
    resolved_options = options or RecommendationStrategyStagedActivationSmokeOptions()
    rule_set = _rule_set_from_profile(rule_profile)
    rules = rule_set.selected_rules(
        require_proposed_production_enabled=False,
        require_no_production_change=False,
    )
    selected_rules = _selected_rules(rules, options=resolved_options)
    allowed_competition_ids = _unique(
        competition_id
        for rule in selected_rules
        for competition_id in rule.allowed_competition_ids
    )
    excluded_competition_ids = _unique(
        competition_id
        for rule in selected_rules
        for competition_id in rule.excluded_competition_ids
    )
    source_promotion_review_report_keys = _unique(
        item.report_key for item in strategy_gate_report.evidence
    )
    source_selected_candidate_keys = _unique(
        strategy_gate_report.selected_candidate_keys
    )
    staged_profile = _staged_profile_json(
        rule_profile=rule_profile,
        rule_set=rule_set,
        selected_rules=selected_rules,
        strategy_gate_report=strategy_gate_report,
        options=resolved_options,
    )
    public_contract_json: dict[str, object] = {
        "public_response_changed": False,
        "frontend_changed": False,
        "ordinary_user_path_changed": False,
        "internal_strategy_details_exposed": False,
        "production_recommendation_changed": False,
        "default_profile_written": False,
    }
    checks = _checks(
        strategy_gate_report,
        rule_profile=rule_profile,
        selected_rules=selected_rules,
        allowed_competition_ids=allowed_competition_ids,
        excluded_competition_ids=excluded_competition_ids,
        public_contract_json=public_contract_json,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    status = _status(strategy_gate_report, blockers)
    staged_activation_ready = status == "staged_activation_ready"
    warnings = [
        *strategy_gate_report.warnings,
        *[
            f"recommendation_strategy_staged_activation_smoke:failed_check:{name}"
            for name in blockers
        ],
    ]
    summary: dict[str, object] = {
        "calculation_basis": "recommendation_strategy_staged_activation_smoke_v3_1",
        "status": status,
        "staged_activation_ready": staged_activation_ready,
        "staged_profile_version": resolved_options.staged_profile_version,
        "source_strategy_gate_key": strategy_gate_report.gate_key,
        "source_strategy_key": strategy_gate_report.strategy_key,
        "source_gate_id": strategy_gate_report.gate_id,
        "source_promotion_review_report_keys": source_promotion_review_report_keys,
        "source_selected_candidate_keys": source_selected_candidate_keys,
        "rule_profile_version": rule_set.profile_version,
        "rule_count": len(rule_set.rules),
        "selected_rule_count": len(selected_rules),
        "allowed_competition_ids": allowed_competition_ids,
        "excluded_competition_ids": excluded_competition_ids,
        "total_final_answer_count": strategy_gate_report.total_final_answer_count,
        "total_changed_final_answer_count": (
            strategy_gate_report.total_changed_final_answer_count
        ),
        "total_final_answer_hit_delta_count": (
            strategy_gate_report.total_final_answer_hit_delta_count
        ),
        "total_profit_loss_delta": strategy_gate_report.total_profit_loss_delta,
        "minimum_roi_delta": strategy_gate_report.minimum_roi_delta,
        "total_harm_count_vs_original": (
            strategy_gate_report.total_harm_count_vs_original
        ),
        "total_final_hit_harm_count_vs_original": (
            strategy_gate_report.total_final_hit_harm_count_vs_original
        ),
        "total_profit_loss_harm_count_vs_original": (
            strategy_gate_report.total_profit_loss_harm_count_vs_original
        ),
        "minimum_active_surface_count": (
            strategy_gate_report.minimum_active_surface_count
        ),
        "total_failed_surface_count": (
            strategy_gate_report.total_failed_surface_count
        ),
        "minimum_active_competition_fold_count": (
            strategy_gate_report.minimum_active_competition_fold_count
        ),
        "minimum_active_season_fold_count": (
            strategy_gate_report.minimum_active_season_fold_count
        ),
        "minimum_active_rolling_fold_count": (
            strategy_gate_report.minimum_active_rolling_fold_count
        ),
        "total_failed_fold_count": strategy_gate_report.total_failed_fold_count,
        "default_profile_write_requested": False,
        "default_profile_written": False,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "blockers": blockers,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, staged_profile)
    return RecommendationStrategyStagedActivationSmokeReport(
        report_key=report_key,
        status=status,
        staged_activation_ready=staged_activation_ready,
        staged_profile_version=resolved_options.staged_profile_version,
        source_strategy_gate_key=strategy_gate_report.gate_key,
        source_strategy_key=strategy_gate_report.strategy_key,
        source_gate_id=strategy_gate_report.gate_id,
        source_promotion_review_report_keys=source_promotion_review_report_keys,
        source_selected_candidate_keys=source_selected_candidate_keys,
        rule_profile_version=rule_set.profile_version,
        rule_count=len(rule_set.rules),
        selected_rule_count=len(selected_rules),
        allowed_competition_ids=allowed_competition_ids,
        excluded_competition_ids=excluded_competition_ids,
        total_final_answer_count=strategy_gate_report.total_final_answer_count,
        total_changed_final_answer_count=(
            strategy_gate_report.total_changed_final_answer_count
        ),
        total_final_answer_hit_delta_count=(
            strategy_gate_report.total_final_answer_hit_delta_count
        ),
        total_profit_loss_delta=strategy_gate_report.total_profit_loss_delta,
        minimum_roi_delta=strategy_gate_report.minimum_roi_delta,
        total_harm_count_vs_original=(
            strategy_gate_report.total_harm_count_vs_original
        ),
        total_final_hit_harm_count_vs_original=(
            strategy_gate_report.total_final_hit_harm_count_vs_original
        ),
        total_profit_loss_harm_count_vs_original=(
            strategy_gate_report.total_profit_loss_harm_count_vs_original
        ),
        minimum_active_surface_count=(
            strategy_gate_report.minimum_active_surface_count
        ),
        total_failed_surface_count=strategy_gate_report.total_failed_surface_count,
        minimum_active_competition_fold_count=(
            strategy_gate_report.minimum_active_competition_fold_count
        ),
        minimum_active_season_fold_count=(
            strategy_gate_report.minimum_active_season_fold_count
        ),
        minimum_active_rolling_fold_count=(
            strategy_gate_report.minimum_active_rolling_fold_count
        ),
        total_failed_fold_count=strategy_gate_report.total_failed_fold_count,
        default_profile_write_requested=False,
        default_profile_written=False,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=checks,
        blockers=blockers,
        staged_profile_json=staged_profile,
        public_contract_json=public_contract_json,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_recommendation_strategy_staged_activation_smoke_report(
    path: Path | str,
) -> RecommendationStrategyStagedActivationSmokeReport:
    return RecommendationStrategyStagedActivationSmokeReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_recommendation_strategy_staged_activation_smoke_report(
        load_recommendation_strategy_promotion_gate_report(args.strategy_gate_report),
        rule_profile=_load_json(args.staged_rule_profile),
        options=_options_from_args(args),
    )
    if args.staged_profile_output_path is not None and report.staged_activation_ready:
        args.staged_profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.staged_profile_output_path.write_text(
            f"{dumps(report.staged_profile_json, indent=2)}\n",
            encoding="utf-8",
        )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(
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
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    strategy_gate: RecommendationStrategyPromotionGateReport,
    *,
    rule_profile: Mapping[str, object],
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    allowed_competition_ids: Sequence[str],
    excluded_competition_ids: Sequence[str],
    public_contract_json: Mapping[str, object],
    options: RecommendationStrategyStagedActivationSmokeOptions,
) -> list[RecommendationStrategyStagedActivationSmokeCheck]:
    return [
        _equality_check(
            name="strategy_gate_status",
            actual=strategy_gate.status,
            expected="ready",
            enabled=options.require_strategy_gate_ready,
            detail="strategy gate must be ready before staged activation smoke passes",
        ),
        _boolean_check(
            name="strategy_gate_ready",
            actual=strategy_gate.strategy_gate_ready,
            expected=True,
            enabled=options.require_strategy_gate_ready,
            detail="strategy gate ready flag must be true",
        ),
        _boolean_check(
            name="profile_dry_run_only",
            actual=bool(rule_profile.get("dry_run_only")),
            expected=True,
            enabled=options.require_profile_dry_run_only,
            detail="staged smoke must consume a dry-run-only profile",
        ),
        _boolean_check(
            name="profile_promotion_review_allowed",
            actual=bool(rule_profile.get("promotion_review_allowed")),
            expected=True,
            enabled=options.require_profile_promotion_review_allowed,
            detail="source review profile must have passed governed review",
        ),
        _equality_check(
            name="profile_review_status",
            actual=str(rule_profile.get("review_status", "")),
            expected="promotion_review_ready",
            enabled=options.require_profile_review_ready,
            detail="source review profile should be promotion-review ready",
        ),
        _boolean_check(
            name="no_default_profile_write_requested",
            actual=True,
            expected=True,
            enabled=options.require_no_default_profile_write,
            detail="staged smoke must not request default profile writes",
        ),
        _boolean_check(
            name="default_profile_not_written",
            actual=True,
            expected=True,
            enabled=options.require_no_default_profile_write,
            detail="staged smoke must not write default profile",
        ),
        _boolean_check(
            name="production_recommendation_allowed_false",
            actual=not strategy_gate.production_recommendation_allowed
            and not bool(rule_profile.get("production_recommendation_allowed")),
            expected=True,
            enabled=options.require_no_production_allowed,
            detail="staged smoke must not allow production recommendations",
        ),
        _boolean_check(
            name="no_production_recommendation_change",
            actual=not strategy_gate.production_recommendation_changed
            and not bool(rule_profile.get("production_recommendation_changed")),
            expected=True,
            enabled=options.require_no_production_change,
            detail="staged smoke must not change production recommendations",
        ),
        _boolean_check(
            name="no_public_response_change",
            actual=not strategy_gate.public_response_changed
            and not bool(rule_profile.get("public_response_changed")),
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="staged smoke must not change public responses",
        ),
        _boolean_check(
            name="public_contract_unchanged",
            actual=not bool(public_contract_json.get("public_response_changed"))
            and not bool(public_contract_json.get("ordinary_user_path_changed"))
            and not bool(public_contract_json.get("internal_strategy_details_exposed")),
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="public contract should remain unchanged",
        ),
        _minimum_check(
            name="selected_rule_count",
            actual=len(selected_rules),
            threshold=options.min_rule_count,
            detail="staged smoke must select enough internal rules",
        ),
        _minimum_check(
            name="allowed_competition_count",
            actual=len(allowed_competition_ids),
            threshold=options.min_allowed_competition_count,
            detail="staged smoke should retain enough scoped competitions",
        ),
        _boolean_check(
            name="allowed_excluded_competition_disjoint",
            actual=not bool(set(allowed_competition_ids) & set(excluded_competition_ids)),
            expected=True,
            enabled=options.require_no_allowed_excluded_overlap,
            detail="allowed and excluded competition scopes must not overlap",
        ),
        _boolean_check(
            name="rules_enabled_for_staging",
            actual=all(rule.proposed_production_enabled for rule in selected_rules),
            expected=True,
            enabled=options.require_rules_enabled,
            detail="selected rules should be explicitly enabled for staged review",
        ),
        _boolean_check(
            name="rule_no_production_recommendation_change",
            actual=not any(
                rule.production_recommendation_changed for rule in selected_rules
            ),
            expected=True,
            enabled=options.require_rule_no_production_change,
            detail="selected rules must not carry production changes",
        ),
        _boolean_check(
            name="rule_no_harm_constraints",
            actual=all(_rule_has_no_harm_constraints(rule) for rule in selected_rules),
            expected=True,
            enabled=options.require_no_harm_constraints,
            detail="selected rules must keep no-harm constraints",
        ),
        _boolean_check(
            name="exclude_original_hit_harm",
            actual=all(
                bool(rule.constraints_json.get("exclude_original_hit_harm"))
                for rule in selected_rules
            ),
            expected=True,
            enabled=options.require_exclude_original_hit_harm,
            detail="selected rules must keep original-hit harm guard",
        ),
        _boolean_check(
            name="source_candidate_match",
            actual=_source_candidate_match(strategy_gate, selected_rules),
            expected=True,
            enabled=options.require_source_candidate_match,
            detail="selected rules must match the strategy gate candidate lineage",
        ),
        _boolean_check(
            name="source_chain_complete",
            actual=all(_evidence_source_chain_complete(item) for item in strategy_gate.evidence),
            expected=True,
            enabled=options.require_source_chain_complete,
            detail="strategy gate evidence must keep source chain complete",
        ),
        _minimum_check(
            name="total_final_answer_count",
            actual=strategy_gate.total_final_answer_count,
            threshold=options.min_total_final_answer_count,
            detail="strategy gate must cover enough final answers",
        ),
        _minimum_check(
            name="total_changed_final_answer_count",
            actual=strategy_gate.total_changed_final_answer_count,
            threshold=options.min_total_changed_final_answer_count,
            detail="strategy gate must affect enough final answers",
        ),
        _minimum_check(
            name="total_final_answer_hit_delta_count",
            actual=strategy_gate.total_final_answer_hit_delta_count,
            threshold=options.min_total_final_answer_hit_delta_count,
            detail="final-answer hit count should not regress",
        ),
        _minimum_check(
            name="total_profit_loss_delta",
            actual=strategy_gate.total_profit_loss_delta,
            threshold=options.min_total_profit_loss_delta,
            detail="P/L should not regress",
        ),
        _optional_minimum_check(
            name="minimum_roi_delta",
            actual=strategy_gate.minimum_roi_delta,
            threshold=options.min_minimum_roi_delta,
            detail="minimum ROI delta should not regress",
        ),
        _maximum_check(
            name="total_harm_count_vs_original",
            actual=strategy_gate.total_harm_count_vs_original,
            threshold=options.max_total_harm_count_vs_original,
            detail="strategy gate should not carry original-answer harm",
        ),
        _maximum_check(
            name="total_final_hit_harm_count_vs_original",
            actual=strategy_gate.total_final_hit_harm_count_vs_original,
            threshold=options.max_total_final_hit_harm_count_vs_original,
            detail="strategy gate should not turn original hits into misses",
        ),
        _maximum_check(
            name="total_profit_loss_harm_count_vs_original",
            actual=strategy_gate.total_profit_loss_harm_count_vs_original,
            threshold=options.max_total_profit_loss_harm_count_vs_original,
            detail="strategy gate should not reduce original final-answer P/L",
        ),
        _minimum_check(
            name="minimum_active_surface_count",
            actual=strategy_gate.minimum_active_surface_count,
            threshold=options.min_minimum_active_surface_count,
            detail="strategy gate should retain enough active surfaces",
        ),
        _maximum_check(
            name="total_failed_surface_count",
            actual=strategy_gate.total_failed_surface_count,
            threshold=options.max_total_failed_surface_count,
            detail="strategy gate should not carry failed surfaces",
        ),
        _minimum_check(
            name="minimum_active_competition_fold_count",
            actual=strategy_gate.minimum_active_competition_fold_count,
            threshold=options.min_minimum_active_competition_fold_count,
            detail="strategy gate should retain enough competition folds",
        ),
        _minimum_check(
            name="minimum_active_season_fold_count",
            actual=strategy_gate.minimum_active_season_fold_count,
            threshold=options.min_minimum_active_season_fold_count,
            detail="strategy gate should retain enough season folds",
        ),
        _minimum_check(
            name="minimum_active_rolling_fold_count",
            actual=strategy_gate.minimum_active_rolling_fold_count,
            threshold=options.min_minimum_active_rolling_fold_count,
            detail="strategy gate should retain enough rolling folds",
        ),
        _maximum_check(
            name="total_failed_fold_count",
            actual=strategy_gate.total_failed_fold_count,
            threshold=options.max_total_failed_fold_count,
            detail="strategy gate should not carry failed folds",
        ),
    ]


def _staged_profile_json(
    *,
    rule_profile: Mapping[str, object],
    rule_set: ShortOddsRuntimeRuleSet,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    strategy_gate_report: RecommendationStrategyPromotionGateReport,
    options: RecommendationStrategyStagedActivationSmokeOptions,
) -> dict[str, object]:
    return {
        "profile_version": options.staged_profile_version,
        "calculation_basis": "recommendation_strategy_staged_activation_smoke_v3_1",
        "staged_only": True,
        "dry_run_only": True,
        "default_profile_write_requested": False,
        "default_profile_written": False,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "base_rule_profile_version": rule_set.profile_version,
        "source_strategy_gate_key": strategy_gate_report.gate_key,
        "source_strategy_key": strategy_gate_report.strategy_key,
        "source_gate_id": strategy_gate_report.gate_id,
        "source_promotion_review_report_keys": [
            item.report_key for item in strategy_gate_report.evidence
        ],
        "selected_candidate_keys": strategy_gate_report.selected_candidate_keys,
        "shadow_replay_enabled": bool(rule_profile.get("shadow_replay_enabled")),
        "short_odds_replacement_rules": [
            rule.model_dump(mode="json") for rule in selected_rules
        ],
        "source_profile_json": {
            "profile_version": rule_profile.get("profile_version"),
            "review_id": rule_profile.get("review_id"),
            "review_status": rule_profile.get("review_status"),
            "promotion_review_allowed": rule_profile.get("promotion_review_allowed"),
        },
        "notes": [
            *(_string_list(rule_profile.get("notes"))),
            "staged_activation_smoke_only",
            "not_written_to_default_profile",
            "not_visible_to_public_recommendations",
        ],
    }


def _rule_set_from_profile(profile: Mapping[str, object]) -> ShortOddsRuntimeRuleSet:
    raw_rules = _mapping_list(profile.get("short_odds_replacement_rules"))
    if not raw_rules:
        raw_rules = _mapping_list(profile.get("rules"))
    return ShortOddsRuntimeRuleSet(
        profile_version=_string(profile.get("profile_version")) or "unknown",
        calculation_basis=(
            _string(profile.get("calculation_basis"))
            or "recommendation_strategy_staged_activation_smoke_loader_v3_1"
        ),
        shadow_replay_enabled=bool(profile.get("shadow_replay_enabled")),
        rules=[
            ShortOddsRuntimeReplacementRule.model_validate(rule)
            for rule in raw_rules
        ],
        notes=_string_list(profile.get("notes")),
    )


def _selected_rules(
    rules: Sequence[ShortOddsRuntimeReplacementRule],
    *,
    options: RecommendationStrategyStagedActivationSmokeOptions,
) -> list[ShortOddsRuntimeReplacementRule]:
    if not options.require_rules_enabled:
        return list(rules)
    return [
        rule
        for rule in rules
        if rule.proposed_production_enabled and not rule.production_recommendation_changed
    ]


def _status(
    strategy_gate: RecommendationStrategyPromotionGateReport,
    blockers: Sequence[str],
) -> RecommendationStrategyStagedActivationSmokeStatus:
    hard_blockers = {
        "strategy_gate_status",
        "strategy_gate_ready",
        "profile_dry_run_only",
        "production_recommendation_allowed_false",
        "no_production_recommendation_change",
        "no_public_response_change",
        "default_profile_not_written",
        "selected_rule_count",
    }
    if strategy_gate.status == "blocked" or any(name in hard_blockers for name in blockers):
        return "blocked"
    if blockers:
        return "staged_activation_watchlist"
    return "staged_activation_ready"


def _rule_has_no_harm_constraints(rule: ShortOddsRuntimeReplacementRule) -> bool:
    constraints = rule.constraints_json
    return (
        constraints.get("max_harm_count_vs_original") == 0
        and constraints.get("max_final_hit_harm_count_vs_original") == 0
        and constraints.get("max_profit_loss_harm_count_vs_original") == 0
    )


def _source_candidate_match(
    strategy_gate: RecommendationStrategyPromotionGateReport,
    rules: Sequence[ShortOddsRuntimeReplacementRule],
) -> bool:
    expected = set(strategy_gate.selected_candidate_keys)
    if not expected:
        return False
    actual = {
        value
        for rule in rules
        for value in [_string(rule.evidence_json.get("candidate_key"))]
        if value
    }
    return bool(actual) and actual <= expected


def _evidence_source_chain_complete(item: object) -> bool:
    return all(
        bool(getattr(item, name, None))
        for name in (
            "source_runtime_dry_run_report_key",
            "source_grid_report_key",
            "source_surface_replay_report_key",
            "source_admission_report_key",
            "generated_runtime_shadow_replay_report_key",
        )
    )


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> RecommendationStrategyStagedActivationSmokeCheck:
    if not enabled:
        return RecommendationStrategyStagedActivationSmokeCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return RecommendationStrategyStagedActivationSmokeCheck(
        name=name,
        status="passed" if actual == expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _equality_check(
    *,
    name: str,
    actual: str,
    expected: str,
    detail: str,
    enabled: bool = True,
) -> RecommendationStrategyStagedActivationSmokeCheck:
    if not enabled:
        return RecommendationStrategyStagedActivationSmokeCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return RecommendationStrategyStagedActivationSmokeCheck(
        name=name,
        status="passed" if actual == expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> RecommendationStrategyStagedActivationSmokeCheck:
    return RecommendationStrategyStagedActivationSmokeCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: int | float | None,
    threshold: int | float | None,
    detail: str,
) -> RecommendationStrategyStagedActivationSmokeCheck:
    if threshold is None:
        return RecommendationStrategyStagedActivationSmokeCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=None,
            detail=f"{detail} (disabled)",
        )
    if actual is None:
        return RecommendationStrategyStagedActivationSmokeCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return _minimum_check(
        name=name,
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> RecommendationStrategyStagedActivationSmokeCheck:
    return RecommendationStrategyStagedActivationSmokeCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _load_json(path: Path | str) -> dict[str, object]:
    payload = loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str)]


def _unique(values: Iterable[str | None]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run a staged-only activation smoke for a governed recommendation "
            "strategy without writing default profiles."
        )
    )
    parser.add_argument("--strategy-gate-report", type=Path, required=True)
    parser.add_argument("--staged-rule-profile", type=Path, required=True)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument("--staged-profile-output-path", type=Path)
    parser.add_argument(
        "--staged-profile-version",
        default="v3_1_probability_preserving_replacement_staged_activation_smoke",
    )
    parser.add_argument("--min-rule-count", type=int, default=1)
    parser.add_argument("--min-allowed-competition-count", type=int, default=5)
    parser.add_argument("--min-total-final-answer-count", type=int, default=30)
    parser.add_argument("--min-total-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-total-final-answer-hit-delta-count", type=int, default=0)
    parser.add_argument("--min-total-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-minimum-roi-delta", type=float, default=0.0)
    parser.add_argument("--allow-missing-roi-delta", action="store_true")
    parser.add_argument("--max-total-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--max-total-final-hit-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-total-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument("--min-minimum-active-surface-count", type=int, default=1)
    parser.add_argument("--max-total-failed-surface-count", type=int, default=0)
    parser.add_argument(
        "--min-minimum-active-competition-fold-count",
        type=int,
        default=1,
    )
    parser.add_argument("--min-minimum-active-season-fold-count", type=int, default=1)
    parser.add_argument("--min-minimum-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--max-total-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-non-ready-strategy-gate", action="store_true")
    parser.add_argument("--allow-non-dry-run-profile", action="store_true")
    parser.add_argument("--allow-non-review-profile", action="store_true")
    parser.add_argument("--allow-default-profile-write", action="store_true")
    parser.add_argument("--allow-production-recommendation", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-competition-scope-overlap", action="store_true")
    parser.add_argument("--include-disabled-rules", action="store_true")
    parser.add_argument("--allow-rule-production-change", action="store_true")
    parser.add_argument("--allow-harm-constraints", action="store_true")
    parser.add_argument("--allow-missing-original-hit-harm-guard", action="store_true")
    parser.add_argument("--allow-candidate-mismatch", action="store_true")
    parser.add_argument("--allow-incomplete-source-chain", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> RecommendationStrategyStagedActivationSmokeOptions:
    return RecommendationStrategyStagedActivationSmokeOptions(
        staged_profile_version=args.staged_profile_version,
        min_rule_count=args.min_rule_count,
        min_allowed_competition_count=args.min_allowed_competition_count,
        min_total_final_answer_count=args.min_total_final_answer_count,
        min_total_changed_final_answer_count=args.min_total_changed_final_answer_count,
        min_total_final_answer_hit_delta_count=(
            args.min_total_final_answer_hit_delta_count
        ),
        min_total_profit_loss_delta=args.min_total_profit_loss_delta,
        min_minimum_roi_delta=(
            None if args.allow_missing_roi_delta else args.min_minimum_roi_delta
        ),
        max_total_harm_count_vs_original=args.max_total_harm_count_vs_original,
        max_total_final_hit_harm_count_vs_original=(
            args.max_total_final_hit_harm_count_vs_original
        ),
        max_total_profit_loss_harm_count_vs_original=(
            args.max_total_profit_loss_harm_count_vs_original
        ),
        min_minimum_active_surface_count=args.min_minimum_active_surface_count,
        max_total_failed_surface_count=args.max_total_failed_surface_count,
        min_minimum_active_competition_fold_count=(
            args.min_minimum_active_competition_fold_count
        ),
        min_minimum_active_season_fold_count=args.min_minimum_active_season_fold_count,
        min_minimum_active_rolling_fold_count=(
            args.min_minimum_active_rolling_fold_count
        ),
        max_total_failed_fold_count=args.max_total_failed_fold_count,
        require_strategy_gate_ready=not args.allow_non_ready_strategy_gate,
        require_profile_dry_run_only=not args.allow_non_dry_run_profile,
        require_profile_promotion_review_allowed=not args.allow_non_review_profile,
        require_profile_review_ready=not args.allow_non_review_profile,
        require_no_default_profile_write=not args.allow_default_profile_write,
        require_no_production_allowed=not args.allow_production_recommendation,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
        require_no_allowed_excluded_overlap=not args.allow_competition_scope_overlap,
        require_rules_enabled=not args.include_disabled_rules,
        require_rule_no_production_change=not args.allow_rule_production_change,
        require_no_harm_constraints=not args.allow_harm_constraints,
        require_exclude_original_hit_harm=not args.allow_missing_original_hit_harm_guard,
        require_source_candidate_match=not args.allow_candidate_mismatch,
        require_source_chain_complete=not args.allow_incomplete_source_chain,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[RecommendationStrategyStagedActivationSmokeCheck],
    staged_profile: Mapping[str, object],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "checks": [check.model_dump(mode="json") for check in checks],
            "staged_profile": staged_profile,
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"recommendation_strategy_staged_activation_smoke:{digest}"
