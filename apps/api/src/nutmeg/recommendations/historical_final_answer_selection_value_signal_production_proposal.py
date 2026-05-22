from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_final_answer_selection_value_signal_search import (
    HistoricalFinalAnswerSelectionValueSignalSearchCandidate,
    HistoricalFinalAnswerSelectionValueSignalSearchReport,
)

type HistoricalFinalAnswerSelectionValueSignalProposalStatus = Literal[
    "runtime_profile_proposal_ready",
    "holdout_only",
    "blocked",
]
type HistoricalFinalAnswerSelectionValueSignalProposalCheckStatus = Literal[
    "passed",
    "failed",
]


class HistoricalFinalAnswerSelectionValueSignalProposalOptions(BaseModel):
    proposal_id: str = "final_answer_selection_value_signal_candidate_v1"
    proposed_profile_version: str = (
        "v3_1_final_answer_selection_value_signal_runtime_candidate"
    )
    source_candidate_key: str | None = None
    min_final_answer_count: int = Field(default=30, ge=1)
    min_affected_leg_count: int = Field(default=1, ge=0)
    min_changed_final_answer_count: int = Field(default=1, ge=0)
    min_positive_movement_count: int = Field(default=1, ge=0)
    max_harmful_movement_count: int = Field(default=0, ge=0)
    max_probability_quality_harm_movement_count: int = Field(default=0, ge=0)
    min_final_answer_hit_delta_count: int = 0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_candidate_roi: float = -1.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    require_search_candidate_accepted: bool = True
    require_no_decision_reasons: bool = True
    require_probability_grid_unchanged: bool = True
    require_movement_conditioned_spec: bool = True
    require_clean_movement_only: bool = True


