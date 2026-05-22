from __future__ import annotations

from math import isclose
from typing import Self

from pydantic import BaseModel, Field, model_validator


class OneXTwoProbabilities(BaseModel):
    home_win: float = Field(ge=0.0, le=1.0)
    draw: float = Field(ge=0.0, le=1.0)
    away_win: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_probability_sum(self) -> Self:
        if not isclose(self.home_win + self.draw + self.away_win, 1.0, abs_tol=1e-6):
            raise ValueError("1X2 probabilities must sum to 1")
        return self

    def as_market_map(self) -> dict[str, float]:
        return {
            "home_win": self.home_win,
            "draw": self.draw,
            "away_win": self.away_win,
        }


class CNHandicapProbabilities(BaseModel):
    handicap: int
    handicap_home_win: float = Field(ge=0.0, le=1.0)
    handicap_draw: float = Field(ge=0.0, le=1.0)
    handicap_away_win: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_probability_sum(self) -> Self:
        total = self.handicap_home_win + self.handicap_draw + self.handicap_away_win
        if not isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError("CN handicap 1X2 probabilities must sum to 1")
        return self


class AsianHandicapProbabilities(BaseModel):
    line: float
    side: str = "home"
    full_win_prob: float = Field(ge=0.0, le=1.0)
    half_win_prob: float = Field(ge=0.0, le=1.0)
    push_prob: float = Field(ge=0.0, le=1.0)
    half_loss_prob: float = Field(ge=0.0, le=1.0)
    full_loss_prob: float = Field(ge=0.0, le=1.0)
    expected_return_prob: float

    @model_validator(mode="after")
    def validate_probability_sum(self) -> Self:
        total = (
            self.full_win_prob
            + self.half_win_prob
            + self.push_prob
            + self.half_loss_prob
            + self.full_loss_prob
        )
        if not isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError("Asian handicap settlement probabilities must sum to 1")
        return self


class CorrectScoreProbability(BaseModel):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)
    option_key: str
