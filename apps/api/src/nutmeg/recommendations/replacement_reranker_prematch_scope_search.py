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
from nutmeg.recommendations.replacement_reranker_shadow_admission import (
    HistoricalReplacementRerankerShadowAdmissionOptions,
    HistoricalReplacementRerankerShadowAdmissionReport,
    build_historical_replacement_reranker_shadow_admission_report,
)
from nutmeg.recommendations.replacement_reranker_shadow_gate import (
    load_historical_replacement_reranker_tolerance_grid_report,
)
from nutmeg.recommendations.replacement_reranker_tolerance_grid import (
    HistoricalReplacementRerankerToleranceGridReport,
)

type HistoricalReplacementRerankerPrematchScopeSearchStatus = Literal[
    "accepted_scope_found",
    "shadow_only_scopes",
    "no_admitted_scope",
    "no_scope_candidates",
]
type HistoricalReplacementRerankerPrematchScopeCandidateStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]


class HistoricalReplacementRerankerPrematchScopeSearchOptions(BaseModel):
    profile_id: str = "quality_edge_blend_v1"
    hit_probability_delta_threshold: float = -0.02
    min_actual_best_profit_loss_delta: float = 0.0
    min_profit_loss_gap: float = 0.0
    min_scope_competition_count: int = Field(default=1, ge=1)
    max_scope_competition_count: int = Field(default=3, ge=1)
    include_full_scope: bool = True
    max_scope_candidate_count: int = Field(default=200, ge=1, le=5000)
    min_overall_final_answer_count: int = Field(default=20, ge=1)
    min_overall_changed_from_model_top_count: int = Field(default=3, ge=0)
    min_overall_final_answer_hit_delta_vs_model_top: int = 0
    min_overall_replacement_leg_hit_delta_vs_model_top: int = 0
    min_overall_profit_loss_delta_vs_model_top: float = 0.0
    min_overall_roi_delta_vs_model_top: float = 0.0
    max_overall_harm_count_vs_model_top: int = Field(default=0, ge=0)
    max_overall_final_hit_harm_count_vs_model_top: int | None = Field(
        default=0,
        ge=0,
    )
    max_overall_profit_loss_harm_count_vs_model_top: int | None = Field(
        default=0,
        ge=0,
    )
    min_overall_average_hit_probability_delta_vs_model_top: float = -0.02
    min_overall_final_answer_hit_delta_vs_original: int = 0
    min_overall_profit_loss_delta_vs_original: float = 0.0
    min_overall_roi_delta_vs_original: float = 0.0
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
    min_fold_changed_from_model_top_count: int = Field(default=1, ge=0)
    min_fold_final_answer_hit_delta_vs_model_top: int = 0
    min_fold_replacement_leg_hit_delta_vs_model_top: int = 0
    min_fold_profit_loss_delta_vs_model_top: float = 0.0
    min_fold_roi_delta_vs_model_top: float = 0.0
    max_fold_harm_count_vs_model_top: int = Field(default=0, ge=0)
    max_fold_final_hit_harm_count_vs_model_top: int | None = Field(default=0, ge=0)
    max_fold_profit_loss_harm_count_vs_model_top: int | None = Field(default=0, ge=0)
    min_fold_average_hit_probability_delta_vs_model_top: float = -0.025
    min_fold_final_answer_hit_delta_vs_original: int = 0
    min_fold_profit_loss_delta_vs_original: float = 0.0
    min_fold_roi_delta_vs_original: float = 0.0
    max_fold_harm_count_vs_original: int = Field(default=0, ge=0)
    max_fold_final_hit_harm_count_vs_original: int | None = Field(default=0, ge=0)
    max_fold_profit_loss_harm_count_vs_original: int | None = Field(default=0, ge=0)
    min_fold_average_hit_probability_delta_vs_original: float = -0.05
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_fold_count: int = Field(default=2, ge=0)
    min_active_rolling_fold_count: int = Field(default=2, ge=0)
    rolling_window_slice_count: int = Field(default=8, ge=1)
    rolling_window_step: int = Field(default=4, ge=1)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_tolerance_candidate: bool = True
    allowed_tolerance_statuses: tuple[str, ...] = ("candidate", "watchlist")
    require_no_production_change: bool = True
    max_report_folds: int = Field(default=120, ge=1, le=500)
    max_report_scope_candidates: int = Field(default=40, ge=1, le=500)


