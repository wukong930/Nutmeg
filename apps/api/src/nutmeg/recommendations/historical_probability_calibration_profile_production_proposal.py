from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationProfile,
)
from nutmeg.recommendations.historical_probability_calibration_profile_grid import (
    HistoricalProbabilityCalibrationProfileGridCandidate,
    HistoricalProbabilityCalibrationProfileGridReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_rolling_admission import (
    HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
)

type HistoricalProbabilityCalibrationProfileProductionProposalStatus = Literal[
    "runtime_profile_proposal_ready",
    "holdout_only",
    "blocked",
]
type HistoricalProbabilityCalibrationProfileProductionProposalCheckStatus = Literal[
    "passed",
    "failed",
]

_FLOAT_TOLERANCE = 1e-9


class HistoricalProbabilityCalibrationProfileProductionProposalOptions(BaseModel):
    proposal_id: str = "probability_calibration_profile_runtime_candidate_v1"
    proposed_profile_version: str = (
        "v3_1_probability_calibration_profile_runtime_candidate"
    )
    min_overall_adjusted_fixture_count: int = Field(default=1, ge=0)
    min_overall_bucket_count: int = Field(default=1, ge=0)
    min_profile_bucket_count: int = Field(default=1, ge=0)
    min_final_answer_changed_count: int = Field(default=1, ge=0)
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_cutoff_fold_count: int = Field(default=1, ge=0)
    min_active_rolling_fold_count: int = Field(default=1, ge=0)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_grid_candidate_accepted: bool = True
    require_candidate_fold_objective_accepted: bool = True
    require_rolling_admission_accepted: bool = True
    require_candidate_profile_allowed: bool = True
    require_active_profile: bool = True
    require_source_key_linkage: bool = True
    require_profile_candidate_match: bool = True


class HistoricalProbabilityCalibrationProfileProductionProposalCheck(BaseModel):
    name: str
    status: HistoricalProbabilityCalibrationProfileProductionProposalCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalProbabilityCalibrationRuntimeProfileProposal(BaseModel):
    profile_id: str
    proposed_profile_version: str
    proposed_production_enabled: bool
    holdout_candidate_enabled: bool
    production_recommendation_changed: bool = False
    profile_key: str
    profile_mode: str
    segment_mode: str
    target_competition_ids: list[str] = Field(default_factory=list)
    target_market_types: list[str] = Field(default_factory=list)
    target_outcomes: list[str] = Field(default_factory=list)
    min_probability: float
    max_probability: float
    min_decimal_odds: float | None = None
    max_decimal_odds: float | None = None
    blend_weight: float = Field(ge=0.0, le=1.0)
    bucket_count: int = Field(ge=0)
    min_bucket_sample_size: int = Field(ge=1)
    constraints_json: dict[str, object] = Field(default_factory=dict)
    source_report_keys: dict[str, str] = Field(default_factory=dict)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    rollback_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HistoricalProbabilityCalibrationProfileProductionProposalReport(BaseModel):
    report_key: str
    status: HistoricalProbabilityCalibrationProfileProductionProposalStatus
    runtime_profile_proposal_allowed: bool
    holdout_candidate_allowed: bool
    proposal_count: int = Field(ge=0)
    source_grid_report_key: str
    source_rolling_admission_report_key: str
    source_candidate_key: str
    source_profile_key: str
    checks: list[HistoricalProbabilityCalibrationProfileProductionProposalCheck] = (
        Field(default_factory=list)
    )
    proposal_profile: HistoricalProbabilityCalibrationRuntimeProfileProposal | None = (
        None
    )
    proposal_profile_set_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_probability_calibration_profile_grid_report(
    path: Path | str,
) -> HistoricalProbabilityCalibrationProfileGridReport:
    return HistoricalProbabilityCalibrationProfileGridReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_historical_probability_calibration_profile_rolling_admission_report(
    path: Path | str,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport:
    return HistoricalProbabilityCalibrationProfileRollingAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_candidate_probability_calibration_profile(
    path: Path | str,
) -> CandidateProbabilityCalibrationProfile:
    return CandidateProbabilityCalibrationProfile.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_probability_calibration_profile_production_proposal_report(
    grid_report: HistoricalProbabilityCalibrationProfileGridReport,
    rolling_admission_report: HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    *,
    candidate_profile: CandidateProbabilityCalibrationProfile | None = None,
    options: (
        HistoricalProbabilityCalibrationProfileProductionProposalOptions | None
    ) = None,
) -> HistoricalProbabilityCalibrationProfileProductionProposalReport:
    resolved_options = (
        options
        or HistoricalProbabilityCalibrationProfileProductionProposalOptions()
    )
    resolved_profile = candidate_profile or rolling_admission_report.profile
    if resolved_profile is None:
        raise ValueError("Probability calibration production proposal needs a profile")
    candidate = _source_candidate(
        grid_report,
        rolling_admission_report,
        profile=resolved_profile,
    )
    checks = _checks(
        grid_report,
        rolling_admission_report,
        candidate_profile=resolved_profile,
        candidate=candidate,
        options=resolved_options,
    )
    runtime_allowed = all(check.status == "passed" for check in checks)
    holdout_allowed = _source_checks_passed(checks) and _holdout_checks_passed(checks)
    status = _status(
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
    )
    proposal_profile = _proposal_profile(
        grid_report,
        candidate,
        rolling_admission_report,
        resolved_profile,
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
        options=resolved_options,
    )
    proposal_profile_set = _proposal_profile_set_json(
        proposal_profile,
        resolved_profile,
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
            "historical_probability_calibration_profile_production_proposal_v3_1"
        ),
        "status": status,
        "runtime_profile_proposal_allowed": runtime_allowed,
        "holdout_candidate_allowed": holdout_allowed,
        "proposal_id": resolved_options.proposal_id,
        "proposed_profile_version": resolved_options.proposed_profile_version,
        "source_grid_report_key": grid_report.report_key,
        "source_rolling_admission_report_key": rolling_admission_report.report_key,
        "source_candidate_key": candidate.candidate_key,
        "source_profile_key": resolved_profile.profile_key,
        "target_outcomes": list(resolved_profile.target_outcomes),
        "target_competition_ids": list(resolved_profile.target_competition_ids),
        "target_market_types": [str(item) for item in resolved_profile.target_market_types],
        "profile_mode": resolved_profile.mode,
        "profile_segment_mode": resolved_profile.segment_mode,
        "profile_bucket_count": len(resolved_profile.buckets),
        "profile_source_report_key": resolved_profile.source_report_key,
        "rolling_admission_status": rolling_admission_report.status,
        "rolling_candidate_profile_allowed": (
            rolling_admission_report.candidate_profile_allowed
        ),
        "rolling_shadow_allowed": rolling_admission_report.shadow_allowed,
        "overall_adjusted_fixture_count": (
            rolling_admission_report.overall_fold.adjusted_fixture_count
        ),
        "overall_bucket_count": rolling_admission_report.overall_fold.bucket_count,
        "failed_fold_count": rolling_admission_report.failed_fold_count,
        "active_competition_fold_count": (
            rolling_admission_report.active_competition_fold_count
        ),
        "active_season_cutoff_fold_count": (
            rolling_admission_report.active_season_cutoff_fold_count
        ),
        "active_rolling_fold_count": (
            rolling_admission_report.active_rolling_fold_count
        ),
        "final_answer_changed_count": _candidate_delta_number(
            candidate,
            "final_answer_changed_count",
        ),
        "final_hit_rate_delta": (
            rolling_admission_report.overall_fold.final_hit_rate_delta
        ),
        "roi_delta": rolling_admission_report.overall_fold.roi_delta,
        "profit_loss_delta": (
            rolling_admission_report.overall_fold.profit_loss_delta
        ),
        "brier_score_delta": (
            rolling_admission_report.overall_fold.brier_score_delta
        ),
        "log_loss_delta": rolling_admission_report.overall_fold.log_loss_delta,
        "mean_calibration_error_delta": (
            rolling_admission_report.overall_fold.mean_calibration_error_delta
        ),
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, proposal_profile)
    return HistoricalProbabilityCalibrationProfileProductionProposalReport(
        report_key=report_key,
        status=status,
        runtime_profile_proposal_allowed=runtime_allowed,
        holdout_candidate_allowed=holdout_allowed,
        proposal_count=1 if proposal_profile is not None else 0,
        source_grid_report_key=grid_report.report_key,
        source_rolling_admission_report_key=rolling_admission_report.report_key,
        source_candidate_key=candidate.candidate_key,
        source_profile_key=resolved_profile.profile_key,
        checks=checks,
        proposal_profile=proposal_profile,
        proposal_profile_set_json=proposal_profile_set,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = (
        build_historical_probability_calibration_profile_production_proposal_report(
            load_historical_probability_calibration_profile_grid_report(
                args.grid_report
            ),
            load_historical_probability_calibration_profile_rolling_admission_report(
                args.rolling_admission_report
            ),
            candidate_profile=load_candidate_probability_calibration_profile(
                args.candidate_profile
            ),
            options=_options_from_args(args),
        )
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
    grid_report: HistoricalProbabilityCalibrationProfileGridReport,
    rolling_admission_report: HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    *,
    profile: CandidateProbabilityCalibrationProfile,
) -> HistoricalProbabilityCalibrationProfileGridCandidate:
    candidates = _unique_candidates(
        [*grid_report.accepted_candidates, *grid_report.candidates]
    )
    report_key_match = next(
        (
            candidate
            for candidate in candidates
            if candidate.fold_objective_report_key == rolling_admission_report.report_key
        ),
        None,
    )
    if report_key_match is not None:
        return report_key_match
    profile_matches = [
        candidate
        for candidate in candidates
        if _profile_matches_candidate(profile, candidate)
    ]
    accepted_profile_matches = [
        candidate for candidate in profile_matches if candidate.decision == "accepted"
    ]
    if accepted_profile_matches:
        return sorted(accepted_profile_matches, key=_candidate_sort_key)[0]
    if profile_matches:
        return sorted(profile_matches, key=_candidate_sort_key)[0]
    if grid_report.best_candidate is not None:
        return grid_report.best_candidate
    raise ValueError("Grid report has no candidate matching calibration profile")


def _unique_candidates(
    candidates: Sequence[HistoricalProbabilityCalibrationProfileGridCandidate],
) -> list[HistoricalProbabilityCalibrationProfileGridCandidate]:
    seen: set[str] = set()
    unique: list[HistoricalProbabilityCalibrationProfileGridCandidate] = []
    for candidate in candidates:
        if candidate.candidate_key in seen:
            continue
        seen.add(candidate.candidate_key)
        unique.append(candidate)
    return unique


def _candidate_sort_key(
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate,
) -> tuple[int, int]:
    rank = candidate.rank if candidate.rank else 1_000_000
    return (rank, candidate.candidate_index)


def _checks(
    grid_report: HistoricalProbabilityCalibrationProfileGridReport,
    rolling_admission_report: HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    *,
    candidate_profile: CandidateProbabilityCalibrationProfile,
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate,
    options: HistoricalProbabilityCalibrationProfileProductionProposalOptions,
) -> list[HistoricalProbabilityCalibrationProfileProductionProposalCheck]:
    overall = rolling_admission_report.overall_fold
    rolling_profile = rolling_admission_report.profile
    candidate_final_answer_changed_count = _candidate_delta_number(
        candidate,
        "final_answer_changed_count",
    )
    checks = [
        _boolean_check(
            name="grid_report_generated",
            actual=grid_report.status == "generated",
            expected=True,
            detail="source profile grid report must be generated",
        ),
        _boolean_check(
            name="grid_candidate_accepted",
            actual=candidate.decision == "accepted",
            expected=True,
            enabled=options.require_grid_candidate_accepted,
            detail="selected grid candidate should be accepted",
        ),
        _equality_check(
            name="grid_candidate_fold_objective_status",
            actual=candidate.fold_objective_status,
            expected="accepted",
            enabled=options.require_candidate_fold_objective_accepted,
            detail="selected grid candidate should pass fold-objective admission",
        ),
        _boolean_check(
            name="grid_candidate_fold_objective_allowed",
            actual=bool(candidate.fold_objective_candidate_profile_allowed),
            expected=True,
            enabled=options.require_candidate_fold_objective_accepted,
            detail="selected grid candidate should be fold-objective profile-allowed",
        ),
        _equality_check(
            name="rolling_admission_status",
            actual=rolling_admission_report.status,
            expected="accepted",
            enabled=options.require_rolling_admission_accepted,
            detail="rolling admission must be accepted before profile proposal",
        ),
        _boolean_check(
            name="rolling_candidate_profile_allowed",
            actual=rolling_admission_report.candidate_profile_allowed,
            expected=True,
            enabled=options.require_candidate_profile_allowed,
            detail="rolling admission should allow staged candidate profile",
        ),
        _boolean_check(
            name="rolling_shadow_allowed",
            actual=rolling_admission_report.shadow_allowed,
            expected=True,
            detail="rolling admission should remain shadow-allowed",
        ),
        _equality_check(
            name="candidate_profile_mode",
            actual=candidate_profile.mode,
            expected="active",
            enabled=options.require_active_profile,
            detail="candidate profile should be active for runtime proposal",
        ),
        _equality_check(
            name="rolling_profile_key",
            actual=rolling_profile.profile_key if rolling_profile is not None else None,
            expected=candidate_profile.profile_key,
            enabled=(
                options.require_source_key_linkage
                and rolling_profile is not None
            ),
            detail="external candidate profile should match rolling admission profile",
        ),
        _profile_source_linkage_check(
            candidate_profile,
            rolling_admission_report,
            enabled=options.require_source_key_linkage,
        ),
        _boolean_check(
            name="profile_matches_grid_candidate",
            actual=_profile_matches_candidate(candidate_profile, candidate),
            expected=True,
            enabled=options.require_profile_candidate_match,
            detail="candidate profile constraints should match selected grid candidate",
        ),
        _boolean_check(
            name="rolling_metrics_match_grid_candidate",
            actual=_rolling_metrics_match_candidate(
                rolling_admission_report,
                candidate,
            ),
            expected=True,
            enabled=options.require_profile_candidate_match,
            detail="rolling admission objective metrics should match grid candidate",
        ),
        _minimum_check(
            name="overall_adjusted_fixture_count",
            actual=overall.adjusted_fixture_count,
            threshold=options.min_overall_adjusted_fixture_count,
            detail="proposal should adjust enough held-out fixtures",
        ),
        _minimum_check(
            name="overall_bucket_count",
            actual=overall.bucket_count,
            threshold=options.min_overall_bucket_count,
            detail="rolling admission should emit enough usable buckets",
        ),
        _minimum_check(
            name="profile_bucket_count",
            actual=len(candidate_profile.buckets),
            threshold=options.min_profile_bucket_count,
            detail="candidate profile should contain enough runtime buckets",
        ),
        _minimum_check(
            name="final_answer_changed_count",
            actual=candidate_final_answer_changed_count,
            threshold=options.min_final_answer_changed_count,
            detail="candidate should move enough final answers to be meaningful",
        ),
        _minimum_check(
            name="final_hit_rate_delta",
            actual=overall.final_hit_rate_delta,
            threshold=options.min_final_hit_rate_delta,
            detail="candidate final-answer hit-rate delta should not regress",
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
            name="active_season_cutoff_fold_count",
            actual=rolling_admission_report.active_season_cutoff_fold_count,
            threshold=options.min_active_season_cutoff_fold_count,
            detail="rolling admission must cover enough active season-cutoff folds",
        ),
        _minimum_check(
            name="active_rolling_fold_count",
            actual=rolling_admission_report.active_rolling_fold_count,
            threshold=options.min_active_rolling_fold_count,
            detail="rolling admission must cover enough active rolling-window folds",
        ),
    ]
    return checks


def _profile_source_linkage_check(
    profile: CandidateProbabilityCalibrationProfile,
    rolling_admission_report: HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    *,
    enabled: bool,
) -> HistoricalProbabilityCalibrationProfileProductionProposalCheck:
    accepted_sources = {
        key
        for key in (
            rolling_admission_report.source_gate_report_key,
            rolling_admission_report.overall_fold.gate_report_key,
        )
        if key is not None
    }
    if not enabled:
        return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
            name="candidate_profile_source_report_key",
            status="passed",
            actual=profile.source_report_key,
            threshold="not_required",
            detail="candidate profile should link to rolling admission gate evidence",
        )
    return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
        name="candidate_profile_source_report_key",
        status=(
            "passed"
            if profile.source_report_key in accepted_sources
            else "failed"
        ),
        actual=profile.source_report_key,
        threshold="|".join(sorted(accepted_sources)) if accepted_sources else None,
        detail="candidate profile should link to rolling admission gate evidence",
    )


def _proposal_profile(
    grid_report: HistoricalProbabilityCalibrationProfileGridReport,
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate,
    rolling_admission_report: HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    candidate_profile: CandidateProbabilityCalibrationProfile,
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalProbabilityCalibrationProfileProductionProposalOptions,
) -> HistoricalProbabilityCalibrationRuntimeProfileProposal | None:
    if not holdout_allowed:
        return None
    overall = rolling_admission_report.overall_fold
    constraints = {
        "probability_calibration_profile_key": candidate_profile.profile_key,
        "probability_calibration_profile_mode": candidate_profile.mode,
        "probability_calibration_segment_mode": candidate_profile.segment_mode,
        "probability_calibration_target_competition_ids": list(
            candidate_profile.target_competition_ids
        ),
        "probability_calibration_target_market_types": [
            str(item) for item in candidate_profile.target_market_types
        ],
        "probability_calibration_target_outcomes": list(
            candidate_profile.target_outcomes
        ),
        "probability_calibration_min_probability": candidate_profile.min_probability,
        "probability_calibration_max_probability": candidate_profile.max_probability,
        "probability_calibration_min_decimal_odds": (
            candidate_profile.min_decimal_odds
        ),
        "probability_calibration_max_decimal_odds": (
            candidate_profile.max_decimal_odds
        ),
        "probability_calibration_blend_weight": candidate_profile.blend_weight,
        "probability_calibration_min_bucket_sample_size": (
            candidate_profile.min_bucket_sample_size
        ),
        "probability_calibration_bucket_count": len(candidate_profile.buckets),
    }
    return HistoricalProbabilityCalibrationRuntimeProfileProposal(
        profile_id=options.proposal_id,
        proposed_profile_version=options.proposed_profile_version,
        proposed_production_enabled=runtime_allowed,
        holdout_candidate_enabled=holdout_allowed,
        production_recommendation_changed=False,
        profile_key=candidate_profile.profile_key,
        profile_mode=candidate_profile.mode,
        segment_mode=candidate_profile.segment_mode,
        target_competition_ids=list(candidate_profile.target_competition_ids),
        target_market_types=[
            str(item) for item in candidate_profile.target_market_types
        ],
        target_outcomes=list(candidate_profile.target_outcomes),
        min_probability=candidate_profile.min_probability,
        max_probability=candidate_profile.max_probability,
        min_decimal_odds=candidate_profile.min_decimal_odds,
        max_decimal_odds=candidate_profile.max_decimal_odds,
        blend_weight=candidate_profile.blend_weight,
        bucket_count=len(candidate_profile.buckets),
        min_bucket_sample_size=candidate_profile.min_bucket_sample_size,
        constraints_json={
            key: value for key, value in constraints.items() if value is not None
        },
        source_report_keys={
            "grid": grid_report.report_key,
            "grid_candidate_gate": candidate.gate_report_key,
            "rolling_admission": rolling_admission_report.report_key,
            "rolling_source_artifact": (
                rolling_admission_report.source_artifact_report_key or ""
            ),
            "rolling_source_gate": (
                rolling_admission_report.source_gate_report_key or ""
            ),
            "candidate": candidate.candidate_key,
            "profile": candidate_profile.profile_key,
        },
        evidence_json={
            "overall_adjusted_fixture_count": overall.adjusted_fixture_count,
            "overall_bucket_count": overall.bucket_count,
            "profile_bucket_count": len(candidate_profile.buckets),
            "final_answer_changed_count": _candidate_delta_number(
                candidate,
                "final_answer_changed_count",
            ),
            "final_hit_rate_delta": overall.final_hit_rate_delta,
            "roi_delta": overall.roi_delta,
            "profit_loss_delta": overall.profit_loss_delta,
            "brier_score_delta": overall.brier_score_delta,
            "log_loss_delta": overall.log_loss_delta,
            "mean_calibration_error_delta": overall.mean_calibration_error_delta,
            "active_competition_fold_count": (
                rolling_admission_report.active_competition_fold_count
            ),
            "active_season_cutoff_fold_count": (
                rolling_admission_report.active_season_cutoff_fold_count
            ),
            "active_rolling_fold_count": (
                rolling_admission_report.active_rolling_fold_count
            ),
            "failed_fold_count": rolling_admission_report.failed_fold_count,
            "rolling_admission_status": rolling_admission_report.status,
            "grid_candidate_decision": candidate.decision,
            "grid_candidate_fold_objective_status": candidate.fold_objective_status,
        },
        rollback_conditions=_rollback_conditions(options),
        notes=[
            (
                "Governed probability-calibration profile proposal only; default "
                "runtime profile is unchanged."
            ),
            "Runtime activation requires a separate promotion/smoke step.",
            "Do not expose this internal strategy label to ordinary users.",
            "No automated betting, wallet, payment, or guaranteed-outcome behavior is introduced.",
        ],
    )


