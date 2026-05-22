from __future__ import annotations


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


def risk_level_from_score(risk_score: float) -> str:
    if risk_score >= 0.75:
        return "high"
    if risk_score >= 0.50:
        return "medium_high"
    if risk_score >= 0.30:
        return "medium"
    return "low"


def placeholder_risk_score(
    *,
    hit_probability: float,
    total_atomic_bets: int,
    correlation_penalty: float,
) -> float:
    complexity_penalty = min(0.25, max(total_atomic_bets - 1, 0) * 0.04)
    base_risk = 1.0 - hit_probability
    return clamp_probability(base_risk + complexity_penalty + correlation_penalty)
