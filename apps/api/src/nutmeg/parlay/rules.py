from __future__ import annotations

from pydantic import BaseModel, Field

from nutmeg.domain.parlay import ParlayLegSelection


class ParlayRuleConfig(BaseModel):
    same_fixture_multiple_markets_allowed: bool = False
    min_data_quality_score_for_recommendation: float = Field(default=50.0, ge=0.0, le=100.0)
    supported_pass_types: set[str] = Field(
        default_factory=lambda: {
            "1x1",
            "2x1",
            "3x1",
            "4x1",
            "5x1",
            "6x1",
            "7x1",
            "8x1",
        }
    )
    max_legs_by_market: dict[str, int] = Field(
        default_factory=lambda: {
            "1x2": 8,
            "cn_handicap_1x2": 8,
            "european_handicap_1x2": 8,
            "asian_handicap": 8,
            "total_goals": 6,
            "correct_score": 4,
        }
    )


class ParlayRuleValidation(BaseModel):
    valid: bool
    reasons: list[str] = Field(default_factory=list)


def _parse_pass_legs(pass_type: str) -> int:
    try:
        leg_count_text, multiplier_text = pass_type.lower().split("x", maxsplit=1)
        leg_count = int(leg_count_text)
        multiplier = int(multiplier_text)
    except ValueError as exc:
        raise ValueError(f"unsupported pass_type: {pass_type}") from exc
    if leg_count < 1 or multiplier != 1:
        raise ValueError("Nutmeg supports Nx1 pass types with at least one leg")
    return leg_count


def evaluate_parlay_rules(
    legs: list[ParlayLegSelection],
    *,
    pass_type: str,
    total_stake: float,
    config: ParlayRuleConfig,
    max_budget: float | None = None,
) -> ParlayRuleValidation:
    reasons: list[str] = []
    if pass_type not in config.supported_pass_types:
        reasons.append("unsupported_pass_type")
        return ParlayRuleValidation(valid=False, reasons=reasons)
    try:
        expected_legs = _parse_pass_legs(pass_type)
    except ValueError:
        reasons.append("invalid_pass_type")
        return ParlayRuleValidation(valid=False, reasons=reasons)
    if len(legs) != expected_legs:
        reasons.append("leg_count_mismatch")
    if max_budget is not None and total_stake > max_budget:
        reasons.append("budget_exceeded")

    fixture_market_pairs = {(leg.fixture_id, leg.market_type) for leg in legs}
    if len(fixture_market_pairs) != len(legs):
        reasons.append("duplicate_fixture_market")

    if not config.same_fixture_multiple_markets_allowed:
        fixture_ids = [leg.fixture_id for leg in legs]
        if len(set(fixture_ids)) != len(fixture_ids):
            reasons.append("same_fixture_multiple_markets_not_allowed")

    market_limits = [config.max_legs_by_market.get(leg.market_type, 0) for leg in legs]
    if not market_limits:
        reasons.append("empty_legs")
    elif len(legs) > min(market_limits):
        reasons.append("market_leg_limit_exceeded")
    if any(limit == 0 for limit in market_limits):
        reasons.append("unsupported_market_type")
    if any(
        leg.data_quality_score is not None
        and leg.data_quality_score < config.min_data_quality_score_for_recommendation
        for leg in legs
    ):
        reasons.append("data_quality_too_low")
    return ParlayRuleValidation(valid=not reasons, reasons=reasons)


def validate_parlay_rules(
    legs: list[ParlayLegSelection],
    *,
    pass_type: str,
    total_stake: float,
    config: ParlayRuleConfig,
    max_budget: float | None = None,
) -> bool:
    return evaluate_parlay_rules(
        legs,
        pass_type=pass_type,
        total_stake=total_stake,
        config=config,
        max_budget=max_budget,
    ).valid
