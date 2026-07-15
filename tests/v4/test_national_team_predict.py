"""V10 W1 Track B Day 3 — tests for national_team_predict module."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.model.national_team_predict import (
    NationalTeamModel,
    bayesian_blend,
    elo_predict_frame,
    elo_to_1x2_probs,
    hit_rate_1x2,
    log_loss_1x2,
    market_implied_probs,
    outcomes_from_goals,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data" / "external"
_HAS_WC_DATA = (DATA / "cup_history" / "WC_2022.parquet").exists() and any(
    (DATA / "eloratings").glob("eloratings_*.parquet")
) if (DATA / "eloratings").exists() else False

# 2026-07-15 — 快照必须【钉死】。`build_wc_training_frame(elo_snapshot_path=None)` 会
# 自动抓 data/external/eloratings/ 下【最新】的快照,而 Elo cron 每周写一个新的 → 这个
# 号称「固定的 2018→2022 历史 walk-forward」的数每周都在悄悄变。实测同一份代码、同一批
# 历史比赛,只换快照:
#     2026-05-25 → 0.9802   2026-06-07 → 0.9767   2026-06-13 → 0.9832
#     2026-06-27 → 0.9859   2026-07-04 → 0.9972   2026-07-11 → 1.0003 ❌
# 当年 SHIP 时用的快照恰好在 1.00 以内,之后一路爬,上周三越线 → 测试红。
# 那不是模型退化,是尺子自己在漂。钉死 = 至少可复现。
_ELO_SNAPSHOT = DATA / "eloratings" / "eloratings_2026-07-11.parquet"

# 逐场【赛前】Elo(时点,零泄漏)—— nutmeg-ingest-eloratings-history 产出。
# 有它就用它:它把未来函数和特征退化一起修掉了(见下方 class docstring 的实测对照)。
_ELO_HISTORY_DIR = DATA / "eloratings_history"


class TestEloToOneXTwoProbs:
    """Closed-form Elo → 1X2."""

    def test_equal_elos_yield_near_one_third(self):
        p_h, p_d, p_a = elo_to_1x2_probs(1900, 1900)
        # Equal Elo → home/away should be near (1-draw)/2 each
        assert abs(p_h - p_a) < 1e-6
        assert p_d > 0.20  # tournament base draw
        assert abs(p_h + p_d + p_a - 1.0) < 1e-9

    def test_strong_home_skews_home_probability(self):
        # Spain (2165) vs Qatar (1425)
        p_h, p_d, p_a = elo_to_1x2_probs(2165, 1425)
        assert p_h > 0.85
        assert p_a < 0.05
        # Draw rate falls off for big gaps
        assert p_d < 0.10

    def test_home_advantage_shifts_probability(self):
        baseline = elo_to_1x2_probs(1800, 1800, home_adv=0)
        with_adv = elo_to_1x2_probs(1800, 1800, home_adv=50)
        # 50-point Elo home advantage should bump home prob
        assert with_adv[0] > baseline[0]
        assert with_adv[2] < baseline[2]

    def test_normalized_to_one(self):
        # Sanity across a range
        for h_elo, a_elo in [(1500, 2000), (2000, 2000), (2200, 1300)]:
            probs = elo_to_1x2_probs(h_elo, a_elo)
            assert abs(sum(probs) - 1.0) < 1e-9


class TestEloPredictFrame:
    def test_missing_elo_defaults_to_uniform(self):
        df = pd.DataFrame([
            {"home_team": "A", "away_team": "B", "home_elo": None, "away_elo": 1500},
            {"home_team": "C", "away_team": "D", "home_elo": 1800, "away_elo": 1800},
        ])
        probs = elo_predict_frame(df)
        assert probs.shape == (2, 3)
        # Row 0 — missing elo → uniform
        np.testing.assert_allclose(probs[0], [1/3, 1/3, 1/3])
        # Row 1 — equal Elos
        assert probs[1].sum() == pytest.approx(1.0)


class TestMarketImpliedProbs:
    def test_basic_normalization(self):
        ph = pd.Series([2.0])
        pd_ = pd.Series([3.0])
        pa = pd.Series([6.0])
        probs = market_implied_probs(ph, pd_, pa)
        # 1/2 + 1/3 + 1/6 = 1.0 (no vig); should yield [0.5, 0.333, 0.167]
        np.testing.assert_allclose(probs[0], [0.5, 1/3, 1/6], atol=1e-6)
        assert probs[0].sum() == pytest.approx(1.0)

    def test_nan_passes_through(self):
        probs = market_implied_probs(
            pd.Series([2.0, np.nan]),
            pd.Series([3.0, 3.0]),
            pd.Series([3.0, 3.0]),
        )
        assert not np.isnan(probs[0]).any()
        assert np.isnan(probs[1]).all()


class TestOutcomesFromGoals:
    def test_basic_outcomes(self):
        out = outcomes_from_goals(
            pd.Series([2, 1, 1, np.nan]),
            pd.Series([1, 1, 2, 0]),
        )
        np.testing.assert_array_equal(out, [0, 1, 2, -1])  # H, D, A, unplayed


class TestLogLossAndHitRate:
    def test_log_loss_skips_unplayed(self):
        probs = np.array([[0.5, 0.3, 0.2], [0.3, 0.4, 0.3]])
        outcomes = np.array([0, -1])  # 1st: H (matches), 2nd: unplayed (skip)
        ll = log_loss_1x2(probs, outcomes)
        # Only 1 row → log(0.5) = 0.693
        assert ll == pytest.approx(-np.log(0.5), abs=1e-6)

    def test_hit_rate_basic(self):
        probs = np.array([[0.6, 0.2, 0.2], [0.1, 0.7, 0.2], [0.2, 0.3, 0.5]])
        outcomes = np.array([0, 1, 0])  # 2/3 correct
        assert hit_rate_1x2(probs, outcomes) == pytest.approx(2.0 / 3.0)


class TestBayesianBlend:
    def test_alpha_one_returns_model(self):
        m = np.array([[0.5, 0.3, 0.2]])
        k = np.array([[0.1, 0.1, 0.8]])
        out = bayesian_blend(m, k, alpha=1.0)
        np.testing.assert_allclose(out, m)

    def test_alpha_zero_returns_market(self):
        m = np.array([[0.5, 0.3, 0.2]])
        k = np.array([[0.1, 0.1, 0.8]])
        out = bayesian_blend(m, k, alpha=0.0)
        np.testing.assert_allclose(out, k)

    def test_market_nan_falls_back_to_model(self):
        m = np.array([[0.5, 0.3, 0.2]])
        k = np.array([[np.nan, np.nan, np.nan]])
        out = bayesian_blend(m, k, alpha=0.5)
        np.testing.assert_allclose(out, m)


class TestNationalTeamModelUnit:
    """Doesn't require local WC data — uses synthetic features."""

    def test_predict_without_fit_falls_back_to_elo(self):
        df = pd.DataFrame([
            {"home_team": "Spain", "away_team": "Qatar",
             "home_elo": 2165, "away_elo": 1425},
        ])
        model = NationalTeamModel()
        probs = model.predict_proba(df)
        # Should match closed-form Elo
        expected = elo_to_1x2_probs(2165, 1425)
        np.testing.assert_allclose(probs[0], expected, atol=1e-6)

    def test_fit_then_predict_returns_valid_probs(self):
        # Synthetic training set, 20 rows
        rng = np.random.default_rng(42)
        n = 30
        df = pd.DataFrame({
            "home_team": [f"H{i}" for i in range(n)],
            "away_team": [f"A{i}" for i in range(n)],
            "home_elo": rng.normal(1800, 150, n),
            "away_elo": rng.normal(1800, 150, n),
            "psc_home": [None] * n,
            "psc_draw": [None] * n,
            "psc_away": [None] * n,
        })
        y = rng.integers(0, 3, n)
        model = NationalTeamModel()
        model.fit(df, y)
        probs = model.predict_proba(df)
        assert probs.shape == (n, 3)
        # All probs in [0, 1] and rows sum ≈ 1
        assert (probs >= 0).all() and (probs <= 1).all()
        np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)


