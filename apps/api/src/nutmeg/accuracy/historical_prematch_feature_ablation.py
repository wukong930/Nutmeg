from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from math import floor, log
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalPrematchFeatureAblationStatus = Literal["generated"]
type HistoricalPrematchFeatureAblationGroupType = Literal[
    "overall",
    "competition",
    "season",
    "competition_season",
]

ONE_X_TWO_OUTCOMES = ("home_win", "draw", "away_win")
DEFAULT_PREMATCH_FEATURE_ABLATION_MODEL_VERSION = (
    "prematch-feature-ablation-shadow-v3.1"
)
DEFAULT_PREMATCH_FEATURE_ABLATION_FEATURE_VERSION = "features-v3.1-prematch-structured"
DEFAULT_PREMATCH_FEATURE_ABLATION_CALIBRATION_VERSION = (
    "uncalibrated-prematch-feature-shadow-v3.1"
)
DEFAULT_LOG_LOSS_EPSILON = 1e-12


class HistoricalPrematchFeatureAblationOptions(BaseModel):
    min_feature_data_quality_score: float = Field(default=80.0, ge=0.0, le=100.0)
    max_probability_shift: float = Field(default=0.12, ge=0.0, le=0.35)
    odds_movement_weight: float = Field(default=0.35, ge=0.0, le=2.0)
    tracked_fragility_weight: float = Field(default=1.0, ge=0.0, le=2.0)
    lineup_strength_weight: float = Field(default=0.35, ge=0.0, le=2.0)
    draw_signal_weight: float = Field(default=0.35, ge=0.0, le=2.0)
    bucket_size: float = Field(default=0.10, gt=0.0, le=1.0)
    min_bucket_sample_size: int = Field(default=1, ge=1)
    prediction_sample_limit: int = Field(default=20, ge=0)
    require_feature_not_after_prediction: bool = True
    require_feature_before_kickoff: bool = True
    model_version: str = DEFAULT_PREMATCH_FEATURE_ABLATION_MODEL_VERSION
    feature_version: str = DEFAULT_PREMATCH_FEATURE_ABLATION_FEATURE_VERSION
    calibration_version: str = DEFAULT_PREMATCH_FEATURE_ABLATION_CALIBRATION_VERSION


class HistoricalPrematchFeatureAblationMetricSet(BaseModel):
    sample_size: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    average_actual_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_calibration_error: float | None = Field(default=None, ge=0.0)
    calibration_observation_count: int = Field(default=0, ge=0)
    included_calibration_bucket_count: int = Field(default=0, ge=0)
    skipped_small_calibration_bucket_count: int = Field(default=0, ge=0)


class HistoricalPrematchFeatureAblationFixtureSample(BaseModel):
    fixture_id: str
    slice_id: str
    competition_id: str
    season: str | None = None
    kickoff_time_utc: datetime
    home_team_name: str
    away_team_name: str
    actual_outcome: str
    favorite_outcome: str
    tracked_outcome: str
    favorite_fragility_score: float = Field(ge=0.0, le=1.0)
    feature_data_quality_score: float = Field(ge=0.0, le=100.0)
    tracked_outcome_fragility_score: float = Field(ge=0.0, le=1.0)
    lineup_strength_score: float = Field(ge=0.0, le=1.0)
    draw_risk_score: float = Field(ge=0.0, le=1.0)
    market_volatility_score: float = Field(ge=0.0, le=1.0)
    lineup_schedule_risk: float = Field(ge=0.0, le=1.0)
    key_player_absence_score: float = Field(ge=0.0, le=1.0)
    semantic_risk_score: float = Field(ge=0.0, le=1.0)
    source_ref_count: int = Field(ge=0)
    odds_movement_probability_delta: float | None = None
    baseline_probabilities: dict[str, float] = Field(default_factory=dict)
    candidate_probabilities: dict[str, float] = Field(default_factory=dict)
    baseline_actual_probability: float = Field(ge=0.0, le=1.0)
    candidate_actual_probability: float = Field(ge=0.0, le=1.0)
    baseline_brier_score: float = Field(ge=0.0)
    candidate_brier_score: float = Field(ge=0.0)
    baseline_log_loss: float = Field(ge=0.0)
    candidate_log_loss: float = Field(ge=0.0)
    brier_score_delta_vs_baseline: float
    log_loss_delta_vs_baseline: float
    actual_probability_delta_vs_baseline: float
    adjustment_json: dict[str, object] = Field(default_factory=dict)
    feature_readout_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureAblationComparisonGroup(BaseModel):
    group_key: str
    group_type: HistoricalPrematchFeatureAblationGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None
    validation_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    candidate: HistoricalPrematchFeatureAblationMetricSet
    baseline: HistoricalPrematchFeatureAblationMetricSet
    deltas_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureAblationReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureAblationStatus
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    overall: HistoricalPrematchFeatureAblationComparisonGroup
    by_competition: list[HistoricalPrematchFeatureAblationComparisonGroup] = Field(
        default_factory=list
    )
    by_season: list[HistoricalPrematchFeatureAblationComparisonGroup] = Field(
        default_factory=list
    )
    by_competition_season: list[HistoricalPrematchFeatureAblationComparisonGroup] = (
        Field(default_factory=list)
    )
    sampled_predictions: list[HistoricalPrematchFeatureAblationFixtureSample] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _FixtureContext(BaseModel):
    slice_id: str
    season: str | None
    fixture: HistoricalFixture


class _SkippedFixture(BaseModel):
    fixture_id: str
    competition_id: str
    season: str | None
    reason: str


class _PrematchFeatureReadout(BaseModel):
    feature_data_quality_score: float = Field(ge=0.0, le=100.0)
    tracked_outcome: str
    tracked_outcome_fragility_score: float = Field(ge=0.0, le=1.0)
    favorite_fragility_score: float = Field(ge=0.0, le=1.0)
    lineup_strength_score: float = Field(ge=0.0, le=1.0)
    draw_risk_score: float = Field(ge=0.0, le=1.0)
    market_volatility_score: float = Field(ge=0.0, le=1.0)
    lineup_schedule_risk: float = Field(ge=0.0, le=1.0)
    key_player_absence_score: float = Field(ge=0.0, le=1.0)
    odds_movement_probability_delta: float | None = None
    semantic_risk_score: float = Field(ge=0.0, le=1.0)
    source_ref_count: int = Field(ge=0)
    reason_codes: list[str] = Field(default_factory=list)
    readout_json: dict[str, object] = Field(default_factory=dict)


class _ProbabilityAdjustment(BaseModel):
    probabilities: dict[str, float]
    raw_shifts: dict[str, float]
    capped_shifts: dict[str, float]
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _CalibrationBucketAccumulator(BaseModel):
    sample_size: int = 0
    predicted_probability_sum: float = 0.0
    actual_count: int = 0


class _MetricAccumulator(BaseModel):
    sample_size: int = 0
    hit_count: int = 0
    brier_score_sum: float = 0.0
    log_loss_sum: float = 0.0
    actual_probability_sum: float = 0.0
    calibration_buckets: dict[tuple[str, float, float], _CalibrationBucketAccumulator] = (
        Field(default_factory=dict)
    )


def build_historical_prematch_feature_ablation_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureAblationOptions | None = None,
) -> HistoricalPrematchFeatureAblationReport:
    resolved_options = options or HistoricalPrematchFeatureAblationOptions()
    fixture_contexts = _fixture_contexts(historical_slices)
    evaluations, skipped = _fixture_evaluations(
        fixture_contexts,
        options=resolved_options,
    )
    overall = _comparison_group(
        "overall",
        group_type="overall",
        label="Overall",
        evaluations=evaluations,
        skipped=skipped,
        options=resolved_options,
    )
    by_competition = _grouped_comparisons(
        evaluations,
        skipped,
        group_type="competition",
        key_fn=lambda item: item.competition_id,
        skipped_key_fn=lambda item: item.competition_id,
        label_fn=lambda key: key,
        options=resolved_options,
    )
    by_season = _grouped_comparisons(
        evaluations,
        skipped,
        group_type="season",
        key_fn=lambda item: item.season or "unknown",
        skipped_key_fn=lambda item: item.season or "unknown",
        label_fn=lambda key: key,
        options=resolved_options,
    )
    by_competition_season = _grouped_comparisons(
        evaluations,
        skipped,
        group_type="competition_season",
        key_fn=lambda item: "|".join(
            [item.competition_id, item.season or "unknown"]
        ),
        skipped_key_fn=lambda item: "|".join(
            [item.competition_id, item.season or "unknown"]
        ),
        label_fn=lambda key: key.replace("|", " "),
        options=resolved_options,
    )
    skipped_reason_counts = dict(Counter(item.reason for item in skipped))
    warnings = _report_warnings(evaluations, skipped)
    report_key = _report_key(
        historical_slices,
        options=resolved_options,
        validation_count=len(evaluations),
        skipped_reason_counts=skipped_reason_counts,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_ablation_v3_1",
        "report_key": report_key,
        "model_version": resolved_options.model_version,
        "feature_version": resolved_options.feature_version,
        "calibration_version": resolved_options.calibration_version,
        "shadow_only": True,
        "base_probability_source": "historical_slice_1x2_prediction_probability",
        "feature_source": "HistoricalFixture.feature_snapshot.features_json.prematch_context",
        "slice_count": len(historical_slices),
        "fixture_count": len(fixture_contexts),
        "validation_count": len(evaluations),
        "skipped_count": len(skipped),
        "skipped_reason_counts": skipped_reason_counts,
        "candidate_brier_score": overall.candidate.brier_score,
        "baseline_brier_score": overall.baseline.brier_score,
        "candidate_log_loss": overall.candidate.log_loss,
        "baseline_log_loss": overall.baseline.log_loss,
        "candidate_hit_rate": overall.candidate.hit_rate,
        "baseline_hit_rate": overall.baseline.hit_rate,
        "candidate_expected_calibration_error": (
            overall.candidate.expected_calibration_error
        ),
        "baseline_expected_calibration_error": (
            overall.baseline.expected_calibration_error
        ),
        "average_tracked_outcome_fragility_score": _safe_divide(
            sum(item.tracked_outcome_fragility_score for item in evaluations),
            len(evaluations),
        ),
        "average_draw_risk_score": _safe_divide(
            sum(item.draw_risk_score for item in evaluations),
            len(evaluations),
        ),
        "average_market_volatility_score": _safe_divide(
            sum(item.market_volatility_score for item in evaluations),
            len(evaluations),
        ),
        "average_lineup_strength_score": _safe_divide(
            sum(item.lineup_strength_score for item in evaluations),
            len(evaluations),
        ),
        "average_lineup_schedule_risk": _safe_divide(
            sum(item.lineup_schedule_risk for item in evaluations),
            len(evaluations),
        ),
        "average_key_player_absence_score": _safe_divide(
            sum(item.key_player_absence_score for item in evaluations),
            len(evaluations),
        ),
        "average_semantic_risk_score": _safe_divide(
            sum(item.semantic_risk_score for item in evaluations),
            len(evaluations),
        ),
        "average_source_ref_count": _safe_divide(
            sum(item.source_ref_count for item in evaluations),
            len(evaluations),
        ),
        "reason_code_counts": _reason_code_counts(evaluations),
        "signal_family_counts": _signal_family_counts(evaluations),
        "deltas_json": overall.deltas_json,
        "warnings": warnings,
    }
    return HistoricalPrematchFeatureAblationReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        fixture_count=len(fixture_contexts),
        validation_count=len(evaluations),
        skipped_count=len(skipped),
        skipped_reason_counts=skipped_reason_counts,
        overall=overall,
        by_competition=by_competition,
        by_season=by_season,
        by_competition_season=by_competition_season,
        sampled_predictions=evaluations[: resolved_options.prediction_sample_limit],
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_prematch_feature_ablation_report(
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


def _fixture_evaluations(
    fixture_contexts: Sequence[_FixtureContext],
    *,
    options: HistoricalPrematchFeatureAblationOptions,
) -> tuple[list[HistoricalPrematchFeatureAblationFixtureSample], list[_SkippedFixture]]:
    evaluations: list[HistoricalPrematchFeatureAblationFixtureSample] = []
    skipped: list[_SkippedFixture] = []
    for context in sorted(
        fixture_contexts,
        key=lambda item: (
            _aware_utc(item.fixture.kickoff_time_utc),
            item.fixture.fixture_id,
        ),
    ):
        fixture = context.fixture
        baseline_probabilities = _baseline_probabilities(fixture)
        if baseline_probabilities is None:
            skipped.append(_skipped(context, "missing_complete_1x2_baseline"))
            continue
        readout, skip_reason = _prematch_feature_readout(
            fixture,
            baseline_probabilities=baseline_probabilities,
            options=options,
        )
        if readout is None:
            skipped.append(_skipped(context, skip_reason or "missing_feature_readout"))
            continue
        adjustment = _apply_prematch_feature_adjustment(
            baseline_probabilities,
            readout=readout,
            options=options,
        )
        evaluations.append(
            _fixture_sample(
                context,
                baseline_probabilities=baseline_probabilities,
                candidate_probabilities=adjustment.probabilities,
                readout=readout,
                adjustment=adjustment,
            )
        )
    return evaluations, skipped


def _fixture_sample(
    context: _FixtureContext,
    *,
    baseline_probabilities: dict[str, float],
    candidate_probabilities: dict[str, float],
    readout: _PrematchFeatureReadout,
    adjustment: _ProbabilityAdjustment,
) -> HistoricalPrematchFeatureAblationFixtureSample:
    fixture = context.fixture
    actual_outcome = fixture.actual_1x2_outcome
    baseline_actual_probability = baseline_probabilities[actual_outcome]
    candidate_actual_probability = candidate_probabilities[actual_outcome]
    baseline_brier_score = _brier_score(baseline_probabilities, actual_outcome)
    candidate_brier_score = _brier_score(candidate_probabilities, actual_outcome)
    baseline_log_loss = _log_loss(baseline_actual_probability)
    candidate_log_loss = _log_loss(candidate_actual_probability)
    return HistoricalPrematchFeatureAblationFixtureSample(
        fixture_id=fixture.fixture_id,
        slice_id=context.slice_id,
        competition_id=fixture.competition_id,
        season=context.season,
        kickoff_time_utc=fixture.kickoff_time_utc,
        home_team_name=fixture.home_team_name,
        away_team_name=fixture.away_team_name,
        actual_outcome=actual_outcome,
        favorite_outcome=_predicted_outcome(baseline_probabilities),
        tracked_outcome=readout.tracked_outcome,
        favorite_fragility_score=readout.favorite_fragility_score,
        feature_data_quality_score=readout.feature_data_quality_score,
        tracked_outcome_fragility_score=readout.tracked_outcome_fragility_score,
        lineup_strength_score=readout.lineup_strength_score,
        draw_risk_score=readout.draw_risk_score,
        market_volatility_score=readout.market_volatility_score,
        lineup_schedule_risk=readout.lineup_schedule_risk,
        key_player_absence_score=readout.key_player_absence_score,
        semantic_risk_score=readout.semantic_risk_score,
        source_ref_count=readout.source_ref_count,
        odds_movement_probability_delta=readout.odds_movement_probability_delta,
        baseline_probabilities=baseline_probabilities,
        candidate_probabilities=candidate_probabilities,
        baseline_actual_probability=baseline_actual_probability,
        candidate_actual_probability=candidate_actual_probability,
        baseline_brier_score=baseline_brier_score,
        candidate_brier_score=candidate_brier_score,
        baseline_log_loss=baseline_log_loss,
        candidate_log_loss=candidate_log_loss,
        brier_score_delta_vs_baseline=candidate_brier_score - baseline_brier_score,
        log_loss_delta_vs_baseline=candidate_log_loss - baseline_log_loss,
        actual_probability_delta_vs_baseline=(
            candidate_actual_probability - baseline_actual_probability
        ),
        adjustment_json=adjustment.summary_json,
        feature_readout_json=readout.readout_json,
    )


def _prematch_feature_readout(
    fixture: HistoricalFixture,
    *,
    baseline_probabilities: dict[str, float],
    options: HistoricalPrematchFeatureAblationOptions,
) -> tuple[_PrematchFeatureReadout | None, str | None]:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return None, "missing_feature_snapshot"
    if snapshot.data_quality_score < options.min_feature_data_quality_score:
        return None, "feature_data_quality_below_threshold"
    if (
        options.require_feature_not_after_prediction
        and _aware_utc(snapshot.feature_time_utc) > _aware_utc(fixture.prediction_time_utc)
    ):
        return None, "feature_after_prediction_time"
    if (
        options.require_feature_before_kickoff
        and _aware_utc(snapshot.feature_time_utc) >= _aware_utc(fixture.kickoff_time_utc)
    ):
        return None, "feature_not_before_kickoff"

    prematch_context = _mapping(snapshot.features_json.get("prematch_context"))
    if prematch_context is None:
        return None, "missing_prematch_context"

    raw_lineup = _mapping(prematch_context.get("lineup"))
    raw_availability = _mapping(prematch_context.get("availability"))
    lineup = raw_lineup or {}
    availability = raw_availability or {}
    risk_signals = _mapping(prematch_context.get("risk_signals")) or {}
    odds_movements = _list_of_mappings(prematch_context.get("odds_movement"))
    semantic_signals = _list_of_mappings(prematch_context.get("semantic_signals"))
    signal_family_presence = {
        "lineup": raw_lineup is not None,
        "availability": raw_availability is not None,
        "odds_movement": bool(odds_movements),
        "semantic": bool(semantic_signals),
    }

    tracked_outcome = _tracked_outcome(odds_movements, baseline_probabilities)
    movement = _movement_for_outcome(odds_movements, tracked_outcome)
    odds_delta = _optional_float(movement.get("probability_delta")) if movement else None
    market_volatility = _clamp(
        max(
            _float(risk_signals.get("market_volatility_score")),
            abs(odds_delta or 0.0),
            _optional_float(movement.get("bookmaker_disagreement")) or 0.0
            if movement
            else 0.0,
        ),
        0.0,
        1.0,
    )
    lineup_risk = _lineup_risk(lineup)
    availability_risk = _availability_risk(availability)
    semantic_risk = _semantic_risk(semantic_signals)
    lineup_schedule_risk = _clamp(
        max(
            _float(risk_signals.get("lineup_schedule_risk")),
            lineup_risk,
            availability_risk,
        ),
        0.0,
        1.0,
    )
    tracked_drift_against = max(0.0, -(odds_delta or 0.0))
    tracked_fragility = _clamp(
        0.30 * lineup_risk
        + 0.30 * availability_risk
        + 0.18 * market_volatility
        + 0.17 * semantic_risk
        + 0.05 * min(1.0, tracked_drift_against * 4.0),
        0.0,
        1.0,
    )
    favorite_outcome = _predicted_outcome(baseline_probabilities)
    draw_risk = _draw_risk(
        baseline_probabilities,
        semantic_signals=semantic_signals,
        lineup_schedule_risk=lineup_schedule_risk,
        market_volatility_score=market_volatility,
    )
    lineup_strength = _lineup_strength(lineup, availability_risk=availability_risk)
    reason_codes = _feature_reason_codes(
        tracked_outcome=tracked_outcome,
        tracked_fragility=tracked_fragility,
        lineup_strength=lineup_strength,
        draw_risk=draw_risk,
        odds_delta=odds_delta,
        semantic_risk=semantic_risk,
        signal_family_presence=signal_family_presence,
    )
    source_ref_count = _source_ref_count(snapshot.source_snapshot_refs)
    favorite_fragility = tracked_fragility if tracked_outcome == favorite_outcome else 0.0
    readout_json: dict[str, object] = {
        "tracked_outcome": tracked_outcome,
        "favorite_outcome": favorite_outcome,
        "tracked_outcome_fragility_score": tracked_fragility,
        "favorite_fragility_score": favorite_fragility,
        "lineup_strength_score": lineup_strength,
        "draw_risk_score": draw_risk,
        "market_volatility_score": market_volatility,
        "lineup_schedule_risk": lineup_schedule_risk,
        "key_player_absence_score": _float(
            availability.get("key_player_absence_score")
        ),
        "odds_movement_probability_delta": odds_delta,
        "semantic_risk_score": semantic_risk,
        "source_ref_count": source_ref_count,
        "signal_family_presence": signal_family_presence,
        "reason_codes": reason_codes,
    }
    return (
        _PrematchFeatureReadout(
            feature_data_quality_score=snapshot.data_quality_score,
            tracked_outcome=tracked_outcome,
            tracked_outcome_fragility_score=tracked_fragility,
            favorite_fragility_score=favorite_fragility,
            lineup_strength_score=lineup_strength,
            draw_risk_score=draw_risk,
            market_volatility_score=market_volatility,
            lineup_schedule_risk=lineup_schedule_risk,
            key_player_absence_score=_float(
                availability.get("key_player_absence_score")
            ),
            odds_movement_probability_delta=odds_delta,
            semantic_risk_score=semantic_risk,
            source_ref_count=source_ref_count,
            reason_codes=reason_codes,
            readout_json=readout_json,
        ),
        None,
    )


def _apply_prematch_feature_adjustment(
    baseline_probabilities: dict[str, float],
    *,
    readout: _PrematchFeatureReadout,
    options: HistoricalPrematchFeatureAblationOptions,
) -> _ProbabilityAdjustment:
    raw_shifts = {outcome: 0.0 for outcome in ONE_X_TWO_OUTCOMES}
    reason_codes: list[str] = []
    if readout.odds_movement_probability_delta is not None:
        odds_shift = (
            readout.odds_movement_probability_delta * options.odds_movement_weight
        )
        raw_shifts[readout.tracked_outcome] += odds_shift
        if odds_shift != 0:
            reason_codes.append("odds_movement_shift")

    fragility_shift = (
        -options.max_probability_shift
        * options.tracked_fragility_weight
        * readout.tracked_outcome_fragility_score
    )
    raw_shifts[readout.tracked_outcome] += fragility_shift
    if fragility_shift < 0:
        _redistribute_from_tracked_outcome(
            raw_shifts,
            tracked_outcome=readout.tracked_outcome,
            amount=-fragility_shift,
            draw_share=_draw_redistribution_share(readout.draw_risk_score),
        )
        reason_codes.append("tracked_outcome_fragility_shift")

    strength_shift = (
        options.max_probability_shift
        * options.lineup_strength_weight
        * readout.lineup_strength_score
    )
    if strength_shift > 0:
        raw_shifts[readout.tracked_outcome] += strength_shift
        _remove_from_alternative_outcomes(
            raw_shifts,
            tracked_outcome=readout.tracked_outcome,
            amount=strength_shift,
            baseline_probabilities=baseline_probabilities,
        )
        reason_codes.append("lineup_strength_shift")

    draw_shift = (
        options.max_probability_shift
        * options.draw_signal_weight
        * readout.draw_risk_score
    )
    if draw_shift > 0 and readout.tracked_outcome != "draw":
        raw_shifts["draw"] += draw_shift
        raw_shifts[readout.tracked_outcome] -= draw_shift * 0.65
        _remove_from_alternative_outcomes(
            raw_shifts,
            tracked_outcome="draw",
            amount=draw_shift * 0.35,
            baseline_probabilities=baseline_probabilities,
        )
        reason_codes.append("draw_risk_shift")

    capped_shifts = {
        outcome: _clamp(shift, -options.max_probability_shift, options.max_probability_shift)
        for outcome, shift in raw_shifts.items()
    }
    candidate = _normalize_probabilities(
        {
            outcome: max(0.001, baseline_probabilities[outcome] + capped_shifts[outcome])
            for outcome in ONE_X_TWO_OUTCOMES
        }
    )
    if candidate is None:
        candidate = baseline_probabilities
    summary: dict[str, object] = {
        "calculation_basis": "prematch_feature_probability_adjustment_v3_1",
        "tracked_outcome": readout.tracked_outcome,
        "raw_shifts": raw_shifts,
        "capped_shifts": capped_shifts,
        "max_probability_shift": options.max_probability_shift,
        "reason_codes": [*readout.reason_codes, *reason_codes],
        "shadow_only": True,
    }
    return _ProbabilityAdjustment(
        probabilities=candidate,
        raw_shifts=raw_shifts,
        capped_shifts=capped_shifts,
        reason_codes=[*readout.reason_codes, *reason_codes],
        summary_json=summary,
    )


def _lineup_risk(lineup: Mapping[str, object]) -> float:
    confidence = _optional_float(lineup.get("expected_lineup_confidence"))
    strength = _optional_float(lineup.get("starting_xi_strength"))
    bench_dropoff = _float(lineup.get("bench_dropoff_score"))
    confidence_risk = 0.0 if confidence is None else max(0.0, 0.78 - confidence) / 0.78
    strength_risk = 0.0 if strength is None else max(0.0, 0.78 - strength) / 0.78
    return _clamp(
        0.40 * confidence_risk + 0.40 * strength_risk + 0.20 * bench_dropoff,
        0.0,
        1.0,
    )


def _availability_risk(availability: Mapping[str, object]) -> float:
    return _clamp(
        0.45 * _float(availability.get("key_player_absence_score"))
        + 0.20 * _float(availability.get("striker_absence_score"))
        + 0.18 * _float(availability.get("defender_absence_score"))
        + 0.17 * _float(availability.get("goalkeeper_absence_score")),
        0.0,
        1.0,
    )


def _lineup_strength(
    lineup: Mapping[str, object],
    *,
    availability_risk: float,
) -> float:
    confidence = _optional_float(lineup.get("expected_lineup_confidence"))
    strength = _optional_float(lineup.get("starting_xi_strength"))
    bench_dropoff = _float(lineup.get("bench_dropoff_score"))
    confidence_edge = 0.0 if confidence is None else max(0.0, confidence - 0.80) / 0.20
    strength_edge = 0.0 if strength is None else max(0.0, strength - 0.78) / 0.22
    return _clamp(
        0.45 * confidence_edge
        + 0.45 * strength_edge
        - 0.35 * availability_risk
        - 0.20 * bench_dropoff,
        0.0,
        1.0,
    )


def _semantic_risk(semantic_signals: Sequence[Mapping[str, object]]) -> float:
    risk_scores = [
        _float(signal.get("confidence"))
        for signal in semantic_signals
        if _semantic_signal_name(signal)
        in {
            "rotation_hint",
            "press_conference_injury_hint",
            "manager_change_recently",
            "relegation_pressure",
        }
    ]
    return max(risk_scores, default=0.0)


def _draw_risk(
    baseline_probabilities: dict[str, float],
    *,
    semantic_signals: Sequence[Mapping[str, object]],
    lineup_schedule_risk: float,
    market_volatility_score: float,
) -> float:
    draw_signal = max(
        (
            _float(signal.get("confidence"))
            for signal in semantic_signals
            if _semantic_signal_name(signal)
            in {"manager_change_recently", "rotation_hint", "relegation_pressure"}
        ),
        default=0.0,
    )
    baseline_draw_pressure = _clamp(
        (baseline_probabilities["draw"] - 0.25) / 0.20,
        0.0,
        1.0,
    )
    return _clamp(
        0.40 * draw_signal
        + 0.30 * baseline_draw_pressure
        + 0.20 * lineup_schedule_risk
        + 0.10 * market_volatility_score,
        0.0,
        1.0,
    )


def _feature_reason_codes(
    *,
    tracked_outcome: str,
    tracked_fragility: float,
    lineup_strength: float,
    draw_risk: float,
    odds_delta: float | None,
    semantic_risk: float,
    signal_family_presence: Mapping[str, bool],
) -> list[str]:
    reason_codes = [f"tracked_outcome:{tracked_outcome}"]
    if signal_family_presence.get("lineup"):
        reason_codes.append("lineup_signal_present")
    if signal_family_presence.get("availability"):
        reason_codes.append("availability_signal_present")
    if signal_family_presence.get("odds_movement"):
        reason_codes.append("odds_movement_signal_present")
    else:
        reason_codes.append("context_only_no_odds_movement")
    if signal_family_presence.get("semantic"):
        reason_codes.append("semantic_signal_present")
    if odds_delta is not None and odds_delta > 0:
        reason_codes.append("tracked_outcome_probability_shortened")
    if odds_delta is not None and odds_delta < 0:
        reason_codes.append("tracked_outcome_probability_drifted")
    if tracked_fragility >= 0.25:
        reason_codes.append("tracked_outcome_fragility_detected")
    if lineup_strength >= 0.25:
        reason_codes.append("lineup_strength_confirmed")
    if draw_risk >= 0.35:
        reason_codes.append("draw_risk_detected")
    if semantic_risk >= 0.50:
        reason_codes.append("semantic_prematch_risk_detected")
    return reason_codes


def _reason_code_counts(
    evaluations: Sequence[HistoricalPrematchFeatureAblationFixtureSample],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for evaluation in evaluations:
        for reason_code in _string_list(evaluation.adjustment_json.get("reason_codes")):
            counter[reason_code] += 1
    return dict(sorted(counter.items()))


def _signal_family_counts(
    evaluations: Sequence[HistoricalPrematchFeatureAblationFixtureSample],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for evaluation in evaluations:
        raw_presence = _mapping(evaluation.feature_readout_json.get("signal_family_presence"))
        if raw_presence is None:
            continue
        for signal_family, present in raw_presence.items():
            if present is True:
                counter[str(signal_family)] += 1
    return dict(sorted(counter.items()))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _redistribute_from_tracked_outcome(
    shifts: dict[str, float],
    *,
    tracked_outcome: str,
    amount: float,
    draw_share: float,
) -> None:
    alternatives = [outcome for outcome in ONE_X_TWO_OUTCOMES if outcome != tracked_outcome]
    if tracked_outcome == "draw":
        for outcome in alternatives:
            shifts[outcome] += amount / 2
        return
    non_draw_alternative = "away_win" if tracked_outcome == "home_win" else "home_win"
    shifts["draw"] += amount * draw_share
    shifts[non_draw_alternative] += amount * (1.0 - draw_share)


def _remove_from_alternative_outcomes(
    shifts: dict[str, float],
    *,
    tracked_outcome: str,
    amount: float,
    baseline_probabilities: dict[str, float],
) -> None:
    alternatives = [outcome for outcome in ONE_X_TWO_OUTCOMES if outcome != tracked_outcome]
    total = sum(baseline_probabilities[outcome] for outcome in alternatives)
    if total <= 0:
        for outcome in alternatives:
            shifts[outcome] -= amount / 2
        return
    for outcome in alternatives:
        shifts[outcome] -= amount * baseline_probabilities[outcome] / total


def _draw_redistribution_share(draw_risk_score: float) -> float:
    return _clamp(0.45 + 0.25 * draw_risk_score, 0.35, 0.70)


def _comparison_group(
    group_key: str,
    *,
    group_type: HistoricalPrematchFeatureAblationGroupType,
    label: str,
    evaluations: Sequence[HistoricalPrematchFeatureAblationFixtureSample],
    skipped: Sequence[_SkippedFixture],
    options: HistoricalPrematchFeatureAblationOptions,
    competition_id: str | None = None,
    season: str | None = None,
) -> HistoricalPrematchFeatureAblationComparisonGroup:
    candidate = _metric_set(
        evaluations,
        probability_fn=lambda item: item.candidate_probabilities,
        options=options,
    )
    baseline = _metric_set(
        evaluations,
        probability_fn=lambda item: item.baseline_probabilities,
        options=options,
    )
    deltas = _metric_deltas(candidate, baseline)
    skipped_reason_counts = dict(Counter(item.reason for item in skipped))
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_ablation_group_v3_1",
        "group_key": group_key,
        "group_type": group_type,
        "label": label,
        "validation_count": len(evaluations),
        "skipped_count": len(skipped),
        "skipped_reason_counts": skipped_reason_counts,
        "candidate": candidate.model_dump(mode="json"),
        "baseline": baseline.model_dump(mode="json"),
        "deltas_json": deltas,
    }
    return HistoricalPrematchFeatureAblationComparisonGroup(
        group_key=group_key,
        group_type=group_type,
        label=label,
        competition_id=competition_id,
        season=season,
        validation_count=len(evaluations),
        skipped_count=len(skipped),
        skipped_reason_counts=skipped_reason_counts,
        candidate=candidate,
        baseline=baseline,
        deltas_json=deltas,
        summary_json=summary,
    )


def _grouped_comparisons(
    evaluations: Sequence[HistoricalPrematchFeatureAblationFixtureSample],
    skipped: Sequence[_SkippedFixture],
    *,
    group_type: HistoricalPrematchFeatureAblationGroupType,
    key_fn: Callable[[HistoricalPrematchFeatureAblationFixtureSample], str],
    skipped_key_fn: Callable[[_SkippedFixture], str],
    label_fn: Callable[[str], str],
    options: HistoricalPrematchFeatureAblationOptions,
) -> list[HistoricalPrematchFeatureAblationComparisonGroup]:
    evaluation_groups: dict[str, list[HistoricalPrematchFeatureAblationFixtureSample]] = {}
    skipped_groups: dict[str, list[_SkippedFixture]] = {}
    for evaluation in evaluations:
        evaluation_groups.setdefault(key_fn(evaluation), []).append(evaluation)
    for skipped_fixture in skipped:
        skipped_groups.setdefault(skipped_key_fn(skipped_fixture), []).append(
            skipped_fixture
        )
    groups: list[HistoricalPrematchFeatureAblationComparisonGroup] = []
    for key in sorted(set(evaluation_groups) | set(skipped_groups)):
        competition_id: str | None = None
        season: str | None = None
        if group_type == "competition":
            competition_id = key
        elif group_type == "season":
            season = None if key == "unknown" else key
        elif group_type == "competition_season":
            competition_id, raw_season = key.split("|", maxsplit=1)
            season = None if raw_season == "unknown" else raw_season
        groups.append(
            _comparison_group(
                key,
                group_type=group_type,
                label=label_fn(key),
                evaluations=evaluation_groups.get(key, []),
                skipped=skipped_groups.get(key, []),
                options=options,
                competition_id=competition_id,
                season=season,
            )
        )
    return groups


def _metric_set(
    evaluations: Sequence[HistoricalPrematchFeatureAblationFixtureSample],
    *,
    probability_fn: Callable[
        [HistoricalPrematchFeatureAblationFixtureSample], dict[str, float]
    ],
    options: HistoricalPrematchFeatureAblationOptions,
) -> HistoricalPrematchFeatureAblationMetricSet:
    accumulator = _MetricAccumulator()
    for evaluation in evaluations:
        probabilities = probability_fn(evaluation)
        _observe_metric(
            accumulator,
            probabilities=probabilities,
            actual_outcome=evaluation.actual_outcome,
            bucket_size=options.bucket_size,
        )
    expected_calibration_error, included_bucket_count, skipped_bucket_count = (
        _expected_calibration_error(
            accumulator.calibration_buckets,
            min_bucket_sample_size=options.min_bucket_sample_size,
        )
    )
    return HistoricalPrematchFeatureAblationMetricSet(
        sample_size=accumulator.sample_size,
        hit_count=accumulator.hit_count,
        hit_rate=_safe_divide(accumulator.hit_count, accumulator.sample_size),
        brier_score=_safe_divide(
            accumulator.brier_score_sum,
            accumulator.sample_size,
        ),
        log_loss=_safe_divide(accumulator.log_loss_sum, accumulator.sample_size),
        average_actual_probability=_safe_divide(
            accumulator.actual_probability_sum,
            accumulator.sample_size,
        ),
        expected_calibration_error=expected_calibration_error,
        calibration_observation_count=sum(
            bucket.sample_size for bucket in accumulator.calibration_buckets.values()
        ),
        included_calibration_bucket_count=included_bucket_count,
        skipped_small_calibration_bucket_count=skipped_bucket_count,
    )


def _observe_metric(
    accumulator: _MetricAccumulator,
    *,
    probabilities: dict[str, float],
    actual_outcome: str,
    bucket_size: float,
) -> None:
    accumulator.sample_size += 1
    if _predicted_outcome(probabilities) == actual_outcome:
        accumulator.hit_count += 1
    actual_probability = probabilities[actual_outcome]
    accumulator.actual_probability_sum += actual_probability
    accumulator.brier_score_sum += _brier_score(probabilities, actual_outcome)
    accumulator.log_loss_sum += _log_loss(actual_probability)
    for outcome in ONE_X_TWO_OUTCOMES:
        probability = probabilities[outcome]
        bucket_start, bucket_end = _bucket_bounds(probability, bucket_size)
        key = (outcome, bucket_start, bucket_end)
        bucket = accumulator.calibration_buckets.setdefault(
            key,
            _CalibrationBucketAccumulator(),
        )
        bucket.sample_size += 1
        bucket.predicted_probability_sum += probability
        bucket.actual_count += 1 if outcome == actual_outcome else 0


def _expected_calibration_error(
    buckets: dict[tuple[str, float, float], _CalibrationBucketAccumulator],
    *,
    min_bucket_sample_size: int,
) -> tuple[float | None, int, int]:
    numerator = 0.0
    denominator = 0
    included_bucket_count = 0
    skipped_bucket_count = 0
    for bucket in buckets.values():
        if bucket.sample_size < min_bucket_sample_size:
            skipped_bucket_count += 1
            continue
        average_predicted = bucket.predicted_probability_sum / bucket.sample_size
        actual_frequency = bucket.actual_count / bucket.sample_size
        numerator += bucket.sample_size * abs(average_predicted - actual_frequency)
        denominator += bucket.sample_size
        included_bucket_count += 1
    return _safe_divide(numerator, denominator), included_bucket_count, skipped_bucket_count


def _metric_deltas(
    candidate: HistoricalPrematchFeatureAblationMetricSet,
    baseline: HistoricalPrematchFeatureAblationMetricSet,
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


def _fixture_contexts(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> list[_FixtureContext]:
    contexts: list[_FixtureContext] = []
    for historical_slice in historical_slices:
        contexts.extend(
            _FixtureContext(
                slice_id=historical_slice.metadata.slice_id,
                season=historical_slice.metadata.season,
                fixture=fixture,
            )
            for fixture in historical_slice.fixtures
        )
    return contexts


def _baseline_probabilities(fixture: HistoricalFixture) -> dict[str, float] | None:
    raw_probabilities = {
        prediction.outcome: prediction.probability
        for prediction in fixture.predictions
        if prediction.market_type == "1x2"
    }
    if any(outcome not in raw_probabilities for outcome in ONE_X_TWO_OUTCOMES):
        return None
    return _normalize_probabilities(
        {outcome: raw_probabilities[outcome] for outcome in ONE_X_TWO_OUTCOMES}
    )


def _normalize_probabilities(probabilities: dict[str, float]) -> dict[str, float] | None:
    total = sum(probabilities.values())
    if total <= 0:
        return None
    return {outcome: value / total for outcome, value in probabilities.items()}


def _tracked_outcome(
    odds_movements: Sequence[Mapping[str, object]],
    baseline_probabilities: dict[str, float],
) -> str:
    movement_candidates: list[tuple[float, str]] = []
    for movement in odds_movements:
        outcome = movement.get("outcome")
        probability_delta = _optional_float(movement.get("probability_delta"))
        if (
            isinstance(outcome, str)
            and outcome in ONE_X_TWO_OUTCOMES
            and probability_delta is not None
        ):
            movement_candidates.append((abs(probability_delta), outcome))
    if movement_candidates:
        return max(movement_candidates, key=lambda item: item[0])[1]
    for movement in odds_movements:
        outcome = movement.get("outcome")
        if isinstance(outcome, str) and outcome in ONE_X_TWO_OUTCOMES:
            return outcome
    return _predicted_outcome(baseline_probabilities)


def _movement_for_outcome(
    odds_movements: Sequence[Mapping[str, object]],
    outcome: str,
) -> Mapping[str, object]:
    for movement in odds_movements:
        if movement.get("outcome") == outcome:
            return movement
    return {}


def _semantic_signal_name(signal: Mapping[str, object]) -> str:
    value = signal.get("signal_name")
    return value if isinstance(value, str) else ""


def _source_ref_count(source_refs: Mapping[str, object]) -> int:
    prematch_refs = _mapping(source_refs.get("prematch"))
    if prematch_refs is None:
        return len(source_refs)
    count = 0
    for value in prematch_refs.values():
        if isinstance(value, list):
            count += len(value)
        elif value:
            count += 1
    return count


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _list_of_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _brier_score(probabilities: dict[str, float], actual_outcome: str) -> float:
    return sum(
        (probabilities[outcome] - (1.0 if outcome == actual_outcome else 0.0)) ** 2
        for outcome in ONE_X_TWO_OUTCOMES
    )


def _log_loss(probability: float) -> float:
    bounded_probability = min(
        max(probability, DEFAULT_LOG_LOSS_EPSILON),
        1.0 - DEFAULT_LOG_LOSS_EPSILON,
    )
    return -log(bounded_probability)


def _predicted_outcome(probabilities: dict[str, float]) -> str:
    return max(ONE_X_TWO_OUTCOMES, key=lambda outcome: probabilities[outcome])


def _bucket_bounds(probability: float, bucket_size: float) -> tuple[float, float]:
    if probability == 1.0:
        bucket_start = max(0.0, 1.0 - bucket_size)
    else:
        bucket_start = floor(probability / bucket_size) * bucket_size
    bucket_end = min(1.0, bucket_start + bucket_size)
    return round(bucket_start, 10), round(bucket_end, 10)


def _skipped(context: _FixtureContext, reason: str) -> _SkippedFixture:
    return _SkippedFixture(
        fixture_id=context.fixture.fixture_id,
        competition_id=context.fixture.competition_id,
        season=context.season,
        reason=reason,
    )


def _report_warnings(
    evaluations: Sequence[HistoricalPrematchFeatureAblationFixtureSample],
    skipped: Sequence[_SkippedFixture],
) -> list[str]:
    warnings: list[str] = []
    if not evaluations:
        warnings.append("historical_prematch_feature_ablation:no_validation_fixtures")
    if skipped:
        warnings.append("historical_prematch_feature_ablation:skipped_fixtures")
    return warnings


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureAblationOptions,
    validation_count: int,
    skipped_reason_counts: dict[str, int],
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "as_of_times": [
            historical_slice.as_of_time_utc.isoformat()
            for historical_slice in historical_slices
        ],
        "validation_count": validation_count,
        "skipped_reason_counts": skipped_reason_counts,
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_ablation:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run a shadow ablation for structured pre-match FeatureSnapshot payloads."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-feature-data-quality-score", type=float, default=80.0)
    parser.add_argument("--max-probability-shift", type=float, default=0.12)
    parser.add_argument("--odds-movement-weight", type=float, default=0.35)
    parser.add_argument("--tracked-fragility-weight", type=float, default=1.0)
    parser.add_argument("--lineup-strength-weight", type=float, default=0.35)
    parser.add_argument("--draw-signal-weight", type=float, default=0.35)
    parser.add_argument("--bucket-size", type=float, default=0.10)
    parser.add_argument("--min-bucket-sample-size", type=int, default=1)
    parser.add_argument(
        "--allow-feature-after-prediction",
        action="store_true",
    )
    parser.add_argument(
        "--allow-feature-not-before-kickoff",
        action="store_true",
    )
    parser.add_argument(
        "--model-version",
        default=DEFAULT_PREMATCH_FEATURE_ABLATION_MODEL_VERSION,
    )
    parser.add_argument(
        "--feature-version",
        default=DEFAULT_PREMATCH_FEATURE_ABLATION_FEATURE_VERSION,
    )
    parser.add_argument(
        "--calibration-version",
        default=DEFAULT_PREMATCH_FEATURE_ABLATION_CALIBRATION_VERSION,
    )
    parser.add_argument("--prediction-sample-limit", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalPrematchFeatureAblationOptions:
    return HistoricalPrematchFeatureAblationOptions(
        min_feature_data_quality_score=args.min_feature_data_quality_score,
        max_probability_shift=args.max_probability_shift,
        odds_movement_weight=args.odds_movement_weight,
        tracked_fragility_weight=args.tracked_fragility_weight,
        lineup_strength_weight=args.lineup_strength_weight,
        draw_signal_weight=args.draw_signal_weight,
        bucket_size=args.bucket_size,
        min_bucket_sample_size=args.min_bucket_sample_size,
        require_feature_not_after_prediction=not args.allow_feature_after_prediction,
        require_feature_before_kickoff=not args.allow_feature_not_before_kickoff,
        model_version=args.model_version,
        feature_version=args.feature_version,
        calibration_version=args.calibration_version,
        prediction_sample_limit=args.prediction_sample_limit,
    )


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


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


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _float(value: object) -> float:
    return _optional_float(value) or 0.0


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline
