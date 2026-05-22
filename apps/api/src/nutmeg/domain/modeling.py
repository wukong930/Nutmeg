from __future__ import annotations

from pydantic import BaseModel, Field


class PoissonBaselineInput(BaseModel):
    fixture_id: str
    home_attack_strength: float = Field(gt=0.0)
    away_attack_strength: float = Field(gt=0.0)
    home_defense_weakness: float = Field(gt=0.0)
    away_defense_weakness: float = Field(gt=0.0)
    league_avg_home_goals: float = Field(gt=0.0)
    league_avg_away_goals: float = Field(gt=0.0)
    home_advantage_multiplier: float = Field(default=1.0, gt=0.0)
    model_version: str = "poisson-m1.0.0"
    feature_version: str = "features-m1.0.0"
    calibration_version: str = "calibration-m1.0.0"
    metadata_json: dict[str, object] = Field(default_factory=dict)


class DixonColesInput(BaseModel):
    fixture_id: str
    mu: float = 0.0
    home_attack: float = 0.0
    away_attack: float = 0.0
    home_defense: float = 0.0
    away_defense: float = 0.0
    home_advantage: float = 0.0
    home_context_adjustment: float = 0.0
    away_context_adjustment: float = 0.0
    rho: float = Field(default=0.0, ge=-0.5, le=0.5)
    days_since_reference_match: float | None = Field(default=None, ge=0.0)
    time_decay_xi: float = Field(default=0.0, ge=0.0)
    model_version: str = "dc-v1.5.0"
    feature_version: str = "features-m1.2.0"
    calibration_version: str = "calibration-m1.0.0"
    metadata_json: dict[str, object] = Field(default_factory=dict)


class GoalLambdaEstimate(BaseModel):
    fixture_id: str
    lambda_home: float = Field(gt=0.0)
    lambda_away: float = Field(gt=0.0)
    model_family: str
    model_version: str
    feature_version: str
    calibration_version: str
    rho: float | None = None
    time_decay_weight: float | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)