def _proposal_profile_set_json(
    proposal_profile: HistoricalProbabilityCalibrationRuntimeProfileProposal | None,
    candidate_profile: CandidateProbabilityCalibrationProfile,
    *,
    status: HistoricalProbabilityCalibrationProfileProductionProposalStatus,
    runtime_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalProbabilityCalibrationProfileProductionProposalOptions,
) -> dict[str, object]:
    return {
        "profile_version": options.proposed_profile_version,
        "calculation_basis": (
            "historical_probability_calibration_profile_production_proposal_v3_1"
        ),
        "status": status,
        "runtime_profile_proposal_allowed": runtime_allowed,
        "holdout_candidate_allowed": holdout_allowed,
        "production_recommendation_changed": False,
        "candidate_probability_calibration_profile_proposals": [
            proposal_profile.model_dump(mode="json")
            for proposal_profile in [proposal_profile]
            if proposal_profile is not None
        ],
        "candidate_probability_calibration_profiles": [
            candidate_profile.model_dump(mode="json")
        ]
        if holdout_allowed
        else [],
        "notes": [
            "This artifact is not a default production profile.",
            "Runtime activation requires a separate promotion/smoke step.",
            "Public recommendation response shape must remain strategy-free.",
        ],
    }


def _rollback_conditions(
    options: HistoricalProbabilityCalibrationProfileProductionProposalOptions,
) -> list[str]:
    return [
        "disable_if_rolling_admission_report_missing_or_failed",
        "disable_if_candidate_profile_missing_or_not_active",
        "disable_if_source_report_key_mismatch_or_missing",
        "disable_if_profile_constraints_do_not_match_grid_candidate",
        f"disable_if_failed_fold_count_above_{options.max_failed_fold_count}",
        (
            "disable_if_final_answer_changed_count_below_"
            f"{options.min_final_answer_changed_count}"
        ),
        (
            "disable_if_final_hit_rate_delta_below_"
            f"{options.min_final_hit_rate_delta}"
        ),
        f"disable_if_roi_delta_below_{options.min_roi_delta}",
        f"disable_if_profit_loss_delta_below_{options.min_profit_loss_delta}",
        (
            "disable_if_brier_score_delta_above_"
            f"{options.max_brier_score_delta}"
        ),
        f"disable_if_log_loss_delta_above_{options.max_log_loss_delta}",
        (
            "disable_if_mean_calibration_error_delta_above_"
            f"{options.max_mean_calibration_error_delta}"
        ),
        "disable_if_public_response_shape_changes",
        "disable_if_default_profile_write_is_not_explicitly_approved",
    ]


