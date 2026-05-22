"""Parlay optimizer skeleton."""

from nutmeg.parlay.expander import (
    evaluate_parlay,
    expand_atomic_bets,
    hit_probability,
    is_multiple_parlay,
)
from nutmeg.parlay.generator import (
    MarketPredictionParlayCandidate,
    MarketPredictionParlayGenerationOptions,
    MarketPredictionParlayGenerationResult,
    list_market_prediction_parlay_candidates,
    run_market_prediction_parlay_generation,
)
from nutmeg.parlay.repository import (
    ParlayRecommendationWriteInput,
    ParlaySettlementRun,
    PostgresParlayRecommendationRepository,
    StoredParlayRecommendation,
    parlay_recommendation_input_from_payload,
)
from nutmeg.parlay.rules import (
    ParlayRuleConfig,
    ParlayRuleValidation,
    evaluate_parlay_rules,
    validate_parlay_rules,
)
from nutmeg.parlay.settlement import (
    ParlayAtomicSettlement,
    ParlayLegSettlement,
    settle_parlay_atomic_bet,
)

__all__ = [
    "ParlayAtomicSettlement",
    "ParlayLegSettlement",
    "ParlayRecommendationWriteInput",
    "ParlayRuleConfig",
    "ParlayRuleValidation",
    "ParlaySettlementRun",
    "PostgresParlayRecommendationRepository",
    "StoredParlayRecommendation",
    "MarketPredictionParlayCandidate",
    "MarketPredictionParlayGenerationOptions",
    "MarketPredictionParlayGenerationResult",
    "evaluate_parlay",
    "evaluate_parlay_rules",
    "expand_atomic_bets",
    "hit_probability",
    "is_multiple_parlay",
    "list_market_prediction_parlay_candidates",
    "parlay_recommendation_input_from_payload",
    "run_market_prediction_parlay_generation",
    "settle_parlay_atomic_bet",
    "validate_parlay_rules",
]
