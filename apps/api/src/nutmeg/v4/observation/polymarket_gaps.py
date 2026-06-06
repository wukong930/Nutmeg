"""Polymarket mispricing-gap log (READ-ONLY measurement, NO betting).

Persists detected gaps over time so we can answer, weeks later, the only honest
question about this experiment: **were the high-confidence gaps actually real,
and did the favorite-flip guard remove the losers?** Each row stores our fair
``q``, the Polymarket ask, the EV, the confidence tier + reasons, and (filled
after kickoff) whether the bought YES would have resolved true — so a report can
score realized hit-rate by tier.

Design mirrors observation/prediction_log.py (denormalized, idempotent,
cron-friendly). Keyed by (match_date, fixture_id, outcome_spec). Re-logging
updates the price/EV/tier columns (prices move) but NEVER clobbers a filled
outcome. NOTHING here places an order — it only records what was observed.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Callable

from nutmeg.v4.observation.prediction_log import _ft_outcome
from nutmeg.v4.observation.store import open_db

log = logging.getLogger(__name__)

__all__ = [
    "ensure_polymarket_gaps_table",
    "record_polymarket_gap",
    "fetch_polymarket_gaps",
    "settle_polymarket_gaps",
]

POLYMARKET_GAPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS polymarket_gaps (
    match_date       TEXT NOT NULL,
    fixture_id       INTEGER NOT NULL,
    outcome_spec     TEXT NOT NULL,        -- HOME_WIN | AWAY_WIN | DRAW
    recorded_at      TEXT NOT NULL,
    league           TEXT,
    home_team        TEXT,
    away_team        TEXT,
    kickoff_utc      TEXT,
    series_slug      TEXT,
    event_slug       TEXT,
    yes_token        TEXT,
    -- the measurement: our fair P vs the Polymarket ask, the gap, confidence.
    q_fair           REAL NOT NULL,        -- Pinnacle de-vig fair probability
    poly_ask         REAL NOT NULL,        -- actionable cost to buy the YES
    poly_mid         REAL,
    ev               REAL NOT NULL,        -- q/ask − 1 (+EV carries RISK, not arb)
    edge_direction   TEXT,                 -- buy_yes | no_edge
    confidence_tier  TEXT NOT NULL,        -- excluded | low | medium | high
    reasons          TEXT,                 -- JSON list of tier reasons
    depth_usd        REAL,
    freshness_hours  REAL,
    match_method     TEXT,
    match_confidence REAL,
    -- settle-later: filled from the 90' score after kickoff.
    home_goals       INTEGER,
    away_goals       INTEGER,
    outcome          INTEGER,              -- 0=H,1=D,2=A (the actual result)
    outcome_hit      INTEGER,              -- 1 iff the bought YES resolved true
    settled_at       TEXT,
    PRIMARY KEY (match_date, fixture_id, outcome_spec)
)
"""

# Which 90' outcome makes each YES share resolve TRUE.
_SPEC_WINS_ON = {"HOME_WIN": 0, "DRAW": 1, "AWAY_WIN": 2}


def ensure_polymarket_gaps_table(db_path: str) -> None:
    """Create the polymarket_gaps table if missing. Idempotent."""
    with open_db(db_path) as conn:
        conn.execute(POLYMARKET_GAPS_SCHEMA)


def _as_dict(gap: object) -> dict:
    if isinstance(gap, dict):
        return gap
    # a polymarket_gap.Gap dataclass
    return {
        "fixture_id": gap.fixture_id, "league": gap.league,
        "home_team": gap.home_team, "away_team": gap.away_team,
        "match_date": gap.match_date, "kickoff_utc": gap.kickoff_utc,
        "series_slug": gap.series_slug, "event_slug": gap.event_slug,
        "yes_token": gap.yes_token, "outcome_spec": gap.outcome_spec,
        "q_fair": gap.q_fair, "poly_ask": gap.poly_ask, "poly_mid": gap.poly_mid,
        "ev": gap.ev, "edge_direction": gap.edge_direction,
        "confidence_tier": gap.confidence_tier, "reasons": gap.reasons,
        "depth_usd": gap.depth_usd, "freshness_hours": gap.freshness_hours,
        "match_method": gap.match_method, "match_confidence": gap.match_confidence,
    }


