"""多书商 1X2 快照 —— **单锚的离散度参照**(2026-09-01,forward-only)。

## 为什么建这张表

Odds API 每场返回 **15–22 家**书商的报价(实测 113 场:每场 4–24 家,中位 ~18),
而 `fetch_pinnacle_lookup` 只留 Pinnacle 一家,其余随 TTL 缓存过期**一起丢**。
实测竞彩在售 693 场里,`odds_api` 来源的 351 场**只有 1%** 还能找回多书商数据
—— **不是覆盖不够,是没存**。

⭐ 存它是**零额外调用、零额外配额**:数据本来就在同一次响应里。

## 用途:回答「Pinnacle 这一次是不是在自说自话」

owner 的原始问题:竞彩**封盘后**价格冻住,Pinnacle 还在动;若 Pinnacle 逆着竞彩
的倾向大幅调整,按封盘价算的 EV 就站不住。实测封盘后主胜隐含概率漂移
**|漂移|>2pp 占 29%、>5pp 占 5%,区间 [−12.4,+9.7]pp** —— 量级远大于所有 δ 校正。

已测两条支持多锚:
  · **单锚会夸大**:法乙那场 Pinnacle 是 13 家里最看好客胜的 ⇒
    单锚 EV **+16.7%** vs 13 家中位 **+8.8%** vs 最保守 **−0.6%**(近一倍);
  · 63 场重叠上,「Pinnacle 过 +5% 闸而共识不过」的腿 **5** 条
    (Canada 客胜 +5.6%→−0.7% · Panama 平局 +9.0%→+3.4% …)。

⛔ **但那 63 场全是世界杯 + 全是缓存没过期的,人口偏斜** ⇒ 只能当「机制存在」的
证据,**不是**「影响多大」的估计。⇒ 先存,攒够了在**完整人口**上重量再谈判闸。

## ⛔ 三条纪律

1. **不改 `odds_snapshots`。** 它是 CLV 地基 + `sigma_p_fit` 的输入,加列/改语义
   风险太大。本表是 append-only 的兄弟表,坏了也不污染地基。
2. **不拿它当 P 喂 EV。** `fetch_pinnacle_lookup` 的 Pinnacle-STRICT 是设计
   (绝不拿软书顶 sharp 先验);本表的用途是**离散度**,绕过那条设计就是倒退。
3. **书商不筛、不归组。** 17 家里有同源的(`unibet_fr/nl/se`、`winamax_fr/de`),
   会让一家顶多票。⛔ 但归组要维护一张母公司字典(又一本会掉队的平行表)——
   改为**把家数一起存下来**,让消费方看得见这个偏差,而不是替它消掉。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS book_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at  TEXT NOT NULL,      -- 我们观测到的时刻(UTC ISO)
    match_date   TEXT NOT NULL,      -- = commence_time 的日期,与 odds_snapshots 同轴
    home_team    TEXT NOT NULL,      -- Odds API 拼法(⚠️ 消费方 join 前必须过 _norm_team)
    away_team    TEXT NOT NULL,
    n_books      INTEGER NOT NULL,   -- 这一条里有几家 —— **必须一起看**:2 家的共识不是共识
    books        TEXT NOT NULL       -- JSON {book_key: [home, draw, away]}(含 vig 的十进制)
);
CREATE INDEX IF NOT EXISTS idx_book_snapshots_match
    ON book_snapshots (match_date, home_team, away_team, captured_at);
"""


def ensure_book_snapshots(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)


def _sane(o: Any) -> bool:
    """三腿都要是 (1.0, 1000] 的有限赔率 —— 同 `odds_snapshots._sane_odds` 的物理闸。"""
    try:
        v = [float(x) for x in o]
    except (TypeError, ValueError):
        return False
    return len(v) == 3 and all(1.0 < x <= 1000.0 for x in v)


def record_book_snapshot(
    db_path: str | Path,
    *,
    match_date: str,
    home_team: str,
    away_team: str,
    books: dict[str, Any],
    captured_at: str | None = None,
) -> bool:
    """写一条多书商快照。→ 真写了 True。

    **去重:同一 (场次, 书商组合的报价) 不变就不写** —— 与 `odds_snapshots` 的
    「线态去重」同一个态度:cron 每天多窗跑,价格没动就不该在表里堆重复行。
    Best-effort:任何失败只 warning,**绝不让一次采集因此失败**(本模块契约)。
    """
    clean = {k: [float(x) for x in v] for k, v in (books or {}).items() if _sane(v)}
    if not clean or not (match_date and home_team and away_team):
        return False
    payload = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    now = captured_at or datetime.now(UTC).isoformat(timespec="seconds")
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            ensure_book_snapshots(conn)
            prev = conn.execute(
                "SELECT books FROM book_snapshots WHERE match_date=? AND home_team=? "
                "AND away_team=? ORDER BY captured_at DESC LIMIT 1",
                (match_date, home_team, away_team)).fetchone()
            if prev and prev[0] == payload:
                return False          # 线态没变 ⇒ 不堆重复行
            conn.execute(
                "INSERT INTO book_snapshots (captured_at, match_date, home_team, "
                "away_team, n_books, books) VALUES (?,?,?,?,?,?)",
                (now, match_date, home_team, away_team, len(clean), payload))
        return True
    except sqlite3.Error:
        log.warning("record_book_snapshot failed", exc_info=True)
        return False