class HistoricalReplacementRerankerPrematchScopeCandidate(BaseModel):
    scope_key: str
    status: HistoricalReplacementRerankerPrematchScopeCandidateStatus
    scope_competition_ids: list[str] = Field(default_factory=list)
    scope_competition_count: int = Field(ge=0)
    admission_report_key: str
    admission_status: str
    runtime_profile_candidate_allowed: bool
    shadow_allowed: bool
    source_surface_kind: str | None = None
    overall_shadow_final_answer_count: int = Field(ge=0)
    overall_changed_from_model_top_count: int = Field(ge=0)
    overall_hit_delta_vs_original_count: int
    overall_hit_delta_vs_model_top_count: int
    overall_replacement_leg_hit_delta_vs_model_top_count: int
    overall_roi_delta_vs_original: float | None = None
    overall_roi_delta_vs_model_top: float | None = None
    overall_profit_loss_delta_vs_original: float
    overall_profit_loss_delta_vs_model_top: float
    overall_harm_count_vs_original: int = Field(ge=0)
    overall_harm_count_vs_model_top: int = Field(ge=0)
    overall_final_hit_harm_count_vs_original: int = Field(ge=0)
    overall_final_hit_harm_count_vs_model_top: int = Field(ge=0)
    overall_profit_loss_harm_count_vs_original: int = Field(ge=0)
    overall_profit_loss_harm_count_vs_model_top: int = Field(ge=0)
    overall_average_hit_probability_delta_vs_original: float | None = None
    overall_average_hit_probability_delta_vs_model_top: float | None = None
    active_competition_fold_count: int = Field(ge=0)
    active_season_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    failed_checks: list[str] = Field(default_factory=list)
    failed_fold_reason_counts: dict[str, int] = Field(default_factory=dict)
    failed_fold_ids: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementRerankerPrematchScopeSearchReport(BaseModel):
    report_key: str
    status: HistoricalReplacementRerankerPrematchScopeSearchStatus
    accepted_scope_found: bool
    shadow_allowed: bool
    source_audit_report_key: str
    source_tolerance_grid_report_key: str
    profile_id: str
    hit_probability_delta_threshold: float
    source_competition_ids: list[str] = Field(default_factory=list)
    scope_candidate_count: int = Field(ge=0)
    accepted_scope_count: int = Field(ge=0)
    shadow_only_scope_count: int = Field(ge=0)
    rejected_scope_count: int = Field(ge=0)
    scope_candidate_limit_reached: bool = False
    best_scope_key: str | None = None
    best_scope: HistoricalReplacementRerankerPrematchScopeCandidate | None = None
    scopes: list[HistoricalReplacementRerankerPrematchScopeCandidate] = Field(
        default_factory=list
    )
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_replacement_reranker_prematch_scope_search_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    tolerance_grid_report: HistoricalReplacementRerankerToleranceGridReport,
    options: HistoricalReplacementRerankerPrematchScopeSearchOptions | None = None,
) -> HistoricalReplacementRerankerPrematchScopeSearchReport:
    resolved_options = (
        options or HistoricalReplacementRerankerPrematchScopeSearchOptions()
    )
    warnings = [*audit_report.warnings, *tolerance_grid_report.warnings]
    source_competition_ids = sorted({item.competition_id for item in audit_report.items})
    scope_sets = _scope_competition_sets(
        source_competition_ids,
        options=resolved_options,
    )
    if not scope_sets:
        warnings.append("replacement_reranker_prematch_scope_search:no_scope_candidates")
        return _report(
            status="no_scope_candidates",
            audit_report=audit_report,
            tolerance_grid_report=tolerance_grid_report,
            source_competition_ids=source_competition_ids,
            scopes=[],
            scope_candidate_limit_reached=False,
            warnings=warnings,
            options=resolved_options,
        )

    scopes: list[HistoricalReplacementRerankerPrematchScopeCandidate] = []
    scope_candidate_limit_reached = False
    for scope_competition_ids in scope_sets:
        if len(scopes) >= resolved_options.max_scope_candidate_count:
            scope_candidate_limit_reached = True
            warnings.append(
                "replacement_reranker_prematch_scope_search:"
                "scope_candidate_limit_reached"
            )
            break
        admission_report = build_historical_replacement_reranker_shadow_admission_report(
            audit_report,
            tolerance_grid_report=tolerance_grid_report,
            options=_admission_options(
                scope_competition_ids,
                options=resolved_options,
            ),
        )
        scopes.append(
            _scope_candidate(
                admission_report,
                scope_competition_ids=scope_competition_ids,
            )
        )

    sorted_scopes = sorted(scopes, key=_scope_sort_key, reverse=True)
    if any(scope.status == "accepted" for scope in sorted_scopes):
        status: HistoricalReplacementRerankerPrematchScopeSearchStatus = (
            "accepted_scope_found"
        )
    elif any(scope.shadow_allowed for scope in sorted_scopes):
        status = "shadow_only_scopes"
    else:
        status = "no_admitted_scope"
    return _report(
        status=status,
        audit_report=audit_report,
        tolerance_grid_report=tolerance_grid_report,
        source_competition_ids=source_competition_ids,
        scopes=sorted_scopes,
        scope_candidate_limit_reached=scope_candidate_limit_reached,
        warnings=warnings,
        options=resolved_options,
    )


