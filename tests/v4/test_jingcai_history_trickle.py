"""竞彩历史涓流:**终点必须跟着今天走**(2026-07-31)。

⚠️ 病史 —— 这条测试是为一个已经发生过的、10.5 个月的静默数据洞写的:

`scripts/jingcai_history_trickle.py` 的 `END` 原本硬编码成 `dt.date(2025, 7, 31)`
(预注册 §H 的窗口)。涓流扫完那天就再也不往前走;而观测库 `jingcai_sp` 从
2026-06-11 才开始 ⇒ **2025-07-28 → 2026-06-10 两边都没有**。

最坏的部分不是丢数据,是**没有任何东西会喊**:游标照常绕回起点 re-sweep、
`skip_existing` 让每轮都便宜、日志天天绿。直到 owner 问「2026-05-30 神户那场
当时 EV 多少」才发现 —— 2,600 场 × 13 联赛,一场都没有。

⇒ **一个「扫完历史」的任务,终点一旦写成常量,就是在给未来挖一个静默的洞。**
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "scripts/jingcai_history_trickle.py"


def _load():
    spec = importlib.util.spec_from_file_location("_trickle", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_end_tracks_today_not_a_frozen_constant():
    """⭐ 核心不变式:终点是**算出来的**,且落在今天附近。"""
    mod = _load()
    end = mod._end_date()
    today = dt.date.today()
    assert isinstance(end, dt.date)
    assert end <= today, "终点跑到未来了 —— 会去抓还没打的比赛"
    assert (today - end).days <= 7, (
        f"终点 {end} 距今 {(today - end).days} 天 —— 又冻住了?"
        " 这正是那个 10.5 个月洞的形状")


def test_no_hardcoded_end_date_literal_survives():
    """源码里不许再出现 `END = dt.date(...)` 这种常量终点。

    钉源码而不只钉行为:有人把 `_end_date()` 改回常量、行为测试**当天仍会过**
    (今天恰好落在窗口里),几个月后才裂开 —— 和原来那次一模一样。
    """
    src = SRC.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert not re.search(r"^\s*END\s*=\s*dt\.date\(", body, re.M), (
        "终点又被写成常量了 —— 见本文件 docstring 里那 10.5 个月")
    assert "def _end_date()" in body, "算终点的函数没了"


def test_begin_stays_pinned_at_the_archive_start():
    """起点**应该**是常量 —— 档案就是从 2021-08 开始的,它不该跟着今天漂。"""
    mod = _load()
    assert dt.date(2021, 8, 1) == mod.BEGIN


def test_all_six_proxy_vars_are_cleared_for_the_china_endpoint():
    """中国站要清 **6 个** 代理变量,不是 4 个。

    `ALL_PROXY`/`all_proxy` 同样被 requests/curl 认;只清 4 个,在本机开了
    全局代理时仍会绕道 —— 此前没炸只是因为 launchd 环境本来就干净。
    """
    src = SRC.read_text(encoding="utf-8")
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        assert f'"{v}"' in src, f"没清 {v}"


def test_leagues_is_all_not_just_the_trained_thirteen():
    """⚠️ 2026-07-31 —— 联赛范围必须是**全部**(`None`),不能退回 13 受训联赛。

    第一次修完 END 之后,job 装上、跑通、日志绿 —— 但同一个夏季窗口
    (2026-06-11→17)实测 `in_scope: 0`:欧洲全休赛,13 受训联赛一场没有。
    **洞的形状会从「时间」变成「联赛」** —— 夏天照样空,而夏天正是竞彩卖
    北欧/韩职/巴甲/MLS 的时候,也正是 owner 实际在买的。

    实测代价(同一 7 天窗口):
      · 2026-06-11→17(夏)  trained **0** · all **31**
      · 2026-03-01→07(季中) trained 70  · all 106   ← 只多 1.5×
    改 `None` 后同窗口:in_scope 31 · fetched 31 · rows 376 · failed 0。

    ⭐ 这条防的是一个**比原 bug 更隐蔽**的形状:原 bug 至少「什么都没抓」,
    这个是「抓了、成功了、日志绿了,但抓的是空集」。
    """
    mod = _load()
    assert mod.LEAGUES is None, (
        "涓流又被限回受训联赛了 —— 夏天会抓到 0 场,而日志照样是绿的")


def test_backfill_is_called_with_the_module_level_leagues():
    """⚠️ 常量改了但调用点没跟上 = 改了个寂寞。这条把两者钉在一起。

    (第一次改就踩了:`LEAGUES = None` 写好了,`backfill(...)` 那行还传着
    `TRAINED_LEAGUES_CN` —— 导入没删所以连 NameError 都不报。)
    """
    body = SRC.read_text(encoding="utf-8")
    assert "leagues=LEAGUES" in body, "调用点没用模块级 LEAGUES"
    assert "TRAINED_LEAGUES_CN" not in body.split('"""', 2)[-1].replace(
        "`TRAINED_LEAGUES_CN`", ""), "还在引用受训联赛常量(注释里提及不算)"