def record_book_lookup(db_path: str | Path, lookup: dict, *,
                       captured_at: str | None = None) -> int:
    """把 `odds_api.fetch_book_lookup` 的整份输出落盘 → 真写入的条数。

    ⚠️ lookup 的键是 **(norm_home, norm_away, date)**,而表里存的是**原始拼法**
    —— 归一后的名字丢了信息,而消费方 join 时会自己再归一一次。
    所以这里从 `books` 拿不到原名 ⇒ 调用方必须传原名版本(见 `record_book_snapshot`)。
    本函数只处理调用方已经准备好 `(date, home, away) → books` 的情形。
    """
    n = 0
    for (date, home, away), books in (lookup or {}).items():
        n += int(record_book_snapshot(
            db_path, match_date=date, home_team=home, away_team=away,
            books=books, captured_at=captured_at))
    return n


def capture_books_for_sport(db_path: str | Path, sport_key: str, *,
                            regions: str = "eu", refresh: bool = False) -> int:
    """把 Odds API **当前缓存里**那 15–22 家写进 `book_snapshots` → 真写入的条数。

    ## ⭐ 为什么这是零配额

    `fetch_book_lookup` 与 `fetch_pinnacle_lookup` 打的是**同一个 endpoint + 同一组
    参数**(`sports/{sk}/odds`,`regions` / `markets=h2h,totals` / `oddsFormat`),
    而 `odds_api._cache_path` 只按参数哈希 ⇒ **同一个缓存文件**。调用方只要在一次
    **成功的** Pinnacle 拉取之后调用本函数,那个文件必然存在;这里传
    `ttl_seconds=None` ⇒ `fresh_enough` 恒 True ⇒ `_request` 走缓存分支,不发请求。

    🚨 反过来说:`refresh=False` **不等于「只读缓存」**。`odds_api._request` 的判据是
    `if cf.exists() and not refresh and fresh_enough:` —— 文件**不存在**时它会直接
    fall through 到 live fetch。所以调用方**必须**先确认同参数的那次拉取成功了
    (最省事的判据:上一步的 lookup 非空),否则这里就是一次真消费。
    额度真凶历来是**服务路径**而不是 cron,别在这里开第二个口子。

    ⚠️ 存**原始拼法**而不是 lookup 的归一键:归一后名字的信息丢了,而消费方
    (`routes._attach_book_consensus` → `team_match.same_team`)join 时会自己再归一
    一次。所以名字从 `fetch_current_odds` 的原始事件里取。

    ⛔ 整体 fail-soft:任何异常都吞掉并返回 0 —— 这是**参照层**,绝不允许它拖垮
    调用方(收盘线采集是 CLV 地基;盘面刷新是 owner 临场在用的)。
    """
    from nutmeg.v4.data.sources import odds_api
    try:
        books = odds_api.fetch_book_lookup(sport_key, regions=regions, refresh=refresh)
        if not books:
            return 0
        n = 0
        for e in (odds_api.fetch_current_odds(
                sport_key, regions=regions, markets="h2h,totals", refresh=False) or []):
            key = (odds_api._norm_team(e.get("home_team") or ""),
                   odds_api._norm_team(e.get("away_team") or ""),
                   str(e.get("commence_time") or "")[:10])
            bk = books.get(key)
            if not bk:
                continue
            n += int(record_book_snapshot(
                db_path, match_date=key[2],
                home_team=e.get("home_team") or "",
                away_team=e.get("away_team") or "", books=bk))
        if n:
            log.info("book-snapshots: %s 写入 %d 条(多书商离散度参照)", sport_key, n)
        return n
    except Exception:  # noqa: BLE001
        log.warning("book-snapshots 采集失败(%s)—— 不影响调用方", sport_key, exc_info=True)
        return 0


__all__ = ["DDL", "capture_books_for_sport", "ensure_book_snapshots",
           "record_book_lookup", "record_book_snapshot"]
