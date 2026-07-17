"""C1 让球修正 — implied_handicap_lines(c1=True) + A′ δ 下界的不变量。

C1 在 ±1 线把 δ 从「强队打穿腿」(DC 高估)守恒地挪给让平(DC 低估),第三腿不动;
其它线与默认(c1=False, eval 路径)完全不变。

δ 于 2026-07-17 重估(prereg v1.7;docs/handicap_h2_calibration_2026-07-17.md):
靶子从「DC−市场」换成「DC−真实赛果」。−1: 0.019→0.046(真实竞彩线 N=1,882 裸偏差
+4.6pp,held-out test z=3.9);+1: 0.013→0.016(证据弱 z=1.2,纯为口径统一)。

**A′**:δ 是估计值,误差 1:1 进被修正的腿、再 ×竞彩SP 放大成 EV 误差 →
``c1_leg_lower_bounds`` 给逐腿下界,**判闸用下界、显示用点估**(前端 dashboard.html
`_spcalcHcRecalc`/`_cupHcRecalc`)。
"""
import pytest

from nutmeg.v4.model.market_handicap import (
    _C1_DELTA,
    _C1_DELTA_P1,
    _C1_DELTA_P1_SE,
    _C1_DELTA_SE,
    _C1_SE_K,
    c1_leg_lower_bounds,
    implied_handicap_lines,
)


def _by_line(rows):
    return {ln: (ph, pd, pa) for ln, ph, pd, pa in rows}


def test_c1_shifts_line_minus1_conserving():
    args = (0.55, 0.25, 0.20)                      # 主热;−1 线让胜 ≈0.32 > δ(不 clamp)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True))
    r, c = raw[-1], c1[-1]
    assert c[0] == pytest.approx(r[0] - _C1_DELTA)   # 让胜 −δ
    assert c[1] == pytest.approx(r[1] + _C1_DELTA)   # 让平 +δ
    assert c[2] == pytest.approx(r[2])               # 让负 不动
    assert sum(c) == pytest.approx(sum(r))           # 质量守恒


def test_c1_shifts_line_plus1_mirror_conserving():
    args = (0.20, 0.25, 0.55)                      # 客热;+1 线让负 ≈0.32 > δ(不 clamp)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True))
    r, c = raw[1], c1[1]
    assert c[2] == pytest.approx(r[2] - _C1_DELTA_P1)   # 让负 −δ(热门在客,DC 高估)
    assert c[1] == pytest.approx(r[1] + _C1_DELTA_P1)   # 让平 +δ
    assert c[0] == pytest.approx(r[0])                  # 让胜 不动
    assert sum(c) == pytest.approx(sum(r))              # 质量守恒


def test_c1_leaves_other_lines_and_default_untouched():
    args = (0.55, 0.25, 0.20)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True))
    for ln in raw:
        if ln not in (-1, 1):                          # 只 ±1 变(−1 让胜 / +1 让负)
            assert c1[ln] == pytest.approx(raw[ln])
    assert _by_line(implied_handicap_lines(*args)) == raw  # 默认 c1=False = raw(不动 eval)


def test_c1_clamps_when_home_cover_below_delta():
    # 主队巨冷(−1 线让胜 ≈0 < δ)→ shift=min(δ, ph):让胜不为负、仍守恒
    args = (0.05, 0.20, 0.75)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True))
    assert c1[-1][0] >= 0.0
    assert sum(c1[-1]) == pytest.approx(sum(raw[-1]))


# ── A′(2026-07-17)δ 不确定性 → 逐腿下界 ──────────────────────────────────

def test_delta_targets_reality_not_market():
    """δ 的量级锁 —— 它现在对齐**真实赛果**(−1 裸偏差 +4.6pp),不是市场价(+1.86pp)。

    要改这两个数,先去改 docs/handicap_h2_calibration_2026-07-17.md + prereg v1.7,
    别只改常量:C1 的靶子选择是**设计决定**,不是可随手调的旋钮。
    """
    assert _C1_DELTA == 0.046      # −1:实测最优 = 裸偏差 4.6pp
    assert _C1_DELTA_P1 == 0.016   # +1:实测最优 1.6pp(证据弱,口径统一)
    assert _C1_DELTA > _C1_DELTA_P1, "−1 的偏差实测就是比 +1 大(4.6 vs 1.6pp)"


def test_lower_bounds_shift_only_the_two_corrected_legs():
    d = _C1_SE_K * _C1_DELTA_SE
    lo = c1_leg_lower_bounds(-1, 0.30, 0.22, 0.48)
    assert lo[0] == pytest.approx(0.30 - d)    # 让胜(被 C1 减过)→ 再减 k·SE
    assert lo[1] == pytest.approx(0.22 - d)    # 让平(被 C1 加过)→ δ 若更小则更低
    assert lo[2] == pytest.approx(0.48)        # 让负 没被 C1 碰 → 无 δ 误差
    dp = _C1_SE_K * _C1_DELTA_P1_SE
    lo1 = c1_leg_lower_bounds(+1, 0.50, 0.22, 0.28)
    assert lo1[0] == pytest.approx(0.50)       # +1 的让胜没被碰
    assert lo1[1] == pytest.approx(0.22 - dp)
    assert lo1[2] == pytest.approx(0.28 - dp)


def test_lower_bounds_identity_off_the_pm1_lines():
    # C1 不碰的线 → 没有 δ,下界 = 点估(前端 `?? 点估` 也依赖这个语义)
    for ln in (-3, -2, 0, 2, 3):
        assert c1_leg_lower_bounds(ln, 0.4, 0.3, 0.3) == pytest.approx((0.4, 0.3, 0.3))


def test_lower_bounds_are_not_a_distribution():
    """⚠️ 下界三元组和 < 1 —— 它是三个独立单腿下界,只配判闸。

    谁把它当分布归一化/喂模型,这条测试就是现场的说明书。
    """
    lo = c1_leg_lower_bounds(-1, 0.30, 0.22, 0.48)
    assert sum(lo) < 1.0
    assert sum(lo) == pytest.approx(1.0 - 2 * _C1_SE_K * _C1_DELTA_SE)


def test_lower_bounds_never_negative():
    lo = c1_leg_lower_bounds(-1, 0.001, 0.002, 0.997)   # δ 的 2SE 大于该腿本身
    assert all(v >= 0.0 for v in lo)


def test_lower_bound_gate_is_stricter_than_point():
    """A′ 的钱学:同一注,按下界判闸只会更严 —— 这是「δ 恰好准」不再是隐含前提的保证。"""
    pt = implied_handicap_lines(0.55, 0.25, 0.20, c1=True)
    line, ph, pd_, pa = next(r for r in pt if r[0] == -1)
    lo = c1_leg_lower_bounds(line, ph, pd_, pa)
    sp = 4.2
    assert lo[1] * sp - 1 < pd_ * sp - 1, "让平:下界 EV 必须 < 点估 EV"
    assert lo[0] * sp - 1 < ph * sp - 1, "让胜:同理"
