from __future__ import annotations

from math import isclose

from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.market_resolver import (
    resolve_1x2,
    resolve_asian_handicap,
    resolve_cn_handicap_1x2,
)


def _simple_grid() -> ScoreProbabilityGrid:
    return ScoreProbabilityGrid(max_goals=1, grid=[[0.1, 0.2], [0.3, 0.4]])


def test_1x2_probabilities_come_from_score_grid() -> None:
    probabilities = resolve_1x2(_simple_grid())

    assert probabilities.home_win == 0.3
    assert probabilities.draw == 0.5
    assert probabilities.away_win == 0.2


def test_cn_handicap_minus_one() -> None:
    probabilities = resolve_cn_handicap_1x2(_simple_grid(), handicap=-1)

    assert probabilities.handicap_home_win == 0.0
    assert probabilities.handicap_draw == 0.3
    assert isclose(probabilities.handicap_away_win, 0.7)


def test_cn_handicap_plus_one() -> None:
    probabilities = resolve_cn_handicap_1x2(_simple_grid(), handicap=1)

    assert probabilities.handicap_home_win == 0.8
    assert probabilities.handicap_draw == 0.2
    assert probabilities.handicap_away_win == 0.0


def test_asian_handicap_integer_line() -> None:
    probabilities = resolve_asian_handicap(_simple_grid(), line=0.0)

    assert probabilities.full_win_prob == 0.3
    assert probabilities.push_prob == 0.5
    assert probabilities.full_loss_prob == 0.2


def test_asian_handicap_half_line() -> None:
    probabilities = resolve_asian_handicap(_simple_grid(), line=-0.5)

    assert probabilities.full_win_prob == 0.3
    assert probabilities.push_prob == 0.0
    assert isclose(probabilities.full_loss_prob, 0.7)


def test_asian_handicap_quarter_line_minus_point_two_five() -> None:
    probabilities = resolve_asian_handicap(_simple_grid(), line=-0.25)

    assert probabilities.full_win_prob == 0.3
    assert probabilities.half_loss_prob == 0.5
    assert probabilities.full_loss_prob == 0.2


def test_asian_handicap_quarter_line_minus_point_seven_five() -> None:
    probabilities = resolve_asian_handicap(_simple_grid(), line=-0.75)

    assert probabilities.full_win_prob == 0.0
    assert probabilities.half_win_prob == 0.3
    assert isclose(probabilities.full_loss_prob, 0.7)


def test_asian_handicap_probabilities_sum_to_one() -> None:
    probabilities = resolve_asian_handicap(_simple_grid(), line=0.25)
    total = (
        probabilities.full_win_prob
        + probabilities.half_win_prob
        + probabilities.push_prob
        + probabilities.half_loss_prob
        + probabilities.full_loss_prob
    )

    assert isclose(total, 1.0)
