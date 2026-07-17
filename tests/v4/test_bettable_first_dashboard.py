"""2026-07-07 — 竞彩可投注置顶: 近期赛事 pins matches 竞彩 lists for betting to a
top zone (still league-grouped), then the model/Pinnacle reference rump. Applies
to BOTH 标准模式 (renderTodaySpCalc) and 市场模式 (loadCupMarket) via one shared
helper. These substring guards keep a future dashboard refactor from silently
reverting the ordering or unwiring one of the two modes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestBettableFirst:
    def test_helpers_defined(self, html: str) -> None:
        assert "function _isJcBettable(pr)" in html
        assert "function _lgGroupsHtml(items, cardHtml, pfx)" in html
        assert "function _bettableFirstHtml(preds, cardHtml, mode)" in html

    def test_bettable_signal_is_full_had_sp(self, html: str) -> None:
        # A match is bettable iff it has a full HAD 竞彩 SP on file (all 3 legs).
        assert "pr.jc_home != null && pr.jc_draw != null && pr.jc_away != null" in html

    def test_standard_mode_wired(self, html: str) -> None:
        # 标准模式 renders through the shared helper (not the old raw byLeague loop).
        assert "const scoredHtml = _bettableFirstHtml(preds, cardHtml, 'spcalc');" in html

    def test_market_mode_wired(self, html: str) -> None:
        # 市场模式 renders through the SAME helper so both modes order identically.
        assert "list.innerHTML = _bettableFirstHtml(preds, _cupCardHtml, 'cup');" in html

    def test_zones_use_distinct_collapse_pfx(self, html: str) -> None:
        # Bettable zone namespaces its collapse keys ('jc:') so the SAME league
        # folds independently from its reference-zone copy.
        assert "_lgGroupsHtml(bett, cardHtml, 'jc:')" in html
        assert "_lgGroupsHtml(rest, cardHtml, '')" in html

    def test_degrades_when_nothing_bettable(self, html: str) -> None:
        # No bettable matches → plain league grouping, no pin header (old look).
        assert "if (!bett.length) return _lgGroupsHtml(rest, cardHtml, '');" in html

    def test_i18n_keys_present_both_locales(self, html: str) -> None:
        # zh + en dicts each carry the two headers (2 defs + ≥1 use site each).
        assert html.count("jc_bettable_hdr") >= 3
        assert html.count("jc_ref_hdr") >= 3
        assert "jc_bettable_hdr:  '竞彩可投注'" in html
        assert "jc_bettable_hdr:  'Bettable on 竞彩'" in html
        assert "jc_ref_hdr:" in html

    def test_headers_rendered_via_i18n(self, html: str) -> None:
        assert "t('jc_bettable_hdr')" in html
        assert "t('jc_ref_hdr')" in html
