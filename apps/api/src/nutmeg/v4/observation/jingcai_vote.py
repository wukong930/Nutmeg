"""竞彩 散户投票/支持比例 capture — the retail-sentiment half of the bias map.

体彩 officially publishes, per match, the three-way 支持比例 (retail support %, by
ticket volume) via the no-auth ``getVoteV1`` endpoint on the same gateway as the SP
feed. This is GENUINE Chinese-retail crowd direction — NOT 唯彩/Okooo's「买量」which
is 必发(Betfair)-exchange-derived (= global sharp money). The endpoint is
FORWARD-ONLY (matchId/date params ignored → current day only; no backfill), so we
capture DAILY and accumulate. Joined later to Pinnacle de-vig P + the result, this
measures "where retail leans heavy AND 竞彩 deviates from sharp" — the autumn
soft-water / retail-bias question. (记忆 jingcai-vote-support-endpoint.)

Upsert-latest keyed (match_date, home_zh, away_zh, pool_code): a re-capture nearer
kickoff overwrites with the latest crowd snapshot; settle-later result columns are
never clobbered. NEVER raises — a lost observation must not break the capture cron.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS jingcai_vote (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at  TEXT NOT NULL,            -- when WE pulled the 支持比例 (UTC ISO)
    source       TEXT NOT NULL DEFAULT 'sporttery',
    match_date   TEXT NOT NULL,
    match_num    TEXT,                     -- 竞彩 编号 (周一001)
    league_cn    TEXT,
    home_zh      TEXT NOT NULL,            -- 竞彩 中文队名 (always present)
    away_zh      TEXT NOT NULL,
    home_team    TEXT,                     -- canonical EN (NULL if unmapped — keep the row anyway)
    away_team    TEXT,
    pool_code    TEXT NOT NULL,            -- HAD(胜平负) | HHAD/HDC(让球)
    handicap_home INTEGER,                 -- 让球线 (NULL for HAD)
    -- retail support % (ticket-volume share, sums ~100) — THE signal
    h_support    REAL, d_support REAL, a_support REAL,
    -- raw vote counts (win/draw/lose)
    h_count      INTEGER, d_count INTEGER, a_count INTEGER,
    -- 体彩 own de-vig implied % + its own bias calc (support − implied); cross-check only
    h_prob       REAL, d_prob REAL, a_prob REAL,
    h_err        REAL, d_err REAL, a_err REAL,
    -- 竞彩 SP odds at capture (vs Pinnacle de-vig at analysis time)
    jc_home      REAL, jc_draw REAL, jc_away REAL,
    -- Pinnacle 1X2 closing, co-captured from odds_snapshots at freeze → locks the 软水 三料 join
    psc_home     REAL, psc_draw REAL, psc_away REAL, ou_line REAL,
    -- settle-later (filled by settle_jingcai_vote; never clobbered on re-capture)
    home_goals   INTEGER, away_goals INTEGER, ft_outcome INTEGER, settled_at TEXT,
    UNIQUE(match_date, home_zh, away_zh, pool_code)
);
CREATE INDEX IF NOT EXISTS idx_jingcai_vote_unsettled
    ON jingcai_vote (settled_at, match_date);
"""


