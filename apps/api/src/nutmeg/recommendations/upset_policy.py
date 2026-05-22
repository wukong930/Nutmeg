from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.models import RecommendationCandidate

type RecommendationUpsetDirection = Literal[
    "none",
    "draw_overlooked",
    "underdog_protection",
    "handicap_protection",
    "favorite_fragility_avoidance",
    "upset_protection",
]


class RecommendationUpsetSignal(BaseModel):
    fixture_id: str
    outcome: str
    direction: RecommendationUpsetDirection = "none"
    signal_score: float = Field(ge=0.0, le=1.0)
    protection_score: float = Field(ge=0.0, le=1.0)
    favorite_fragility_score: float = Field(ge=0.0, le=1.0)
    avoidance_penalty: float = Field(ge=0.0, le=1.0)
    model_edge_signal: float = Field(ge=0.0, le=1.0)
    odds_anomaly_signal: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)


def analyze_candidate_upset_signal(
    candidate: RecommendationCandidate,
) -> RecommendationUpsetSignal:
    explicit_upset_score = _explicit_upset_score(candidate)
    favorite_likelihood = _favorite_likelihood(candidate)
    protection_hint = _protection_outcome_hint(candidate)
    model_edge_signal = _model_edge_signal(candidate)
    odds_anomaly_signal = _odds_anomaly_signal(candidate)
    favorite_fragility_score = _favorite_fragility_score(
        candidate,
        explicit_upset_score=explicit_upset_score,
        favorite_likelihood=favorite_likelihood,
        odds_anomaly_signal=odds_anomaly_signal,
    )
    protection_score = _protection_score(
        explicit_upset_score=explicit_upset_score,
        protection_hint=protection_hint,
        favorite_likelihood=favorite_likelihood,
        model_edge_signal=model_edge_signal,
        odds_anomaly_signal=odds_anomaly_signal,
    )
    avoidance_penalty = _avoidance_penalty(
        candidate,
        favorite_likelihood=favorite_likelihood,
        favorite_fragility_score=favorite_fragility_score,
        protection_hint=protection_hint,
        odds_anomaly_signal=odds_anomaly_signal,
    )
    direction = _upset_direction(
        candidate,
        protection_hint=protection_hint,
        protection_score=protection_score,
        avoidance_penalty=avoidance_penalty,
        explicit_upset_score=explicit_upset_score,
    )
    signal_score = _clamp(max(protection_score, favorite_fragility_score))
    return RecommendationUpsetSignal(
        fixture_id=candidate.fixture_id,
        outcome=candidate.outcome,
        direction=direction,
        signal_score=signal_score,
        protection_score=protection_score,
        favorite_fragility_score=favorite_fragility_score,
        avoidance_penalty=avoidance_penalty,
        model_edge_signal=model_edge_signal,
        odds_anomaly_signal=odds_anomaly_signal,
        reason_codes=_reason_codes(
            direction=direction,
            protection_score=protection_score,
            avoidance_penalty=avoidance_penalty,
            model_edge_signal=model_edge_signal,
            odds_anomaly_signal=odds_anomaly_signal,
        ),
    )


def aggregate_upset_quality(
    candidates: Sequence[RecommendationCandidate],
) -> float:
    if not candidates:
        return 0.50
    signals = [analyze_candidate_upset_signal(candidate) for candidate in candidates]
    max_protection = max(signal.protection_score for signal in signals)
    max_avoidance = max(signal.avoidance_penalty for signal in signals)
    average_signal = sum(signal.signal_score for signal in signals) / len(signals)
    return _clamp(0.50 + 0.34 * max_protection + 0.16 * average_signal - 0.32 * max_avoidance)


def build_upset_policy_payload(
    candidates: Sequence[RecommendationCandidate],
) -> dict[str, object]:
    signals = [analyze_candidate_upset_signal(candidate) for candidate in candidates]
    return {
        "calculation_basis": "recommendation_upset_policy_v3_1",
        "upset_quality": aggregate_upset_quality(candidates),
        "max_protection_score": max(
            (signal.protection_score for signal in signals),
            default=0.0,
        ),
        "max_avoidance_penalty": max(
            (signal.avoidance_penalty for signal in signals),
            default=0.0,
        ),
        "directions": sorted(
            {signal.direction for signal in signals if signal.direction != "none"}
        ),
        "reason_codes": _dedupe(
            code for signal in signals for code in signal.reason_codes
        ),
    }


def _explicit_upset_score(candidate: RecommendationCandidate) -> float:
    return max(
        candidate.upset_protection_score,
        _metadata_score(candidate, "upset_score"),
    )


def _favorite_fragility_score(
    candidate: RecommendationCandidate,
    *,
    explicit_upset_score: float,
    favorite_likelihood: float,
    odds_anomaly_signal: float,
) -> float:
    metadata_fragility = _metadata_score(candidate, "favorite_fragility_score")
    fragility_seed = max(metadata_fragility, explicit_upset_score * favorite_likelihood)
    return _clamp(
        0.70 * fragility_seed
        + 0.18 * odds_anomaly_signal
        + 0.12 * candidate.volatility_penalty
    )