def _status(
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
) -> HistoricalProbabilityCalibrationProfileProductionProposalStatus:
    if runtime_allowed:
        return "runtime_profile_proposal_ready"
    if holdout_allowed:
        return "holdout_only"
    return "blocked"


def _source_checks_passed(
    checks: Sequence[HistoricalProbabilityCalibrationProfileProductionProposalCheck],
) -> bool:
    source_check_names = {
        "grid_report_generated",
        "grid_candidate_accepted",
        "grid_candidate_fold_objective_status",
        "grid_candidate_fold_objective_allowed",
        "rolling_admission_status",
        "rolling_candidate_profile_allowed",
        "rolling_shadow_allowed",
        "candidate_profile_mode",
        "rolling_profile_key",
        "candidate_profile_source_report_key",
        "profile_matches_grid_candidate",
        "rolling_metrics_match_grid_candidate",
    }
    return all(
        check.status == "passed"
        for check in checks
        if check.name in source_check_names
    )


def _holdout_checks_passed(
    checks: Sequence[HistoricalProbabilityCalibrationProfileProductionProposalCheck],
) -> bool:
    ignored_for_holdout = {
        "final_answer_changed_count",
        "final_hit_rate_delta",
        "roi_delta",
        "profit_loss_delta",
        "brier_score_delta",
        "log_loss_delta",
        "mean_calibration_error_delta",
    }
    return all(
        check.status == "passed"
        for check in checks
        if check.name not in ignored_for_holdout
    )