def ensure_jingcai_vote_table(conn: sqlite3.Connection) -> None:
    """Idempotent DDL — safe to call on every write. Forward-migrates the
    co-captured Pinnacle columns onto a pre-existing table."""
    conn.executescript(_DDL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(jingcai_vote)")}
    for col in ("psc_home", "psc_draw", "psc_away", "ou_line"):
        if col not in have:
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(f"ALTER TABLE jingcai_vote ADD COLUMN {col} REAL")


def _pct(v) -> float | None:
    """'17%' / '-8%' / 17 → float; None/'' → None."""
    if v is None or v == "":
        return None
    try:
        return float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _flt(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def parse_vote_row(raw: dict, pool_code: str) -> dict | None:
    """Map one sporttery ``getVoteV1`` match row → ``record_jingcai_vote`` kwargs,
    or None if it lacks team names / a support triple. Imports zh_to_canonical
    lazily (keeps this module import-light for tests)."""
    from nutmeg.v4.data.sources.sporttery import zh_to_canonical

    md = raw.get("matchDate") or raw.get("businessDate")
    hz = (raw.get("homeTeamAllName") or raw.get("homeTeamAbbName") or "").strip()
    az = (raw.get("awayTeamAllName") or raw.get("awayTeamAbbName") or "").strip()
    if not (md and hz and az):
        return None
    hs, ds, asp = (_pct(raw.get("hsupportRate")), _pct(raw.get("dsupportRate")),
                   _pct(raw.get("asupportRate")))
    if hs is None and ds is None and asp is None:
        return None  # no support data on this row
    return {
        "match_date": str(md)[:10],
        "match_num": raw.get("matchNum"),
        "league_cn": raw.get("leagueAllName") or raw.get("leagueAbbName"),
        "home_zh": hz, "away_zh": az,
        "home_team": zh_to_canonical(hz), "away_team": zh_to_canonical(az),
        "pool_code": pool_code.upper(),
        "handicap_home": _int(raw.get("goalLine")),
        "h_support": hs, "d_support": ds, "a_support": asp,
        "h_count": _int(raw.get("win")), "d_count": _int(raw.get("draw")),
        "a_count": _int(raw.get("lose")),
        "h_prob": _pct(raw.get("hprobability")), "d_prob": _pct(raw.get("dprobability")),
        "a_prob": _pct(raw.get("aprobability")),
        "h_err": _pct(raw.get("herror")), "d_err": _pct(raw.get("derror")),
        "a_err": _pct(raw.get("aerror")),
        "jc_home": _flt(raw.get("h")), "jc_draw": _flt(raw.get("d")),
        "jc_away": _flt(raw.get("a")),
    }


def record_jingcai_vote(
    db_path: str | Path,
    *,
    match_date: str,
    home_zh: str,
    away_zh: str,
    pool_code: str,
    home_team: str | None = None,
    away_team: str | None = None,
    match_num: str | None = None,
    league_cn: str | None = None,
    handicap_home: int | None = None,
    h_support: float | None = None,
    d_support: float | None = None,
    a_support: float | None = None,
    h_count: int | None = None,
    d_count: int | None = None,
    a_count: int | None = None,
    h_prob: float | None = None,
    d_prob: float | None = None,
    a_prob: float | None = None,
    h_err: float | None = None,
    d_err: float | None = None,
    a_err: float | None = None,
    jc_home: float | None = None,
    jc_draw: float | None = None,
    jc_away: float | None = None,
    source: str = "sporttery",
) -> bool:
    """Upsert ONE 支持比例 snapshot for (match_date, home_zh, away_zh, pool_code).
    A re-capture overwrites the latest crowd numbers but preserves any settle-later
    result. Returns False (no-op) if keys/support are absent, or on ANY internal
    failure (logged, never raised)."""
    try:
        if not (match_date and home_zh and away_zh and pool_code):
            return False
        if h_support is None and d_support is None and a_support is None:
            return False
        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_jingcai_vote_table(conn)
            conn.execute(
                "INSERT INTO jingcai_vote (captured_at, source, match_date, match_num, "
                "league_cn, home_zh, away_zh, home_team, away_team, pool_code, handicap_home, "
                "h_support, d_support, a_support, h_count, d_count, a_count, "
                "h_prob, d_prob, a_prob, h_err, d_err, a_err, jc_home, jc_draw, jc_away) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(match_date, home_zh, away_zh, pool_code) DO UPDATE SET "
                "captured_at=excluded.captured_at, source=excluded.source, "
                "match_num=COALESCE(excluded.match_num, jingcai_vote.match_num), "
                "league_cn=COALESCE(excluded.league_cn, jingcai_vote.league_cn), "
                "home_team=COALESCE(excluded.home_team, jingcai_vote.home_team), "
                "away_team=COALESCE(excluded.away_team, jingcai_vote.away_team), "
                "handicap_home=excluded.handicap_home, "
                "h_support=excluded.h_support, d_support=excluded.d_support, "
                "a_support=excluded.a_support, h_count=excluded.h_count, "
                "d_count=excluded.d_count, a_count=excluded.a_count, "
                "h_prob=excluded.h_prob, d_prob=excluded.d_prob, a_prob=excluded.a_prob, "
                "h_err=excluded.h_err, d_err=excluded.d_err, a_err=excluded.a_err, "
                "jc_home=excluded.jc_home, jc_draw=excluded.jc_draw, jc_away=excluded.jc_away",
                (
                    now, source, match_date, match_num, league_cn, home_zh, away_zh,
                    home_team, away_team, pool_code.upper(),
                    int(handicap_home) if handicap_home is not None else None,
                    h_support, d_support, a_support, h_count, d_count, a_count,
                    h_prob, d_prob, a_prob, h_err, d_err, a_err,
                    jc_home, jc_draw, jc_away,
                ),
            )
        return True
    except Exception:  # noqa: BLE001 — a lost observation must never break the capture
        log.warning("jingcai_vote capture failed for %s vs %s (db=%s)",
                    home_zh, away_zh, db_path, exc_info=True)
        return False


def fetch_jingcai_vote(db_path: str | Path) -> list[dict]:
    """All 支持比例 rows as dicts (analysis-side reader). Best-effort: [] on failure."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            ensure_jingcai_vote_table(conn)
            return [dict(r) for r in conn.execute(
                "SELECT * FROM jingcai_vote ORDER BY match_date, home_zh").fetchall()]
    except sqlite3.Error:
        log.warning("fetch_jingcai_vote failed", exc_info=True)
        return []


def backfill_vote_pinnacle(db_path: str | Path) -> int:
    """Co-locate the Pinnacle 1X2 line onto each jingcai_vote row by pulling the
    latest snapshot from ``odds_snapshots`` (the automated Pinnacle line-history).

    This LOCKS the soft-water three-way (散户支持 + 竞彩 SP + Pinnacle) into a single
    table at freeze time, so Q② is a single-table query going forward and never
    depends on re-deriving the comparison anchor later. Matched on canonical EN team
    names with a ±1-day window — jingcai_vote uses the 竞彩 Beijing selling-date but
    odds_snapshots the UTC fixture-date, so they differ by the timezone (e.g.
    France-Sweden = vote 07-01 vs snapshot 06-30); a (date,teams) join would silently
    drop everything. Takes the LATEST snapshot (closest to 竞彩 freeze), updates each
    run (the final pre-freeze capture pins the freshest line). Fail-soft; returns the
    number of rows filled."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_jingcai_vote_table(conn)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, match_date, home_team, away_team FROM jingcai_vote "
                "WHERE home_team IS NOT NULL AND away_team IS NOT NULL").fetchall()
            filled = 0
            for r in rows:
                try:
                    d0 = dt.date.fromisoformat(str(r["match_date"])[:10])
                except ValueError:
                    continue
                lo = (d0 - dt.timedelta(days=1)).isoformat()
                hi = (d0 + dt.timedelta(days=1)).isoformat()
                pin = conn.execute(
                    "SELECT psc_home, psc_draw, psc_away, ou_line FROM odds_snapshots "
                    "WHERE home_team = ? AND away_team = ? AND psc_home > 1 AND psc_draw > 1 "
                    "AND psc_away > 1 AND substr(match_date, 1, 10) BETWEEN ? AND ? "
                    "ORDER BY captured_at DESC LIMIT 1",
                    (r["home_team"], r["away_team"], lo, hi)).fetchone()
                if pin:
                    conn.execute(
                        "UPDATE jingcai_vote SET psc_home=?, psc_draw=?, psc_away=?, "
                        "ou_line=? WHERE id=?",
                        (pin["psc_home"], pin["psc_draw"], pin["psc_away"],
                         pin["ou_line"], r["id"]))
                    filled += 1
            return filled
    except Exception:  # noqa: BLE001 — co-capture is best-effort, never break the capture
        log.warning("backfill_vote_pinnacle failed (db=%s)", db_path, exc_info=True)
        return 0
