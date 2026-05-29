"""post-v9 P1#14 — i18n (zh/en) + PWA shell tests.

The i18n part asserts:
 - I18N dict with zh + en keys (parity)
 - Language toggle button present
 - All static elements have data-i18n attributes
 - Dynamic strings use t() (status_recorded_req etc.)
 - localStorage persistence + browser-language detection wired
 - Default locale = zh; toggle button label flips

The PWA part asserts:
 - /api/v4/manifest.json valid + has required fields
 - /api/v4/sw.js returns service-worker JS
 - /api/v4/icon.svg returns SVG
 - dashboard.html links to manifest + icon + theme-color
 - dashboard.html registers service worker
"""
from __future__ import annotations

import json
import re
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


# ============ i18n =================================================

class TestI18nFrameworkPresent:
    def test_i18n_dict_defined(self, html):
        assert "const I18N = {" in html
        # Both locales present
        assert "  zh: {" in html
        assert "  en: {" in html

    def test_t_helper_defined(self, html):
        assert "function t(key)" in html
        assert "function applyI18n()" in html
        assert "function setLocale(loc)" in html
        assert "function initLocale()" in html

    def test_default_locale_is_zh(self, html):
        # Module-level let initialized to 'zh'
        assert "let _LOCALE = 'zh';" in html


class TestI18nDictionaryParity:
    """Every zh key must also appear in en (no missing translations)."""

    def _extract_locale_keys(self, html: str, locale: str) -> set:
        # Find  `<locale>: {` then collect keys until the matching `},`
        m = re.search(rf"\s+{locale}: \{{(.+?)\n  \}}", html, re.DOTALL)
        assert m, f"could not find {locale} block"
        body = m.group(1)
        # Each entry looks like `    key_name:  'value',`
        keys = set(re.findall(r"^\s+([a-z][a-z_0-9]*):\s+['\"]", body, re.MULTILINE))
        return keys

    def test_zh_and_en_have_same_keys(self, html):
        zh_keys = self._extract_locale_keys(html, "zh")
        en_keys = self._extract_locale_keys(html, "en")
        assert zh_keys, "zh keys empty (parser broken?)"
        missing_in_en = zh_keys - en_keys
        missing_in_zh = en_keys - zh_keys
        assert not missing_in_en, f"keys in zh but not en: {sorted(missing_in_en)}"
        assert not missing_in_zh, f"keys in en but not zh: {sorted(missing_in_zh)}"

    def test_at_least_50_keys_translated(self, html):
        """Sanity floor — we translated ~60 strings; if accidentally
        truncated to 5 something is very wrong."""
        zh_keys = self._extract_locale_keys(html, "zh")
        assert len(zh_keys) >= 50, f"only {len(zh_keys)} keys — too few"


class TestI18nMarkup:
    def test_lang_toggle_button(self, html):
        assert 'id="lang-toggle"' in html

    def test_tab_buttons_marked(self, html):
        # V11 P1-FE#1 removed 4 engineer tabs (outcomes/roi/sessions/rules).
        # P1-FE#3 added 推荐追溯 (history). 6 tabs all carry data-i18n.
        for key in ("tab_today", "tab_wc", "tab_single", "tab_parlay",
                    "tab_pool", "tab_history"):
            assert f'data-i18n="{key}"' in html, f"tab missing data-i18n={key}"

    def test_section_headings_marked(self, html):
        # V11 P1-FE#1: removed h_outcomes / h_roi / h_sessions / h_rules.
        # Retained tabs' headings still carry data-i18n.
        for key in ("h_single_rec", "h_parlay_rec", "h_pool_rec"):
            assert f'data-i18n="{key}"' in html, f"heading missing data-i18n={key}"

    def test_textareas_have_i18n_attr_aria(self, html):
        # All 3 JSON textareas use data-i18n-attr for aria-label
        for key in ("aria_single_json", "aria_parlay_json", "aria_pool_json"):
            assert key in html

    def test_predictions_table_headers_marked(self, html):
        # 10 columns must all be i18n'd
        for key in ("th_match", "th_lambda_home", "th_lambda_away",
                    "th_p_home", "th_p_draw", "th_p_away",
                    "th_handicap", "th_p_hc_home", "th_p_hc_draw", "th_p_hc_away"):
            assert f'data-i18n="{key}"' in html, f"predictions header missing: {key}"


