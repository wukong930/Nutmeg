"""开球闸 + 数据陈旧标(2026-08-03)。

## 起因

owner 问「串关构造器要不要加个刷新」。查下来:**已经有一个**(甜区榜标题那个 ↻
调 `_sweetBoardRefresh()`,同一次调用重建榜和构造器),再加一个是重复。

但查的过程里撞见真问题:**后端只在抓取那一刻过滤已开球的场**
(`min_kickoff_buffer_minutes=5`,routes.py 三处),而 `_isJcBettable` 原来
**只看竞彩 SP 字段在不在、完全没有时间概念**。⇒ 一个开着不动的页面会随时间静默
变陈旧:早上 9 点打开、晚上 11 点再看,20 点已开球的场仍在池里、仍被推荐进串关,
还连累「只串同一天」(最近一期永远停在今天)。

## ⭐ 为什么加按钮修不了

按 ↻ 只是拿**同一份陈旧的 `_SPCALC.preds`** 重跑**同一个过滤** —— 已开球的场
还在,答案一模一样,却让人以为按过就是新的。**闸必须在过滤里,不在按钮里。**
这正是本仓反复记的那族:一个看起来在处理陈旧、实际前提对不上的控件。

陈旧标(③)是**知情**不是**防护**:它只让「该不该去重取」有依据。
"""
from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"
#: 后端 routes.py 三处 `_gather_rows(..., min_kickoff_buffer_minutes=5)`。
#: 前端镜像它 —— 改一处必须改两处(同 `_FRZ_COEF` ↔ `FREEZE_SIGMA_COEF` 的规矩)。
BUFFER_MIN = 5


def _js() -> str:
    return DASH.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    js = _js()
    i = js.index(name)
    depth, j, started = 0, i, False
    while j < len(js):
        if js[j] == "{":
            depth += 1
            started = True
        elif js[j] == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:j + 1]
        elif js[j] == ";" and not started:
            return js[i:j + 1]
        j += 1
    return js[i:]


def _run(names: tuple[str, ...], body: str) -> str:
    r = subprocess.run(["node", "-e", "\n".join(_fn(n) for n in names) + "\n" + body],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


#: ⚠️ 2026-08-21 —— `_isJcBettable` 的时间判据抽进了 `_jcKoState`、
#: SP 判据抽进了 `_hasJcSp`(三分区显示层要共用)。harness 必须把依赖一起喂给 node。
#: ⭐ **下面所有断言一字未改** —— 它们现在同时是「抽取没有改变行为」的验收。
_GATE = ("const _JC_KO_BUFFER_MIN", "function _hasJcSp",
         "function _jcKoState", "function _isJcBettable")
_SP = "{jc_home:2,jc_draw:3,jc_away:4}"


def _bettable(minutes_from_now: float | None) -> bool:
    ko = ""
    if minutes_from_now is not None:
        at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=minutes_from_now)
        ko = f", kickoff_utc:'{at.isoformat()}'"
    return _run(_GATE, f"console.log(_isJcBettable({{...{_SP}{ko}}}));") == "true"


def test_already_kicked_off_drops_out_without_any_button() -> None:
    """⭐ 承重:已开球的场自己退出池 —— 不需要刷新、不需要联网、不需要人动手。

    这是本次改动的**全部要点**。开着的页面随时间自愈,靠的是过滤不是按钮。
    """
    assert _bettable(-180) is False, "已开球 3 小时仍算可投注"
    assert _bettable(0) is False, "正好开球仍算可投注"


def test_the_buffer_mirrors_the_backend() -> None:
    """镜像后端的 5 分钟缓冲 —— 竞彩开球前就停售,踩着开球点的场买不到。"""
    assert _bettable(BUFFER_MIN - 1) is False, f"开球前 {BUFFER_MIN-1} 分钟应已剔除"
    assert _bettable(BUFFER_MIN + 5) is True, f"开球前 {BUFFER_MIN+5} 分钟不该剔除"
    assert f"_JC_KO_BUFFER_MIN = {BUFFER_MIN}" in _js(), "缓冲常数和后端对不上"
    routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text(encoding="utf-8")
    assert f"min_kickoff_buffer_minutes={BUFFER_MIN}" in routes, (
        "后端的缓冲改了而前端没跟 —— 两处必须同值")


