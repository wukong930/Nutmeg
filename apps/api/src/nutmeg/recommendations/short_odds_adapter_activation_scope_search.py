from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from itertools import combinations
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditReport,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)
from nutmeg.recommendations.replacement_short_odds_rolling_admission import (
    HistoricalShortOddsRollingAdmissionOptions,
    HistoricalShortOddsRollingAdmissionReport,
    build_historical_short_odds_rolling_admission_report,
)
from nutmeg.recommendations.short_odds_adapter_activation_grid import (
    ShortOddsAdapterActivationGridCandidate,
    ShortOddsAdapterActivationGridReport,
    load_short_odds_adapter_activation_grid_report,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
    load_short_odds_runtime_rule_set,
)

type ShortOddsAdapterActivationScopeSearchStatus = Literal[
    "accepted_scope_found",
    "shadow_only_scopes",
    "no_admitted_scope",
    "no_scope_candidates",
    "no_rules",
]
type ShortOddsAdapterActivationScopeCandidateStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]


class ShortOddsAdapterActivationScopeSearchOptions(BaseModel):
    candidate_keys: tuple[str, ...] = ()
    accepted_candidates_only: bool = True
    max_source_candidate_count: int = Field(default=5, ge=1, le=100)
    min_scope_competition_count: int = Field(default=1, ge=1)
    max_scope_competition_count: int = Field(default=4, ge=1)
    include_full_probe_scope: bool = True
    max_scope_candidate_count: int = Field(default=200, ge=1, le=5000)
    min_overall_final_answer_count: int = Field(default=50, ge=1)
    min_overall_changed_final_answer_count: int = Field(default=2, ge=0)
    min_overall_final_answer_hit_rate_delta: float = 0.0
    min_overall_roi_delta: float = 0.0
    min_overall_profit_loss_delta: float = 0.0
    max_overall_harm_count_vs_original: int = Field(default=0, ge=0)
    max_overall_final_hit_harm_count_vs_original: int | None = Field(default=0, ge=0)
    max_overall_profit_loss_harm_count_vs_original: int | None = Field(default=0, ge=0)
    min_overall_average_hit_probability_delta_vs_original: float = -0.05
    min_fold_final_answer_count: int = Field(default=1, ge=1)
    min_fold_changed_final_answer_count: int = Field(default=1, ge=0)
    min_fold_final_answer_hit_rate_delta: float = 0.0
    min_fold_roi_delta: float = 0.0
    min_fold_profit_loss_delta: float = 0.0
    max_fold_harm_count_vs_original: int = Field(default=0, ge=0)
    max_fold_final_hit_harm_count_vs_original: int | None = Field(default=0, ge=0)
    max_fold_profit_loss_harm_count_vs_original: int | None = Field(default=0, ge=0)
    min_fold_average_hit_probability_delta_vs_original: float = -0.05
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_fold_count: int = Field(default=2, ge=0)
    min_active_rolling_fold_count: int = Field(default=2, ge=0)
    rolling_window_final_answer_count: int = Field(default=12, ge=1)
    rolling_window_step: int = Field(default=6, ge=1)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_no_production_change: bool = True
    max_report_folds: int = Field(default=120, ge=1, le=500)
    max_report_scope_candidates: int = Field(default=40, ge=1, le=500)


