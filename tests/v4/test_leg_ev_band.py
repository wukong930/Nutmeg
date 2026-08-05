"""串关腿行的 ± 带 —— 三处共用一个 `_legEvHtml`(owner 2026-08-05)。

## 起因不只是「加个带」

同一条腿在**同一页上**曾经有两个数:
  · 甜区榜        `EV <点估> ±<带>`
  · 串关腿行      `<evLo>`(下界,没有带)
  · 点进去那张卡  `EV <点估> ±<带>`
点一下串关腿会跳到卡片 —— 用户看到的两个数字对不上,而它们说的是同一注。

## 为什么带只能挂在点估上

`half = hypot(ev − evLo, 冻结带)`,**按定义**是围绕点估的半宽。写成
`evLo ± half` 会造出一个不存在的统计量 —— 同「δ₊₂ 故意不出常数:编常数比缺常数
更坏」。所以正确做法是腿行改印**点估 + 带**,而不是把带贴到下界后面。

## 判闸没有放松

颜色/粗细仍由 `evLo` 决定,票面的「理论 EV」仍是下界之积。变的只有腿行印出来的
那个数字。⚠️ 点估比下界**好看**,所以它必须永远和 ± 一起出现 —— 单独印点估
就是把眼睛往乐观那边带,正是 [[two-modes-coverage-and-p-source]] 里
"never auto-pick the rosier one" 要防的事。
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


def _fn(name: str) -> str:
    js = _js()
    m = re.search(rf"\n(async )?function {re.escape(name)}\(", js)
    assert m, f"找不到 {name}"
    start, j, depth = m.start() + 1, js.index("{", m.end()), 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[start:j + 1]
        j += 1
    raise AssertionError(name)


def _run(lg: dict) -> str:
    """真跑 `_legEvHtml`,不 grep 源码。"""
    r = subprocess.run(
        ["node", "-e", f"{_fn('_legEvHtml')}console.log(_legEvHtml({json.dumps(lg)}));"],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


#: 点估 +12.6%,下界 −2.0%(没过闸),半宽 16.0% —— 三个数刻意互不相等,
#: 否则「印的是哪一个」根本测不出来。
_LEG = {"ev": 0.126, "evLo": -0.020, "half": 0.160, "sp": 2.90, "label": "主胜"}


class TestBandIsRenderedAndCentredOnThePointEstimate:
    def test_point_estimate_and_band_both_appear(self):
        out = _run(_LEG)
        assert "+12.6%" in out, f"没印点估\n{out}"
        assert "±16.0%" in out, f"没印 ± 带\n{out}"

    def test_the_printed_number_is_not_the_lower_bound(self):
        """⚠️ 印下界 + 带 = 一个不存在的统计量。这条就是守它。"""
        out = _run(_LEG)
        assert "-2.0%" not in out and "−2.0%" not in out, (
            f"腿行印了下界又挂了围绕点估的带\n{out}")

    def test_no_band_when_there_is_no_uncertainty(self):
        """半宽为 0(没有 δ 也没有冻结缺口)⇒ 不出 ± —— 别画一个 ±0.0% 的假精度。"""
        out = _run({**_LEG, "half": 0.0})
        assert "±" not in out, out


class TestGatingIsUnchanged:
    def test_green_comes_from_the_lower_bound_not_the_point(self):
        """点估好看不算数:必须下界过 +5% 才变绿。"""
        # 点估 +12.6% 但下界 −2% ⇒ 不绿
        assert "#059669" not in _run(_LEG)
        # 下界抬到 +6% ⇒ 绿
        assert "#059669" in _run({**_LEG, "evLo": 0.06})

    def test_red_comes_from_a_negative_point_estimate(self):
        assert "#e11d48" in _run({**_LEG, "ev": -0.05, "evLo": -0.20})

    def test_bold_tracks_the_gate_too(self):
        assert "font-weight:600" in _run({**_LEG, "evLo": 0.06})
        assert "font-weight:400" in _run(_LEG)


class TestThreeSurfacesCannotDriftApart:
    """⭐ 抽 helper 的**理由**,不是它的实现。"""

    def test_sweet_board_delegates(self):
        assert "_legEvHtml(lg)" in _fn("_sweetLegHtml"), "甜区榜自己又算了一遍"

    def test_parlay_leg_rows_delegate(self):
        body = _fn("_parlayBuilderHtml")
        assert "_legEvHtml(l)" in body, "串关组合腿行没走共用函数"
        assert "_legEvHtml(b1)" in body, "1 串参考那行没走共用函数"

    def test_no_leg_row_still_prints_a_bare_lower_bound(self):
        """回归守卫:三处腿行里不能再出现「裸印 evLo」的老写法。

        ⚠️ 这条是**语法**断言,只当补充 —— 承重的是上面那些真跑 node 的。
        贴着当时那个具体写法写,加了新腿行要么复用 helper 要么来改这里。
        """
        body = _fn("_parlayBuilderHtml")
        assert 'style="color:#059669">${f(l.evLo)}' not in body
        assert 'style="color:#059669">${f(b1.evLo)}' not in body

    def test_ticket_total_still_uses_the_lower_bound(self):
        """票面的「理论 EV」**不动** —— 改的只是腿行。
        下界之积是这个构造器的钱学,把它换成点估之积会让整块板变乐观。"""
        assert "${f(c.evLo)}" in _fn("_parlayBuilderHtml"), "票面理论 EV 不再走下界"


class TestCopyExplainsTheTwoBases:
    def test_pb_note_says_legs_and_ticket_use_different_bases(self):
        """两个数字口径不同且**故意**不同 ⇒ 必须写出来,否则读的人会以为哪个错了。"""
        hits = re.findall(r"pb_note:\s*'((?:[^'\\]|\\.)*)'", _js())
        assert len(hits) == 2, f"中英没齐({len(hits)})"
        zh = next(h for h in hits if "点估" in h)
        en = next(h for h in hits if "POINT" in h)
        assert "下界之积" in zh and "颜色仍由下界决定" in zh, zh[-300:]
        assert "LOWER BOUNDS" in en and "lower bound" in en, en[-300:]
