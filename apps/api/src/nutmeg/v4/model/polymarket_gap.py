"""Mispricing gap engine: Polymarket ask vs our Pinnacle de-vig fair P.

For a matched game we de-vig Pinnacle's 1X2 → fair ``q`` per outcome, read the
Polymarket ASK ``p`` for the YES share of that outcome, and report
``ev = q/p − 1`` (buying the YES is +EV iff q > p). EV is labelled HONESTLY:
**+EV carries risk; it is NOT risk-free arbitrage**, and ``q`` is only as good
as the (possibly stale) Pinnacle line behind it.

The confidence TIER is the soul of this module — a big gap is usually a data
artifact, not an edge:
- ``excluded``  favorite-flip: Pinnacle and Polymarket disagree on which TEAM is
                more likely to win → almost always one side's data is wrong
                (the friendly "favorite flip" anomaly). Dropped, never surfaced
                as actionable.
- capped to ``low``     stale Pinnacle line, thin Polymarket book, or an
                        unverifiable flip (missing opposite-side price).
- capped to ``medium``  wide ask-vs-mid spread (illiquid → inflated apparent edge).
- ``high``      survives all of the above.

Tier reflects DATA QUALITY, independent of EV magnitude; callers filter/sort by
EV separately. Network (odds + orderbooks) is injected so the core is pure and
unit-tested with literals (including the mandatory favorite-flip case).
"""
from __future__ import annotations

import datetime as dt
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nutmeg.v4.data.odds_parser import extract_1x2_odds
from nutmeg.v4.data.polymarket_match import AWAY_WIN, DRAW, HOME_WIN, MatchedGame
from nutmeg.v4.data.sources.polymarket import ask_depth_usd, best_ask, mid_price

log = logging.getLogger(__name__)

# Confidence thresholds (data-quality, not EV magnitude).
FRESH_MAX_HOURS = 12.0       # Pinnacle line older than this → cap at low
MIN_DEPTH_USD = 200.0        # USD resting at the ask below this → cap at low (thin)
WIDE_SPREAD_FRAC = 0.10      # (ask − mid)/mid above this → cap at medium
FAVORITE_TOL = 0.03          # |P_home − P_away| (or ask gap) below this = "too close
                             # to call" → never flagged as a flip
LONGSHOT_FLOOR = 0.15        # min(q, ask) below this → the "+EV" is a favourite-
                             # longshot / penny-tick ARTIFACT, not an edge: Polymarket
                             # prices in $0.01 ticks (a 1¢ tick is 25% of a 4¢ price),
                             # and the de-vig of an extreme Pinnacle line (17-to-1,
                             # 25-to-1) systematically overestimates tiny probabilities.
                             # Both manufacture fake +EV on deep underdogs/draws → cap low.
POLY_TICK = 0.01             # Polymarket's price granularity. An EV smaller than one
                             # tick's relative value (TICK/ask) is inside the rounding
                             # noise — it can flip sign on the next tick → cap low.

_TIER_RANK = {"excluded": 0, "low": 1, "medium": 2, "high": 3}
_RANK_TIER = {v: k for k, v in _TIER_RANK.items()}


@dataclass(frozen=True)
class Gap:
    fixture_id: int
    league: str
    home_team: str
    away_team: str
    match_date: str
    kickoff_utc: str | None
    outcome_spec: str           # HOME_WIN | AWAY_WIN | DRAW
    q_fair: float               # our Pinnacle de-vig fair probability
    poly_ask: float             # actionable cost to buy the YES share
    poly_mid: float | None
    ev: float                   # q/p − 1 (+EV iff > 0; carries RISK, not arb)
    edge_direction: str         # "buy_yes" | "no_edge"
    confidence_tier: str        # excluded | low | medium | high
    reasons: list[str] = field(default_factory=list)
    depth_usd: float = 0.0
    freshness_hours: float | None = None
    yes_token: str = ""
    series_slug: str = ""
    event_slug: str = ""
    match_method: str = ""
    match_confidence: float = 0.0


def _devig_1x2(h: Any, d: Any, a: Any) -> tuple[float, float, float] | None:
    """Multiplicative de-vig of 1X2 odds → fair (P_H, P_D, P_A). None on junk
    or any non-favourable (≤1.0) leg — same guard as routes._pinnacle_devig_1x2."""
    try:
        h, d, a = float(h), float(d), float(a)
    except (TypeError, ValueError):
        return None
    if any(math.isnan(x) for x in (h, d, a)) or min(h, d, a) <= 1.0:
        return None
    inv = [1.0 / h, 1.0 / d, 1.0 / a]
    s = sum(inv)
    return (inv[0] / s, inv[1] / s, inv[2] / s) if s > 0 else None


def _cap(tier: str, ceiling: str) -> str:
    return _RANK_TIER[min(_TIER_RANK[tier], _TIER_RANK[ceiling])]


def _age_hours(iso_update: str | None, now: dt.datetime) -> float | None:
    if not iso_update:
        return None
    s = str(iso_update).replace("Z", "+00:00")
    try:
        then = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.UTC)
    return (now - then).total_seconds() / 3600.0


