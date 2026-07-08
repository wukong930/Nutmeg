"""竞彩 历史赔率走势 — backfill 表(long-format,一行一次变盘).

Feeds the pre-registered HISTORICAL held-out analysis (`docs/autumn_prereg_analysis_plan.md`
§H, frozen 2026-07-09): 8 年竞彩 胜平负/让球 全程走势 × Pinnacle 收盘 × 结果 → H-P1/P2
CLV + H-S1′/S3/S4/S6。源 = `sources/sporttery_history.getFixedBonusV1`(`记忆
jingcai-fixedbonus-history-endpoint`)。

**去规范化长表**:每行 = 一个 (match_id, market∈{had,hhad}, seq) 的赔率快照,比赛元数据
(联赛/队名/结果/单关标记/收盘日)冗余到每行 → 一张表直接 SQL 分析,免 join。settled 历史
场走势固定 → 回填一次即定;re-ingest 用 delete-then-insert 保持幂等干净。FAIL-SOFT。
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS jingcai_odds_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id     INTEGER NOT NULL,
    market       TEXT NOT NULL,          -- had(胜平负) | hhad(让球)
    seq          INTEGER NOT NULL,       -- 0 = 初盘(开售),末 = 终盘(封盘)
    update_dt    TEXT,                   -- 竞彩发布该赔率的时刻 (Beijing 'YYYY-MM-DD HH:MM:SS')
    h            REAL NOT NULL, d REAL NOT NULL, a REAL NOT NULL,
    goal_line    INTEGER,                -- 让球线 (hhad; NULL for had)
    -- 去规范化的比赛元数据(同一 match 各行一致)
    league_id    INTEGER, league_cn TEXT,
    home_zh      TEXT, away_zh TEXT,
    home_team    TEXT, away_team TEXT,   -- canonical EN (zh_to_canonical; NULL if unmapped)
    home_goals   INTEGER, away_goals INTEGER,   -- 90' 结果 (sectionsNo999; NULL if 未知)
    single_available INTEGER,            -- 该 market 是否可单关 (singleList; 历史也有)
    close_date   TEXT,                   -- 末次发布日 = 比赛日代理 (精确 kickoff 需 getMatchHeadV1)
    ingested_at  TEXT NOT NULL,
    UNIQUE(match_id, market, seq)
);
CREATE INDEX IF NOT EXISTS idx_joh_match   ON jingcai_odds_history (match_id);
CREATE INDEX IF NOT EXISTS idx_joh_league  ON jingcai_odds_history (league_id, close_date);
CREATE INDEX IF NOT EXISTS idx_joh_date    ON jingcai_odds_history (close_date);
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)


def record_history_match(db_path: str | Path, parsed: dict) -> int:
    """Store one parsed match's full had+hhad series (delete-then-insert by match_id
    for idempotent re-ingest). Returns rows written; 0 on no-op / any failure
    (logged, never raised)."""
    mid = parsed.get("match_id")
    series = parsed.get("series") or {}
    if mid is None or not (series.get("had") or series.get("hhad")):
        return 0
    single = parsed.get("single") or {}
    meta = (
        parsed.get("league_id"), parsed.get("league_cn"),
        parsed.get("home_zh"), parsed.get("away_zh"),
        parsed.get("home_team"), parsed.get("away_team"),
        parsed.get("home_goals"), parsed.get("away_goals"),
        parsed.get("close_date"),
    )
    try:
        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        n = 0
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_table(conn)
            conn.execute("DELETE FROM jingcai_odds_history WHERE match_id=?", (int(mid),))
            for market in ("had", "hhad"):
                rows = series.get(market) or []
                sa = single.get(market)
                for seq, r in enumerate(rows):
                    conn.execute(
                        "INSERT INTO jingcai_odds_history (match_id, market, seq, "
                        "update_dt, h, d, a, goal_line, league_id, league_cn, home_zh, "
                        "away_zh, home_team, away_team, home_goals, away_goals, "
                        "single_available, close_date, ingested_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (int(mid), market, seq, r.get("update_dt"),
                         r["h"], r["d"], r["a"], r.get("goal_line"),
                         *meta[:6],
                         meta[6], meta[7],
                         int(sa) if sa is not None else None,
                         meta[8], now),
                    )
                    n += 1
        return n
    except Exception:  # noqa: BLE001 — a lost backfill row must never break the run
        log.warning("jingcai_odds_history write failed (mid=%s, db=%s)",
                    mid, db_path, exc_info=True)
        return 0
