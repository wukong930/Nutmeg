"""Unit tests for nutmeg-score-ev (correct-score EV).

Network-free: the API I/O (fetch_odds) is separated from the pure math, so these
exercise parsing / line-shopping / EV without hitting API-Football.
"""
from __future__ import annotations

import numpy as np

from nutmeg.v4.cli.score_ev import (
    best_odds,
    composite_overround,
    consensus_1x2_devig,
    consensus_over_devig,
    correct_score_books,
    ev_flags,
    model_grid,
    parse_scoreline,
    score_ev_rows,
    sharp_1x2_devig,
    sharp_over_devig,
)
from nutmeg.v4.model.market_handicap import DEFAULT_RHO


def _blob_with_pinnacle():
    """Pinnacle (1X2 + O/U only — no correct-score, like the real feed) alongside a
    soft book that quotes 1X2 + correct-score. Pinnacle's de-vig differs clearly
    from the soft book / consensus so the prior choice is observable."""
    return [{"bookmakers": [
        {"name": "Pinnacle", "bets": [
            {"name": "Match Winner", "values": [
                {"value": "Home", "odd": "1.50"},
                {"value": "Draw", "odd": "4.00"},
                {"value": "Away", "odd": "6.00"}]},
            {"name": "Goals Over/Under", "values": [
                {"value": "Over 2.5", "odd": "1.95"},
                {"value": "Under 2.5", "odd": "1.85"}]},
        ]},
        {"name": "BookA", "bets": [
            {"name": "Match Winner", "values": [
                {"value": "Home", "odd": "1.20"},
                {"value": "Draw", "odd": "6.00"},
                {"value": "Away", "odd": "12.00"}]},
            {"name": "Correct Score", "values": [
                {"value": "1:0", "odd": "7.0"},
                {"value": "2:1", "odd": "50.0"}]},   # generous → +EV flag
        ]},
    ]}]


def _full_blob():
    """A fixture's /odds blob: 1X2 + O/U (for the prior) + correct-score, with a
    deliberately generous 2:1 price (→ +EV) and a junk 1xBet line (→ excluded)."""
    return [{"bookmakers": [
        {"name": "BookA", "bets": [
            {"name": "Match Winner", "values": [
                {"value": "Home", "odd": "1.20"},
                {"value": "Draw", "odd": "6.00"},
                {"value": "Away", "odd": "12.00"}]},
            {"name": "Goals Over/Under", "values": [
                {"value": "Over 2.5", "odd": "1.90"},
                {"value": "Under 2.5", "odd": "1.90"}]},
            {"name": "Correct Score", "values": [
                {"value": "1:0", "odd": "7.0"}, {"value": "2:0", "odd": "7.0"},
                {"value": "2:1", "odd": "50.0"},     # generous → +EV flag
                {"value": "4:4", "odd": "300.0"}]},   # over max_odds → dropped
        ]},
        {"name": "1xBet", "bets": [
            {"name": "Correct Score", "values": [{"value": "3:3", "odd": "500.0"}]},
        ]},
    ]}]


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


def test_consensus_1x2_devig():
    p = consensus_1x2_devig(_full_blob())
    assert p is not None and abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1] > p[2]                 # home fav, away longest
    assert consensus_1x2_devig([]) is None


def test_consensus_over_devig():
    # Over/Under both 1.90 → de-vig P(over) = 0.5
    assert abs(consensus_over_devig(_full_blob(), 2.5) - 0.5) < 1e-9
    assert consensus_over_devig(_full_blob(), 3.5) is None  # line not quoted


def test_sharp_1x2_devig_prefers_pinnacle():
    # Pinnacle present → use ITS de-vig, not the all-book consensus.
    p, src = sharp_1x2_devig(_blob_with_pinnacle())
    assert src == "Pinnacle"
    # Pinnacle 1.50/4.00/6.00 de-vig: home ≈ 0.615, distinct from consensus ≈ 0.69.
    assert abs(p[0] - 0.615) < 0.01
    assert p != consensus_1x2_devig(_blob_with_pinnacle())


def test_sharp_1x2_devig_falls_back_to_consensus():
    # No Pinnacle in _full_blob → consensus, equal to consensus_1x2_devig.
    p, src = sharp_1x2_devig(_full_blob())
    assert src == "consensus"
    assert p == consensus_1x2_devig(_full_blob())
    assert sharp_1x2_devig([]) == (None, "none")


def test_sharp_over_devig_prefers_pinnacle():
    # Pinnacle O/U 1.95/1.85 → P(over) < 0.5; consensus path absent here.
    pov = sharp_over_devig(_blob_with_pinnacle(), 2.5)
    assert pov is not None and pov < 0.5
    assert sharp_over_devig(_full_blob(), 2.5) == consensus_over_devig(_full_blob(), 2.5)


def test_ev_flags_records_prior_src():
    # Pinnacle present → flags tagged prior_src='Pinnacle'; model_p uses Pinnacle.
    pin_flags = ev_flags(_blob_with_pinnacle(), min_ev=0.05, rho=DEFAULT_RHO)
    assert pin_flags and all(f["prior_src"] == "Pinnacle" for f in pin_flags)
    # No Pinnacle → prior_src='consensus'.
    con_flags = ev_flags(_full_blob(), min_ev=0.05, rho=DEFAULT_RHO)
    assert con_flags and all(f["prior_src"] == "consensus" for f in con_flags)


def test_ev_flags_core():
    flags = ev_flags(_full_blob(), min_ev=0.05, max_odds=80.0, rho=DEFAULT_RHO)
    assert isinstance(flags, list) and flags
    sl = {(f["home"], f["away"]) for f in flags}
    assert (2, 1) in sl                         # generous 2:1 → flagged
    assert (3, 3) not in sl                      # 1xBet junk → excluded
    assert (4, 4) not in sl                      # 300.0 > max_odds → dropped
    assert all(f["ev"] >= 0.05 for f in flags)   # threshold honoured
    assert all(f["book"] != "1xBet" for f in flags)


def test_ev_flags_none_without_market():
    # No correct-score market → None
    blob = [{"bookmakers": [{"name": "B", "bets": [
        {"name": "Match Winner", "values": [{"value": "Home", "odd": "1.5"}]}]}]}]
    assert ev_flags(blob, rho=DEFAULT_RHO) is None