def _favorite_flip(
    p_home: float, p_away: float, home_ask: float | None, away_ask: float | None
) -> bool | None:
    """True if Pinnacle and Polymarket disagree on the more-likely TEAM, None if
    not checkable (missing a side), False otherwise. A near-even matchup on
    EITHER source (within FAVORITE_TOL) is treated as no-flip (too close to call)."""
    if home_ask is None or away_ask is None:
        return None
    if abs(p_home - p_away) < FAVORITE_TOL or abs(home_ask - away_ask) < FAVORITE_TOL:
        return False
    # higher de-vig P / higher ask price ⇒ that source's favourite
    return (p_home > p_away) != (home_ask > away_ask)


def compute_gaps(
    game: MatchedGame,
    devig: tuple[float, float, float],
    books_by_token: dict[str, dict | None],
    odds_update: str | None,
    *,
    now: dt.datetime | None = None,
) -> list[Gap]:
    """PURE core: gaps for one game from its de-vig 1X2 + Polymarket orderbooks."""
    now = now or dt.datetime.now(dt.UTC)
    p_h, p_d, p_a = devig
    q_by_spec = {HOME_WIN: p_h, DRAW: p_d, AWAY_WIN: p_a}

    # game-level favorite-flip (needs both team asks)
    ask_of: dict[str, float | None] = {}
    for mk in game.markets:
        ba = best_ask(books_by_token.get(mk.yes_token))
        ask_of[mk.outcome_spec] = ba[0] if ba else None
    flip = _favorite_flip(p_h, p_a, ask_of.get(HOME_WIN), ask_of.get(AWAY_WIN))
    fresh_h = _age_hours(odds_update, now)

    gaps: list[Gap] = []
    for mk in game.markets:
        q = q_by_spec.get(mk.outcome_spec)
        book = books_by_token.get(mk.yes_token)
        ba = best_ask(book)
        if q is None or ba is None:
            continue  # no price / unknown outcome → can't form a gap
        p = ba[0]
        mid = mid_price(book)
        depth = ask_depth_usd(book)
        ev = q / p - 1.0

        reasons: list[str] = []
        tier = "high"
        if flip is True:
            tier = "excluded"
            reasons.append("favorite_flip")
        elif flip is None:
            tier = _cap(tier, "low")
            reasons.append("flip_uncheckable")
        if fresh_h is None:
            tier = _cap(tier, "low")
            reasons.append("pinnacle_age_unknown")
        elif fresh_h > FRESH_MAX_HOURS:
            tier = _cap(tier, "low")
            reasons.append(f"stale_pinnacle:{fresh_h:.0f}h")
        if depth < MIN_DEPTH_USD:
            tier = _cap(tier, "low")
            reasons.append(f"thin:{depth:.0f}usd")
        if mid and mid > 0 and (p - mid) / mid > WIDE_SPREAD_FRAC:
            tier = _cap(tier, "medium")
            reasons.append("wide_spread")
        if min(q, p) < LONGSHOT_FLOOR:
            tier = _cap(tier, "low")
            reasons.append(f"longshot:{min(q, p) * 100:.0f}pp")
        if 0.0 < ev < POLY_TICK / p:  # edge smaller than one price tick → noise
            tier = _cap(tier, "low")
            reasons.append("within_tick")

        gaps.append(Gap(
            fixture_id=game.fixture_id, league=game.league,
            home_team=game.home_team, away_team=game.away_team,
            match_date=game.match_date, kickoff_utc=game.kickoff_utc,
            outcome_spec=mk.outcome_spec, q_fair=q, poly_ask=p, poly_mid=mid,
            ev=ev, edge_direction="buy_yes" if q > p else "no_edge",
            confidence_tier=tier, reasons=reasons, depth_usd=depth,
            freshness_hours=fresh_h, yes_token=mk.yes_token,
            series_slug=game.series_slug, event_slug=game.event_slug,
            match_method=game.match_method, match_confidence=game.match_confidence,
        ))
    return gaps


def gaps_for_game(
    game: MatchedGame,
    *,
    fetch_odds: Callable[[int], list[dict]],
    fetch_book: Callable[[str], dict | None],
    now: dt.datetime | None = None,
) -> list[Gap]:
    """Orchestrator: fetch the fixture's Pinnacle odds + each YES token's book,
    de-vig, and compute gaps. Returns [] when no Pinnacle 1X2 line exists
    (skip — we have no fair P to compare against)."""
    try:
        envs = fetch_odds(game.fixture_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("polymarket-gap: odds fetch failed for fixture %s: %s", game.fixture_id, exc)
        return []
    env = envs[0] if envs else None
    if env is None:
        return []
    o1 = extract_1x2_odds(env)
    if not o1:
        return []
    devig = _devig_1x2(o1.get("H"), o1.get("D"), o1.get("A"))
    if devig is None:
        return []
    books = {mk.yes_token: fetch_book(mk.yes_token) for mk in game.markets}
    return compute_gaps(game, devig, books, env.get("update"), now=now)


def sort_gaps(gaps: list[Gap]) -> list[Gap]:
    """Excluded sink to the bottom; otherwise EV descending."""
    return sorted(gaps, key=lambda g: (g.confidence_tier == "excluded", -g.ev))


__all__ = [
    "Gap", "compute_gaps", "gaps_for_game", "sort_gaps",
    "FRESH_MAX_HOURS", "MIN_DEPTH_USD", "WIDE_SPREAD_FRAC", "FAVORITE_TOL",
    "LONGSHOT_FLOOR", "POLY_TICK",
]
