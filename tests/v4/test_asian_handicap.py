"""V14 — international Asian Handicap (HALF-line, 2-way) for the 让球 prediction.

Real Pinnacle AH de-vig (primary) + DC-grid cover-prob (fallback). NOT the 竞彩
integer 3-way market. Validates the money-math: de-vig sums to 1, the −0.5 line
equals P(home win), the board is monotonic, and the real-vs-DC overlay tags work.
"""
from __future__ import annotations

import math

import pytest

from nutmeg.v4.data.odds_parser import extract_asian_handicap
from nutmeg.v4.model.dixon_coles import grid_to_1x2, score_grid
from nutmeg.v4.model.market_handicap import (
    DEFAULT_MAX_GOALS,
    DEFAULT_RHO,
    asian_handicap_board,
    dc_home_cover_prob,
    devig_asian_handicap_line,
    fit_lambdas,
)


def _devig_1x2(h, d, a):
    inv = [1.0 / h, 1.0 / d, 1.0 / a]
    s = sum(inv)
    return [x / s for x in inv]


class TestDevigAsianHandicapLine:
    def test_sums_to_one(self):
        ph, pa = devig_asian_handicap_line(2.31, 1.58)
        assert ph + pa == pytest.approx(1.0, abs=1e-12)

    def test_real_devig_value(self):
        # Home -0.5 = 2.31, Away -0.5 = 1.58 → P(home covers) ≈ 0.406
        ph, _ = devig_asian_handicap_line(2.31, 1.58)
        assert ph == pytest.approx(0.4062, abs=1e-3)

    @pytest.mark.parametrize("h,a", [(1.0, 2.0), (2.0, 1.0), (0.0, 2.0), (None, 2.0), ("x", 2.0)])
    def test_junk_returns_none(self, h, a):
        assert devig_asian_handicap_line(h, a) is None


class TestDcHomeCoverProb:
    GRID = score_grid(1.6, 1.0, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS)

    def test_minus_half_equals_home_win(self):
        # home -0.5 cover = home wins outright = 1X2 home
        ph_1x2, _, _ = grid_to_1x2(self.GRID)
        assert dc_home_cover_prob(self.GRID, -0.5) == pytest.approx(ph_1x2, abs=1e-12)

    def test_plus_half_equals_home_or_draw(self):
        # home +0.5 cover = home win OR draw = 1 − P(away win)
        ph, pd_, pa = grid_to_1x2(self.GRID)
        assert dc_home_cover_prob(self.GRID, 0.5) == pytest.approx(ph + pd_, abs=1e-12)

    def test_monotonic_increasing_in_line(self):
        vals = [dc_home_cover_prob(self.GRID, ln) for ln in (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)]
        assert all(a <= b + 1e-12 for a, b in zip(vals, vals[1:], strict=False))

    def test_away_cover_is_complement_at_same_line(self):
        # half-line has no push: P(home covers @ln) + P(away covers @ln) = 1,
        # where away covers iff (i−j)+ln < 0. (Compute away-cover directly.)
        import numpy as np
        n = self.GRID.shape[0]
        margin = np.arange(n)[:, None] - np.arange(n)[None, :]
        for ln in (-1.5, -0.5, 0.5, 1.5):
            p_away = float(self.GRID[(margin + ln) < 0.0].sum())
            assert dc_home_cover_prob(self.GRID, ln) + p_away == pytest.approx(1.0, abs=1e-12)


