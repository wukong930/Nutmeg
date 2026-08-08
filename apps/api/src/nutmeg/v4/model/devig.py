"""Single source of truth for de-vigging bookmaker odds → fair probabilities.

Default = **WPO** (margin-weights-proportional-to-odds, Buchdahl): it corrects the
favourite-longshot bias (basic normalization over-states longshots) and, per
Buchdahl's 136,876-game Pinnacle closing-1X2 test, is tied-best by realized yield
with a **closed-form, zero-iteration** formula. Falls back to basic proportional
normalization if WPO ever produces an out-of-[0,1] value (extreme longshot × fat
margin — measured 0/5,234 times on real Pinnacle 1X2, so the guard is belt-and-
suspenders). See ``docs/devig_method_comparison.md``.

WPO:  p_i = (n − M·O_i) / (n·O_i),  where M = Σ(1/O_j) − 1 (the book margin), n = #outcomes.
basic: p_i = (1/O_i) / Σ(1/O_j).

SCOPE NOTE: this is for **fair-P-for-EV / analysis** (soft-water EV measurement,
dashboard EV, CLV). The MODEL-FEATURE de-vigs in ``features/market.py`` and
``features/market_dynamics.py`` deliberately STAY on basic normalization — changing
them shifts the trained model's input distribution and would require a full retrain
+ walk-forward re-validation. Don't route those through here without that.
"""
from __future__ import annotations

_VALID_METHODS = ("wpo", "basic")

# ── 水位闸(2026-07-23)─────────────────────────────────────────────────────
# 去vig 只会**照单全收**给它的那条线:输入是软盘,输出就是一个伪装成 sharp 先验的
# 公允概率,而 EV = P × SP − 1 会把这个错误原封不动放大成一个假 +EV。
#
# 病史:哈马比 vs 安德莱赫特(UEL Q2)面板显示客胜 EV **+9.4% 绿色过闸**。查下来
# 那条"Pinnacle 原盘"的三腿水位是 **14.5%** —— Pinnacle 的 1X2 从来不是这个数。
# Odds API 对欧战资格赛覆盖为 0,overlay 从未触发,一直吃的是 AF 那份会漂的镜像。
# 换成正常水位的线重算,客胜是 **−16%**,差 25.4 个百分点。
#
# 阈值 8% 是**实测**的(全库 14,452 条 psc 三腿):
#   纯 OA 行(sport_key 标签)      中位 3.3–4.5%
#   有 OA 覆盖的联赛              中位 4.8–6.0%,**观测最大 7.3%**
#   UCL / UEL / UECL(无 OA)      中位 7.9% / 8.5% / 10.6%,最大 17.2%
# 8% 高于所有 OA 覆盖联赛的观测最大值、低于三个欧战的中位数 —— 天然切口,
# 拦下全库 7.1%。
#
# ⚠️ 它判的是「**这条线配不配叫 sharp 锚**」,不是「这注好不好」。宽水位可能是
# 真 Pinnacle 在低流动性市场放宽(资格赛 5–7% 合理),也可能是软盘冒充 —— 单看
# 水位分不出来,所以这道闸只**降级 + 标红**,不静默丢弃数据。
WIDE_BOOK_VIG = 0.08


def book_vig(*odds: float) -> float | None:
    """三腿(或任意腿数)的 booksum − 1,即这本盘口的抽水。

    任一腿 ≤1 或缺失 → None(算不出,不装懂)。返回小数:0.145 = 14.5%。"""
    if not odds or any(o is None or not (o > 1.0) for o in odds):
        return None
    return sum(1.0 / o for o in odds) - 1.0


def is_wide_book(*odds: float, limit: float = WIDE_BOOK_VIG) -> bool:
    """True = 这条线宽到不配当 sharp 锚。算不出水位时返回 False(不冤枉)。"""
    v = book_vig(*odds)
    return v is not None and v > limit


#: 抽水下界 —— 低于它的「盘口」在物理上不存在。
#:
#: ⭐ 2026-08-08 加。为什么**不是**把它塞进 `WIDE_BOOK_VIG` 那个布尔:
#: `is_wide_book` 判的是「这条线配不配当 sharp 锚」,有 6 个调用点靠它**降级**;
#: 而这里判的是「这根本不是一本盘口」,唯一正确的反应是**拒绝并让人重打**。
#: 两件事塞进同一个布尔 = 那 6 个调用点会一起改变行为(本项目「一个布尔背两件事」的老坑)。
#:
#: 为什么下界是 0 而不是某个正数:任何一本真盘口都要抽水,booksum > 1 是**恒真**的,
#: 不是经验阈值 —— 所以这道闸**零误报**,不需要预注册,也不会随联赛/季节漂移。
#: 留 0.005 的余量是给「三腿都被四舍五入到两位小数」的极限情形,不是给软盘的。
IMPOSSIBLE_BOOK_VIG = 0.005


def is_impossible_book(*odds: float, floor: float = IMPOSSIBLE_BOOK_VIG) -> bool:
    """True = 这组赔率**不可能**来自一本真盘口(抽水 ≤ 0,庄家在送钱)。

    动机(实测,2026-08-08):手填 Pinnacle 时把小数点打丢一位 —— `1.9 / 33.5 / 3.3`
    本该是 `1.9 / 3.35 / 3.3` —— booksum = 0.8592 ⇒ 抽水 **−14.08%**。
    当时**没有任何一道闸会响**:`_sane_odds` 只看 (1,1000]、devig 只拒 ≤1.0、
    Pydantic 是裸 float、水位闸只测 `> 0.08`。而面板会用**绿色**告诉你「✓ 已应用」。
    ⇒ 主胜公允 P 0.4837 → **0.5733**(+8.96pp);竞彩 SP 2.00 时
    EV 从 −3.3% 变成 **+14.7%**,穿过 +5% 闸、可下注、可入台账。

    ⚠️ 反过来那一半更荒唐:**打对了反而报警**(12.79% > 8% ⇒ 标黄),
    打错了一路绿灯 —— 提示的方向是反的。这个函数补的就是缺掉的那一侧。

    算不出水位时返回 False(不冤枉),与 `is_wide_book` 同惯例。
    """
    v = book_vig(*odds)
    return v is not None and v <= floor


def _basic(odds: list[float]) -> list[float]:
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def _wpo(odds: list[float]) -> list[float]:
    n = len(odds)
    margin = sum(1.0 / o for o in odds) - 1.0
    return [(n - margin * o) / (n * o) for o in odds]


def devig(odds, *, method: str = "wpo") -> list[float] | None:
    """Fair (de-vig) probabilities from decimal odds. ``method`` ∈ {'wpo','basic'}.
    Returns None if any odd is missing/NaN/≤1.0. WPO falls back to basic if it would
    emit an out-of-[0,1] probability."""
    try:
        odds = [float(o) for o in odds]
    except (TypeError, ValueError):
        return None
    # reject NaN (o != o) and non-decimal odds (≤ 1.0)
    if any(o != o or o <= 1.0 for o in odds):
        return None
    if method == "basic":
        return _basic(odds)
    p = _wpo(odds)
    if any(x <= 0.0 or x >= 1.0 for x in p):  # extreme longshot × fat margin
        return _basic(odds)
    return p


def devig_1x2(h, d, a, *, method: str = "wpo") -> tuple[float, float, float] | None:
    """3-way convenience wrapper → (p_home, p_draw, p_away) or None."""
    if h is None or d is None or a is None:
        return None
    p = devig([h, d, a], method=method)
    return (p[0], p[1], p[2]) if p else None
