from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
)
from nutmeg.recommendations.replacement_final_answer_probability_preserving_grid import (
    HistoricalReplacementProbabilityPreservingGridCandidate,
    HistoricalReplacementProbabilityPreservingGridReport,
    load_historical_replacement_probability_preserving_grid_report,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)
from nutmeg.recommendations.replacement_short_odds_competition_gate import (
    HistoricalShortOddsCompetitionGateReport,
)
from nutmeg.recommendations.replacement_short_odds_final_answer_gate import (
    HistoricalShortOddsFinalAnswerGateOptions,
    HistoricalShortOddsFinalAnswerGateReport,
    build_historical_short_odds_final_answer_gate_report,
    load_historical_short_odds_competition_gate_report,
)

type HistoricalReplacementProbabilityPreservingSurfaceReplayStatus = Literal[
    "cross_surface_passed",
    "cross_surface_watchlist",
    "rejected",
]
type HistoricalReplacementProbabilityPreservingSurfaceStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalReplacementProbabilityPreservingSurfaceCheckStatus = Literal[
    "passed",
    "failed",
]


class HistoricalReplacementProbabilityPreservingSurfaceReplayOptions(BaseModel):
    candidate_key: str | None = None
    source_competition_ids: tuple[str, ...] = ()
    surface_competition_sets: tuple[str, ...] = ()
    min_surface_changed_final_answer_count: int = Field(default=1, ge=1)
    min_surface_final_answer_hit_delta_count_vs_original: int = 0
    min_surface_profit_loss_delta_vs_original: float = 0.0
    min_surface_average_hit_probability_delta_vs_original: float = -0.02
    max_surface_harm_count_vs_original: int = Field(default=0, ge=0)
    min_active_surface_count: int = Field(default=1, ge=0)
    max_failed_surface_count: int = Field(default=0, ge=0)
    min_all_audit_changed_final_answer_count: int = Field(default=1, ge=0)
    min_non_source_changed_final_answer_count: int = Field(default=0, ge=0)
    min_changed_final_answer_count_without_small_sample_warning: int = Field(
        default=8,
        ge=1,
    )
    require_no_production_change: bool = True
    max_report_surfaces: int = Field(default=160, ge=1, le=500)


