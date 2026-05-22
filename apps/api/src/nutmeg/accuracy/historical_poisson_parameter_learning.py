from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_poisson_walk_forward import (
    DEFAULT_EMA_FORM_HALF_LIFE_MATCHES,
    DEFAULT_FORM_WINDOW_MATCHES,
    DEFAULT_MAX_LAMBDA_ADJUSTMENT,
    DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT,
    DEFAULT_PRIOR_SEASON_WEIGHT,
    DEFAULT_REST_REFERENCE_DAYS,
    DEFAULT_STRENGTH_SHRINKAGE_MATCHES,
    HistoricalPoissonLambdaMethod,
    HistoricalPoissonWalkForwardComparisonGroup,
    HistoricalPoissonWalkForwardMetricSet,
    HistoricalPoissonWalkForwardOptions,
    HistoricalPoissonWalkForwardReport,
    HistoricalWalkForwardScoreGridFamily,
    build_historical_poisson_walk_forward_report,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalPoissonParameterLearningStatus = Literal["generated"]
type HistoricalPoissonParameterSelectionMetric = Literal[
    "brier_score_delta",
    "log_loss_delta",
    "expected_calibration_error_delta",
    "no_harm_score",
]


class HistoricalPoissonParameterLearningOptions(BaseModel):
    holdout_season_count: int = Field(default=1, ge=1)
    min_training_season_count: int = Field(default=2, ge=1)
    min_validation_sample_size: int = Field(default=100, ge=1)
    selection_metric: HistoricalPoissonParameterSelectionMetric = "brier_score_delta"
    selection_primary_metric_weight: float = Field(default=1.0, ge=0.0)
    selection_hit_rate_regression_penalty: float = Field(default=10.0, ge=0.0)
    selection_brier_regression_penalty: float = Field(default=5.0, ge=0.0)
    selection_log_loss_regression_penalty: float = Field(default=2.0, ge=0.0)
    selection_calibration_regression_penalty: float = Field(default=2.0, ge=0.0)
    selection_actual_probability_regression_penalty: float = Field(
        default=2.0,
        ge=0.0,
    )
    selection_min_model_signal_weight: float = Field(default=0.05, ge=0.0, le=1.0)
    selection_low_model_signal_penalty: float = Field(default=1.0, ge=0.0)
    lambda_method: HistoricalPoissonLambdaMethod = "rolling_strength"
    include_poisson_candidates: bool = True
    include_dixon_coles_candidates: bool = True
    candidate_draw_correction_weights: tuple[float, ...] = (0.0, 0.40)
    candidate_market_anchor_weights: tuple[float, ...] = (0.0,)
    candidate_dixon_coles_rhos: tuple[float, ...] = (-0.10, -0.05, 0.05)
    candidate_form_adjustment_weights: tuple[float, ...] = (0.0,)
    candidate_ema_form_half_life_matches: tuple[float, ...] = Field(
        default_factory=tuple
    )
    candidate_prior_season_weights: tuple[float, ...] = Field(default_factory=tuple)
    candidate_rest_adjustment_weights: tuple[float, ...] = (0.0,)
    candidate_prematch_feature_odds_movement_weights: tuple[float, ...] = (0.0,)
    candidate_prematch_feature_draw_risk_weights: tuple[float, ...] = (0.0,)
    candidate_max_prematch_feature_lambda_adjustments: tuple[float, ...] = (
        DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT,
    )
    candidate_recency_half_life_days: tuple[float | None, ...] = Field(
        default_factory=tuple
    )
    candidate_home_away_split_weights: tuple[float, ...] = Field(default_factory=tuple)
    candidate_strength_shrinkage_matches: tuple[float, ...] = Field(
        default_factory=tuple
    )
    min_prior_matches: int = Field(default=60, ge=0)
    min_team_matches: int = Field(default=5, ge=1)
    max_training_results: int = Field(default=380, ge=1)
    max_goals: int = Field(default=8, ge=1, le=20)
    bucket_size: float = Field(default=0.10, gt=0.0, le=1.0)
    min_bucket_sample_size: int = Field(default=30, ge=1)
    recency_half_life_days: float | None = Field(default=None, gt=0.0)
    home_away_split_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    strength_shrinkage_matches: float = Field(
        default=DEFAULT_STRENGTH_SHRINKAGE_MATCHES,
        ge=0.0,
        le=80.0,
    )
    prior_season_weight: float = Field(
        default=DEFAULT_PRIOR_SEASON_WEIGHT,
        ge=0.0,
        le=1.0,
    )
    form_window_matches: int = Field(default=DEFAULT_FORM_WINDOW_MATCHES, ge=1)
    ema_form_half_life_matches: float = Field(
        default=DEFAULT_EMA_FORM_HALF_LIFE_MATCHES,
        gt=0.0,
        le=20.0,
    )
    rest_reference_days: float = Field(default=DEFAULT_REST_REFERENCE_DAYS, gt=0.0)
    max_lambda_adjustment: float = Field(
        default=DEFAULT_MAX_LAMBDA_ADJUSTMENT,
        ge=0.0,
        le=1.0,
    )
    min_prematch_feature_data_quality_score: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
    )
    prematch_feature_lineup_strength_weight: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
    )
    prematch_feature_availability_risk_weight: float = Field(
        default=0.06,
        ge=0.0,
        le=1.0,
    )
    prematch_feature_semantic_risk_weight: float = Field(
        default=0.04,
        ge=0.0,
        le=1.0,
    )
    model_version_prefix: str = "learned-league-parameter-v3.1"
    feature_version: str = "rolling-results-team-strength-v1"
    calibration_version_prefix: str = "learned-league-draw-rho-v3.1"
    prediction_sample_limit: int = Field(default=0, ge=0)


class HistoricalPoissonParameterCandidate(BaseModel):
    candidate_key: str
    lambda_method: HistoricalPoissonLambdaMethod
    score_grid_family: HistoricalWalkForwardScoreGridFamily
    dixon_coles_rho: float | None = Field(default=None, ge=-0.5, le=0.5)
    draw_correction_weight: float = Field(ge=0.0, le=1.0)
    market_anchor_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    recency_half_life_days: float | None = Field(default=None, gt=0.0)
    home_away_split_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    strength_shrinkage_matches: float = Field(default=0.0, ge=0.0, le=80.0)
    prior_season_weight: float = Field(
        default=DEFAULT_PRIOR_SEASON_WEIGHT,
        ge=0.0,
        le=1.0,
    )
    ema_form_half_life_matches: float = Field(
        default=DEFAULT_EMA_FORM_HALF_LIFE_MATCHES,
        gt=0.0,
        le=20.0,
    )
    form_adjustment_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    rest_adjustment_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    prematch_feature_odds_movement_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
    )
    prematch_feature_draw_risk_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    max_prematch_feature_lambda_adjustment: float = Field(
        default=DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT,
        ge=0.0,
        le=0.50,
    )


