"""体检(2026-06-10)— The Odds API fresher-Pinnacle-line overlay.

A measured head-to-head showed The Odds API's Pinnacle line is ~3h fresher than
API-Football's mirror (median 36s vs 2.9h) and broader for the World Cup. This
overlays the fresher line onto _gather_rows rows WITHOUT touching identity:
API-Football still owns team names / results / sharp-flip books; only the PRICE
is swapped, and only when Odds API is genuinely fresher (or AF had no line).
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from nutmeg.v4.cli.ingest_odds import (
    _apply_odds_api_overlay,
    _gather_rows,
    _iso_newer,
)
from nutmeg.v4.data.sources import odds_api


def _pin_event(home="Mexico", away="South Africa", date="2026-06-11",
               last_update="2026-06-11T03:00:00Z", with_totals=True):
    markets = [{"key": "h2h", "outcomes": [
        {"name": home, "price": 1.43},
        {"name": away, "price": 8.70},
        {"name": "Draw", "price": 4.43},
    ]}]
    if with_totals:
        markets.append({"key": "totals", "outcomes": [
            {"name": "Over", "price": 1.96, "point": 2.25},
            {"name": "Under", "price": 1.93, "point": 2.25},
        ]})
    return {
        "home_team": home, "away_team": away,
        "commence_time": f"{date}T19:00:00Z",
        "bookmakers": [{"key": "pinnacle", "last_update": last_update,
                        "markets": markets}],
    }


# ---------- parsing primitives ----------------------------------------

class TestNormTeam:
    def test_amp_and_accents_fold(self):
        assert odds_api._norm_team("Bosnia & Herzegovina") == "bosniaandherzegovina"
        assert odds_api._norm_team("Bosnia and Herzegovina") == "bosniaandherzegovina"
        assert odds_api._norm_team("Côte d'Ivoire") == odds_api._norm_team("Cote dIvoire")

    def test_af_oa_spelling_pairs_collapse(self):
        """API-Football vs Odds API spellings that diverge past accent-fold must
        still key the same, else the fresher-line overlay silently misses them."""
        assert odds_api._norm_team("Türkiye") == odds_api._norm_team("Turkey")
        assert odds_api._norm_team("Cape Verde Islands") == odds_api._norm_team("Cape Verde")
        assert odds_api._norm_team("Congo DR") == odds_api._norm_team("DR Congo")
        assert odds_api._norm_team("Czechia") == odds_api._norm_team("Czech Republic")
        # Veikkausliiga (FIN) prefix/suffix/reorder pairs
        assert odds_api._norm_team("Inter Turku") == odds_api._norm_team("FC Inter Turku")
        assert odds_api._norm_team("VPS") == odds_api._norm_team("VPS Vaasa")
        assert odds_api._norm_team("Turku PS") == odds_api._norm_team("TPS Turku")
        assert odds_api._norm_team("FF Jaro") == odds_api._norm_team("Jaro")
        # K League 1 (KOR) — brand middle-token + a 2021 relocation the Odds API
        # never renamed (measured live overlay misses, 体检 2026-07-03)
        nt = odds_api._norm_team
        assert nt("Jeonbuk Motors") == nt("Jeonbuk Hyundai Motors")
        assert nt("Gimcheon Sangmu FC") == nt("Sangju Sangmu FC")

    def test_kleague_and_j1_sport_keys_registered(self):
        """体检 2026-07-03 — 韩职 cards stayed on the stale AF mirror because the
        league had NO Odds API sport key (no lookup → the overlay never ran; the
        club-core fix only helps leagues that HAVE a lookup). kleague1 probed
        active=True; j_league key exists (inactive between rounds = fail-soft)."""
        assert odds_api.SPORT_KEYS["KOR_K_LEAGUE_1"] == "soccer_korea_kleague1"
        assert odds_api.SPORT_KEYS["JPN_J1"] == "soccer_japan_j_league"


class TestExtractTotals:
    def test_picks_line_closest_to_2_5(self):
        bk = {"markets": [{"key": "totals", "outcomes": [
            {"name": "Over", "price": 1.9, "point": 2.25},
            {"name": "Under", "price": 1.95, "point": 2.25}]}]}
        assert odds_api._extract_totals(bk) == (2.25, 1.9, 1.95)

    def test_none_when_absent(self):
        assert odds_api._extract_totals({"markets": [{"key": "h2h", "outcomes": []}]}) is None


class TestFetchPinnacleLookup:
    def test_parses_pinnacle_h2h_and_totals(self, monkeypatch):
        monkeypatch.setattr(odds_api, "fetch_current_odds", lambda *a, **k: [_pin_event()])
        lk = odds_api.fetch_pinnacle_lookup("soccer_fifa_world_cup")
        rec = lk[("mexico", "southafrica", "2026-06-11")]
        assert (rec["psc_home"], rec["psc_draw"], rec["psc_away"]) == (1.43, 4.43, 8.70)
        assert (rec["ou_line"], rec["psc_over"], rec["psc_under"]) == (2.25, 1.96, 1.93)
        assert rec["last_update"] == "2026-06-11T03:00:00Z"

    def test_skips_fixtures_without_pinnacle(self, monkeypatch):
        ev = _pin_event()
        ev["bookmakers"][0]["key"] = "bet365"   # no pinnacle
        monkeypatch.setattr(odds_api, "fetch_current_odds", lambda *a, **k: [ev])
        assert odds_api.fetch_pinnacle_lookup("soccer_fifa_world_cup") == {}


# ---------- overlay logic ---------------------------------------------

class TestIsoNewer:
    def test_basic(self):
        assert _iso_newer("2026-06-11T03:00:00Z", "2026-06-10T00:00:00Z")
        assert not _iso_newer("2026-06-10T00:00:00Z", "2026-06-11T03:00:00Z")
        assert _iso_newer("2026-06-11T03:00:00Z", None)   # AF had no ts → fresher
        assert not _iso_newer(None, "2026-06-11T03:00:00Z")


def _lookup():
    return {("mexico", "southafrica", "2026-06-11"): {
        "psc_home": 1.43, "psc_draw": 4.43, "psc_away": 8.70,
        "ou_line": 2.25, "psc_over": 1.96, "psc_under": 1.93,
        "last_update": "2026-06-11T03:00:00Z"}}


class TestApplyOverlay:
    def _af_row(self, **over):
        row = {"date": "2026-06-11", "home_team": "Mexico", "away_team": "South Africa",
               "psc_home": 1.60, "psc_draw": 4.00, "psc_away": 6.00,
               "odds_update": "2026-06-10T00:00:00Z"}
        row.update(over)
        return row

    def test_fresher_line_wins(self):
        row = self._af_row()
        assert _apply_odds_api_overlay(row, _lookup()) is True
        assert row["psc_home"] == 1.43 and row["psc_away"] == 8.70
        assert row["odds_update"] == "2026-06-11T03:00:00Z"
        assert row["odds_source"] == "odds_api"

    def test_fills_pending_row(self):
        row = self._af_row(psc_home=None, psc_draw=None, psc_away=None, odds_update=None)
        assert _apply_odds_api_overlay(row, _lookup()) is True
        assert row["psc_home"] == 1.43 and row["odds_source"] == "odds_api"

    def test_prefers_odds_api_even_when_af_newer(self):
        # V14 — even when AF's line is NEWER, PREFER the Odds API Pinnacle: it
        # tracks real Pinnacle more closely (AF mirror drifts). The card's
        # freshness badge still surfaces staleness to the user.
        row = self._af_row(odds_update="2026-06-11T12:00:00Z")
        assert _apply_odds_api_overlay(row, _lookup()) is True
        assert row["psc_home"] == 1.43 and row["odds_source"] == "odds_api"

    def test_unmatched_fixture_is_noop(self):
        row = self._af_row(home_team="Brazil", away_team="Morocco")
        assert _apply_odds_api_overlay(row, _lookup()) is False
        assert row["psc_home"] == 1.60


# ---------- end-to-end through _gather_rows ---------------------------

def _wire_af(monkeypatch, *, with_af_odds=True, fid=900):
    from nutmeg.v4.cli import ingest_odds as mod
    env = {
        "fixture": {"id": fid, "date": "2026-06-11T19:00:00+00:00",
                    "status": {"short": "NS"}},
        "teams": {"home": {"name": "Mexico"}, "away": {"name": "South Africa"}},
        "update": "2026-06-10T00:00:00Z",
        "bookmakers": ([{"id": 4, "name": "Pinnacle", "bets": [
            {"id": 1, "name": "Match Winner", "values": [
                {"value": "Home", "odd": "1.60"},
                {"value": "Draw", "odd": "4.00"},
                {"value": "Away", "odd": "6.00"}]}]}] if with_af_odds else []),
    }
    monkeypatch.setattr(mod.api_football, "fetch_fixtures_for_date", lambda *a, **k: [env])
    monkeypatch.setattr(mod.api_football, "fetch_odds", lambda *a, **k: [env])
    return mod


class TestGatherRowsOverlay:
    def test_fresher_odds_api_line_overrides_af(self, tmp_path, monkeypatch):
        mod = _wire_af(monkeypatch)
        monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", lambda *a, **k: _lookup())
        rows, _, _ = mod._gather_rows(
            ["WC"], dt.date(2026, 6, 11), cache_dir=tmp_path,
            bookmaker_id=4, refresh_fixtures=False, refresh_odds=False,
            use_odds_api=True)
        assert len(rows) == 1
        r = rows[0]
        assert r["psc_home"] == 1.43 and r["ou_line"] == 2.25
        assert r["odds_source"] == "odds_api"
        assert r["odds_update"] == "2026-06-11T03:00:00Z"

    def test_pending_af_filled_by_odds_api(self, tmp_path, monkeypatch):
        mod = _wire_af(monkeypatch, with_af_odds=False)
        monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", lambda *a, **k: _lookup())
        # require_odds=True would normally drop the odds-less fixture; the overlay
        # fills it first, so it survives.
        rows, _, _ = mod._gather_rows(
            ["WC"], dt.date(2026, 6, 11), cache_dir=tmp_path,
            bookmaker_id=4, refresh_fixtures=False, refresh_odds=False,
            require_odds=True, use_odds_api=True)
        assert len(rows) == 1 and rows[0]["psc_home"] == 1.43

    def test_overlay_failure_falls_back_to_af(self, tmp_path, monkeypatch):
        mod = _wire_af(monkeypatch)

        def boom(*a, **k):
            raise odds_api.OddsApiError("synthetic")

        monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", boom)
        rows, _, _ = mod._gather_rows(
            ["WC"], dt.date(2026, 6, 11), cache_dir=tmp_path,
            bookmaker_id=4, refresh_fixtures=False, refresh_odds=False,
            use_odds_api=True)
        assert len(rows) == 1
        assert rows[0]["psc_home"] == 1.60          # API-Football line kept
        assert "odds_source" not in rows[0]


# ---------- club-core fallback (体检 2026-07-03, SWE slate) -------------

class TestClubCoreFallback:
    """AF↔OA club LEGAL-FORM drift: 'Sirius'↔'IK Sirius' etc. left the card on
    the 3.6h-stale AF mirror while the Odds API HAD a fresh Pinnacle line. The
    lookup indexes a secondary club-core key; collisions are poisoned."""

    def test_club_core_strips_legal_form_tokens(self):
        assert odds_api._club_core("IK Sirius") == "sirius"
        assert odds_api._club_core("Vasteras SK FK") == "vasteras"
        assert odds_api._club_core("Västerås SK") == "vasteras"
        assert odds_api._club_core("Hammarby FF") == "hammarby"
        assert odds_api._club_core("Hammarby IF") == "hammarby"
        assert odds_api._club_core("AIK") == "aik"        # pure abbrev untouched
        assert odds_api._club_core("FF") is None          # nothing usable left
        assert odds_api._club_core(None) is None

    def _overlay_row(self, home, away, date="2026-07-03"):
        return {"home_team": home, "away_team": away, "date": date,
                "psc_home": 1.68, "psc_draw": 3.97, "psc_away": 4.84,
                "odds_update": "2026-07-03T10:00:00+00:00"}

    def test_overlay_patches_via_club_core(self, monkeypatch):
        ev = _pin_event(home="IK Sirius", away="Mjällby AIF", date="2026-07-03",
                        last_update="2026-07-03T13:30:00Z")
        monkeypatch.setattr(odds_api, "fetch_current_odds", lambda *a, **k: [ev])
        lookup = odds_api.fetch_pinnacle_lookup("soccer_sweden_allsvenskan")
        row = self._overlay_row("Sirius", "Mjallby AIF")   # AF spellings
        now = dt.datetime(2026, 7, 3, 12, 0, tzinfo=dt.UTC)  # pre-kickoff
        assert _apply_odds_api_overlay(row, lookup, now=now) is True
        assert row["odds_source"] == "odds_api" and row["psc_home"] == 1.43

    def test_swedish_genitive_alias(self, monkeypatch):
        # AF 'Halmstad' ↔ OA 'Halmstads BK': morphology → _NORM_ALIAS, not core
        ev = _pin_event(home="Halmstads BK", away="Västerås SK", date="2026-07-04",
                        last_update="2026-07-03T13:30:00Z")
        monkeypatch.setattr(odds_api, "fetch_current_odds", lambda *a, **k: [ev])
        lookup = odds_api.fetch_pinnacle_lookup("soccer_sweden_allsvenskan")
        row = self._overlay_row("Halmstad", "Vasteras SK FK", date="2026-07-04")
        now = dt.datetime(2026, 7, 3, 12, 0, tzinfo=dt.UTC)
        assert _apply_odds_api_overlay(row, lookup, now=now) is True

    def test_ambiguous_core_never_patches(self, monkeypatch):
        # two same-day events whose cores collide → poisoned → NO patch (wrong-team
        # odds are worse than stale odds); their exact keys still work.
        e1 = _pin_event(home="IK Sirius", away="Mjällby AIF", date="2026-07-03")
        e2 = _pin_event(home="Sirius FF", away="Mjallby SK", date="2026-07-03")
        monkeypatch.setattr(odds_api, "fetch_current_odds", lambda *a, **k: [e1, e2])
        lookup = odds_api.fetch_pinnacle_lookup("soccer_sweden_allsvenskan")
        assert lookup[("sirius", "mjallby", "2026-07-03")] is None   # poisoned
        row = self._overlay_row("Sirius", "Mjallby")
        now = dt.datetime(2026, 7, 3, 12, 0, tzinfo=dt.UTC)
        assert _apply_odds_api_overlay(row, lookup, now=now) is False
        # exact keys unaffected
        assert lookup[("iksirius", "mjallbyaif", "2026-07-03")]["psc_home"] == 1.43


# ---------- quota/auth breaker ----------------------------------------

class _Resp:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body
        self.headers = {}

    @property
    def text(self):
        return json.dumps(self._body)

    def json(self):
        return self._body


class _CountingClient:
    """Stands in for the keep-alive httpx client; counts live calls."""

    def __init__(self, resp):
        self.resp, self.n = resp, 0

    def get(self, endpoint, params=None):
        self.n += 1
        return self.resp


_QUOTA_401 = {"error_code": "OUT_OF_USAGE_CREDITS",
              "message": "Usage quota has been reached."}


class TestQuotaBreaker:
    """Once the Odds API says the credits are gone, every later endpoint 401s
    too — and a failed call caches nothing, so the 市场模式 overlay used to pay
    a live ~0.4s round-trip per (sport × day): 119 of them = 45.2s of a 48.0s
    /predictions/cup-market (measured 2026-07-17). One 401 is enough to know."""

    @pytest.fixture(autouse=True)
    def _closed_breaker(self):
        odds_api.reset_quota_breaker()   # never inherit a sibling test's state
        yield
        odds_api.reset_quota_breaker()   # never leak into one

    def _client(self, monkeypatch, status, body):
        c = _CountingClient(_Resp(status, body))
        monkeypatch.setattr(odds_api, "_client", lambda: c)
        return c

    def test_401_trips_breaker_so_the_next_call_never_leaves_the_process(
        self, tmp_path, monkeypatch,
    ):
        c = self._client(monkeypatch, 401, _QUOTA_401)
        for _ in range(5):
            with pytest.raises(odds_api.OddsApiError):
                odds_api._request("sports/a/odds", {"regions": "eu"}, cache_dir=tmp_path)
        # 5 callers, ONE round-trip: the other 4 were answered locally.
        assert c.n == 1

    def test_open_breaker_still_serves_a_fresh_cache(self, tmp_path, monkeypatch):
        # The breaker suppresses the pointless live call — it must NOT blind a
        # warm cache, which is the whole point of the overlay on a passive load.
        params = {"regions": "eu", "markets": "h2h"}
        cf = odds_api._cache_path("sports/b/odds", params, tmp_path)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps([{"id": "cached"}]))
        c = self._client(monkeypatch, 401, _QUOTA_401)
        odds_api._trip_breaker()
        got = odds_api._request("sports/b/odds", params, cache_dir=tmp_path,
                                ttl_seconds=1800)
        assert got == [{"id": "cached"}]
        assert c.n == 0

    def test_stale_cache_is_never_served_while_open(self, tmp_path, monkeypatch):
        # The TTL gate ("never serve a day-old line") outranks the breaker: a
        # dead quota must degrade to the API-Football mirror, NOT to stale odds.
        params = {"regions": "eu", "markets": "h2h"}
        cf = odds_api._cache_path("sports/c/odds", params, tmp_path)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps([{"id": "stale"}]))
        self._client(monkeypatch, 401, _QUOTA_401)
        odds_api._trip_breaker()
        with pytest.raises(odds_api.OddsApiError):
            odds_api._request("sports/c/odds", params, cache_dir=tmp_path,
                              ttl_seconds=0.0)   # cache older than its TTL

    def test_5xx_stays_retryable(self, tmp_path, monkeypatch):
        # A transient is not a quota death — don't lock the overlay out for 15min.
        c = self._client(monkeypatch, 503, {"message": "upstream hiccup"})
        for _ in range(3):
            with pytest.raises(odds_api.OddsApiError):
                odds_api._request("sports/d/odds", {"regions": "eu"}, cache_dir=tmp_path)
        assert c.n == 3

    def test_reset_reopens_the_valve_after_a_top_up(self, tmp_path, monkeypatch):
        c = self._client(monkeypatch, 401, _QUOTA_401)
        with pytest.raises(odds_api.OddsApiError):
            odds_api._request("sports/e/odds", {"regions": "eu"}, cache_dir=tmp_path)
        odds_api.reset_quota_breaker()
        with pytest.raises(odds_api.OddsApiError):
            odds_api._request("sports/e/odds", {"regions": "eu"}, cache_dir=tmp_path)
        assert c.n == 2   # reset → the retry really went out again
