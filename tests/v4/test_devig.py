"""Shared de-vig helper — WPO default (FLB-aware) + basic toggle + guard.

WPO: p_i = (n − M·O_i)/(n·O_i), M = Σ(1/O)−1. Corrects the favourite-longshot bias
(raises favourites, shrinks longshots) vs basic proportional normalization.
"""
from __future__ import annotations

import math

import pytest

from nutmeg.v4.model.devig import devig, devig_1x2


def test_wpo_exact_values():
    # odds [2.0, 3.5, 4.0]: M = 0.5 + 1/3.5 + 0.25 − 1 = 0.0357142857
    p = devig([2.0, 3.5, 4.0])  # wpo default
    assert math.isclose(sum(p), 1.0, abs_tol=1e-12)
    assert math.isclose(p[0], 0.488095238, abs_tol=1e-6)
    assert math.isclose(p[1], 0.273809524, abs_tol=1e-6)
    assert math.isclose(p[2], 0.238095238, abs_tol=1e-6)


def test_basic_normalization():
    p = devig([2.0, 3.5, 4.0], method="basic")
    s = 1 / 2.0 + 1 / 3.5 + 1 / 4.0
    assert math.isclose(p[0], (1 / 2.0) / s, abs_tol=1e-12)
    assert math.isclose(sum(p), 1.0, abs_tol=1e-12)


def test_wpo_corrects_favourite_longshot_bias():
    # vs basic, WPO must RAISE the favourite (lowest odds) and SHRINK the longshot.
    odds = [1.8, 3.6, 5.0]  # home favourite, away longshot
    w = devig(odds)
    b = devig(odds, method="basic")
    assert w[0] > b[0]   # favourite raised
    assert w[2] < b[2]   # longshot shrunk  ← the cold-trap-tightening direction
    assert math.isclose(sum(w), 1.0, abs_tol=1e-12)


def test_near_even_market_wpo_close_to_basic():
    # no clear favourite → FLB correction tiny → methods nearly equal.
    odds = [2.9, 3.1, 2.95]
    w, b = devig(odds), devig(odds, method="basic")
    assert all(abs(x - y) < 0.01 for x, y in zip(w, b, strict=True))


def test_out_of_bounds_falls_back_to_basic():
    # [1.05, 6, 50]: WPO gives a negative longshot prob → must fall back to basic.
    odds = [1.05, 6.0, 50.0]
    w = devig(odds)
    b = devig(odds, method="basic")
    assert all(0.0 < x < 1.0 for x in w)        # no negative / >1 leaked out
    assert w == b                                # fell back to basic
    assert math.isclose(sum(w), 1.0, abs_tol=1e-12)


def test_closed_form_inverse_roundtrip():
    # WPO fair odds Of_i = n·O_i/(n − M·O_i); 1/Of_i must equal p_i.
    odds = [2.2, 3.4, 3.3]
    p = devig(odds)
    n, M = 3, sum(1 / o for o in odds) - 1.0
    for o, pi in zip(odds, p, strict=True):
        of = n * o / (n - M * o)
        assert math.isclose(1.0 / of, pi, abs_tol=1e-12)


def test_invalid_inputs_return_none():
    assert devig([2.0, 3.0, None]) is None
    assert devig([2.0, 3.0, float("nan")]) is None
    assert devig([1.0, 3.0, 4.0]) is None        # ≤ 1.0 decimal odds
    assert devig_1x2(None, 3.0, 4.0) is None
    assert devig_1x2("x", 3.0, 4.0) is None


def test_devig_1x2_returns_tuple():
    p = devig_1x2(2.0, 3.5, 4.0)
    assert isinstance(p, tuple) and len(p) == 3
    assert math.isclose(sum(p), 1.0, abs_tol=1e-12)


# ── 水位闸(2026-07-23)──────────────────────────────────────────────────────
# 去vig 照单全收:喂它软盘就吐出一个伪装成 sharp 先验的公允概率,EV 把错误放大成
# 假 +EV。真实病例:哈马比 vs 安德莱赫特面板显示客胜 +9.4% 绿灯过闸,那条
# 「Pinnacle 原盘」水位 14.5%,换正常宽度的线重算是 −16%。

def test_book_vig_matches_hand_calc():
    from nutmeg.v4.model.devig import book_vig
    # 病例本身:1/2.19 + 1/3.14 + 1/2.70 − 1
    assert book_vig(2.19, 3.14, 2.70) == pytest.approx(0.1455, abs=5e-4)
    # 有 OA 覆盖的联赛 —— 取自库里真实一行(BRA_SERIE_A 2026-07-23),不是编的
    assert book_vig(1.77, 3.51, 5.29) == pytest.approx(0.0389, abs=5e-4)


def test_wide_book_catches_the_real_case_and_spares_healthy_lines():
    from nutmeg.v4.model.devig import is_wide_book
    assert is_wide_book(2.19, 3.14, 2.70)            # 14.5% — 真病例,必拦
    assert not is_wide_book(1.961, 3.490, 3.720)     # 6.5% — owner 截图的参考盘
    assert not is_wide_book(1.77, 3.51, 5.29)        # 3.9% — 真实巴甲行


def test_unusable_odds_never_accuse():
    """算不出水位时必须放行 —— 宁可漏报也不冤枉一条本来没问题的线。"""
    from nutmeg.v4.model.devig import book_vig, is_wide_book
    for bad in [(), (None, 3.0, 3.0), (1.0, 3.0, 3.0), (0.5, 3.0, 3.0), (2.0, 3.0)]:
        if len(bad) == 2:            # 腿数少但都合法 → 能算,只是两腿
            continue
        assert book_vig(*bad) is None, bad
        assert is_wide_book(*bad) is False, bad


def test_threshold_is_the_measured_one():
    """8% 是实测定的(OA 覆盖联赛观测最大 7.3%,UCL/UEL/UECL 中位 7.9/8.5/10.6%)。
    改它等于改「什么算 sharp 锚」——必须同时改前端 WIDE_BOOK_VIG 并重测分布。"""
    from nutmeg.v4.model.devig import WIDE_BOOK_VIG
    assert WIDE_BOOK_VIG == 0.08


def test_frontend_mirrors_the_threshold():
    """dashboard.html 的 WIDE_BOOK_VIG 必须与本模块同值 —— 漂开 = 面板放行了
    Python 侧会拦的线(或反过来),而闸的意义正是两边说同一句话。"""
    import re
    from pathlib import Path

    from nutmeg.v4.model.devig import WIDE_BOOK_VIG
    html = (Path(__file__).resolve().parents[2] / "apps/api/src/nutmeg/v4/api/static"
            / "dashboard.html").read_text(encoding="utf-8")
    m = re.search(r"const WIDE_BOOK_VIG = ([\d.]+);", html)
    assert m, "dashboard.html 里找不到 WIDE_BOOK_VIG —— 前端镜像被改名或删了"
    assert float(m.group(1)) == WIDE_BOOK_VIG
