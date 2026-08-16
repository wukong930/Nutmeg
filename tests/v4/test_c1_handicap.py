"""C1 让球修正 — implied_handicap_lines(c1=True) + A′ δ 下界的不变量。

🚨 2026-08-16:δ 上了**联赛范围闸**,本文件全部判闸调用显式传 `league=_IN`。

在此之前这些不变量隐含「δ 处处适用」,而实测**不适用** ——
桥接检验判定「两锚系统性不同」⇒ 覆盖外一律不施加点估 δ。
⇒ 不传 league ⇒ 按未校准处理(方案 A),这些不变量在覆盖外**本来就不该成立**。
覆盖**外**的对照见文末 `TestDeltaScopeGate`。
⚠️ `c1=False`(eval/measurement)的调用**一律不传** —— 尺子不该被闸改口径。

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
    _C2_DELTA_A,
    _C2_DELTA_D,
    _C2_DELTA_H,
    _C2_SE_A,
    _C2_SE_D,
    _C2_SE_H,
    _UNCAL_SE,
    c1_leg_lower_bounds,
    implied_handicap_lines,
)

_IN = "EPL"      # δ 实测覆盖内(见 market_handicap._DELTA_CALIBRATED_LEAGUES)
_OUT = "JPN_J1"  # 覆盖外 —— 日职从未进过 δ 的校准人口


def _by_line(rows):
    return {ln: (ph, pd, pa) for ln, ph, pd, pa in rows}


def test_c1_shifts_line_minus1_conserving():
    args = (0.55, 0.25, 0.20)                      # 主热;−1 线让胜 ≈0.32 > δ(不 clamp)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True, league=_IN))
    r, c = raw[-1], c1[-1]
    assert c[0] == pytest.approx(r[0] - _C1_DELTA)   # 让胜 −δ
    assert c[1] == pytest.approx(r[1] + _C1_DELTA)   # 让平 +δ
    assert c[2] == pytest.approx(r[2])               # 让负 不动
    assert sum(c) == pytest.approx(sum(r))           # 质量守恒


def test_c1_shifts_line_plus1_mirror_conserving():
    args = (0.20, 0.25, 0.55)                      # 客热;+1 线让负 ≈0.32 > δ(不 clamp)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True, league=_IN))
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
    c1 = _by_line(implied_handicap_lines(*args, c1=True, league=_IN))
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
    c1 = _by_line(implied_handicap_lines(*args, c1=True, league=_IN))
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
    """哪些腿被下界修正 —— **期望值写死字面量,不用常数反推**。

    ⚠️ 2026-08-07(P0-3)重写。原版是 `d = _C1_SE_K * _C1_DELTA_SE` 再断言
    `lo[0] == 0.30 - d` —— **用同一个常数推出期望值**,所以 `_C1_SE_K` 从 2.0
    改成 0.1 时 `d` 跟着变,断言照样过。钱路审查实测:那个改动**全量 3,182 条零红**,
    而它把整套 A′ 保守带缩了 20 倍(下界≈点估 ⇒ 让球闸实质失效)。

    ⭐ 规矩:**断言值别连带断言结构**。结构(哪条腿被碰)和数值(碰多少)要分开钉,
    数值那半必须是外部算好的常数。
    """
    # 0.30 − 2.0×0.0078 = 0.2844;0.22 − 2.0×0.0078 = 0.2044(手算,不引常数)
    lo = c1_leg_lower_bounds(-1, 0.30, 0.22, 0.48, league=_IN)
    assert lo[0] == pytest.approx(0.2844, abs=1e-9)   # 让胜(被 C1 减过)→ 再减 k·SE
    assert lo[1] == pytest.approx(0.2044, abs=1e-9)   # 让平(被 C1 加过)→ δ 若更小则更低
    # ⭐ 2026-08-08 改:第三腿(−1 让负)原来断言 `== 0.48`,即**下界 == 点估**。
    # 那条断言忠实地钉住了当时的行为,而**行为本身是错的** —— 「没被 C1 碰过」
    # 被消费者 `_boardLegs` 读成「没有不确定性」,可它自己的 SE 和兄弟一样大
    # (实测 0.0077 vs 0.0071)。按本文件自己的规矩,这是一次审慎决定,
    # 所以它红得对、也确实逼人回来改了记录。
    # 0.48 − 2.0×0.0077 = 0.4646(手算,不引常数)
    assert lo[2] == pytest.approx(0.4646, abs=1e-9)   # 让负:无 δ 修正,但有自己的 SE
    # 0.22 − 2.0×0.0101 = 0.1998;0.28 − 2.0×0.0101 = 0.2598;0.50 − 2.0×0.0103 = 0.4794
    lo1 = c1_leg_lower_bounds(+1, 0.50, 0.22, 0.28, league=_IN)
    assert lo1[0] == pytest.approx(0.4794, abs=1e-9)  # +1 让胜:同上,吃自己的 SE
    assert lo1[1] == pytest.approx(0.1998, abs=1e-9)
    assert lo1[2] == pytest.approx(0.2598, abs=1e-9)


def test_no_gateable_handicap_leg_gets_a_free_pass():
    """⭐ **行为**断言:任何会被判闸的让球腿,折扣都必须 > 0。

    `lo == p` 等于断言 **SE = 0**,而 SE=0 是**确定错的** —— 同
    `onex_calibration.py` 那句话。消费者 `_boardLegs` 拿 `evLo` 当排序键 + 5% 闸,
    零折扣的腿在与被收 1.5–2pp 的兄弟抢每场 argmax 时**系统性占便宜**。
    实测(修前):那条零收缩腿六选一拿下 **55.4%** 的 argmax。

    ⛔ 断言的是**性质**不是**数值** —— 任何正的 SE 都能让它绿,所以它不会变成
    下一个「改常数就误报」的护栏(本文件开头那条病历讲的正是那种)。
    ⚠️ 线 0 不在判闸集里:竞彩**从不开 0 线**(`jingcai_odds_history` 实测 0 行),
    而 `_boardLegs` 只取 `pr.jc_hc_line` 那一条线。
    """
    offered = (-3, -2, -1, 1, 2, 3)
    # 三张不同形状的卡:免得某一张的触底钳位偶然遮住失败
    for fair in ((0.4180, 0.2914, 0.2906), (0.6200, 0.2200, 0.1600),
                 (0.2500, 0.2600, 0.4900)):
        for ln, ph, pd_, pa in implied_handicap_lines(*fair, 0.52, c1=True, league=_IN):
            if ln not in offered:
                continue
            legs = c1_leg_lower_bounds(ln, ph, pd_, pa, league=_IN)
            for cn, pt, bound in zip(("让胜", "让平", "让负"), (ph, pd_, pa), legs,
                                     strict=True):
                if bound == 0.0:
                    continue        # 触底钳位(深线上 p < k·SE)—— 合法的零折扣
                assert pt - bound > 1e-9, (
                    f"线{ln:+d} {cn}(p={pt:.4f}):lo == p ⇒ 判闸吃的是点估")


def test_conservatism_multiplier_is_pinned_by_value():
    """⭐ `_C1_SE_K` 的**量值**必须被钉住,不只是「存在且为正」。

    它是把点估变成判闸下界的那个乘数,**通吃每一条让球腿**(占腿位约 52%)。
    改小它 = 悄悄放松整套 A′ 判闸,而 P0-2 的护栏会全绿 —— 那些护栏守的是
    「判闸读 `PB.lo` 而不是 `P`」,**不是**「`PB.lo` 有多低」。两者互补,缺一半
    就是虚假的安全感。

    2.0 ≈ 95% 单侧,是**预注册的策略选择**,不是可调旋钮。要改必须走预注册
    (同「看过结局之后不许调参数」),改完把这里的数字一起改 —— 让它红一次是**目的**。
    """
    assert _C1_SE_K == 2.0, (
        f"_C1_SE_K = {_C1_SE_K},不是 2.0(≈95% 单侧)。"
        "调小 ⇒ 让球闸整体放松且没有别的东西会响;调大 ⇒ 更保守但会静默砍掉可投注腿。"
        "任一方向都要走预注册,不是在这里改个数。")


def test_delta_and_se_magnitudes_are_pinned_with_provenance():
    """⭐ δ 与 SE 的**量值**钉死 —— 每个数字后面都有 N 和 prereg 版本。

    原有断言只守「SE 比 v1.9 收缩值大」「+1 的 SE 比 −1 大」—— 都是**不等式**,
    对「三个 δ₋₂ 常数一起缩 10 倍」这种等比变化完全免疫(守恒和方向都不变)。
    审查实测:δ₋₂ 三个一起缩 10× ⇒ **零红**。

    这里钉字面量。δ 重估(prereg 走完)时这条会红 —— **那正是要的**:
    重估是一次审慎决定,应该逼人回来更新这份记录,而不是悄悄漂过去。
    """
    # v2.0 独立聚类 SE(prereg v2.0);括号里是样本量
    assert pytest.approx(0.0463, abs=1e-9) == _C1_DELTA       # δ₋₁ 点估
    assert pytest.approx(0.0078, abs=1e-9) == _C1_DELTA_SE    # δ₋₁ SE(N=3,131)
    assert pytest.approx(0.0320, abs=1e-9) == _C1_DELTA_P1    # δ₊₁ 点估
    assert pytest.approx(0.0101, abs=1e-9) == _C1_DELTA_P1_SE  # δ₊₁ SE(N=1,803)
    # δ₋₂ 三腿(prereg v1.8),守恒:−0.064 + 0.021 + 0.043 = 0
    assert pytest.approx((0.064, 0.021, 0.043), abs=1e-9) == (_C2_DELTA_H, _C2_DELTA_D, _C2_DELTA_A)
    assert pytest.approx((0.025, 0.023, 0.027), abs=1e-9) == (_C2_SE_H, _C2_SE_D, _C2_SE_A)
    # 未校准线(+2 / ±3)吃的地板 —— 借 +2 实测,秋季须重测
    assert pytest.approx(0.078, abs=1e-9) == _UNCAL_SE


def test_the_band_is_actually_wide_enough_to_matter():
    """行为侧:下界必须**真的**比点估低到能改变判闸结论的程度。

    上面两条钉的是常数;这条钉的是**后果** —— 万一有人绕开常数、在
    `c1_leg_lower_bounds` 里改了组合方式,常数没动但带塌了,这条会红。

    −1 线让胜:点估 0.30 → 下界 0.2844,差 1.56pp。在 SP=3.50 上
    EV 从 +5.0% 掉到 −0.5% ⇒ **足以翻转 +5% 闸**。带若缩到 0.1×,
    差只剩 0.08pp,EV 差 0.3pp,闸基本不动 —— 那才是审查发现的实质放松。
    """
    lo = c1_leg_lower_bounds(-1, 0.30, 0.22, 0.48, league=_IN)
    gap = 0.30 - lo[0]
    assert gap > 0.010, f"让胜下界只比点估低 {gap:.4f} —— A′ 保守带塌了"
    sp = 3.50
    assert 0.30 * sp - 1 >= 0.05, "fixture 前提:点估口径应过 +5% 闸"
    assert lo[0] * sp - 1 < 0.05, (
        f"下界口径也过闸了(EV={lo[0] * sp - 1:+.2%})—— 带不足以改变结论,判闸形同虚设")


def test_lower_bounds_identity_only_on_the_zero_line():
    """⚠️ 2026-07-27 **有意的行为变更**(prereg v1.8 §3),不是放松断言。

    本测试原先断言「C1 不碰的线 → 下界 = 点估」。那个语义是个**符号反了的 bug**:
    `se=0` 不只是「不修正」,它同时把 ① 前端 ± 带 `hypot(dHalf=0, frz)` 拉**窄**、
    ② 判闸 `evLo>=minEv` 变成直接拿点估过闸 —— **越不可信的线越容易变绿**。

    现在:0 线(无让球切分偏差可言)才是恒等;±1/−2 用各自实测 SE;其余未校准线
    吃地板 SE(借 +2 实测 ±7.82pp),下界一律严格低于点估。
    """
    assert c1_leg_lower_bounds(0, 0.4, 0.3, 0.3, league=_IN) == pytest.approx((0.4, 0.3, 0.3))
    for ln in (-3, -2, 2, 3):
        lo = c1_leg_lower_bounds(ln, 0.4, 0.3, 0.3, league=_IN)
        assert all(x < y for x, y in zip(lo, (0.4, 0.3, 0.3), strict=True)), (
            f"线 {ln} 的下界又等于点估了 —— 那个反转回来了")


def test_lower_bounds_are_not_a_distribution():
    """⚠️ 下界三元组和 < 1 —— 它是三个独立单腿下界,只配判闸。

    谁把它当分布归一化/喂模型,这条测试就是现场的说明书。
    """
    lo = c1_leg_lower_bounds(-1, 0.30, 0.22, 0.48, league=_IN)
    assert sum(lo) < 1.0
    # ⭐ 2026-08-08 改:原式是 `1.0 - 2*k*_C1_DELTA_SE`,把「**只有两条腿**被收缩」
    # 这个**结构**焊进了一个本来只想说「和 < 1」的测试。第三腿拿到自己的 SE 之后
    # 它就红了 —— 红得对,但也说明这一行超出了本测试的职责。
    # 现在按「三条腿各减各的 k·SE」写,并且**每个数都手算**(不引常数),
    # 遵守本文件开头那条「断言值别连带断言结构」。
    # 0.30−2×0.0078 + 0.22−2×0.0078 + 0.48−2×0.0077 = 0.2844+0.2044+0.4646
    assert sum(lo) == pytest.approx(0.2844 + 0.2044 + 0.4646, abs=1e-9)


def test_lower_bounds_never_negative():
    lo = c1_leg_lower_bounds(-1, 0.001, 0.002, 0.997, league=_IN)   # δ 的 2SE 大于该腿本身
    assert all(v >= 0.0 for v in lo)


def test_lower_bound_gate_is_stricter_than_point():
    """A′ 的钱学:同一注,按下界判闸只会更严 —— 这是「δ 恰好准」不再是隐含前提的保证。"""
    pt = implied_handicap_lines(0.55, 0.25, 0.20, c1=True, league=_IN)
    line, ph, pd_, pa = next(r for r in pt if r[0] == -1)
    lo = c1_leg_lower_bounds(line, ph, pd_, pa, league=_IN)
    sp = 4.2
    assert lo[1] * sp - 1 < pd_ * sp - 1, "让平:下界 EV 必须 < 点估 EV"
    assert lo[0] * sp - 1 < ph * sp - 1, "让胜:同理"


# ─────────────────────────────────────────────────────────────────────────────
# δ 联赛范围闸(2026-08-16 上线)—— 上面全部不变量都显式传 `league=_IN`,
# 本节是它们的**覆盖外对照**。没有这一节,上面那些只证明「覆盖内还工作」,
# 证明不了「覆盖外真的关掉了」。
# ─────────────────────────────────────────────────────────────────────────────

class TestDeltaScopeGate:
    """δ 点估只在**实测覆盖内**施加;覆盖外 = 裸网格 + 未校准地板 SE。"""

    _FAIR = (0.55, 0.25, 0.20)

    def _m1(self, **kw):
        return implied_handicap_lines(*self._FAIR, 0.52, lines=(-1,), **kw)[0]

    def test_delta_applies_inside_and_not_outside(self) -> None:
        """⭐ 承重条:同一组输入,覆盖内让胜被扣 δ、覆盖外分毫不动。"""
        inside = self._m1(c1=True, league=_IN)
        outside = self._m1(c1=True, league=_OUT)
        raw = self._m1(c1=False)
        assert inside[1] < outside[1], f"覆盖内没扣 δ:{inside} vs {outside}"
        assert outside == pytest.approx(raw, abs=1e-12), (
            f"覆盖外不该动:{outside} vs 裸 {raw}")

    def test_missing_league_is_treated_as_uncalibrated(self) -> None:
        """🚨 方案 A:**没传 league ⇒ 按未校准处理**(保守方向)。

        代价是「哪个调用点漏传,δ 就静默关掉」——
        对策是 `_SCOPE_STATS["suppressed_none"]` 让它可观测,见下一条。
        """
        assert self._m1(c1=True) == pytest.approx(self._m1(c1=False), abs=1e-12)

    def test_the_ruler_is_never_gated(self) -> None:
        """⚠️ `c1=False`(eval/measurement)**完全不受闸影响** —— 尺子不该被闸改口径。

        覆盖内/外/不传,三者在 `c1=False` 下必须逐字相同。
        """
        a = self._m1(c1=False, league=_IN)
        b = self._m1(c1=False, league=_OUT)
        c = self._m1(c1=False)
        # ⚠️ 别写成链式 `a == approx(b) == approx(c)` —— Python 会拆成
        #    `(a==approx(b)) and (approx(b)==approx(c))`,后半是 approx 比 approx。
        assert a == pytest.approx(b, abs=1e-12)
        assert a == pytest.approx(c, abs=1e-12)

    def test_chinese_and_english_league_labels_both_resolve(self) -> None:
        """🚨 白名单写英文键,而 `canonical_league("EPL")` 返回 **"英超"**。

        2026-08-15 第一次实现时两侧没都过归一 ⇒ **所有联赛都落在覆盖外**、
        δ 被全局静默关掉(包括那 10 个校准过的)。不报错、不红任何测试。
        这条红 = `_canon` 双侧归一又断了。
        """
        assert self._m1(c1=True, league="EPL") == pytest.approx(
            self._m1(c1=True, league="英超"), abs=1e-12)
        assert self._m1(c1=True, league="英超")[1] < self._m1(c1=False)[1]

    def test_out_of_scope_bounds_fall_back_to_the_uncalibrated_floor(self) -> None:
        """覆盖外的**下界**改吃 `_UNCAL_SE` 地板,不借用校准 SE。

        既然没施加点估 δ,就不能再用「在测过的联赛上 δ 有多准」的那批 SE ——
        那等于把**别人的精度**借给一个未知偏差。地板更宽 ⇒ 判闸更严(保守)。
        """
        p = (0.30, 0.22, 0.48)
        drop_in = p[0] - c1_leg_lower_bounds(-1, *p, league=_IN)[0]
        drop_out = p[0] - c1_leg_lower_bounds(-1, *p, league=_OUT)[0]
        assert drop_out > drop_in, f"覆盖外的带没变宽:{drop_out} vs {drop_in}"

    def test_zero_line_is_never_gated(self) -> None:
        """0 线无让球偏差可言 ⇒ 闸对它是 no-op,覆盖内外都返回点估。"""
        p = (0.4, 0.3, 0.3)
        assert c1_leg_lower_bounds(0, *p, league=_OUT) == pytest.approx(p, abs=1e-12)
        assert c1_leg_lower_bounds(0, *p, league=_IN) == pytest.approx(p, abs=1e-12)

    def test_scope_stats_make_a_missing_league_observable(self) -> None:
        """⛔ 三态计数器是方案 A 的**唯一**可观测性,别把它删成 no-op。

        `suppressed_none` 不为 0 = 有调用点漏传 league。
        """
        from nutmeg.v4.model.market_handicap import _SCOPE_STATS

        before = dict(_SCOPE_STATS)
        self._m1(c1=True, league=_IN)
        self._m1(c1=True, league=_OUT)
        self._m1(c1=True)
        assert _SCOPE_STATS["applied"] > before["applied"]
        assert _SCOPE_STATS["suppressed_league"] > before["suppressed_league"]
        assert _SCOPE_STATS["suppressed_none"] > before["suppressed_none"]


class TestNoServingPathDropsLeague:
    """🚨 **方案 A 的代价:哪个调用点漏传 league,δ 就静默关掉。**

    2026-08-16 线上实测到这个 bug:手填重定价端点(`/recommend/market-reprice`)
    构造的 `r` 字面量只有三个键,**没有 `league`** ⇒ `r.get("league")` 得 None
    ⇒ 按未校准处理 ⇒ 让球 ±1/−2 线改吃 `_UNCAL_SE` 地板。
    owner 截图上的西甲手填卡:**±80.9% / ±59.1% / ±24.8%**,
    正确值是 **±7.8% / ±5.7% / ±2.4%** —— 整整 10 倍;
    而且**点估也错**(让胜 0.1975 vs 正确的 0.1512,少扣了 δ 该扣的 4.6pp)。

    ⚠️ **它不报错、不红任何测试** —— 上线当天全套 3,200+ 测试全绿。

    ## 我当时的"验证"为什么没抓住

    重启后我查了 `_SCOPE_STATS["suppressed_none"] == 0` 并报「无调用点漏传」。
    但那是在**新进程里重放 `_market_handicap_lines`**,`r` 用的是 `sp-calc`
    端点返回的行(**带** league)。
    ⇒ 我测的是**同一个函数被另一个调用者调用**的情形。
       **六个调用点只验了一个,却报了「全部」** —— [[first-match-is-not-the-population]]。

    ## 所以本类驱动**端点**,不是函数

    每个能出让球线的服务端点各打一次,断言全程 `suppressed_none` **不增长**。
    ⭐ 判据是**计数器增量**而不是「有没有 δ」—— 后者会被「这条线本来就不吃 δ」冒充。
    """

    @staticmethod
    def _client():
        import os

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from nutmeg.v4.api import v4_router
        os.environ.setdefault("NUTMEG_V4_ARTIFACT_PATH", "data/v4_model_cat_lineups")
        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        return TestClient(app)

    _BODY = {"psc_home": 2.34, "psc_draw": 3.03, "psc_away": 3.64,
             "psc_over25": 2.04, "psc_under25": 1.85, "ou_line": 2.25}

    def test_market_reprice_passes_league_through(self) -> None:
        """手填重定价 —— **就是 2026-08-16 漏掉的那条**。"""
        from nutmeg.v4.model.market_handicap import _SCOPE_STATS

        c = self._client()
        before = _SCOPE_STATS["suppressed_none"]
        r = c.post("/api/v4/recommend/market-reprice",
                   json={**self._BODY, "league": _IN})
        assert r.status_code == 200, r.text
        assert _SCOPE_STATS["suppressed_none"] == before, (
            "传了 league 却仍有调用记为 suppressed_none ⇒ "
            "端点内部有一处没把它透传下去(2026-08-16 就是这个形态)")

    def test_market_reprice_actually_applies_delta_when_in_scope(self) -> None:
        """⭐ 行为对照:同一份盘口,覆盖内 vs 覆盖外,**点估和带宽都必须不同**。

        只断言「计数器没涨」会被「端点根本没算让球线」冒充,所以要这条。
        """
        c = self._client()

        def m1(**extra):
            r = c.post("/api/v4/recommend/market-reprice", json={**self._BODY, **extra})
            assert r.status_code == 200, r.text
            x = next(v for v in r.json()["handicap_lines"] if v["line"] == -1)
            return x["p_home"], x["p_home"] - x["p_home_lo"]

        p_in, band_in = m1(league=_IN)
        p_out, band_out = m1(league=_OUT)
        p_none, band_none = m1()
        assert p_in < p_out, f"覆盖内没扣 δ:{p_in} vs {p_out}"
        assert band_out > band_in * 5, (
            f"覆盖外的带没变宽:{band_out:.4f} vs {band_in:.4f} —— "
            f"`_UNCAL_SE` 地板是校准 SE 的 10 倍,差距应该很显眼")
        # 方案 A:不传 == 覆盖外
        assert (p_none, band_none) == pytest.approx((p_out, band_out), abs=1e-12)

    def test_market_handicap_endpoint_passes_league_through(self) -> None:
        """另一条出让球线的端点 —— 一起钉,别再只验一个。"""
        from nutmeg.v4.model.market_handicap import _SCOPE_STATS

        c = self._client()
        before = _SCOPE_STATS["suppressed_none"]
        r = c.post("/api/v4/recommend/market-handicap", json={
            "league": _IN, "date": "2026-08-17",
            "home_team": "A", "away_team": "B",
            "psc_home": 2.34, "psc_draw": 3.03, "psc_away": 3.64,
            "psc_over25": 2.04, "psc_under25": 1.85, "ou_line": 2.25,
            "handicap_home": -1,
            "odds_handicap_H": 5.0, "odds_handicap_D": 3.65, "odds_handicap_A": 1.53,
        })
        assert r.status_code == 200, r.text
        assert _SCOPE_STATS["suppressed_none"] == before, (
            "market-handicap 端点有一处没透传 league")
