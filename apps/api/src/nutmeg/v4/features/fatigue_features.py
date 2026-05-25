"""Fatigue / fixture-congestion features — Path 4 of V11 Branch B (skeleton).

_V11 Phase 0 — pure-function skeleton + API shape. Production
integration is Branch B W3 work. This module compiles and tests pass
on synthetic match-history data._

## What this adds beyond form.py's existing rest_days

`features/form.py` already produces `form_home_rest_days` and
`form_away_rest_days` (continuous days-since-last-match). Empirically
these have weak predictive power because the relationship is **nonlinear**:

- 3-day turnaround: -3 to -5pp win-rate (real fatigue)
- 5-7 days: optimal recovery, no penalty
- 14+ days: rusty, slight penalty (-1pp)
- Plus: midweek UEFA matches add a separate, larger penalty (-4pp)

This module exposes **bucketed / flagged** features that capture
those nonlinearities.

## Feature output (one match, vectorized)

| Column | Type | Description |
|---|---|---|
| `fatigue_home_short_rest_3day` | int {0,1} | played within last 3 days |
| `fatigue_home_short_rest_5day` | int {0,1} | played within last 5 days |
| `fatigue_home_long_rest_14day` | int {0,1} | hasn't played in 14+ days (rust) |
| `fatigue_home_euro_midweek_4day` | int {0,1} | played UEFA cup competition in last 4 days |
| `fatigue_home_third_match_8day` | int {0,1} | this is 3rd match in 8 days |
| `fatigue_home_matches_in_30day` | int [0,12] | match count in last 30 days |
| `fatigue_away_*` | same | same for away team |

12 features total. Branch B W3's ablation decides which are kept.

## Combination with form.py

These features are **additive** to the continuous `rest_days` already
produced by `form.py` — they're not replacements. The model learns
to use both: continuous for fine-grained, flags for the known
nonlinearities.

## NOT in this skeleton (Branch B W3 deliverable)

- Walk-forward ablation against current production
- Per-league fatigue-curve tuning (UCL fixtures impact EPL teams
  differently than they do La Liga teams)
- Travel-distance fatigue (cross-link with `stadium_features.py`)
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Deque

import numpy as np
import pandas as pd


log = logging.getLogger(__name__)


# Competitions counted as "Euro midweek" — UEFA-organized club competitions
# that traditionally play Tuesday/Wednesday/Thursday. Used by the
# euro_midweek_4day flag.
EURO_MIDWEEK_COMPETITIONS: set[str] = {
    "UCL",                   # UEFA Champions League
    "UEFA_CHAMPIONS_LEAGUE", # canonical alias
    "UEL",                   # UEFA Europa League
    "UEFA_EUROPA_LEAGUE",
    "UECL",                  # UEFA Conference League
    "UEFA_CONFERENCE_LEAGUE",
}


def _is_euro_competition(league_or_competition: str) -> bool:
    """Check whether a competition string maps to a UEFA midweek cup.

    Tolerant to case + common aliases (V8 W1 canonical naming).
    """
    if not league_or_competition:
        return False
    upper = league_or_competition.upper().strip()
    if upper in EURO_MIDWEEK_COMPETITIONS:
        return True
    # Allow contains-match for free-form league strings
    for canonical in EURO_MIDWEEK_COMPETITIONS:
        if canonical in upper:
            return True
    return False


# ---------- Per-team match history container --------------------------------

class TeamHistory:
    """Bounded-deque history of one team's recent matches.

    Each entry: (date, league_or_competition).
    Bounded at 30 days lookback — past that is irrelevant for fatigue.

    Mirror of the pattern used in `form.py` (rolling deque per team)
    so Branch B W3's walk-forward integration is symmetric.
    """

    def __init__(self):
        self._deque: Deque[tuple[pd.Timestamp, str]] = deque()

    def add(self, date: pd.Timestamp, competition: str) -> None:
        """Record that this team played a match on `date` in `competition`."""
        self._deque.append((date, competition or ""))

    def prune_older_than(self, cutoff_date: pd.Timestamp) -> None:
        """Drop entries older than `cutoff_date`."""
        while self._deque and self._deque[0][0] < cutoff_date:
            self._deque.popleft()

    def matches_within(self, current_date: pd.Timestamp, days: int) -> list[tuple[pd.Timestamp, str]]:
        """Return all entries within `days` of `current_date` (inclusive)."""
        cutoff = current_date - pd.Timedelta(days=days)
        return [(d, c) for d, c in self._deque if d >= cutoff and d < current_date]

    def last_match(self) -> tuple[pd.Timestamp, str] | None:
        """Most recent entry, or None when empty."""
        if not self._deque:
            return None
        return self._deque[-1]


# ---------- Pure-function feature compute -----------------------------------

def short_rest_flag(
    history: TeamHistory,
    current_date: pd.Timestamp,
    days: int,
) -> int:
    """1 if the team played within `days` of current_date, else 0.

    Used for the 3-day and 5-day buckets (short rest = fatigue).
    """
    matches = history.matches_within(current_date, days)
    return 1 if matches else 0


def long_rest_flag(
    history: TeamHistory,
    current_date: pd.Timestamp,
    days: int = 14,
) -> int:
    """1 if the team has NOT played in `days` (rust risk), else 0.

    Edge case: if the team has never played, returns 0 (no signal).
    """
    last = history.last_match()
    if last is None:
        return 0
    days_since = (current_date - last[0]).days
    return 1 if days_since >= days else 0


def euro_midweek_flag(
    history: TeamHistory,
    current_date: pd.Timestamp,
    days: int = 4,
) -> int:
    """1 if the team played a UEFA midweek competition in the last
    `days` days, else 0.

    The 4-day default targets the "domestic match this weekend, played
    UCL Tuesday/Wednesday" pattern.
    """
    matches = history.matches_within(current_date, days)
    for _, comp in matches:
        if _is_euro_competition(comp):
            return 1
    return 0


def third_match_in_window(
    history: TeamHistory,
    current_date: pd.Timestamp,
    days: int = 8,
) -> int:
    """1 if `current_date`'s match is the team's 3rd match in `days`-day
    window (counting this match), else 0.

    Standard "fixture congestion" definition. 3 matches in 8 days is
    high-load; 4+ is brutal.
    """
    # Count prior matches in [current - days, current)
    matches = history.matches_within(current_date, days)
    # +1 for THIS match (which isn't in history yet)
    return 1 if len(matches) + 1 >= 3 else 0


def matches_count_in_window(
    history: TeamHistory,
    current_date: pd.Timestamp,
    days: int = 30,
) -> int:
    """Number of matches the team played in the last `days` days
    (NOT counting the current match)."""
    return len(history.matches_within(current_date, days))


# ---------- Vectorized builder ----------------------------------------------

OUTPUT_COLUMNS = [
    "fatigue_home_short_rest_3day",
    "fatigue_home_short_rest_5day",
    "fatigue_home_long_rest_14day",
    "fatigue_home_euro_midweek_4day",
    "fatigue_home_third_match_8day",
    "fatigue_home_matches_in_30day",
    "fatigue_away_short_rest_3day",
    "fatigue_away_short_rest_5day",
    "fatigue_away_long_rest_14day",
    "fatigue_away_euro_midweek_4day",
    "fatigue_away_third_match_8day",
    "fatigue_away_matches_in_30day",
]


def build_fatigue_features(
    df: pd.DataFrame,
    *,
    history_lookback_days: int = 30,
) -> pd.DataFrame:
    """Compute fatigue features for each row of `df`.

    `df` must be sorted by `date` ascending. Required columns:
      - `date` (pd.Timestamp)
      - `home_team`, `away_team` (str)
      - `league` or `competition` (str) — used to detect Euro matches

    For each team, maintains a rolling history. For each match row:
      1. Look up home team + away team's history BEFORE this match's date
      2. Compute fatigue features
      3. Add this match to both teams' history (so the NEXT match sees
         it as a prior)
      4. Prune entries older than `history_lookback_days` from each
         team's deque (memory bound)

    This mirrors `form.build_form_features`'s walk-in-time-order
    pattern so the same train/predict split semantics apply.

    Returns a DataFrame with the same index as `df` and OUTPUT_COLUMNS.
    """
    n = len(df)
    histories: dict[str, TeamHistory] = defaultdict(TeamHistory)
    out: dict[str, np.ndarray] = {col: np.zeros(n, dtype=int) for col in OUTPUT_COLUMNS}

    # Ensure date is a Timestamp (caller might pass string dates)
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        dates = pd.to_datetime(df["date"])
    else:
        dates = df["date"] if "date" in df.columns else pd.Series([pd.NaT] * n)

    competition_col = "competition" if "competition" in df.columns else "league"

    for i in range(n):
        row = df.iloc[i]
        d = dates.iloc[i]
        home = row.get("home_team", "")
        away = row.get("away_team", "")
        comp = row.get(competition_col, "")

        # Prune both teams' history
        prune_cutoff = d - pd.Timedelta(days=history_lookback_days)
        histories[home].prune_older_than(prune_cutoff)
        histories[away].prune_older_than(prune_cutoff)

        # Compute features for home team
        h_hist = histories[home]
        out["fatigue_home_short_rest_3day"][i] = short_rest_flag(h_hist, d, 3)
        out["fatigue_home_short_rest_5day"][i] = short_rest_flag(h_hist, d, 5)
        out["fatigue_home_long_rest_14day"][i] = long_rest_flag(h_hist, d, 14)
        out["fatigue_home_euro_midweek_4day"][i] = euro_midweek_flag(h_hist, d, 4)
        out["fatigue_home_third_match_8day"][i] = third_match_in_window(h_hist, d, 8)
        out["fatigue_home_matches_in_30day"][i] = matches_count_in_window(h_hist, d, 30)

        # Compute features for away team
        a_hist = histories[away]
        out["fatigue_away_short_rest_3day"][i] = short_rest_flag(a_hist, d, 3)
        out["fatigue_away_short_rest_5day"][i] = short_rest_flag(a_hist, d, 5)
        out["fatigue_away_long_rest_14day"][i] = long_rest_flag(a_hist, d, 14)
        out["fatigue_away_euro_midweek_4day"][i] = euro_midweek_flag(a_hist, d, 4)
        out["fatigue_away_third_match_8day"][i] = third_match_in_window(a_hist, d, 8)
        out["fatigue_away_matches_in_30day"][i] = matches_count_in_window(a_hist, d, 30)

        # Add this match to both teams' history for FUTURE rows
        histories[home].add(d, comp)
        histories[away].add(d, comp)

    return pd.DataFrame(out, index=df.index)


__all__ = [
    "EURO_MIDWEEK_COMPETITIONS",
    "OUTPUT_COLUMNS",
    "TeamHistory",
    "build_fatigue_features",
    "short_rest_flag",
    "long_rest_flag",
    "euro_midweek_flag",
    "third_match_in_window",
    "matches_count_in_window",
]
