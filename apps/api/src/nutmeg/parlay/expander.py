from __future__ import annotations

from itertools import product
from math import prod

from nutmeg.domain.parlay import AtomicBet, AtomicLeg, ParlayEvaluation, ParlayLegSelection
from nutmeg.parlay.risk import placeholder_risk_score, risk_level_from_score
from nutmeg.parlay.rules import ParlayRuleConfig, evaluate_parlay_rules


def _atomic_leg(selection: ParlayLegSelection, outcome: str) -> AtomicLeg:
    try:
        probability = selection.probabilities[outcome]
        odds = selection.odds[outcome]
    except KeyError as exc:
        raise ValueError(f"missing probability or odds for outcome {outcome}") from exc
    return AtomicLeg(
        fixture_id=selection.fixture_id,
        market_type=selection.market_type,
        outcome=outcome,
        probability=probability,
        odds=odds,
        line=selection.line,
        side=selection.side,
        model_version=selection.model_version,
        prediction_snapshot_id=selection.prediction_snapshot_id,
        correlation_key=selection.correlation_key,
    )


def expand_atomic_bets(
    legs: list[ParlayLegSelection],
    *,
    unit_stake: float = 1.0,
    multiplier: int = 1,
) -> list[AtomicBet]:
    if not legs:
        return []
    if unit_stake <= 0:
        raise ValueError("unit_stake must be positive")
    if multiplier < 1:
        raise ValueError("multiplier must be at least 1")

    atomic_bets: list[AtomicBet] = []
    for outcome_tuple in product(*(leg.outcomes for leg in legs)):
        atomic_legs = [
            _atomic_leg(leg, outcome) for leg, outcome in zip(legs, outcome_tuple, strict=True)
        ]
        probability = prod(atomic_leg.probability for atomic_leg in atomic_legs)
        odds_product = prod(atomic_leg.odds for atomic_leg in atomic_legs)
        stake = unit_stake * multiplier
        expected_payout = stake * probability * odds_product
        expected_value = expected_payout - stake
        roi = expected_value / stake
        atomic_bets.append(
            AtomicBet(
                legs=atomic_legs,
                stake=stake,
                probability=probability,
                odds_product=odds_product,
                expected_payout=expected_payout,
                expected_value=expected_value,
                roi=roi,
            )
        )
    return atomic_bets


def hit_probability(legs: list[ParlayLegSelection]) -> float:
    if not legs:
        return 0.0
    return prod(sum(leg.probabilities[outcome] for outcome in leg.outcomes) for leg in legs)


def is_multiple_parlay(legs: list[ParlayLegSelection]) -> bool:
    return any(len(leg.outcomes) > 1 for leg in legs)


def _selected_probability_by_fixture(legs: list[ParlayLegSelection]) -> dict[str, float]:
    return {
        leg.fixture_id: sum(leg.probabilities[outcome] for outcome in leg.outcomes)
        for leg in legs
    }


def _derived_correlation_penalty(legs: list[ParlayLegSelection]) -> float:
    exposure_counts: dict[str, int] = {}
    for leg in legs:
        if not leg.correlation_key:
            continue
        exposure_counts[leg.correlation_key] = exposure_counts.get(leg.correlation_key, 0) + 1
    repeated_exposure_count = sum(count - 1 for count in exposure_counts.values() if count > 1)
    return min(0.30, 0.07 * repeated_exposure_count)


def _correlation_exposure_payload(legs: list[ParlayLegSelection]) -> dict[str, int]:
    exposure_counts: dict[str, int] = {}
    for leg in legs:
        if not leg.correlation_key:
            continue
        exposure_counts[leg.correlation_key] = exposure_counts.get(leg.correlation_key, 0) + 1
    return {
        key: count
        for key, count in sorted(exposure_counts.items())
        if count > 1
    }


