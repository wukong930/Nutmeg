from __future__ import annotations

from argparse import ArgumentParser, Namespace
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
    HistoricalPoissonParameterCandidate,
    HistoricalPoissonParameterLearningReport,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
    load_historical_prematch_feature_sample_readiness_report,
)

type HistoricalPoissonPrematchLambdaAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalPoissonPrematchLambdaAdmissionCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalPoissonPrematchLambdaAdmissionOptions(BaseModel):
    min_learned_competition_count: int = Field(default=1, ge=0)
    min_validation_count: int = Field(default=100, ge=0)
    min_candidate_count: int = Field(default=1, ge=0)
    max_warning_count: int | None = Field(default=0, ge=0)
    min_ready_fixture_count: int = Field(default=100, ge=0)
    min_ready_competition_count: int = Field(default=1, ge=0)
    min_ready_season_count: int = Field(default=1, ge=0)
    min_ready_competition_season_count: int = Field(default=1, ge=0)
    min_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_expected_calibration_error_delta: float | None = 0.0
    min_average_actual_probability_delta: float | None = None
    max_failed_competition_no_harm_count: int | None = Field(default=0, ge=0)
    min_selected_prematch_signal_weight: float | None = Field(
        default=0.001,
        ge=0.0,
    )
    min_selected_market_movement_weight: float | None = Field(default=0.01, ge=0.0)
    require_source_status_generated: bool = True
    require_sample_readiness_report: bool = True
    require_sample_ready_allowed: bool = True
    require_prematch_lambda_method: bool = True
    require_no_public_prediction_change: bool = True