class HistoricalFinalAnswerSelectionValueSignalProposalCheck(BaseModel):
    name: str
    status: HistoricalFinalAnswerSelectionValueSignalProposalCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalFinalAnswerSelectionValueSignalRuntimeRuleProposal(BaseModel):
    rule_id: str
    proposed_profile_version: str
    proposed_production_enabled: bool
    holdout_candidate_enabled: bool
    production_recommendation_changed: bool = False
    competition_ids: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    probability_min: float = Field(ge=0.0, le=1.0)
    probability_max: float = Field(ge=0.0, le=1.0)
    min_decimal_odds: float = Field(ge=1.0)
    max_decimal_odds: float = Field(gt=1.0)
    max_model_edge: float | None = None
    score_min: float = Field(ge=0.0, le=1.0)
    score_max: float = Field(ge=0.0, le=1.0)
    strength: float = Field(ge=-1.0, le=1.0)
    max_hit_probability_deficit: float | None = Field(default=None, ge=0.0, le=1.0)
    min_option_roi: float | None = None
    max_option_risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_bucket_key: str | None = None
    source_bucket_search_candidate_key: str | None = None
    source_report_keys: dict[str, str] = Field(default_factory=dict)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    constraints_json: dict[str, object] = Field(default_factory=dict)
    rollback_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HistoricalFinalAnswerSelectionValueSignalProposalReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSelectionValueSignalProposalStatus
    runtime_profile_proposal_allowed: bool
    holdout_candidate_allowed: bool
    proposal_count: int = Field(ge=0)
    source_search_report_key: str
    source_candidate_key: str
    checks: list[HistoricalFinalAnswerSelectionValueSignalProposalCheck] = Field(
        default_factory=list
    )
    proposal_rule: HistoricalFinalAnswerSelectionValueSignalRuntimeRuleProposal | None = (
        None
    )
    proposal_profile_set_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_final_answer_selection_value_signal_search_report(
    path: Path | str,
) -> HistoricalFinalAnswerSelectionValueSignalSearchReport:
    return HistoricalFinalAnswerSelectionValueSignalSearchReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_final_answer_selection_value_signal_proposal_report(
    search_report: HistoricalFinalAnswerSelectionValueSignalSearchReport,
    *,
    options: HistoricalFinalAnswerSelectionValueSignalProposalOptions | None = None,
) -> HistoricalFinalAnswerSelectionValueSignalProposalReport:
    resolved_options = (
        options or HistoricalFinalAnswerSelectionValueSignalProposalOptions()
    )
    candidate = _source_candidate(search_report, resolved_options)
    checks = _checks(search_report, candidate=candidate, options=resolved_options)
    runtime_allowed = all(check.status == "passed" for check in checks)
    holdout_allowed = _source_checks_passed(checks) and _no_harm_checks_passed(checks)
    status = _status(runtime_allowed=runtime_allowed, holdout_allowed=holdout_allowed)
    proposal_rule = _proposal_rule(
        search_report,
        candidate,
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
        options=resolved_options,
    )
    proposal_profile_set = _proposal_profile_set_json(
        proposal_rule,
        status=status,
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
        options=resolved_options,
    )
    warnings = _warnings(
        status=status,
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
        checks=checks,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_production_proposal_v3_1"
        ),
        "status": status,
        "runtime_profile_proposal_allowed": runtime_allowed,
        "holdout_candidate_allowed": holdout_allowed,
        "proposal_id": resolved_options.proposal_id,
        "proposed_profile_version": resolved_options.proposed_profile_version,
        "source_search_report_key": search_report.report_key,
        "source_candidate_key": candidate.candidate_key,
        "candidate_decision": candidate.decision,
        "candidate_decision_reasons": list(candidate.decision_reasons),
        "candidate_spec_key": candidate.spec.spec_key,
        "candidate_competition_ids": list(candidate.spec.competition_ids),
        "candidate_outcomes": list(candidate.spec.outcomes),
        "candidate_strength": candidate.spec.strength,
        "candidate_roi": candidate.candidate_roi,
        "candidate_score_min": candidate.spec.score_min,
        "candidate_score_max": candidate.spec.score_max,
        "final_answer_count": candidate.final_answer_count,
        "affected_leg_count": candidate.affected_leg_count,
        "guard_blocked_option_count": candidate.guard_blocked_option_count,
        "changed_final_answer_count": candidate.changed_final_answer_count,
        "final_answer_hit_delta_count": candidate.final_answer_hit_delta_count,
        "roi_delta": candidate.roi_delta,
        "profit_loss_delta": candidate.profit_loss_delta,
        "brier_score_delta": candidate.brier_score_delta,
        "log_loss_delta": candidate.log_loss_delta,
        "mean_calibration_error_delta": candidate.mean_calibration_error_delta,
        "final_hit_harm_count_vs_baseline": (
            candidate.final_hit_harm_count_vs_baseline
        ),
        "profit_loss_harm_count_vs_baseline": (
            candidate.profit_loss_harm_count_vs_baseline
        ),
        "movement_count": candidate.movement_count,
        "positive_movement_count": candidate.positive_movement_count,
        "harmful_movement_count": candidate.harmful_movement_count,
        "probability_quality_harm_movement_count": (
            candidate.probability_quality_harm_movement_count
        ),
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, proposal_rule)
    return HistoricalFinalAnswerSelectionValueSignalProposalReport(
        report_key=report_key,
        status=status,
        runtime_profile_proposal_allowed=runtime_allowed,
        holdout_candidate_allowed=holdout_allowed,
        proposal_count=1 if proposal_rule is not None else 0,
        source_search_report_key=search_report.report_key,
        source_candidate_key=candidate.candidate_key,
        checks=checks,
        proposal_rule=proposal_rule,
        proposal_profile_set_json=proposal_profile_set,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_final_answer_selection_value_signal_proposal_report(
        load_historical_final_answer_selection_value_signal_search_report(
            args.search_report
        ),
        options=_options_from_args(args),
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    if args.profile_output_path is not None and report.holdout_candidate_allowed:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{dumps(report.proposal_profile_set_json, indent=2)}\n",
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
    if not report.runtime_profile_proposal_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _source_candidate(
    search_report: HistoricalFinalAnswerSelectionValueSignalSearchReport,
    options: HistoricalFinalAnswerSelectionValueSignalProposalOptions,
) -> HistoricalFinalAnswerSelectionValueSignalSearchCandidate:
    candidates = search_report.candidates
    if options.source_candidate_key is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.candidate_key == options.source_candidate_key
        ]
    accepted = [candidate for candidate in candidates if candidate.decision == "accepted"]
    if accepted:
        return accepted[0]
    if candidates:
        return candidates[0]
    raise ValueError("Selection-value proposal needs at least one source candidate")


def _checks(
    search_report: HistoricalFinalAnswerSelectionValueSignalSearchReport,
    *,
    candidate: HistoricalFinalAnswerSelectionValueSignalSearchCandidate,
    options: HistoricalFinalAnswerSelectionValueSignalProposalOptions,
) -> list[HistoricalFinalAnswerSelectionValueSignalProposalCheck]:
    return [
        _boolean_check(
            "source_search_has_accepted_candidate",
            search_report.accepted_count > 0,
            enabled=options.require_search_candidate_accepted,
            detail="source search should contain an accepted candidate",
        ),
        _boolean_check(
            "source_candidate_accepted",
            candidate.decision == "accepted",
            enabled=options.require_search_candidate_accepted,
            detail="selected source candidate should be accepted",
        ),
        _boolean_check(
            "source_candidate_has_no_decision_reasons",
            not candidate.decision_reasons,
            enabled=options.require_no_decision_reasons,
            detail="accepted source candidate should not carry rejection reasons",
        ),
        _boolean_check(
            "probability_grid_unchanged",
            search_report.summary_json.get("probability_grid_unchanged") is True
            and candidate.summary_json.get("probability_grid_unchanged") is True,
            enabled=options.require_probability_grid_unchanged,
            detail="selection-value proposal must not rewrite probability grids",
        ),
        _boolean_check(
            "movement_conditioned_spec",
            "movement_clean_positive" in candidate.spec.spec_key,
            enabled=options.require_movement_conditioned_spec,
            detail="proposal should come from movement-conditioned clean evidence",
        ),
        _minimum_check(
            "final_answer_count",
            candidate.final_answer_count,
            options.min_final_answer_count,
            detail="proposal should cover enough final answers",
        ),
        _minimum_check(
            "affected_leg_count",
            candidate.affected_leg_count,
            options.min_affected_leg_count,
            detail="proposal should exercise the selection-value signal",
        ),
        _minimum_check(
            "changed_final_answer_count",
            candidate.changed_final_answer_count,
            options.min_changed_final_answer_count,
            detail="proposal should change at least one final answer in shadow",
        ),
        _minimum_check(
            "positive_movement_count",
            candidate.positive_movement_count,
            options.min_positive_movement_count,
            detail="proposal should preserve at least one positive movement",
        ),
        _maximum_check(
            "harmful_movement_count",
            candidate.harmful_movement_count,
            options.max_harmful_movement_count,
            detail="proposal must not introduce harmful movements",
        ),
        _maximum_check(
            "probability_quality_harm_movement_count",
            candidate.probability_quality_harm_movement_count,
            options.max_probability_quality_harm_movement_count,
            detail="proposal movements should not regress probability quality",
            enabled=options.require_clean_movement_only,
        ),
        _minimum_check(
            "final_answer_hit_delta_count",
            candidate.final_answer_hit_delta_count,
            options.min_final_answer_hit_delta_count,
            detail="proposal should not reduce final-answer hits",
        ),
        _minimum_check(
            "roi_delta",
            candidate.roi_delta,
            options.min_roi_delta,
            detail="proposal should not reduce ROI",
        ),
        _minimum_check(
            "profit_loss_delta",
            candidate.profit_loss_delta,
            options.min_profit_loss_delta,
            detail="proposal should not reduce profit/loss",
        ),
        _minimum_check(
            "candidate_roi",
            candidate.candidate_roi,
            options.min_candidate_roi,
            detail="proposal candidate ROI should clear the configured floor",
        ),
        _maximum_check(
            "brier_score_delta",
            candidate.brier_score_delta,
            options.max_brier_score_delta,
            detail="proposal should not regress Brier score",
        ),
        _maximum_check(
            "log_loss_delta",
            candidate.log_loss_delta,
            options.max_log_loss_delta,
            detail="proposal should not regress log loss",
        ),
        _maximum_check(
            "mean_calibration_error_delta",
            candidate.mean_calibration_error_delta,
            options.max_mean_calibration_error_delta,
            detail="proposal should not regress calibration error",
        ),
        _maximum_check(
            "final_hit_harm_count_vs_baseline",
            candidate.final_hit_harm_count_vs_baseline,
            options.max_final_hit_harm_count_vs_baseline,
            detail="proposal should not harm local final-hit outcomes",
        ),
        _maximum_check(
            "profit_loss_harm_count_vs_baseline",
            candidate.profit_loss_harm_count_vs_baseline,
            options.max_profit_loss_harm_count_vs_baseline,
            detail="proposal should not harm local profit/loss outcomes",
        ),
    ]


def _proposal_rule(
    search_report: HistoricalFinalAnswerSelectionValueSignalSearchReport,
    candidate: HistoricalFinalAnswerSelectionValueSignalSearchCandidate,
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalFinalAnswerSelectionValueSignalProposalOptions,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeRuleProposal | None:
    if not holdout_allowed:
        return None
    spec = candidate.spec
    return HistoricalFinalAnswerSelectionValueSignalRuntimeRuleProposal(
        rule_id=options.proposal_id,
        proposed_profile_version=options.proposed_profile_version,
        proposed_production_enabled=runtime_allowed,
        holdout_candidate_enabled=holdout_allowed,
        competition_ids=list(spec.competition_ids),
        outcomes=list(spec.outcomes),
        probability_min=spec.probability_min,
        probability_max=spec.probability_max,
        min_decimal_odds=spec.min_decimal_odds,
        max_decimal_odds=spec.max_decimal_odds,
        max_model_edge=spec.max_model_edge,
        score_min=spec.score_min,
        score_max=spec.score_max,
        strength=spec.strength,
        max_hit_probability_deficit=spec.max_hit_probability_deficit,
        min_option_roi=spec.min_option_roi,
        max_option_risk_score=spec.max_option_risk_score,
        source_bucket_key=spec.source_bucket_key,
        source_bucket_search_candidate_key=spec.source_bucket_search_candidate_key,
        source_report_keys={
            "selection_value_signal_search": search_report.report_key,
            "selection_value_signal_candidate": candidate.candidate_key,
        },
        constraints_json={
            "probability_grid_unchanged": True,
            "movement_conditioned": "movement_clean_positive" in spec.spec_key,
            "public_default_activation": False,
        },
        evidence_json=_candidate_evidence(candidate),
        rollback_conditions=[
            "disable_if_source_proposal_report_missing_or_failed",
            "disable_if_final_hit_harm_count_above_0",
            "disable_if_profit_loss_harm_count_above_0",
            "disable_if_probability_quality_regresses",
            "disable_if_harmful_movement_count_above_0",
        ],
        notes=[
            "Shadow proposal only; do not enable as default without governed rollout.",
            "Selection-value signal changes final-answer arbitration only.",
            "No probability grid, score grid, or model probability rewrite is allowed.",
        ],
    )


def _proposal_profile_set_json(
    proposal_rule: HistoricalFinalAnswerSelectionValueSignalRuntimeRuleProposal | None,
    *,
    status: HistoricalFinalAnswerSelectionValueSignalProposalStatus,
    runtime_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalFinalAnswerSelectionValueSignalProposalOptions,
) -> dict[str, object]:
    rules = [] if proposal_rule is None else [proposal_rule.model_dump(mode="json")]
    rollback_conditions = (
        [] if proposal_rule is None else list(proposal_rule.rollback_conditions)
    )
    notes = [] if proposal_rule is None else list(proposal_rule.notes)
    return {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_proposal_profile_set_v3_1"
        ),
        "status": status,
        "runtime_profile_proposal_allowed": runtime_allowed,
        "holdout_candidate_allowed": holdout_allowed,
        "proposal_id": options.proposal_id,
        "proposed_profile_version": options.proposed_profile_version,
        "default_recommendation_path_changed": False,
        "final_answer_selection_value_signal_rules": rules,
        "rules": rules,
        "rollback_conditions": rollback_conditions,
        "notes": notes,
    }


def _candidate_evidence(
    candidate: HistoricalFinalAnswerSelectionValueSignalSearchCandidate,
) -> dict[str, object]:
    return {
        "candidate_key": candidate.candidate_key,
        "decision": candidate.decision,
        "final_answer_count": candidate.final_answer_count,
        "affected_leg_count": candidate.affected_leg_count,
        "guard_blocked_option_count": candidate.guard_blocked_option_count,
        "changed_final_answer_count": candidate.changed_final_answer_count,
        "final_answer_hit_delta_count": candidate.final_answer_hit_delta_count,
        "candidate_roi": candidate.candidate_roi,
        "roi_delta": candidate.roi_delta,
        "profit_loss_delta": candidate.profit_loss_delta,
        "brier_score_delta": candidate.brier_score_delta,
        "log_loss_delta": candidate.log_loss_delta,
        "mean_calibration_error_delta": candidate.mean_calibration_error_delta,
        "final_hit_harm_count_vs_baseline": (
            candidate.final_hit_harm_count_vs_baseline
        ),
        "profit_loss_harm_count_vs_baseline": (
            candidate.profit_loss_harm_count_vs_baseline
        ),
        "movement_count": candidate.movement_count,
        "positive_movement_count": candidate.positive_movement_count,
        "harmful_movement_count": candidate.harmful_movement_count,
        "probability_quality_harm_movement_count": (
            candidate.probability_quality_harm_movement_count
        ),
    }


def _boolean_check(
    name: str,
    passed: bool,
    *,
    enabled: bool = True,
    detail: str,
) -> HistoricalFinalAnswerSelectionValueSignalProposalCheck:
    return HistoricalFinalAnswerSelectionValueSignalProposalCheck(
        name=name,
        status="passed" if (not enabled or passed) else "failed",
        actual=passed,
        threshold=True if enabled else None,
        detail=detail,
    )


def _minimum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int,
    *,
    detail: str,
) -> HistoricalFinalAnswerSelectionValueSignalProposalCheck:
    return HistoricalFinalAnswerSelectionValueSignalProposalCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int,
    *,
    detail: str,
    enabled: bool = True,
) -> HistoricalFinalAnswerSelectionValueSignalProposalCheck:
    return HistoricalFinalAnswerSelectionValueSignalProposalCheck(
        name=name,
        status=(
            "passed"
            if not enabled or (actual is not None and actual <= threshold)
            else "failed"
        ),
        actual=actual,
        threshold=threshold if enabled else None,
        detail=detail,
    )


