"""标准模式卡片补三件(owner 2026-08-05,欧洲 13 联赛开赛前)。

13 个受训联赛休赛期结束,标准模式重新有内容。逐条验证后发现这张卡有三处「瞎着」:

## B ⭐ 大小球驱动着让球,却完全不可见 —— 本文件的重点

标准模式的 1X2 走**模型 P**,但**让球走 Pinnacle 市场反推**
(`routes.py::_model_board_handicap_lines`:从去vig 的 Pinnacle 1X2 **+ 大小球**
拟合 DC 网格;依据是 4330 场无泄漏 walk-forward)。

⇒ 大小球线在决定你要下注的让球数字,而这张卡上**看不到它**。那条线要是脏的
(非常规盘口、滚球退化价),让球 P 跟着脏,**没有任何察觉的办法**。
`_pinRawHtml` 顺带还带着**水位过宽警告**,标准模式此前一道这类闸都没有。

## A 「竞彩未开盘」和「无 +EV」原来长得一模一样

没腿过闸就一律写「无 +EV(建议 no-bet)」。实测 08-05 的 4 场标准模式赛事
竞彩 SP 全 null,却全部显示成 no-bet —— 一句劝退用在你**根本还买不了**的场次上。
同族:「分不出『没有』和『没去看』」。

## E 净胜球分组

`margin_bands` 一直就在 sp-calc 的返回里(白发了),`_marginBandsHtml` 也是现成的。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _js() -> str:
    return DASH.read_text(encoding="utf-8")


def _card() -> str:
    """标准模式卡片模板 `cardHtml` 的定义体。

    ⚠️ 用**配对括号**抠,不是正则贪婪匹配 —— 第一版用 `.*?` 一次吞掉了 74k 字符
    (等于全文搜索),于是「有没有渲染 X」全部假阳性。范围抠错的断言比没有断言更坏。
    """
    js = _js()
    i = js.index("const cardHtml = (pr, idx) => {")
    depth, j, started = 0, i, False
    while j < len(js):
        if js[j] == "{":
            depth += 1
            started = True
        elif js[j] == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:j + 1]
        j += 1
    raise AssertionError("抠不到 cardHtml")


def _recalc() -> str:
    js = _js()
    i = js.index("function _spcalcRecalc(idx) {")
    return js[i:js.index("\nfunction ", i + 10)]


def _node(src: str) -> str:
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _run_pin_raw(pr: dict) -> str:
    """真跑 `_pinRawHtml(pr)`,把桩打在文案/图标上,数字一律走真实代码。"""
    js = _js()
    i = js.index("function _pinRawHtml(pr) {")
    fn = js[i:js.index("\n}", i) + 2]
    vig = js[js.index("function _bookVig("):]
    vig = vig[:vig.index("\n}") + 2]
    wide = re.search(r"WIDE_BOOK_VIG\s*=\s*([\d.]+)", js).group(1)
    stub = ("const t = k => (k === 'pin_wide' ? 'WIDE' : k.replace('pin_raw_', ''));"
            "const IC = () => '';"
            f"const WIDE_BOOK_VIG = {wide};")
    return _node(f"{stub}\n{vig}\n{fn}\nconsole.log(_pinRawHtml({json.dumps(pr)}));")


def _run_verdict(sp_count: int, pr: dict) -> str:
    """把 `jcOnSale` 的**赋值**和判词三元表达式**一起**抠出来真求值。

    ⚠️ 第一版只抠了三元表达式,`jcOnSale` 由 harness 自己定义 ⇒
    源码里那行赋值被写死成 false 时测试照样绿。**桩把被测的东西替换掉了**,
    同 [[syntactic-proxy-for-semantic-property]] 里那个「测试替身抹掉守卫」。
    现在 pr 是入参,`jcOnSale` 走真实代码。
    """
    body = _recalc()
    assign = re.search(r"(const jcOnSale = [^;]+;)", body)
    expr = re.search(r"verdict\.textContent = (spCount > 0[^;]+);", body, re.S)
    assert assign and expr, "抠不到 jcOnSale 赋值或判词表达式"
    return _node(
        f"const t = k => k; const spCount = {sp_count}; const pr = {json.dumps(pr)};"
        f"{assign.group(1)} console.log({expr.group(1)});")


_JC_ON = {"jc_home": 2.1, "jc_draw": 3.3, "jc_away": 3.4}
_JC_OFF: dict = {"jc_home": None, "jc_draw": None, "jc_away": None}
#: ⚠️ 只有一条腿有价 —— 判据必须是**三条任一**,不能只看主胜。
#: 没有这个夹具时,「只看 jc_home」的写法测不出来(前两个夹具三条腿要么全有要么全无)。
_JC_PARTIAL: dict = {"jc_home": None, "jc_draw": 3.3, "jc_away": None}


class TestOverUnderIsVisible:
    """⭐ B —— 本次改动的主要理由。"""

    def test_card_renders_the_pinnacle_raw_line(self):
        assert "_pinRawHtml(pr)" in _card(), (
            "标准模式卡片没渲染 Pinnacle 原盘 —— 而大小球正驱动着这张卡的让球反推")

    def test_the_rendered_line_actually_contains_the_ou_numbers(self):
        """⚠️ **真跑 `_pinRawHtml`,不是 grep 它的源码。**

        第一版写的是 `assert "psc_over25" in body` —— 变异把渲染代码挪进一个死变量
        (字符串仍在源码里)时它照样绿。**子串存在 ≠ 数字被渲染出来。**
        这是本会话同一形状的第六次,所以这条改成拿真实返回值断言。
        """
        out = _run_pin_raw({"psc_home": 2.25, "psc_draw": 3.57, "psc_away": 2.99,
                            "psc_over25": 1.63, "psc_under25": 2.26, "ou_line": 2.5})
        for want in ("2.25", "3.57", "2.99", "2.50", "1.63", "2.26"):
            assert want in out, f"渲染结果里没有 {want}\n{out}"

    def test_no_ou_degrades_to_1x2_only_without_faking_a_line(self):
        """没有大小球时只出 1X2 —— ⛔ 不许默认一条 2.5 出来充数。
        编一条盘口线比缺一条更坏(同「δ₊₂ 故意不出常数」)。"""
        out = _run_pin_raw({"psc_home": 2.25, "psc_draw": 3.57, "psc_away": 2.99})
        assert "2.25" in out
        assert "1.63" not in out and "OU-MARK" not in out, out

    def test_wide_vig_warning_fires_on_a_wide_book(self):
        """水位闸:标签自称「Pinnacle 原盘」,水位宽到不像 Pinnacle 就得当场喊。
        标准模式此前**一道这类闸都没有**。"""
        narrow = _run_pin_raw({"psc_home": 2.25, "psc_draw": 3.57, "psc_away": 2.99})
        wide = _run_pin_raw({"psc_home": 1.80, "psc_draw": 3.00, "psc_away": 2.60})
        assert "WIDE" not in narrow, f"正常水位误报了\n{narrow}"
        assert "WIDE" in wide, f"宽水位没报警\n{wide}"


class TestNoJcIsNotTheSameAsNoEv:
    """A —— 三态,不是两态。"""

    def test_verdict_has_three_branches(self):
        body = _recalc()
        for key in ("spcalc_nobet", "spcalc_enter_sp", "spcalc_nojc"):
            assert key in body, f"判词少了 {key} 这一态"

    def test_the_branch_keys_on_actual_sp_count_not_on_best(self):
        """⚠️ 判据必须是「填了几个 SP」,不是「有没有腿过闸」。

        用 `best` 判会把「填了 SP 但都不过闸」也说成未开盘 —— 反过来错。
        """
        body = _recalc()
        assert "spCount" in body, "没有统计填了几个 SP"
        assert "spCount > 0 ? t('spcalc_nobet')" in body, \
            "「无 +EV」必须只在**确实填了 SP** 时才说"

    def test_the_three_states_actually_evaluate_differently(self):
        """⚠️ **真求值那个三元表达式**,不是 grep 它。

        第一版写的是 `assert "jc_home != null" in body` —— 变异把 `jcOnSale`
        写死成 false、把原表达式挪进死变量时,它照样绿(字符串还在源码里)。
        改成把表达式抠出来喂 node,三种输入必须给出三个不同的结果。
        """
        no_jc = _run_verdict(0, _JC_OFF).strip()
        cleared = _run_verdict(0, _JC_ON).strip()
        real = _run_verdict(3, _JC_ON).strip()
        assert no_jc == "spcalc_nojc", f"竞彩没上架时说的是 {no_jc!r}"
        assert cleared == "spcalc_enter_sp", f"框被清空时说的是 {cleared!r}"
        assert real == "spcalc_nobet", f"填了 SP 但不过闸时说的是 {real!r}"
        assert len({no_jc, cleared, real}) == 3, "三态没真的分开"
        # 三条腿**任一**有价就算上架 —— 只看主胜会把「只解析出平局价」误判成未开盘
        assert _run_verdict(0, _JC_PARTIAL).strip() == "spcalc_enter_sp", \
            "只有平局有价时被当成竞彩未开盘 —— 判据只看了主胜"

    def test_both_locales_define_the_new_key(self):
        hits = re.findall(r"spcalc_nojc:\s*'((?:[^'\\]|\\.)*)'", _js())
        assert len(hits) == 2, f"中英双语没齐(找到 {len(hits)} 条)"
        assert any("竞彩未开盘" in h for h in hits)
        assert any("竞彩" in h and "listed" in h for h in hits)


class TestMarginBands:
    def test_card_renders_margin_bands(self):
        assert "_marginBandsHtml(pr.margin_bands" in _card(), "标准模式卡片没有净胜球分组"

    def test_handicap_line_is_passed_for_the_cluster_view(self):
        """`_marginBandsHtml` 的第二参用于 `b.margin + L` 分走盘/输赢簇。
        传 null 就只有分组没有簇 —— 那才是这个工具一半的价值。"""
        assert "_marginBandsHtml(pr.margin_bands, pr.jc_hc_line" in _card(), \
            "没把竞彩让球线传进去,净胜球簇不会出现"

    def test_fold_state_helper_is_reused_not_reimplemented(self):
        """`_fold*` 是**两个模式共用**的折叠状态 sink(键=队名+开球时刻)。
        两个模式的场次集合不相交,不会撞键。另写一套只会多一处漂移。

        ⭐ 2026-08-07 从 `_cupFold*` 改名 —— 它一直是通用的,但 `_cup` 前缀让它
        看起来是市场模式专有,于是加标准模式**让球**折叠时没人想到用(见下一条)。
        """
        assert "_foldAttrs('mb', _foldKey(pr))" in _card()

    def test_the_handicap_fold_survives_a_rerender(self):
        """⭐ owner 报的 bug:标准模式展开让球 → 手填实时盘口 → 应用 → 折回去。

        卡片是 innerHTML 重建的,原生 `<details>` 会回到关闭态。市场模式没这问题
        只因为它那半早就挂了 `_foldAttrs`。让球线选择和已填 SP 本来就保住了
        (`renderTodaySpCalc` 的 `_entered.hcline`),丢的**只有展开状态** ——
        但那正是最烦的:每应用一次要重新点开一次。
        """
        card = _card()
        i = card.index("t('spcalc_hc_toggle')")
        # 往回找这个 summary 所属的 <details> 开标签
        j = card.rindex("<details", 0, i)
        tag = card[j:card.index(">", j) + 1]
        assert "_foldAttrs('hc'" in tag, (
            f"标准模式让球折叠没有折叠记忆,重渲会关掉它。实际标签:{tag}")

    def test_the_fold_memory_actually_remembers(self):
        """⭐ 变异检验抓到的洞:上面几条只断言**标签里有没有 `_foldAttrs`**,
        没断言**机制真的会记住并还原**。把 `_openFolds.add(...)` 改成 no-op,
        它们照样全绿 —— 接线在、机制死了。又是语法代理测语义属性。

        这条跑**生产函数原文**:模拟用户展开 → 再问 `_foldAttrs` 要不要加 open。
        """
        import json
        import subprocess

        js = _js()

        def fn(name):
            i = js.index(f"function {name}(")
            j, depth = js.index("{", i), 0
            while j < len(js):
                if js[j] == "{":
                    depth += 1
                elif js[j] == "}":
                    depth -= 1
                    if depth == 0:
                        return js[i:j + 1]
                j += 1
            raise AssertionError(name)

        src = f"""