class TestAsianHandicapBoard:
    H, D, A = 2.36, 3.35, 3.15

    def test_dc_only_board_valid(self):
        t = _devig_1x2(self.H, self.D, self.A)
        board = asian_handicap_board(*t, real_board=None)
        assert [round(ln, 1) for ln, *_ in board] == [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]
        for _ln, ph, pa, src in board:
            assert ph + pa == pytest.approx(1.0, abs=1e-9)
            assert src == "dc"

    def test_minus_half_equals_1x2_home(self):
        # the -0.5 line P(home covers) must equal the de-vig 1X2 主胜 exactly
        t = _devig_1x2(self.H, self.D, self.A)
        lh, la = fit_lambdas(*t)
        ph_home = grid_to_1x2(score_grid(lh, la, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS))[0]
        board = {round(ln, 1): ph for ln, ph, _, _ in asian_handicap_board(*t)}
        assert board[-0.5] == pytest.approx(ph_home, abs=1e-9)

    def test_real_board_overlays_with_source_tag(self):
        # quote a real ±0.5 line → those become "mkt"; deep ±1.5/±2.5 stay "dc"
        t = _devig_1x2(self.H, self.D, self.A)
        real = {-0.5: {"home": 2.31, "away": 1.58}, 0.5: {"home": 1.36, "away": 2.96}}
        board = {round(ln, 1): (ph, src) for ln, ph, _, src in asian_handicap_board(*t, real_board=real)}
        assert board[-0.5][1] == "mkt"
        assert board[0.5][1] == "mkt"
        assert board[-1.5][1] == "dc" and board[2.5][1] == "dc"
        # the -0.5 mkt P matches the standalone de-vig
        assert board[-0.5][0] == pytest.approx(devig_asian_handicap_line(2.31, 1.58)[0], abs=1e-12)

    def test_real_quarter_and_level_lines_pass_through(self):
        # Pinnacle headlines 0 / ±0.25 for even matches — they MUST appear (the
        # "对不上" fix). Only half-lines were shown before; now every real line is.
        t = _devig_1x2(self.H, self.D, self.A)
        real = {0.0: {"home": 2.02, "away": 1.781}, -0.25: {"home": 1.95, "away": 1.85}}
        board = {round(ln, 2): (ph, src) for ln, ph, _, src in asian_handicap_board(*t, real_board=real)}
        assert board[0.0][1] == "mkt" and board[-0.25][1] == "mkt"
        # de-vig of the level line matches the standalone calc (1:1 with Pinnacle)
        assert board[0.0][0] == pytest.approx(devig_asian_handicap_line(2.02, 1.781)[0], abs=1e-12)
        # deep Polymarket lines (±1.5) still filled off the DC grid
        assert -1.5 in board and 1.5 in board


class TestExtractAsianHandicapRealPayload:
    """Parse the REAL cached Pinnacle payload — proves the data source carries
    the international half/quarter-line AH and we read it correctly."""

    def _envelope(self):
        # Find a cached Pinnacle payload whose AH board actually carries the ±0.5
        # half-lines this test validates. NOT just the first AH file: lopsided
        # matches (a heavy favourite) only quote one-sided lines (e.g. −3.0…−0.75,
        # no +0.5), so scan for a balanced one. Robust to whatever the odds cache
        # happens to hold.
        import glob
        import json
        for f in sorted(glob.glob("data/external/api_football/_odds/*.json")):
            d = json.load(open(f))
            resp = d if isinstance(d, list) else d.get("response", [])
            for r in resp:
                board = extract_asian_handicap(r)
                if board and -0.5 in board and 0.5 in board:
                    return r
        return None

    def test_extracts_half_and_quarter_lines(self):
        env = self._envelope()
        if env is None:
            pytest.skip("no cached payload with Pinnacle Asian Handicap")
        board = extract_asian_handicap(env)
        assert board is not None
        # every kept line is a complete 2-way pair
        for _ln, v in board.items():
            assert "home" in v and "away" in v and v["home"] > 1.0 and v["away"] > 1.0
        # the international half-lines we care about are present
        assert -0.5 in board and 0.5 in board
        # de-vig of the main −0.5 line is a valid probability
        ph, pa = devig_asian_handicap_line(board[-0.5]["home"], board[-0.5]["away"])
        assert 0.0 < ph < 1.0 and math.isclose(ph + pa, 1.0)
