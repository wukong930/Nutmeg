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

type HistoricalReplacementProbabilityPreservingAdmissionStatus = Literal[
    "shadow_admission_passed",
    "shadow_admission_watchlist",
    "rejected",
]
type HistoricalReplacementProbabilityPreservingAdmissionCheckStatus = Literal[
    "passed",
    "failed",
]
type HistoricalReplacementProbabilityPreservingFoldStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalReplacementProbabilityPreservingAdmissionOptions(BaseModel):
    candidate_key: str | None = None
    min_overall_final_answer_count: int = Field(default=1, ge=1)
    min_overall_changed_final_answer_count: int = Field(default=1, ge=1)
    min_overall_final_answer_hit_delta_count_vs_original: int = 0
    min_overall_profit_loss_delta_vs_original: float = 0.0
    min_overall_average_hit_probability_delta_vs_original: float = -0.02
    max_overall_harm_count_vs_original: int = Field(default=0, ge=0)
    min_fold_final_answer_count: int = Field(default=1, ge=1)
    min_fold_changed_final_answer_count: int = Field(default=1, ge=0)
    min_fold_final_answer_hit_delta_count_vs_original: int = 0
    min_fold_profit_loss_delta_vs_original: float = 0.0
    min_fold_average_hit_probability_delta_vs_original: float = -0.02
    max_fold_harm_count_vs_original: int = Field(default=0, ge=0)
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_fold_count: int = Field(default=1, ge=0)
    min_active_rolling_fold_count: int = Field(default=1, ge=0)
    rolling_window_final_answer_count: int = Field(default=1, ge=1)
    rolling_window_step: int = Field(default=1, ge=1)
    max_failed_fold_count: int = Field(default=0, ge=0)
    min_changed_final_answer_count_without_small_sample_warning: int = Field(
        default=5,
        ge=1,
    )
    require_no_production_change: bool = True
    max_report_folds: int = Field(default=120, ge=1, le=500)


class HistoricalReplacementProbabilityPreservingAdmissionCheck(BaseModel):
    name: str
    status: HistoricalReplacementProbabilityPreservingAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalReplacementProbabilityPreservingAdmissionFold(BaseModel):
    fold_id: str
    fold_type: str
    status: HistoricalReplacementProbabilityPreservingFoldStatus
    source_slice_ids: list[str] = Field(default_factory=list)
    final_answer_count: int = Field(ge=0)
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


class HistoricalReplacementProbabilityPreservingAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalReplacementProbabilityPreservingAdmissionStatus
    shadow_candidate_allowed: bool
    production_recommendation_changed: bool = False
    source_audit_report_key: str
    source_competition_gate_report_key: str
    source_grid_report_key: str
    selected_candidate_key: str | None = None
    selected_candidate_status: str | None = None
    overall_final_answer_gate_report_key: str
    fold_count: int = Field(ge=0)
    active_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    checks: list[HistoricalReplacementProbabilityPreservingAdmissionCheck] = Field(
        default_factory=list
    )
    folds: list[HistoricalReplacementProbabilityPreservingAdmissionFold] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_replacement_probability_preserving_admission_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    grid_report: HistoricalReplacementProbabilityPreservingGridReport,
    *,
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions | None = None,
) -> HistoricalReplacementProbabilityPreservingAdmissionReport:
    resolved_options = (
        options or HistoricalReplacementProbabilityPreservingAdmissionOptions()
    )
    warnings = [*audit_report.warnings, *competition_gate_report.warnings, *grid_report.warnings]
    candidate = _selected_candidate(grid_report, candidate_key=resolved_options.candidate_key)
    if candidate is None:
        warnings.append(
            "replacement_probability_preserving_admission:no_selected_candidate"
        )
        overall_gate = _empty_overall_gate(
            audit_report,
            competition_gate_report,
            options=resolved_options,
        )
        folds: list[HistoricalReplacementProbabilityPreservingAdmissionFold] = []
    else:
        overall_gate = build_historical_short_odds_final_answer_gate_report(
            audit_report,
            competition_gate_report,
            options=_overall_gate_options(candidate, resolved_options),
        )
        folds = _fold_reports(
            audit_report,
            competition_gate_report=competition_gate_report,
            candidate=candidate,
            options=resolved_options,
        )
        if (
            overall_gate.changed_final_answer_count
            < resolved_options.min_changed_final_answer_count_without_small_sample_warning
        ):
            warnings.append(
                "replacement_probability_preserving_admission:small_changed_sample"
            )

    checks = _checks(
        grid_report,
        candidate=candidate,
        overall_gate=overall_gate,
        folds=folds,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    active_folds = [fold for fold in folds if fold.status != "skipped"]
    failed_folds = [fold for fold in folds if fold.status == "failed"]
    if candidate is None or candidate.status != "accepted" or _overall_failed(overall_gate):
        status: HistoricalReplacementProbabilityPreservingAdmissionStatus = "rejected"
    elif failed_checks:
        status = "shadow_admission_watchlist"
    else:
        status = "shadow_admission_passed"
    shadow_allowed = status == "shadow_admission_passed"
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_replacement_probability_preserving_admission_v3_1"
        ),
        "status": status,
        "shadow_candidate_allowed": shadow_allowed,
        "production_recommendation_changed": False,
        "source_audit_report_key": audit_report.report_key,
        "source_competition_gate_report_key": competition_gate_report.report_key,
        "source_grid_report_key": grid_report.report_key,
        "selected_candidate_key": candidate.candidate_key if candidate else None,
        "selected_candidate_status": candidate.status if candidate else None,
        "overall_final_answer_gate_report_key": overall_gate.report_key,
        "overall_decision": overall_gate.decision,
        "overall_changed_final_answer_count": overall_gate.changed_final_answer_count,
        "overall_final_answer_hit_delta_count_vs_original": (
            overall_gate.final_answer_hit_delta_count_vs_original
        ),
        "overall_profit_loss_delta_vs_original": (
            overall_gate.profit_loss_delta_vs_original
        ),
        "overall_harm_count_vs_original": overall_gate.harm_count_vs_original,
        "overall_average_hit_probability_delta_vs_original": (
            overall_gate.average_hit_probability_delta_vs_original
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
    return HistoricalReplacementProbabilityPreservingAdmissionReport(
        report_key=report_key,
        status=status,
        shadow_candidate_allowed=shadow_allowed,
        production_recommendation_changed=False,
        source_audit_report_key=audit_report.report_key,
        source_competition_gate_report_key=competition_gate_report.report_key,
        source_grid_report_key=grid_report.report_key,
        selected_candidate_key=candidate.candidate_key if candidate else None,
        selected_candidate_status=candidate.status if candidate else None,
        overall_final_answer_gate_report_key=overall_gate.report_key,
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


def load_historical_replacement_probability_preserving_admission_report(
    path: Path | str,
) -> HistoricalReplacementProbabilityPreservingAdmissionReport:
    return (
        HistoricalReplacementProbabilityPreservingAdmissionReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_replacement_probability_preserving_admission_report(
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


def _empty_overall_gate(
    audit_report: HistoricalCandidateMarginalAuditReport,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    *,
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions,
) -> HistoricalShortOddsFinalAnswerGateReport:
    return build_historical_short_odds_final_answer_gate_report(
        audit_report,
        competition_gate_report,
        options=HistoricalShortOddsFinalAnswerGateOptions(
            min_changed_final_answer_count=options.min_overall_changed_final_answer_count,
            min_final_answer_hit_delta_count_vs_original=(
                options.min_overall_final_answer_hit_delta_count_vs_original
            ),
            min_profit_loss_delta_vs_original=(
                options.min_overall_profit_loss_delta_vs_original
            ),
            min_average_hit_probability_delta_vs_original=(
                options.min_overall_average_hit_probability_delta_vs_original
            ),
            max_harm_count_vs_original=options.max_overall_harm_count_vs_original,
        ),
    )


def _fold_reports(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions,
) -> list[HistoricalReplacementProbabilityPreservingAdmissionFold]:
    folds: list[HistoricalReplacementProbabilityPreservingAdmissionFold] = []
    for competition_id, items in _groups_by_competition(audit_report.items).items():
        folds.append(
            _fold_report(
                f"competition:{competition_id}",
                "competition",
                items,
                audit_report=audit_report,
                competition_gate_report=competition_gate_report,
                candidate=candidate,
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
                competition_gate_report=competition_gate_report,
                candidate=candidate,
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
                competition_gate_report=competition_gate_report,
                candidate=candidate,
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
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions,
) -> HistoricalReplacementProbabilityPreservingAdmissionFold:
    fold_audit = _filtered_audit_report(audit_report, items=items, fold_id=fold_id)
    gate_report = build_historical_short_odds_final_answer_gate_report(
        fold_audit,
        competition_gate_report,
        options=_fold_gate_options(candidate, options),
    )
    final_answer_count = _final_answer_count(items)
    failure_reasons = _fold_failure_reasons(gate_report, options=options)
    skipped = (
        final_answer_count < options.min_fold_final_answer_count
        or gate_report.changed_final_answer_count < options.min_fold_changed_final_answer_count
    )
    status: HistoricalReplacementProbabilityPreservingFoldStatus = (
        "skipped" if skipped else "failed" if failure_reasons else "passed"
    )
    return HistoricalReplacementProbabilityPreservingAdmissionFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status=status,
        source_slice_ids=_unique(item.slice_id for item in items),
        final_answer_count=final_answer_count,
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
        production_recommendation_changed=gate_report.production_recommendation_changed,
        failure_reasons=[] if skipped else failure_reasons,
        summary_json={
            "generated_final_answer_gate_report_key": gate_report.report_key,
            "generated_final_answer_gate_decision": gate_report.decision,
        },
    )


def _overall_gate_options(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions,
) -> HistoricalShortOddsFinalAnswerGateOptions:
    return _gate_options(
        candidate,
        min_changed_final_answer_count=options.min_overall_changed_final_answer_count,
        min_final_answer_hit_delta_count_vs_original=(
            options.min_overall_final_answer_hit_delta_count_vs_original
        ),
        min_profit_loss_delta_vs_original=options.min_overall_profit_loss_delta_vs_original,
        min_average_hit_probability_delta_vs_original=(
            options.min_overall_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=options.max_overall_harm_count_vs_original,
    )


def _fold_gate_options(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions,
) -> HistoricalShortOddsFinalAnswerGateOptions:
    return _gate_options(
        candidate,
        min_changed_final_answer_count=max(1, options.min_fold_changed_final_answer_count),
        min_final_answer_hit_delta_count_vs_original=(
            options.min_fold_final_answer_hit_delta_count_vs_original
        ),
        min_profit_loss_delta_vs_original=options.min_fold_profit_loss_delta_vs_original,
        min_average_hit_probability_delta_vs_original=(
            options.min_fold_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=options.max_fold_harm_count_vs_original,
    )


def _gate_options(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
    *,
    min_changed_final_answer_count: int,
    min_final_answer_hit_delta_count_vs_original: int,
    min_profit_loss_delta_vs_original: float,
    min_average_hit_probability_delta_vs_original: float,
    max_harm_count_vs_original: int,
) -> HistoricalShortOddsFinalAnswerGateOptions:
    return HistoricalShortOddsFinalAnswerGateOptions(
        profile_id=candidate.profile_id,
        ready_competition_ids=tuple(candidate.ready_competition_ids),
        selection_rule=candidate.selection_rule,
        shadow_selection_rule=candidate.shadow_selection_rule,
        min_changed_final_answer_count=min_changed_final_answer_count,
        min_final_answer_hit_delta_count_vs_original=(
            min_final_answer_hit_delta_count_vs_original
        ),
        min_profit_loss_delta_vs_original=min_profit_loss_delta_vs_original,
        min_average_hit_probability_delta_vs_original=(
            min_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=max_harm_count_vs_original,
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


def _checks(
    grid_report: HistoricalReplacementProbabilityPreservingGridReport,
    *,
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate | None,
    overall_gate: HistoricalShortOddsFinalAnswerGateReport,
    folds: Sequence[HistoricalReplacementProbabilityPreservingAdmissionFold],
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions,
) -> list[HistoricalReplacementProbabilityPreservingAdmissionCheck]:
    failed_fold_count = sum(1 for fold in folds if fold.status == "failed")
    return [
        _boolean_check(
            name="grid_has_accepted_candidate",
            actual=grid_report.accepted_candidate_found,
            expected=True,
            detail="source grid must have at least one accepted shadow candidate",
        ),
        _boolean_check(
            name="selected_candidate_accepted",
            actual=candidate is not None and candidate.status == "accepted",
            expected=True,
            detail="selected candidate must be accepted by source grid",
        ),
        _boolean_check(
            name="overall_final_answer_gate_passed",
            actual=overall_gate.decision == "final_answer_shadow_candidate",
            expected=True,
            detail="overall final-answer gate must pass for selected candidate",
        ),
        _minimum_check(
            name="overall_final_answer_count",
            actual=overall_gate.changed_final_answer_count,
            threshold=options.min_overall_final_answer_count,
            detail="overall changed final-answer coverage should be sufficient",
        ),
        _minimum_check(
            name="overall_changed_final_answer_count",
            actual=overall_gate.changed_final_answer_count,
            threshold=options.min_overall_changed_final_answer_count,
            detail="overall candidate should change enough final answers",
        ),
        _minimum_check(
            name="overall_final_answer_hit_delta_count_vs_original",
            actual=overall_gate.final_answer_hit_delta_count_vs_original,
            threshold=options.min_overall_final_answer_hit_delta_count_vs_original,
            detail="overall final-answer hit count should not regress",
        ),
        _minimum_check(
            name="overall_profit_loss_delta_vs_original",
            actual=overall_gate.profit_loss_delta_vs_original,
            threshold=options.min_overall_profit_loss_delta_vs_original,
            detail="overall profit/loss should not regress",
        ),
        _maximum_check(
            name="overall_harm_count_vs_original",
            actual=overall_gate.harm_count_vs_original,
            threshold=options.max_overall_harm_count_vs_original,
            detail="overall candidate should not harm original final answers",
        ),
        _minimum_check(
            name="overall_average_hit_probability_delta_vs_original",
            actual=overall_gate.average_hit_probability_delta_vs_original,
            threshold=options.min_overall_average_hit_probability_delta_vs_original,
            detail="overall expected hit-probability loss should be bounded",
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
            detail="candidate should validate across enough competition folds",
        ),
        _minimum_check(
            name="active_season_fold_count",
            actual=_active_fold_count(folds, "season"),
            threshold=options.min_active_season_fold_count,
            detail="candidate should validate across enough season folds",
        ),
        _minimum_check(
            name="active_rolling_fold_count",
            actual=_active_fold_count(folds, "rolling_window"),
            threshold=options.min_active_rolling_fold_count,
            detail="candidate should validate across enough rolling-window folds",
        ),
        _boolean_check(
            name="no_production_recommendation_change",
            actual=not overall_gate.production_recommendation_changed,
            expected=True,
            detail="admission must not change production recommendations",
        )
        if options.require_no_production_change
        else _passed_check(
            name="no_production_recommendation_change",
            detail="check disabled by options",
        ),
    ]


def _fold_failure_reasons(
    gate_report: HistoricalShortOddsFinalAnswerGateReport,
    *,
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions,
) -> list[str]:
    failures: list[str] = []
    if (
        gate_report.final_answer_hit_delta_count_vs_original
        < options.min_fold_final_answer_hit_delta_count_vs_original
    ):
        failures.append("final_answer_hit_delta_count_below_threshold")
    if gate_report.profit_loss_delta_vs_original < options.min_fold_profit_loss_delta_vs_original:
        failures.append("profit_loss_delta_below_threshold")
    if gate_report.harm_count_vs_original > options.max_fold_harm_count_vs_original:
        failures.append("harm_count_vs_original_above_threshold")
    if gate_report.average_hit_probability_delta_vs_original is not None and (
        gate_report.average_hit_probability_delta_vs_original
        < options.min_fold_average_hit_probability_delta_vs_original
    ):
        failures.append("average_hit_probability_delta_below_threshold")
    if gate_report.production_recommendation_changed:
        failures.append("production_recommendation_changed")
    return failures


def _overall_failed(gate_report: HistoricalShortOddsFinalAnswerGateReport) -> bool:
    return gate_report.decision == "rejected"


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
    options: HistoricalReplacementProbabilityPreservingAdmissionOptions,
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
    item_keys = {item.item_key for item in resolved_items}
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
                if item.item_key in item_keys
            ],
            "top_model_replacement_opportunities": [
                item
                for item in audit_report.top_model_replacement_opportunities
                if item.item_key in item_keys
            ],
            "summary_json": {
                **audit_report.summary_json,
                "fold_id": fold_id,
                "source_audit_report_key": audit_report.report_key,
            },
        }
    )


def _final_answer_count(items: Sequence[HistoricalCandidateMarginalAuditItem]) -> int:
    return len({f"{item.slice_id}:{item.final_answer_scenario_key}" for item in items})


def _season_id(slice_id: str) -> str:
    match = search(r"_(\d{4}(?:_\d{4})?)_", slice_id)
    return match.group(1) if match else "unknown"


def _season_sort_key(slice_id: str) -> tuple[int, str]:
    season = _season_id(slice_id)
    match = search(r"\d{4}", season)
    return (int(match.group(0)) if match else 0, slice_id)


def _active_fold_count(
    folds: Sequence[HistoricalReplacementProbabilityPreservingAdmissionFold],
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
) -> HistoricalReplacementProbabilityPreservingAdmissionCheck:
    return HistoricalReplacementProbabilityPreservingAdmissionCheck(
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
) -> HistoricalReplacementProbabilityPreservingAdmissionCheck:
    return HistoricalReplacementProbabilityPreservingAdmissionCheck(
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
) -> HistoricalReplacementProbabilityPreservingAdmissionCheck:
    if actual is None:
        return HistoricalReplacementProbabilityPreservingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementProbabilityPreservingAdmissionCheck(
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
) -> HistoricalReplacementProbabilityPreservingAdmissionCheck:
    if actual is None:
        return HistoricalReplacementProbabilityPreservingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementProbabilityPreservingAdmissionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run rolling/fold admission for a probability-preserving replacement "
            "grid candidate."
        )
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--competition-gate-report", type=Path, required=True)
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--candidate-key")
    parser.add_argument("--min-overall-final-answer-count", type=int, default=1)
    parser.add_argument("--min-overall-changed-final-answer-count", type=int, default=1)
    parser.add_argument(
        "--min-overall-final-answer-hit-delta-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-overall-profit-loss-delta-vs-original",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-overall-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-overall-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--min-fold-final-answer-count", type=int, default=1)
    parser.add_argument("--min-fold-changed-final-answer-count", type=int, default=1)
    parser.add_argument(
        "--min-fold-final-answer-hit-delta-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-fold-profit-loss-delta-vs-original",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-fold-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-fold-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--min-active-season-fold-count", type=int, default=1)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--rolling-window-final-answer-count", type=int, default=1)
    parser.add_argument("--rolling-window-step", type=int, default=1)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument(
        "--min-changed-final-answer-count-without-small-sample-warning",
        type=int,
        default=5,
    )
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementProbabilityPreservingAdmissionOptions:
    return HistoricalReplacementProbabilityPreservingAdmissionOptions(
        candidate_key=args.candidate_key,
        min_overall_final_answer_count=args.min_overall_final_answer_count,
        min_overall_changed_final_answer_count=(
            args.min_overall_changed_final_answer_count
        ),
        min_overall_final_answer_hit_delta_count_vs_original=(
            args.min_overall_final_answer_hit_delta_count_vs_original
        ),
        min_overall_profit_loss_delta_vs_original=(
            args.min_overall_profit_loss_delta_vs_original
        ),
        min_overall_average_hit_probability_delta_vs_original=(
            args.min_overall_average_hit_probability_delta_vs_original
        ),
        max_overall_harm_count_vs_original=args.max_overall_harm_count_vs_original,
        min_fold_final_answer_count=args.min_fold_final_answer_count,
        min_fold_changed_final_answer_count=args.min_fold_changed_final_answer_count,
        min_fold_final_answer_hit_delta_count_vs_original=(
            args.min_fold_final_answer_hit_delta_count_vs_original
        ),
        min_fold_profit_loss_delta_vs_original=(
            args.min_fold_profit_loss_delta_vs_original
        ),
        min_fold_average_hit_probability_delta_vs_original=(
            args.min_fold_average_hit_probability_delta_vs_original
        ),
        max_fold_harm_count_vs_original=args.max_fold_harm_count_vs_original,
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_fold_count=args.min_active_season_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        rolling_window_final_answer_count=args.rolling_window_final_answer_count,
        rolling_window_step=args.rolling_window_step,
        max_failed_fold_count=args.max_failed_fold_count,
        min_changed_final_answer_count_without_small_sample_warning=(
            args.min_changed_final_answer_count_without_small_sample_warning
        ),
        require_no_production_change=not args.allow_production_change,
        max_report_folds=args.max_report_folds,
    )


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
    checks: Sequence[HistoricalReplacementProbabilityPreservingAdmissionCheck],
    folds: Sequence[HistoricalReplacementProbabilityPreservingAdmissionFold],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "checks": [check.model_dump(mode="json") for check in checks],
            "folds": [fold.model_dump(mode="json") for fold in folds],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_probability_preserving_admission:{digest}"