class HistoricalPoissonParameterCandidateTrainingResult(BaseModel):
    candidate: HistoricalPoissonParameterCandidate
    training_report_key: str
    training_sample_size: int = Field(ge=0)
    training_candidate: HistoricalPoissonWalkForwardMetricSet
    training_baseline: HistoricalPoissonWalkForwardMetricSet
    training_deltas_json: dict[str, object] = Field(default_factory=dict)
    selection_metric_value: float | None = None
    selection_summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPoissonCompetitionParameterLearningResult(BaseModel):
    competition_id: str
    training_seasons: list[str] = Field(default_factory=list)
    validation_seasons: list[str] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    training_fixture_count: int = Field(ge=0)
    validation_fixture_count: int = Field(ge=0)
    selected_candidate: HistoricalPoissonParameterCandidate | None = None
    selected_training_result: HistoricalPoissonParameterCandidateTrainingResult | None = None
    selected_validation_report_key: str | None = None
    selected_validation: HistoricalPoissonWalkForwardComparisonGroup | None = None
    baseline_validation: HistoricalPoissonWalkForwardMetricSet | None = None
    status: str
    warnings: list[str] = Field(default_factory=list)
    training_results: list[HistoricalPoissonParameterCandidateTrainingResult] = Field(
        default_factory=list
    )
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPoissonParameterLearningReport(BaseModel):
    report_key: str
    status: HistoricalPoissonParameterLearningStatus
    competition_count: int = Field(ge=0)
    learned_competition_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    selected_candidate_counts: dict[str, int] = Field(default_factory=dict)
    overall_validation_candidate: HistoricalPoissonWalkForwardMetricSet | None = None
    overall_validation_baseline: HistoricalPoissonWalkForwardMetricSet | None = None
    overall_validation_deltas_json: dict[str, object] = Field(default_factory=dict)
    competitions: list[HistoricalPoissonCompetitionParameterLearningResult] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_poisson_parameter_learning_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPoissonParameterLearningOptions | None = None,
) -> HistoricalPoissonParameterLearningReport:
    resolved_options = options or HistoricalPoissonParameterLearningOptions()
    candidates = _candidate_grid(resolved_options)
    competition_results = [
        _competition_learning_result(
            competition_id,
            slices=competition_slices,
            candidates=candidates,
            options=resolved_options,
        )
        for competition_id, competition_slices in sorted(
            _slices_by_competition(historical_slices).items()
        )
    ]
    learned_results = [
        result for result in competition_results if result.status == "learned"
    ]
    overall_candidate = _combine_metric_sets(
        [
            result.selected_validation.candidate
            for result in learned_results
            if result.selected_validation is not None
        ]
    )
    overall_baseline = _combine_metric_sets(
        [
            result.selected_validation.baseline
            for result in learned_results
            if result.selected_validation is not None
        ]
    )
    selected_counts = Counter(
        result.selected_candidate.candidate_key
        for result in learned_results
        if result.selected_candidate is not None
    )
    warnings = [
        warning for result in competition_results for warning in result.warnings
    ]
    if not learned_results:
        warnings.append("historical_poisson_parameter_learning:no_learned_competitions")
    report_key = _report_key(
        historical_slices,
        candidates=candidates,
        options=resolved_options,
    )
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    validation_count = (
        overall_candidate.sample_size if overall_candidate is not None else 0
    )
    deltas = (
        _metric_deltas(overall_candidate, overall_baseline)
        if overall_candidate is not None and overall_baseline is not None
        else {}
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_poisson_parameter_learning_v3_1",
        "report_key": report_key,
        "selection_metric": resolved_options.selection_metric,
        "selection_no_harm_options": _selection_no_harm_options_summary(
            resolved_options
        ),
        "holdout_season_count": resolved_options.holdout_season_count,
        "candidate_count": len(candidates),
        "candidate_market_anchor_weights": _market_anchor_weight_grid(
            resolved_options
        ),
        "candidate_recency_half_life_days": _recency_grid(resolved_options),
        "candidate_home_away_split_weights": _home_away_split_weight_grid(
            resolved_options
        ),
        "candidate_strength_shrinkage_matches": _strength_shrinkage_grid(
            resolved_options
        ),
        "candidate_ema_form_half_life_matches": _ema_form_half_life_grid(
            resolved_options
        ),
        "candidate_prior_season_weights": _prior_season_weight_grid(
            resolved_options
        ),
        "candidate_prematch_feature_weight_grid": (
            _prematch_feature_weight_grid(resolved_options)
        ),
        "competition_count": len(competition_results),
        "learned_competition_count": len(learned_results),
        "fixture_count": fixture_count,
        "validation_count": validation_count,
        "selected_candidate_counts": dict(selected_counts),
        "overall_validation_deltas_json": deltas,
        "warnings": warnings,
    }
    return HistoricalPoissonParameterLearningReport(
        report_key=report_key,
        status="generated",
        competition_count=len(competition_results),
        learned_competition_count=len(learned_results),
        candidate_count=len(candidates),
        fixture_count=fixture_count,
        validation_count=validation_count,
        selected_candidate_counts=dict(selected_counts),
        overall_validation_candidate=overall_candidate,
        overall_validation_baseline=overall_baseline,
        overall_validation_deltas_json=deltas,
        competitions=competition_results,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_poisson_parameter_learning_report(
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


def _competition_learning_result(
    competition_id: str,
    *,
    slices: Sequence[HistoricalRecommendationSlice],
    candidates: Sequence[HistoricalPoissonParameterCandidate],
    options: HistoricalPoissonParameterLearningOptions,
) -> HistoricalPoissonCompetitionParameterLearningResult:
    sorted_slices = sorted(slices, key=_slice_sort_key)
    holdout_count = min(options.holdout_season_count, len(sorted_slices))
    training_slices = sorted_slices[:-holdout_count]
    validation_slices = sorted_slices[-holdout_count:]
    training_seasons = [_slice_season(slice_item) for slice_item in training_slices]
    validation_seasons = [_slice_season(slice_item) for slice_item in validation_slices]
    training_fixture_count = sum(len(slice_item.fixtures) for slice_item in training_slices)
    validation_fixture_count = sum(len(slice_item.fixtures) for slice_item in validation_slices)
    warnings: list[str] = []
    if len(training_slices) < options.min_training_season_count:
        warnings.append(
            f"historical_poisson_parameter_learning:{competition_id}:insufficient_training_seasons"
        )
        return _skipped_competition_result(
            competition_id,
            training_seasons=training_seasons,
            validation_seasons=validation_seasons,
            candidate_count=len(candidates),
            training_fixture_count=training_fixture_count,
            validation_fixture_count=validation_fixture_count,
            warnings=warnings,
        )
    training_results = [
        _candidate_training_result(
            candidate,
            training_slices=training_slices,
            options=options,
        )
        for candidate in candidates
    ]
    selected_training = _select_candidate(training_results, options=options)
    if selected_training is None:
        warnings.append(
            f"historical_poisson_parameter_learning:{competition_id}:no_selectable_candidate"
        )
        return _skipped_competition_result(
            competition_id,
            training_seasons=training_seasons,
            validation_seasons=validation_seasons,
            candidate_count=len(candidates),
            training_fixture_count=training_fixture_count,
            validation_fixture_count=validation_fixture_count,
            warnings=warnings,
            training_results=training_results,
        )
    validation_report = build_historical_poisson_walk_forward_report(
        sorted_slices,
        options=_walk_forward_options(
            selected_training.candidate,
            options=options,
            prediction_sample_limit=options.prediction_sample_limit,
        ),
    )
    validation_group = _validation_group(
        validation_report,
        competition_id=competition_id,
        validation_seasons=validation_seasons,
    )
    if validation_group.validation_count < options.min_validation_sample_size:
        warnings.append(
            f"historical_poisson_parameter_learning:{competition_id}:insufficient_validation_samples"
        )
    status = "learned" if not warnings else "learned_with_warnings"
    summary: dict[str, object] = {
        "calculation_basis": "historical_poisson_competition_parameter_learning_v3_1",
        "competition_id": competition_id,
        "training_seasons": training_seasons,
        "validation_seasons": validation_seasons,
        "candidate_count": len(candidates),
        "selected_candidate": selected_training.candidate.model_dump(mode="json"),
        "selection_metric": options.selection_metric,
        "selection_metric_value": selected_training.selection_metric_value,
        "selected_validation_report_key": validation_report.report_key,
        "selected_validation_deltas_json": validation_group.deltas_json,
        "status": status,
        "warnings": warnings,
    }
    return HistoricalPoissonCompetitionParameterLearningResult(
        competition_id=competition_id,
        training_seasons=training_seasons,
        validation_seasons=validation_seasons,
        candidate_count=len(candidates),
        training_fixture_count=training_fixture_count,
        validation_fixture_count=validation_fixture_count,
        selected_candidate=selected_training.candidate,
        selected_training_result=selected_training,
        selected_validation_report_key=validation_report.report_key,
        selected_validation=validation_group,
        baseline_validation=validation_group.baseline,
        status=status,
        warnings=warnings,
        training_results=training_results,
        summary_json=summary,
    )


def _candidate_training_result(
    candidate: HistoricalPoissonParameterCandidate,
    *,
    training_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalPoissonParameterLearningOptions,
) -> HistoricalPoissonParameterCandidateTrainingResult:
    training_report = build_historical_poisson_walk_forward_report(
        training_slices,
        options=_walk_forward_options(candidate, options=options, prediction_sample_limit=0),
    )
    selection_metric_value = _selection_metric_value(
        training_report.overall.deltas_json,
        metric=options.selection_metric,
        candidate=candidate,
        options=options,
    )
    selection_summary = _selection_summary(
        training_report.overall.deltas_json,
        metric=options.selection_metric,
        candidate=candidate,
        options=options,
        selection_metric_value=selection_metric_value,
    )
    return HistoricalPoissonParameterCandidateTrainingResult(
        candidate=candidate,
        training_report_key=training_report.report_key,
        training_sample_size=training_report.validation_count,
        training_candidate=training_report.overall.candidate,
        training_baseline=training_report.overall.baseline,
        training_deltas_json=training_report.overall.deltas_json,
        selection_metric_value=selection_metric_value,
        selection_summary_json=selection_summary,
    )


def _walk_forward_options(
    candidate: HistoricalPoissonParameterCandidate,
    *,
    options: HistoricalPoissonParameterLearningOptions,
    prediction_sample_limit: int,
) -> HistoricalPoissonWalkForwardOptions:
    return HistoricalPoissonWalkForwardOptions(
        lambda_method=candidate.lambda_method,
        score_grid_family=candidate.score_grid_family,
        dixon_coles_rho=(
            candidate.dixon_coles_rho
            if candidate.dixon_coles_rho is not None
            else -0.05
        ),
        min_prior_matches=options.min_prior_matches,
        min_team_matches=options.min_team_matches,
        max_training_results=options.max_training_results,
        max_goals=options.max_goals,
        bucket_size=options.bucket_size,
        min_bucket_sample_size=options.min_bucket_sample_size,
        recency_half_life_days=candidate.recency_half_life_days,
        home_away_split_weight=candidate.home_away_split_weight,
        strength_shrinkage_matches=candidate.strength_shrinkage_matches,
        prior_season_weight=candidate.prior_season_weight,
        draw_correction_weight=candidate.draw_correction_weight,
        market_anchor_weight=candidate.market_anchor_weight,
        form_window_matches=options.form_window_matches,
        ema_form_half_life_matches=candidate.ema_form_half_life_matches,
        form_adjustment_weight=candidate.form_adjustment_weight,
        rest_adjustment_weight=candidate.rest_adjustment_weight,
        rest_reference_days=options.rest_reference_days,
        max_lambda_adjustment=options.max_lambda_adjustment,
        min_prematch_feature_data_quality_score=(
            options.min_prematch_feature_data_quality_score
        ),
        prematch_feature_odds_movement_weight=(
            candidate.prematch_feature_odds_movement_weight
        ),
        prematch_feature_lineup_strength_weight=(
            options.prematch_feature_lineup_strength_weight
        ),
        prematch_feature_availability_risk_weight=(
            options.prematch_feature_availability_risk_weight
        ),
        prematch_feature_draw_risk_weight=(
            candidate.prematch_feature_draw_risk_weight
        ),
        prematch_feature_semantic_risk_weight=(
            options.prematch_feature_semantic_risk_weight
        ),
        max_prematch_feature_lambda_adjustment=(
            candidate.max_prematch_feature_lambda_adjustment
        ),
        model_version=f"{options.model_version_prefix}-{candidate.candidate_key}",
        feature_version=options.feature_version,
        calibration_version=f"{options.calibration_version_prefix}-{candidate.candidate_key}",
        prediction_sample_limit=prediction_sample_limit,
    )


def _candidate_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> list[HistoricalPoissonParameterCandidate]:
    candidates: list[HistoricalPoissonParameterCandidate] = []
    draw_weights = tuple(dict.fromkeys(options.candidate_draw_correction_weights))
    market_anchor_weights = _market_anchor_weight_grid(options)
    form_rest_weights = _form_rest_weight_grid(options)
    prematch_feature_weights = _prematch_feature_weight_grid(options)
    recency_values = _recency_grid(options)
    home_away_weights = _home_away_split_weight_grid(options)
    strength_shrinkage_values = _strength_shrinkage_grid(options)
    ema_half_life_values = _ema_form_half_life_grid(options)
    prior_season_weights = _prior_season_weight_grid(options)
    if options.include_poisson_candidates:
        candidates.extend(
            HistoricalPoissonParameterCandidate(
                candidate_key=_candidate_key(
                    "poisson",
                    draw_weight=draw_weight,
                    market_anchor_weight=market_anchor_weight,
                    recency_half_life_days=recency_half_life_days,
                    home_away_split_weight=home_away_split_weight,
                    strength_shrinkage_matches=strength_shrinkage_matches,
                    prior_season_weight=prior_season_weight,
                    ema_form_half_life_matches=ema_form_half_life_matches,
                    form_adjustment_weight=form_weight,
                    rest_adjustment_weight=rest_weight,
                    prematch_feature_odds_movement_weight=prematch_odds_weight,
                    prematch_feature_draw_risk_weight=prematch_draw_risk_weight,
                    max_prematch_feature_lambda_adjustment=prematch_max_adjustment,
                    lambda_method=options.lambda_method,
                ),
                lambda_method=options.lambda_method,
                score_grid_family="poisson",
                dixon_coles_rho=None,
                draw_correction_weight=draw_weight,
                market_anchor_weight=market_anchor_weight,
                recency_half_life_days=recency_half_life_days,
                home_away_split_weight=home_away_split_weight,
                strength_shrinkage_matches=strength_shrinkage_matches,
                prior_season_weight=prior_season_weight,
                ema_form_half_life_matches=ema_form_half_life_matches,
                form_adjustment_weight=form_weight,
                rest_adjustment_weight=rest_weight,
                prematch_feature_odds_movement_weight=prematch_odds_weight,
                prematch_feature_draw_risk_weight=prematch_draw_risk_weight,
                max_prematch_feature_lambda_adjustment=prematch_max_adjustment,
            )
            for draw_weight in draw_weights
            for market_anchor_weight in market_anchor_weights
            for recency_half_life_days in recency_values
            for home_away_split_weight in home_away_weights
            for strength_shrinkage_matches in strength_shrinkage_values
            for prior_season_weight in prior_season_weights
            for ema_form_half_life_matches in ema_half_life_values
            for form_weight, rest_weight in form_rest_weights
            for (
                prematch_odds_weight,
                prematch_draw_risk_weight,
                prematch_max_adjustment,
            ) in prematch_feature_weights
        )
    if options.include_dixon_coles_candidates:
        candidates.extend(
            HistoricalPoissonParameterCandidate(
                candidate_key=_candidate_key(
                    f"dc_rho_{_rho_key(rho)}",
                    draw_weight=draw_weight,
                    market_anchor_weight=market_anchor_weight,
                    recency_half_life_days=recency_half_life_days,
                    home_away_split_weight=home_away_split_weight,
                    strength_shrinkage_matches=strength_shrinkage_matches,
                    prior_season_weight=prior_season_weight,
                    ema_form_half_life_matches=ema_form_half_life_matches,
                    form_adjustment_weight=form_weight,
                    rest_adjustment_weight=rest_weight,
                    prematch_feature_odds_movement_weight=prematch_odds_weight,
                    prematch_feature_draw_risk_weight=prematch_draw_risk_weight,
                    max_prematch_feature_lambda_adjustment=prematch_max_adjustment,
                    lambda_method=options.lambda_method,
                ),
                lambda_method=options.lambda_method,
                score_grid_family="dixon_coles_low_score",
                dixon_coles_rho=rho,
                draw_correction_weight=draw_weight,
                market_anchor_weight=market_anchor_weight,
                recency_half_life_days=recency_half_life_days,
                home_away_split_weight=home_away_split_weight,
                strength_shrinkage_matches=strength_shrinkage_matches,
                prior_season_weight=prior_season_weight,
                ema_form_half_life_matches=ema_form_half_life_matches,
                form_adjustment_weight=form_weight,
                rest_adjustment_weight=rest_weight,
                prematch_feature_odds_movement_weight=prematch_odds_weight,
                prematch_feature_draw_risk_weight=prematch_draw_risk_weight,
                max_prematch_feature_lambda_adjustment=prematch_max_adjustment,
            )
            for rho in tuple(dict.fromkeys(options.candidate_dixon_coles_rhos))
            for draw_weight in draw_weights
            for market_anchor_weight in market_anchor_weights
            for recency_half_life_days in recency_values
            for home_away_split_weight in home_away_weights
            for strength_shrinkage_matches in strength_shrinkage_values
            for prior_season_weight in prior_season_weights
            for ema_form_half_life_matches in ema_half_life_values
            for form_weight, rest_weight in form_rest_weights
            for (
                prematch_odds_weight,
                prematch_draw_risk_weight,
                prematch_max_adjustment,
            ) in prematch_feature_weights
        )
    return candidates


def _select_candidate(
    training_results: Sequence[HistoricalPoissonParameterCandidateTrainingResult],
    *,
    options: HistoricalPoissonParameterLearningOptions,
) -> HistoricalPoissonParameterCandidateTrainingResult | None:
    selectable = [
        result
        for result in training_results
        if result.selection_metric_value is not None
        and result.training_sample_size >= options.min_validation_sample_size
    ]
    if not selectable:
        return None
    return min(
        selectable,
        key=lambda result: (
            result.selection_metric_value
            if result.selection_metric_value is not None
            else float("inf"),
            result.candidate.candidate_key,
        ),
    )


def _validation_group(
    report: HistoricalPoissonWalkForwardReport,
    *,
    competition_id: str,
    validation_seasons: Sequence[str],
) -> HistoricalPoissonWalkForwardComparisonGroup:
    selected_groups = [
        group
        for group in report.by_competition_season
        if group.competition_id == competition_id
        and (group.season or "unknown") in set(validation_seasons)
    ]
    if not selected_groups:
        return HistoricalPoissonWalkForwardComparisonGroup(
            group_key=f"{competition_id}|validation",
            group_type="competition_season",
            label=f"{competition_id} validation",
            competition_id=competition_id,
            validation_count=0,
            skipped_count=0,
            candidate=_empty_metric_set(),
            baseline=_empty_metric_set(),
            deltas_json={},
        )
    candidate = _combine_metric_sets([group.candidate for group in selected_groups])
    baseline = _combine_metric_sets([group.baseline for group in selected_groups])
    candidate = candidate or _empty_metric_set()
    baseline = baseline or _empty_metric_set()
    skipped_reason_counts: Counter[str] = Counter()
    for group in selected_groups:
        skipped_reason_counts.update(group.skipped_reason_counts)
    return HistoricalPoissonWalkForwardComparisonGroup(
        group_key=f"{competition_id}|validation",
        group_type="competition_season",
        label=f"{competition_id} validation",
        competition_id=competition_id,
        season=",".join(validation_seasons),
        validation_count=sum(group.validation_count for group in selected_groups),
        skipped_count=sum(group.skipped_count for group in selected_groups),
        skipped_reason_counts=dict(skipped_reason_counts),
        candidate=candidate,
        baseline=baseline,
        deltas_json=_metric_deltas(candidate, baseline),
    )


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


def _empty_metric_set() -> HistoricalPoissonWalkForwardMetricSet:
    return HistoricalPoissonWalkForwardMetricSet(
        sample_size=0,
        hit_count=0,
        hit_rate=None,
        brier_score=None,
        log_loss=None,
        average_actual_probability=None,
        expected_calibration_error=None,
    )


def _skipped_competition_result(
    competition_id: str,
    *,
    training_seasons: Sequence[str],
    validation_seasons: Sequence[str],
    candidate_count: int,
    training_fixture_count: int,
    validation_fixture_count: int,
    warnings: Sequence[str],
    training_results: Sequence[HistoricalPoissonParameterCandidateTrainingResult] = (),
) -> HistoricalPoissonCompetitionParameterLearningResult:
    return HistoricalPoissonCompetitionParameterLearningResult(
        competition_id=competition_id,
        training_seasons=list(training_seasons),
        validation_seasons=list(validation_seasons),
        candidate_count=candidate_count,
        training_fixture_count=training_fixture_count,
        validation_fixture_count=validation_fixture_count,
        status="skipped",
        warnings=list(warnings),
        training_results=list(training_results),
        summary_json={
            "calculation_basis": "historical_poisson_competition_parameter_learning_v3_1",
            "competition_id": competition_id,
            "status": "skipped",
            "warnings": list(warnings),
        },
    )


def _selection_metric_value(
    deltas_json: dict[str, object],
    *,
    metric: HistoricalPoissonParameterSelectionMetric,
    candidate: HistoricalPoissonParameterCandidate | None = None,
    options: HistoricalPoissonParameterLearningOptions | None = None,
) -> float | None:
    if metric == "no_harm_score":
        if candidate is None or options is None:
            return None
        return _no_harm_selection_score(
            deltas_json,
            candidate=candidate,
            options=options,
        )
    value = deltas_json.get(metric)
    if isinstance(value, int | float):
        return float(value)
    return None


def _no_harm_selection_score(
    deltas_json: dict[str, object],
    *,
    candidate: HistoricalPoissonParameterCandidate,
    options: HistoricalPoissonParameterLearningOptions,
) -> float | None:
    brier_delta = _delta_float(deltas_json, "brier_score_delta")
    if brier_delta is None:
        return None
    hit_rate_delta = _delta_float(deltas_json, "hit_rate_delta", default=0.0)
    log_loss_delta = _delta_float(deltas_json, "log_loss_delta", default=0.0)
    calibration_delta = _delta_float(
        deltas_json,
        "expected_calibration_error_delta",
        default=0.0,
    )
    actual_probability_delta = _delta_float(
        deltas_json,
        "average_actual_probability_delta",
        default=0.0,
    )
    model_signal_weight = 1.0 - candidate.market_anchor_weight
    return (
        options.selection_primary_metric_weight * brier_delta
        + options.selection_hit_rate_regression_penalty
        * max(0.0, -(hit_rate_delta or 0.0))
        + options.selection_brier_regression_penalty * max(0.0, brier_delta)
        + options.selection_log_loss_regression_penalty
        * max(0.0, log_loss_delta or 0.0)
        + options.selection_calibration_regression_penalty
        * max(0.0, calibration_delta or 0.0)
        + options.selection_actual_probability_regression_penalty
        * max(0.0, -(actual_probability_delta or 0.0))
        + options.selection_low_model_signal_penalty
        * max(0.0, options.selection_min_model_signal_weight - model_signal_weight)
    )


def _selection_summary(
    deltas_json: dict[str, object],
    *,
    metric: HistoricalPoissonParameterSelectionMetric,
    candidate: HistoricalPoissonParameterCandidate,
    options: HistoricalPoissonParameterLearningOptions,
    selection_metric_value: float | None,
) -> dict[str, object]:
    model_signal_weight = 1.0 - candidate.market_anchor_weight
    summary: dict[str, object] = {
        "selection_metric": metric,
        "selection_metric_value": selection_metric_value,
        "candidate_key": candidate.candidate_key,
        "model_signal_weight": model_signal_weight,
        "market_anchor_weight": candidate.market_anchor_weight,
    }
    if metric != "no_harm_score":
        return summary
    summary.update(
        {
            "calculation_basis": "historical_poisson_no_harm_selection_score_v3_2",
            "penalty_weights": _selection_no_harm_options_summary(options),
            "positive_regression_penalties": {
                "hit_rate_delta": max(
                    0.0,
                    -(_delta_float(deltas_json, "hit_rate_delta", default=0.0) or 0.0),
                ),
                "brier_score_delta": max(
                    0.0,
                    _delta_float(deltas_json, "brier_score_delta", default=0.0)
                    or 0.0,
                ),
                "log_loss_delta": max(
                    0.0,
                    _delta_float(deltas_json, "log_loss_delta", default=0.0) or 0.0,
                ),
                "expected_calibration_error_delta": max(
                    0.0,
                    _delta_float(
                        deltas_json,
                        "expected_calibration_error_delta",
                        default=0.0,
                    )
                    or 0.0,
                ),
                "average_actual_probability_delta": max(
                    0.0,
                    -(
                        _delta_float(
                            deltas_json,
                            "average_actual_probability_delta",
                            default=0.0,
                        )
                        or 0.0
                    ),
                ),
                "low_model_signal_weight": max(
                    0.0,
                    options.selection_min_model_signal_weight - model_signal_weight,
                ),
            },
        }
    )
    return summary


def _selection_no_harm_options_summary(
    options: HistoricalPoissonParameterLearningOptions,
) -> dict[str, object]:
    return {
        "selection_primary_metric_weight": options.selection_primary_metric_weight,
        "selection_hit_rate_regression_penalty": (
            options.selection_hit_rate_regression_penalty
        ),
        "selection_brier_regression_penalty": (
            options.selection_brier_regression_penalty
        ),
        "selection_log_loss_regression_penalty": (
            options.selection_log_loss_regression_penalty
        ),
        "selection_calibration_regression_penalty": (
            options.selection_calibration_regression_penalty
        ),
        "selection_actual_probability_regression_penalty": (
            options.selection_actual_probability_regression_penalty
        ),
        "selection_min_model_signal_weight": options.selection_min_model_signal_weight,
        "selection_low_model_signal_penalty": (
            options.selection_low_model_signal_penalty
        ),
    }


def _delta_float(
    deltas_json: dict[str, object],
    key: str,
    *,
    default: float | None = None,
) -> float | None:
    value = deltas_json.get(key, default)
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


def _slices_by_competition(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> dict[str, list[HistoricalRecommendationSlice]]:
    grouped: dict[str, list[HistoricalRecommendationSlice]] = {}
    for historical_slice in historical_slices:
        grouped.setdefault(historical_slice.metadata.competition_id, []).append(
            historical_slice
        )
    return grouped


def _slice_sort_key(historical_slice: HistoricalRecommendationSlice) -> tuple[str, str]:
    return (
        historical_slice.metadata.season or "",
        historical_slice.metadata.slice_id,
    )


def _slice_season(historical_slice: HistoricalRecommendationSlice) -> str:
    return historical_slice.metadata.season or "unknown"


def _weight_key(value: float) -> str:
    return str(value).replace("-", "neg_").replace(".", "_")


def _rho_key(value: float) -> str:
    return str(value).replace("-", "neg_").replace(".", "_")


def _form_rest_weight_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> tuple[tuple[float, float], ...]:
    if options.lambda_method == "ema_form_adjusted":
        form_weights = tuple(dict.fromkeys(options.candidate_form_adjustment_weights))
        return tuple((form_weight, 0.0) for form_weight in form_weights)
    if options.lambda_method not in {"form_rest_adjusted", "prematch_feature_adjusted"}:
        return ((0.0, 0.0),)
    form_weights = tuple(dict.fromkeys(options.candidate_form_adjustment_weights))
    rest_weights = tuple(dict.fromkeys(options.candidate_rest_adjustment_weights))
    return tuple(
        (form_weight, rest_weight)
        for form_weight in form_weights
        for rest_weight in rest_weights
    )


def _prematch_feature_weight_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> tuple[tuple[float, float, float], ...]:
    if options.lambda_method != "prematch_feature_adjusted":
        return ((0.0, 0.0, DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT),)
    odds_weights = tuple(
        dict.fromkeys(options.candidate_prematch_feature_odds_movement_weights)
    )
    draw_risk_weights = tuple(
        dict.fromkeys(options.candidate_prematch_feature_draw_risk_weights)
    )
    max_adjustments = tuple(
        dict.fromkeys(options.candidate_max_prematch_feature_lambda_adjustments)
    )
    return tuple(
        (odds_weight, draw_risk_weight, max_adjustment)
        for odds_weight in odds_weights
        for draw_risk_weight in draw_risk_weights
        for max_adjustment in max_adjustments
    )


def _market_anchor_weight_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> tuple[float, ...]:
    return tuple(dict.fromkeys(options.candidate_market_anchor_weights))


def _recency_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> tuple[float | None, ...]:
    configured = options.candidate_recency_half_life_days
    if configured:
        return tuple(dict.fromkeys(configured))
    return (options.recency_half_life_days,)


def _home_away_split_weight_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> tuple[float, ...]:
    configured = options.candidate_home_away_split_weights
    if configured:
        return tuple(dict.fromkeys(configured))
    return (options.home_away_split_weight,)


def _strength_shrinkage_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> tuple[float, ...]:
    if options.lambda_method not in {
        "shrunken_weighted_home_away",
        "hierarchical_weighted_home_away",
        "reliability_weighted_home_away",
    }:
        return (0.0,)
    configured = options.candidate_strength_shrinkage_matches
    if configured:
        return tuple(dict.fromkeys(configured))
    return (options.strength_shrinkage_matches,)


def _ema_form_half_life_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> tuple[float, ...]:
    if options.lambda_method != "ema_form_adjusted":
        return (DEFAULT_EMA_FORM_HALF_LIFE_MATCHES,)
    configured = options.candidate_ema_form_half_life_matches
    if configured:
        return tuple(dict.fromkeys(configured))
    return (options.ema_form_half_life_matches,)


def _prior_season_weight_grid(
    options: HistoricalPoissonParameterLearningOptions,
) -> tuple[float, ...]:
    if options.lambda_method != "season_weighted_home_away":
        return (DEFAULT_PRIOR_SEASON_WEIGHT,)
    configured = options.candidate_prior_season_weights
    if configured:
        return tuple(dict.fromkeys(configured))
    return (options.prior_season_weight,)


def _candidate_key(
    prefix: str,
    *,
    draw_weight: float,
    market_anchor_weight: float,
    recency_half_life_days: float | None,
    home_away_split_weight: float,
    strength_shrinkage_matches: float,
    prior_season_weight: float,
    ema_form_half_life_matches: float,
    form_adjustment_weight: float,
    rest_adjustment_weight: float,
    prematch_feature_odds_movement_weight: float,
    prematch_feature_draw_risk_weight: float,
    max_prematch_feature_lambda_adjustment: float,
    lambda_method: HistoricalPoissonLambdaMethod,
) -> str:
    key = f"{prefix}_draw_{_weight_key(draw_weight)}"
    if market_anchor_weight != 0.0:
        key = f"{key}_marketanchor_{_weight_key(market_anchor_weight)}"
    if recency_half_life_days is not None:
        key = f"{key}_recency_{_weight_key(recency_half_life_days)}"
    if home_away_split_weight != 0.0:
        key = f"{key}_homeaway_{_weight_key(home_away_split_weight)}"
    if lambda_method in {
        "shrunken_weighted_home_away",
        "hierarchical_weighted_home_away",
        "reliability_weighted_home_away",
    }:
        key = f"{key}_shrink_{_weight_key(strength_shrinkage_matches)}"
    if lambda_method == "season_weighted_home_away":
        key = f"{key}_priorseason_{_weight_key(prior_season_weight)}"
    if lambda_method == "ema_form_adjusted":
        key = (
            f"{key}_ema_{_weight_key(ema_form_half_life_matches)}"
            f"_form_{_weight_key(form_adjustment_weight)}"
        )
    if lambda_method == "form_rest_adjusted":
        key = (
            f"{key}_form_{_weight_key(form_adjustment_weight)}"
            f"_rest_{_weight_key(rest_adjustment_weight)}"
        )
    if lambda_method == "prematch_feature_adjusted":
        key = (
            f"{key}_form_{_weight_key(form_adjustment_weight)}"
            f"_rest_{_weight_key(rest_adjustment_weight)}"
            f"_prematch_odds_{_weight_key(prematch_feature_odds_movement_weight)}"
            f"_prematch_draw_{_weight_key(prematch_feature_draw_risk_weight)}"
            f"_prematch_max_{_weight_key(max_prematch_feature_lambda_adjustment)}"
        )
    return key


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    candidates: Sequence[HistoricalPoissonParameterCandidate],
    options: HistoricalPoissonParameterLearningOptions,
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "candidate_keys": [candidate.candidate_key for candidate in candidates],
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_poisson_parameter_learning:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Learn league-level Poisson/Dixon-Coles draw and rho parameters."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--holdout-season-count", type=int, default=1)
    parser.add_argument("--min-training-season-count", type=int, default=2)
    parser.add_argument("--min-validation-sample-size", type=int, default=100)
    parser.add_argument(
        "--selection-metric",
        choices=[
            "brier_score_delta",
            "log_loss_delta",
            "expected_calibration_error_delta",
            "no_harm_score",
        ],
        default="brier_score_delta",
    )
    parser.add_argument("--selection-primary-metric-weight", type=float, default=1.0)
    parser.add_argument("--selection-hit-rate-regression-penalty", type=float, default=10.0)
    parser.add_argument("--selection-brier-regression-penalty", type=float, default=5.0)
    parser.add_argument("--selection-log-loss-regression-penalty", type=float, default=2.0)
    parser.add_argument("--selection-calibration-regression-penalty", type=float, default=2.0)
    parser.add_argument(
        "--selection-actual-probability-regression-penalty",
        type=float,
        default=2.0,
    )
    parser.add_argument("--selection-min-model-signal-weight", type=float, default=0.05)
    parser.add_argument("--selection-low-model-signal-penalty", type=float, default=1.0)
    parser.add_argument(
        "--lambda-method",
        choices=[
            "rolling_strength",
            "enhanced_weighted_home_away",
            "shrunken_weighted_home_away",
            "hierarchical_weighted_home_away",
            "reliability_weighted_home_away",
            "season_weighted_home_away",
            "ema_form_adjusted",
            "form_rest_adjusted",
            "prematch_feature_adjusted",
        ],
        default="rolling_strength",
    )
    parser.add_argument("--disable-poisson-candidates", action="store_true")
    parser.add_argument("--disable-dixon-coles-candidates", action="store_true")
    parser.add_argument("--candidate-draw-correction-weights", default="0.0,0.4")
    parser.add_argument("--candidate-market-anchor-weights", default="0.0")
    parser.add_argument("--candidate-dixon-coles-rhos", default="-0.1,-0.05,0.05")
    parser.add_argument("--candidate-form-adjustment-weights", default="0.0")
    parser.add_argument("--candidate-ema-form-half-life-matches", default="")
    parser.add_argument("--candidate-prior-season-weights", default="")
    parser.add_argument("--candidate-rest-adjustment-weights", default="0.0")
    parser.add_argument("--candidate-prematch-feature-odds-movement-weights", default="0.0")
    parser.add_argument("--candidate-prematch-feature-draw-risk-weights", default="0.0")
    parser.add_argument(
        "--candidate-max-prematch-feature-lambda-adjustments",
        default=str(DEFAULT_PREMATCH_FEATURE_MAX_LAMBDA_ADJUSTMENT),
    )
    parser.add_argument(
        "--candidate-recency-half-life-days",
        default="",
        help="Comma-separated half-life candidates; use none for unweighted history.",
    )
    parser.add_argument("--candidate-home-away-split-weights", default="")
    parser.add_argument("--candidate-strength-shrinkage-matches", default="")
    parser.add_argument("--min-prior-matches", type=int, default=60)
    parser.add_argument("--min-team-matches", type=int, default=5)
    parser.add_argument("--max-training-results", type=int, default=380)
    parser.add_argument("--max-goals", type=int, default=8)
    parser.add_argument("--bucket-size", type=float, default=0.10)
    parser.add_argument("--min-bucket-sample-size", type=int, default=30)
    parser.add_argument("--recency-half-life-days", type=float)
    parser.add_argument("--home-away-split-weight", type=float, default=0.0)
    parser.add_argument(
        "--strength-shrinkage-matches",
        type=float,
        default=DEFAULT_STRENGTH_SHRINKAGE_MATCHES,
    )
    parser.add_argument(
        "--prior-season-weight",
        type=float,
        default=DEFAULT_PRIOR_SEASON_WEIGHT,
    )
    parser.add_argument("--form-window-matches", type=int, default=DEFAULT_FORM_WINDOW_MATCHES)
    parser.add_argument(
        "--ema-form-half-life-matches",
        type=float,
        default=DEFAULT_EMA_FORM_HALF_LIFE_MATCHES,
    )
    parser.add_argument("--rest-reference-days", type=float, default=DEFAULT_REST_REFERENCE_DAYS)
    parser.add_argument(
        "--max-lambda-adjustment",
        type=float,
        default=DEFAULT_MAX_LAMBDA_ADJUSTMENT,
    )
    parser.add_argument("--min-prematch-feature-data-quality-score", type=float, default=80.0)
    parser.add_argument("--prematch-feature-lineup-strength-weight", type=float, default=0.08)
    parser.add_argument("--prematch-feature-availability-risk-weight", type=float, default=0.06)
    parser.add_argument("--prematch-feature-semantic-risk-weight", type=float, default=0.04)
    parser.add_argument("--model-version-prefix", default="learned-league-parameter-v3.1")
    parser.add_argument("--feature-version", default="rolling-results-team-strength-v1")
    parser.add_argument(
        "--calibration-version-prefix",
        default="learned-league-draw-rho-v3.1",
    )
    parser.add_argument("--prediction-sample-limit", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalPoissonParameterLearningOptions:
    return HistoricalPoissonParameterLearningOptions(
        holdout_season_count=args.holdout_season_count,
        min_training_season_count=args.min_training_season_count,
        min_validation_sample_size=args.min_validation_sample_size,
        selection_metric=args.selection_metric,
        selection_primary_metric_weight=args.selection_primary_metric_weight,
        selection_hit_rate_regression_penalty=(
            args.selection_hit_rate_regression_penalty
        ),
        selection_brier_regression_penalty=args.selection_brier_regression_penalty,
        selection_log_loss_regression_penalty=(
            args.selection_log_loss_regression_penalty
        ),
        selection_calibration_regression_penalty=(
            args.selection_calibration_regression_penalty
        ),
        selection_actual_probability_regression_penalty=(
            args.selection_actual_probability_regression_penalty
        ),
        selection_min_model_signal_weight=args.selection_min_model_signal_weight,
        selection_low_model_signal_penalty=args.selection_low_model_signal_penalty,
        lambda_method=args.lambda_method,
        include_poisson_candidates=not args.disable_poisson_candidates,
        include_dixon_coles_candidates=not args.disable_dixon_coles_candidates,
        candidate_draw_correction_weights=_float_tuple(
            args.candidate_draw_correction_weights
        ),
        candidate_market_anchor_weights=_float_tuple(
            args.candidate_market_anchor_weights
        ),
        candidate_dixon_coles_rhos=_float_tuple(args.candidate_dixon_coles_rhos),
        candidate_form_adjustment_weights=_float_tuple(
            args.candidate_form_adjustment_weights
        ),
        candidate_ema_form_half_life_matches=_float_tuple(
            args.candidate_ema_form_half_life_matches
        ),
        candidate_prior_season_weights=_float_tuple(
            args.candidate_prior_season_weights
        ),
        candidate_rest_adjustment_weights=_float_tuple(
            args.candidate_rest_adjustment_weights
        ),
        candidate_prematch_feature_odds_movement_weights=_float_tuple(
            args.candidate_prematch_feature_odds_movement_weights
        ),
        candidate_prematch_feature_draw_risk_weights=_float_tuple(
            args.candidate_prematch_feature_draw_risk_weights
        ),
        candidate_max_prematch_feature_lambda_adjustments=_float_tuple(
            args.candidate_max_prematch_feature_lambda_adjustments
        ),
        candidate_recency_half_life_days=_optional_float_tuple(
            args.candidate_recency_half_life_days
        ),
        candidate_home_away_split_weights=_float_tuple(
            args.candidate_home_away_split_weights
        ),
        candidate_strength_shrinkage_matches=_float_tuple(
            args.candidate_strength_shrinkage_matches
        ),
        min_prior_matches=args.min_prior_matches,
        min_team_matches=args.min_team_matches,
        max_training_results=args.max_training_results,
        max_goals=args.max_goals,
        bucket_size=args.bucket_size,
        min_bucket_sample_size=args.min_bucket_sample_size,
        recency_half_life_days=args.recency_half_life_days,
        home_away_split_weight=args.home_away_split_weight,
        strength_shrinkage_matches=args.strength_shrinkage_matches,
        prior_season_weight=args.prior_season_weight,
        form_window_matches=args.form_window_matches,
        ema_form_half_life_matches=args.ema_form_half_life_matches,
        rest_reference_days=args.rest_reference_days,
        max_lambda_adjustment=args.max_lambda_adjustment,
        min_prematch_feature_data_quality_score=(
            args.min_prematch_feature_data_quality_score
        ),
        prematch_feature_lineup_strength_weight=(
            args.prematch_feature_lineup_strength_weight
        ),
        prematch_feature_availability_risk_weight=(
            args.prematch_feature_availability_risk_weight
        ),
        prematch_feature_semantic_risk_weight=(
            args.prematch_feature_semantic_risk_weight
        ),
        model_version_prefix=args.model_version_prefix,
        feature_version=args.feature_version,
        calibration_version_prefix=args.calibration_version_prefix,
        prediction_sample_limit=args.prediction_sample_limit,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    historical_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    if args.suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            args.suite_manifest
        )
        historical_slices = [*manifest_result.slices, *historical_slices]
        warnings.extend(manifest_result.warnings)
    return _LoadedHistoricalSlices(
        slices=historical_slices,
        manifest_result=manifest_result,
        warnings=warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "enabled_slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in value.split(",") if part.strip())


def _optional_float_tuple(value: str) -> tuple[float | None, ...]:
    values: list[float | None] = []
    for part in value.split(","):
        normalized = part.strip().lower()
        if not normalized:
            continue
        if normalized in {"none", "null", "off", "unweighted"}:
            values.append(None)
        else:
            values.append(float(normalized))
    return tuple(values)


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline
