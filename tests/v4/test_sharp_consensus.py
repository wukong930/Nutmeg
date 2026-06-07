"""V14 — sharp-book consensus + favorite-flip guard (Pinnacle+Betfair+SBOBET).

Guards the read-only cross-check: de-vig each sharp book in the SAME /odds
envelope, build a consensus, and flag when Pinnacle's favourite disagrees with
the other sharps (a likely-stale Pinnacle line — same idea as the Polymarket
detector's favorite-flip guard).
"""
from __future__ import annotations

from nutmeg.v4.model.sharp_consensus import (
    consensus,
    devig_1x2,
    ev_1x2,
    per_book_fair,
)


def _env(books):
    """Minimal /odds envelope. books = {bookmaker_id: (oH, oD, oA)}."""
    return {
        "fixture": {"id": 1},
        "bookmakers": [
            {"id": bid, "name": str(bid), "bets": [
                {"id": 1, "name": "Match Winner", "values": [
                    {"value": "Home", "odd": str(o[0])},
                    {"value": "Draw", "odd": str(o[1])},
                    {"value": "Away", "odd": str(o[2])},
                ]},
            ]}
            for bid, o in books.items()
        ],
    }


class TestDevig:
    def test_sums_to_one(self):
        p = devig_1x2({"H": 2.0, "D": 3.4, "A": 3.6})
        assert abs(sum(p.values()) - 1.0) < 1e-12

    def test_favorite_has_highest_p(self):
        p = devig_1x2({"H": 1.5, "D": 4.0, "A": 6.0})
        assert p["H"] > p["D"] and p["H"] > p["A"]


class TestPerBookAndConsensus:
    def test_extracts_present_sharps_only(self):
        # Pinnacle(4) + Betfair(3) present; SBOBET(5) absent
        env = _env({4: (2.0, 3.4, 3.6), 3: (2.05, 3.3, 3.55)})
        by = per_book_fair(env)
        assert set(by) == {"pinnacle", "betfair"}

    def test_consensus_is_unit_sum_mean(self):
        env = _env({4: (2.0, 4.0, 4.0), 3: (4.0, 4.0, 2.0)})
        c = consensus(per_book_fair(env))
        assert c.n_books == 2
        assert abs(sum(c.consensus.values()) - 1.0) < 1e-12
        # symmetric inputs → consensus H == A
        assert abs(c.consensus["H"] - c.consensus["A"]) < 1e-9

    def test_soft_book_is_not_a_sharp(self):
        env = _env({8: (2.0, 3.4, 3.6)})  # Bet365 only — soft, not in SHARP_BOOKS
        c = consensus(per_book_fair(env))
        assert c.consensus is None and c.n_books == 0


class TestFlipGuard:
    def test_flip_fires_when_pinnacle_disagrees_on_favorite(self):
        # Pinnacle: HOME favourite; Betfair+SBOBET: AWAY favourite → FLIP
        env = _env({4: (1.5, 4.0, 6.0), 3: (6.0, 4.0, 1.5), 5: (5.5, 4.0, 1.6)})
        c = consensus(per_book_fair(env))
        assert c.pinnacle_flip is True
        assert c.argmax_agree is False

    def test_no_flip_when_sharps_agree(self):
        env = _env({4: (1.5, 4.0, 6.0), 3: (1.55, 3.9, 5.8), 5: (1.52, 4.1, 6.1)})
        c = consensus(per_book_fair(env))
        assert c.pinnacle_flip is False
        assert c.argmax_agree is True
        assert c.max_spread < 0.05   # the three sharps are tight

    def test_no_flip_with_only_pinnacle(self):
        env = _env({4: (1.5, 4.0, 6.0)})
        c = consensus(per_book_fair(env))
        assert c.pinnacle_flip is False   # can't flip against nothing


class TestEv:
    def test_ev_only_for_filled_sp(self):
        fair = {"H": 0.5, "D": 0.3, "A": 0.2}
        ev = ev_1x2(fair, {"H": 2.2, "A": 1.0})   # D absent, A sentinel ≤ 1
        assert set(ev) == {"H"}
        assert abs(ev["H"] - (0.5 * 2.2 - 1)) < 1e-12