def _explanation_payload(
    legs: list[ParlayLegSelection],
    *,
    pass_type: str,
    unit_stake: float,
    multiplier: int,
    max_budget: float | None,
    total_stake: float,
    hit_probability_value: float,
    adjusted_hit_probability: float,
    risk_score: float,
    risk_level: str,
    correlation_exposures: dict[str, int],
    min_data_quality_score_for_recommendation: float,
    rule_reasons: list[str],
) -> dict[str, object]:
    return {
        "calculation_basis": "independent_fixture_approximation",
        "pass_type": pass_type,
        "is_multiple": is_multiple_parlay(legs),
        "unit_stake": unit_stake,
        "multiplier": multiplier,
        "budget": {
            "max_budget": max_budget,
            "total_stake": total_stake,
            "within_budget": max_budget is None or total_stake <= max_budget,
        },
        "selected_probability_by_fixture": _selected_probability_by_fixture(legs),
        "hit_probability_raw": hit_probability_value,
        "hit_probability_after_correlation_penalty": adjusted_hit_probability,
        "correlation_exposures": correlation_exposures,
        "risk": {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "method": "placeholder_v1",
        },
        "data_quality": {
            "minimum_score_for_recommendation": min_data_quality_score_for_recommendation,
            "leg_scores": {
                leg.fixture_id: leg.data_quality_score
                for leg in legs
                if leg.data_quality_score is not None
            },
        },
        "model_lineage": {
            "model_versions": sorted(
                {leg.model_version for leg in legs if leg.model_version is not None}
            ),
            "prediction_snapshot_ids": [
                leg.prediction_snapshot_id
                for leg in legs
                if leg.prediction_snapshot_id is not None
            ],
        },
        "rule_reasons": rule_reasons,
        "notes": [
            "Expected payout, EV, and ROI use model probabilities and decimal odds.",
            "This is probability analysis only and does not place or recommend a bet.",
        ],
    }


def evaluate_parlay(
    legs: list[ParlayLegSelection],
    *,
    pass_type: str,
    unit_stake: float,
    multiplier: int = 1,
    max_budget: float | None = None,
    rule_config: ParlayRuleConfig | None = None,
    correlation_penalty: float = 0.0,
    derive_correlation_penalty: bool = False,
) -> ParlayEvaluation:
    if not 0.0 <= correlation_penalty <= 1.0:
        raise ValueError("correlation_penalty must be between 0 and 1")
    derived_correlation_penalty = (
        _derived_correlation_penalty(legs) if derive_correlation_penalty else 0.0
    )
    resolved_correlation_penalty = max(correlation_penalty, derived_correlation_penalty)
    atomic_bets = expand_atomic_bets(legs, unit_stake=unit_stake, multiplier=multiplier)
    total_stake = sum(atomic_bet.stake for atomic_bet in atomic_bets)
    expected_payout = sum(atomic_bet.expected_payout for atomic_bet in atomic_bets)
    expected_value = expected_payout - total_stake
    roi = expected_value / total_stake if total_stake > 0 else 0.0
    raw_hit_probability = hit_probability(legs)
    adjusted_hit_probability = raw_hit_probability * (1 - resolved_correlation_penalty)
    risk_score = placeholder_risk_score(
        hit_probability=adjusted_hit_probability,
        total_atomic_bets=len(atomic_bets),
        correlation_penalty=resolved_correlation_penalty,
    )
    risk_level = risk_level_from_score(risk_score)
    resolved_rule_config = rule_config or ParlayRuleConfig()
    rule_validation = evaluate_parlay_rules(
        legs,
        pass_type=pass_type,
        max_budget=max_budget,
        total_stake=total_stake,
        config=resolved_rule_config,
    )
    explanation_json = _explanation_payload(
        legs,
        pass_type=pass_type,
        unit_stake=unit_stake,
        multiplier=multiplier,
        max_budget=max_budget,
        total_stake=total_stake,
        hit_probability_value=raw_hit_probability,
        adjusted_hit_probability=adjusted_hit_probability,
        risk_score=risk_score,
        risk_level=risk_level,
        correlation_exposures=_correlation_exposure_payload(legs),
        min_data_quality_score_for_recommendation=(
            resolved_rule_config.min_data_quality_score_for_recommendation
        ),
        rule_reasons=rule_validation.reasons,
    )
    return ParlayEvaluation(
        pass_type=pass_type,
        is_multiple=is_multiple_parlay(legs),
        unit_stake=unit_stake,
        multiplier=multiplier,
        total_atomic_bets=len(atomic_bets),
        total_stake=total_stake,
        hit_probability=adjusted_hit_probability,
        expected_payout=expected_payout,
        expected_value=expected_value,
        roi=roi,
        risk_score=risk_score,
        risk_level=risk_level,
        correlation_penalty=resolved_correlation_penalty,
        rule_valid=rule_validation.valid,
        explanation_json=explanation_json,
        atomic_bets=atomic_bets,
    )
