"""Cup training-row builder — V8 W2.

V7 W6 dropped cup fixtures + scores. V7 W8 dropped cup odds. V8 W1
shipped the global team-name canonicalizer. V8 W2 stitches all three
together: cup_history × cup_odds + canonicalize team names + pad
remaining V4 schema cols = V4-MATCH-shaped training rows.

The result is a DataFrame with the canonical `MATCH_COLUMNS` schema
that V4's `load_all_matches` returns, so `build_feature_frame` and
the rest of the training pipeline (Elo, form, xG-lite, etc.)
consume cup rows identically to league rows.

Pad strategy for the 23-of-37 V4 cols cup data doesn't carry:
- All score-not-final cols (ht_home_goals, ht_away_goals): NaN
- All shot stats (shots, sot, corners, yellow, red): NaN — form
  builders use `_team_form_avg` which is NaN-tolerant
- Alternate-book odds (ps_*, b365c_*, avgc_*): copy from psc_*
  (Pinnacle is sharp; using it as the proxy is the same fallback
  V7 W1's ingest_odds CSV applies)
- O/U handicap (psc_over25/under25): from cup_odds when present, else NaN
- Asian handicap (ahch, pcahh, pcaha): NaN

Team-name canonicalization runs at construction time:
- Both home and away resolved via `to_v4_canonical_global`
- Rows where either side fails to resolve (or resolves with fuzzy
  confidence < threshold) are dropped with a logged count
- The global pool is built from the league_df that's passed in (so
  the canonicalizer knows what V4 names exist)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from nutmeg.utils.team_canonical import (
    build_global_team_pool,
    to_v4_canonical_global,
)
from nutmeg.v4.data.cup_history import load_multi_season_cup_history
from nutmeg.v4.data.cup_odds import (
    load_multi_season_cup_odds,
    merge_cup_fixtures_and_odds,
)
from nutmeg.v4.data.schema import MATCH_COLUMNS


log = logging.getLogger(__name__)


def _result_1x2(hg: float | int | None, ag: float | int | None) -> str | None:
    if hg is None or ag is None:
        return None
    if hg > ag:
        return "H"
    if hg < ag:
        return "A"
    return "D"


def _team_pool_from_league_df(league_df: pd.DataFrame) -> list[str]:
    """Build the global team pool from a V4 training DataFrame.

    Used as the canonicalization target for cup team names.
    """
    league_pools: dict[str, set[str]] = {}
    for league, group in league_df.groupby("league"):
        teams: set[str] = set()
        teams.update(str(t) for t in group["home_team"].dropna().unique())
        teams.update(str(t) for t in group["away_team"].dropna().unique())
        league_pools[str(league)] = teams
    return build_global_team_pool(league_pools)


def _canonicalize_pair(
    home: str,
    away: str,
    global_pool: list[str],
    *,
    fuzzy_threshold: float = 0.86,
) -> tuple[str | None, str | None, str]:
    """Return (canonical_home, canonical_away, drop_reason).

    drop_reason is "" when both resolve, otherwise a short string for logging.
    """
    h_res = to_v4_canonical_global(home, global_pool, fuzzy_threshold=fuzzy_threshold)
    a_res = to_v4_canonical_global(away, global_pool, fuzzy_threshold=fuzzy_threshold)
    if h_res.canonical is None and a_res.canonical is None:
        return None, None, "both_unresolved"
    if h_res.canonical is None:
        return None, a_res.canonical, "home_unresolved"
    if a_res.canonical is None:
        return h_res.canonical, None, "away_unresolved"
    return h_res.canonical, a_res.canonical, ""


def build_cup_training_rows(
    cup_history_dir: Path,
    cup_odds_dir: Path,
    leagues: Iterable[str],
    seasons: Iterable[int],
    league_team_df: pd.DataFrame,
    *,
    fuzzy_threshold: float = 0.86,
) -> pd.DataFrame:
    """Top-level builder: cup parquets → V4-MATCH-shaped DataFrame.

    Pipeline:
      1. Load multi-season cup history (V7 W6) and cup odds (V7 W8)
      2. Inner-join on api_football_id (drops fixtures without odds)
      3. Build the canonical team pool from `league_team_df`
      4. Canonicalize home/away via `to_v4_canonical_global`; drop
         rows where either side can't resolve
      5. Pad V4 MATCH_COLUMNS not carried by cup data (shots/sot/
         corners/cards/ht_goals/alt-book odds/asian-handicap)
      6. Return DataFrame with exactly MATCH_COLUMNS schema

    Returns an empty DataFrame with the right schema when no
    cup data was found (callers can still concat without conditional).
    """
    fixtures = load_multi_season_cup_history(cup_history_dir, leagues, seasons)
    odds = load_multi_season_cup_odds(cup_odds_dir, leagues, seasons)
    log.info(
        "cup_training: loaded %d fixtures, %d odds rows",
        len(fixtures), len(odds),
    )
    if len(fixtures) == 0 or len(odds) == 0:
        return pd.DataFrame(columns=MATCH_COLUMNS)

    joined = merge_cup_fixtures_and_odds(fixtures, odds, how="inner")
    log.info(
        "cup_training: %d rows after fixtures × odds inner join",
        len(joined),
    )
    if len(joined) == 0:
        return pd.DataFrame(columns=MATCH_COLUMNS)

    pool = _team_pool_from_league_df(league_team_df)
    log.info("cup_training: global team pool size %d", len(pool))

    # Canonicalize + drop unresolved
    keep_indices: list[int] = []
    canonical_home: list[str] = []
    canonical_away: list[str] = []
    drop_counts: dict[str, int] = {}
    for idx, row in joined.iterrows():
        h, a, reason = _canonicalize_pair(
            str(row["home_team"]), str(row["away_team"]),
            pool, fuzzy_threshold=fuzzy_threshold,
        )
        if reason:
            drop_counts[reason] = drop_counts.get(reason, 0) + 1
            continue
        keep_indices.append(idx)
        canonical_home.append(h)
        canonical_away.append(a)

    if drop_counts:
        log.warning(
            "cup_training: dropped rows due to unresolved names: %s "
            "(extend CUP_TEAM_ALIASES via nutmeg-canonical-report-cup)",
            drop_counts,
        )

    if not keep_indices:
        return pd.DataFrame(columns=MATCH_COLUMNS)

    kept = joined.loc[keep_indices].copy()
    kept["home_team"] = canonical_home
    kept["away_team"] = canonical_away

    # Build the V4-schema DataFrame column-by-column so we have full
    # control over types + NaN padding
    n = len(kept)
    nan_arr = np.full(n, np.nan)
    out = pd.DataFrame({
        "league":       kept["league"].astype(str).to_numpy(),
        "season":       kept["season"].astype(int).to_numpy(),
        "date":         pd.to_datetime(kept["date"]).to_numpy(),
        "home_team":    kept["home_team"].astype(str).to_numpy(),
        "away_team":    kept["away_team"].astype(str).to_numpy(),
        "home_goals":   kept["home_goals"].astype(int).to_numpy(),
        "away_goals":   kept["away_goals"].astype(int).to_numpy(),
        "result_1x2":   [
            _result_1x2(hg, ag)
            for hg, ag in zip(kept["home_goals"], kept["away_goals"])
        ],
        # Half-time goals: not in API-Football /fixtures basic payload
        "ht_home_goals": nan_arr,
        "ht_away_goals": nan_arr,
        # Shot stats: not pulled in V7 W6 (would need /fixtures/statistics)
        "home_shots":              nan_arr,
        "away_shots":              nan_arr,
        "home_shots_on_target":    nan_arr,
        "away_shots_on_target":    nan_arr,
        "home_corners":            nan_arr,
        "away_corners":            nan_arr,
        "home_yellow":             nan_arr,
        "away_yellow":             nan_arr,
        "home_red":                nan_arr,
        "away_red":                nan_arr,
        # Primary closing odds (Pinnacle from cup_odds)
        "psc_home":    kept["psc_home"].astype(float).to_numpy(),
        "psc_draw":    kept["psc_draw"].astype(float).to_numpy(),
        "psc_away":    kept["psc_away"].astype(float).to_numpy(),
        # Alt-book odds: not in cup_odds; copy from psc_ as a sharp proxy
        # (same fallback V7 W1 ingest_odds CSV uses for the lottery cols)
        "ps_home":     kept["psc_home"].astype(float).to_numpy(),
        "ps_draw":     kept["psc_draw"].astype(float).to_numpy(),
        "ps_away":     kept["psc_away"].astype(float).to_numpy(),
        "b365c_home":  kept["psc_home"].astype(float).to_numpy(),
        "b365c_draw":  kept["psc_draw"].astype(float).to_numpy(),
        "b365c_away":  kept["psc_away"].astype(float).to_numpy(),
        "avgc_home":   kept["psc_home"].astype(float).to_numpy(),
        "avgc_draw":   kept["psc_draw"].astype(float).to_numpy(),
        "avgc_away":   kept["psc_away"].astype(float).to_numpy(),
        # O/U 2.5: from cup_odds when present, else NaN
        "psc_over25":  pd.to_numeric(kept["psc_over25"], errors="coerce").to_numpy(),
        "psc_under25": pd.to_numeric(kept["psc_under25"], errors="coerce").to_numpy(),
        # Asian handicap: not pulled
        "ahch":        nan_arr,
        "pcahh":       nan_arr,
        "pcaha":       nan_arr,
    })
    # Sanity: column order matches MATCH_COLUMNS exactly
    out = out[MATCH_COLUMNS]
    return out


def union_league_and_cup(
    league_df: pd.DataFrame,
    cup_df: pd.DataFrame,
) -> pd.DataFrame:
    """Concat league + cup DataFrames, re-sort by date.

    Time order matters for form-feature builders (they walk rows in
    time order and update per-team state). Concat + sort preserves
    that order across the union.

    Empty cup_df → returns league_df unchanged (cheap when caller
    doesn't pass --with-cup-data).
    """
    if cup_df is None or len(cup_df) == 0:
        return league_df
    # Both should already have MATCH_COLUMNS; concat is safe
    combined = pd.concat([league_df, cup_df], ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.sort_values(["date", "league", "home_team"]).reset_index(drop=True)
    return combined


__all__ = [
    "build_cup_training_rows",
    "union_league_and_cup",
]
