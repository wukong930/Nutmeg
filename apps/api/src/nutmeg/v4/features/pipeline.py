"""Compose all feature builders into one DataFrame.

Standard usage::

    raw = load_all_matches(...)
    feats = build_feature_frame(raw)
    # feats has all original columns + market_*, elo_*, form_*, xg_lite_*,
    # clubelo_* features

Order is critical: ``build_form_features`` walks rows in time order and
updates per-team state; ``build_elo_features`` does the same with its own
state. Market features are pure column transforms. xG-lite must run AFTER
form (it derives from form_*_shots*); clubelo must run BEFORE the GBM but
its order vs other builders doesn't matter (only depends on home_team/away_team/date
which are in the raw frame).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nutmeg.v4.features.clubelo_features import CLUBELO_FEATURE_COLUMNS, build_clubelo_features
from nutmeg.v4.features.elo import build_elo_features
from nutmeg.v4.features.form import build_form_features
from nutmeg.v4.features.market import build_market_features
from nutmeg.v4.features.xg_lite import XG_LITE_FEATURE_COLUMNS, build_xg_lite_features


# Canonical feature columns the GBM will use (must exist after pipeline runs).
GBM_FEATURE_COLUMNS = [
    # Market signals (the biggest lever)
    "market_p_home", "market_p_draw", "market_p_away",
    "market_logit_home", "market_logit_away",
    "market_overround",
    "market_total_over_2_5",
    "market_handicap_line",
    # Elo (per-league internal)
    "elo_home", "elo_away", "elo_diff", "elo_p_home",
    # Form
    "form_home_goals_for_n", "form_home_goals_against_n",
    "form_home_shots_n", "form_home_shots_on_target_n",
    "form_away_goals_for_n", "form_away_goals_against_n",
    "form_away_shots_n", "form_away_shots_on_target_n",
    "form_home_goal_diff_n", "form_away_goal_diff_n",
    "form_home_rest_days", "form_away_rest_days",
    # V5 W4: xG-lite (10 cols) + clubelo (5 cols)
    *XG_LITE_FEATURE_COLUMNS,
    *CLUBELO_FEATURE_COLUMNS,
]


def build_feature_frame(
    df: pd.DataFrame,
    *,
    clubelo_cache_dir: Path | str = Path("data/external/clubelo"),
    clubelo_history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build all features. df must contain the canonical MATCH_COLUMNS.

    ``clubelo_cache_dir`` is read once at the end. Pass ``clubelo_history``
    directly to skip disk I/O (used in tests).
    """
    out = build_market_features(df)
    out = build_form_features(out)
    out = build_elo_features(out)
    out = build_xg_lite_features(out)
    out = build_clubelo_features(out, cache_dir=clubelo_cache_dir, history=clubelo_history)
    return out
