"""体检(2026-06-10)— raw Pinnacle line (1X2 + O/U) shown on the cards so the
user can eyeball it directly against Pinnacle.com (the 公允 rows are these with
the vig stripped; the O/U drives the 让球/比分 reverse-fit but wasn't displayed)."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASH = REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestPinRawDisplay:
    def test_helper_defined_and_wired(self, html):
        assert "function _pinRawHtml(" in html
        assert "${_pinRawHtml(pr)}" in html

    def test_shows_1x2_and_ou(self, html):
        assert "t('pin_raw_lbl')" in html
        assert "pr.psc_over25" in html and "pr.psc_under25" in html

    def test_hidden_when_pending(self, html):
        # 待开盘 (no Pinnacle line yet) → render nothing
        assert "if (pr.psc_home == null) return ''" in html

    def test_i18n_both_locales(self, html):
        for k in ("pin_raw_lbl", "pin_raw_ou", "pin_raw_over", "pin_raw_under"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing a locale"

    def test_cache_bumped(self):
        import re
        routes = (REPO_ROOT / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        # pin-raw shipped at v41; _FE_VERSION is the version source (the SW
        # CACHE_VERSION '__FE_VERSION__' placeholder is substituted from it).
        # Assert ≥ v41, not the exact slug (which moves on every legitimate bump).
        m = re.search(r'_FE_VERSION = "nutmeg-v(\d+)-', routes)
        assert m and int(m.group(1)) >= 41
