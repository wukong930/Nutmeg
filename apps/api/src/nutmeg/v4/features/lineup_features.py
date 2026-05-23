"""Lineup-derived features — V6 W2.

These features answer: "what does the model know about today's starting XI
that it didn't know from historical Elo/form alone?" Pinnacle's remaining
edge over V5 CatBoost is largely day-of-info (lineups, injuries) — these
features narrow that gap.

Inputs: per-fixture API-Football payload from
``nutmeg.v4.data.sources.api_football.fetch_lineups(fixture_id)`` (a list
of 2 dicts, one per team, each with `startXI`, `substitutes`, `formation`,
`coach`).

We expect the caller to have:
1. Resolved the API-Football team_id from our canonical team name (see
   `nutmeg.utils.team_canonical` — V6 W2 will add an api_football alias dict)
2. Fetched the lineup payload (cached)
3. Optionally fetched per-team injuries

Features produced per match:
  lineup_home_xi_present_flag       1 if API-Football has published the XI
                                    by feature-build time, else 0
  lineup_away_xi_present_flag       same for away team
  lineup_home_formation_compactness Heuristic for defensive setup:
                                    0 = high block, 1 = mid, 2 = low block
                                    derived from formation string
                                    ('4-3-3' = 1, '5-4-1' = 2, '3-4-3' = 0)
  lineup_away_formation_compactness same for away
  lineup_home_n_injuries            Count of injured players for the home
                                    team's current squad (per /injuries
                                    payload at fixture time)
  lineup_away_n_injuries            same for away
  lineup_home_xi_minutes_share      [0,1] — what fraction of this season's
                                    starts at this club's XI are by the
                                    players actually starting today?
                                    (proxy for "are key starters present?";
                                    requires per-player season minutes
                                    data — V6 W3 task; for now defaults to
                                    1.0 when XI is present, 0.5 when not)
  lineup_away_xi_minutes_share      same for away
  lineup_available                  1 if both XIs are present (and we
                                    consider the row "fully lineup-aware"),
                                    else 0 — GBM uses this as a gating flag

All features default to placeholder values when the lineup payload is
absent (most rows in the historical training set won't have lineups
because we only started ingesting in V6 W1). The xg_lite + clubelo W4
pattern: placeholder + flag, never NaN.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# Formation → defensive compactness heuristic. Higher = more defenders /
# more compact block. Used by the GBM as a single numeric feature rather
# than 1-hot encoding 20+ formations.
FORMATION_COMPACTNESS: dict[str, float] = {
    # 3-back attacking
    "3-4-3": 0.0, "3-5-2": 0.5, "3-4-2-1": 0.2,
    # 4-back balanced
    "4-3-3": 1.0, "4-2-3-1": 1.0, "4-4-2": 1.0,
    "4-1-4-1": 1.2, "4-4-1-1": 1.1, "4-3-2-1": 1.0,
    "4-2-4": 0.8, "4-3-1-2": 0.9,
    # 5-back compact
    "5-3-2": 2.0, "5-4-1": 2.0, "5-2-3": 1.5, "5-2-1-2": 1.8,
}
DEFAULT_COMPACTNESS = 1.0  # 4-3-3-ish baseline when formation unknown


# Defaults for placeholder values when lineup data not available
DEFAULT_XI_MINUTES_SHARE_WITH_LINEUP = 1.0
DEFAULT_XI_MINUTES_SHARE_NO_LINEUP = 0.5
DEFAULT_N_INJURIES = 0


LINEUP_FEATURE_COLUMNS = [
    "lineup_home_xi_present_flag",
    "lineup_away_xi_present_flag",
    "lineup_home_formation_compactness",
    "lineup_away_formation_compactness",
    "lineup_home_n_injuries",
    "lineup_away_n_injuries",
    "lineup_home_xi_minutes_share",
    "lineup_away_xi_minutes_share",
    "lineup_available",
]


# V6 W5 ablation determined that of the 9 lineup features, only
# `lineup_home_recent_n_injuries` and `lineup_away_recent_n_injuries` —
# the leak-free 30-day unique-injured count — actually improve log-loss.
# Formation compactness and season-cumulative injury count regress or
# leak. These two recent-injury columns are added separately so the
# pipeline can opt in to JUST the validated subset.
LINEUP_FEATURE_COLUMNS_RECENT_INJURY = [
    "lineup_home_recent_n_injuries",
    "lineup_away_recent_n_injuries",
]


def _formation_compactness(formation: str | None) -> float:
    if not formation:
        return DEFAULT_COMPACTNESS
    # API-Football sometimes returns "4-3-3" or with extra spaces
    f = formation.replace(" ", "").strip()
    return FORMATION_COMPACTNESS.get(f, DEFAULT_COMPACTNESS)


def derive_lineup_features_single(
    home_lineup: dict[str, Any] | None,
    away_lineup: dict[str, Any] | None,
    *,
    home_injuries: list[dict[str, Any]] | None = None,
    away_injuries: list[dict[str, Any]] | None = None,
    home_minutes_share: float | None = None,
    away_minutes_share: float | None = None,
) -> dict[str, float]:
    """Compute the feature dict for a single fixture from API-Football payloads.

    ``home_lineup`` / ``away_lineup`` are individual lineup records (one
    per team), e.g. ``fetch_lineups(fixture_id)[0]`` / ``[1]``. Pass None
    when the lineup isn't published yet — features fall back to safe
    placeholders + flag bits.

    ``home_minutes_share`` / ``away_minutes_share`` are precomputed [0,1]
    values from a player-stats data source (V6 W3 task). When None, we use
    the default-with-lineup or default-without-lineup constant.
    """
    home_present = home_lineup is not None
    away_present = away_lineup is not None

    home_form = _formation_compactness(
        home_lineup.get("formation") if home_lineup else None
    )
    away_form = _formation_compactness(
        away_lineup.get("formation") if away_lineup else None
    )

    home_inj = len(home_injuries or [])
    away_inj = len(away_injuries or [])

    if home_minutes_share is None:
        home_minutes_share = (
            DEFAULT_XI_MINUTES_SHARE_WITH_LINEUP if home_present
            else DEFAULT_XI_MINUTES_SHARE_NO_LINEUP
        )
    if away_minutes_share is None:
        away_minutes_share = (
            DEFAULT_XI_MINUTES_SHARE_WITH_LINEUP if away_present
            else DEFAULT_XI_MINUTES_SHARE_NO_LINEUP
        )

    return {
        "lineup_home_xi_present_flag": float(home_present),
        "lineup_away_xi_present_flag": float(away_present),
        "lineup_home_formation_compactness": home_form,
        "lineup_away_formation_compactness": away_form,
        "lineup_home_n_injuries": float(home_inj),
        "lineup_away_n_injuries": float(away_inj),
        "lineup_home_xi_minutes_share": float(home_minutes_share),
        "lineup_away_xi_minutes_share": float(away_minutes_share),
        "lineup_available": float(home_present and away_present),
    }


def build_lineup_features(
    df: pd.DataFrame,
    lineup_lookup: dict[str, tuple[dict | None, dict | None]] | None = None,
    *,
    injury_lookup: dict[str, tuple[list | None, list | None]] | None = None,
    minutes_share_lookup: dict[str, tuple[float | None, float | None]] | None = None,
    recent_injury_lookup: dict[str, tuple[int, int]] | None = None,
) -> pd.DataFrame:
    """Augment df with lineup feature columns.

    ``lineup_lookup`` maps a fixture key (e.g. ``f"{league}_{date}_{home}_{away}"``)
    to (home_lineup, away_lineup) tuples. When a fixture key isn't in the
    lookup (the common case — most historical training rows have no lineup
    data), placeholder values are filled.

    Same shape for ``injury_lookup`` and ``minutes_share_lookup``.

    ``recent_injury_lookup`` is a V6 W5 addition mapping fixture_key →
    (home_count, away_count) of leak-free 30-day-unique-injured player
    counts. When provided, ``lineup_home_recent_n_injuries`` and
    ``lineup_away_recent_n_injuries`` columns are added.

    Lookup keys are *strings* so the caller decides on canonical format
    rather than us baking a contract.
    """
    out = df.copy()
    lineup_lookup = lineup_lookup or {}
    injury_lookup = injury_lookup or {}
    minutes_share_lookup = minutes_share_lookup or {}
    recent_injury_lookup = recent_injury_lookup or {}

    # Vector-friendly: build the 9 feature arrays then assign as columns
    n = len(out)
    cols: dict[str, np.ndarray] = {c: np.empty(n) for c in LINEUP_FEATURE_COLUMNS}
    recent_home = np.zeros(n, dtype=float)
    recent_away = np.zeros(n, dtype=float)

    for i, row in enumerate(out.itertuples(index=False)):
        key = _fixture_key(row)
        home_lineup, away_lineup = lineup_lookup.get(key, (None, None))
        home_inj, away_inj = injury_lookup.get(key, (None, None))
        home_ms, away_ms = minutes_share_lookup.get(key, (None, None))
        feats = derive_lineup_features_single(
            home_lineup, away_lineup,
            home_injuries=home_inj, away_injuries=away_inj,
            home_minutes_share=home_ms, away_minutes_share=away_ms,
        )
        for c in LINEUP_FEATURE_COLUMNS:
            cols[c][i] = feats[c]
        ri_h, ri_a = recent_injury_lookup.get(key, (0, 0))
        recent_home[i] = ri_h
        recent_away[i] = ri_a

    for c, arr in cols.items():
        out[c] = arr
    out["lineup_home_recent_n_injuries"] = recent_home
    out["lineup_away_recent_n_injuries"] = recent_away
    return out


def _fixture_key(row) -> str:
    """Canonical fixture key for lineup_lookup. Match what the caller produces."""
    # Format: <league>__<YYYY-MM-DD>__<home>__<away>
    # date may be Timestamp / datetime / str — coerce to YYYY-MM-DD string
    d = row.date
    if hasattr(d, "strftime"):
        d_str = d.strftime("%Y-%m-%d")
    else:
        d_str = str(d)[:10]
    return f"{row.league}__{d_str}__{row.home_team}__{row.away_team}"


__all__ = [
    "LINEUP_FEATURE_COLUMNS",
    "FORMATION_COMPACTNESS",
    "build_lineup_features",
    "derive_lineup_features_single",
]
