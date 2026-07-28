"""B2 — variance-adjusted EV threshold: threshold(P) = base + z·σ_P·lf·SP.

A-3 影子模式(2026-07-23)加了 σ_P(h) = A·h^B —— 下半部分锁它。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nutmeg.v4.model.ev_threshold import (
    BASE_THRESHOLD,
    FREEZE_SIGMA_COEF,
    MIN_HOURS,
    SIGMA_P,
    sigma_p_at,
)
from nutmeg.v4.model.ev_threshold import variance_adjusted_threshold as vt


def test_sweet_small_haircut():
    # P=0.4 → SP=2.5 → 0.05 + 1·0.012·1·2.5 = 0.08
    assert vt(0.40) == pytest.approx(0.08)


def test_deep_longshot_big_haircut():
    # P=0.08 → SP=12.5 → 0.05 + 0.012·12.5 = 0.20
    assert vt(0.08) == pytest.approx(0.20)


def test_monotone_rises_for_longshots():
    assert vt(0.08) > vt(0.40) > vt(0.80) > BASE_THRESHOLD


def test_non_probability_falls_back_to_flat_base():
    for bad in (0.0, 1.0, -0.1, 1.2):
        assert vt(bad) == BASE_THRESHOLD


def test_explicit_sp_overrides_fair_odds():
    # sp given → use it, not 1/p. P=0.5 but 竞彩 SP=3.0 → 0.05 + 0.012·3.0
    assert vt(0.50, sp=3.0) == pytest.approx(0.05 + 0.012 * 3.0)
    # default (sp=None) uses 1/p = 2.0
    assert vt(0.50) == pytest.approx(0.05 + 0.012 * 2.0)


def test_league_factor_and_z_scale_the_haircut():
    base_hair = vt(0.08) - BASE_THRESHOLD
    assert vt(0.08, league_factor=1.39) - BASE_THRESHOLD == pytest.approx(base_hair * 1.39)
    assert vt(0.08, z=1.65) - BASE_THRESHOLD == pytest.approx(base_hair * 1.65)


def test_zero_sigma_recovers_flat_bar():
    # σ_P=0 (no estimation error) → the flat base at every P
    for p in (0.05, 0.4, 0.9):
        assert vt(p, sigma_p=0.0) == BASE_THRESHOLD


# ── A-3 影子模式:σ_P(h) = A·h^B ──────────────────────────────────────────────

def test_no_hours_keeps_the_old_constant():
    """拿不到开球时刻的老调用点必须**逐位**回落到改动前的行为。"""
    assert sigma_p_at(None) == SIGMA_P
    assert vt(0.40) == pytest.approx(0.08)          # 与本文件顶部那条同值


@pytest.mark.parametrize("bad", ["", "abc", float("nan"), float("inf"), float("-inf")])
def test_unparseable_hours_falls_back_not_crashes(bad):
    """脏输入不该炸,也不该悄悄变成 σ=0(那等于把门槛降成平 5%)。"""
    assert sigma_p_at(bad) == SIGMA_P


def test_sigma_grows_with_the_freeze_gap():
    for leg in FREEZE_SIGMA_COEF:
        assert sigma_p_at(1, leg) < sigma_p_at(6, leg) < sigma_p_at(24, leg)


def test_hours_floor_stops_sigma_collapsing_to_zero():
    """h→0 时 A·h^B→0,但去vig 误差不会消失 —— 必须被 MIN_HOURS 托住。"""
    at_floor = sigma_p_at(MIN_HOURS, "H")
    assert sigma_p_at(0.0, "H") == at_floor
    assert sigma_p_at(1e-9, "H") == at_floor
    assert sigma_p_at(-3, "H") == at_floor          # 已开球也托住,不返回 0
    assert at_floor > 0


def test_draw_leg_drifts_least():
    """A-1:平局腿的漂移幅度最小 —— 系数别被抄串行。"""
    for h in (1, 6, 24):
        assert sigma_p_at(h, "D") < sigma_p_at(h, "A")
        assert sigma_p_at(h, "D") < sigma_p_at(h, "H")


def test_unknown_leg_falls_back_to_home_curve():
    # 让球腿('hcH' 等)没有自己的曲线 → 落到最宽的主胜曲线(保守)
    assert sigma_p_at(6, "hcH") == sigma_p_at(6, "H")
    assert sigma_p_at(6, "h") == sigma_p_at(6, "H")   # 大小写不敏感


def test_threshold_widens_for_overnight_gaps():
    """同一注,凌晨场(缺口大)的门槛必须高于临开球。这是 A-3 的全部意义。"""
    near = vt(0.40, 2.5, hours_to_kickoff=0.5, leg="H")
    far = vt(0.40, 2.5, hours_to_kickoff=24, leg="H")
    assert far > near > BASE_THRESHOLD


def test_explicit_sigma_wins_over_the_curve():
    """调用方自己算好的 σ 优先级最高 —— 否则前端传下来的值会被悄悄改写。"""
    assert vt(0.40, 2.5, sigma_p=0.02, hours_to_kickoff=24) == pytest.approx(0.05 + 0.02 * 2.5)


def test_frontend_mirrors_the_same_coefficients():
    """dashboard.html 的 _FRZ_COEF / Math.max(h, 0.5) 必须与本模块同值 ——
    两处漂开 = 同一场比赛的 ± 带与门槛各算各的 σ,而这正是 A-3 要消灭的东西。"""
    html = (Path(__file__).resolve().parents[2] / "apps/api/src/nutmeg/v4/api/static"
            / "dashboard.html").read_text(encoding="utf-8")
    m = re.search(r"const _FRZ_COEF = \{([^}]*)\}", html)
    assert m, "dashboard.html 里找不到 _FRZ_COEF —— 前端镜像被改名或删了"
    for leg, (a, b) in FREEZE_SIGMA_COEF.items():
        assert re.search(rf"{leg}:\s*\[{a},\s*{b}\]", m.group(1)), f"{leg} 系数不一致"
    assert f"Math.max(h, {MIN_HOURS})" in html, "前端 h 下界与 MIN_HOURS 不一致"


# ── σ_P 溯源(2026-07-28 调查后钉死)────────────────────────────────────────
#: A-1 §C 实测的竞彩停售→开球缺口分布(涓流史 8,139 场 × football-data,
#: 比分硬闸,窗口内 N=3,461)。⚠️ **不是** 06-26 假设的 12–24h —— 那个桶只占 0.7%。
_MEASURED_FREEZE_GAP_H = {"median": 3.0, "p75": 6.5, "p90": 8.7, "overnight_median": 6.0}


def test_sigma_p_constant_matches_the_measured_freeze_gap_not_the_12_24h_myth():
    """⭐ `SIGMA_P` 的**溯源**锁 —— 数值不锁死,锁的是它必须落在实测缺口的量级上。

    2026-07-28 调查(docs/sigma_p_reconciliation_2026-07-28.md)推翻了旧溯源:
    06-26 把 1.2pp 归给「竞彩 12–24h 封盘」,但 A-1 §C 实测中位缺口只有 **3.0h**,
    16–30h 桶占 0.7% —— 那个前提不存在,06-26 是从自己表里读错了行。

    站得住的读法:`SIGMA_P` ≈ **A-1 曲线在实测封盘缺口区间内**的值。本测试断言它
    落在 [中位 3.0h, p90 8.7h] 对应的 σ 区间里 —— 谁把它改回「12–24h 的 1.7–2.1pp」
    就会红,谁把它调到实测缺口之外也会红。
    """
    lo = sigma_p_at(_MEASURED_FREEZE_GAP_H["median"], "H")
    hi = sigma_p_at(_MEASURED_FREEZE_GAP_H["p90"], "H")
    assert lo < hi, "测试前提:σ 随缺口单调增"
    assert lo <= SIGMA_P <= hi, (
        f"SIGMA_P={SIGMA_P} 落到了实测封盘缺口 [3.0h,8.7h] → [{lo:.5f},{hi:.5f}] 之外。"
        "改它须走预注册,见 docs/sigma_p_reconciliation_2026-07-28.md §8")


def test_the_12_24h_gap_would_give_a_visibly_larger_sigma():
    """反向锁:证明「12–24h」确实是个**不同**的答案,不是同一个数的另一种说法。

    若哪天有人「统一口径」把常数改成 12–24h 档,这条会红并指回调查文档 ——
    那不是统一,那是把已经证伪的前提又装回去。
    """
    myth = sigma_p_at(12.0, "H")
    assert myth > SIGMA_P * 1.3, "12h 处的 σ 应显著大于回落常数(实测约 1.71pp vs 1.2pp)"
    assert sigma_p_at(24.0, "H") > myth


def test_provenance_note_is_present_in_the_module_docstring():
    """溯源写在代码里,不只写在文档里 —— 文档会被绕过,docstring 不会。

    ⚠️ 这条钉的是「更正过的溯源仍在」,不是措辞。旧的「这个分歧没有被调查过」
    必须已经消失,否则下一个人还会照着错的溯源改数。
    """
    import nutmeg.v4.model.ev_threshold as M
    doc = M.__doc__ or ""
    assert "sigma_p_reconciliation_2026-07-28" in doc, "更正后的调查文档链接丢了"
    assert "这个分歧没有被调查过" not in doc, "旧的未调查警告又回来了"
