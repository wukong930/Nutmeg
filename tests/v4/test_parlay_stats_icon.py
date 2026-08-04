"""档位统计从常驻文案改成 ⓘ 点开(owner 2026-08-04)。

原来每个档位标题后面挂着
「· 历史实测 ≈ −12.5% ±10.6pp (n=750) · 命中率 11.1% · 随机腿基线 −25.2%±0.9」
—— 一行 40+ 字符,把「这一注是哪几条腿」挤出了视线。

## 这次改动的唯一风险:**悄悄漏掉一个数**

搬家不是删减。所以本文件不测「好不好看」,只测**信息守恒**:改之前常驻显示的
每一个数字,改之后必须能在 ⓘ 里找到,而且值一样。

⚠️ 特意**不**断言 HTML 结构(标签、class、行顺序)—— 那会在下次调样式时误红,
而它本来要守的东西(数字还在不在)一点没变。同
[[syntactic-proxy-for-semantic-property]]:断言值,别连带断言结构。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"

#: 改动前常驻显示的四个量(取自 dashboard 的常数表)。这里**故意重抄一遍字面值**
#: —— 从源码里读出来再和源码比是同义反复,钉不住「值被改了」。
#: 改这些数请同步 `_PARLAY_*` 常量,并在提交信息里写清依据。
EXPECTED = {
    1: {"hist": -0.052, "hist_se": 0.051, "n": 873, "rand": -0.127, "rand_se": 0.0058},
    2: {"hist": -0.125, "hist_se": 0.106, "n": 750, "rand": -0.252, "rand_se": 0.0094,
        "hit": 0.111},
    3: {"hist": -0.252, "hist_se": 0.176, "n": 648, "rand": -0.319, "rand_se": 0.0155,
        "hit": 0.039},
    4: {"hist": -0.304, "hist_se": 0.335, "n": 550, "rand": -0.447, "rand_se": 0.0230,
        "hit": 0.011},
}


def _js() -> str:
    return DASH.read_text(encoding="utf-8")


def _block(pattern: str, src: str) -> str:
    m = re.search(pattern, src, re.S)
    assert m, f"没抠到:{pattern}"
    return m.group(0)


def _render(k: int) -> str:
    """真跑 `_parlayStatsBody(k)`,拿回它实际生成的 HTML。"""
    js = _js()
    parts = [_block(r"\nfunction _parlayStatsBody\(.*?\n\}", js)]
    for c in ("_PARLAY_BACKTEST", "_PARLAY_BACKTEST_SE", "_PARLAY_BACKTEST_N",
              "_PARLAY_RANDOM", "_PARLAY_RANDOM_SE", "_PARLAY_HIT"):
        parts.append(_block(rf"\nconst {c}\s*=.*?;", js))
    # t() 只需返回标签;本文件测的是**数字**,不是文案
    stub = "function t(k){return k;}"
    r = subprocess.run(["node", "-e", "\n".join(parts) + f"\n{stub}\n"
                        f"console.log(_parlayStatsBody({k}));"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


class TestNoNumberLost:
    @pytest.mark.parametrize("k", [1, 2, 3, 4])
    def test_every_number_survives_the_move(self, k):
        """⭐ 本文件的核心。搬进 ⓘ 之后,四个量必须一个不少、值不变。"""
        html, e = _render(k), EXPECTED[k]
        want = [
            f"{e['hist'] * 100:.1f}%",
            f"{e['hist_se'] * 100:.1f}pp",
            f"n={e['n']}",
            f"{e['rand'] * 100:.1f}%",
            f"{e['rand_se'] * 100:.1f}pp",
        ]
        if "hit" in e:
            want.append(f"{e['hit'] * 100:.1f}%")
        for w in want:
            assert w in html, f"{k} 串的 ⓘ 里找不到 {w!r} —— 搬家漏了一个数\n{html}"

    @pytest.mark.parametrize("k", [1, 2, 3, 4])
    def test_se_and_n_are_never_dropped(self, k):
        """⚠️ 单独钉一遍 ±SE 和 n。

        它们是这些数**唯一**的可信度信息。只留「−12.5%」就成了假精度 ——
        那个数自己带着 ±10.6pp。删 ± 是「精简文案」时最容易顺手做的事。
        """
        html = _render(k)
        assert "±" in html, f"{k} 串:± 不见了 ⇒ 只剩点估计 = 假精度"
        assert f"n={EXPECTED[k]['n']}" in html, f"{k} 串:样本量 n 不见了"

    def test_single_leg_has_no_hit_rate(self):
        """1 串没有「命中率」这个量(它就是单场胜负),不许凭空造一个。"""
        assert "_PARLAY_HIT" not in _render(1) and "%" in _render(1)

    def test_net_gain_is_hist_minus_random(self):
        """净提升 = 历史实测 − 随机腿基线。两个数都是负的 ⇒ 它衡量的是
        「选腿这步有没有用」,不是「这档能不能赢」。算错方向会把负的说成正的。"""
        for k, e in EXPECTED.items():
            assert f"+{(e['hist'] - e['rand']) * 100:.1f}pp" in _render(k), k


class TestFourLegWarningFoldedIn:
    """4 串那条「100 张中 1 张ⓘ」并进了 实测ⓘ(owner 2026-08-04)。

    ⚠️ 它讲的是这一档**最危险**的地方 —— 命中率 1.1%,平均 91 张才中 1 张,
    「中一次的爽感会盖过 90 次没中」。合并是为了少一个入口,**不是**为了淡化它。
    """

    def test_note_is_in_the_four_leg_body_only(self):
        assert "pb_4x_note" in _render(4), "4 串的警告没并进 ⓘ"
        for k in (1, 2, 3):
            assert "pb_4x_note" not in _render(k), f"{k} 串不该出现 4 串的警告"

    def test_standalone_badge_is_gone(self):
        """并进来了就不该在标题旁再挂一个 —— 两个入口讲同一件事只会互相稀释。"""
        block = _block(r"\n  const block = \(k\) => \{.*?\n  \};", _js())
        assert "pb_4x_note" not in block, "标题旁还挂着独立的 4 串 ⓘ"

    def test_the_hit_rate_line_still_names_the_91_tickets(self):
        """表格里那行命中率必须带上「平均 91 张才中 1 张」——
        「1.1%」这个百分数本身不会让人产生「91 张」的实感。"""
        assert "pb_hit_note_4x" in _render(4), "4 串命中率行没带 91 张的注解"


class TestAltLabelIsVisibleButNotGreen:
    def test_alt_label_uses_the_scoped_class(self):
        js = _js()
        assert ".pb-alt-label" in js and '[data-theme="dark"] .pb-alt-label' in js, \
            "备选标题色没有亮/暗两套"
        assert "pb-alt-label" in _block(r"\n  const block = \(k\) => \{.*?\n  \};", js), \
            "备选行没挂上那个 class"

    def test_alt_label_is_not_green(self):
        """⛔ **不许用绿色。** 实测备选并不比主选好(−22.8±10.1 / −4.3±25.0 /
        +25.3±65.9,分不出好坏),它唯一的价值是不跟主选一起死。
        绿色 = 用颜色说了一句数据不支持的话。
        """
        js = _js()
        rules = re.findall(r"\.pb-alt-label\s*\{\s*color:\s*(#[0-9a-fA-F]{6})", js)
        assert rules, "抠不到 .pb-alt-label 的色值"
        for hexv in rules:
            r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
            assert not (g > r + 24 and g > b + 24), \
                f"{hexv} 偏绿 —— 会被读成「备选更好」,而实测分不出好坏"


class TestLegRowsJumpToTheMatchCard:
    """腿行点击跳到该场卡片(owner 2026-08-04),**复用甜区榜的 `_sweetJump`**。

    ⚠️ 关键是「复用」不是「另写一份」:`_sweetJump` 里有一段处理联赛组折叠
    (`.spcalc-lg-cards` 折着就先展开)。另写一个跳转函数迟早会漏掉那一段,
    然后表现成「有时候跳不过去」——最难查的那种。
    """

    def _rows(self):
        js = _js()
        return (_block(r"\n  const block = \(k\) => \{.*?\n  \};", js),
                _block(r"const solo = !b1 \? '' :.*?</div></div></div>`;", js))

    def test_both_combo_and_solo_rows_are_clickable(self):
        """1 串参考那行也要能点 —— 它和组合行是同一个池子里的腿,
        只在组合行接上会造成「有的能点有的不能」,比都不能点更让人困惑。"""
        for name, src in zip(("档位块", "1串参考"), self._rows(), strict=True):
            assert "_sweetJump(" in src, f"{name}的腿行没接跳转"

    def test_jump_carries_that_leg_s_own_mode_and_idx(self):
        """⚠️ mode/idx 必须来自**这条腿自己**。写死或取错会跳到别场 ——
        而且看起来「功能是好的」,只是跳错了,不会报错。
        """
        block, solo = self._rows()
        assert "_sweetJump('${l.mode}',${l.idx})" in block, \
            f"档位块的跳转没带上这条腿自己的 mode/idx\n{block[:400]}"
        assert "_sweetJump('${b1.mode}',${b1.idx})" in solo, \
            "1串参考的跳转没带上那条腿自己的 mode/idx"

    def test_pool_actually_carries_mode_and_idx(self):
        """跳转的前提:池里的腿身上真的有 mode/idx。
        `_parlayPool` 若哪天不再透传,上面两条仍然会绿(它们只看模板字符串),
        但线上会变成 `_sweetJump('undefined', undefined)`。"""
        pool = _block(r"\nfunction _parlayPool\(.*?\n\}", _js())
        assert "idx, mode" in pool or ("idx" in pool and "mode" in pool), \
            "_parlayPool 没把 mode/idx 放进腿对象"

    def test_hover_affordance_is_scoped_to_this_card(self):
        """密排小字不给 hover 反馈就完全不像能点。
        ⚠️ 只给 .pb-leg,**不改 .sw-row** —— 改它会波及甜区榜,那是另一件事。"""
        js = _js()
        # ⚠️ 不能写 `".pb-leg:hover" in js` —— `[data-theme="dark"] .pb-leg:hover`
        # **含有**这个子串,于是删掉亮色那条它照样绿(2026-08-04 变异验出来的)。
        # 逐条抠出选择器,再看亮/暗各有没有。
        sels = [s.strip() for s in re.findall(r"([^\n{};]*\.pb-leg:hover)\s*\{", js)]
        light = [s for s in sels if "data-theme" not in s]
        dark = [s for s in sels if 'data-theme="dark"' in s]
        assert light, f"缺亮色底的 .pb-leg:hover(现有:{sels})"
        assert dark, f"缺暗色底的 .pb-leg:hover(现有:{sels})"
        assert not re.search(r"\.sw-row\s*[:{]", js), \
            "动到了甜区榜的 .sw-row —— 本次改动不该碰它"


class TestHeaderNoLongerCarriesTheBlob:
    def test_tier_header_delegates_to_the_icon(self):
        """档位标题行不再内联那一串统计,而是接上 ⓘ。

        ⚠️ 范围取**整个 `block()`**,不是标题那一行 —— ⓘ 是先算进局部变量再插进
        模板的,只看标题行会因为「写法」不同而误红。第一版就是这么错的。
        """
        js = _js()
        block = _block(r"\n  const block = \(k\) => \{.*?\n  \};", js)
        # 2026-08-04 二次收口:票行上那个「· 历史实测 −12.5%」也搬进 ⓘ 了 ⇒
        # `_PARLAY_BACKTEST` 本身也不该再出现在档位块里(它是**逐档常数**,
        # 每张票印一遍纯属重复)。
        for c in ("_PARLAY_BACKTEST", "_PARLAY_BACKTEST_SE", "_PARLAY_BACKTEST_N",
                  "_PARLAY_HIT", "_PARLAY_RANDOM"):
            assert c not in block, f"档位块还内联着 {c} —— 没搬干净"
        assert "_parlayStatsIcon(" in block, "档位块没接上 ⓘ"

    # 「ⓘ 里必须有『按历史实测定注额、别按理论 EV』那句指路」这条断言,
    # 放在 test_parlay_builder.py::test_theoretical_ev_is_never_the_only_unqualified_number
    # —— 它就在被退役的那条老护栏原位,带着完整的来龙去脉。这里**不重复一份**,
    # 否则将来要同步改两处,而漏改一处就是一条哑掉的护栏。

    def test_icon_is_wired_to_the_right_tier(self):
        """ⓘ 的 onclick 必须带上自己那一档的 k,否则四个档会弹同一份数据。"""
        js = _js()
        icon = _block(r"\nfunction _parlayStatsIcon\(.*?\n\}", js)
        assert "_parlayStatsBody(${k})" in icon, icon
        assert "t('pb_${k}x')" in icon, "弹窗标题没跟着档位走"


class TestParlayCardFontScope:
    """字号只在 .pb-card 内放大 —— 全局改 text-xs 会波及整个面板。"""

    def test_rules_are_scoped_to_the_card(self):
        """每一条 `.text-xs` / `.text-sm` 规则都必须限定在 .pb-card 内。

        ⚠️ 第一版写成 `assert not re.search(r"(?<![\\w.-])\\.text-xs\\s*\\{")`,
        想表达「没有裸的全局规则」—— 但 `.pb-card .text-xs` 前面是**空格**,
        空格不在 `[\\w.-]` 里,负向后顾照样通过,于是它把我自己那条限定规则
        当成全局规则报了红。又一次[[syntactic-proxy-for-semantic-property]]:
        正则表达的不是我想守的属性。改成**逐条取出选择器再看它前缀**。
        """
        js = _js()
        rules = re.findall(r"([^\n{};]*\.text-(?:xs|sm))\s*\{", js)
        assert rules, "一条 .text-xs/.text-sm 规则都没有?选择器抠错了"
        for sel in rules:
            assert ".pb-card" in sel, \
                f"规则 {sel.strip()!r} 没限定在 .pb-card 内,会波及整个面板的表格/徽章"
        assert any(".text-xs" in s for s in rules) and any(".text-sm" in s for s in rules)

    def test_card_actually_carries_the_class(self):
        """CSS 写了但 DOM 上没挂 class = 一条永远不生效的规则(静默无效)。"""
        assert 'class="pb-card ' in _js(), "构造器卡片没挂 .pb-card"
