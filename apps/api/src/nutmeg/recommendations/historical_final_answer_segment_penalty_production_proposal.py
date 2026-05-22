from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_final_answer_segment_penalty_grid import (
    HistoricalFinalAnswerSegmentPenaltyCandidate,
    HistoricalFinalAnswerSegmentPenaltyGridReport,
)
from nutmeg.recommendations.historical_final_answer_segment_penalty_rolling_admission import (
    HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport,
)

type HistoricalFinalAnswerSegmentPenaltyProductionProposalStatus = Literal[
    "runtime_profile_proposal_ready",
    "holdout_only",
    "blocked",
]
type HistoricalFinalAnswerSegmentPenaltyProductionProposalCheckStatus = Literal[
    "passed",
    "failed",
]


class HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions(BaseModel):
    proposal_id: str = "final_answer_segment_penalty_regime_v1"
    proposed_profile_version: str = (
        "v3_1_final_answer_segment_penalty_runtime_profile_candidate"
    )
    min_final_answer_count: int = Field(default=30, ge=1)
    min_changed_final_answer_count: int = Field(default=1, ge=0)
    min_penalty_option_count: int = Field(default=1, ge=0)
    min_final_answer_hit_count_delta: int = 0
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_candidate_roi: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    max_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_fold_count: int = Field(default=2, ge=0)
    min_active_rolling_fold_count: int = Field(default=2, ge=0)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_grid_candidate_accepted: bool = True
    require_rolling_admission_accepted: bool = True
    require_forward_safe_regime_filter: bool = True
    require_no_explicit_season_ids: bool = True
    require_source_key_linkage: bool = True


class HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(BaseModel):
    name: str
    status: HistoricalFinalAnswerSegmentPenaltyProductionProposalCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalFinalAnswerSegmentPenaltyRuntimeRuleProposal(BaseModel):
    rule_id: str
    proposed_profile_version: str
    proposed_production_enabled: bool
    holdout_candidate_enabled: bool
    production_recommendation_changed: bool = False
    pass_types: list[str] = Field(default_factory=list)
    modes: list[str] = Field(default_factory=list)
    competition_ids: list[str] = Field(default_factory=list)
    season_ids: list[str] = Field(default_factory=list)
    min_competition_season_index: int | None = Field(default=None, ge=1)
    max_competition_season_index: int | None = Field(default=None, ge=1)
    penalty_strength: float = Field(ge=0.0, le=1.0)
    constraints_json: dict[str, object] = Field(default_factory=dict)
    source_report_keys: dict[str, str] = Field(default_factory=dict)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    rollback_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HistoricalFinalAnswerSegmentPenaltyProductionProposalReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSegmentPenaltyProductionProposalStatus
    runtime_profile_proposal_allowed: bool
    holdout_candidate_allowed: bool
    proposal_count: int = Field(ge=0)
    source_grid_report_key: str
    source_rolling_admission_report_key: str
    source_candidate_key: str
    checks: list[HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck] = (
        Field(default_factory=list)
    )
    proposal_rule: HistoricalFinalAnswerSegmentPenaltyRuntimeRuleProposal | None = None
    proposal_profile_set_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_final_answer_segment_penalty_grid_report(
    path: Path | str,
) -> HistoricalFinalAnswerSegmentPenaltyGridReport:
    return HistoricalFinalAnswerSegmentPenaltyGridReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_historical_final_answer_segment_penalty_rolling_admission_report(
    path: Path | str,
) -> HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport:
    return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_final_answer_segment_penalty_production_proposal_report(
    grid_report: HistoricalFinalAnswerSegmentPenaltyGridReport,
    rolling_admission_report: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport,
    *,
    options: HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions | None = None,
) -> HistoricalFinalAnswerSegmentPenaltyProductionProposalReport:
    resolved_options = (
        options or HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions()
    )
    candidate = _source_candidate(grid_report, rolling_admission_report)
    checks = _checks(
        grid_report,
        rolling_admission_report,
        candidate=candidate,
        options=resolved_options,
    )
    runtime_allowed = all(check.status == "passed" for check in checks)
    holdout_allowed = _source_checks_passed(checks) and _holdout_checks_passed(checks)
    status = _status(
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
    )
    proposal_rule = _proposal_rule(
        candidate,
        rolling_admission_report,
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
    overall = rolling_admission_report.overall_fold
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_segment_penalty_production_proposal_v3_1"
        ),
        "status": status,
        "runtime_profile_proposal_allowed": runtime_allowed,
        "holdout_candidate_allowed": holdout_allowed,
        "proposal_id": resolved_options.proposal_id,
        "proposed_profile_version": resolved_options.proposed_profile_version,
        "source_grid_report_key": grid_report.report_key,
        "source_rolling_admission_report_key": rolling_admission_report.report_key,
        "source_candidate_key": candidate.candidate_key,
        "candidate_strength": candidate.strength,
        "candidate_competition_ids": list(candidate.competition_ids),
        "candidate_pass_types": list(candidate.pass_types),
        "candidate_modes": list(candidate.modes),
        "candidate_season_ids": list(candidate.season_ids),
        "candidate_min_competition_season_index": (
            candidate.min_competition_season_index
        ),
        "candidate_max_competition_season_index": (
            candidate.max_competition_season_index
        ),
        "final_answer_count": overall.final_answer_count,
        "changed_final_answer_count": overall.changed_final_answer_count,
        "penalty_option_count": overall.penalty_option_count,
        "baseline_final_answer_hit_count": overall.baseline_final_answer_hit_count,
        "candidate_final_answer_hit_count": overall.candidate_final_answer_hit_count,
        "final_answer_hit_delta_count": overall.final_answer_hit_delta_count,
        "final_answer_hit_rate_delta": overall.final_answer_hit_rate_delta,
        "candidate_roi": candidate.roi,
        "roi_delta": overall.roi_delta,
        "profit_loss_delta": overall.profit_loss_delta,
        "brier_score_delta": overall.brier_score_delta,
        "log_loss_delta": overall.log_loss_delta,
        "mean_calibration_error_delta": overall.mean_calibration_error_delta,
        "harm_count_vs_baseline": overall.harm_count_vs_baseline,
        "final_hit_harm_count_vs_baseline": overall.final_hit_harm_count_vs_baseline,
        "profit_loss_harm_count_vs_baseline": (
            overall.profit_loss_harm_count_vs_baseline
        ),
        "active_competition_fold_count": (
            rolling_admission_report.active_competition_fold_count
        ),
        "active_season_fold_count": rolling_admission_report.active_season_fold_count,
        "active_rolling_fold_count": (
            rolling_admission_report.active_rolling_fold_count
        ),
        "failed_fold_count": rolling_admission_report.failed_fold_count,
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, proposal_rule)
    return HistoricalFinalAnswerSegmentPenaltyProductionProposalReport(
        report_key=report_key,
        status=status,
        runtime_profile_proposal_allowed=runtime_allowed,
        holdout_candidate_allowed=holdout_allowed,
        proposal_count=1 if proposal_rule is not None else 0,
        source_grid_report_key=grid_report.report_key,
        source_rolling_admission_report_key=rolling_admission_report.report_key,
        source_candidate_key=candidate.candidate_key,
        checks=checks,
        proposal_rule=proposal_rule,
        proposal_profile_set_json=proposal_profile_set,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_final_answer_segment_penalty_production_proposal_report(
        load_historical_final_answer_segment_penalty_grid_report(args.grid_report),
        load_historical_final_answer_segment_penalty_rolling_admission_report(
            args.rolling_admission_report
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
    grid_report: HistoricalFinalAnswerSegmentPenaltyGridReport,
    rolling_admission_report: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport,
) -> HistoricalFinalAnswerSegmentPenaltyCandidate:
    candidates = [*grid_report.accepted_candidates, *grid_report.candidates]
    candidate = next(
        (
            candidate
            for candidate in candidates
            if candidate.candidate_key == rolling_admission_report.source_candidate_key
        ),
        None,
    )
    if candidate is not None:
        return candidate
    if grid_report.best_candidate is not None:
        return grid_report.best_candidate
    raise ValueError("Grid report has no candidate matching rolling admission")


def _checks(
    grid_report: HistoricalFinalAnswerSegmentPenaltyGridReport,
    rolling_admission_report: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport,
    *,
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
    options: HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions,
) -> list[HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck]:
    overall = rolling_admission_report.overall_fold
    checks = [
        _boolean_check(
            name="grid_report_generated",
            actual=grid_report.status == "generated",
            expected=True,
            detail="source grid report must be generated",
        ),
        _equality_check(
            name="rolling_admission_grid_key",
            actual=rolling_admission_report.source_grid_report_key,
            expected=grid_report.report_key,
            enabled=options.require_source_key_linkage,
            detail="rolling admission must be linked to the supplied grid report",
        ),
        _equality_check(
            name="rolling_admission_candidate_key",
            actual=rolling_admission_report.source_candidate_key,
            expected=candidate.candidate_key,
            enabled=options.require_source_key_linkage,
            detail="rolling admission must be linked to the selected grid candidate",
        ),
        _boolean_check(
            name="grid_candidate_accepted",
            actual=candidate.status == "accepted",
            expected=True,
            enabled=options.require_grid_candidate_accepted,
            detail="selected grid candidate should be accepted",
        ),
        _equality_check(
            name="rolling_admission_status",
            actual=rolling_admission_report.status,
            expected="accepted",
            enabled=options.require_rolling_admission_accepted,
            detail="rolling admission must be accepted before profile proposal",
        ),
        _boolean_check(
            name="forward_safe_regime_filter_present",
            actual=(
                candidate.min_competition_season_index is not None
                or candidate.max_competition_season_index is not None
            ),
            expected=True,
            enabled=options.require_forward_safe_regime_filter,
            detail="candidate should use competition season index instead of only season IDs",
        ),
        _boolean_check(
            name="explicit_season_ids_absent",
            actual=not candidate.season_ids,
            expected=True,
            enabled=options.require_no_explicit_season_ids,
            detail="runtime candidates must not depend on hindsight season IDs",
        ),
        _minimum_check(
            name="final_answer_count",
            actual=overall.final_answer_count,
            threshold=options.min_final_answer_count,
            detail="proposal should cover enough historical final answers",
        ),
        _minimum_check(
            name="changed_final_answer_count",
            actual=overall.changed_final_answer_count,
            threshold=options.min_changed_final_answer_count,
            detail="proposal should affect enough final answers to be meaningful",
        ),
        _minimum_check(
            name="penalty_option_count",
            actual=overall.penalty_option_count,
            threshold=options.min_penalty_option_count,
            detail="proposal should exercise the segment penalty",
        ),
        _minimum_check(
            name="final_answer_hit_count_delta",
            actual=overall.final_answer_hit_delta_count,
            threshold=options.min_final_answer_hit_count_delta,
            detail="candidate final-answer hit count should not regress",
        ),
        _minimum_check(
            name="final_answer_hit_rate_delta",
            actual=overall.final_answer_hit_rate_delta,
            threshold=options.min_final_answer_hit_rate_delta,
            detail="candidate final-answer hit rate should not regress",
        ),
        _minimum_check(
            name="roi_delta",
            actual=overall.roi_delta,
            threshold=options.min_roi_delta,
            detail="candidate ROI delta should not regress",
        ),
        _minimum_check(
            name="profit_loss_delta",
            actual=overall.profit_loss_delta,
            threshold=options.min_profit_loss_delta,
            detail="candidate profit/loss delta should not regress",
        ),
        _minimum_check(
            name="candidate_roi",
            actual=candidate.roi,
            threshold=options.min_candidate_roi,
            detail="candidate absolute ROI should clear the runtime proposal floor",
        ),
        _maximum_check(
            name="brier_score_delta",
            actual=overall.brier_score_delta,
            threshold=options.max_brier_score_delta,
            detail="candidate Brier score should not regress",
        ),
        _maximum_check(
            name="log_loss_delta",
            actual=overall.log_loss_delta,
            threshold=options.max_log_loss_delta,
            detail="candidate log loss should not regress",
        ),
        _maximum_check(
            name="mean_calibration_error_delta",
            actual=overall.mean_calibration_error_delta,
            threshold=options.max_mean_calibration_error_delta,
            detail="candidate calibration error should not regress",
        ),
        _maximum_check(
            name="harm_count_vs_baseline",
            actual=overall.harm_count_vs_baseline,
            threshold=options.max_harm_count_vs_baseline,
            detail="candidate should not turn correct final answers into misses",
        ),
        _maximum_check(
            name="final_hit_harm_count_vs_baseline",
            actual=overall.final_hit_harm_count_vs_baseline,
            threshold=options.max_final_hit_harm_count_vs_baseline,
            detail="candidate should not reduce original final-answer hit counts",
        ),
        _maximum_check(
            name="profit_loss_harm_count_vs_baseline",
            actual=overall.profit_loss_harm_count_vs_baseline,
            threshold=options.max_profit_loss_harm_count_vs_baseline,
            detail="candidate should not reduce original final-answer profit/loss",
        ),
        _maximum_check(
            name="failed_fold_count",
            actual=rolling_admission_report.failed_fold_count,
            threshold=options.max_failed_fold_count,
            detail="rolling admission must not have failing active folds",
        ),
        _minimum_check(
            name="active_competition_fold_count",
            actual=rolling_admission_report.active_competition_fold_count,
            threshold=options.min_active_competition_fold_count,
            detail="rolling admission must cover enough active competition folds",
        ),
        _minimum_check(
            name="active_season_fold_count",
            actual=rolling_admission_report.active_season_fold_count,
            threshold=options.min_active_season_fold_count,
            detail="rolling admission must cover enough active season folds",
        ),
        _minimum_check(
            name="active_rolling_fold_count",
            actual=rolling_admission_report.active_rolling_fold_count,
            threshold=options.min_active_rolling_fold_count,
            detail="rolling admission must cover enough active rolling-window folds",
        ),
    ]
    return checks


def _proposal_rule(
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
    rolling_admission_report: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport,
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeRuleProposal | None:
    if not holdout_allowed:
        return None
    overall = rolling_admission_report.overall_fold
    constraints = {
        "final_answer_segment_penalty": True,
        "final_answer_segment_penalty_strength": candidate.strength,
        "final_answer_segment_pass_types": list(candidate.pass_types),
        "final_answer_segment_modes": list(candidate.modes),
        "final_answer_segment_competition_ids": list(candidate.competition_ids),
        "final_answer_segment_season_ids": list(candidate.season_ids),
        "final_answer_segment_min_competition_season_index": (
            candidate.min_competition_season_index
        ),
        "final_answer_segment_max_competition_season_index": (
            candidate.max_competition_season_index
        ),
        "final_answer_segment_min_hit_probability": candidate.min_hit_probability,
        "final_answer_segment_max_hit_probability": candidate.max_hit_probability,
        "final_answer_segment_min_odds_product": candidate.min_odds_product,
        "final_answer_segment_max_odds_product": candidate.max_odds_product,
        "final_answer_segment_min_average_leg_decimal_odds": (
            candidate.min_average_leg_decimal_odds
        ),
        "final_answer_segment_max_average_leg_decimal_odds": (
            candidate.max_average_leg_decimal_odds
        ),
    }
    return HistoricalFinalAnswerSegmentPenaltyRuntimeRuleProposal(
        rule_id=options.proposal_id,
        proposed_profile_version=options.proposed_profile_version,
        proposed_production_enabled=runtime_allowed,
        holdout_candidate_enabled=holdout_allowed,
        production_recommendation_changed=False,
        pass_types=list(candidate.pass_types),
        modes=[str(mode) for mode in candidate.modes],
        competition_ids=list(candidate.competition_ids),
        season_ids=list(candidate.season_ids),
        min_competition_season_index=candidate.min_competition_season_index,
        max_competition_season_index=candidate.max_competition_season_index,
        penalty_strength=candidate.strength,
        constraints_json={
            key: value for key, value in constraints.items() if value is not None
        },
        source_report_keys={
            "grid": rolling_admission_report.source_grid_report_key,
            "rolling_admission": rolling_admission_report.report_key,
            "candidate": candidate.candidate_key,
        },
        evidence_json={
            "final_answer_count": overall.final_answer_count,
            "changed_final_answer_count": overall.changed_final_answer_count,
            "penalty_option_count": overall.penalty_option_count,
            "baseline_final_answer_hit_count": (
                overall.baseline_final_answer_hit_count
            ),
            "candidate_final_answer_hit_count": (
                overall.candidate_final_answer_hit_count
            ),
            "final_answer_hit_delta_count": overall.final_answer_hit_delta_count,
            "final_answer_hit_rate_delta": overall.final_answer_hit_rate_delta,
            "candidate_roi": candidate.roi,
            "roi_delta": overall.roi_delta,
            "profit_loss_delta": overall.profit_loss_delta,
            "brier_score_delta": overall.brier_score_delta,
            "log_loss_delta": overall.log_loss_delta,
            "mean_calibration_error_delta": overall.mean_calibration_error_delta,
            "harm_count_vs_baseline": overall.harm_count_vs_baseline,
            "final_hit_harm_count_vs_baseline": (
                overall.final_hit_harm_count_vs_baseline
            ),
            "profit_loss_harm_count_vs_baseline": (
                overall.profit_loss_harm_count_vs_baseline
            ),
            "active_competition_fold_count": (
                rolling_admission_report.active_competition_fold_count
            ),
            "active_season_fold_count": (
                rolling_admission_report.active_season_fold_count
            ),
            "active_rolling_fold_count": (
                rolling_admission_report.active_rolling_fold_count
            ),
            "failed_fold_count": rolling_admission_report.failed_fold_count,
            "rolling_admission_status": rolling_admission_report.status,
        },
        rollback_conditions=_rollback_conditions(options),
        notes=[
            "Governed runtime-profile proposal artifact only; default profile is unchanged.",
            "Holdout-only status can be used for expanded historical validation, not production.",
            "Do not expose this internal strategy label to ordinary users.",
            "No automated betting, wallet, payment, or guaranteed-outcome behavior is introduced.",
        ],
    )


def _proposal_profile_set_json(
    proposal_rule: HistoricalFinalAnswerSegmentPenaltyRuntimeRuleProposal | None,
    *,
    status: HistoricalFinalAnswerSegmentPenaltyProductionProposalStatus,
    runtime_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions,
) -> dict[str, object]:
    return {
        "profile_version": options.proposed_profile_version,
        "calculation_basis": (
            "historical_final_answer_segment_penalty_production_proposal_v3_1"
        ),
        "status": status,
        "runtime_profile_proposal_allowed": runtime_allowed,
        "holdout_candidate_allowed": holdout_allowed,
        "production_recommendation_changed": False,
        "final_answer_segment_penalty_rules": [
            proposal_rule.model_dump(mode="json")
            for proposal_rule in [proposal_rule]
            if proposal_rule is not None
        ],
        "notes": [
            "This artifact is not a default production profile.",
            "Runtime activation requires a separate promotion/smoke step.",
            "Absolute ROI and expanded holdout evidence must pass before production.",
        ],
    }


def _rollback_conditions(
    options: HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions,
) -> list[str]:
    return [
        "disable_if_rolling_admission_report_missing_or_failed",
        "disable_if_source_report_key_mismatch_or_missing",
        "disable_if_hindsight_season_ids_present",
        (
            "disable_if_failed_fold_count_above_"
            f"{options.max_failed_fold_count}"
        ),
        (
            "disable_if_final_answer_hit_count_delta_below_"
            f"{options.min_final_answer_hit_count_delta}"
        ),
        (
            "disable_if_final_answer_hit_rate_delta_below_"
            f"{options.min_final_answer_hit_rate_delta}"
        ),
        f"disable_if_roi_delta_below_{options.min_roi_delta}",
        f"disable_if_profit_loss_delta_below_{options.min_profit_loss_delta}",
        f"disable_if_absolute_candidate_roi_below_{options.min_candidate_roi}",
        (
            "disable_if_harm_count_vs_baseline_above_"
            f"{options.max_harm_count_vs_baseline}"
        ),
        (
            "disable_if_final_hit_harm_count_vs_baseline_above_"
            f"{options.max_final_hit_harm_count_vs_baseline}"
        ),
        (
            "disable_if_profit_loss_harm_count_vs_baseline_above_"
            f"{options.max_profit_loss_harm_count_vs_baseline}"
        ),
        "disable_if_public_response_shape_changes",
        "disable_if_default_profile_write_is_not_explicitly_approved",
    ]


def _status(
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
) -> HistoricalFinalAnswerSegmentPenaltyProductionProposalStatus:
    if runtime_allowed:
        return "runtime_profile_proposal_ready"
    if holdout_allowed:
        return "holdout_only"
    return "blocked"


def _source_checks_passed(
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck],
) -> bool:
    source_check_names = {
        "grid_report_generated",
        "rolling_admission_grid_key",
        "rolling_admission_candidate_key",
        "grid_candidate_accepted",
        "rolling_admission_status",
        "forward_safe_regime_filter_present",
        "explicit_season_ids_absent",
    }
    return all(
        check.status == "passed"
        for check in checks
        if check.name in source_check_names
    )


def _holdout_checks_passed(
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck],
) -> bool:
    ignored_for_holdout = {"candidate_roi"}
    return all(
        check.status == "passed"
        for check in checks
        if check.name not in ignored_for_holdout
    )


def _warnings(
    *,
    status: HistoricalFinalAnswerSegmentPenaltyProductionProposalStatus,
    runtime_allowed: bool,
    holdout_allowed: bool,
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck],
) -> list[str]:
    warnings: list[str] = []
    if status == "holdout_only":
        warnings.append(
            "final_answer_segment_penalty_production_proposal:holdout_only"
        )
    elif status == "blocked":
        warnings.append("final_answer_segment_penalty_production_proposal:blocked")
    if holdout_allowed and not runtime_allowed:
        warnings.append(
            "final_answer_segment_penalty_production_proposal:runtime_profile_not_ready"
        )
    for check in checks:
        if check.status == "failed":
            warnings.append(
                "final_answer_segment_penalty_production_proposal:failed_check:"
                f"{check.name}"
            )
    return warnings


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck:
    if not enabled:
        return HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(
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
    expected: str,
    detail: str,
    enabled: bool = True,
) -> HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck:
    if not enabled:
        return HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(
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
) -> HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck:
    if actual is None:
        return HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(
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
) -> HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck:
    if actual is None:
        return HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build a governed production/holdout proposal for final-answer "
            "segment penalty candidates."
        )
    )
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--rolling-admission-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument(
        "--proposal-id",
        default="final_answer_segment_penalty_regime_v1",
    )
    parser.add_argument(
        "--proposed-profile-version",
        default="v3_1_final_answer_segment_penalty_runtime_profile_candidate",
    )
    parser.add_argument("--min-final-answer-count", type=int, default=30)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-penalty-option-count", type=int, default=1)
    parser.add_argument("--min-final-answer-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument(
        "--max-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument("--min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--min-active-season-fold-count", type=int, default=2)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=2)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-rejected-grid-candidate", action="store_true")
    parser.add_argument("--allow-unaccepted-rolling-admission", action="store_true")
    parser.add_argument("--allow-non-regime-filter", action="store_true")
    parser.add_argument("--allow-explicit-season-ids", action="store_true")
    parser.add_argument("--allow-source-key-mismatch", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions:
    return HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions(
        proposal_id=args.proposal_id,
        proposed_profile_version=args.proposed_profile_version,
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_penalty_option_count=args.min_penalty_option_count,
        min_final_answer_hit_count_delta=args.min_final_answer_hit_count_delta,
        min_final_answer_hit_rate_delta=args.min_final_answer_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        min_candidate_roi=args.min_candidate_roi,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        max_harm_count_vs_baseline=args.max_harm_count_vs_baseline,
        max_final_hit_harm_count_vs_baseline=(
            args.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            args.max_profit_loss_harm_count_vs_baseline
        ),
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_fold_count=args.min_active_season_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        max_failed_fold_count=args.max_failed_fold_count,
        require_grid_candidate_accepted=not args.allow_rejected_grid_candidate,
        require_rolling_admission_accepted=not args.allow_unaccepted_rolling_admission,
        require_forward_safe_regime_filter=not args.allow_non_regime_filter,
        require_no_explicit_season_ids=not args.allow_explicit_season_ids,
        require_source_key_linkage=not args.allow_source_key_mismatch,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck],
    proposal_rule: HistoricalFinalAnswerSegmentPenaltyRuntimeRuleProposal | None,
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "proposal_rule": (
            proposal_rule.model_dump(mode="json") if proposal_rule is not None else None
        ),
    }
    digest = sha256(
        dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_segment_penalty_production_proposal:{digest}"
