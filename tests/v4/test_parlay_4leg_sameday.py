"""串关构造器:4 串 + 只串同一天(2026-08-03)。

## 两件事,来源完全不同 —— 测法也不同

**4 串**是 owner 问「周末几十场能不能放大到 4 串」时**补测出来的**:
n=550,ROI −30.4% ±33.5pp,命中率 1.1%。它是一个数,测它只要钉住「这个数没被
人顺手改掉、且展示时没漏掉命中率」。

**只串同一天**是 owner 的判断,**不是我测出来的效应** —— 我明确告诉过他:档案里
只有终盘价,没有「D−2 时刻的竞彩价」,按终盘距开球分箱 ROI 也分不出来
(<6h −12.3% vs >48h −12.3%),那测的是终盘新鲜度不是提前几天下注。所以这里
**不测它有没有用**(测不了),只测它**按正确的边界切**。

## ⭐ 而「正确的边界」我一开始就写错了

第一版按**日历天**分组。写完顺手拿 `jingcai_vote` 的 `match_num`(竞彩自己的
期号,周一001)对开球时刻一验,发现:

    北京 00:00–11:59 开球 → 期号 = 前一日   123 场
    北京 18:00–23:59 开球 → 期号 = 当日     105 场
    228 场,零例外

**竞彩的一天在北京 12:00 换日,不是午夜。** 周日 22:00 那场和周一 03:00 那场是
**同一期**,日历天分组会把 54% 的场次劈错边 —— 而且劈错的方式很隐蔽:界面照常
出票,只是少了一半本该可串的组合,没有任何东西会喊。

本文件把那次测量钉死。谁把它「简化」回 `getDate()` 就红。

⚠️ 换日点落在 [12:00, 18:00) 的哪一点**没测出来**(样本是 7 月世界杯,全欧美夜场,
这个窗口空的)。取 12:00 的依据是晨批实测 09:24–09:44 —— 当天早上才发布的名单
装不下 10 点开球的场。这是个**有依据的选择,不是测量结果**,下面显式标注。
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"

#: 4 串实测(2026-08-03)。改这里必须重跑回测,不许「凑一个像样的数」。
#: ⚠️ 同日 `random` 从 −0.385 改成 −0.447:那一位原来是**解析值** (1/1.1294)^4−1,
#: 后来换成 873 个比赛日的**实测**随机取腿 ROI(解析式假设抽水三腿均摊,
#: 实测不是 —— 热门腿吃 60%)。其余四个数没动,它们本来就是实测的。
#: 详见 test_parlay_picks.py::test_random_baseline_is_the_measured_one_not_the_analytic。
FOUR_LEG = {"roi": -0.304, "se": 0.335, "n": 550, "random": -0.447, "hit": 0.011}


def _js() -> str:
    return DASH.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 4 串


def test_four_leg_constants_are_the_measured_ones() -> None:
    js = _js()
    for name, key, val in (
        ("_PARLAY_BACKTEST", "roi", FOUR_LEG["roi"]),
        ("_PARLAY_BACKTEST_SE", "se", FOUR_LEG["se"]),
        ("_PARLAY_BACKTEST_N", "n", FOUR_LEG["n"]),
        ("_PARLAY_RANDOM", "random", FOUR_LEG["random"]),
        ("_PARLAY_HIT", "hit", FOUR_LEG["hit"]),
    ):
        m = re.search(rf"const {name} *= *\{{([^}}]*)\}}", js)
        assert m, f"{name} 不见了"
        got = re.search(r"4: *(-?[\d.]+)", m.group(1))
        assert got, f"{name} 缺 4 串这一档"
        assert float(got.group(1)) == pytest.approx(val), (
            f"{name}[4] = {got.group(1)},实测是 {val}({key})")


def test_the_ladder_stays_monotonically_worse() -> None:
    """⭐ 承重:每加一条腿都更差 —— 1 > 2 > 3 > 4。

    这是整个构造器唯一的诚实结论。若哪天有人把 4 串的数字调好看了,或者插进一档
    「4 串比 3 串好」,这条会红。页面上「理论 EV 随腿数上升」的视觉暗示很强,
    只有实测阶梯压得住它。
    """
    m = re.search(r"const _PARLAY_BACKTEST *= *\{([^}]*)\}", _js())
    vals = {int(k): float(v) for k, v in re.findall(r"(\d+): *(-?[\d.]+)", m.group(1))}
    ks = sorted(vals)
    assert ks == [1, 2, 3, 4], ks
    for a, b in zip(ks, ks[1:], strict=False):
        assert vals[a] > vals[b], f"{a} 串 {vals[a]} 不比 {b} 串 {vals[b]} 好 —— 阶梯断了"


def test_hit_rate_is_rendered_next_to_every_tier() -> None:
    """4 串命中率 1.1% = 平均 91 张中 1 张。**不显示它就是骗人**:
    只看 ROI 会以为「−30% 而已」,看不见「90 次都是零」。"""
    js = _js()
    assert "t('pb_hit')" in js, "小节标题没渲染命中率"
    assert "_PARLAY_HIT[k]" in js, "命中率不是按档取的"


def test_four_leg_block_carries_its_own_warning() -> None:
    """1.1% 必须当场说破,不能只躺在总说明的第三段里。"""
    js = _js()
    assert "k >= 4 ?" in js, "4 串没有专属警示分支"
    for key in ("pb_4x", "pb_4x_tag", "pb_4x_note"):
        assert f"{key}:" in js, f"i18n 缺 {key}"
    zh = js[js.index("pb_4x_note:"):][:1400]
    assert "1.1%" in zh and "91" in zh, "4 串说明没写命中率/几张中一张"


def test_four_leg_is_actually_rendered() -> None:
    assert "${solo}${block(2)}${block(3)}${block(4)}" in _js(), "4 串没接进渲染"


def test_pool_cap_can_still_feed_four_legs() -> None:
    """C(12,4)=495 —— 池上限得够 4 串枚举,否则这一档永远空着还不报错。"""
    cap = int(re.search(r"const _PARLAY_POOL_CAP *= *(\d+)", _js()).group(1))
    assert cap >= 4, cap


# ------------------------------------------------- 只串同一天 = 同一期


#: ⭐ 2026-08-03 实测锚点。(北京时刻, 期号是否 == 开球当日)
#: 前 6 条来自「归前一日」的 6 个小时段,后 3 条来自「归当日」的 3 个。
ROLLOVER_ANCHORS = [
    ("2026-08-04T00:30+08:00", "08-03"),
    ("2026-08-04T03:00+08:00", "08-03"),
    ("2026-08-04T05:00+08:00", "08-03"),
    ("2026-08-04T07:00+08:00", "08-03"),
    ("2026-08-04T09:00+08:00", "08-03"),
    ("2026-08-04T11:59+08:00", "08-03"),
    ("2026-08-04T18:00+08:00", "08-04"),
    ("2026-08-04T21:00+08:00", "08-04"),
    ("2026-08-04T23:30+08:00", "08-04"),
]


def _run_node(body: str) -> str:
    """把 dashboard 里的几个纯函数抠出来在 node 里跑。

    抠而不是整页加载:整页要 DOM。抠的代价是「抠错了函数也会绿」,所以下面
    `test_the_extracted_snippet_is_the_real_one` 反过来钉住抠的是不是真源码。

    ⭐ `_kickoffMs` **必须抠真的,不许写替身** —— 这条是踩出来的:第一版给它写了
    个两行假货 `new Date(pr.kickoff_utc).getTime()`,结果把 `_parlayDay` 里的
    `!pr.kickoff_utc` 守卫**删掉,测试照样全绿**。因为真货有一条兜底
    (`pr.date` → 当日 23:59:59 本地),假货没有 —— 而那条兜底正是守卫存在的
    全部理由。替身抹掉了要测的前提,于是检查和它的前提又一次对不上。
    """
    js = _js()
    out = []
    for anchor in ("const _JC_DAY_ROLLOVER_H", "function _kickoffMs(pr)",
                   "function _parlayDay(pr)"):
        i = js.index(anchor)
        depth, j, started = 0, i, False
        while j < len(js):
            if js[j] == "{":
                depth += 1
                started = True
            elif js[j] == "}":
                depth -= 1
                if started and depth == 0:
                    j += 1
                    break
            elif js[j] == ";" and not started:
                j += 1
                break
            j += 1
        out.append(js[i:j])
    src = "\n".join(out) + "\n"
    r = subprocess.run(["node", "-e", src + body], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.mark.parametrize("ko,expect", ROLLOVER_ANCHORS)
def test_matchday_key_reproduces_the_measured_rollover(ko: str, expect: str) -> None:
    """⭐ 承重:竞彩期 = 北京时刻回拨 12h 的日期。

    实测口径:`jingcai_vote.match_num`(周一001)vs 开球时刻,228 场零例外 ——
    00:00–11:59 归前一日、18:00–23:59 归当日。按日历天分组会劈错 54%。
    """
    utc = dt.datetime.fromisoformat(ko).astimezone(dt.UTC).isoformat().replace("+00:00", "Z")
    got = _run_node(f'console.log(_parlayDay({{kickoff_utc: "{utc}"}}))')
    assert got == expect, (
        f"北京 {ko} 应属 {expect} 期,得到 {got} —— "
        "有人把分组键改回日历天了?见本文件顶部的实测表")


def test_calendar_day_grouping_would_fail_these_anchors() -> None:
    """⚠️ 变异检验:证明上面那组锚点**分得开**两种实现。

    没有这条,若 `_parlayDay` 退化成 `getDate()`,只要锚点恰好都在同一天,
    上面 9 条仍会全绿 —— 一个测不出目标差异的测试是最坏的一种绿。
    """
    diff = [ko for ko, exp in ROLLOVER_ANCHORS
            if dt.datetime.fromisoformat(ko).strftime("%m-%d") != exp]
    assert len(diff) == 6, f"只有 {len(diff)} 条锚点能区分日历天/竞彩期,太少"


def test_matches_without_a_kickoff_time_are_excluded() -> None:
    """无开球时刻 ⇒ null ⇒ 不进同期票。

    `_kickoffMs` 对这种场会兜底成「当日 23:59:59 **本地**」—— 那是个猜,
    还是个跟着浏览器时区变的猜。拿它当分组键 = 在票里塞一条「不知道什么时候踢」
    的腿,而界面上看不出来。宁可少一条。

    ⚠️ 这条测的是**守卫**,所以 `_run_node` 必须跑真的 `_kickoffMs`(见其 docstring):
    只有真货有那条兜底,守卫删掉才会真的变绿→变红。
    """
    # 先证明兜底确实会给出一个「看着挺像样」的数 —— 否则这条守卫无从谈起
    assert _run_node(
        'console.log(Number.isFinite(_kickoffMs({date: "2026-08-04"})))') == "true"
    assert _run_node('console.log(String(_parlayDay({date: "2026-08-04"})))') == "null"
    assert _run_node("console.log(String(_parlayDay(null)))") == "null"


def test_the_extracted_snippet_is_the_real_one() -> None:
    """上面几条是把源码抠出来跑的 —— 钉住抠到的确实是那两段,不是别处的同名代码。"""
    js = _js()
    assert js.count("function _parlayDay(pr)") == 1
    assert js.count("const _JC_DAY_ROLLOVER_H") == 1
    assert "_parlayDay(pr)" in js[js.index("function _parlayPool"):][:900], (
        "池没有在用 _parlayDay 当分组键")


def test_the_unmeasured_window_is_documented_not_hidden() -> None:
    """⛔ [12:00,18:00) 没有样本 —— 这个洞必须写在代码和界面上。

    「分不出没测过和测过没事」正是本项目反复踩的那个洞;把一个有依据的**选择**
    写得像**测量结果**,下次读代码的人(我)就会拿它当地基。
    """
    js = _js()
    src = js[js.index("//: ⭐ 竞彩「期」"):js.index("const _JC_DAY_ROLLOVER_H")]
    assert "没测出来" in src and "[12:00, 18:00)" in src, "代码注释没标注未测窗口"
    note = js[js.index("pb_sameday_note:"):][:2200]
    assert "没测出来" in note, "界面说明没标注未测窗口"


def test_the_toggle_is_on_by_default_and_persists() -> None:
    js = _js()
    assert "!== '0'" in js[js.index("function _parlaySameDay"):][:260], "默认不是开的"
    assert "_LS_PARLAY_SAMEDAY" in js and "localStorage" in js
    assert "_sweetBoardRefresh()" in js[js.index("function _parlaySetSameDay"):][:300], (
        "切换开关没触发重排")


def test_day_distribution_is_always_visible() -> None:
    """同期开关挡掉了什么必须看得见 —— 静默少几场就是又一个假的「就这些」。"""
    js = _js()
    assert "_parlayDayCounts" in js
    assert "pb_sameday_excl" in js
    assert "|| '?'" in js[js.index("function _parlayDayCounts"):][:400], (
        "无开球时刻的场没有单列出来")


def test_the_note_does_not_claim_same_day_was_measured() -> None:
    """⛔ 红线:这条是 owner 的判断,我**测不出**它有没有用。

    界面若把它写成「实测有效」,就是我用一个没做过的测量给决策背书。
    可以写「换日点是实测的」(那确实测了),不能写「同日过滤是实测有效的」。
    """
    js = _js()
    note = js[js.index("pb_sameday_note:"):][:2200]
    zh = js[js.index("pb_note:"):][:6000]
    assert "这条规则本身有没有用我测不出来" in zh, "总说明没声明这条未经检验"
    assert "−12.3%" in zh or "-12.3%" in zh, "没给出那个分不出来的分箱结果"
    assert "零例外" in note, "换日点的实测依据没写"


def test_fe_version_was_bumped_for_this_change() -> None:
    """前端改动必须 bump —— 否则 service worker 会拿旧壳。

    ⚠️ 静态测试**无法**验证「这次提交 bump 了」,只能验格式(v118 那次我就是
    钉了字面量,下次改动它自己红)。所以这里只钉「还在、还是 nutmeg-v<N>- 形状」。
    """
    routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text(encoding="utf-8")
    m = re.search(r'_FE_VERSION = "(nutmeg-v\d+-[a-z0-9-]+)"', routes)
    assert m, "_FE_VERSION 不见了或格式变了"


def test_same_day_filter_never_makes_the_card_vanish_silently() -> None:
    """⭐ 承重:同期开关把腿数压到 1 时,卡片**必须还在**。

    第一版是 `if (pool.length < 2) return ''` —— 最近一期只有 1 场、明天有 8 场时,
    整张构造器**静默消失**:用户看不到开关(没法关掉它)、看不到日分布(不知道
    明天有 8 场)、也不知道是过滤干的还是今天真没得下。

    「真的没腿」和「被我自己的过滤挡住」长得一模一样 —— 这是本项目反复踩的
    「分不出没有和没去看」。两种情况必须分开:前者不出卡,后者出壳 + 说破。
    """
    js = _js()
    assert "blockedBySameDay" in js, "没有区分「真没腿」和「被同期挡住」"
    assert "pb_sameday_empty" in js, "被挡时没有给出解释文案"
    seg = js[js.index("function _parlayBuilderHtml"):][:900]
    assert "!blockedBySameDay" in seg, "被挡住时仍然直接 return '' 了"
    note = js[js.index("pb_sameday_empty:"):][:400]
    assert "取消勾选" in note, "没告诉用户怎么解除"


def test_the_pool_badge_shows_what_was_filtered_out() -> None:
    """徽章上的数字是过滤**后**的 —— 只显示它会让人以为今天就这么几场。"""
    js = _js()
    seg = js[js.index("${pool.length}"):][:200]
    assert "rawTotal" in seg, "池徽章没显示「过滤后/总数」"
