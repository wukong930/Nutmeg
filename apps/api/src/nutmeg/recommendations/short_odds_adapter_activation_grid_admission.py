from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
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

type ShortOddsAdapterActivationGridAdmissionStatus = Literal[
    "accepted_candidate_found",
    "shadow_only_candidates",
    "no_admitted_candidate",
    "no_candidates",
    "no_rules",
]
type ShortOddsAdapterActivationGridAdmissionCandidateStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]


class ShortOddsAdapterActivationGridAdmissionOptions(BaseModel):
    candidate_keys: tuple[str, ...] = ()
    accepted_candidates_only: bool = True
    max_candidate_count: int = Field(default=5, ge=1, le=100)
    min_overall_final_answer_count: int = Field(default=30, ge=1)
    min_overall_changed_final_answer_count: int = Field(default=5, ge=0)
    min_overall_final_answer_hit_rate_delta: float = 0.0
    min_overall_roi_delta: float = 0.0
    min_overall_profit_loss_delta: float = 0.0
    max_overall_harm_count_vs_original: int = Field(default=0, ge=0)
    max_overall_final_hit_harm_count_vs_original: int | None = Field(
        default=0,
        ge=0,
    )
    max_overall_profit_loss_harm_count_vs_original: int | None = Field(
        default=0,
        ge=0,
    )
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
    min_active_competition_fold_count: int = Field(default=3, ge=0)
    min_active_season_fold_count: int = Field(default=2, ge=0)
    min_active_rolling_fold_count: int = Field(default=2, ge=0)
    rolling_window_final_answer_count: int = Field(default=12, ge=1)
    rolling_window_step: int = Field(default=6, ge=1)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_no_production_change: bool = True
    max_report_folds: int = Field(default=120, ge=1, le=500)


class ShortOddsAdapterActivationGridAdmissionCandidate(BaseModel):
    candidate_key: str
    status: ShortOddsAdapterActivationGridAdmissionCandidateStatus
    production_candidate_allowed: bool
    shadow_allowed: bool
    source_candidate_status: str
    source_changed_final_answer_count: int = Field(ge=0)
    source_final_answer_hit_rate_delta: float | None = None
    source_roi_delta: float | None = None
    source_profit_loss_delta: float
    source_harm_count_vs_original: int = Field(ge=0)
    source_final_hit_harm_count_vs_original: int = Field(ge=0)
    source_profit_loss_harm_count_vs_original: int = Field(ge=0)
    min_replacement_probability: float
    max_replacement_decimal_odds: float
    min_candidate_hit_probability_delta_vs_model_top: float
    min_candidate_hit_probability_delta_vs_original: float
    rolling_admission_report_key: str
    rolling_admission_status: str
    rolling_fold_count: int = Field(ge=0)
    rolling_active_fold_count: int = Field(ge=0)
    rolling_failed_fold_count: int = Field(ge=0)
    rolling_active_competition_fold_count: int = Field(ge=0)
    rolling_active_season_fold_count: int = Field(ge=0)
    rolling_active_rolling_fold_count: int = Field(ge=0)
    rolling_failed_checks: list[str] = Field(default_factory=list)
    rolling_failed_fold_reason_counts: dict[str, int] = Field(default_factory=dict)
    rolling_failed_fold_ids: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    summary_json: dict[str, object] = Field(default_factory=dict)


