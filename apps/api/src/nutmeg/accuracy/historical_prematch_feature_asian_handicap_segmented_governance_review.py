from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_prematch_feature_asian_handicap_segmented_admission import (
    HistoricalPrematchFeatureAsianHandicapSegmentDecision,
    HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport,
    load_historical_prematch_feature_asian_handicap_segmented_admission_report,
)

type HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewStatus = Literal[
    "governance_ready",
    "watchlist",
    "blocked",
]
type HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheckStatus = (
    Literal["passed", "failed"]
)

DEFAULT_ASIAN_HANDICAP_SEGMENTED_GOVERNANCE_REVIEW_ID = (
    "prematch-feature-asian-handicap-segmented-governance-review-v3.2"
)


class HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewOptions(BaseModel):
    review_id: str = DEFAULT_ASIAN_HANDICAP_SEGMENTED_GOVERNANCE_REVIEW_ID
    min_source_admission_count: int = Field(default=1, ge=1)
    min_ready_admission_count: int = Field(default=1, ge=0)
    min_accepted_segment_count: int = Field(default=3, ge=0)
    max_shadow_segment_count: int = Field(default=0, ge=0)
    max_fallback_segment_count: int = Field(default=2, ge=0)
    max_rejected_segment_count: int = Field(default=0, ge=0)
    min_accepted_validation_count: int = Field(default=100, ge=0)
    min_calibration_sample_expansion_applied_count: int = Field(default=1, ge=0)
    min_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_expected_calibration_error_delta: float | None = 0.0
    min_average_actual_probability_delta: float | None = 0.0
    require_all_source_admissions_accepted: bool = True
    require_segmented_candidate_model_allowed: bool = True
    require_default_path_isolated: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True
    require_internal_review_only_profile: bool = True


class HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck(BaseModel):
    name: str
    status: HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence(BaseModel):
    source_path: str | None = None
    report_key: str
    status: str
    segmented_candidate_model_allowed: bool
    default_path_isolated: bool
    production_recommendation_changed: bool
    public_response_changed: bool
    accepted_segment_count: int = Field(ge=0)
    shadow_segment_count: int = Field(ge=0)
    fallback_segment_count: int = Field(ge=0)
    rejected_segment_count: int = Field(ge=0)
    calibration_sample_expansion_applied_count: int = Field(ge=0)
    accepted_validation_count: int = Field(ge=0)
    accepted_hit_rate_delta: float | None = None
    accepted_brier_score_delta: float | None = None
    accepted_log_loss_delta: float | None = None
    accepted_expected_calibration_error_delta: float | None = None
    accepted_average_actual_probability_delta: float | None = None
    accepted_segment_ids: list[str] = Field(default_factory=list)
    fallback_segment_ids: list[str] = Field(default_factory=list)
    shadow_segment_ids: list[str] = Field(default_factory=list)
    rejected_segment_ids: list[str] = Field(default_factory=list)
    warning_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewStatus
    governance_review_ready: bool
    internal_review_only: bool = True
    production_recommendation_allowed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    default_path_isolated: bool = True
    review_id: str
    source_admission_count: int = Field(ge=0)
    ready_admission_count: int = Field(ge=0)
    watchlist_admission_count: int = Field(ge=0)
    blocked_admission_count: int = Field(ge=0)
    accepted_segment_count: int = Field(ge=0)
    shadow_segment_count: int = Field(ge=0)
    fallback_segment_count: int = Field(ge=0)
    rejected_segment_count: int = Field(ge=0)
    calibration_sample_expansion_applied_count: int = Field(ge=0)
    accepted_validation_count: int = Field(ge=0)
    accepted_segment_deltas_json: dict[str, object] = Field(default_factory=dict)
    accepted_segment_ids: list[str] = Field(default_factory=list)
    fallback_segment_ids: list[str] = Field(default_factory=list)
    shadow_segment_ids: list[str] = Field(default_factory=list)
    rejected_segment_ids: list[str] = Field(default_factory=list)
    evidence: list[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ] = Field(default_factory=list)
    checks: list[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck
    ] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    staged_profile_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _GovernanceMetrics(BaseModel):
    source_admission_count: int = Field(ge=0)
    ready_admission_count: int = Field(ge=0)
    watchlist_admission_count: int = Field(ge=0)
    blocked_admission_count: int = Field(ge=0)
    accepted_segment_count: int = Field(ge=0)
    shadow_segment_count: int = Field(ge=0)
    fallback_segment_count: int = Field(ge=0)
    rejected_segment_count: int = Field(ge=0)
    calibration_sample_expansion_applied_count: int = Field(ge=0)
    accepted_validation_count: int = Field(ge=0)
    accepted_segment_deltas_json: dict[str, object] = Field(default_factory=dict)
    accepted_segment_ids: list[str] = Field(default_factory=list)
    fallback_segment_ids: list[str] = Field(default_factory=list)
    shadow_segment_ids: list[str] = Field(default_factory=list)
    rejected_segment_ids: list[str] = Field(default_factory=list)


