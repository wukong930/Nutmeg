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

    def test_wired_into_recalc(self, html):
        # called from _spcalcRecalc so every pre-kickoff re-price is captured
        assert "_jcStaleCapture(idx)" in html

    def test_posts_to_endpoint(self, html):
        assert "/observation/jingcai-sp" in html

    def test_debounced_and_silent(self, html):
        assert "_jcCapT" in html and "setTimeout" in html  # debounced
        assert ".catch(() => {})" in html                  # fire-and-forget

    def test_only_complete_1x2_captured(self, html):
        assert "if (!(oh && od && oa)) return;" in html

    def test_cache_bumped(self):
        routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        assert "nutmeg-v42-fe-jcstale" in routes
