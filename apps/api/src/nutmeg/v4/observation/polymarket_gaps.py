"""Polymarket mispricing-gap log (READ-ONLY measurement, NO betting).

Persists detected gaps over time so we can answer, weeks later, the only honest
question about this experiment: **were the high-confidence gaps actually real,
and did the favorite-flip guard remove the losers?** Each row stores our fair
``q``, the Polymarket ask, the EV, the confidence tier + reasons, and (filled
after kickoff) whether the bought YES would have resolved true — so a report can
score realized hit-rate by tier.

Covers 胜平负 (HOME_WIN/DRAW/AWAY_WIN), 让球 (HANDICAP_HOME/AWAY + line) and 大小球
(OVER/UNDER + line) — one row per (match, spec, line). ``line`` is stored NOT
NULL with a ``_NO_LINE`` sentinel for moneyline so it can sit in the primary key
(SQLite treats NULLs as distinct, which would break the upsert dedup).

Design mirrors observation/prediction_log.py (denormalized, idempotent,
cron-friendly). NOTHING here places an order — it only records what was observed.
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

# Moneyline has no line; a NOT NULL sentinel lets `line` live in the PK (a NULL in
# a PK column is treated as distinct by SQLite → the upsert would never dedup).
# Real lines are half-integers within ±8.5, so -100.0 can never collide.
_NO_LINE = -100.0

POLYMARKET_GAPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS polymarket_gaps (
    match_date       TEXT NOT NULL,
    fixture_id       INTEGER NOT NULL,
    outcome_spec     TEXT NOT NULL,        -- 胜平负 | HANDICAP_HOME/AWAY | OVER | UNDER
    line             REAL NOT NULL DEFAULT -100.0,  -- 让球/大小球 line; -100 = moneyline
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
    PRIMARY KEY (match_date, fixture_id, outcome_spec, line)
)
"""


def _yes_resolves(spec: str, line: float | None, hg: int, ag: int) -> int | None:
    """1 iff the bought YES of ``spec`` (at ``line``) resolves true given the 90'
    score, 0 if it loses, None for an unknown spec. Half-lines ⇒ no push."""
    margin = hg - ag
    total = hg + ag
    if spec == "HOME_WIN":
        return 1 if margin > 0 else 0
    if spec == "DRAW":
        return 1 if margin == 0 else 0
    if spec == "AWAY_WIN":
        return 1 if margin < 0 else 0
    if line is None:
        return None
    if spec == "HANDICAP_HOME":
        return 1 if margin + line > 0 else 0   # home covers `line`
    if spec == "HANDICAP_AWAY":
        return 1 if -margin + line > 0 else 0   # away covers `line`
    if spec == "OVER":
        return 1 if total > line else 0
    if spec == "UNDER":
        return 1 if total < line else 0
    return None


