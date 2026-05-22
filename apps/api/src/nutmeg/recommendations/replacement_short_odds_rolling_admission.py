from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import search
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
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
    ShortOddsRuntimeRuleSet,
    load_short_odds_runtime_rule_set,
)

type HistoricalShortOddsRollingAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalShortOddsRollingAdmissionCheckStatus = Literal["passed", "failed"]
type HistoricalShortOddsRollingFoldStatus = Literal["passed", "failed", "skipped"]


class HistoricalShortOddsRollingAdmissionOptions(BaseModel):
    rule_ids: tuple[str, ...] = ()
    min_overall_final_answer_count: int = Field(default=30, ge=1)
    min_overall_changed_final_answer_count: int = Field(default=5, ge=0)
    min_overall_final_answer_hit_rate_delta: float = 0.0
    min_overall_roi_delta: float = 0.0
    min_overall_profit_loss_delta: float = 0.0
    max_overall_harm_count_vs_original: int = Field(default=0, ge=0)
    max_overall_final_hit_harm_count_vs_original: int | None = Field(
        default=None,
        ge=0,
    )
    max_overall_profit_loss_harm_count_vs_original: int | None = Field(
        default=None,
        ge=0,
    )
    min_overall_average_hit_probability_delta_vs_original: float = -0.02
    min_fold_final_answer_count: int = Field(default=1, ge=1)
    min_fold_changed_final_answer_count: int = Field(default=1, ge=0)
    min_fold_final_answer_hit_rate_delta: float = 0.0
    min_fold_roi_delta: float = 0.0
    min_fold_profit_loss_delta: float = 0.0
    max_fold_harm_count_vs_original: int = Field(default=0, ge=0)
    max_fold_final_hit_harm_count_vs_original: int | None = Field(
        default=None,
        ge=0,
    )
    max_fold_profit_loss_harm_count_vs_original: int | None = Field(
        default=None,
        ge=0,
    )
    min_fold_average_hit_probability_delta_vs_original: float = -0.025
    min_active_competition_fold_count: int = Field(default=4, ge=0)
    min_active_season_fold_count: int = Field(default=5, ge=0)
    min_active_rolling_fold_count: int = Field(default=4, ge=0)
    rolling_window_final_answer_count: int = Field(default=12, ge=1)
    rolling_window_step: int = Field(default=6, ge=1)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_no_production_change: bool = True
    max_report_folds: int = Field(default=120, ge=1, le=500)


