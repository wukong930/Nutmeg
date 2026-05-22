from __future__ import annotations

from collections.abc import Iterator
from math import isclose
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


class ScoreProbability(BaseModel):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)


class ScoreGridTailMetrics(BaseModel):
    truncated_tail_mass: float = Field(ge=0.0, le=1.0)
    home_win_by_3plus: float = Field(ge=0.0, le=1.0)
    away_win_by_3plus: float = Field(ge=0.0, le=1.0)
    any_team_4plus_goals: float = Field(ge=0.0, le=1.0)
    total_goals_5plus: float = Field(ge=0.0, le=1.0)
    blowout_tail_risk: str


class ScoreProbabilityGrid(BaseModel):
    fixture_id: str | None = None
    max_goals: int = Field(default=8, ge=0, le=20)
    grid: list[list[float]]
    tail_mass: float = Field(default=0.0, ge=0.0, le=1.0)
    lambda_home: float | None = Field(default=None, ge=0.0)
    lambda_away: float | None = Field(default=None, ge=0.0)
    model_version: str | None = None
    calibration_version: str | None = None

    @field_validator("grid")
    @classmethod
    def validate_grid_values(cls, grid: list[list[float]]) -> list[list[float]]:
        if not grid:
            raise ValueError("score probability grid must not be empty")
        expected_width = len(grid[0])
        if expected_width == 0:
            raise ValueError("score probability grid rows must not be empty")
        for row in grid:
            if len(row) != expected_width:
                raise ValueError("score probability grid must be rectangular")
            if any(value < 0 for value in row):
                raise ValueError("score probability grid probabilities must be non-negative")
        return grid

    @model_validator(mode="after")
    def validate_shape_and_mass(self) -> Self:
        expected_size = self.max_goals + 1
        if len(self.grid) != expected_size:
            raise ValueError("score probability grid height must be max_goals + 1")
        if any(len(row) != expected_size for row in self.grid):
            raise ValueError("score probability grid width must be max_goals + 1")
        total_with_tail = self.total_probability() + self.tail_mass
        if total_with_tail <= 0:
            raise ValueError("score probability grid probability mass must be positive")
        return self

    def total_probability(self) -> float:
        return sum(sum(row) for row in self.grid)

    def total_probability_with_tail(self) -> float:
        return self.total_probability() + self.tail_mass

    def is_normalized(self, tolerance: float = 1e-6) -> bool:
        return isclose(self.total_probability(), 1.0, abs_tol=tolerance)

    def probability_for(self, home_goals: int, away_goals: int) -> float:
        if home_goals < 0 or away_goals < 0:
            raise ValueError("goals must be non-negative")
        if home_goals > self.max_goals or away_goals > self.max_goals:
            return 0.0
        return self.grid[home_goals][away_goals]

    def iter_scores(self) -> Iterator[ScoreProbability]:
        for home_goals, row in enumerate(self.grid):
            for away_goals, probability in enumerate(row):
                yield ScoreProbability(
                    home_goals=home_goals,
                    away_goals=away_goals,
                    probability=probability,
                )

    def normalized(self) -> ScoreProbabilityGrid:
        total = self.total_probability()
        if total <= 0:
            raise ValueError("cannot normalize an empty probability grid")
        normalized_grid = [[value / total for value in row] for row in self.grid]
        return self.model_copy(update={"grid": normalized_grid, "tail_mass": 0.0})
