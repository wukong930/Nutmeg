"""V12 W8 — market-implied 让球 (handicap) from Pinnacle 1X2 + over/under.

Fits a Dixon-Coles goal grid to BOTH the de-vigged Pinnacle 1X2 AND the
Pinnacle over/under line, then reads off any integer handicap line's
让胜/让平/让负 probabilities. Pure market — no model.

Why this exists
---------------
竞彩 让球 is a 3-way European handicap on an integer line (−1 = 主队让1球).
Computing it needs a goal-margin distribution. The production CatBoost model
is out-of-distribution for J1 + cups (the cup ablation was negative; J1
diverges ~13pp from the sharp line). So for those surfaces we DON'T use the
model — we reverse-engineer the goal distribution from two sharp Pinnacle
markets:

  - de-vig 1X2          → pins λ_diff = λ_home − λ_away (the supremacy)
  - de-vig over/under   → pins λ_total = λ_home + λ_away (the goal level)

Two anchors uniquely determine (λ_home, λ_away); the DC grid then gives every
handicap line. When the O/U is missing we fall back to a 1X2-only fit (the
draw rate weakly constrains the total — empirically within ~1pp on the
handicap, slightly optimistic on the favourite's 让胜).

Distinct from ``national_team_handicap.lambdas_from_1x2``, which FIXES
λ_total at a constant prior (WC had no reliable O/U). Anchoring λ_total to
the actual O/U is what makes this accurate.

Validation
----------
Fit only to 1X2 + O/U, the resulting grid reproduces Pinnacle's OWN Asian
Handicap cover probability within ~1pp across a full J1 matchday (the AH line
was held out, never fitted) — i.e. Pinnacle's own money agrees with the
reverse-mapped goal distribution. See tests/v4/test_market_handicap.py.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize

from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_handicap_1x2,
    grid_to_margin_bands,
    score_grid,
)

# Production DC low-score correction (matches gbm_rho default).
DEFAULT_RHO = -0.10
# Score-grid truncation. Goals >9 are vanishingly rare; 10 is ample headroom
# for blowouts (the 让胜 tail) while keeping the fit fast.
DEFAULT_MAX_GOALS = 10
# Integer handicap lines 竞彩 offers (主队 −3..+3). −1 = 主队让1球.
DEFAULT_LINES = tuple(range(-3, 4))

# Loss weights. The 1X2 is the sharper, lower-vig market, so weight matching
# it above the O/U. These reproduce the ~1pp AH cross-check (see module docstring).
_W_1X2 = 4.0
_W_OU = 2.0

# Fit search domain. λ outside [0.2, 3.4] is unphysical for a single team's
# expected goals; the bounds keep score_grid's λ>0 precondition satisfied.
_LAMBDA_BOUNDS = (0.2, 3.4)
_LAMBDA_X0 = (1.20, 1.05)


def devig_over(odds_over, odds_under) -> float | None:
    """2-way de-vig of an over/under pair → P(over). None if either leg is
    missing or non-positive (caller then fits 1X2-only).

    DELIBERATELY basic normalization (the 1X2 de-vig is WPO; this stays basic) —
    don't "fix" the inconsistency. MEASURED 2026-06-26 on 23,840 football-data
    Pinnacle-closing matches: routing this through WPO shifts the reconstructed
    让球 P by ~0.05pp median (p99 0.22pp, max 0.71pp on the most lopsided totals)
    with ZERO calibration change (3-way logloss Δ=−6e-6, paired-bootstrap 95% CI
    [−2e-5,+1e-5] straddles 0). 0.05pp P ≈ 0.1pp EV vs the +5% bar → ~50× too
    small to flip any pick. The O/U leg only nudges λ_total (2nd-order for
    integer-line cover); the already-WPO 1X2 split dominates. See
    docs/devig_method_comparison.md §5."""
    try:
        o = float(odds_over)
        u = float(odds_under)
    except (TypeError, ValueError):
        return None
    if not (o > 1.0 and u > 1.0):
        return None
    inv_o, inv_u = 1.0 / o, 1.0 / u
    return inv_o / (inv_o + inv_u)


def asian_total_over_prob(grid: np.ndarray, line: float) -> float:
    """P(over) at any Asian total ``line`` from a Dixon-Coles score grid,
    counting a push (stake refunded) as half a win.

    Handles the three Asian-line families 竞彩/Pinnacle actually quote:

      - half line  (…, 2.5, 3.5): no push — ``P(total > line)``.
      - whole line (…, 2.0, 3.0): pushes when ``total == line`` — adds
        ``0.5·P(==line)``.
      - quarter line (…, 2.25, 2.75): the stake splits 50/50 across the two
        neighbouring lines (2.25 = ½·2.0 + ½·2.5), so the over prob is the mean
        of those two single-line values.

    Why this matters: :func:`fit_lambdas` anchors λ_total to this number.
    Treating a 2.25 line as a 2.5 line (the old hard-coded assumption) biases
    λ_total high — on a typical J1 total by ~+0.22 goals, shifting the 让球 P by
    ~1pp. The push-as-half convention makes ``over + under == 1`` at every line,
    consistent with the 2-way de-vig in :func:`devig_over`.

    Reduces EXACTLY to ``grid_to_over_under(grid, line)[0]`` at half lines, so
    the default-2.5 serving path is unchanged.
    """
    tot: dict[int, float] = {}
    n = grid.shape[0]
    for i in range(n):
        for j in range(n):
            tot[i + j] = tot.get(i + j, 0.0) + float(grid[i, j])

    def _single(ell: float) -> float:
        # A push (total == ell, only possible at whole lines) counts as half.
        return sum(
            p * (1.0 if k > ell else 0.5 if k == ell else 0.0)
            for k, p in tot.items()
        )

    frac = line - math.floor(line)
    if abs(frac - 0.25) < 1e-9 or abs(frac - 0.75) < 1e-9:
        return 0.5 * _single(line - 0.25) + 0.5 * _single(line + 0.25)
    return _single(line)


def fit_lambdas(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over: float | None = None,
    *,
    ou_line: float = 2.5,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
) -> tuple[float, float]:
    """Fit (λ_home, λ_away) so the DC grid reproduces the de-vig 1X2 — and the
    de-vig P(over) at ``ou_line`` when provided.

    Returns a positive (λ_home, λ_away) pair. ``p_over`` None → 1X2-only fit.
    """
    th = np.array([p_home, p_draw, p_away], dtype=float)
    s = th.sum()
    if s <= 0:
        raise ValueError("1X2 probabilities sum to zero")
    th = th / s

    def loss(x: np.ndarray) -> float:
        lh, la = float(x[0]), float(x[1])
        grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
        ph, pd_, pa = grid_to_1x2(grid)
        err = _W_1X2 * ((ph - th[0]) ** 2 + (pd_ - th[1]) ** 2 + (pa - th[2]) ** 2)
        if p_over is not None:
            over = asian_total_over_prob(grid, ou_line)
            err += _W_OU * (over - p_over) ** 2
        return float(err)

    res = minimize(
        loss,
        x0=np.array(_LAMBDA_X0, dtype=float),
        method="L-BFGS-B",
        bounds=[_LAMBDA_BOUNDS, _LAMBDA_BOUNDS],
    )
    return float(res.x[0]), float(res.x[1])


# C1 让球修正 — DC 网格系统性高估「热门方净胜≥2 的爆盘尾」,低估「净胜恰好1」(让平)。
# 结构(2026-07-17 在真实竞彩线上复核,质量守恒得几乎完美、第三腿分毫不动 → 结构正确):
#   −1 线(热门在主):让胜 +4.6pp / 让平 −4.7pp / 让负 +0.1pp → 让胜−δ / 让平+δ
#   +1 线(热门在客):让负 +1.6pp / 让平 −2.1pp / 让胜 +0.5pp → 让负−δ / 让平+δ(镜像)
#
# ⚠️ δ 于 2026-07-17 重估(owner 决定;docs/handicap_h2_calibration_2026-07-17.md,
# prereg v1.7)。**靶子从「DC−市场」换成「DC−真实赛果」** —— 旧 δ(−1: 0.019 / +1: 0.013)
# 拟合的是 DC 与让球市场价的差,而市场自己也高估让胜 ~2.7pp,于是 C1 把我们对齐到了一个
# 有偏的靶子:真实竞彩 −1 线上,旧 δ 修完仍余 +2.7pp(样本外 +3.5pp,z=2.5)= EV 虚高 +12.8pp。
#
# 新 δ 的证据(涓流真实竞彩线 × football-data Pinnacle 收盘锚 × 比分硬闸门,拒绝率 0.00%):
#   −1: N=1,882  裸偏差 +4.6pp(z=4.6);held-out train +3.7 / test +5.4(z=3.9)
#   +1: N=1,044  裸偏差 +1.6pp(z=1.2,弱 —— 0.013→0.016 纯为口径统一,不是证据驱动)
# 交叉验证:crown 路径(500 真实线 + 皇冠全收盘锚,N=3,505)−1 得 +4.2pp,换锚不变形。
# ⚠️ 合成线(把 −1 套到全样本)只得 +2.2pp = 稀释一半 —— 校准必须在真实竞彩线上测。
# ⭐⭐ v2.0(2026-07-29,owner 口令):**回到不合并的独立估计** —— 因为「+1 自己
# 站不住」这个前提被推翻了。v1.9 引入随机效应收缩的唯一理由是 δ₊₁ 当时 t=1.83、
# 判闸下界为负;而那个「测不出」来自一个**漏了别名层的 join**:
# `handicap_delta_homogeneity.py` 两侧只做 `normalize_name`,跳过了
# `to_v4_canonical` 的别名链 ⇒「Manchester United」永远对不上「Man United」,
# 59% 的样本被静默丢弃(命中率 41%)。走解析器后 67%,样本 3,038 → 4,934。
#
#   修前  δ₋₁ 0.0456±0.0098 (t=4.65) · δ₊₁ 0.0241±0.0132 (**t=1.83**,下界 −0.0023)
#   修后  δ₋₁ 0.0463±0.0078 (t=5.92) · δ₊₁ 0.0320±0.0101 (**t=3.16**,下界 +0.0118)
#
# ⇒ 两条线**各自独立确立**,不需要向对方借力 ⇒ 收缩(v1.9)与完全合并都作废。
# ⚠️ 巧合但别误读:v1.9 收缩出的 0.03220 和 v2.0 独立估的 0.0320 几乎相同 ——
# 那是「借力方向恰好对」的运气,不是方法对(k=2 上估 τ 本来就撑不住)。
#
# ⚠️ **代价是 +1 的判闸变弱**:SE 从借来的 0.00787 回到诚实的 0.0101 ⇒
# 下界 +0.0165 → +0.0118。这是放弃可交换性假设该付的价,不是退步。
# owner 授权时已知悉此项(prereg v2.0 §3)。docs/handicap_delta_prereg_v2.0_2026-07-29.md
_C1_DELTA = 0.0463      # −1 线:让胜 → 让平(v2.0;v1.9 收缩值 0.04113 / v1.7 0.046)
_C1_DELTA_P1 = 0.0320   # +1 线:让负 → 让平(镜像)(v2.0;v1.9 收缩值 0.03220 / v1.7 0.016)

# δ 的估计标准误 —— A′ 的核心:δ 不是精确值,它的误差 1:1 传进被修正的腿,
# 再乘 竞彩SP(让平常 ~4.2)放大成 EV 误差。判闸必须吃这个不确定性,否则
# 「δ 恰好准」就成了下注的隐含前提(实测:按 δ−2SE 判闸,那 30 张让平票全部消失
# ⇒ 它们的 +EV 完全依赖 δ 点估无误)。呼应 `记忆 ev-threshold-variance-sigmap`:
# 门槛是不确定性的函数,不是平的 5%。
# ⚠️ 这是**朴素二项 SE**,未做比赛日聚类 → 真实不确定性只会更大,故本带宽是**下限**。
# ── ⭐ v1.9(2026-07-28,owner 口令)—— ±1 改为**部分合并(随机效应收缩)** ──────
# 起因:功效分析发现 **δ₊₁ 是在 t=1.19、判闸下界为负的情况下上线的**(0.016/0.0135)。
# A′ 当时的理由是「修完残余不显著」—— 那是**修完看不出残余**,不等于**修正有效**。
# 而 N > 4p(1−p)/δ² 说明确立 δ=0.016 需 N≈3,700(朴素)/5,500-7,400(聚类),
# 竞彩每年只开约 660 场 +1 线 ⇒ **≈8 年**。「等 N 攒够」对小 δ 是无效策略。
#
# ⭐ 洞察:**分开拟合是 +1 确立不了的直接原因**。win-by-one clustering(领先方收缩
# 防守)是**一个物理机制**,不关心领先的是主队还是客队;劈成两半则两半都不够样本。
#
# 同源性检验(scripts/handicap_delta_homogeneity.py,真实竞彩线 × Pinnacle 锚,
# 比分硬闸门拒绝率 0.00%):−1 δ̂=0.0456(N=1,958,聚类SE 0.0098,t=4.65);
# +1 δ̂=0.0241(N=1,080,SE 0.0132,t=1.83);**z=+1.31 拒绝不了同源**。
# 三项稳健性全过:半分稳定、构成效应重加权后差距不动(+0.0215→+0.0223)、
# 管线自验(独立重实现 δ₋₁=0.0456 vs 线上 0.046)。
#
# 部署 = **部分合并**而非全合并:先由数据估计线间异质性 τ²=9.60e-05(τ=0.0098),
# 再按各自精度收缩。全合并**假设** τ=0,而我们估出 τ≠0;部分合并让数据决定收缩量,
# 且代价更小(−1 让胜判闸只松 1.1pp 而非 1.2pp)。
#
# ⚠️⚠️ **本次最弱的一环,必须留在代码里**:同源性检验**只有 26% 功效**
# (真实差 0.0215 时也有 74% 概率看不出来)。「拒绝不了同源」≈「没能力分辨」,
# **不是「证明了同源」**。且这是**同一批数据的重拟合**(A′ 用的也是它)。
# ⇒ 本次是在「证据不足但方向合理 + 损失函数不对称」下的判断,**不是已证实的实施**。
# ⚠️ 收缩后的 SE 比原始 SE 更紧,这**借用了可交换性假设** —— 即那条只有 26% 功效
# 支持的假设。更保守的变体(收缩点估 + 保留原 SE)见 prereg v1.9 §3;owner 明确
# 授权了收缩 SE 版。回滚条件见 prereg §4。
_C1_DELTA_SE = 0.0078      # v2.0 **独立**聚类SE(δ₋₁,N=3,131);v1.9 收缩值 0.00693
_C1_DELTA_P1_SE = 0.0101   # v2.0 **独立**聚类SE(δ₊₁,N=1,803);v1.9 收缩值 0.00787
_C1_SE_K = 2.0             # 判闸用的保守倍数(≈95% 单侧)

#: ±1 线上**没被 C1 碰过**的那条腿的聚类 SE(δ 第三腿,2026-08-08 上线)。
#:
#: ⭐ 为什么需要它:C1 重构只碰两条腿,第三条是锚 —— 「无 δ 误差」这句话**对**。
#: 但 `c1_leg_lower_bounds` 原来对它返回 `float(p_*)`,即下界 == 点估,
#: 而消费者 `_boardLegs` 的 `evLo` 是**排序键 + 5% 闸**。
#: ⇒ 「没被这次校准碰过」被读成了「**没有不确定性**」。
#: 这是同族第三次发作:① `_UNCAL_SE` 修 |line|≥2、② δ₁ₓ₂ 修 1X2 家族,
#: ±1 线的第三腿两次都没盖到。`onex_calibration.py` 那句话字面上就在判本案:
#: 「保持 lo=p 等于断言 SE=0,那是**确定错的**」。
#:
#: 预注册 `docs/c1_third_leg_se_prereg_v1.0_2026-08-08.md`(测量前提交,且**如实
#: 标注是探索性测量之后的确认轮**);测量 `docs/c1_third_leg_se_measurement_2026-08-08.md`;
#: 复现 `scripts/c1_third_leg_se.py`(复用 δ₋₁/δ₊₁ 当初那把尺子,一行没改)。
#:
#: ⛔ **点估一律不动**:−1 让负 δ̂=−0.0029 t=−0.38、+1 让胜 δ̂=−0.0150 t=−1.45,
#: 都测不出偏差 ⇒ 不出点估修正。同 δ₁ₓ₂ 的立场:编常数比缺常数更坏。
#: ⛔ **不借 `_UNCAL_SE`**:那是跨家族借地板(δ₁ₓ₂ 那轮已否决)。第三腿是在
#: **同一批样本、同一次重构**上直接测出来的,不需要借。
#: ⚠️ 范围:football-data 覆盖的欧洲联赛;日职/杯赛/北欧/韩职 **0 覆盖**,
#: 与 δ₁ₓ₂ 记录的是同一条 caveat。锚死于 2026-01-14(Pinnacle 末日)。
_C1_THIRD_SE_M1 = 0.0077   # −1 线 让负(N=3,878 / 799 比赛日,比赛日聚类;兄弟 0.0071)
_C1_THIRD_SE_P1 = 0.0103   # +1 线 让胜(N=2,217 / 680 比赛日,比赛日聚类;兄弟 0.0091)

# ── δ₋₂(−2 线)—— prereg v1.8 / owner 口令 2026-07-27 ─────────────────────
# 测量:docs/handicap_delta2_measurement_2026-07-20.md(N=340,fd+皇冠双锚同向,
# 时代切片同向 2021-23 +3.5 / 2024+ +7.5,SE 内)。
#   让胜(净胜 3+ 深尾)实测 **+6.4±2.5pp 高估** → 校正 −0.064
#   让负                 实测 −4.3±2.7pp 低估 → 校正 +0.043
#   让平                 守恒残差 +0.021 —— 而这**恰好等于**它自己的点估
#                        (实测 −2.1±2.3,自身跨零故文档写「不动」;但三腿必须
#                         守恒,残差总得落地,两条独立理由指向同一个数)。
# 守恒:−0.064 + 0.043 + 0.021 = 0.000 ⇒ 仍是合法概率三元组,可用于展示。
# 危险度:该腿 P̄≈39%(**甜区**)、中位 SP 2.43 ⇒ 幻影 EV +12~20%,而 ±1 深尾
# (P 15-20%)有冷门门槛拦 —— 这条腿此前**任何护栏都不覆盖**。
_C2_DELTA_H = 0.064        # −2 让胜:P − δ
_C2_DELTA_A = 0.043        # −2 让负:P + δ
_C2_DELTA_D = 0.021        # −2 让平:P + δ(守恒残差,= 自身点估)
_C2_SE_H, _C2_SE_A, _C2_SE_D = 0.025, 0.027, 0.023

# ── 未校准线的**下界地板**(+2 / ±3 / 更深)—— prereg v1.8 §3 ─────────────
# ⚠️ **+2 不出点估校正**:fd 让胜 −14.80±7.82 vs 皇冠 −2.93±7.77 —— 方向同、
# 量级差一倍、N≈40,测量文档明写「+2:不部署数字」。编一个常数比缺常数更坏。
# 但 se=0 的老写法有个**符号反了**的副作用(prereg §3):下界=点估 ⇒ ① 前端
# ± 带 hypot(dHalf=0, frz) 反而**变窄**,② 判闸 `evLo>=minEv` 直接拿点估过 ——
# **越不可信的线越容易变绿**。所以:不猜点估,但下界按地板 SE 拉宽。
# 0.078 = +2 两锚实测 SE 的较大者(fd ±7.82),是**实测量级不是猜测**;用在
# ±3+ 上是**借来的**(±3+ 从未测过),家族病灶随深度只会更大 ⇒ 借用属保守方向。
# ⚠️ 秋季 P1 回填后必须重测,不许当永久常数。
_UNCAL_SE = 0.078


# ─────────────────────────────────────────────────────────────────────────────
# 🚨 δ 的**联赛适用范围闸**(2026-08-16 上线;方案
#    `docs/delta_league_scope_gate_plan_2026-08-14.md`,两次回滚后的第三次)
#
# 本文件顶部注释从一开始就写着「范围:football-data 覆盖的欧洲联赛;
# 日职/杯赛/北欧/韩职 **0 覆盖**」—— 但 `grep -n league` 在本文件曾**零命中**:
# **警告写在注释里,闸没写在代码里。**
#
# 预定动作(不是新提案):锚迁移桥接检验判定落在「① 不过」——
# Pinnacle 与 Betfair 两锚在让胜腿系统性不同(+0.4070pp / t=17.0;
# −2 线达 ±0.010 等价界的 **178%**)⇒ §2.4 逐字写着
# 「⛔ 不换锚,且现行 δ 值的适用性存疑 ⇒ **覆盖外一律不施加点估 δ**」。
# 配套事实(2026-08-13 审计):当日可投注人口只有 **102/2,352 = 4.3%** 在覆盖内,
# 而**过闸的 8 条腿 0/8 在覆盖内** —— 全系统最大的单常数杠杆,
# 正被全额施加在一个它从未被测量过的人口上。
#
# ⚠️ 白名单**跑尺子自己的加载器取的,不是猜的**(6,095 场合格样本的联赛分布):
#     英超 1171 / 意甲 1041 / 西甲 1009 / 法甲 646 / 德甲 602
#     英冠 523 / 荷甲 412 / 葡超 378 / 法乙 284 / 德乙 29
# 🚨 是 **10 个不是 9 个** —— 我和记忆文件一直写「9 个欧洲联赛」,错的。
# 🚨 **文件数 ≠ 联赛数**:football-data 有 13 个文件带 Pinnacle 收盘(25,941 行),
#    但 B1/N1/SP2 三个**从未 join 上竞彩让球** ⇒ 校准人口只有这 10 个。
# ⚠️ 德乙只有 29 场也进白名单:δ 是**池化**估计(同源性 z=1.40,拒绝不了同源)
#    ⇒ 白名单 = δ 的实测人口,**不另发明「每联赛最小样本量」**(那是事后加判据)。
_DELTA_CALIBRATED_LEAGUES = frozenset({
    "EPL", "ITA_SERIE_A", "ESP_LA_LIGA", "FRA_LIGUE_1", "GER_BUNDESLIGA",
    "ENG_CHAMPIONSHIP", "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA",
    "FRA_LIGUE_2", "GER_2_BUNDESLIGA",
})

#: 三态计数器 —— 方案 A(`league=None` ⇒ 按未校准处理)的**唯一可观测性**。
#: `suppressed_none` 不为 0 = **有调用点漏传 league**。
#: ⛔ 别把它删成 no-op:方案 A 的代价就是「漏传会静默关掉 δ」,
#:    这个计数器是把「静默」变回可见的那个东西。
_SCOPE_STATS: dict[str, int] = {
    "applied": 0,             # 覆盖内,点估已施加
    "suppressed_league": 0,   # 联赛在覆盖外 ⇒ 不施加(**预期形态**,不是异常)
    "suppressed_none": 0,     # 没传 league ⇒ 不施加(**可能是漏传,要查**)
}

_CANON_SCOPE: frozenset[str] | None = None


def _canon(league: str) -> str:
    """联赛标签 → 正典形。⚠️ `canonical_league` 归一到**中文**(`EPL`→`英超`)。"""
    from nutmeg.v4.data.league_labels import canonical_league

    return canonical_league(league) or ""


def _canonical_scope() -> frozenset[str]:
    """白名单的**正典形**(缓存一次)。

    🚨 2026-08-15 实测踩过:白名单写英文键,而 `canonical_league("EPL")` 返回
    **`"英超"`** ⇒ 直接拿英文键比,**所有联赛都落在覆盖外**、δ 被全局静默关掉
    (包括那 10 个校准过的)。**不报错、不红任何测试、面板照常出数。**
    ⇒ **两侧都必须过归一**。
    ⭐ 它唯一被抓住的原因是我把 `_delta_in_scope("EPL")` 的返回值**打出来看了一眼**
       —— 只写「加了闸」就交付的话,它会静默生效成「到处都不施加」,
       正好和闸的本意相反。
    ⛔ 别改成「白名单直接写中文」:英文键是尺子加载器的输出形态,
       写中文会让「白名单从哪来」这条线索断掉。
    """
    global _CANON_SCOPE
    if _CANON_SCOPE is None:
        _CANON_SCOPE = frozenset(
            c for x in _DELTA_CALIBRATED_LEAGUES if (c := _canon(x)))
    return _CANON_SCOPE


def _delta_in_scope(league: str | None) -> bool:
    """δ 点估是否适用于该联赛。**方案 A:传 None ⇒ 按未校准处理**(保守方向)。

    ⚠️ 内部先过 `canonical_league`,所以中文(`英超`)或英文键都行 ——
    但**传 None 不等于「全局」**,它等于「不知道 ⇒ 不施加」。
    """
    if league is None or league == "":
        _SCOPE_STATS["suppressed_none"] += 1
        return False
    if _canon(league) in _canonical_scope():
        _SCOPE_STATS["applied"] += 1
        return True
    _SCOPE_STATS["suppressed_league"] += 1
    return False


def c1_leg_lower_bounds(
    line: int, p_home: float, p_draw: float, p_away: float, *, k: float = _C1_SE_K,
    league: str | None = None,
) -> tuple[float, float, float]:
    """给 **已应用 C1(点估)** 的三元组,返回每条腿在 δ 估计误差下的**自身下界**。

    🚨 `league` 在**覆盖外**(或没传)时,非 0 线一律改吃 `_UNCAL_SE` 地板 ——
    既然没施加点估 δ,就不能再用「在测过的联赛上 δ 有多准」的那批 SE:
    那等于把**别人的精度**借给一个未知偏差。与 +2/±3 未校准线同一处理。

    保守方向是**逐腿**的 —— 每条腿取「让它自己的 P 更小」的那侧:
      −1 线:让胜 = 点估 − k·SE(δ 若更大 → 让胜更低);让平 = 点估 − k·SE(δ 若更小 → 让平更低)
      +1 线:让负 / 让平 同理;未被 C1 碰的第三腿无 δ 误差 → 下界 = 点估。
    (代数上两侧都落到「点估 − k·SE」,因为点估 = raw∓δ。)

    ⚠️ **返回值不是概率分布**(和 < 1)—— 它是三个独立的单腿下界,**只用于判闸**,
    绝不可用于展示/归一化/喂模型。展示请用点估(``implied_handicap_lines(c1=True)``)。
    """
    ln = int(line)
    if ln != 0 and not _delta_in_scope(league):
        d = k * _UNCAL_SE    # 覆盖外:点估没施加过 ⇒ 校准 SE 不适用,吃地板
        return (max(p_home - d, 0.0), max(p_draw - d, 0.0), max(p_away - d, 0.0))
    if ln == -1:             # C1 碰了 让胜 + 让平;让负是锚(无 δ 误差,但**有** SE)
        d = k * _C1_DELTA_SE
        return (max(p_home - d, 0.0), max(p_draw - d, 0.0),
                max(p_away - k * _C1_THIRD_SE_M1, 0.0))
    if ln == 1:              # 镜像:让平 + 让负被碰;让胜是锚
        d = k * _C1_DELTA_P1_SE
        return (max(p_home - k * _C1_THIRD_SE_P1, 0.0),
                max(p_draw - d, 0.0), max(p_away - d, 0.0))
    if ln == -2:             # δ₋₂(prereg v1.8)—— 三腿全被碰,逐腿用**自己的** SE
        return (max(p_home - k * _C2_SE_H, 0.0),
                max(p_draw - k * _C2_SE_D, 0.0),
                max(p_away - k * _C2_SE_A, 0.0))
    if abs(ln) >= 2:         # 未校准线(+2 / ±3 / 更深)—— 不猜点估,但拉宽下界
        # 老写法在这里返回点估(se=0),等于「没测过校准」被当成「没有不确定性」:
        # 前端 ± 带反而变窄、判闸门槛反而更低。见 prereg v1.8 §3。
        d = k * _UNCAL_SE
        return (max(p_home - d, 0.0), max(p_draw - d, 0.0), max(p_away - d, 0.0))
    return float(p_home), float(p_draw), float(p_away)   # 0 线:无让球偏差可言


def implied_handicap_lines(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over: float | None = None,
    *,
    lines=DEFAULT_LINES,
    ou_line: float = 2.5,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
    c1: bool = False,
    league: str | None = None,
) -> list[tuple[int, float, float, float]]:
    """Fit the goal grid once, then return ``(line, P让胜, P让平, P让负)`` for
    each integer handicap line.

    ``line`` is ``handicap_home`` in DC convention (added to home's score):
    −1 = 主队让1球, +1 = 主队受让1球. The triple is
    (P(home covers), P(push), P(away covers)).

    ``c1=True`` applies the **C1 让球修正** on the ±1 lines (serving path;
    eval/measurement keeps raw): −1 移 ``_C1_DELTA`` 让胜→让平;+1 移
    ``_C1_DELTA_P1`` 让负→让平。守恒(和仍 =1),故可用于展示。
    **判闸别只用这个** —— δ 自带估计误差,见 ``c1_leg_lower_bounds``。
    """
    lh, la = fit_lambdas(
        p_home, p_draw, p_away, p_over,
        ou_line=ou_line, rho=rho, max_goals=max_goals,
    )
    grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
    # 🚨 范围闸:`c1=True` **且**联赛在 δ 实测覆盖内才施加点估。
    # ⚠️ `c1=False`(eval/measurement)**完全不受影响** —— 尺子不该被闸改口径。
    # ⚠️ 方案 A:`league=None` ⇒ 按未校准处理(保守)。漏传会静默关掉 δ,
    #    靠 `_SCOPE_STATS["suppressed_none"]` 让它可见。
    _c1 = bool(c1) and _delta_in_scope(league)
    out: list[tuple[int, float, float, float]] = []
    for line in lines:
        ph, pd_, pa = grid_to_handicap_1x2(grid, handicap_home=int(line))
        if _c1 and int(line) == -1:            # 热门在主:让胜(DC 高估)→ 让平
            shift = min(_C1_DELTA, ph)         # 守恒 + 不越界(ph 罕见 <δ 时不为负)
            ph, pd_ = ph - shift, pd_ + shift
        elif _c1 and int(line) == 1:           # 热门在客:让负(DC 高估)→ 让平(镜像)
            shift = min(_C1_DELTA_P1, pa)
            pa, pd_ = pa - shift, pd_ + shift
        elif _c1 and int(line) == -2:          # δ₋₂(prereg v1.8):让胜 → 让平 + 让负
            # 守恒:−0.064 + 0.021 + 0.043 = 0。让胜不够扣时按比例缩,保持和为 1
            # 且不越界(ph 罕见 < δ 的深线上,直接扣会出负概率)。
            shift = min(_C2_DELTA_H, ph)
            r = shift / _C2_DELTA_H if _C2_DELTA_H > 0 else 0.0
            ph = ph - shift
            pd_ = pd_ + _C2_DELTA_D * r
            pa = pa + _C2_DELTA_A * r
        # ⚠️ +2 / ±3+ **故意不出点估校正**(prereg v1.8 §0):+2 两锚量级差一倍、
        # N≈40 钉不住,编常数比缺常数更坏。它们只在 c1_leg_lower_bounds 里吃地板 SE。
        out.append((int(line), float(ph), float(pd_), float(pa)))
    return out


#: 让球腿的三个结果标签,下标与 `implied_handicap_lines` 返回的 (让胜, 让平, 让负) 一致。
HANDICAP_OUTCOME_LABELS = ("让胜", "让平", "让负")


def handicap_outcome(
    home_goals: int | None,
    away_goals: int | None,
    handicap_home: int | None,
) -> int | None:
    """让球后的结果下标 —— `0 让胜 / 1 让平 / 2 让负`,算不出返回 None。

    `handicap_home` 是**主队让球数**的带符号值:`-1` = 主让一球、`+1` = 主受让一球。
    让球后主队净胜球 = `(主进 − 客进) + handicap_home`。

    ## 为什么这条三行规则要单独成函数

    2026-08-10 复盘时发现它在仓库里有**三份独立实现**
    (`delta_calibration` / `handicap_delta_homogeneity` / `jingcai_staleness`),
    代数上都对 —— 但**第四个该有它的地方没有**:`settle_jingcai_sp` 结算时
    对让球行写的是 `_ft_outcome()` 的**原始 1X2 结果**,完全不看 `market` 列。

    ⚠️ 那个值**不是错的**(90′ 的 1X2 结果对让球行也是事实),它是个**陷阱**:
    列名 `ft_outcome`、类型 INTEGER、值域 {0,1,2} —— 三样都长得像能直接拿来算
    让球命中率。真那么用的话,实测 **404 行里 217 行(53.7%)结论是反的**。

    ⭐ 教训不是「有人写错了」,是**没人拥有这条规则** —— 三份拷贝各自都对,
    所以谁也没发现第四处压根没实现。同族:「加列同步补 SET」。

    ⛔ 别再写第四份。要判让球结果就调这里。
    """
    if home_goals is None or away_goals is None or handicap_home is None:
        return None
    margin = (int(home_goals) - int(away_goals)) + int(handicap_home)
    return 0 if margin > 0 else (1 if margin == 0 else 2)


def implied_margin_bands(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over: float | None = None,
    *,
    ou_line: float = 2.5,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
    tail: int = 4,
    top: int = 4,
) -> list[dict]:
    """净胜球分组 (goal-margin bands) from the SAME fit as ``implied_handicap_lines``
    (de-vig 1X2 + O/U → Dixon-Coles grid). Returns ``grid_to_margin_bands`` with
    each band's ``scores`` capped at ``top``.

    READOUT only — a 1500-fixture eval showed feeding the Asian Handicap INTO the
    fit adds ~0 info (the grid already reproduces the AH curve to ~1.5pp). ``tail=4``
    so every 竞彩 让球 line (−3..+3) classifies exactly into 让胜/让平/让负."""
    lh, la = fit_lambdas(
        p_home, p_draw, p_away, p_over, ou_line=ou_line, rho=rho, max_goals=max_goals,
    )
    bands = grid_to_margin_bands(score_grid(lh, la, rho=rho, max_goals=max_goals), tail=tail)
    for b in bands:
        b["scores"] = b["scores"][:top]
    return bands


# ── International Asian Handicap (HALF-line, 2-way: cover / not, NO push) ──────
# 竞彩 让球 (implied_handicap_lines above) is a 3-way INTEGER market (主胜/平/负
# after the line). The INTERNATIONAL / Pinnacle handicap is a 2-way HALF-line
# (主 -0.5 / -1.5 …): home covers OR away covers, no 让平. This is the line
# Polymarket-style "win by N+" markets map to. We price it two ways:
#   - REAL: de-vig the actual Pinnacle Asian-Handicap 2-way quote (most accurate)
#   - FALLBACK: read P(home covers) straight off the DC grid (when not quoted)

DEFAULT_AH_LINES = (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)


def devig_asian_handicap_line(home_odd, away_odd) -> tuple[float, float] | None:
    """De-vig ONE 2-way Asian-handicap line → (P(home covers), P(away covers)).

    The pair sums to 1 (a half-line has no push). Returns None for junk odds
    (≤ 1.0 or non-numeric) so callers fall back to the DC grid.
    """
    try:
        h, a = float(home_odd), float(away_odd)
    except (TypeError, ValueError):
        return None
    if h <= 1.0 or a <= 1.0:
        return None
    ih, ia = 1.0 / h, 1.0 / a
    s = ih + ia
    if s <= 0:
        return None
    return ih / s, ia / s


def dc_home_cover_prob(grid: np.ndarray, line: float) -> float:
    """P(home covers) at home-handicap ``line`` from a DC grid (half-line, no push).

    Home covers iff ``(home_goals − away_goals) + line > 0``. ``line`` is the
    home handicap: −0.5 ⇒ home must win; +0.5 ⇒ home win-or-draw; −1.5 ⇒ home
    wins by ≥ 2. For a half-line the margin can never tie the line, so there is
    no push and ``P(away covers) = 1 − P(home covers)``.

    体检 Wave3 (P2) — the half-line contract is now ENFORCED: on an integer
    line the margin CAN tie it (AH push, stake returned), and the ``1 − P``
    complement everywhere downstream would silently dump that push mass onto
    "away covers" — a mispriced cover-P with no error raised. Integer/quarter
    lines must price via the market de-vig (``devig_asian_handicap_line``) or
    the 3-way ``implied_handicap_lines``; raising keeps the wrong path loud.
    """
    if abs(line * 2 - round(line * 2)) > 1e-9 or int(round(line * 2)) % 2 == 0:
        raise ValueError(
            f"dc_home_cover_prob is half-line-only (no push); got line={line}")
    n = grid.shape[0]
    idx = np.arange(n)
    margin = idx[:, None] - idx[None, :]          # margin[i, j] = i − j
    return float(grid[(margin + line) > 0.0].sum())


def asian_handicap_board(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over: float | None = None,
    *,
    real_board: dict[float, dict[str, float]] | None = None,
    deep_lines=(-2.5, -1.5, 1.5, 2.5),
    ou_line: float = 2.5,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
) -> list[tuple[float, float, float, str]]:
    """International AH board: ``(line, P(home covers), P(away covers), source)``.

    Mirrors what Pinnacle actually shows. EVERY line Pinnacle quotes — level 0,
    quarter ±0.25/±0.75, half ±0.5, integer ±1, … — is de-vigged straight off
    its odds (``source="mkt"``), so the board lines up 1:1 with the Pinnacle page
    (which headlines 0 / ±0.25 for even matches, not just half-lines). The deep
    half-lines ``deep_lines`` (±1.5/±2.5, for Polymarket "win by N+") are filled
    off the DC grid (``"dc"``) when Pinnacle doesn't quote them. With NO real AH
    at all, the whole board falls back to the DC half-line ladder.

    ``real_board`` shape: ``{line: {"home": odd, "away": odd}}`` (line = home
    handicap; e.g. from ``odds_parser.extract_asian_handicap``). The DC grid is
    fitted to the de-vig 1X2 (+ O/U) — the SAME anchor as the 1X2 board.
    """
    out: dict[float, tuple[float, float, str]] = {}
    if real_board:
        for ln, q in real_board.items():
            dv = devig_asian_handicap_line(q.get("home"), q.get("away"))
            if dv is not None:
                out[float(ln)] = (dv[0], dv[1], "mkt")
    # DC fill: just the deep Polymarket lines when Pinnacle quoted SOMETHING;
    # the whole half-line ladder when it quoted nothing.
    fill = (
        [float(x) for x in deep_lines if float(x) not in out]
        if out else list(DEFAULT_AH_LINES)
    )
    if fill:
        lh, la = fit_lambdas(
            p_home, p_draw, p_away, p_over,
            ou_line=ou_line, rho=rho, max_goals=max_goals,
        )
        grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
        for line in fill:
            ph = dc_home_cover_prob(grid, line)
            out[line] = (ph, 1.0 - ph, "dc")
    return [(ln, float(out[ln][0]), float(out[ln][1]), out[ln][2]) for ln in sorted(out)]


__all__ = [
    "handicap_outcome",
    "HANDICAP_OUTCOME_LABELS",
    "DEFAULT_RHO",
    "DEFAULT_MAX_GOALS",
    "DEFAULT_LINES",
    "DEFAULT_AH_LINES",
    "devig_over",
    "asian_total_over_prob",
    "fit_lambdas",
    "implied_handicap_lines",
    "c1_leg_lower_bounds",
    "devig_asian_handicap_line",
    "dc_home_cover_prob",
    "asian_handicap_board",
]
