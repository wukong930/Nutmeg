"""V11 P1-FE#5 — tests for recommendation version hashing + diff.

The version module is pure (no DB, no model), so we can exhaustively
exercise its determinism + stability properties.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------- selection_fingerprint -------------------------------------

class TestSelectionFingerprint:
    def test_basic(self):
        from nutmeg.v4.observation.recommendation_version import selection_fingerprint
        a = [
            {"match_id": "EPL_A_vs_B", "market_type": "1x2", "outcome": "H"},
            {"match_id": "EPL_C_vs_D", "market_type": "1x2", "outcome": "A"},
        ]
        fp = selection_fingerprint(a)
        assert isinstance(fp, str)
        assert len(fp) == 12  # short hash

    def test_order_invariant(self):
        """Reordering the picks doesn't change the fingerprint."""
        from nutmeg.v4.observation.recommendation_version import selection_fingerprint
        a = [
            {"match_id": "X", "market_type": "1x2", "outcome": "H"},
            {"match_id": "Y", "market_type": "1x2", "outcome": "A"},
        ]
        b = list(reversed(a))
        assert selection_fingerprint(a) == selection_fingerprint(b)

    def test_outcome_changes_hash(self):
        """Same matches but different outcome → different fingerprint."""
        from nutmeg.v4.observation.recommendation_version import selection_fingerprint
        a = [{"match_id": "X", "market_type": "1x2", "outcome": "H"}]
        b = [{"match_id": "X", "market_type": "1x2", "outcome": "A"}]
        assert selection_fingerprint(a) != selection_fingerprint(b)

    def test_market_changes_hash(self):
        from nutmeg.v4.observation.recommendation_version import selection_fingerprint
        a = [{"match_id": "X", "market_type": "1x2", "outcome": "H"}]
        b = [{"match_id": "X", "market_type": "handicap_1x2", "outcome": "H"}]
        assert selection_fingerprint(a) != selection_fingerprint(b)

    def test_empty(self):
        from nutmeg.v4.observation.recommendation_version import selection_fingerprint
        # Empty list should still produce a stable fingerprint (not error)
        fp = selection_fingerprint([])
        assert isinstance(fp, str)
        assert len(fp) == 12


# ---------- parlay_recommendation_fingerprint -------------------------

class TestParlayFingerprint:
    def test_picks_one_per_leg(self):
        from nutmeg.v4.observation.recommendation_version import (
            parlay_recommendation_fingerprint,
        )
        rec = {
            "legs": [
                {"match_id": "X", "market_type": "1x2",
                 "selections": [{"outcome": "H", "odds": 1.85}]},
                {"match_id": "Y", "market_type": "1x2",
                 "selections": [{"outcome": "A", "odds": 2.10}]},
            ]
        }
        fp = parlay_recommendation_fingerprint(rec)
        assert len(fp) == 12

    def test_a_b_c_d_vs_a_b_c_e_differ(self):
        """User's stated scenario: ABCD vs ABCE differ."""
        from nutmeg.v4.observation.recommendation_version import (
            parlay_recommendation_fingerprint,
        )
        abcd = {"legs": [
            {"match_id": "A", "market_type": "1x2", "selections": [{"outcome": "H"}]},
            {"match_id": "B", "market_type": "1x2", "selections": [{"outcome": "H"}]},
            {"match_id": "C", "market_type": "1x2", "selections": [{"outcome": "H"}]},
            {"match_id": "D", "market_type": "1x2", "selections": [{"outcome": "H"}]},
        ]}
        abce = {"legs": [
            {"match_id": "A", "market_type": "1x2", "selections": [{"outcome": "H"}]},
            {"match_id": "B", "market_type": "1x2", "selections": [{"outcome": "H"}]},
            {"match_id": "C", "market_type": "1x2", "selections": [{"outcome": "H"}]},
            {"match_id": "E", "market_type": "1x2", "selections": [{"outcome": "H"}]},
        ]}
        assert parlay_recommendation_fingerprint(abcd) != parlay_recommendation_fingerprint(abce)


# ---------- single / pool ticket fingerprints ------------------------

class TestSingleTicketFingerprint:
    def test_single_ticket_fingerprint(self):
        from nutmeg.v4.observation.recommendation_version import single_ticket_fingerprint
        t = {"match_id": "EPL_A_vs_B", "market_type": "1x2", "outcome": "H"}
        fp = single_ticket_fingerprint(t)
        assert len(fp) == 12

    def test_outcome_change_differs(self):
        from nutmeg.v4.observation.recommendation_version import single_ticket_fingerprint
        a = {"match_id": "X", "market_type": "1x2", "outcome": "H"}
        b = {"match_id": "X", "market_type": "1x2", "outcome": "A"}
        assert single_ticket_fingerprint(a) != single_ticket_fingerprint(b)


