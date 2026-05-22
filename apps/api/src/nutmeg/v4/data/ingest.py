"""Ingest football-data.co.uk CSVs into a canonical pandas DataFrame.

Source layout:
  data/historical_sources/football_data_co_uk/europe/<season>/<league_code>.csv
  data/historical_sources/football_data_co_uk/japan/JPN.csv

Europe CSVs share a common (~70-119 col) schema with abbreviated codes:
  FTHG/FTAG = full-time home/away goals, FTR = full-time result
  PSCH/PSCD/PSCA = Pinnacle closing 1X2
  B365CH/B365CD/B365CA = Bet365 closing 1X2
  AHCh = closing Asian handicap line (home perspective)

Japan CSV (international cross-country aggregator) uses different column names.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from nutmeg.v4.data.schema import MATCH_COLUMNS


# Map football-data.co.uk league codes to canonical names.
# Codes seen in europe/<season>/: D1, D2, E0, E1, F1, F2, I1, I2, N1, P1, SP1, SP2
LEAGUE_NAMES = {
    "D1": "GER_BUNDESLIGA",
    "D2": "GER_2_BUNDESLIGA",
    "E0": "EPL",
    "E1": "ENG_CHAMPIONSHIP",
    "F1": "FRA_LIGUE_1",
    "F2": "FRA_LIGUE_2",
    "I1": "ITA_SERIE_A",
    "I2": "ITA_SERIE_B",
    "N1": "NED_EREDIVISIE",
    "P1": "PRT_PRIMEIRA_LIGA",
    "SP1": "ESP_LA_LIGA",
    "SP2": "ESP_SEGUNDA_DIVISION",
    "EC": "ENG_LEAGUE_ONE",  # not always present
    "T1": "TUR_SUPER_LIG",
    "G1": "GRE_SUPER_LEAGUE",
    "B1": "BEL_PRO_LEAGUE",
    "SC0": "SCO_PREMIERSHIP",
}


# Map source column → canonical column. Source value is None → fill NaN.
EUROPE_COLUMN_MAP = {
    "home_team": "HomeTeam",
    "away_team": "AwayTeam",
    "home_goals": "FTHG",
    "away_goals": "FTAG",
    "result_1x2": "FTR",
    "ht_home_goals": "HTHG",
    "ht_away_goals": "HTAG",
    "home_shots": "HS",
    "away_shots": "AS",
    "home_shots_on_target": "HST",
    "away_shots_on_target": "AST",
    "home_corners": "HC",
    "away_corners": "AC",
    "home_yellow": "HY",
    "away_yellow": "AY",
    "home_red": "HR",
    "away_red": "AR",
    "psc_home": "PSCH",
    "psc_draw": "PSCD",
    "psc_away": "PSCA",
    "ps_home": "PSH",
    "ps_draw": "PSD",
    "ps_away": "PSA",
    "b365c_home": "B365CH",
    "b365c_draw": "B365CD",
    "b365c_away": "B365CA",
    "avgc_home": "AvgCH",
    "avgc_draw": "AvgCD",
    "avgc_away": "AvgCA",
    "psc_over25": "PC>2.5",
    "psc_under25": "PC<2.5",
    "ahch": "AHCh",
    "pcahh": "PCAHH",
    "pcaha": "PCAHA",
}


def _read_europe_csv(path: Path, season: str) -> pd.DataFrame:
    """Read one football-data.co.uk Europe season CSV → canonical DataFrame."""
    # First column has a BOM (﻿'Div'); use utf-8-sig.
    raw = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    if "Div" not in raw.columns:
        raise ValueError(f"{path}: missing 'Div' column; got {list(raw.columns)[:10]}")
    if "Date" not in raw.columns:
        raise ValueError(f"{path}: missing 'Date' column")
    # Drop rows where the basic result columns are missing (often trailing blank lines).
    raw = raw.dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]).copy()
    out = pd.DataFrame(index=raw.index)
    out["league"] = raw["Div"].map(LEAGUE_NAMES).fillna(raw["Div"])
    out["season"] = season
    out["date"] = pd.to_datetime(raw["Date"], format="mixed", dayfirst=True)
    for canon, src in EUROPE_COLUMN_MAP.items():
        if src in raw.columns:
            out[canon] = raw[src]
        else:
            out[canon] = pd.NA
    # Make sure integer columns are int (we already dropped NaN rows on the critical ones).
    for c in ["home_goals", "away_goals"]:
        out[c] = out[c].astype(int)
    # Ordering for downstream stability
    return out.reindex(columns=MATCH_COLUMNS).reset_index(drop=True)


def _read_japan_csv(path: Path) -> pd.DataFrame:
    """Read the Japan multi-season CSV (different schema)."""
    raw = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    # Sample cols: Country, League, Season, Date, Time, Home, Away, HG, AG, Res, PSCH, PSCD, PSCA...
    if "League" not in raw.columns:
        return pd.DataFrame(columns=MATCH_COLUMNS)
    raw = raw.dropna(subset=["Home", "Away", "HG", "AG", "Res"]).copy()
    out = pd.DataFrame(index=raw.index)
    league_raw = raw["League"].astype(str).str.strip()
    league_map = {"J1 League": "JPN_J1", "J2 League": "JPN_J2"}
    out["league"] = league_raw.map(league_map).fillna(league_raw)
    out["season"] = raw["Season"].astype(str).str.replace("/", "").str[-4:]
    out["date"] = pd.to_datetime(raw["Date"], format="mixed", dayfirst=True)
    out["home_team"] = raw["Home"]
    out["away_team"] = raw["Away"]
    out["home_goals"] = raw["HG"].astype(int)
    out["away_goals"] = raw["AG"].astype(int)
    out["result_1x2"] = raw["Res"]
    for col in MATCH_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    # The international file does carry PS closing odds when available.
    for canon, src in [
        ("psc_home", "PSCH"), ("psc_draw", "PSCD"), ("psc_away", "PSCA"),
        ("avgc_home", "AvgCH"), ("avgc_draw", "AvgCD"), ("avgc_away", "AvgCA"),
    ]:
        if src in raw.columns:
            out[canon] = raw[src]
    return out.reindex(columns=MATCH_COLUMNS).reset_index(drop=True)


def load_football_data_csv(path: str | Path, season: Optional[str] = None) -> pd.DataFrame:
    """Public function: read one CSV into canonical format. Auto-detects schema."""
    p = Path(path)
    name = p.name.lower()
    if name.startswith("jpn"):
        return _read_japan_csv(p)
    if season is None:
        season = p.parent.name
    return _read_europe_csv(p, season=season)


def load_all_matches(root: str | Path) -> pd.DataFrame:
    """Walk the football-data.co.uk tree and concatenate everything."""
    root_p = Path(root)
    frames: list[pd.DataFrame] = []
    europe = root_p / "europe"
    if europe.is_dir():
        for season_dir in sorted(europe.iterdir()):
            if not season_dir.is_dir():
                continue
            for csv in sorted(season_dir.glob("*.csv")):
                df = _read_europe_csv(csv, season=season_dir.name)
                if not df.empty:
                    frames.append(df)
    japan = root_p / "japan" / "JPN.csv"
    if japan.exists():
        frames.append(_read_japan_csv(japan))
    if not frames:
        return pd.DataFrame(columns=MATCH_COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["date", "league", "home_team"]).reset_index(drop=True)
    return out
