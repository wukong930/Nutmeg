"""Market-implied features from Pinnacle / Bet365 / average closing odds.

These features are derived from bookmaker prices that are available BEFORE
kickoff, so they don't cause leakage. They are the single biggest source
of "alpha" the V4 model has access to that the legacy heuristic DC didn't.

Output features (per match):
  market_p_home, market_p_draw, market_p_away   — devig Pinnacle closing
  market_logit_home, market_logit_away          — log(p / (1-p)), useful for GBM
  market_overround                              — sum of 1/odds before devig (book vig)
  market_total_2_5                              — Pinnacle O/U 2.5 over probability (devig vs under)
  market_handicap_line                          — AHCh (European Asian handicap, home side)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


EPS = 1e-9


def _safe_devig(home: pd.Series, draw: pd.Series, away: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Devig 1X2 odds; return (p_h, p_d, p_a, overround). NaN-safe row-wise."""
    inv_h = 1.0 / home
    inv_d = 1.0 / draw
    inv_a = 1.0 / away
    total = inv_h + inv_d + inv_a
    return inv_h / total, inv_d / total, inv_a / total, total


def _safe_devig_two_way(over: pd.Series, under: pd.Series) -> pd.Series:
    """Devig two-way (over/under) odds → P(over). Coerces non-numeric and zeros to NaN."""
    over_n = pd.to_numeric(over, errors="coerce").replace(0, np.nan)
    under_n = pd.to_numeric(under, errors="coerce").replace(0, np.nan)
    inv_o = 1.0 / over_n
    inv_u = 1.0 / under_n
    return inv_o / (inv_o + inv_u)


def build_market_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add market-derived feature columns to df (returns NEW frame, doesn't mutate).

    Required input columns: psc_home, psc_draw, psc_away,
                            psc_over25, psc_under25,
                            ahch
    """
    out = df.copy()
    p_h, p_d, p_a, total = _safe_devig(out["psc_home"], out["psc_draw"], out["psc_away"])
    out["market_p_home"] = p_h
    out["market_p_draw"] = p_d
    out["market_p_away"] = p_a
    out["market_overround"] = total - 1.0

    out["market_logit_home"] = np.log(p_h.clip(EPS, 1 - EPS) / (1 - p_h.clip(EPS, 1 - EPS)))
    out["market_logit_away"] = np.log(p_a.clip(EPS, 1 - EPS) / (1 - p_a.clip(EPS, 1 - EPS)))

    # Over 2.5 implied probability (when both columns present)
    out["market_total_over_2_5"] = _safe_devig_two_way(out["psc_over25"], out["psc_under25"])

    # The Asian handicap home line itself (negative = home gives goals)
    out["market_handicap_line"] = pd.to_numeric(out["ahch"], errors="coerce")

    return out
