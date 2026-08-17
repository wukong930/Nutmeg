"""δ 校准常设仪表 —— 锁住功效算式和「常数不许漂」。

背景:δ₋₁/δ₊₁ 上线 11 天里没有任何东西看着它们,直到 owner 随口一问才发现
δ₊₁ 在自己的拟合人口上 log-loss 变差。这个仪表存在的意义就是别再靠人问。
"""
from __future__ import annotations

import math

import pytest

from nutmeg.v4.cli.delta_calibration import power_table, render, required_n
from nutmeg.v4.model import market_handicap as MH


def test_required_n_scales_as_inverse_delta_squared():
    """⭐ N ∝ 1/δ² —— δ 减半,所需样本变 4 倍。

    这是「小 δ 不可确立」的**全部**原因,也是本仪表最有用的一条结论:
    对 δ₊₁=0.016 而言「再等等攒 N」是无效策略,不是耐心问题。
    """
    p = 0.35
    assert required_n(0.02, p) == pytest.approx(4 * required_n(0.04, p), rel=1e-9)


def test_required_n_matches_the_delta_equals_2se_boundary():
    """定义自洽:在 N=required_n 处,恰好 δ == 2·SE(即判闸下界恰为 0)。"""
    d, p = 0.046, 0.25
    n = required_n(d, p)
    se = math.sqrt(p * (1 - p) / n)
    assert 2 * se == pytest.approx(d, rel=1e-9)


def test_required_n_is_infinite_for_zero_delta():
    assert required_n(0.0, 0.3) == float("inf")
    assert required_n(-0.01, 0.3) == float("inf")


def test_power_table_reads_live_constants_not_a_snapshot(monkeypatch):
    """⭐ 常数必须**现读** `market_handicap`,不能在加载时快照。

    初版把 δ 在模块加载时求值存进元组 —— 那样将来有人改了那边的 δ,本仪表会
    悄悄停在旧值,而它的全部职责就是监督那些 δ。这条测试钉死这个失效模式。
    """
    before = {r["leg"]: r["delta"] for r in power_table()}
    monkeypatch.setattr(MH, "_C1_DELTA", 0.099)
    after = {r["leg"]: r["delta"] for r in power_table()}
    assert before["−1 让胜"] != 0.099, "测试前提:原值不应恰好是这个哨兵值"
    assert after["−1 让胜"] == 0.099, "改了 market_handicap 的 δ,表却没跟上 = 已漂"


def test_established_flag_is_exactly_delta_gt_2se():
    """「在做功」的判定 = 判闸下界为正,不是别的什么直觉。"""
    for r in power_table():
        assert r["established"] == (r["delta"] - 2 * r["se"] > 0)
        assert r["lower"] == pytest.approx(r["delta"] - 2 * r["se"])


def test_delta_p1_established_independently_after_v2_0():
    """现状留痕(v1.9 后)。**这条测试上一版红过一次,而那是它该做的事。**

    v1.8 时它叫 `test_delta_p1_is_currently_flagged_as_not_established`,断言
    δ₊₁ 未确立(t=1.19、下界为负),docstring 写着「若 owner 走 prereg 改了它,
    这条会红,那正是提示现状记录要更新」。2026-07-28 owner 授权部分合并后它如期
    变红 —— 绊线按设计工作,故随现状更新而非删除。

    ⭐⭐ **v2.0(2026-07-29)后它是真正独立确立的了** —— 不再借可交换性:
    join 补上别名层后样本 3,038→4,934,δ₊₁ 自己就是 t=3.16、下界 +0.0118。
    v1.9 那句「借用了可交换性假设」的警告**到此作废**。
    ⚠️ 若这条又变红,**先查 join 命中率再查常数** —— 上一次「测不出」的根因是
    脚本裸用 normalize_name 丢了 59% 样本,不是样本真的不够。
    """
    row = next(r for r in power_table() if r["leg"] == "+1 让负")
    assert row["established"], "v1.9 收缩后 δ₊₁ 的判闸下界应转正;若又变负,查 prereg v1.9"
    assert row["t"] > 2.0
    # −1 一直是确立的,收缩后仍必须是 —— 收缩不该把好的那条弄坏
    m1 = next(r for r in power_table() if r["leg"] == "−1 让胜")
    assert m1["established"] and m1["t"] > 2.0


