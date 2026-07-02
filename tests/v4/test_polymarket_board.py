"""PM board (让球 + 大小球 + model triangulation) — pure unit tests, no network.

Complements test_polymarket_gap.py (moneyline). Covers the PM-1..PM-4 additions:
handicap/total parsing + event merge, DC-grid fair q, score-vs-line settlement,
and the model↔Pinnacle↔Polymarket triangulation flags.
"""
from __future__ import annotations

from nutmeg.v4.data.polymarket_match import collect_matched_games
from nutmeg.v4.model.polymarket_gap import _build_grid, _q_for
from nutmeg.v4.observation.polymarket_gaps import _yes_resolves
from nutmeg.v4.observation.polymarket_model_overlay import triangulate

_KO = "2026-07-02 20:00:00+00"


def _mkt(q, toks, outcomes, git=None):
    m = {"question": q, "gameStartTime": _KO, "clobTokenIds": toks, "outcomes": outcomes}
    if git is not None:
        m["groupItemTitle"] = git
    return m


def _base_event():
    return {"title": "Alpha vs. Beta", "slug": "alpha-beta", "seriesSlug": "", "markets": [
        _mkt("Will Alpha win on 2026-07-02?", ["hA", "nA"], ["Yes", "No"], "Alpha"),
        _mkt("Will Beta win on 2026-07-02?", ["hB", "nB"], ["Yes", "No"], "Beta"),
        _mkt("Will Alpha vs. Beta end in a draw?", ["hD", "nD"], ["Yes", "No"], "Draw"),
    ]}


def _more_event():
    return {"title": "Alpha vs. Beta - More Markets", "slug": "alpha-beta-more-markets",
            "seriesSlug": "", "markets": [
        _mkt("Spread: Alpha (-1.5)", ["sAh", "sAa"], ["Alpha", "Beta"]),
        _mkt("Alpha vs. Beta: O/U 2.5", ["ov", "un"], ["Over", "Under"]),
        _mkt("Alpha vs. Beta: Alpha O/U 2.5", ["x", "y"], ["Over", "Under"]),  # TEAM total → skip
        _mkt("Alpha vs. Beta: O/U 2.5 Corners", ["p", "q"], ["Over", "Under"]),  # corners → skip
    ]}


_FIXTURES = [{"fixture": {"id": 7, "date": "2026-07-02T20:00:00+00:00"},
              "teams": {"home": {"name": "Alpha"}, "away": {"name": "Beta"}},
              "league": {"name": "Test League"}}]


def test_parser_merges_moneyline_handicap_totals():
    games, _ = collect_matched_games(
        [_base_event(), _more_event()], lambda d: _FIXTURES)
    assert len(games) == 1  # the two events merged into one fixture
    g = games[0]
    by = {(m.outcome_spec, m.line) for m in g.markets}
    # moneyline
    assert ("HOME_WIN", None) in by and ("DRAW", None) in by and ("AWAY_WIN", None) in by
    # handicap: Alpha(home) covers -1.5, Beta(away) covers +1.5 (both sides of one market)
    assert ("HANDICAP_HOME", -1.5) in by and ("HANDICAP_AWAY", 1.5) in by
    # full-match total only — team total + corners excluded
    assert ("OVER", 2.5) in by and ("UNDER", 2.5) in by
    assert not any(m.outcome_spec in ("OVER", "UNDER") and m.line != 2.5 for m in g.markets)
    # correct YES token for the home handicap leg
    hh = next(m for m in g.markets if m.outcome_spec == "HANDICAP_HOME")
    assert hh.yes_token == "sAh"


def test_handicap_and_total_q_are_complements():
    grid = _build_grid(0.50, 0.28, 0.22, 0.55)
    h = _q_for("HANDICAP_HOME", -1.5, 0.50, 0.28, 0.22, grid)
    a = _q_for("HANDICAP_AWAY", 1.5, 0.50, 0.28, 0.22, grid)
    assert abs((h + a) - 1.0) < 1e-9   # 2-way half-line, no push
    o = _q_for("OVER", 2.5, 0.50, 0.28, 0.22, grid)
    u = _q_for("UNDER", 2.5, 0.50, 0.28, 0.22, grid)
    assert abs((o + u) - 1.0) < 1e-9
    assert 0.0 < h < 1.0 and 0.0 < o < 1.0
    # moneyline routes straight through the de-vig 1X2
    assert _q_for("HOME_WIN", None, 0.50, 0.28, 0.22, grid) == 0.50


def test_settlement_score_vs_line():
    # 3-0: margin +3, total 3
    assert _yes_resolves("HOME_WIN", None, 3, 0) == 1
    assert _yes_resolves("DRAW", None, 3, 0) == 0
    assert _yes_resolves("AWAY_WIN", None, 3, 0) == 0
    assert _yes_resolves("HANDICAP_HOME", -1.5, 3, 0) == 1   # home by ≥2 ✓
    assert _yes_resolves("HANDICAP_HOME", -3.5, 3, 0) == 0   # not by ≥4
    assert _yes_resolves("HANDICAP_AWAY", 1.5, 3, 0) == 0
    assert _yes_resolves("OVER", 2.5, 3, 0) == 1
    assert _yes_resolves("UNDER", 2.5, 3, 0) == 0
    # 1-1: margin 0, total 2
    assert _yes_resolves("DRAW", None, 1, 1) == 1
    assert _yes_resolves("HANDICAP_HOME", 1.5, 1, 1) == 1    # home +1.5 covers a draw
    assert _yes_resolves("UNDER", 2.5, 1, 1) == 1
    assert _yes_resolves("BOGUS", 1.5, 1, 1) is None


def test_triangulation_all_agree():
    t = triangulate((0.55, 0.25, 0.20), {"H": 0.57, "D": 0.26, "A": 0.18}, (0.53, 0.26, 0.21))
    assert t.all_three_agree and not t.consensus_vs_poly_diverge and t.flip_backer is None


def test_triangulation_diverge_flags_polymarket():
    # model + Pinnacle say H, Polymarket says A → Polymarket mispricing candidate
    t = triangulate((0.55, 0.25, 0.20), {"H": 0.30, "D": 0.25, "A": 0.45}, (0.52, 0.26, 0.22))
    assert t.consensus_vs_poly_diverge and t.flip_backer == "pinnacle"


def test_triangulation_model_backs_polymarket_on_flip():
    # Pinnacle H, Polymarket A, model A → Pinnacle likely stale
    t = triangulate((0.45, 0.25, 0.30), {"H": 0.30, "D": 0.25, "A": 0.45}, (0.30, 0.25, 0.45))
    assert t.flip_backer == "polymarket" and not t.consensus_vs_poly_diverge


def test_triangulation_no_model():
    t = triangulate((0.55, 0.25, 0.20), {"H": 0.57, "D": 0.26, "A": 0.18}, None)
    assert t.model_argmax is None and not t.all_three_agree and not t.consensus_vs_poly_diverge
    assert t.pinnacle_argmax == "H" and t.polymarket_argmax == "H"
