"""WC blocks that survive in 今日推荐 (today's recommendations) + SW cache-bust.

History
-------
The standalone 🏆 WC 2026 prediction tab (1X2 forecast cards + a 让球 redirect
into 市场模式) was removed in the V14 真-EV-board cleanup, along with its
``renderWcMatch`` / ``renderWcHandicapSection`` renderers and every WC-tab i18n
key (``tab_wc`` / ``h_wc_*`` / ``wc_hc_*`` / ``wc_lookahead_*`` …). The earlier
``TestRendererPresent`` / ``TestHandicapRedirect`` / ``TestRedirectI18nKeys``
classes pinned those now-deleted artifacts and were removed with them.

What remains — and what these tests still guard:
  - the 🏆 WC section inside 今日推荐 (``renderTodayWc`` / ``today-wc-*`` ids),
    which deep-links 让球 to 市场模式 like every other competition;
  - its i18n keys (``h_today_wc`` / ``today_wc_*``), zh + en parity;
  - the service-worker ``CACHE_VERSION`` format (PWA cache-bust on deploy).

Lightweight — HTML/JS substring checks, no Playwright.
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
