"""Per-match candidate selections.

A "selection" is a single (match, market, outcome) bet:
  - market_type: "1x2" or "handicap_1x2"
  - outcome:     "H" / "D" / "A"
  - probability: model-estimated P(this outcome wins)
  - odds:        decimal odds offered by the lottery for this outcome
  - edge:        probability * odds - 1 (positive = +EV)

For a given match the system produces up to 6 selections (2 markets × 3 outcomes).
The user only outputs the BEST 1-2 selections per match in the final answer
(per V3.2 §1: keep the user-facing answer simple).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_handicap_1x2,
    score_grid,
)


MarketType = Literal["1x2", "handicap_1x2"]
Outcome = Literal["H", "D", "A"]


@dataclass(frozen=True)
class MatchInput:
    """Inputs needed to compute selections for one match.

    `lambda_home`, `lambda_away`: model-predicted goal expectations.
    `rho`: DC tau correction parameter.
    `handicap_home`: China integer handicap line for home team (e.g. -1 means home gives 1).
                     If None, the handicap_1x2 market is skipped.
    `odds_1x2`: dict {"H": 2.10, "D": 3.30, "A": 3.50}; bookmaker odds.
    `odds_handicap_1x2`: same shape but for the handicap market.
    """
    match_id: str
    lambda_home: float
    lambda_away: float
    rho: float = -0.10
    handicap_home: int | None = None
    odds_1x2: dict[str, float] | None = None
    odds_handicap_1x2: dict[str, float] | None = None


@dataclass(frozen=True)
class Selection:
    match_id: str
    market_type: MarketType
    outcome: Outcome
    probability: float
    odds: float

    @property
    def edge(self) -> float:
        return self.probability * self.odds - 1.0

    @property
    def implied(self) -> float:
        return 1.0 / self.odds

    def __repr__(self) -> str:  # pragma: no cover - debugging only
        return (f"Selection(match={self.match_id}, market={self.market_type}, "
                f"outcome={self.outcome}, p={self.probability:.3f}, odds={self.odds:.2f}, "
                f"edge={self.edge:+.3f})")


def build_selections_from_match(match: MatchInput) -> list[Selection]:
    """Compute up to 6 selections for one match (3 outcomes × up to 2 markets)."""
    grid = score_grid(match.lambda_home, match.lambda_away, rho=match.rho)
    out: list[Selection] = []

    if match.odds_1x2:
        ph, pd, pa = grid_to_1x2(grid)
        probs = {"H": ph, "D": pd, "A": pa}
        for outcome, prob in probs.items():
            o = match.odds_1x2.get(outcome)
            if o is None or o <= 1.0:
                continue
            out.append(Selection(
                match_id=match.match_id,
                market_type="1x2",
                outcome=outcome,
                probability=prob,
                odds=o,
            ))

    if match.handicap_home is not None and match.odds_handicap_1x2:
        ph, pd, pa = grid_to_handicap_1x2(grid, handicap_home=match.handicap_home)
        probs = {"H": ph, "D": pd, "A": pa}
        for outcome, prob in probs.items():
            o = match.odds_handicap_1x2.get(outcome)
            if o is None or o <= 1.0:
                continue
            out.append(Selection(
                match_id=match.match_id,
                market_type="handicap_1x2",
                outcome=outcome,
                probability=prob,
                odds=o,
            ))

    return out
