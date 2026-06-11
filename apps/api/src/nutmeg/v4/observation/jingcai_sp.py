"""竞彩 SP staleness observations — the soft-book half of the edge map.

Why: EV = P(true) × 竞彩SP − 1, and the only place edge can live is where 竞彩's
FROZEN SP (the lottery stops updating ~23:00 daily) drifts from Pinnacle's LIVE
fair as news/money keep moving the sharp line to kickoff. ``odds_snapshots``
already captures the Pinnacle trajectory (open→close); this table captures the
OTHER half — the 竞彩 SP the user prices a match at — so the gap (and whether
betting it actually wins) can be measured on the right axis.

Capture is SILENT and UPSERT-LATEST keyed on (match_date, home, away, market):
the user re-prices a match many times before kickoff to verify, so each capture
OVERWRITES — the table always holds the canonical (latest = nearest-kickoff) 竞彩
line, auto-solving the "填很多次" duplication. Settle-later columns hold the
result and are NEVER clobbered by a re-capture. NEVER raises out of the capture
path: a lost observation must not break the user's live EV view.
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS jingcai_sp (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at  TEXT NOT NULL,          -- when WE logged the 竞彩 SP (UTC ISO)
    source       TEXT NOT NULL,          -- market_mode | manual | ...
    fixture_id   INTEGER,
    league       TEXT,
    match_date   TEXT NOT NULL,
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    kickoff_utc  TEXT,
    market       TEXT NOT NULL DEFAULT 'had',   -- had(1X2) | hhad(让球) | ttg ...
    handicap_home INTEGER,   -- 竞彩 让球线 (DC: −1=主队让1球); NULL for 'had'
    -- 竞彩 SP (the frozen lottery line the user is pricing against)
    jc_home      REAL, jc_draw REAL, jc_away REAL,
    -- Pinnacle raw at capture time (vig included) — 竞彩 vs Pinnacle-at-capture
    psc_home     REAL, psc_draw REAL, psc_away REAL,
    ou_line      REAL,
    -- settle-later (filled by settle_jingcai_sp; never clobbered on re-capture)
    home_goals   INTEGER, away_goals INTEGER, ft_outcome INTEGER, settled_at TEXT,
    UNIQUE(match_date, home_team, away_team, market)
);
CREATE INDEX IF NOT EXISTS idx_jingcai_sp_unsettled
    ON jingcai_sp (settled_at, match_date);
"""


def ensure_jingcai_sp_table(conn: sqlite3.Connection) -> None:
    """Idempotent DDL — safe to call on every write. Includes a forward
    migration: a table created before 让球 support lacks handicap_home, and
    CREATE TABLE IF NOT EXISTS won't add it."""
    conn.executescript(_DDL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jingcai_sp)")}
    if "handicap_home" not in cols:
        conn.execute("ALTER TABLE jingcai_sp ADD COLUMN handicap_home INTEGER")


def record_jingcai_sp(
    db_path: str | Path,
    *,
    match_date: str,
    home_team: str,
    away_team: str,
    jc_home: float | None = None,
    jc_draw: float | None = None,
    jc_away: float | None = None,
    psc_home: float | None = None,
    psc_draw: float | None = None,
    psc_away: float | None = None,
    ou_line: float | None = None,
    fixture_id: int | None = None,
    league: str | None = None,
    kickoff_utc: str | None = None,
    market: str = "had",
    handicap_home: int | None = None,
    source: str = "market_mode",
) -> bool:
    """Upsert ONE canonical 竞彩 SP observation for (match_date, home, away,
    market). A re-capture overwrites the line (latest = canonical) but preserves
    any settle-later result. Requires the 竞彩 1X2 triple — returns False (no-op)
    if it is absent, or on ANY internal failure (logged, never raised)."""
    try:
        if jc_home is None or jc_draw is None or jc_away is None:
            return False  # no 竞彩 line to log
        if not (match_date and home_team and away_team):
            return False
        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_jingcai_sp_table(conn)
            conn.execute(
                "INSERT INTO jingcai_sp (captured_at, source, fixture_id, league, "
                "match_date, home_team, away_team, kickoff_utc, market, handicap_home, "
                "jc_home, jc_draw, jc_away, psc_home, psc_draw, psc_away, ou_line) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(match_date, home_team, away_team, market) DO UPDATE SET "
                "captured_at=excluded.captured_at, source=excluded.source, "
                "fixture_id=COALESCE(excluded.fixture_id, jingcai_sp.fixture_id), "
                "league=COALESCE(excluded.league, jingcai_sp.league), "
                "kickoff_utc=COALESCE(excluded.kickoff_utc, jingcai_sp.kickoff_utc), "
                "handicap_home=excluded.handicap_home, "
                "jc_home=excluded.jc_home, jc_draw=excluded.jc_draw, jc_away=excluded.jc_away, "
                "psc_home=excluded.psc_home, psc_draw=excluded.psc_draw, "
                "psc_away=excluded.psc_away, ou_line=excluded.ou_line",
                (
                    now, source, fixture_id, league, match_date, home_team,
                    away_team, kickoff_utc, market,
                    int(handicap_home) if handicap_home is not None else None,
                    float(jc_home), float(jc_draw), float(jc_away),
                    _f(psc_home), _f(psc_draw), _f(psc_away), _f(ou_line),
                ),
            )
        return True
    except Exception:  # noqa: BLE001 — a lost observation must never break the EV view
        log.warning("jingcai_sp capture failed for %s vs %s (db=%s)",
                    home_team, away_team, db_path, exc_info=True)
        return False


