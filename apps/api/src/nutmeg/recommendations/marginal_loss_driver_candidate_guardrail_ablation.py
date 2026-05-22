from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    _final_answer_signature,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalMarginalLossDriverCandidateGuardrailAblationDecision = Literal[
    "accepted",
    "rejected",
]


class HistoricalMarginalLossDriverCandidateGuardrailAblationOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    optimizer_profile: HistoricalOptimizerProfile = "solver"
    competition_ids: tuple[str, ...] = ("JPN_J1",)
    probability_min: float = Field(default=0.65, ge=0.0, le=1.0)
    probability_max: float = Field(default=0.80, ge=0.0, le=1.0)
    max_decimal_odds: float = Field(default=1.50, gt=1.0)
    max_model_edge: float = -0.02
    max_calibration_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_model_confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_odds_stability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    min_excluded_candidate_count: int = Field(default=1, ge=0)
    min_final_hit_count_delta: int = 0
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_baseline: int | None = Field(default=None, ge=0)
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    min_upset_capture_rate_delta: float = 0.0
    require_objective_improvement: bool = True
    min_objective_final_hit_rate_delta: float = 0.0
    min_objective_roi_delta: float = 0.0
    comparison_epsilon: float = Field(default=1e-12, ge=0.0)


class HistoricalMarginalLossDriverCandidateGuardrailAblationItem(BaseModel):
    slice_id: str
    competition_id: str
    baseline_backtest_key: str
    candidate_backtest_key: str
    baseline_final_answer_scenario_key: str | None = None
    candidate_final_answer_scenario_key: str | None = None
    final_answer_changed: bool
    excluded_candidate_count: int = Field(ge=0)
    baseline_final_hit_count: int = Field(ge=0)
    candidate_final_hit_count: int = Field(ge=0)
    final_hit_harmed_vs_baseline: bool = False
    baseline_profit_loss: float
    candidate_profit_loss: float
    profit_loss_harmed_vs_baseline: bool = False
    deltas_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarginalLossDriverCandidateGuardrailAblationReport(BaseModel):
    report_key: str
    status: Literal["generated"]
    decision: HistoricalMarginalLossDriverCandidateGuardrailAblationDecision
    reason_codes: list[str] = Field(default_factory=list)
    objective_improvement_metric_codes: list[str] = Field(default_factory=list)
    slice_count: int = Field(ge=0)
    final_answer_changed_count: int = Field(ge=0)
    excluded_candidate_count: int = Field(ge=0)
    baseline_final_hit_sample_size: int = Field(ge=0)
    candidate_final_hit_sample_size: int = Field(ge=0)
    baseline_final_hit_count: int = Field(ge=0)
    candidate_final_hit_count: int = Field(ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    baseline_final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_roi: float | None = None
    candidate_roi: float | None = None
    baseline_profit_loss: float
    candidate_profit_loss: float
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    deltas_json: dict[str, object] = Field(default_factory=dict)
    items: list[HistoricalMarginalLossDriverCandidateGuardrailAblationItem] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    manifest_results: list[HistoricalRecommendationSuiteManifestLoadResult] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)


