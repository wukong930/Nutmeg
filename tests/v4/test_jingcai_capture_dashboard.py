"""体检 — silent 竞彩 SP staleness capture wired into the spcalc recompute."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestJingcaiCapture:
    def test_helper_defined(self, html):
        assert "function _jcStaleCapture(" in html

    def test_wired_into_both_modes(self, html):
        # 标准模式 (_SPCALC/_spcalcRecalc) AND 市场模式 (_CUPMKT/_cupRecalc) both
        # capture every pre-kickoff re-price
        assert "_jcStaleCapture(_SPCALC.preds[idx], 'spcalc-sp'" in html
        assert "_jcStaleCapture(_CUPMKT.preds[idx], 'cupsp'" in html

    def test_handicap_wired_both_modes(self, html):
        # 让球 (hhad) capture wired into both boards' handicap recompute
        assert "function _jcStaleCaptureHc(" in html
        assert "_jcStaleCaptureHc(_SPCALC.preds[idx], 'spcalc-hcsp'" in html
        assert "_jcStaleCaptureHc(_CUPMKT.preds[idx], 'cuphcsp'" in html
        assert "market: 'hhad', handicap_home: line" in html

    def test_posts_to_endpoint(self, html):
        assert "/observation/jingcai-sp" in html

    def test_debounced_and_silent(self, html):
        assert "_jcCapT" in html and "setTimeout" in html  # debounced
        assert ".catch(() => {})" in html                  # fire-and-forget

    def test_only_complete_1x2_captured(self, html):
        assert "if (!(oh && od && oa)) return;" in html

    def test_skips_official_prefill(self, html):
        # Render pre-fills the input with the attached 竞彩 SP; re-capturing it as
        # market_mode re-stamps the official feed (the "🎯 refreshed but didn't
        # update" bug). Only a genuine override (value ≠ attached) may write.
        assert "_eq(oh, pr.jc_home) && _eq(od, pr.jc_draw) && _eq(oa, pr.jc_away)) return;" in html
        assert "line === pr.jc_hc_line && _eq(oh, pr.jc_hc_home)" in html

    def test_cache_bumped(self):
        routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        assert "nutmeg-v50-fe-versionbanner" in routes
