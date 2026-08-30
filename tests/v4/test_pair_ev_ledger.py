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


# ─────────────────────────────────────────────────────────────────────────
# 次要结局 A(两腿 CLV 相关)—— 2026-08-30:原判据是 `abs(r) < 0.3` 的**硬阈值**,
# 不看功效。实测 r=+0.22 / N=31 被印成「≈0 → 分散化成立」,而 N=31 的最小可检出
# |r| 是 0.36 ⇒ **「测不出」被印成了「成立」**,而 prereg ② 的整套论证靠它当前提。
# ⇒ 三态:成立(等价检验)/ 推翻(区间不含 0)/ **功效不足**。
# ⚠️ 这些断言全是**行为断言** —— 造数据跑 render,不查源码里有没有某个字符串。
# ─────────────────────────────────────────────────────────────────────────

def _pairs_with_corr(n: int, rho: float, spread: float = 0.10):
    """造 n 对腿,两腿 clv 的相关约等于 rho。"""
    import math
    import random
    rnd = random.Random(4242)
    out = []
    for i in range(n):
        z = rnd.gauss(0, 1)
        a = spread * z
        b = spread * (rho * z + math.sqrt(max(1 - rho * rho, 0.0)) * rnd.gauss(0, 1))
        leg = lambda c, k: {                                    # noqa: E731
            "clv": c, "cap_ev": 0.05, "date": f"2026-06-{i % 28 + 1:02d}",
            "hc": None, "label": "主胜", "league": "西甲",
            "market": "had", "match": f"H{k}{i} vs A{k}{i}"}
        out.append((leg(a, "a"), leg(b, "b")))
    return out


def _verdict_line(pairs):
    from nutmeg.v4.cli.pair_ev_ledger import render
    import collections
    nbd = collections.Counter(p[0]["date"] for p in pairs)
    rep = {"legs": [], "pairs": pairs, "selected": pairs, "n_by_day": nbd}
    for line in render(rep).splitlines():
        if "相关系数" in line:
            return line
    raise AssertionError("render 没有输出相关系数行 —— 夹具没生效,断言会是空的")


def test_underpowered_r_is_reported_as_undecidable_not_as_zero() -> None:
    """🚨 主回归:小 r + 小 N 必须说「判不了」,**不许**说「≈0/成立」。"""
    line = _verdict_line(_pairs_with_corr(31, 0.22))
    assert "功效不足" in line, line
    assert "分散化成立" not in line, "把「测不出」印成了「成立」—— 旧 bug 复发"
    assert "最小可检出" in line, "没告诉读者这个 N 买得到什么"


def test_strong_positive_r_is_reported_as_refuting_the_premise() -> None:
    """真的正相关(区间不含 0)必须推翻 ② 的前提。"""
    line = _verdict_line(_pairs_with_corr(80, 0.75))
    assert "正相关" in line and "归零" in line, line
    assert "功效不足" not in line, line


def test_equivalence_passes_only_with_enough_n() -> None:
    """宣布「分散化成立」必须过**等价检验**:整个区间落在 ±0.3 内。

    同一个 rho≈0,N 小 ⇒ 判不了;N 大 ⇒ 才允许说成立。
    ⇒ 结论随 **N** 变而不随点估变 —— 这正是「不显著 ≠ 相等」的可执行形式。
    """
    small = _verdict_line(_pairs_with_corr(20, 0.0))
    big = _verdict_line(_pairs_with_corr(400, 0.0))
    assert "功效不足" in small, small
    assert "分散化成立" in big and "等价检验" in big, big
