"""Canonical match schema for V4.

All ingestion functions normalize raw CSV columns into these names.
This is the only place where column names should be defined.
"""
from __future__ import annotations

from dataclasses import dataclass


# Canonical columns of a match row in the V4 store.
# Use snake_case throughout.
MATCH_COLUMNS = [
    # identity
    "league",         # canonical league code, e.g. "E0", "D1", "JPN_J1"
    "season",         # e.g. "2425", "2324"
    "date",           # pandas Timestamp (UTC midnight; football-data has only date, not time)
    "home_team",
    "away_team",
    # full-time result
    "home_goals",     # int
    "away_goals",     # int
    "result_1x2",     # 'H' / 'D' / 'A'
    # half-time
    "ht_home_goals",  # int or NaN if missing
    "ht_away_goals",
    # match stats (may be missing for older leagues)
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "home_corners",
    "away_corners",
    "home_yellow",
    "away_yellow",
    "home_red",
    "away_red",
    # Pinnacle closing odds (sharpest, used as gold-standard baseline)
    "psc_home",
    "psc_draw",
    "psc_away",
    # Pinnacle opening odds (useful for market movement features)
    "ps_home",
    "ps_draw",
    "ps_away",
    # Bet365 closing odds (broad-book backup if PSC missing)
    "b365c_home",
    "b365c_draw",
    "b365c_away",
    # market consensus closing (average across many books)
    "avgc_home",
    "avgc_draw",
    "avgc_away",
    # Over/Under 2.5 — Pinnacle closing
    "psc_over25",
    "psc_under25",
    # Asian handicap line and Pinnacle closing odds (NOTE: this is the European AH line,
    # in 0.25 steps from home perspective. Used as a market signal feature, NOT as the
    # bet outcome — China integer handicap is settled differently from this AH line.)
    "ahch",           # closing AH line (e.g. -0.5 means home gives 0.5)
    "pcahh",          # PS closing AH home odds
    "pcaha",          # PS closing AH away odds
]


@dataclass(frozen=True)
class Match:
    """Typed view of a single row from the matches table. For type-hinting only.
    Real flows use pandas DataFrames keyed by MATCH_COLUMNS."""
    league: str
    season: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int

    @property
    def result_1x2(self) -> str:
        if self.home_goals > self.away_goals:
            return "H"
        if self.home_goals < self.away_goals:
            return "A"
        return "D"
