"""Cup competition historical odds → parquet store — V7 W8.

Companion to `nutmeg.v4.data.cup_history` (V7 W6, which holds fixture
+ score data). This module holds the Pinnacle (or other sharp book)
closing 1X2 + O/U-2.5 odds for the same fixtures, keyed by
API-Football `fixture_id`. Joining the two yields a training-frame-
compatible cup match row.

Workflow:

  V7 W6 parquets (data/external/cup_history/)   ←──┐
  cup fixtures + scores                            │ merge_cup_fixtures_and_odds()
  V7 W8 parquets (data/external/cup_odds/)      ←──┘
  Pinnacle 1X2 + O/U per fixture

  → DataFrame ready for V7 W7's build_feature_frame(cup_history_df=...)

V7 W8's CLI (`nutmeg-ingest-cup-odds`) reads the W6 parquets to know
which fixture IDs to query, calls `/odds` per fixture (cached), parses
via the shared `odds_parser` (W1 module), writes per-(league, season)
parquets here.

Schema (one row per fixture, keyed by api_football_id):

| Column          | Type   | Notes |
|-----------------|--------|---|
| api_football_id | int    | join key with cup_history parquets |
| league          | str    | V4 canonical cup code |
| season          | int    | season start year |
| bookmaker_id    | int    | which book this row came from (Pinnacle = 4) |
| psc_home        | float  | 1X2 H odds (None → no quote) |
| psc_draw        | float  | 1X2 D odds |
| psc_away        | float  | 1X2 A odds |
| psc_over25      | float  | O/U-2.5 over (optional; None when book doesn't carry) |
| psc_under25     | float  | O/U-2.5 under (optional) |
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from nutmeg.v4.data.odds_parser import (
    PINNACLE_BOOKMAKER_ID,
    extract_1x2_odds,
    extract_over_under_25,
)


CUP_ODDS_COLUMNS = [
    "api_football_id",
    "league",
    "season",
    "bookmaker_id",
    "psc_home",
    "psc_draw",
    "psc_away",
    "psc_over25",
    "psc_under25",
]


def normalize_odds_envelope(
    odds_envelope: dict,
    fixture_id: int,
    league_code: str,
    season: int,
    *,
    bookmaker_id: int = PINNACLE_BOOKMAKER_ID,
) -> Optional[dict]:
    """Parse one API-Football `/odds` envelope into our cup-odds row dict.

    Returns None when the requested bookmaker doesn't quote 1X2 for
    this fixture (common for lower-tier qualifying matches). When 1X2
    is present but O/U-2.5 isn't, the row is kept and O/U columns
    emit None.
    """
    if odds_envelope is None:
        return None
    odds_1x2 = extract_1x2_odds(odds_envelope, bookmaker_id)
    if odds_1x2 is None:
        return None
    ou = extract_over_under_25(odds_envelope, bookmaker_id)
    row: dict = {
        "api_football_id": int(fixture_id),
        "league": league_code,
        "season": int(season),
        "bookmaker_id": int(bookmaker_id),
        "psc_home": odds_1x2["H"],
        "psc_draw": odds_1x2["D"],
        "psc_away": odds_1x2["A"],
        "psc_over25": ou[0] if ou is not None else None,
        "psc_under25": ou[1] if ou is not None else None,
    }
    return row


def cup_odds_parquet_path(
    out_dir: Path,
    league_code: str,
    season: int,
) -> Path:
    """Canonical filename — mirrors cup_history naming for symmetry."""
    return out_dir / f"{league_code}_{season}.parquet"


def write_cup_odds_parquet(
    rows: list[dict],
    out_path: Path,
) -> Path:
    """Write rows with the canonical CUP_ODDS_COLUMNS schema.

    Empty rows still emits a valid empty-schema parquet so downstream
    loaders don't special-case missing seasons.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=CUP_ODDS_COLUMNS)
    df.to_parquet(out_path, index=False)
    return out_path


def load_cup_odds_parquet(path: Path) -> pd.DataFrame:
    """Read one (league, season) parquet back. Empty when file missing."""
    if not path.exists():
        return pd.DataFrame(columns=CUP_ODDS_COLUMNS)
    return pd.read_parquet(path)


def load_multi_season_cup_odds(
    out_dir: Path,
    leagues: Iterable[str],
    seasons: Iterable[int],
) -> pd.DataFrame:
    """Concat every (league, season) parquet found in out_dir.

    Missing files are silently skipped — symmetric with V7 W6's
    `load_multi_season_cup_history`.
    """
    parts: list[pd.DataFrame] = []
    for league in leagues:
        for season in seasons:
            path = cup_odds_parquet_path(out_dir, league, season)
            if not path.exists():
                continue
            df = load_cup_odds_parquet(path)
            if len(df) > 0:
                parts.append(df)
    if not parts:
        return pd.DataFrame(columns=CUP_ODDS_COLUMNS)
    return pd.concat(parts, ignore_index=True)


def merge_cup_fixtures_and_odds(
    fixtures_df: pd.DataFrame,
    odds_df: pd.DataFrame,
    *,
    how: str = "inner",
) -> pd.DataFrame:
    """Inner-join cup_history fixtures with cup_odds on `api_football_id`.

    Default `how="inner"` keeps only fixtures with usable odds (the
    common case when feeding into the training pipeline). Pass
    `how="left"` to keep all fixtures and see None odds for those the
    sharp book didn't quote (diagnostic only).

    Returns a DataFrame combining cup_history's fields (date, league,
    home/away teams, goals, round_label) with cup_odds's market columns
    (psc_home/draw/away + optional over25/under25). The result is shape-
    compatible with the V4 training-frame columns (still needs Elo /
    form / etc. — that's W9 territory).
    """
    if len(fixtures_df) == 0 or len(odds_df) == 0:
        return pd.DataFrame()

    # Only keep columns we actually need from odds_df to avoid duplicating
    # league/season (those already live on fixtures_df via cup_history).
    odds_subset = odds_df[
        ["api_football_id", "bookmaker_id",
         "psc_home", "psc_draw", "psc_away",
         "psc_over25", "psc_under25"]
    ].copy()
    return fixtures_df.merge(odds_subset, on="api_football_id", how=how)


__all__ = [
    "CUP_ODDS_COLUMNS",
    "normalize_odds_envelope",
    "cup_odds_parquet_path",
    "write_cup_odds_parquet",
    "load_cup_odds_parquet",
    "load_multi_season_cup_odds",
    "merge_cup_fixtures_and_odds",
]
