"""xG-lite features — prematch expected-goals proxies from shots/SoT history.

V5 W4 addition. We can't access real Opta/understat xG (sources blocked in W3),
so we approximate it from football-data.co.uk's per-match ``home_shots`` /
``away_shots`` and shots-on-target columns, which are already in V4's DataFrame.

The approximation formula:

    xg_proxy = SHOT_WEIGHT * (shots - SoT) + SOT_WEIGHT * SoT

The two weights are the empirical conversion rates a model learns from a large
football corpus: an off-target shot scores ~3-4% of the time, a shot on target
~25-30%. Concrete constants chosen to give a season-average xG_proxy of about
1.4–1.6 goals per match, matching the observed league averages.

These are NOT meant to compete with real xG — they discard shot location,
defender pressure, body part, and assist quality. But they are a cheap
defensive/offensive proxy the GBM can blend with the market + Elo features.

Features produced (per match, prematch only):
  xg_lite_home_for_n     — home team's rolling xG_proxy (offence)
  xg_lite_home_against_n — opponent xG_proxy when home team played (defence)
  xg_lite_away_for_n / xg_lite_away_against_n — same for away team
  xg_lite_diff_n         — (home_for − home_against) − (away_for − away_against)
  xg_lite_home_minus_goals_diff_n  — xg_proxy minus actual goals; positive =
      team has been unlucky (regression-to-mean signal)
  xg_lite_away_minus_goals_diff_n
  shots_to_sot_ratio_home_n / shots_to_sot_ratio_away_n  — shot quality (higher =
      lower conversion of attempts into on-target)
  xg_lite_available — 1 if all upstream form_*_shots columns are present, else 0
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# Empirical shot → goal conversion rates (off-target / on-target).
# Calibrated so league-average xG_proxy ≈ 1.4 goals / team / match.
NON_SOT_WEIGHT = 0.04
SOT_WEIGHT = 0.30
# Placeholder values used when shots data is missing (typical for J1 + the
# first 6 matches of any team's history before the rolling deque fills).
# The GBM also gets the ``xg_lite_available`` flag and can discount these.
XG_PLACEHOLDER = 1.4  # ~league-average goals per team per match
SOT_RATIO_PLACEHOLDER = 3.0  # ~league-average shots-to-SoT ratio


XG_LITE_FEATURE_COLUMNS = [
    "xg_lite_home_for_n",
    "xg_lite_home_against_n",
    "xg_lite_away_for_n",
    "xg_lite_away_against_n",
    "xg_lite_diff_n",
    "xg_lite_home_minus_goals_diff_n",
    "xg_lite_away_minus_goals_diff_n",
    "shots_to_sot_ratio_home_n",
    "shots_to_sot_ratio_away_n",
    "xg_lite_available",
]


def _xg_proxy(shots: pd.Series, sot: pd.Series) -> pd.Series:
    """xG proxy from shots and shots-on-target. NaN propagates."""
    return NON_SOT_WEIGHT * (shots - sot) + SOT_WEIGHT * sot


def _sot_ratio(shots: pd.Series, sot: pd.Series) -> pd.Series:
    """Shots-to-SoT ratio. >=1; lower (closer to 1) = more accurate. NaN if shots == 0."""
    s = shots.where(shots > 0)
    return s / sot.where(sot > 0)


def build_xg_lite_features(df: pd.DataFrame) -> pd.DataFrame:
    """Augment df with xG-lite features. Requires form_*_shots* columns first.

    Assumes ``build_form_features`` has already run (provides form_home_shots_n,
    form_home_shots_on_target_n, form_home_shots_against_n, form_home_sot_against_n
    and the same four for away). Missing form_* columns trigger a clear KeyError.
    """
    required = [
        "form_home_shots_n", "form_home_shots_on_target_n",
        "form_home_shots_against_n", "form_home_sot_against_n",
        "form_away_shots_n", "form_away_shots_on_target_n",
        "form_away_shots_against_n", "form_away_sot_against_n",
        "form_home_goals_for_n", "form_away_goals_for_n",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(
            f"build_xg_lite_features requires form_* columns first; missing: {missing}"
        )

    out = df.copy()

    # Flag whether xG-lite is computable for THIS row (no NaN in inputs)
    # — compute BEFORE we fill so the flag reflects reality.
    inputs_complete = (
        out["form_home_shots_n"].notna()
        & out["form_home_shots_on_target_n"].notna()
        & out["form_home_shots_against_n"].notna()
        & out["form_home_sot_against_n"].notna()
        & out["form_away_shots_n"].notna()
        & out["form_away_shots_on_target_n"].notna()
        & out["form_away_shots_against_n"].notna()
        & out["form_away_sot_against_n"].notna()
    )

    home_for = _xg_proxy(out["form_home_shots_n"], out["form_home_shots_on_target_n"])
    home_against = _xg_proxy(out["form_home_shots_against_n"], out["form_home_sot_against_n"])
    away_for = _xg_proxy(out["form_away_shots_n"], out["form_away_shots_on_target_n"])
    away_against = _xg_proxy(out["form_away_shots_against_n"], out["form_away_sot_against_n"])

    # Fill NaN with league-average placeholder. The xg_lite_available flag
    # tells the GBM whether to trust these or fall back to other features.
    home_for = home_for.fillna(XG_PLACEHOLDER)
    home_against = home_against.fillna(XG_PLACEHOLDER)
    away_for = away_for.fillna(XG_PLACEHOLDER)
    away_against = away_against.fillna(XG_PLACEHOLDER)

    out["xg_lite_home_for_n"] = home_for
    out["xg_lite_home_against_n"] = home_against
    out["xg_lite_away_for_n"] = away_for
    out["xg_lite_away_against_n"] = away_against
    out["xg_lite_diff_n"] = (home_for - home_against) - (away_for - away_against)

    # Regression-to-mean signal: positive = team has been getting goals below its xG (unlucky)
    out["xg_lite_home_minus_goals_diff_n"] = (
        home_for - out["form_home_goals_for_n"].fillna(XG_PLACEHOLDER)
    )
    out["xg_lite_away_minus_goals_diff_n"] = (
        away_for - out["form_away_goals_for_n"].fillna(XG_PLACEHOLDER)
    )

    # Shot quality (>=1; closer to 1 = sharper)
    out["shots_to_sot_ratio_home_n"] = _sot_ratio(
        out["form_home_shots_n"], out["form_home_shots_on_target_n"]
    ).fillna(SOT_RATIO_PLACEHOLDER)
    out["shots_to_sot_ratio_away_n"] = _sot_ratio(
        out["form_away_shots_n"], out["form_away_shots_on_target_n"]
    ).fillna(SOT_RATIO_PLACEHOLDER)

    out["xg_lite_available"] = inputs_complete.astype(int)

    return out
