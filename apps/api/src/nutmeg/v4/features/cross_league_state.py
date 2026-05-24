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
    *,
    nation_state: dict[str, float] | None = None,
    is_national_team_league: bool = False,
) -> float:
    """Return a seeded Elo value for (league, team).

    Precedence:
      1. If `state[league][team]` is already populated, return it
      2. **Post-V8 P1#4**: when `is_national_team_league=True` AND
         `nation_state` is provided, try `lookup_nation_elo(nation_state, team)`.
         Hits get seeded into `state[league][team]` and returned.
         (Skipped for non-national-team leagues since the nation lookup
         could resolve "Manchester" → "ENG" which is wrong for club rows.)
      3. Walk every other league pool for a non-default value
         (the original V8 W3 cross-league seeding)
      4. Return the default

    Mutates `state` by writing the seeded value into `state[league][team]`
    so subsequent reads short-circuit.

    `nation_state` is the dict returned by `build_nation_elo_lookup` —
    `{clubelo_code: elo}`. The resolver tolerates name variants
    ("United States" → "USA") via the V8 W7 alias map.
    """
    league_pool = state.get(league)
    # 1. Team already in THIS league pool
    if league_pool is not None and team in league_pool:
        return league_pool[team]

    # 2. (Post-V8 P1#4) National-team Elo seed for national-team-cup leagues
    if is_national_team_league and nation_state:
        # Lazy import to avoid circular dependency (data → features in this
        # module is a one-way relationship, but the function only needs to
        # be importable once at first call)
        from nutmeg.v4.data.national_team_elo import lookup_nation_elo
        code, elo = lookup_nation_elo(nation_state, team)
        if elo is not None:
            if league_pool is None:
                state[league] = {team: elo}
            else:
                league_pool[team] = elo
            return elo

    # 3. Walk every other league pool for a non-default value
    for other_league, other_pool in state.items():
        if other_league == league:
            continue
        if team in other_pool and other_pool[team] != default:
            seeded = other_pool[team]
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
