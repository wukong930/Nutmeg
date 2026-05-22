from __future__ import annotations

from nutmeg.parlay import settle_parlay_atomic_bet


def test_parlay_atomic_settlement_marks_all_matching_legs_won() -> None:
    settlement = settle_parlay_atomic_bet(
        [
            {"fixture_id": "fix_a", "market_type": "1x2", "outcome": "home_win"},
            {
                "fixture_id": "fix_b",
                "market_type": "cn_handicap_1x2",
                "line": -1,
                "outcome": "handicap_away_win",
            },
        ],
        [
            {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0},
            {"fixture_id": "fix_b", "home_goals": 1, "away_goals": 1},
        ],
        stake=2,
        odds_product=3,
    )

    assert settlement.result_status == "won"
    assert settlement.gross_payout == 6
    assert settlement.profit_loss == 4
    assert all(leg.hit is True for leg in settlement.leg_results)


def test_parlay_atomic_settlement_marks_any_missed_leg_lost() -> None:
    settlement = settle_parlay_atomic_bet(
        [{"fixture_id": "fix_a", "market_type": "1x2", "outcome": "away_win"}],
        [{"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0}],
        stake=2,
        odds_product=2.5,
    )

    assert settlement.result_status == "lost"
    assert settlement.gross_payout == 0
    assert settlement.profit_loss == -2
    assert settlement.leg_results[0].actual_outcome == "home_win"


def test_parlay_atomic_settlement_keeps_missing_results_unresolved() -> None:
    settlement = settle_parlay_atomic_bet(
        [{"fixture_id": "fix_a", "market_type": "1x2", "outcome": "home_win"}],
        [],
        stake=2,
        odds_product=2,
    )

    assert settlement.result_status == "unresolved"
    assert settlement.is_settled is False
    assert settlement.unresolved_reasons == ["result_missing:fix_a"]
