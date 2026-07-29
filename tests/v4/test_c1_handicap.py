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
    """C1 只碰**已校准**的线:±1(v1.7 A′)+ −2(v1.8 δ₋₂,owner 口令 2026-07-27)。

    ⚠️ 本测试原先断言「只 ±1 变」。2026-07-27 owner 授权部署 δ₋₂ 后 −2 也在被
    校正之列 —— 这是**有意的行为变更**,不是放松断言。+2 依然不动(两锚量级差
    一倍、N≈40 钉不住,prereg v1.8 §0 明写「+2:不部署数字」),下面单独钉死。
    """
    args = (0.55, 0.25, 0.20)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True))
    calibrated = (-1, 1, -2)
    for ln in raw:
        if ln not in calibrated:
            assert c1[ln] == pytest.approx(raw[ln]), f"线 {ln} 未校准,不该被碰"
    for ln in calibrated:
        if ln in raw:
            assert c1[ln] != pytest.approx(raw[ln]), f"线 {ln} 已校准,应当被碰"
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
    """δ 的量级锁 —— 靶子是**真实赛果**,不是市场价。

    ⭐⭐ **v2.0(2026-07-29,owner 口令)回到不合并的独立估计。** 本测试上一版钉的是
    v1.9 的**收缩方向性**(两值必须落在各自 δ̂ 与总体 0.03667 之间);它如期变红,
    因为 v1.9 的前提被推翻了 —— 「δ₊₁ 站不住」来自一个**漏了别名层的 join**
    (裸 `normalize_name` 跳过 `to_v4_canonical` 的别名链,丢掉 59% 样本)。
    补上后样本 3,038→4,934,δ₊₁ 从 t=1.83 变成 **t=3.16**,不需要借力。

    改这两个数要先走 prereg(v1.7 → v1.8 → v1.9 → v2.0),别只改常量:
    C1 的靶子与**是否合并**都是设计决定,不是可随手调的旋钮。
    """
    assert abs(_C1_DELTA - 0.0463) < 1e-9        # −1:N=3,131 独立聚类估计
    assert abs(_C1_DELTA_P1 - 0.0320) < 1e-9     # +1:N=1,803 独立聚类估计
    # ⭐ 序关系保留(自 v1.7 起一直成立):−1 的裸偏差实测就是比 +1 大
    assert _C1_DELTA > _C1_DELTA_P1
    # ⭐⭐ **反收缩锁** —— v1.9 断言两值落在 δ̂ 与总体 0.03667 之间;v2.0 断言它们
    # **就是各自的 δ̂**,没有被向任何中心拉。谁再引入合并,这两条会红。
    assert _C1_DELTA > 0.0456, "−1 被向某个总体拉了?v2.0 要的是独立估计"
    assert _C1_DELTA_P1 > 0.03, "+1 不该退回 v1.7 的 0.016 或被拉向别处"


def test_both_lines_are_independently_established_no_borrowing():
    """⭐⭐ v2.0 的**核心不变式**:两条线各自 `δ − 2·SE > 0`,谁都不靠谁。

    这是 v2.0 存在的全部理由。v1.9 时 +1 的独立下界是 **−0.0023**(不做功),
    只有借了 −1 的精度才转正;现在它自己就是 **+0.0118**。
    若哪天这条红了 ⇒ 要么 join 又退化了、要么有人动了 SE,**先查 join 再查常数**。
    """
    for lab, d, se in (("−1", _C1_DELTA, _C1_DELTA_SE),
                       ("+1", _C1_DELTA_P1, _C1_DELTA_P1_SE)):
        assert d - _C1_SE_K * se > 0, f"{lab} 的判闸下界转负 —— 该腿的修正不再做功"


def test_ses_are_the_honest_unpooled_ones_not_the_borrowed_ones():
    """⚠️ SE **必须比 v1.9 的收缩值大** —— 小 SE 是借来的,不是测出来的。

    v1.9: SE₋₁=0.00693 / SE₊₁=0.00787(向对方借精度的产物)
    v2.0: SE₋₁=0.0078  / SE₊₁=0.0101 (各自的聚类 SE)

    ⭐ 这条防的是一个**很容易犯且很难看出**的错:只把 δ 换成新值、SE 留旧的。
    那样判闸会得到一个谁也没测过的量(新点估 + 借来的精度),而且**看起来更强**
    —— 正是「越不可信越容易变绿」那类 bug 的形状。
    """
    assert _C1_DELTA_SE > 0.00693, "SE₋₁ 小于 v1.9 收缩值 ⇒ 还在借精度"
    assert _C1_DELTA_P1_SE > 0.00787, "SE₊₁ 小于 v1.9 收缩值 ⇒ 还在借精度"
    # 且 +1 的 SE 必须比 −1 大 —— 它样本更少(1,803 vs 3,131),这是物理事实
    assert _C1_DELTA_P1_SE > _C1_DELTA_SE, "样本更少的 +1 反而更精确?SE 配错了"


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


def test_lower_bounds_identity_only_on_the_zero_line():
    """⚠️ 2026-07-27 **有意的行为变更**(prereg v1.8 §3),不是放松断言。

    本测试原先断言「C1 不碰的线 → 下界 = 点估」。那个语义是个**符号反了的 bug**:
    `se=0` 不只是「不修正」,它同时把 ① 前端 ± 带 `hypot(dHalf=0, frz)` 拉**窄**、
    ② 判闸 `evLo>=minEv` 变成直接拿点估过闸 —— **越不可信的线越容易变绿**。

    现在:0 线(无让球切分偏差可言)才是恒等;±1/−2 用各自实测 SE;其余未校准线
    吃地板 SE(借 +2 实测 ±7.82pp),下界一律严格低于点估。
    """
    assert c1_leg_lower_bounds(0, 0.4, 0.3, 0.3) == pytest.approx((0.4, 0.3, 0.3))
    for ln in (-3, -2, 2, 3):
        lo = c1_leg_lower_bounds(ln, 0.4, 0.3, 0.3)
        assert all(x < y for x, y in zip(lo, (0.4, 0.3, 0.3), strict=True)), (
            f"线 {ln} 的下界又等于点估了 —— 那个反转回来了")


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
