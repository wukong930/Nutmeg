"""V11 post-ship — Path A++ WC handicap recommendation dashboard tests.

Verifies that the new 让球推荐 inline section is wired into the WC tab:
  - renderWcHandicapSection helper exists with both states (form + warning)
  - All form inputs have correct data-fld names so _wcHcCalc reads them
  - Click handler is bound via event delegation
  - i18n keys are present in BOTH zh + en locales (parity)
  - SW cache version was bumped (forces refresh on existing PWA installs)

Lightweight — only checks HTML/JS substring presence; no Playwright.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    from nutmeg.v4.api import v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


@pytest.fixture(scope="module")
def html(client):
    r = client.get("/api/v4/dashboard")
    assert r.status_code == 200
    return r.text


@pytest.fixture(scope="module")
def sw_js(client):
    r = client.get("/api/v4/sw.js")
    assert r.status_code == 200
    return r.text


# ============ Renderer + handler wiring =================================

class TestRendererPresent:

    def test_renderwcmatch_calls_handicap_section(self, html):
        """The base WC card should invoke the new handicap section."""
        assert "renderWcHandicapSection(p)" in html

    def test_handicap_section_function_defined(self, html):
        assert "function renderWcHandicapSection(p)" in html

    def test_form_includes_handicap_line_input(self, html):
        """data-fld names must match what _wcHcCalc reads."""
        assert 'data-fld="handicap_home"' in html

    def test_form_includes_three_sp_inputs(self, html):
        for fld in ("odds_h", "odds_d", "odds_a"):
            assert f'data-fld="{fld}"' in html

    def test_calc_button_has_meta_attribute(self, html):
        """meta passes fixture_id + Pinnacle 1X2 to the handler."""
        assert "wc-hc-calc-btn" in html
        assert 'data-meta=' in html

    def test_no_pinnacle_warning_branch_present(self, html):
        """When has_pinnacle=false, show warning instead of form."""
        assert "if (!p.has_pinnacle)" in html
        assert "wc_hc_needs_pin" in html

    def test_calc_handler_defined(self, html):
        assert "async function _wcHcCalc(btn)" in html

    def test_calc_handler_posts_to_endpoint(self, html):
        # The handler must POST to /recommend/wc/single
        assert "/recommend/wc/single" in html
        assert "method: 'POST'" in html

    def test_event_delegation_wired(self, html):
        """The button is dynamic — needs delegation, not direct binding."""
        assert "e.target.closest('.wc-hc-calc-btn')" in html

    def test_outcome_row_renderer_present(self, html):
        """Per-outcome row (让胜/让平/让负) renderer."""
        assert "_wcHcOutcomeRow" in html

    def test_handicap_validation_present(self, html):
        """Client-side guard against odds <= 1.0."""
        assert "SP 必须 > 1.0" in html or "v > 1.0" in html


# ============ i18n parity ==============================================

class TestI18nKeys:
    """Both zh + en locales must have the same 6 new keys."""

    REQUIRED_KEYS = (
        "wc_hc_toggle",
        "wc_hc_needs_pin",
        "wc_hc_line",
        "wc_hc_sp_h",
        "wc_hc_sp_d",
        "wc_hc_sp_a",
        "wc_hc_calc",
    )

    def test_all_keys_in_zh(self, html):
        # Crude — count "wc_hc_*:" occurrences. zh and en each get one.
        for key in self.REQUIRED_KEYS:
            assert f"{key}:" in html, f"missing key {key}"

    def test_each_key_appears_at_least_twice(self, html):
        """One occurrence in zh + one in en = each key shows ≥2 times."""
        for key in self.REQUIRED_KEYS:
            assert html.count(f"{key}:") >= 2, (
                f"{key} appears < 2 times — i18n parity broken"
            )

    def test_zh_label_format(self, html):
        """Spot-check Chinese label content."""
        assert "让球推荐 (Path A++)" in html  # toggle
        assert "让胜 SP" in html
        assert "让平 SP" in html
        assert "让负 SP" in html

    def test_en_label_format(self, html):
        """Spot-check English label content."""
        assert "Handicap recommendation (Path A++)" in html
        assert "Home SP" in html
        assert "Draw SP" in html
        assert "Away SP" in html


# ============ Service worker cache busted ==============================

class TestSwCacheBust:
    def test_cache_version_bumped(self, sw_js):
        """When dashboard.html changes, CACHE_VERSION must change so PWA
        clients pick up the new version. v11-fe-wc-handicap was set
        when this feature shipped."""
        import re
        # Pattern: nutmeg-vN-fe-something — the something must reference wc/handicap.
        m = re.search(r"'(nutmeg-v\d+-fe-[a-z0-9-]+)'", sw_js)
        assert m is not None, "CACHE_VERSION constant missing"
        version = m.group(1)
        # The current ship is wc-handicap — match prefix loosely so a later
        # bump (e.g. nutmeg-v11-fe-wc-handicap-2) still passes.
        assert "wc-handicap" in version, (
            f"CACHE_VERSION = {version!r} doesn't mention wc-handicap"
        )


# ============ V11 post-ship — Today WC block ==========================

class TestTodayWcBlock:
    """Today's recommendations tab surfaces a 🏆 WC section when the
    today endpoint returns body.wc populated."""

    def test_today_section_div_present(self, html):
        assert 'id="today-wc-section"' in html
        assert 'id="today-wc-count"' in html
        assert 'id="today-wc-list"' in html

    def test_render_function_defined(self, html):
        assert "function renderTodayWc(wc)" in html

    def test_render_called_in_today_load(self, html):
        # Hook into the existing load pipeline alongside single/parlay/pool
        assert "renderTodayWc(body.wc)" in html

    def test_deeplink_to_wc_tab(self, html):
        # CTA button uses data-tab-link="wc" which the existing handler
        # picks up to switch the active tab.
        assert 'data-tab-link="wc"' in html
        # i18n key for the CTA copy
        assert "today_wc_cta" in html

    def test_pinnacle_required_indicator(self, html):
        """Cards render a "需 Pinnacle 盘口" badge when has_pinnacle=false."""
        assert "today_wc_no_pin" in html
        assert "today_wc_blend_ready" in html

    def test_error_path_hides_section(self, html):
        """On today error, the WC section is hidden alongside others."""
        # Look for the cleanup line we added
        assert "$('#today-wc-section').classList.add('hidden')" in html


# ============ V11 post-ship — record-session checkbox =================

class TestRecordSessionCheckbox:
    """WC handicap form now has the same opt-in observation checkbox
    as single/parlay/pool — both env + flag required for an actual write."""

    def test_checkbox_in_handicap_form(self, html):
        assert "wc-hc-record-session" in html

    def test_record_session_flag_in_request_body(self, html):
        """The JS must pass record_session: recordChecked into the POST."""
        assert "record_session: recordChecked," in html

    def test_label_uses_shared_i18n_key(self, html):
        """Reuse lbl_record_session (already in both locales) instead of
        defining a new key — keeps the dictionary lean."""
        # The existing key is present (used by 4 forms now)
        assert "lbl_record_session" in html


# ============ V11 post-ship — Today WC i18n parity ====================

class TestTodayWcI18n:
    REQUIRED_KEYS = (
        "h_today_wc",
        "today_wc_hint",
        "today_wc_cta",
        "today_wc_blend_ready",
        "today_wc_no_pin",
    )

    def test_each_key_present_twice(self, html):
        """Each new key must appear in both zh + en locales."""
        for key in self.REQUIRED_KEYS:
            count = html.count(f"{key}:")
            assert count >= 2, (
                f"{key} appears {count}x — i18n parity broken (zh+en expected)"
            )
