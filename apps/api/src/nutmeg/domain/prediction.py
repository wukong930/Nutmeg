from __future__ import annotations

from datetime import datetime
from math import isclose
from typing import Self

from pydantic import BaseModel, Field, model_validator

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.domain.score_grid import ScoreProbabilityGrid

type MarketProbabilityValue = dict[str, float] | list[dict[str, float | int | str]]


class PredictionSnapshot(BaseModel):
    fixture_id: str
    prediction_time_utc: datetime
    model_version: str
    feature_version: str
    calibration_version: str
    feature_snapshot_id: int | None = Field(default=None, gt=0)
    feature_snapshot: FeatureSnapshot | None = None
    score_grid: ScoreProbabilityGrid
    market_probabilities: dict[str, MarketProbabilityValue]
    p_home: float = Field(ge=0.0, le=1.0)
    p_draw: float = Field(ge=0.0, le=1.0)
    p_away: float = Field(ge=0.0, le=1.0)
    uncertainty: str = "medium"
    data_quality_score: float = Field(default=75.0, ge=0.0, le=100.0)
    explanation_json: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_traceability_and_1x2(self) -> Self:
        if not self.score_grid.is_normalized(tolerance=1e-4):
            raise ValueError("prediction snapshot score grid must be normalized")
        if not isclose(self.p_home + self.p_draw + self.p_away, 1.0, abs_tol=1e-6):
            raise ValueError("prediction snapshot 1X2 probabilities must sum to 1")
        market_1x2 = self.market_probabilities.get("1x2")
        if market_1x2 is None or not isinstance(market_1x2, dict):
            raise ValueError("prediction snapshot must include 1x2 market probabilities")
        expected_keys = {"home_win", "draw", "away_win"}
        if set(market_1x2) != expected_keys:
            raise ValueError("1x2 market probabilities must include home_win, draw, away_win")
        if not all(isinstance(probability, float | int) for probability in market_1x2.values()):
            raise ValueError("1x2 market probabilities must be numeric")
        return self
