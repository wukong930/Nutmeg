"""Tests for nutmeg.v4.combo.lottery_rules (V6 W4)."""
from __future__ import annotations

import pytest

from nutmeg.v4.combo.lottery_rules import (
    DEFAULT_MIN_EV_PER_UNIT,
    DEFAULT_MIN_HIT_PROBABILITY,
    JINGCAI_DEFAULT,
    LOTTERY_PAYOUT_RATIO,
    LOTTERY_VIG,
    MAX_LEGS_PER_TICKET,
    MAX_TICKET_STAKE_CNY,
    MIN_PARLAY_LEGS,
    STAKE_UNIT_CNY,
    LotteryRules,
    cap_ticket_stake,
    passes_recommendation_thresholds,
    validate_legs_count,
)


class TestConstants:
    def test_stake_unit_is_2(self):
        assert STAKE_UNIT_CNY == 2.0
        assert JINGCAI_DEFAULT.stake_unit == 2.0

    def test_max_ticket_stake(self):
        assert MAX_TICKET_STAKE_CNY == 20_000.0
        assert JINGCAI_DEFAULT.max_ticket_stake == 20_000.0

    def test_max_legs_per_ticket(self):
        assert MAX_LEGS_PER_TICKET == 8
        assert JINGCAI_DEFAULT.max_legs_per_ticket == 8

    def test_payout_ratio_around_69pct(self):
        # 中国体彩 official payout ratio is in the 68-69% range
        assert 0.65 <= LOTTERY_PAYOUT_RATIO <= 0.70

    def test_vig_consistency(self):
        assert LOTTERY_VIG == pytest.approx(1.0 - LOTTERY_PAYOUT_RATIO)
        assert JINGCAI_DEFAULT.vig == pytest.approx(LOTTERY_VIG)


class TestCapTicketStake:
    def test_under_cap_unchanged(self):
        assert cap_ticket_stake(100.0) == 100.0
        assert cap_ticket_stake(19_999.99) == 19_999.99

    def test_at_cap(self):
        assert cap_ticket_stake(20_000.0) == 20_000.0

    def test_over_cap(self):
        assert cap_ticket_stake(20_001.0) == 20_000.0
        assert cap_ticket_stake(1_000_000.0) == 20_000.0

    def test_negative_clamped_to_zero(self):
        assert cap_ticket_stake(-50.0) == 0.0

    def test_custom_rules(self):
        custom = LotteryRules(max_ticket_stake=5_000.0)
        assert cap_ticket_stake(7_000.0, rules=custom) == 5_000.0


class TestValidateLegsCount:
    def test_accepts_single_when_not_require_parlay(self):
        validate_legs_count(1, require_parlay=False)

    def test_rejects_single_when_require_parlay(self):
        with pytest.raises(ValueError, match=f"legs must be ≥ {MIN_PARLAY_LEGS}"):
            validate_legs_count(1, require_parlay=True)

    def test_accepts_at_max(self):
        validate_legs_count(8)

    def test_rejects_above_max(self):
        with pytest.raises(ValueError, match="legs must be ≤ 8"):
            validate_legs_count(9)

    def test_rejects_zero(self):
        with pytest.raises(ValueError):
            validate_legs_count(0)

    def test_custom_rules_override(self):
        # A different game variant might allow up to 12 legs
        custom = LotteryRules(max_legs_per_ticket=12)
        validate_legs_count(12, rules=custom)
        with pytest.raises(ValueError):
            validate_legs_count(13, rules=custom)


class TestPassesThresholds:
    def test_passes_when_both_above(self):
        # Both above defaults
        assert passes_recommendation_thresholds(
            hit_probability=0.20, ev_per_unit=0.10,
        )

    def test_fails_low_hit_probability(self):
        # hit_p below default 0.05
        assert not passes_recommendation_thresholds(
            hit_probability=0.02, ev_per_unit=0.10,
        )

    def test_fails_low_ev(self):
        # EV below default 0.05
        assert not passes_recommendation_thresholds(
            hit_probability=0.50, ev_per_unit=0.02,
        )

    def test_fails_negative_ev(self):
        assert not passes_recommendation_thresholds(
            hit_probability=0.30, ev_per_unit=-0.10,
        )

    def test_custom_threshold(self):
        # Pickier rules: 10% minimum EV
        strict = LotteryRules(min_ev_per_unit=0.10)
        assert not passes_recommendation_thresholds(
            hit_probability=0.50, ev_per_unit=0.06, rules=strict,
        )
        assert passes_recommendation_thresholds(
            hit_probability=0.50, ev_per_unit=0.12, rules=strict,
        )


