"""B2 — the +EV bar as a FUNCTION of the outcome's fair P (variance-adjusted),
not a flat +5% constant.

Motivation (measured, docs/ev_threshold_variance_2026-06-26.md): EV = P·SP − 1
⇒ σ_EV = SP·σ_P. The de-vig fair-P estimate has σ_P ≈ const (~1–1.5pp at 竞彩's
freeze gap), so a longshot's +EV carries ~1/P× (= SP×) the uncertainty of a
sweet-spot pick. To hold "true EV > 0" confidence CONSTANT across the
probability range, the bar must rise for low P (high SP):

    threshold(P) = base + z · σ_P · league_factor · SP      (SP defaults to 1/P)

Measured calibration (28k Pinnacle 1X2 open→close + odds_snapshots line history):
  - league_factor spread only 1.39× (soft/lower leagues noisier, ~2.3pp vs ~1.7pp).
  - ⇒ sweet (SP~2.5) bar ~8%, deep longshot (SP~12.5) bar ~20% at z=1.

A-3 影子模式(2026-07-23,docs/a3_shadow_mode_2026-07-23.md)把原来的「σ_P ≈ 常数」
换成了 A-1 实测的**曲线** σ_P(h)=A·h^B —— 见 ``sigma_p_at``。

⭐ σ_P 溯源(2026-07-28 **已调查并更正**,docs/sigma_p_reconciliation_2026-07-28.md)

本文件曾挂着一条警告:06-26 说竞彩封盘缺口 σ_P≈1.2pp,A-1 曲线在 12-24h 给
1.7-2.1pp,而该分歧当时未查。**现在查完了 —— 两次测量并不冲突**:

  ① **参照点不同,不是结论不同。** 06-26 的参考线在开赛前 ~9.5h(其文档自己标为
     「vs 真收盘的**下界**」),A-1 要求近收盘锚 ≤1.5h。同一个 σ_P(h) 符号,一个
     量 [9.5h→h] 的漂移、一个量 [1.5h→h] 的漂移。对账
     σ_06-26(h)² ≈ σ_A1(h)² − σ_A1(9.5h)² 在 12.5h / 19.5h 给比值 0.87× / 1.17×
     (夹住 1.0)⇒ 那个 1.42× 被参照点解释掉了。
  ② **「竞彩 12-24h 封盘」这个前提本身是错的。** A-1 §C 实测缺口分布:
     **中位 3.0h / p75 6.5h / p90 8.7h**,16-30h 桶只占 0.7%。06-26 读错了自己的行。
  ③ **三个错互相抵消**:下界曲线(低估 ~1.5×)× 读错行(高估 ~1.6×)× 文档说要加的
     0.8pp 参考线残差从没进代码。净结果 —— 下面的 SIGMA_P **数值站得住,但原来那套
     推导每一步都是错的**。溯源见 ``SIGMA_P`` 行注。

⚠️ 通用教训:原警告里写着「1.2pp 其实落在 h≈4h」——**它把答案写出来了却读成了问题**。
h≈4h 不是异常,那就是真实的封盘缺口。**发现两个数对不上,先问它们量的是不是同一个
东西,再问谁错了。**

STATUS: 仍是 DISPLAY-ONLY — NOT wired into the live +EV gate (that is a deliberate
betting-rule change). The dashboard shows this side-by-side with the flat 5% so
the cost of the flat bar on longshots is visible.
"""
from __future__ import annotations

# Measured defaults — see the doc above. Override per call as data sharpens.
BASE_THRESHOLD = 0.05      # the legacy flat +5% bar
# SIGMA_P —— 拿不到开球时刻时的回落常数。
# ⭐ **溯源已于 2026-07-28 更正**:它**不是**「06-26 测出的 12-24h 封盘 σ_P」——
# 那个缺口不存在(A-1 §C 实测中位 3.0h / p75 6.5h,16-30h 桶仅 0.7%)。
# ⚠️ **而且这个值已知偏低,只是还没到改的时候。** 同日 held-out 验证(187 条 07-19
# 起累积的轨迹,方法对齐 A-1)显示 A-1 曲线在 **h<4h 低估 1.5-2.5×** —— 而短端
# 正是竞彩的人口重心。在实测中位缺口 3.0h 处:
#     A-1 曲线 1.11pp · **本常数 1.20pp** · 我们全样本 1.41pp · held-out 1.73pp
# ⇒ **偏低约 1.2-1.4×,方向 fail-open(门槛显示得比该有的松)。**
# 根因是曲线形状:纯幂律无地板项,近端被硬拉向 0。正确形状 √(floor²+drift(h)²)。
# **修法 = 重拟合带地板的曲线,须走预注册**(docs/sigma_p_reconciliation_2026-07-28.md
# §5b/§8)。在那之前**不要**单独动这个数 —— 它和 sigma_p_at 必须同源。
SIGMA_P = 0.012
Z_CONFIDENCE = 1.0         # one-sided multiplier (1.0≈84%, 1.65≈95%) for true-EV>0

# ── A-3 影子模式:σ_P 随「距开球还有多久」变化 ───────────────────────────────
# 上面那个 SIGMA_P 是**单点**常数(≈ 曲线在 h≈4h 处的值)。A-1 实测(2026-07-18,
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
