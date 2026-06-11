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

    def test_cache_bumped(self):
        routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        assert "nutmeg-v45-fe-jcprefill" in routes
