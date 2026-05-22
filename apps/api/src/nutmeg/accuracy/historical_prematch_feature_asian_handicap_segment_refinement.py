from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
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

type HistoricalPrematchFeatureAsianHandicapSegmentRefinementStatus = Literal[
    "refinement_ready",
    "blocked",
    "no_action",
]
type HistoricalPrematchFeatureAsianHandicapSegmentRefinementAction = Literal[
    "retain_candidate_segment",
    "calibration_sample_expansion",
    "calibration_scope_refinement",
    "line_transform_enrichment",
    "baseline_fallback",
]
type HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheckStatus = Literal[
    "passed",
    "failed",
]

DEFAULT_ASIAN_HANDICAP_SEGMENT_REFINEMENT_ID = (
    "prematch-feature-asian-handicap-segment-refinement-v3.2"
)


class HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions(BaseModel):
    refinement_id: str = DEFAULT_ASIAN_HANDICAP_SEGMENT_REFINEMENT_ID
    min_refinement_candidate_count: int = Field(default=1, ge=0)
    min_promising_validation_count: int = Field(default=40, ge=0)
    min_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_expected_calibration_error_delta: float | None = 0.0
    require_default_path_isolated: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck(BaseModel):
    name: str
    status: HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision(BaseModel):
    segment_id: str
    source_status: str
    recommended_action: HistoricalPrematchFeatureAsianHandicapSegmentRefinementAction
    refinement_candidate: bool
    validation_count: int = Field(ge=0)
    selected_candidate_id: str | None = None
    selected_candidate_status: str | None = None
    blocker_categories: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    hit_rate_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    expected_calibration_error_delta: float | None = None
    average_actual_probability_delta: float | None = None
    priority_score: float = 0.0
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureAsianHandicapSegmentRefinementStatus
    refinement_id: str
    source_report_key: str
    source_status: str
    source_segment_count: int = Field(ge=0)
    refinement_candidate_count: int = Field(ge=0)
    baseline_fallback_segment_count: int = Field(ge=0)
    calibration_sample_expansion_count: int = Field(ge=0)
    calibration_scope_refinement_count: int = Field(ge=0)
    line_transform_enrichment_count: int = Field(ge=0)
    retained_candidate_segment_count: int = Field(ge=0)
    blocker_category_counts: dict[str, int] = Field(default_factory=dict)
    recommended_action_counts: dict[str, int] = Field(default_factory=dict)
    top_refinement_segment_ids: list[str] = Field(default_factory=list)
    default_path_isolated: bool
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    decisions: list[
        HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision
    ] = Field(default_factory=list)
    checks: list[HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_prematch_feature_asian_handicap_segment_refinement_report(
    path: Path | str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport:
    return HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_prematch_feature_asian_handicap_segment_refinement_report(
    source_report: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport,
    *,
    options: HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions | None = None,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport:
    resolved_options = (
        options or HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions()
    )
    decisions = [
        _refinement_decision(decision, options=resolved_options)
        for decision in source_report.decisions
    ]
    metrics = _metrics(decisions)
    checks = _checks(source_report, metrics=metrics, options=resolved_options)
    blockers = [check.name for check in checks if check.status == "failed"]
    status = _status(metrics, blockers=blockers)
    warnings = _warnings(status=status, checks=checks, decisions=decisions)
    decision_payload = _decision_payload(
        source_report,
        decisions=decisions,
        metrics=metrics,
        status=status,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_segment_refinement_v3_2"
        ),
        "refinement_id": resolved_options.refinement_id,
        "source_report_key": source_report.report_key,
        "source_status": source_report.status,
        "status": status,
        **metrics,
        "default_path_isolated": source_report.default_path_isolated,
        "production_recommendation_changed": (
            source_report.production_recommendation_changed
        ),
        "public_response_changed": source_report.public_response_changed,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decisions, decision_payload)
    return HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport(
        report_key=report_key,
        status=status,
        refinement_id=resolved_options.refinement_id,
        source_report_key=source_report.report_key,
        source_status=source_report.status,
        source_segment_count=source_report.source_report_count,
        refinement_candidate_count=_int(metrics["refinement_candidate_count"]),
        baseline_fallback_segment_count=_int(
            metrics["baseline_fallback_segment_count"]
        ),
        calibration_sample_expansion_count=_int(
            metrics["calibration_sample_expansion_count"]
        ),
        calibration_scope_refinement_count=_int(
            metrics["calibration_scope_refinement_count"]
        ),
        line_transform_enrichment_count=_int(
            metrics["line_transform_enrichment_count"]
        ),
        retained_candidate_segment_count=_int(
            metrics["retained_candidate_segment_count"]
        ),
        blocker_category_counts=_int_mapping(metrics["blocker_category_counts"]),
        recommended_action_counts=_int_mapping(metrics["recommended_action_counts"]),
        top_refinement_segment_ids=_string_list(metrics["top_refinement_segment_ids"]),
        default_path_isolated=source_report.default_path_isolated,
        production_recommendation_changed=(
            source_report.production_recommendation_changed
        ),
        public_response_changed=source_report.public_response_changed,
        decisions=decisions,
        checks=checks,
        warnings=warnings,
        decision_payload_json=decision_payload,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_prematch_feature_asian_handicap_segment_refinement_report(
        load_historical_prematch_feature_asian_handicap_segmented_admission_report(
            args.segmented_admission_report
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
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


def _refinement_decision(
    decision: HistoricalPrematchFeatureAsianHandicapSegmentDecision,
    *,
    options: HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision:
    blocker_categories = _blocker_categories(decision)
    action = _recommended_action(decision, blocker_categories, options=options)
    refinement_candidate = action in {
        "retain_candidate_segment",
        "calibration_sample_expansion",
        "calibration_scope_refinement",
        "line_transform_enrichment",
    }
    priority_score = _priority_score(decision, action=action)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_segment_refinement_decision_v3_2"
        ),
        "segment_id": decision.segment_id,
        "source_status": decision.status,
        "recommended_action": action,
        "refinement_candidate": refinement_candidate,
        "validation_count": decision.validation_count,
        "blocker_categories": blocker_categories,
        "failure_reasons": decision.failure_reasons,
        "priority_score": priority_score,
    }
    return HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision(
        segment_id=decision.segment_id,
        source_status=decision.status,
        recommended_action=action,
        refinement_candidate=refinement_candidate,
        validation_count=decision.validation_count,
        selected_candidate_id=decision.selected_candidate_id,
        selected_candidate_status=decision.selected_candidate_status,
        blocker_categories=blocker_categories,
        failure_reasons=decision.failure_reasons,
        hit_rate_delta=decision.hit_rate_delta,
        brier_score_delta=decision.brier_score_delta,
        log_loss_delta=decision.log_loss_delta,
        expected_calibration_error_delta=decision.expected_calibration_error_delta,
        average_actual_probability_delta=decision.average_actual_probability_delta,
        priority_score=priority_score,
        summary_json=summary,
    )


def _blocker_categories(
    decision: HistoricalPrematchFeatureAsianHandicapSegmentDecision,
) -> list[str]:
    reasons = set(decision.failure_reasons)
    categories: list[str] = []
    if decision.status == "accepted":
        categories.append("accepted_segment")
    if _has_role_acceptance_blocker(reasons):
        categories.append("role_acceptance_blocked")
    if decision.validation_count <= 0 or "validation_count_below_minimum" in reasons:
        categories.append("validation_shortfall")
    if "expected_calibration_error_delta_missing" in reasons:
        categories.append("calibration_missing")
    if "expected_calibration_error_delta_above_maximum" in reasons:
        categories.append("calibration_regression")
    if _has_probability_quality_regression(reasons):
        categories.append("probability_quality_regression")
    if "source_warning_count_above_maximum" in reasons:
        categories.append("source_warning")
    if not categories:
        categories.append("research_only")
    return categories


def _recommended_action(
    decision: HistoricalPrematchFeatureAsianHandicapSegmentDecision,
    blocker_categories: Sequence[str],
    *,
    options: HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementAction:
    if decision.status == "accepted":
        return "retain_candidate_segment"
    probability_quality_ready = _probability_quality_ready(decision, options=options)
    calibration_missing = "calibration_missing" in blocker_categories
    calibration_regression = "calibration_regression" in blocker_categories
    if (
        probability_quality_ready
        and calibration_missing
        and decision.validation_count >= options.min_promising_validation_count
    ):
        return "calibration_sample_expansion"
    if (
        probability_quality_ready
        and calibration_regression
        and decision.validation_count >= options.min_promising_validation_count
    ):
        return "calibration_scope_refinement"
    if "probability_quality_regression" in blocker_categories:
        return "line_transform_enrichment"
    return "baseline_fallback"


def _probability_quality_ready(
    decision: HistoricalPrematchFeatureAsianHandicapSegmentDecision,
    *,
    options: HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions,
) -> bool:
    return (
        _meets_min(decision.hit_rate_delta, options.min_hit_rate_delta)
        and _meets_max(decision.brier_score_delta, options.max_brier_score_delta)
        and _meets_max(decision.log_loss_delta, options.max_log_loss_delta)
    )


def _has_role_acceptance_blocker(reasons: set[str]) -> bool:
    return bool(
        reasons
        & {
            "accepted_nonzero_candidate_count_below_minimum",
            "missing_best_accepted_candidate",
            "selected_candidate_not_accepted",
            "selected_candidate_failed_non_regression_gate",
        }
    )


def _has_probability_quality_regression(reasons: set[str]) -> bool:
    return bool(
        reasons
        & {
            "hit_rate_delta_below_minimum",
            "brier_score_delta_above_maximum",
            "log_loss_delta_above_maximum",
            "average_actual_probability_delta_below_minimum",
        }
    )


def _priority_score(
    decision: HistoricalPrematchFeatureAsianHandicapSegmentDecision,
    *,
    action: HistoricalPrematchFeatureAsianHandicapSegmentRefinementAction,
) -> float:
    if action == "baseline_fallback":
        return 0.0
    action_bonus = {
        "retain_candidate_segment": 100.0,
        "calibration_sample_expansion": 75.0,
        "calibration_scope_refinement": 60.0,
        "line_transform_enrichment": 25.0,
        "baseline_fallback": 0.0,
    }[action]
    brier_gain = max(0.0, -(decision.brier_score_delta or 0.0)) * 10_000
    log_loss_gain = max(0.0, -(decision.log_loss_delta or 0.0)) * 5_000
    hit_gain = max(0.0, decision.hit_rate_delta or 0.0) * 100
    return action_bonus + brier_gain + log_loss_gain + hit_gain


def _metrics(
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision],
) -> dict[str, object]:
    action_counts = Counter(decision.recommended_action for decision in decisions)
    blocker_counts: Counter[str] = Counter()
    for decision in decisions:
        blocker_counts.update(decision.blocker_categories)
    refinement_candidates = [
        decision for decision in decisions if decision.refinement_candidate
    ]
    top_segments = [
        decision.segment_id
        for decision in sorted(
            refinement_candidates,
            key=lambda item: item.priority_score,
            reverse=True,
        )
    ]
    return {
        "source_segment_count": len(decisions),
        "refinement_candidate_count": len(refinement_candidates),
        "baseline_fallback_segment_count": action_counts["baseline_fallback"],
        "calibration_sample_expansion_count": action_counts[
            "calibration_sample_expansion"
        ],
        "calibration_scope_refinement_count": action_counts[
            "calibration_scope_refinement"
        ],
        "line_transform_enrichment_count": action_counts[
            "line_transform_enrichment"
        ],
        "retained_candidate_segment_count": action_counts["retain_candidate_segment"],
        "recommended_action_counts": dict(action_counts),
        "blocker_category_counts": dict(blocker_counts),
        "top_refinement_segment_ids": top_segments,
    }


def _checks(
    source_report: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport,
    *,
    metrics: Mapping[str, object],
    options: HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions,
) -> list[HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck]:
    checks = [
        _check_min(
            "refinement_candidate_count",
            _int(metrics["refinement_candidate_count"]),
            options.min_refinement_candidate_count,
            detail="refinement should produce at least one bounded next experiment",
        ),
        _check_bool(
            "default_path_isolated",
            source_report.default_path_isolated,
            True,
            detail="refinement must not start from a default-path-changing report",
        ),
        _check_bool(
            "production_recommendation_changed",
            source_report.production_recommendation_changed,
            False,
            detail="refinement must not start from production-changing evidence",
        ),
        _check_bool(
            "public_response_changed",
            source_report.public_response_changed,
            False,
            detail="refinement must not start from public-response-changing evidence",
        ),
    ]
    if not options.require_default_path_isolated:
        checks = [
            check for check in checks if check.name != "default_path_isolated"
        ]
    if not options.require_no_production_change:
        checks = [
            check
            for check in checks
            if check.name != "production_recommendation_changed"
        ]
    if not options.require_no_public_response_change:
        checks = [
            check for check in checks if check.name != "public_response_changed"
        ]
    return checks


def _decision_payload(
    source_report: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport,
    *,
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision],
    metrics: Mapping[str, object],
    status: HistoricalPrematchFeatureAsianHandicapSegmentRefinementStatus,
    options: HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_segment_refinement_decision_v3_2"
        ),
        "status": status,
        "source_report_key": source_report.report_key,
        "source_status": source_report.status,
        "metrics": dict(metrics),
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
        "recommended_next_steps": _recommended_next_steps(metrics),
        "default_path_isolated": source_report.default_path_isolated,
        "production_recommendation_changed": (
            source_report.production_recommendation_changed
        ),
        "public_response_changed": source_report.public_response_changed,
        "options": options.model_dump(mode="json"),
    }


def _recommended_next_steps(metrics: Mapping[str, object]) -> list[str]:
    steps: list[str] = []
    if _int(metrics["calibration_sample_expansion_count"]) > 0:
        steps.append("expand_or_rebucket_calibration_samples_for_missing_ece_segments")
    if _int(metrics["calibration_scope_refinement_count"]) > 0:
        steps.append("split_line_aware_signal_by_calibration_sensitive_scope")
    if _int(metrics["line_transform_enrichment_count"]) > 0:
        steps.append("change_line_transform_before_retesting_regressing_segments")
    if not steps:
        steps.append("keep_baseline_fallback_and_collect_more_feature_evidence")
    return steps


def _status(
    metrics: Mapping[str, object],
    *,
    blockers: Sequence[str],
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementStatus:
    if blockers:
        return "blocked"
    if _int(metrics["refinement_candidate_count"]) > 0:
        return "refinement_ready"
    return "no_action"


def _warnings(
    *,
    status: HistoricalPrematchFeatureAsianHandicapSegmentRefinementStatus,
    checks: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck],
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision],
) -> list[str]:
    warnings = [
        f"asian_handicap_segment_refinement:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    warnings.extend(
        (
            "asian_handicap_segment_refinement:baseline_fallback:"
            f"{decision.segment_id}"
        )
        for decision in decisions
        if decision.recommended_action == "baseline_fallback"
    )
    warnings.append(f"asian_handicap_segment_refinement:{status}")
    return warnings


def _meets_min(value: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return value is not None and value >= threshold


def _meets_max(value: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return value is not None and value <= threshold


def _check_min(
    name: str,
    actual: int | float,
    threshold: int | float,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
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
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck(
        name=name,
        status="passed" if actual is threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Turn a segmented line-aware Asian-handicap admission report into "
            "bounded refinement actions without activating the signal."
        )
    )
    parser.add_argument("segmented_admission_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--refinement-id",
        default=DEFAULT_ASIAN_HANDICAP_SEGMENT_REFINEMENT_ID,
    )
    parser.add_argument("--min-refinement-candidate-count", type=int, default=1)
    parser.add_argument("--min-promising-validation-count", type=int, default=40)
    parser.add_argument("--min-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--allow-default-path-not-isolated", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions:
    return HistoricalPrematchFeatureAsianHandicapSegmentRefinementOptions(
        refinement_id=args.refinement_id,
        min_refinement_candidate_count=args.min_refinement_candidate_count,
        min_promising_validation_count=args.min_promising_validation_count,
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        require_default_path_isolated=not args.allow_default_path_not_isolated,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentRefinementCheck],
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision],
    decision_payload: Mapping[str, object],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
        "decision_payload": decision_payload,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return (
        "historical_prematch_feature_asian_handicap_segment_refinement:"
        f"{digest}"
    )


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _int_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _int(item) for key, item in value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [str(item) for item in value]
