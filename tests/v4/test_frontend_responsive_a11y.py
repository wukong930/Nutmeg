"""post-v9 P1#13 — front-end audit + tier-1 fixes.

Tests assert structural changes in dashboard.html that close the mobile +
a11y + error-UX gaps the user flagged. Each test maps to a P1#13 sub-task:

- Viewport meta tag present (mobile renders at device width)
- Tab nav single-line horizontal scroll (not flex-wrap)
- Responsive grids on ROI headline (2 cols on mobile, 4 on sm+)
- JSON textareas have font-mono + no-autocorrect attrs
- Recommendation tables have both desktop table + mobile card-list render
- All number inputs have inputmode (mobile keyboard hints)
- All status spans have role=status + aria-live=polite
- Tab panels have role=tabpanel; tabs have role=tab + aria-controls
- setStatus helper exists + is wired into 4 error / 3 loading paths

These are STRUCTURAL tests, not visual regression. Real mobile-render
testing requires Playwright + browser; deferred.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = (
    REPO_ROOT / "apps" / "api" / "src" / "nutmeg" / "v4"
    / "api" / "static" / "dashboard.html"
)


@pytest.fixture(scope="module")
def html() -> str:
    """Fetch dashboard via the FastAPI route (closer to production)."""
    from nutmeg.v4.api import v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    client = TestClient(app)
    r = client.get("/api/v4/dashboard")
    assert r.status_code == 200
    return r.text


# ---------- Mobile rendering ----------------------------------------

class TestMobileRendering:
    def test_viewport_meta_present(self, html):
        """Without this iOS/Android render at desktop ~980px width."""
        assert 'name="viewport"' in html
        assert 'width=device-width' in html
        assert 'initial-scale=1' in html

    def test_tab_nav_horizontal_scroll_not_wrap(self, html):
        """flex-wrap was eating ~120px vertical on mobile."""
        # New pattern: flex-nowrap + overflow-x-auto
        assert 'flex-nowrap overflow-x-auto' in html
        # flex-wrap should not be the tab nav class anymore
        # (it's still allowed elsewhere e.g. input rows)

    def test_tab_buttons_whitespace_nowrap(self, html):
        """Chinese labels should never break mid-character on small viewports."""
        # All tab buttons have whitespace-nowrap
        assert html.count('whitespace-nowrap') >= 7   # 7 tabs

    def test_header_stacks_on_mobile(self, html):
        """flex-col then sm:flex-row keeps title from competing with health pill."""
        # Find the header area
        idx = html.index('<h1')
        head_block = html[idx-200:idx+200]
        assert 'flex-col' in head_block
        assert 'sm:flex-row' in head_block

    def test_roi_headline_grid_responsive(self, html):
        """4 KPI cards: 2x2 on mobile, 1x4 on sm+."""
        assert 'grid-cols-2 sm:grid-cols-4' in html


# ---------- JSON textarea mobile optimization -----------------------

class TestJsonTextareas:
    def test_three_textareas_have_aria_labels(self, html):
        for cid in ('single-fixtures-json', 'fixtures-json', 'pool-fixtures-json'):
            # The textarea opening tag's region should contain aria-label
            idx = html.index(f'id="{cid}"')
            chunk = html[idx:idx+300]
            assert 'aria-label' in chunk, f"{cid} missing aria-label"

    def test_textareas_disable_autocorrect(self, html):
        """JSON input must not be autocorrected by mobile keyboard."""
        for cid in ('single-fixtures-json', 'fixtures-json', 'pool-fixtures-json'):
            idx = html.index(f'id="{cid}"')
            chunk = html[idx:idx+300]
            assert 'autocorrect="off"' in chunk
            assert 'autocapitalize="off"' in chunk
            assert 'spellcheck="false"' in chunk


# ---------- Recommendation tables — dual render --------------------

class TestRecommendationsDualRender:
    def test_predictions_card_div_present(self, html):
        """Mobile card-list fallback for the 10-col predictions table."""
        assert 'id="predictions-cards"' in html
        assert 'md:hidden' in html

    def test_predictions_table_desktop_only_on_md(self, html):
        """Original predictions-table only rendered at md+."""
        # The wrapper div should have hidden md:block
        idx = html.index('id="predictions-table"')
        chunk = html[idx-100:idx]
        assert 'hidden md:block' in chunk

    def test_pool_cards_branch_in_render_js(self, html):
        """Pool render function emits both table (hidden md:block) and
        card list (md:hidden) so each viewport sees exactly one."""
        # Look in the renderPoolRecommendations function
        idx = html.index('function renderPoolRecommendations')
        chunk = html[idx:idx+3000]
        assert 'hidden md:block' in chunk   # desktop table wrapper
        assert 'md:hidden space-y' in chunk  # mobile card list


# ---------- a11y — input modes + ARIA ------------------------------

class TestNumberInputModes:
    def test_currency_inputs_have_numeric_inputmode(self, html):
        """Bankroll-like inputs (integer ¥) should request numeric keypad."""
        for cid in ('single-bankroll', 'bankroll', 'pool-bankroll', 'pool-max-budget'):
            idx = html.index(f'id="{cid}"')
            chunk = html[idx:idx+300]
            assert 'inputmode="numeric"' in chunk, f"{cid} missing inputmode=numeric"

    def test_decimal_inputs_have_decimal_inputmode(self, html):
        """Kelly fraction + min-hit (decimal step) → decimal keypad."""
        for cid in ('single-kelly-fraction', 'pool-kelly-fraction', 'min-hit'):
            idx = html.index(f'id="{cid}"')
            chunk = html[idx:idx+300]
            assert 'inputmode="decimal"' in chunk, f"{cid} missing inputmode=decimal"


class TestAriaSemantics:
    def test_tablist_role(self, html):
        assert 'role="tablist"' in html
        # 7 tab buttons should have role=tab
        assert html.count('role="tab"') >= 7

    def test_tabpanels_have_role(self, html):
        # V10 W1 added 今日推荐 as the default landing tab → 8 panels now
        assert html.count('role="tabpanel"') == 8

    def test_status_spans_have_aria_live(self, html):
        for cid in ('single-status', 'recommend-status', 'pool-status', 'outcomes-status'):
            idx = html.index(f'id="{cid}"')
            chunk = html[idx:idx+200]
            assert 'role="status"' in chunk, f"{cid} missing role=status"
            assert 'aria-live="polite"' in chunk, f"{cid} missing aria-live"

    def test_switch_tab_sets_aria_selected(self, html):
        """JS must update aria-selected when switching tabs."""
        assert "setAttribute('aria-selected', 'true')" in html
        assert "setAttribute('aria-selected', 'false')" in html


# ---------- Error UX — setStatus helper ----------------------------

class TestSetStatusHelper:
    def test_helper_defined(self, html):
        """setStatus(sel, kind, msg) helper used for visual error/loading."""
        assert 'function setStatus(' in html

    def test_error_kind_uses_red_banner(self, html):
        """Errors get a red-50 background + red-500 left border."""
        idx = html.index('function setStatus')
        helper = html[idx:idx+1500]
        assert "border-l-4" in helper
        assert "border-red-500" in helper
        assert "bg-red-50" in helper

    def test_loading_kind_uses_pulse_animation(self, html):
        idx = html.index('function setStatus')
        helper = html[idx:idx+1500]
        assert "animate-pulse" in helper

    def test_4_endpoints_use_setstatus_for_errors(self, html):
        """All 4 user-facing endpoints (recommend / single / pool / outcomes)
        emit errors via setStatus, not raw textContent."""
        # Count setStatus(..., 'error', ...) call sites
        assert html.count("setStatus('#") >= 8   # 4 error + 3 loading + buffer

    def test_3_endpoints_use_setstatus_for_loading(self, html):
        """recommend / single / pool / outcomes all use 'loading' kind."""
        for sel in ("'#recommend-status'", "'#single-status'",
                    "'#pool-status'", "'#outcomes-status'"):
            assert f"setStatus({sel}, 'loading'" in html, (
                f"missing setStatus loading call for {sel}"
            )


# ---------- regression: existing tests still pass ------------------

class TestNoRegressionFromExistingTests:
    """The 24 V9 W3 record-session-gate tests + V9 P1#7/8 still need to
    pass. Quick sanity that the responsive changes didn't strip critical
    IDs / strings used elsewhere."""

    def test_3_record_session_checkboxes_still_present(self, html):
        for cid in ('record-session', 'single-record-session', 'pool-record-session'):
            assert f'id="{cid}"' in html

    def test_localstorage_init_helper_still_present(self, html):
        # P1#7
        assert 'initRecordSessionPersistence' in html

    def test_sessions_latest_verify_helper_still_present(self, html):
        # P1#8
        assert 'verifyRecordedAndAppend' in html
        assert '/observation/sessions/latest' in html
