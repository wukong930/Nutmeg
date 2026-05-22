"""Rolling form features for each team, computed from prior matches only.

For each (team, league) we keep a rolling deque of the last N matches and
expose summary stats BEFORE the current match.

Output per match:
  form_home_goals_for_n6        — avg goals scored by home team in last 6 matches
  form_home_goals_against_n6    — avg conceded
  form_home_shots_n6, form_home_shots_on_target_n6 — xG-lite
  form_away_*  — same for away team
  form_home_rest_days, form_away_rest_days — days since each team's last match

These DO NOT split by home/away venue (sample size at N=6 too small).
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque

import numpy as np
import pandas as pd


WINDOW = 6


def _avg(vals: Deque) -> float:
    if not vals:
        return np.nan
    return float(np.mean([v for v in vals if v is not None and not np.isnan(v)])
                  if any(v is not None and not np.isnan(v) for v in vals) else np.nan)


def build_form_features(df: pd.DataFrame, *, window: int = WINDOW) -> pd.DataFrame:
    """Walk in time order, maintain per-(league, team) rolling deques."""
    out = df.sort_values(["league", "date"]).reset_index(drop=True).copy()

    # Per-team rolling state. `shots` is shots-FOR; `shots_ag` is shots-AGAINST
    # (i.e., the opponent's shot count when this team played). The against
    # variants are V5 W4 additions used by xg_lite features as a defensive proxy.
    g_for: dict[tuple[str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=window))
    g_ag: dict[tuple[str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=window))
    shots: dict[tuple[str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=window))
    shots_ag: dict[tuple[str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=window))
    sot: dict[tuple[str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=window))
    sot_ag: dict[tuple[str, str], Deque[float]] = defaultdict(lambda: deque(maxlen=window))
    last_date: dict[tuple[str, str], pd.Timestamp] = {}

    cols_to_init = [
        "form_home_goals_for_n", "form_home_goals_against_n",
        "form_home_shots_n", "form_home_shots_on_target_n",
        "form_home_shots_against_n", "form_home_sot_against_n",
        "form_away_goals_for_n", "form_away_goals_against_n",
        "form_away_shots_n", "form_away_shots_on_target_n",
        "form_away_shots_against_n", "form_away_sot_against_n",
        "form_home_rest_days", "form_away_rest_days",
    ]
    init = {c: np.full(len(out), np.nan) for c in cols_to_init}

    for i, row in enumerate(out.itertuples(index=False)):
        kh = (row.league, row.home_team)
        ka = (row.league, row.away_team)

        init["form_home_goals_for_n"][i] = _avg(g_for[kh])
        init["form_home_goals_against_n"][i] = _avg(g_ag[kh])
        init["form_home_shots_n"][i] = _avg(shots[kh])
        init["form_home_shots_on_target_n"][i] = _avg(sot[kh])
        init["form_home_shots_against_n"][i] = _avg(shots_ag[kh])
        init["form_home_sot_against_n"][i] = _avg(sot_ag[kh])
        init["form_away_goals_for_n"][i] = _avg(g_for[ka])
        init["form_away_goals_against_n"][i] = _avg(g_ag[ka])
        init["form_away_shots_n"][i] = _avg(shots[ka])
        init["form_away_shots_on_target_n"][i] = _avg(sot[ka])
        init["form_away_shots_against_n"][i] = _avg(shots_ag[ka])
        init["form_away_sot_against_n"][i] = _avg(sot_ag[ka])
        if kh in last_date:
            init["form_home_rest_days"][i] = (row.date - last_date[kh]).total_seconds() / 86400
        if ka in last_date:
            init["form_away_rest_days"][i] = (row.date - last_date[ka]).total_seconds() / 86400

        # Update after recording features
        g_for[kh].append(float(row.home_goals))
        g_ag[kh].append(float(row.away_goals))
        g_for[ka].append(float(row.away_goals))
        g_ag[ka].append(float(row.home_goals))
        # Shots may be NaN for older / Japan rows
        hs = getattr(row, "home_shots", np.nan)
        ash = getattr(row, "away_shots", np.nan)
        hst = getattr(row, "home_shots_on_target", np.nan)
        ast_ = getattr(row, "away_shots_on_target", np.nan)

        def _nan_or_float(v: object) -> float:
            try:
                if v is None or pd.isna(v):
                    return np.nan
                return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return np.nan

        hs_f, ash_f, hst_f, ast_f = (
            _nan_or_float(hs), _nan_or_float(ash), _nan_or_float(hst), _nan_or_float(ast_)
        )
        # FOR (this team's shots)
        shots[kh].append(hs_f)
        shots[ka].append(ash_f)
        sot[kh].append(hst_f)
        sot[ka].append(ast_f)
        # AGAINST (opponent's shots when this team played)
        shots_ag[kh].append(ash_f)
        shots_ag[ka].append(hs_f)
        sot_ag[kh].append(ast_f)
        sot_ag[ka].append(hst_f)

        last_date[kh] = row.date
        last_date[ka] = row.date

    for c, v in init.items():
        out[c] = v
    out["form_home_goal_diff_n"] = out["form_home_goals_for_n"] - out["form_home_goals_against_n"]
    out["form_away_goal_diff_n"] = out["form_away_goals_for_n"] - out["form_away_goals_against_n"]
    return out
