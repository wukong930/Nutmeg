"""Compose all feature builders into one DataFrame.

Standard usage:
    raw = load_all_matches(...)
    feats = build_feature_frame(raw)
    # feats has all original columns + market_* + elo_* + form_* features

Order is critical: build_form_features needs the original df (it walks
through matches and updates state); build_elo_features same. Market features
are pure column transforms, so order doesn't matter.
"""
from __future__ import annotations

import pandas as pd

from nutmeg.v4.features.elo import build_elo_features
from nutmeg.v4.features.form import build_form_features
from nutmeg.v4.features.market import build_market_features


# Canonical feature columns the GBM will use (must exist after pipeline runs).
GBM_FEATURE_COLUMNS = [
    # Market signals (the biggest lever)
    "market_p_home", "market_p_draw", "market_p_away",
    "market_logit_home", "market_logit_away",
    "market_overround",
    "market_total_over_2_5",
    "market_handicap_line",
    # Elo
    "elo_home", "elo_away", "elo_diff", "elo_p_home",
    # Form
    "form_home_goals_for_n", "form_home_goals_against_n",
    "form_home_shots_n", "form_home_shots_on_target_n",
    "form_away_goals_for_n", "form_away_goals_against_n",
    "form_away_shots_n", "form_away_shots_on_target_n",
    "form_home_goal_diff_n", "form_away_goal_diff_n",
    "form_home_rest_days", "form_away_rest_days",
]


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Build all features. df must contain the canonical MATCH_COLUMNS."""
    out = build_market_features(df)
    out = build_form_features(out)
    out = build_elo_features(out)
    return out