def _warnings(
    *,
    status: HistoricalProbabilityCalibrationProfileProductionProposalStatus,
    runtime_allowed: bool,
    holdout_allowed: bool,
    checks: Sequence[HistoricalProbabilityCalibrationProfileProductionProposalCheck],
) -> list[str]:
    warnings: list[str] = []
    if status == "holdout_only":
        warnings.append(
            "probability_calibration_profile_production_proposal:holdout_only"
        )
    elif status == "blocked":
        warnings.append(
            "probability_calibration_profile_production_proposal:blocked"
        )
    if holdout_allowed and not runtime_allowed:
        warnings.append(
            "probability_calibration_profile_production_proposal:runtime_profile_not_ready"
        )
    for check in checks:
        if check.status == "failed":
            warnings.append(
                "probability_calibration_profile_production_proposal:failed_check:"
                f"{check.name}"
            )
    return warnings


def _profile_matches_candidate(
    profile: CandidateProbabilityCalibrationProfile,
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate,
) -> bool:
    return (
        tuple(profile.target_outcomes) == tuple(candidate.target_outcomes)
        and _float_equal(profile.min_probability, candidate.probability_min)
        and _float_equal(profile.max_probability, candidate.probability_max)
        and _optional_float_equal(
            profile.min_decimal_odds,
            candidate.min_decimal_odds,
        )
        and _optional_float_equal(
            profile.max_decimal_odds,
            candidate.max_decimal_odds,
        )
        and _float_equal(profile.blend_weight, candidate.blend_weight)
    )


