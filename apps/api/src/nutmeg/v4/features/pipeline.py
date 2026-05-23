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
from nutmeg.v4.features.lineup_features import (
    LINEUP_FEATURE_COLUMNS,
    LINEUP_FEATURE_COLUMNS_RECENT_INJURY,
    build_lineup_features,
)
from nutmeg.v4.features.market import build_market_features
from nutmeg.v4.features.market_dynamics import (
    MARKET_DYNAMICS_FEATURE_COLUMNS,
    build_market_dynamics_features,
)
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
    # V5 W5 — DISABLED after ablation: market-dynamics drift features
    # (prob_drift_*, overround_compression, steam_flag, etc.) failed to
    # produce stable multi-season log-loss improvement. The build function
    # is still wired into the pipeline so the columns exist on the frame
    # for diagnostics, but they're excluded from the GBM input. See
    # docs/v5_w5_ablation.md for the full numbers and reasoning.
    #
    # V6 W2 lineup features — gated. They're added to GBM_FEATURE_COLUMNS
    # below ONLY when the build_feature_frame caller passes a lineup_lookup.
    # Without lineup data (the common case for historical training rows
    # not covered by W5 ingest), the columns would be 99% placeholder + 0
    # for `lineup_available`, contributing essentially no signal and
    # potentially confusing the GBM.
]


# V6 W2 — all 9 lineup feature columns. Available on the dataframe for
# diagnostic visibility but NOT included in the validated production
# feature list (V6 W5+W6 ablation rejected 8 of 9).
LINEUP_GATED_COLUMNS = list(LINEUP_FEATURE_COLUMNS)

# V6 W6 — the validated subset (multi-cutoff multi-league −0.0020 mean
# log-loss). These ARE included in feature_columns_with_lineups when the
# caller provides a recent_injury_lookup to build_feature_frame.
LINEUP_VALIDATED_COLUMNS = list(LINEUP_FEATURE_COLUMNS_RECENT_INJURY)


def feature_columns_with_lineups() -> list[str]:
    """Return the feature column list including V6 W6 lineup-validated cols.

    Note: only the recent-injury columns (2 of the original 9) make it
    into the production GBM input. Others stay on the dataframe for
    diagnostics. See docs/v6_w6_lineup_validation.md for the ablation.
    """
    return list(GBM_FEATURE_COLUMNS) + LINEUP_VALIDATED_COLUMNS


def build_feature_frame(
    df: pd.DataFrame,
    *,
    clubelo_cache_dir: Path | str = Path("data/external/clubelo"),
    clubelo_history: pd.DataFrame | None = None,
    lineup_lookup: dict | None = None,
    injury_lookup: dict | None = None,
    recent_injury_lookup: dict | None = None,
) -> pd.DataFrame:
    """Build all features. df must contain the canonical MATCH_COLUMNS.

    ``clubelo_cache_dir`` is read once at the end. Pass ``clubelo_history``
    directly to skip disk I/O (used in tests).

    V6 W5: when ``lineup_lookup`` is provided, lineup features are computed
    and the columns get added to the frame. Rows whose fixture_key is not
    in the lookup fill with placeholder values + ``lineup_available=0``,
    so partial coverage (e.g. only some leagues have lineups ingested) is
    handled gracefully.

    V6 W6: when ``recent_injury_lookup`` is provided, the validated
    `lineup_*_recent_n_injuries` columns are populated. Rows without
    a lookup entry get 0 (no recent injuries data); the GBM should NOT
    be trained with these columns unless lineup data is available for
    most training rows (use `feature_columns_with_lineups()`).
    """
    out = build_market_features(df)
    out = build_market_dynamics_features(out)
    out = build_form_features(out)
    out = build_elo_features(out)
    out = build_xg_lite_features(out)
    out = build_clubelo_features(out, cache_dir=clubelo_cache_dir, history=clubelo_history)
    if lineup_lookup is not None:
        out = build_lineup_features(
            out,
            lineup_lookup=lineup_lookup,
            injury_lookup=injury_lookup,
            recent_injury_lookup=recent_injury_lookup,
        )
    return out
