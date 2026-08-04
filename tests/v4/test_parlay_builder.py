"""2026-08-02 — 串关构造器:owner「怎么串一直困扰我」。

## 它为什么只能长这样

串关 EV 是**恒等式** `∏(1+EVᵢ) − 1`。所以构造器只做两件事:选腿、乘起来。
选腿的规则不是品味,是当天审计出来的三条:

① **只认下界 `evLo`,不认点估 EV** —— 实测赢家诅咒(13,031 场 / 38,511 腿):
     不筛           校准 **+0.00pp**(P 本身是准的)
     点估 EV≥0      −2.58pp(t=−2.11)· 实测 ROI −6.3%
     点估 EV≥+5%    显示均值 +9.1% **兑现成 −7.6%**
     点估 EV≥+10%   实测 **−27.9%**   ← 门槛越高越差
     下界 evLo≥+5%  实测 **−4.7%**    ← 全场最好
   按估计值挑就是挑估计偏高的;下界是收缩估计量。**这条一旦被改回点估,
   构造器就变成一台专挑高估腿的机器 —— 所以钉死在测试里。**

② **每场只出一条腿** —— 竞彩混合过关禁止同场两腿(owner 那张 3 串 1 里同场
   两个选择被拆成 2 注,不是 1 注)。

③ **同联赛要警告** —— 2026-08-02 美职联 6 场 4 平(+2.59 SD),一次事件杀 4 条腿。
   串关联合概率默认独立,相关腿的真实概率更低。

## ⭐ 最容易出的诚实性 bug

全正腿相乘时,**3 串的理论 EV 必然高于 2 串**((1.09)(1.07)(1.06) > (1.09)(1.07))。
只把「历史实测」放小节标题的话,用户逐行扫下来看到的是「串越多理论越高」,
和实测(2串 −9.2% / 3串 −13.4%)正好相反。所以**每一行都必须并排显示实测**。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _src() -> str:
    return DASH.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    """抠出一个函数体(按花括号配平)。"""
    s = _src()
    i = s.index(f"function {name}(")
    d, j = 0, s.index("{", i)
    for k in range(j, len(s)):
        if s[k] == "{":
            d += 1
        elif s[k] == "}":
            d -= 1
            if not d:
                return s[i:k + 1]
    raise AssertionError(f"{name} 没配平")


def test_pool_has_no_floor() -> None:
    """⭐ 承重断言:池**不许**设 EV 地板 —— owner 要的是「今天这几场里的最优组合」。

    v119 曾闸在 evLo≥+5%,结果 873 个比赛日只有 11 天(1.3%)凑得出 2 串 = 等于没有。
    而且实测**加地板会变差**(每场最优腿 → ∏(1+evLo) 最大组合):

        地板    2串 ROI            3串 ROI
        无      **−12.5%**±10.6    **−25.2%**±17.6   ← 最好
        −5%       −10.4%±15.2        −43.8%±23.5
         0%       −42.9%±25.2       −100%   (n=34)
        +5%     −100%   (n=11)      −100%   (n=2)

    筛得越狠,选中的越是被高估的腿(赢家诅咒)。**谁想加回地板,先看这张表。**

    ⚠️ 2026-08-03 收窄了断言。原来写的是「源码里不许出现 `filter(`」—— 那是拿
    「有没有过滤」当「有没有地板」的替身,太粗:加同期过滤(按开球日分组,和 EV
    无关)时它就误报了。承重的是**不许按 EV/evLo 设阈值**,不是不许过滤。
    替身式断言的代价不是这次的误报,是下次:一个不停误报的护栏,最后会被人删掉。
    """
    body = _fn("_parlayPool")
    assert "_boardLegs(pr, idx, mode)[0]" in body, "池不是每场取最优一条"
    assert "_PARLAY_MIN_EVLO" not in _src(), "地板常量残留"
    # 池里任何拿 ev/evLo 和一个数比大小的地方 = 地板
    floor = re.findall(r"(ev(?:Lo)?\s*[<>]=?\s*[-\d.]|[-\d.]\s*[<>]=?\s*l?\.?ev(?:Lo)?\b)", body)
    assert not floor, f"候选池按 EV 设了阈值 = 地板:{floor}"


def test_ranking_uses_lower_bound_not_point_estimate() -> None:
    """排序仍必须走 `evLo`(收缩估计量),不是点估 —— 这条没变。"""
    body = _fn("_parlayCombos")
    assert "a * (1 + l.evLo)" in body and "sort((a, b) => b.evLo - a.evLo)" in body


def test_one_leg_per_match() -> None:
    """竞彩混合过关禁止同场两腿 —— 池里每场只能留最优的一条。"""
    body = _fn("_parlayPool")
    assert "[0]" in body, "没有取每场第一条(每场应只出一条腿)"
    assert "pool.push" in body and body.count("pool.push") == 1


def test_combo_ev_is_the_product_identity() -> None:
    """EV_串 = ∏(1+EVᵢ) − 1。写成加法或平均都是错的。"""
    body = _fn("_parlayCombos")
    assert "reduce((a, l) => a * (1 + l.evLo), 1) - 1" in body, "判闸口径不是乘积"
    assert "reduce((a, l) => a * l.sp, 1)" in body, "赔率不是乘积"


def test_ranked_by_lower_bound_not_point_estimate() -> None:
    body = _fn("_parlayCombos")
    assert "sort((a, b) => b.evLo - a.evLo)" in body, "组合排序键不是下界"


def test_same_league_combo_is_flagged() -> None:
    """相关腿:一次事件可以同时杀掉多条腿,联合概率比算出来的低。"""
    body = _fn("_parlayCombos")
    assert "new Set(lg).size < lg.length" in body, "没检测同联赛"
    assert "c.dup ?" in _fn("_parlayBuilderHtml"), "同联赛没渲染警告"


def test_theoretical_ev_is_never_the_only_unqualified_number() -> None:
    """⚠️ **本条 2026-08-04 由 owner 的显式要求改写,原护栏已退役 —— 留档如下。**

    原护栏叫 `test_historical_realized_appears_on_every_combo_row`,理由是:
    「全正腿相乘时 3 串理论 EV **必然**高于 2 串 —— 只在小节标题写实测,逐行扫
    下来的结论会和实测反过来。所以每行都要并排显示。」

    owner 要求把「· 历史实测 −12.5%」和档位标题那串统计**一起**收进 ⓘ(理由是
    版面太挤)。⇒ 票行上现在**只剩理论 EV 一个数**,而它正是原护栏点名的那个
    会把人带反的数。**这不是护栏过期,是护栏守的东西被有意取舍掉了。**

    残余风险(记在这里,免得将来当成 bug 查):**逐行横扫时 3 串看着比 2 串好**,
    而实测是反的(−25.2% vs −12.5%)。

    替代缓解:ⓘ 弹窗**第一句**就是「定注额看历史实测,别看票行上那个理论 EV」,
    并说明名次不预测 ROI。本测试改为钉住**那句指路存在**——
    如果连它都没了,票行上那个会带反人的数就成了唯一信息源,且无人提示。
    """
    body = _fn("_parlayBuilderHtml")
    rows = body[body.index("pb_odds"):body.index("</details>")]
    assert "pb_theo" in rows, "票行连理论 EV 都没有了?"
    assert "_PARLAY_BACKTEST" not in rows, (
        "历史实测又回到票行了 —— 若是有意恢复,请连同本测试的理由一起改回")
    src = DASH.read_text(encoding="utf-8")
    hits = re.findall(r"pb_stats_caveat:\s*'((?:[^'\\]|\\.)*)'", src)
    assert len(hits) >= 2, f"pb_stats_caveat 中英双语没齐(找到 {len(hits)} 条)"
    for body_text in hits:
        assert ("定注额" in body_text or "Size stakes" in body_text), (
            "ⓘ 里没有「按历史实测定注额、别按理论 EV」那句指路 —— "
            "票行上唯一可见的数会把人带反,而且没有任何提示")


def test_backtest_constants_match_the_measurement() -> None:
    """⚠️ 2026-08-03 换过一次:去掉地板后**选法变了,人口也就变了**,
    旧常数(−4.7/−9.2/−13.4,在 evLo≥+5% 人口上测)不能再用 ——
    那正是「统计量必须在会下注的人口上算」那条红线。新数来自
    「每场最优腿 → 最优组合」873 个比赛日:−5.2 / −12.5 / −25.2。

    ⚠️ 同日二次收窄:原来的正则把「恰好三档」焊死在字面量里,加 4 串时整条测试
    崩在「结构变了」,而真正该守的 1/2/3 三个数**一个都没被检查到** —— 一条把
    格式和内容绑死的断言,在格式合法变化时不是变严,是变瞎。
    改成按档取值:加档不该弄红它,**改数**才该。4 串另钉在
    `test_parlay_4leg_sameday.py`。
    """
    s = _src()

    def tier(name: str) -> dict:
        m = re.search(rf"const {name} *= *\{{([^}}]*)\}}", s)
        assert m, f"{name} 不见了"
        return {int(k): float(v) for k, v in re.findall(r"(\d+): *(-?[\d.]+)", m.group(1))}

    b = tier("_PARLAY_BACKTEST")
    assert [b[k] for k in (1, 2, 3)] == [-0.052, -0.125, -0.252]
    n = tier("_PARLAY_BACKTEST_N")
    assert [int(n[k]) for k in (1, 2, 3)] == [873, 750, 648], "样本量没跟着换"
    # ⚠️ 2026-08-03 换过一次:随机基线从**解析值**换成**实测值**。
    # 旧值 (1/1.1294)^k−1 = −11.5/−21.6/−30.6,假设抽水在三条腿上均摊 ——
    # 而我们实测过它不是(热门腿吃 60% 抽水)。真跑一遍(每个比赛日随机取腿
    # ×200 次、按真实赛果结算、SE 按**比赛日**聚类)得 −12.7/−25.2/−31.9/−44.7:
    # **真实随机比解析线更差** ⇒ 旧尺子把构造器自己的净提升低估了 1.2-6.2pp。
    # 这条测试当时红了 —— 红得对,它就是为「有人动了基线」立的。详见
    # test_parlay_picks.py::test_random_baseline_is_the_measured_one_not_the_analytic。
    r = tier("_PARLAY_RANDOM")
    assert [r[k] for k in (1, 2, 3)] == [-0.127, -0.252, -0.319], (
        "随机腿基线变了 —— 它是 873 个比赛日的**实测**随机取腿 ROI,是那把尺子")


def test_note_says_it_will_not_be_positive() -> None:
    """⛔ 「不会给正数」必须留着 —— 长文进了 ⓘ 弹窗,**但一句摘要仍要在卡面上**。

    2026-08-03 owner:「提示类文案看起来很累,用图标代替」。搬进弹窗是对的,
    但整句搬走就等于默认没人点 ⓘ。所以长版进 `pb_note`(弹窗),
    卡面留 `pb_note_short` 一行 —— 两边都钉。
    """
    s = _src()
    assert "它不会给你正数" in s, "弹窗正文删掉了「不会给正数」"
    assert "will NOT hand you a positive number" in s, "英文弹窗删掉了同一句"
    assert "⚠️ 不会给正数" in s, "卡面摘要没留「不会给正数」"
    assert "Never positive" in s, "英文卡面摘要同上"


def test_long_notes_moved_into_the_info_modal() -> None:
    """长文案走**已有的** `showInfo` 弹窗,不另造一套提示机制(Reuse)。"""
    s = _src()
    body = _fn("_parlayBuilderHtml")
    assert "showInfo(t('pb_hdr'), t('pb_note'))" in body, "卡头 ⓘ 没接弹窗"
    assert "showInfo(t('pb_dup'), t('pb_dup_body'))" in body, "同联赛 ⓘ 没接弹窗"
    assert "showInfo(t('pb_1x'), t('pb_1x_note'))" in body, "单关注记 ⓘ 没接弹窗"
    assert "function showInfo(" in s, "复用的 showInfo 不见了"


def test_header_info_icon_does_not_toggle_the_fold() -> None:
    """⚠️ ⓘ 在 `<summary>` 里 —— 不拦事件的话点它会顺手折叠整张卡。"""
    body = _fn("_parlayBuilderHtml")
    i = body.index("showInfo(t('pb_hdr')")
    seg = body[max(0, i - 160):i]
    assert "preventDefault()" in seg and "stopPropagation()" in seg, (
        "卡头 ⓘ 没拦 summary 的默认折叠")


def test_single_leg_reference_is_rendered_first() -> None:
    """⭐ 单关 −5.2% 是实测最优,必须**排在组合上面**。

    光靠文字压不住「3 串理论 EV 更高」的视觉暗示(v119 踩过一次):全正腿相乘时
    理论值单调上升,而实测单调下降。把最好的那个选项摆在第一行,让两种排序在
    同一屏上对峙。
    """
    body = _fn("_parlayBuilderHtml")
    assert "const solo" in body and "${solo}${block(2)}${block(3)}" in body, (
        "1 串参考没有排在 2/3 串前面")
    assert "pb_1x_note" in body or "pb_1x_note" in _src(), "没说明让球腿买不到单关"


def test_both_locales_have_all_new_keys() -> None:
    s = _src()
    for key in ("pb_hdr", "pb_note", "pb_note_short", "pb_info_tip",
                "pb_1x", "pb_1x_note", "pb_1x_tag", "pb_2x", "pb_3x", "pb_hist",
                "pb_rand", "pb_odds", "pb_theo", "pb_dup", "pb_dup_body"):
        assert s.count(f"{key}:") == 2, f"{key} 不是中英各 1 次"


def test_icon_exists_in_the_sprite() -> None:
    """sprite 里没有的图标 `IC()` 渲染成空 svg 且不报错(v118 踩过)。"""
    s = _src()
    for name in re.findall(r"IC\('([a-z-]+)'\)", s):
        assert f'<symbol id="ic-{name}"' in s, f"IC('{name}') 没有对应 symbol"


def test_gate_untouched() -> None:
    """⛔ 构造器是纯计算 —— +5% 闸、甜区榜排序、绿灯口径一个都不许动。"""
    s = _src()
    assert "lg.evLo >= 0.05 ? '#059669'" in s, "甜区榜绿灯阈值被改了"
    assert "rows.sort((a, b) => b.best.evLo - a.best.evLo)" in s, "甜区榜排序被改了"


def test_fe_version_is_well_formed() -> None:
    """前端改动要 bump `_FE_VERSION`(service worker 靠它清旧缓存)。

    ⚠️ 2026-08-02 改写。原版**钉死字面量**(`== "nutmeg-v118-…"`),结果下一次
    前端改动 bump 到 v119 时,它就以一个和自己毫无关系的理由变红 —— 我还在新写的
    v119 测试里把同样的错抄了一遍。**版本号是全局递增量,任何按功能分文件的测试
    都不该钉它的字面值。**

    静态测试根本无法验证「这次提交 bump 了没有」(它看不见上一次的值)。能验证的
    只有格式合法,于是就只验证格式;「记得 bump」属于评审纪律,不属于单测。
    """
    routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text(encoding="utf-8")
    m = re.search(r'_FE_VERSION = "([^"]+)"', routes)
    assert m, "_FE_VERSION 不见了"
    assert re.fullmatch(r"nutmeg-v\d+-fe-[a-z0-9-]+", m.group(1)), m.group(1)