def test_small_slices_are_skipped_not_interpreted():
    """N 小于门槛的切片只报「样本太小」,绝不给出「谁更近」的解读。"""
    tiny = {(-2, "俱乐部"): [((0.4, 0.3, 0.3), (0.35, 0.35, 0.3), 0)] * 3}
    txt = render(tiny, min_n=10)
    assert "样本太小" in txt
    assert "谁更近" not in txt


def test_render_survives_empty_input():
    assert "无已结算" in render({})


# ────────────────────────────────────────────────────────────────────
# δ 范围闸(2026-08-16)之后:「没测」必须和「无害」分开
# ────────────────────────────────────────────────────────────────────

class TestZeroAppliedIsNotHarmless:
    """🚨 范围闸让**大多数**竞彩行的 `cor ≡ raw`(人口以杯赛/日职/北欧为主,
    而 δ 只在 10 个欧洲联赛上校准过)。实测三个「大赛」切片 δ **一行都没生效**。

    那种切片的 log-loss 差**恒为 0** ⇒ 报表原来印「✅ 改善 +0.0000」——
    和「δ 生效了且无害」**逐字一样**。
    后果:prereg v2.0 §5.1 的「±1 线连续两周变差 ⇒ 回滚」在这些切片上
    **数学上永不可能成立** ⇒ 回滚观察窗被静音,而仪表看起来一切正常。

    ⭐ 同族:「检查的前提没人检查」——「δ 在这个切片上生效过吗」从来没人问。
    """

    @staticmethod
    def _rows(n_delta: int, n_total: int, *, worse: bool = False):
        """造 n_total 行,其中 n_delta 行 raw≠cor。

        ⚠️ `worse=True` 才能触发 §5.1 的回滚判定。**这不是可以随便写的数** ——
        实际命中是 `i % 3`(近似均匀),所以「修正后更差」= cor 比 raw **更远离**
        均匀。我第一版的 cor=(0.35,0.32,0.33) 其实比 raw **更接近**均匀 ⇒
        log-loss 反而改善 ⇒ 回滚分支永远不进,而失败信息只说「夹具没触发」。
        ⭐ 夹具造不出被测条件时,测试是**假红**不是真红 —— 得先看懂夹具在造什么。
        """
        raw = (0.40, 0.30, 0.30)
        bad = (0.70, 0.15, 0.15) if worse else (0.35, 0.32, 0.33)
        return [(raw, bad if i < n_delta else raw, i % 3) for i in range(n_total)]

    def test_n_delta_counts_rows_where_delta_moved_the_number(self):
        from nutmeg.v4.cli.delta_calibration import _n_delta
        assert _n_delta(self._rows(0, 10)) == 0
        assert _n_delta(self._rows(4, 12)) == 4
        assert _n_delta(self._rows(12, 12)) == 12

    def test_n_delta_is_a_behavioural_test_not_a_whitelist_lookup(self):
        """判据必须是「数字动了没有」,不是「联赛在不在白名单里」。

        白名单查表会漏掉「在覆盖内、但该线根本没被 C1 碰」的情形(|line| ≥ 3),
        那种行同样对判定没有贡献。**语法代理测语义属性**在本仓是明令的反模式。
        """
        import inspect

        from nutmeg.v4.cli.delta_calibration import _n_delta
        src = inspect.getsource(_n_delta)
        assert "_DELTA_CALIBRATED_LEAGUES" not in src and "delta_scope" not in src, \
            "`_n_delta` 在查白名单 —— 它该问「数字动了没有」"

    def test_report_says_not_measured_not_improved_when_nothing_applied(self):
        from nutmeg.v4.cli import delta_calibration as DC
        md = DC.render({(-1, "大赛"): self._rows(0, 40)}, min_n=10)
        assert "🚫" in md and "未生效" in md, f"零生效切片没被标出来:\n{md}"
        assert "不是「无害」,是「没测」" in md
        assert "✅ 改善" not in md, "🚨 零生效切片仍印「改善」—— 和「δ 有效且无害」同形"
        assert "不可判定" in md, "没说明它不参与 §5.1 判定"

    def test_report_still_judges_when_delta_did_apply(self):
        """反向 —— 别把闸焊死:真生效过的切片必须照常给判定。"""
        from nutmeg.v4.cli import delta_calibration as DC
        md = DC.render({(-1, "俱乐部"): self._rows(40, 40)}, min_n=10)
        assert "🚫" not in md, "δ 全生效的切片被误标成未生效"
        assert ("✅ 改善" in md or "变差" in md), "生效切片没有给出判定"

    def test_report_flags_a_thin_applied_sample_behind_a_fat_N(self):
        """⚠️ `min_n` 卡的是 N,判定站的是 n_delta。

        2026-08-17 实测:`+1 俱乐部` N=106 过闸,δ 生效只有 **14** 场 ——
        而那正是 §5.1 回滚条件命中的切片。报表必须把这个差距印出来。
        ⛔ 本条**不**主张改 `min_n`(预注册参数,改它要 owner 口令)。
        """
        from nutmeg.v4.cli import delta_calibration as DC
        md = DC.render({(-1, "俱乐部"): self._rows(3, 40)}, min_n=10)
        assert "δ 生效只有 3 场" in md, f"薄样本没被点名:\n{md}"
        assert "不是 40 场" in md

    def test_header_always_reports_how_many_rows_delta_actually_moved(self):
        """⭐ 这条是**空包弹逼出来的**:我先写的三条只测了 🚫 分支和薄样本警告,
        把标题里的「δ 实际生效 N 场」整个删掉 ⇒ **全绿**。

        而那个数正是每周人眼要读的东西 —— 「N=106」和「其中 δ 只动了 14 场」
        是两个完全不同的读数,后者才是判定实际站的地方。
        """
        from nutmeg.v4.cli import delta_calibration as DC
        md = DC.render({(-1, "俱乐部"): self._rows(7, 40)}, min_n=10)
        assert "δ **实际生效 7 场**" in md, f"标题没报生效行数:\n{md[:400]}"
        assert "N=40 场" in md, "总行数也得留着 —— 两个数缺一不可"

    def test_rollback_line_states_how_many_rows_it_rests_on(self):
        """🚨 §5.1「回滚条件成立」这句话必须自带 δ 生效场数。

        实测(2026-08-17):`+1 俱乐部` N=106 场触发了回滚条件,δ **实际生效 14 场**。
        14 > min_n=10 ⇒ 薄样本警告**不会**触发 ⇒ 这句话印出来时,读者拿不到
        唯一要紧的那个数。owner 要据此决定回不回滚。

        ⛔ 本条**不**主张改 `min_n` —— 改判据来迁就一个不喜欢的读数是
           「事后加判据」,本仓明令禁止。只主张把数摆出来。
        """
        from nutmeg.v4.cli import delta_calibration as DC
        rows = self._rows(14, 106, worse=True)
        prev = {DC.slice_key(1, "俱乐部"): {"n": 100, "n_delta": 12,
                                            "raw_ll": 1.0, "c1_ll": 1.2},
                "_gap_days": 14, "_date": "2026-08-03"}
        md = DC.render({(1, "俱乐部"): rows}, min_n=10, prev=prev)
        assert "回滚条件成立" in md, f"夹具没触发回滚判定:\n{md}"
        assert "本次 δ 生效 **14** 场" in md, f"回滚那句没带本次生效场数:\n{md}"
        assert "上次 **12** 场" in md, "没带上次的生效场数"
        assert "N=106" in md, "总场数也得留着 —— 两个数缺一不可"

    def test_rollback_line_says_unknown_for_a_legacy_archive(self):
        """旧存档没有 `n_delta` 键 ⇒ 明写「未知」,**不许当 0**。

        「这一版没记」和「记了是 0」是两件事 —— 后者会让人以为上次也没生效。
        """
        from nutmeg.v4.cli import delta_calibration as DC
        prev = {DC.slice_key(1, "俱乐部"): {"n": 100, "raw_ll": 1.0, "c1_ll": 1.2},
                "_gap_days": 14, "_date": "2026-08-03"}
        md = DC.render({(1, "俱乐部"): self._rows(14, 106, worse=True)}, min_n=10, prev=prev)
        assert "上次未知(旧存档)" in md, f"旧存档没被标成未知:\n{md}"