def build_historical_prematch_feature_asian_handicap_segmented_governance_review_report(
    admission_reports: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport
    ],
    *,
    source_paths: Sequence[Path | str | None] | None = None,
    options: (
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewOptions | None
    ) = None,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport:
    resolved_options = (
        options
        or HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewOptions()
    )
    evidence = _evidence_items(admission_reports, source_paths=source_paths)
    metrics = _metrics(evidence)
    staged_profile = _staged_profile(admission_reports, evidence=evidence)
    checks = _checks(
        evidence,
        metrics=metrics,
        staged_profile=staged_profile,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    status = _status(evidence, blockers)
    warnings = _warnings(evidence, blockers=blockers, status=status)
    governance_review_ready = status == "governance_ready"
    default_path_isolated = all(item.default_path_isolated for item in evidence)
    production_recommendation_changed = any(
        item.production_recommendation_changed for item in evidence
    )
    public_response_changed = any(item.public_response_changed for item in evidence)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_segmented_governance_review_v3_2"
        ),
        "status": status,
        "governance_review_ready": governance_review_ready,
        "internal_review_only": True,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": production_recommendation_changed,
        "public_response_changed": public_response_changed,
        "default_path_isolated": default_path_isolated,
        "review_id": resolved_options.review_id,
        **metrics.model_dump(mode="json"),
        "blockers": blockers,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, evidence, checks, staged_profile)
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport(
        report_key=report_key,
        status=status,
        governance_review_ready=governance_review_ready,
        internal_review_only=True,
        production_recommendation_allowed=False,
        production_recommendation_changed=production_recommendation_changed,
        public_response_changed=public_response_changed,
        default_path_isolated=default_path_isolated,
        review_id=resolved_options.review_id,
        source_admission_count=metrics.source_admission_count,
        ready_admission_count=metrics.ready_admission_count,
        watchlist_admission_count=metrics.watchlist_admission_count,
        blocked_admission_count=metrics.blocked_admission_count,
        accepted_segment_count=metrics.accepted_segment_count,
        shadow_segment_count=metrics.shadow_segment_count,
        fallback_segment_count=metrics.fallback_segment_count,
        rejected_segment_count=metrics.rejected_segment_count,
        calibration_sample_expansion_applied_count=(
            metrics.calibration_sample_expansion_applied_count
        ),
        accepted_validation_count=metrics.accepted_validation_count,
        accepted_segment_deltas_json=metrics.accepted_segment_deltas_json,
        accepted_segment_ids=metrics.accepted_segment_ids,
        fallback_segment_ids=metrics.fallback_segment_ids,
        shadow_segment_ids=metrics.shadow_segment_ids,
        rejected_segment_ids=metrics.rejected_segment_ids,
        evidence=evidence,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        staged_profile_json=staged_profile,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_prematch_feature_asian_handicap_segmented_governance_review_report(
    path: Path | str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport:
    return (
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    reports = [
        load_historical_prematch_feature_asian_handicap_segmented_admission_report(path)
        for path in args.segmented_admission_reports
    ]
    report = build_historical_prematch_feature_asian_handicap_segmented_governance_review_report(
        reports,
        source_paths=args.segmented_admission_reports,
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
    if not report.governance_review_ready and not args.no_fail_process:
        raise SystemExit(1)


def _evidence_items(
    admission_reports: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport
    ],
    *,
    source_paths: Sequence[Path | str | None] | None,
) -> list[HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence]:
    paths = list(source_paths or [])
    return [
        _evidence_item(
            report,
            source_path=paths[index] if index < len(paths) else None,
        )
        for index, report in enumerate(admission_reports)
    ]


def _evidence_item(
    report: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport,
    *,
    source_path: Path | str | None,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence:
    deltas = report.accepted_segment_deltas_json
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence(
        source_path=str(source_path) if source_path is not None else None,
        report_key=report.report_key,
        status=report.status,
        segmented_candidate_model_allowed=report.segmented_candidate_model_allowed,
        default_path_isolated=report.default_path_isolated,
        production_recommendation_changed=report.production_recommendation_changed,
        public_response_changed=report.public_response_changed,
        accepted_segment_count=report.accepted_segment_count,
        shadow_segment_count=report.shadow_segment_count,
        fallback_segment_count=report.fallback_segment_count,
        rejected_segment_count=report.rejected_segment_count,
        calibration_sample_expansion_applied_count=(
            report.calibration_sample_expansion_applied_count
        ),
        accepted_validation_count=report.accepted_validation_count,
        accepted_hit_rate_delta=_float_from_mapping(deltas, "hit_rate_delta"),
        accepted_brier_score_delta=_float_from_mapping(deltas, "brier_score_delta"),
        accepted_log_loss_delta=_float_from_mapping(deltas, "log_loss_delta"),
        accepted_expected_calibration_error_delta=_float_from_mapping(
            deltas,
            "expected_calibration_error_delta",
        ),
        accepted_average_actual_probability_delta=_float_from_mapping(
            deltas,
            "average_actual_probability_delta",
        ),
        accepted_segment_ids=report.accepted_segment_ids,
        fallback_segment_ids=report.fallback_segment_ids,
        shadow_segment_ids=report.shadow_segment_ids,
        rejected_segment_ids=report.rejected_segment_ids,
        warning_count=len(report.warnings),
        warnings=report.warnings,
    )


def _metrics(
    evidence: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ],
) -> _GovernanceMetrics:
    ready = [
        item
        for item in evidence
        if item.status == "accepted" and item.segmented_candidate_model_allowed
    ]
    watchlist = [
        item
        for item in evidence
        if item.status == "shadow_only" and not _hard_blocked_evidence(item)
    ]
    blocked = [item for item in evidence if _hard_blocked_evidence(item)]
    return _GovernanceMetrics(
        source_admission_count=len(evidence),
        ready_admission_count=len(ready),
        watchlist_admission_count=len(watchlist),
        blocked_admission_count=len(blocked),
        accepted_segment_count=sum(item.accepted_segment_count for item in evidence),
        shadow_segment_count=sum(item.shadow_segment_count for item in evidence),
        fallback_segment_count=sum(item.fallback_segment_count for item in evidence),
        rejected_segment_count=sum(item.rejected_segment_count for item in evidence),
        calibration_sample_expansion_applied_count=sum(
            item.calibration_sample_expansion_applied_count for item in evidence
        ),
        accepted_validation_count=sum(item.accepted_validation_count for item in evidence),
        accepted_segment_deltas_json=_weighted_delta_summary(evidence),
        accepted_segment_ids=_unique_ordered(
            segment_id
            for item in evidence
            for segment_id in item.accepted_segment_ids
        ),
        fallback_segment_ids=_unique_ordered(
            segment_id
            for item in evidence
            for segment_id in item.fallback_segment_ids
        ),
        shadow_segment_ids=_unique_ordered(
            segment_id for item in evidence for segment_id in item.shadow_segment_ids
        ),
        rejected_segment_ids=_unique_ordered(
            segment_id for item in evidence for segment_id in item.rejected_segment_ids
        ),
    )


def _staged_profile(
    admission_reports: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport
    ],
    *,
    evidence: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ],
) -> dict[str, object]:
    accepted_decisions = [
        _profile_decision(decision, report_key=report.report_key)
        for report in admission_reports
        for decision in report.decisions
        if decision.status == "accepted"
    ]
    fallback_decisions = [
        _profile_decision(decision, report_key=report.report_key)
        for report in admission_reports
        for decision in report.decisions
        if decision.status == "baseline_fallback"
    ]
    return {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_segmented_governance_staged_profile_v3_2"
        ),
        "dry_run_only": True,
        "internal_review_only": True,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "default_path_isolated": all(item.default_path_isolated for item in evidence),
        "source_admission_report_keys": [item.report_key for item in evidence],
        "accepted_segments": accepted_decisions,
        "fallback_segments": fallback_decisions,
        "shadow_segment_ids": _unique_ordered(
            segment_id for item in evidence for segment_id in item.shadow_segment_ids
        ),
        "rejected_segment_ids": _unique_ordered(
            segment_id for item in evidence for segment_id in item.rejected_segment_ids
        ),
        "runtime_policy": {
            "accepted_segments": "candidate_line_aware_asian_handicap_model_quality",
            "fallback_segments": "baseline_prediction_path",
            "shadow_segments": "research_only",
            "rejected_segments": "ignored",
        },
    }


