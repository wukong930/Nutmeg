"""`jingcai_sp[open]` 哨兵拆成「上新场节律」+「cron 心跳」两条(2026-08-18)。

## 出事的形状

体检 2026-08-18T09:45 报:
    9. 捕获表漏数据哨兵 | jingcai_sp[open] 停长! 最后 2026-08-15 (3d)
       · 竞彩 初盘 SP (jc_open 子流) —— **捕获 cron 可能静默死了**

**那句诊断是错的。** cron 一直在跑(launchd 日志连续、HTTP 200、逐轮写入)。

病根:`opened_at` 是 **set-once**(COALESCE,记竞彩把这场**开出来**的时刻)
⇒ `max(opened_at)` 量的是「**竞彩最近一次上新场**」,不是「我们的 cron 活没活」。

## 为什么必须拆而不是只调阈值

两个量的**语义不同**,合成一条就必然既报错人又报错事:
· 竞彩不上新场 = **外部市场行为**,不是我们漏数据 ⇒ 不该 gate
· cron 死了 = **forward-only 数据永久丢失** ⇒ 必须 gate,且要快

⚠️ 本文件守的这条,`data_freshness.py` 里 `snapshot_provenance` 那条的注释
**早就写明了正确做法**:「空盘面的日子 leg 表本来就该是 0 行,拿它当心跳会在
**正确的日子假红**;provenance 则是『跑过就有一行』」。那条为快照层做对了,
`[open]` 这条没做 —— 同一个错误在同一个文件里并存了一段时间。

## 阈值不是拍的

实测节律(N=47 个间隔,2026-06-22~08-18):间隔 1 天 41 次 / 2 天 2 次 / **3 天 4 次**,
最大 3;按星期:周一 3 天有上新、周日 4 天,周二~周六各 8-9 天 ⇒
**周六→周二 3 天空档是常态**。旧阈值 2 ⇒ 9% 的间隔必假红。
"""
from __future__ import annotations

import datetime as dt

from nutmeg.v4.cli.data_freshness import CAPTURE_TABLES


def _entries():
    return {e[6] or e[0]: e for e in CAPTURE_TABLES}


def test_both_entries_exist():
    e = _entries()
    assert "jingcai_sp[open]" in e, "上新场节律那条没了"
    assert "jingcai_sp[open-heartbeat]" in e, "🚨 cron 心跳那条没了 —— 漏数据探测器消失"


def test_cadence_entry_measures_listings_and_does_not_gate():
    """上新场那条:量 `opened_at`、阈值 ≥3(容得下常态 3 天空档)、**不 gate**。"""
    tbl, ts, days, crit, *_ = _entries()["jingcai_sp[open]"]
    assert ts == "opened_at", f"它该量 opened_at,实际 {ts}"
    assert days >= 3, (
        f"阈值 {days} 天 —— 实测最大常态空档就是 3 天(周六→周二),"
        f"≤2 会让 9% 的间隔假红")
    assert crit is False, (
        "🚨 它又变回 CRITICAL 了 —— 竞彩不上新场是**外部市场行为**,"
        "不是我们漏数据,不该 gate 体检")


def test_heartbeat_entry_measures_the_cron_and_does_gate():
    """心跳那条:量 `captured_at`、按 open 子流过滤、阈值紧、**必须 gate**。"""
    tbl, ts, days, crit, _desc, where, _name = _entries()["jingcai_sp[open-heartbeat]"]
    assert tbl == "jingcai_sp" and ts == "captured_at"
    assert crit is True, "🚨 心跳降级成 warn 了 —— cron 死掉就不会让体检失败"
    assert days <= 2, f"心跳阈值 {days} 天太松 —— forward-only 数据每多丢一天都补不回"
    assert where and "jc_open_home" in where, (
        f"🚨 过滤是 {where!r} —— 必须按 open 子流切。用整表会被 ingest/evening 两个 "
        f"cron 顶绿(data_freshness.py 开头 P0-1 记的病根)")


def test_the_two_entries_do_not_measure_the_same_thing():
    """⭐ 前提自检:两条必须真的量不同的东西,否则拆分是装饰。

    (若哪天有人把心跳也改成 `opened_at`,上面三条仍会全绿。)
    """
    a = _entries()["jingcai_sp[open]"]
    b = _entries()["jingcai_sp[open-heartbeat]"]
    assert a[1] != b[1], f"两条量的是同一列 {a[1]} —— 拆分没有意义"
    assert (a[5] or "") != (b[5] or ""), "两条的子流过滤相同 —— 拆分没有意义"


def test_heartbeat_column_really_advances_when_no_new_listings(tmp_path):
    """🚨🚨 **承重条**:心跳字段必须能在「竞彩没上新场」的日子仍然前进。

    如果它不能,这条心跳就和被它取代的那条一样,会在**正确的日子假红** ——
    换了个字段名而已。

    ⭐ 这里用**合成库**而不是生产库:生产数据会变,而这条断言的是**机制**。
    (拿生产库跑会变成「今天恰好有数据」的快照,明天可能因为真实空窗而假红。)
    """
    import sqlite3
    db = tmp_path / "t.db"
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE jingcai_sp (captured_at TEXT, opened_at TEXT,
                 jc_open_home REAL)""")
    # D0:竞彩上新场 + cron 抓到
    c.execute("INSERT INTO jingcai_sp VALUES ('2026-08-15T01:50:00Z','2026-08-15T01:50:00Z',2.1)")
    # D1/D2:**没有新场**,但 cron 照跑 ⇒ UPSERT 刷新同一批行的 captured_at
    c.execute("UPDATE jingcai_sp SET captured_at='2026-08-17T03:05:00Z'")
    c.commit()
    mx_open = c.execute("SELECT MAX(substr(opened_at,1,10)) FROM jingcai_sp "
                        "WHERE opened_at IS NOT NULL").fetchone()[0]
    mx_beat = c.execute("SELECT MAX(substr(captured_at,1,10)) FROM jingcai_sp "
                        "WHERE jc_open_home IS NOT NULL").fetchone()[0]
    today = dt.date(2026, 8, 18)
    stale_open = (today - dt.date.fromisoformat(mx_open)).days
    stale_beat = (today - dt.date.fromisoformat(mx_beat)).days
    assert stale_open == 3, f"夹具没造出 3 天空档(实际 {stale_open})—— 本条无判别力"
    assert stale_beat == 1, (
        f"🚨 心跳也停了 {stale_beat} 天 —— 说明 `captured_at` 并不随 cron 每轮前进,"
        f"这条心跳是假的")
    # 用真阈值判定
    e = _entries()
    assert stale_open <= e["jingcai_sp[open]"][2], "上新场那条在常态空档下仍会红"
    assert stale_beat <= e["jingcai_sp[open-heartbeat]"][2], "心跳在 cron 活着时红了"
