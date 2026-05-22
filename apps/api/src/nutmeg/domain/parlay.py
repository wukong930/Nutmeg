from __future__ import annotations

from pydantic import BaseModel, Field


class ParlayLegSelection(BaseModel):
    fixture_id: str
    market_type: str
    outcomes: list[str] = Field(min_length=1)
    probabilities: dict[str, float]
    odds: dict[str, float]
    line: float | None = None
    side: str | None = None
    model_version: str | None = None
    prediction_snapshot_id: int | None = Field(default=None, gt=0)
    correlation_key: str | None = None
    confidence: str | None = None
    data_quality_score: float | None = Field(default=None, ge=0.0, le=100.0)


class AtomicLeg(BaseModel):
    fixture_id: str
    market_type: str
    outcome: str
    probability: float = Field(ge=0.0, le=1.0)
    odds: float = Field(gt=1.0)
    line: float | None = None
    side: str | None = None
    model_version: str | None = None
    prediction_snapshot_id: int | None = Field(default=None, gt=0)
    correlation_key: str | None = None


class AtomicBet(BaseModel):
    legs: list[AtomicLeg]
    stake: float = Field(gt=0.0)
    probability: float = Field(ge=0.0, le=1.0)
    odds_product: float = Field(gt=1.0)
    expected_payout: float
    expected_value: float
    roi: float


class ParlayEvaluation(BaseModel):
    pass_type: str
    is_multiple: bool = False
    unit_stake: float = Field(gt=0.0)
    multiplier: int = Field(default=1, ge=1)
    total_atomic_bets: int = Field(ge=0)
    total_stake: float = Field(ge=0.0)
    hit_probability: float = Field(ge=0.0, le=1.0)
    expected_payout: float
    expected_value: float
    roi: float
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: str = "unknown"
    correlation_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    rule_valid: bool = True
    explanation_json: dict[str, object] = Field(default_factory=dict)
    atomic_bets: list[AtomicBet] = Field(default_factory=list)
