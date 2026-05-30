"""V12 W8 — WC handicap unified into 市场模式 (was: Path A++ inline form).

History
-------
V11 post-ship shipped a per-fixture Path A++ 让球推荐 form inside each WC
card: enter an integer line + 3 竞彩 SP → POST ``/recommend/wc/single`` →
model-vs-market Bayesian blend. V12 W8 retired that path. A leakage-free
walk-forward (4330 EU matches, 24/25) measured pure **market-reverse**
(de-vig Pinnacle 1X2 + O/U(2.5) → Dixon-Coles grid → read the let-line)
at 0.20452 AH-cover Brier — sitting on Pinnacle's own AH ceiling (0.20444)
and beating the fair model (0.20690) by 2.4e-3. WC/EURO/WC_QUAL_UEFA are
in ``_CUP_MARKET_COMPETITIONS``, so 市场模式 already prices their 让球 that
way. Path A++ also blended *toward* the 竞彩 SP, shrinking any real edge.

So the WC tab now:
  - keeps its 1X2 pre-line forecast (``renderWcMatch`` / ``loadWcPredictions``)
  - replaces the 让球 section with a redirect button into 市场模式
  - the old form renderer + ``_wcHcCalc`` / ``_wcHcOutcomeRow`` JS and the
    ``wc_hc_toggle`` / ``wc_hc_line`` / ``wc_hc_sp_*`` / ``wc_hc_calc`` /
    ``wc_hc_needs_pin`` i18n keys were deleted.

These tests pin the new redirect + guard the dead artifacts from creeping
back. Lightweight — HTML/JS substring checks, no Playwright.
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


# ============ Renderer still wired into the WC card ====================

class TestRendererPresent:

    def test_renderwcmatch_calls_handicap_section(self, html):
        """The base WC card still invokes the handicap section (now a redirect)."""
        assert "renderWcHandicapSection(p)" in html

    def test_handicap_section_function_defined(self, html):
        assert "function renderWcHandicapSection(p)" in html


# ============ Section is now a redirect into 市场模式 ==================

class TestHandicapRedirect:
    """The 让球 section renders a hint + a button that jumps to 市场模式
    (the 今日推荐 tab's 国际盘口 board) instead of an inline Path A++ form."""

    def test_redirect_copy_present(self, html):
        assert 'data-i18n="wc_hc_moved"' in html
        assert 'data-i18n="wc_hc_goto_market"' in html

    def test_redirect_button_loads_market_mode(self, html):
        """The button switches to 今日推荐 and triggers loadCupMarket()."""
        assert "switchTab('today'); setTimeout(loadCupMarket, 150);" in html

    def test_old_path_a_form_artifacts_removed(self, html):
        """Guardrail — the retired Path A++ form must not creep back."""
        for dead in (
            'data-fld="handicap_home"',
            'data-fld="odds_h"',
            "wc-hc-calc-btn",
            "wc-hc-record-session",
            "function _wcHcCalc",
            "function _wcHcOutcomeRow",
        ):
            assert dead not in html, f"retired Path A++ artifact resurfaced: {dead}"

    def test_no_live_fetch_to_deprecated_endpoint(self, html):
        """No client code may POST to the deprecated /recommend/wc/single.
        (A doc comment may *name* it, but there must be no fetch template.)"""
        assert "${API}/recommend/wc/single" not in html


# ============ i18n: only the 2 redirect keys remain ===================

class TestRedirectI18nKeys:
    """Both zh + en locales keep exactly the redirect keys; the old form
    keys are gone."""

    REDIRECT_KEYS = ("wc_hc_moved", "wc_hc_goto_market")
    RETIRED_KEYS = (
        "wc_hc_toggle", "wc_hc_needs_pin", "wc_hc_line",
        "wc_hc_sp_h", "wc_hc_sp_d", "wc_hc_sp_a", "wc_hc_calc",
    )

    def test_redirect_keys_present_twice(self, html):
        """One occurrence in zh + one in en = each key shows ≥2 times."""
        for key in self.REDIRECT_KEYS:
            assert html.count(f"{key}:") >= 2, (
                f"{key} appears < 2 times — i18n parity broken"
            )

    def test_retired_form_keys_absent(self, html):
        """The orphaned Path A++ form keys were removed from both locales."""
        for key in self.RETIRED_KEYS:
            assert f"{key}:" not in html, (
                f"retired i18n key {key} still defined — cleanup regressed"
            )


# ============ Service worker cache busted ==============================

class TestSwCacheBust:
    def test_cache_version_bumped(self, sw_js):
        """The service-worker CACHE_VERSION must follow the
        ``nutmeg-vN-fe-<slug>`` convention so PWA clients pick up new builds.

        We assert the FORMAT, not a specific feature slug. The slug changes
        on every frontend deploy by design — pinning it to one feature name
        made this test break on each later bump."""
        import re
        m = re.search(r"'(nutmeg-v\d+-fe-[a-z0-9-]+)'", sw_js)
        assert m is not None, (
            "CACHE_VERSION missing or not in 'nutmeg-vN-fe-<slug>' form"
        )
        version = m.group(1)
        slug = version.split("-fe-", 1)[1]
        assert slug and re.fullmatch(r"[a-z0-9-]+", slug), (
            f"CACHE_VERSION {version!r} has an empty / invalid kebab-case slug"
        )


# ============ Today's recommendations — 🏆 WC block ===================

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

    def test_deeplink_to_market_mode(self, html):
        """V12 W8 — the WC card CTA used to deep-link to the WC tab
        (data-tab-link="wc"); it now jumps to 市场模式 via loadCupMarket so
        the user reads WC 让球 the same way as every other competition."""
        assert "today-wc-deeplink" in html
        assert 'data-tab-link="wc"' not in html
        assert "setTimeout(loadCupMarket, 150);" in html
        assert "today_wc_cta" in html

    def test_pinnacle_required_indicator(self, html):
        """Cards render a "需 Pinnacle 盘口" badge when has_pinnacle=false."""
        assert "today_wc_no_pin" in html
        assert "today_wc_blend_ready" in html

    def test_error_path_hides_section(self, html):
        """On today error, the WC section is hidden alongside others."""
        assert "$('#today-wc-section').classList.add('hidden')" in html


# ============ Today WC i18n parity ====================================

class TestTodayWcI18n:
    REQUIRED_KEYS = (
        "h_today_wc",
        "today_wc_hint",
        "today_wc_cta",
        "today_wc_blend_ready",
        "today_wc_no_pin",
    )

    def test_each_key_present_twice(self, html):
        """Each key must appear in both zh + en locales."""
        for key in self.REQUIRED_KEYS:
            count = html.count(f"{key}:")
            assert count >= 2, (
                f"{key} appears {count}x — i18n parity broken (zh+en expected)"
            )