class ShortOddsAdapterActivationScopeCandidate(BaseModel):
    scope_key: str
    status: ShortOddsAdapterActivationScopeCandidateStatus
    source_candidate_key: str
    source_candidate_status: str
    scope_competition_ids: list[str] = Field(default_factory=list)
    scope_competition_count: int = Field(ge=0)
    production_candidate_allowed: bool
    shadow_allowed: bool
    min_replacement_probability: float
    max_replacement_decimal_odds: float
    min_candidate_hit_probability_delta_vs_model_top: float
    min_candidate_hit_probability_delta_vs_original: float
    overall_runtime_shadow_report_key: str
    rolling_admission_report_key: str
    rolling_admission_status: str
    overall_final_answer_count: int = Field(ge=0)
    overall_changed_final_answer_count: int = Field(ge=0)
    overall_final_answer_hit_rate_delta: float | None = None
    overall_roi_delta: float | None = None
    overall_profit_loss_delta: float
    overall_harm_count_vs_original: int = Field(ge=0)
    overall_final_hit_harm_count_vs_original: int = Field(ge=0)
    overall_profit_loss_harm_count_vs_original: int = Field(ge=0)
    overall_average_hit_probability_delta_vs_original: float | None = None
    rolling_active_competition_fold_count: int = Field(ge=0)
    rolling_active_season_fold_count: int = Field(ge=0)
    rolling_active_rolling_fold_count: int = Field(ge=0)
    rolling_failed_fold_count: int = Field(ge=0)
    rolling_failed_checks: list[str] = Field(default_factory=list)
    rolling_failed_fold_reason_counts: dict[str, int] = Field(default_factory=dict)
    rolling_failed_fold_ids: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    summary_json: dict[str, object] = Field(default_factory=dict)


class ShortOddsAdapterActivationScopeSearchReport(BaseModel):
    report_key: str
    status: ShortOddsAdapterActivationScopeSearchStatus
    accepted_scope_found: bool
    shadow_allowed: bool
    source_grid_report_key: str
    source_audit_report_key: str
    source_rule_profile_version: str
    selected_source_candidate_count: int = Field(ge=0)
    scope_candidate_count: int = Field(ge=0)
    accepted_scope_count: int = Field(ge=0)
    shadow_only_scope_count: int = Field(ge=0)
    rejected_scope_count: int = Field(ge=0)
    scope_candidate_limit_reached: bool = False
    best_scope_key: str | None = None
    best_scope: ShortOddsAdapterActivationScopeCandidate | None = None
    scopes: list[ShortOddsAdapterActivationScopeCandidate] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_short_odds_adapter_activation_scope_search_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    grid_report: ShortOddsAdapterActivationGridReport,
    options: ShortOddsAdapterActivationScopeSearchOptions | None = None,
) -> ShortOddsAdapterActivationScopeSearchReport:
    resolved_options = options or ShortOddsAdapterActivationScopeSearchOptions()
    source_candidates = _selected_source_candidates(
        grid_report,
        options=resolved_options,
    )
    selected_rules = rule_set.selected_rules(
        rule_ids=_selected_rule_ids(source_candidates),
        require_proposed_production_enabled=True,
        require_no_production_change=True,
    )
    warnings = [*grid_report.warnings, *audit_report.warnings]
    if not source_candidates:
        warnings.append("short_odds_adapter_activation_scope_search:no_candidates")
        return _report(
            status="no_scope_candidates",
            audit_report=audit_report,
            rule_set=rule_set,
            grid_report=grid_report,
            source_candidates=source_candidates,
            scopes=[],
            scope_candidate_limit_reached=False,
            warnings=warnings,
            options=resolved_options,
        )
    if not selected_rules:
        warnings.append("short_odds_adapter_activation_scope_search:no_enabled_rules")
        return _report(
            status="no_rules",
            audit_report=audit_report,
            rule_set=rule_set,
            grid_report=grid_report,
            source_candidates=source_candidates,
            scopes=[],
            scope_candidate_limit_reached=False,
            warnings=warnings,
            options=resolved_options,
        )

    scopes: list[ShortOddsAdapterActivationScopeCandidate] = []
    scope_candidate_limit_reached = False
    for source_candidate in source_candidates:
        for scope_competition_ids in _scope_competition_sets(
            source_candidate,
            options=resolved_options,
        ):
            if len(scopes) >= resolved_options.max_scope_candidate_count:
                scope_candidate_limit_reached = True
                warnings.append(
                    "short_odds_adapter_activation_scope_search:"
                    "scope_candidate_limit_reached"
                )
                break
            scopes.append(
                _scope_candidate(
                    source_candidate,
                    scope_competition_ids=scope_competition_ids,
                    audit_report=audit_report,
                    rule_set=rule_set,
                    selected_rules=selected_rules,
                    options=resolved_options,
                )
            )
        if scope_candidate_limit_reached:
            break

    sorted_scopes = sorted(scopes, key=_scope_sort_key, reverse=True)
    if any(scope.status == "accepted" for scope in sorted_scopes):
        status: ShortOddsAdapterActivationScopeSearchStatus = "accepted_scope_found"
    elif any(scope.shadow_allowed for scope in sorted_scopes):
        status = "shadow_only_scopes"
    else:
        status = "no_admitted_scope"
    return _report(
        status=status,
        audit_report=audit_report,
        rule_set=rule_set,
        grid_report=grid_report,
        source_candidates=source_candidates,
        scopes=sorted_scopes,
        scope_candidate_limit_reached=scope_candidate_limit_reached,
        warnings=warnings,
        options=resolved_options,
    )


