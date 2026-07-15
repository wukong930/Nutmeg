"""真 Pinnacle 历史收盘 — 喂 §H 确诊 CLV(竞彩 vs Pinnacle 收盘).

源 = Odds API 历史快照(`sources/odds_api_history`)。一行一场,存 Pinnacle 1X2 + 大小球
收盘 + 该收盘取自的快照时刻(必 < kickoff,避 in-play)。按 (match_date, home_team,
away_team) 与 `jingcai_odds_history` join。EN 队名(Odds API = AF 系,与我们 canonical 对齐,
无中文 join)。`docs/autumn_prereg_analysis_plan.md` §H · `记忆
jingcai-fixedbonus-history-endpoint`。FAIL-SOFT。
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS pinnacle_close_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date   TEXT NOT NULL,           -- UTC 比赛日(= commence 的日期)
    home_team    TEXT NOT NULL, away_team TEXT NOT NULL,   -- Odds API EN(AF 系)
    commence_utc TEXT,                     -- 开赛 ISO
    snapshot_utc TEXT,                     -- 该收盘取自的快照时刻(必 < commence)
    p_home       REAL, p_draw REAL, p_away REAL,   -- Pinnacle 1X2 收盘(decimal)
    ou_line      REAL, over REAL, under REAL,       -- Pinnacle 主盘大小球
    ingested_at  TEXT NOT NULL,
    UNIQUE(match_date, home_team, away_team)
);
CREATE INDEX IF NOT EXISTS idx_pch_date ON pinnacle_close_history (match_date);
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)


def record_close(db_path: str | Path, row: dict, *, snapshot_utc: str) -> int:
    """Upsert one match's Pinnacle close. Keeps the row whose snapshot is CLOSEST
    before kickoff (a later snapshot, still < commence, = tighter close → overwrite).
    Returns 1 on write, 0 on no-op/failure (logged, never raised)."""
    home, away = row.get("home_team"), row.get("away_team")
    commence = row.get("commence_time")
    if not (home and away and commence and row.get("p_home")):
        return 0
    match_date = commence[:10]
    try:
        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_table(conn)
            conn.execute(
                "INSERT INTO pinnacle_close_history (match_date, home_team, away_team, "
                "commence_utc, snapshot_utc, p_home, p_draw, p_away, ou_line, over, under, "
                "ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(match_date, home_team, away_team) DO UPDATE SET "
                # 体检 W1 2026-07-15 — commence_utc/ingested_at 以前不在 SET:改时刻
                # 永不传播(§H CLV 地基表),行内容更新了 ingested_at 却停在首见时刻。
                "commence_utc=excluded.commence_utc, "
                "snapshot_utc=excluded.snapshot_utc, p_home=excluded.p_home, "
                "p_draw=excluded.p_draw, p_away=excluded.p_away, ou_line=excluded.ou_line, "
                "over=excluded.over, under=excluded.under, "
                "ingested_at=excluded.ingested_at "
                # 仅当新快照更贴近开赛(仍 < commence,由回填保证)时覆盖 → 保留最紧收盘。
                # 体检 W1 — 旧行 snapshot_utc 为 NULL 时比较结果是 NULL(假)→ 该行
                # 永久冻结,任何新收盘都进不来;IS NULL 分支放行首次真快照。
                "WHERE pinnacle_close_history.snapshot_utc IS NULL "
                "OR excluded.snapshot_utc > pinnacle_close_history.snapshot_utc",
                (match_date, home, away, commence, snapshot_utc,
                 row.get("p_home"), row.get("p_draw"), row.get("p_away"),
                 row.get("ou_line"), row.get("over"), row.get("under"), now),
            )
        return 1
    except Exception:  # noqa: BLE001 — a lost close row must never break the run
        log.warning("pinnacle_close write failed (%s vs %s)", home, away, exc_info=True)
        return 0
