from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_final_answer_selection_value_signal_runtime_replay import (
    HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport,
)
from nutmeg.recommendations.historical_probability_calibration_profile_model_quality_gate import (
    HistoricalProbabilityCalibrationProfileModelQualityGateReport,
    load_historical_probability_calibration_profile_model_quality_gate_report,
)

type HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionStatus = Literal[
    "accepted",
    "holdout_only",
    "rejected",
]
type HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheckStatus = Literal[
    "passed",
    "failed",
]


class HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions(BaseModel):
    min_rule_count: int = Field(default=1, ge=0)
    min_selected_rule_count: int = Field(default=1, ge=0)
    max_selected_rule_count: int = Field(default=1, ge=1)
    min_final_answer_count: int = Field(default=100, ge=1)
    min_changed_final_answer_count: int = Field(default=1, ge=0)
    min_affected_leg_count: int = Field(default=1, ge=0)
    min_positive_movement_count: int = Field(default=1, ge=0)
    max_harmful_movement_count: int = Field(default=0, ge=0)
    max_probability_quality_harm_movement_count: int = Field(default=0, ge=0)
    min_final_answer_hit_delta_count: int = 0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_candidate_roi: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    require_probability_calibration_model_quality_gate: bool = False
    require_probability_calibration_model_quality_ready: bool = True
    min_probability_calibration_model_quality_selected_competition_count: int = Field(
        default=1,
        ge=0,
    )
    min_probability_calibration_model_quality_adjusted_fixture_count: int = Field(
        default=1,
        ge=0,
    )
    max_probability_calibration_model_quality_final_answer_changed_count: (
        int | None
    ) = Field(default=0, ge=0)
    max_probability_calibration_model_quality_brier_score_delta: float | None = 0.0
    max_probability_calibration_model_quality_log_loss_delta: float | None = 0.0
    max_probability_calibration_model_quality_calibration_error_delta: (
        float | None
    ) = 0.0
    require_runtime_replay_allowed: bool = True
    require_holdout_replay_allowed: bool = True
    require_runtime_replay_passed_status: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck(BaseModel):
    name: str
    status: HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionStatus
    production_recommendation_allowed: bool
    holdout_allowed: bool
    source_runtime_replay_report_key: str
    source_runtime_replay_status: str
    source_rule_profile_version: str
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    affected_leg_count: int = Field(ge=0)
    movement_count: int = Field(ge=0)
    positive_movement_count: int = Field(ge=0)
    harmful_movement_count: int = Field(ge=0)
    probability_quality_harm_movement_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    roi_delta: float | None = None
    profit_loss_delta: float
    candidate_roi: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    final_hit_harm_count_vs_baseline: int = Field(ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(ge=0)
    probability_calibration_model_quality_gate_present: bool = False
    probability_calibration_model_quality_gate_ready: bool | None = None
    probability_calibration_model_quality_gate_report_key: str | None = None
    probability_calibration_model_quality_gate_status: str | None = None
    probability_calibration_model_quality_adjusted_fixture_count: int = Field(
        default=0,
        ge=0,
    )
    probability_calibration_model_quality_final_answer_changed_count: int = Field(
        default=0,
        ge=0,
    )
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck] = (
        Field(default_factory=list)
    )
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_final_answer_selection_value_signal_runtime_replay_report(
    path: Path | str,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport:
    return HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_final_answer_selection_value_signal_runtime_admission_report(
    runtime_replay: HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport,
    *,
    probability_calibration_model_quality_gate: (
        HistoricalProbabilityCalibrationProfileModelQualityGateReport | None
    ) = None,
    options: (
        HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions | None
    ) = None,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionReport:
    resolved_options = (
        options or HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions()
    )
    checks = _checks(
        runtime_replay,
        probability_calibration_model_quality_gate=(
            probability_calibration_model_quality_gate
        ),
        options=resolved_options,
    )
    source_passed = _source_checks_passed(checks)
    no_harm_passed = _no_harm_checks_passed(checks)
    runtime_allowed = all(check.status == "passed" for check in checks)
    holdout_allowed = source_passed and no_harm_passed
    status = _status(
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
    )
    production_allowed = status == "accepted"
    decision_payload = _decision_payload(
        runtime_replay,
        status=status,
        production_allowed=production_allowed,
        holdout_allowed=holdout_allowed,
        options=resolved_options,
    )
    warnings = _warnings(status=status, checks=checks)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_runtime_admission_v3_1"
        ),
        "status": status,
        "production_recommendation_allowed": production_allowed,
        "holdout_allowed": holdout_allowed,
        "source_runtime_replay_report_key": runtime_replay.report_key,
        "source_runtime_replay_status": runtime_replay.status,
        "source_rule_profile_version": runtime_replay.source_rule_profile_version,
        "rule_count": runtime_replay.rule_count,
        "selected_rule_count": runtime_replay.selected_rule_count,
        "final_answer_count": runtime_replay.final_answer_count,
        "changed_final_answer_count": runtime_replay.changed_final_answer_count,
        "affected_leg_count": runtime_replay.affected_leg_count,
        "movement_count": runtime_replay.movement_count,
        "positive_movement_count": runtime_replay.positive_movement_count,
        "harmful_movement_count": runtime_replay.harmful_movement_count,
        "probability_quality_harm_movement_count": (
            runtime_replay.probability_quality_harm_movement_count
        ),
        "final_answer_hit_delta_count": runtime_replay.final_answer_hit_delta_count,
        "roi_delta": runtime_replay.roi_delta,
        "profit_loss_delta": runtime_replay.profit_loss_delta,
        "candidate_roi": runtime_replay.candidate_roi,
        "brier_score_delta": runtime_replay.brier_score_delta,
        "log_loss_delta": runtime_replay.log_loss_delta,
        "mean_calibration_error_delta": runtime_replay.mean_calibration_error_delta,
        "final_hit_harm_count_vs_baseline": (
            runtime_replay.final_hit_harm_count_vs_baseline
        ),
        "profit_loss_harm_count_vs_baseline": (
            runtime_replay.profit_loss_harm_count_vs_baseline
        ),
        **_model_quality_summary_fields(probability_calibration_model_quality_gate),
        "production_recommendation_changed": (
            runtime_replay.production_recommendation_changed
        ),
        "public_response_changed": runtime_replay.public_response_changed,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decision_payload)
    return HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionReport(
        report_key=report_key,
        status=status,
        production_recommendation_allowed=production_allowed,
        holdout_allowed=holdout_allowed,
        source_runtime_replay_report_key=runtime_replay.report_key,
        source_runtime_replay_status=runtime_replay.status,
        source_rule_profile_version=runtime_replay.source_rule_profile_version,
        rule_count=runtime_replay.rule_count,
        selected_rule_count=runtime_replay.selected_rule_count,
        final_answer_count=runtime_replay.final_answer_count,
        changed_final_answer_count=runtime_replay.changed_final_answer_count,
        affected_leg_count=runtime_replay.affected_leg_count,
        movement_count=runtime_replay.movement_count,
        positive_movement_count=runtime_replay.positive_movement_count,
        harmful_movement_count=runtime_replay.harmful_movement_count,
        probability_quality_harm_movement_count=(
            runtime_replay.probability_quality_harm_movement_count
        ),
        final_answer_hit_delta_count=runtime_replay.final_answer_hit_delta_count,
        roi_delta=runtime_replay.roi_delta,
        profit_loss_delta=runtime_replay.profit_loss_delta,
        candidate_roi=runtime_replay.candidate_roi,
        brier_score_delta=runtime_replay.brier_score_delta,
        log_loss_delta=runtime_replay.log_loss_delta,
        mean_calibration_error_delta=runtime_replay.mean_calibration_error_delta,
        final_hit_harm_count_vs_baseline=(
            runtime_replay.final_hit_harm_count_vs_baseline
        ),
        profit_loss_harm_count_vs_baseline=(
            runtime_replay.profit_loss_harm_count_vs_baseline
        ),
        probability_calibration_model_quality_gate_present=(
            probability_calibration_model_quality_gate is not None
        ),
        probability_calibration_model_quality_gate_ready=(
            probability_calibration_model_quality_gate.model_quality_gate_passed
            if probability_calibration_model_quality_gate is not None
            else None
        ),
        probability_calibration_model_quality_gate_report_key=(
            probability_calibration_model_quality_gate.report_key
            if probability_calibration_model_quality_gate is not None
            else None
        ),
        probability_calibration_model_quality_gate_status=(
            probability_calibration_model_quality_gate.status
            if probability_calibration_model_quality_gate is not None
            else None
        ),
        probability_calibration_model_quality_adjusted_fixture_count=(
            probability_calibration_model_quality_gate.adjusted_fixture_count
            if probability_calibration_model_quality_gate is not None
            else 0
        ),
        probability_calibration_model_quality_final_answer_changed_count=(
            probability_calibration_model_quality_gate.final_answer_changed_count
            if probability_calibration_model_quality_gate is not None
            else 0
        ),
        production_recommendation_changed=(
            runtime_replay.production_recommendation_changed
        ),
        public_response_changed=runtime_replay.public_response_changed,
        checks=checks,
        decision_payload_json=decision_payload,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_final_answer_selection_value_signal_runtime_admission_report(
        load_historical_final_answer_selection_value_signal_runtime_replay_report(
            args.runtime_replay_report
        ),
        probability_calibration_model_quality_gate=(
            load_historical_probability_calibration_profile_model_quality_gate_report(
                args.probability_calibration_model_quality_gate_report
            )
            if args.probability_calibration_model_quality_gate_report is not None
            else None
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
    if not report.production_recommendation_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    runtime_replay: HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport,
    *,
    probability_calibration_model_quality_gate: (
        HistoricalProbabilityCalibrationProfileModelQualityGateReport | None
    ),
    options: HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions,
) -> list[HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck]:
    return [
        _boolean_check(
            "runtime_replay_allowed",
            runtime_replay.runtime_replay_allowed,
            enabled=options.require_runtime_replay_allowed,
            detail="runtime replay should be runtime-allowed",
        ),
        _boolean_check(
            "holdout_replay_allowed",
            runtime_replay.holdout_replay_allowed,
            enabled=options.require_holdout_replay_allowed,
            detail="runtime replay should be holdout-allowed",
        ),
        _boolean_check(
            "runtime_replay_passed_status",
            runtime_replay.status == "runtime_replay_passed",
            enabled=options.require_runtime_replay_passed_status,
            detail="runtime replay status should be passed",
        ),
        _minimum_check(
            "rule_count",
            runtime_replay.rule_count,
            options.min_rule_count,
            detail="runtime replay should load enough rules",
        ),
        _minimum_check(
            "selected_rule_count",
            runtime_replay.selected_rule_count,
            options.min_selected_rule_count,
            detail="runtime replay should select enough rules",
        ),
        _maximum_check(
            "selected_rule_count_max",
            runtime_replay.selected_rule_count,
            options.max_selected_rule_count,
            detail="runtime replay should stay within rule limits",
        ),
        _minimum_check(
            "final_answer_count",
            runtime_replay.final_answer_count,
            options.min_final_answer_count,
            detail="runtime replay should cover enough final answers",
        ),
        _minimum_check(
            "changed_final_answer_count",
            runtime_replay.changed_final_answer_count,
            options.min_changed_final_answer_count,
            detail="runtime replay should change enough final answers",
        ),
        _minimum_check(
            "affected_leg_count",
            runtime_replay.affected_leg_count,
            options.min_affected_leg_count,
            detail="runtime replay should exercise the signal",
        ),
        _minimum_check(
            "positive_movement_count",
            runtime_replay.positive_movement_count,
            options.min_positive_movement_count,
            detail="runtime replay should preserve positive movements",
        ),
        _maximum_check(
            "harmful_movement_count",
            runtime_replay.harmful_movement_count,
            options.max_harmful_movement_count,
            detail="runtime replay must not introduce harmful movements",
        ),
        _maximum_check(
            "probability_quality_harm_movement_count",
            runtime_replay.probability_quality_harm_movement_count,
            options.max_probability_quality_harm_movement_count,
            detail="runtime replay movements should not regress probability quality",
        ),
        _minimum_check(
            "final_answer_hit_delta_count",
            runtime_replay.final_answer_hit_delta_count,
            options.min_final_answer_hit_delta_count,
            detail="runtime replay final-answer hits should not regress",
        ),
        _minimum_check(
            "roi_delta",
            runtime_replay.roi_delta,
            options.min_roi_delta,
            detail="runtime replay ROI should not regress",
        ),
        _minimum_check(
            "profit_loss_delta",
            runtime_replay.profit_loss_delta,
            options.min_profit_loss_delta,
            detail="runtime replay profit/loss should not regress",
        ),
        _minimum_check(
            "candidate_roi",
            runtime_replay.candidate_roi,
            options.min_candidate_roi,
            detail="runtime admission requires non-negative absolute candidate ROI",
        ),
        _maximum_check(
            "brier_score_delta",
            runtime_replay.brier_score_delta,
            options.max_brier_score_delta,
            detail="runtime replay Brier score should not regress",
        ),
        _maximum_check(
            "log_loss_delta",
            runtime_replay.log_loss_delta,
            options.max_log_loss_delta,
            detail="runtime replay log loss should not regress",
        ),
        _maximum_check(
            "mean_calibration_error_delta",
            runtime_replay.mean_calibration_error_delta,
            options.max_mean_calibration_error_delta,
            detail="runtime replay calibration error should not regress",
        ),
        _maximum_check(
            "final_hit_harm_count_vs_baseline",
            runtime_replay.final_hit_harm_count_vs_baseline,
            options.max_final_hit_harm_count_vs_baseline,
            detail="runtime replay should not harm final-answer hits",
        ),
        _maximum_check(
            "profit_loss_harm_count_vs_baseline",
            runtime_replay.profit_loss_harm_count_vs_baseline,
            options.max_profit_loss_harm_count_vs_baseline,
            detail="runtime replay should not harm final-answer profit/loss",
        ),
        _boolean_check(
            "production_recommendation_unchanged",
            not runtime_replay.production_recommendation_changed,
            enabled=options.require_no_production_change,
            detail="runtime replay must not change production recommendations",
        ),
        _boolean_check(
            "public_response_unchanged",
            not runtime_replay.public_response_changed,
            enabled=options.require_no_public_response_change,
            detail="runtime replay must not change public response",
        ),
        *_model_quality_checks(
            probability_calibration_model_quality_gate,
            options=options,
        ),
    ]


def _model_quality_checks(
    model_quality_gate: HistoricalProbabilityCalibrationProfileModelQualityGateReport
    | None,
    *,
    options: HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions,
) -> list[HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck]:
    checks = [
        _boolean_check(
            "probability_calibration_model_quality_gate_present",
            model_quality_gate is not None,
            enabled=options.require_probability_calibration_model_quality_gate,
            detail=(
                "selection-value runtime admission should be guarded by "
                "probability model-quality evidence when required"
            ),
        )
    ]
    if model_quality_gate is None:
        return checks
    checks.extend(
        [
            _boolean_check(
                "probability_calibration_model_quality_gate_ready",
                model_quality_gate.model_quality_gate_passed
                and model_quality_gate.status == "model_quality_ready",
                enabled=(
                    options.require_probability_calibration_model_quality_gate
                    and options.require_probability_calibration_model_quality_ready
                ),
                detail=(
                    "probability model-quality evidence should be ready before "
                    "selection-value runtime admission can pass"
                ),
            ),
            _minimum_check(
                "probability_calibration_model_quality_selected_competition_count",
                len(model_quality_gate.selected_competition_ids),
                options.min_probability_calibration_model_quality_selected_competition_count,
                detail=(
                    "probability model-quality evidence should cover enough "
                    "selected competitions"
                ),
            ),
            _minimum_check(
                "probability_calibration_model_quality_adjusted_fixture_count",
                model_quality_gate.adjusted_fixture_count,
                options.min_probability_calibration_model_quality_adjusted_fixture_count,
                detail=(
                    "probability model-quality evidence should adjust enough fixtures"
                ),
            ),
            _optional_maximum_check(
                "probability_calibration_model_quality_final_answer_changed_count",
                model_quality_gate.final_answer_changed_count,
                options.max_probability_calibration_model_quality_final_answer_changed_count,
                detail=(
                    "model-quality evidence should not be confused with final-answer "
                    "activation"
                ),
            ),
            _optional_maximum_check(
                "probability_calibration_model_quality_brier_score_delta",
                model_quality_gate.brier_score_delta,
                options.max_probability_calibration_model_quality_brier_score_delta,
                detail="probability model-quality Brier score should not regress",
            ),
            _optional_maximum_check(
                "probability_calibration_model_quality_log_loss_delta",
                model_quality_gate.log_loss_delta,
                options.max_probability_calibration_model_quality_log_loss_delta,
                detail="probability model-quality log loss should not regress",
            ),
            _optional_maximum_check(
                "probability_calibration_model_quality_calibration_error_delta",
                model_quality_gate.mean_calibration_error_delta,
                options.max_probability_calibration_model_quality_calibration_error_delta,
                detail=(
                    "probability model-quality calibration error should not regress"
                ),
            ),
        ]
    )
    return checks


def _decision_payload(
    runtime_replay: HistoricalFinalAnswerSelectionValueSignalRuntimeReplayReport,
    *,
    status: HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionStatus,
    production_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_runtime_admission_decision_v3_1"
        ),
        "status": status,
        "production_recommendation_allowed": production_allowed,
        "holdout_allowed": holdout_allowed,
        "default_recommendation_path_changed": False,
        "source_runtime_replay_report_key": runtime_replay.report_key,
        "source_rule_profile_version": runtime_replay.source_rule_profile_version,
        "candidate_roi": runtime_replay.candidate_roi,
        "minimum_candidate_roi": options.min_candidate_roi,
        "requires_probability_calibration_model_quality_gate": (
            options.require_probability_calibration_model_quality_gate
        ),
        "rollback_conditions": [
            "disable_if_runtime_replay_missing_or_failed",
            "disable_if_probability_model_quality_gate_missing_or_failed",
            "disable_if_absolute_candidate_roi_below_floor",
            "disable_if_final_hit_harm_count_above_0",
            "disable_if_profit_loss_harm_count_above_0",
            "disable_if_probability_quality_regresses",
            "disable_if_harmful_movement_count_above_0",
        ],
        "notes": [
            "Admission is a governance decision only; it does not modify defaults.",
            "Negative absolute candidate ROI keeps the rule in holdout.",
        ],
    }


def _status(
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionStatus:
    if runtime_allowed:
        return "accepted"
    if holdout_allowed:
        return "holdout_only"
    return "rejected"


def _source_checks_passed(
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck],
) -> bool:
    source_names = {
        "runtime_replay_allowed",
        "holdout_replay_allowed",
        "runtime_replay_passed_status",
        "probability_calibration_model_quality_gate_present",
        "probability_calibration_model_quality_gate_ready",
        "probability_calibration_model_quality_selected_competition_count",
        "probability_calibration_model_quality_adjusted_fixture_count",
        "rule_count",
        "selected_rule_count",
        "selected_rule_count_max",
        "production_recommendation_unchanged",
        "public_response_unchanged",
    }
    return all(check.status == "passed" for check in checks if check.name in source_names)


def _no_harm_checks_passed(
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck],
) -> bool:
    ignored_for_holdout = {"candidate_roi"}
    return all(
        check.status == "passed"
        for check in checks
        if check.name not in ignored_for_holdout
    )