def load_short_odds_adapter_activation_scope_search_report(
    path: Path | str,
) -> ShortOddsAdapterActivationScopeSearchReport:
    return ShortOddsAdapterActivationScopeSearchReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_short_odds_adapter_activation_scope_search_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        rule_set=load_short_odds_runtime_rule_set(
            args.rule_profile,
            enable_shadow_replay=True,
        ),
        grid_report=load_short_odds_adapter_activation_grid_report(args.grid_report),
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
        args.require_accepted_scope
        and not report.accepted_scope_found
        and not args.no_fail_process
    ):
        raise SystemExit(1)


def _selected_source_candidates(
    grid_report: ShortOddsAdapterActivationGridReport,
    *,
    options: ShortOddsAdapterActivationScopeSearchOptions,
) -> list[ShortOddsAdapterActivationGridCandidate]:
    by_key: dict[str, ShortOddsAdapterActivationGridCandidate] = {}
    for candidate in [grid_report.best_candidate, *grid_report.candidates]:
        if candidate is None:
            continue
        by_key.setdefault(candidate.candidate_key, candidate)
    selected = list(by_key.values())
    if options.accepted_candidates_only:
        selected = [candidate for candidate in selected if candidate.accepted]
    if options.candidate_keys:
        candidate_keys = set(options.candidate_keys)
        selected = [
            candidate for candidate in selected if candidate.candidate_key in candidate_keys
        ]
    return selected[: options.max_source_candidate_count]


def _selected_rule_ids(
    candidates: Sequence[ShortOddsAdapterActivationGridCandidate],
) -> tuple[str, ...]:
    rule_ids: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        for rule_id in candidate.rule_ids:
            if rule_id in seen:
                continue
            seen.add(rule_id)
            rule_ids.append(rule_id)
    return tuple(rule_ids)


def _scope_competition_sets(
    candidate: ShortOddsAdapterActivationGridCandidate,
    *,
    options: ShortOddsAdapterActivationScopeSearchOptions,
) -> list[tuple[str, ...]]:
    source_competition_ids = tuple(
        sorted(candidate.changed_competition_counts or candidate.probe_competition_ids)
    )
    scopes: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    max_size = min(options.max_scope_competition_count, len(source_competition_ids))
    for size in range(options.min_scope_competition_count, max_size + 1):
        for scope in combinations(source_competition_ids, size):
            if scope in seen:
                continue
            seen.add(scope)
            scopes.append(scope)
    if options.include_full_probe_scope:
        full_scope = tuple(sorted(candidate.probe_competition_ids))
        if full_scope and full_scope not in seen:
            scopes.append(full_scope)
    return scopes


def _scope_candidate(
    source_candidate: ShortOddsAdapterActivationGridCandidate,
    *,
    scope_competition_ids: Sequence[str],
    audit_report: HistoricalCandidateMarginalAuditReport,
    rule_set: ShortOddsRuntimeRuleSet,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    options: ShortOddsAdapterActivationScopeSearchOptions,
) -> ShortOddsAdapterActivationScopeCandidate:
    candidate_rules = [
        _candidate_rule(
            rule,
            source_candidate=source_candidate,
            scope_competition_ids=scope_competition_ids,
        )
        for rule in selected_rules
        if not source_candidate.rule_ids or rule.rule_id in source_candidate.rule_ids
    ]
    rolling_report = build_historical_short_odds_rolling_admission_report(
        audit_report,
        rule_set=rule_set.model_copy(
            update={
                "shadow_replay_enabled": True,
                "rules": _replace_selected_rules(rule_set.rules, candidate_rules),
            }
        ),
        options=_rolling_options(source_candidate, options=options),
    )
    failed_checks = [
        check.name for check in rolling_report.checks if check.status == "failed"
    ]
    if rolling_report.production_recommendation_allowed:
        status: ShortOddsAdapterActivationScopeCandidateStatus = "accepted"
    elif rolling_report.shadow_allowed:
        status = "shadow_only"
    else:
        status = "rejected"
    summary = _scope_summary(
        source_candidate,
        rolling_report=rolling_report,
        scope_competition_ids=scope_competition_ids,
        status=status,
        failed_checks=failed_checks,
    )
    scope_key = _digest_key("short_odds_adapter_activation_scope_candidate", summary)
    return ShortOddsAdapterActivationScopeCandidate(
        scope_key=scope_key,
        status=status,
        source_candidate_key=source_candidate.candidate_key,
        source_candidate_status=source_candidate.status,
        scope_competition_ids=list(scope_competition_ids),
        scope_competition_count=len(scope_competition_ids),
        production_candidate_allowed=rolling_report.production_recommendation_allowed,
        shadow_allowed=rolling_report.shadow_allowed,
        min_replacement_probability=source_candidate.min_replacement_probability,
        max_replacement_decimal_odds=source_candidate.max_replacement_decimal_odds,
        min_candidate_hit_probability_delta_vs_model_top=(
            source_candidate.min_candidate_hit_probability_delta_vs_model_top
        ),
        min_candidate_hit_probability_delta_vs_original=(
            source_candidate.min_candidate_hit_probability_delta_vs_original
        ),
        overall_runtime_shadow_report_key=str(
            rolling_report.summary_json.get("overall_runtime_shadow_report_key", "")
        ),
        rolling_admission_report_key=rolling_report.report_key,
        rolling_admission_status=rolling_report.status,
        overall_final_answer_count=_summary_int(
            rolling_report,
            "overall_final_answer_count",
        ),
        overall_changed_final_answer_count=_summary_int(
            rolling_report,
            "overall_changed_final_answer_count",
        ),
        overall_final_answer_hit_rate_delta=_summary_optional_float(
            rolling_report,
            "overall_final_answer_hit_rate_delta",
        ),
        overall_roi_delta=_summary_optional_float(rolling_report, "overall_roi_delta"),
        overall_profit_loss_delta=_summary_float(
            rolling_report,
            "overall_profit_loss_delta",
        ),
        overall_harm_count_vs_original=_summary_int(
            rolling_report,
            "overall_harm_count_vs_original",
        ),
        overall_final_hit_harm_count_vs_original=_summary_int(
            rolling_report,
            "overall_final_hit_harm_count_vs_original",
        ),
        overall_profit_loss_harm_count_vs_original=_summary_int(
            rolling_report,
            "overall_profit_loss_harm_count_vs_original",
        ),
        overall_average_hit_probability_delta_vs_original=_summary_optional_float(
            rolling_report,
            "overall_average_hit_probability_delta_vs_original",
        ),
        rolling_active_competition_fold_count=(
            rolling_report.active_competition_fold_count
        ),
        rolling_active_season_fold_count=rolling_report.active_season_fold_count,
        rolling_active_rolling_fold_count=rolling_report.active_rolling_fold_count,
        rolling_failed_fold_count=rolling_report.failed_fold_count,
        rolling_failed_checks=failed_checks,
        rolling_failed_fold_reason_counts=_failed_fold_reason_counts(rolling_report),
        rolling_failed_fold_ids=_failed_fold_ids(rolling_report),
        production_recommendation_changed=_production_changed(rolling_report),
        public_response_changed=_public_response_changed(rolling_report),
        summary_json={**summary, "scope_key": scope_key},
    )


