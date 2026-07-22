"""B2 — the +EV bar as a FUNCTION of the outcome's fair P (variance-adjusted),
not a flat +5% constant.

Motivation (measured, docs/ev_threshold_variance_2026-06-26.md): EV = P·SP − 1
⇒ σ_EV = SP·σ_P. The de-vig fair-P estimate has σ_P ≈ const (~1–1.5pp at 竞彩's
freeze gap), so a longshot's +EV carries ~1/P× (= SP×) the uncertainty of a
sweet-spot pick. To hold "true EV > 0" confidence CONSTANT across the
probability range, the bar must rise for low P (high SP):

    threshold(P) = base + z · σ_P · league_factor · SP      (SP defaults to 1/P)

Measured calibration (28k Pinnacle 1X2 open→close + odds_snapshots line history):
  - σ_P ≈ 1.2pp at 竞彩's 12–24h freeze gap (range 0.4pp near-close … 2.5pp open).
  - league_factor spread only 1.39× (soft/lower leagues noisier, ~2.3pp vs ~1.7pp).
  - ⇒ sweet (SP~2.5) bar ~8%, deep longshot (SP~12.5) bar ~20% at z=1.

A-3 影子模式(2026-07-23,docs/a3_shadow_mode_2026-07-23.md)把上面那个「σ_P ≈ 常数」
换成了 A-1 实测的**曲线** σ_P(h)=A·h^B —— 见 ``sigma_p_at``。
⚠️ **两次测量在 12-24h 处对不上**:本文件原注(06-26)说该缺口 σ_P≈1.2pp,而 A-1
(07-18,直接拟合 75 条线史轨迹)的曲线在 12-24h 给 1.7-2.1pp,1.2pp 其实落在 h≈4h。
按新压旧取 A-1,但**这个分歧没有被调查过** —— 别把两处数字当同一次测量引用。

STATUS: 仍是 DISPLAY-ONLY — NOT wired into the live +EV gate (that is a deliberate
betting-rule change). The dashboard shows this side-by-side with the flat 5% so
the cost of the flat bar on longshots is visible.
"""
from __future__ import annotations

# Measured defaults — see the doc above. Override per call as data sharpens.
BASE_THRESHOLD = 0.05      # the legacy flat +5% bar
SIGMA_P = 0.012            # σ of the de-vig fair-P estimate at 竞彩 freeze (~1.2pp)
Z_CONFIDENCE = 1.0         # one-sided multiplier (1.0≈84%, 1.65≈95%) for true-EV>0

# ── A-3 影子模式:σ_P 随「距开球还有多久」变化 ───────────────────────────────
# 上面那个 SIGMA_P=1.2pp 是**单点**常数(≈h 4h 的水平)。A-1 实测(2026-07-18,
# docs/freeze_gap_measurement_2026-07-18.md)给出的是曲线:σ_P(h) = A·h^B。
# 固定值的代价:凌晨场(缺口 6h+,占 41%)被低估、临近开球被高估。
#   同前端 dashboard.html 的 _FRZ_COEF —— 改一处必须改两处(见 test_ev_threshold)。
FREEZE_SIGMA_COEF: dict[str, tuple[float, float]] = {
    "H": (0.0079, 0.31),   # 主胜:漂得最凶
    "D": (0.0042, 0.23),   # 平局
    "A": (0.0077, 0.27),   # 客胜
}
# h→0 时 A·h^B→0,但**去vig 本身的估计误差不会消失**。给 h 设下界(而不是给 σ 设
# floor)—— 前者在曲线上自洽,后者会在接缝处造出一个不连续的台阶。
# 0.5h = A-1 拟合数据的实际下限,**与前端 _frzHalfEv 的 Math.max(h, 0.5) 同值**:
# 两处必须一致,否则同一场比赛的 ± 带与门槛会算出两个 σ。
MIN_HOURS = 0.5


def sigma_p_at(hours_to_kickoff: float | None, leg: str = "H") -> float:
    """σ_P 在距开球 ``hours_to_kickoff`` 小时处的值(A-1 曲线)。

    ``hours_to_kickoff`` 为 None / 非有限 → 回落到常数 ``SIGMA_P``(保持旧行为,
    调用方拿不到开球时刻时不该被静默变严)。已开球(h<0)按 MIN_HOURS 处理。"""
    if hours_to_kickoff is None:
        return SIGMA_P
    try:
        h = float(hours_to_kickoff)
    except (TypeError, ValueError):
        return SIGMA_P
    if h != h or h in (float("inf"), float("-inf")):   # NaN / inf
        return SIGMA_P
    a, b = FREEZE_SIGMA_COEF.get(leg.upper(), FREEZE_SIGMA_COEF["H"])
    return a * max(h, MIN_HOURS) ** b


def variance_adjusted_threshold(
    p: float,
    sp: float | None = None,
    *,
    base: float = BASE_THRESHOLD,
    sigma_p: float | None = None,
    z: float = Z_CONFIDENCE,
    league_factor: float = 1.0,
    hours_to_kickoff: float | None = None,
    leg: str = "H",
) -> float:
    """EV threshold for an outcome with fair probability ``p`` (and optional
    actual 竞彩 ``sp`` — defaults to the fair odds 1/p). Returns an EV fraction
    (e.g. 0.08 = +8%). Rises for longshots because σ_EV = σ_P·SP.

    σ_P 的来源,按优先级:
      1. 显式 ``sigma_p``(调用方自己算好了)
      2. ``hours_to_kickoff`` + ``leg`` → A-1 曲线 ``sigma_p_at``(A-3 影子模式)
      3. 都没有 → 常数 ``SIGMA_P``(旧行为)

    A non-probability ``p`` (≤0 or ≥1) falls back to the flat ``base`` — no SP to
    amplify. ``league_factor`` is the per-league σ_P multiplier (~0.85–1.2)."""
    if not (0.0 < p < 1.0):
        return base
    if sp is None:
        sp = 1.0 / p
    if sigma_p is None:
        sigma_p = sigma_p_at(hours_to_kickoff, leg)
    return base + z * sigma_p * league_factor * sp
