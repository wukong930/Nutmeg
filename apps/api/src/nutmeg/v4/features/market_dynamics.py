"""Market-dynamics features — opening-to-closing odds movement signals.

V5 W5 addition. football-data.co.uk records both Pinnacle opening (PSH/D/A)
and closing (PSCH/CD/CA) 1X2 odds. The difference between them encodes
information the market absorbed between opening and kickoff (injuries
revealed, lineups announced, sharps placing money, weather updates, etc.).

Even though V4 already uses the closing odds as a feature, the *direction*
and *magnitude* of the drift from opening → closing is a distinct signal:
a team whose price shortens (drift_home > 0) had positive news; whose price
drifts longer had negative news. Crucially this drift information is not
encoded in the closing price alone — the closing price is "what the market
believes now", but the drift is "what the market learned".

Inputs (must come from ``build_market_features`` running first):
  ps_home / ps_draw / ps_away    — Pinnacle opening 1X2 odds (raw decimal)
  market_p_home / draw / away    — closing devig probabilities
  market_overround               — closing book overround

Features produced (per match), slimmed in W5 after ablation:
  prob_drift_home/draw/away      — closing − opening devig prob
  overround_compression          — opening overround − closing overround
                                    (typically positive: book sharpens by close)
  market_dynamics_available      — 1 if opening odds present and valid, else 0
                                    (∼83% of our 27k matches have PSH/D/A;
                                    earlier seasons + Japan often miss them)

Notes on leakage / availability:
  - Opening odds are recorded BEFORE the match → no lookahead risk.
  - When opening odds are missing, all drift features are set to 0 (= "we don't
    know") and the available flag is 0 so the GBM can learn to discount.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# Slimmed feature set after W5 ablation. Discarded:
#   - market_p_open_*  : redundant with closing_p + drift (linear dependence)
#   - market_overround_open : redundant with compression + closing_overround
#   - dominant_drift_side : np.sign() is unstable near 0; the same info is in
#                           prob_drift_home/away signs already
#   - {home,away}_steam_flag : binary thresholds with arbitrary cutoff;
#                              multi-season eval showed they introduced noise
#                              on 22/23 + 23/24 with positive contribution only
#                              on 24/25. Net effect was worse than W4.
# Keeping only the continuous, monotone, well-defined signals.

MARKET_DYNAMICS_FEATURE_COLUMNS = [
    "prob_drift_home",
    "prob_drift_draw",
    "prob_drift_away",
]


def _devig_3way(home: pd.Series, draw: pd.Series, away: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Pure devig — same formula as features.market._safe_devig, but here we
    coerce object → numeric first since ps_* columns are object dtype.
    """
    h = pd.to_numeric(home, errors="coerce").replace(0, np.nan)
    d = pd.to_numeric(draw, errors="coerce").replace(0, np.nan)
    a = pd.to_numeric(away, errors="coerce").replace(0, np.nan)
    inv_h, inv_d, inv_a = 1.0 / h, 1.0 / d, 1.0 / a
    total = inv_h + inv_d + inv_a
    return inv_h / total, inv_d / total, inv_a / total, total - 1.0


def build_market_dynamics_features(df: pd.DataFrame) -> pd.DataFrame:
    """Augment df with market-dynamics features. Assumes ``build_market_features``
    has already run (we need ``market_p_*`` and ``market_overround`` closing
    columns to compare against).
    """
    for col in ("ps_home", "ps_draw", "ps_away", "market_p_home", "market_p_draw", "market_p_away", "market_overround"):
        if col not in df.columns:
            raise KeyError(
                f"build_market_dynamics_features requires {col!r} (run build_market_features first)"
            )
    out = df.copy()

    p_open_h, p_open_d, p_open_a, overround_open = _devig_3way(
        out["ps_home"], out["ps_draw"], out["ps_away"]
    )

    # available flag based on whether all three opening prices parsed to a positive number
    available = p_open_h.notna() & p_open_d.notna() & p_open_a.notna()

    # Drift = closing − opening. Positive home drift = market shortened home's price.
    drift_h = (out["market_p_home"] - p_open_h).fillna(0.0)
    drift_d = (out["market_p_draw"] - p_open_d).fillna(0.0)
    drift_a = (out["market_p_away"] - p_open_a).fillna(0.0)
    overround_open_filled = overround_open.fillna(out["market_overround"])

    out["prob_drift_home"] = drift_h
    out["prob_drift_draw"] = drift_d
    out["prob_drift_away"] = drift_a
    # Books usually sharpen between open and close → positive compression
    out["overround_compression"] = overround_open_filled - out["market_overround"]
    out["market_dynamics_available"] = available.astype(int)

    return out
