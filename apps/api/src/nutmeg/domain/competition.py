from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CompetitionType = Literal[
    "domestic_league",
    "domestic_cup",
    "continental_club",
    "national_team",
    "international_cup",
]
TeamType = Literal["club", "national_team"]
CoverageTier = Literal["A_full", "B_medium", "C_basic", "D_beta"]
ModelStatus = Literal["inactive", "beta", "production", "experimental"]


class ModelCompetitionConfig(BaseModel):
    base_model: str
    calibration_scope: str
    home_advantage_mode: str
    goal_distribution_mode: str
    cold_start_strategy: str
    cross_league_strength_required: bool = False
    two_leg_context_required: bool = False


class MarketAvailabilityConfig(BaseModel):
    enabled: list[str] = Field(default_factory=list)
    cn_lottery_available: bool = False


class QualityRequirements(BaseModel):
    min_historical_matches: int = 300
    min_odds_coverage: float = Field(default=0.60, ge=0.0, le=1.0)
    min_result_coverage: float = Field(default=0.99, ge=0.0, le=1.0)


class CompetitionConfig(BaseModel):
    competition_id: str
    name: str
    country: str | None = None
    region: str | None = None
    competition_type: CompetitionType
    team_type: TeamType
    season_calendar: str
    provider_primary: str
    provider_secondary: str | None = None
    coverage_tier: CoverageTier = "D_beta"
    model_status: ModelStatus = "inactive"
    model: ModelCompetitionConfig
    markets: MarketAvailabilityConfig
    quality_requirements: QualityRequirements = Field(default_factory=QualityRequirements)
