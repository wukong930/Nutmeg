"""Cup competition historical fixtures → parquet store — V7 W6.

V6 W11 shipped the cup registry + side-channel feature columns; the
GBM still has zero cup training data. V7 W6-W8 backfill that data,
starting here in W6 with the data layer:

  raw API-Football /fixtures envelopes
       ↓  normalize_fixture()
  per-fixture dict (V4-schema columns + cup-specific fields)
       ↓  write_cup_history_parquet()
  data/external/cup_history/<league>_<season>.parquet
       ↓  load_multi_season_cup_history()
  merged DataFrame ready for V7 W7's feature_columns_with_cup() training

V7 W7 wires the parquet contents into the training pipeline (multi-fold
validation on 4 cutoffs × {UCL, UEL}). V7 W8 ships the cup-aware
artifact opt-in. This module is intentionally pure data plumbing —
no training, no model.

Schema (one row per fixture):

| Column              | Type   | Notes |
|---------------------|--------|---|
| date                | str    | YYYY-MM-DD, UTC kickoff date |
| league              | str    | V4 canonical code (UCL/UEL/UECL/FAC/...) |
| home_team           | str    | API-Football's team name (matches ingest-odds output) |
| away_team           | str    | same |
| home_goals          | int    | final score after status filter |
| away_goals          | int    | final score after status filter |
| status_short        | str    | API-Football short status (FT/AET/PEN) |
| round_label         | str    | API-Football round string ("Group A - Matchday 3", "Round of 16", "Final") |
| api_football_id     | int    | fixture id (for cache traceability) |
| season              | int    | season start year |
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from nutmeg.v4.cli.auto_settle import FINISHED_STATUSES
from nutmeg.v4.data.competitions import is_knockout_fixture
from nutmeg.v4.data.sources import api_football


CUP_HISTORY_COLUMNS = [
    "date",
    "league",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "status_short",
    "round_label",
    "api_football_id",
    "season",
]


def normalize_fixture(
    api_fixture: dict,
    league_code: str,
    season: int,
) -> Optional[dict]:
    """API-Football /fixtures envelope → our cup-history row dict.

    Returns None when:
      - status isn't in FINISHED_STATUSES (LIVE / NS / PST / CANC etc.)
      - goals missing (defensive)
      - team names or date missing

    The status filter is identical to V7 W2's auto_settle — for
    training we want only matches with real final scores.
    """
    fixture_blob = api_fixture.get("fixture") or {}
    status_short = (fixture_blob.get("status") or {}).get("short")
    if status_short not in FINISHED_STATUSES:
        return None

    iso_date = fixture_blob.get("date", "")
    match_date = iso_date[:10] if iso_date else None
    if not match_date:
        return None

    teams = api_fixture.get("teams") or {}
    home = (teams.get("home") or {}).get("name")
    away = (teams.get("away") or {}).get("name")
    if not (home and away):
        return None

    goals = api_fixture.get("goals") or {}
    hg = goals.get("home")
    ag = goals.get("away")
    if hg is None or ag is None:
        return None

    league_blob = api_fixture.get("league") or {}
    round_label = league_blob.get("round") or ""
    fid = fixture_blob.get("id")

    return {
        "date": match_date,
        "league": league_code,
        "home_team": home,
        "away_team": away,
        "home_goals": int(hg),
        "away_goals": int(ag),
        "status_short": status_short,
        "round_label": round_label,
        "api_football_id": int(fid) if fid is not None else None,
        "season": int(season),
    }


def gather_cup_history_for_season(
    league_code: str,
    season: int,
    *,
    cache_dir: Path,
    refresh: bool = False,
) -> list[dict]:
    """Pull one (league, season) from API-Football, return normalized rows.

    One API call (the season-wide /fixtures), all matches with final
    scores returned as cup-history dicts. Non-finished matches are
    silently dropped.
    """
    fixtures = api_football._request(
        "/fixtures",
        {"league": api_football.league_id(league_code), "season": season},
        cache_dir=cache_dir,
        refresh=refresh,
    )
    rows: list[dict] = []
    for f in fixtures:
        row = normalize_fixture(f, league_code, season)
        if row is not None:
            rows.append(row)
    return rows


def write_cup_history_parquet(
    rows: list[dict],
    out_path: Path,
) -> Path:
    """Write rows as parquet with the canonical CUP_HISTORY_COLUMNS schema.

    Empty rows still produces a valid empty-schema parquet (so downstream
    `load_multi_season_cup_history` can concat across all seasons without
    special-casing the "this season was all-postponed" edge).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=CUP_HISTORY_COLUMNS)
    df.to_parquet(out_path, index=False)
    return out_path


def cup_history_parquet_path(
    out_dir: Path,
    league_code: str,
    season: int,
) -> Path:
    """Canonical filename for one (league, season) parquet."""
    return out_dir / f"{league_code}_{season}.parquet"


def load_cup_history_parquet(path: Path) -> pd.DataFrame:
    """Read one (league, season) parquet back. Empty when file missing."""
    if not path.exists():
        return pd.DataFrame(columns=CUP_HISTORY_COLUMNS)
    return pd.read_parquet(path)


def load_multi_season_cup_history(
    out_dir: Path,
    leagues: Iterable[str],
    seasons: Iterable[int],
) -> pd.DataFrame:
    """Concat every (league, season) parquet found in out_dir.

    Missing files are silently skipped — callers should pre-check
    coverage if they expect every combination to be present.
    Returns a DataFrame with `date` parsed to datetime (V4 pipeline
    expects timestamps).
    """
    parts: list[pd.DataFrame] = []
    for league in leagues:
        for season in seasons:
            path = cup_history_parquet_path(out_dir, league, season)
            if not path.exists():
                continue
            df = load_cup_history_parquet(path)
            if len(df) > 0:
                parts.append(df)
    if not parts:
        return pd.DataFrame(columns=CUP_HISTORY_COLUMNS)
    combined = pd.concat(parts, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    return combined


def derive_round_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Append `is_knockout` boolean column derived from (`league`, `round_label`).

    Competition-first: a pure-knockout cup is flagged from the registry
    (the FA Cup's "3rd Round" is a knockout tie — the old label-only
    path scored it 0), and only group-stage cups like UCL fall through
    to the round-label heuristic.

    Pulled out as a separate function so V7 W7's
    feature_columns_with_cup() can call it on the loaded multi-season
    DataFrame without duplicating the dispatch.
    """
    out = df.copy()
    pairs = out[["league", "round_label"]].itertuples(index=False, name=None)
    out["is_knockout"] = pd.Series(
        [is_knockout_fixture(league, label) for league, label in pairs],
        index=out.index,
    ).astype(int)
    return out


__all__ = [
    "CUP_HISTORY_COLUMNS",
    "normalize_fixture",
    "gather_cup_history_for_season",
    "write_cup_history_parquet",
    "cup_history_parquet_path",
    "load_cup_history_parquet",
    "load_multi_season_cup_history",
    "derive_round_flags",
]
