"""净胜球分组 frontend wiring (dashboard.html): collapsible block on the
reverse-calc + 近期赛事(标准)+ 市场模式 cards, both via _cupCardHtml."""
from __future__ import annotations

from pathlib import Path

import pytest

DASH = (
    Path(__file__).resolve().parents[2]
    / "apps/api/src/nutmeg/v4/api/static/dashboard.html"
)


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestMarginBandsFrontend:
    def test_helpers_defined(self, html):
        assert "function _marginBandsHtml(" in html
        assert "function _mbLabel(" in html

    def test_collapsible_details(self, html):
        # user asked for 折叠 — the block must be a <details> driven by mb_toggle
        assert "<details" in html and "t('mb_toggle')" in html

    def test_wired_into_cup_cards(self, html):
        # 近期赛事(标准模式)+ 市场模式 both render through _cupCardHtml.
        # (净胜球 fold-persist work added a 3rd arg _cupFoldAttrs — match the
        # prefix so the assertion survives the signature change.)
        assert "_marginBandsHtml(pr.margin_bands, pr.handicap_home" in html

    def test_wired_into_reverse_calc(self, html):
        assert "_marginBandsHtml(data.margin_bands, hcap)" in html

    def test_handicap_cluster_present(self, html):
        # the 让胜/让平/让负 cluster keyed off the entered 让球数
        for key in ("t('mb_win')", "t('mb_push')", "t('mb_lose')"):
            assert key in html

    def test_i18n_both_locales(self, html):
        for k in ("mb_toggle", "mb_home", "mb_away", "mb_draw", "mb_goals",
                  "mb_cluster", "mb_win", "mb_push", "mb_lose", "mb_hint"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"
