"""Cross-league state seeding for Elo + form features — V8 W3.

Background: V4's `build_elo_features` and `build_form_features` keep
state keyed by `(league, team)` — a team's Elo in the EPL pool is
independent of its Elo in UCL, etc. That's correct for league-only
training: EPL state stays clean, La Liga state stays clean.

V8 W2 introduced cup rows into the training frame via `--with-cup-data`.
When a UCL match for "Real Madrid vs Bayern Munich" comes through
`build_elo_features`, it looks up `state["UCL"]["Real Madrid"]` and
finds the default (1500) — Real Madrid's actual La Liga Elo (~1750
after a season) goes unused. The cup row's feature signal collapses
to "two unseen teams"; the GBM learns nothing useful from it.

**Cross-league seeding** fixes this by intercepting the FIRST lookup
in a new pool. If `state[league][team]` would return the default but
the team HAS a non-default value somewhere else in `state[*][team]`,
seed the cup pool with that cross-league value before reading.

Update logic stays the same — subsequent writes go to
`state[league][team]` only (cup pool maintains its own state after
seeding). This means:
- Domestic Elo isn't polluted by cross-league dynamics
- Cup matches use the team's REAL current strength as their prior
- After several cup matches, the cup pool develops its own state

The seeding is opt-in via a `cross_league_seed: bool` parameter on
the builders. Default is False — preserves V4/V5/V6/V7 behavior for
league-only training paths.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Iterable


def seed_elo_value(
    state: dict[str, dict[str, float]],
    league: str,
    team: str,
    default: float,
) -> float:
    """Return a seeded Elo value for (league, team).

    If `state[league][team]` would be the default (i.e., not yet seen
    in THIS league pool), search the other leagues in `state` for a
    different value. Returns the first non-default value found, else
    the default.

    Mutates `state` by writing the seeded value into
    `state[league][team]` so subsequent reads short-circuit.
    """
    league_pool = state.get(league)
    # Team already present in THIS league pool → keep existing value
    if league_pool is not None and team in league_pool:
        return league_pool[team]
    # Walk every other league pool for a non-default value
    for other_league, other_pool in state.items():
        if other_league == league:
            continue
        if team in other_pool and other_pool[team] != default:
            seeded = other_pool[team]
            # Write back so subsequent reads in THIS league are stable
            # (defaultdict-based caller may auto-create league_pool;
            # handle both dict-of-dict and defaultdict gracefully)
            if league_pool is None:
                state[league] = {team: seeded}
            else:
                league_pool[team] = seeded
            return seeded
    return default


def seed_form_deque(
    state: dict[tuple[str, str], Deque],
    league: str,
    team: str,
    *,
    window: int,
) -> Deque:
    """Return a seeded rolling-deque for (league, team) form state.

    `state` is V4 form's tuple-keyed defaultdict (deque per
    `(league, team)`). If `state[(league, team)]` is empty AND the
    team has non-empty form history in any OTHER league pool, COPY
    that history into the cup pool (limited to `window`).

    Mutates `state` by writing the seeded deque into
    `state[(league, team)]`. Returns the seeded deque (or the
    original empty one when no cross-league history exists).
    """
    own = state.get((league, team))
    if own is not None and len(own) > 0:
        return own
    # Search across other leagues
    for (other_league, other_team), other_deque in state.items():
        if other_team != team or other_league == league:
            continue
        if len(other_deque) > 0:
            # Copy the most-recent up-to-window values
            seeded = deque(list(other_deque), maxlen=window)
            state[(league, team)] = seeded
            return seeded
    # No seed available; defaultdict will keep the empty deque
    if own is None:
        new_deque = deque(maxlen=window)
        state[(league, team)] = new_deque
        return new_deque
    return own


def seed_form_last_date(
    state: dict[tuple[str, str], object],
    league: str,
    team: str,
):
    """Return the most-recent last_match_date for (league, team).

    If the team has a cup-pool entry, return it. Else fall back to
    the maximum last_date across all other-league pools (so the
    rest-days feature for a UCL-first-appearance Real Madrid uses
    their last La Liga match date).
    """
    own = state.get((league, team))
    if own is not None:
        return own
    candidates = []
    for (other_league, other_team), other_date in state.items():
        if other_team != team or other_league == league:
            continue
        candidates.append(other_date)
    if not candidates:
        return None
    return max(candidates)


__all__ = [
    "seed_elo_value",
    "seed_form_deque",
    "seed_form_last_date",
]
