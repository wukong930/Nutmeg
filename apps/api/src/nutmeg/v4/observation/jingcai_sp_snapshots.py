"""竞彩 SP 线史快照 —— 冻结缺口的另一半地基(2026-07-25)。

**病史**:owner 问「竞彩封盘、Pinnacle 还在动,一直拿冻结价算 EV 有没有价值」。
去查前向数据才发现:**我们根本没法回答**。

  · `jingcai_sp` 是 UPSERT(键 = match_date+home+away+market),每场只留最新一行;
  · 而 `sporttery_evening` 17:00-23:00 **每 30 分抓一次**(13 次/天),13 次全覆盖
    同一行 —— 盘中变化写进去又被自己冲掉。**抓取成本照付,数据全丢。**
  · 前向期唯一残存的 SP 时间序列是 `jingcai_vote_snapshots`(vote cron,3 次/天),
    拿它测:81 场里 **81/81 最后一次变盘 == 最后一次观测** = 100% 右审查 ——
    我们从没观测到竞彩真的冻结,量到的「冻结 5.5h」其实是**我们的观测节奏**。

`odds_snapshots` 给了 Pinnacle 侧的完整轨迹(CLV 地基),这张表补上竞彩侧。
两张齐了才能前向回答:真实冻结时长多久、A-3 触发条件 (b)(长缺口绿灯 ROI 是否
更差)、以及「临停售调价」—— 你看到的 SP ≠ 你买到的 SP,那个才是真 EV 杀手。

**APPEND-ONLY**:不 UPSERT、不覆盖、不删。仅当线态真变了才插一行(照
`odds_snapshots.record_row_snapshot` 的去重口径)—— 13 次抓同一个价只留 1 行,
表不会因为加密采样而爆炸。

**闸**(两道继承 + 一道自己的):
  1+2. booksum 带 / 开球后 market_mode 拒写 —— 由 `record_jingcai_sp` 在调用本
       模块**之前**把关,脏值根本走不到这里(共享 sink,别在这儿复制一份)。
  3.   **开球后一律拒写(所有源)**。这是今天现学的:`jingcai_vote_snapshots`
       14% 的行在开球后,而且 jc_* 还在变 —— 直接把冻结时长算成**负数**。停售后的
       读数不是可下注的价,进了这张表就会毒死它唯一的用途。kickoff 未知 → 放行
       (与 `_past_kickoff` 的 fail-open 一致),消费方另有 `captured_at <
       kickoff_utc` 可用。

**永不抛异常**:丢一条快照不能弄挂 cron —— 失败记 warning 返回 False。
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS jingcai_sp_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at   TEXT NOT NULL,          -- 我们观测到它的时刻 (UTC ISO)
    source        TEXT NOT NULL,          -- sporttery_open|sporttery_evening|market_mode|…
    league        TEXT,
    match_date    TEXT NOT NULL,
    home_team     TEXT NOT NULL,
    away_team     TEXT NOT NULL,
    kickoff_utc   TEXT,
    market        TEXT NOT NULL,          -- had | hhad
    handicap_home INTEGER,                -- hhad 的让球线
    jc_home       REAL NOT NULL,
    jc_draw       REAL NOT NULL,
    jc_away       REAL NOT NULL,
    booksum       REAL                    -- Σ1/odds,存下来好事后审计捕获闸
);
CREATE INDEX IF NOT EXISTS idx_jc_snap_match
    ON jingcai_sp_snapshots (match_date, home_team, away_team, market, captured_at);
CREATE INDEX IF NOT EXISTS idx_jc_snap_captured
    ON jingcai_sp_snapshots (captured_at);
"""

# 构成「这条竞彩线」的全部列 —— 去重就比这几个。
_STATE_COLS = ("jc_home", "jc_draw", "jc_away", "handicap_home")


def ensure_jingcai_sp_snapshots(conn: sqlite3.Connection) -> None:
    """幂等 DDL —— 每次写入前调用都安全。"""
    conn.executescript(_DDL)


def _past_kickoff(kickoff_utc: str | None) -> bool:
    """now > kickoff?kickoff 未知/不可解析 → False(fail-open,与捕获端一致)。"""
    if not kickoff_utc:
        return False
    try:
        ko = dt.datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=dt.UTC)
    return dt.datetime.now(dt.UTC) > ko


def record_jingcai_sp_snapshot(
    db_path: str | Path,
    *,
    match_date: str,
    home_team: str,
    away_team: str,
    market: str,
    jc_home: float,
    jc_draw: float,
    jc_away: float,
    league: str | None = None,
    kickoff_utc: str | None = None,
    handicap_home: int | None = None,
    booksum: float | None = None,
    source: str = "gather",
    captured_at: str | None = None,
) -> bool:
    """追加一条竞彩线态快照。→ 线态真变了(或首次见到)才 True。

    ``captured_at`` 只给历史回填用;实时 cron 一律走默认(此刻)。

    调用方**必须**已经过 `record_jingcai_sp` 的 booksum / 开球后闸 —— 本函数只
    再加一道「开球后一律拒写」(见模块头闸 3)。
    """
    try:
        if jc_home is None or jc_draw is None or jc_away is None:
            return False
        if not (match_date and home_team and away_team and market):
            return False
        # 闸 3 —— 开球后的读数不是可下注的价(见模块头)。
        if _past_kickoff(kickoff_utc):
            return False

        state = (float(jc_home), float(jc_draw), float(jc_away), handicap_home)
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
            ensure_jingcai_sp_snapshots(conn)
            cols = ", ".join(_STATE_COLS)
            last = conn.execute(
                f"SELECT {cols} FROM jingcai_sp_snapshots WHERE match_date=? "
                "AND home_team=? AND away_team=? AND market=? "
                "ORDER BY id DESC LIMIT 1",
                (match_date, home_team, away_team, market)).fetchone()
            if last is not None and tuple(last) == state:
                return False  # 线没动 —— 13 次抓同一个价只留 1 行
            conn.execute(
                "INSERT INTO jingcai_sp_snapshots (captured_at, source, league, "
                "match_date, home_team, away_team, kickoff_utc, market, "
                "handicap_home, jc_home, jc_draw, jc_away, booksum) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    captured_at
                    or dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                    source, league, match_date, home_team, away_team,
                    kickoff_utc or None, market,
                    handicap_home, float(jc_home), float(jc_draw), float(jc_away),
                    booksum,
                ))
        return True
    except Exception:  # noqa: BLE001 — 丢一条快照不能弄挂 cron
        log.warning(
            "竞彩 SP 快照写入失败:%s vs %s %s (db=%s)",
            home_team, away_team, market, db_path, exc_info=True)
        return False