class HistoricalShortOddsRollingAdmissionCheck(BaseModel):
    name: str
    status: HistoricalShortOddsRollingAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalShortOddsRollingAdmissionFold(BaseModel):
    fold_id: str
    fold_type: str
    status: HistoricalShortOddsRollingFoldStatus
    source_slice_ids: list[str] = Field(default_factory=list)
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    baseline_final_answer_hit_count: int = Field(ge=0)
    shadow_final_answer_hit_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    final_answer_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float
    harm_count_vs_original: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalShortOddsRollingAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalShortOddsRollingAdmissionStatus
    production_recommendation_allowed: bool
    shadow_allowed: bool
    source_audit_report_key: str
    source_rule_profile_version: str
    overall_runtime_shadow_report_key: str
    fold_count: int = Field(ge=0)
    active_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    checks: list[HistoricalShortOddsRollingAdmissionCheck] = Field(default_factory=list)
    folds: list[HistoricalShortOddsRollingAdmissionFold] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_short_odds_rolling_admission_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    options: HistoricalShortOddsRollingAdmissionOptions | None = None,
) -> HistoricalShortOddsRollingAdmissionReport:
    resolved_options = options or HistoricalShortOddsRollingAdmissionOptions()
    runtime_options = _runtime_options(resolved_options)
    overall_report = build_historical_short_odds_runtime_shadow_replay_report(
        audit_report,
        rule_set=rule_set,
        options=runtime_options,
    )
    folds = _fold_reports(
        audit_report,
        rule_set=rule_set,
        options=resolved_options,
    )
    checks = _checks(
        overall_report,
        folds=folds,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    status: HistoricalShortOddsRollingAdmissionStatus
    if not overall_report.passed:
        status = "rejected"
    elif failed_checks:
        status = "shadow_only"
    else:
        status = "accepted"
    active_folds = [fold for fold in folds if fold.status != "skipped"]
    failed_folds = [fold for fold in folds if fold.status == "failed"]
    production_allowed = status == "accepted"
    shadow_allowed = status in {"accepted", "shadow_only"}
    warnings = [
        f"short_odds_rolling_admission:failed_check:{check.name}"
        for check in failed_checks
    ]
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_rolling_admission_v3_1",
        "status": status,
        "production_recommendation_allowed": production_allowed,
        "shadow_allowed": shadow_allowed,
        "source_audit_report_key": audit_report.report_key,
        "source_rule_profile_version": rule_set.profile_version,
        "overall_runtime_shadow_report_key": overall_report.report_key,
        "overall_status": overall_report.status,
        "overall_passed": overall_report.passed,
        "overall_final_answer_count": overall_report.final_answer_count,
        "overall_changed_final_answer_count": (
            overall_report.changed_final_answer_count
        ),
        "overall_final_answer_hit_rate_delta": (
            overall_report.final_answer_hit_rate_delta
        ),
        "overall_roi_delta": overall_report.roi_delta,
        "overall_profit_loss_delta": overall_report.profit_loss_delta,
        "overall_harm_count_vs_original": overall_report.harm_count_vs_original,
        "overall_final_hit_harm_count_vs_original": (
            overall_report.final_hit_harm_count_vs_original
        ),
        "overall_profit_loss_harm_count_vs_original": (
            overall_report.profit_loss_harm_count_vs_original
        ),
        "overall_average_hit_probability_delta_vs_original": (
            overall_report.average_hit_probability_delta_vs_original
        ),
        "fold_count": len(folds),
        "active_fold_count": len(active_folds),
        "failed_fold_count": len(failed_folds),
        "active_competition_fold_count": _active_fold_count(folds, "competition"),
        "active_season_fold_count": _active_fold_count(folds, "season"),
        "active_rolling_fold_count": _active_fold_count(folds, "rolling_window"),
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, folds)
    return HistoricalShortOddsRollingAdmissionReport(
        report_key=report_key,
        status=status,
        production_recommendation_allowed=production_allowed,
        shadow_allowed=shadow_allowed,
        source_audit_report_key=audit_report.report_key,
        source_rule_profile_version=rule_set.profile_version,
        overall_runtime_shadow_report_key=overall_report.report_key,
        fold_count=len(folds),
        active_fold_count=len(active_folds),
        failed_fold_count=len(failed_folds),
        active_competition_fold_count=_active_fold_count(folds, "competition"),
        active_season_fold_count=_active_fold_count(folds, "season"),
        active_rolling_fold_count=_active_fold_count(folds, "rolling_window"),
        checks=checks,
        folds=folds[: resolved_options.max_report_folds],
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_short_odds_rolling_admission_report(
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
    if not report.production_recommendation_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _fold_reports(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> list[HistoricalShortOddsRollingAdmissionFold]:
    folds: list[HistoricalShortOddsRollingAdmissionFold] = []
    for competition_id, items in _groups_by_competition(audit_report.items).items():
        folds.append(
            _fold_report(
                f"competition:{competition_id}",
                "competition",
                items,
                audit_report=audit_report,
                rule_set=rule_set,
                options=options,
            )
        )
    for season_id, items in _groups_by_season(audit_report.items).items():
        folds.append(
            _fold_report(
                f"season:{season_id}",
                "season",
                items,
                audit_report=audit_report,
                rule_set=rule_set,
                options=options,
            )
        )
    for index, items in enumerate(_rolling_window_groups(audit_report.items, options)):
        slice_ids = _unique(item.slice_id for item in items)
        folds.append(
            _fold_report(
                f"rolling_window:{index + 1}:{slice_ids[0]}..{slice_ids[-1]}",
                "rolling_window",
                items,
                audit_report=audit_report,
                rule_set=rule_set,
                options=options,
            )
        )
    return folds


def _fold_report(
    fold_id: str,
    fold_type: str,
    items: Sequence[HistoricalCandidateMarginalAuditItem],
    *,
    audit_report: HistoricalCandidateMarginalAuditReport,
    rule_set: ShortOddsRuntimeRuleSet,
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> HistoricalShortOddsRollingAdmissionFold:
    fold_audit = _filtered_audit_report(audit_report, items=items, fold_id=fold_id)
    runtime_report = build_historical_short_odds_runtime_shadow_replay_report(
        fold_audit,
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            rule_ids=options.rule_ids,
            min_final_answer_count=1,
            min_changed_final_answer_count=0,
            min_final_answer_hit_rate_delta=options.min_fold_final_answer_hit_rate_delta,
            min_roi_delta=options.min_fold_roi_delta,
            min_profit_loss_delta=options.min_fold_profit_loss_delta,
            max_harm_count_vs_original=options.max_fold_harm_count_vs_original,
            max_final_hit_harm_count_vs_original=(
                _fold_final_hit_harm_threshold(options)
            ),
            max_profit_loss_harm_count_vs_original=(
                _fold_profit_loss_harm_threshold(options)
            ),
            min_average_hit_probability_delta_vs_original=(
                options.min_fold_average_hit_probability_delta_vs_original
            ),
        ),
    )
    failure_reasons = _fold_failure_reasons(runtime_report, options=options)
    skipped = (
        runtime_report.final_answer_count < options.min_fold_final_answer_count
        or runtime_report.changed_final_answer_count
        < options.min_fold_changed_final_answer_count
    )
    status: HistoricalShortOddsRollingFoldStatus = (
        "skipped" if skipped else "failed" if failure_reasons else "passed"
    )
    return HistoricalShortOddsRollingAdmissionFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status=status,
        source_slice_ids=_unique(item.slice_id for item in items),
        final_answer_count=runtime_report.final_answer_count,
        changed_final_answer_count=runtime_report.changed_final_answer_count,
        baseline_final_answer_hit_count=runtime_report.baseline_final_answer_hit_count,
        shadow_final_answer_hit_count=runtime_report.shadow_final_answer_hit_count,
        final_answer_hit_delta_count=runtime_report.final_answer_hit_delta_count,
        final_answer_hit_rate_delta=runtime_report.final_answer_hit_rate_delta,
        roi_delta=runtime_report.roi_delta,
        profit_loss_delta=runtime_report.profit_loss_delta,
        harm_count_vs_original=runtime_report.harm_count_vs_original,
        final_hit_harm_count_vs_original=(
            runtime_report.final_hit_harm_count_vs_original
        ),
        profit_loss_harm_count_vs_original=(
            runtime_report.profit_loss_harm_count_vs_original
        ),
        average_hit_probability_delta_vs_original=(
            runtime_report.average_hit_probability_delta_vs_original
        ),
        production_recommendation_changed=(
            runtime_report.production_recommendation_changed
        ),
        public_response_changed=runtime_report.public_response_changed,
        failure_reasons=[] if skipped else failure_reasons,
        summary_json={
            "runtime_report_key": runtime_report.report_key,
            "runtime_status": runtime_report.status,
            "runtime_passed": runtime_report.passed,
        },
    )


def _fold_failure_reasons(
    runtime_report: HistoricalShortOddsRuntimeShadowReplayReport,
    *,
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> list[str]:
    failures: list[str] = []
    if runtime_report.final_answer_hit_rate_delta is None or (
        runtime_report.final_answer_hit_rate_delta
        < options.min_fold_final_answer_hit_rate_delta
    ):
        failures.append("final_answer_hit_rate_delta_below_threshold")
    if runtime_report.roi_delta is None or runtime_report.roi_delta < options.min_fold_roi_delta:
        failures.append("roi_delta_below_threshold")
    if runtime_report.profit_loss_delta < options.min_fold_profit_loss_delta:
        failures.append("profit_loss_delta_below_threshold")
    if runtime_report.harm_count_vs_original > options.max_fold_harm_count_vs_original:
        failures.append("harm_count_vs_original_above_threshold")
    if (
        runtime_report.final_hit_harm_count_vs_original
        > _fold_final_hit_harm_threshold(options)
    ):
        failures.append("final_hit_harm_count_vs_original_above_threshold")
    if (
        runtime_report.profit_loss_harm_count_vs_original
        > _fold_profit_loss_harm_threshold(options)
    ):
        failures.append("profit_loss_harm_count_vs_original_above_threshold")
    if runtime_report.average_hit_probability_delta_vs_original is not None and (
        runtime_report.average_hit_probability_delta_vs_original
        < options.min_fold_average_hit_probability_delta_vs_original
    ):
        failures.append("average_hit_probability_delta_below_threshold")
    if runtime_report.production_recommendation_changed:
        failures.append("production_recommendation_changed")
    if runtime_report.public_response_changed:
        failures.append("public_response_changed")
    return failures


def _checks(
    overall_report: HistoricalShortOddsRuntimeShadowReplayReport,
    *,
    folds: Sequence[HistoricalShortOddsRollingAdmissionFold],
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> list[HistoricalShortOddsRollingAdmissionCheck]:
    failed_fold_count = sum(1 for fold in folds if fold.status == "failed")
    return [
        _boolean_check(
            name="overall_runtime_shadow_replay_passed",
            actual=overall_report.passed,
            expected=True,
            detail="overall guarded runtime replay must pass",
        ),
        _minimum_check(
            name="overall_final_answer_count",
            actual=overall_report.final_answer_count,
            threshold=options.min_overall_final_answer_count,
            detail="overall replay should cover enough final answers",
        ),
        _minimum_check(
            name="overall_changed_final_answer_count",
            actual=overall_report.changed_final_answer_count,
            threshold=options.min_overall_changed_final_answer_count,
            detail="overall replay should affect enough final answers",
        ),
        _minimum_check(
            name="overall_final_answer_hit_rate_delta",
            actual=overall_report.final_answer_hit_rate_delta,
            threshold=options.min_overall_final_answer_hit_rate_delta,
            detail="overall final-answer hit rate should not regress",
        ),
        _minimum_check(
            name="overall_roi_delta",
            actual=overall_report.roi_delta,
            threshold=options.min_overall_roi_delta,
            detail="overall ROI should not regress",
        ),
        _minimum_check(
            name="overall_profit_loss_delta",
            actual=overall_report.profit_loss_delta,
            threshold=options.min_overall_profit_loss_delta,
            detail="overall profit/loss should not regress",
        ),
        _maximum_check(
            name="overall_harm_count_vs_original",
            actual=overall_report.harm_count_vs_original,
            threshold=options.max_overall_harm_count_vs_original,
            detail=(
                "compatibility check: overall replay should not reduce "
                "final-answer profit/loss"
            ),
        ),
        _maximum_check(
            name="overall_final_hit_harm_count_vs_original",
            actual=overall_report.final_hit_harm_count_vs_original,
            threshold=_overall_final_hit_harm_threshold(options),
            detail="overall replay should not turn original hits into misses",
        ),
        _maximum_check(
            name="overall_profit_loss_harm_count_vs_original",
            actual=overall_report.profit_loss_harm_count_vs_original,
            threshold=_overall_profit_loss_harm_threshold(options),
            detail="overall replay should not reduce original final-answer profit/loss",
        ),
        _minimum_check(
            name="overall_average_hit_probability_delta_vs_original",
            actual=overall_report.average_hit_probability_delta_vs_original,
            threshold=options.min_overall_average_hit_probability_delta_vs_original,
            detail="overall expected hit-probability loss should be bounded",
        ),
        _maximum_check(
            name="failed_fold_count",
            actual=failed_fold_count,
            threshold=options.max_failed_fold_count,
            detail="rolling admission should not have failing active folds",
        ),
        _minimum_check(
            name="active_competition_fold_count",
            actual=_active_fold_count(folds, "competition"),
            threshold=options.min_active_competition_fold_count,
            detail="admission should validate enough active competition folds",
        ),
        _minimum_check(
            name="active_season_fold_count",
            actual=_active_fold_count(folds, "season"),
            threshold=options.min_active_season_fold_count,
            detail="admission should validate enough active season folds",
        ),
        _minimum_check(
            name="active_rolling_fold_count",
            actual=_active_fold_count(folds, "rolling_window"),
            threshold=options.min_active_rolling_fold_count,
            detail="admission should validate enough rolling-window folds",
        ),
        _boolean_check(
            name="no_production_recommendation_change",
            actual=not overall_report.production_recommendation_changed,
            expected=True,
            detail="rolling admission must not change production recommendations",
        )
        if options.require_no_production_change
        else _skipped_boolean_check("no_production_recommendation_change"),
        _boolean_check(
            name="no_public_response_change",
            actual=not overall_report.public_response_changed,
            expected=True,
            detail="rolling admission must not change public responses",
        ),
    ]


def _runtime_options(
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> HistoricalShortOddsRuntimeShadowReplayOptions:
    return HistoricalShortOddsRuntimeShadowReplayOptions(
        enable_shadow_replay=True,
        rule_ids=options.rule_ids,
        min_final_answer_count=options.min_overall_final_answer_count,
        min_changed_final_answer_count=options.min_overall_changed_final_answer_count,
        min_final_answer_hit_rate_delta=options.min_overall_final_answer_hit_rate_delta,
        min_roi_delta=options.min_overall_roi_delta,
        min_profit_loss_delta=options.min_overall_profit_loss_delta,
        max_harm_count_vs_original=options.max_overall_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            _overall_final_hit_harm_threshold(options)
        ),
        max_profit_loss_harm_count_vs_original=(
            _overall_profit_loss_harm_threshold(options)
        ),
        min_average_hit_probability_delta_vs_original=(
            options.min_overall_average_hit_probability_delta_vs_original
        ),
    )


def _overall_final_hit_harm_threshold(
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> int:
    return (
        options.max_overall_final_hit_harm_count_vs_original
        if options.max_overall_final_hit_harm_count_vs_original is not None
        else options.max_overall_harm_count_vs_original
    )


def _overall_profit_loss_harm_threshold(
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> int:
    return (
        options.max_overall_profit_loss_harm_count_vs_original
        if options.max_overall_profit_loss_harm_count_vs_original is not None
        else options.max_overall_harm_count_vs_original
    )


def _fold_final_hit_harm_threshold(
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> int:
    return (
        options.max_fold_final_hit_harm_count_vs_original
        if options.max_fold_final_hit_harm_count_vs_original is not None
        else options.max_fold_harm_count_vs_original
    )


def _fold_profit_loss_harm_threshold(
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> int:
    return (
        options.max_fold_profit_loss_harm_count_vs_original
        if options.max_fold_profit_loss_harm_count_vs_original is not None
        else options.max_fold_harm_count_vs_original
    )


def _groups_by_competition(
    items: Sequence[HistoricalCandidateMarginalAuditItem],
) -> dict[str, list[HistoricalCandidateMarginalAuditItem]]:
    grouped: dict[str, list[HistoricalCandidateMarginalAuditItem]] = {}
    for item in items:
        grouped.setdefault(item.competition_id, []).append(item)
    return dict(sorted(grouped.items()))


def _groups_by_season(
    items: Sequence[HistoricalCandidateMarginalAuditItem],
) -> dict[str, list[HistoricalCandidateMarginalAuditItem]]:
    grouped: dict[str, list[HistoricalCandidateMarginalAuditItem]] = {}
    for item in items:
        grouped.setdefault(_season_id(item.slice_id), []).append(item)
    return dict(sorted(grouped.items()))


def _rolling_window_groups(
    items: Sequence[HistoricalCandidateMarginalAuditItem],
    options: HistoricalShortOddsRollingAdmissionOptions,
) -> list[list[HistoricalCandidateMarginalAuditItem]]:
    by_slice: dict[str, list[HistoricalCandidateMarginalAuditItem]] = {}
    for item in items:
        by_slice.setdefault(item.slice_id, []).append(item)
    ordered_slice_ids = sorted(
        by_slice,
        key=lambda slice_id: (_season_sort_key(slice_id), slice_id),
    )
    windows: list[list[HistoricalCandidateMarginalAuditItem]] = []
    for start in range(0, len(ordered_slice_ids), options.rolling_window_step):
        window_slice_ids = ordered_slice_ids[
            start : start + options.rolling_window_final_answer_count
        ]
        if len(window_slice_ids) < options.rolling_window_final_answer_count:
            break
        windows.append(
            [
                item
                for slice_id in window_slice_ids
                for item in by_slice.get(slice_id, [])
            ]
        )
    return windows


def _filtered_audit_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    items: Sequence[HistoricalCandidateMarginalAuditItem],
    fold_id: str,
) -> HistoricalCandidateMarginalAuditReport:
    resolved_items = list(items)
    slice_ids = set(item.slice_id for item in resolved_items)
    competition_ids = set(item.competition_id for item in resolved_items)
    final_answer_keys = {
        f"{item.slice_id}:{item.final_answer_scenario_key}" for item in resolved_items
    }
    model_top_replacements = [
        item.model_top_replacement
        for item in resolved_items
        if item.model_top_replacement is not None
    ]
    return audit_report.model_copy(
        update={
            "report_key": f"{audit_report.report_key}:{fold_id}",
            "slice_count": len(slice_ids),
            "competition_count": len(competition_ids),
            "final_answer_count": len(final_answer_keys),
            "selected_leg_count": len(resolved_items),
            "missed_leg_count": sum(1 for item in resolved_items if not item.leg_actual_hit),
            "replacement_simulation_count": sum(
                item.replacement_count for item in resolved_items
            ),
            "actual_replacement_opportunity_count": sum(
                1
                for item in resolved_items
                if item.actual_best_replacement is not None
                and item.actual_best_replacement.decision == "actual_improved"
            ),
            "model_top_replacement_count": len(model_top_replacements),
            "model_top_actual_improvement_count": sum(
                1
                for replacement in model_top_replacements
                if replacement.decision == "actual_improved"
            ),
            "model_top_actual_harm_count": sum(
                1
                for replacement in model_top_replacements
                if replacement.decision == "actual_regressed"
            ),
            "average_model_top_profit_loss_delta": _average(
                replacement.profit_loss_delta for replacement in model_top_replacements
            ),
            "average_model_top_hit_probability_delta": _average(
                replacement.hit_probability_delta for replacement in model_top_replacements
            ),
            "items": resolved_items,
            "top_actual_replacement_opportunities": [
                item
                for item in audit_report.top_actual_replacement_opportunities
                if item.item_key in {resolved.item_key for resolved in resolved_items}
            ],
            "top_model_replacement_opportunities": [
                item
                for item in audit_report.top_model_replacement_opportunities
                if item.item_key in {resolved.item_key for resolved in resolved_items}
            ],
            "summary_json": {
                **audit_report.summary_json,
                "fold_id": fold_id,
                "source_audit_report_key": audit_report.report_key,
            },
        }
    )


def _season_id(slice_id: str) -> str:
    match = search(r"_(\d{4}(?:_\d{4})?)_", slice_id)
    return match.group(1) if match else "unknown"


def _season_sort_key(slice_id: str) -> tuple[int, str]:
    season = _season_id(slice_id)
    match = search(r"\d{4}", season)
    return (int(match.group(0)) if match else 0, slice_id)


def _active_fold_count(
    folds: Sequence[HistoricalShortOddsRollingAdmissionFold],
    fold_type: str,
) -> int:
    return sum(
        1 for fold in folds if fold.fold_type == fold_type and fold.status != "skipped"
    )


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> HistoricalShortOddsRollingAdmissionCheck:
    return HistoricalShortOddsRollingAdmissionCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _skipped_boolean_check(name: str) -> HistoricalShortOddsRollingAdmissionCheck:
    return HistoricalShortOddsRollingAdmissionCheck(
        name=name,
        status="passed",
        actual=None,
        threshold="not_required",
        detail="check disabled by options",
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalShortOddsRollingAdmissionCheck:
    if actual is None:
        return HistoricalShortOddsRollingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRollingAdmissionCheck(
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
) -> HistoricalShortOddsRollingAdmissionCheck:
    if actual is None:
        return HistoricalShortOddsRollingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRollingAdmissionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Run rolling/holdout admission for guarded short-odds rules."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--rule-ids",
        default="",
        help="Comma-separated rule ids. Empty means all enabled rules.",
    )
    parser.add_argument("--min-overall-final-answer-count", type=int, default=30)
    parser.add_argument("--min-overall-changed-final-answer-count", type=int, default=5)
    parser.add_argument("--min-overall-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-overall-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-overall-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-overall-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-overall-final-hit-harm-count-vs-original", type=int)
    parser.add_argument("--max-overall-profit-loss-harm-count-vs-original", type=int)
    parser.add_argument(
        "--min-overall-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--min-fold-final-answer-count", type=int, default=1)
    parser.add_argument("--min-fold-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-fold-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-fold-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-fold-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-fold-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-fold-final-hit-harm-count-vs-original", type=int)
    parser.add_argument("--max-fold-profit-loss-harm-count-vs-original", type=int)
    parser.add_argument(
        "--min-fold-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.025,
    )
    parser.add_argument("--min-active-competition-fold-count", type=int, default=4)
    parser.add_argument("--min-active-season-fold-count", type=int, default=5)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=4)
    parser.add_argument("--rolling-window-final-answer-count", type=int, default=12)
    parser.add_argument("--rolling-window-step", type=int, default=6)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalShortOddsRollingAdmissionOptions:
    return HistoricalShortOddsRollingAdmissionOptions(
        rule_ids=_csv_values(args.rule_ids),
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


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalShortOddsRollingAdmissionCheck],
    folds: Sequence[HistoricalShortOddsRollingAdmissionFold],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "folds": [fold.model_dump(mode="json") for fold in folds],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_short_odds_rolling_admission:{digest}"
