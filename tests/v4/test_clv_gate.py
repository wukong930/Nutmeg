"""CLV soft-water gate statistics — the N≥15/38 → t-test + BHY-FDR + 2-layer upgrade.

Pins the properties that make the gate honest:
  * with one obs per cluster it IS the textbook one-sample t-test (vs scipy);
  * clustering by round inflates the SE and lowers t (the anti-"too-loose" guard);
  * BHY rejects nothing when one league is significant among many nulls — the
    multiple-testing fix (same league ALONE would confirm).
"""
from __future__ import annotations

import math

from scipy import stats as sps

from nutmeg.v4.model.clv_gate import (
    CONFIRM_MIN_N,
    CONFIRM_T,
    bhy_reject,
    evaluate,
    mean_clv_test,
    pooled_test,
)


def _vals(mean: float, sd: float, n: int) -> list[float]:
    """n (even) values with exact sample mean and ±sd spread around it."""
    assert n % 2 == 0
    return [mean + (sd if i % 2 == 0 else -sd) for i in range(n)]


# ---------------------------------------------------------------- mean_clv_test

def test_naive_equals_textbook_one_sample_ttest():
    """clusters=None must reproduce scipy's one-sided one-sample t-test exactly."""
    vals = [0.10, -0.05, 0.20, 0.00, 0.15, -0.10, 0.08, 0.12]
    mt = mean_clv_test(vals)            # each obs its own cluster
    ref = sps.ttest_1samp(vals, 0.0, alternative="greater")
    assert mt.n == 8 and mt.n_clusters == 8
    assert abs(mt.t - float(ref.statistic)) < 1e-9
    assert abs(mt.p - float(ref.pvalue)) < 1e-12


def test_clustering_by_round_inflates_se_and_lowers_t():
    """Correlated legs in the same round → clustered SE bigger, t & significance
    lower than the naive i.i.d. test on the same numbers."""
    vals = [0.08] * 5 + [0.06] * 5 + [0.04] * 5 + [0.02] * 5   # mean 0.05
    clusters = [0] * 5 + [1] * 5 + [2] * 5 + [3] * 5           # 4 rounds
    naive = mean_clv_test(vals)                # 20 clusters
    clustered = mean_clv_test(vals, clusters)  # 4 clusters
    assert clustered.n_clusters == 4 and naive.n_clusters == 20
    assert abs(naive.mean - 0.05) < 1e-12 and abs(clustered.mean - 0.05) < 1e-12
    assert clustered.t < naive.t               # SE inflated → t shrinks
    assert clustered.p > naive.p               # and significance weakens


def test_balanced_clusters_cancel_to_undefined():
    """If every round's residuals cancel, the cluster-robust SE is 0 → t undefined
    (we return None rather than a spurious infinity)."""
    vals = [0.04, 0.06] * 10
    clusters = [i // 2 for i in range(20)]     # each round = one 0.04 + one 0.06
    mt = mean_clv_test(vals, clusters)
    assert mt.t is None and mt.p is None and mt.n_clusters == 10


def test_negative_mean_gives_p_above_half():
    mt = mean_clv_test(_vals(-0.03, 0.05, 40))
    assert mt.mean < 0 and mt.p > 0.5


def test_single_cluster_and_tiny_n_undefined():
    assert mean_clv_test([]).t is None
    assert mean_clv_test([0.05]).t is None                    # n<2
    assert mean_clv_test([0.04, 0.06], clusters=[7, 7]).t is None  # one cluster


# ------------------------------------------------------------------- bhy_reject

def test_bhy_all_tiny_reject_all_large_reject_none():
    assert bhy_reject([1e-6, 1e-6, 1e-6], q=0.05) == [True, True, True]
    assert bhy_reject([0.9, 0.8, 0.7], q=0.05) == [False, False, False]


def test_bhy_one_small_among_nulls_rejects_none():
    """The multiple-testing trap: one league at p=0.002 among 11 nulls (p=0.5) is
    NOT discovered — its p exceeds even the rank-1 BHY line."""
    pvals = [0.002] + [0.5] * 11
    rej = bhy_reject(pvals, q=0.05)
    assert rej == [False] * 12
    # sanity: rank-1 threshold is 0.05 / (12 · Σ1/i) ≈ 0.00134 < 0.002
    c = sum(1.0 / i for i in range(1, 13))
    assert 0.05 / (12 * c) < 0.002


def test_bhy_no_more_rejections_than_bh():
    pvals = [0.001, 0.01, 0.02, 0.2, 0.5]
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    bh = 0
    for rank, idx in enumerate(order, 1):
        if pvals[idx] <= (rank / m) * 0.05:
            bh = rank
    assert sum(bhy_reject(pvals, 0.05)) <= bh   # BHY ⊆ BH (more conservative)


# --------------------------------------------------------------------- evaluate

def _confirm_league(n=CONFIRM_MIN_N + 50, t_target=CONFIRM_T + 0.2):
    """Per-obs-cluster league engineered to a target t (high df)."""
    sd = 0.10
    mean = t_target * sd / math.sqrt(n)        # t = mean / (sd/√n), sample sd≈sd
    return {"values": _vals(mean, sd, n), "clusters": list(range(n))}


def test_evaluate_confirm_when_alone():
    v = evaluate({"软联": _confirm_league()})
    assert v[0].layer == "confirm" and v[0].fdr_pass and v[0].t >= CONFIRM_T


def test_evaluate_same_league_only_warns_among_many_nulls():
    """THE multiple-testing fix: a league that confirms ALONE drops to 'warn' once
    it is screened alongside 11 null leagues — exactly what the upgrade buys."""
    leagues = {"软联": _confirm_league()}
    for i in range(11):
        leagues[f"null{i}"] = {"values": _vals(0.0, 0.05, 30),
                               "clusters": list(range(30))}
    verdicts = {v.league: v for v in evaluate(leagues)}
    soft = verdicts["软联"]
    assert soft.t >= CONFIRM_T and soft.n >= CONFIRM_MIN_N   # passes t & N floors…
    assert not soft.fdr_pass and soft.layer == "warn"        # …but FDR blocks confirm
    assert all(v.layer != "confirm" for v in verdicts.values())


def test_evaluate_warn_then_dash():
    leagues = {
        "warnable": {"values": _vals(0.03, 0.10, 20), "clusters": list(range(20))},
        "too_few": {"values": _vals(0.20, 0.05, 6), "clusters": list(range(6))},
        "negative": {"values": _vals(-0.04, 0.05, 40), "clusters": list(range(40))},
    }
    v = {x.league: x for x in evaluate(leagues)}
    assert v["warnable"].layer == "warn" and v["warnable"].t < CONFIRM_T
    assert v["too_few"].layer == "—"      # N<15
    assert v["negative"].layer == "—"     # mean≤0


def test_pooled_namespaces_clusters_by_league():
    """Same match_date in two leagues must not collapse into one cluster."""
    per = {
        "A": {"values": [0.05, 0.06], "clusters": ["2026-08-01", "2026-08-08"]},
        "B": {"values": [0.04, 0.07], "clusters": ["2026-08-01", "2026-08-08"]},
    }
    assert pooled_test(per).n_clusters == 4    # not 2