def _profile_decision(
    decision: HistoricalPrematchFeatureAsianHandicapSegmentDecision,
    *,
    report_key: str,
) -> dict[str, object]:
    return {
        "segment_id": decision.segment_id,
        "source_admission_report_key": report_key,
        "source_role_search_id": decision.source_role_search_id,
        "source_report_key": decision.source_report_key,
        "selected_candidate_id": decision.selected_candidate_id,
        "status": decision.status,
        "validation_count": decision.validation_count,
        "asian_handicap_movement_weight": decision.asian_handicap_movement_weight,
        "asian_handicap_line_movement_weight": (
            decision.asian_handicap_line_movement_weight
        ),
        "asian_handicap_line_movement_transform": (
            decision.asian_handicap_line_movement_transform
        ),
        "calibration_sample_expansion_applied": (
            decision.calibration_sample_expansion_applied
        ),
    }


def _checks(
    evidence: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ],
    *,
    metrics: _GovernanceMetrics,
    staged_profile: Mapping[str, object],
    options: HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewOptions,
) -> list[HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck]:
    checks = [
        _check_min(
            "source_admission_count",
            metrics.source_admission_count,
            options.min_source_admission_count,
            detail="governance review needs enough segmented admission reports",
        ),
        _check_min(
            "ready_admission_count",
            metrics.ready_admission_count,
            options.min_ready_admission_count,
            detail="enough source admissions must already be accepted",
        ),
        _check_bool(
            "all_source_admissions_accepted",
            all(item.status == "accepted" for item in evidence),
            True,
            detail="source admission reports must be accepted before governance review",
        ),
        _check_bool(
            "all_segmented_candidate_models_allowed",
            all(item.segmented_candidate_model_allowed for item in evidence),
            True,
            detail="source admissions must allow segmented candidate model evidence",
        ),
        _check_min(
            "accepted_segment_count",
            metrics.accepted_segment_count,
            options.min_accepted_segment_count,
            detail="enough competition segments must pass model-quality gates",
        ),
        _check_max(
            "shadow_segment_count",
            metrics.shadow_segment_count,
            options.max_shadow_segment_count,
            detail="shadow-only segments must remain within governance tolerance",
        ),
        _check_max(
            "fallback_segment_count",
            metrics.fallback_segment_count,
            options.max_fallback_segment_count,
            detail="baseline fallback segments must remain within governance tolerance",
        ),
        _check_max(
            "rejected_segment_count",
            metrics.rejected_segment_count,
            options.max_rejected_segment_count,
            detail="rejected segments are not allowed in a staged profile",
        ),
        _check_min(
            "accepted_validation_count",
            metrics.accepted_validation_count,
            options.min_accepted_validation_count,
            detail="accepted segments need enough held-out validation samples",
        ),
        _check_min(
            "calibration_sample_expansion_applied_count",
            metrics.calibration_sample_expansion_applied_count,
            options.min_calibration_sample_expansion_applied_count,
            detail="calibration measurements must support previously missing ECE evidence",
        ),
        _check_metric_min(
            "accepted_hit_rate_delta",
            _delta_from_metrics(metrics, "hit_rate_delta"),
            options.min_hit_rate_delta,
            detail="accepted segments must not reduce hit rate",
        ),
        _check_metric_max(
            "accepted_brier_score_delta",
            _delta_from_metrics(metrics, "brier_score_delta"),
            options.max_brier_score_delta,
            detail="accepted segments must not worsen Brier score",
        ),
        _check_metric_max(
            "accepted_log_loss_delta",
            _delta_from_metrics(metrics, "log_loss_delta"),
            options.max_log_loss_delta,
            detail="accepted segments must not worsen log loss",
        ),
        _check_metric_max(
            "accepted_expected_calibration_error_delta",
            _delta_from_metrics(metrics, "expected_calibration_error_delta"),
            options.max_expected_calibration_error_delta,
            detail="accepted segments must not worsen calibration",
        ),
        _check_metric_min(
            "accepted_average_actual_probability_delta",
            _delta_from_metrics(metrics, "average_actual_probability_delta"),
            options.min_average_actual_probability_delta,
            detail="accepted segments must not reduce actual-outcome probability",
        ),
        _check_bool(
            "default_path_isolated",
            all(item.default_path_isolated for item in evidence),
            True,
            detail="governance review must not change the default prediction path",
        ),
        _check_bool(
            "production_recommendation_changed",
            any(item.production_recommendation_changed for item in evidence),
            False,
            detail="governance review must not change production recommendations",
        ),
        _check_bool(
            "public_response_changed",
            any(item.public_response_changed for item in evidence),
            False,
            detail="governance review must not change public responses",
        ),
        _check_bool(
            "staged_profile_internal_review_only",
            staged_profile.get("internal_review_only") is True
            and staged_profile.get("dry_run_only") is True,
            True,
            detail="staged profile must stay internal-only and dry-run-only",
        ),
    ]
    if not options.require_all_source_admissions_accepted:
        checks = [
            check for check in checks if check.name != "all_source_admissions_accepted"
        ]
    if not options.require_segmented_candidate_model_allowed:
        checks = [
            check
            for check in checks
            if check.name != "all_segmented_candidate_models_allowed"
        ]
    if not options.require_default_path_isolated:
        checks = [check for check in checks if check.name != "default_path_isolated"]
    if not options.require_no_production_change:
        checks = [
            check
            for check in checks
            if check.name != "production_recommendation_changed"
        ]
    if not options.require_no_public_response_change:
        checks = [check for check in checks if check.name != "public_response_changed"]
    if not options.require_internal_review_only_profile:
        checks = [
            check
            for check in checks
            if check.name != "staged_profile_internal_review_only"
        ]
    return checks


