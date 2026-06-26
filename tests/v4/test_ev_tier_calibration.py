"""V14 (Feature B) — pure bucketing logic for the EV-tier calibration measure."""
from __future__ import annotations

import math

from nutmeg.v4.model.ev_tier_calibration import (
    TIERS,
    BandStat,
    by_bins,
    by_tier,
    tier_of,
)


class TestTierOf:
    def test_mirrors_dashboard_boundaries(self):
        # cold p<0.15 ; chalk p>0.77 ; sweet 0.25..0.67 ; edge else (incl 0.15..0.25)
        assert tier_of(0.10) == "cold"
        assert tier_of(0.149) == "cold"
        assert tier_of(0.15) == "edge"   # 'overpriced' RETIRED (n=323 phantom) → edge
        assert tier_of(0.18) == "edge"
        assert tier_of(0.199) == "edge"
        assert tier_of(0.20) == "edge"
        assert tier_of(0.25) == "sweet"
        assert tier_of(0.50) == "sweet"
        assert tier_of(0.67) == "sweet"
        assert tier_of(0.68) == "edge"
        assert tier_of(0.77) == "edge"      # 0.77 is NOT >0.77
        assert tier_of(0.78) == "chalk"
        assert tier_of(0.95) == "chalk"

    def test_rejects_non_probabilities(self):
        assert tier_of(0.0) is None
        assert tier_of(1.0) is None
        assert tier_of(-0.1) is None
        assert tier_of(1.2) is None


class TestStat:
    def test_perfect_calibration_zero_gap(self):
        # half the p=0.5 samples hit → realised 0.5 == implied 0.5
        samples = [(0.5, 1), (0.5, 0), (0.5, 1), (0.5, 0)]
        st = by_tier(samples)["sweet"]
        assert st.n == 4
        assert abs(st.mean_p - 0.5) < 1e-12
        assert abs(st.hit_rate - 0.5) < 1e-12
        assert abs(st.gap) < 1e-12
        assert abs(st.abs_gap) < 1e-12

    def test_negative_gap_when_realised_below_implied(self):
        # implied 0.20 but only 1/10 actually happen → realised < implied
        samples = [(0.20, 1)] + [(0.20, 0)] * 9
        st = by_tier(samples)["edge"]
        assert st.n == 10
        assert abs(st.mean_p - 0.20) < 1e-12
        assert abs(st.hit_rate - 0.10) < 1e-12
        assert st.gap < 0
        assert abs(st.abs_gap - 0.10) < 1e-12

    def test_empty_tier_is_nan_n_zero(self):
        st = by_tier([(0.5, 1)])["cold"]
        assert st.n == 0
        assert math.isnan(st.mean_p) and math.isnan(st.gap)


class TestByTier:
    def test_routes_each_sample_to_right_tier(self):
        samples = [(0.10, 0), (0.17, 1), (0.22, 1), (0.50, 1), (0.90, 1)]
        res = by_tier(samples)
        assert set(res) == set(TIERS)
        assert res["cold"].n == 1
        assert res["edge"].n == 2         # 0.17 and 0.22 both → edge (0.15–0.25)
        assert res["sweet"].n == 1
        assert res["chalk"].n == 1

    def test_drops_non_probabilities(self):
        res = by_tier([(0.5, 1), (0.0, 0), (1.0, 1)])
        assert res["sweet"].n == 1
        assert sum(s.n for s in res.values()) == 1


class TestByBins:
    def test_last_bin_is_right_closed(self):
        # p == 1.0 would be dropped by tier_of, but by_bins bins raw p; the
        # final bin [0.85,1.0] must INCLUDE its right edge.
        bins = by_bins([(0.90, 1), (1.00, 0)], [0.0, 0.85, 1.0])
        last = bins[-1]
        assert last.label.endswith("1.00]")
        assert last.n == 2

    def test_interior_bin_is_right_open(self):
        # p == 0.50 lands in [0.50,0.67), not [0.33,0.50)
        edges = [0.33, 0.50, 0.67]
        bins = by_bins([(0.50, 1)], edges)
        assert bins[0].n == 0      # [0.33,0.50)
        assert bins[1].n == 1      # [0.50,0.67]

    def test_one_bandstat_per_bin(self):
        edges = [0.0, 0.25, 0.5, 0.75, 1.0]
        bins = by_bins([(0.1, 0), (0.3, 1), (0.6, 1), (0.8, 0)], edges)
        assert len(bins) == 4
        assert all(isinstance(b, BandStat) for b in bins)
