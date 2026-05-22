from __future__ import annotations

from math import isclose

from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.market_resolver import score_grid_to_market_probabilities


def test_score_grid_to_market_probabilities_converts_requested_markets() -> None:
    score_grid = ScoreProbabilityGrid(
        max_goals=2,
        grid=[
            [0.05, 0.10, 0.05],
            [0.10, 0.20, 0.10],
            [0.15, 0.15, 0.10],
        ],
    )

    payload = score_grid_to_market_probabilities(
        score_grid,
        cn_handicaps=(-1, 1),
        asian_handicap_lines=(-0.25, -0.75),
        european_handicaps=(-1,),
        correct_score_top_n=3,
    )

    assert payload["1x2"] == {"home_win": 0.4, "draw": 0.35, "away_win": 0.25}
    assert payload["cn_handicap_1x2:-1"] == {
        "handicap_home_win": 0.15,
        "handicap_draw": 0.25,
        "handicap_away_win": 0.6,
    }
    assert payload["european_handicap_1x2:-1"] == payload["cn_handicap_1x2:-1"]

    asian_minus_quarter = payload["asian_handicap:home:-0.25"]
    assert isinstance(asian_minus_quarter, dict)
    assert isclose(asian_minus_quarter["full_win"], 0.4)
    assert isclose(asian_minus_quarter["half_loss"], 0.35)
    assert isclose(asian_minus_quarter["full_loss"], 0.25)

    correct_scores = payload["correct_score_top_n"]
    assert isinstance(correct_scores, list)
    assert len(correct_scores) == 3
    assert correct_scores[0]["home_goals"] == 1
    assert correct_scores[0]["away_goals"] == 1
    assert correct_scores[0]["probability"] == 0.2
