"""δ 校准常设仪表 —— 锁住功效算式和「常数不许漂」。

背景:δ₋₁/δ₊₁ 上线 11 天里没有任何东西看着它们,直到 owner 随口一问才发现
δ₊₁ 在自己的拟合人口上 log-loss 变差。这个仪表存在的意义就是别再靠人问。
"""
from __future__ import annotations

import math

import pytest

from nutmeg.v4.cli.delta_calibration import power_table, render, required_n
from nutmeg.v4.model import market_handicap as MH


def test_required_n_scales_as_inverse_delta_squared():
    """⭐ N ∝ 1/δ² —— δ 减半,所需样本变 4 倍。

    这是「小 δ 不可确立」的**全部**原因,也是本仪表最有用的一条结论:
    对 δ₊₁=0.016 而言「再等等攒 N」是无效策略,不是耐心问题。
    """
    p = 0.35
    assert required_n(0.02, p) == pytest.approx(4 * required_n(0.04, p), rel=1e-9)


def test_required_n_matches_the_delta_equals_2se_boundary():
    """定义自洽:在 N=required_n 处,恰好 δ == 2·SE(即判闸下界恰为 0)。"""
    d, p = 0.046, 0.25
    n = required_n(d, p)
    se = math.sqrt(p * (1 - p) / n)
    assert 2 * se == pytest.approx(d, rel=1e-9)


def test_required_n_is_infinite_for_zero_delta():
    assert required_n(0.0, 0.3) == float("inf")
    assert required_n(-0.01, 0.3) == float("inf")


def test_power_table_reads_live_constants_not_a_snapshot(monkeypatch):
    """⭐ 常数必须**现读** `market_handicap`,不能在加载时快照。

    初版把 δ 在模块加载时求值存进元组 —— 那样将来有人改了那边的 δ,本仪表会
    悄悄停在旧值,而它的全部职责就是监督那些 δ。这条测试钉死这个失效模式。
    """
    before = {r["leg"]: r["delta"] for r in power_table()}
    monkeypatch.setattr(MH, "_C1_DELTA", 0.099)
    after = {r["leg"]: r["delta"] for r in power_table()}
    assert before["−1 让胜"] != 0.099, "测试前提:原值不应恰好是这个哨兵值"
    assert after["−1 让胜"] == 0.099, "改了 market_handicap 的 δ,表却没跟上 = 已漂"


def test_established_flag_is_exactly_delta_gt_2se():
    """「在做功」的判定 = 判闸下界为正,不是别的什么直觉。"""
    for r in power_table():
        assert r["established"] == (r["delta"] - 2 * r["se"] > 0)
        assert r["lower"] == pytest.approx(r["delta"] - 2 * r["se"])


def test_delta_p1_is_currently_flagged_as_not_established():
    """现状留痕:δ₊₁ 是在 t=1.19、下界为负的情况下上线的。

    ⚠️ 这条**不是**在断言「δ₊₁ 永远该是 0.016」—— 若 owner 走 prereg 改了它,
    这条测试会红,那正是提示「现状记录要更新」,不是提示代码坏了。
    """
    row = next(r for r in power_table() if r["leg"] == "+1 让负")
    assert not row["established"], (
        "δ₊₁ 变成「已确立」了 —— 若是 owner 经 prereg 调整了 δ/SE,更新本测试的注记")
    assert row["t"] < 2.0


def test_small_slices_are_skipped_not_interpreted():
    """N 小于门槛的切片只报「样本太小」,绝不给出「谁更近」的解读。"""
    tiny = {(-2, "俱乐部"): [((0.4, 0.3, 0.3), (0.35, 0.35, 0.3), 0)] * 3}
    txt = render(tiny, min_n=10)
    assert "样本太小" in txt
    assert "谁更近" not in txt


def test_render_survives_empty_input():
    assert "无已结算" in render({})
