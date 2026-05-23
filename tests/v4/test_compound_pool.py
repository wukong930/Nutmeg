"""Tests for nutmeg.v4.combo.compound_pool (V6 W3)."""
from __future__ import annotations

from math import comb

import pytest

from nutmeg.v4.combo.compound_pool import (
    MAX_LEGS_PER_TICKET,
    STAKE_UNIT_CNY,
    PoolRecommendation,
    PoolTicket,
    enumerate_combinations,
    evaluate_ticket,
    quantize_stake,
    recommend_pool,
)
from nutmeg.v4.combo.selections import Selection


def _sel(
    match_id: str, outcome: str = "H", prob: float = 0.5, odds: float = 2.10,
    market: str = "1x2",
) -> Selection:
    return Selection(
        match_id=match_id,
        market_type=market,
        outcome=outcome,
        probability=prob,
        odds=odds,
    )


class TestQuantizeStake:
    def test_below_unit_zero(self):
        assert quantize_stake(0.5) == 0.0
        assert quantize_stake(1.99) == 0.0

    def test_exact_unit(self):
        assert quantize_stake(2.0) == 2.0
        assert quantize_stake(10.0) == 10.0

    def test_floor_to_nearest_unit(self):
        assert quantize_stake(3.5) == 2.0
        assert quantize_stake(7.99) == 6.0
        assert quantize_stake(99.0) == 98.0  # floor to even

    def test_custom_unit(self):
        assert quantize_stake(11.5, unit=5.0) == 10.0
        assert quantize_stake(4.99, unit=5.0) == 0.0


class TestEnumerateCombinations:
    def test_c_m_n_count(self):
        sels = [_sel(f"m{i}") for i in range(6)]
        combos = enumerate_combinations(sels, n=4)
        assert len(combos) == comb(6, 4)  # 15
        for c in combos:
            assert len(c) == 4

    def test_n_equals_m(self):
        sels = [_sel(f"m{i}") for i in range(3)]
        combos = enumerate_combinations(sels, n=3)
        assert len(combos) == 1  # the single full combination

    def test_n_one(self):
        sels = [_sel(f"m{i}") for i in range(5)]
        combos = enumerate_combinations(sels, n=1)
        assert len(combos) == 5

    def test_rejects_n_zero(self):
        with pytest.raises(ValueError, match="n must be"):
            enumerate_combinations([_sel("a"), _sel("b")], n=0)

    def test_rejects_n_too_large(self):
        with pytest.raises(ValueError, match="n must be"):
            enumerate_combinations([_sel("a"), _sel("b")], n=3)

    def test_rejects_n_above_max_legs(self):
        sels = [_sel(f"m{i}") for i in range(10)]
        with pytest.raises(ValueError, match=f"max legs = {MAX_LEGS_PER_TICKET}"):
            enumerate_combinations(sels, n=9)

    def test_no_duplicate_combinations(self):
        sels = [_sel(f"m{i}") for i in range(5)]
        combos = enumerate_combinations(sels, n=3)
        # All combinations should be unique
        match_id_sets = [tuple(s.match_id for s in c) for c in combos]
        assert len(set(match_id_sets)) == len(match_id_sets)


class TestEvaluateTicket:
    def test_hit_prob_is_product(self):
        legs = (
            _sel("a", prob=0.6, odds=2.0),
            _sel("b", prob=0.5, odds=2.5),
        )
        t = evaluate_ticket(legs, bankroll=1000)
        assert t.hit_probability == pytest.approx(0.30)

    def test_combined_odds_is_product(self):
        legs = (
            _sel("a", prob=0.5, odds=2.0),
            _sel("b", prob=0.5, odds=3.0),
        )
        t = evaluate_ticket(legs, bankroll=1000)
        assert t.combined_odds == pytest.approx(6.0)

    def test_ev_formula(self):
        # p=0.4, odds=3.0 → EV = 3.0*0.4 - 1 = 0.20
        legs = (_sel("a", prob=0.4, odds=3.0),)
        t = evaluate_ticket(legs, bankroll=1000)
        assert t.ev_per_unit == pytest.approx(0.20)

    def test_negative_ev_yields_zero_stake(self):
        # p=0.3, odds=2.0 → EV = 0.6 - 1 = -0.4
        legs = (_sel("a", prob=0.3, odds=2.0),)
        t = evaluate_ticket(legs, bankroll=1000)
        assert t.ev_per_unit == pytest.approx(-0.4)
        assert t.stake == 0.0
        assert t.raw_kelly_stake == 0.0
        assert t.expected_return == 0.0

    def test_quantization_floor(self):
        # Force a small positive EV → small Kelly → quantize to 0 or unit
        legs = (_sel("a", prob=0.55, odds=2.0),)  # EV = 0.10
        t = evaluate_ticket(legs, bankroll=100, kelly_fraction=0.25)
        # raw_kelly_stake will be some odd amount; quantized to ¥2 multiple
        assert t.stake % STAKE_UNIT_CNY == 0
        assert t.stake <= t.raw_kelly_stake or t.stake == 0

    def test_empty_legs_raises(self):
        with pytest.raises(ValueError, match="at least 1 leg"):
            evaluate_ticket(tuple(), bankroll=1000)


