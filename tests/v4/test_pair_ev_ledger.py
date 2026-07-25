"""配对 EV Phase 1 —— 口径守卫(2026-07-25)。

这些测试守的不是「代码能跑」,是**预注册不被悄悄改**
(docs/pair_ev_prereg_2026-07-25.md)。常量一动、宇宙定义一松,整个测量就作废。
"""
from __future__ import annotations

import pytest

from nutmeg.v4.cli import pair_ev_ledger as M


class TestPreregConstantsAreLocked:
    def test_floor_and_gate(self):
        """FLOOR=+2%(单腿闸的一半)· GATE=+5%(与单腿闸同一个数)。
        prereg §2/§3 明写:看过任何结局之后都不许调。改这两个数 = 新假设。"""
        assert M.LEG_FLOOR == 0.02
        assert M.PAIR_GATE == 0.05

    def test_floor_admits_the_phenomenon_being_tested(self):
        """FLOOR 必须**低于**闸,否则「两条都不够、合起来够」这个要测的现象
        会被宇宙定义自己筛掉 —— 那就是循环论证。"""
        assert M.LEG_FLOOR < M.PAIR_GATE
        # 2%+2% 不过闸;3%+3% 过闸 —— 现象落在窗口内
        assert M._ev({"cap_ev": .02}, {"cap_ev": .02}, "cap_ev") < M.PAIR_GATE
        assert M._ev({"cap_ev": .03}, {"cap_ev": .03}, "cap_ev") >= M.PAIR_GATE


class TestPairEvMath:
    def test_multiplicative_not_additive(self):
        """EV_串 = (1+EV₁)(1+EV₂)−1,不是 EV₁+EV₂。"""
        got = M._ev({"x": 0.03}, {"x": 0.03}, "x")
        assert got == pytest.approx(0.0609, abs=1e-6)
        assert got > 0.06, "交叉项 EV₁·EV₂ 不能漏"

    def test_a_losing_leg_drags_the_pair_down(self):
        """+6% 配 −5% ≈ +0.7% —— 单腿过闸但实际这注接近零。
        这正是逐腿闸看不见的另一面(不只是漏机会,也在放过假信号)。"""
        assert M._ev({"x": 0.06}, {"x": -0.05}, "x") == pytest.approx(0.007, abs=1e-6)


class TestUniverseRules:
    def _leg(self, day, match, ev):
        return {"date": day, "match": match, "cap_ev": ev, "clv": 0.0,
                "market": "had", "hc": None, "label": "x", "league": "L"}

    def test_same_match_pair_is_excluded(self):
        """同场两腿互斥/强相关,竞彩本就不许 —— 宇宙里绝不能出现。"""
        m = ("2026-08-01", "A", "B")
        legs = [self._leg("2026-08-01", m, .05), self._leg("2026-08-01", m, .05)]
        assert M._pairs(legs) == []

    def test_cross_day_pair_is_excluded(self):
        legs = [self._leg("2026-08-01", ("d1", "A", "B"), .05),
                self._leg("2026-08-02", ("d2", "C", "D"), .05)]
        assert M._pairs(legs) == []

    def test_below_floor_leg_is_excluded(self):
        legs = [self._leg("2026-08-01", ("d", "A", "B"), .05),
                self._leg("2026-08-01", ("d", "C", "D"), .019)]   # 差一点
        assert M._pairs(legs) == []

    def test_valid_cross_match_same_day_pair_survives(self):
        legs = [self._leg("2026-08-01", ("d", "A", "B"), .03),
                self._leg("2026-08-01", ("d", "C", "D"), .03)]
        assert len(M._pairs(legs)) == 1


class TestHonestReporting:
    def _sel(self, n):
        return {"legs": [], "pairs": [], "selected": [], "n_by_day": {}}

    def test_small_sample_correlation_is_withheld(self):
        """⚠️ 我第一版在 N=3 上打印了 r=−0.67 —— 3 个点的相关系数几乎必然是
        ±0.7 量级的噪声,显示出来会被当成发现。低于 _CORR_MIN_N 必须留白。"""
        assert M._CORR_MIN_N >= 10

    def test_no_pairs_is_a_result_not_an_error(self):
        out = M.render({"legs": [], "pairs": [], "selected": [], "n_by_day": {}})
        assert "无合法对" in out

    def test_report_states_the_stopping_rule(self):
        """报告必须自带「N 不够别下结论」——防止有人看一眼 N=3 就上闸。"""
        out = M.render({"legs": [], "pairs": [], "selected": [], "n_by_day": {}})
        assert "N≥30" in out or "只读" in out


class TestReadOnly:
    def test_module_never_writes(self):
        """Phase 1 铁律:只读。不许出现任何写入观测库的调用。"""
        from pathlib import Path
        src = Path(M.__file__).read_text()
        for banned in ("INSERT", "UPDATE ", "DELETE", "record_session",
                       "record_jingcai_sp", "record_row_snapshot"):
            assert banned not in src, f"Phase 1 只读,不该出现 {banned}"
        assert "mode=ro" in src, "必须以只读模式打开数据库"
