"""体检 Wave3 — hardening regressions (P1#7/#13 + P2 batch), one class per fix."""
from __future__ import annotations

import sqlite3

import pytest


def _sel(home, away, p=0.5, odds=2.6):
    from nutmeg.v4.combo.selections import Selection
    return Selection(
        match_id=f"EPL_{home}_vs_{away}", market_type="1x2", outcome="H",
        probability=p, odds=odds,
    )


class TestCorrelatedPoolExposureCap:
    """P1#7 — C(M,N) tickets share legs; their independent Kelly stakes must
    never SUM as if independent (synthetic M=6/N=5 hit 30.9% of bankroll)."""

    def test_default_budget_caps_pool_at_single_ticket_ceiling(self):
        from nutmeg.v4.combo.compound_pool import recommend_pool
        sels = [_sel(f"H{i}", f"A{i}", p=0.62, odds=2.4) for i in range(6)]
        rec = recommend_pool(sels, 5, bankroll=1000.0)
        assert rec.total_stake <= 0.05 * 1000.0 + 1e-9, (
            f"correlated pool exposure {rec.total_stake} exceeds the "
            f"single-ticket ceiling (5% of bankroll)"
        )

    def test_explicit_budget_still_wins(self):
        from nutmeg.v4.combo.compound_pool import recommend_pool
        sels = [_sel(f"H{i}", f"A{i}", p=0.62, odds=2.4) for i in range(6)]
        rec = recommend_pool(sels, 5, bankroll=1000.0, max_total_budget=20.0)
        assert rec.total_stake <= 20.0 + 1e-9


class TestRecordIdempotency:
    """P2 — a client retry of the IDENTICAL record payload must not
    double-book; a regenerated (different) payload records normally."""

    def _payload(self, gen="2026-07-04T10:00:00+00:00"):
        req = {"fixtures": [{"home_team": "A", "away_team": "B"}]}
        resp = {
            "bankroll": 1000.0, "n_fixtures": 1, "n_recommendations": 1,
            "generated_at_utc": gen,
            "model": {"model_type": "catboost"},
            "tickets": [{
                "match_id": "EPL_A_vs_B", "market_type": "1x2", "outcome": "H",
                "odds": 2.5, "probability": 0.5, "ev_per_unit": 0.25,
                "stake": 10.0, "expected_return": 2.5,
            }],
        }
        return req, resp

    def test_identical_retry_returns_same_session(self, tmp_path):
        from nutmeg.v4.observation.recorder import record_single_session
        db = tmp_path / "obs.db"
        req, resp = self._payload()
        s1 = record_single_session(db, request=req, response=resp)
        s2 = record_single_session(db, request=req, response=resp)
        assert s1 == s2
        with sqlite3.connect(db) as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0]
        assert n == 1

    def test_regenerated_payload_records_normally(self, tmp_path):
        from nutmeg.v4.observation.recorder import record_single_session
        db = tmp_path / "obs.db"
        req, resp1 = self._payload(gen="2026-07-04T10:00:00+00:00")
        _, resp2 = self._payload(gen="2026-07-04T10:05:00+00:00")
        s1 = record_single_session(db, request=req, response=resp1)
        s2 = record_single_session(db, request=req, response=resp2)
        assert s1 != s2


class TestJingcaiSpWriteHygiene:
    """P2 — psc COALESCE on re-capture; protect_manual no longer swallows the
    初盘 stamp."""

    def test_recapture_without_psc_keeps_stored_pinnacle(self, tmp_path):
        from nutmeg.v4.observation.jingcai_sp import fetch_jingcai_sp, record_jingcai_sp
        db = tmp_path / "obs.db"
        record_jingcai_sp(db, match_date="2026-08-15", home_team="A", away_team="B",
                          jc_home=2.1, jc_draw=3.2, jc_away=3.3,
                          psc_home=2.0, psc_draw=3.4, psc_away=3.6, ou_line=2.25)
        # manual re-pin of the 竞彩 SP with NO Pinnacle reading
        record_jingcai_sp(db, match_date="2026-08-15", home_team="A", away_team="B",
                          jc_home=2.05, jc_draw=3.25, jc_away=3.4)
        r = fetch_jingcai_sp(db)[0]
        assert r["jc_home"] == 2.05          # latest 竞彩 line wins
        assert r["psc_home"] == 2.0          # sharp anchor NOT nulled
        assert r["ou_line"] == 2.25

    def test_protect_manual_still_stamps_open(self, tmp_path):
        from nutmeg.v4.observation.jingcai_sp import fetch_jingcai_sp, record_jingcai_sp
        db = tmp_path / "obs.db"
        # user hand-priced first (source=market_mode)
        record_jingcai_sp(db, match_date="2026-08-15", home_team="A", away_team="B",
                          jc_home=2.1, jc_draw=3.2, jc_away=3.3, source="market_mode")
        # 11:00 开售 cron: protect_manual=True + phase=open
        ok = record_jingcai_sp(db, match_date="2026-08-15", home_team="A",
                               away_team="B", jc_home=2.3, jc_draw=3.1,
                               jc_away=3.0, source="sporttery",
                               protect_manual=True, phase="open")
        assert ok
        r = fetch_jingcai_sp(db)[0]
        assert r["jc_home"] == 2.1           # hand-priced line NOT clobbered
        assert r["jc_open_home"] == 2.3      # …but the 初盘 IS stamped
        assert r["opened_at"] is not None