class ShortOddsAdapterActivationGridAdmissionReport(BaseModel):
    report_key: str
    status: ShortOddsAdapterActivationGridAdmissionStatus
    production_candidate_allowed: bool
    shadow_allowed: bool
    source_grid_report_key: str
    source_audit_report_key: str
    source_rule_profile_version: str
    selected_candidate_count: int = Field(ge=0)
    accepted_candidate_count: int = Field(ge=0)
    shadow_only_candidate_count: int = Field(ge=0)
    rejected_candidate_count: int = Field(ge=0)
    best_candidate_key: str | None = None
    best_candidate: ShortOddsAdapterActivationGridAdmissionCandidate | None = None
    candidates: list[ShortOddsAdapterActivationGridAdmissionCandidate] = Field(
        default_factory=list
    )
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_short_odds_adapter_activation_grid_admission_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    grid_report: ShortOddsAdapterActivationGridReport,
    options: ShortOddsAdapterActivationGridAdmissionOptions | None = None,
) -> ShortOddsAdapterActivationGridAdmissionReport:
    resolved_options = options or ShortOddsAdapterActivationGridAdmissionOptions()
    selected_source_candidates = _selected_source_candidates(
        grid_report,
        options=resolved_options,
    )
    selected_rules = rule_set.selected_rules(
        rule_ids=_selected_rule_ids(selected_source_candidates),
        require_proposed_production_enabled=True,
        require_no_production_change=True,
    )
    warnings = [*grid_report.warnings, *audit_report.warnings]
    if not selected_source_candidates:
        warnings.append("short_odds_adapter_activation_grid_admission:no_candidates")
        return _report(
            status="no_candidates",
            audit_report=audit_report,
            rule_set=rule_set,
            grid_report=grid_report,
            candidates=[],
            warnings=warnings,
            options=resolved_options,
        )
    if not selected_rules:
        warnings.append("short_odds_adapter_activation_grid_admission:no_enabled_rules")
        return _report(
            status="no_rules",
            audit_report=audit_report,
            rule_set=rule_set,
            grid_report=grid_report,
            candidates=[],
            warnings=warnings,
            options=resolved_options,
        )
    admissions = [
        _admission_candidate(
            source_candidate,
            audit_report=audit_report,
            rule_set=rule_set,
            selected_rules=selected_rules,
            options=resolved_options,
        )
        for source_candidate in selected_source_candidates
    ]
    if any(candidate.status == "accepted" for candidate in admissions):
        status: ShortOddsAdapterActivationGridAdmissionStatus = (
            "accepted_candidate_found"
        )
    elif any(candidate.shadow_allowed for candidate in admissions):
        status = "shadow_only_candidates"
    else:
        status = "no_admitted_candidate"
    return _report(
        status=status,
        audit_report=audit_report,
        rule_set=rule_set,
        grid_report=grid_report,
        candidates=sorted(admissions, key=_candidate_sort_key, reverse=True),
        warnings=warnings,
        options=resolved_options,
    )


def load_short_odds_adapter_activation_grid_admission_report(
    path: Path | str,
) -> ShortOddsAdapterActivationGridAdmissionReport:
    return ShortOddsAdapterActivationGridAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_short_odds_adapter_activation_grid_admission_report(
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
        args.require_production_candidate
        and not report.production_candidate_allowed
        and not args.no_fail_process
    ):
        raise SystemExit(1)


