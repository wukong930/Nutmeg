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

import numpy as np

from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_handicap_1x2,
    score_grid,
)
from nutmeg.v4.observation.auto_calibration import apply_correction_to_probs


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
    `handicap_probs`: optional {"H","D","A"} OVERRIDE for the 让球 probabilities.
        When supplied, build_selections_from_match uses these verbatim instead of
        the model grid (and applies NO temperature correction — they are already
        a de-vig probability, not a model output). This is how the API feeds the
        MARKET-REVERSE 让球 P (de-vig Pinnacle 1X2 + O/U) so the single-leg
        recommendation matches the dashboard display + parlay record (V12 W8 —
        validated better than the model grid on cover-Brier). None → model grid.
    """
    match_id: str
    lambda_home: float
    lambda_away: float
    rho: float = -0.10
    handicap_home: int | None = None
    odds_1x2: dict[str, float] | None = None
    odds_handicap_1x2: dict[str, float] | None = None
    handicap_probs: dict[str, float] | None = None


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


def build_selections_from_match(
    match: MatchInput,
    *,
    correction: dict | None = None,
) -> list[Selection]:
    """Compute up to 6 selections for one match (3 outcomes × up to 2 markets).

    V10 W2 Day 3 — optional ``correction`` (dict from
    ``nutmeg.v4.observation.auto_calibration.load_artifact_correction``).
    When supplied and ``T != 1.0``, post-hoc temperature scaling is applied
    to both the 1X2 and the handicap_1x2 probability tuples before
    building selections. Downstream Kelly / EV computations therefore see
    the calibrated probabilities. ``correction=None`` is the no-op
    passthrough — backward compatible with all pre-Day-3 callers.
    """
    grid = score_grid(match.lambda_home, match.lambda_away, rho=match.rho)
    out: list[Selection] = []

    if match.odds_1x2:
        ph, pd, pa = tuple(
            apply_correction_to_probs(np.array(grid_to_1x2(grid)), correction)
        )
        probs = {"H": ph, "D": pd, "A": pa}
        for outcome, prob in probs.items():
            o = match.odds_1x2.get(outcome)
            if o is None or o <= 1.0:
                continue
            out.append(Selection(
                match_id=match.match_id,
                market_type="1x2",
                outcome=outcome,
                probability=float(prob),
                odds=o,
            ))

    if match.handicap_home is not None and match.odds_handicap_1x2:
        if match.handicap_probs is not None:
            # F1 — market-reverse 让球 P (de-vig Pinnacle 1X2 + O/U), the SAME
            # source the dashboard displays + the parlay path records. It is
            # already a probability, so NO temperature correction is applied.
            ph = float(match.handicap_probs.get("H", 0.0))
            pd = float(match.handicap_probs.get("D", 0.0))
            pa = float(match.handicap_probs.get("A", 0.0))
        else:
            ph, pd, pa = tuple(
                apply_correction_to_probs(
                    np.array(grid_to_handicap_1x2(grid, handicap_home=match.handicap_home)),
                    correction,
                )
            )
        probs = {"H": ph, "D": pd, "A": pa}
        for outcome, prob in probs.items():
            o = match.odds_handicap_1x2.get(outcome)
            if o is None or o <= 1.0:
                continue
            out.append(Selection(
                match_id=match.match_id,
                market_type="handicap_1x2",
                outcome=outcome,
                probability=float(prob),
                odds=o,
            ))

    return out