def ensure_polymarket_gaps_table(db_path: str) -> None:
    """Create the table if missing; migrate the pre-让球 schema (no ``line`` column,
    3-col PK) in place, preserving existing moneyline rows (line ← sentinel).
    Idempotent."""
    with open_db(db_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(polymarket_gaps)")]
        if not cols:
            conn.execute(POLYMARKET_GAPS_SCHEMA)
            return
        if "line" in cols:
            return
        # Old schema → rebuild with `line` + 4-col PK, carrying rows over.
        old_cols = ", ".join(cols)
        conn.executescript(
            "BEGIN;"
            "ALTER TABLE polymarket_gaps RENAME TO _polymarket_gaps_old;"
            + POLYMARKET_GAPS_SCHEMA + ";"
            + f"INSERT INTO polymarket_gaps ({old_cols}, line) "
              f"SELECT {old_cols}, {_NO_LINE} FROM _polymarket_gaps_old;"
              "DROP TABLE _polymarket_gaps_old;"
              "COMMIT;"
        )
        log.info("polymarket_gaps migrated to line-aware schema (%d cols carried)", len(cols))


def _as_dict(gap: object) -> dict:
    if isinstance(gap, dict):
        return gap
    return {
        "fixture_id": gap.fixture_id, "league": gap.league,
        "home_team": gap.home_team, "away_team": gap.away_team,
        "match_date": gap.match_date, "kickoff_utc": gap.kickoff_utc,
        "series_slug": gap.series_slug, "event_slug": gap.event_slug,
        "yes_token": gap.yes_token, "outcome_spec": gap.outcome_spec,
        "line": gap.line, "q_fair": gap.q_fair, "poly_ask": gap.poly_ask,
        "poly_mid": gap.poly_mid, "ev": gap.ev, "edge_direction": gap.edge_direction,
        "confidence_tier": gap.confidence_tier, "reasons": gap.reasons,
        "depth_usd": gap.depth_usd, "freshness_hours": gap.freshness_hours,
        "match_method": gap.match_method, "match_confidence": gap.match_confidence,
    }


def record_polymarket_gap(
    db_path: str, gap: object, *, recorded_at: dt.datetime | None = None
) -> None:
    """Upsert one detected gap (a polymarket_gap.Gap or an equivalent dict).

    Idempotent on (match_date, fixture_id, outcome_spec, line): re-logging refreshes
    the price/EV/tier columns (prices move) but leaves a filled outcome intact.
    """
    g = _as_dict(gap)
    ts = (recorded_at or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
    reasons = g.get("reasons")
    reasons_json = json.dumps(reasons, ensure_ascii=False) if reasons is not None else None
    line = float(g["line"]) if g.get("line") is not None else _NO_LINE
    ensure_polymarket_gaps_table(db_path)  # own connection (migration-aware); never nest
    with open_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO polymarket_gaps (
                match_date, fixture_id, outcome_spec, line, recorded_at, league,
                home_team, away_team, kickoff_utc, series_slug, event_slug,
                yes_token, q_fair, poly_ask, poly_mid, ev, edge_direction,
                confidence_tier, reasons, depth_usd, freshness_hours,
                match_method, match_confidence
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(match_date, fixture_id, outcome_spec, line) DO UPDATE SET
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
                str(g["match_date"]), int(g["fixture_id"]), g["outcome_spec"], line, ts,
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
    """Return all polymarket_gaps rows as dicts (newest match first). The moneyline
    ``line`` sentinel is surfaced as None."""
    ensure_polymarket_gaps_table(db_path)
    with open_db(db_path) as conn:
        where = "WHERE outcome IS NOT NULL" if settled_only else ""
        cur = conn.execute(
            f"SELECT * FROM polymarket_gaps {where} "
            "ORDER BY match_date DESC, ev DESC"
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    for r in rows:
        if r.get("line") == _NO_LINE:
            r["line"] = None
    return rows


def settle_polymarket_gaps(
    db_path: str,
    *,
    fetch_fixtures: Callable[[dt.date], list[dict]] | None = None,
    today: dt.date | None = None,
) -> int:
    """Fill the outcome columns for unsettled, kicked-off gaps from the 90' score.

    Groups unsettled rows by match_date, fetches that day's fixtures once, indexes
    by fixture_id, and writes (home_goals, away_goals, outcome, outcome_hit).
    ``outcome_hit`` = 1 iff the bought YES of that (spec, line) resolved true.
    ``fetch_fixtures(date) -> list[fixture]`` is injectable for tests.
    Returns the number of rows newly settled.
    """
    if fetch_fixtures is None:
        from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_date

        def fetch_fixtures(d: dt.date) -> list[dict]:  # type: ignore[misc]
            return fetch_fixtures_for_date(d, refresh=True)

    today = today or dt.datetime.now(dt.UTC).date()
    ensure_polymarket_gaps_table(db_path)
    settled = 0
    with open_db(db_path) as conn:
        cur = conn.execute(
            "SELECT match_date, fixture_id, outcome_spec, line FROM polymarket_gaps "
            "WHERE outcome IS NULL"
        )
        unsettled = cur.fetchall()
        groups: dict[str, list[tuple[int, str, float]]] = {}
        for md, fid, spec, line in unsettled:
            try:
                d = dt.date.fromisoformat(md)
            except (ValueError, TypeError):
                continue
            if d > today:
                continue
            groups.setdefault(md, []).append((fid, spec, line))

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
            for fid, spec, line in items:
                fx = by_id.get(int(fid))
                if fx is None:
                    continue
                res = _ft_outcome(fx)
                if res is None:
                    continue
                hg, ag, outcome = res
                real_line = None if line == _NO_LINE else line
                hit = _yes_resolves(spec, real_line, hg, ag)
                if hit is None:
                    continue
                upd = conn.execute(
                    "UPDATE polymarket_gaps SET home_goals=?, away_goals=?, "
                    "outcome=?, outcome_hit=?, settled_at=? "
                    "WHERE match_date=? AND fixture_id=? AND outcome_spec=? AND line=? "
                    "AND outcome IS NULL",
                    (hg, ag, outcome, hit, ts, md, fid, spec, line),
                )
                settled += max(0, upd.rowcount)
    return settled