def load_historical_replacement_reranker_prematch_scope_search_report(
    path: Path | str,
) -> HistoricalReplacementRerankerPrematchScopeSearchReport:
    return HistoricalReplacementRerankerPrematchScopeSearchReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_replacement_reranker_prematch_scope_search_report(
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
    if (
        args.require_accepted_scope
        and not report.accepted_scope_found
        and not args.no_fail_process
    ):
        raise SystemExit(1)


def _scope_competition_sets(
    competition_ids: Sequence[str],
    *,
    options: HistoricalReplacementRerankerPrematchScopeSearchOptions,
) -> list[tuple[str, ...]]:
    scopes: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    max_size = min(options.max_scope_competition_count, len(competition_ids))
    for size in range(options.min_scope_competition_count, max_size + 1):
        for scope in combinations(competition_ids, size):
            if scope in seen:
                continue
            seen.add(scope)
            scopes.append(scope)
    full_scope = tuple(sorted(competition_ids))
    if options.include_full_scope and full_scope and full_scope not in seen:
        scopes.append(full_scope)
    return scopes


def _admission_options(
    scope_competition_ids: Sequence[str],
    *,
    options: HistoricalReplacementRerankerPrematchScopeSearchOptions,
) -> HistoricalReplacementRerankerShadowAdmissionOptions:
    return HistoricalReplacementRerankerShadowAdmissionOptions(
        profile_id=options.profile_id,
        hit_probability_delta_threshold=options.hit_probability_delta_threshold,
        min_actual_best_profit_loss_delta=options.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=options.min_profit_loss_gap,
        scope_competition_ids=tuple(scope_competition_ids),
        min_overall_final_answer_count=options.min_overall_final_answer_count,
        min_overall_changed_from_model_top_count=(
            options.min_overall_changed_from_model_top_count
        ),
        min_overall_final_answer_hit_delta_vs_model_top=(
            options.min_overall_final_answer_hit_delta_vs_model_top
        ),
        min_overall_replacement_leg_hit_delta_vs_model_top=(
            options.min_overall_replacement_leg_hit_delta_vs_model_top
        ),
        min_overall_profit_loss_delta_vs_model_top=(
            options.min_overall_profit_loss_delta_vs_model_top
        ),
        min_overall_roi_delta_vs_model_top=options.min_overall_roi_delta_vs_model_top,
        max_overall_harm_count_vs_model_top=(
            options.max_overall_harm_count_vs_model_top
        ),
        max_overall_final_hit_harm_count_vs_model_top=(
            options.max_overall_final_hit_harm_count_vs_model_top
        ),
        max_overall_profit_loss_harm_count_vs_model_top=(
            options.max_overall_profit_loss_harm_count_vs_model_top
        ),
        min_overall_average_hit_probability_delta_vs_model_top=(
            options.min_overall_average_hit_probability_delta_vs_model_top
        ),
        min_overall_final_answer_hit_delta_vs_original=(
            options.min_overall_final_answer_hit_delta_vs_original
        ),
        min_overall_profit_loss_delta_vs_original=(
            options.min_overall_profit_loss_delta_vs_original
        ),
        min_overall_roi_delta_vs_original=options.min_overall_roi_delta_vs_original,
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
        min_fold_changed_from_model_top_count=(
            options.min_fold_changed_from_model_top_count
        ),
        min_fold_final_answer_hit_delta_vs_model_top=(
            options.min_fold_final_answer_hit_delta_vs_model_top
        ),
        min_fold_replacement_leg_hit_delta_vs_model_top=(
            options.min_fold_replacement_leg_hit_delta_vs_model_top
        ),
        min_fold_profit_loss_delta_vs_model_top=(
            options.min_fold_profit_loss_delta_vs_model_top
        ),
        min_fold_roi_delta_vs_model_top=options.min_fold_roi_delta_vs_model_top,
        max_fold_harm_count_vs_model_top=options.max_fold_harm_count_vs_model_top,
        max_fold_final_hit_harm_count_vs_model_top=(
            options.max_fold_final_hit_harm_count_vs_model_top
        ),
        max_fold_profit_loss_harm_count_vs_model_top=(
            options.max_fold_profit_loss_harm_count_vs_model_top
        ),
        min_fold_average_hit_probability_delta_vs_model_top=(
            options.min_fold_average_hit_probability_delta_vs_model_top
        ),
        min_fold_final_answer_hit_delta_vs_original=(
            options.min_fold_final_answer_hit_delta_vs_original
        ),
        min_fold_profit_loss_delta_vs_original=(
            options.min_fold_profit_loss_delta_vs_original
        ),
        min_fold_roi_delta_vs_original=options.min_fold_roi_delta_vs_original,
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
        rolling_window_slice_count=options.rolling_window_slice_count,
        rolling_window_step=options.rolling_window_step,
        max_failed_fold_count=options.max_failed_fold_count,
        require_prematch_source_surface=True,
        require_tolerance_candidate=options.require_tolerance_candidate,
        allowed_tolerance_statuses=options.allowed_tolerance_statuses,
        require_no_production_change=options.require_no_production_change,
        max_report_folds=options.max_report_folds,
    )


def _scope_candidate(
    admission_report: HistoricalReplacementRerankerShadowAdmissionReport,
    *,
    scope_competition_ids: Sequence[str],
) -> HistoricalReplacementRerankerPrematchScopeCandidate:
    failed_checks = [
        check.name for check in admission_report.checks if check.status == "failed"
    ]
    if admission_report.runtime_profile_candidate_allowed:
        status: HistoricalReplacementRerankerPrematchScopeCandidateStatus = "accepted"
    elif admission_report.shadow_allowed:
        status = "shadow_only"
    else:
        status = "rejected"
    summary = _scope_summary(
        admission_report,
        scope_competition_ids=scope_competition_ids,
        status=status,
        failed_checks=failed_checks,
    )
    scope_key = _digest_key("replacement_reranker_prematch_scope_candidate", summary)
    return HistoricalReplacementRerankerPrematchScopeCandidate(
        scope_key=scope_key,
        status=status,
        scope_competition_ids=list(scope_competition_ids),
        scope_competition_count=len(scope_competition_ids),
        admission_report_key=admission_report.report_key,
        admission_status=admission_report.status,
        runtime_profile_candidate_allowed=(
            admission_report.runtime_profile_candidate_allowed
        ),
        shadow_allowed=admission_report.shadow_allowed,
        source_surface_kind=_summary_optional_str(admission_report, "source_surface_kind"),
        overall_shadow_final_answer_count=_summary_int(
            admission_report,
            "overall_shadow_final_answer_count",
        ),
        overall_changed_from_model_top_count=_summary_int(
            admission_report,
            "overall_changed_from_model_top_count",
        ),
        overall_hit_delta_vs_original_count=_summary_int(
            admission_report,
            "overall_hit_delta_vs_original_count",
        ),
        overall_hit_delta_vs_model_top_count=_summary_int(
            admission_report,
            "overall_hit_delta_vs_model_top_count",
        ),
        overall_replacement_leg_hit_delta_vs_model_top_count=_summary_int(
            admission_report,
            "overall_replacement_leg_hit_delta_vs_model_top_count",
        ),
        overall_roi_delta_vs_original=_summary_optional_float(
            admission_report,
            "overall_roi_delta_vs_original",
        ),
        overall_roi_delta_vs_model_top=_summary_optional_float(
            admission_report,
            "overall_roi_delta_vs_model_top",
        ),
        overall_profit_loss_delta_vs_original=_summary_float(
            admission_report,
            "overall_profit_loss_delta_vs_original",
        ),
        overall_profit_loss_delta_vs_model_top=_summary_float(
            admission_report,
            "overall_profit_loss_delta_vs_model_top",
        ),
        overall_harm_count_vs_original=_summary_int(
            admission_report,
            "overall_harm_count_vs_original",
        ),
        overall_harm_count_vs_model_top=_summary_int(
            admission_report,
            "overall_harm_count_vs_model_top",
        ),
        overall_final_hit_harm_count_vs_original=_summary_int(
            admission_report,
            "overall_final_hit_harm_count_vs_original",
        ),
        overall_final_hit_harm_count_vs_model_top=_summary_int(
            admission_report,
            "overall_final_hit_harm_count_vs_model_top",
        ),
        overall_profit_loss_harm_count_vs_original=_summary_int(
            admission_report,
            "overall_profit_loss_harm_count_vs_original",
        ),
        overall_profit_loss_harm_count_vs_model_top=_summary_int(
            admission_report,
            "overall_profit_loss_harm_count_vs_model_top",
        ),
        overall_average_hit_probability_delta_vs_original=_summary_optional_float(
            admission_report,
            "overall_average_hit_probability_delta_vs_original",
        ),
        overall_average_hit_probability_delta_vs_model_top=_summary_optional_float(
            admission_report,
            "overall_average_hit_probability_delta_vs_model_top",
        ),
        active_competition_fold_count=admission_report.active_competition_fold_count,
        active_season_fold_count=admission_report.active_season_fold_count,
        active_rolling_fold_count=admission_report.active_rolling_fold_count,
        failed_fold_count=admission_report.failed_fold_count,
        failed_checks=failed_checks,
        failed_fold_reason_counts=_failed_fold_reason_counts(admission_report),
        failed_fold_ids=_failed_fold_ids(admission_report),
        production_recommendation_changed=_production_changed(admission_report),
        public_response_changed=_public_response_changed(admission_report),
        warnings=list(admission_report.warnings),
        summary_json={**summary, "scope_key": scope_key},
    )


def _scope_summary(
    admission_report: HistoricalReplacementRerankerShadowAdmissionReport,
    *,
    scope_competition_ids: Sequence[str],
    status: HistoricalReplacementRerankerPrematchScopeCandidateStatus,
    failed_checks: Sequence[str],
) -> dict[str, object]:
    return {
        "calculation_basis": "replacement_reranker_prematch_scope_candidate_v3_1",
        "status": status,
        "scope_competition_ids": list(scope_competition_ids),
        "admission_report_key": admission_report.report_key,
        "admission_status": admission_report.status,
        "source_surface_kind": _summary_optional_str(
            admission_report,
            "source_surface_kind",
        ),
        "overall_shadow_final_answer_count": _summary_int(
            admission_report,
            "overall_shadow_final_answer_count",
        ),
        "overall_changed_from_model_top_count": _summary_int(
            admission_report,
            "overall_changed_from_model_top_count",
        ),
        "overall_hit_delta_vs_original_count": _summary_int(
            admission_report,
            "overall_hit_delta_vs_original_count",
        ),
        "overall_hit_delta_vs_model_top_count": _summary_int(
            admission_report,
            "overall_hit_delta_vs_model_top_count",
        ),
        "overall_roi_delta_vs_original": _summary_optional_float(
            admission_report,
            "overall_roi_delta_vs_original",
        ),
        "overall_roi_delta_vs_model_top": _summary_optional_float(
            admission_report,
            "overall_roi_delta_vs_model_top",
        ),
        "overall_profit_loss_delta_vs_original": _summary_float(
            admission_report,
            "overall_profit_loss_delta_vs_original",
        ),
        "overall_profit_loss_delta_vs_model_top": _summary_float(
            admission_report,
            "overall_profit_loss_delta_vs_model_top",
        ),
        "overall_harm_count_vs_original": _summary_int(
            admission_report,
            "overall_harm_count_vs_original",
        ),
        "overall_final_hit_harm_count_vs_original": _summary_int(
            admission_report,
            "overall_final_hit_harm_count_vs_original",
        ),
        "overall_profit_loss_harm_count_vs_original": _summary_int(
            admission_report,
            "overall_profit_loss_harm_count_vs_original",
        ),
        "failed_checks": list(failed_checks),
        "failed_fold_count": admission_report.failed_fold_count,
        "failed_fold_reason_counts": _failed_fold_reason_counts(admission_report),
        "production_recommendation_changed": _production_changed(admission_report),
        "public_response_changed": _public_response_changed(admission_report),
    }


def _report(
    *,
    status: HistoricalReplacementRerankerPrematchScopeSearchStatus,
    audit_report: HistoricalCandidateMarginalAuditReport,
    tolerance_grid_report: HistoricalReplacementRerankerToleranceGridReport,
    source_competition_ids: Sequence[str],
    scopes: Sequence[HistoricalReplacementRerankerPrematchScopeCandidate],
    scope_candidate_limit_reached: bool,
    warnings: Sequence[str],
    options: HistoricalReplacementRerankerPrematchScopeSearchOptions,
) -> HistoricalReplacementRerankerPrematchScopeSearchReport:
    accepted = [scope for scope in scopes if scope.status == "accepted"]
    shadow_only = [scope for scope in scopes if scope.status == "shadow_only"]
    rejected = [scope for scope in scopes if scope.status == "rejected"]
    best_scope = accepted[0] if accepted else shadow_only[0] if shadow_only else None
    production_changed = any(scope.production_recommendation_changed for scope in scopes)
    public_response_changed = any(scope.public_response_changed for scope in scopes)
    summary: dict[str, object] = {
        "calculation_basis": "replacement_reranker_prematch_scope_search_v3_1",
        "status": status,
        "accepted_scope_found": bool(accepted),
        "shadow_allowed": bool(accepted or shadow_only),
        "source_audit_report_key": audit_report.report_key,
        "source_tolerance_grid_report_key": tolerance_grid_report.report_key,
        "profile_id": options.profile_id,
        "hit_probability_delta_threshold": options.hit_probability_delta_threshold,
        "source_competition_ids": list(source_competition_ids),
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
        "replacement_reranker_prematch_scope_search",
        {
            **summary,
            "scope_keys": [scope.scope_key for scope in scopes],
        },
    )
    return HistoricalReplacementRerankerPrematchScopeSearchReport(
        report_key=report_key,
        status=status,
        accepted_scope_found=bool(accepted),
        shadow_allowed=bool(accepted or shadow_only),
        source_audit_report_key=audit_report.report_key,
        source_tolerance_grid_report_key=tolerance_grid_report.report_key,
        profile_id=options.profile_id,
        hit_probability_delta_threshold=options.hit_probability_delta_threshold,
        source_competition_ids=list(source_competition_ids),
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


def _scope_sort_key(
    scope: HistoricalReplacementRerankerPrematchScopeCandidate,
) -> tuple[float, float, float, float, float, float, float, float]:
    status_score = {"accepted": 2.0, "shadow_only": 1.0, "rejected": 0.0}[
        scope.status
    ]
    return (
        status_score,
        float(scope.overall_hit_delta_vs_original_count),
        scope.overall_roi_delta_vs_original
        if scope.overall_roi_delta_vs_original is not None
        else -999.0,
        scope.overall_profit_loss_delta_vs_original,
        scope.overall_roi_delta_vs_model_top
        if scope.overall_roi_delta_vs_model_top is not None
        else -999.0,
        scope.overall_profit_loss_delta_vs_model_top,
        -float(scope.failed_fold_count),
        -float(scope.scope_competition_count),
    )


def _summary_int(
    report: HistoricalReplacementRerankerShadowAdmissionReport,
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
    report: HistoricalReplacementRerankerShadowAdmissionReport,
    key: str,
) -> float:
    value = report.summary_json.get(key)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _summary_optional_float(
    report: HistoricalReplacementRerankerShadowAdmissionReport,
    key: str,
) -> float | None:
    value = report.summary_json.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _summary_optional_str(
    report: HistoricalReplacementRerankerShadowAdmissionReport,
    key: str,
) -> str | None:
    value = report.summary_json.get(key)
    if isinstance(value, str):
        return value
    return None


def _failed_fold_reason_counts(
    report: HistoricalReplacementRerankerShadowAdmissionReport,
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


def _failed_fold_ids(
    report: HistoricalReplacementRerankerShadowAdmissionReport,
) -> list[str]:
    return [fold.fold_id for fold in report.folds if fold.status == "failed"][:20]


def _production_changed(
    report: HistoricalReplacementRerankerShadowAdmissionReport,
) -> bool:
    return any(fold.production_recommendation_changed for fold in report.folds)


def _public_response_changed(
    report: HistoricalReplacementRerankerShadowAdmissionReport,
) -> bool:
    return any(fold.public_response_changed for fold in report.folds)


def _digest_key(prefix: str, payload: Mapping[str, object]) -> str:
    body = dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Search prematch competition scopes for replacement reranker admission."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--tolerance-grid-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--profile-id", default="quality_edge_blend_v1")
    parser.add_argument("--hit-probability-delta-threshold", type=float, default=-0.02)
    parser.add_argument("--min-actual-best-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-gap", type=float, default=0.0)
    parser.add_argument("--min-scope-competition-count", type=int, default=1)
    parser.add_argument("--max-scope-competition-count", type=int, default=3)
    parser.add_argument("--exclude-full-scope", action="store_true")
    parser.add_argument("--max-scope-candidate-count", type=int, default=200)
    parser.add_argument("--min-overall-final-answer-count", type=int, default=20)
    parser.add_argument("--min-overall-changed-from-model-top-count", type=int, default=3)
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
    parser.add_argument("--min-overall-profit-loss-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--min-overall-roi-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--max-overall-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-overall-final-hit-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument(
        "--max-overall-profit-loss-harm-count-vs-model-top",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-overall-average-hit-probability-delta-vs-model-top",
        type=float,
        default=-0.02,
    )
    parser.add_argument(
        "--min-overall-final-answer-hit-delta-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-overall-profit-loss-delta-vs-original",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-overall-roi-delta-vs-original", type=float, default=0.0)
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
    parser.add_argument("--min-fold-profit-loss-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--min-fold-roi-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--max-fold-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-fold-final-hit-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-fold-profit-loss-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument(
        "--min-fold-average-hit-probability-delta-vs-model-top",
        type=float,
        default=-0.025,
    )
    parser.add_argument(
        "--min-fold-final-answer-hit-delta-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument("--min-fold-profit-loss-delta-vs-original", type=float, default=0.0)
    parser.add_argument("--min-fold-roi-delta-vs-original", type=float, default=0.0)
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
    parser.add_argument("--rolling-window-slice-count", type=int, default=8)
    parser.add_argument("--rolling-window-step", type=int, default=4)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-missing-tolerance-candidate", action="store_true")
    parser.add_argument("--allowed-tolerance-statuses", default="candidate,watchlist")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--max-report-scope-candidates", type=int, default=40)
    parser.add_argument("--require-accepted-scope", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementRerankerPrematchScopeSearchOptions:
    return HistoricalReplacementRerankerPrematchScopeSearchOptions(
        profile_id=args.profile_id,
        hit_probability_delta_threshold=args.hit_probability_delta_threshold,
        min_actual_best_profit_loss_delta=args.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=args.min_profit_loss_gap,
        min_scope_competition_count=args.min_scope_competition_count,
        max_scope_competition_count=args.max_scope_competition_count,
        include_full_scope=not args.exclude_full_scope,
        max_scope_candidate_count=args.max_scope_candidate_count,
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
        min_fold_profit_loss_delta_vs_original=args.min_fold_profit_loss_delta_vs_original,
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
        require_tolerance_candidate=not args.allow_missing_tolerance_candidate,
        allowed_tolerance_statuses=tuple(_csv(args.allowed_tolerance_statuses)),
        require_no_production_change=not args.allow_production_change,
        max_report_folds=args.max_report_folds,
        max_report_scope_candidates=args.max_report_scope_candidates,
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
