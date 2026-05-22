"""Tests for nutmeg.v4.combo (parlay enumeration + Kelly)."""
import pytest

from nutmeg.v4.combo import MatchInput, recommend_combinations
from nutmeg.v4.combo.enumerate import (
    generate_single_parlays,
    rank_parlays,
)
from nutmeg.v4.combo.kelly import fractional_kelly_stake
from nutmeg.v4.combo.selections import build_selections_from_match


def _strong_edge_match(mid: str, lh: float, la: float, h_odds: dict) -> MatchInput:
    return MatchInput(match_id=mid, lambda_home=lh, lambda_away=la,
                      handicap_home=None, odds_1x2=h_odds)


class TestSelections:
    def test_no_handicap_market_when_handicap_none(self):
        m = MatchInput(match_id="X", lambda_home=1.5, lambda_away=1.2,
                       handicap_home=None,
                       odds_1x2={"H": 2.0, "D": 3.5, "A": 4.0})
        sels = build_selections_from_match(m)
        assert all(s.market_type == "1x2" for s in sels)
        assert len(sels) == 3

    def test_edge_computation(self):
        m = MatchInput(match_id="X", lambda_home=2.0, lambda_away=0.8,
                       handicap_home=None,
                       odds_1x2={"H": 2.20, "D": 3.40, "A": 3.60})
        sels = build_selections_from_match(m)
        # Strong home -> positive edge on H
        h = next(s for s in sels if s.outcome == "H")
        assert h.edge > 0


class TestKelly:
    def test_zero_when_negative_ev(self):
        r = fractional_kelly_stake(
            hit_probability=0.3, ev_per_unit=-0.1, bankroll=1000.0,
        )
        assert r.recommended_stake == 0.0

    def test_positive_when_positive_ev(self):
        r = fractional_kelly_stake(
            hit_probability=0.5, ev_per_unit=0.20, bankroll=1000.0,
        )
        assert r.recommended_stake > 0
        assert r.expected_return > 0

    def test_cap_at_max_fraction(self):
        # Huge edge — full kelly would be >> max_stake_fraction
        r = fractional_kelly_stake(
            hit_probability=0.9, ev_per_unit=2.0, bankroll=1000.0,
            kelly_fraction=1.0, max_stake_fraction=0.05,
        )
        assert r.recommended_stake == pytest.approx(50.0, abs=0.01)


class TestEnumeration:
    def _toy_selections(self):
        m1 = _strong_edge_match("M1", 2.2, 0.7, {"H": 2.10, "D": 3.50, "A": 4.00})
        m2 = _strong_edge_match("M2", 2.1, 0.8, {"H": 2.20, "D": 3.60, "A": 3.80})
        m3 = _strong_edge_match("M3", 1.9, 0.9, {"H": 2.40, "D": 3.40, "A": 3.50})
        sels = []
        for m in (m1, m2, m3):
            sels.extend(build_selections_from_match(m))
        return sels

    def test_generates_pairs(self):
        sels = self._toy_selections()
        parlays = generate_single_parlays(sels, k_min=2, k_max=3,
                                           include_compound=False, top_k_per_match=1)
        ks = {p.k for p in parlays}
        assert 2 in ks
        assert 3 in ks

    def test_distinct_matches(self):
        sels = self._toy_selections()
        parlays = generate_single_parlays(sels, k_min=2, k_max=3,
                                           include_compound=False, top_k_per_match=1)
        for p in parlays:
            mids = [leg.match_id for leg in p.legs]
            assert len(set(mids)) == len(mids), "duplicate match in parlay"

    def test_hit_probability_product(self):
        sels = self._toy_selections()
        parlays = generate_single_parlays(sels, k_min=2, k_max=2,
                                           include_compound=False, top_k_per_match=1)
        # For single-outcome 2-leg, hit_p = product of leg probs
        for p in parlays:
            expected = 1.0
            for leg in p.legs:
                expected *= leg.selections[0].probability
            assert p.hit_probability == pytest.approx(expected, abs=1e-9)


class TestRecommendCombinations:
    def test_returns_zero_when_market_is_fair(self):
        """If model probs equal market implied (no edge), no recommendations."""
        # Build matches where lambdas exactly match market odds → 0 edge
        # (Hard to make exactly 0; we use a case where bookmaker has tiny overround
        # so model is slightly below — should give 0 recs.)
        unfavorable = [
            MatchInput(match_id=f"M{i}", lambda_home=1.3, lambda_away=1.3,
                       handicap_home=None,
                       odds_1x2={"H": 2.50, "D": 3.30, "A": 2.50})
            for i in range(5)
        ]
        recs = recommend_combinations(unfavorable, bankroll=1000.0,
                                       min_hit_probability=0.05, min_kelly_stake=2.0)
        assert len(recs) == 0

    def test_returns_recs_when_edge_exists(self):
        with_edge = [
            _strong_edge_match("M1", 2.2, 0.7, {"H": 2.10, "D": 3.50, "A": 4.00}),
            _strong_edge_match("M2", 2.0, 0.8, {"H": 2.30, "D": 3.60, "A": 3.50}),
            _strong_edge_match("M3", 1.9, 0.9, {"H": 2.40, "D": 3.40, "A": 3.50}),
            _strong_edge_match("M4", 1.8, 1.0, {"H": 2.50, "D": 3.40, "A": 3.30}),
        ]
        recs = recommend_combinations(with_edge, bankroll=1000.0,
                                       top_n_recommendations=5,
                                       min_hit_probability=0.05,
                                       min_kelly_stake=2.0)
        assert len(recs) > 0
        for r in recs:
            assert r.parlay.ev_per_unit > 0
            assert r.parlay.hit_probability >= 0.05
            assert r.kelly.recommended_stake >= 2.0
            assert r.kelly_log_growth >= 0  # all recommendations are wealth-positive

    def test_top_rank_has_highest_log_growth(self):
        with_edge = [
            _strong_edge_match("M1", 2.2, 0.7, {"H": 2.10, "D": 3.50, "A": 4.00}),
            _strong_edge_match("M2", 2.0, 0.8, {"H": 2.30, "D": 3.60, "A": 3.50}),
            _strong_edge_match("M3", 1.9, 0.9, {"H": 2.40, "D": 3.40, "A": 3.50}),
            _strong_edge_match("M4", 1.8, 1.0, {"H": 2.50, "D": 3.40, "A": 3.30}),
        ]
        recs = recommend_combinations(with_edge, top_n_recommendations=10)
        for i in range(len(recs) - 1):
            assert recs[i].kelly_log_growth >= recs[i + 1].kelly_log_growth