def _status(
    evidence: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ],
    blockers: Sequence[str],
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewStatus:
    if any(_hard_blocked_evidence(item) for item in evidence):
        return "blocked"
    if any(
        blocker
        in {
            "default_path_isolated",
            "production_recommendation_changed",
            "public_response_changed",
            "staged_profile_internal_review_only",
        }
        for blocker in blockers
    ):
        return "blocked"
    if blockers:
        return "watchlist"
    return "governance_ready"


def _warnings(
    evidence: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ],
    *,
    blockers: Sequence[str],
    status: HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewStatus,
) -> list[str]:
    warnings = [
        f"asian_handicap_segmented_governance_review:failed_check:{blocker}"
        for blocker in blockers
    ]
    warnings.extend(
        f"asian_handicap_segmented_governance_review:source_warning:{item.report_key}"
        for item in evidence
        if item.warning_count > 0
    )
    warnings.append(f"asian_handicap_segmented_governance_review:{status}")
    return warnings


def _hard_blocked_evidence(
    evidence: HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence,
) -> bool:
    return (
        not evidence.default_path_isolated
        or evidence.production_recommendation_changed
        or evidence.public_response_changed
    )


def _weighted_delta_summary(
    evidence: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ],
) -> dict[str, object]:
    return {
        "hit_rate_delta": _weighted_evidence_delta(evidence, "accepted_hit_rate_delta"),
        "brier_score_delta": _weighted_evidence_delta(
            evidence,
            "accepted_brier_score_delta",
        ),
        "log_loss_delta": _weighted_evidence_delta(
            evidence,
            "accepted_log_loss_delta",
        ),
        "expected_calibration_error_delta": _weighted_evidence_delta(
            evidence,
            "accepted_expected_calibration_error_delta",
        ),
        "average_actual_probability_delta": _weighted_evidence_delta(
            evidence,
            "accepted_average_actual_probability_delta",
        ),
    }