class HistoricalReplacementProbabilityPreservingSurfaceReplayCheck(BaseModel):
    name: str
    status: HistoricalReplacementProbabilityPreservingSurfaceCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalReplacementProbabilityPreservingSurfaceReplaySurface(BaseModel):
    surface_id: str
    surface_type: str
    competition_ids: list[str] = Field(default_factory=list)
    status: HistoricalReplacementProbabilityPreservingSurfaceStatus
    final_answer_count: int = Field(ge=0)
    candidate_replacement_option_count: int = Field(ge=0)
    original_safe_replacement_option_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    final_answer_hit_delta_count_vs_original: int
    profit_loss_delta_vs_original: float
    harm_count_vs_original: int = Field(ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    generated_final_answer_gate_report_key: str
    generated_final_answer_gate_decision: str
    production_recommendation_changed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementProbabilityPreservingSurfaceReplayReport(BaseModel):
    report_key: str
    status: HistoricalReplacementProbabilityPreservingSurfaceReplayStatus
    shadow_candidate_allowed: bool
    production_recommendation_changed: bool = False
    source_audit_report_key: str
    source_competition_gate_report_key: str
    source_grid_report_key: str
    selected_candidate_key: str | None = None
    selected_candidate_status: str | None = None
    surface_count: int = Field(ge=0)
    active_surface_count: int = Field(ge=0)
    failed_surface_count: int = Field(ge=0)
    all_audit_changed_final_answer_count: int = Field(default=0, ge=0)
    non_source_changed_final_answer_count: int = Field(default=0, ge=0)
    checks: list[HistoricalReplacementProbabilityPreservingSurfaceReplayCheck] = Field(
        default_factory=list
    )
    surfaces: list[HistoricalReplacementProbabilityPreservingSurfaceReplaySurface] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _SurfaceSpec(BaseModel):
    surface_id: str
    surface_type: str
    competition_ids: tuple[str, ...]


def build_historical_replacement_probability_preserving_surface_replay_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    grid_report: HistoricalReplacementProbabilityPreservingGridReport,
    *,
    options: HistoricalReplacementProbabilityPreservingSurfaceReplayOptions | None = None,
) -> HistoricalReplacementProbabilityPreservingSurfaceReplayReport:
    resolved_options = (
        options or HistoricalReplacementProbabilityPreservingSurfaceReplayOptions()
    )
    warnings = [*audit_report.warnings, *competition_gate_report.warnings, *grid_report.warnings]
    candidate = _selected_candidate(grid_report, candidate_key=resolved_options.candidate_key)
    if candidate is None:
        warnings.append(
            "replacement_probability_preserving_surface_replay:no_selected_candidate"
        )
        surfaces: list[HistoricalReplacementProbabilityPreservingSurfaceReplaySurface] = []
    else:
        surfaces = _surface_reports(
            audit_report,
            competition_gate_report=competition_gate_report,
            candidate=candidate,
            options=resolved_options,
        )
    all_audit_changed = _surface_changed_count(surfaces, "all_audit_competitions")
    non_source_changed = _surface_changed_count(
        surfaces,
        "non_source_audit_competitions",
    )
    if (
        all_audit_changed
        < resolved_options.min_changed_final_answer_count_without_small_sample_warning
    ):
        warnings.append(
            "replacement_probability_preserving_surface_replay:small_changed_sample"
        )
    checks = _checks(
        grid_report,
        candidate=candidate,
        surfaces=surfaces,
        all_audit_changed=all_audit_changed,
        non_source_changed=non_source_changed,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    active_surfaces = [surface for surface in surfaces if surface.status != "skipped"]
    failed_surfaces = [surface for surface in surfaces if surface.status == "failed"]
    if candidate is None or candidate.status != "accepted":
        status: HistoricalReplacementProbabilityPreservingSurfaceReplayStatus = "rejected"
    elif failed_checks:
        status = "cross_surface_watchlist"
    else:
        status = "cross_surface_passed"
    shadow_allowed = status == "cross_surface_passed"
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_replacement_probability_preserving_surface_replay_v3_1"
        ),
        "status": status,
        "shadow_candidate_allowed": shadow_allowed,
        "production_recommendation_changed": False,
        "source_audit_report_key": audit_report.report_key,
        "source_competition_gate_report_key": competition_gate_report.report_key,
        "source_grid_report_key": grid_report.report_key,
        "selected_candidate_key": candidate.candidate_key if candidate else None,
        "selected_candidate_status": candidate.status if candidate else None,
        "surface_count": len(surfaces),
        "active_surface_count": len(active_surfaces),
        "failed_surface_count": len(failed_surfaces),
        "all_audit_changed_final_answer_count": all_audit_changed,
        "non_source_changed_final_answer_count": non_source_changed,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, surfaces)
    return HistoricalReplacementProbabilityPreservingSurfaceReplayReport(
        report_key=report_key,
        status=status,
        shadow_candidate_allowed=shadow_allowed,
        production_recommendation_changed=False,
        source_audit_report_key=audit_report.report_key,
        source_competition_gate_report_key=competition_gate_report.report_key,
        source_grid_report_key=grid_report.report_key,
        selected_candidate_key=candidate.candidate_key if candidate else None,
        selected_candidate_status=candidate.status if candidate else None,
        surface_count=len(surfaces),
        active_surface_count=len(active_surfaces),
        failed_surface_count=len(failed_surfaces),
        all_audit_changed_final_answer_count=all_audit_changed,
        non_source_changed_final_answer_count=non_source_changed,
        checks=checks,
        surfaces=surfaces[: resolved_options.max_report_surfaces],
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_replacement_probability_preserving_surface_replay_report(
    path: Path | str,
) -> HistoricalReplacementProbabilityPreservingSurfaceReplayReport:
    return HistoricalReplacementProbabilityPreservingSurfaceReplayReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_replacement_probability_preserving_surface_replay_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        load_historical_short_odds_competition_gate_report(args.competition_gate_report),
        load_historical_replacement_probability_preserving_grid_report(args.grid_report),
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
    if not report.shadow_candidate_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _surface_reports(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    options: HistoricalReplacementProbabilityPreservingSurfaceReplayOptions,
) -> list[HistoricalReplacementProbabilityPreservingSurfaceReplaySurface]:
    surfaces: list[HistoricalReplacementProbabilityPreservingSurfaceReplaySurface] = []
    for spec in _surface_specs(audit_report, candidate=candidate, options=options):
        scope_items = [
            item for item in audit_report.items if item.competition_id in spec.competition_ids
        ]
        gate_report = build_historical_short_odds_final_answer_gate_report(
            audit_report,
            competition_gate_report,
            options=_gate_options(candidate, spec.competition_ids, options),
        )
        failure_reasons = _surface_failure_reasons(gate_report, options=options)
        skipped = gate_report.changed_final_answer_count < (
            options.min_surface_changed_final_answer_count
        )
        status: HistoricalReplacementProbabilityPreservingSurfaceStatus = (
            "skipped" if skipped else "failed" if failure_reasons else "passed"
        )
        surfaces.append(
            HistoricalReplacementProbabilityPreservingSurfaceReplaySurface(
                surface_id=spec.surface_id,
                surface_type=spec.surface_type,
                competition_ids=list(spec.competition_ids),
                status=status,
                final_answer_count=_final_answer_count(scope_items),
                candidate_replacement_option_count=(
                    gate_report.candidate_replacement_option_count
                ),
                original_safe_replacement_option_count=(
                    gate_report.original_safe_replacement_option_count
                ),
                changed_final_answer_count=gate_report.changed_final_answer_count,
                final_answer_hit_delta_count_vs_original=(
                    gate_report.final_answer_hit_delta_count_vs_original
                ),
                profit_loss_delta_vs_original=gate_report.profit_loss_delta_vs_original,
                harm_count_vs_original=gate_report.harm_count_vs_original,
                average_hit_probability_delta_vs_original=(
                    gate_report.average_hit_probability_delta_vs_original
                ),
                generated_final_answer_gate_report_key=gate_report.report_key,
                generated_final_answer_gate_decision=gate_report.decision,
                production_recommendation_changed=(
                    gate_report.production_recommendation_changed
                ),
                failure_reasons=[] if skipped else failure_reasons,
                summary_json={
                    "generated_final_answer_gate_report_key": gate_report.report_key,
                    "generated_final_answer_gate_decision": gate_report.decision,
                },
            )
        )
    return surfaces


def _surface_specs(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    options: HistoricalReplacementProbabilityPreservingSurfaceReplayOptions,
) -> list[_SurfaceSpec]:
    if options.surface_competition_sets:
        return [_surface_spec_from_string(value) for value in options.surface_competition_sets]
    audit_competitions = tuple(sorted({item.competition_id for item in audit_report.items}))
    configured_source_competitions = (
        options.source_competition_ids
        if options.source_competition_ids
        else tuple(candidate.ready_competition_ids)
    )
    source_competitions = tuple(
        competition_id
        for competition_id in configured_source_competitions
        if competition_id in audit_competitions
    )
    non_source_competitions = tuple(
        competition_id
        for competition_id in audit_competitions
        if competition_id not in set(source_competitions)
    )
    specs: list[_SurfaceSpec] = []
    if source_competitions:
        specs.append(
            _SurfaceSpec(
                surface_id="source_candidate_competitions",
                surface_type="source_candidate_competitions",
                competition_ids=source_competitions,
            )
        )
    if audit_competitions:
        specs.append(
            _SurfaceSpec(
                surface_id="all_audit_competitions",
                surface_type="all_audit_competitions",
                competition_ids=audit_competitions,
            )
        )
    if non_source_competitions:
        specs.append(
            _SurfaceSpec(
                surface_id="non_source_audit_competitions",
                surface_type="non_source_audit_competitions",
                competition_ids=non_source_competitions,
            )
        )
    for competition_id in audit_competitions:
        specs.append(
            _SurfaceSpec(
                surface_id=f"competition:{competition_id}",
                surface_type="competition",
                competition_ids=(competition_id,),
            )
        )
    return specs


def _surface_spec_from_string(value: str) -> _SurfaceSpec:
    name, separator, competitions_value = value.partition(":")
    if not separator:
        raise ValueError(
            "Surface competition sets must use name:COMP1|COMP2 syntax"
        )
    competitions = tuple(
        item.strip()
        for item in competitions_value.split("|")
        if item.strip()
    )
    if not competitions:
        raise ValueError("Surface competition set must include at least one competition")
    return _SurfaceSpec(
        surface_id=name.strip(),
        surface_type="custom",
        competition_ids=competitions,
    )


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


def _gate_options(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    competition_ids: Sequence[str],
    options: HistoricalReplacementProbabilityPreservingSurfaceReplayOptions,
) -> HistoricalShortOddsFinalAnswerGateOptions:
    return HistoricalShortOddsFinalAnswerGateOptions(
        profile_id=candidate.profile_id,
        ready_competition_ids=tuple(competition_ids),
        selection_rule=candidate.selection_rule,
        shadow_selection_rule=candidate.shadow_selection_rule,
        min_changed_final_answer_count=options.min_surface_changed_final_answer_count,
        min_final_answer_hit_delta_count_vs_original=(
            options.min_surface_final_answer_hit_delta_count_vs_original
        ),
        min_profit_loss_delta_vs_original=(
            options.min_surface_profit_loss_delta_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            options.min_surface_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=options.max_surface_harm_count_vs_original,
        min_item_hit_probability_delta_vs_original=(
            candidate.min_item_hit_probability_delta_vs_original
        ),
        exclude_original_hit_harm=candidate.exclude_original_hit_harm,
        min_replacement_probability=candidate.min_replacement_probability,
        min_replacement_decimal_odds=candidate.min_replacement_decimal_odds,
        max_replacement_decimal_odds=candidate.max_replacement_decimal_odds,
        min_candidate_hit_probability_delta_vs_model_top=(
            candidate.min_candidate_hit_probability_delta_vs_model_top
        ),
        max_candidate_hit_probability_delta_vs_model_top=(
            candidate.max_candidate_hit_probability_delta_vs_model_top
        ),
        min_decimal_odds_delta_vs_model_top=(
            candidate.min_decimal_odds_delta_vs_model_top
        ),
        max_report_items=500,
    )


def _surface_failure_reasons(
    gate_report: HistoricalShortOddsFinalAnswerGateReport,
    *,
    options: HistoricalReplacementProbabilityPreservingSurfaceReplayOptions,
) -> list[str]:
    failures: list[str] = []
    if (
        gate_report.final_answer_hit_delta_count_vs_original
        < options.min_surface_final_answer_hit_delta_count_vs_original
    ):
        failures.append("final_answer_hit_delta_count_below_threshold")
    if (
        gate_report.profit_loss_delta_vs_original
        < options.min_surface_profit_loss_delta_vs_original
    ):
        failures.append("profit_loss_delta_below_threshold")
    if gate_report.harm_count_vs_original > options.max_surface_harm_count_vs_original:
        failures.append("harm_count_vs_original_above_threshold")
    if gate_report.average_hit_probability_delta_vs_original is not None and (
        gate_report.average_hit_probability_delta_vs_original
        < options.min_surface_average_hit_probability_delta_vs_original
    ):
        failures.append("average_hit_probability_delta_below_threshold")
    if gate_report.production_recommendation_changed:
        failures.append("production_recommendation_changed")
    return failures


def _checks(
    grid_report: HistoricalReplacementProbabilityPreservingGridReport,
    *,
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate | None,
    surfaces: Sequence[HistoricalReplacementProbabilityPreservingSurfaceReplaySurface],
    all_audit_changed: int,
    non_source_changed: int,
    options: HistoricalReplacementProbabilityPreservingSurfaceReplayOptions,
) -> list[HistoricalReplacementProbabilityPreservingSurfaceReplayCheck]:
    failed_surface_count = sum(1 for surface in surfaces if surface.status == "failed")
    active_surface_count = sum(1 for surface in surfaces if surface.status != "skipped")
    production_changed = any(surface.production_recommendation_changed for surface in surfaces)
    return [
        _boolean_check(
            name="grid_has_accepted_candidate",
            actual=grid_report.accepted_candidate_found,
            expected=True,
            detail="source grid must have an accepted candidate",
        ),
        _boolean_check(
            name="selected_candidate_accepted",
            actual=candidate is not None and candidate.status == "accepted",
            expected=True,
            detail="selected candidate must be accepted by source grid",
        ),
        _minimum_check(
            name="active_surface_count",
            actual=active_surface_count,
            threshold=options.min_active_surface_count,
            detail="surface replay should activate enough scopes",
        ),
        _maximum_check(
            name="failed_surface_count",
            actual=failed_surface_count,
            threshold=options.max_failed_surface_count,
            detail="active surface replay scopes should not fail",
        ),
        _minimum_check(
            name="all_audit_changed_final_answer_count",
            actual=all_audit_changed,
            threshold=options.min_all_audit_changed_final_answer_count,
            detail="all-audit surface should expand changed final-answer count",
        ),
        _minimum_check(
            name="non_source_changed_final_answer_count",
            actual=non_source_changed,
            threshold=options.min_non_source_changed_final_answer_count,
            detail="non-source surfaces should contribute changed final answers",
        ),
        _boolean_check(
            name="no_production_recommendation_change",
            actual=not production_changed,
            expected=True,
            detail="surface replay must not change production recommendations",
        )
        if options.require_no_production_change
        else _passed_check(
            name="no_production_recommendation_change",
            detail="check disabled by options",
        ),
    ]


def _surface_changed_count(
    surfaces: Sequence[HistoricalReplacementProbabilityPreservingSurfaceReplaySurface],
    surface_id: str,
) -> int:
    return next(
        (
            surface.changed_final_answer_count
            for surface in surfaces
            if surface.surface_id == surface_id
        ),
        0,
    )


def _final_answer_count(items: Sequence[HistoricalCandidateMarginalAuditItem]) -> int:
    return len({f"{item.slice_id}:{item.final_answer_scenario_key}" for item in items})


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> HistoricalReplacementProbabilityPreservingSurfaceReplayCheck:
    return HistoricalReplacementProbabilityPreservingSurfaceReplayCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _passed_check(
    *,
    name: str,
    detail: str,
) -> HistoricalReplacementProbabilityPreservingSurfaceReplayCheck:
    return HistoricalReplacementProbabilityPreservingSurfaceReplayCheck(
        name=name,
        status="passed",
        actual=None,
        threshold="not_required",
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalReplacementProbabilityPreservingSurfaceReplayCheck:
    if actual is None:
        return HistoricalReplacementProbabilityPreservingSurfaceReplayCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementProbabilityPreservingSurfaceReplayCheck(
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
) -> HistoricalReplacementProbabilityPreservingSurfaceReplayCheck:
    if actual is None:
        return HistoricalReplacementProbabilityPreservingSurfaceReplayCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementProbabilityPreservingSurfaceReplayCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Replay a probability-preserving replacement candidate across adjacent "
            "competition surfaces."
        )
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--competition-gate-report", type=Path, required=True)
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--candidate-key")
    parser.add_argument(
        "--source-competitions",
        default="",
        help=(
            "Optional comma-separated source competitions used to split "
            "source/non-source surfaces. Defaults to the selected candidate's "
            "ready competitions."
        ),
    )
    parser.add_argument(
        "--surface-competition-set",
        action="append",
        default=[],
        help=(
            "Optional custom surface in name:COMP1|COMP2 syntax. Repeatable. "
            "When omitted, source/all/non-source/per-competition scopes are used."
        ),
    )
    parser.add_argument("--min-surface-changed-final-answer-count", type=int, default=1)
    parser.add_argument(
        "--min-surface-final-answer-hit-delta-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-surface-profit-loss-delta-vs-original",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-surface-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-surface-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--min-active-surface-count", type=int, default=1)
    parser.add_argument("--max-failed-surface-count", type=int, default=0)
    parser.add_argument("--min-all-audit-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-non-source-changed-final-answer-count", type=int, default=0)
    parser.add_argument(
        "--min-changed-final-answer-count-without-small-sample-warning",
        type=int,
        default=8,
    )
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-surfaces", type=int, default=160)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementProbabilityPreservingSurfaceReplayOptions:
    return HistoricalReplacementProbabilityPreservingSurfaceReplayOptions(
        candidate_key=args.candidate_key,
        source_competition_ids=_csv_values(args.source_competitions),
        surface_competition_sets=tuple(args.surface_competition_set),
        min_surface_changed_final_answer_count=(
            args.min_surface_changed_final_answer_count
        ),
        min_surface_final_answer_hit_delta_count_vs_original=(
            args.min_surface_final_answer_hit_delta_count_vs_original
        ),
        min_surface_profit_loss_delta_vs_original=(
            args.min_surface_profit_loss_delta_vs_original
        ),
        min_surface_average_hit_probability_delta_vs_original=(
            args.min_surface_average_hit_probability_delta_vs_original
        ),
        max_surface_harm_count_vs_original=args.max_surface_harm_count_vs_original,
        min_active_surface_count=args.min_active_surface_count,
        max_failed_surface_count=args.max_failed_surface_count,
        min_all_audit_changed_final_answer_count=(
            args.min_all_audit_changed_final_answer_count
        ),
        min_non_source_changed_final_answer_count=(
            args.min_non_source_changed_final_answer_count
        ),
        min_changed_final_answer_count_without_small_sample_warning=(
            args.min_changed_final_answer_count_without_small_sample_warning
        ),
        require_no_production_change=not args.allow_production_change,
        max_report_surfaces=args.max_report_surfaces,
    )


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalReplacementProbabilityPreservingSurfaceReplayCheck],
    surfaces: Sequence[HistoricalReplacementProbabilityPreservingSurfaceReplaySurface],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "checks": [check.model_dump(mode="json") for check in checks],
            "surfaces": [surface.model_dump(mode="json") for surface in surfaces],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_probability_preserving_surface_replay:{digest}"
