"""CLV soft-water gate statistics: cluster-robust t-test + BHY-FDR + two layers.

Replaces the old ``N≥15/38`` selected-counter, which had no statistical meaning —
a count is not a significance test, and screening the 13 trained leagues for the
"softest" is multiple testing (a flat p=0.05 systematically manufactures false
positives). Per ``docs/clv_statistical_methodology.md`` §4 the gate is:

  * the t-stat of the MEAN per-leg CLV (not a count): ``t = mean / SE(mean)``;
  * threshold ``t≈2.8`` (one-sided p<0.005) — the Harvey-Liu-Zhu multiple-testing
    floor, not p=0.05;
  * BHY/FDR correction across the league family, so the "soft" league that pops
    out of 13 is an edge, not the luckiest draw;
  * two layers — WARN (worth watching, N≥15) vs CONFIRM (act: t≥2.8 ∧ FDR-pass ∧
    N in the hundreds).

Correctness choices, each guarding a way the naive test stays "too loose":

  * CLUSTER-ROBUST SE, clustered by match-day. CLV legs that share a round move
    together (one public-money wave, one close-capture timing). An i.i.d. t-test
    counts N correlated legs as N independent and OVERSTATES t — the same "too
    loose" sin in subtler form. Clustering inflates the SE to the honest
    effective sample size. With one observation per cluster this reduces EXACTLY
    to the standard one-sample t-test.
  * BHY (Benjamini–Yekutieli), not BH: controls FDR under ARBITRARY dependence
    (league CLVs may be +/- correlated); more conservative, the right trade when
    the cost of a false "this league is soft" is real money.
  * ONE-SIDED (mean CLV > 0): we only ever act on POSITIVE soft-water.

Pure functions + frozen dataclasses; no DB, no I/O. scipy supplies the
t-distribution survival function.
"""
from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass

from scipy import stats as _sps

# Thresholds — docs/clv_statistical_methodology.md §4.
WARN_MIN_N = 15        # "worth watching" (the old +5%-edge counter target)
CONFIRM_T = 2.8        # one-sided p≈0.005 — multiple-testing floor (Harvey-Liu-Zhu)
CONFIRM_MIN_N = 200    # "N in the hundreds" — a real edge needed ~672 to reach p≈0.09
FDR_Q = 0.05           # BHY false-discovery rate across the league family


@dataclass(frozen=True)
class MeanTest:
    """One group's cluster-robust mean-CLV test."""

    n: int
    n_clusters: int
    mean: float
    t: float | None          # None when undefined (n<2, <2 clusters, or zero spread)
    p: float | None          # one-sided P(observed mean | H0 mean=0); None when t is None


def _one_sided_p(t: float, df: float) -> float:
    """P(T_df > t): the chance of a mean at least this positive under H0 mean=0."""
    return float(_sps.t.sf(t, df))


def mean_clv_test(values, clusters=None) -> MeanTest:
    """Cluster-robust one-sided t-test of ``mean(values) > 0``.

    ``clusters``: a hashable id per value (e.g. match_date). ``None`` → every
    observation is its own cluster, i.e. the naive i.i.d. one-sample t-test — and
    in that case this returns EXACTLY the textbook ``t = mean / (s/√n)`` with
    ``df = n−1`` (a property the tests pin against scipy's ``ttest_1samp``).
    Passing the round as the cluster is what the gate uses, because soft-water
    legs on the same day are correlated.
    """
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return MeanTest(0, 0, 0.0, None, None)
    mean = st.fmean(vals)
    if clusters is None:
        clusters = range(n)                      # each obs its own cluster
    groups: dict = {}
    for v, c in zip(vals, clusters, strict=True):
        groups.setdefault(c, []).append(v)
    g = len(groups)
    if n < 2 or g < 2:
        return MeanTest(n, g, mean, None, None)
    # Cluster-robust variance of the mean (CR1):
    #   meat = Σ_g (Σ_{i∈g}(x_i − mean))²   ;   Var(mean) = corr · meat / n²
    # finite-cluster correction corr = g/(g−1). With g=n this collapses to the
    # ordinary SE² = Σ(x−mean)² / [(n−1)·n].
    tss = math.fsum((x - mean) ** 2 for x in vals)       # total spread, the scale
    meat = 0.0
    for members in groups.values():
        s = math.fsum(x - mean for x in members)
        meat += s * s
    # Degenerate: zero spread, or perfectly offsetting clusters whose residuals
    # cancel (meat≈0 only as float noise) → SE→0 would fabricate t→∞. Guard with a
    # RELATIVE floor, not `meat<=0` (which float noise sails past).
    if tss <= 0.0 or meat <= 1e-9 * tss:
        return MeanTest(n, g, mean, None, None)
    var_mean = (g / (g - 1)) * meat / (n * n)
    se = math.sqrt(var_mean)
    if se <= 0.0:
        return MeanTest(n, g, mean, None, None)
    t = mean / se
    df = g - 1                                    # clustered df = #clusters − 1
    return MeanTest(n, g, mean, t, _one_sided_p(t, df))


def bhy_reject(pvalues, q: float = FDR_Q) -> list[bool]:
    """Benjamini–Yekutieli step-up: which hypotheses to reject controlling
    FDR ≤ q under ARBITRARY dependence. Returns a ``list[bool]`` parallel to
    ``pvalues``. Differs from plain BH by the harmonic factor ``c(m)=Σ1/i``,
    which makes it valid (more conservative) when the tests are dependent — as
    league CLVs are.
    """
    m = len(pvalues)
    if m == 0:
        return []
    c = math.fsum(1.0 / i for i in range(1, m + 1))   # harmonic dependence factor
    order = sorted(range(m), key=lambda i: pvalues[i])
    kmax = 0
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= (rank / (m * c)) * q:
            kmax = rank
    reject = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= kmax:
            reject[idx] = True
    return reject


@dataclass(frozen=True)
class LeagueVerdict:
    """Two-layer verdict for one league."""

    league: str
    n: int
    n_clusters: int
    mean: float
    t: float | None
    p: float | None
    in_family: bool          # had a computable p → entered the FDR family
    fdr_pass: bool           # survived BHY across the family
    layer: str               # 'confirm' | 'warn' | '—'
    reason: str


def evaluate(
    per_league,
    *,
    warn_min_n: int = WARN_MIN_N,
    confirm_t: float = CONFIRM_T,
    confirm_min_n: int = CONFIRM_MIN_N,
    fdr_q: float = FDR_Q,
) -> list[LeagueVerdict]:
    """Classify each league into confirm / warn / —.

    ``per_league``: ``{league: {"values": [clv, ...], "clusters": [id, ...]}}``
    (``clusters`` optional; defaults to one-per-obs). The FDR family is exactly
    the leagues with a computable one-sided p (≥2 clusters). Returns verdicts
    sorted confirm→warn→rest, then by t descending.
    """
    tests = {
        lg: mean_clv_test(d.get("values", []), d.get("clusters"))
        for lg, d in per_league.items()
    }
    family = [lg for lg, mt in tests.items() if mt.p is not None]
    rej = bhy_reject([tests[lg].p for lg in family], fdr_q)
    fdr_pass = dict(zip(family, rej, strict=True))

    verdicts: list[LeagueVerdict] = []
    for lg, mt in tests.items():
        passed = fdr_pass.get(lg, False)
        in_fam = lg in fdr_pass
        if (
            mt.t is not None
            and mt.t >= confirm_t
            and passed
            and mt.n >= confirm_min_n
            and mt.mean > 0
        ):
            layer = "confirm"
            reason = f"t={mt.t:.2f}≥{confirm_t} · 过FDR · N={mt.n}≥{confirm_min_n}"
        elif mt.n >= warn_min_n and mt.mean > 0:
            layer = "warn"
            bits = [f"N={mt.n}≥{warn_min_n}"]
            if mt.t is None:
                bits.append("t 未定义(簇<2)")
            else:
                if mt.t < confirm_t:
                    bits.append(f"t={mt.t:.2f}<{confirm_t}")
                if not passed and in_fam:
                    bits.append("未过 FDR")
                if mt.n < confirm_min_n:
                    bits.append(f"N<{confirm_min_n}")
            reason = "观察: " + ", ".join(bits)
        else:
            layer = "—"
            reason = (
                f"平均 CLV {mt.mean * 100:+.1f}%≤0"
                if mt.mean <= 0
                else f"N={mt.n}<{warn_min_n}"
            )
        verdicts.append(
            LeagueVerdict(lg, mt.n, mt.n_clusters, mt.mean, mt.t, mt.p,
                          in_fam, passed, layer, reason)
        )
    order = {"confirm": 0, "warn": 1, "—": 2}
    verdicts.sort(key=lambda v: (order[v.layer], -(v.t if v.t is not None else -9.9)))
    return verdicts


def pooled_test(per_league) -> MeanTest:
    """All leagues pooled into one cluster-robust test, for context only.

    Clusters are namespaced by league so the same match_date in two leagues does
    not collapse. NB this pooled number ignores the cross-league multiple-testing
    problem — it is a sanity readout, never the gate.
    """
    vals: list[float] = []
    clusters: list = []
    for lg, d in per_league.items():
        vs = [float(v) for v in d.get("values", [])]
        cs = d.get("clusters")
        if cs is None:
            cs = range(len(vs))
        vals += vs
        clusters += [(lg, c) for c in cs]
    return mean_clv_test(vals, clusters)
