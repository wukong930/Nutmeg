"""Polymarket keyset 分页 —— 2026-09-01 换掉 offset 分页时的回归闸。

## 病史(一次塌了 10 天没人发现的静默降级)

`/events` 的 offset 分页在 ≥2100 返 422。旧实现按 `startDate` **升序** +
`closed=false` 翻页 ⇒ 浅页全是**已开球却没关闭**的旧市场(实测墙内 95.6% 是过去的
比赛),今天的比赛被挤到墙后面 ⇒ 每轮只捞到 ~20 个赛事(峰值 344)。
2026-07-15 的「修复」接住 422 并接受已抓到的页 —— **消除症状、保留病因、
移除唯一告警**,于是 08-23 起抓取量塌 10 倍而 cron 一路绿灯。

修法:`/events/keyset` + `after_cursor` + **`start_time_min/max`**(服务端按开球筛)。

## 这个文件守三件事

1. 游标真的在前进(**我自己就栽在这上面** —— 见 `test_a_stuck_cursor_is_detected`)
2. 用的是 `start_time_*` 而不是 `start_date_*`(后者筛的是上架日期,实测返回 0 条)
3. 撞到保险丝会**喊**,不会静默截断
"""
from __future__ import annotations

import logging

import pytest

from nutmeg.v4.data.sources import polymarket as pm


def _ev(eid: int, kickoff: str) -> dict:
    return {"id": str(eid), "slug": f"ev-{eid}",
            "markets": [{"gameStartTime": kickoff, "question": "A vs B"}]}


@pytest.fixture
def fake_api(monkeypatch):
    """把 keyset 取数器换成可控的假分页。返回记录调用参数的 list。"""
    calls: list[dict] = []

    def make(pages: list[list[dict]], *, stuck: bool = False):
        def _fetch(**kw):
            calls.append(kw)
            idx = 0 if stuck else len(calls) - 1
            if idx >= len(pages):
                return [], None
            nxt = "cur" if (stuck or idx + 1 < len(pages)) else None
            return pages[idx], nxt
        monkeypatch.setattr(pm, "fetch_events_keyset", _fetch)
        return calls
    return make


def test_it_pages_through_the_cursor(fake_api) -> None:
    """多页必须全部收下,不是只拿第一页。"""
    p1 = [_ev(i, "2026-09-02T12:00:00Z") for i in range(100)]
    p2 = [_ev(100 + i, "2026-09-02T13:00:00Z") for i in range(30)]
    calls = fake_api([p1, p2])
    out = pm.fetch_soccer_game_events(start_date_min="2026-09-01", end_date="2026-09-03")
    assert len(out) == 130, f"只收到 {len(out)}"
    assert calls[1]["after_cursor"] == "cur", "第二次调用没带游标"


def test_a_stuck_cursor_is_detected(fake_api, caplog) -> None:
    """🚨 承重:游标不生效(每次返回同一页)必须**当场停并 error**。

    2026-09-01 实犯:猜了 7 个游标参数名,服务端对未知查询参数**不报错**,
    于是「翻了 80 页、拉了 467MB,累计仍是 100 条」跑完才发现。
    没有这条断言,一个失效的游标就是一个无限循环 + 假的「数据就这么多」。
    """
    page = [_ev(i, "2026-09-02T12:00:00Z") for i in range(100)]
    fake_api([page] * 50, stuck=True)
    with caplog.at_level(logging.ERROR):
        out = pm.fetch_soccer_game_events(start_date_min="2026-09-01", end_date="2026-09-03")
    assert len(out) == 100, f"卡住的游标却收了 {len(out)} 条 —— 重复计数了"
    assert any("没有前进" in r.message for r in caplog.records), "卡住了却没 error"


def test_the_kickoff_window_filter_still_applies(fake_api) -> None:
    """服务端已按开球筛,代码里**仍要**再过一道 —— 服务端语义变了要能兜住。"""
    fake_api([[_ev(1, "2026-09-02T12:00:00Z"),      # 窗口内
               _ev(2, "2026-09-20T12:00:00Z"),      # 窗口外
               _ev(3, "2026-08-01T12:00:00Z")]])    # 窗口外
    out = pm.fetch_soccer_game_events(start_date_min="2026-09-01", end_date="2026-09-03")
    assert [e["id"] for e in out] == ["1"], [e["id"] for e in out]


