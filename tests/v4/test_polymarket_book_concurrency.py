"""CLOB 盘口并发拉取 —— **只改快慢,不改数据**(2026-09-01)。

英冠匹配修好后 `gaps computed` 从 841 涨到 1,687,一轮 CLOB 调用 1,659 次串行
≈ 10 分钟,而 cron 是每天 3 窗的 `StartCalendarInterval`。

⭐ 优化对象是**数出来的**不是推出来的:同一轮里 AF `/odds` 只有 **26** 次、
AF `/fixtures` **0** 次(全缓存),CLOB `/book` **1,659** 次。
我先前从代码顺序(`fetch_odds` 写在 CLOB 之前)推断「AF 配额才是真代价」——
错的。⇒ **先数调用,再优化。**

这个文件守的是「并发没有偷偷改变结果」,不是「快了多少」(那是环境相关的)。
"""
from __future__ import annotations

import threading
import time

import pytest

from nutmeg.v4.model import polymarket_gap as pg


class _Rec:
    """记录并发度与调用序列的假 fetch_book。"""

    def __init__(self, delay: float = 0.02) -> None:
        self.delay = delay
        self.calls: list[str] = []
        self.live = 0
        self.peak = 0
        self._lk = threading.Lock()

    def __call__(self, tok: str):
        with self._lk:
            self.calls.append(tok)
            self.live += 1
            self.peak = max(self.peak, self.live)
        time.sleep(self.delay)
        with self._lk:
            self.live -= 1
        return {"bids": [{"price": 0.4, "size": 100}], "asks": [{"price": 0.5, "size": 100}]}


def _game(n_legs: int):
    """n 条 moneyline 腿(`_informative` 对 1X2 恒真 ⇒ 全部会被拉)。"""
    from nutmeg.v4.data.polymarket_match import (
        AWAY_WIN,
        DRAW,
        HOME_WIN,
        MatchedGame,
        MatchedMarket,
    )
    specs = [HOME_WIN, DRAW, AWAY_WIN]
    mks = [MatchedMarket(specs[i % 3], f"tok{i}", f"q{i}") for i in range(n_legs)]
    return MatchedGame(
        fixture_id=1, league="X", home_team="A", away_team="B",
        match_date="2026-09-01", kickoff_utc=None, series_slug="s",
        event_slug="e", match_method="exact", match_confidence=1.0, markets=mks,
    )


def _odds(_fid):
    """⚠️ 夹具是**当场验过**的:`extract_1x2_odds` 按 **bookmaker id**(4)和
    **bet id**(1)查,不是按名字。我第一版只写了 name ⇒ `gaps_for_game` 在拉
    盘口**之前**就 `return []`,四条测试全红且报「DID NOT RAISE」——
    ⭐ 夹具不生效时,断言不是变红而是**变成无意义的红**,和真 bug 长得不一样。"""
    from nutmeg.v4.data.odds_parser import BET_MATCH_WINNER, PINNACLE_BOOKMAKER_ID
    return [{"update": "2026-09-01T00:00:00+00:00", "bookmakers": [{
        "id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
        "bets": [{"id": BET_MATCH_WINNER, "name": "Match Winner", "values": [
            {"value": "Home", "odd": "2.10"},
            {"value": "Draw", "odd": "3.40"},
            {"value": "Away", "odd": "3.60"}]}]}]}]


def test_books_are_fetched_concurrently() -> None:
    """🚨 承重:并发**真的发生了**(峰值 >1)。

    没有这条,把 `ThreadPoolExecutor` 换回串行推导式**不会有任何测试变红** ——
    那正是「性能改动没有回归闸」的典型死法。
    """
    rec = _Rec()
    pg.gaps_for_game(_game(12), fetch_odds=_odds, fetch_book=rec)
    assert rec.peak > 1, f"峰值并发 {rec.peak} ⇒ 还是串行"
    assert rec.peak <= pg._BOOK_WORKERS, f"峰值 {rec.peak} 超过上限 {pg._BOOK_WORKERS}"


def test_every_token_is_fetched_exactly_once() -> None:
    """⛔ 并发不许漏拉、也不许重复拉(重复=白花一次来回)。"""
    rec = _Rec(delay=0)
    g = _game(9)
    pg.gaps_for_game(g, fetch_odds=_odds, fetch_book=rec)
    want = {m.yes_token for m in g.markets}
    assert set(rec.calls) == want, (set(rec.calls) ^ want)
    assert len(rec.calls) == len(want), f"有重复:{rec.calls}"


def test_a_single_leg_does_not_spin_up_a_pool() -> None:
    """一条腿时走直路 —— 起线程池比调用本身还贵。"""
    rec = _Rec(delay=0)
    pg.gaps_for_game(_game(1), fetch_odds=_odds, fetch_book=rec)
    assert rec.peak == 1 and len(rec.calls) == 1


def test_a_failing_book_still_propagates() -> None:
    """异常语义必须与串行版一致 —— ⛔ 并发不许把错误吞成「安静少给你」。

    (今天刚在 Polymarket 分页上栽过一次同形的:接住异常 ⇒ 静默降级 ⇒ 塌 10 天。)
    """
    def _boom(tok: str):
        raise RuntimeError("book down")

    with pytest.raises(RuntimeError):
        pg.gaps_for_game(_game(6), fetch_odds=_odds, fetch_book=_boom)
