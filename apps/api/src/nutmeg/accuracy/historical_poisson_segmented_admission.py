from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_poisson_parameter_admission import (
    load_historical_poisson_parameter_learning_report,
)
from nutmeg.accuracy.historical_poisson_parameter_learning import (
    HistoricalPoissonCompetitionParameterLearningResult,
    HistoricalPoissonParameterLearningReport,
)
from nutmeg.accuracy.historical_poisson_walk_forward import (
    HistoricalPoissonWalkForwardMetricSet,
)

type HistoricalPoissonSegmentedAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalPoissonSegmentDecisionStatus = Literal[
    "admitted",
    "baseline_fallback",
    "skipped",
]
type HistoricalPoissonSegmentCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalPoissonSegmentedAdmissionOptions(BaseModel):
    min_source_learned_competition_count: int = Field(default=1, ge=0)
    min_source_validation_count: int = Field(default=100, ge=0)
    min_source_candidate_count: int = Field(default=1, ge=0)
    max_source_warning_count: int | None = Field(default=0, ge=0)
    min_competition_validation_count: int = Field(default=100, ge=0)
    min_admitted_competition_count: int = Field(default=1, ge=0)
    min_admitted_validation_count: int = Field(default=100, ge=0)
    min_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_expected_calibration_error_delta: float | None = 0.0
    min_average_actual_probability_delta: float | None = None
    min_selected_model_signal_weight: float | None = Field(default=0.05, ge=0.0, le=1.0)
    require_source_status_generated: bool = True
    require_segmented_no_harm: bool = True
    require_no_public_prediction_change: bool = True


