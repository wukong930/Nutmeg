"""V12 W3 — 竞彩 SP live calculator (single 1X2): markup + i18n + JS-hook guard.

The calculator is pure client-side: model P (from the today response's
``single_match_predictions``) × the user-entered 竞彩 SP → live EV / Kelly,
recorded to the observation DB only when the user clicks 已下单. Recompute
on every SP keystroke needs no server round-trip (P is market-agnostic).

These tests guard the dashboard markup, JS hooks, and i18n completeness
against accidental removal. The numeric contract is covered elsewhere:
``test_today_recommendations.test_single_match_predictions_populated_for_spcalc``
(model P + psc reach the client) and the /recommend/single endpoint tests
(server-authoritative stake math on record).
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASH = REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html"
ROUTES = REPO_ROOT / "apps/api/src/nutmeg/v4/api/routes.py"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestSpCalcMarkup:
    def test_section_present(self, html):
        assert 'id="today-spcalc-section"' in html
        assert 'id="today-spcalc-list"' in html

    def test_js_hooks_present(self, html):
        for fn in (
            "function renderTodaySpCalc(",
            "function _spcalcRecalc(",
            "async function _spcalcRecord(",
            "function _spcalcStake(",
        ):
            assert fn in html, f"missing JS function: {fn}"

    def test_wired_into_today_loader(self, html):
        assert "renderTodaySpCalc(body.single_match_predictions" in html

    def test_record_posts_to_single_with_record_session(self, html):
        # 已下单 records the placed bet (once) via /recommend/single.
        assert "/recommend/single" in html
        assert "record_session: true" in html

    def test_kelly_formula_mirrors_jingcai(self, html):
        # edge/(SP-1) fractional Kelly + 5% cap + ¥2 quantize.
        assert "edge / (sp - 1.0)" in html
        assert "bankroll * 0.05" in html
        assert "Math.floor(stake / 2) * 2" in html


class TestSpCalcI18n:
    REQUIRED_KEYS = [
        "h_today_spcalc", "today_spcalc_hint", "spcalc_n_matches",
        "spcalc_enter_sp", "spcalc_record_btn", "spcalc_pick", "spcalc_suggest",
        "spcalc_nobet", "spcalc_recorded", "spcalc_recorded_btn",
        "spcalc_record_err", "spcalc_need_all_sp", "spcalc_jc", "spcalc_fair",
    ]

    def test_each_key_defined_in_both_locales(self, html):
        # Each key must be defined in BOTH the zh and en dict (the dict entry
        # is `key:` — distinct from the data-i18n="key" / t('key') uses).
        for k in self.REQUIRED_KEYS:
            assert html.count(k + ":") >= 2, (
                f"i18n key {k!r} missing from zh or en dict (found "
                f"{html.count(k + ':')} dict entries, need 2)"
            )


class TestSpCalcCacheBust:
    def test_cache_version_bumped_for_spcalc(self):
        src = ROUTES.read_text(encoding="utf-8")
        assert "nutmeg-v12-fe-w3-spcalc" in src, (
            "SW CACHE_VERSION not bumped for the SP-calc frontend change"
        )
