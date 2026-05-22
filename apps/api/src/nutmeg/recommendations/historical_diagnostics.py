from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalRecommendationDiagnosticGroupType = Literal[
    "overall",
    "competition",
    "season",
    "competition_season",
]


class HistoricalRecommendationDiagnosticOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"


class HistoricalRecommendationDiagnosticMetricSet(BaseModel):
    optimizer_profile: HistoricalOptimizerProfile
    final_hit_sample_size: int = Field(ge=0)
    final_hit_count: int = Field(ge=0)
    final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    total_stake: float = Field(ge=0.0)
    actual_return: float = Field(ge=0.0)
    profit_loss: float
    roi: float | None = None
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    mean_calibration_error: float | None = Field(default=None, ge=0.0)
    upset_opportunity_count: int = Field(ge=0)
    upset_capture_count: int = Field(ge=0)
    upset_capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    solver_selected_scenario_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)


class HistoricalRecommendationDiagnosticGroup(BaseModel):
    group_key: str
    group_type: HistoricalRecommendationDiagnosticGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    comparison_count: int = Field(ge=0)
    comparison_status_counts: dict[str, int] = Field(default_factory=dict)
    baseline: HistoricalRecommendationDiagnosticMetricSet
    candidate: HistoricalRecommendationDiagnosticMetricSet
    deltas_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalRecommendationDiagnosticReport(BaseModel):
    report_key: str
    status: str
    suite_key: str
    suite_status: str
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    comparison_count: int = Field(ge=0)
    baseline_optimizer_profile: HistoricalOptimizerProfile
    candidate_optimizer_profile: HistoricalOptimizerProfile
    overall: HistoricalRecommendationDiagnosticGroup
    by_competition: list[HistoricalRecommendationDiagnosticGroup] = Field(
        default_factory=list
    )
    by_season: list[HistoricalRecommendationDiagnosticGroup] = Field(default_factory=list)
    by_competition_season: list[HistoricalRecommendationDiagnosticGroup] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _SliceComparison(BaseModel):
    historical_slice: HistoricalRecommendationSlice
    comparison: HistoricalRecommendationBacktestComparisonResult


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_recommendation_diagnostic_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationDiagnosticOptions | None = None,
) -> HistoricalRecommendationDiagnosticReport:
    resolved_options = options or HistoricalRecommendationDiagnosticOptions()
    suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=resolved_options.backtest_options,
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
    )
    pairs = [
        _SliceComparison(historical_slice=historical_slice, comparison=comparison)
        for historical_slice, comparison in zip(
            historical_slices,
            suite.comparisons,
            strict=True,
        )
    ]
    overall = _diagnostic_group(
        "overall",
        group_type="overall",
        label="Overall",
        pairs=pairs,
        options=resolved_options,
    )
    by_competition = _grouped_diagnostics(
        pairs,
        group_type="competition",
        key_fn=lambda pair: pair.historical_slice.metadata.competition_id,
        label_fn=lambda key: key,
        options=resolved_options,
    )
    by_season = _grouped_diagnostics(
        pairs,
        group_type="season",
        key_fn=lambda pair: pair.historical_slice.metadata.season or "unknown",
        label_fn=lambda key: key,
        options=resolved_options,
    )
    by_competition_season = _grouped_diagnostics(
        pairs,
        group_type="competition_season",
        key_fn=lambda pair: "|".join(
            [
                pair.historical_slice.metadata.competition_id,
                pair.historical_slice.metadata.season or "unknown",
            ]
        ),
        label_fn=lambda key: key.replace("|", " "),
        options=resolved_options,
    )
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    warnings = [*suite.warnings]
    summary: dict[str, object] = {
        "calculation_basis": "historical_recommendation_diagnostic_report_v3_1",
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "comparison_count": len(suite.comparisons),
        "baseline_optimizer_profile": resolved_options.baseline_optimizer_profile,
        "candidate_optimizer_profile": resolved_options.candidate_optimizer_profile,
        "pass_types": list(resolved_options.backtest_options.pass_types),
        "modes": list(resolved_options.backtest_options.modes),
        "short_price_negative_edge_guardrail": suite.summary_json.get(
            "short_price_negative_edge_guardrail"
        ),
        "short_price_negative_edge_max_decimal_odds": suite.summary_json.get(
            "short_price_negative_edge_max_decimal_odds"
        ),
        "short_price_negative_edge_min_probability": suite.summary_json.get(
            "short_price_negative_edge_min_probability"
        ),
        "short_price_negative_edge_max_model_edge": suite.summary_json.get(
            "short_price_negative_edge_max_model_edge"
        ),
        "baseline_short_price_negative_edge_guardrail_excluded_candidate_count": (
            suite.summary_json.get(
                "baseline_short_price_negative_edge_guardrail_excluded_candidate_count"
            )
        ),
        "candidate_short_price_negative_edge_guardrail_excluded_candidate_count": (
            suite.summary_json.get(
                "candidate_short_price_negative_edge_guardrail_excluded_candidate_count"
            )
        ),
        "short_price_negative_edge_soft_penalty": suite.summary_json.get(
            "short_price_negative_edge_soft_penalty"
        ),
        "short_price_negative_edge_soft_penalty_strength": suite.summary_json.get(
            "short_price_negative_edge_soft_penalty_strength"
        ),
        "short_price_negative_edge_soft_penalty_competition_ids": suite.summary_json.get(
            "short_price_negative_edge_soft_penalty_competition_ids"
        ),
        "baseline_short_price_negative_edge_soft_penalty_candidate_count": (
            suite.summary_json.get(
                "baseline_short_price_negative_edge_soft_penalty_candidate_count"
            )
        ),
        "candidate_short_price_negative_edge_soft_penalty_candidate_count": (
            suite.summary_json.get(
                "candidate_short_price_negative_edge_soft_penalty_candidate_count"
            )
        ),
        "upset_exposure_reserve": suite.summary_json.get("upset_exposure_reserve"),
        "upset_exposure_reserve_fixture_count": suite.summary_json.get(
            "upset_exposure_reserve_fixture_count"
        ),
        "upset_exposure_reserve_min_protection_score": suite.summary_json.get(
            "upset_exposure_reserve_min_protection_score"
        ),
        "upset_exposure_reserve_min_probability": suite.summary_json.get(
            "upset_exposure_reserve_min_probability"
        ),
        "upset_exposure_reserve_max_decimal_odds": suite.summary_json.get(
            "upset_exposure_reserve_max_decimal_odds"
        ),
        "baseline_candidate_pool_upset_exposure_reserve_candidate_count": (
            suite.summary_json.get(
                "baseline_candidate_pool_upset_exposure_reserve_candidate_count"
            )
        ),
        "candidate_candidate_pool_upset_exposure_reserve_candidate_count": (
            suite.summary_json.get(
                "candidate_candidate_pool_upset_exposure_reserve_candidate_count"
            )
        ),
        "baseline_final_answer_upset_exposure_reserve_selected_candidate_count": (
            suite.summary_json.get(
                "baseline_final_answer_upset_exposure_reserve_selected_candidate_count"
            )
        ),
        "candidate_final_answer_upset_exposure_reserve_selected_candidate_count": (
            suite.summary_json.get(
                "candidate_final_answer_upset_exposure_reserve_selected_candidate_count"
            )
        ),
        "upset_final_answer_lane": suite.summary_json.get(
            "upset_final_answer_lane"
        ),
        "upset_final_answer_lane_pass_type": suite.summary_json.get(
            "upset_final_answer_lane_pass_type"
        ),
        "upset_final_answer_lane_mode": suite.summary_json.get(
            "upset_final_answer_lane_mode"
        ),
        "upset_final_answer_lane_candidate_limit": suite.summary_json.get(
            "upset_final_answer_lane_candidate_limit"
        ),
        "upset_final_answer_lane_min_protection_score": suite.summary_json.get(
            "upset_final_answer_lane_min_protection_score"
        ),
        "upset_final_answer_lane_min_probability": suite.summary_json.get(
            "upset_final_answer_lane_min_probability"
        ),
        "upset_final_answer_lane_min_decimal_odds": suite.summary_json.get(
            "upset_final_answer_lane_min_decimal_odds"
        ),
        "upset_final_answer_lane_max_decimal_odds": suite.summary_json.get(
            "upset_final_answer_lane_max_decimal_odds"
        ),
        "upset_final_answer_lane_min_model_edge": suite.summary_json.get(
            "upset_final_answer_lane_min_model_edge"
        ),
        "upset_final_answer_lane_max_model_edge": suite.summary_json.get(
            "upset_final_answer_lane_max_model_edge"
        ),
        "upset_final_answer_lane_competition_ids": suite.summary_json.get(
            "upset_final_answer_lane_competition_ids"
        ),
        "upset_final_answer_lane_excluded_competition_ids": suite.summary_json.get(
            "upset_final_answer_lane_excluded_competition_ids"
        ),
        "upset_final_answer_lane_min_calibration_score": suite.summary_json.get(
            "upset_final_answer_lane_min_calibration_score"
        ),
        "upset_final_answer_lane_min_model_confidence_score": suite.summary_json.get(
            "upset_final_answer_lane_min_model_confidence_score"
        ),
        "upset_final_answer_lane_min_odds_stability_score": suite.summary_json.get(
            "upset_final_answer_lane_min_odds_stability_score"
        ),
        "upset_final_answer_lane_max_volatility_penalty": suite.summary_json.get(
            "upset_final_answer_lane_max_volatility_penalty"
        ),
        "upset_final_answer_lane_max_hit_probability_deficit": (
            suite.summary_json.get(
                "upset_final_answer_lane_max_hit_probability_deficit"
            )
        ),
        "upset_final_answer_lane_max_signal_calibration_risk": (
            suite.summary_json.get(
                "upset_final_answer_lane_max_signal_calibration_risk"
            )
        ),
        "upset_final_answer_lane_min_signal_reliability_score": (
            suite.summary_json.get(
                "upset_final_answer_lane_min_signal_reliability_score"
            )
        ),
        "upset_final_answer_lane_score_boost": suite.summary_json.get(
            "upset_final_answer_lane_score_boost"
        ),
        "baseline_upset_final_answer_lane_candidate_count": suite.summary_json.get(
            "baseline_upset_final_answer_lane_candidate_count"
        ),
        "candidate_upset_final_answer_lane_candidate_count": suite.summary_json.get(
            "candidate_upset_final_answer_lane_candidate_count"
        ),
        "baseline_candidate_pool_upset_final_answer_lane_candidate_count": (
            suite.summary_json.get(
                "baseline_candidate_pool_upset_final_answer_lane_candidate_count"
            )
        ),
        "candidate_candidate_pool_upset_final_answer_lane_candidate_count": (
            suite.summary_json.get(
                "candidate_candidate_pool_upset_final_answer_lane_candidate_count"
            )
        ),
        "baseline_completed_upset_final_answer_lane_count": suite.summary_json.get(
            "baseline_completed_upset_final_answer_lane_count"
        ),
        "candidate_completed_upset_final_answer_lane_count": suite.summary_json.get(
            "candidate_completed_upset_final_answer_lane_count"
        ),
        "baseline_final_answer_upset_final_answer_lane_count": (
            suite.summary_json.get("baseline_final_answer_upset_final_answer_lane_count")
        ),
        "candidate_final_answer_upset_final_answer_lane_count": (
            suite.summary_json.get("candidate_final_answer_upset_final_answer_lane_count")
        ),
        "baseline_final_answer_upset_final_answer_lane_selected_candidate_count": (
            suite.summary_json.get(
                "baseline_final_answer_upset_final_answer_lane_selected_candidate_count"
            )
        ),
        "candidate_final_answer_upset_final_answer_lane_selected_candidate_count": (
            suite.summary_json.get(
                "candidate_final_answer_upset_final_answer_lane_selected_candidate_count"
            )
        ),
        "baseline_upset_final_answer_lane_calibration_guard_blocked_option_count": (
            suite.summary_json.get(
                "baseline_upset_final_answer_lane_calibration_guard_blocked_option_count"
            )
        ),
        "candidate_upset_final_answer_lane_calibration_guard_blocked_option_count": (
            suite.summary_json.get(
                "candidate_upset_final_answer_lane_calibration_guard_blocked_option_count"
            )
        ),
        "overall": overall.summary_json,
        "competition_count": len(by_competition),
        "season_count": len(by_season),
        "competition_season_count": len(by_competition_season),
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    return HistoricalRecommendationDiagnosticReport(
        report_key=report_key,
        status="generated",
        suite_key=suite.suite_key,
        suite_status=suite.status,
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        comparison_count=len(suite.comparisons),
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
        overall=overall,
        by_competition=by_competition,
        by_season=by_season,
        by_competition_season=by_competition_season,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_recommendation_diagnostic_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
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


def _diagnostic_group(
    group_key: str,
    *,
    group_type: HistoricalRecommendationDiagnosticGroupType,
    label: str,
    pairs: Sequence[_SliceComparison],
    options: HistoricalRecommendationDiagnosticOptions,
    competition_id: str | None = None,
    season: str | None = None,
) -> HistoricalRecommendationDiagnosticGroup:
    baseline = _metric_set(
        [pair.comparison.baseline for pair in pairs],
        optimizer_profile=options.baseline_optimizer_profile,
    )
    candidate = _metric_set(
        [pair.comparison.candidate for pair in pairs],
        optimizer_profile=options.candidate_optimizer_profile,
    )
    fixture_count = sum(len(pair.historical_slice.fixtures) for pair in pairs)
    prediction_count = sum(
        len(fixture.predictions)
        for pair in pairs
        for fixture in pair.historical_slice.fixtures
    )
    comparison_status_counts = _comparison_status_counts(
        [pair.comparison for pair in pairs]
    )
    final_answer_changed_count = sum(
        1
        for pair in pairs
        if pair.comparison.summary_json.get("final_answer_changed") is True
    )
    baseline_upset_reserve_pool_candidate_count = sum(
        _summary_int(
            pair.comparison.baseline.summary_json,
            "candidate_pool_upset_exposure_reserve_candidate_count",
        )
        for pair in pairs
    )
    candidate_upset_reserve_pool_candidate_count = sum(
        _summary_int(
            pair.comparison.candidate.summary_json,
            "candidate_pool_upset_exposure_reserve_candidate_count",
        )
        for pair in pairs
    )
    baseline_upset_reserve_selected_candidate_count = sum(
        _summary_int(
            pair.comparison.baseline.summary_json,
            "final_answer_upset_exposure_reserve_selected_candidate_count",
        )
        for pair in pairs
    )
    candidate_upset_reserve_selected_candidate_count = sum(
        _summary_int(
            pair.comparison.candidate.summary_json,
            "final_answer_upset_exposure_reserve_selected_candidate_count",
        )
        for pair in pairs
    )
    baseline_upset_lane_candidate_count = sum(
        _summary_int(
            pair.comparison.baseline.summary_json,
            "upset_final_answer_lane_candidate_count",
        )
        for pair in pairs
    )
    candidate_upset_lane_candidate_count = sum(
        _summary_int(
            pair.comparison.candidate.summary_json,
            "upset_final_answer_lane_candidate_count",
        )
        for pair in pairs
    )
    baseline_pool_upset_lane_candidate_count = sum(
        _summary_int(
            pair.comparison.baseline.summary_json,
            "candidate_pool_upset_final_answer_lane_candidate_count",
        )
        for pair in pairs
    )
    candidate_pool_upset_lane_candidate_count = sum(
        _summary_int(
            pair.comparison.candidate.summary_json,
            "candidate_pool_upset_final_answer_lane_candidate_count",
        )
        for pair in pairs
    )
    baseline_final_answer_upset_lane_count = sum(
        1
        for pair in pairs
        if pair.comparison.baseline.summary_json.get(
            "final_answer_upset_final_answer_lane"
        )
        is True
    )
    candidate_final_answer_upset_lane_count = sum(
        1
        for pair in pairs
        if pair.comparison.candidate.summary_json.get(
            "final_answer_upset_final_answer_lane"
        )
        is True
    )
    baseline_upset_lane_selected_candidate_count = sum(
        _summary_int(
            pair.comparison.baseline.summary_json,
            "final_answer_upset_final_answer_lane_selected_candidate_count",
        )
        for pair in pairs
    )
    candidate_upset_lane_selected_candidate_count = sum(
        _summary_int(
            pair.comparison.candidate.summary_json,
            "final_answer_upset_final_answer_lane_selected_candidate_count",
        )
        for pair in pairs
    )
    baseline_upset_lane_calibration_guard_blocked_option_count = sum(
        _summary_int(
            pair.comparison.baseline.summary_json,
            "upset_final_answer_lane_calibration_guard_blocked_option_count",
        )
        for pair in pairs
    )
    candidate_upset_lane_calibration_guard_blocked_option_count = sum(
        _summary_int(
            pair.comparison.candidate.summary_json,
            "upset_final_answer_lane_calibration_guard_blocked_option_count",
        )
        for pair in pairs
    )
    deltas = _metric_deltas(
        baseline,
        candidate,
        final_answer_changed_count=final_answer_changed_count,
    )
    summary: dict[str, object] = {
        "group_key": group_key,
        "group_type": group_type,
        "label": label,
        "competition_id": competition_id,
        "season": season,
        "slice_count": len(pairs),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "comparison_count": len(pairs),
        "candidate_final_hit_rate": candidate.final_hit_rate,
        "candidate_roi": candidate.roi,
        "candidate_profit_loss": candidate.profit_loss,
        "candidate_brier_score": candidate.brier_score,
        "candidate_log_loss": candidate.log_loss,
        "candidate_mean_calibration_error": candidate.mean_calibration_error,
        "candidate_upset_opportunity_count": candidate.upset_opportunity_count,
        "candidate_upset_capture_rate": candidate.upset_capture_rate,
        "baseline_candidate_pool_upset_exposure_reserve_candidate_count": (
            baseline_upset_reserve_pool_candidate_count
        ),
        "candidate_candidate_pool_upset_exposure_reserve_candidate_count": (
            candidate_upset_reserve_pool_candidate_count
        ),
        "baseline_final_answer_upset_exposure_reserve_selected_candidate_count": (
            baseline_upset_reserve_selected_candidate_count
        ),
        "candidate_final_answer_upset_exposure_reserve_selected_candidate_count": (
            candidate_upset_reserve_selected_candidate_count
        ),
        "baseline_upset_final_answer_lane_candidate_count": (
            baseline_upset_lane_candidate_count
        ),
        "candidate_upset_final_answer_lane_candidate_count": (
            candidate_upset_lane_candidate_count
        ),
        "baseline_candidate_pool_upset_final_answer_lane_candidate_count": (
            baseline_pool_upset_lane_candidate_count
        ),
        "candidate_candidate_pool_upset_final_answer_lane_candidate_count": (
            candidate_pool_upset_lane_candidate_count
        ),
        "baseline_final_answer_upset_final_answer_lane_count": (
            baseline_final_answer_upset_lane_count
        ),
        "candidate_final_answer_upset_final_answer_lane_count": (
            candidate_final_answer_upset_lane_count
        ),
        "baseline_final_answer_upset_final_answer_lane_selected_candidate_count": (
            baseline_upset_lane_selected_candidate_count
        ),
        "candidate_final_answer_upset_final_answer_lane_selected_candidate_count": (
            candidate_upset_lane_selected_candidate_count
        ),
        "baseline_upset_final_answer_lane_calibration_guard_blocked_option_count": (
            baseline_upset_lane_calibration_guard_blocked_option_count
        ),
        "candidate_upset_final_answer_lane_calibration_guard_blocked_option_count": (
            candidate_upset_lane_calibration_guard_blocked_option_count
        ),
        "deltas": deltas,
    }
    return HistoricalRecommendationDiagnosticGroup(
        group_key=group_key,
        group_type=group_type,
        label=label,
        competition_id=competition_id,
        season=season,
        slice_count=len(pairs),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        comparison_count=len(pairs),
        comparison_status_counts=comparison_status_counts,
        baseline=baseline,
        candidate=candidate,
        deltas_json=deltas,
        summary_json=summary,
    )


def _grouped_diagnostics(
    pairs: Sequence[_SliceComparison],
    *,
    group_type: Literal["competition", "season", "competition_season"],
    key_fn: Callable[[_SliceComparison], str],
    label_fn: Callable[[str], str],
    options: HistoricalRecommendationDiagnosticOptions,
) -> list[HistoricalRecommendationDiagnosticGroup]:
    grouped: dict[str, list[_SliceComparison]] = defaultdict(list)
    for pair in pairs:
        grouped[key_fn(pair)].append(pair)
    groups: list[HistoricalRecommendationDiagnosticGroup] = []
    for key in sorted(grouped):
        competition_id, season = _group_dimensions(key, group_type=group_type)
        groups.append(
            _diagnostic_group(
                key,
                group_type=group_type,
                label=label_fn(key),
                pairs=grouped[key],
                options=options,
                competition_id=competition_id,
                season=season,
            )
        )
    return groups


def _metric_set(
    results: Sequence[HistoricalRecommendationBacktestResult],
    *,
    optimizer_profile: HistoricalOptimizerProfile,
) -> HistoricalRecommendationDiagnosticMetricSet:
    final_hit_sample_size = sum(result.final_hit_sample_size for result in results)
    final_hit_count = sum(result.final_hit_count for result in results)
    total_stake = sum(result.total_stake for result in results)
    actual_return = sum(result.actual_return for result in results)
    profit_loss = actual_return - total_stake
    upset_opportunity_count = sum(result.upset_opportunity_count for result in results)
    upset_capture_count = sum(result.upset_capture_count for result in results)
    return HistoricalRecommendationDiagnosticMetricSet(
        optimizer_profile=optimizer_profile,
        final_hit_sample_size=final_hit_sample_size,
        final_hit_count=final_hit_count,
        final_hit_rate=_ratio(final_hit_count, final_hit_sample_size),
        total_stake=total_stake,
        actual_return=actual_return,
        profit_loss=profit_loss,
        roi=profit_loss / total_stake if total_stake > 0 else None,
        brier_score=_weighted_metric(results, lambda result: result.brier_score),
        log_loss=_weighted_metric(results, lambda result: result.log_loss),
        mean_calibration_error=_weighted_metric(
            results,
            lambda result: result.mean_calibration_error,
        ),
        upset_opportunity_count=upset_opportunity_count,
        upset_capture_count=upset_capture_count,
        upset_capture_rate=_ratio(upset_capture_count, upset_opportunity_count),
        solver_selected_scenario_count=sum(
            _summary_int(result.summary_json, "solver_selected_scenario_count")
            for result in results
        ),
        warning_count=sum(len(result.warnings) for result in results),
    )


def _metric_deltas(
    baseline: HistoricalRecommendationDiagnosticMetricSet,
    candidate: HistoricalRecommendationDiagnosticMetricSet,
    *,
    final_answer_changed_count: int,
) -> dict[str, object]:
    return {
        "final_hit_rate_delta": _optional_delta(
            candidate.final_hit_rate,
            baseline.final_hit_rate,
        ),
        "final_hit_count_delta": candidate.final_hit_count - baseline.final_hit_count,
        "profit_loss_delta": candidate.profit_loss - baseline.profit_loss,
        "roi_delta": _optional_delta(candidate.roi, baseline.roi),
        "brier_score_delta": _optional_delta(
            candidate.brier_score,
            baseline.brier_score,
        ),
        "log_loss_delta": _optional_delta(candidate.log_loss, baseline.log_loss),
        "mean_calibration_error_delta": _optional_delta(
            candidate.mean_calibration_error,
            baseline.mean_calibration_error,
        ),
        "upset_capture_rate_delta": _optional_delta(
            candidate.upset_capture_rate,
            baseline.upset_capture_rate,
        ),
        "upset_capture_count_delta": (
            candidate.upset_capture_count - baseline.upset_capture_count
        ),
        "candidate_solver_selected_scenario_count": (
            candidate.solver_selected_scenario_count
        ),
        "final_answer_changed_count": final_answer_changed_count,
    }


def _weighted_metric(
    results: Sequence[HistoricalRecommendationBacktestResult],
    value_fn: Callable[[HistoricalRecommendationBacktestResult], float | None],
) -> float | None:
    total_weight = 0
    weighted_sum = 0.0
    for result in results:
        value = value_fn(result)
        if value is None or result.final_hit_sample_size == 0:
            continue
        total_weight += result.final_hit_sample_size
        weighted_sum += value * result.final_hit_sample_size
    return weighted_sum / total_weight if total_weight > 0 else None


def _comparison_status_counts(
    comparisons: Sequence[HistoricalRecommendationBacktestComparisonResult],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for comparison in comparisons:
        counts[comparison.status] = counts.get(comparison.status, 0) + 1
    return counts


def _group_dimensions(
    group_key: str,
    *,
    group_type: HistoricalRecommendationDiagnosticGroupType,
) -> tuple[str | None, str | None]:
    if group_type == "competition":
        return group_key, None
    if group_type == "season":
        return None, group_key
    if group_type == "competition_season":
        competition_id, _, season = group_key.partition("|")
        return competition_id, season
    return None, None


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _summary_int(summary_json: Mapping[str, object], key: str) -> int:
    value = summary_json.get(key, 0)
    return value if isinstance(value, int) else 0


def _report_key(
    summary: Mapping[str, object],
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "slice_ids": [
                    historical_slice.metadata.slice_id
                    for historical_slice in historical_slices
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_recommendation_diagnostic:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Build league/season diagnostics for historical recommendation slices."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_HISTORICAL_BACKTEST_MODES))
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
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--upset-exposure-reserve", action="store_true")
    parser.add_argument("--upset-exposure-reserve-fixture-count", type=int, default=0)
    parser.add_argument(
        "--upset-exposure-reserve-max-candidates-per-fixture",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--upset-exposure-reserve-min-protection-score",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--upset-exposure-reserve-min-probability",
        type=float,
        default=0.15,
    )
    parser.add_argument("--upset-exposure-reserve-max-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane", action="store_true")
    parser.add_argument("--upset-final-answer-lane-pass-type", default="1x1")
    parser.add_argument(
        "--upset-final-answer-lane-mode",
        choices=["single", "multiple"],
        default="single",
    )
    parser.add_argument("--upset-final-answer-lane-candidate-limit", type=int, default=24)
    parser.add_argument(
        "--upset-final-answer-lane-min-protection-score",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-probability",
        type=float,
        default=0.15,
    )
    parser.add_argument("--upset-final-answer-lane-min-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane-max-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane-min-model-edge", type=float)
    parser.add_argument("--upset-final-answer-lane-max-model-edge", type=float)
    parser.add_argument("--upset-final-answer-lane-competitions", default="")
    parser.add_argument("--upset-final-answer-lane-excluded-competitions", default="")
    parser.add_argument(
        "--upset-final-answer-lane-min-calibration-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-model-confidence-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-odds-stability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-max-volatility-penalty", type=float)
    parser.add_argument(
        "--upset-final-answer-lane-max-hit-probability-deficit",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-max-signal-calibration-risk",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-signal-reliability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-score-boost", type=float, default=0.0)
    parser.add_argument("--short-price-negative-edge-guardrail", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-max-decimal-odds",
        type=float,
        default=1.35,
    )
    parser.add_argument(
        "--short-price-negative-edge-min-probability",
        type=float,
        default=0.70,
    )
    parser.add_argument(
        "--short-price-negative-edge-max-model-edge",
        type=float,
        default=0.0,
    )
    parser.add_argument("--short-price-negative-edge-soft-penalty", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-strength",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-competitions",
        default="",
    )
    parser.add_argument(
        "--baseline-optimizer-profile",
        choices=["heuristic", "solver"],
        default="heuristic",
    )
    parser.add_argument(
        "--candidate-optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalRecommendationDiagnosticOptions:
    return HistoricalRecommendationDiagnosticOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=_csv_tuple(args.pass_types),
            modes=tuple(
                cast(RecommendationMode, mode)
                for mode in _csv_tuple(args.modes)
            ),
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
            upset_exposure_reserve=args.upset_exposure_reserve,
            upset_exposure_reserve_fixture_count=(
                args.upset_exposure_reserve_fixture_count
            ),
            upset_exposure_reserve_max_candidates_per_fixture=(
                args.upset_exposure_reserve_max_candidates_per_fixture
            ),
            upset_exposure_reserve_min_protection_score=(
                args.upset_exposure_reserve_min_protection_score
            ),
            upset_exposure_reserve_min_probability=(
                args.upset_exposure_reserve_min_probability
            ),
            upset_exposure_reserve_max_decimal_odds=(
                args.upset_exposure_reserve_max_decimal_odds
            ),
            upset_final_answer_lane=args.upset_final_answer_lane,
            upset_final_answer_lane_pass_type=args.upset_final_answer_lane_pass_type,
            upset_final_answer_lane_mode=cast(
                RecommendationMode,
                args.upset_final_answer_lane_mode,
            ),
            upset_final_answer_lane_candidate_limit=(
                args.upset_final_answer_lane_candidate_limit
            ),
            upset_final_answer_lane_min_protection_score=(
                args.upset_final_answer_lane_min_protection_score
            ),
            upset_final_answer_lane_min_probability=(
                args.upset_final_answer_lane_min_probability
            ),
            upset_final_answer_lane_min_decimal_odds=(
                args.upset_final_answer_lane_min_decimal_odds
            ),
            upset_final_answer_lane_max_decimal_odds=(
                args.upset_final_answer_lane_max_decimal_odds
            ),
            upset_final_answer_lane_min_model_edge=(
                args.upset_final_answer_lane_min_model_edge
            ),
            upset_final_answer_lane_max_model_edge=(
                args.upset_final_answer_lane_max_model_edge
            ),
            upset_final_answer_lane_competition_ids=_csv_tuple(
                args.upset_final_answer_lane_competitions
            ),
            upset_final_answer_lane_excluded_competition_ids=_csv_tuple(
                args.upset_final_answer_lane_excluded_competitions
            ),
            upset_final_answer_lane_min_calibration_score=(
                args.upset_final_answer_lane_min_calibration_score
            ),
            upset_final_answer_lane_min_model_confidence_score=(
                args.upset_final_answer_lane_min_model_confidence_score
            ),
            upset_final_answer_lane_min_odds_stability_score=(
                args.upset_final_answer_lane_min_odds_stability_score
            ),
            upset_final_answer_lane_max_volatility_penalty=(
                args.upset_final_answer_lane_max_volatility_penalty
            ),
            upset_final_answer_lane_max_hit_probability_deficit=(
                args.upset_final_answer_lane_max_hit_probability_deficit
            ),
            upset_final_answer_lane_max_signal_calibration_risk=(
                args.upset_final_answer_lane_max_signal_calibration_risk
            ),
            upset_final_answer_lane_min_signal_reliability_score=(
                args.upset_final_answer_lane_min_signal_reliability_score
            ),
            upset_final_answer_lane_score_boost=(
                args.upset_final_answer_lane_score_boost
            ),
            short_price_negative_edge_guardrail=(
                args.short_price_negative_edge_guardrail
            ),
            short_price_negative_edge_max_decimal_odds=(
                args.short_price_negative_edge_max_decimal_odds
            ),
            short_price_negative_edge_min_probability=(
                args.short_price_negative_edge_min_probability
            ),
            short_price_negative_edge_max_model_edge=(
                args.short_price_negative_edge_max_model_edge
            ),
            short_price_negative_edge_soft_penalty=(
                args.short_price_negative_edge_soft_penalty
            ),
            short_price_negative_edge_soft_penalty_strength=(
                args.short_price_negative_edge_soft_penalty_strength
            ),
            short_price_negative_edge_soft_penalty_competition_ids=_csv_tuple(
                args.short_price_negative_edge_soft_penalty_competitions
            ),
        ),
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
    )


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _historical_slices_from_args(
    args: Namespace,
) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    if args.suite_manifest is None:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            resolved_slice_paths=list(args.slice_paths),
            slices=explicit_slices,
        )
    bundle = load_historical_recommendation_suite_manifest_bundle(args.suite_manifest)
    return _LoadedHistoricalSlices(
        slices=[*bundle.slices, *explicit_slices],
        resolved_slice_paths=[*bundle.resolved_slice_paths, *args.slice_paths],
        manifest_result=bundle,
        warnings=bundle.warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": (
            manifest_result.manifest.suite_id
            if manifest_result.manifest is not None
            else None
        ),
        "name": (
            manifest_result.manifest.name
            if manifest_result.manifest is not None
            else None
        ),
        "slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }
