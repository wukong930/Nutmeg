from __future__ import annotations

import pytest

from nutmeg.domain.settlement import (
    AsianHandicapSettlement,
    HandicapOneXTwoOutcome,
    OneXTwoOutcome,
)
from nutmeg.market_resolver import (
    correct_score_option_key,
    settle_1x2,
    settle_asian_1x2,
    settle_asian_handicap,
    settle_cn_handicap_1x2,
    settle_correct_score,
    settle_european_handicap_1x2,
)


def test_settle_1x2_home_draw_away() -> None:
    assert settle_1x2(2, 1) is OneXTwoOutcome.HOME_WIN
    assert settle_1x2(1, 1) is OneXTwoOutcome.DRAW
    assert settle_1x2(0, 1) is OneXTwoOutcome.AWAY_WIN


def test_settle_asian_1x2_is_provider_normalized_three_way_market() -> None:
    assert settle_asian_1x2(3, 0) is OneXTwoOutcome.HOME_WIN
    assert settle_asian_1x2(2, 2) is OneXTwoOutcome.DRAW
    assert settle_asian_1x2(1, 2) is OneXTwoOutcome.AWAY_WIN


def test_negative_goal_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="goals must be non-negative"):
        settle_1x2(-1, 0)


def test_cn_handicap_1x2_examples_from_document() -> None:
    assert (
        settle_cn_handicap_1x2(2, 0, handicap=-1)
        is HandicapOneXTwoOutcome.HANDICAP_HOME_WIN
    )
    assert (
        settle_cn_handicap_1x2(1, 0, handicap=-1) is HandicapOneXTwoOutcome.HANDICAP_DRAW
    )
    assert (
        settle_cn_handicap_1x2(2, 1, handicap=-1) is HandicapOneXTwoOutcome.HANDICAP_DRAW
    )
    assert (
        settle_cn_handicap_1x2(0, 0, handicap=-1)
        is HandicapOneXTwoOutcome.HANDICAP_AWAY_WIN
    )
    assert (
        settle_cn_handicap_1x2(1, 1, handicap=-1)
        is HandicapOneXTwoOutcome.HANDICAP_AWAY_WIN
    )


def test_european_handicap_1x2_uses_three_way_handicap_settlement() -> None:
    assert (
        settle_european_handicap_1x2(3, 1, handicap=-1)
        is HandicapOneXTwoOutcome.HANDICAP_HOME_WIN
    )
    assert (
        settle_european_handicap_1x2(2, 1, handicap=-1)
        is HandicapOneXTwoOutcome.HANDICAP_DRAW
    )
    assert (
        settle_european_handicap_1x2(1, 1, handicap=-1)
        is HandicapOneXTwoOutcome.HANDICAP_AWAY_WIN
    )


def test_asian_handicap_integer_line_settlements() -> None:
    assert settle_asian_handicap(2, 0, line=-1) is AsianHandicapSettlement.FULL_WIN
    assert settle_asian_handicap(1, 0, line=-1) is AsianHandicapSettlement.PUSH
    assert settle_asian_handicap(0, 0, line=-1) is AsianHandicapSettlement.FULL_LOSS


def test_asian_handicap_half_line_has_no_push() -> None:
    assert settle_asian_handicap(1, 0, line=-0.5) is AsianHandicapSettlement.FULL_WIN
    assert settle_asian_handicap(0, 0, line=-0.5) is AsianHandicapSettlement.FULL_LOSS


def test_asian_handicap_quarter_line_settlements_cover_all_half_results() -> None:
    assert settle_asian_handicap(1, 0, line=-0.75) is AsianHandicapSettlement.HALF_WIN
    assert settle_asian_handicap(0, 0, line=-0.25) is AsianHandicapSettlement.HALF_LOSS
    assert settle_asian_handicap(0, 0, line=0.25) is AsianHandicapSettlement.HALF_WIN
    assert settle_asian_handicap(0, 1, line=0.75) is AsianHandicapSettlement.HALF_LOSS


def test_asian_handicap_away_side_uses_away_margin() -> None:
    assert (
        settle_asian_handicap(0, 1, line=-0.5, side="away")
        is AsianHandicapSettlement.FULL_WIN
    )
    assert (
        settle_asian_handicap(1, 0, line=-0.5, side="away")
        is AsianHandicapSettlement.FULL_LOSS
    )


def test_asian_handicap_rejects_invalid_line_and_side() -> None:
    with pytest.raises(ValueError, match="multiple of 0.25"):
        settle_asian_handicap(1, 1, line=0.125)
    with pytest.raises(ValueError, match="side must be"):
        settle_asian_handicap(1, 1, line=0, side="both")


def test_correct_score_exact_settlement() -> None:
    assert settle_correct_score(2, 1, selected_home_goals=2, selected_away_goals=1)
    assert not settle_correct_score(2, 1, selected_home_goals=1, selected_away_goals=1)


def test_correct_score_option_key_maps_listed_and_other_scores() -> None:
    listed = {(1, 0), (1, 1), (0, 1)}

    assert correct_score_option_key(1, 0, listed_options=listed) == "1-0"
    assert correct_score_option_key(4, 2, listed_options=listed) == "home_other"
    assert correct_score_option_key(4, 4, listed_options=listed) == "draw_other"
    assert correct_score_option_key(2, 4, listed_options=listed) == "away_other"
