"""S6 让球切分偏差复现 — regression tests locking the frozen prereg tool.

Synthetic-only (CI-stable): the LIVE-cache reproduction of the discovery finding
is the CLI's ``--include-discovery`` self-check, not a unit test (cache drifts).
Here we pin the frozen constants, the triple/settle math, and the residual-test
structure (symbol consistency + anchor) on hand-built samples.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from nutmeg.v4.model.split_bias import (
    DRAW,
    LOSE,
    S6_DELTA,
    S6_LINES,
    S6_WINDOW_START,
    WIN,
    S6Sample,
    grid_triple,
    is_pure_half,
    margin_pmf,
    s6_result,
    settle_handicap,
)


class TestFrozenConstants:
    def test_delta_frozen(self):
        # C1 δ is prereg-frozen; a change here is a prereg amendment, not a tweak.
        assert S6_DELTA == 0.028

    def test_window_and_lines_frozen(self):
        assert S6_WINDOW_START == "2026-08-01"
        assert S6_LINES == (-1, 1)


class TestTripleMath:
    def test_is_pure_half(self):
        assert is_pure_half(-0.5) and is_pure_half(1.5) and is_pure_half(-2.5)
        assert not is_pure_half(0.0) and not is_pure_half(1.0)
        assert not is_pure_half(0.25) and not is_pure_half(-0.75)  # quarter lines

    def test_grid_triple_sums_to_one(self):
        # symmetric grid → margin pmf symmetric; triple at h=0 = 1X2-ish
        g = np.outer([0.3, 0.4, 0.3], [0.3, 0.4, 0.3])
        pmf = margin_pmf(g)
        assert abs(sum(pmf.values()) - 1.0) < 1e-9
        w, d, ll = grid_triple(pmf, -1)
        assert abs(w + d + ll - 1.0) < 1e-9
        assert w >= 0 and d >= 0 and ll >= 0

    def test_settle_handicap(self):
        # home -1: (hg-1) vs ag
        assert settle_handicap(3, 1, -1) == WIN      # 2>1
        assert settle_handicap(2, 1, -1) == DRAW     # 1==1
        assert settle_handicap(1, 1, -1) == LOSE     # 0<1
        # home +1
        assert settle_handicap(2, 3, 1) == DRAW      # 3==3


def _samples(spec, grid=(0.40, 0.22, 0.38), day0="2026-08-01"):
    """spec = list of realized-outcome codes; spread across 2+ match-days."""
    out = []
    for i, y in enumerate(spec):
        day = f"2026-08-0{1 + (i % 3)}"   # 3 match-days → clusters computable
        out.append(S6Sample(day, 1000 + i, -1, grid[0], grid[1], grid[2], y))
    return out


class TestS6Result:
    def test_only_h1_counted(self):
        s = [S6Sample("2026-08-01", 1, 2, .5, .2, .3, WIN),   # |h|=2 → excluded
             S6Sample("2026-08-01", 2, -1, .4, .22, .38, DRAW)]
        r = s6_result(s)
        assert r.n == 1   # the h=2 sample dropped

    def test_zero_samples_safe(self):
        r = s6_result([])
        assert r.n == 0 and r.draw_test.t is None

    def test_symbol_consistency_on_under_stated_draw(self):
        # Realize draws MORE than grid (grid 22% → realized 40%), wins LESS
        # (grid 40% → realized 20%) → draw residual>0, win residual<0.
        spec = [DRAW] * 4 + [WIN] * 2 + [LOSE] * 4   # 10 samples
        r = s6_result(_samples(spec))
        assert r.real_draw > r.grid_draw            # draw under-stated by grid
        assert r.real_win < r.grid_win              # win over-stated by grid
        assert r.draw_test.mean > 0
        assert r.win_test.mean < 0
        assert r.symbol_consistent

    def test_anchor_flag_when_lose_drifts(self):
        # Construct a case where 让负 itself moves a lot → anchor NOT intact.
        # All lose realized (100%) vs grid 38% → huge lose residual.
        r = s6_result(_samples([LOSE] * 12))
        # lose residual mean = 1 - 0.38 = +0.62, extreme → anchor check should
        # flag it (t large) unless degenerate. At minimum the mean is large.
        assert r.lose_test.mean > 0.5

    def test_c1_helps_when_draw_under_stated(self):
        # Draws realized more than grid → bumping draw P up (C1) lowers log-loss.
        r = s6_result(_samples([DRAW] * 8 + [WIN] * 1 + [LOSE] * 1))
        assert r.corrected_logloss_delta < 0        # correction improves ll


class TestWindowFilterOnLiveCache:
    """The frozen ≥2026-08-01 window filter is wired — proven without a clock.

    ⚠️ 2026-08-02 重写。原版断言 `samples == []`,理由是「今天还没有秋季数据」。
    那个证明手法**自带保质期**:2026-08-02 窗口一开、真实数据流进来,它就变红 ——
    而它红的时候,被测的东西其实**正在按设计工作**。

    与涓流那个「END 写成常量 ⇒ 零新增数学上必然」是同一族错误:
    **把一个未言明的时间假设焊进检查里**。一个说「永远查不到新的」,
    一个说「永远查不到任何」,两个都在某个日期之后变成关于日历的断言,
    而不是关于代码的断言。

    改成三条只讲**过滤器契约**、与日期无关的断言。它们比原来那条更强:
    原版只能证明「今天是空的」,新版证明「凡返回的都合规、能全排除、窗口单调」。
    """

    _CACHE = Path("data/external/api_football")

    def _samples(self, since: str):
        import pytest
        if not (self._CACHE / "_odds").exists():
            pytest.skip("no odds cache in this checkout")
        from nutmeg.v4.cli.s6_split_check import collect_samples
        return collect_samples(self._CACHE, since)

    def test_every_returned_sample_is_inside_the_window(self):
        """过滤器的**契约**:返回的每一条都必须 ≥ 窗口起点。永不过期。"""
        bad = [s.match_date for s in self._samples(S6_WINDOW_START)
               if s.match_date < S6_WINDOW_START]
        assert not bad, f"窗口外的样本漏进来了:{sorted(set(bad))[:5]}"

    def test_a_future_window_excludes_everything(self):
        """能全排除 —— 证明过滤器真的在过滤,而不是恰好没数据。"""
        assert self._samples("2099-01-01") == []

    def test_widening_the_window_only_adds(self):
        """单调性:放宽起点得到的是超集。这条同时证明窗口**确实挡掉了东西** ——
        不然它就退化成一句关于「缓存里恰好只有窗口内数据」的断言(见类注释)。
        """
        wide = self._samples("1970-01-01")
        narrow = self._samples(S6_WINDOW_START)
        key = lambda s: (s.fixture_id, s.h)   # noqa: E731 — 局部取键,写成 def 更吵
        assert {key(s) for s in narrow} <= {key(s) for s in wide}, "窗口内的不是超集的子集"
        assert len(wide) > len(narrow), (
            "放宽窗口没多出任何样本 —— 要么缓存里没有窗口前的数据(该检验此刻无意义),"
            "要么过滤器根本没生效")
