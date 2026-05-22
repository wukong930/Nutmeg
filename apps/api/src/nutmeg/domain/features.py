from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

type PrematchLineupType = Literal["expected", "confirmed", "projected", "unknown"]


class FeatureSnapshot(BaseModel):
    fixture_id: str
    feature_time_utc: datetime
    feature_version: str
    features_json: dict[str, object] = Field(default_factory=dict)
    source_snapshot_refs: dict[str, object] = Field(default_factory=dict)
    data_quality_score: float = Field(ge=0.0, le=100.0)


class PrematchLineupFeature(BaseModel):
    lineup_type: PrematchLineupType = "unknown"
    snapshot_time_utc: datetime | None = None
    expected_lineup_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    starting_xi_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    bench_dropoff_score: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str | None = None
    source_snapshot_ref: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PrematchAvailabilityFeature(BaseModel):
    snapshot_time_utc: datetime | None = None
    unavailable_key_player_count: int = Field(default=0, ge=0)
    doubtful_key_player_count: int = Field(default=0, ge=0)
    key_player_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    defender_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    goalkeeper_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    striker_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str | None = None
    source_snapshot_ref: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PrematchOddsMovementPoint(BaseModel):
    snapshot_time_utc: datetime
    market_type: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    decimal_odds: float | None = Field(default=None, gt=1.0)
    fair_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    bookmaker_count: int | None = Field(default=None, ge=0)
    source: str | None = None
    source_snapshot_ref: str | None = None


class PrematchOddsMovementFeature(BaseModel):
    market_type: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    points: list[PrematchOddsMovementPoint] = Field(default_factory=list)
    bookmaker_disagreement: float | None = Field(default=None, ge=0.0, le=1.0)
    exchange_liquidity: float | None = Field(default=None, ge=0.0)
    market_delay_signal: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class PrematchSemanticSignal(BaseModel):
    signal_name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_text_short: str = Field(min_length=1, max_length=280)
    extracted_at_utc: datetime
    metadata_json: dict[str, object] = Field(default_factory=dict)


class StructuredPrematchFeatureSet(BaseModel):
    lineup: PrematchLineupFeature | None = None
    availability: PrematchAvailabilityFeature | None = None
    odds_movements: list[PrematchOddsMovementFeature] = Field(default_factory=list)
    semantic_signals: list[PrematchSemanticSignal] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)