def test_it_asks_the_server_by_kickoff_not_by_listing_date(fake_api) -> None:
    """⛔ 必须传 `start_time_min/max`,**不是** `start_date_min/max`。

    实测:`start_date_min` 返回 **0 条**(它筛的是事件创建/上架日期,与开球
    中位差 **1085h**);`start_time_min/max` 窗口内命中 **100/100**。
    这个断言防的是有人「顺手统一成 start_date_*」。
    """
    calls = fake_api([[]])
    pm.fetch_soccer_game_events(start_date_min="2026-09-01", end_date="2026-09-03")
    kw = calls[0]
    assert kw.get("start_time_min", "").startswith("2026-09-01"), kw
    assert kw.get("start_time_max", "").startswith("2026-09-03"), kw
    assert "start_date_min" not in kw and "start_date_max" not in kw, kw


def test_hitting_the_fuse_is_loud(fake_api, caplog) -> None:
    """⚠️ 撞到 `max_events` 必须喊 —— 「量刚好等于上限」和「真的只有这么多」同形。

    旧默认值 3000 就是这么坑人的:未来 7 天实测 3000+ 个赛事,结果被切在整数上。
    """
    pages = [[_ev(i + p * 100, "2026-09-02T12:00:00Z") for i in range(100)]
             for p in range(5)]
    fake_api(pages)
    with caplog.at_level(logging.WARNING):
        out = pm.fetch_soccer_game_events(
            start_date_min="2026-09-01", end_date="2026-09-03", max_events=250)
    assert len(out) >= 250
    assert any("保险丝" in r.message for r in caplog.records), "截断了却没喊"


def test_rows_understands_the_keyset_envelope() -> None:
    """`/events` 给 `{"data": …}`,`/events/keyset` 给 `{"events": …}` —— 两个都要认。"""
    assert pm._rows({"data": [{"id": "1"}]}) == [{"id": "1"}]
    assert pm._rows({"events": [{"id": "2"}]}) == [{"id": "2"}]
    assert pm._rows([{"id": "3"}]) == [{"id": "3"}]
    assert pm._rows({}) == []


def test_the_http_query_carries_start_time_not_start_date(monkeypatch) -> None:
    """🚨 打在**正确的层**:断言真正发出去的 HTTP query。

    ⚠️ 上面那条 `test_it_asks_the_server_by_kickoff_not_by_listing_date` 是
    **假绿的**:它 monkeypatch 掉了整个 `fetch_events_keyset`,只看得到调用方传的
    **关键字参数名**,而把 `params["start_time_min"]` 改成 `params["start_date_min"]`
    的变异发生在函数**内部**(关键字 → HTTP query 的那一步)⇒ 测试照样全绿。
    2026-09-01 空包弹当场抓到的。

    ⭐ 同族:memory `syntactic-proxy-for-semantic-property` 的
    「查中间产物的形状代替查最终答案」。判据:**变异打在哪一层,断言就得打在哪一层。**
    留着上面那条(它守的是调用方不传错关键字),但**承重的是这一条**。
    """
    seen: dict = {}

    def _req(base, endpoint, params=None, **kw):
        seen["endpoint"] = endpoint
        seen["params"] = dict(params or {})
        return {"events": [], "next_cursor": None}

    monkeypatch.setattr(pm, "_request", _req)
    pm.fetch_events_keyset(start_time_min="2026-09-01T00:00:00Z",
                           start_time_max="2026-09-03T23:59:59Z",
                           after_cursor="CUR")
    assert seen["endpoint"] == "/events/keyset", seen["endpoint"]
    q = seen["params"]
    assert q.get("start_time_min") == "2026-09-01T00:00:00Z", q
    assert q.get("start_time_max") == "2026-09-03T23:59:59Z", q
    assert q.get("after_cursor") == "CUR", q
    # ⛔ 实测 start_date_min 返回 0 条(它筛上架日期,与开球中位差 1085h)
    assert "start_date_min" not in q and "start_date_max" not in q, q
    # ⛔ 别退回被弃用的 offset 分页(≥2100 → 422,正是这次事故的根因)
    assert "offset" not in q, q