def test_no_kickoff_time_is_kept_not_guessed() -> None:
    """⚠️ 判不了就不判:`kickoff_utc` 缺失(实测 2.6%)⇒ **保留**。

    方向是刻意选的:多留一条可能过期的,你在投注站会发现;
    静默吞掉一条能买的,你永远不知道错过了什么。
    """
    assert _bettable(None) is True, "没有开球时刻的场被误剔了"


def test_the_gate_lives_in_the_shared_filter_not_in_the_parlay_pool() -> None:
    """⭐ 闸放在共享 sink,三个消费者一起受益(全局榜+构造器 / 近期赛事分组 /
    竞彩价年龄标)。逐个消费者打补丁 = Altitude 那条老教训。"""
    js = _js()
    assert js.count("function _isJcBettable") == 1
    assert js.count("_isJcBettable(") >= 4, "共享 sink 的消费者变少了?"
    assert "kickoff_utc" not in _fn("function _parlayPool"), (
        "开球闸被下沉到了 _parlayPool —— 那样只有构造器受益,榜和分组还是陈旧的")


# ------------------------------------------------------------ 陈旧标


def _age(sp: str, cup: str) -> str:
    return _run(("function _parlayDataAge",),
                f"let _SPCALC={sp}, _CUPMKT={cup};"
                "console.log(String(_parlayDataAge() === null ? 'null' : 'AGE'));")


def test_data_age_only_counts_sources_that_fed_the_pool() -> None:
    """⚠️ preds 为空的源(杯赛 tab 从没打开过)对候选池零贡献 ⇒ 它的抓取时刻无关。

    第一版要求「两个源都有 fetchedAt」,那会让标签**永远不显示** —— 比不准更坏。
    """
    assert _age("{preds:[{}],fetchedAt:Date.now()}", "{preds:[]}") == "AGE"
    assert _age("null", "null") == "null"
    assert _age("{preds:[],fetchedAt:Date.now()}", "{preds:[]}") == "null", (
        "池子本来就空还标了个年龄")


def test_has_data_but_no_timestamp_shows_nothing_rather_than_the_other_source() -> None:
    """⛔ 承重:「我不知道」和「刚取的」必须长得不一样。

    ⭐ 这条是踩出来的:第一版 `filter(Boolean)` 之后取剩下那个 —— 注释写着
    「不拿另一个源顶替」,**代码却正是在顶替**。端到端跑一遍才发现。
    """
    assert _age("{preds:[{}]}", "{preds:[{}],fetchedAt:Date.now()}") == "null"


def test_age_takes_the_older_source() -> None:
    """两源都供料时取**较旧**的 —— 和 `jc_captured_at` 取 min(stamps) 同一个保守口径。"""
    out = _run(("function _parlayDataAge",),
               "let _SPCALC={preds:[{}],fetchedAt:Date.now()-600000},"
               "    _CUPMKT={preds:[{}],fetchedAt:Date.now()-60000};"
               "console.log(Math.round(_parlayDataAge()/60000));")
    assert int(out) == 10, f"没取较旧的那个,得到 {out} 分钟"


def test_the_age_label_says_it_is_not_the_protection() -> None:
    """⛔ 文案必须说破:标签是**知情**,防陈旧靠的是开球闸。

    否则它就变成又一个「看起来在处理陈旧」的摆设 —— 正是这次要避免的东西。
    """
    js = _js()
    assert "pb_age:" in js and "pb_age_tip:" in js
    tip = js[js.index("pb_age_tip:"):][:700]
    assert "开球闸" in tip and "不需要你按任何按钮" in tip, "没说清真正防陈旧的是什么"
