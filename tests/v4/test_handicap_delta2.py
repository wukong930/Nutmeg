"""δ₋₂ 部署 + 未校准线护栏地板 —— prereg v1.8(owner 口令 2026-07-27)。

锁三件事:
  ① −2 的点估校正守恒(三腿仍和为 1),且方向 = 让胜 ↓ / 让平·让负 ↑
  ② −2 的判闸下界逐腿用**自己的** SE
  ③ ⭐ **未校准线(+2/±3)的下界必须严格低于点估** —— 老实现在这里返回点估
     (se=0),导致前端 ± 带 hypot(0, frz) 反而**变窄**、判闸 evLo>=minEv 直接
     拿点估过闸 ⇒ **越不可信的线越容易变绿**。这个符号反了的 bug 不许回来。
"""
from __future__ import annotations

import pytest

from nutmeg.v4.model.market_handicap import (
    _C2_DELTA_A,
    _C2_DELTA_D,
    _C2_DELTA_H,
    c1_leg_lower_bounds,
    implied_handicap_lines,
)

# 一组普通的强主场 1X2(和为 1),够撑出 −2 线
_FAIR = (0.62, 0.22, 0.16)


def _line(n: int, *, c1: bool):
    out = implied_handicap_lines(*_FAIR, None, lines=(n,), c1=c1)
    assert out, f"线 {n} 没拟合出来"
    return out[0][1:]          # (让胜, 让平, 让负)


def test_delta2_constants_conserve():
    """守恒是可用于展示的前提:−0.064 + 0.021 + 0.043 = 0。"""
    residual = _C2_DELTA_H - _C2_DELTA_D - _C2_DELTA_A
    assert abs(residual) < 1e-12, f"三腿校正不守恒,残差 {residual}"


def test_minus2_shift_direction_and_sum():
    """−2:让胜 ↓、让平 ↑、让负 ↑,且三腿仍和为 1。"""
    raw = _line(-2, c1=False)
    got = _line(-2, c1=True)
    assert got[0] < raw[0], "让胜应被下调(实测 +6.4pp 高估)"
    assert got[1] > raw[1] and got[2] > raw[2], "让平/让负应被上调"
    assert sum(got) == pytest.approx(1.0, abs=1e-9), "三腿必须仍和为 1"
    assert (raw[0] - got[0]) == pytest.approx(_C2_DELTA_H, abs=1e-9)


def test_plus2_gets_no_point_correction():
    """⚠️ +2 **不出常数** —— 两锚量级差一倍、N≈40 钉不住(prereg v1.8 §0)。

    「编一个常数」比「缺常数」更坏:缺的时候护栏会响,错的时候它静默把幻影 EV
    变成绿灯。这条测试就是防止有人后来「顺手补上对称的 +2」。
    """
    assert _line(2, c1=True) == pytest.approx(_line(2, c1=False), abs=1e-12)


def test_minus2_bounds_use_per_leg_se():
    """−2 三腿都被碰过 ⇒ 三条下界都必须严格低于点估,且各用自己的 SE。"""
    ph, pd_, pa = _line(-2, c1=True)
    lo = c1_leg_lower_bounds(-2, ph, pd_, pa)
    assert lo[0] < ph and lo[1] < pd_ and lo[2] < pa
    # SE 不同 ⇒ 三条腿被扣掉的量必须互不相等(同一个 d 会是实现退化)
    drops = (ph - lo[0], pd_ - lo[1], pa - lo[2])
    assert len(set(round(x, 6) for x in drops)) == 3


@pytest.mark.parametrize("line", [2, 3, -3, -4])
def test_uncalibrated_lines_still_get_a_widened_bound(line):
    """⭐ 未校准线的下界必须**严格低于**点估。

    老实现 se=0 → 下界=点估 → ① ± 带 hypot(0, frz) 反而比 ±1 窄
    ② 判闸 evLo>=minEv 直接拿点估过 ⇒ 越不可信越容易变绿。符号反了。
    """
    ph, pd_, pa = 0.45, 0.28, 0.27
    lo = c1_leg_lower_bounds(line, ph, pd_, pa)
    assert lo[0] < ph and lo[1] < pd_ and lo[2] < pa, (
        f"线 {line} 的下界等于点估 —— 「没测过校准」被当成「没有不确定性」")


def test_uncalibrated_band_is_wider_than_calibrated():
    """地板必须比 ±1 的 δ 带**宽** —— 不确定性该随「知道得越少」而增大。"""
    p = (0.45, 0.28, 0.27)
    drop_m1 = p[0] - c1_leg_lower_bounds(-1, *p)[0]
    drop_unc = p[0] - c1_leg_lower_bounds(3, *p)[0]
    assert drop_unc > drop_m1, "未校准线的带反而比已校准的窄 = 那个反转又回来了"


def test_zero_line_is_untouched():
    """0 线没有让球切分偏差可言 —— 下界 = 点估,不该被地板误伤。"""
    p = (0.45, 0.28, 0.27)
    assert c1_leg_lower_bounds(0, *p) == pytest.approx(p, abs=1e-12)


def test_bounds_never_go_negative():
    """深线上点估可能小于 δ/地板 —— 截到 0,不许出负概率。"""
    lo = c1_leg_lower_bounds(-2, 0.01, 0.01, 0.01)
    assert all(x >= 0.0 for x in lo)


def test_shift_never_makes_probability_negative():
    """让胜 < δ 时按比例缩,和仍为 1(深线拟合出的极小 ph 会走到这条路)。"""
    from nutmeg.v4.model.market_handicap import implied_handicap_lines as f
    for fair in [(0.62, 0.22, 0.16), (0.30, 0.30, 0.40), (0.80, 0.14, 0.06)]:
        for ln, ph, pd_, pa in f(*fair, None, lines=(-2,), c1=True):
            assert ph >= 0.0 and pd_ >= 0.0 and pa >= 0.0, f"线 {ln} 出了负概率"
            assert sum((ph, pd_, pa)) == pytest.approx(1.0, abs=1e-9)
