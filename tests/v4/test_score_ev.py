"""Unit tests for nutmeg-score-ev (correct-score EV).

Network-free: the API I/O (fetch_odds) is separated from the pure math, so these
exercise parsing / line-shopping / EV without hitting API-Football.
"""
from __future__ import annotations

import numpy as np

from nutmeg.v4.cli.score_ev import (
    best_odds,
    composite_overround,
    correct_score_books,
    model_grid,
    parse_scoreline,
    score_ev_rows,
)


def _odds_blob():
    # Shape of API-Football /odds response (list → bookmakers → bets → values).
    return [{
        "bookmakers": [
            {"name": "BookA", "bets": [
                {"name": "Match Winner", "values": [{"value": "Home", "odd": "1.4"}]},
                {"name": "Exact Score", "values": [
                    {"value": "1:0", "odd": "5.0"},
                    {"value": "2:0", "odd": "7.0"},
                    {"value": "Other", "odd": "3.0"},  # must be skipped
                ]},
            ]},
            {"name": "BookB", "bets": [
                {"name": "Correct Score", "values": [
                    {"value": "1-0", "odd": "6.0"},
                    {"value": "2:0", "odd": "6.5"},
                    {"value": "0:1", "odd": "15.0"},
                ]},
            ]},
        ],
    }]


def test_parse_scoreline():
    assert parse_scoreline("2:1") == (2, 1)
    assert parse_scoreline("2-1") == (2, 1)
    assert parse_scoreline(" 0 : 3 ") == (0, 3)
    assert parse_scoreline("Other") is None
    assert parse_scoreline("Any Other Score") is None
    assert parse_scoreline(None) is None


def test_correct_score_books_only_score_market():
    books = correct_score_books(_odds_blob())
    assert set(books) == {"BookA", "BookB"}
    assert books["BookA"] == {(1, 0): 5.0, (2, 0): 7.0}   # Match Winner ignored
    assert books["BookB"] == {(1, 0): 6.0, (2, 0): 6.5, (0, 1): 15.0}


def test_best_odds_line_shops_highest_per_scoreline():
    best = best_odds(correct_score_books(_odds_blob()), max_goals=8)
    assert best[(1, 0)] == (6.0, "BookB")   # B's 6.0 beats A's 5.0
    assert best[(2, 0)] == (7.0, "BookA")   # A's 7.0 beats B's 6.5
    assert best[(0, 1)] == (15.0, "BookB")


def test_best_odds_drops_out_of_grid_scores():
    books = {"X": {(1, 0): 5.0, (9, 9): 2000.0}}
    best = best_odds(books, max_goals=8)
    assert (1, 0) in best and (9, 9) not in best


def test_score_ev_rows_math_and_sort():
    books = correct_score_books(_odds_blob())
    grid = np.zeros((9, 9))
    grid[1, 0], grid[2, 0], grid[0, 1] = 0.20, 0.10, 0.05
    rows = score_ev_rows(grid, books, max_goals=8)
    ev = {(r.home, r.away): round(r.ev, 4) for r in rows}
    assert ev[(1, 0)] == 0.2     # 0.20 * 6.0 - 1
    assert ev[(2, 0)] == -0.3    # 0.10 * 7.0 - 1
    assert ev[(0, 1)] == -0.25   # 0.05 * 15.0 - 1
    assert (rows[0].home, rows[0].away) == (1, 0)  # sorted +EV first


def test_composite_overround():
    books = correct_score_books(_odds_blob())
    assert abs(composite_overround(books) - (1 / 6 + 1 / 7 + 1 / 15)) < 1e-9


def test_model_grid_smoke():
    # Slovenia vs Cyprus Pinnacle lines → valid distribution, home favorite.
    grid, (lh, la), p, pov = model_grid((1.386, 4.7, 8.12), (2.5, 2.0, 1.84),
                                        rho=-0.10)
    assert abs(grid.sum() - 1.0) < 1e-6
    assert lh > la           # home is the favorite
    assert pov is not None    # O/U supplied → P(over) anchored