class TestI18nWiring:
    def test_init_locale_called_at_startup(self, html):
        # initLocale() invoked in init section
        # It must appear AFTER its definition
        idx_def = html.index("function initLocale()")
        # Two occurrences expected (definition + invocation in init block)
        assert html.count("initLocale()") >= 2
        # Last occurrence is in init section (after definition)
        idx_last = html.rfind("initLocale()")
        assert idx_last > idx_def

    def test_lang_toggle_handler_wired(self, html):
        # Click handler on lang-toggle
        assert "$('#lang-toggle').addEventListener('click'" in html
        assert "setLocale(_LOCALE === 'zh' ? 'en' : 'zh')" in html

    def test_localstorage_key_used(self, html):
        assert "'nutmeg.locale'" in html

    def test_dynamic_status_messages_use_t(self, html):
        # V11 P1-FE#1: status_submitting was in the outcomes-tab JS, now
        # removed. Remaining i18n status keys must still be called via t().
        for key in ("status_computing", "status_pool_compute",
                    "status_recorded_req", "status_recorded_db",
                    "status_not_recorded"):
            assert f"t('{key}')" in html, f"missing t() call for {key}"


# ============ PWA shell ============================================

class TestManifestEndpoint:
    def test_returns_200(self, client):
        r = client.get("/api/v4/manifest.json")
        assert r.status_code == 200

    def test_correct_content_type(self, client):
        r = client.get("/api/v4/manifest.json")
        # FastAPI returns "application/manifest+json"
        assert "manifest" in r.headers["content-type"]

    def test_has_required_pwa_fields(self, client):
        r = client.get("/api/v4/manifest.json")
        m = r.json()
        for field in ("name", "short_name", "start_url", "scope",
                      "display", "theme_color", "background_color", "icons"):
            assert field in m, f"manifest missing field: {field}"

    def test_display_standalone(self, client):
        m = client.get("/api/v4/manifest.json").json()
        assert m["display"] == "standalone"

    def test_start_url_points_to_dashboard(self, client):
        m = client.get("/api/v4/manifest.json").json()
        assert m["start_url"] == "/api/v4/dashboard"
        assert m["scope"] == "/api/v4/"

    def test_icons_have_src(self, client):
        m = client.get("/api/v4/manifest.json").json()
        assert len(m["icons"]) >= 1
        for icon in m["icons"]:
            assert "src" in icon
            assert icon["src"].startswith("/api/v4/")


class TestIconEndpoint:
    def test_svg_returned(self, client):
        r = client.get("/api/v4/icon.svg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/svg+xml"
        assert r.text.startswith("<svg")


class TestServiceWorkerEndpoint:
    def test_returns_javascript(self, client):
        r = client.get("/api/v4/sw.js")
        assert r.status_code == 200
        assert "javascript" in r.headers["content-type"]

    def test_has_install_activate_fetch_handlers(self, client):
        body = client.get("/api/v4/sw.js").text
        assert "addEventListener('install'" in body
        assert "addEventListener('activate'" in body
        assert "addEventListener('fetch'" in body

    def test_caches_shell_urls(self, client):
        body = client.get("/api/v4/sw.js").text
        for url in ("/api/v4/dashboard", "/api/v4/manifest.json", "/api/v4/icon.svg"):
            assert url in body, f"SW doesn't cache {url}"

    def test_versioned_cache(self, client):
        body = client.get("/api/v4/sw.js").text
        # Versioned cache name lets us force refresh on shell updates
        assert "CACHE_VERSION" in body
        # Old caches deleted on activate
        assert "caches.delete" in body

    def test_dashboard_is_network_first(self, client):
        # V12 W4 — the dashboard shell switched cache-first → network-first so
        # a shipped dashboard.html update shows on the next normal reload (the
        # old cache-first served the stale page until a manual hard-refresh).
        # manifest + icon stay cache-first (truly static).
        body = client.get("/api/v4/sw.js").text
        assert "STATIC_SHELL" in body                      # static assets cache-first
        assert "Network-first for the dashboard" in body   # dashboard network-first branch


class TestDashboardLinksToPWA:
    def test_manifest_link(self, html):
        assert '<link rel="manifest" href="/api/v4/manifest.json">' in html

    def test_theme_color_meta(self, html):
        # V11 P1-FE#1: theme-color updated from indigo (#4f46e5) to new
        # premium dark base (#0a0e1a). Either is acceptable.
        assert ('<meta name="theme-color" content="#0a0e1a">' in html
                or '<meta name="theme-color" content="#4f46e5">' in html)

    def test_icon_link(self, html):
        assert '/api/v4/icon.svg' in html

    def test_apple_touch_icon(self, html):
        # iOS Safari needs this for Add-to-Home-Screen
        assert 'apple-touch-icon' in html

    def test_sw_registered(self, html):
        assert "serviceWorker.register('/api/v4/sw.js'" in html
        # Scoped to /api/v4/ (not entire origin)
        assert "scope: '/api/v4/'" in html
