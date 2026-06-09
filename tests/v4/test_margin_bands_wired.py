"""净胜球分组 wired into the backend: SinglePrediction (market mode) + the
reverse-calc (MarketHandicapResponse) path. READOUT, not a signal."""
from __future__ import annotations

from nutmeg.v4.api.routes import (
    _market_margin_bands,
    _mk_margin_bands,
    _pinnacle_devig_1x2,
    _row_to_market_prediction,
)
from nutmeg.v4.model.market_handicap import implied_margin_bands

_ROW = {
    "home_team": "A", "away_team": "B", "league": "WC", "date": "2026-06-11",
    "kickoff_utc": None, "psc_home": 1.95, "psc_draw": 3.30, "psc_away": 4.20,
    "psc_over25": 1.90, "psc_under25": 1.95, "ou_line": 2.5,
    "asian_handicap": None, "handicap_home": -1,
}


class TestImpliedMarginBands:
    def test_sums_to_one_and_capped(self):
        bands = implied_margin_bands(0.49, 0.29, 0.23, 0.53, ou_line=2.25, top=3)
        assert abs(sum(b["p"] for b in bands) - 1.0) < 1e-9
        assert all(len(b["scores"]) <= 3 for b in bands)

    def test_tail_4_covers_jc_handicaps(self):
        # tail=4 ⇒ margins ±1,2,3 are separate, so 让球 lines −3..+3 classify exactly
        bands = implied_margin_bands(0.80, 0.13, 0.07, 0.55, ou_line=3.0)
        margins = {b["margin"] for b in bands}
        assert {-1, 0, 1, 2, 3}.issubset(margins)


class TestMkMarginBands:
    def test_to_schema(self):
        bands = _mk_margin_bands(implied_margin_bands(0.5, 0.3, 0.2, None))
        assert bands and abs(sum(b.p for b in bands) - 1.0) < 1e-9
        b0 = bands[0]
        assert isinstance(b0.margin, int) and b0.scores
        assert b0.scores[0].home >= 0 and b0.scores[0].away >= 0


class TestFlowsToPrediction:
    def test_market_row_carries_bands(self):
        mp = _row_to_market_prediction(_ROW)
        assert mp is not None
        assert mp.margin_bands
        assert abs(sum(b.p for b in mp.margin_bands) - 1.0) < 1e-9

    def test_market_margin_bands_helper(self):
        fair = _pinnacle_devig_1x2(1.95, 3.30, 4.20)
        bands = _market_margin_bands(fair, _ROW)
        assert bands and abs(sum(b.p for b in bands) - 1.0) < 1e-9
