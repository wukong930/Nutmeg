"""Cup + national-team feature columns — V6 W11.

A small bundle of side-channel features the GBM can learn a downweight
on for cup vs league matches. The current V4/V6 W6 model is trained on
domestic league data only; cup data backfill is deferred. These columns
emit zeros on the existing training set (since every existing row has
`league` ∈ the domestic registry), so adding them is a no-op on the
shipped artifact's predictions. When future training includes cup rows
the GBM picks them up automatically.

Why side-channel rather than retraining now:
- Cup sample is small (UCL ~125 matches/season vs EPL 380), so a
  cup-trained model would suffer high variance. Keeping the league
  model and side-channeling cup-ness lets the league signal dominate
  while still letting the GBM dial down confidence for cup matches.
- Cup-specific kinematics (neutral venues, two-legged ties, knockout
  pressure) are partly captured by `is_knockout` + `is_two_legged`
  flags here; finer-grained cup features (aggregate-leg context, away-
  goal rules) are V7 territory.

Cross-league team resolution (`find_team_state_cross_league`) lives in
this module too — UCL matches pit teams from different leagues against
each other; the league-keyed `team_state` dict needs a fallback search
when the row's `league` is a cup.
"""
from __future__ import annotations

import pandas as pd

from nutmeg.v4.data.competitions import (
    CUP_COMPETITIONS,
    competition_type_id,
    has_two_legged_format,
    is_cup_competition,
    is_knockout_round,
    is_national_team_competition,
)


CUP_FEATURE_COLUMNS: list[str] = [
    "is_cup_match",
    "is_knockout",
    "is_two_legged",
    "is_national_team_match",
    "competition_type_id",
]
"""GBM-side feature names produced by `build_cup_features`. Order matters —
keep in lockstep with `feature_columns_with_cup()` in features.pipeline
(W12 wires the columns into the model)."""


def derive_cup_features_single(
    league_code: str,
    round_label: str | None = None,
) -> dict[str, float]:
    """Compute the 5 cup features for a single (league, round) tuple.

    Round label comes from API-Football's `fixture.league.round` — e.g.
    "Group A - Matchday 3" (group stage) or "Round of 16" (knockout).
    For non-cup matches this is ignored and all knockout flags are 0.
    """
    is_cup = is_cup_competition(league_code)
    is_nat = is_national_team_competition(league_code)
    # is_knockout: only set for cup matches when the round label is a
    # knockout token. League matches always emit 0.
    is_ko = 1.0 if (is_cup and is_knockout_round(round_label)) else 0.0
    # is_two_legged: structural flag of the COMPETITION. The actual leg
    # number (1st/2nd) isn't surfaced here — finer-grained features can
    # be added later when training data includes aggregate context.
    is_two = 1.0 if (is_cup and has_two_legged_format(league_code)) else 0.0
    return {
        "is_cup_match":           1.0 if is_cup else 0.0,
        "is_knockout":            is_ko,
        "is_two_legged":          is_two,
        "is_national_team_match": 1.0 if is_nat else 0.0,
        "competition_type_id":    float(competition_type_id(league_code)),
    }


def build_cup_features(
    df: pd.DataFrame,
    *,
    league_col: str = "league",
    round_col: str = "round",
) -> pd.DataFrame:
    """Append the 5 cup feature columns to a fixture DataFrame.

    `df` should have at least `league_col`. `round_col` is optional —
    when missing the column is treated as all-None and only the
    competition-level flags (is_cup_match, is_two_legged,
    is_national_team_match, competition_type_id) fire; `is_knockout`
    stays 0.

    Returns a copy of `df` with the new columns appended; original
    untouched.
    """
    out = df.copy()
    if round_col not in out.columns:
        out[round_col] = None
    feats = [
        derive_cup_features_single(row[league_col], row[round_col])
        for _, row in out.iterrows()
    ]
    for col in CUP_FEATURE_COLUMNS:
        out[col] = [f[col] for f in feats]
    return out


# --- Cross-league team state resolution ---------------------------------

def find_team_state_cross_league(
    team_state: dict[str, dict[str, object]],
    team_name: str,
    preferred_league: str | None = None,
) -> object | None:
    """Look up a team's state regardless of which league it's stored under.

    Pre-W11 `team_state` is keyed by (league, team). For league fixtures
    we know the team is under its native league. For CUP fixtures the
    `league` field is the cup code (UCL, FAC etc) and the team is stored
    under its DOMESTIC league. This helper does the search:

    1. Try `preferred_league` first (when caller has a hint, e.g. "the
       team is known to play in ESP_LA_LIGA").
    2. Fall back to walking every league in `team_state` and returning
       the first match.
    3. Return None when the team isn't found anywhere.

    Returns the TeamState object (or None). Does not mutate state.

    Caveat: when a team name collides across leagues (rare — usually
    only with obvious dual-league names like "Real Madrid" vs "Real
    Madrid C" or two clubs sharing a literal name), the first match
    in dict-iteration order wins. Callers concerned about collisions
    should pass `preferred_league`.
    """
    if preferred_league is not None:
        teams = team_state.get(preferred_league, {})
        if team_name in teams:
            return teams[team_name]
    for league, teams in team_state.items():
        if league == preferred_league:
            continue  # already tried
        if team_name in teams:
            return teams[team_name]
    return None


def lookup_cup_team_pair(
    team_state: dict[str, dict[str, object]],
    league_code: str,
    home_team: str,
    away_team: str,
) -> tuple[object | None, object | None]:
    """Resolve (home, away) team states for a CUP fixture.

    For domestic league fixtures use `team_state[league][team]` directly
    — this helper handles the cup case where `league_code` is a cup and
    neither team has state stored under that key.
    """
    if not is_cup_competition(league_code):
        teams = team_state.get(league_code, {})
        return teams.get(home_team), teams.get(away_team)
    h = find_team_state_cross_league(team_state, home_team)
    a = find_team_state_cross_league(team_state, away_team)
    return h, a


def display_zh(code: str) -> str:
    """Chinese display name for any competition code (cup or league).

    For league codes the registry doesn't include them, so we return the
    code unchanged (the V4 codes themselves like 'EPL', 'ESP_LA_LIGA'
    are well-known abbreviations and dashboards display them as-is).
    """
    comp = CUP_COMPETITIONS.get(code)
    return comp.display_zh if comp else code


__all__ = [
    "CUP_FEATURE_COLUMNS",
    "derive_cup_features_single",
    "build_cup_features",
    "find_team_state_cross_league",
    "lookup_cup_team_pair",
    "display_zh",
]