class HistoricalPoissonSegmentedAdmissionCheck(BaseModel):
    name: str
    status: HistoricalPoissonSegmentCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPoissonCompetitionSegmentDecision(BaseModel):
    competition_id: str
    status: HistoricalPoissonSegmentDecisionStatus
    validation_count: int = Field(ge=0)
    selected_candidate_key: str | None = None
    model_signal_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    deltas_json: dict[str, object] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPoissonSegmentedAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalPoissonSegmentedAdmissionStatus
    segmented_candidate_model_allowed: bool
    shadow_allowed: bool
    source_report_key: str
    source_status: str
    source_competition_count: int = Field(ge=0)
    source_learned_competition_count: int = Field(ge=0)
    source_candidate_count: int = Field(ge=0)
    source_validation_count: int = Field(ge=0)
    source_warning_count: int = Field(ge=0)
    admitted_competition_count: int = Field(ge=0)
    fallback_competition_count: int = Field(ge=0)
    skipped_competition_count: int = Field(ge=0)
    admitted_validation_count: int = Field(ge=0)
    fallback_validation_count: int = Field(ge=0)
    segmented_validation_count: int = Field(ge=0)
    segmented_candidate: HistoricalPoissonWalkForwardMetricSet | None = None
    segmented_baseline: HistoricalPoissonWalkForwardMetricSet | None = None
    segmented_deltas_json: dict[str, object] = Field(default_factory=dict)
    admitted_candidate_counts: dict[str, int] = Field(default_factory=dict)
    decisions: list[HistoricalPoissonCompetitionSegmentDecision] = Field(
        default_factory=list
    )
    checks: list[HistoricalPoissonSegmentedAdmissionCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_poisson_segmented_admission_report(
    path: Path | str,
) -> HistoricalPoissonSegmentedAdmissionReport:
    return HistoricalPoissonSegmentedAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_poisson_segmented_admission_report(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    options: HistoricalPoissonSegmentedAdmissionOptions | None = None,
) -> HistoricalPoissonSegmentedAdmissionReport:
    resolved_options = options or HistoricalPoissonSegmentedAdmissionOptions()
    decisions = [
        _competition_decision(competition, options=resolved_options)
        for competition in source_report.competitions
    ]
    metrics = _segmented_metrics(source_report, decisions)
    checks = _checks(
        source_report,
        decisions=decisions,
        metrics=metrics,
        options=resolved_options,
    )
    source_ready = _source_ready(checks)
    coverage_ready = _coverage_ready(checks)
    no_harm = _segmented_no_harm_ready(checks)
    segmented_candidate_model_allowed = source_ready and coverage_ready and no_harm
    shadow_allowed = source_ready
    status = _status(
        candidate_model_allowed=segmented_candidate_model_allowed,
        shadow_allowed=shadow_allowed,
    )
    warnings = _warnings(status=status, checks=checks, decisions=decisions)
    decision_payload = _decision_payload(
        source_report,
        decisions=decisions,
        metrics=metrics,
        status=status,
        segmented_candidate_model_allowed=segmented_candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_poisson_segmented_admission_v3_2",
        "status": status,
        "segmented_candidate_model_allowed": segmented_candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "source_report_key": source_report.report_key,
        "source_status": source_report.status,
        **metrics,
        "public_prediction_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decisions, decision_payload)
    return HistoricalPoissonSegmentedAdmissionReport(
        report_key=report_key,
        status=status,
        segmented_candidate_model_allowed=segmented_candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        source_report_key=source_report.report_key,
        source_status=source_report.status,
        source_competition_count=source_report.competition_count,
        source_learned_competition_count=source_report.learned_competition_count,
        source_candidate_count=source_report.candidate_count,
        source_validation_count=source_report.validation_count,
        source_warning_count=len(source_report.warnings),
        admitted_competition_count=_int(metrics["admitted_competition_count"]),
        fallback_competition_count=_int(metrics["fallback_competition_count"]),
        skipped_competition_count=_int(metrics["skipped_competition_count"]),
        admitted_validation_count=_int(metrics["admitted_validation_count"]),
        fallback_validation_count=_int(metrics["fallback_validation_count"]),
        segmented_validation_count=_int(metrics["segmented_validation_count"]),
        segmented_candidate=_metric_or_none(metrics["segmented_candidate"]),
        segmented_baseline=_metric_or_none(metrics["segmented_baseline"]),
        segmented_deltas_json=_mapping_dict(metrics["segmented_deltas_json"]),
        admitted_candidate_counts={
            str(key): _int(value)
            for key, value in _mapping(metrics["admitted_candidate_counts"]).items()
        },
        decisions=decisions,
        checks=checks,
        warnings=warnings,
        decision_payload_json=decision_payload,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_poisson_segmented_admission_report(
        load_historical_poisson_parameter_learning_report(args.source_learning_report),
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
    if not report.segmented_candidate_model_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _competition_decision(
    competition: HistoricalPoissonCompetitionParameterLearningResult,
    *,
    options: HistoricalPoissonSegmentedAdmissionOptions,
) -> HistoricalPoissonCompetitionSegmentDecision:
    selected_validation = competition.selected_validation
    selected_candidate = competition.selected_candidate
    if selected_validation is None:
        return HistoricalPoissonCompetitionSegmentDecision(
            competition_id=competition.competition_id,
            status="skipped",
            validation_count=0,
            reasons=["missing_selected_validation"],
        )
    model_signal_weight = (
        max(0.0, min(1.0, 1.0 - selected_candidate.market_anchor_weight))
        if selected_candidate is not None
        else None
    )
    reasons = _competition_failure_reasons(
        selected_validation.validation_count,
        selected_validation.deltas_json,
        model_signal_weight=model_signal_weight,
        options=options,
    )
    status: HistoricalPoissonSegmentDecisionStatus = (
        "admitted" if not reasons else "baseline_fallback"
    )
    summary = {
        "calculation_basis": "historical_poisson_competition_segment_decision_v3_2",
        "competition_id": competition.competition_id,
        "status": status,
        "validation_count": selected_validation.validation_count,
        "selected_candidate": (
            selected_candidate.model_dump(mode="json")
            if selected_candidate is not None
            else None
        ),
        "model_signal_weight": model_signal_weight,
        "deltas_json": dict(selected_validation.deltas_json),
        "reasons": reasons,
    }
    return HistoricalPoissonCompetitionSegmentDecision(
        competition_id=competition.competition_id,
        status=status,
        validation_count=selected_validation.validation_count,
        selected_candidate_key=(
            selected_candidate.candidate_key if selected_candidate is not None else None
        ),
        model_signal_weight=model_signal_weight,
        deltas_json=dict(selected_validation.deltas_json),
        reasons=reasons,
        summary_json=summary,
    )


def _competition_failure_reasons(
    validation_count: int,
    deltas: Mapping[str, object],
    *,
    model_signal_weight: float | None,
    options: HistoricalPoissonSegmentedAdmissionOptions,
) -> list[str]:
    reasons: list[str] = []
    if validation_count < options.min_competition_validation_count:
        reasons.append("validation_count_below_floor")
    if (
        options.min_selected_model_signal_weight is not None
        and (
            model_signal_weight is None
            or model_signal_weight < options.min_selected_model_signal_weight
        )
    ):
        reasons.append("model_signal_weight_below_floor")
    _append_minimum_reason(
        reasons,
        deltas,
        "hit_rate_delta",
        options.min_hit_rate_delta,
    )
    _append_maximum_reason(
        reasons,
        deltas,
        "brier_score_delta",
        options.max_brier_score_delta,
    )
    _append_maximum_reason(
        reasons,
        deltas,
        "log_loss_delta",
        options.max_log_loss_delta,
    )
    _append_maximum_reason(
        reasons,
        deltas,
        "expected_calibration_error_delta",
        options.max_expected_calibration_error_delta,
    )
    _append_minimum_reason(
        reasons,
        deltas,
        "average_actual_probability_delta",
        options.min_average_actual_probability_delta,
    )
    return reasons


def _segmented_metrics(
    source_report: HistoricalPoissonParameterLearningReport,
    decisions: Sequence[HistoricalPoissonCompetitionSegmentDecision],
) -> dict[str, object]:
    decision_by_competition = {
        decision.competition_id: decision for decision in decisions
    }
    candidate_metrics: list[HistoricalPoissonWalkForwardMetricSet] = []
    baseline_metrics: list[HistoricalPoissonWalkForwardMetricSet] = []
    admitted_candidate_counts: Counter[str] = Counter()
    admitted_validation_count = 0
    fallback_validation_count = 0
    for competition in source_report.competitions:
        selected_validation = competition.selected_validation
        if selected_validation is None:
            continue
        decision = decision_by_competition.get(competition.competition_id)
        if decision is not None and decision.status == "admitted":
            candidate_metrics.append(selected_validation.candidate)
            admitted_validation_count += selected_validation.validation_count
            if decision.selected_candidate_key is not None:
                admitted_candidate_counts[decision.selected_candidate_key] += 1
        else:
            candidate_metrics.append(selected_validation.baseline)
            fallback_validation_count += selected_validation.validation_count
        baseline_metrics.append(selected_validation.baseline)
    segmented_candidate = _combine_metric_sets(candidate_metrics)
    segmented_baseline = _combine_metric_sets(baseline_metrics)
    segmented_deltas = (
        _metric_deltas(segmented_candidate, segmented_baseline)
        if segmented_candidate is not None and segmented_baseline is not None
        else {}
    )
    return {
        "admitted_competition_count": sum(
            1 for decision in decisions if decision.status == "admitted"
        ),
        "fallback_competition_count": sum(
            1 for decision in decisions if decision.status == "baseline_fallback"
        ),
        "skipped_competition_count": sum(
            1 for decision in decisions if decision.status == "skipped"
        ),
        "admitted_validation_count": admitted_validation_count,
        "fallback_validation_count": fallback_validation_count,
        "segmented_validation_count": (
            segmented_candidate.sample_size if segmented_candidate is not None else 0
        ),
        "segmented_candidate": segmented_candidate,
        "segmented_baseline": segmented_baseline,
        "segmented_deltas_json": segmented_deltas,
        "admitted_candidate_counts": dict(admitted_candidate_counts),
    }


def _checks(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    decisions: Sequence[HistoricalPoissonCompetitionSegmentDecision],
    metrics: Mapping[str, object],
    options: HistoricalPoissonSegmentedAdmissionOptions,
) -> list[HistoricalPoissonSegmentedAdmissionCheck]:
    deltas = _mapping(metrics["segmented_deltas_json"])
    return [
        _boolean_check(
            "source_status_generated",
            source_report.status == "generated",
            enabled=options.require_source_status_generated,
            detail="source parameter learning report must be generated",
        ),
        _minimum_check(
            "source_learned_competition_count",
            source_report.learned_competition_count,
            options.min_source_learned_competition_count,
            detail="source report needs enough learned competitions",
        ),
        _minimum_check(
            "source_validation_count",
            source_report.validation_count,
            options.min_source_validation_count,
            detail="source report needs enough validation samples",
        ),
        _minimum_check(
            "source_candidate_count",
            source_report.candidate_count,
            options.min_source_candidate_count,
            detail="source report must evaluate enough candidates",
        ),
        _maximum_check(
            "source_warning_count",
            len(source_report.warnings),
            options.max_source_warning_count,
            detail="source report warnings should remain within the limit",
        ),
        _minimum_check(
            "admitted_competition_count",
            _int(metrics["admitted_competition_count"]),
            options.min_admitted_competition_count,
            detail="segmented promotion needs enough admitted competitions",
        ),
        _minimum_check(
            "admitted_validation_count",
            _int(metrics["admitted_validation_count"]),
            options.min_admitted_validation_count,
            detail="segmented promotion needs enough admitted validation samples",
        ),
        _minimum_check(
            "segmented_hit_rate_delta",
            _optional_float(_mapping_value(deltas, "hit_rate_delta")),
            options.min_hit_rate_delta if options.require_segmented_no_harm else None,
            detail="segmented candidate should not reduce aggregate hit rate",
        ),
        _maximum_check(
            "segmented_brier_score_delta",
            _optional_float(_mapping_value(deltas, "brier_score_delta")),
            options.max_brier_score_delta
            if options.require_segmented_no_harm
            else None,
            detail="segmented candidate should not worsen aggregate Brier score",
        ),
        _maximum_check(
            "segmented_log_loss_delta",
            _optional_float(_mapping_value(deltas, "log_loss_delta")),
            options.max_log_loss_delta if options.require_segmented_no_harm else None,
            detail="segmented candidate should not worsen aggregate log loss",
        ),
        _maximum_check(
            "segmented_expected_calibration_error_delta",
            _optional_float(
                _mapping_value(deltas, "expected_calibration_error_delta")
            ),
            options.max_expected_calibration_error_delta
            if options.require_segmented_no_harm
            else None,
            detail="segmented candidate should not worsen aggregate calibration",
        ),
        _minimum_check(
            "segmented_average_actual_probability_delta",
            _optional_float(_mapping_value(deltas, "average_actual_probability_delta")),
            options.min_average_actual_probability_delta
            if options.require_segmented_no_harm
            else None,
            detail="segmented candidate should not reduce actual-outcome probability",
        ),
        _boolean_check(
            "public_prediction_unchanged",
            True,
            enabled=options.require_no_public_prediction_change,
            detail="segmented admission is evidence only and must not alter defaults",
        ),
        _boolean_check(
            "no_admitted_competition_failed_local_no_harm",
            all(
                not decision.reasons
                for decision in decisions
                if decision.status == "admitted"
            ),
            detail="admitted competitions must pass local no-harm checks",
        ),
    ]


def _decision_payload(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    decisions: Sequence[HistoricalPoissonCompetitionSegmentDecision],
    metrics: Mapping[str, object],
    status: HistoricalPoissonSegmentedAdmissionStatus,
    segmented_candidate_model_allowed: bool,
    shadow_allowed: bool,
    options: HistoricalPoissonSegmentedAdmissionOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": "historical_poisson_segmented_admission_decision_v3_2",
        "status": status,
        "segmented_candidate_model_allowed": segmented_candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "source_report_key": source_report.report_key,
        "default_prediction_path_changed": False,
        "deployment_scope": "competition_segmented",
        "admitted_competitions": [
            decision.competition_id
            for decision in decisions
            if decision.status == "admitted"
        ],
        "fallback_competitions": [
            decision.competition_id
            for decision in decisions
            if decision.status == "baseline_fallback"
        ],
        "admitted_validation_count": metrics["admitted_validation_count"],
        "segmented_validation_count": metrics["segmented_validation_count"],
        "segmented_deltas_json": metrics["segmented_deltas_json"],
        "options": options.model_dump(mode="json"),
        "rollback_conditions": [
            "disable_if_source_learning_report_missing_or_not_generated",
            "disable_if_admitted_competition_count_below_floor",
            "disable_if_admitted_validation_count_below_floor",
            "disable_if_segmented_brier_or_log_loss_regresses",
            "disable_if_any_admitted_competition_fails_local_no_harm",
        ],
    }


def _status(
    *,
    candidate_model_allowed: bool,
    shadow_allowed: bool,
) -> HistoricalPoissonSegmentedAdmissionStatus:
    if candidate_model_allowed:
        return "accepted"
    if shadow_allowed:
        return "shadow_only"
    return "rejected"


def _source_ready(checks: Sequence[HistoricalPoissonSegmentedAdmissionCheck]) -> bool:
    source_names = {
        "source_status_generated",
        "source_learned_competition_count",
        "source_validation_count",
        "source_candidate_count",
        "source_warning_count",
        "public_prediction_unchanged",
    }
    return all(check.status != "failed" for check in checks if check.name in source_names)


def _coverage_ready(checks: Sequence[HistoricalPoissonSegmentedAdmissionCheck]) -> bool:
    coverage_names = {
        "admitted_competition_count",
        "admitted_validation_count",
        "no_admitted_competition_failed_local_no_harm",
    }
    return all(check.status != "failed" for check in checks if check.name in coverage_names)


def _segmented_no_harm_ready(
    checks: Sequence[HistoricalPoissonSegmentedAdmissionCheck],
) -> bool:
    no_harm_names = {
        "segmented_hit_rate_delta",
        "segmented_brier_score_delta",
        "segmented_log_loss_delta",
        "segmented_expected_calibration_error_delta",
        "segmented_average_actual_probability_delta",
    }
    return all(check.status != "failed" for check in checks if check.name in no_harm_names)


def _warnings(
    *,
    status: HistoricalPoissonSegmentedAdmissionStatus,
    checks: Sequence[HistoricalPoissonSegmentedAdmissionCheck],
    decisions: Sequence[HistoricalPoissonCompetitionSegmentDecision],
) -> list[str]:
    warnings = [
        f"poisson_segmented_admission:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    fallback_count = sum(
        1 for decision in decisions if decision.status == "baseline_fallback"
    )
    skipped_count = sum(1 for decision in decisions if decision.status == "skipped")
    if fallback_count:
        warnings.append(f"poisson_segmented_admission:fallback_competitions:{fallback_count}")
    if skipped_count:
        warnings.append(f"poisson_segmented_admission:skipped_competitions:{skipped_count}")
    warnings.append(f"poisson_segmented_admission:{status}")
    return warnings


def _combine_metric_sets(
    metric_sets: Sequence[HistoricalPoissonWalkForwardMetricSet],
) -> HistoricalPoissonWalkForwardMetricSet | None:
    sample_size = sum(metric.sample_size for metric in metric_sets)
    if sample_size == 0:
        return None
    return HistoricalPoissonWalkForwardMetricSet(
        sample_size=sample_size,
        hit_count=sum(metric.hit_count for metric in metric_sets),
        hit_rate=_safe_divide(sum(metric.hit_count for metric in metric_sets), sample_size),
        brier_score=_weighted_metric(metric_sets, "brier_score"),
        log_loss=_weighted_metric(metric_sets, "log_loss"),
        average_actual_probability=_weighted_metric(
            metric_sets,
            "average_actual_probability",
        ),
        expected_calibration_error=_weighted_metric(
            metric_sets,
            "expected_calibration_error",
        ),
        calibration_observation_count=sum(
            metric.calibration_observation_count for metric in metric_sets
        ),
        included_calibration_bucket_count=sum(
            metric.included_calibration_bucket_count for metric in metric_sets
        ),
        skipped_small_calibration_bucket_count=sum(
            metric.skipped_small_calibration_bucket_count for metric in metric_sets
        ),
    )


def _weighted_metric(
    metric_sets: Sequence[HistoricalPoissonWalkForwardMetricSet],
    metric_name: str,
) -> float | None:
    numerator = 0.0
    denominator = 0
    for metric in metric_sets:
        value = getattr(metric, metric_name)
        if value is None:
            continue
        numerator += value * metric.sample_size
        denominator += metric.sample_size
    return _safe_divide(numerator, denominator)


def _metric_deltas(
    candidate: HistoricalPoissonWalkForwardMetricSet,
    baseline: HistoricalPoissonWalkForwardMetricSet,
) -> dict[str, object]:
    return {
        "hit_rate_delta": _optional_delta(candidate.hit_rate, baseline.hit_rate),
        "brier_score_delta": _optional_delta(
            candidate.brier_score,
            baseline.brier_score,
        ),
        "log_loss_delta": _optional_delta(candidate.log_loss, baseline.log_loss),
        "average_actual_probability_delta": _optional_delta(
            candidate.average_actual_probability,
            baseline.average_actual_probability,
        ),
        "expected_calibration_error_delta": _optional_delta(
            candidate.expected_calibration_error,
            baseline.expected_calibration_error,
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Gate learned Poisson parameters by competition segment."
    )
    parser.add_argument("source_learning_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-source-learned-competition-count", type=int, default=1)
    parser.add_argument("--min-source-validation-count", type=int, default=100)
    parser.add_argument("--min-source-candidate-count", type=int, default=1)
    parser.add_argument("--max-source-warning-count", type=int, default=0)
    parser.add_argument("--min-competition-validation-count", type=int, default=100)
    parser.add_argument("--min-admitted-competition-count", type=int, default=1)
    parser.add_argument("--min-admitted-validation-count", type=int, default=100)
    parser.add_argument("--min-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-average-actual-probability-delta", type=float)
    parser.add_argument("--min-selected-model-signal-weight", type=float, default=0.05)
    parser.add_argument("--allow-source-status-not-generated", action="store_true")
    parser.add_argument("--allow-segmented-harm", action="store_true")
    parser.add_argument("--allow-public-prediction-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalPoissonSegmentedAdmissionOptions:
    return HistoricalPoissonSegmentedAdmissionOptions(
        min_source_learned_competition_count=(
            args.min_source_learned_competition_count
        ),
        min_source_validation_count=args.min_source_validation_count,
        min_source_candidate_count=args.min_source_candidate_count,
        max_source_warning_count=args.max_source_warning_count,
        min_competition_validation_count=args.min_competition_validation_count,
        min_admitted_competition_count=args.min_admitted_competition_count,
        min_admitted_validation_count=args.min_admitted_validation_count,
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        min_average_actual_probability_delta=(
            args.min_average_actual_probability_delta
        ),
        min_selected_model_signal_weight=args.min_selected_model_signal_weight,
        require_source_status_generated=not args.allow_source_status_not_generated,
        require_segmented_no_harm=not args.allow_segmented_harm,
        require_no_public_prediction_change=not args.allow_public_prediction_change,
    )


def _boolean_check(
    name: str,
    passed: bool,
    *,
    enabled: bool = True,
    detail: str,
) -> HistoricalPoissonSegmentedAdmissionCheck:
    if not enabled:
        return _skipped_check(name=name, actual=passed, detail=detail)
    return HistoricalPoissonSegmentedAdmissionCheck(
        name=name,
        status="passed" if passed else "failed",
        actual=passed,
        threshold=True,
        detail=detail,
    )


def _minimum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    *,
    detail: str,
) -> HistoricalPoissonSegmentedAdmissionCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalPoissonSegmentedAdmissionCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    *,
    detail: str,
) -> HistoricalPoissonSegmentedAdmissionCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalPoissonSegmentedAdmissionCheck(
        name=name,
        status="passed" if actual is not None and actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _skipped_check(
    *,
    name: str,
    actual: float | int | str | bool | None,
    detail: str,
) -> HistoricalPoissonSegmentedAdmissionCheck:
    return HistoricalPoissonSegmentedAdmissionCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _append_minimum_reason(
    reasons: list[str],
    deltas: Mapping[str, object],
    key: str,
    threshold: float | None,
) -> None:
    if threshold is None:
        return
    value = _optional_float(_mapping_value(deltas, key))
    if value is None or value < threshold:
        reasons.append(f"{key}_below_floor")


def _append_maximum_reason(
    reasons: list[str],
    deltas: Mapping[str, object],
    key: str,
    threshold: float | None,
) -> None:
    if threshold is None:
        return
    value = _optional_float(_mapping_value(deltas, key))
    if value is None or value > threshold:
        reasons.append(f"{key}_above_ceiling")


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalPoissonSegmentedAdmissionCheck],
    decisions: Sequence[HistoricalPoissonCompetitionSegmentDecision],
    decision_payload: Mapping[str, object],
) -> str:
    payload = {
        "summary": _jsonable(summary),
        "checks": [check.model_dump(mode="json") for check in checks],
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
        "decision_payload": dict(decision_payload),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_poisson_segmented_admission:{digest}"


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_jsonable(item) for item in value]
    return value


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _mapping_dict(value: object) -> dict[str, object]:
    return dict(_mapping(value))


def _mapping_value(value: Mapping[str, object], key: str) -> object:
    return value.get(key)


def _metric_or_none(value: object) -> HistoricalPoissonWalkForwardMetricSet | None:
    if isinstance(value, HistoricalPoissonWalkForwardMetricSet):
        return value
    return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline
