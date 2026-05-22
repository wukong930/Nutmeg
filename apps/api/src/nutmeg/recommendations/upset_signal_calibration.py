from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, Field

from nutmeg.recommendations.models import RecommendationCandidate
from nutmeg.recommendations.upset_policy import (
    RecommendationUpsetSignal,
    analyze_candidate_upset_signal,
)


class RecommendationUpsetSignalCalibrationConfig(BaseModel):
    min_observation_count: int = Field(default=3, ge=1)
    max_hit_probability_deficit: float = Field(default=0.20, ge=0.0, le=1.0)
    max_brier_score_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    max_log_loss_delta: float = Field(default=0.0, ge=-10.0, le=10.0)
    max_calibration_error_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    shape_prior_weight: float = Field(default=0.40, ge=0.0, le=1.0)


class RecommendationUpsetSignalCalibration(BaseModel):
    fixture_id: str
    outcome: str
    risk_score: float = Field(ge=0.0, le=1.0)
    reliability_score: float = Field(ge=0.0, le=1.0)
    observed_profile: bool = False
    observation_count: int = Field(default=0, ge=0)
    hit_probability_deficit: float = Field(default=0.0, ge=0.0, le=1.0)
    brier_score_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    log_loss_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    calibration_error_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    shape_prior_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def assess_upset_signal_calibration(
    candidate: RecommendationCandidate,
    *,
    upset_signal: RecommendationUpsetSignal | None = None,
    config: RecommendationUpsetSignalCalibrationConfig | None = None,
) -> RecommendationUpsetSignalCalibration:
    resolved_config = config or RecommendationUpsetSignalCalibrationConfig()
    signal = upset_signal or analyze_candidate_upset_signal(candidate)
    if signal.protection_score < 0.20 and candidate.upset_protection_score < 0.20:
        return RecommendationUpsetSignalCalibration(
            fixture_id=candidate.fixture_id,
            outcome=candidate.outcome,
            risk_score=0.0,
            reliability_score=1.0,
            reason_codes=["upset_signal_calibration:not_upset_lane"],
        )

    historical_metrics = _historical_metrics(candidate.metadata_json)
    shape_prior_pressure = _shape_prior_pressure(candidate, signal)
    if historical_metrics is None:
        risk_score = resolved_config.shape_prior_weight * shape_prior_pressure
        return RecommendationUpsetSignalCalibration(
            fixture_id=candidate.fixture_id,
            outcome=candidate.outcome,
            risk_score=_clamp(risk_score),
            reliability_score=_clamp(1.0 - risk_score),
            observed_profile=False,
            observation_count=0,
            shape_prior_pressure=shape_prior_pressure,
            reason_codes=_reason_codes(
                observed_profile=False,
                risk_score=risk_score,
                hit_probability_deficit=0.0,
                brier_score_pressure=0.0,
                log_loss_pressure=0.0,
                calibration_error_pressure=0.0,
                shape_prior_pressure=shape_prior_pressure,
            ),
            summary_json={
                "calculation_basis": "upset_signal_calibration_v3_1",
                "profile_source": "shape_prior",
            },
        )

    observation_count = historical_metrics.observation_count
    hit_probability_deficit = max(0.0, -historical_metrics.average_hit_probability_delta)
    brier_score_pressure = _positive_delta_pressure(
        historical_metrics.average_brier_score_delta,
        threshold=resolved_config.max_brier_score_delta,
        scale=0.35,
    )
    log_loss_pressure = _positive_delta_pressure(
        historical_metrics.average_log_loss_delta,
        threshold=resolved_config.max_log_loss_delta,
        scale=0.80,
    )
    calibration_error_pressure = _positive_delta_pressure(
        historical_metrics.average_calibration_error_delta,
        threshold=resolved_config.max_calibration_error_delta,
        scale=0.30,
    )
    deficit_pressure = _positive_delta_pressure(
        hit_probability_deficit,
        threshold=resolved_config.max_hit_probability_deficit,
        scale=0.30,
    )
    sample_discount = 1.0 if observation_count >= resolved_config.min_observation_count else 0.55
    observed_risk = sample_discount * (
        0.36 * deficit_pressure
        + 0.24 * brier_score_pressure
        + 0.22 * log_loss_pressure
        + 0.18 * calibration_error_pressure
    )
    risk_score = _clamp(
        observed_risk + resolved_config.shape_prior_weight * 0.35 * shape_prior_pressure
    )
    return RecommendationUpsetSignalCalibration(
        fixture_id=candidate.fixture_id,
        outcome=candidate.outcome,
        risk_score=risk_score,
        reliability_score=_clamp(1.0 - risk_score),
        observed_profile=True,
        observation_count=observation_count,
        hit_probability_deficit=hit_probability_deficit,
        brier_score_pressure=brier_score_pressure,
        log_loss_pressure=log_loss_pressure,
        calibration_error_pressure=calibration_error_pressure,
        shape_prior_pressure=shape_prior_pressure,
        reason_codes=_reason_codes(
            observed_profile=True,
            risk_score=risk_score,
            hit_probability_deficit=hit_probability_deficit,
            brier_score_pressure=brier_score_pressure,
            log_loss_pressure=log_loss_pressure,
            calibration_error_pressure=calibration_error_pressure,
            shape_prior_pressure=shape_prior_pressure,
        ),
        summary_json={
            "calculation_basis": "upset_signal_calibration_v3_1",
            "profile_source": historical_metrics.profile_key,
            "average_hit_probability_delta": (
                historical_metrics.average_hit_probability_delta
            ),
            "average_brier_score_delta": historical_metrics.average_brier_score_delta,
            "average_log_loss_delta": historical_metrics.average_log_loss_delta,
            "average_calibration_error_delta": (
                historical_metrics.average_calibration_error_delta
            ),
        },
    )


class _HistoricalUpsetSignalMetrics(BaseModel):
    profile_key: str | None = None
    observation_count: int = Field(default=0, ge=0)
    average_hit_probability_delta: float = 0.0
    average_brier_score_delta: float = 0.0
    average_log_loss_delta: float = 0.0
    average_calibration_error_delta: float = 0.0


def _historical_metrics(
    metadata_json: Mapping[str, object],
) -> _HistoricalUpsetSignalMetrics | None:
    nested = metadata_json.get("upset_signal_calibration")
    if isinstance(nested, Mapping):
        source: Mapping[str, object] = nested
    else:
        source = metadata_json
    observation_count = _metadata_int(
        source,
        "historical_upset_signal_observation_count",
        "historical_upset_profile_observation_count",
        "observation_count",
    )
    if observation_count is None:
        return None
    return _HistoricalUpsetSignalMetrics(
        profile_key=_metadata_text(
            source,
            "historical_upset_signal_profile_key",
            "historical_upset_profile_key",
            "profile_key",
        ),
        observation_count=observation_count,
        average_hit_probability_delta=_metadata_float(
            source,
            "historical_upset_signal_average_hit_probability_delta",
            "historical_upset_profile_average_hit_probability_delta",
            "average_hit_probability_delta",
        )
        or 0.0,
        average_brier_score_delta=_metadata_float(
            source,
            "historical_upset_signal_average_brier_score_delta",
            "historical_upset_profile_average_brier_score_delta",
            "average_brier_score_delta",
        )
        or 0.0,
        average_log_loss_delta=_metadata_float(
            source,
            "historical_upset_signal_average_log_loss_delta",
            "historical_upset_profile_average_log_loss_delta",
            "average_log_loss_delta",
        )
        or 0.0,
        average_calibration_error_delta=_metadata_float(
            source,
            "historical_upset_signal_average_calibration_error_delta",
            "historical_upset_profile_average_calibration_error_delta",
            "average_calibration_error_delta",
        )
        or 0.0,
    )


def _shape_prior_pressure(
    candidate: RecommendationCandidate,
    signal: RecommendationUpsetSignal,
) -> float:
    if candidate.decimal_odds is None:
        return 0.0
    protection_pressure = max(signal.protection_score, candidate.upset_protection_score)
    if protection_pressure < 0.35:
        return 0.0
    low_probability_pressure = _clamp((0.30 - candidate.probability) / 0.16)
    long_odds_pressure = _clamp((candidate.decimal_odds - 3.50) / 2.50)
    negative_edge_pressure = _clamp((0.01 - candidate.effective_model_edge()) / 0.08)
    calibration_gap = _clamp(1.0 - candidate.calibration_score)
    return _clamp(
        protection_pressure
        * (
            0.34 * low_probability_pressure
            + 0.28 * long_odds_pressure
            + 0.22 * negative_edge_pressure
            + 0.16 * calibration_gap
        )
    )


def _positive_delta_pressure(value: float, *, threshold: float, scale: float) -> float:
    return _clamp((value - threshold) / max(scale, 0.01))


def _reason_codes(
    *,
    observed_profile: bool,
    risk_score: float,
    hit_probability_deficit: float,
    brier_score_pressure: float,
    log_loss_pressure: float,
    calibration_error_pressure: float,
    shape_prior_pressure: float,
) -> list[str]:
    reason_codes = [
        "upset_signal_calibration:observed_profile"
        if observed_profile
        else "upset_signal_calibration:shape_prior"
    ]
    if risk_score >= 0.20:
        reason_codes.append("upset_signal_calibration:risk_penalty")
    if hit_probability_deficit > 0.20:
        reason_codes.append("upset_signal_calibration:hit_probability_deficit")
    if brier_score_pressure > 0:
        reason_codes.append("upset_signal_calibration:brier_pressure")
    if log_loss_pressure > 0:
        reason_codes.append("upset_signal_calibration:log_loss_pressure")
    if calibration_error_pressure > 0:
        reason_codes.append("upset_signal_calibration:calibration_error_pressure")
    if shape_prior_pressure >= 0.30:
        reason_codes.append("upset_signal_calibration:longshot_shape_prior")
    return reason_codes


def _metadata_float(
    metadata_json: Mapping[str, object],
    *keys: str,
) -> float | None:
    for key in keys:
        raw = metadata_json.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int | float):
            return float(raw)
    return None


def _metadata_int(
    metadata_json: Mapping[str, object],
    *keys: str,
) -> int | None:
    for key in keys:
        raw = metadata_json.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float) and raw.is_integer():
            return int(raw)
    return None


def _metadata_text(
    metadata_json: Mapping[str, object],
    *keys: str,
) -> str | None:
    for key in keys:
        raw = metadata_json.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
