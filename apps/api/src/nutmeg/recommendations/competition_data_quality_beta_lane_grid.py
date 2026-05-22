from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalMarketPrediction,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    build_historical_competition_season_index_by_slice_id,
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
    _summary_int,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalCompetitionDataQualityBetaLaneStatus = Literal["accepted", "rejected"]


class HistoricalCompetitionDataQualityBetaLaneGridOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    optimizer_profile: HistoricalOptimizerProfile = "solver"
    baseline_min_data_quality_score: float = Field(default=80.0, ge=0.0, le=100.0)
    beta_min_data_quality_score_values: tuple[float, ...] = (70.0,)
    competition_ids: tuple[str, ...] = ("FRA_LIGUE_2",)
    season_groups: tuple[tuple[str, ...], ...] = ((),)
    min_competition_season_index_values: tuple[int | None, ...] = (None,)
    max_competition_season_index_values: tuple[int | None, ...] = (None,)
    min_probability_values: tuple[float, ...] = (0.45, 0.50)
    max_decimal_odds_values: tuple[float, ...] = (2.30, 2.80)
    min_model_edge_values: tuple[float, ...] = (-0.02, 0.0)
    min_model_confidence_score_values: tuple[float, ...] = (0.66,)
    min_calibration_score_values: tuple[float, ...] = (0.70,)
    min_odds_stability_score_values: tuple[float, ...] = (0.90, 0.95)
    max_volatility_penalty_values: tuple[float, ...] = (0.08, 0.05)
    probability_repair_strength_values: tuple[float, ...] = (0.0,)
    probability_repair_max_delta_values: tuple[float, ...] = (0.0,)
    probability_repair_min_market_probability_delta_values: tuple[float, ...] = (0.0,)
    probability_repair_extra_uplift_values: tuple[float, ...] = (0.0,)
    probability_repair_data_quality_gap_weight_values: tuple[float, ...] = (0.0,)
    probability_repair_odds_stability_weight_values: tuple[float, ...] = (0.0,)
    probability_repair_max_probability_values: tuple[float, ...] = (1.0,)
    min_beta_lane_prediction_count: int = Field(default=1, ge=0)
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


class HistoricalCompetitionDataQualityBetaLaneCandidate(BaseModel):
    candidate_key: str
    status: HistoricalCompetitionDataQualityBetaLaneStatus
    competition_id: str
    season_ids: tuple[str, ...] = ()
    min_competition_season_index: int | None = Field(default=None, ge=1)
    max_competition_season_index: int | None = Field(default=None, ge=1)
    beta_min_data_quality_score: float = Field(ge=0.0, le=100.0)
    min_probability: float = Field(ge=0.0, le=1.0)
    max_decimal_odds: float = Field(gt=1.0)
    min_model_edge: float
    min_model_confidence_score: float = Field(ge=0.0, le=1.0)
    min_calibration_score: float = Field(ge=0.0, le=1.0)
    min_odds_stability_score: float = Field(ge=0.0, le=1.0)
    max_volatility_penalty: float = Field(ge=0.0, le=1.0)
    probability_repair_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    probability_repair_max_delta: float = Field(default=0.0, ge=0.0, le=1.0)
    probability_repair_min_market_probability_delta: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    probability_repair_extra_uplift: float = Field(default=0.0, ge=0.0, le=1.0)
    probability_repair_data_quality_gap_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    probability_repair_odds_stability_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    probability_repair_max_probability: float = Field(default=1.0, ge=0.0, le=1.0)
    beta_lane_prediction_count: int = Field(ge=0)
    beta_lane_fixture_count: int = Field(ge=0)
    probability_repair_candidate_count: int = Field(default=0, ge=0)
    probability_repair_candidate_pool_count: int = Field(default=0, ge=0)
    probability_repair_final_answer_selected_candidate_count: int = Field(
        default=0,
        ge=0,
    )
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


class HistoricalCompetitionDataQualityBetaLaneGridReport(BaseModel):
    report_key: str
    status: Literal["generated"]
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    candidates: list[HistoricalCompetitionDataQualityBetaLaneCandidate] = Field(
        default_factory=list
    )
    accepted_candidates: list[HistoricalCompetitionDataQualityBetaLaneCandidate] = (
        Field(default_factory=list)
    )
    best_candidate: HistoricalCompetitionDataQualityBetaLaneCandidate | None = None
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


def build_historical_competition_data_quality_beta_lane_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalCompetitionDataQualityBetaLaneGridOptions | None = None,
) -> HistoricalCompetitionDataQualityBetaLaneGridReport:
    resolved_options = _options_with_global_competition_season_context(
        options or HistoricalCompetitionDataQualityBetaLaneGridOptions(),
        historical_slices,
    )
    baseline_results = [
        run_historical_recommendation_backtest(
            historical_slice,
            options=_baseline_backtest_options(resolved_options),
        )
        for historical_slice in historical_slices
    ]
    warnings = [
        warning for result in baseline_results for warning in result.warnings
    ]
    candidates = [
        _evaluate_beta_lane_candidate(
            historical_slices,
            baseline_results=baseline_results,
            competition_id=competition_id,
            beta_min_data_quality_score=beta_min_data_quality_score,
            min_probability=min_probability,
            max_decimal_odds=max_decimal_odds,
            min_model_edge=min_model_edge,
            min_model_confidence_score=min_model_confidence_score,
            min_calibration_score=min_calibration_score,
            min_odds_stability_score=min_odds_stability_score,
            max_volatility_penalty=max_volatility_penalty,
            probability_repair_strength=probability_repair_strength,
            probability_repair_max_delta=probability_repair_max_delta,
            probability_repair_min_market_probability_delta=(
                probability_repair_min_market_probability_delta
            ),
            probability_repair_extra_uplift=probability_repair_extra_uplift,
            probability_repair_data_quality_gap_weight=(
                probability_repair_data_quality_gap_weight
            ),
            probability_repair_odds_stability_weight=(
                probability_repair_odds_stability_weight
            ),
            probability_repair_max_probability=probability_repair_max_probability,
            season_ids=season_ids,
            min_competition_season_index=min_competition_season_index,
            max_competition_season_index=max_competition_season_index,
            options=resolved_options,
        )
        for competition_id in resolved_options.competition_ids
        for season_ids in resolved_options.season_groups
        for min_competition_season_index in (
            resolved_options.min_competition_season_index_values
        )
        for max_competition_season_index in (
            resolved_options.max_competition_season_index_values
        )
        if _valid_min_max(
            min_competition_season_index,
            max_competition_season_index,
        )
        for beta_min_data_quality_score in resolved_options.beta_min_data_quality_score_values
        for min_probability in resolved_options.min_probability_values
        for max_decimal_odds in resolved_options.max_decimal_odds_values
        for min_model_edge in resolved_options.min_model_edge_values
        for min_model_confidence_score in resolved_options.min_model_confidence_score_values
        for min_calibration_score in resolved_options.min_calibration_score_values
        for min_odds_stability_score in resolved_options.min_odds_stability_score_values
        for max_volatility_penalty in resolved_options.max_volatility_penalty_values
        for probability_repair_strength in resolved_options.probability_repair_strength_values
        for probability_repair_max_delta in resolved_options.probability_repair_max_delta_values
        for probability_repair_min_market_probability_delta in (
            resolved_options.probability_repair_min_market_probability_delta_values
        )
        for probability_repair_extra_uplift in (
            resolved_options.probability_repair_extra_uplift_values
        )
        for probability_repair_data_quality_gap_weight in (
            resolved_options.probability_repair_data_quality_gap_weight_values
        )
        for probability_repair_odds_stability_weight in (
            resolved_options.probability_repair_odds_stability_weight_values
        )
        for probability_repair_max_probability in (
            resolved_options.probability_repair_max_probability_values
        )
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
            "historical_competition_data_quality_beta_lane_grid_v3_1"
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
        "season_groups": [list(group) for group in resolved_options.season_groups],
        "min_competition_season_index_values": list(
            resolved_options.min_competition_season_index_values
        ),
        "max_competition_season_index_values": list(
            resolved_options.max_competition_season_index_values
        ),
        "beta_min_data_quality_score_values": list(
            resolved_options.beta_min_data_quality_score_values
        ),
        "min_probability_values": list(resolved_options.min_probability_values),
        "max_decimal_odds_values": list(resolved_options.max_decimal_odds_values),
        "min_model_edge_values": list(resolved_options.min_model_edge_values),
        "min_odds_stability_score_values": list(
            resolved_options.min_odds_stability_score_values
        ),
        "max_volatility_penalty_values": list(
            resolved_options.max_volatility_penalty_values
        ),
        "probability_repair_strength_values": list(
            resolved_options.probability_repair_strength_values
        ),
        "probability_repair_max_delta_values": list(
            resolved_options.probability_repair_max_delta_values
        ),
        "probability_repair_min_market_probability_delta_values": list(
            resolved_options.probability_repair_min_market_probability_delta_values
        ),
        "probability_repair_extra_uplift_values": list(
            resolved_options.probability_repair_extra_uplift_values
        ),
        "probability_repair_data_quality_gap_weight_values": list(
            resolved_options.probability_repair_data_quality_gap_weight_values
        ),
        "probability_repair_odds_stability_weight_values": list(
            resolved_options.probability_repair_odds_stability_weight_values
        ),
        "probability_repair_max_probability_values": list(
            resolved_options.probability_repair_max_probability_values
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
    return HistoricalCompetitionDataQualityBetaLaneGridReport(
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


def _options_with_global_competition_season_context(
    options: HistoricalCompetitionDataQualityBetaLaneGridOptions,
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> HistoricalCompetitionDataQualityBetaLaneGridOptions:
    if options.backtest_options.competition_season_index_by_slice_id:
        return options
    return options.model_copy(
        update={
            "backtest_options": options.backtest_options.model_copy(
                update={
                    "competition_season_index_by_slice_id": (
                        build_historical_competition_season_index_by_slice_id(
                            historical_slices
                        )
                    )
                }
            )
        }
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded = _historical_slices_from_args(args)
    report = build_historical_competition_data_quality_beta_lane_grid_report(
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
    options: HistoricalCompetitionDataQualityBetaLaneGridOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.backtest_options.model_copy(
        update={
            "optimizer_profile": options.optimizer_profile,
            "min_data_quality_score": options.baseline_min_data_quality_score,
            "min_data_quality_score_by_competition_id": {},
            "data_quality_beta_lane_enabled": False,
        }
    )


def _candidate_backtest_options(
    options: HistoricalCompetitionDataQualityBetaLaneGridOptions,
    *,
    competition_id: str,
    season_ids: tuple[str, ...],
    min_competition_season_index: int | None,
    max_competition_season_index: int | None,
    beta_min_data_quality_score: float,
    min_probability: float,
    max_decimal_odds: float,
    min_model_edge: float,
    min_model_confidence_score: float,
    min_calibration_score: float,
    min_odds_stability_score: float,
    max_volatility_penalty: float,
    probability_repair_strength: float,
    probability_repair_max_delta: float,
    probability_repair_min_market_probability_delta: float,
    probability_repair_extra_uplift: float,
    probability_repair_data_quality_gap_weight: float,
    probability_repair_odds_stability_weight: float,
    probability_repair_max_probability: float,
) -> HistoricalRecommendationBacktestOptions:
    probability_repair_enabled = probability_repair_max_delta > 0 and any(
        value > 0
        for value in (
            probability_repair_strength,
            probability_repair_extra_uplift,
            probability_repair_data_quality_gap_weight,
            probability_repair_odds_stability_weight,
        )
    )
    return options.backtest_options.model_copy(
        update={
            "optimizer_profile": options.optimizer_profile,
            "min_data_quality_score": options.baseline_min_data_quality_score,
            "min_data_quality_score_by_competition_id": {
                competition_id: beta_min_data_quality_score,
            },
            "data_quality_beta_lane_enabled": True,
            "data_quality_beta_lane_competition_ids": (competition_id,),
            "data_quality_beta_lane_season_ids": season_ids,
            "data_quality_beta_lane_min_competition_season_index": (
                min_competition_season_index
            ),
            "data_quality_beta_lane_max_competition_season_index": (
                max_competition_season_index
            ),
            "data_quality_beta_lane_min_probability": min_probability,
            "data_quality_beta_lane_max_decimal_odds": max_decimal_odds,
            "data_quality_beta_lane_min_model_edge": min_model_edge,
            "data_quality_beta_lane_min_model_confidence_score": (
                min_model_confidence_score
            ),
            "data_quality_beta_lane_min_calibration_score": min_calibration_score,
            "data_quality_beta_lane_min_odds_stability_score": (
                min_odds_stability_score
            ),
            "data_quality_beta_lane_max_volatility_penalty": max_volatility_penalty,
            "data_quality_beta_lane_probability_repair_enabled": (
                probability_repair_enabled
            ),
            "data_quality_beta_lane_probability_repair_strength": (
                probability_repair_strength
            ),
            "data_quality_beta_lane_probability_repair_max_delta": (
                probability_repair_max_delta
            ),
            "data_quality_beta_lane_probability_repair_min_market_probability_delta": (
                probability_repair_min_market_probability_delta
            ),
            "data_quality_beta_lane_probability_repair_extra_uplift": (
                probability_repair_extra_uplift
            ),
            "data_quality_beta_lane_probability_repair_data_quality_gap_weight": (
                probability_repair_data_quality_gap_weight
            ),
            "data_quality_beta_lane_probability_repair_odds_stability_weight": (
                probability_repair_odds_stability_weight
            ),
            "data_quality_beta_lane_probability_repair_max_probability": (
                probability_repair_max_probability
            ),
        }
    )


def _evaluate_beta_lane_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_results: Sequence[HistoricalRecommendationBacktestResult],
    competition_id: str,
    season_ids: tuple[str, ...],
    min_competition_season_index: int | None,
    max_competition_season_index: int | None,
    beta_min_data_quality_score: float,
    min_probability: float,
    max_decimal_odds: float,
    min_model_edge: float,
    min_model_confidence_score: float,
    min_calibration_score: float,
    min_odds_stability_score: float,
    max_volatility_penalty: float,
    probability_repair_strength: float,
    probability_repair_max_delta: float,
    probability_repair_min_market_probability_delta: float,
    probability_repair_extra_uplift: float,
    probability_repair_data_quality_gap_weight: float,
    probability_repair_odds_stability_weight: float,
    probability_repair_max_probability: float,
    options: HistoricalCompetitionDataQualityBetaLaneGridOptions,
) -> HistoricalCompetitionDataQualityBetaLaneCandidate:
    candidate_options = _candidate_backtest_options(
        options,
        competition_id=competition_id,
        season_ids=season_ids,
        min_competition_season_index=min_competition_season_index,
        max_competition_season_index=max_competition_season_index,
        beta_min_data_quality_score=beta_min_data_quality_score,
        min_probability=min_probability,
        max_decimal_odds=max_decimal_odds,
        min_model_edge=min_model_edge,
        min_model_confidence_score=min_model_confidence_score,
        min_calibration_score=min_calibration_score,
        min_odds_stability_score=min_odds_stability_score,
        max_volatility_penalty=max_volatility_penalty,
        probability_repair_strength=probability_repair_strength,
        probability_repair_max_delta=probability_repair_max_delta,
        probability_repair_min_market_probability_delta=(
            probability_repair_min_market_probability_delta
        ),
        probability_repair_extra_uplift=probability_repair_extra_uplift,
        probability_repair_data_quality_gap_weight=(
            probability_repair_data_quality_gap_weight
        ),
        probability_repair_odds_stability_weight=(
            probability_repair_odds_stability_weight
        ),
        probability_repair_max_probability=probability_repair_max_probability,
    )
    candidate_results = [
        run_historical_recommendation_backtest(
            historical_slice,
            options=candidate_options,
        )
        for historical_slice in historical_slices
    ]
    deltas = _threshold_deltas(baseline_results, candidate_results)
    beta_lane_prediction_count = _beta_lane_prediction_count(
        historical_slices,
        competition_id=competition_id,
        season_ids=season_ids,
        min_competition_season_index=min_competition_season_index,
        max_competition_season_index=max_competition_season_index,
        competition_season_index_by_slice_id=(
            options.backtest_options.competition_season_index_by_slice_id
        ),
        beta_min_data_quality_score=beta_min_data_quality_score,
        baseline_threshold=options.baseline_min_data_quality_score,
        min_probability=min_probability,
        max_decimal_odds=max_decimal_odds,
        min_model_edge=min_model_edge,
        min_model_confidence_score=min_model_confidence_score,
        min_calibration_score=min_calibration_score,
        min_odds_stability_score=min_odds_stability_score,
        max_volatility_penalty=max_volatility_penalty,
    )
    beta_lane_fixture_count = _beta_lane_fixture_count(
        historical_slices,
        competition_id=competition_id,
        season_ids=season_ids,
        min_competition_season_index=min_competition_season_index,
        max_competition_season_index=max_competition_season_index,
        competition_season_index_by_slice_id=(
            options.backtest_options.competition_season_index_by_slice_id
        ),
        beta_min_data_quality_score=beta_min_data_quality_score,
        baseline_threshold=options.baseline_min_data_quality_score,
        min_probability=min_probability,
        max_decimal_odds=max_decimal_odds,
        min_model_edge=min_model_edge,
        min_model_confidence_score=min_model_confidence_score,
        min_calibration_score=min_calibration_score,
        min_odds_stability_score=min_odds_stability_score,
        max_volatility_penalty=max_volatility_penalty,
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
        beta_lane_prediction_count=beta_lane_prediction_count,
        objective_improvement_satisfied=objective_improvement_satisfied,
        options=options,
    )
    status: HistoricalCompetitionDataQualityBetaLaneStatus = (
        "accepted" if not reason_codes else "rejected"
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_competition_data_quality_beta_lane_candidate_v3_1"
        ),
        "status": status,
        "competition_id": competition_id,
        "season_ids": list(season_ids),
        "min_competition_season_index": min_competition_season_index,
        "max_competition_season_index": max_competition_season_index,
        "beta_min_data_quality_score": beta_min_data_quality_score,
        "min_probability": min_probability,
        "max_decimal_odds": max_decimal_odds,
        "min_model_edge": min_model_edge,
        "min_model_confidence_score": min_model_confidence_score,
        "min_calibration_score": min_calibration_score,
        "min_odds_stability_score": min_odds_stability_score,
        "max_volatility_penalty": max_volatility_penalty,
        "probability_repair_strength": probability_repair_strength,
        "probability_repair_max_delta": probability_repair_max_delta,
        "probability_repair_min_market_probability_delta": (
            probability_repair_min_market_probability_delta
        ),
        "probability_repair_extra_uplift": probability_repair_extra_uplift,
        "probability_repair_data_quality_gap_weight": (
            probability_repair_data_quality_gap_weight
        ),
        "probability_repair_odds_stability_weight": (
            probability_repair_odds_stability_weight
        ),
        "probability_repair_max_probability": probability_repair_max_probability,
        "beta_lane_prediction_count": beta_lane_prediction_count,
        "beta_lane_fixture_count": beta_lane_fixture_count,
        "probability_repair_candidate_count": (
            _probability_repair_candidate_count(candidate_results)
        ),
        "probability_repair_candidate_pool_count": (
            _probability_repair_candidate_pool_count(candidate_results)
        ),
        "probability_repair_final_answer_selected_candidate_count": (
            _probability_repair_final_answer_selected_candidate_count(candidate_results)
        ),
        "objective_improvement_satisfied": objective_improvement_satisfied,
        "objective_improvement_metric_codes": objective_metric_codes,
        "reason_codes": reason_codes,
        "deltas": deltas,
    }
    candidate_key = _candidate_key(summary)
    return HistoricalCompetitionDataQualityBetaLaneCandidate(
        candidate_key=candidate_key,
        status=status,
        competition_id=competition_id,
        season_ids=season_ids,
        min_competition_season_index=min_competition_season_index,
        max_competition_season_index=max_competition_season_index,
        beta_min_data_quality_score=beta_min_data_quality_score,
        min_probability=min_probability,
        max_decimal_odds=max_decimal_odds,
        min_model_edge=min_model_edge,
        min_model_confidence_score=min_model_confidence_score,
        min_calibration_score=min_calibration_score,
        min_odds_stability_score=min_odds_stability_score,
        max_volatility_penalty=max_volatility_penalty,
        probability_repair_strength=probability_repair_strength,
        probability_repair_max_delta=probability_repair_max_delta,
        probability_repair_min_market_probability_delta=(
            probability_repair_min_market_probability_delta
        ),
        probability_repair_extra_uplift=probability_repair_extra_uplift,
        probability_repair_data_quality_gap_weight=(
            probability_repair_data_quality_gap_weight
        ),
        probability_repair_odds_stability_weight=(
            probability_repair_odds_stability_weight
        ),
        probability_repair_max_probability=probability_repair_max_probability,
        beta_lane_prediction_count=beta_lane_prediction_count,
        beta_lane_fixture_count=beta_lane_fixture_count,
        probability_repair_candidate_count=_probability_repair_candidate_count(
            candidate_results
        ),
        probability_repair_candidate_pool_count=(
            _probability_repair_candidate_pool_count(candidate_results)
        ),
        probability_repair_final_answer_selected_candidate_count=(
            _probability_repair_final_answer_selected_candidate_count(candidate_results)
        ),
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


def _probability_repair_candidate_count(
    candidate_results: Sequence[HistoricalRecommendationBacktestResult],
) -> int:
    return sum(
        _summary_int(
            result.summary_json,
            "data_quality_beta_lane_probability_repair_candidate_count",
        )
        for result in candidate_results
    )


def _probability_repair_candidate_pool_count(
    candidate_results: Sequence[HistoricalRecommendationBacktestResult],
) -> int:
    return sum(
        _summary_int(
            result.summary_json,
            "data_quality_beta_lane_probability_repair_candidate_pool_count",
        )
        for result in candidate_results
    )


def _probability_repair_final_answer_selected_candidate_count(
    candidate_results: Sequence[HistoricalRecommendationBacktestResult],
) -> int:
    return sum(
        _summary_int(
            result.summary_json,
            "data_quality_beta_lane_probability_repair_final_answer_selected_candidate_count",
        )
        for result in candidate_results
    )


def _beta_lane_prediction_count(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    competition_id: str,
    season_ids: tuple[str, ...],
    min_competition_season_index: int | None,
    max_competition_season_index: int | None,
    competition_season_index_by_slice_id: Mapping[str, int],
    beta_min_data_quality_score: float,
    baseline_threshold: float,
    min_probability: float,
    max_decimal_odds: float,
    min_model_edge: float,
    min_model_confidence_score: float,
    min_calibration_score: float,
    min_odds_stability_score: float,
    max_volatility_penalty: float,
) -> int:
    return sum(
        1
        for historical_slice in historical_slices
        if _slice_satisfies_beta_lane_regime(
            historical_slice,
            season_ids=season_ids,
            min_competition_season_index=min_competition_season_index,
            max_competition_season_index=max_competition_season_index,
            competition_season_index_by_slice_id=competition_season_index_by_slice_id,
        )
        for fixture in historical_slice.fixtures
        if fixture.competition_id == competition_id
        for prediction in fixture.predictions
        if _prediction_satisfies_beta_lane(
            prediction,
            beta_min_data_quality_score=beta_min_data_quality_score,
            baseline_threshold=baseline_threshold,
            min_probability=min_probability,
            max_decimal_odds=max_decimal_odds,
            min_model_edge=min_model_edge,
            min_model_confidence_score=min_model_confidence_score,
            min_calibration_score=min_calibration_score,
            min_odds_stability_score=min_odds_stability_score,
            max_volatility_penalty=max_volatility_penalty,
        )
    )


def _beta_lane_fixture_count(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    competition_id: str,
    season_ids: tuple[str, ...],
    min_competition_season_index: int | None,
    max_competition_season_index: int | None,
    competition_season_index_by_slice_id: Mapping[str, int],
    beta_min_data_quality_score: float,
    baseline_threshold: float,
    min_probability: float,
    max_decimal_odds: float,
    min_model_edge: float,
    min_model_confidence_score: float,
    min_calibration_score: float,
    min_odds_stability_score: float,
    max_volatility_penalty: float,
) -> int:
    return len(
        {
            fixture.fixture_id
            for historical_slice in historical_slices
            if _slice_satisfies_beta_lane_regime(
                historical_slice,
                season_ids=season_ids,
                min_competition_season_index=min_competition_season_index,
                max_competition_season_index=max_competition_season_index,
                competition_season_index_by_slice_id=(
                    competition_season_index_by_slice_id
                ),
            )
            for fixture in historical_slice.fixtures
            if fixture.competition_id == competition_id
            if any(
                _prediction_satisfies_beta_lane(
                    prediction,
                    beta_min_data_quality_score=beta_min_data_quality_score,
                    baseline_threshold=baseline_threshold,
                    min_probability=min_probability,
                    max_decimal_odds=max_decimal_odds,
                    min_model_edge=min_model_edge,
                    min_model_confidence_score=min_model_confidence_score,
                    min_calibration_score=min_calibration_score,
                    min_odds_stability_score=min_odds_stability_score,
                    max_volatility_penalty=max_volatility_penalty,
                )
                for prediction in fixture.predictions
            )
        }
    )


def _prediction_satisfies_beta_lane(
    prediction: HistoricalMarketPrediction,
    *,
    beta_min_data_quality_score: float,
    baseline_threshold: float,
    min_probability: float,
    max_decimal_odds: float,
    min_model_edge: float,
    min_model_confidence_score: float,
    min_calibration_score: float,
    min_odds_stability_score: float,
    max_volatility_penalty: float,
) -> bool:
    if not beta_min_data_quality_score <= prediction.data_quality_score < baseline_threshold:
        return False
    if prediction.probability < min_probability:
        return False
    if prediction.decimal_odds > max_decimal_odds:
        return False
    if _prediction_model_edge(prediction) < min_model_edge:
        return False
    if prediction.model_confidence_score < min_model_confidence_score:
        return False
    if prediction.calibration_score < min_calibration_score:
        return False
    if prediction.odds_stability_score < min_odds_stability_score:
        return False
    return prediction.volatility_penalty <= max_volatility_penalty


def _slice_satisfies_beta_lane_regime(
    historical_slice: HistoricalRecommendationSlice,
    *,
    season_ids: tuple[str, ...],
    min_competition_season_index: int | None,
    max_competition_season_index: int | None,
    competition_season_index_by_slice_id: Mapping[str, int],
) -> bool:
    if season_ids and historical_slice.metadata.season not in set(season_ids):
        return False
    if min_competition_season_index is None and max_competition_season_index is None:
        return True
    season_index = competition_season_index_by_slice_id.get(
        historical_slice.metadata.slice_id
    )
    if season_index is None:
        return False
    if (
        min_competition_season_index is not None
        and season_index < min_competition_season_index
    ):
        return False
    return not (
        max_competition_season_index is not None
        and season_index > max_competition_season_index
    )


def _prediction_model_edge(prediction: HistoricalMarketPrediction) -> float:
    if prediction.model_edge is not None:
        return prediction.model_edge
    if prediction.market_probability is not None:
        return prediction.probability - prediction.market_probability
    return prediction.probability - 1.0 / prediction.decimal_odds


def _reason_codes(
    deltas: Mapping[str, object],
    *,
    beta_lane_prediction_count: int,
    objective_improvement_satisfied: bool,
    options: HistoricalCompetitionDataQualityBetaLaneGridOptions,
) -> list[str]:
    reason_codes: list[str] = []
    if beta_lane_prediction_count < options.min_beta_lane_prediction_count:
        reason_codes.append(
            "competition_data_quality_beta_lane:beta_lane_prediction_count_too_low"
        )
    if (
        _int_delta(deltas, "final_hit_sample_size_delta")
        < options.min_final_hit_sample_size_delta
    ):
        reason_codes.append(
            "competition_data_quality_beta_lane:final_hit_sample_size_regressed"
        )
    if _int_delta(deltas, "final_hit_count_delta") < options.min_final_hit_count_delta:
        reason_codes.append("competition_data_quality_beta_lane:final_hit_count_regressed")
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="final_hit_rate_delta",
        threshold=options.min_final_hit_rate_delta,
        reason_code="competition_data_quality_beta_lane:final_hit_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="roi_delta",
        threshold=options.min_roi_delta,
        reason_code="competition_data_quality_beta_lane:roi_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="profit_loss_delta",
        threshold=options.min_profit_loss_delta,
        reason_code="competition_data_quality_beta_lane:profit_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="final_hit_harm_count_vs_baseline",
        threshold=options.max_final_hit_harm_count_vs_baseline,
        reason_code=(
            "competition_data_quality_beta_lane:final_hit_harm_count_above_threshold"
        ),
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="profit_loss_harm_count_vs_baseline",
        threshold=options.max_profit_loss_harm_count_vs_baseline,
        reason_code=(
            "competition_data_quality_beta_lane:profit_loss_harm_count_above_threshold"
        ),
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="brier_score_delta",
        threshold=options.max_brier_score_delta,
        reason_code="competition_data_quality_beta_lane:brier_score_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="log_loss_delta",
        threshold=options.max_log_loss_delta,
        reason_code="competition_data_quality_beta_lane:log_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="mean_calibration_error_delta",
        threshold=options.max_mean_calibration_error_delta,
        reason_code=(
            "competition_data_quality_beta_lane:mean_calibration_error_regressed"
        ),
        epsilon=options.comparison_epsilon,
    )
    if not objective_improvement_satisfied:
        reason_codes.append("competition_data_quality_beta_lane:objective_improvement_missing")
    return reason_codes


def _objective_improvement_metric_codes(
    deltas: Mapping[str, object],
    *,
    options: HistoricalCompetitionDataQualityBetaLaneGridOptions,
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
    candidates: Sequence[HistoricalCompetitionDataQualityBetaLaneCandidate],
) -> HistoricalCompetitionDataQualityBetaLaneCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key, reverse=True)[0]


def _candidate_sort_key(
    candidate: HistoricalCompetitionDataQualityBetaLaneCandidate,
) -> tuple[int, float, float, float, float, int, int, int, str]:
    return (
        1 if candidate.status == "accepted" else 0,
        _number(candidate.deltas_json, "final_hit_rate_delta") or -999.0,
        _number(candidate.deltas_json, "roi_delta") or -999.0,
        _number(candidate.deltas_json, "profit_loss_delta") or -999.0,
        -(_number(candidate.deltas_json, "brier_score_delta") or 999.0),
        -candidate.final_hit_harm_count_vs_baseline,
        -candidate.profit_loss_harm_count_vs_baseline,
        candidate.beta_lane_prediction_count,
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
        description="Search beta-quality lane filters inside the 70-79 data band."
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
    parser.add_argument("--beta-min-data-quality-score-values", default="70")
    parser.add_argument("--competitions", default="FRA_LIGUE_2")
    parser.add_argument("--season-group", action="append", default=[])
    parser.add_argument("--min-competition-season-index-values", default="none")
    parser.add_argument("--max-competition-season-index-values", default="none")
    parser.add_argument("--beta-min-probability-values", default="0.45,0.50")
    parser.add_argument("--beta-max-decimal-odds-values", default="2.30,2.80")
    parser.add_argument("--beta-min-model-edge-values", default="-0.02,0.0")
    parser.add_argument("--beta-min-model-confidence-score-values", default="0.66")
    parser.add_argument("--beta-min-calibration-score-values", default="0.70")
    parser.add_argument("--beta-min-odds-stability-score-values", default="0.90,0.95")
    parser.add_argument("--beta-max-volatility-penalty-values", default="0.08,0.05")
    parser.add_argument("--probability-repair-strength-values", default="0.0")
    parser.add_argument("--probability-repair-max-delta-values", default="0.0")
    parser.add_argument(
        "--probability-repair-min-market-probability-delta-values",
        default="0.0",
    )
    parser.add_argument("--probability-repair-extra-uplift-values", default="0.0")
    parser.add_argument(
        "--probability-repair-data-quality-gap-weight-values",
        default="0.0",
    )
    parser.add_argument(
        "--probability-repair-odds-stability-weight-values",
        default="0.0",
    )
    parser.add_argument("--probability-repair-max-probability-values", default="1.0")
    parser.add_argument("--min-beta-lane-prediction-count", type=int, default=1)
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


def _options_from_args(args: Namespace) -> HistoricalCompetitionDataQualityBetaLaneGridOptions:
    return HistoricalCompetitionDataQualityBetaLaneGridOptions(
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
        beta_min_data_quality_score_values=_float_tuple(
            args.beta_min_data_quality_score_values
        ),
        competition_ids=tuple(_csv(args.competitions)),
        season_groups=_string_groups_from_args(args.season_group, default=((),)),
        min_competition_season_index_values=_optional_int_tuple(
            args.min_competition_season_index_values
        ),
        max_competition_season_index_values=_optional_int_tuple(
            args.max_competition_season_index_values
        ),
        min_probability_values=_float_tuple(args.beta_min_probability_values),
        max_decimal_odds_values=_float_tuple(args.beta_max_decimal_odds_values),
        min_model_edge_values=_float_tuple(args.beta_min_model_edge_values),
        min_model_confidence_score_values=_float_tuple(
            args.beta_min_model_confidence_score_values
        ),
        min_calibration_score_values=_float_tuple(
            args.beta_min_calibration_score_values
        ),
        min_odds_stability_score_values=_float_tuple(
            args.beta_min_odds_stability_score_values
        ),
        max_volatility_penalty_values=_float_tuple(
            args.beta_max_volatility_penalty_values
        ),
        probability_repair_strength_values=_float_tuple(
            args.probability_repair_strength_values
        ),
        probability_repair_max_delta_values=_float_tuple(
            args.probability_repair_max_delta_values
        ),
        probability_repair_min_market_probability_delta_values=_float_tuple(
            args.probability_repair_min_market_probability_delta_values
        ),
        probability_repair_extra_uplift_values=_float_tuple(
            args.probability_repair_extra_uplift_values
        ),
        probability_repair_data_quality_gap_weight_values=_float_tuple(
            args.probability_repair_data_quality_gap_weight_values
        ),
        probability_repair_odds_stability_weight_values=_float_tuple(
            args.probability_repair_odds_stability_weight_values
        ),
        probability_repair_max_probability_values=_float_tuple(
            args.probability_repair_max_probability_values
        ),
        min_beta_lane_prediction_count=args.min_beta_lane_prediction_count,
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


def _string_groups_from_args(
    values: Sequence[str],
    *,
    default: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    if not values:
        return default
    groups = tuple(tuple(_csv(value)) for value in values)
    return groups or default


def _optional_int_tuple(value: str) -> tuple[int | None, ...]:
    items = _csv(value)
    if not items:
        return (None,)
    return tuple(None if item.lower() == "none" else int(item) for item in items)


def _valid_min_max(
    minimum: float | int | None,
    maximum: float | int | None,
) -> bool:
    return minimum is None or maximum is None or minimum <= maximum


def _candidate_key(summary: Mapping[str, object]) -> str:
    digest = sha256(dumps(summary, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"historical_competition_data_quality_beta_lane:{digest}"


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
    return f"historical_competition_data_quality_beta_lane_grid:{digest}"