def _rolling_metrics_match_candidate(
    rolling_admission_report: HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate,
) -> bool:
    metrics = {
        "final_hit_rate_delta": rolling_admission_report.overall_fold.final_hit_rate_delta,
        "roi_delta": rolling_admission_report.overall_fold.roi_delta,
        "profit_loss_delta": rolling_admission_report.overall_fold.profit_loss_delta,
        "brier_score_delta": rolling_admission_report.overall_fold.brier_score_delta,
        "log_loss_delta": rolling_admission_report.overall_fold.log_loss_delta,
        "mean_calibration_error_delta": (
            rolling_admission_report.overall_fold.mean_calibration_error_delta
        ),
    }
    for metric_name, rolling_value in metrics.items():
        candidate_value = _candidate_delta_number(candidate, metric_name)
        if rolling_value is None or candidate_value is None:
            return False
        if not _float_equal(float(rolling_value), float(candidate_value)):
            return False
    return True


def _candidate_delta_number(
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate,
    name: str,
) -> float | int | None:
    value = candidate.deltas_json.get(name)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    return None


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalProbabilityCalibrationProfileProductionProposalCheck:
    if not enabled:
        return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
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
) -> HistoricalProbabilityCalibrationProfileProductionProposalCheck:
    if not enabled:
        return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
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
) -> HistoricalProbabilityCalibrationProfileProductionProposalCheck:
    if actual is None:
        return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
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
) -> HistoricalProbabilityCalibrationProfileProductionProposalCheck:
    if actual is None:
        return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalProbabilityCalibrationProfileProductionProposalCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _float_equal(left: float, right: float) -> bool:
    return abs(left - right) <= _FLOAT_TOLERANCE


def _optional_float_equal(
    left: float | None,
    right: float | None,
) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return _float_equal(left, right)


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build a governed production/holdout proposal for probability "
            "calibration profiles."
        )
    )
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--rolling-admission-report", type=Path, required=True)
    parser.add_argument("--candidate-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument(
        "--proposal-id",
        default="probability_calibration_profile_runtime_candidate_v1",
    )
    parser.add_argument(
        "--proposed-profile-version",
        default="v3_1_probability_calibration_profile_runtime_candidate",
    )
    parser.add_argument("--min-overall-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-overall-bucket-count", type=int, default=1)
    parser.add_argument("--min-profile-bucket-count", type=int, default=1)
    parser.add_argument("--min-final-answer-changed-count", type=int, default=1)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--min-active-season-cutoff-fold-count", type=int, default=1)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-rejected-grid-candidate", action="store_true")
    parser.add_argument(
        "--allow-unaccepted-candidate-fold-objective",
        action="store_true",
    )
    parser.add_argument("--allow-unaccepted-rolling-admission", action="store_true")
    parser.add_argument("--allow-shadow-only-candidate-profile", action="store_true")
    parser.add_argument("--allow-non-active-profile", action="store_true")
    parser.add_argument("--allow-source-key-mismatch", action="store_true")
    parser.add_argument("--allow-profile-candidate-mismatch", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileProductionProposalOptions:
    return HistoricalProbabilityCalibrationProfileProductionProposalOptions(
        proposal_id=args.proposal_id,
        proposed_profile_version=args.proposed_profile_version,
        min_overall_adjusted_fixture_count=(
            args.min_overall_adjusted_fixture_count
        ),
        min_overall_bucket_count=args.min_overall_bucket_count,
        min_profile_bucket_count=args.min_profile_bucket_count,
        min_final_answer_changed_count=args.min_final_answer_changed_count,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        min_active_competition_fold_count=(
            args.min_active_competition_fold_count
        ),
        min_active_season_cutoff_fold_count=(
            args.min_active_season_cutoff_fold_count
        ),
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        max_failed_fold_count=args.max_failed_fold_count,
        require_grid_candidate_accepted=not args.allow_rejected_grid_candidate,
        require_candidate_fold_objective_accepted=(
            not args.allow_unaccepted_candidate_fold_objective
        ),
        require_rolling_admission_accepted=(
            not args.allow_unaccepted_rolling_admission
        ),
        require_candidate_profile_allowed=(
            not args.allow_shadow_only_candidate_profile
        ),
        require_active_profile=not args.allow_non_active_profile,
        require_source_key_linkage=not args.allow_source_key_mismatch,
        require_profile_candidate_match=not args.allow_profile_candidate_mismatch,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalProbabilityCalibrationProfileProductionProposalCheck],
    proposal_profile: HistoricalProbabilityCalibrationRuntimeProfileProposal | None,
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "proposal_profile": (
            proposal_profile.model_dump(mode="json")
            if proposal_profile is not None
            else None
        ),
    }
    digest = sha256(
        dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_production_proposal:{digest}"