def _candidate_rule(
    rule: ShortOddsRuntimeReplacementRule,
    *,
    source_candidate: ShortOddsAdapterActivationGridCandidate,
    scope_competition_ids: Sequence[str],
) -> ShortOddsRuntimeReplacementRule:
    constraints: dict[str, object] = dict(
        rule.constraints().model_dump(mode="json", exclude_none=True)
    )
    constraints.update(
        {
            "min_replacement_probability": (
                source_candidate.min_replacement_probability
            ),
            "max_replacement_decimal_odds": (
                source_candidate.max_replacement_decimal_odds
            ),
            "min_candidate_hit_probability_delta_vs_model_top": (
                source_candidate.min_candidate_hit_probability_delta_vs_model_top
            ),
            "max_candidate_hit_probability_delta_vs_model_top": (
                source_candidate.max_candidate_hit_probability_delta_vs_model_top
            ),
            "min_decimal_odds_delta_vs_model_top": (
                source_candidate.min_decimal_odds_delta_vs_model_top
            ),
            "min_candidate_hit_probability_delta_vs_original": (
                source_candidate.min_candidate_hit_probability_delta_vs_original
            ),
        }
    )
    return rule.model_copy(
        update={
            "allowed_competition_ids": list(scope_competition_ids),
            "constraints_json": constraints,
        }
    )


def _replace_selected_rules(
    rules: Sequence[ShortOddsRuntimeReplacementRule],
    replacements: Sequence[ShortOddsRuntimeReplacementRule],
) -> list[ShortOddsRuntimeReplacementRule]:
    by_rule_id = {rule.rule_id: rule for rule in replacements}
    return [by_rule_id.get(rule.rule_id, rule) for rule in rules]


def _rolling_options(
    source_candidate: ShortOddsAdapterActivationGridCandidate,
    *,
    options: ShortOddsAdapterActivationScopeSearchOptions,
) -> HistoricalShortOddsRollingAdmissionOptions:
    return HistoricalShortOddsRollingAdmissionOptions(
        rule_ids=tuple(source_candidate.rule_ids),
        min_overall_final_answer_count=options.min_overall_final_answer_count,
        min_overall_changed_final_answer_count=(
            options.min_overall_changed_final_answer_count
        ),
        min_overall_final_answer_hit_rate_delta=(
            options.min_overall_final_answer_hit_rate_delta
        ),
        min_overall_roi_delta=options.min_overall_roi_delta,
        min_overall_profit_loss_delta=options.min_overall_profit_loss_delta,
        max_overall_harm_count_vs_original=options.max_overall_harm_count_vs_original,
        max_overall_final_hit_harm_count_vs_original=(
            options.max_overall_final_hit_harm_count_vs_original
        ),
        max_overall_profit_loss_harm_count_vs_original=(
            options.max_overall_profit_loss_harm_count_vs_original
        ),
        min_overall_average_hit_probability_delta_vs_original=(
            options.min_overall_average_hit_probability_delta_vs_original
        ),
        min_fold_final_answer_count=options.min_fold_final_answer_count,
        min_fold_changed_final_answer_count=options.min_fold_changed_final_answer_count,
        min_fold_final_answer_hit_rate_delta=(
            options.min_fold_final_answer_hit_rate_delta
        ),
        min_fold_roi_delta=options.min_fold_roi_delta,
        min_fold_profit_loss_delta=options.min_fold_profit_loss_delta,
        max_fold_harm_count_vs_original=options.max_fold_harm_count_vs_original,
        max_fold_final_hit_harm_count_vs_original=(
            options.max_fold_final_hit_harm_count_vs_original
        ),
        max_fold_profit_loss_harm_count_vs_original=(
            options.max_fold_profit_loss_harm_count_vs_original
        ),
        min_fold_average_hit_probability_delta_vs_original=(
            options.min_fold_average_hit_probability_delta_vs_original
        ),
        min_active_competition_fold_count=options.min_active_competition_fold_count,
        min_active_season_fold_count=options.min_active_season_fold_count,
        min_active_rolling_fold_count=options.min_active_rolling_fold_count,
        rolling_window_final_answer_count=options.rolling_window_final_answer_count,
        rolling_window_step=options.rolling_window_step,
        max_failed_fold_count=options.max_failed_fold_count,
        require_no_production_change=options.require_no_production_change,
        max_report_folds=options.max_report_folds,
    )