def _weighted_evidence_delta(
    evidence: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ],
    field_name: str,
) -> float | None:
    weighted_total = 0.0
    weight_total = 0
    for item in evidence:
        value = getattr(item, field_name)
        if value is None:
            continue
        weighted_total += value * item.accepted_validation_count
        weight_total += item.accepted_validation_count
    if weight_total == 0:
        return None
    return weighted_total / weight_total


def _delta_from_metrics(metrics: _GovernanceMetrics, metric_name: str) -> float | None:
    return _float_from_mapping(metrics.accepted_segment_deltas_json, metric_name)


def _float_from_mapping(mapping: Mapping[str, object], key: str) -> float | None:
    value = mapping.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _check_min(
    name: str,
    actual: int | float,
    threshold: int | float,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_max(
    name: str,
    actual: int | float,
    threshold: int | float,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_bool(
    name: str,
    actual: bool,
    threshold: bool,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck(
        name=name,
        status="passed" if actual is threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_metric_min(
    name: str,
    actual: float | None,
    threshold: float | None,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck(
        name=name,
        status="passed" if _meets_min(actual, threshold) else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_metric_max(
    name: str,
    actual: float | None,
    threshold: float | None,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck(
        name=name,
        status="passed" if _meets_max(actual, threshold) else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _meets_min(value: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return value is not None and value >= threshold


def _meets_max(value: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return value is not None and value <= threshold


def _unique_ordered(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        string_value = str(value)
        if string_value in seen:
            continue
        seen.add(string_value)
        unique.append(string_value)
    return unique


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run an internal-only governance review for accepted segmented "
            "Asian-handicap model-quality evidence without changing production."
        )
    )
    parser.add_argument(
        "--segmented-admission-report",
        dest="segmented_admission_reports",
        action="append",
        type=Path,
        default=[],
        required=True,
    )
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--review-id",
        default=DEFAULT_ASIAN_HANDICAP_SEGMENTED_GOVERNANCE_REVIEW_ID,
    )
    parser.add_argument("--min-source-admission-count", type=int, default=1)
    parser.add_argument("--min-ready-admission-count", type=int, default=1)
    parser.add_argument("--min-accepted-segment-count", type=int, default=3)
    parser.add_argument("--max-shadow-segment-count", type=int, default=0)
    parser.add_argument("--max-fallback-segment-count", type=int, default=2)
    parser.add_argument("--max-rejected-segment-count", type=int, default=0)
    parser.add_argument("--min-accepted-validation-count", type=int, default=100)
    parser.add_argument(
        "--min-calibration-sample-expansion-applied-count",
        type=int,
        default=1,
    )
    parser.add_argument("--min-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-average-actual-probability-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--allow-source-admission-not-accepted", action="store_true")
    parser.add_argument("--allow-segmented-candidate-model-not-allowed", action="store_true")
    parser.add_argument("--allow-default-path-not-isolated", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-non-internal-review-profile", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewOptions:
    return HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewOptions(
        review_id=args.review_id,
        min_source_admission_count=args.min_source_admission_count,
        min_ready_admission_count=args.min_ready_admission_count,
        min_accepted_segment_count=args.min_accepted_segment_count,
        max_shadow_segment_count=args.max_shadow_segment_count,
        max_fallback_segment_count=args.max_fallback_segment_count,
        max_rejected_segment_count=args.max_rejected_segment_count,
        min_accepted_validation_count=args.min_accepted_validation_count,
        min_calibration_sample_expansion_applied_count=(
            args.min_calibration_sample_expansion_applied_count
        ),
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        min_average_actual_probability_delta=(
            args.min_average_actual_probability_delta
        ),
        require_all_source_admissions_accepted=(
            not args.allow_source_admission_not_accepted
        ),
        require_segmented_candidate_model_allowed=(
            not args.allow_segmented_candidate_model_not_allowed
        ),
        require_default_path_isolated=not args.allow_default_path_not_isolated,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
        require_internal_review_only_profile=(
            not args.allow_non_internal_review_profile
        ),
    )


def _report_key(
    summary: Mapping[str, object],
    evidence: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewEvidence
    ],
    checks: Sequence[
        HistoricalPrematchFeatureAsianHandicapSegmentedGovernanceReviewCheck
    ],
    staged_profile: Mapping[str, object],
) -> str:
    payload = {
        "summary": summary,
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "checks": [check.model_dump(mode="json") for check in checks],
        "staged_profile": staged_profile,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return (
        "historical_prematch_feature_asian_handicap_segmented_governance_review:"
        f"{digest}"
    )