class TestPoolTicketFingerprint:
    def test_pool_ticket_fingerprint(self):
        from nutmeg.v4.observation.recommendation_version import pool_ticket_fingerprint
        t = {"legs": [
            {"match_id": "X", "market_type": "1x2", "outcome": "H"},
            {"match_id": "Y", "market_type": "1x2", "outcome": "A"},
        ]}
        fp = pool_ticket_fingerprint(t)
        assert len(fp) == 12

    def test_leg_order_invariant(self):
        from nutmeg.v4.observation.recommendation_version import pool_ticket_fingerprint
        a = {"legs": [
            {"match_id": "X", "market_type": "1x2", "outcome": "H"},
            {"match_id": "Y", "market_type": "1x2", "outcome": "A"},
        ]}
        b = {"legs": list(reversed(a["legs"]))}
        assert pool_ticket_fingerprint(a) == pool_ticket_fingerprint(b)


# ---------- fixtures_odds_digest -------------------------------------

class TestOddsDigest:
    def test_stable_under_reorder(self):
        from nutmeg.v4.observation.recommendation_version import fixtures_odds_digest
        a = [
            {"date": "2026-05-25", "league": "EPL", "home_team": "X", "away_team": "Y",
             "psc_home": 2.0, "psc_draw": 3.4, "psc_away": 3.6},
            {"date": "2026-05-25", "league": "EPL", "home_team": "A", "away_team": "B",
             "psc_home": 1.5, "psc_draw": 4.0, "psc_away": 5.0},
        ]
        b = list(reversed(a))
        assert fixtures_odds_digest(a) == fixtures_odds_digest(b)

    def test_odds_change_changes_digest(self):
        from nutmeg.v4.observation.recommendation_version import fixtures_odds_digest
        a = [{"date": "2026-05-25", "league": "EPL", "home_team": "X", "away_team": "Y",
              "psc_home": 2.0, "psc_draw": 3.4, "psc_away": 3.6}]
        b = [{"date": "2026-05-25", "league": "EPL", "home_team": "X", "away_team": "Y",
              "psc_home": 1.90, "psc_draw": 3.4, "psc_away": 3.6}]  # home moved 5%
        assert fixtures_odds_digest(a) != fixtures_odds_digest(b)

    def test_small_jitter_stable(self):
        """Rounding to 4 decimals — sub-decimal float noise doesn't flip the hash."""
        from nutmeg.v4.observation.recommendation_version import fixtures_odds_digest
        a = [{"date": "2026-05-25", "league": "EPL", "home_team": "X", "away_team": "Y",
              "psc_home": 2.0, "psc_draw": 3.4, "psc_away": 3.6}]
        b = [{"date": "2026-05-25", "league": "EPL", "home_team": "X", "away_team": "Y",
              "psc_home": 2.0 + 1e-9, "psc_draw": 3.4, "psc_away": 3.6}]
        assert fixtures_odds_digest(a) == fixtures_odds_digest(b)


# ---------- version_hash composition ---------------------------------

class TestVersionHash:
    def test_independent_of_fingerprint_order(self):
        from nutmeg.v4.observation.recommendation_version import version_hash
        h1 = version_hash(parlay_fingerprints=["aaa", "bbb"], odds_digest="o1")
        h2 = version_hash(parlay_fingerprints=["bbb", "aaa"], odds_digest="o1")
        assert h1 == h2

    def test_odds_change_propagates(self):
        from nutmeg.v4.observation.recommendation_version import version_hash
        h1 = version_hash(parlay_fingerprints=["aaa"], odds_digest="o1")
        h2 = version_hash(parlay_fingerprints=["aaa"], odds_digest="o2")
        assert h1 != h2

    def test_pick_change_propagates(self):
        from nutmeg.v4.observation.recommendation_version import version_hash
        h1 = version_hash(parlay_fingerprints=["aaa"], odds_digest="o1")
        h2 = version_hash(parlay_fingerprints=["zzz"], odds_digest="o1")
        assert h1 != h2

    def test_empty_inputs_stable(self):
        from nutmeg.v4.observation.recommendation_version import version_hash
        h = version_hash()
        assert len(h) == 12


# ---------- Endpoint integration --------------------------------------

@pytest.fixture
def client():
    from nutmeg.v4.api import v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


