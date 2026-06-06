"""Polymarket mispricing detector (READ-ONLY) — engine + matcher + log tests.

The detector compares the Polymarket ASK against our Pinnacle de-vig fair P and
tiers each gap by confidence. The SOUL of the feature is the confidence filter:
the favorite-flip exclusion (Pinnacle and Polymarket disagree on the favorite →
almost certainly a stale-data artifact, not an edge). The synthetic flip case is
the must-pass guard here. Nothing in this module places an order.
"""
from __future__ import annotations

import datetime as dt

from nutmeg.v4.data.polymarket_match import (
    AWAY_WIN,
    DRAW,
    HOME_WIN,
    MatchedGame,
    MatchedMarket,
    is_excluded_event,
    match_to_fixture,
    parse_event,
)
from nutmeg.v4.model.polymarket_gap import (
    _devig_1x2,
    compute_gaps,
    sort_gaps,
)
from nutmeg.v4.observation.polymarket_gaps import (
    fetch_polymarket_gaps,
    record_polymarket_gap,
    settle_polymarket_gaps,
)

NOW = dt.datetime(2026, 6, 6, 18, 0, tzinfo=dt.UTC)
FRESH = (NOW - dt.timedelta(hours=1)).isoformat()  # 1h old → fresh


def _book(ask: float, *, bid: float | None = None, depth_shares: float = 2000.0) -> dict:
    """A minimal CLOB book: asks ordered high→low (best=last), bids low→high."""
    bid = bid if bid is not None else round(ask - 0.02, 4)
    return {
        "asks": [{"price": str(round(ask + 0.02, 4)), "size": "100"},
                 {"price": str(ask), "size": str(depth_shares)}],
        "bids": [{"price": "0.01", "size": "50"},
                 {"price": str(bid), "size": str(depth_shares)}],
    }


def _game(fixture_id: int = 111) -> MatchedGame:
    return MatchedGame(
        fixture_id=fixture_id, league="Friendlies",
        home_team="Sierra Leone", away_team="Liberia",
        match_date="2026-06-06", kickoff_utc="2026-06-06 16:00:00+00",
        series_slug="fifa-friendly", event_slug="fif-sle-lbr-2026-06-06",
        match_method="exact", match_confidence=1.0,
        markets=[
            MatchedMarket(HOME_WIN, "tokH", "Will Sierra Leone win?"),
            MatchedMarket(DRAW, "tokD", "Will it end in a draw?"),
            MatchedMarket(AWAY_WIN, "tokA", "Will Liberia win?"),
        ],
    )


# --------------------------------------------------------------------------
class TestDevig1x2:
    def test_normalizes_to_one(self):
        p = _devig_1x2(2.0, 3.5, 4.0)
        assert abs(sum(p) - 1.0) < 1e-12 and p[0] > p[2]

    def test_rejects_non_favourable_and_junk(self):
        assert _devig_1x2(1.0, 3.5, 4.0) is None      # ≤1.0 leg
        assert _devig_1x2("x", 3.5, 4.0) is None
        assert _devig_1x2(None, 3.5, 4.0) is None


class TestFavoriteFlipGuard:
    """THE must-pass guard. Pinnacle favours home; Polymarket favours away →
    every gap of the game is EXCLUDED (the friendly-anomaly class)."""

    def test_flip_excludes_all_gaps(self):
        devig = (0.60, 0.20, 0.20)                       # Pinnacle: home favourite
        books = {"tokH": _book(0.25), "tokD": _book(0.30), "tokA": _book(0.65)}  # Poly: away
        gaps = compute_gaps(_game(), devig, books, FRESH, now=NOW)
        assert gaps and all(g.confidence_tier == "excluded" for g in gaps)
        assert all("favorite_flip" in g.reasons for g in gaps)

    def test_agreement_is_not_flipped(self):
        devig = (0.60, 0.20, 0.20)
        books = {"tokH": _book(0.62), "tokD": _book(0.30), "tokA": _book(0.22)}  # Poly: home too
        gaps = compute_gaps(_game(), devig, books, FRESH, now=NOW)
        assert all(g.confidence_tier != "excluded" for g in gaps)

    def test_near_even_is_never_a_flip(self):
        devig = (0.40, 0.20, 0.40)                       # too close to call
        books = {"tokH": _book(0.45), "tokD": _book(0.30), "tokA": _book(0.41)}
        gaps = compute_gaps(_game(), devig, books, FRESH, now=NOW)
        assert all(g.confidence_tier != "excluded" for g in gaps)

    def test_uncheckable_flip_caps_low(self):
        # only the HOME market present → cannot verify the favorite → cap low
        game = MatchedGame(
            fixture_id=1, league="X", home_team="A", away_team="B",
            match_date="2026-06-06", kickoff_utc=None, series_slug="", event_slug="",
            match_method="exact", match_confidence=1.0,
            markets=[MatchedMarket(HOME_WIN, "tokH", "q")],
        )
        gaps = compute_gaps(game, (0.6, 0.2, 0.2), {"tokH": _book(0.40)}, FRESH, now=NOW)
        assert gaps[0].confidence_tier == "low"
        assert "flip_uncheckable" in gaps[0].reasons