class TestJingcaiVoteCoalesce:
    def test_recapture_without_odds_keeps_sp(self, tmp_path):
        from nutmeg.v4.observation.jingcai_vote import (
            fetch_jingcai_vote,
            record_jingcai_vote,
        )
        db = tmp_path / "obs.db"
        record_jingcai_vote(db, match_date="2026-08-15", home_zh="甲", away_zh="乙",
                            pool_code="HAD", h_support=40.0, d_support=30.0,
                            a_support=30.0, jc_home=2.1, jc_draw=3.2, jc_away=3.3,
                            handicap_home=-1)
        record_jingcai_vote(db, match_date="2026-08-15", home_zh="甲", away_zh="乙",
                            pool_code="HAD", h_support=45.0, d_support=28.0,
                            a_support=27.0)   # later window: no odds in payload
        r = fetch_jingcai_vote(db)[0]
        assert r["h_support"] == 45.0        # crowd numbers = latest
        assert r["jc_home"] == 2.1           # SP survives
        assert r["handicap_home"] == -1


class TestDcHalfLineContract:
    """P2 — integer lines push; dc_home_cover_prob must refuse them loudly and
    the polymarket entry must skip them honestly."""

    def test_integer_and_quarter_lines_raise(self):
        from nutmeg.v4.model.market_handicap import dc_home_cover_prob, score_grid
        grid = score_grid(1.5, 1.1)
        for bad in (-1.0, 0.0, 1.0, -0.25, 0.75):
            with pytest.raises(ValueError):
                dc_home_cover_prob(grid, bad)

    def test_half_lines_still_work(self):
        from nutmeg.v4.model.market_handicap import dc_home_cover_prob, score_grid
        grid = score_grid(1.5, 1.1)
        vals = [dc_home_cover_prob(grid, ln) for ln in (-1.5, -0.5, 0.5, 1.5)]
        assert all(0.0 < v < 1.0 for v in vals)
        assert vals == sorted(vals)  # monotone in the line

    def test_polymarket_integer_handicap_skipped(self):
        from nutmeg.v4.model.market_handicap import score_grid
        from nutmeg.v4.model.polymarket_gap import HANDICAP_HOME, _q_for
        grid = score_grid(1.5, 1.1)
        assert _q_for(HANDICAP_HOME, -1.0, 0.5, 0.3, 0.2, grid) is None
        assert _q_for(HANDICAP_HOME, -0.5, 0.5, 0.3, 0.2, grid) is not None


class TestAetScoreFallback:
    def test_aet_without_fulltime_split_is_skipped(self):
        from nutmeg.v4.observation.prediction_log import _ft_outcome
        fx = {"fixture": {"status": {"short": "AET"}},
              "score": {"fulltime": {}},
              "goals": {"home": 2, "away": 1}}   # 120' score — NOT the 90' result
        assert _ft_outcome(fx) is None
        # FT with a missing split may still use goals (same thing at FT)
        fx["fixture"]["status"]["short"] = "FT"
        assert _ft_outcome(fx) == (2, 1, 0)


class TestQuotaAlarm:
    def test_exhausted_oa_quota_alarms_and_gates(self, monkeypatch, tmp_path):
        import httpx

        from nutmeg.v4.cli import data_freshness as df

        monkeypatch.setenv("NUTMEG_ODDS_API_KEY", "test-key")
        monkeypatch.delenv("NUTMEG_API_FOOTBALL_KEY", raising=False)

        class R:
            headers = {"x-requests-remaining": "12"}
        monkeypatch.setattr(httpx, "get", lambda *a, **k: R())
        alarms, probe_fails = df.check_api_quota()
        assert alarms and "12" in alarms[0]
        assert probe_fails == []

    def test_no_keys_no_probe(self, monkeypatch):
        from nutmeg.v4.cli import data_freshness as df
        monkeypatch.delenv("NUTMEG_ODDS_API_KEY", raising=False)
        monkeypatch.delenv("NUTMEG_API_FOOTBALL_KEY", raising=False)
        assert df.check_api_quota() == ([], [])

    def test_probe_failure_visible_not_alarm(self, monkeypatch):
        """体检 W1 — 探针失败必须可见(probe_failures),但不冒充配额报警。"""
        import httpx

        from nutmeg.v4.cli import data_freshness as df
        monkeypatch.setenv("NUTMEG_ODDS_API_KEY", "test-key")
        monkeypatch.delenv("NUTMEG_API_FOOTBALL_KEY", raising=False)

        def boom(*a, **k):
            raise httpx.ConnectError("network down")
        monkeypatch.setattr(httpx, "get", boom)
        alarms, probe_fails = df.check_api_quota()
        assert alarms == []
        assert probe_fails and "探针失败" in probe_fails[0]


class TestClvTierRegistrySync:
    def test_tier_labels_match_display_order(self):
        from nutmeg.v4.cli.clv_ledger import _TIER_ORDER, _tier
        labels = {_tier(p / 100) for p in range(1, 100)}
        assert labels == set(_TIER_ORDER)