class TestRecommendPool:
    def test_basic_workflow(self):
        # 4 matches, all +EV; n=2
        sels = [
            _sel(f"m{i}", prob=0.55, odds=2.0) for i in range(4)
        ]
        rec = recommend_pool(sels, n=2, bankroll=10000)
        assert rec.m == 4
        assert rec.n == 2
        assert rec.n_combinations == comb(4, 2)  # 6
        assert len(rec.tickets) == 6
        # All +EV → all selected
        assert len(rec.selected_tickets) > 0
        assert rec.total_stake > 0

    def test_ev_descending_sort(self):
        # Mix high-EV and low-EV legs
        sels = [
            _sel("a", prob=0.7, odds=2.0),  # high EV
            _sel("b", prob=0.5, odds=2.5),  # +EV
            _sel("c", prob=0.4, odds=2.5),  # +EV (smaller)
        ]
        rec = recommend_pool(sels, n=2, bankroll=1000)
        evs = [t.ev_per_unit for t in rec.tickets]
        assert evs == sorted(evs, reverse=True)

    def test_negative_ev_skipped_from_selected(self):
        # All legs are -EV
        sels = [_sel(f"m{i}", prob=0.3, odds=2.0) for i in range(3)]
        rec = recommend_pool(sels, n=2, bankroll=1000)
        assert len(rec.selected_tickets) == 0
        assert rec.total_stake == 0.0
        # Still report all combinations
        assert rec.n_combinations == comb(3, 2)
        assert len(rec.tickets) == comb(3, 2)

    def test_max_total_budget_rescales(self):
        # 4 strong-EV legs, n=2 → 6 tickets each wanting a lot of stake
        sels = [_sel(f"m{i}", prob=0.7, odds=2.0) for i in range(4)]
        rec = recommend_pool(sels, n=2, bankroll=100000,
                              max_total_budget=20)
        assert rec.total_stake <= 20

    def test_all_stakes_quantized(self):
        sels = [_sel(f"m{i}", prob=0.55, odds=2.0) for i in range(5)]
        rec = recommend_pool(sels, n=2, bankroll=10000)
        for t in rec.tickets:
            assert t.stake % STAKE_UNIT_CNY == 0

    def test_expected_return_consistent(self):
        sels = [_sel(f"m{i}", prob=0.6, odds=2.0) for i in range(4)]
        rec = recommend_pool(sels, n=2, bankroll=10000)
        for t in rec.tickets:
            assert t.expected_return == pytest.approx(t.stake * t.ev_per_unit)

    def test_handicap_legs_work_in_pool(self):
        # Mix 1x2 and handicap legs in the same pool
        sels = [
            _sel("a", prob=0.55, odds=2.0, market="1x2"),
            _sel("b", prob=0.55, odds=1.95, market="handicap_1x2"),
            _sel("c", prob=0.55, odds=2.10, market="1x2"),
        ]
        rec = recommend_pool(sels, n=2, bankroll=10000)
        # Should produce C(3,2)=3 tickets, no special-casing required
        assert rec.n_combinations == 3
        # Mixed-market combinations valid
        for t in rec.tickets:
            market_types = {leg.market_type for leg in t.legs}
            # We don't enforce same-market combos; mixed parlay is allowed
            assert len(market_types) >= 1

    def test_pool_ticket_n_legs_property(self):
        sels = [_sel(f"m{i}", prob=0.55, odds=2.0) for i in range(3)]
        rec = recommend_pool(sels, n=2, bankroll=1000)
        for t in rec.tickets:
            assert t.n_legs == 2
            assert len(t.match_ids) == 2
            # match_ids are tuples, hashable
            hash(t.match_ids)
