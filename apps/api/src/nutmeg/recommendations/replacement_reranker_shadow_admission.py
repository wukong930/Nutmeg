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
from nutmeg.recommendations.replacement_reranker_shadow_gate import (
    HistoricalReplacementRerankerShadowGateOptions,
    HistoricalReplacementRerankerShadowGateReport,
    build_historical_replacement_reranker_shadow_gate_report,
    load_historical_replacement_reranker_tolerance_grid_report,
)
from nutmeg.recommendations.replacement_reranker_tolerance_grid import (
    HistoricalReplacementRerankerToleranceGridReport,
)

type HistoricalReplacementRerankerShadowAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalReplacementRerankerShadowAdmissionCheckStatus = Literal[
    "passed",
    "failed",
]
type HistoricalReplacementRerankerShadowAdmissionFoldStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalReplacementRerankerShadowAdmissionOptions(BaseModel):
    profile_id: str = "quality_edge_blend_v1"
    hit_probability_delta_threshold: float = -0.02
    min_actual_best_profit_loss_delta: float = 0.0
    min_profit_loss_gap: float = 0.0
    scope_competition_ids: tuple[str, ...] = ()
    scope_season_ids: tuple[str, ...] = ()
    scope_min_competition_season_index: int | None = Field(default=None, ge=1)
    scope_max_competition_season_index: int | None = Field(default=None, ge=1)
    min_overall_final_answer_count: int = Field(default=20, ge=1)
    min_overall_changed_from_model_top_count: int = Field(default=4, ge=0)
    min_overall_final_answer_hit_delta_vs_model_top: int = 0
    min_overall_replacement_leg_hit_delta_vs_model_top: int = 0
    min_overall_profit_loss_delta_vs_model_top: float = 0.0
    min_overall_roi_delta_vs_model_top: float = 0.0
    max_overall_harm_count_vs_model_top: int = Field(default=0, ge=0)
    max_overall_final_hit_harm_count_vs_model_top: int | None = Field(
        default=None,
        ge=0,
    )
    max_overall_profit_loss_harm_count_vs_model_top: int | None = Field(
        default=None,
        ge=0,
    )
    min_overall_average_hit_probability_delta_vs_model_top: float = -0.02
    min_overall_final_answer_hit_delta_vs_original: int | None = None
    min_overall_profit_loss_delta_vs_original: float | None = None
    min_overall_roi_delta_vs_original: float | None = None
    max_overall_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_overall_final_hit_harm_count_vs_original: int | None = Field(
        default=None,
        ge=0,
    )
    max_overall_profit_loss_harm_count_vs_original: int | None = Field(
        default=None,
        ge=0,
    )
    min_overall_average_hit_probability_delta_vs_original: float | None = None
    min_fold_final_answer_count: int = Field(default=1, ge=1)
    min_fold_changed_from_model_top_count: int = Field(default=1, ge=0)
    min_fold_final_answer_hit_delta_vs_model_top: int = 0
    min_fold_replacement_leg_hit_delta_vs_model_top: int = 0
    min_fold_profit_loss_delta_vs_model_top: float = 0.0
    min_fold_roi_delta_vs_model_top: float = 0.0
    max_fold_harm_count_vs_model_top: int = Field(default=0, ge=0)
    max_fold_final_hit_harm_count_vs_model_top: int | None = Field(
        default=None,
        ge=0,
    )
    max_fold_profit_loss_harm_count_vs_model_top: int | None = Field(
        default=None,
        ge=0,
    )
    min_fold_average_hit_probability_delta_vs_model_top: float = -0.025
    min_fold_final_answer_hit_delta_vs_original: int | None = None
    min_fold_profit_loss_delta_vs_original: float | None = None
    min_fold_roi_delta_vs_original: float | None = None
    max_fold_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_fold_final_hit_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_fold_profit_loss_harm_count_vs_original: int | None = Field(default=None, ge=0)
    min_fold_average_hit_probability_delta_vs_original: float | None = None
    min_active_competition_fold_count: int = Field(default=2, ge=0)
    min_active_season_fold_count: int = Field(default=2, ge=0)
    min_active_rolling_fold_count: int = Field(default=2, ge=0)
    rolling_window_slice_count: int = Field(default=8, ge=1)
    rolling_window_step: int = Field(default=4, ge=1)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_prematch_source_surface: bool = False
    require_tolerance_candidate: bool = True
    allowed_tolerance_statuses: tuple[str, ...] = ("candidate", "watchlist")
    require_no_production_change: bool = True
    max_report_folds: int = Field(default=120, ge=1, le=500)