def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_jingcai_sp(db_path: str | Path, *, settled: bool | None = None) -> list[dict]:
    """All observations as dicts; ``settled`` filters on result presence."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        ensure_jingcai_sp_table(conn)
        q = "SELECT * FROM jingcai_sp"
        if settled is True:
            q += " WHERE settled_at IS NOT NULL"
        elif settled is False:
            q += " WHERE settled_at IS NULL"
        q += " ORDER BY match_date, home_team"
        return [dict(r) for r in conn.execute(q).fetchall()]


def settle_jingcai_sp(
    db_path: str | Path,
    *,
    fetch_fixtures=None,
    today: dt.date | None = None,
) -> int:
    """Fill results for unsettled observations whose match_date is today-or-past.

    Mirrors ``settle_league_predictions`` but groups by DATE only (竞彩 spans many
    leagues, so we pull the whole day's fixtures and match by team), writing the
    90' FT score + outcome (0 home / 1 draw / 2 away). ``fetch_fixtures(date)``
    takes a ``date`` object and is injectable for tests; the default pulls all of
    that day's API-Football fixtures. Returns the number of rows newly settled."""
    from nutmeg.utils.team_canonical import normalize_name
    from nutmeg.v4.observation.prediction_log import _ft_outcome

    if fetch_fixtures is None:
        from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_date

        def fetch_fixtures(d: dt.date) -> list[dict]:  # type: ignore[misc]
            return fetch_fixtures_for_date(d, refresh=True)

    today = today or dt.datetime.now(dt.UTC).date()
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        ensure_jingcai_sp_table(conn)
        rows = conn.execute(
            "SELECT id, match_date, home_team, away_team FROM jingcai_sp "
            "WHERE settled_at IS NULL ORDER BY match_date").fetchall()
        if not rows:
            return 0
        by_date: dict[str, list[sqlite3.Row]] = {}
        for r in rows:
            try:
                d = dt.date.fromisoformat(r["match_date"])
            except ValueError:
                continue
            if d > today:  # not kicked off yet
                continue
            by_date.setdefault(r["match_date"], []).append(r)

        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        settled = 0
        for date_str, drows in by_date.items():
            try:
                fixtures = fetch_fixtures(dt.date.fromisoformat(date_str)) or []
            except Exception:  # noqa: BLE001 — one bad day must not abort the rest
                log.warning("settle_jingcai_sp: fetch failed for %s", date_str, exc_info=True)
                continue
            index: dict[tuple[str, str], dict] = {}
            for fx in fixtures:
                teams = (fx.get("teams") or {})
                h = normalize_name((teams.get("home") or {}).get("name", ""))
                a = normalize_name((teams.get("away") or {}).get("name", ""))
                if h and a:
                    index[(h, a)] = fx
            for r in drows:
                fx = index.get((normalize_name(r["home_team"]), normalize_name(r["away_team"])))
                if not fx:
                    continue
                res = _ft_outcome(fx)
                if res is None:
                    continue
                hg, ag, outcome = res
                conn.execute(
                    "UPDATE jingcai_sp SET home_goals=?, away_goals=?, ft_outcome=?, "
                    "settled_at=? WHERE id=?", (hg, ag, outcome, now, r["id"]))
                settled += 1
        return settled