class TestTodayEndpointVersionFields:
    """today-recommendations now emits version_hash + optional diff."""

    def test_response_has_version_hash(self, client, monkeypatch):
        from unittest.mock import patch
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=([], 0, 0)):
            r = client.post("/api/v4/today-recommendations", json={})
        assert r.status_code == 200
        body = r.json()
        assert "version_hash" in body
        # Even with 0 fixtures, the field is set (just hashes the empty input)
        assert body["version_hash"] is not None
        assert len(body["version_hash"]) == 12

    def test_no_diff_when_prev_omitted(self, client):
        from unittest.mock import patch
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=([], 0, 0)):
            r = client.post("/api/v4/today-recommendations", json={})
        assert r.json()["diff"] is None

    def test_no_diff_when_prev_matches_current(self, client):
        from unittest.mock import patch
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=([], 0, 0)):
            r1 = client.post("/api/v4/today-recommendations", json={})
            current = r1.json()["version_hash"]
            r2 = client.post("/api/v4/today-recommendations",
                             json={"prev_version": current})
        assert r2.json()["diff"] is None

    def test_diff_emitted_on_hash_mismatch(self, client):
        from unittest.mock import patch
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=([], 0, 0)):
            r = client.post("/api/v4/today-recommendations",
                            json={"prev_version": "deadbeef0000"})
        body = r.json()
        assert body["diff"] is not None
        d = body["diff"]
        assert d["prev_version"] == "deadbeef0000"
        assert d["current_version"] == body["version_hash"]
        assert "summary" in d


class TestSchemaVersionFields:
    """Confirm the new schema fields are present on the response models."""

    def test_today_response_has_version_hash_field(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsResponse
        assert "version_hash" in TodayRecommendationsResponse.model_fields
        assert "diff" in TodayRecommendationsResponse.model_fields

    def test_today_request_has_prev_version_field(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        assert "prev_version" in TodayRecommendationsRequest.model_fields

    def test_single_ticket_has_selection_fingerprint(self):
        from nutmeg.v4.api.schemas import SingleTicketResponse
        assert "selection_fingerprint" in SingleTicketResponse.model_fields

    def test_parlay_rec_has_selection_fingerprint(self):
        from nutmeg.v4.api.schemas import RecommendationResponse
        assert "selection_fingerprint" in RecommendationResponse.model_fields

    def test_pool_ticket_has_selection_fingerprint(self):
        from nutmeg.v4.api.schemas import PoolTicketResponse
        assert "selection_fingerprint" in PoolTicketResponse.model_fields

    def test_diff_schema_shape(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsDiff
        for f in ("prev_version", "current_version", "odds_changed",
                  "added_fingerprints", "removed_fingerprints", "summary"):
            assert f in TodayRecommendationsDiff.model_fields


# ---------- Dashboard wiring (Day 3) ----------------------------------

class TestDashboardDynamicRec:
    @pytest.fixture(scope="class")
    def html(self):
        from nutmeg.v4.api import v4_router
        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        c = TestClient(app)
        return c.get("/api/v4/dashboard").text

    def test_update_banner_element_present(self, html):
        assert 'id="today-update-banner"' in html
        assert 'id="today-update-banner-text"' in html
        assert 'id="today-update-banner-dismiss"' in html

    def test_banner_css_class_defined(self, html):
        for cls in (".update-banner", ".update-banner-icon",
                    ".update-banner-text", ".update-banner-dismiss"):
            assert cls in html

    def test_badge_updated_css_defined(self, html):
        assert ".badge-updated" in html
        assert ".card-rec.is-updated" in html

    def test_localstorage_keys_declared(self, html):
        assert "nutmeg.today.lastVersion" in html
        assert "nutmeg.today.lastFingerprints" in html

    def test_prev_version_sent_in_request(self, html):
        """JS body should conditionally include prev_version."""
        idx = html.index("async function loadTodayRecommendations")
        body = html[idx:idx+2500]
        assert "prev_version" in body
        assert "_readLastVersion" in body

    def test_collect_current_fingerprints_helper(self, html):
        assert "function _collectCurrentFingerprints" in html

    def test_renders_apply_is_updated_class(self, html):
        """All 3 today renders should reference is-updated + badge-updated."""
        for fn in ("renderTodaySingle", "renderTodayParlay", "renderTodayPool"):
            idx = html.index(f"function {fn}")
            body = html[idx:idx+4000]
            assert "is-updated" in body, f"{fn} doesn't apply .is-updated"
            assert "badge-updated" in body, f"{fn} doesn't render the updated badge"
            assert "isFingerprintChanged" in body, f"{fn} doesn't check changed set"

    def test_banner_show_hide_helpers(self, html):
        assert "function _showUpdateBanner" in html
        assert "function _hideUpdateBanner" in html

    def test_dismiss_button_wired(self, html):
        # Click listener attached
        assert "today-update-banner-dismiss" in html
        idx = html.index("today-update-banner-dismiss")
        # After the element + before end-of-script there should be an addEventListener
        # Check anywhere — it's bound via the _bannerDismiss element capture
        assert "_bannerDismiss" in html

    def test_i18n_keys_present_both_locales(self, html):
        for key in ("banner_updated", "badge_updated"):
            assert html.count(f"{key}:") >= 2, f"{key} not in both i18n dicts"