class HistoricalReplacementRerankerShadowAdmissionCheck(BaseModel):
    name: str
    status: HistoricalReplacementRerankerShadowAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalReplacementRerankerShadowAdmissionFold(BaseModel):
    fold_id: str
    fold_type: str
    status: HistoricalReplacementRerankerShadowAdmissionFoldStatus
    source_slice_ids: list[str] = Field(default_factory=list)
    shadow_final_answer_count: int = Field(ge=0)
    changed_from_model_top_count: int = Field(ge=0)
    original_final_answer_hit_count: int = Field(ge=0)
    model_top_final_answer_hit_count: int = Field(ge=0)
    shadow_final_answer_hit_count: int = Field(ge=0)
    hit_delta_vs_original_count: int
    hit_delta_vs_model_top_count: int
    replacement_leg_hit_delta_vs_model_top_count: int
    roi_delta_vs_original: float | None = None
    roi_delta_vs_model_top: float | None = None
    profit_loss_delta_vs_original: float
    profit_loss_delta_vs_model_top: float
    harm_count_vs_original: int = Field(ge=0)
    harm_count_vs_model_top: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    final_hit_harm_count_vs_model_top: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_model_top: int = Field(default=0, ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementRerankerShadowAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalReplacementRerankerShadowAdmissionStatus
    runtime_profile_candidate_allowed: bool
    shadow_allowed: bool
    source_audit_report_key: str
    source_tolerance_grid_report_key: str
    overall_shadow_gate_report_key: str
    profile_id: str
    hit_probability_delta_threshold: float
    fold_count: int = Field(ge=0)
    active_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    checks: list[HistoricalReplacementRerankerShadowAdmissionCheck] = Field(
        default_factory=list
    )
    folds: list[HistoricalReplacementRerankerShadowAdmissionFold] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_replacement_reranker_shadow_admission_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    tolerance_grid_report: HistoricalReplacementRerankerToleranceGridReport,
    options: HistoricalReplacementRerankerShadowAdmissionOptions | None = None,
) -> HistoricalReplacementRerankerShadowAdmissionReport:
    resolved_options = options or HistoricalReplacementRerankerShadowAdmissionOptions()
    scoped_audit_report = _scoped_audit_report(audit_report, options=resolved_options)
    scope_summary = _scope_summary(
        audit_report,
        scoped_audit_report,
        options=resolved_options,
    )
    source_surface_summary = _source_surface_summary(audit_report)
    overall_report = build_historical_replacement_reranker_shadow_gate_report(
        scoped_audit_report,
        tolerance_grid_report=tolerance_grid_report,
        options=_overall_shadow_options(resolved_options),
    )
    folds = _fold_reports(
        scoped_audit_report,
        tolerance_grid_report=tolerance_grid_report,
        options=resolved_options,
    )
    checks = _checks(
        overall_report,
        folds=folds,
        options=resolved_options,
        source_surface_summary=source_surface_summary,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    failed_folds = [fold for fold in folds if fold.status == "failed"]
    active_folds = [fold for fold in folds if fold.status != "skipped"]
    if not overall_report.passed:
        status: HistoricalReplacementRerankerShadowAdmissionStatus = "rejected"
    elif failed_checks:
        status = "shadow_only"
    else:
        status = "accepted"
    runtime_profile_allowed = status == "accepted"
    shadow_allowed = status in {"accepted", "shadow_only"}
    warnings = _scope_warnings(scope_summary) + [
        f"replacement_reranker_shadow_admission:failed_check:{check.name}"
        for check in failed_checks
    ]
    summary: dict[str, object] = {
        "calculation_basis": "historical_replacement_reranker_shadow_admission_v3_1",
        "status": status,
        "runtime_profile_candidate_allowed": runtime_profile_allowed,
        "shadow_allowed": shadow_allowed,
        "source_audit_report_key": audit_report.report_key,
        "source_tolerance_grid_report_key": tolerance_grid_report.report_key,
        "overall_shadow_gate_report_key": overall_report.report_key,
        "source_surface": source_surface_summary,
        "source_surface_kind": source_surface_summary["kind"],
        "source_surface_missed_legs_only": (
            source_surface_summary["missed_legs_only"]
        ),
        "scope": scope_summary,
        "overall_status": overall_report.status,
        "overall_passed": overall_report.passed,
        "overall_shadow_final_answer_count": overall_report.shadow_final_answer_count,
        "overall_changed_from_model_top_count": (
            overall_report.changed_from_model_top_count
        ),
        "overall_hit_delta_vs_model_top_count": (
            overall_report.hit_delta_vs_model_top_count
        ),
        "overall_hit_delta_vs_original_count": (
            overall_report.hit_delta_vs_original_count
        ),
        "overall_replacement_leg_hit_delta_vs_model_top_count": (
            overall_report.replacement_leg_hit_delta_vs_model_top_count
        ),
        "overall_roi_delta_vs_original": overall_report.roi_delta_vs_original,
        "overall_roi_delta_vs_model_top": overall_report.roi_delta_vs_model_top,
        "overall_profit_loss_delta_vs_original": (
            overall_report.profit_loss_delta_vs_original
        ),
        "overall_profit_loss_delta_vs_model_top": (
            overall_report.profit_loss_delta_vs_model_top
        ),
        "overall_harm_count_vs_original": overall_report.harm_count_vs_original,
        "overall_harm_count_vs_model_top": overall_report.harm_count_vs_model_top,
        "overall_final_hit_harm_count_vs_original": (
            overall_report.final_hit_harm_count_vs_original
        ),
        "overall_final_hit_harm_count_vs_model_top": (
            overall_report.final_hit_harm_count_vs_model_top
        ),
        "overall_profit_loss_harm_count_vs_original": (
            overall_report.profit_loss_harm_count_vs_original
        ),
        "overall_profit_loss_harm_count_vs_model_top": (
            overall_report.profit_loss_harm_count_vs_model_top
        ),
        "overall_average_hit_probability_delta_vs_original": (
            overall_report.average_hit_probability_delta_vs_original
        ),
        "overall_average_hit_probability_delta_vs_model_top": (
            overall_report.average_hit_probability_delta_vs_model_top
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
    return HistoricalReplacementRerankerShadowAdmissionReport(
        report_key=report_key,
        status=status,
        runtime_profile_candidate_allowed=runtime_profile_allowed,
        shadow_allowed=shadow_allowed,
        source_audit_report_key=audit_report.report_key,
        source_tolerance_grid_report_key=tolerance_grid_report.report_key,
        overall_shadow_gate_report_key=overall_report.report_key,
        profile_id=resolved_options.profile_id,
        hit_probability_delta_threshold=(
            resolved_options.hit_probability_delta_threshold
        ),
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
    report = build_historical_replacement_reranker_shadow_admission_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        tolerance_grid_report=load_historical_replacement_reranker_tolerance_grid_report(
            args.tolerance_grid_report
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
    if not report.runtime_profile_candidate_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _scoped_audit_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> HistoricalCandidateMarginalAuditReport:
    if not _scope_enabled(options):
        return audit_report
    competition_season_indexes = _competition_season_index_map(audit_report.items)
    scoped_items = [
        item
        for item in audit_report.items
        if _item_in_scope(
            item,
            competition_season_indexes=competition_season_indexes,
            options=options,
        )
    ]
    scoped_report = _filtered_audit_report(
        audit_report,
        items=scoped_items,
        fold_id="scope",
    )
    return scoped_report.model_copy(
        update={
            "report_key": audit_report.report_key,
            "summary_json": {
                **audit_report.summary_json,
                "scope_enabled": True,
                "source_audit_report_key": audit_report.report_key,
            },
        }
    )


def _scope_enabled(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> bool:
    return bool(
        options.scope_competition_ids
        or options.scope_season_ids
        or options.scope_min_competition_season_index is not None
        or options.scope_max_competition_season_index is not None
    )


def _item_in_scope(
    item: HistoricalCandidateMarginalAuditItem,
    *,
    competition_season_indexes: Mapping[tuple[str, str], int],
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> bool:
    season_id = _season_id(item.slice_id)
    competition_season_index = competition_season_indexes.get(
        (item.competition_id, season_id)
    )
    if (
        options.scope_competition_ids
        and item.competition_id not in options.scope_competition_ids
    ):
        return False
    if options.scope_season_ids and season_id not in options.scope_season_ids:
        return False
    if (
        options.scope_min_competition_season_index is not None
        and (
            competition_season_index is None
            or competition_season_index
            < options.scope_min_competition_season_index
        )
    ):
        return False
    return not (
        options.scope_max_competition_season_index is not None
        and (
            competition_season_index is None
            or competition_season_index
            > options.scope_max_competition_season_index
        )
    )


def _scope_summary(
    source_report: HistoricalCandidateMarginalAuditReport,
    scoped_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> dict[str, object]:
    source_items = source_report.items
    scoped_items = scoped_report.items
    competition_season_indexes = _competition_season_index_map(source_items)
    scoped_competition_ids = sorted({item.competition_id for item in scoped_items})
    scoped_season_ids = sorted(
        {_season_id(item.slice_id) for item in scoped_items},
        key=_season_id_sort_key,
    )
    return {
        "enabled": _scope_enabled(options),
        "competition_ids": list(options.scope_competition_ids),
        "season_ids": list(options.scope_season_ids),
        "min_competition_season_index": (
            options.scope_min_competition_season_index
        ),
        "max_competition_season_index": (
            options.scope_max_competition_season_index
        ),
        "source_item_count": len(source_items),
        "scoped_item_count": len(scoped_items),
        "source_slice_count": len({item.slice_id for item in source_items}),
        "scoped_slice_count": len({item.slice_id for item in scoped_items}),
        "source_final_answer_count": len(
            {
                f"{item.slice_id}:{item.final_answer_scenario_key}"
                for item in source_items
            }
        ),
        "scoped_final_answer_count": len(
            {
                f"{item.slice_id}:{item.final_answer_scenario_key}"
                for item in scoped_items
            }
        ),
        "scoped_competition_ids": scoped_competition_ids,
        "scoped_season_ids": scoped_season_ids,
        "scoped_competition_season_indexes": _competition_season_index_summary(
            scoped_items,
            competition_season_indexes=competition_season_indexes,
        ),
    }


def _scope_warnings(scope_summary: Mapping[str, object]) -> list[str]:
    if scope_summary.get("enabled") and scope_summary.get("scoped_item_count") == 0:
        return ["replacement_reranker_shadow_admission:empty_scope"]
    return []


def _source_surface_summary(
    audit_report: HistoricalCandidateMarginalAuditReport,
) -> dict[str, object]:
    target_filter = audit_report.summary_json.get("target_filter")
    target_filter_json = target_filter if isinstance(target_filter, dict) else {}
    missed_legs_only = _mapping_bool(target_filter_json, "missed_legs_only")
    if missed_legs_only is True:
        kind = "missed_leg_diagnostic_surface"
    elif missed_legs_only is False:
        kind = "prematch_replacement_surface"
    else:
        kind = "unknown"
    return {
        "kind": kind,
        "source_audit_report_key": audit_report.report_key,
        "missed_legs_only": missed_legs_only,
        "target_filter": target_filter_json,
        "final_answer_count": audit_report.final_answer_count,
        "selected_leg_count": audit_report.selected_leg_count,
        "missed_leg_count": audit_report.missed_leg_count,
        "replacement_simulation_count": audit_report.replacement_simulation_count,
        "actual_replacement_opportunity_count": (
            audit_report.actual_replacement_opportunity_count
        ),
        "model_top_replacement_count": audit_report.model_top_replacement_count,
        "model_top_actual_improvement_count": (
            audit_report.model_top_actual_improvement_count
        ),
        "model_top_actual_harm_count": audit_report.model_top_actual_harm_count,
    }


def _mapping_bool(mapping: Mapping[str, object], key: str) -> bool | None:
    value = mapping.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _competition_season_index_map(
    items: Sequence[HistoricalCandidateMarginalAuditItem],
) -> dict[tuple[str, str], int]:
    seasons_by_competition: dict[str, set[str]] = {}
    for item in items:
        seasons_by_competition.setdefault(item.competition_id, set()).add(
            _season_id(item.slice_id)
        )
    indexes: dict[tuple[str, str], int] = {}
    for competition_id, season_ids in seasons_by_competition.items():
        for index, season_id in enumerate(
            sorted(season_ids, key=_season_id_sort_key),
            start=1,
        ):
            indexes[(competition_id, season_id)] = index
    return indexes


def _competition_season_index_summary(
    items: Sequence[HistoricalCandidateMarginalAuditItem],
    *,
    competition_season_indexes: Mapping[tuple[str, str], int],
) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    summary: list[dict[str, object]] = []
    for item in sorted(
        items,
        key=lambda value: (
            value.competition_id,
            _season_id_sort_key(_season_id(value.slice_id)),
        ),
    ):
        season_id = _season_id(item.slice_id)
        key = (item.competition_id, season_id)
        if key in seen:
            continue
        seen.add(key)
        summary.append(
            {
                "competition_id": item.competition_id,
                "season_id": season_id,
                "competition_season_index": competition_season_indexes.get(key),
            }
        )
    return summary


def _fold_reports(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    tolerance_grid_report: HistoricalReplacementRerankerToleranceGridReport,
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> list[HistoricalReplacementRerankerShadowAdmissionFold]:
    folds: list[HistoricalReplacementRerankerShadowAdmissionFold] = []
    for competition_id, items in _groups_by_competition(audit_report.items).items():
        folds.append(
            _fold_report(
                f"competition:{competition_id}",
                "competition",
                items,
                audit_report=audit_report,
                tolerance_grid_report=tolerance_grid_report,
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
                tolerance_grid_report=tolerance_grid_report,
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
                tolerance_grid_report=tolerance_grid_report,
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
    tolerance_grid_report: HistoricalReplacementRerankerToleranceGridReport,
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> HistoricalReplacementRerankerShadowAdmissionFold:
    fold_audit = _filtered_audit_report(audit_report, items=items, fold_id=fold_id)
    shadow_report = build_historical_replacement_reranker_shadow_gate_report(
        fold_audit,
        tolerance_grid_report=tolerance_grid_report,
        options=_fold_shadow_options(options),
    )
    skipped = (
        shadow_report.shadow_final_answer_count < options.min_fold_final_answer_count
        or shadow_report.changed_from_model_top_count
        < options.min_fold_changed_from_model_top_count
    )
    failure_reasons = _fold_failure_reasons(shadow_report, options=options)
    status: HistoricalReplacementRerankerShadowAdmissionFoldStatus = (
        "skipped" if skipped else "failed" if failure_reasons else "passed"
    )
    return HistoricalReplacementRerankerShadowAdmissionFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status=status,
        source_slice_ids=_unique(item.slice_id for item in items),
        shadow_final_answer_count=shadow_report.shadow_final_answer_count,
        changed_from_model_top_count=shadow_report.changed_from_model_top_count,
        original_final_answer_hit_count=(
            shadow_report.original_final_answer_hit_count
        ),
        model_top_final_answer_hit_count=shadow_report.model_top_final_answer_hit_count,
        shadow_final_answer_hit_count=shadow_report.shadow_final_answer_hit_count,
        hit_delta_vs_original_count=shadow_report.hit_delta_vs_original_count,
        hit_delta_vs_model_top_count=shadow_report.hit_delta_vs_model_top_count,
        replacement_leg_hit_delta_vs_model_top_count=(
            shadow_report.replacement_leg_hit_delta_vs_model_top_count
        ),
        roi_delta_vs_original=shadow_report.roi_delta_vs_original,
        roi_delta_vs_model_top=shadow_report.roi_delta_vs_model_top,
        profit_loss_delta_vs_original=shadow_report.profit_loss_delta_vs_original,
        profit_loss_delta_vs_model_top=shadow_report.profit_loss_delta_vs_model_top,
        harm_count_vs_original=shadow_report.harm_count_vs_original,
        harm_count_vs_model_top=shadow_report.harm_count_vs_model_top,
        final_hit_harm_count_vs_original=(
            shadow_report.final_hit_harm_count_vs_original
        ),
        final_hit_harm_count_vs_model_top=(
            shadow_report.final_hit_harm_count_vs_model_top
        ),
        profit_loss_harm_count_vs_original=(
            shadow_report.profit_loss_harm_count_vs_original
        ),
        profit_loss_harm_count_vs_model_top=(
            shadow_report.profit_loss_harm_count_vs_model_top
        ),
        average_hit_probability_delta_vs_original=(
            shadow_report.average_hit_probability_delta_vs_original
        ),
        average_hit_probability_delta_vs_model_top=(
            shadow_report.average_hit_probability_delta_vs_model_top
        ),
        production_recommendation_changed=(
            shadow_report.production_recommendation_changed
        ),
        public_response_changed=shadow_report.public_response_changed,
        failure_reasons=[] if skipped else failure_reasons,
        summary_json={
            "shadow_gate_report_key": shadow_report.report_key,
            "shadow_gate_status": shadow_report.status,
            "shadow_gate_passed": shadow_report.passed,
        },
    )


def _fold_failure_reasons(
    shadow_report: HistoricalReplacementRerankerShadowGateReport,
    *,
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> list[str]:
    failures: list[str] = []
    if (
        shadow_report.hit_delta_vs_model_top_count
        < options.min_fold_final_answer_hit_delta_vs_model_top
    ):
        failures.append("final_answer_hit_delta_vs_model_top_below_threshold")
    if (
        shadow_report.replacement_leg_hit_delta_vs_model_top_count
        < options.min_fold_replacement_leg_hit_delta_vs_model_top
    ):
        failures.append("replacement_leg_hit_delta_vs_model_top_below_threshold")
    if (
        shadow_report.roi_delta_vs_model_top is None
        or shadow_report.roi_delta_vs_model_top < options.min_fold_roi_delta_vs_model_top
    ):
        failures.append("roi_delta_vs_model_top_below_threshold")
    if (
        shadow_report.profit_loss_delta_vs_model_top
        < options.min_fold_profit_loss_delta_vs_model_top
    ):
        failures.append("profit_loss_delta_vs_model_top_below_threshold")
    if shadow_report.harm_count_vs_model_top > options.max_fold_harm_count_vs_model_top:
        failures.append("harm_count_vs_model_top_above_threshold")
    if (
        shadow_report.final_hit_harm_count_vs_model_top
        > _max_fold_final_hit_harm_count_vs_model_top(options)
    ):
        failures.append("final_hit_harm_count_vs_model_top_above_threshold")
    if (
        shadow_report.profit_loss_harm_count_vs_model_top
        > _max_fold_profit_loss_harm_count_vs_model_top(options)
    ):
        failures.append("profit_loss_harm_count_vs_model_top_above_threshold")
    if (
        shadow_report.average_hit_probability_delta_vs_model_top is not None
        and shadow_report.average_hit_probability_delta_vs_model_top
        < options.min_fold_average_hit_probability_delta_vs_model_top
    ):
        failures.append("average_hit_probability_delta_vs_model_top_below_threshold")
    if (
        options.min_fold_final_answer_hit_delta_vs_original is not None
        and shadow_report.hit_delta_vs_original_count
        < options.min_fold_final_answer_hit_delta_vs_original
    ):
        failures.append("final_answer_hit_delta_vs_original_below_threshold")
    if (
        options.min_fold_profit_loss_delta_vs_original is not None
        and shadow_report.profit_loss_delta_vs_original
        < options.min_fold_profit_loss_delta_vs_original
    ):
        failures.append("profit_loss_delta_vs_original_below_threshold")
    if (
        options.min_fold_roi_delta_vs_original is not None
        and (
            shadow_report.roi_delta_vs_original is None
            or shadow_report.roi_delta_vs_original
            < options.min_fold_roi_delta_vs_original
        )
    ):
        failures.append("roi_delta_vs_original_below_threshold")
    if (
        options.max_fold_harm_count_vs_original is not None
        and shadow_report.harm_count_vs_original > options.max_fold_harm_count_vs_original
    ):
        failures.append("harm_count_vs_original_above_threshold")
    max_fold_final_hit_harm_count_vs_original = (
        _max_fold_final_hit_harm_count_vs_original(options)
    )
    if (
        max_fold_final_hit_harm_count_vs_original is not None
        and shadow_report.final_hit_harm_count_vs_original
        > max_fold_final_hit_harm_count_vs_original
    ):
        failures.append("final_hit_harm_count_vs_original_above_threshold")
    max_fold_profit_loss_harm_count_vs_original = (
        _max_fold_profit_loss_harm_count_vs_original(options)
    )
    if (
        max_fold_profit_loss_harm_count_vs_original is not None
        and shadow_report.profit_loss_harm_count_vs_original
        > max_fold_profit_loss_harm_count_vs_original
    ):
        failures.append("profit_loss_harm_count_vs_original_above_threshold")
    if (
        options.min_fold_average_hit_probability_delta_vs_original is not None
        and shadow_report.average_hit_probability_delta_vs_original is not None
        and shadow_report.average_hit_probability_delta_vs_original
        < options.min_fold_average_hit_probability_delta_vs_original
    ):
        failures.append("average_hit_probability_delta_vs_original_below_threshold")
    if shadow_report.production_recommendation_changed:
        failures.append("production_recommendation_changed")
    if shadow_report.public_response_changed:
        failures.append("public_response_changed")
    return failures


def _checks(
    overall_report: HistoricalReplacementRerankerShadowGateReport,
    *,
    folds: Sequence[HistoricalReplacementRerankerShadowAdmissionFold],
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
    source_surface_summary: Mapping[str, object],
) -> list[HistoricalReplacementRerankerShadowAdmissionCheck]:
    failed_fold_count = sum(1 for fold in folds if fold.status == "failed")
    return [
        _source_surface_prematch_check(
            source_surface_summary,
            required=options.require_prematch_source_surface,
        ),
        _boolean_check(
            name="overall_shadow_gate_passed",
            actual=overall_report.passed,
            expected=True,
            detail="overall replacement reranker shadow gate must pass",
        ),
        _minimum_check(
            name="overall_shadow_final_answer_count",
            actual=overall_report.shadow_final_answer_count,
            threshold=options.min_overall_final_answer_count,
            detail="overall shadow gate should cover enough targeted final answers",
        ),
        _minimum_check(
            name="overall_changed_from_model_top_count",
            actual=overall_report.changed_from_model_top_count,
            threshold=options.min_overall_changed_from_model_top_count,
            detail="overall shadow gate should rerank enough model-top replacements",
        ),
        _minimum_check(
            name="overall_final_answer_hit_delta_vs_model_top",
            actual=overall_report.hit_delta_vs_model_top_count,
            threshold=options.min_overall_final_answer_hit_delta_vs_model_top,
            detail="overall final-answer hits should not regress versus model-top",
        ),
        _minimum_check(
            name="overall_replacement_leg_hit_delta_vs_model_top",
            actual=overall_report.replacement_leg_hit_delta_vs_model_top_count,
            threshold=options.min_overall_replacement_leg_hit_delta_vs_model_top,
            detail="overall replacement-leg hits should not regress versus model-top",
        ),
        _minimum_check(
            name="overall_roi_delta_vs_model_top",
            actual=overall_report.roi_delta_vs_model_top,
            threshold=options.min_overall_roi_delta_vs_model_top,
            detail="overall ROI should not regress versus model-top",
        ),
        _minimum_check(
            name="overall_profit_loss_delta_vs_model_top",
            actual=overall_report.profit_loss_delta_vs_model_top,
            threshold=options.min_overall_profit_loss_delta_vs_model_top,
            detail="overall profit/loss should not regress versus model-top",
        ),
        _maximum_check(
            name="overall_harm_count_vs_model_top",
            actual=overall_report.harm_count_vs_model_top,
            threshold=options.max_overall_harm_count_vs_model_top,
            detail="overall shadow gate should not harm model-top replacements",
        ),
        _maximum_check(
            name="overall_final_hit_harm_count_vs_model_top",
            actual=overall_report.final_hit_harm_count_vs_model_top,
            threshold=_max_overall_final_hit_harm_count_vs_model_top(options),
            detail=(
                "overall shadow gate should not turn model-top final-answer "
                "hits into misses"
            ),
        ),
        _maximum_check(
            name="overall_profit_loss_harm_count_vs_model_top",
            actual=overall_report.profit_loss_harm_count_vs_model_top,
            threshold=_max_overall_profit_loss_harm_count_vs_model_top(options),
            detail=(
                "overall shadow gate should not reduce model-top final-answer "
                "profit/loss"
            ),
        ),
        _minimum_check(
            name="overall_average_hit_probability_delta_vs_model_top",
            actual=overall_report.average_hit_probability_delta_vs_model_top,
            threshold=options.min_overall_average_hit_probability_delta_vs_model_top,
            detail="overall hit-probability tolerance should remain bounded",
        ),
        _optional_minimum_check(
            name="overall_final_answer_hit_delta_vs_original",
            actual=overall_report.hit_delta_vs_original_count,
            threshold=options.min_overall_final_answer_hit_delta_vs_original,
            detail="overall final-answer hits should not regress versus original recommendations",
        ),
        _optional_minimum_check(
            name="overall_profit_loss_delta_vs_original",
            actual=overall_report.profit_loss_delta_vs_original,
            threshold=options.min_overall_profit_loss_delta_vs_original,
            detail="overall profit/loss should not regress versus original recommendations",
        ),
        _optional_minimum_check(
            name="overall_roi_delta_vs_original",
            actual=overall_report.roi_delta_vs_original,
            threshold=options.min_overall_roi_delta_vs_original,
            detail="overall ROI should not regress versus original recommendations",
        ),
        _optional_maximum_check(
            name="overall_harm_count_vs_original",
            actual=overall_report.harm_count_vs_original,
            threshold=options.max_overall_harm_count_vs_original,
            detail="overall shadow gate should not harm original recommendations",
        ),
        _optional_maximum_check(
            name="overall_final_hit_harm_count_vs_original",
            actual=overall_report.final_hit_harm_count_vs_original,
            threshold=_max_overall_final_hit_harm_count_vs_original(options),
            detail=(
                "overall shadow gate should not turn original final-answer hits "
                "into misses"
            ),
        ),
        _optional_maximum_check(
            name="overall_profit_loss_harm_count_vs_original",
            actual=overall_report.profit_loss_harm_count_vs_original,
            threshold=_max_overall_profit_loss_harm_count_vs_original(options),
            detail=(
                "overall shadow gate should not reduce original recommendation "
                "profit/loss"
            ),
        ),
        _optional_minimum_check(
            name="overall_average_hit_probability_delta_vs_original",
            actual=overall_report.average_hit_probability_delta_vs_original,
            threshold=options.min_overall_average_hit_probability_delta_vs_original,
            detail=(
                "overall hit-probability tolerance versus original recommendations "
                "should remain bounded"
            ),
        ),
        _maximum_check(
            name="failed_fold_count",
            actual=failed_fold_count,
            threshold=options.max_failed_fold_count,
            detail="admission should not have failing active folds",
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
            detail="admission must not change production recommendations",
        )
        if options.require_no_production_change
        else _skipped_boolean_check("no_production_recommendation_change"),
        _boolean_check(
            name="no_public_response_change",
            actual=not overall_report.public_response_changed,
            expected=True,
            detail="admission must not change public responses",
        ),
    ]


def _overall_shadow_options(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> HistoricalReplacementRerankerShadowGateOptions:
    return HistoricalReplacementRerankerShadowGateOptions(
        enable_shadow_gate=True,
        profile_id=options.profile_id,
        hit_probability_delta_threshold=options.hit_probability_delta_threshold,
        min_actual_best_profit_loss_delta=options.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=options.min_profit_loss_gap,
        min_final_answer_count=options.min_overall_final_answer_count,
        min_changed_from_model_top_count=(
            options.min_overall_changed_from_model_top_count
        ),
        min_final_answer_hit_delta_vs_model_top=(
            options.min_overall_final_answer_hit_delta_vs_model_top
        ),
        min_replacement_leg_hit_delta_vs_model_top=(
            options.min_overall_replacement_leg_hit_delta_vs_model_top
        ),
        min_profit_loss_delta_vs_model_top=(
            options.min_overall_profit_loss_delta_vs_model_top
        ),
        min_roi_delta_vs_model_top=options.min_overall_roi_delta_vs_model_top,
        max_harm_count_vs_model_top=options.max_overall_harm_count_vs_model_top,
        max_final_hit_harm_count_vs_model_top=(
            options.max_overall_final_hit_harm_count_vs_model_top
        ),
        max_profit_loss_harm_count_vs_model_top=(
            options.max_overall_profit_loss_harm_count_vs_model_top
        ),
        min_average_hit_probability_delta_vs_model_top=(
            options.min_overall_average_hit_probability_delta_vs_model_top
        ),
        min_final_answer_hit_delta_vs_original=(
            options.min_overall_final_answer_hit_delta_vs_original
        ),
        min_profit_loss_delta_vs_original=(
            options.min_overall_profit_loss_delta_vs_original
        ),
        min_roi_delta_vs_original=options.min_overall_roi_delta_vs_original,
        max_harm_count_vs_original=options.max_overall_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            options.max_overall_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            options.max_overall_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            options.min_overall_average_hit_probability_delta_vs_original
        ),
        require_tolerance_candidate=options.require_tolerance_candidate,
        allowed_tolerance_statuses=options.allowed_tolerance_statuses,
        require_source_audit_match=True,
        require_no_production_change=options.require_no_production_change,
        max_report_items=500,
    )


def _fold_shadow_options(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> HistoricalReplacementRerankerShadowGateOptions:
    return HistoricalReplacementRerankerShadowGateOptions(
        enable_shadow_gate=True,
        profile_id=options.profile_id,
        hit_probability_delta_threshold=options.hit_probability_delta_threshold,
        min_actual_best_profit_loss_delta=options.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=options.min_profit_loss_gap,
        min_final_answer_count=1,
        min_changed_from_model_top_count=0,
        min_final_answer_hit_delta_vs_model_top=(
            options.min_fold_final_answer_hit_delta_vs_model_top
        ),
        min_replacement_leg_hit_delta_vs_model_top=(
            options.min_fold_replacement_leg_hit_delta_vs_model_top
        ),
        min_profit_loss_delta_vs_model_top=(
            options.min_fold_profit_loss_delta_vs_model_top
        ),
        min_roi_delta_vs_model_top=options.min_fold_roi_delta_vs_model_top,
        max_harm_count_vs_model_top=options.max_fold_harm_count_vs_model_top,
        max_final_hit_harm_count_vs_model_top=(
            options.max_fold_final_hit_harm_count_vs_model_top
        ),
        max_profit_loss_harm_count_vs_model_top=(
            options.max_fold_profit_loss_harm_count_vs_model_top
        ),
        min_average_hit_probability_delta_vs_model_top=(
            options.min_fold_average_hit_probability_delta_vs_model_top
        ),
        min_final_answer_hit_delta_vs_original=(
            options.min_fold_final_answer_hit_delta_vs_original
        ),
        min_profit_loss_delta_vs_original=(
            options.min_fold_profit_loss_delta_vs_original
        ),
        min_roi_delta_vs_original=options.min_fold_roi_delta_vs_original,
        max_harm_count_vs_original=options.max_fold_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            options.max_fold_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            options.max_fold_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            options.min_fold_average_hit_probability_delta_vs_original
        ),
        require_tolerance_candidate=options.require_tolerance_candidate,
        allowed_tolerance_statuses=options.allowed_tolerance_statuses,
        require_source_audit_match=False,
        require_no_production_change=options.require_no_production_change,
        max_report_items=500,
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
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
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
            start : start + options.rolling_window_slice_count
        ]
        if len(window_slice_ids) < options.rolling_window_slice_count:
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
    actual_best_replacements = [
        item.actual_best_replacement
        for item in resolved_items
        if item.actual_best_replacement is not None
    ]
    resolved_item_keys = {item.item_key for item in resolved_items}
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
            "average_actual_best_profit_loss_delta": _average(
                replacement.profit_loss_delta for replacement in actual_best_replacements
            ),
            "items": resolved_items,
            "top_actual_replacement_opportunities": [
                item
                for item in audit_report.top_actual_replacement_opportunities
                if item.item_key in resolved_item_keys
            ],
            "top_model_replacement_opportunities": [
                item
                for item in audit_report.top_model_replacement_opportunities
                if item.item_key in resolved_item_keys
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
    return _season_id_sort_key(season)


def _season_id_sort_key(season: str) -> tuple[int, str]:
    match = search(r"\d{4}", season)
    return (int(match.group(0)) if match else 0, season)


def _active_fold_count(
    folds: Sequence[HistoricalReplacementRerankerShadowAdmissionFold],
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
) -> HistoricalReplacementRerankerShadowAdmissionCheck:
    return HistoricalReplacementRerankerShadowAdmissionCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _skipped_boolean_check(
    name: str,
) -> HistoricalReplacementRerankerShadowAdmissionCheck:
    return HistoricalReplacementRerankerShadowAdmissionCheck(
        name=name,
        status="passed",
        actual=None,
        threshold="not_required",
        detail="check disabled by options",
    )


def _source_surface_prematch_check(
    source_surface_summary: Mapping[str, object],
    *,
    required: bool,
) -> HistoricalReplacementRerankerShadowAdmissionCheck:
    kind = source_surface_summary.get("kind")
    if not required:
        return HistoricalReplacementRerankerShadowAdmissionCheck(
            name="source_surface_prematch",
            status="passed",
            actual=kind if isinstance(kind, str) else "unknown",
            threshold="not_required",
            detail="prematch source surface evidence is optional",
        )
    return HistoricalReplacementRerankerShadowAdmissionCheck(
        name="source_surface_prematch",
        status="passed" if kind == "prematch_replacement_surface" else "failed",
        actual=kind if isinstance(kind, str) else "unknown",
        threshold="prematch_replacement_surface",
        detail=(
            "replacement reranker admission must come from a full pre-match "
            "eligible surface, not a missed-leg diagnostic surface"
        ),
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalReplacementRerankerShadowAdmissionCheck:
    if actual is None:
        return HistoricalReplacementRerankerShadowAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementRerankerShadowAdmissionCheck(
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
) -> HistoricalReplacementRerankerShadowAdmissionCheck:
    if actual is None:
        return HistoricalReplacementRerankerShadowAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementRerankerShadowAdmissionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalReplacementRerankerShadowAdmissionCheck:
    if threshold is None:
        return HistoricalReplacementRerankerShadowAdmissionCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail="check disabled by options",
        )
    return _minimum_check(name=name, actual=actual, threshold=threshold, detail=detail)


def _optional_maximum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalReplacementRerankerShadowAdmissionCheck:
    if threshold is None:
        return HistoricalReplacementRerankerShadowAdmissionCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail="check disabled by options",
        )
    return _maximum_check(name=name, actual=actual, threshold=threshold, detail=detail)


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Run rolling/competition admission for replacement reranker shadows."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--tolerance-grid-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-id", type=str, default="quality_edge_blend_v1")
    parser.add_argument("--hit-probability-delta-threshold", type=float, default=-0.02)
    parser.add_argument("--min-actual-best-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-gap", type=float, default=0.0)
    parser.add_argument("--scope-competition-ids", type=str, default="")
    parser.add_argument("--scope-season-ids", type=str, default="")
    parser.add_argument("--scope-min-competition-season-index", type=int)
    parser.add_argument("--scope-max-competition-season-index", type=int)
    parser.add_argument("--min-overall-final-answer-count", type=int, default=20)
    parser.add_argument("--min-overall-changed-from-model-top-count", type=int, default=4)
    parser.add_argument(
        "--min-overall-final-answer-hit-delta-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-overall-replacement-leg-hit-delta-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-overall-profit-loss-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-overall-roi-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--max-overall-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-overall-final-hit-harm-count-vs-model-top", type=int)
    parser.add_argument("--max-overall-profit-loss-harm-count-vs-model-top", type=int)
    parser.add_argument(
        "--min-overall-average-hit-probability-delta-vs-model-top",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--min-overall-final-answer-hit-delta-vs-original", type=int)
    parser.add_argument("--min-overall-profit-loss-delta-vs-original", type=float)
    parser.add_argument("--min-overall-roi-delta-vs-original", type=float)
    parser.add_argument("--max-overall-harm-count-vs-original", type=int)
    parser.add_argument("--max-overall-final-hit-harm-count-vs-original", type=int)
    parser.add_argument("--max-overall-profit-loss-harm-count-vs-original", type=int)
    parser.add_argument(
        "--min-overall-average-hit-probability-delta-vs-original",
        type=float,
    )
    parser.add_argument("--min-fold-final-answer-count", type=int, default=1)
    parser.add_argument("--min-fold-changed-from-model-top-count", type=int, default=1)
    parser.add_argument(
        "--min-fold-final-answer-hit-delta-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-fold-replacement-leg-hit-delta-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-fold-profit-loss-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-fold-roi-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--max-fold-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-fold-final-hit-harm-count-vs-model-top", type=int)
    parser.add_argument("--max-fold-profit-loss-harm-count-vs-model-top", type=int)
    parser.add_argument(
        "--min-fold-average-hit-probability-delta-vs-model-top",
        type=float,
        default=-0.025,
    )
    parser.add_argument("--min-fold-final-answer-hit-delta-vs-original", type=int)
    parser.add_argument("--min-fold-profit-loss-delta-vs-original", type=float)
    parser.add_argument("--min-fold-roi-delta-vs-original", type=float)
    parser.add_argument("--max-fold-harm-count-vs-original", type=int)
    parser.add_argument("--max-fold-final-hit-harm-count-vs-original", type=int)
    parser.add_argument("--max-fold-profit-loss-harm-count-vs-original", type=int)
    parser.add_argument(
        "--min-fold-average-hit-probability-delta-vs-original",
        type=float,
    )
    parser.add_argument("--min-active-competition-fold-count", type=int, default=2)
    parser.add_argument("--min-active-season-fold-count", type=int, default=2)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=2)
    parser.add_argument("--rolling-window-slice-count", type=int, default=8)
    parser.add_argument("--rolling-window-step", type=int, default=4)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--require-prematch-source-surface", action="store_true")
    parser.add_argument("--allow-missing-tolerance-candidate", action="store_true")
    parser.add_argument(
        "--allowed-tolerance-statuses",
        type=str,
        default="candidate,watchlist",
    )
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementRerankerShadowAdmissionOptions:
    return HistoricalReplacementRerankerShadowAdmissionOptions(
        profile_id=args.profile_id,
        hit_probability_delta_threshold=args.hit_probability_delta_threshold,
        min_actual_best_profit_loss_delta=args.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=args.min_profit_loss_gap,
        scope_competition_ids=_csv_values(args.scope_competition_ids),
        scope_season_ids=_csv_values(args.scope_season_ids),
        scope_min_competition_season_index=(
            args.scope_min_competition_season_index
        ),
        scope_max_competition_season_index=(
            args.scope_max_competition_season_index
        ),
        min_overall_final_answer_count=args.min_overall_final_answer_count,
        min_overall_changed_from_model_top_count=(
            args.min_overall_changed_from_model_top_count
        ),
        min_overall_final_answer_hit_delta_vs_model_top=(
            args.min_overall_final_answer_hit_delta_vs_model_top
        ),
        min_overall_replacement_leg_hit_delta_vs_model_top=(
            args.min_overall_replacement_leg_hit_delta_vs_model_top
        ),
        min_overall_profit_loss_delta_vs_model_top=(
            args.min_overall_profit_loss_delta_vs_model_top
        ),
        min_overall_roi_delta_vs_model_top=args.min_overall_roi_delta_vs_model_top,
        max_overall_harm_count_vs_model_top=(
            args.max_overall_harm_count_vs_model_top
        ),
        max_overall_final_hit_harm_count_vs_model_top=(
            args.max_overall_final_hit_harm_count_vs_model_top
        ),
        max_overall_profit_loss_harm_count_vs_model_top=(
            args.max_overall_profit_loss_harm_count_vs_model_top
        ),
        min_overall_average_hit_probability_delta_vs_model_top=(
            args.min_overall_average_hit_probability_delta_vs_model_top
        ),
        min_overall_final_answer_hit_delta_vs_original=(
            args.min_overall_final_answer_hit_delta_vs_original
        ),
        min_overall_profit_loss_delta_vs_original=(
            args.min_overall_profit_loss_delta_vs_original
        ),
        min_overall_roi_delta_vs_original=args.min_overall_roi_delta_vs_original,
        max_overall_harm_count_vs_original=(
            args.max_overall_harm_count_vs_original
        ),
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
        min_fold_changed_from_model_top_count=args.min_fold_changed_from_model_top_count,
        min_fold_final_answer_hit_delta_vs_model_top=(
            args.min_fold_final_answer_hit_delta_vs_model_top
        ),
        min_fold_replacement_leg_hit_delta_vs_model_top=(
            args.min_fold_replacement_leg_hit_delta_vs_model_top
        ),
        min_fold_profit_loss_delta_vs_model_top=(
            args.min_fold_profit_loss_delta_vs_model_top
        ),
        min_fold_roi_delta_vs_model_top=args.min_fold_roi_delta_vs_model_top,
        max_fold_harm_count_vs_model_top=args.max_fold_harm_count_vs_model_top,
        max_fold_final_hit_harm_count_vs_model_top=(
            args.max_fold_final_hit_harm_count_vs_model_top
        ),
        max_fold_profit_loss_harm_count_vs_model_top=(
            args.max_fold_profit_loss_harm_count_vs_model_top
        ),
        min_fold_average_hit_probability_delta_vs_model_top=(
            args.min_fold_average_hit_probability_delta_vs_model_top
        ),
        min_fold_final_answer_hit_delta_vs_original=(
            args.min_fold_final_answer_hit_delta_vs_original
        ),
        min_fold_profit_loss_delta_vs_original=(
            args.min_fold_profit_loss_delta_vs_original
        ),
        min_fold_roi_delta_vs_original=args.min_fold_roi_delta_vs_original,
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
        rolling_window_slice_count=args.rolling_window_slice_count,
        rolling_window_step=args.rolling_window_step,
        max_failed_fold_count=args.max_failed_fold_count,
        require_prematch_source_surface=args.require_prematch_source_surface,
        require_tolerance_candidate=not args.allow_missing_tolerance_candidate,
        allowed_tolerance_statuses=_csv_values(args.allowed_tolerance_statuses),
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


def _max_overall_final_hit_harm_count_vs_model_top(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> int:
    return (
        options.max_overall_final_hit_harm_count_vs_model_top
        if options.max_overall_final_hit_harm_count_vs_model_top is not None
        else options.max_overall_harm_count_vs_model_top
    )


def _max_overall_profit_loss_harm_count_vs_model_top(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> int:
    return (
        options.max_overall_profit_loss_harm_count_vs_model_top
        if options.max_overall_profit_loss_harm_count_vs_model_top is not None
        else options.max_overall_harm_count_vs_model_top
    )


def _max_overall_final_hit_harm_count_vs_original(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> int | None:
    return (
        options.max_overall_final_hit_harm_count_vs_original
        if options.max_overall_final_hit_harm_count_vs_original is not None
        else options.max_overall_harm_count_vs_original
    )


def _max_overall_profit_loss_harm_count_vs_original(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> int | None:
    return (
        options.max_overall_profit_loss_harm_count_vs_original
        if options.max_overall_profit_loss_harm_count_vs_original is not None
        else options.max_overall_harm_count_vs_original
    )


def _max_fold_final_hit_harm_count_vs_model_top(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> int:
    return (
        options.max_fold_final_hit_harm_count_vs_model_top
        if options.max_fold_final_hit_harm_count_vs_model_top is not None
        else options.max_fold_harm_count_vs_model_top
    )


def _max_fold_profit_loss_harm_count_vs_model_top(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> int:
    return (
        options.max_fold_profit_loss_harm_count_vs_model_top
        if options.max_fold_profit_loss_harm_count_vs_model_top is not None
        else options.max_fold_harm_count_vs_model_top
    )


def _max_fold_final_hit_harm_count_vs_original(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> int | None:
    return (
        options.max_fold_final_hit_harm_count_vs_original
        if options.max_fold_final_hit_harm_count_vs_original is not None
        else options.max_fold_harm_count_vs_original
    )


def _max_fold_profit_loss_harm_count_vs_original(
    options: HistoricalReplacementRerankerShadowAdmissionOptions,
) -> int | None:
    return (
        options.max_fold_profit_loss_harm_count_vs_original
        if options.max_fold_profit_loss_harm_count_vs_original is not None
        else options.max_fold_harm_count_vs_original
    )


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
    checks: Sequence[HistoricalReplacementRerankerShadowAdmissionCheck],
    folds: Sequence[HistoricalReplacementRerankerShadowAdmissionFold],
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
    return f"historical_replacement_reranker_shadow_admission:{digest}"