const _openFolds = new Set();
{fn('_foldKey')}
{fn('_onFoldToggle')}
{fn('_foldAttrs')}
const pr = {{ home_team: 'A', away_team: 'B', kickoff_utc: '2026-08-08T10:00:00Z' }};
const k = _foldKey(pr);
const before = _foldAttrs('hc', k);
// 用户点开 —— 模拟浏览器派发 ontoggle
_onFoldToggle({{ open: true, getAttribute: () => 'hc::' + k }});
const after = _foldAttrs('hc', k);
// ⚠️ 隔离检查必须在**还开着的时候**做:第一版把它放在「用户关上」之后,
// 那时集合已经空了 ⇒ 键不隔离也测不出来(变异 R6 抓到的)。
const other = _foldAttrs('hc', _foldKey({{ home_team: 'C', away_team: 'D', kickoff_utc: 'x' }}));
// 另一个 kind 也不该被连带打开(hc 开了不等于 mb 开了)
const otherKind = _foldAttrs('mb', k);
// 再点上
_onFoldToggle({{ open: false, getAttribute: () => 'hc::' + k }});
const closed = _foldAttrs('hc', k);
console.log(JSON.stringify({{ before, after, closed, other, otherKind }}));
"""
        r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[:1500]
        d = json.loads(r.stdout)
        assert " open" not in d["before"], "还没展开就带 open"
        assert " open" in d["after"], (
            "展开后 `_foldAttrs` 没返回 open —— 折叠记忆是死的,"
            "重渲仍会把面板关掉(标签里有 _foldAttrs 只证明接线在)")
        assert " open" not in d["closed"], "用户手动关上后仍然记成展开"
        assert " open" not in d["other"], "一场展开把别的场也带开了(键不隔离)"
        assert " open" not in d["otherKind"], "让球展开把净胜球也带开了(kind 不隔离)"

    def test_both_modes_handicap_folds_are_guarded(self):
        """⛔ 别再只守一半。

        这个 bug 的形状是「机制存在、但只接了一个模式」——
        `_foldAttrs` 从第一天就是通用的,漏的是**接线**。所以断言必须同时覆盖
        两个模式的让球折叠;只断言标准模式,下次轮到市场模式漏也发现不了。
        """
        js = _js()
        for label, summary_key in (("标准模式", "spcalc_hc_toggle"),
                                   ("市场模式", "cupmkt_hc_toggle")):
            i = js.index(f"t('{summary_key}')")
            j = js.rindex("<details", 0, i)
            tag = js[j:js.index(">", j) + 1]
            assert "_foldAttrs('hc'" in tag, f"{label}的让球折叠没有折叠记忆:{tag}"
