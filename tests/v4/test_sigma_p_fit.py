"""σ_P 分层拟合仪表 —— 锁住口径、分层归属、以及「未到评估点不判定」。

这个仪表的存在理由是「到了评估点会被发现」(prereg v2.1 §7)。所以它最坏的失效
不是崩,而是**悄悄不再监督它该监督的东西**:线上常数被快照、评估点被自动推进、
或者把「未到点」渲染成看起来像结论的样子。下面钉的就是这些。
"""
from __future__ import annotations

import pytest

from nutmeg.v4.cli.sigma_p_fit import (
    _ANCHOR_MAX_H,
    _STRATA,
    NEXT_EVAL_N,
    _live_coef,
    bucket_points,
    buckets,
    fit_power,
    render,
    robust_sigma,
)
from nutmeg.v4.model import ev_threshold as ET


def _traj(hours, *, league="芬超", stratum=_STRATA[0], trained=False, drift=0.0):
    """造一条轨迹:锚在 hours[0],其余点按 drift×h 线性漂。"""
    pts = [(h, 0.40 + drift * h, 0.30 - drift * h, 0.30) for h in hours]
    return {"league": league, "stratum": stratum, "trained": trained, "points": pts}


def test_live_coefficients_are_read_lazily_not_snapshotted(monkeypatch):
    """⭐ 线上常数必须**现读** `ev_threshold`,不能在模块加载时快照。

    `delta_calibration` 踩过这个坑:初版把常数在 import 时求值存进元组,那样将来
    有人改了那边的值,仪表会悄悄停在旧值上 —— 而它的全部职责就是监督那些值。
    """
    before = _live_coef("H")
    monkeypatch.setitem(ET.FREEZE_SIGMA_COEF, "H", (0.0999, 0.999))
    assert before != (0.0999, 0.999), "测试前提:原值不应恰好是这个哨兵值"
    assert _live_coef("H") == (0.0999, 0.999), "改了 ev_threshold 却没跟上 = 已漂"


def test_anchor_gate_is_load_time_not_render_time():
    """近收盘锚闸(≤1.5h)是**口径**的一部分,和 A-1 逐条对齐,不许放松。

    这里只钉常数本身 —— 真正的过滤在 load_trajectories 里(要 DB)。常数被改大
    就意味着换了口径、两次拟合不再可比,这条会红。
    """
    assert _ANCHOR_MAX_H == 1.5


def test_eval_point_threshold_is_a_manual_gate_not_auto_advancing():
    """⚠️ prereg §3.2:评估未过 ⇒ 下次门槛翻倍,由 owner 手动改这个常数。

    **自动推进 = 无人看管的反复检验**,正是 §3 要防的 optional stopping。
    这条钉住它是个模块级常数(可被人审阅/diff),而不是运行时算出来的。
    """
    assert isinstance(NEXT_EVAL_N, int)
    assert NEXT_EVAL_N >= 300, "门槛只能由 owner 按 prereg 上调,不能下调"


def test_render_says_not_at_eval_point_when_no_trained_league_data():
    """没有 13 训练联赛数据时,必须明说「未到评估点」并**不给判定**。

    ⚠️ 这是本仪表最容易坏的地方:表格照常渲染,人一眼扫过去就当成了结论。
    """
    trajs = [_traj([0.5, 3, 10, 30, 60], drift=0.001 * i) for i in range(60)]
    txt = render(trajs, n_boot=20, seed=1)
    assert "未到评估点" in txt
    assert f"0 / {NEXT_EVAL_N}" in txt, "进度条要显示 13 训练联赛的真实计数"
    assert "已到评估点" not in txt


def test_render_never_emits_a_betting_recommendation():
    trajs = [_traj([0.5, 3, 10, 30, 60], drift=0.001 * i) for i in range(60)]
    txt = render(trajs, n_boot=20, seed=1)
    for banned in ("建议下注", "推荐买", "可以下", "应当改成"):
        assert banned not in txt
    assert "永不 gate" in txt
    assert "不判闸" in txt


def test_render_survives_tiny_input_without_pretending():
    assert "样本太小" in render([_traj([0.5, 3])], n_boot=10, seed=1)


def test_per_league_empty_table_explains_itself():
    """空的诊断表必须报出最大联赛的 N —— 光写「无」会被读成「管线坏了」。"""
    trajs = [_traj([0.5, 3, 10, 30, 60], league="芬超", drift=0.001 * i) for i in range(50)]
    txt = render(trajs, n_boot=20, seed=1)
    assert "最大为 芬超 50 条" in txt


def test_fit_recovers_a_known_power_law():
    """自检:喂一条已知的 σ=A·h^B,拟合要能还原它(否则整张表都不可信)。"""
    a0, b0 = 0.010, 0.25
    pts = [(h, a0 * h ** b0, 100) for h in (1, 2, 4, 8, 16, 32, 64)]
    a, b = fit_power(pts)
    assert a == pytest.approx(a0, rel=1e-6)
    assert b == pytest.approx(b0, rel=1e-6)


def test_robust_sigma_ignores_a_single_wild_outlier():
    """MAD 口径的意义:一条脏线(比如领先方的滚球线)不该把整个桶的 σ 顶上天。

    ⚠️ 样本必须**单峰**。我第一版写了两簇挤在 ±0.01 的双峰样本 —— 中位数落在两簇
    之间的空隙上,加一个点就跳到某一簇,测出来的是中位数位置抖动而不是抗离群性。
    """
    clean = [i * 0.002 - 0.02 for i in range(21)]        # −0.02…+0.02 均匀单峰
    assert robust_sigma([*clean, 5.0]) == pytest.approx(robust_sigma(clean), rel=0.15)
    # 对照:同一条脏线进朴素 SD 会把它顶高一个量级以上
    import statistics as _st
    assert _st.pstdev([*clean, 5.0]) > 10 * _st.pstdev(clean)


def test_one_increment_per_bucket_per_trajectory():
    """抓得密的场次不许主导某个桶 —— 每轨每桶只取一条增量。"""
    dense = _traj([0.5, 20, 21, 22, 23, 24])        # 16-32h 桶里塞了 5 个点
    acc = buckets([dense])
    assert len(acc["H"][(16, 32)]) == 1


def test_bucket_points_drops_underpowered_buckets():
    """N < 20 的桶直接丢弃,不进拟合 —— 否则少数噪声桶会拽偏系数。"""
    thin = [_traj([0.5, 20]) for _ in range(5)]
    assert bucket_points(buckets(thin)["H"]) == []
