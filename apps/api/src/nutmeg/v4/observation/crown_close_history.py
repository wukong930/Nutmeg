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
    kickoff_utc TEXT,                      -- 真·开赛时刻 UTC (由北京 matchdate+matchtime 推)
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

# 后加的列(旧库靠 ALTER 补;新库靠 _DDL 直接建好)。以后加列往这里追加即可。
_ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("kickoff_utc", "TEXT"),
)

# ⚠️ 引用【后加列】的索引必须放这里,不能放 _DDL —— 在老表上 _DDL 先于 ALTER 跑,
# 那时列还不存在,executescript 会 "no such column" 整个炸掉(测试抓到过)。
_POST_MIGRATION_DDL = """
CREATE INDEX IF NOT EXISTS idx_cch_ko ON crown_close_history (kickoff_utc);
"""


def ensure_table(conn: sqlite3.Connection) -> None:
    """建表 + **迁移已存在的旧表**。顺序:建表 → ALTER 补列 → 建索引。

    ⚠️ `CREATE TABLE IF NOT EXISTS` 对**已存在**的表是 no-op —— 光在 _DDL 里加列,
    线上那张 5,813 行的老表**永远不会长出新列**。新增列必须登记进 `_ADDED_COLUMNS`
    走 ALTER。幂等(重复调用只是几次 PRAGMA)。
    """
    conn.executescript(_DDL)
    have = {r[1] for r in conn.execute("PRAGMA table_info(crown_close_history)")}
    for col, decl in _ADDED_COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE crown_close_history ADD COLUMN {col} {decl}")
            log.info("crown_close_history: 迁移新增列 %s", col)
    conn.executescript(_POST_MIGRATION_DDL)


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
                "INSERT INTO crown_close_history (match_id, match_date, kickoff_utc, "
                "league_cn, home_zh, away_zh, home_team, away_team, home_goals, away_goals, "
                "rangqiu, c_home, c_draw, c_away, ou_line, ou_over, ou_under, rq_home, "
                "rq_draw, rq_away, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(match_id) DO UPDATE SET "
                # 体检 W1 2026-07-15 全列收口 —— 上午只补了出事的队名列,漏了 rangqiu
                # (「修坏的那列而不是修 sink」的活标本,当天被 L2 扫描抓回来)。现在
                # 一次修完:数据列全跟最新抓取走;可空捕获列(kickoff/league/rangqiu/
                # 队名)COALESCE —— 新值能传播、None 不冲好数据(clubelo 自毁教训)。
                "match_date=excluded.match_date, "
                "kickoff_utc=COALESCE(excluded.kickoff_utc, crown_close_history.kickoff_utc), "
                "league_cn=COALESCE(excluded.league_cn, crown_close_history.league_cn), "
                "home_zh=excluded.home_zh, away_zh=excluded.away_zh, "
                # ⚠️ 2026-07-15 — home_team/away_team 以前【不在 SET 里】= 补词典永远传不到
                # 已有的行。实证:重抓后 kickoff_utc 更新了,home_team 却仍是 NULL。
                # 于是 _ZH_OVERRIDES 越补越好、库里纹丝不动(和 clubelo 那个「数据不更新」同类)。
                "home_team=COALESCE(excluded.home_team, crown_close_history.home_team), "
                "away_team=COALESCE(excluded.away_team, crown_close_history.away_team), "
                "home_goals=excluded.home_goals, away_goals=excluded.away_goals, "
                "rangqiu=COALESCE(excluded.rangqiu, crown_close_history.rangqiu), "
                "c_home=excluded.c_home, c_draw=excluded.c_draw, c_away=excluded.c_away, "
                "ou_line=excluded.ou_line, ou_over=excluded.ou_over, "
                "ou_under=excluded.ou_under, rq_home=excluded.rq_home, "
                "rq_draw=excluded.rq_draw, rq_away=excluded.rq_away, "
                "ingested_at=excluded.ingested_at "
                # 第二 UNIQUE(match_date,home_zh,away_zh):500 给同一场换发新 match_id
                # (改期回挂)时,首个子句不匹配 → 以前直接 IntegrityError 被外层吃掉、
                # 该行每次重抓重复丢。第二子句按赛事身份接住,把行迁移到新 match_id。
                "ON CONFLICT(match_date, home_zh, away_zh) DO UPDATE SET "
                "match_id=excluded.match_id, "
                "kickoff_utc=COALESCE(excluded.kickoff_utc, crown_close_history.kickoff_utc), "
                "league_cn=COALESCE(excluded.league_cn, crown_close_history.league_cn), "
                "home_team=COALESCE(excluded.home_team, crown_close_history.home_team), "
                "away_team=COALESCE(excluded.away_team, crown_close_history.away_team), "
                "home_goals=excluded.home_goals, away_goals=excluded.away_goals, "
                "rangqiu=COALESCE(excluded.rangqiu, crown_close_history.rangqiu), "
                "c_home=excluded.c_home, c_draw=excluded.c_draw, c_away=excluded.c_away, "
                "ou_line=excluded.ou_line, ou_over=excluded.ou_over, "
                "ou_under=excluded.ou_under, rq_home=excluded.rq_home, "
                "rq_draw=excluded.rq_draw, rq_away=excluded.rq_away, "
                "ingested_at=excluded.ingested_at",
                (mid, rec.get("date"), rec.get("kickoff_utc"), rec.get("league_cn"),
                 rec.get("home_zh"), rec.get("away_zh"),
                 zh_to_canonical(rec.get("home_zh")), zh_to_canonical(rec.get("away_zh")),
                 rec.get("home_goals"), rec.get("away_goals"), rec.get("rangqiu"),
                 c1x2[0], c1x2[1], c1x2[2], ou[1], ou[0], ou[2], rq[0], rq[1], rq[2], now),
            )
        return 1
    except Exception:  # noqa: BLE001 — a lost close row must never break the run
        log.warning("crown_close write failed (match_id=%s)", mid, exc_info=True)
        return 0
