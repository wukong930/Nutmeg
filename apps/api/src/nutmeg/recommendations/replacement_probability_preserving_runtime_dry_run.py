from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditReport,
)
from nutmeg.recommendations.replacement_final_answer_probability_preserving_grid import (
    HistoricalReplacementProbabilityPreservingGridCandidate,
    HistoricalReplacementProbabilityPreservingGridReport,
    load_historical_replacement_probability_preserving_grid_report,
)
from nutmeg.recommendations.replacement_probability_preserving_admission import (
    HistoricalReplacementProbabilityPreservingAdmissionReport,
    load_historical_replacement_probability_preserving_admission_report,
)
from nutmeg.recommendations.replacement_probability_preserving_surface_replay import (
    HistoricalReplacementProbabilityPreservingSurfaceReplayReport,
    load_historical_replacement_probability_preserving_surface_replay_report,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayOptions,
    HistoricalShortOddsRuntimeShadowReplayReport,
    build_historical_short_odds_runtime_shadow_replay_report,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
)

type HistoricalReplacementProbabilityPreservingRuntimeDryRunStatus = Literal[
    "runtime_dry_run_passed",
    "runtime_dry_run_watchlist",
    "rejected",
]
type HistoricalReplacementProbabilityPreservingRuntimeDryRunCheckStatus = Literal[
    "passed",
    "failed",
]


class HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions(BaseModel):
    candidate_key: str | None = None
    rule_id: str | None = None
    proposed_profile_version: str = (
        "v3_1_probability_preserving_replacement_runtime_dry_run"
    )
    min_final_answer_count: int = Field(default=13, ge=1)
    min_changed_final_answer_count: int = Field(default=13, ge=0)
    min_final_answer_hit_delta_count: int = 0
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_average_hit_probability_delta_vs_original: float = -0.02
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    min_active_surface_count: int = Field(default=1, ge=0)
    max_failed_surface_count: int = Field(default=0, ge=0)
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_fold_count: int = Field(default=1, ge=0)
    min_active_rolling_fold_count: int = Field(default=1, ge=0)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_surface_replay_passed: bool = True
    require_admission_passed: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True
    max_report_items: int = Field(default=80, ge=1, le=500)


class HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(BaseModel):
    name: str
    status: HistoricalReplacementProbabilityPreservingRuntimeDryRunCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalReplacementProbabilityPreservingRuntimeDryRunReport(BaseModel):
    report_key: str
    status: HistoricalReplacementProbabilityPreservingRuntimeDryRunStatus
    shadow_runtime_candidate_allowed: bool
    production_recommendation_allowed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    source_audit_report_key: str
    source_grid_report_key: str
    source_surface_replay_report_key: str
    source_admission_report_key: str
    selected_candidate_key: str | None = None
    selected_candidate_status: str | None = None
    generated_runtime_shadow_replay_report_key: str | None = None
    final_answer_count: int = Field(default=0, ge=0)
    changed_final_answer_count: int = Field(default=0, ge=0)
    final_answer_hit_delta_count: int = 0
    profit_loss_delta: float = 0.0
    roi_delta: float | None = None
    harm_count_vs_original: int = Field(default=0, ge=0)
    final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    active_surface_count: int = Field(default=0, ge=0)
    failed_surface_count: int = Field(default=0, ge=0)
    active_competition_fold_count: int = Field(default=0, ge=0)
    active_season_fold_count: int = Field(default=0, ge=0)
    active_rolling_fold_count: int = Field(default=0, ge=0)
    failed_fold_count: int = Field(default=0, ge=0)
    checks: list[HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck] = (
        Field(default_factory=list)
    )
    runtime_proposal_profile_set_json: dict[str, object] = Field(default_factory=dict)
    runtime_shadow_replay_summary_json: dict[str, object] = Field(default_factory=dict)
    changed_items_json: list[dict[str, object]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_replacement_probability_preserving_runtime_dry_run_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    grid_report: HistoricalReplacementProbabilityPreservingGridReport,
    surface_replay_report: HistoricalReplacementProbabilityPreservingSurfaceReplayReport,
    admission_report: HistoricalReplacementProbabilityPreservingAdmissionReport,
    *,
    options: HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions | None = None,
) -> HistoricalReplacementProbabilityPreservingRuntimeDryRunReport:
    resolved_options = (
        options or HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions()
    )
    warnings = [
        *audit_report.warnings,
        *grid_report.warnings,
        *surface_replay_report.warnings,
        *admission_report.warnings,
    ]
    candidate = _selected_candidate(
        grid_report,
        candidate_key=resolved_options.candidate_key,
    )
    rule_set = (
        _rule_set_from_candidate(
            candidate,
            grid_report=grid_report,
            surface_replay_report=surface_replay_report,
            admission_report=admission_report,
            options=resolved_options,
        )
        if candidate is not None
        else ShortOddsRuntimeRuleSet(
            profile_version=resolved_options.proposed_profile_version,
            calculation_basis=(
                "probability_preserving_replacement_runtime_dry_run_v3_1"
            ),
            shadow_replay_enabled=True,
            rules=[],
            notes=["dry_run_only", "no_production_change"],
        )
    )
    runtime_shadow_report = (
        build_historical_short_odds_runtime_shadow_replay_report(
            audit_report,
            rule_set=rule_set,
            options=_runtime_shadow_options(candidate, resolved_options),
        )
        if candidate is not None
        else None
    )
    checks = _checks(
        audit_report,
        grid_report,
        surface_replay_report,
        admission_report,
        candidate=candidate,
        runtime_shadow_report=runtime_shadow_report,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    if candidate is None or candidate.status != "accepted":
        status: HistoricalReplacementProbabilityPreservingRuntimeDryRunStatus = (
            "rejected"
        )
    elif failed_checks:
        status = "runtime_dry_run_watchlist"
    else:
        status = "runtime_dry_run_passed"
    shadow_allowed = status == "runtime_dry_run_passed"
    runtime_summary = (
        _runtime_shadow_summary(runtime_shadow_report)
        if runtime_shadow_report is not None
        else {}
    )
    changed_items = (
        [
            item.model_dump(mode="json")
            for item in runtime_shadow_report.changed_items[: resolved_options.max_report_items]
        ]
        if runtime_shadow_report is not None
        else []
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_replacement_probability_preserving_runtime_dry_run_v3_1"
        ),
        "status": status,
        "shadow_runtime_candidate_allowed": shadow_allowed,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "source_audit_report_key": audit_report.report_key,
        "source_grid_report_key": grid_report.report_key,
        "source_surface_replay_report_key": surface_replay_report.report_key,
        "source_admission_report_key": admission_report.report_key,
        "selected_candidate_key": candidate.candidate_key if candidate else None,
        "selected_candidate_status": candidate.status if candidate else None,
        "generated_runtime_shadow_replay_report_key": (
            runtime_shadow_report.report_key if runtime_shadow_report else None
        ),
        "runtime_shadow": runtime_summary,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, changed_items)
    return HistoricalReplacementProbabilityPreservingRuntimeDryRunReport(
        report_key=report_key,
        status=status,
        shadow_runtime_candidate_allowed=shadow_allowed,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        source_audit_report_key=audit_report.report_key,
        source_grid_report_key=grid_report.report_key,
        source_surface_replay_report_key=surface_replay_report.report_key,
        source_admission_report_key=admission_report.report_key,
        selected_candidate_key=candidate.candidate_key if candidate else None,
        selected_candidate_status=candidate.status if candidate else None,
        generated_runtime_shadow_replay_report_key=(
            runtime_shadow_report.report_key if runtime_shadow_report else None
        ),
        final_answer_count=_runtime_int(runtime_shadow_report, "final_answer_count"),
        changed_final_answer_count=_runtime_int(
            runtime_shadow_report,
            "changed_final_answer_count",
        ),
        final_answer_hit_delta_count=_runtime_int(
            runtime_shadow_report,
            "final_answer_hit_delta_count",
        ),
        profit_loss_delta=_runtime_float(runtime_shadow_report, "profit_loss_delta"),
        roi_delta=runtime_shadow_report.roi_delta if runtime_shadow_report else None,
        harm_count_vs_original=_runtime_int(
            runtime_shadow_report,
            "harm_count_vs_original",
        ),
        final_hit_harm_count_vs_original=_runtime_int(
            runtime_shadow_report,
            "final_hit_harm_count_vs_original",
        ),
        profit_loss_harm_count_vs_original=_runtime_int(
            runtime_shadow_report,
            "profit_loss_harm_count_vs_original",
        ),
        average_hit_probability_delta_vs_original=(
            runtime_shadow_report.average_hit_probability_delta_vs_original
            if runtime_shadow_report
            else None
        ),
        active_surface_count=surface_replay_report.active_surface_count,
        failed_surface_count=surface_replay_report.failed_surface_count,
        active_competition_fold_count=admission_report.active_competition_fold_count,
        active_season_fold_count=admission_report.active_season_fold_count,
        active_rolling_fold_count=admission_report.active_rolling_fold_count,
        failed_fold_count=admission_report.failed_fold_count,
        checks=checks,
        runtime_proposal_profile_set_json=_proposal_profile_set_json(rule_set),
        runtime_shadow_replay_summary_json=runtime_summary,
        changed_items_json=changed_items,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_replacement_probability_preserving_runtime_dry_run_report(
    path: Path | str,
) -> HistoricalReplacementProbabilityPreservingRuntimeDryRunReport:
    return HistoricalReplacementProbabilityPreservingRuntimeDryRunReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_replacement_probability_preserving_runtime_dry_run_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        load_historical_replacement_probability_preserving_grid_report(args.grid_report),
        load_historical_replacement_probability_preserving_surface_replay_report(
            args.surface_replay_report
        ),
        load_historical_replacement_probability_preserving_admission_report(
            args.admission_report
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
    if report.status != "runtime_dry_run_passed" and not args.no_fail_process:
        raise SystemExit(1)


def _selected_candidate(
    grid_report: HistoricalReplacementProbabilityPreservingGridReport,
    *,
    candidate_key: str | None,
) -> HistoricalReplacementProbabilityPreservingGridCandidate | None:
    candidates = list(grid_report.candidates)
    if grid_report.best_candidate is not None:
        candidates.append(grid_report.best_candidate)
    if candidate_key:
        return next(
            (candidate for candidate in candidates if candidate.candidate_key == candidate_key),
            None,
        )
    if grid_report.best_candidate is not None and grid_report.best_candidate.accepted:
        return grid_report.best_candidate
    return next((candidate for candidate in candidates if candidate.accepted), None)


def _rule_set_from_candidate(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    *,
    grid_report: HistoricalReplacementProbabilityPreservingGridReport,
    surface_replay_report: HistoricalReplacementProbabilityPreservingSurfaceReplayReport,
    admission_report: HistoricalReplacementProbabilityPreservingAdmissionReport,
    options: HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions,
) -> ShortOddsRuntimeRuleSet:
    rule_id = _rule_id(candidate, options)
    rule = ShortOddsRuntimeReplacementRule(
        rule_id=rule_id,
        profile_id=candidate.shadow_selection_rule,
        proposed_profile_version=options.proposed_profile_version,
        proposed_production_enabled=True,
        production_recommendation_changed=False,
        allowed_competition_ids=sorted(set(candidate.ready_competition_ids)),
        excluded_competition_ids=[],
        selection_rule=candidate.selection_rule,
        constraints_json=_constraints_json(candidate, options),
        source_report_keys={
            "grid": grid_report.report_key,
            "surface_replay": surface_replay_report.report_key,
            "admission": admission_report.report_key,
            "final_answer_gate": candidate.final_answer_gate_report_key,
        },
        evidence_json={
            "dry_run_only": True,
            "candidate_key": candidate.candidate_key,
            "changed_final_answer_count": candidate.changed_final_answer_count,
            "final_answer_hit_delta_count_vs_original": (
                candidate.final_answer_hit_delta_count_vs_original
            ),
            "profit_loss_delta_vs_original": candidate.profit_loss_delta_vs_original,
            "harm_count_vs_original": candidate.harm_count_vs_original,
            "average_hit_probability_delta_vs_original": (
                candidate.average_hit_probability_delta_vs_original
            ),
            "surface_replay_status": surface_replay_report.status,
            "admission_status": admission_report.status,
        },
        rollback_conditions=[
            "disable_if_runtime_dry_run_report_missing_or_failed",
            "disable_if_production_recommendation_changed",
            "disable_if_public_response_changed",
            "disable_if_harm_count_vs_original_exceeds_0",
        ],
        notes=[
            "runtime_proposal_dry_run_only",
            "not_written_to_default_profile",
            "not_visible_to_public_recommendations",
        ],
    )
    return ShortOddsRuntimeRuleSet(
        profile_version=options.proposed_profile_version,
        calculation_basis=(
            "probability_preserving_replacement_runtime_dry_run_rule_set_v3_1"
        ),
        shadow_replay_enabled=True,
        rules=[rule],
        notes=[
            "dry_run_only",
            "production_recommendation_allowed_false",
            "public_response_changed_false",
        ],
    )


def _constraints_json(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    options: HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions,
) -> dict[str, object]:
    return {
        "selection_rule": candidate.selection_rule,
        "shadow_selection_rule": candidate.shadow_selection_rule,
        "max_replacements_per_final_answer": 1,
        "min_replacement_probability": candidate.min_replacement_probability,
        "min_replacement_decimal_odds": candidate.min_replacement_decimal_odds,
        "max_replacement_decimal_odds": candidate.max_replacement_decimal_odds,
        "min_candidate_hit_probability_delta_vs_model_top": (
            candidate.min_candidate_hit_probability_delta_vs_model_top
        ),
        "max_candidate_hit_probability_delta_vs_model_top": (
            candidate.max_candidate_hit_probability_delta_vs_model_top
        ),
        "min_decimal_odds_delta_vs_model_top": (
            candidate.min_decimal_odds_delta_vs_model_top
        ),
        "min_candidate_hit_probability_delta_vs_original": (
            candidate.min_item_hit_probability_delta_vs_original
        ),
        "exclude_original_hit_harm": candidate.exclude_original_hit_harm,
        "min_average_hit_probability_delta_vs_original": (
            options.min_average_hit_probability_delta_vs_original
        ),
        "max_harm_count_vs_original": options.max_harm_count_vs_original,
        "max_final_hit_harm_count_vs_original": (
            options.max_final_hit_harm_count_vs_original
        ),
        "max_profit_loss_harm_count_vs_original": (
            options.max_profit_loss_harm_count_vs_original
        ),
    }


def _runtime_shadow_options(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate | None,
    options: HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions,
) -> HistoricalShortOddsRuntimeShadowReplayOptions:
    return HistoricalShortOddsRuntimeShadowReplayOptions(
        enable_shadow_replay=True,
        rule_ids=(_rule_id(candidate, options),) if candidate is not None else (),
        min_final_answer_count=options.min_final_answer_count,
        min_changed_final_answer_count=options.min_changed_final_answer_count,
        min_final_answer_hit_rate_delta=options.min_final_answer_hit_rate_delta,
        min_roi_delta=options.min_roi_delta,
        min_profit_loss_delta=options.min_profit_loss_delta,
        max_harm_count_vs_original=options.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            options.max_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            options.max_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            options.min_average_hit_probability_delta_vs_original
        ),
        min_candidate_hit_probability_delta_vs_original=(
            candidate.min_item_hit_probability_delta_vs_original
            if candidate is not None
            else None
        ),
        require_no_production_change=options.require_no_production_change,
        max_report_items=options.max_report_items,
    )


def _checks(
    audit_report: HistoricalCandidateMarginalAuditReport,
    grid_report: HistoricalReplacementProbabilityPreservingGridReport,
    surface_replay_report: HistoricalReplacementProbabilityPreservingSurfaceReplayReport,
    admission_report: HistoricalReplacementProbabilityPreservingAdmissionReport,
    *,
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate | None,
    runtime_shadow_report: HistoricalShortOddsRuntimeShadowReplayReport | None,
    options: HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions,
) -> list[HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck]:
    checks = [
        _boolean_check(
            name="selected_candidate_accepted",
            actual=candidate is not None and candidate.status == "accepted",
            expected=True,
            detail="selected candidate must be accepted by the source grid",
        ),
        _equality_check(
            name="surface_replay_source_grid_report_key",
            actual=surface_replay_report.source_grid_report_key,
            expected=grid_report.report_key,
            detail="surface replay must be linked to the supplied grid report",
        ),
        _equality_check(
            name="admission_source_grid_report_key",
            actual=admission_report.source_grid_report_key,
            expected=grid_report.report_key,
            detail="admission must be linked to the supplied grid report",
        ),
        _equality_check(
            name="surface_replay_source_audit_report_key",
            actual=surface_replay_report.source_audit_report_key,
            expected=audit_report.report_key,
            detail="surface replay must use the supplied audit report",
        ),
        _equality_check(
            name="admission_source_audit_report_key",
            actual=admission_report.source_audit_report_key,
            expected=audit_report.report_key,
            detail="admission must use the supplied audit report",
        ),
        _equality_check(
            name="surface_replay_selected_candidate_key",
            actual=surface_replay_report.selected_candidate_key,
            expected=candidate.candidate_key if candidate else None,
            detail="surface replay must evaluate the selected candidate",
        ),
        _equality_check(
            name="admission_selected_candidate_key",
            actual=admission_report.selected_candidate_key,
            expected=candidate.candidate_key if candidate else None,
            detail="admission must evaluate the selected candidate",
        ),
        _equality_check(
            name="surface_replay_status",
            actual=surface_replay_report.status,
            expected="cross_surface_passed",
            enabled=options.require_surface_replay_passed,
            detail="surface replay must pass before runtime dry run is allowed",
        ),
        _equality_check(
            name="admission_status",
            actual=admission_report.status,
            expected="shadow_admission_passed",
            enabled=options.require_admission_passed,
            detail="admission must pass before runtime dry run is allowed",
        ),
        _minimum_check(
            name="active_surface_count",
            actual=surface_replay_report.active_surface_count,
            threshold=options.min_active_surface_count,
            detail="runtime dry run should keep enough active surfaces",
        ),
        _maximum_check(
            name="failed_surface_count",
            actual=surface_replay_report.failed_surface_count,
            threshold=options.max_failed_surface_count,
            detail="runtime dry run should not carry failed surfaces",
        ),
        _minimum_check(
            name="active_competition_fold_count",
            actual=admission_report.active_competition_fold_count,
            threshold=options.min_active_competition_fold_count,
            detail="runtime dry run should keep enough competition folds",
        ),
        _minimum_check(
            name="active_season_fold_count",
            actual=admission_report.active_season_fold_count,
            threshold=options.min_active_season_fold_count,
            detail="runtime dry run should keep enough season folds",
        ),
        _minimum_check(
            name="active_rolling_fold_count",
            actual=admission_report.active_rolling_fold_count,
            threshold=options.min_active_rolling_fold_count,
            detail="runtime dry run should keep enough rolling folds",
        ),
        _maximum_check(
            name="failed_fold_count",
            actual=admission_report.failed_fold_count,
            threshold=options.max_failed_fold_count,
            detail="runtime dry run should not carry failed folds",
        ),
        _boolean_check(
            name="runtime_shadow_replay_present",
            actual=runtime_shadow_report is not None,
            expected=True,
            detail="runtime dry run must generate runtime-style shadow replay",
        ),
        _boolean_check(
            name="production_recommendation_allowed_false",
            actual=False,
            expected=False,
            detail="runtime dry run must not allow production recommendation changes",
        ),
    ]
    if runtime_shadow_report is not None:
        checks.extend(
            [
                _boolean_check(
                    name="runtime_shadow_replay_passed",
                    actual=runtime_shadow_report.passed,
                    expected=True,
                    detail="runtime-style shadow replay must pass",
                ),
                _minimum_check(
                    name="runtime_final_answer_count",
                    actual=runtime_shadow_report.final_answer_count,
                    threshold=options.min_final_answer_count,
                    detail="runtime replay should cover enough final answers",
                ),
                _minimum_check(
                    name="runtime_changed_final_answer_count",
                    actual=runtime_shadow_report.changed_final_answer_count,
                    threshold=options.min_changed_final_answer_count,
                    detail="runtime replay should affect enough final answers",
                ),
                _minimum_check(
                    name="runtime_final_answer_hit_delta_count",
                    actual=runtime_shadow_report.final_answer_hit_delta_count,
                    threshold=options.min_final_answer_hit_delta_count,
                    detail="runtime replay final-answer hit count should not regress",
                ),
                _minimum_check(
                    name="runtime_final_answer_hit_rate_delta",
                    actual=runtime_shadow_report.final_answer_hit_rate_delta,
                    threshold=options.min_final_answer_hit_rate_delta,
                    detail="runtime replay final-answer hit rate should not regress",
                ),
                _minimum_check(
                    name="runtime_roi_delta",
                    actual=runtime_shadow_report.roi_delta,
                    threshold=options.min_roi_delta,
                    detail="runtime replay ROI should not regress",
                ),
                _minimum_check(
                    name="runtime_profit_loss_delta",
                    actual=runtime_shadow_report.profit_loss_delta,
                    threshold=options.min_profit_loss_delta,
                    detail="runtime replay profit/loss should not regress",
                ),
                _maximum_check(
                    name="runtime_harm_count_vs_original",
                    actual=runtime_shadow_report.harm_count_vs_original,
                    threshold=options.max_harm_count_vs_original,
                    detail="runtime replay should not reduce original P/L",
                ),
                _maximum_check(
                    name="runtime_final_hit_harm_count_vs_original",
                    actual=runtime_shadow_report.final_hit_harm_count_vs_original,
                    threshold=options.max_final_hit_harm_count_vs_original,
                    detail="runtime replay should not turn hits into misses",
                ),
                _maximum_check(
                    name="runtime_profit_loss_harm_count_vs_original",
                    actual=runtime_shadow_report.profit_loss_harm_count_vs_original,
                    threshold=options.max_profit_loss_harm_count_vs_original,
                    detail="runtime replay should not reduce original final-answer P/L",
                ),
                _minimum_check(
                    name="runtime_average_hit_probability_delta_vs_original",
                    actual=(
                        runtime_shadow_report
                        .average_hit_probability_delta_vs_original
                    ),
                    threshold=options.min_average_hit_probability_delta_vs_original,
                    detail="runtime replay probability loss should stay bounded",
                ),
                _boolean_check(
                    name="runtime_no_production_recommendation_change",
                    actual=not runtime_shadow_report.production_recommendation_changed,
                    expected=True,
                    enabled=options.require_no_production_change,
                    detail="runtime replay must not change production recommendations",
                ),
                _boolean_check(
                    name="runtime_no_public_response_change",
                    actual=not runtime_shadow_report.public_response_changed,
                    expected=True,
                    enabled=options.require_no_public_response_change,
                    detail="runtime replay must not change public responses",
                ),
            ]
        )
    return checks


def _runtime_shadow_summary(
    report: HistoricalShortOddsRuntimeShadowReplayReport,
) -> dict[str, object]:
    return {
        "report_key": report.report_key,
        "status": report.status,
        "passed": report.passed,
        "final_answer_count": report.final_answer_count,
        "changed_final_answer_count": report.changed_final_answer_count,
        "final_answer_hit_delta_count": report.final_answer_hit_delta_count,
        "profit_loss_delta": report.profit_loss_delta,
        "roi_delta": report.roi_delta,
        "harm_count_vs_original": report.harm_count_vs_original,
        "final_hit_harm_count_vs_original": report.final_hit_harm_count_vs_original,
        "profit_loss_harm_count_vs_original": (
            report.profit_loss_harm_count_vs_original
        ),
        "average_hit_probability_delta_vs_original": (
            report.average_hit_probability_delta_vs_original
        ),
        "production_recommendation_changed": report.production_recommendation_changed,
        "public_response_changed": report.public_response_changed,
        "warnings": report.warnings,
    }


def _proposal_profile_set_json(rule_set: ShortOddsRuntimeRuleSet) -> dict[str, object]:
    payload = rule_set.model_dump(mode="json")
    payload.update(
        {
            "dry_run_only": True,
            "production_recommendation_allowed": False,
            "production_recommendation_changed": False,
            "public_response_changed": False,
        }
    )
    return payload


def _runtime_int(
    report: HistoricalShortOddsRuntimeShadowReplayReport | None,
    field_name: str,
) -> int:
    if report is None:
        return 0
    value = getattr(report, field_name)
    return int(value) if isinstance(value, int) else 0


def _runtime_float(
    report: HistoricalShortOddsRuntimeShadowReplayReport | None,
    field_name: str,
) -> float:
    if report is None:
        return 0.0
    value = getattr(report, field_name)
    return float(value) if isinstance(value, int | float) else 0.0


def _rule_id(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate | None,
    options: HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions,
) -> str:
    if options.rule_id:
        return options.rule_id
    if candidate is None:
        return "probability_preserving_runtime_dry_run:missing_candidate"
    suffix = candidate.candidate_key.rsplit(":", maxsplit=1)[-1]
    return f"probability_preserving_runtime_dry_run:{suffix}"


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck:
    if not enabled:
        return HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _equality_check(
    *,
    name: str,
    actual: str | None,
    expected: str | None,
    detail: str,
    enabled: bool = True,
) -> HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck:
    if not enabled:
        return HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(
        name=name,
        status="passed" if actual == expected else "failed",
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
) -> HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck:
    if actual is None:
        return HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(
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
) -> HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck:
    if actual is None:
        return HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build a shadow-only runtime proposal dry run for a probability-"
            "preserving replacement candidate."
        )
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--surface-replay-report", type=Path, required=True)
    parser.add_argument("--admission-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--candidate-key")
    parser.add_argument("--rule-id")
    parser.add_argument(
        "--proposed-profile-version",
        default="v3_1_probability_preserving_replacement_runtime_dry_run",
    )
    parser.add_argument("--min-final-answer-count", type=int, default=13)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=13)
    parser.add_argument("--min-final-answer-hit-delta-count", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-final-hit-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-profit-loss-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--min-active-surface-count", type=int, default=1)
    parser.add_argument("--max-failed-surface-count", type=int, default=0)
    parser.add_argument("--min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--min-active-season-fold-count", type=int, default=1)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-surface-watchlist", action="store_true")
    parser.add_argument("--allow-admission-watchlist", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--max-report-items", type=int, default=80)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions:
    return HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions(
        candidate_key=args.candidate_key,
        rule_id=args.rule_id,
        proposed_profile_version=args.proposed_profile_version,
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_final_answer_hit_delta_count=args.min_final_answer_hit_delta_count,
        min_final_answer_hit_rate_delta=args.min_final_answer_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            args.max_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            args.max_profit_loss_harm_count_vs_original
        ),
        min_active_surface_count=args.min_active_surface_count,
        max_failed_surface_count=args.max_failed_surface_count,
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_fold_count=args.min_active_season_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        max_failed_fold_count=args.max_failed_fold_count,
        require_surface_replay_passed=not args.allow_surface_watchlist,
        require_admission_passed=not args.allow_admission_watchlist,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
        max_report_items=args.max_report_items,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalReplacementProbabilityPreservingRuntimeDryRunCheck],
    changed_items: Sequence[Mapping[str, object]],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "checks": [check.model_dump(mode="json") for check in checks],
            "changed_item_count": len(changed_items),
            "changed_item_keys": [
                str(item.get("final_answer_key", "")) for item in changed_items
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_probability_preserving_runtime_dry_run:{digest}"