def _selected_source_candidates(
    grid_report: ShortOddsAdapterActivationGridReport,
    *,
    options: ShortOddsAdapterActivationGridAdmissionOptions,
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
    return selected[: options.max_candidate_count]


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


def _admission_candidate(
    source_candidate: ShortOddsAdapterActivationGridCandidate,
    *,
    audit_report: HistoricalCandidateMarginalAuditReport,
    rule_set: ShortOddsRuntimeRuleSet,
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    options: ShortOddsAdapterActivationGridAdmissionOptions,
) -> ShortOddsAdapterActivationGridAdmissionCandidate:
    candidate_rules = [
        _candidate_rule(rule, source_candidate=source_candidate)
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
    status: ShortOddsAdapterActivationGridAdmissionCandidateStatus
    if rolling_report.production_recommendation_allowed:
        status = "accepted"
    elif rolling_report.shadow_allowed:
        status = "shadow_only"
    else:
        status = "rejected"
    summary: dict[str, object] = {
        "calculation_basis": (
            "short_odds_adapter_activation_grid_admission_candidate_v3_1"
        ),
        "candidate_key": source_candidate.candidate_key,
        "status": status,
        "source_candidate": _source_candidate_summary(source_candidate),
        "rolling_admission_report_key": rolling_report.report_key,
        "rolling_admission_status": rolling_report.status,
        "rolling_failed_checks": failed_checks,
        "rolling_failed_fold_reason_counts": _failed_fold_reason_counts(
            rolling_report
        ),
        "rolling_failed_fold_ids": _failed_fold_ids(rolling_report),
        "production_candidate_allowed": rolling_report.production_recommendation_allowed,
        "shadow_allowed": rolling_report.shadow_allowed,
        "production_recommendation_changed": _production_changed(rolling_report),
        "public_response_changed": _public_response_changed(rolling_report),
    }
    return ShortOddsAdapterActivationGridAdmissionCandidate(
        candidate_key=source_candidate.candidate_key,
        status=status,
        production_candidate_allowed=rolling_report.production_recommendation_allowed,
        shadow_allowed=rolling_report.shadow_allowed,
        source_candidate_status=source_candidate.status,
        source_changed_final_answer_count=source_candidate.changed_final_answer_count,
        source_final_answer_hit_rate_delta=(
            source_candidate.final_answer_hit_rate_delta
        ),
        source_roi_delta=source_candidate.roi_delta,
        source_profit_loss_delta=source_candidate.profit_loss_delta,
        source_harm_count_vs_original=source_candidate.harm_count_vs_original,
        source_final_hit_harm_count_vs_original=(
            source_candidate.final_hit_harm_count_vs_original
        ),
        source_profit_loss_harm_count_vs_original=(
            source_candidate.profit_loss_harm_count_vs_original
        ),
        min_replacement_probability=source_candidate.min_replacement_probability,
        max_replacement_decimal_odds=source_candidate.max_replacement_decimal_odds,
        min_candidate_hit_probability_delta_vs_model_top=(
            source_candidate.min_candidate_hit_probability_delta_vs_model_top
        ),
        min_candidate_hit_probability_delta_vs_original=(
            source_candidate.min_candidate_hit_probability_delta_vs_original
        ),
        rolling_admission_report_key=rolling_report.report_key,
        rolling_admission_status=rolling_report.status,
        rolling_fold_count=rolling_report.fold_count,
        rolling_active_fold_count=rolling_report.active_fold_count,
        rolling_failed_fold_count=rolling_report.failed_fold_count,
        rolling_active_competition_fold_count=(
            rolling_report.active_competition_fold_count
        ),
        rolling_active_season_fold_count=rolling_report.active_season_fold_count,
        rolling_active_rolling_fold_count=rolling_report.active_rolling_fold_count,
        rolling_failed_checks=failed_checks,
        rolling_failed_fold_reason_counts=_failed_fold_reason_counts(rolling_report),
        rolling_failed_fold_ids=_failed_fold_ids(rolling_report),
        production_recommendation_changed=_production_changed(rolling_report),
        public_response_changed=_public_response_changed(rolling_report),
        summary_json=summary,
    )


def _candidate_rule(
    rule: ShortOddsRuntimeReplacementRule,
    *,
    source_candidate: ShortOddsAdapterActivationGridCandidate,
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
            "allowed_competition_ids": list(source_candidate.probe_competition_ids),
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
    options: ShortOddsAdapterActivationGridAdmissionOptions,
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
    status: ShortOddsAdapterActivationGridAdmissionStatus,
    audit_report: HistoricalCandidateMarginalAuditReport,
    rule_set: ShortOddsRuntimeRuleSet,
    grid_report: ShortOddsAdapterActivationGridReport,
    candidates: Sequence[ShortOddsAdapterActivationGridAdmissionCandidate],
    warnings: Sequence[str],
    options: ShortOddsAdapterActivationGridAdmissionOptions,
) -> ShortOddsAdapterActivationGridAdmissionReport:
    accepted = [candidate for candidate in candidates if candidate.status == "accepted"]
    shadow_only = [
        candidate for candidate in candidates if candidate.status == "shadow_only"
    ]
    rejected = [candidate for candidate in candidates if candidate.status == "rejected"]
    best_candidate = accepted[0] if accepted else shadow_only[0] if shadow_only else None
    production_changed = any(
        candidate.production_recommendation_changed for candidate in candidates
    )
    public_response_changed = any(
        candidate.public_response_changed for candidate in candidates
    )
    summary: dict[str, object] = {
        "calculation_basis": "short_odds_adapter_activation_grid_admission_v3_1",
        "status": status,
        "production_candidate_allowed": bool(accepted),
        "shadow_allowed": bool(accepted or shadow_only),
        "source_grid_report_key": grid_report.report_key,
        "source_audit_report_key": audit_report.report_key,
        "source_rule_profile_version": rule_set.profile_version,
        "selected_candidate_count": len(candidates),
        "accepted_candidate_count": len(accepted),
        "shadow_only_candidate_count": len(shadow_only),
        "rejected_candidate_count": len(rejected),
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "options": options.model_dump(mode="json"),
        "production_recommendation_changed": production_changed,
        "public_response_changed": public_response_changed,
        "warnings": list(warnings),
    }
    report_key = _digest_key(
        {
            **summary,
            "candidate_summaries": [
                candidate.summary_json for candidate in candidates
            ],
        }
    )
    return ShortOddsAdapterActivationGridAdmissionReport(
        report_key=report_key,
        status=status,
        production_candidate_allowed=bool(accepted),
        shadow_allowed=bool(accepted or shadow_only),
        source_grid_report_key=grid_report.report_key,
        source_audit_report_key=audit_report.report_key,
        source_rule_profile_version=rule_set.profile_version,
        selected_candidate_count=len(candidates),
        accepted_candidate_count=len(accepted),
        shadow_only_candidate_count=len(shadow_only),
        rejected_candidate_count=len(rejected),
        best_candidate_key=(
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        best_candidate=best_candidate,
        candidates=list(candidates),
        production_recommendation_changed=production_changed,
        public_response_changed=public_response_changed,
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _candidate_sort_key(
    candidate: ShortOddsAdapterActivationGridAdmissionCandidate,
) -> tuple[float, float, float, float, float, float]:
    status_score = {"accepted": 2.0, "shadow_only": 1.0, "rejected": 0.0}[
        candidate.status
    ]
    return (
        status_score,
        candidate.source_final_answer_hit_rate_delta
        if candidate.source_final_answer_hit_rate_delta is not None
        else -999.0,
        candidate.source_roi_delta if candidate.source_roi_delta is not None else -999.0,
        candidate.source_profit_loss_delta,
        float(candidate.rolling_active_fold_count),
        -float(candidate.rolling_failed_fold_count),
    )


def _source_candidate_summary(
    candidate: ShortOddsAdapterActivationGridCandidate,
) -> dict[str, object]:
    return {
        "candidate_key": candidate.candidate_key,
        "status": candidate.status,
        "accepted": candidate.accepted,
        "changed_final_answer_count": candidate.changed_final_answer_count,
        "final_answer_hit_rate_delta": candidate.final_answer_hit_rate_delta,
        "roi_delta": candidate.roi_delta,
        "profit_loss_delta": candidate.profit_loss_delta,
        "harm_count_vs_original": candidate.harm_count_vs_original,
        "min_replacement_probability": candidate.min_replacement_probability,
        "max_replacement_decimal_odds": candidate.max_replacement_decimal_odds,
        "min_candidate_hit_probability_delta_vs_model_top": (
            candidate.min_candidate_hit_probability_delta_vs_model_top
        ),
        "min_candidate_hit_probability_delta_vs_original": (
            candidate.min_candidate_hit_probability_delta_vs_original
        ),
    }


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


def _digest_key(payload: Mapping[str, object]) -> str:
    body = dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"short_odds_adapter_activation_grid_admission:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Run rolling admission for short-odds activation grid candidates."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--candidate-keys", default="")
    parser.add_argument("--include-rejected-candidates", action="store_true")
    parser.add_argument("--max-candidate-count", type=int, default=5)
    parser.add_argument("--min-overall-final-answer-count", type=int, default=30)
    parser.add_argument("--min-overall-changed-final-answer-count", type=int, default=5)
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
    parser.add_argument("--min-active-competition-fold-count", type=int, default=3)
    parser.add_argument("--min-active-season-fold-count", type=int, default=2)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=2)
    parser.add_argument("--rolling-window-final-answer-count", type=int, default=12)
    parser.add_argument("--rolling-window-step", type=int, default=6)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--require-production-candidate", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> ShortOddsAdapterActivationGridAdmissionOptions:
    return ShortOddsAdapterActivationGridAdmissionOptions(
        candidate_keys=tuple(_csv(args.candidate_keys)),
        accepted_candidates_only=not args.include_rejected_candidates,
        max_candidate_count=args.max_candidate_count,
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
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