class HistoricalPoissonPrematchLambdaAdmissionCheck(BaseModel):
    name: str
    status: HistoricalPoissonPrematchLambdaAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPoissonPrematchLambdaAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalPoissonPrematchLambdaAdmissionStatus
    candidate_model_allowed: bool
    shadow_allowed: bool
    source_report_key: str
    source_status: str
    sample_readiness_key: str | None = None
    sample_readiness_status: str | None = None
    sample_ready_allowed: bool | None = None
    competition_count: int = Field(ge=0)
    learned_competition_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    ready_fixture_count: int | None = Field(default=None, ge=0)
    ready_competition_count: int | None = Field(default=None, ge=0)
    ready_season_count: int | None = Field(default=None, ge=0)
    ready_competition_season_count: int | None = Field(default=None, ge=0)
    selected_prematch_candidate_count: int = Field(ge=0)
    selected_non_prematch_candidate_count: int = Field(ge=0)
    failed_competition_no_harm_count: int = Field(ge=0)
    hit_rate_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    expected_calibration_error_delta: float | None = None
    average_actual_probability_delta: float | None = None
    min_selected_prematch_signal_weight: float | None = None
    average_selected_prematch_signal_weight: float | None = None
    min_selected_market_movement_weight: float | None = None
    average_selected_market_movement_weight: float | None = None
    selected_candidate_counts: dict[str, int] = Field(default_factory=dict)
    public_prediction_changed: bool = False
    checks: list[HistoricalPoissonPrematchLambdaAdmissionCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_poisson_prematch_lambda_admission_report(
    path: Path | str,
) -> HistoricalPoissonPrematchLambdaAdmissionReport:
    return HistoricalPoissonPrematchLambdaAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_poisson_prematch_lambda_admission_report(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None = None,
    options: HistoricalPoissonPrematchLambdaAdmissionOptions | None = None,
) -> HistoricalPoissonPrematchLambdaAdmissionReport:
    resolved_options = options or HistoricalPoissonPrematchLambdaAdmissionOptions()
    metrics = _metrics(source_report, sample_readiness_report=sample_readiness_report)
    checks = _checks(
        source_report,
        sample_readiness_report=sample_readiness_report,
        metrics=metrics,
        options=resolved_options,
    )
    source_ready = _source_ready(checks)
    sample_ready = _sample_ready(checks)
    lambda_signal_ready = _lambda_signal_ready(checks)
    no_harm = _no_harm_ready(checks)
    candidate_model_allowed = (
        source_ready and sample_ready and lambda_signal_ready and no_harm
    )
    shadow_allowed = source_ready and (
        sample_readiness_report is None or sample_readiness_report.shadow_allowed
    )
    status = _status(
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
    )
    warnings = _warnings(status=status, checks=checks)
    decision_payload = _decision_payload(
        source_report,
        sample_readiness_report=sample_readiness_report,
        metrics=metrics,
        status=status,
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_poisson_prematch_lambda_admission_v3_2",
        "status": status,
        "candidate_model_allowed": candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "source_report_key": source_report.report_key,
        "source_status": source_report.status,
        **metrics,
        "public_prediction_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decision_payload)
    return HistoricalPoissonPrematchLambdaAdmissionReport(
        report_key=report_key,
        status=status,
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        source_report_key=source_report.report_key,
        source_status=source_report.status,
        sample_readiness_key=_optional_str(metrics["sample_readiness_key"]),
        sample_readiness_status=_optional_str(metrics["sample_readiness_status"]),
        sample_ready_allowed=_optional_bool(metrics["sample_ready_allowed"]),
        competition_count=source_report.competition_count,
        learned_competition_count=source_report.learned_competition_count,
        candidate_count=source_report.candidate_count,
        fixture_count=source_report.fixture_count,
        validation_count=source_report.validation_count,
        warning_count=len(source_report.warnings),
        ready_fixture_count=_optional_int(metrics["ready_fixture_count"]),
        ready_competition_count=_optional_int(metrics["ready_competition_count"]),
        ready_season_count=_optional_int(metrics["ready_season_count"]),
        ready_competition_season_count=_optional_int(
            metrics["ready_competition_season_count"]
        ),
        selected_prematch_candidate_count=_int(
            metrics["selected_prematch_candidate_count"]
        ),
        selected_non_prematch_candidate_count=_int(
            metrics["selected_non_prematch_candidate_count"]
        ),
        failed_competition_no_harm_count=_int(
            metrics["failed_competition_no_harm_count"]
        ),
        hit_rate_delta=_optional_float(metrics["hit_rate_delta"]),
        brier_score_delta=_optional_float(metrics["brier_score_delta"]),
        log_loss_delta=_optional_float(metrics["log_loss_delta"]),
        expected_calibration_error_delta=_optional_float(
            metrics["expected_calibration_error_delta"]
        ),
        average_actual_probability_delta=_optional_float(
            metrics["average_actual_probability_delta"]
        ),
        min_selected_prematch_signal_weight=_optional_float(
            metrics["min_selected_prematch_signal_weight"]
        ),
        average_selected_prematch_signal_weight=_optional_float(
            metrics["average_selected_prematch_signal_weight"]
        ),
        min_selected_market_movement_weight=_optional_float(
            metrics["min_selected_market_movement_weight"]
        ),
        average_selected_market_movement_weight=_optional_float(
            metrics["average_selected_market_movement_weight"]
        ),
        selected_candidate_counts={
            str(key): _int(value)
            for key, value in _mapping(metrics["selected_candidate_counts"]).items()
        },
        public_prediction_changed=False,
        checks=checks,
        warnings=warnings,
        decision_payload_json=decision_payload,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    sample_readiness_report = (
        load_historical_prematch_feature_sample_readiness_report(
            args.sample_readiness_report
        )
        if args.sample_readiness_report is not None
        else None
    )
    report = build_historical_poisson_prematch_lambda_admission_report(
        load_historical_poisson_parameter_learning_report(args.source_learning_report),
        sample_readiness_report=sample_readiness_report,
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
    if not report.candidate_model_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _metrics(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None,
) -> dict[str, object]:
    deltas = dict(source_report.overall_validation_deltas_json)
    selected_candidates = _selected_candidates(source_report)
    prematch_candidates = [
        candidate
        for candidate in selected_candidates
        if candidate.lambda_method == "prematch_feature_adjusted"
    ]
    prematch_signal_weights = [
        _prematch_signal_weight(candidate) for candidate in prematch_candidates
    ]
    market_movement_weights = [
        candidate.prematch_feature_odds_movement_weight
        for candidate in prematch_candidates
    ]
    return {
        "competition_count": source_report.competition_count,
        "learned_competition_count": source_report.learned_competition_count,
        "candidate_count": source_report.candidate_count,
        "fixture_count": source_report.fixture_count,
        "validation_count": source_report.validation_count,
        "warning_count": len(source_report.warnings),
        "sample_readiness_key": (
            sample_readiness_report.readiness_key
            if sample_readiness_report is not None
            else None
        ),
        "sample_readiness_status": (
            sample_readiness_report.status
            if sample_readiness_report is not None
            else None
        ),
        "sample_ready_allowed": (
            sample_readiness_report.sample_ready_allowed
            if sample_readiness_report is not None
            else None
        ),
        "ready_fixture_count": (
            sample_readiness_report.ready_fixture_count
            if sample_readiness_report is not None
            else None
        ),
        "ready_competition_count": (
            sample_readiness_report.ready_competition_count
            if sample_readiness_report is not None
            else None
        ),
        "ready_season_count": (
            sample_readiness_report.ready_season_count
            if sample_readiness_report is not None
            else None
        ),
        "ready_competition_season_count": (
            sample_readiness_report.ready_competition_season_count
            if sample_readiness_report is not None
            else None
        ),
        "selected_prematch_candidate_count": len(prematch_candidates),
        "selected_non_prematch_candidate_count": (
            len(selected_candidates) - len(prematch_candidates)
        ),
        "failed_competition_no_harm_count": _failed_competition_no_harm_count(
            source_report
        ),
        "hit_rate_delta": _mapping_float(deltas, "hit_rate_delta"),
        "brier_score_delta": _mapping_float(deltas, "brier_score_delta"),
        "log_loss_delta": _mapping_float(deltas, "log_loss_delta"),
        "expected_calibration_error_delta": _mapping_float(
            deltas,
            "expected_calibration_error_delta",
        ),
        "average_actual_probability_delta": _mapping_float(
            deltas,
            "average_actual_probability_delta",
        ),
        "min_selected_prematch_signal_weight": (
            min(prematch_signal_weights) if prematch_signal_weights else None
        ),
        "average_selected_prematch_signal_weight": (
            sum(prematch_signal_weights) / len(prematch_signal_weights)
            if prematch_signal_weights
            else None
        ),
        "min_selected_market_movement_weight": (
            min(market_movement_weights) if market_movement_weights else None
        ),
        "average_selected_market_movement_weight": (
            sum(market_movement_weights) / len(market_movement_weights)
            if market_movement_weights
            else None
        ),
        "selected_candidate_counts": dict(source_report.selected_candidate_counts),
    }


def _checks(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None,
    metrics: Mapping[str, object],
    options: HistoricalPoissonPrematchLambdaAdmissionOptions,
) -> list[HistoricalPoissonPrematchLambdaAdmissionCheck]:
    return [
        _boolean_check(
            "source_status_generated",
            source_report.status == "generated",
            enabled=options.require_source_status_generated,
            detail="prematch lambda learning report must be generated before admission",
        ),
        _minimum_check(
            "learned_competition_count",
            _optional_float(metrics["learned_competition_count"]),
            options.min_learned_competition_count,
            detail="prematch lambda learning needs enough learned competitions",
        ),
        _minimum_check(
            "validation_count",
            _optional_float(metrics["validation_count"]),
            options.min_validation_count,
            detail="prematch lambda learning needs enough held-out validation samples",
        ),
        _minimum_check(
            "candidate_count",
            _optional_float(metrics["candidate_count"]),
            options.min_candidate_count,
            detail="prematch lambda learning must evaluate enough candidates",
        ),
        _maximum_check(
            "warning_count",
            _optional_float(metrics["warning_count"]),
            options.max_warning_count,
            detail="prematch lambda learning warnings should remain within the limit",
        ),
        _boolean_check(
            "sample_readiness_report_present",
            sample_readiness_report is not None,
            enabled=options.require_sample_readiness_report,
            detail="prematch lambda admission needs a sample-readiness report",
        ),
        _boolean_check(
            "sample_ready_allowed",
            sample_readiness_report is not None
            and sample_readiness_report.sample_ready_allowed,
            enabled=options.require_sample_ready_allowed,
            detail="prematch feature sample readiness must be accepted",
        ),
        _minimum_check(
            "ready_fixture_count",
            _optional_float(metrics["ready_fixture_count"]),
            options.min_ready_fixture_count if sample_readiness_report is not None else None,
            detail="accepted prematch feature sample should contain enough fixtures",
        ),
        _minimum_check(
            "ready_competition_count",
            _optional_float(metrics["ready_competition_count"]),
            (
                options.min_ready_competition_count
                if sample_readiness_report is not None
                else None
            ),
            detail="accepted prematch feature sample should cover enough competitions",
        ),
        _minimum_check(
            "ready_season_count",
            _optional_float(metrics["ready_season_count"]),
            options.min_ready_season_count if sample_readiness_report is not None else None,
            detail="accepted prematch feature sample should cover enough seasons",
        ),
        _minimum_check(
            "ready_competition_season_count",
            _optional_float(metrics["ready_competition_season_count"]),
            (
                options.min_ready_competition_season_count
                if sample_readiness_report is not None
                else None
            ),
            detail="accepted prematch feature sample should cover enough competition seasons",
        ),
        _minimum_check(
            "selected_prematch_candidate_count",
            _optional_float(metrics["selected_prematch_candidate_count"]),
            options.min_learned_competition_count,
            detail="selected candidates should use the prematch lambda method",
        ),
        _maximum_check(
            "selected_non_prematch_candidate_count",
            _optional_float(metrics["selected_non_prematch_candidate_count"]),
            0 if options.require_prematch_lambda_method else None,
            detail="prematch lambda admission cannot promote non-prematch candidates",
        ),
        _minimum_check(
            "selected_prematch_signal_weight",
            _optional_float(metrics["min_selected_prematch_signal_weight"]),
            options.min_selected_prematch_signal_weight,
            detail="selected prematch candidates need a non-trivial lambda signal",
        ),
        _minimum_check(
            "selected_market_movement_weight",
            _optional_float(metrics["min_selected_market_movement_weight"]),
            options.min_selected_market_movement_weight,
            detail="market-movement samples need selected odds-movement signal",
        ),
        _minimum_check(
            "hit_rate_delta",
            _optional_float(metrics["hit_rate_delta"]),
            options.min_hit_rate_delta,
            detail="prematch lambda candidate should not reduce 1X2 hit rate",
        ),
        _maximum_check(
            "brier_score_delta",
            _optional_float(metrics["brier_score_delta"]),
            options.max_brier_score_delta,
            detail="prematch lambda candidate should not worsen Brier score",
        ),
        _maximum_check(
            "log_loss_delta",
            _optional_float(metrics["log_loss_delta"]),
            options.max_log_loss_delta,
            detail="prematch lambda candidate should not worsen log loss",
        ),
        _maximum_check(
            "expected_calibration_error_delta",
            _optional_float(metrics["expected_calibration_error_delta"]),
            options.max_expected_calibration_error_delta,
            detail="prematch lambda candidate should not worsen calibration",
        ),
        _minimum_check(
            "average_actual_probability_delta",
            _optional_float(metrics["average_actual_probability_delta"]),
            options.min_average_actual_probability_delta,
            detail="prematch lambda candidate should not reduce actual-outcome probability",
        ),
        _maximum_check(
            "failed_competition_no_harm_count",
            _optional_float(metrics["failed_competition_no_harm_count"]),
            options.max_failed_competition_no_harm_count,
            detail="competition-level prematch lambda regressions should stay within limit",
        ),
        _boolean_check(
            "public_prediction_unchanged",
            True,
            enabled=options.require_no_public_prediction_change,
            detail="admission evidence must not change the public prediction path",
        ),
    ]


def _decision_payload(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None,
    metrics: Mapping[str, object],
    status: HistoricalPoissonPrematchLambdaAdmissionStatus,
    candidate_model_allowed: bool,
    shadow_allowed: bool,
    options: HistoricalPoissonPrematchLambdaAdmissionOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": "historical_poisson_prematch_lambda_admission_decision_v3_2",
        "status": status,
        "candidate_model_allowed": candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "source_report_key": source_report.report_key,
        "sample_readiness_key": (
            sample_readiness_report.readiness_key
            if sample_readiness_report is not None
            else None
        ),
        "default_prediction_path_changed": False,
        "deployment_scope": "prematch_feature_lambda_shadow_gate",
        "selected_candidate_counts": metrics["selected_candidate_counts"],
        "min_selected_prematch_signal_weight": metrics[
            "min_selected_prematch_signal_weight"
        ],
        "min_selected_market_movement_weight": metrics[
            "min_selected_market_movement_weight"
        ],
        "failed_competition_no_harm_count": metrics[
            "failed_competition_no_harm_count"
        ],
        "options": options.model_dump(mode="json"),
        "rollback_conditions": [
            "disable_if_learning_report_missing_or_not_generated",
            "disable_if_sample_readiness_missing_or_not_accepted",
            "disable_if_validation_sample_count_below_floor",
            "disable_if_selected_candidate_is_not_prematch_feature_adjusted",
            "disable_if_prematch_signal_weight_below_floor",
            "disable_if_brier_or_log_loss_regresses",
            "disable_if_calibration_error_regresses_or_is_unmeasured",
            "disable_if_competition_level_regressions_exceed_limit",
        ],
        "notes": [
            "Admission is governance evidence only; it does not modify defaults.",
            "Shadow-only status keeps prematch feature lambda adjustment out of production.",
        ],
    }


def _selected_candidates(
    source_report: HistoricalPoissonParameterLearningReport,
) -> list[HistoricalPoissonParameterCandidate]:
    return [
        competition.selected_candidate
        for competition in source_report.competitions
        if competition.selected_candidate is not None
    ]


def _prematch_signal_weight(candidate: HistoricalPoissonParameterCandidate) -> float:
    feature_weight = (
        candidate.prematch_feature_odds_movement_weight
        + candidate.prematch_feature_draw_risk_weight
    )
    return max(0.0, feature_weight * candidate.max_prematch_feature_lambda_adjustment)


def _failed_competition_no_harm_count(
    source_report: HistoricalPoissonParameterLearningReport,
) -> int:
    failed_count = 0
    for competition in source_report.competitions:
        if competition.selected_validation is None:
            continue
        deltas = competition.selected_validation.deltas_json
        hit_rate_delta = _mapping_float_or_none(deltas, "hit_rate_delta")
        brier_score_delta = _mapping_float_or_none(deltas, "brier_score_delta")
        log_loss_delta = _mapping_float_or_none(deltas, "log_loss_delta")
        calibration_delta = _mapping_float_or_none(
            deltas,
            "expected_calibration_error_delta",
        )
        if (
            hit_rate_delta is None
            or hit_rate_delta < 0.0
            or brier_score_delta is None
            or brier_score_delta > 0.0
            or log_loss_delta is None
            or log_loss_delta > 0.0
            or calibration_delta is None
            or calibration_delta > 0.0
        ):
            failed_count += 1
    return failed_count


def _source_ready(
    checks: Sequence[HistoricalPoissonPrematchLambdaAdmissionCheck],
) -> bool:
    source_names = {
        "source_status_generated",
        "learned_competition_count",
        "validation_count",
        "candidate_count",
        "warning_count",
        "public_prediction_unchanged",
    }
    return all(check.status != "failed" for check in checks if check.name in source_names)


def _sample_ready(
    checks: Sequence[HistoricalPoissonPrematchLambdaAdmissionCheck],
) -> bool:
    sample_names = {
        "sample_readiness_report_present",
        "sample_ready_allowed",
        "ready_fixture_count",
        "ready_competition_count",
        "ready_season_count",
        "ready_competition_season_count",
    }
    return all(check.status != "failed" for check in checks if check.name in sample_names)


def _lambda_signal_ready(
    checks: Sequence[HistoricalPoissonPrematchLambdaAdmissionCheck],
) -> bool:
    signal_names = {
        "selected_prematch_candidate_count",
        "selected_non_prematch_candidate_count",
        "selected_prematch_signal_weight",
        "selected_market_movement_weight",
    }
    return all(check.status != "failed" for check in checks if check.name in signal_names)


def _no_harm_ready(
    checks: Sequence[HistoricalPoissonPrematchLambdaAdmissionCheck],
) -> bool:
    no_harm_names = {
        "hit_rate_delta",
        "brier_score_delta",
        "log_loss_delta",
        "expected_calibration_error_delta",
        "average_actual_probability_delta",
        "failed_competition_no_harm_count",
    }
    return all(check.status != "failed" for check in checks if check.name in no_harm_names)


def _status(
    *,
    candidate_model_allowed: bool,
    shadow_allowed: bool,
) -> HistoricalPoissonPrematchLambdaAdmissionStatus:
    if candidate_model_allowed:
        return "accepted"
    if shadow_allowed:
        return "shadow_only"
    return "rejected"


def _warnings(
    *,
    status: HistoricalPoissonPrematchLambdaAdmissionStatus,
    checks: Sequence[HistoricalPoissonPrematchLambdaAdmissionCheck],
) -> list[str]:
    warnings = [
        f"poisson_prematch_lambda_admission:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    warnings.append(f"poisson_prematch_lambda_admission:{status}")
    return warnings


def _boolean_check(
    name: str,
    passed: bool,
    *,
    enabled: bool = True,
    detail: str,
) -> HistoricalPoissonPrematchLambdaAdmissionCheck:
    if not enabled:
        return _skipped_check(name=name, actual=passed, detail=detail)
    return HistoricalPoissonPrematchLambdaAdmissionCheck(
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
) -> HistoricalPoissonPrematchLambdaAdmissionCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalPoissonPrematchLambdaAdmissionCheck(
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
) -> HistoricalPoissonPrematchLambdaAdmissionCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalPoissonPrematchLambdaAdmissionCheck(
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
) -> HistoricalPoissonPrematchLambdaAdmissionCheck:
    return HistoricalPoissonPrematchLambdaAdmissionCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Gate prematch-feature Poisson lambda adjustments before promotion."
    )
    parser.add_argument("source_learning_report", type=Path)
    parser.add_argument("--sample-readiness-report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-learned-competition-count", type=int, default=1)
    parser.add_argument("--min-validation-count", type=int, default=100)
    parser.add_argument("--min-candidate-count", type=int, default=1)
    parser.add_argument("--max-warning-count", type=int, default=0)
    parser.add_argument("--min-ready-fixture-count", type=int, default=100)
    parser.add_argument("--min-ready-competition-count", type=int, default=1)
    parser.add_argument("--min-ready-season-count", type=int, default=1)
    parser.add_argument("--min-ready-competition-season-count", type=int, default=1)
    parser.add_argument("--min-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-average-actual-probability-delta", type=float)
    parser.add_argument("--max-failed-competition-no-harm-count", type=int, default=0)
    parser.add_argument("--min-selected-prematch-signal-weight", type=float, default=0.001)
    parser.add_argument("--min-selected-market-movement-weight", type=float, default=0.01)
    parser.add_argument("--allow-source-status-not-generated", action="store_true")
    parser.add_argument("--allow-missing-sample-readiness-report", action="store_true")
    parser.add_argument("--allow-sample-readiness-shadow-only", action="store_true")
    parser.add_argument("--allow-non-prematch-lambda-method", action="store_true")
    parser.add_argument("--allow-public-prediction-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalPoissonPrematchLambdaAdmissionOptions:
    return HistoricalPoissonPrematchLambdaAdmissionOptions(
        min_learned_competition_count=args.min_learned_competition_count,
        min_validation_count=args.min_validation_count,
        min_candidate_count=args.min_candidate_count,
        max_warning_count=args.max_warning_count,
        min_ready_fixture_count=args.min_ready_fixture_count,
        min_ready_competition_count=args.min_ready_competition_count,
        min_ready_season_count=args.min_ready_season_count,
        min_ready_competition_season_count=args.min_ready_competition_season_count,
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        min_average_actual_probability_delta=(
            args.min_average_actual_probability_delta
        ),
        max_failed_competition_no_harm_count=(
            args.max_failed_competition_no_harm_count
        ),
        min_selected_prematch_signal_weight=(
            args.min_selected_prematch_signal_weight
        ),
        min_selected_market_movement_weight=(
            args.min_selected_market_movement_weight
        ),
        require_source_status_generated=not args.allow_source_status_not_generated,
        require_sample_readiness_report=not args.allow_missing_sample_readiness_report,
        require_sample_ready_allowed=not args.allow_sample_readiness_shadow_only,
        require_prematch_lambda_method=not args.allow_non_prematch_lambda_method,
        require_no_public_prediction_change=not args.allow_public_prediction_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalPoissonPrematchLambdaAdmissionCheck],
    decision_payload: Mapping[str, object],
) -> str:
    payload = {
        "summary": dict(summary),
        "checks": [check.model_dump(mode="json") for check in checks],
        "decision_payload": dict(decision_payload),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_poisson_prematch_lambda_admission:{digest}"


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _mapping_float(
    value: Mapping[str, object],
    key: str,
    *,
    default: float | None = None,
) -> float | None:
    raw_value = value.get(key, default)
    return _optional_float(raw_value)


def _mapping_float_or_none(value: Mapping[str, object], key: str) -> float | None:
    return _mapping_float(value, key)


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


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0
