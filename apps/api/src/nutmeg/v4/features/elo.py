"""Elo rating engine.

Standard Elo with:
  - Home advantage offset added BEFORE expectancy computation
  - Per-league rating pools (different leagues are kept separate)
  - K factor configurable; standard chess K=20 is a reasonable football default
  - Initial rating 1500
  - Goal-difference multiplier optional (FIFA-style: K_eff = K * (1 + log(|diff|+1)))

Features added per match (using ratings BEFORE that match):
  elo_home  — home team Elo before kickoff
  elo_away  — away team Elo before kickoff
  elo_diff  — elo_home - elo_away + home_advantage
  elo_p_home — Elo-implied P(home wins, no draw) for context
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_INITIAL = 1500.0
DEFAULT_K = 20.0
DEFAULT_HOME_ADV = 60.0


def _expected(elo_a: float, elo_b: float) -> float:
    """Probability of A beating B given Elo ratings."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


def build_elo_features(
    df: pd.DataFrame,
    *,
    initial: float = DEFAULT_INITIAL,
    k: float = DEFAULT_K,
    home_advantage: float = DEFAULT_HOME_ADV,
    use_goal_diff: bool = True,
    cross_league_seed: bool = False,
    nation_state: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Walk df in time order, maintaining per-league Elo state, attach pre-match ratings.

    Returns a NEW DataFrame with added columns:
      elo_home, elo_away, elo_diff, elo_p_home

    Caller is responsible for time order; we sort defensively.

    V8 W3: when ``cross_league_seed=True``, the FIRST encounter of a
    team in a new league pool seeds that pool with the team's current
    Elo from any OTHER league pool. Used when training on
    `--with-cup-data` runs where cup teams (UCL Real Madrid) need
    their domestic-league Elo as a prior. No behavior change for
    league-only training (default False).

    Post-V8 P1#4: when ``nation_state`` is provided AND a row's league
    is registered as a national-team cup (WC, EURO, COPA_AMERICA, etc.),
    seed each team's Elo from clubelo's per-nation history via
    `lookup_nation_elo`. Requires ``cross_league_seed=True`` (seeding
    happens through the same code path). When ``nation_state`` is None,
    national-team rows fall back to V4's default 1500 — the V8 W7
    behavior.
    """
    # V8 W3: cross_league_seed needs to walk in pure chronological order
    # (not per-league chunks) so cup matches see the most-recent state
    # of cross-league teams. League-only paths keep the original
    # (league, date) sort for backward compatibility.
    if cross_league_seed:
        from nutmeg.v4.data.competitions import is_national_team_competition
        from nutmeg.v4.features.cross_league_state import seed_elo_value
        out = df.sort_values(["date", "league"]).reset_index(drop=True).copy()
    else:
        seed_elo_value = None
        is_national_team_competition = None
        out = df.sort_values(["league", "date"]).reset_index(drop=True).copy()
    # State: league → team → rating
    state: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(lambda: initial))

    elo_h = np.empty(len(out), dtype=float)
    elo_a = np.empty(len(out), dtype=float)

    for i, row in enumerate(out.itertuples(index=False)):
        league = row.league
        if cross_league_seed:
            is_nt = is_national_team_competition(league)
            rh = seed_elo_value(
                state, league, row.home_team, initial,
                nation_state=nation_state,
                is_national_team_league=is_nt,
            )
            ra = seed_elo_value(
                state, league, row.away_team, initial,
                nation_state=nation_state,
                is_national_team_league=is_nt,
            )
            s = state[league]
        else:
            s = state[league]
            rh = s[row.home_team]
            ra = s[row.away_team]
        elo_h[i] = rh
        elo_a[i] = ra

        # Update post-match
        ph = _expected(rh + home_advantage, ra)
        if row.home_goals > row.away_goals:
            actual_h = 1.0
        elif row.home_goals < row.away_goals:
            actual_h = 0.0
        else:
            actual_h = 0.5
        delta = row.home_goals - row.away_goals
        k_eff = k * (1.0 + np.log(abs(delta) + 1.0)) if use_goal_diff else k
        update = k_eff * (actual_h - ph)
        s[row.home_team] = rh + update
        s[row.away_team] = ra - update

    out["elo_home"] = elo_h
    out["elo_away"] = elo_a
    out["elo_diff"] = elo_h - elo_a + home_advantage
    out["elo_p_home"] = 1.0 / (1.0 + 10.0 ** (-(out["elo_diff"]) / 400.0))
    return out
