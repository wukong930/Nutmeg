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
_C1_DELTA = 0.046       # −1 线:让胜 → 让平
_C1_DELTA_P1 = 0.016    # +1 线:让负 → 让平(镜像)

# δ 的估计标准误 —— A′ 的核心:δ 不是精确值,它的误差 1:1 传进被修正的腿,
# 再乘 竞彩SP(让平常 ~4.2)放大成 EV 误差。判闸必须吃这个不确定性,否则
# 「δ 恰好准」就成了下注的隐含前提(实测:按 δ−2SE 判闸,那 30 张让平票全部消失
# ⇒ 它们的 +EV 完全依赖 δ 点估无误)。呼应 `记忆 ev-threshold-variance-sigmap`:
# 门槛是不确定性的函数,不是平的 5%。
# ⚠️ 这是**朴素二项 SE**,未做比赛日聚类 → 真实不确定性只会更大,故本带宽是**下限**。
_C1_DELTA_SE = 0.010       # SE(δ₋₁),N=1,882
_C1_DELTA_P1_SE = 0.0135   # SE(δ₊₁),N=1,044
_C1_SE_K = 2.0             # 判闸用的保守倍数(≈95% 单侧)

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


def c1_leg_lower_bounds(
    line: int, p_home: float, p_draw: float, p_away: float, *, k: float = _C1_SE_K,
) -> tuple[float, float, float]:
    """给 **已应用 C1(点估)** 的三元组,返回每条腿在 δ 估计误差下的**自身下界**。

    保守方向是**逐腿**的 —— 每条腿取「让它自己的 P 更小」的那侧:
      −1 线:让胜 = 点估 − k·SE(δ 若更大 → 让胜更低);让平 = 点估 − k·SE(δ 若更小 → 让平更低)
      +1 线:让负 / 让平 同理;未被 C1 碰的第三腿无 δ 误差 → 下界 = 点估。
    (代数上两侧都落到「点估 − k·SE」,因为点估 = raw∓δ。)

    ⚠️ **返回值不是概率分布**(和 < 1)—— 它是三个独立的单腿下界,**只用于判闸**,
    绝不可用于展示/归一化/喂模型。展示请用点估(``implied_handicap_lines(c1=True)``)。
    """
    ln = int(line)
    if ln == -1:             # C1 碰了 让胜 + 让平;让负是锚,无 δ 误差
        d = k * _C1_DELTA_SE
        return max(p_home - d, 0.0), max(p_draw - d, 0.0), float(p_away)
    if ln == 1:              # 镜像:让平 + 让负
        d = k * _C1_DELTA_P1_SE
        return float(p_home), max(p_draw - d, 0.0), max(p_away - d, 0.0)
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
    out: list[tuple[int, float, float, float]] = []
    for line in lines:
        ph, pd_, pa = grid_to_handicap_1x2(grid, handicap_home=int(line))
        if c1 and int(line) == -1:            # 热门在主:让胜(DC 高估)→ 让平
            shift = min(_C1_DELTA, ph)         # 守恒 + 不越界(ph 罕见 <δ 时不为负)
            ph, pd_ = ph - shift, pd_ + shift
        elif c1 and int(line) == 1:           # 热门在客:让负(DC 高估)→ 让平(镜像)
            shift = min(_C1_DELTA_P1, pa)
            pa, pd_ = pa - shift, pd_ + shift
        elif c1 and int(line) == -2:          # δ₋₂(prereg v1.8):让胜 → 让平 + 让负
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