def _protection_score(
    *,
    explicit_upset_score: float,
    protection_hint: float,
    favorite_likelihood: float,
    model_edge_signal: float,
    odds_anomaly_signal: float,
) -> float:
    favorite_discount = 1.0 - 0.70 * favorite_likelihood * (1.0 - protection_hint)
    signal = (
        0.58 * explicit_upset_score * max(protection_hint, 0.20)
        + 0.18 * protection_hint
        + 0.16 * model_edge_signal
        + 0.08 * odds_anomaly_signal
    )
    return _clamp(signal * favorite_discount)


def _avoidance_penalty(
    candidate: RecommendationCandidate,
    *,
    favorite_likelihood: float,
    favorite_fragility_score: float,
    protection_hint: float,
    odds_anomaly_signal: float,
) -> float:
    if favorite_likelihood < 0.45:
        return 0.0
    protection_discount = 1.0 - 0.65 * protection_hint
    negative_edge = _clamp(-candidate.effective_model_edge() / 0.12)
    return _clamp(
        protection_discount
        * (
            0.68 * favorite_fragility_score
            + 0.17 * odds_anomaly_signal
            + 0.10 * candidate.volatility_penalty
            + 0.05 * negative_edge
        )
    )


def _upset_direction(
    candidate: RecommendationCandidate,
    *,
    protection_hint: float,
    protection_score: float,
    avoidance_penalty: float,
    explicit_upset_score: float,
) -> RecommendationUpsetDirection:
    metadata_direction = _metadata_text(candidate, "upset_direction")
    if metadata_direction in {
        "draw_overlooked",
        "underdog_protection",
        "handicap_protection",
        "favorite_fragility_avoidance",
        "upset_protection",
    }:
        return metadata_direction  # type: ignore[return-value]
    if avoidance_penalty >= 0.45:
        return "favorite_fragility_avoidance"
    outcome = candidate.outcome.lower()
    if "draw" in outcome and protection_score >= 0.20:
        return "draw_overlooked"
    if "handicap_away" in outcome and protection_score >= 0.20:
        return "handicap_protection"
    if protection_hint >= 0.55 and protection_score >= 0.20:
        return "underdog_protection"
    if explicit_upset_score > 0 or protection_score >= 0.20:
        return "upset_protection"
    return "none"


def _protection_outcome_hint(candidate: RecommendationCandidate) -> float:
    metadata_target = _metadata_text(candidate, "target_outcome")
    outcome = candidate.outcome.lower()
    if metadata_target and metadata_target == outcome:
        return 1.0
    hints = []
    if "draw" in outcome:
        hints.append(0.86)
    if "handicap_away" in outcome or "underdog" in outcome:
        hints.append(0.78)
    if outcome == "away_win" and candidate.decimal_odds is not None:
        if candidate.decimal_odds >= 2.25:
            hints.append(0.62)
        elif _explicit_upset_score(candidate) >= 0.50:
            hints.append(0.42)
    elif outcome == "away_win":
        hints.append(0.62)
    if candidate.decimal_odds is not None and candidate.decimal_odds >= 2.80:
        hints.append(min(1.0, 0.45 + (candidate.decimal_odds - 2.80) / 4.0))
    if (
        candidate.market_type in {"cn_handicap_1x2", "european_handicap_1x2"}
        and ("away" in outcome or "draw" in outcome)
    ):
        hints.append(0.65)
    return max(hints, default=0.0)


def _favorite_likelihood(candidate: RecommendationCandidate) -> float:
    probability_signal = _clamp((candidate.probability - 0.45) / 0.25)
    market_probability = candidate.effective_market_probability()
    market_signal = (
        _clamp((market_probability - 0.44) / 0.28)
        if market_probability is not None
        else 0.0
    )
    price_signal = (
        _clamp((2.30 - candidate.decimal_odds) / 1.15)
        if candidate.decimal_odds is not None
        else 0.0
    )
    return max(probability_signal, market_signal, price_signal)


def _model_edge_signal(candidate: RecommendationCandidate) -> float:
    return _clamp((candidate.effective_model_edge() + 0.02) / 0.16)


def _odds_anomaly_signal(candidate: RecommendationCandidate) -> float:
    return _clamp(
        0.58 * (1.0 - candidate.odds_stability_score)
        + 0.42 * candidate.volatility_penalty
    )


def _metadata_score(candidate: RecommendationCandidate, key: str) -> float:
    raw = candidate.metadata_json.get(key)
    if isinstance(raw, int | float):
        return _clamp(float(raw))
    return 0.0


def _metadata_text(candidate: RecommendationCandidate, key: str) -> str | None:
    raw = candidate.metadata_json.get(key)
    if not isinstance(raw, str):
        return None
    text = raw.strip().lower()
    return text or None


def _reason_codes(
    *,
    direction: RecommendationUpsetDirection,
    protection_score: float,
    avoidance_penalty: float,
    model_edge_signal: float,
    odds_anomaly_signal: float,
) -> list[str]:
    reason_codes: list[str] = []
    if direction != "none":
        reason_codes.append(f"upset_direction_{direction}")
    if protection_score >= 0.35:
        reason_codes.append("upset_protection_quality")
    if avoidance_penalty >= 0.35:
        reason_codes.append("favorite_fragility_avoidance")
    if model_edge_signal >= 0.60:
        reason_codes.append("upset_model_edge_signal")
    if odds_anomaly_signal >= 0.55:
        reason_codes.append("upset_odds_anomaly_signal")
    return reason_codes


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