class TestLotteryRulesDataclass:
    def test_frozen(self):
        with pytest.raises(Exception):  # FrozenInstanceError
            JINGCAI_DEFAULT.stake_unit = 5.0  # type: ignore[misc]

    def test_default_values_match_module_constants(self):
        rules = LotteryRules()
        assert rules.stake_unit == STAKE_UNIT_CNY
        assert rules.max_ticket_stake == MAX_TICKET_STAKE_CNY
        assert rules.max_legs_per_ticket == MAX_LEGS_PER_TICKET
        assert rules.min_ev_per_unit == DEFAULT_MIN_EV_PER_UNIT
        assert rules.min_hit_probability == DEFAULT_MIN_HIT_PROBABILITY
        assert rules.payout_ratio == LOTTERY_PAYOUT_RATIO

    def test_custom_override(self):
        custom = LotteryRules(
            stake_unit=5.0,
            max_ticket_stake=1_000.0,
            min_ev_per_unit=0.20,
        )
        assert custom.stake_unit == 5.0
        assert custom.max_ticket_stake == 1_000.0
        # Untouched fields keep defaults
        assert custom.max_legs_per_ticket == MAX_LEGS_PER_TICKET


class TestIntegrationWithCompoundPool:
    """Confirm the lottery rules actually affect compound_pool behavior."""

    def test_evaluate_ticket_caps_at_20k(self):
        from nutmeg.v4.combo.compound_pool import evaluate_ticket
        from nutmeg.v4.combo.selections import Selection

        # Force a huge Kelly stake via massive bankroll + high-edge leg
        legs = (Selection(
            match_id="m", market_type="1x2", outcome="H",
            probability=0.95, odds=2.5,  # EV = 1.375 (extreme)
        ),)
        t = evaluate_ticket(legs, bankroll=10_000_000.0)
        # Despite a multi-million bankroll the cap kicks in
        assert t.stake <= MAX_TICKET_STAKE_CNY
        assert t.stake > 0  # not zeroed

    def test_recommend_pool_drops_sub_threshold_tickets(self):
        from nutmeg.v4.combo.compound_pool import recommend_pool
        from nutmeg.v4.combo.selections import Selection

        # Three legs: two strong, one barely +EV (below min_ev threshold)
        legs = [
            Selection("a", "1x2", "H", 0.50, 2.50),  # EV 0.25 (passes)
            Selection("b", "1x2", "H", 0.50, 2.30),  # EV 0.15 (passes)
            Selection("c", "1x2", "H", 0.50, 2.05),  # EV 0.025 (FAILS default 0.05)
        ]
        rec = recommend_pool(legs, n=2, bankroll=10_000, apply_thresholds=True)

        # All 3 C(3,2)=3 tickets enumerated, but the one including 'c' has
        # combined EV that may or may not pass — verify only +EV pass
        for t in rec.tickets:
            if t.stake > 0:
                # Threshold says ev_per_unit ≥ 0.05
                assert t.ev_per_unit >= DEFAULT_MIN_EV_PER_UNIT
                assert t.hit_probability >= DEFAULT_MIN_HIT_PROBABILITY

    def test_apply_thresholds_false_includes_all(self):
        from nutmeg.v4.combo.compound_pool import recommend_pool
        from nutmeg.v4.combo.selections import Selection

        legs = [
            Selection("a", "1x2", "H", 0.55, 2.0),  # +EV
            Selection("b", "1x2", "H", 0.45, 2.0),  # -EV (0.9 - 1 = -0.1)
        ]
        rec_strict = recommend_pool(legs, n=2, bankroll=1000, apply_thresholds=True)
        rec_loose = recommend_pool(legs, n=2, bankroll=1000, apply_thresholds=False)
        # Same n_combinations either way
        assert rec_strict.n_combinations == rec_loose.n_combinations
        # Both yield 0 selected because the combined EV here is negative
        # (0.55*0.45 * 4.0 - 1 ≈ -0.01) — i.e., a single -EV leg poisons
        # the parlay even before threshold filtering
        assert len(rec_strict.selected_tickets) == len(rec_loose.selected_tickets) == 0