def _wc_walk_forward(elo_snapshot=_ELO_SNAPSHOT, elo_history=True):
    """2018 训练 → 2022 测试。返回 (blend, pin, lgb, y) 四份对齐的数组。

    显式传 elo_snapshot(绝不用默认的 None=抓最新),见 _ELO_SNAPSHOT 的漂移说明。
    elo_history=True 时用【逐场赛前】Elo(时点,零泄漏),否则退回快照口径(有未来函数,
    只留给对照实验)。
    """
    from nutmeg.v4.data.wc_training_frame import build_wc_training_frame

    def _hist(year):
        p = _ELO_HISTORY_DIR / f"matches_{year}.parquet"
        return str(p) if (elo_history and p.exists()) else None

    df_train = build_wc_training_frame(2018, elo_snapshot_path=elo_snapshot,
                                       elo_match_history_path=_hist(2018))
    df_test = build_wc_training_frame(2022, elo_snapshot_path=elo_snapshot,
                                      elo_match_history_path=_hist(2022))
    y_train = outcomes_from_goals(df_train["home_goals"], df_train["away_goals"])
    y_test = outcomes_from_goals(df_test["home_goals"], df_test["away_goals"])

    mask_t = df_train["home_elo"].notna() & df_train["away_elo"].notna() & (y_train >= 0)
    mask_v = df_test["home_elo"].notna() & df_test["away_elo"].notna() & (y_test >= 0)
    df_train_ok, y_train_ok = df_train[mask_t].reset_index(drop=True), y_train[mask_t]
    df_test_ok, y_test_ok = df_test[mask_v].reset_index(drop=True), y_test[mask_v]

    model = NationalTeamModel()
    model.fit(df_train_ok, y_train_ok, host_country="Russia", host_advantage=50.0)
    lgb = np.asarray(
        model.predict_proba(df_test_ok, host_country="Qatar", host_advantage=50.0), float)
    pin = np.asarray(market_implied_probs(
        df_test_ok["psc_home"], df_test_ok["psc_draw"], df_test_ok["psc_away"]), float)
    # α=0.4 per Day 3。NB bayesian_blend 在 pin 全 NaN 的行上【回退成纯模型】(fail-soft),
    # 所以 blend 没有 NaN 行,而 pin 有 —— 下面比大小必须先对齐到 pin 可用的子集。
    blend = np.asarray(bayesian_blend(lgb, pin, alpha=0.4), float)
    return blend, pin, lgb, np.asarray(y_test_ok)


@pytest.mark.skipif(
    not _HAS_WC_DATA or not _ELO_SNAPSHOT.exists(),
    reason=f"WC 2022 fixtures/odds + 钉死的 Elo 快照 {_ELO_SNAPSHOT.name} required",
)
class TestWalkForwardOnWC:
    """2018→2022 WC walk-forward。

    ⚠️⚠️ 2026-07-15 复盘 —— 这个 walk-forward 目前【在科学上是无效的】,别拿它的数字当
    模型好坏的证据。原 `test_blend_meets_ship_gate`(绝对闸门 log-loss ≤ 1.00,d427edd
    「→ SHIP」)三重破产:

    1. **未来函数**:磁盘上的 eloratings 快照【全是 2026 年的】(schema 只有 rank/
       country_code/elo/elo_1y_ago,没有时间维度)。于是 2018 年踢的比赛被贴上 2026 年
       7 月的 Elo —— 那份评分里已经编码了要预测的结果本身,外加之后 8 年。
    2. **特征退化**:同一份快照同时贴给 2018 帧和 2022 帧 → 两季都出现的 24 支队
       【24/24 Elo 完全相同】。模型根本区分不了 2018-法国 和 2022-法国,只能背一张静态
       国家强弱表。这解释了实测:纯模型 log-loss 1.0983 vs 均匀先验 1.0986 —— 它其实
       什么都没学到。
    3. **闸门本身不自洽**:在同样这 63 场上,【sharp 市场自己】log-loss = 1.0056。
       原闸门要求 ≤ 1.00,等于要求我们在 64 场样本上打赢 Pinnacle。而 1.0003 这个
       「差点就过」的数还是被【一场】撑出来的:卡塔尔 vs 厄瓜多尔没有 Pinnacle 线 →
       blend 回退成纯模型 → 模型恰好给了厄瓜多尔 79% 且押中 → 这一行的 loss 0.2324
       把均值从 1.0125 拉到 1.0003(单行撬动 0.012,而闸门余量只有 0.0003)。

    CI 从没发现这些:`skipif` + data/external 是 gitignore 的 → 这个测试【在 CI 里从未
    运行过】,一直"绿"。它只在 owner 的机器上跑,而那台机器的 Elo 快照每周被 cron 换掉。

    修法(未做,需单独一轮):去 eloratings.net 回填【时点】Elo(2018/2022 当时的评分),
    才能做一次诚实的 walk-forward,然后再决定 WC 模型到底该不该上。现有 6 个快照全是
    2026 的,救不了。
    """

    def test_walk_forward_is_reproducible_under_pinned_elo(self):
        """钉死快照后必须可复现 —— 这是防【尺子自己漂】那个坑复发的护栏。

        原实现走 elo_snapshot_path=None(=抓最新),Elo cron 每周写一个新快照,同一段
        代码同一批历史比赛就每周换一个数,直到某周越过闸门、看起来像"模型退化"。
        """
        blend1, _, _, y1 = _wc_walk_forward()
        blend2, _, _, y2 = _wc_walk_forward()
        ll1, ll2 = log_loss_1x2(blend1, y1), log_loss_1x2(blend2, y2)
        assert ll1 == pytest.approx(ll2, abs=1e-12), "同一钉死快照下两次跑出不同的数"

    def test_point_in_time_elo_beats_uniform(self):
        """时点 Elo 修好后,纯模型必须真的比瞎猜强 —— 这是回填的回归护栏。

        泄漏口径下纯模型 log-loss 1.0983 vs 均匀先验 1.0986 = 差 0.0003 = 什么都没学到
        (同一份 2026 快照贴两季 → 24/24 队 Elo 相同 → 区分不了 2018-法国和 2022-法国)。
        换成逐场时点 Elo 后 1.0097,领先均匀先验 0.089 —— 这个差距大到不是噪声。
        若这条转红,多半是逐场 Elo 没接上(退回了快照口径),而不是模型退化。
        """
        _blend, _pin, lgb, y = _wc_walk_forward()
        assert log_loss_1x2(lgb, y) < np.log(3) - 0.04

    @pytest.mark.xfail(
        strict=True,
        reason="已知红,且这才是诚实的判据。点估计上 blend(0.9797)确实优于单用市场"
               "(1.0056),但【拿不出证据】:N=63、配对 t=0.98、95% bootstrap CI "
               "[−0.024,+0.080] 跨 0;且 α=0.4 是当年在【这同一个测试集】上挑的(扫描显示"
               "最优 α≈0.5=0.9793 就紧挨着)= 拿测试集调参。留 strict=True 当探针:等 WC2026"
               "把 N 堆够、且 α 改成样本外选出来之后,若真显著会转红,提醒回来重判该不该上。",
    )
    def test_blend_significantly_beats_market(self):
        """闸门必须是【显著性】,不是点估计 —— 与 CLV gate 同一个教训(N 小时点估计骗人)。

        必须只在【市场可用】的行上比:blend 在 pin=NaN 的行会回退成纯模型,拿全 64 行比
        就是把"有市场的预测"和"没市场的预测"混着比(那 1 行幸运球曾把均值撬走 0.012)。
        """
        blend, pin, _lgb, y = _wc_walk_forward()
        ok = np.isfinite(pin).all(axis=1)          # 只比市场可用的 63 场
        b, p, yy = blend[ok], pin[ok], y[ok]
        idx = np.arange(len(yy))
        d = (-np.log(np.clip(p[idx, yy], 1e-15, 1))) - (-np.log(np.clip(b[idx, yy], 1e-15, 1)))
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
        assert t > 2.0, (
            f"blend 相对市场的每场优势 {d.mean():+.4f} 但 t={t:.2f} (N={len(d)}) → 不显著,"
            f"拿不出证据说掺模型有增益。别把点估计当信号。"
        )
