"""500 Crown 历史收盘表 — 免费 Pinnacle 替代(§H CLV / C1 让球修正校准)。

一行一场,存 500 hisdata 的 Crown(皇冠)1X2 收盘 + 让球线 + 让球1X2 市场均 + O/U + 结果 +
best-effort canonical EN 队名(`zh_to_canonical`,500 中文名与 sporttery 略异 → 常 None,
不阻塞;仅供日后跨源 join)。Crown ≈ Pinnacle 收盘(验 N=36 median 0.62pp)。喂 C1 δ 估计
(不需队名,直接读 crown_1x2+rangqiu+结果)。`记忆 500-historical-odds-archive`。FAIL-SOFT。
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from pathlib import Path

from nutmeg.v4.data.sources.sporttery import zh_to_canonical

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS crown_close_history (
    match_id    TEXT PRIMARY KEY,          -- 500 match id
    match_date  TEXT NOT NULL,             -- 竞彩投注日 (matchnumdate, 北京)
    league_cn   TEXT,
    home_zh     TEXT NOT NULL, away_zh TEXT NOT NULL,
    home_team   TEXT, away_team TEXT,       -- canonical EN (zh_to_canonical, 可空)
    home_goals  INTEGER, away_goals INTEGER,
    rangqiu     INTEGER,                    -- 让球线 (home handicap, 竞彩式整数)
    c_home  REAL, c_draw REAL, c_away REAL,        -- 皇冠 1X2 decimal (sharp close)
    ou_line REAL, ou_over REAL, ou_under REAL,     -- O/U decimal (Crown 优先)
    rq_home REAL, rq_draw REAL, rq_away REAL,       -- 让球1X2 市场均 decimal
    ingested_at TEXT NOT NULL,
    UNIQUE(match_date, home_zh, away_zh)
);
CREATE INDEX IF NOT EXISTS idx_cch_date ON crown_close_history (match_date);
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)


def record_match(db_path: str | Path, rec: dict) -> int:
    """Upsert one ``parse_hisdata`` record. Idempotent (500 close is stable) — keyed on
    the 500 ``match_id``. Returns 1 on write, 0 on skip/failure (logged, never raised)."""
    mid = rec.get("match_id")
    c1x2 = rec.get("crown_1x2")
    if not (mid and c1x2 and rec.get("home_zh") and rec.get("away_zh")):
        return 0
    ou = rec.get("crown_ou") or (None, None, None)
    rq = rec.get("rq_avg") or (None, None, None)
    try:
        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_table(conn)
            conn.execute(
                "INSERT INTO crown_close_history (match_id, match_date, league_cn, "
                "home_zh, away_zh, home_team, away_team, home_goals, away_goals, rangqiu, "
                "c_home, c_draw, c_away, ou_line, ou_over, ou_under, rq_home, rq_draw, "
                "rq_away, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(match_id) DO UPDATE SET "
                "home_goals=excluded.home_goals, away_goals=excluded.away_goals, "
                "c_home=excluded.c_home, c_draw=excluded.c_draw, c_away=excluded.c_away, "
                "ou_line=excluded.ou_line, ou_over=excluded.ou_over, "
                "ou_under=excluded.ou_under, rq_home=excluded.rq_home, "
                "rq_draw=excluded.rq_draw, rq_away=excluded.rq_away",
                (mid, rec.get("date"), rec.get("league_cn"),
                 rec.get("home_zh"), rec.get("away_zh"),
                 zh_to_canonical(rec.get("home_zh")), zh_to_canonical(rec.get("away_zh")),
                 rec.get("home_goals"), rec.get("away_goals"), rec.get("rangqiu"),
                 c1x2[0], c1x2[1], c1x2[2], ou[1], ou[0], ou[2], rq[0], rq[1], rq[2], now),
            )
        return 1
    except Exception:  # noqa: BLE001 — a lost close row must never break the run
        log.warning("crown_close write failed (match_id=%s)", mid, exc_info=True)
        return 0
