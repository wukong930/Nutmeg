"""Tests for V6 W10 /api/v4/rules endpoint + dashboard Chinese localization.

The /rules endpoint is the single source of truth for the dashboard's
rule explainers (派奖率, ¥2 起投, ¥20k 上限 etc); these tests pin its
shape and verify the dashboard wires it up.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nutmeg.v4.api import v4_router
from nutmeg.v4.combo.lottery_rules import JINGCAI_DEFAULT


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


class TestRulesEndpoint:
    def test_rules_returns_200(self, client):
        r = client.get("/api/v4/rules")
        assert r.status_code == 200

    def test_rules_match_lottery_rules_constants(self, client):
        body = client.get("/api/v4/rules").json()
        assert body["stake_unit"] == JINGCAI_DEFAULT.stake_unit
        assert body["max_ticket_stake"] == JINGCAI_DEFAULT.max_ticket_stake
        assert body["max_period_stake"] == JINGCAI_DEFAULT.max_period_stake
        assert body["min_parlay_legs"] == JINGCAI_DEFAULT.min_parlay_legs
        assert body["max_legs_per_ticket"] == JINGCAI_DEFAULT.max_legs_per_ticket
        assert body["payout_ratio"] == pytest.approx(JINGCAI_DEFAULT.payout_ratio)
        assert body["vig"] == pytest.approx(JINGCAI_DEFAULT.vig)
        assert body["min_ev_per_unit"] == JINGCAI_DEFAULT.min_ev_per_unit
        assert body["min_hit_probability"] == JINGCAI_DEFAULT.min_hit_probability

    def test_rules_label_is_chinese(self, client):
        body = client.get("/api/v4/rules").json()
        # Default label identifies the rule set in Chinese (visible in UI)
        assert "竞彩" in body["label"]

    def test_rules_payout_plus_vig_equals_one(self, client):
        body = client.get("/api/v4/rules").json()
        assert body["payout_ratio"] + body["vig"] == pytest.approx(1.0)

    def test_rules_lottery_vs_pinnacle_check(self, client):
        """Sanity check: lottery vig should be at least 5x Pinnacle's ~2.5%.

        The 31.5% lottery vig is the central reason recommendations gate
        themselves on EV ≥ 5% (V6 W4). If the constant ever shifts toward
        Pinnacle-style numbers, the gating logic + the dashboard's
        explanation would need to update; this test guards the assumption.
        """
        body = client.get("/api/v4/rules").json()
        assert body["vig"] >= 0.10, "expected high-vig lottery, not exchange-style"


class TestDashboardChineseLocalization:
    """Lightweight regex checks on dashboard.html for V6 W10 deliverables."""

    @pytest.fixture
    def html(self, client) -> str:
        r = client.get("/api/v4/dashboard")
        assert r.status_code == 200
        return r.text

    def test_dashboard_has_rules_tab(self, html: str):
        # V8 W6 renumbered tabs (added 单关 + 复式), rules moved from ⑤ to ⑦
        assert "规则说明" in html
        assert "data-tab=\"rules\"" in html
        assert "tab-rules" in html

    def test_dashboard_calls_loadRules(self, html: str):
        # JS path that fetches /rules + binds values into the tab
        assert "function loadRules" in html or "async function loadRules" in html
        assert "renderRules" in html
        assert "/rules" in html

    def test_dashboard_renders_key_chinese_terms(self, html: str):
        """The rule tab + inline hint must surface the explicit terms
        the user asked us to call out (派奖率, 浮动让球, 起投 ¥2)."""
        for term in ("派奖率", "浮动让球", "浮动 SP", "起投", "¥2", "¥20,000",
                     "庄家抽水", "凯利"):
            assert term in html, f"missing UI term: {term!r}"

    def test_dashboard_no_orphan_english_copy(self, html: str):
        """A few English phrases shouldn't appear in user-facing copy.

        Doesn't check every English word (tag names, IDs, code samples
        are intentional). Just guards the previously-found gap.
        """
        # The "of bankroll" English phrase was patched in W10
        assert "of bankroll" not in html

    def test_dashboard_min_kelly_input_snaps_to_2(self, html: str):
        # The bankroll + min-kelly inputs should snap to ¥2 multiples
        # to align with 起投 ¥2.
        assert 'id="min-kelly"' in html
        # Easiest invariant: presence of step="2" on a form input
        assert 'step="2"' in html