def build_historical_marginal_loss_driver_candidate_guardrail_ablation_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: (
        HistoricalMarginalLossDriverCandidateGuardrailAblationOptions | None
    ) = None,
) -> HistoricalMarginalLossDriverCandidateGuardrailAblationReport:
    resolved_options = (
        options or HistoricalMarginalLossDriverCandidateGuardrailAblationOptions()
    )
    baseline_options = _baseline_backtest_options(resolved_options)
    candidate_options = _candidate_backtest_options(resolved_options)
    items: list[HistoricalMarginalLossDriverCandidateGuardrailAblationItem] = []
    baseline_results: list[HistoricalRecommendationBacktestResult] = []
    candidate_results: list[HistoricalRecommendationBacktestResult] = []
    warnings: list[str] = []

    for historical_slice in historical_slices:
        baseline = run_historical_recommendation_backtest(
            historical_slice,
            options=baseline_options,
        )
        candidate = run_historical_recommendation_backtest(
            historical_slice,
            options=candidate_options,
        )
        baseline_results.append(baseline)
        candidate_results.append(candidate)
        warnings.extend(baseline.warnings)
        warnings.extend(candidate.warnings)
        items.append(_ablation_item(historical_slice, baseline, candidate))

    deltas = _aggregate_deltas(baseline_results, candidate_results)
    objective_metric_codes = _objective_improvement_metric_codes(
        deltas,
        options=resolved_options,
    )
    objective_improvement_satisfied = (
        not resolved_options.require_objective_improvement
        or bool(objective_metric_codes)
    )
    reason_codes = _reason_codes(
        deltas,
        objective_improvement_satisfied=objective_improvement_satisfied,
        options=resolved_options,
    )
    decision: HistoricalMarginalLossDriverCandidateGuardrailAblationDecision = (
        "accepted" if not reason_codes else "rejected"
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_marginal_loss_driver_candidate_guardrail_ablation_v3_1"
        ),
        "decision": decision,
        "slice_count": len(historical_slices),
        "optimizer_profile": resolved_options.optimizer_profile,
        "competition_ids": list(resolved_options.competition_ids),
        "probability_min": resolved_options.probability_min,
        "probability_max": resolved_options.probability_max,
        "max_decimal_odds": resolved_options.max_decimal_odds,
        "max_model_edge": resolved_options.max_model_edge,
        "max_calibration_score": resolved_options.max_calibration_score,
        "max_model_confidence_score": resolved_options.max_model_confidence_score,
        "max_odds_stability_score": resolved_options.max_odds_stability_score,
        "max_final_hit_harm_count_vs_baseline": (
            resolved_options.max_final_hit_harm_count_vs_baseline
        ),
        "max_profit_loss_harm_count_vs_baseline": (
            resolved_options.max_profit_loss_harm_count_vs_baseline
        ),
        "objective_improvement_satisfied": objective_improvement_satisfied,
        "objective_improvement_metric_codes": objective_metric_codes,
        "reason_codes": reason_codes,
        "deltas": deltas,
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    return HistoricalMarginalLossDriverCandidateGuardrailAblationReport(
        report_key=report_key,
        status="generated",
        decision=decision,
        reason_codes=reason_codes,
        objective_improvement_metric_codes=objective_metric_codes,
        slice_count=len(historical_slices),
        final_answer_changed_count=sum(1 for item in items if item.final_answer_changed),
        excluded_candidate_count=_int_delta(deltas, "excluded_candidate_count"),
        baseline_final_hit_sample_size=_int_delta(
            deltas,
            "baseline_final_hit_sample_size",
        ),
        candidate_final_hit_sample_size=_int_delta(
            deltas,
            "candidate_final_hit_sample_size",
        ),
        baseline_final_hit_count=_int_delta(deltas, "baseline_final_hit_count"),
        candidate_final_hit_count=_int_delta(deltas, "candidate_final_hit_count"),
        final_hit_harm_count_vs_baseline=_int_delta(
            deltas,
            "final_hit_harm_count_vs_baseline",
        ),
        baseline_final_hit_rate=_number(deltas, "baseline_final_hit_rate"),
        candidate_final_hit_rate=_number(deltas, "candidate_final_hit_rate"),
        baseline_roi=_number(deltas, "baseline_roi"),
        candidate_roi=_number(deltas, "candidate_roi"),
        baseline_profit_loss=_number(deltas, "baseline_profit_loss") or 0.0,
        candidate_profit_loss=_number(deltas, "candidate_profit_loss") or 0.0,
        profit_loss_harm_count_vs_baseline=_int_delta(
            deltas,
            "profit_loss_harm_count_vs_baseline",
        ),
        deltas_json=deltas,
        items=items,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_marginal_loss_driver_candidate_guardrail_ablation_report(
    path: Path | str,
) -> HistoricalMarginalLossDriverCandidateGuardrailAblationReport:
    return (
        HistoricalMarginalLossDriverCandidateGuardrailAblationReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded = _historical_slices_from_args(args)
    report = build_historical_marginal_loss_driver_candidate_guardrail_ablation_report(
        loaded.slices,
        options=_options_from_args(args),
    )
    if loaded.manifest_results:
        manifest_summaries = [
            _manifest_summary(manifest_result)
            for manifest_result in loaded.manifest_results
        ]
        report.summary_json["suite_manifests"] = manifest_summaries
        if len(manifest_summaries) == 1:
            report.summary_json["suite_manifest"] = manifest_summaries[0]
    if loaded.warnings:
        report.warnings.extend(loaded.warnings)
        report.summary_json["manifest_warnings"] = loaded.warnings
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


def _baseline_backtest_options(
    options: HistoricalMarginalLossDriverCandidateGuardrailAblationOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.backtest_options.model_copy(
        update={
            "optimizer_profile": options.optimizer_profile,
            "marginal_loss_driver_candidate_guardrail": False,
        }
    )


def _candidate_backtest_options(
    options: HistoricalMarginalLossDriverCandidateGuardrailAblationOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.backtest_options.model_copy(
        update={
            "optimizer_profile": options.optimizer_profile,
            "marginal_loss_driver_candidate_guardrail": True,
            "marginal_loss_driver_candidate_guardrail_probability_min": (
                options.probability_min
            ),
            "marginal_loss_driver_candidate_guardrail_probability_max": (
                options.probability_max
            ),
            "marginal_loss_driver_candidate_guardrail_max_decimal_odds": (
                options.max_decimal_odds
            ),
            "marginal_loss_driver_candidate_guardrail_max_model_edge": (
                options.max_model_edge
            ),
            "marginal_loss_driver_candidate_guardrail_max_calibration_score": (
                options.max_calibration_score
            ),
            "marginal_loss_driver_candidate_guardrail_max_model_confidence_score": (
                options.max_model_confidence_score
            ),
            "marginal_loss_driver_candidate_guardrail_max_odds_stability_score": (
                options.max_odds_stability_score
            ),
            "marginal_loss_driver_candidate_guardrail_competition_ids": (
                options.competition_ids
            ),
        }
    )


def _ablation_item(
    historical_slice: HistoricalRecommendationSlice,
    baseline: HistoricalRecommendationBacktestResult,
    candidate: HistoricalRecommendationBacktestResult,
) -> HistoricalMarginalLossDriverCandidateGuardrailAblationItem:
    deltas = _result_deltas(baseline, candidate)
    excluded_count = _summary_int(
        candidate.summary_json,
        "marginal_loss_driver_candidate_guardrail_excluded_candidate_count",
    )
    return HistoricalMarginalLossDriverCandidateGuardrailAblationItem(
        slice_id=historical_slice.metadata.slice_id,
        competition_id=historical_slice.metadata.competition_id,
        baseline_backtest_key=baseline.backtest_key,
        candidate_backtest_key=candidate.backtest_key,
        baseline_final_answer_scenario_key=(
            baseline.final_answer.scenario.scenario_key
            if baseline.final_answer is not None
            else None
        ),
        candidate_final_answer_scenario_key=(
            candidate.final_answer.scenario.scenario_key
            if candidate.final_answer is not None
            else None
        ),
        final_answer_changed=(
            _final_answer_signature(baseline.final_answer)
            != _final_answer_signature(candidate.final_answer)
        ),
        excluded_candidate_count=excluded_count,
        baseline_final_hit_count=baseline.final_hit_count,
        candidate_final_hit_count=candidate.final_hit_count,
        final_hit_harmed_vs_baseline=(
            candidate.final_hit_count < baseline.final_hit_count
        ),
        baseline_profit_loss=baseline.profit_loss,
        candidate_profit_loss=candidate.profit_loss,
        profit_loss_harmed_vs_baseline=(
            candidate.profit_loss < baseline.profit_loss
        ),
        deltas_json=deltas,
        summary_json={
            "baseline_final_hit_rate": baseline.final_hit_rate,
            "candidate_final_hit_rate": candidate.final_hit_rate,
            "baseline_roi": baseline.roi,
            "candidate_roi": candidate.roi,
            "excluded_candidate_count": excluded_count,
        },
    )


def _aggregate_deltas(
    baseline_results: Sequence[HistoricalRecommendationBacktestResult],
    candidate_results: Sequence[HistoricalRecommendationBacktestResult],
) -> dict[str, object]:
    baseline_stake = sum(result.total_stake for result in baseline_results)
    candidate_stake = sum(result.total_stake for result in candidate_results)
    baseline_profit_loss = sum(result.profit_loss for result in baseline_results)
    candidate_profit_loss = sum(result.profit_loss for result in candidate_results)
    baseline_final_hit_sample_size = sum(
        result.final_hit_sample_size for result in baseline_results
    )
    candidate_final_hit_sample_size = sum(
        result.final_hit_sample_size for result in candidate_results
    )
    baseline_final_hit_count = sum(result.final_hit_count for result in baseline_results)
    candidate_final_hit_count = sum(result.final_hit_count for result in candidate_results)
    baseline_upset_opportunities = sum(
        result.upset_opportunity_count for result in baseline_results
    )
    candidate_upset_opportunities = sum(
        result.upset_opportunity_count for result in candidate_results
    )
    baseline_upset_captures = sum(result.upset_capture_count for result in baseline_results)
    candidate_upset_captures = sum(result.upset_capture_count for result in candidate_results)
    baseline_final_hit_rate = _ratio(
        baseline_final_hit_count,
        baseline_final_hit_sample_size,
    )
    candidate_final_hit_rate = _ratio(
        candidate_final_hit_count,
        candidate_final_hit_sample_size,
    )
    baseline_roi = _float_ratio(baseline_profit_loss, baseline_stake)
    candidate_roi = _float_ratio(candidate_profit_loss, candidate_stake)
    baseline_upset_capture_rate = _ratio(
        baseline_upset_captures,
        baseline_upset_opportunities,
    )
    candidate_upset_capture_rate = _ratio(
        candidate_upset_captures,
        candidate_upset_opportunities,
    )
    return {
        "excluded_candidate_count": sum(
            _summary_int(
                result.summary_json,
                "marginal_loss_driver_candidate_guardrail_excluded_candidate_count",
            )
            for result in candidate_results
        ),
        "baseline_final_hit_sample_size": baseline_final_hit_sample_size,
        "candidate_final_hit_sample_size": candidate_final_hit_sample_size,
        "baseline_final_hit_count": baseline_final_hit_count,
        "candidate_final_hit_count": candidate_final_hit_count,
        "final_hit_count_delta": candidate_final_hit_count - baseline_final_hit_count,
        "final_hit_harm_count_vs_baseline": sum(
            1
            for baseline, candidate in zip(
                baseline_results,
                candidate_results,
                strict=True,
            )
            if candidate.final_hit_count < baseline.final_hit_count
        ),
        "baseline_final_hit_rate": baseline_final_hit_rate,
        "candidate_final_hit_rate": candidate_final_hit_rate,
        "final_hit_rate_delta": _optional_delta(
            candidate_final_hit_rate,
            baseline_final_hit_rate,
        ),
        "baseline_roi": baseline_roi,
        "candidate_roi": candidate_roi,
        "roi_delta": _optional_delta(candidate_roi, baseline_roi),
        "baseline_profit_loss": baseline_profit_loss,
        "candidate_profit_loss": candidate_profit_loss,
        "profit_loss_delta": candidate_profit_loss - baseline_profit_loss,
        "profit_loss_harm_count_vs_baseline": sum(
            1
            for baseline, candidate in zip(
                baseline_results,
                candidate_results,
                strict=True,
            )
            if candidate.profit_loss < baseline.profit_loss
        ),
        "baseline_brier_score": _average(result.brier_score for result in baseline_results),
        "candidate_brier_score": _average(result.brier_score for result in candidate_results),
        "brier_score_delta": _optional_delta(
            _average(result.brier_score for result in candidate_results),
            _average(result.brier_score for result in baseline_results),
        ),
        "baseline_log_loss": _average(result.log_loss for result in baseline_results),
        "candidate_log_loss": _average(result.log_loss for result in candidate_results),
        "log_loss_delta": _optional_delta(
            _average(result.log_loss for result in candidate_results),
            _average(result.log_loss for result in baseline_results),
        ),
        "baseline_mean_calibration_error": _average(
            result.mean_calibration_error for result in baseline_results
        ),
        "candidate_mean_calibration_error": _average(
            result.mean_calibration_error for result in candidate_results
        ),
        "mean_calibration_error_delta": _optional_delta(
            _average(result.mean_calibration_error for result in candidate_results),
            _average(result.mean_calibration_error for result in baseline_results),
        ),
        "baseline_upset_capture_rate": baseline_upset_capture_rate,
        "candidate_upset_capture_rate": candidate_upset_capture_rate,
        "upset_capture_rate_delta": _optional_delta(
            candidate_upset_capture_rate,
            baseline_upset_capture_rate,
        ),
    }


def _result_deltas(
    baseline: HistoricalRecommendationBacktestResult,
    candidate: HistoricalRecommendationBacktestResult,
) -> dict[str, object]:
    return {
        "final_hit_count_delta": candidate.final_hit_count - baseline.final_hit_count,
        "final_hit_rate_delta": _optional_delta(
            candidate.final_hit_rate,
            baseline.final_hit_rate,
        ),
        "roi_delta": _optional_delta(candidate.roi, baseline.roi),
        "profit_loss_delta": candidate.profit_loss - baseline.profit_loss,
        "brier_score_delta": _optional_delta(candidate.brier_score, baseline.brier_score),
        "log_loss_delta": _optional_delta(candidate.log_loss, baseline.log_loss),
        "mean_calibration_error_delta": _optional_delta(
            candidate.mean_calibration_error,
            baseline.mean_calibration_error,
        ),
        "upset_capture_rate_delta": _optional_delta(
            candidate.upset_capture_rate,
            baseline.upset_capture_rate,
        ),
    }


def _reason_codes(
    deltas: Mapping[str, object],
    *,
    objective_improvement_satisfied: bool,
    options: HistoricalMarginalLossDriverCandidateGuardrailAblationOptions,
) -> list[str]:
    reason_codes: list[str] = []
    if _int_delta(deltas, "excluded_candidate_count") < options.min_excluded_candidate_count:
        reason_codes.append("loss_driver_guardrail:excluded_candidate_count_too_low")
    if _int_delta(deltas, "final_hit_count_delta") < options.min_final_hit_count_delta:
        reason_codes.append("loss_driver_guardrail:final_hit_count_regressed")
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="final_hit_rate_delta",
        threshold=options.min_final_hit_rate_delta,
        reason_code="loss_driver_guardrail:final_hit_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="roi_delta",
        threshold=options.min_roi_delta,
        reason_code="loss_driver_guardrail:roi_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="profit_loss_delta",
        threshold=options.min_profit_loss_delta,
        reason_code="loss_driver_guardrail:profit_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="final_hit_harm_count_vs_baseline",
        threshold=options.max_final_hit_harm_count_vs_baseline,
        reason_code="loss_driver_guardrail:final_hit_harm_count_above_threshold",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="profit_loss_harm_count_vs_baseline",
        threshold=options.max_profit_loss_harm_count_vs_baseline,
        reason_code="loss_driver_guardrail:profit_loss_harm_count_above_threshold",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="brier_score_delta",
        threshold=options.max_brier_score_delta,
        reason_code="loss_driver_guardrail:brier_score_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="log_loss_delta",
        threshold=options.max_log_loss_delta,
        reason_code="loss_driver_guardrail:log_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="mean_calibration_error_delta",
        threshold=options.max_mean_calibration_error_delta,
        reason_code="loss_driver_guardrail:mean_calibration_error_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="upset_capture_rate_delta",
        threshold=options.min_upset_capture_rate_delta,
        reason_code="loss_driver_guardrail:upset_capture_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    if not objective_improvement_satisfied:
        reason_codes.append("loss_driver_guardrail:objective_improvement_missing")
    return reason_codes


def _objective_improvement_metric_codes(
    deltas: Mapping[str, object],
    *,
    options: HistoricalMarginalLossDriverCandidateGuardrailAblationOptions,
) -> list[str]:
    metric_codes: list[str] = []
    if _minimum_delta_exceeded(
        deltas,
        key="final_hit_rate_delta",
        threshold=options.min_objective_final_hit_rate_delta,
        epsilon=options.comparison_epsilon,
    ):
        metric_codes.append("final_hit_rate_delta")
    if _minimum_delta_exceeded(
        deltas,
        key="roi_delta",
        threshold=options.min_objective_roi_delta,
        epsilon=options.comparison_epsilon,
    ):
        metric_codes.append("roi_delta")
    return metric_codes


def _minimum_delta_exceeded(
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    epsilon: float,
) -> bool:
    value = _number(deltas, key)
    return value is not None and value > threshold + epsilon


def _append_minimum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    reason_code: str,
    epsilon: float,
) -> None:
    value = _number(deltas, key)
    if value is None or value + epsilon < threshold:
        reason_codes.append(reason_code)


def _append_maximum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    reason_code: str,
    epsilon: float,
) -> None:
    value = _number(deltas, key)
    if value is not None and value > threshold + epsilon:
        reason_codes.append(reason_code)


def _append_optional_maximum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: int | None,
    reason_code: str,
    epsilon: float,
) -> None:
    if threshold is None:
        return
    _append_maximum_reason(
        reason_codes,
        deltas,
        key=key,
        threshold=threshold,
        reason_code=reason_code,
        epsilon=epsilon,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    suite_manifests = list(args.suite_manifest or [])
    if not suite_manifests:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
            resolved_slice_paths=list(args.slice_paths),
        )
    bundles = [
        load_historical_recommendation_suite_manifest_bundle(suite_manifest)
        for suite_manifest in suite_manifests
    ]
    return _LoadedHistoricalSlices(
        slices=[
            historical_slice
            for bundle in bundles
            for historical_slice in bundle.slices
        ]
        + explicit_slices,
        resolved_slice_paths=[
            resolved_path
            for bundle in bundles
            for resolved_path in bundle.resolved_slice_paths
        ]
        + list(args.slice_paths),
        manifest_result=bundles[0] if len(bundles) == 1 else None,
        manifest_results=bundles,
        warnings=[warning for bundle in bundles for warning in bundle.warnings],
    )


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run marginal loss-driver candidate-pool guardrail ablation."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--pass-types", default="2x1")
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=64.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=80.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=2)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument(
        "--optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--competitions", default="JPN_J1")
    parser.add_argument("--probability-min", type=float, default=0.65)
    parser.add_argument("--probability-max", type=float, default=0.80)
    parser.add_argument("--max-decimal-odds", type=float, default=1.50)
    parser.add_argument("--max-model-edge", type=float, default=-0.02)
    parser.add_argument("--max-calibration-score", type=float)
    parser.add_argument("--max-model-confidence-score", type=float)
    parser.add_argument("--max-odds-stability-score", type=float)
    parser.add_argument("--min-excluded-candidate-count", type=int, default=1)
    parser.add_argument("--min-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int)
    parser.add_argument("--max-profit-loss-harm-count-vs-baseline", type=int)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--min-upset-capture-rate-delta", type=float, default=0.0)
    parser.add_argument(
        "--require-objective-improvement",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--min-objective-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-objective-roi-delta", type=float, default=0.0)
    parser.add_argument("--comparison-epsilon", type=float, default=1e-12)
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalMarginalLossDriverCandidateGuardrailAblationOptions:
    return HistoricalMarginalLossDriverCandidateGuardrailAblationOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            upset_threshold=args.upset_threshold,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
        ),
        optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
        competition_ids=tuple(_csv(args.competitions)),
        probability_min=args.probability_min,
        probability_max=args.probability_max,
        max_decimal_odds=args.max_decimal_odds,
        max_model_edge=args.max_model_edge,
        max_calibration_score=args.max_calibration_score,
        max_model_confidence_score=args.max_model_confidence_score,
        max_odds_stability_score=args.max_odds_stability_score,
        min_excluded_candidate_count=args.min_excluded_candidate_count,
        min_final_hit_count_delta=args.min_final_hit_count_delta,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_final_hit_harm_count_vs_baseline=(
            args.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            args.max_profit_loss_harm_count_vs_baseline
        ),
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        min_upset_capture_rate_delta=args.min_upset_capture_rate_delta,
        require_objective_improvement=args.require_objective_improvement,
        min_objective_final_hit_rate_delta=args.min_objective_final_hit_rate_delta,
        min_objective_roi_delta=args.min_objective_roi_delta,
        comparison_epsilon=args.comparison_epsilon,
    )


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _int_delta(deltas: Mapping[str, object], key: str) -> int:
    value = deltas.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _number(mapping: Mapping[str, object], key: str) -> float | None:
    value = mapping.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _float_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _average(values: Iterable[float | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(path) for path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _report_key(
    summary: Mapping[str, object],
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> str:
    slice_payload = ";".join(
        f"{historical_slice.metadata.slice_id}@{historical_slice.as_of_time_utc.isoformat()}"
        for historical_slice in historical_slices
    )
    payload = dumps({"summary": summary, "slices": slice_payload}, sort_keys=True)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_marginal_loss_driver_candidate_guardrail_ablation:{digest}"
