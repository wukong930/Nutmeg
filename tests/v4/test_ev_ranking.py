"""EV 排序力仪表 —— 锁住零假设的选法(这是整个统计量的成败所在)。

最容易犯、也最难发现的错:把场内对比的基准写成三腿 EV 的**算术**均值。
竞彩的 vig 不均匀(散户买热门 ⇒ 热门被压价 ⇒ 热门 EV 天然低),而热门又赢得多,
所以算术均值当基准会**机械地**产出负值 —— 和「EV 反向」长得一模一样,而且
数字看起来完全正常,不会有任何报错。

下面 test_null_is_anchor_weighted_not_arithmetic 就是钉死这一点的:构造一个
锚完全校准、EV 纯粹由 vig 分布造成的世界,正确实现必须给出 0。
"""
from __future__ import annotations

import math

from nutmeg.v4.cli.ev_ranking import _band, bands_table, within_match


def _match(p, sp, won, day="2026-07-01", market="had"):
    return {"day": day, "league": None, "market": market, "p": list(p),
            "sp": [float(x) for x in sp],
            "ev": [p[i] * sp[i] - 1.0 for i in range(3)], "won": won}


def test_null_is_anchor_weighted_not_arithmetic():
    """锚校准良好时,场内对比的期望必须是 0 —— 即使各腿 EV 差别很大。

    构造:真实概率 = 锚概率 = (0.60, 0.25, 0.15)。竞彩把热门压价(vig 重),
    冷门给得慷慨 ⇒ 热门 EV 低、冷门 EV 高。用**算术均值**当基准会得到负数
    (因为热门 EV 低而热门赢得最多);用 Σ Pᵢ·EVᵢ 才是 0。
    """
    p = (0.60, 0.25, 0.15)
    sp = (1.45, 3.60, 6.90)          # 热门被压价,冷门慷慨
    evs = [p[i] * sp[i] - 1.0 for i in range(3)]
    assert evs[0] < evs[2], "构造前提:热门 EV 应低于冷门,否则这个测试没意义"

    # 三腿按真实概率各出现一批,比例 = p(锚校准 ⇒ 真实频率 = 锚概率)
    ms = ([_match(p, sp, 0, day=f"d{i}") for i in range(60)]
          + [_match(p, sp, 1, day=f"d{i}") for i in range(60, 85)]
          + [_match(p, sp, 2, day=f"d{i}") for i in range(85, 100)])
    test, _ = within_match(ms)
    assert abs(test.mean) < 1e-9, f"锚校准时对比应为 0,实得 {test.mean}"

    # 反证:换成算术均值当基准,同一批数据会得到**负数** —— 那就是那个陷阱
    arith = math.fsum(evs) / 3
    naive = math.fsum(m["ev"][m["won"]] - arith for m in ms) / len(ms)
    assert naive < -0.01, "构造应能重现算术均值基准的机械负偏,否则测试失效"


def test_contrast_positive_when_cheap_side_overperforms():
    """竞彩定价便宜(EV 高)那一侧赢得比锚说的更多 ⇒ 对比为正。"""
    p = (0.50, 0.25, 0.25)
    sp = (1.90, 3.40, 4.60)          # 客胜 EV 最高
    ms = [_match(p, sp, 2, day=f"d{i}") for i in range(40)]   # 客胜一直赢
    test, _ = within_match(ms)
    assert test.mean > 0


def test_bands_use_realized_return_not_ev():
    """分档 ROI 必须是**实际**回报(中了 SP−1,没中 −1),不是 EV 的平均。"""
    p = (0.34, 0.33, 0.33)
    sp = (3.00, 3.00, 3.00)
    ms = [_match(p, sp, 0, day=f"d{i}") for i in range(30)]   # 主胜每场都中
    rows = {r[0]: r for r in bands_table(ms)}
    _, n, roi, _ = rows["全部腿(基准)"]
    assert n == 90
    # 90 腿里 30 中:(30×2.0 + 60×(−1)) / 90 = 0.0
    assert abs(roi - 0.0) < 1e-12


def test_band_edges_are_half_open():
    """边界归属明确:0.05 属于 5–15% 档,不属于 0–5%(避免重复计数)。"""
    assert _band(-0.01) == "EV <0%"
    assert _band(0.0) == "EV 0–5%"
    assert _band(0.049) == "EV 0–5%"
    assert _band(0.05) == "EV 5–15%"
    assert _band(0.15) == "EV ≥15%"


def test_clusters_are_days_not_matches():
    """同一天的多场必须聚成一簇 —— 否则 t 被高估(同日腿相关)。

    命中腿要**轮换**,否则 20 场完全相同 ⇒ 对比值方差为零 ⇒ t 按设计返回 None
    (MeanTest 的 zero-spread 分支),那就测不到聚类本身了。
    """
    p, sp = (0.40, 0.30, 0.30), (2.50, 3.30, 3.40)
    same_day = [_match(p, sp, i % 3, day="2026-07-01") for i in range(20)]
    spread = [_match(p, sp, i % 3, day=f"2026-07-{i + 1:02d}") for i in range(20)]
    t_same, _ = within_match(same_day)
    t_spread, _ = within_match(spread)
    assert t_same.n_clusters == 1 and t_spread.n_clusters == 20
    # 全在一天 → 只有 1 簇 → t 无法定义(而不是给出一个虚高的值)
    assert t_same.t is None
    assert t_spread.t is not None


def test_incomplete_leg_is_dropped():
    """缺腿的场次必须整场丢弃 —— Σ Pᵢ·EVᵢ 的零假设要求三腿齐全。"""
    from nutmeg.v4.cli.ev_ranking import _assemble
    assert _assemble((0.4, 0.3, 0.3), (2.5, None, 3.4), 0, "2026-07-01", None, "had") is None
    assert _assemble((0.4, 0.3, 0.3), (2.5, 1.0, 3.4), 0, "2026-07-01", None, "had") is None
    assert _assemble((0.4, 0.3, 0.3), (2.5, 3.3, 3.4), 0, "2026-07-01", None, "had")