class TestGapMathAndTiers:
    def test_ev_sign_and_direction(self):
        # q=0.60, ask=0.40 → +EV buy; q=0.20, ask=0.40 → −EV no_edge
        devig = (0.60, 0.20, 0.20)
        books = {"tokH": _book(0.40), "tokD": _book(0.30), "tokA": _book(0.42)}
        by = {g.outcome_spec: g for g in compute_gaps(_game(), devig, books, FRESH, now=NOW)}
        assert by[HOME_WIN].ev > 0 and by[HOME_WIN].edge_direction == "buy_yes"
        assert abs(by[HOME_WIN].ev - (0.60 / 0.40 - 1)) < 1e-9
        assert by[AWAY_WIN].ev < 0 and by[AWAY_WIN].edge_direction == "no_edge"

    def test_clean_case_is_high(self):
        devig = (0.50, 0.25, 0.25)
        books = {"tokH": _book(0.45), "tokD": _book(0.27), "tokA": _book(0.27)}
        g = next(x for x in compute_gaps(_game(), devig, books, FRESH, now=NOW)
                 if x.outcome_spec == HOME_WIN)
        assert g.confidence_tier == "high" and not g.reasons

    def test_stale_pinnacle_caps_low(self):
        stale = (NOW - dt.timedelta(hours=30)).isoformat()
        g = next(x for x in compute_gaps(_game(), (0.5, 0.25, 0.25),
                 {"tokH": _book(0.45), "tokD": _book(0.27), "tokA": _book(0.27)},
                 stale, now=NOW) if x.outcome_spec == HOME_WIN)
        assert g.confidence_tier == "low" and any("stale" in r for r in g.reasons)

    def test_thin_book_caps_low(self):
        thin = _book(0.45, depth_shares=100)  # 0.45*100 ≈ $45 < $200
        g = next(x for x in compute_gaps(_game(), (0.5, 0.25, 0.25),
                 {"tokH": thin, "tokD": _book(0.27), "tokA": _book(0.27)},
                 FRESH, now=NOW) if x.outcome_spec == HOME_WIN)
        assert g.confidence_tier == "low" and any("thin" in r for r in g.reasons)

    def test_longshot_caps_low(self):
        # deep underdog: q=6%, ask=4¢ → "+50% EV" is a penny-tick/de-vig artifact,
        # NOT an edge. Must be demoted out of high/medium.
        devig = (0.90, 0.04, 0.06)
        books = {"tokH": _book(0.88), "tokD": _book(0.05, depth_shares=6000),
                 "tokA": _book(0.04, depth_shares=6000)}
        g = next(x for x in compute_gaps(_game(), devig, books, FRESH, now=NOW)
                 if x.outcome_spec == AWAY_WIN)
        assert g.ev > 0                      # naively looks +EV
        assert g.confidence_tier == "low"    # but demoted (not actionable)
        assert any("longshot" in r for r in g.reasons)

    def test_sort_excluded_sinks(self):
        devig = (0.60, 0.20, 0.20)
        books = {"tokH": _book(0.25), "tokD": _book(0.30), "tokA": _book(0.65)}  # flip → excluded
        gaps = sort_gaps(compute_gaps(_game(), devig, books, FRESH, now=NOW))
        assert gaps[-1].confidence_tier == "excluded"


# --------------------------------------------------------------------------
def _event(title, *, series="fifa-friendly", slug="fif-x-2026-06-06", draw=True):
    mk = [
        {"groupItemTitle": "Sierra Leone", "question": "Will Sierra Leone win on 2026-06-06?",
         "clobTokenIds": ["tokH", "noH"], "gameStartTime": "2026-06-06 16:00:00+00"},
        {"groupItemTitle": "Liberia", "question": "Will Liberia win on 2026-06-06?",
         "clobTokenIds": ["tokA", "noA"], "gameStartTime": "2026-06-06 16:00:00+00"},
    ]
    if draw:
        mk.insert(1, {"groupItemTitle": "Draw (Sierra Leone vs. Liberia)",
                      "question": "Will Sierra Leone vs. Liberia end in a draw?",
                      "clobTokenIds": ["tokD", "noD"], "gameStartTime": "2026-06-06 16:00:00+00"})
    return {"title": title, "slug": slug, "seriesSlug": series, "markets": mk}


