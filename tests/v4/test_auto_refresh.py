"""V11 P1-FE#6 — tests for the dashboard's auto-refresh wiring.

The polling itself runs in the browser (setInterval + Visibility API),
so these are structural tests against the served HTML:
  - Stale-indicator element + i18n keys present
  - Helper functions defined with the expected names
  - Visibility / tab switching hooks wired
  - SW cache version bumped
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def html():
    from nutmeg.v4.api import v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app).get("/api/v4/dashboard").text


class TestStaleIndicatorElement:
    def test_element_present(self, html):
        assert 'id="today-stale"' in html

    def test_placed_near_refresh(self, html):
        """Stale label and refresh button should be in the same flex container."""
        # The chunk between the stale span and the refresh button is short
        idx_stale = html.index('id="today-stale"')
        idx_refresh = html.index('id="today-refresh"')
        assert abs(idx_refresh - idx_stale) < 500, "stale label not adjacent to refresh button"


class TestPollingConstants:
    def test_interval_constant_defined(self, html):
        assert "TODAY_POLL_INTERVAL_MS" in html

    def test_stale_tick_constant_defined(self, html):
        assert "TODAY_STALE_TICK_MS" in html

    def test_interval_is_60s_default(self, html):
        """Picks rarely move faster than 1 minute — 60s default."""
        # Allow either 60000 or 60_000 numeric literal forms
        assert ("60_000" in html) or ("60000" in html)


class TestVisibilityHook:
    def test_visibilitychange_listener_registered(self, html):
        assert "visibilitychange" in html

    def test_should_auto_poll_helper(self, html):
        assert "function _shouldAutoPoll" in html

    def test_helpers_defined(self, html):
        for name in ("_startTodayPolling", "_stopTodayPolling",
                     "_renderStaleLabel", "_formatStale"):
            assert f"function {name}" in html, f"missing helper {name}"


class TestSwitchTabHook:
    def test_switchtab_wrapped(self, html):
        """The polling wiring wraps switchTab via _origSwitchTab capture."""
        assert "_origSwitchTab" in html

    def test_only_polls_when_today_active(self, html):
        idx = html.index("_origSwitchTab")
        block = html[idx:idx+800]
        # When name === 'today' → start polling; else stop
        assert "'today'" in block
        assert "_startTodayPolling" in block
        assert "_stopTodayPolling" in block


class TestLoadTodayWrapped:
    def test_loadtoday_wrapped_for_timestamp(self, html):
        """loadTodayRecommendations is wrapped so every call updates the
        _todayLastLoadAt timestamp + re-renders the stale label."""
        assert "_origLoadToday" in html
        idx = html.index("_origLoadToday")
        block = html[idx:idx+500]
        assert "_todayLastLoadAt" in block
        assert "_renderStaleLabel" in block


class TestI18nStaleKeys:
    def test_keys_present_both_locales(self, html):
        for key in ("stale_just_now", "stale_seconds_ago",
                    "stale_minutes_ago", "stale_hours_ago"):
            assert html.count(f"{key}:") >= 2, f"{key} missing from either zh or en"

    def test_zh_uses_chinese(self, html):
        # 页面刚刚刷新 is the zh value for stale_just_now (体检 Wave3 — the label
        # names the PAGE refresh time, not the odds time).
        assert "页面刚刚刷新" in html


class TestSWCacheBumped:
    def test_sw_cache_is_a_v_prefixed_version(self, html):
        """Force browsers to re-fetch the dashboard. We bump CACHE_VERSION
        with every P1-FE patch — the specific tag changes per ship, but
        the 'nutmeg-vN-fe-…' prefix is the durable convention."""
        from nutmeg.v4.api import v4_router
        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        sw = TestClient(app).get("/api/v4/sw.js").text
        import re as _re
        m = _re.search(r"'(nutmeg-v\d+-fe-[a-z0-9\-]+)'", sw)
        assert m is not None, "no 'nutmeg-vN-fe-…' CACHE_VERSION found in sw.js"


class TestFormatStaleLogic:
    """The _formatStale function is pure JS — sanity-check via regex
    that it covers all four time buckets (<5s, <60s, <60m, ≥60m)."""

    def test_all_buckets_referenced(self, html):
        idx = html.index("function _formatStale")
        body = html[idx:idx+800]
        for key in ("stale_just_now", "stale_seconds_ago",
                    "stale_minutes_ago", "stale_hours_ago"):
            assert key in body, f"_formatStale doesn't use {key}"
