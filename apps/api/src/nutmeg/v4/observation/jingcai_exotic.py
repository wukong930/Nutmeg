"""竞彩冷门玩法 SP — 比分(crs) + 总进球(ttg),长格式(一行一个结果).

The literature points to exotics as where soft books are *softest* (heavy public
bias on popular scorelines, higher variance). We forward-capture the frozen 竞彩 SP
for every offered outcome so the EV-vs-Pinnacle test — P read off our existing DC
score grid (比分 = a cell, 总进球 = a diagonal sum) — can run come autumn. See
``docs/parlay_soft_water_research.md`` §7. 半全场 is deferred (needs a half-time
model; Pinnacle prices 1st-half only for top leagues — measured 2026-06-23).

This layer is CAPTURE + SETTLE only — EV is NOT computed here (autumn). Long-format
because 比分 has 31 outcomes / 总进球 8, which won't fit the 3-column jingcai_sp.
Fail-soft: a lost observation never raises.
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS jingcai_exotic_sp (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at  TEXT NOT NULL,
    source       TEXT NOT NULL,
    league       TEXT,
    match_date   TEXT NOT NULL,
    home_team    TEXT NOT NULL,
    away_team    TEXT NOT NULL,
    kickoff_utc  TEXT,
    market       TEXT NOT NULL,          -- crs(比分) | ttg(总进球)
    outcome      TEXT NOT NULL,          -- '2:1' / '胜其他' / '3'(总进球) ...
    jc_sp        REAL NOT NULL,
    -- settle-later (filled by settle_exotic_sp; never clobbered on re-capture)
    home_goals   INTEGER, away_goals INTEGER, hit INTEGER, settled_at TEXT,
    UNIQUE(match_date, home_team, away_team, market, outcome)
);
CREATE INDEX IF NOT EXISTS idx_jingcai_exotic_unsettled
    ON jingcai_exotic_sp (settled_at, match_date);
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)


def record_exotic_sp(
    db_path: str | Path, *, match_date: str, home_team: str, away_team: str,
    market: str, outcomes: dict[str, float], league: str | None = None,
    kickoff_utc: str | None = None, source: str = "sporttery",
) -> int:
    """Upsert one row per (match, market, outcome). Latest SP overwrites (canonical
    = nearest-freeze); the settle-later result is preserved. Returns rows written;
    0 on no-op / any internal failure (logged, never raised)."""
    if not (match_date and home_team and away_team and outcomes):
        return 0
    try:
        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        n = 0
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_table(conn)
            for outcome, sp in outcomes.items():
                try:
                    sp_f = float(sp)
                except (TypeError, ValueError):
                    continue
                conn.execute(
                    "INSERT INTO jingcai_exotic_sp (captured_at, source, league, "
                    "match_date, home_team, away_team, kickoff_utc, market, outcome, "
                    "jc_sp) VALUES (?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(match_date, home_team, away_team, market, outcome) "
                    "DO UPDATE SET captured_at=excluded.captured_at, "
                    "source=excluded.source, jc_sp=excluded.jc_sp, "
                    "kickoff_utc=COALESCE(excluded.kickoff_utc, jingcai_exotic_sp.kickoff_utc), "
                    "league=COALESCE(excluded.league, jingcai_exotic_sp.league)",
                    (now, source, league, match_date, home_team, away_team,
                     kickoff_utc, market, str(outcome), sp_f),
                )
                n += 1
        return n
    except Exception:  # noqa: BLE001 — a lost observation must never break the pipeline
        log.warning("exotic SP capture failed for %s vs %s (db=%s)",
                    home_team, away_team, db_path, exc_info=True)
        return 0


def crs_winning_outcome(hg: int, ag: int, offered: set[str]) -> str:
    """比分 winner: the exact 'H:A' if 竞彩 offered it, else the 胜/平/负其他 bucket
    by result sign (高比分超出网格时归入其他)."""
    s = f"{int(hg)}:{int(ag)}"
    if s in offered:
        return s
    return "胜其他" if hg > ag else "平其他" if hg == ag else "负其他"


def ttg_winning_outcome(hg: int, ag: int) -> str:
    """总进球 winner; 7 或更多 collapse to '7'."""
    return str(min(int(hg) + int(ag), 7))


def settle_exotic_sp(
    db_path: str | Path, *, fetch_fixtures=None, today: dt.date | None = None,
) -> int:
    """Fill the result for unsettled exotic rows whose match_date is today-or-past.
    Mirrors ``settle_jingcai_sp``: pull the day's fixtures, match by normalized team
    name, then per market mark the winning outcome ``hit=1`` and the rest ``hit=0``.
    Returns the number of rows newly settled."""
    from nutmeg.utils.team_canonical import normalize_name
    from nutmeg.v4.observation.prediction_log import _ft_outcome

    if fetch_fixtures is None:
        from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_date

        def fetch_fixtures(d: dt.date) -> list[dict]:  # type: ignore[misc]
            return fetch_fixtures_for_date(d, refresh=True)

    today = today or dt.datetime.now(dt.UTC).date()
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        ensure_table(conn)
        rows = conn.execute(
            "SELECT id, match_date, home_team, away_team, market, outcome "
            "FROM jingcai_exotic_sp WHERE settled_at IS NULL ORDER BY match_date"
        ).fetchall()
        if not rows:
            return 0
        by_match: dict[tuple[str, str, str], list[sqlite3.Row]] = defaultdict(list)
        for r in rows:
            try:
                d = dt.date.fromisoformat(r["match_date"])
            except ValueError:
                continue
            if d > today:  # not kicked off yet
                continue
            by_match[(r["match_date"], r["home_team"], r["away_team"])].append(r)

        # fetch each needed day's fixtures once → normalized index
        idx: dict[tuple[str, str, str], dict] = {}
        for date_str in {k[0] for k in by_match}:
            try:
                fixtures = fetch_fixtures(dt.date.fromisoformat(date_str)) or []
            except Exception:  # noqa: BLE001 — one bad day must not abort the rest
                log.warning("settle_exotic: fetch failed for %s", date_str, exc_info=True)
                continue
            for fx in fixtures:
                teams = fx.get("teams") or {}
                h = normalize_name((teams.get("home") or {}).get("name", ""))
                a = normalize_name((teams.get("away") or {}).get("name", ""))
                if h and a:
                    idx[(date_str, h, a)] = fx

        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        settled = 0
        for (md, home, away), grp in by_match.items():
            fx = idx.get((md, normalize_name(home), normalize_name(away)))
            if not fx:
                continue
            res = _ft_outcome(fx)
            if res is None:
                continue
            hg, ag, _ = res
            crs_offered = {r["outcome"] for r in grp
                           if r["market"] == "crs" and ":" in r["outcome"]}
            win = {"crs": crs_winning_outcome(hg, ag, crs_offered),
                   "ttg": ttg_winning_outcome(hg, ag)}
            for r in grp:
                w = win.get(r["market"])
                if w is None:
                    continue
                conn.execute(
                    "UPDATE jingcai_exotic_sp SET home_goals=?, away_goals=?, hit=?, "
                    "settled_at=? WHERE id=?",
                    (hg, ag, 1 if r["outcome"] == w else 0, now, r["id"]))
                settled += 1
    return settled