def _fixture(home, away, fid=111, status="NS", hg=None, ag=None):
    fx = {
        "fixture": {"id": fid, "date": "2026-06-06T16:00:00+00:00", "status": {"short": status}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "league": {"name": "Friendlies"},
    }
    if hg is not None:
        fx["score"] = {"fulltime": {"home": hg, "away": ag}}
        fx["goals"] = {"home": hg, "away": ag}
    return fx


class TestMatcher:
    def test_parse_clean_moneyline_event(self):
        p = parse_event(_event("Sierra Leone vs. Liberia"))
        assert p is not None
        assert p.team_a == "Sierra Leone" and p.team_b == "Liberia"
        assert set(p.outcomes) == {"Sierra Leone", "Liberia", "DRAW"}

    def test_prop_event_title_is_skipped(self):
        assert parse_event(_event("Sierra Leone vs. Liberia - Exact Score")) is None

    def test_womens_event_excluded(self):
        ev = _event("Sweden vs. Italy", series="uefa-womens-world-cup-qualification",
                    slug="wwcquefa-swe-ita-2026-06-09")
        assert is_excluded_event(ev) is not None

    def test_u21_event_excluded(self):
        ev = _event("France vs. Spain", series="uefa-u21-championship", slug="u21-fra-esp")
        assert is_excluded_event(ev) is not None

    def test_match_maps_outcomes_to_fixture_sides(self):
        p = parse_event(_event("Sierra Leone vs. Liberia"))
        mg = match_to_fixture(p, [_fixture("Sierra Leone", "Liberia")])
        assert mg is not None and mg.fixture_id == 111
        specs = {m.outcome_spec for m in mg.markets}
        assert specs == {HOME_WIN, DRAW, AWAY_WIN}
        home_mk = next(m for m in mg.markets if m.outcome_spec == HOME_WIN)
        assert home_mk.yes_token == "tokH"

    def test_reversed_home_away_in_fixture_remaps(self):
        # Polymarket title order ≠ fixture home/away → spec follows the FIXTURE
        p = parse_event(_event("Sierra Leone vs. Liberia"))
        mg = match_to_fixture(p, [_fixture("Liberia", "Sierra Leone")])  # Liberia is home
        home_mk = next(m for m in mg.markets if m.outcome_spec == HOME_WIN)
        assert home_mk.yes_token == "tokA"  # Liberia's YES token = the HOME_WIN now

    def test_conservative_no_false_join(self):
        # Real Madrid must NOT fuzzy-match Real Sociedad (ratio ~0.79 < 0.86)
        p = parse_event(_event("Real Madrid vs. Liberia"))
        assert match_to_fixture(p, [_fixture("Real Sociedad", "Liberia")]) is None

    def test_club_suffix_matches_core(self):
        # Polymarket "FC Imabari"/"Iwaki FC" ↔ API-Football "Imabari"/"Iwaki":
        # the bare FC suffix drops fuzzy below 0.86, so strip club tokens to a core.
        ev = {
            "title": "FC Imabari vs. Iwaki FC", "slug": "j2-imb-iwk",
            "seriesSlug": "japan-j2-league",
            "markets": [
                {"groupItemTitle": "FC Imabari", "question": "Will FC Imabari win on 2026-06-07?",
                 "clobTokenIds": ["tH", "x"], "gameStartTime": "2026-06-07 03:00:00+00"},
                {"groupItemTitle": "Draw (FC Imabari vs. Iwaki FC)",
                 "question": "Will FC Imabari vs. Iwaki FC end in a draw?",
                 "clobTokenIds": ["tD", "x"], "gameStartTime": "2026-06-07 03:00:00+00"},
                {"groupItemTitle": "Iwaki FC", "question": "Will Iwaki FC win on 2026-06-07?",
                 "clobTokenIds": ["tA", "x"], "gameStartTime": "2026-06-07 03:00:00+00"},
            ],
        }
        mg = match_to_fixture(parse_event(ev), [_fixture("Imabari", "Iwaki", fid=9)])
        assert mg is not None and mg.fixture_id == 9
        assert mg.match_confidence == 1.0  # core-exact, not fuzzy
        home = next(m for m in mg.markets if m.outcome_spec == HOME_WIN)
        assert home.yes_token == "tH"  # FC Imabari = the fixture home


class TestPersistenceAndSettle:
    def test_record_idempotent_and_settle_hit(self, tmp_path):
        db = str(tmp_path / "obs.db")
        g = compute_gaps(_game(), (0.50, 0.25, 0.25),
                         {"tokH": _book(0.40), "tokD": _book(0.30), "tokA": _book(0.40)},
                         FRESH, now=NOW)
        for gap in g:               # log all 3 outcomes
            record_polymarket_gap(db, gap)
        record_polymarket_gap(db, g[0])   # re-log → idempotent
        rows = fetch_polymarket_gaps(db)
        assert len(rows) == 3       # not 4

        # Sierra Leone (home) win 2-0 → HOME_WIN YES hits, AWAY/DRAW miss
        fixtures = [_fixture("Sierra Leone", "Liberia", status="FT", hg=2, ag=0)]
        n = settle_polymarket_gaps(db, fetch_fixtures=lambda d: fixtures,
                                   today=dt.date(2026, 6, 7))
        assert n == 3
        settled = {r["outcome_spec"]: r for r in fetch_polymarket_gaps(db, settled_only=True)}
        assert settled[HOME_WIN]["outcome_hit"] == 1
        assert settled[AWAY_WIN]["outcome_hit"] == 0
        assert settled[DRAW]["outcome_hit"] == 0
