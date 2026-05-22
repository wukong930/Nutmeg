from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Mapping, Sequence
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
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.marginal_loss_driver_candidate_soft_penalty_grid import (
    _aggregate_deltas,
    _csv,
    _final_answer_changed_count,
    _float_tuple,
    _int_delta,
    _manifest_summary,
    _number,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalCompetitionDataQualityThresholdStatus = Literal["accepted", "rejected"]


class HistoricalCompetitionDataQualityThresholdGridOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    optimizer_profile: HistoricalOptimizerProfile = "solver"
    baseline_min_data_quality_score: float = Field(default=80.0, ge=0.0, le=100.0)
    competition_ids: tuple[str, ...] = ("FRA_LIGUE_2",)
    candidate_min_data_quality_score_values: tuple[float, ...] = (
        75.0,
        70.0,
        60.0,
        50.0,
    )
    min_newly_admitted_prediction_count: int = Field(default=1, ge=0)
    min_final_hit_sample_size_delta: int = 0
    min_final_hit_count_delta: int = 0
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_baseline: int | None = Field(default=None, ge=0)
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    require_objective_improvement: bool = True
    min_objective_final_hit_count_delta: int = 0
    min_objective_final_hit_rate_delta: float = 0.0
    min_objective_roi_delta: float = 0.0
    comparison_epsilon: float = Field(default=1e-12, ge=0.0)


class HistoricalCompetitionDataQualityThresholdCandidate(BaseModel):
    candidate_key: str
    status: HistoricalCompetitionDataQualityThresholdStatus
    competition_id: str
    candidate_min_data_quality_score: float = Field(ge=0.0, le=100.0)
    newly_admitted_prediction_count: int = Field(ge=0)
    newly_admitted_fixture_count: int = Field(ge=0)
    final_answer_changed_count: int = Field(ge=0)
    baseline_final_hit_sample_size: int = Field(ge=0)
    candidate_final_hit_sample_size: int = Field(ge=0)
    final_hit_sample_size_delta: int
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
    objective_improvement_satisfied: bool = False
    objective_improvement_metric_codes: list[str] = Field(default_factory=list)
    deltas_json: dict[str, object] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalCompetitionDataQualityThresholdGridReport(BaseModel):
    report_key: str
    status: Literal["generated"]
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    candidates: list[HistoricalCompetitionDataQualityThresholdCandidate] = Field(
        default_factory=list
    )
    accepted_candidates: list[HistoricalCompetitionDataQualityThresholdCandidate] = (
        Field(default_factory=list)
    )
    best_candidate: HistoricalCompetitionDataQualityThresholdCandidate | None = None
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


def build_historical_competition_data_quality_threshold_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalCompetitionDataQualityThresholdGridOptions | None = None,
) -> HistoricalCompetitionDataQualityThresholdGridReport:
    resolved_options = options or HistoricalCompetitionDataQualityThresholdGridOptions()
    baseline_options = _baseline_backtest_options(resolved_options)
    baseline_results = [
        run_historical_recommendation_backtest(
            historical_slice,
            options=baseline_options,
        )
        for historical_slice in historical_slices
    ]
    warnings = [
        warning for result in baseline_results for warning in result.warnings
    ]
    candidates = [
        _evaluate_threshold_candidate(
            historical_slices,
            baseline_results=baseline_results,
            competition_id=competition_id,
            threshold=threshold,
            options=resolved_options,
        )
        for competition_id in resolved_options.competition_ids
        for threshold in resolved_options.candidate_min_data_quality_score_values
    ]
    accepted_candidates = [
        candidate for candidate in candidates if candidate.status == "accepted"
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_competition_data_quality_threshold_grid_v3_1"
        ),
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "optimizer_profile": resolved_options.optimizer_profile,
        "baseline_min_data_quality_score": (
            resolved_options.baseline_min_data_quality_score
        ),
        "competition_ids": list(resolved_options.competition_ids),
        "candidate_min_data_quality_score_values": list(
            resolved_options.candidate_min_data_quality_score_values
        ),
        "max_final_hit_harm_count_vs_baseline": (
            resolved_options.max_final_hit_harm_count_vs_baseline
        ),
        "max_profit_loss_harm_count_vs_baseline": (
            resolved_options.max_profit_loss_harm_count_vs_baseline
        ),
        "require_objective_improvement": (
            resolved_options.require_objective_improvement
        ),
        "best_candidate_key": best_candidate.candidate_key
        if best_candidate is not None
        else None,
        "best_candidate_status": best_candidate.status
        if best_candidate is not None
        else None,
        "best_candidate_deltas": best_candidate.deltas_json
        if best_candidate is not None
        else {},
        "accepted_candidate_keys": [
            candidate.candidate_key for candidate in accepted_candidates
        ],
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    return HistoricalCompetitionDataQualityThresholdGridReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        best_candidate=best_candidate,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded = _historical_slices_from_args(args)
    report = build_historical_competition_data_quality_threshold_grid_report(
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
    options: HistoricalCompetitionDataQualityThresholdGridOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.backtest_options.model_copy(
        update={
            "optimizer_profile": options.optimizer_profile,
            "min_data_quality_score": options.baseline_min_data_quality_score,
            "min_data_quality_score_by_competition_id": {},
        }
    )


def _candidate_backtest_options(
    options: HistoricalCompetitionDataQualityThresholdGridOptions,
    *,
    competition_id: str,
    threshold: float,
) -> HistoricalRecommendationBacktestOptions:
    return options.backtest_options.model_copy(
        update={
            "optimizer_profile": options.optimizer_profile,
            "min_data_quality_score": options.baseline_min_data_quality_score,
            "min_data_quality_score_by_competition_id": {
                competition_id: threshold,
            },
        }
    )


def _evaluate_threshold_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_results: Sequence[HistoricalRecommendationBacktestResult],
    competition_id: str,
    threshold: float,
    options: HistoricalCompetitionDataQualityThresholdGridOptions,
) -> HistoricalCompetitionDataQualityThresholdCandidate:
    candidate_options = _candidate_backtest_options(
        options,
        competition_id=competition_id,
        threshold=threshold,
    )
    candidate_results = [
        run_historical_recommendation_backtest(
            historical_slice,
            options=candidate_options,
        )
        for historical_slice in historical_slices
    ]
    deltas = _threshold_deltas(baseline_results, candidate_results)
    newly_admitted_prediction_count = _newly_admitted_prediction_count(
        historical_slices,
        competition_id=competition_id,
        threshold=threshold,
        baseline_threshold=options.baseline_min_data_quality_score,
    )
    newly_admitted_fixture_count = _newly_admitted_fixture_count(
        historical_slices,
        competition_id=competition_id,
        threshold=threshold,
        baseline_threshold=options.baseline_min_data_quality_score,
    )
    objective_metric_codes = _objective_improvement_metric_codes(
        deltas,
        options=options,
    )
    objective_improvement_satisfied = (
        not options.require_objective_improvement or bool(objective_metric_codes)
    )
    reason_codes = _reason_codes(
        deltas,
        newly_admitted_prediction_count=newly_admitted_prediction_count,
        objective_improvement_satisfied=objective_improvement_satisfied,
        options=options,
    )
    status: HistoricalCompetitionDataQualityThresholdStatus = (
        "accepted" if not reason_codes else "rejected"
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_competition_data_quality_threshold_candidate_v3_1"
        ),
        "status": status,
        "competition_id": competition_id,
        "candidate_min_data_quality_score": threshold,
        "newly_admitted_prediction_count": newly_admitted_prediction_count,
        "newly_admitted_fixture_count": newly_admitted_fixture_count,
        "objective_improvement_satisfied": objective_improvement_satisfied,
        "objective_improvement_metric_codes": objective_metric_codes,
        "reason_codes": reason_codes,
        "deltas": deltas,
    }
    candidate_key = _candidate_key(summary)
    return HistoricalCompetitionDataQualityThresholdCandidate(
        candidate_key=candidate_key,
        status=status,
        competition_id=competition_id,
        candidate_min_data_quality_score=threshold,
        newly_admitted_prediction_count=newly_admitted_prediction_count,
        newly_admitted_fixture_count=newly_admitted_fixture_count,
        final_answer_changed_count=_final_answer_changed_count(
            baseline_results,
            candidate_results,
        ),
        baseline_final_hit_sample_size=_int_delta(
            deltas,
            "baseline_final_hit_sample_size",
        ),
        candidate_final_hit_sample_size=_int_delta(
            deltas,
            "candidate_final_hit_sample_size",
        ),
        final_hit_sample_size_delta=_int_delta(
            deltas,
            "final_hit_sample_size_delta",
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
        objective_improvement_satisfied=objective_improvement_satisfied,
        objective_improvement_metric_codes=objective_metric_codes,
        deltas_json=deltas,
        reason_codes=reason_codes,
        summary_json={**summary, "candidate_key": candidate_key},
    )


def _threshold_deltas(
    baseline_results: Sequence[HistoricalRecommendationBacktestResult],
    candidate_results: Sequence[HistoricalRecommendationBacktestResult],
) -> dict[str, object]:
    deltas = dict(_aggregate_deltas(baseline_results, candidate_results))
    deltas["final_hit_sample_size_delta"] = _int_delta(
        deltas,
        "candidate_final_hit_sample_size",
    ) - _int_delta(deltas, "baseline_final_hit_sample_size")
    return deltas


def _newly_admitted_prediction_count(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    competition_id: str,
    threshold: float,
    baseline_threshold: float,
) -> int:
    if threshold >= baseline_threshold:
        return 0
    return sum(
        1
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
        if fixture.competition_id == competition_id
        for prediction in fixture.predictions
        if threshold <= prediction.data_quality_score < baseline_threshold
    )


def _newly_admitted_fixture_count(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    competition_id: str,
    threshold: float,
    baseline_threshold: float,
) -> int:
    if threshold >= baseline_threshold:
        return 0
    return len(
        {
            fixture.fixture_id
            for historical_slice in historical_slices
            for fixture in historical_slice.fixtures
            if fixture.competition_id == competition_id
            if any(
                threshold <= prediction.data_quality_score < baseline_threshold
                for prediction in fixture.predictions
            )
        }
    )


def _reason_codes(
    deltas: Mapping[str, object],
    *,
    newly_admitted_prediction_count: int,
    objective_improvement_satisfied: bool,
    options: HistoricalCompetitionDataQualityThresholdGridOptions,
) -> list[str]:
    reason_codes: list[str] = []
    if newly_admitted_prediction_count < options.min_newly_admitted_prediction_count:
        reason_codes.append(
            "competition_data_quality_threshold:newly_admitted_prediction_count_too_low"
        )
    if (
        _int_delta(deltas, "final_hit_sample_size_delta")
        < options.min_final_hit_sample_size_delta
    ):
        reason_codes.append(
            "competition_data_quality_threshold:final_hit_sample_size_regressed"
        )
    if _int_delta(deltas, "final_hit_count_delta") < options.min_final_hit_count_delta:
        reason_codes.append(
            "competition_data_quality_threshold:final_hit_count_regressed"
        )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="final_hit_rate_delta",
        threshold=options.min_final_hit_rate_delta,
        reason_code="competition_data_quality_threshold:final_hit_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="roi_delta",
        threshold=options.min_roi_delta,
        reason_code="competition_data_quality_threshold:roi_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="profit_loss_delta",
        threshold=options.min_profit_loss_delta,
        reason_code="competition_data_quality_threshold:profit_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="final_hit_harm_count_vs_baseline",
        threshold=options.max_final_hit_harm_count_vs_baseline,
        reason_code=(
            "competition_data_quality_threshold:final_hit_harm_count_above_threshold"
        ),
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="profit_loss_harm_count_vs_baseline",
        threshold=options.max_profit_loss_harm_count_vs_baseline,
        reason_code=(
            "competition_data_quality_threshold:profit_loss_harm_count_above_threshold"
        ),
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="brier_score_delta",
        threshold=options.max_brier_score_delta,
        reason_code="competition_data_quality_threshold:brier_score_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="log_loss_delta",
        threshold=options.max_log_loss_delta,
        reason_code="competition_data_quality_threshold:log_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="mean_calibration_error_delta",
        threshold=options.max_mean_calibration_error_delta,
        reason_code=(
            "competition_data_quality_threshold:mean_calibration_error_regressed"
        ),
        epsilon=options.comparison_epsilon,
    )
    if not objective_improvement_satisfied:
        reason_codes.append(
            "competition_data_quality_threshold:objective_improvement_missing"
        )
    return reason_codes


def _objective_improvement_metric_codes(
    deltas: Mapping[str, object],
    *,
    options: HistoricalCompetitionDataQualityThresholdGridOptions,
) -> list[str]:
    metric_codes: list[str] = []
    if (
        _int_delta(deltas, "final_hit_count_delta")
        > options.min_objective_final_hit_count_delta
    ):
        metric_codes.append("final_hit_count_delta")
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


def _best_candidate(
    candidates: Sequence[HistoricalCompetitionDataQualityThresholdCandidate],
) -> HistoricalCompetitionDataQualityThresholdCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key, reverse=True)[0]


def _candidate_sort_key(
    candidate: HistoricalCompetitionDataQualityThresholdCandidate,
) -> tuple[int, float, float, float, float, int, int, int, float, str]:
    return (
        1 if candidate.status == "accepted" else 0,
        _number(candidate.deltas_json, "final_hit_rate_delta") or -999.0,
        _number(candidate.deltas_json, "roi_delta") or -999.0,
        _number(candidate.deltas_json, "profit_loss_delta") or -999.0,
        -(_number(candidate.deltas_json, "brier_score_delta") or 999.0),
        -candidate.final_hit_harm_count_vs_baseline,
        -candidate.profit_loss_harm_count_vs_baseline,
        candidate.newly_admitted_prediction_count,
        -candidate.candidate_min_data_quality_score,
        candidate.candidate_key,
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
        description="Search per-competition data-quality threshold overrides."
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
    parser.add_argument("--baseline-min-data-quality-score", type=float, default=80.0)
    parser.add_argument("--competitions", default="FRA_LIGUE_2")
    parser.add_argument(
        "--candidate-min-data-quality-score-values",
        default="75,70,60,50",
    )
    parser.add_argument("--min-newly-admitted-prediction-count", type=int, default=1)
    parser.add_argument("--min-final-hit-sample-size-delta", type=int, default=0)
    parser.add_argument("--min-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int)
    parser.add_argument("--max-profit-loss-harm-count-vs-baseline", type=int)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument(
        "--require-objective-improvement",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--min-objective-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-objective-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-objective-roi-delta", type=float, default=0.0)
    parser.add_argument("--comparison-epsilon", type=float, default=1e-12)
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalCompetitionDataQualityThresholdGridOptions:
    return HistoricalCompetitionDataQualityThresholdGridOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            upset_threshold=args.upset_threshold,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
        ),
        optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
        baseline_min_data_quality_score=args.baseline_min_data_quality_score,
        competition_ids=tuple(_csv(args.competitions)),
        candidate_min_data_quality_score_values=_float_tuple(
            args.candidate_min_data_quality_score_values
        ),
        min_newly_admitted_prediction_count=(
            args.min_newly_admitted_prediction_count
        ),
        min_final_hit_sample_size_delta=args.min_final_hit_sample_size_delta,
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
        require_objective_improvement=args.require_objective_improvement,
        min_objective_final_hit_count_delta=(
            args.min_objective_final_hit_count_delta
        ),
        min_objective_final_hit_rate_delta=(
            args.min_objective_final_hit_rate_delta
        ),
        min_objective_roi_delta=args.min_objective_roi_delta,
        comparison_epsilon=args.comparison_epsilon,
    )


def _candidate_key(summary: Mapping[str, object]) -> str:
    digest = sha256(dumps(summary, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"historical_competition_data_quality_threshold:{digest}"


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
    return f"historical_competition_data_quality_threshold_grid:{digest}"