def _report(
    *,
    status: ShortOddsAdapterActivationScopeSearchStatus,
    audit_report: HistoricalCandidateMarginalAuditReport,
    rule_set: ShortOddsRuntimeRuleSet,
    grid_report: ShortOddsAdapterActivationGridReport,
    source_candidates: Sequence[ShortOddsAdapterActivationGridCandidate],
    scopes: Sequence[ShortOddsAdapterActivationScopeCandidate],
    scope_candidate_limit_reached: bool,
    warnings: Sequence[str],
    options: ShortOddsAdapterActivationScopeSearchOptions,
) -> ShortOddsAdapterActivationScopeSearchReport:
    accepted = [scope for scope in scopes if scope.status == "accepted"]
    shadow_only = [scope for scope in scopes if scope.status == "shadow_only"]
    rejected = [scope for scope in scopes if scope.status == "rejected"]
    best_scope = accepted[0] if accepted else shadow_only[0] if shadow_only else None
    production_changed = any(scope.production_recommendation_changed for scope in scopes)
    public_response_changed = any(scope.public_response_changed for scope in scopes)
    summary: dict[str, object] = {
        "calculation_basis": "short_odds_adapter_activation_scope_search_v3_1",
        "status": status,
        "accepted_scope_found": bool(accepted),
        "shadow_allowed": bool(accepted or shadow_only),
        "source_grid_report_key": grid_report.report_key,
        "source_audit_report_key": audit_report.report_key,
        "source_rule_profile_version": rule_set.profile_version,
        "selected_source_candidate_count": len(source_candidates),
        "scope_candidate_count": len(scopes),
        "accepted_scope_count": len(accepted),
        "shadow_only_scope_count": len(shadow_only),
        "rejected_scope_count": len(rejected),
        "scope_candidate_limit_reached": scope_candidate_limit_reached,
        "best_scope_key": best_scope.scope_key if best_scope is not None else None,
        "options": options.model_dump(mode="json"),
        "production_recommendation_changed": production_changed,
        "public_response_changed": public_response_changed,
        "warnings": list(warnings),
    }
    report_key = _digest_key(
        "short_odds_adapter_activation_scope_search",
        {
            **summary,
            "scope_keys": [scope.scope_key for scope in scopes],
        },
    )
    return ShortOddsAdapterActivationScopeSearchReport(
        report_key=report_key,
        status=status,
        accepted_scope_found=bool(accepted),
        shadow_allowed=bool(accepted or shadow_only),
        source_grid_report_key=grid_report.report_key,
        source_audit_report_key=audit_report.report_key,
        source_rule_profile_version=rule_set.profile_version,
        selected_source_candidate_count=len(source_candidates),
        scope_candidate_count=len(scopes),
        accepted_scope_count=len(accepted),
        shadow_only_scope_count=len(shadow_only),
        rejected_scope_count=len(rejected),
        scope_candidate_limit_reached=scope_candidate_limit_reached,
        best_scope_key=best_scope.scope_key if best_scope is not None else None,
        best_scope=best_scope,
        scopes=list(scopes)[: options.max_report_scope_candidates],
        production_recommendation_changed=production_changed,
        public_response_changed=public_response_changed,
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _scope_summary(
    source_candidate: ShortOddsAdapterActivationGridCandidate,
    *,
    rolling_report: HistoricalShortOddsRollingAdmissionReport,
    scope_competition_ids: Sequence[str],
    status: ShortOddsAdapterActivationScopeCandidateStatus,
    failed_checks: Sequence[str],
) -> dict[str, object]:
    return {
        "calculation_basis": "short_odds_adapter_activation_scope_candidate_v3_1",
        "status": status,
        "source_candidate_key": source_candidate.candidate_key,
        "scope_competition_ids": list(scope_competition_ids),
        "rolling_admission_report_key": rolling_report.report_key,
        "rolling_admission_status": rolling_report.status,
        "overall_final_answer_count": _summary_int(
            rolling_report,
            "overall_final_answer_count",
        ),
        "overall_changed_final_answer_count": _summary_int(
            rolling_report,
            "overall_changed_final_answer_count",
        ),
        "overall_final_answer_hit_rate_delta": _summary_optional_float(
            rolling_report,
            "overall_final_answer_hit_rate_delta",
        ),
        "overall_roi_delta": _summary_optional_float(
            rolling_report,
            "overall_roi_delta",
        ),
        "overall_profit_loss_delta": _summary_float(
            rolling_report,
            "overall_profit_loss_delta",
        ),
        "overall_harm_count_vs_original": _summary_int(
            rolling_report,
            "overall_harm_count_vs_original",
        ),
        "overall_average_hit_probability_delta_vs_original": (
            _summary_optional_float(
                rolling_report,
                "overall_average_hit_probability_delta_vs_original",
            )
        ),
        "rolling_failed_checks": list(failed_checks),
        "rolling_failed_fold_count": rolling_report.failed_fold_count,
        "rolling_failed_fold_reason_counts": _failed_fold_reason_counts(rolling_report),
        "production_recommendation_changed": _production_changed(rolling_report),
        "public_response_changed": _public_response_changed(rolling_report),
    }


def _scope_sort_key(
    scope: ShortOddsAdapterActivationScopeCandidate,
) -> tuple[float, float, float, float, float, float, float]:
    status_score = {"accepted": 2.0, "shadow_only": 1.0, "rejected": 0.0}[
        scope.status
    ]
    return (
        status_score,
        scope.overall_final_answer_hit_rate_delta
        if scope.overall_final_answer_hit_rate_delta is not None
        else -999.0,
        scope.overall_roi_delta if scope.overall_roi_delta is not None else -999.0,
        scope.overall_profit_loss_delta,
        float(scope.overall_changed_final_answer_count),
        -float(scope.rolling_failed_fold_count),
        -float(scope.scope_competition_count),
    )


def _summary_int(
    report: HistoricalShortOddsRollingAdmissionReport,
    key: str,
) -> int:
    value = report.summary_json.get(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _summary_float(
    report: HistoricalShortOddsRollingAdmissionReport,
    key: str,
) -> float:
    value = report.summary_json.get(key)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _summary_optional_float(
    report: HistoricalShortOddsRollingAdmissionReport,
    key: str,
) -> float | None:
    value = report.summary_json.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _failed_fold_reason_counts(
    report: HistoricalShortOddsRollingAdmissionReport,
) -> dict[str, int]:
    counts: Counter[str] = Counter(
        reason
        for fold in report.folds
        if fold.status == "failed"
        for reason in fold.failure_reasons
    )
    return {
        key: value
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    }


def _failed_fold_ids(report: HistoricalShortOddsRollingAdmissionReport) -> list[str]:
    return [fold.fold_id for fold in report.folds if fold.status == "failed"][:20]


def _production_changed(report: HistoricalShortOddsRollingAdmissionReport) -> bool:
    return any(fold.production_recommendation_changed for fold in report.folds)


def _public_response_changed(report: HistoricalShortOddsRollingAdmissionReport) -> bool:
    return any(fold.public_response_changed for fold in report.folds)


def _digest_key(prefix: str, payload: Mapping[str, object]) -> str:
    body = dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Search competition scopes for short-odds activation candidates."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--candidate-keys", default="")
    parser.add_argument("--include-rejected-candidates", action="store_true")
    parser.add_argument("--max-source-candidate-count", type=int, default=5)
    parser.add_argument("--min-scope-competition-count", type=int, default=1)
    parser.add_argument("--max-scope-competition-count", type=int, default=4)
    parser.add_argument("--exclude-full-probe-scope", action="store_true")
    parser.add_argument("--max-scope-candidate-count", type=int, default=200)
    parser.add_argument("--min-overall-final-answer-count", type=int, default=50)
    parser.add_argument("--min-overall-changed-final-answer-count", type=int, default=2)
    parser.add_argument("--min-overall-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-overall-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-overall-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-overall-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-overall-final-hit-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--max-overall-profit-loss-harm-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-overall-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.05,
    )
    parser.add_argument("--min-fold-final-answer-count", type=int, default=1)
    parser.add_argument("--min-fold-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-fold-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-fold-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-fold-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-fold-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-fold-final-hit-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-fold-profit-loss-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--min-fold-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.05,
    )
    parser.add_argument("--min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--min-active-season-fold-count", type=int, default=2)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=2)
    parser.add_argument("--rolling-window-final-answer-count", type=int, default=12)
    parser.add_argument("--rolling-window-step", type=int, default=6)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--max-report-scope-candidates", type=int, default=40)
    parser.add_argument("--require-accepted-scope", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> ShortOddsAdapterActivationScopeSearchOptions:
    return ShortOddsAdapterActivationScopeSearchOptions(
        candidate_keys=tuple(_csv(args.candidate_keys)),
        accepted_candidates_only=not args.include_rejected_candidates,
        max_source_candidate_count=args.max_source_candidate_count,
        min_scope_competition_count=args.min_scope_competition_count,
        max_scope_competition_count=args.max_scope_competition_count,
        include_full_probe_scope=not args.exclude_full_probe_scope,
        max_scope_candidate_count=args.max_scope_candidate_count,
        min_overall_final_answer_count=args.min_overall_final_answer_count,
        min_overall_changed_final_answer_count=(
            args.min_overall_changed_final_answer_count
        ),
        min_overall_final_answer_hit_rate_delta=(
            args.min_overall_final_answer_hit_rate_delta
        ),
        min_overall_roi_delta=args.min_overall_roi_delta,
        min_overall_profit_loss_delta=args.min_overall_profit_loss_delta,
        max_overall_harm_count_vs_original=args.max_overall_harm_count_vs_original,
        max_overall_final_hit_harm_count_vs_original=(
            args.max_overall_final_hit_harm_count_vs_original
        ),
        max_overall_profit_loss_harm_count_vs_original=(
            args.max_overall_profit_loss_harm_count_vs_original
        ),
        min_overall_average_hit_probability_delta_vs_original=(
            args.min_overall_average_hit_probability_delta_vs_original
        ),
        min_fold_final_answer_count=args.min_fold_final_answer_count,
        min_fold_changed_final_answer_count=args.min_fold_changed_final_answer_count,
        min_fold_final_answer_hit_rate_delta=args.min_fold_final_answer_hit_rate_delta,
        min_fold_roi_delta=args.min_fold_roi_delta,
        min_fold_profit_loss_delta=args.min_fold_profit_loss_delta,
        max_fold_harm_count_vs_original=args.max_fold_harm_count_vs_original,
        max_fold_final_hit_harm_count_vs_original=(
            args.max_fold_final_hit_harm_count_vs_original
        ),
        max_fold_profit_loss_harm_count_vs_original=(
            args.max_fold_profit_loss_harm_count_vs_original
        ),
        min_fold_average_hit_probability_delta_vs_original=(
            args.min_fold_average_hit_probability_delta_vs_original
        ),
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_fold_count=args.min_active_season_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        rolling_window_final_answer_count=args.rolling_window_final_answer_count,
        rolling_window_step=args.rolling_window_step,
        max_failed_fold_count=args.max_failed_fold_count,
        require_no_production_change=not args.allow_production_change,
        max_report_folds=args.max_report_folds,
        max_report_scope_candidates=args.max_report_scope_candidates,
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