def _warnings(
    *,
    status: HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionStatus,
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck],
) -> list[str]:
    warnings = [
        f"selection_value_signal_runtime_admission:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    if status == "accepted":
        warnings.append("selection_value_signal_runtime_admission:accepted")
    elif status == "holdout_only":
        warnings.append("selection_value_signal_runtime_admission:holdout_only")
    else:
        warnings.append("selection_value_signal_runtime_admission:rejected")
    return warnings


def _boolean_check(
    name: str,
    passed: bool,
    *,
    enabled: bool = True,
    detail: str,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck:
    return HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck(
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
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck:
    return HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck(
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
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck:
    return HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck(
        name=name,
        status="passed" if actual is not None and actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_maximum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    *,
    detail: str,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck:
    if threshold is None:
        return HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=None,
            detail=detail,
        )
    return _maximum_check(name, actual, threshold, detail=detail)


def _model_quality_summary_fields(
    model_quality_gate: HistoricalProbabilityCalibrationProfileModelQualityGateReport
    | None,
) -> dict[str, object]:
    if model_quality_gate is None:
        return {
            "probability_calibration_model_quality_gate_present": False,
            "probability_calibration_model_quality_gate_ready": None,
            "probability_calibration_model_quality_gate_report_key": None,
            "probability_calibration_model_quality_gate_status": None,
            "probability_calibration_model_quality_selected_competition_count": 0,
            "probability_calibration_model_quality_adjusted_fixture_count": 0,
            "probability_calibration_model_quality_final_answer_changed_count": 0,
            "probability_calibration_model_quality_brier_score_delta": None,
            "probability_calibration_model_quality_log_loss_delta": None,
            "probability_calibration_model_quality_mean_calibration_error_delta": None,
        }
    return {
        "probability_calibration_model_quality_gate_present": True,
        "probability_calibration_model_quality_gate_ready": (
            model_quality_gate.model_quality_gate_passed
        ),
        "probability_calibration_model_quality_gate_report_key": (
            model_quality_gate.report_key
        ),
        "probability_calibration_model_quality_gate_status": model_quality_gate.status,
        "probability_calibration_model_quality_selected_competition_count": len(
            model_quality_gate.selected_competition_ids
        ),
        "probability_calibration_model_quality_adjusted_fixture_count": (
            model_quality_gate.adjusted_fixture_count
        ),
        "probability_calibration_model_quality_final_answer_changed_count": (
            model_quality_gate.final_answer_changed_count
        ),
        "probability_calibration_model_quality_brier_score_delta": (
            model_quality_gate.brier_score_delta
        ),
        "probability_calibration_model_quality_log_loss_delta": (
            model_quality_gate.log_loss_delta
        ),
        "probability_calibration_model_quality_mean_calibration_error_delta": (
            model_quality_gate.mean_calibration_error_delta
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Create a runtime admission decision for selection-value replay."
    )
    parser.add_argument("runtime_replay_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-rule-count", type=int, default=1)
    parser.add_argument("--min-selected-rule-count", type=int, default=1)
    parser.add_argument("--max-selected-rule-count", type=int, default=1)
    parser.add_argument("--min-final-answer-count", type=int, default=100)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-affected-leg-count", type=int, default=1)
    parser.add_argument("--min-positive-movement-count", type=int, default=1)
    parser.add_argument("--max-harmful-movement-count", type=int, default=0)
    parser.add_argument(
        "--max-probability-quality-harm-movement-count",
        type=int,
        default=0,
    )
    parser.add_argument("--min-final-answer-hit-delta-count", type=int, default=0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--max-profit-loss-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument(
        "--probability-calibration-model-quality-gate-report",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--require-probability-calibration-model-quality-gate",
        action="store_true",
    )
    parser.add_argument(
        "--allow-probability-calibration-model-quality-not-ready",
        action="store_true",
    )
    parser.add_argument(
        "--min-probability-calibration-model-quality-selected-competition-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-probability-calibration-model-quality-adjusted-fixture-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-probability-calibration-model-quality-final-answer-changed-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-probability-calibration-model-quality-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-probability-calibration-model-quality-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-probability-calibration-model-quality-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--allow-runtime-replay-not-allowed", action="store_true")
    parser.add_argument("--allow-holdout-replay-not-allowed", action="store_true")
    parser.add_argument("--allow-runtime-replay-non-passed-status", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions:
    return HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionOptions(
        min_rule_count=args.min_rule_count,
        min_selected_rule_count=args.min_selected_rule_count,
        max_selected_rule_count=args.max_selected_rule_count,
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_affected_leg_count=args.min_affected_leg_count,
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
        require_probability_calibration_model_quality_gate=(
            args.require_probability_calibration_model_quality_gate
        ),
        require_probability_calibration_model_quality_ready=(
            not args.allow_probability_calibration_model_quality_not_ready
        ),
        min_probability_calibration_model_quality_selected_competition_count=(
            args.min_probability_calibration_model_quality_selected_competition_count
        ),
        min_probability_calibration_model_quality_adjusted_fixture_count=(
            args.min_probability_calibration_model_quality_adjusted_fixture_count
        ),
        max_probability_calibration_model_quality_final_answer_changed_count=(
            args.max_probability_calibration_model_quality_final_answer_changed_count
        ),
        max_probability_calibration_model_quality_brier_score_delta=(
            args.max_probability_calibration_model_quality_brier_score_delta
        ),
        max_probability_calibration_model_quality_log_loss_delta=(
            args.max_probability_calibration_model_quality_log_loss_delta
        ),
        max_probability_calibration_model_quality_calibration_error_delta=(
            args.max_probability_calibration_model_quality_calibration_error_delta
        ),
        require_runtime_replay_allowed=not args.allow_runtime_replay_not_allowed,
        require_holdout_replay_allowed=not args.allow_holdout_replay_not_allowed,
        require_runtime_replay_passed_status=(
            not args.allow_runtime_replay_non_passed_status
        ),
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalFinalAnswerSelectionValueSignalRuntimeAdmissionCheck],
    decision_payload: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "decision_payload": decision_payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_selection_value_signal_runtime_admission:{digest}"


if __name__ == "__main__":
    main()