def record_polymarket_gap(
    db_path: str, gap: object, *, recorded_at: dt.datetime | None = None
) -> None:
    """Upsert one detected gap (a polymarket_gap.Gap or an equivalent dict).

    Idempotent on (match_date, fixture_id, outcome_spec): re-logging refreshes
    the price/EV/tier columns (prices move) but leaves a filled outcome intact.
    """
    g = _as_dict(gap)
    ts = (recorded_at or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
    reasons = g.get("reasons")
    reasons_json = json.dumps(reasons, ensure_ascii=False) if reasons is not None else None
    with open_db(db_path) as conn:
        conn.execute(POLYMARKET_GAPS_SCHEMA)
        conn.execute(
            """
            INSERT INTO polymarket_gaps (
                match_date, fixture_id, outcome_spec, recorded_at, league,
                home_team, away_team, kickoff_utc, series_slug, event_slug,
                yes_token, q_fair, poly_ask, poly_mid, ev, edge_direction,
                confidence_tier, reasons, depth_usd, freshness_hours,
                match_method, match_confidence
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(match_date, fixture_id, outcome_spec) DO UPDATE SET
                recorded_at = excluded.recorded_at,
                league = excluded.league,
                home_team = excluded.home_team,
                away_team = excluded.away_team,
                kickoff_utc = excluded.kickoff_utc,
                series_slug = excluded.series_slug,
                event_slug = excluded.event_slug,
                yes_token = excluded.yes_token,
                q_fair = excluded.q_fair,
                poly_ask = excluded.poly_ask,
                poly_mid = excluded.poly_mid,
                ev = excluded.ev,
                edge_direction = excluded.edge_direction,
                confidence_tier = excluded.confidence_tier,
                reasons = excluded.reasons,
                depth_usd = excluded.depth_usd,
                freshness_hours = excluded.freshness_hours,
                match_method = excluded.match_method,
                match_confidence = excluded.match_confidence
            """,
            (
                str(g["match_date"]), int(g["fixture_id"]), g["outcome_spec"], ts,
                g.get("league"), g.get("home_team"), g.get("away_team"),
                g.get("kickoff_utc"), g.get("series_slug"), g.get("event_slug"),
                g.get("yes_token"), float(g["q_fair"]), float(g["poly_ask"]),
                g.get("poly_mid"), float(g["ev"]), g.get("edge_direction"),
                g["confidence_tier"], reasons_json, g.get("depth_usd"),
                g.get("freshness_hours"), g.get("match_method"),
                g.get("match_confidence"),
            ),
        )


def fetch_polymarket_gaps(db_path: str, *, settled_only: bool = False) -> list[dict]:
    """Return all polymarket_gaps rows as dicts (newest match first)."""
    with open_db(db_path) as conn:
        conn.execute(POLYMARKET_GAPS_SCHEMA)
        where = "WHERE outcome IS NOT NULL" if settled_only else ""
        cur = conn.execute(
            f"SELECT * FROM polymarket_gaps {where} "
            "ORDER BY match_date DESC, ev DESC"
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def settle_polymarket_gaps(
    db_path: str,
    *,
    fetch_fixtures: Callable[[dt.date], list[dict]] | None = None,
    today: dt.date | None = None,
) -> int:
    """Fill the outcome columns for unsettled, kicked-off gaps from the 90' score.

    Groups unsettled rows by match_date, fetches that day's fixtures once, indexes
    by fixture_id, and writes (home_goals, away_goals, outcome, outcome_hit).
    ``outcome_hit`` = 1 iff the bought YES of that outcome_spec resolved true.
    ``fetch_fixtures(date) -> list[fixture]`` is injectable for tests.
    Returns the number of rows newly settled.
    """
    if fetch_fixtures is None:
        from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_date

        def fetch_fixtures(d: dt.date) -> list[dict]:  # type: ignore[misc]
            return fetch_fixtures_for_date(d, refresh=True)

    today = today or dt.datetime.now(dt.UTC).date()
    settled = 0
    with open_db(db_path) as conn:
        conn.execute(POLYMARKET_GAPS_SCHEMA)
        cur = conn.execute(
            "SELECT match_date, fixture_id, outcome_spec FROM polymarket_gaps "
            "WHERE outcome IS NULL"
        )
        unsettled = cur.fetchall()
        groups: dict[str, list[tuple[int, str]]] = {}
        for md, fid, spec in unsettled:
            try:
                d = dt.date.fromisoformat(md)
            except (ValueError, TypeError):
                continue
            if d > today:
                continue
            groups.setdefault(md, []).append((fid, spec))

        ts = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        for md, items in groups.items():
            try:
                fixtures = fetch_fixtures(dt.date.fromisoformat(md))
            except Exception as exc:  # noqa: BLE001
                log.warning("polymarket settle: fetch failed for %s: %s", md, exc)
                continue
            by_id: dict[int, dict] = {}
            for fx in fixtures:
                fid = (fx.get("fixture") or {}).get("id")
                if fid is not None:
                    by_id[int(fid)] = fx
            for fid, spec in items:
                fx = by_id.get(int(fid))
                if fx is None:
                    continue
                res = _ft_outcome(fx)
                if res is None:
                    continue
                hg, ag, outcome = res
                hit = 1 if _SPEC_WINS_ON.get(spec) == outcome else 0
                upd = conn.execute(
                    "UPDATE polymarket_gaps SET home_goals=?, away_goals=?, "
                    "outcome=?, outcome_hit=?, settled_at=? "
                    "WHERE match_date=? AND fixture_id=? AND outcome_spec=? "
                    "AND outcome IS NULL",
                    (hg, ag, outcome, hit, ts, md, fid, spec),
                )
                settled += max(0, upd.rowcount)
    return settled
