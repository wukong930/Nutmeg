"""抽水分配常设仪表 —— 锁住会计恒等式、腿位定义、检验方向。

这个仪表的全部价值是「说明结构」,所以最容易坏的方式不是崩,而是**悄悄测错东西**:
腿位排错、方向设反、把再分配读成折扣。下面四条就是钉这些。
"""
from __future__ import annotations

import pytest

from nutmeg.v4.cli.vig_split import _BETTABLE, _RANKS, by_league, by_rank, render


def _m(sp, fair, *, date="2026-07-01", league="芬超", club=True):
    """按给定的公允 P 和竞彩 SP 造一场(绕开 DB,直接构 load() 的输出形状)。"""
    order = sorted(range(3), key=lambda i: -fair[i])
    rank = {order[0]: "热门", order[1]: "居中", order[2]: "冷门"}
    return {"date": date, "league": league, "club": club,
            "booksum": sum(1 / x for x in sp),
            "legs": [{"rank": rank[i], "vig": 1 / sp[i] - fair[i], "fair": fair[i],
                      "sp": sp[i], "ev": fair[i] * sp[i] - 1} for i in range(3)]}


#: 天狼星 vs 哥德堡(2026-07-25)的真实形状:竞彩把 12.8% 里的 12.4pp 全压在主胜上,
#: 平/客几乎无水。下面多条测试都用它,免得再自己编出「热门水最轻」的反向样本。
_REAL_SP = (1.31, 4.22, 7.80)
_REAL_FAIR = (0.639, 0.234, 0.127)


def test_leg_vigs_sum_to_booksum_minus_one():
    """⭐ 会计恒等式:Σ 逐腿抽水 = booksum − 1(因为 Σ 公允 P = 1)。

    这条是整个仪表的地基 —— 「把 12.9% 分到哪条腿上」只有在总和守恒时才是句人话。
    谁改了 vig 的定义(比如误写成 `fair − 1/sp`),这里立刻红。
    """
    m = _m(_REAL_SP, _REAL_FAIR)
    assert sum(lg["vig"] for lg in m["legs"]) == pytest.approx(m["booksum"] - 1)


def test_rank_is_assigned_by_fair_p_not_by_sp():
    """腿位按 **Pinnacle 公允 P** 排,不按竞彩 SP 排。

    通常两者同序,但竞彩把水重压热门时排序可能翻转 —— 那时按 SP 排会把「被压水
    最狠的腿」错标成别的腿位,恰好抹掉本仪表要测的现象。
    """
    # 客队公允更高(=热门),但竞彩给主队的 SP 更低(1/SP 更高)
    m = _m((1.90, 3.60, 1.95), (0.44, 0.22, 0.34))
    by = {lg["rank"]: lg["fair"] for lg in m["legs"]}
    assert by["热门"] == pytest.approx(0.44)
    assert by["冷门"] == pytest.approx(0.22)


def test_favourite_is_excluded_from_the_bettable_slice():
    """⚠️ 热门**不算**可投腿 —— 它扛 60% 抽水、过闸率 0.4%,我们不会买它。

    第一版我按热门腿筛联赛,等于在测一个与下注决策无关的量。这条钉住修正。
    """
    assert "热门" not in _BETTABLE
    assert set(_BETTABLE) == set(_RANKS) - {"热门"}


def test_by_league_direction_is_cheaper_not_pricier():
    """检验方向必须是「更便宜」:抽水低 ⇒ t 为正、p 小。

    第一版设反了(筛「更贵」),而更贵对我们毫无用处 —— +EV 的空间来自抽水**低**。
    造一个可投腿明显更便宜的联赛,它必须排第一且 t>0。

    ⚠️ 造样本踩过两次 `t=None`:① 所有场次完全相同 ⇒ 簇内零方差;② 抖动让两条可投腿
    **反向**移动 ⇒ 同一天的残差精确抵消,撞上 `clv_gate` 的 `meat <= 1e-9·tss` 护栏
    (那护栏是对的,是我的样本病)。所以抖动加在两条可投腿**同向**、由热门腿配平。
    """
    def wk(lg, sp_draw, sp_away):
        return [_m((1.60, sp_draw, sp_away),
                   (0.62 - 2 * d * 0.001, 0.235 + d * 0.001, 0.145 + d * 0.001),
                   date=f"2026-07-{d:02d}", league=lg) for d in range(1, 13)]
    cheap, dear = wk("便宜联", 4.30, 6.90), wk("昂贵联", 3.60, 5.60)
    rows = {r["league"]: r for r in by_league(cheap + dear, min_n=10)}
    assert rows["便宜联"]["dev"] < 0 < rows["昂贵联"]["dev"]
    assert rows["便宜联"]["t"] > 0, "更便宜的联赛 t 必须为正 —— 方向又反了"
    assert rows["昂贵联"]["t"] < 0


def test_by_rank_shares_are_reported_against_total():
    m = [_m(_REAL_SP, _REAL_FAIR, date=f"2026-07-{d:02d}") for d in range(1, 9)]
    rk = {r["rank"]: r for r in by_rank(m)}
    assert set(rk) == set(_RANKS)
    assert rk["热门"]["n"] == len(m)
    assert rk["热门"]["vig"] > rk["居中"]["vig"], "构造的样本就是热门水最重"


def test_render_survives_empty_and_never_emits_a_recommendation():
    """只读仪表 —— 任何情况下都不许吐出下注措辞。"""
    assert "无可用" in render([])
    txt = render([_m(_REAL_SP, _REAL_FAIR, date=f"2026-07-{d:02d}")
                  for d in range(1, 31)])
    for banned in ("建议下注", "推荐买", "可以下"):
        assert banned not in txt
    assert "永不 gate" in txt