def _source_checks_passed(
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalProposalCheck],
) -> bool:
    source_names = {
        "source_search_has_accepted_candidate",
        "source_candidate_accepted",
        "source_candidate_has_no_decision_reasons",
        "probability_grid_unchanged",
    }
    return all(check.status == "passed" for check in checks if check.name in source_names)


def _no_harm_checks_passed(
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalProposalCheck],
) -> bool:
    harm_names = {
        "final_answer_hit_delta_count",
        "roi_delta",
        "profit_loss_delta",
        "brier_score_delta",
        "log_loss_delta",
        "mean_calibration_error_delta",
        "final_hit_harm_count_vs_baseline",
        "profit_loss_harm_count_vs_baseline",
        "harmful_movement_count",
        "probability_quality_harm_movement_count",
    }
    return all(check.status == "passed" for check in checks if check.name in harm_names)


def _status(
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
) -> HistoricalFinalAnswerSelectionValueSignalProposalStatus:
    if runtime_allowed:
        return "runtime_profile_proposal_ready"
    if holdout_allowed:
        return "holdout_only"
    return "blocked"


def _warnings(
    *,
    status: HistoricalFinalAnswerSelectionValueSignalProposalStatus,
    runtime_allowed: bool,
    holdout_allowed: bool,
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalProposalCheck],
) -> list[str]:
    warnings = [
        f"selection_value_signal_proposal:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    if runtime_allowed:
        warnings.append("selection_value_signal_proposal:ready_for_governed_review")
    elif holdout_allowed:
        warnings.append("selection_value_signal_proposal:holdout_only")
    else:
        warnings.append(f"selection_value_signal_proposal:{status}")
    return warnings


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Create a governed production proposal for selection-value signal candidates."
    )
    parser.add_argument("search_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument("--proposal-id", default="final_answer_selection_value_signal_candidate_v1")
    parser.add_argument(
        "--proposed-profile-version",
        default="v3_1_final_answer_selection_value_signal_runtime_candidate",
    )
    parser.add_argument("--source-candidate-key")
    parser.add_argument("--min-final-answer-count", type=int, default=30)
    parser.add_argument("--min-affected-leg-count", type=int, default=1)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-positive-movement-count", type=int, default=1)
    parser.add_argument("--max-harmful-movement-count", type=int, default=0)
    parser.add_argument("--max-probability-quality-harm-movement-count", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-delta-count", type=int, default=0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float, default=-1.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--max-profit-loss-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--allow-non-accepted-source-candidate", action="store_true")
    parser.add_argument("--allow-decision-reasons", action="store_true")
    parser.add_argument("--allow-probability-grid-change", action="store_true")
    parser.add_argument("--allow-non-movement-conditioned-spec", action="store_true")
    parser.add_argument("--allow-probability-quality-harm-movements", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSelectionValueSignalProposalOptions:
    return HistoricalFinalAnswerSelectionValueSignalProposalOptions(
        proposal_id=args.proposal_id,
        proposed_profile_version=args.proposed_profile_version,
        source_candidate_key=args.source_candidate_key,
        min_final_answer_count=args.min_final_answer_count,
        min_affected_leg_count=args.min_affected_leg_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_positive_movement_count=args.min_positive_movement_count,
        max_harmful_movement_count=args.max_harmful_movement_count,
        max_probability_quality_harm_movement_count=(
            args.max_probability_quality_harm_movement_count
        ),
        min_final_answer_hit_delta_count=args.min_final_answer_hit_delta_count,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        min_candidate_roi=args.min_candidate_roi,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        max_final_hit_harm_count_vs_baseline=(
            args.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            args.max_profit_loss_harm_count_vs_baseline
        ),
        require_search_candidate_accepted=not args.allow_non_accepted_source_candidate,
        require_no_decision_reasons=not args.allow_decision_reasons,
        require_probability_grid_unchanged=not args.allow_probability_grid_change,
        require_movement_conditioned_spec=not args.allow_non_movement_conditioned_spec,
        require_clean_movement_only=not args.allow_probability_quality_harm_movements,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalProposalCheck],
    proposal_rule: HistoricalFinalAnswerSelectionValueSignalRuntimeRuleProposal | None,
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "proposal_rule": (
                    None
                    if proposal_rule is None
                    else proposal_rule.model_dump(mode="json")
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_selection_value_signal_production_proposal:{digest}"


if __name__ == "__main__":
    main()
