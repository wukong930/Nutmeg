"""体检(2026-06-10)— manual reverse-calculator settle-identity hardening.

Root cause of the Croatia/Slovenia orphan: the 📌 record path stored a
hand-typed identity (league free-text defaulting to JPN_J1 + Chinese team
names) that the exact-match settle join could never resolve. The fix:
league becomes a SELECT of fetchable codes, zh team names are reverse-mapped
to API English via the zhTeam dict at record time, and an un-resolvable
identity requires an explicit confirm().
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASH = REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestLeagueSelect:
    def test_is_select_not_freetext(self, html):
        assert '<select id="mrev-league"' in html
        assert '<input id="mrev-league"' not in html

    def test_offers_settleable_codes(self, html):
        for code in ('value="FRIENDLIES"', 'value="WC"', 'value="JPN_J1"',
                     'value="MANUAL"'):
            assert code in html

    def test_last_choice_persisted(self, html):
        assert "localStorage.setItem('mrev_league'" in html
        assert "localStorage.getItem('mrev_league')" in html


class TestTeamNormalisation:
    def test_helper_defined_and_used(self, html):
        assert "function _enTeamForSettle(" in html
        assert html.count("_enTeamForSettle(") >= 3  # def + home + away

    def test_unresolvable_identity_requires_confirm(self, html):
        assert "window.confirm(t('mrev_settle_warn'))" in html

    def test_i18n_both_locales(self, html):
        for k in ("mrev_settle_warn", "mrev_record_aborted"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing a locale"


class TestCacheBumped:
    def test_at_least_v40(self):
        import re
        routes = (REPO_ROOT / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        # _FE_VERSION is the version source; the SW CACHE_VERSION is its
        # `__FE_VERSION__` placeholder substituted at serve time.
        m = re.search(r'_FE_VERSION = "nutmeg-v(\d+)-', routes)
        assert m and int(m.group(1)) >= 40
