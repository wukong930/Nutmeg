"""V12 W8 — 市场模式 让球 tracking: record → settle → ROI compatibility.

A market-mode 让球 pick (J1 / cup) is recorded with the MARKET-IMPLIED P (not
the OOD model), tagged model_type=market_handicap. Because the recorded shape
matches the regular pipeline (match_id = "{league}_{home}_vs_{away}",
market_type=handicap_1x2, handicap_home on the single_prediction), the generic
``settle_unsettled`` settles it for free once the result lands.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.observation.recorder import record_market_handicap_session
from nutmeg.v4.observation.settlement import settle_unsettled
from nutmeg.v4.observation.store import init_db, open_db, upsert_outcome

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client():
    import os

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nutmeg.v4.api import v4_router
    os.environ.setdefault(
        "NUTMEG_V4_ARTIFACT_PATH",
        str(REPO_ROOT / "data" / "v4_model_cat_lineups"),
    )
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


def _prep(tmp_path):
    db = tmp_path / "obs.db"
    init_db(db)
    return db


def _record_kobe(db, *, outcome="H", odds=5.50, ev=-0.01, line=-1):
    """神户 vs 鹿岛 · 让球-1 · market-implied P ≈ (18/22/60)."""
    return record_market_handicap_session(
        db,
        league="JPN_J1", match_date="2026-05-30",
        home_team="Vissel Kobe", away_team="Kashima",
        handicap_home=line,
        p_handicap=(0.18, 0.22, 0.60),
        p_1x2=(0.40, 0.32, 0.28),
        pick_outcome=outcome, pick_odds=odds, pick_ev=ev,
        pick_stake=2.0, pick_expected_return=2.0 * ev,
        bankroll=1000.0, psc_1x2=(2.43, 3.04, 3.41),
    )


# ============ Recorder shape ==========================================

class TestRecorderShape:
    def test_session_tagged_market_handicap(self, tmp_path):
        db = _prep(tmp_path)
        sid = _record_kobe(db)
        assert sid > 0
        with sqlite3.connect(db) as conn:
            mt, meta = conn.execute(
                "SELECT model_type, metadata_json FROM recommendation_sessions "
                "WHERE session_id=?", (sid,)
            ).fetchone()
        assert mt == "market_handicap"
        assert "market_handicap" in meta  # session_kind tag

    def test_single_prediction_pins_handicap(self, tmp_path):
        db = _prep(tmp_path)
        sid = _record_kobe(db)
        with sqlite3.connect(db) as conn:
            lg, hh, ph_hc = conn.execute(
                "SELECT league, handicap_home, p_home_handicap "
                "FROM single_predictions WHERE session_id=?", (sid,)
            ).fetchone()
        assert lg == "JPN_J1"
        assert hh == -1
        assert ph_hc == pytest.approx(0.18)

    def test_leg_is_handicap_1x2(self, tmp_path):
        db = _prep(tmp_path)
        sid = _record_kobe(db, outcome="H")
        with sqlite3.connect(db) as conn:
            k_legs, legs = conn.execute(
                "SELECT k_legs, legs_json FROM parlay_recommendations "
                "WHERE session_id=?", (sid,)
            ).fetchone()
        assert k_legs == 1
        assert '"market_type": "handicap_1x2"' in legs
        assert '"outcome": "H"' in legs
        assert "JPN_J1_Vissel Kobe_vs_Kashima" in legs  # settle-pipeline match_id

    def test_bad_outcome_raises(self, tmp_path):
        db = _prep(tmp_path)
        with pytest.raises(ValueError):
            _record_kobe(db, outcome="X")


# ============ End-to-end: record → result lands → settle ===============

class TestEndToEndSettlement:
    def test_win_settles_positive(self, tmp_path):
        """神户 5-0 → home wins by 5 → covers 让球-1 (outcome H) → hit, +PnL."""
        db = _prep(tmp_path)
        _record_kobe(db, outcome="H", odds=5.50)
        with open_db(db) as conn:
            upsert_outcome(
                conn, match_date="2026-05-30", league="JPN_J1",
                home_team="Vissel Kobe", away_team="Kashima",
                home_goals=5, away_goals=0,
            )
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        assert counts["still_unknown"] == 0
        with sqlite3.connect(db) as conn:
            hit, stake, payout, pnl = conn.execute(
                "SELECT hit, stake, actual_payout, profit_loss FROM settlements"
            ).fetchone()
        assert hit == 1
        assert payout > stake
        assert pnl > 0

    def test_loss_settles_negative(self, tmp_path):
        """神户 1-0 → at 让球-1, (1-1)=0 vs 0 → D on the line → H bet loses."""
        db = _prep(tmp_path)
        _record_kobe(db, outcome="H", odds=5.50)
        with open_db(db) as conn:
            upsert_outcome(
                conn, match_date="2026-05-30", league="JPN_J1",
                home_team="Vissel Kobe", away_team="Kashima",
                home_goals=1, away_goals=0,
            )
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        with sqlite3.connect(db) as conn:
            hit, pnl = conn.execute(
                "SELECT hit, profit_loss FROM settlements"
            ).fetchone()
        assert hit == 0
        assert pnl < 0


# ============ Endpoint ================================================

class TestMarketHandicapEndpoint:
    def _payload(self, **over):
        # 让平 SP 4.30 是这里**唯一** +EV 的腿(P=25.65% → 打平 SP 3.90 → EV +10.3%),
        # 记录路径(下面两个 gate 测试)全靠它才走得到。
        #
        # ⚠️ 原 fixture 的 +EV 腿是 让胜 @5.50 —— 它在 prereg v1.7(2026-07-17)δ 重估
        # 前是 +1.03%,重估后是 **−13.8%**。那个 +EV 从来不是真的:它正是 C1 要杀的
        # 「−1 线让胜虚高」(DC 高估爆盘尾 +4.6pp)。所以这里不是「测试挂了去迁就」,
        # 是 fixture 当初把**错的校准**固化了下来。别把 +EV 腿搬回让胜。
        p = {
            "league": "JPN_J1", "date": "2026-05-30",
            "home_team": "Vissel Kobe", "away_team": "Kashima",
            "psc_home": 2.43, "psc_draw": 3.04, "psc_away": 3.41,
            "psc_over25": 1.95, "psc_under25": 1.95,
            "handicap_home": -1,
            "odds_handicap_H": 5.50, "odds_handicap_D": 4.30, "odds_handicap_A": 1.46,
            "bankroll": 1000.0, "kelly_fraction": 0.25,
            "record_session": False,
        }
        p.update(over)
        return p

    def test_payload_has_exactly_one_positive_ev_leg(self, client):
        """守住上面那条注释 —— 两个 gate 测试只有在**真有** +EV 腿时才不是空转。

        δ 若再动而这条先红,说明 fixture 又跟校准脱节了:重挑 SP,别删断言。
        """
        b = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload()).json()
        assert [e > 0 for e in b["ev_per_unit"]].count(True) == 1
        assert b["best_outcome"] == "D"          # 让平 —— 不是让胜(那个是 C1 修掉的假象)

    def test_computes_market_implied_p_and_ev(self, client):
        r = client.post("/api/v4/recommend/market-handicap", json=self._payload())
        assert r.status_code == 200, r.text
        b = r.json()
        assert len(b["market_implied_p"]) == 3
        assert abs(sum(b["market_implied_p"]) - 1.0) < 1e-6
        assert b["best_outcome"] in ("H", "D", "A")
        # every EV slot present (3 SPs supplied)
        assert all(e is not None for e in b["ev_per_unit"])
        assert b["recorded"] is False  # record_session False

    def test_handicap_line_out_of_range_422(self, client):
        r = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload(handicap_home=9))
        assert r.status_code == 422

    def test_manual_pinnacle_is_recorded_as_manual(self, client, tmp_path, monkeypatch):
        """手填的 Pinnacle 必须在台账里留下 'manual' 标(2026-07-23)。

        owner 在 OA 没覆盖的赛事上手打 Pinnacle,📌 记一笔会把手打值原样落账 ——
        此前**没有任何字段**能把它和抓来的价区分开。手填若是陈旧价或手滑打错,
        记下的就是虚构价,事后谁也查不出来。这条锁住整条链:
        前端设 pr.odds_source='manual' → 请求体 → store._request_odds_source。
        """
        db = tmp_path / "obs.db"
        init_db(db)
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        r = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload(record_session=True, odds_source="manual"))
        assert r.status_code == 200, r.text
        assert r.json()["recorded"] is True
        with sqlite3.connect(db) as conn:
            got = conn.execute(
                "SELECT odds_source FROM recommendation_sessions").fetchone()[0]
        assert got == "manual"

    def test_unmarked_request_records_null_not_a_guess(self, client, tmp_path, monkeypatch):
        """老客户端(没 bump 到 v112)不带该字段 → NULL。
        **绝不**默认成 'api_football':那等于把「没告诉我」伪装成「我查过了」。"""
        db = tmp_path / "obs.db"
        init_db(db)
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        r = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload(record_session=True))
        assert r.status_code == 200, r.text
        with sqlite3.connect(db) as conn:
            got = conn.execute(
                "SELECT odds_source FROM recommendation_sessions").fetchone()[0]
        assert got is None

    def test_records_when_gate_on(self, client, tmp_path, monkeypatch):
        db = tmp_path / "obs.db"
        init_db(db)
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        r = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload(record_session=True))
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["recorded"] is True
        assert b["session_id"] is not None
        with sqlite3.connect(db) as conn:
            mt = conn.execute(
                "SELECT model_type FROM recommendation_sessions"
            ).fetchone()[0]
        assert mt == "market_handicap"

    def test_no_record_when_gate_off(self, client, tmp_path, monkeypatch):
        monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
        r = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload(record_session=True))
        assert r.status_code == 200, r.text
        assert r.json()["recorded"] is False

    def test_all_negative_ev_not_recorded(self, client, tmp_path, monkeypatch):
        """AUDIT FIX (R1): when every outcome is −EV (the market default under
        竞彩's ~31.5% vig) the endpoint must NOT manufacture a ¥2 'best' leg or
        record it — no +EV → 空仓 → stake 0, recorded False, nothing in the DB
        to pollute the unfiltered ROI / calibration population."""
        db = tmp_path / "obs.db"
        init_db(db)
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        payload = {
            "league": "JPN_J1", "date": "2026-06-03",
            "home_team": "A", "away_team": "B",
            "psc_home": 2.43, "psc_draw": 3.04, "psc_away": 3.41,
            "psc_over25": 1.95, "psc_under25": 1.95,
            "handicap_home": -1,
            # 三腿全 −EV:让胜 −29.5% / 让平 −2.5% / 让负 −14.3%(prereg v1.7 δ 下实测)。
            # 关键是 让平 SP 3.80 < 打平线 3.90 —— 它是本盘最接近 +EV 的腿,压住它
            # 才真的证明「无 +EV → 空仓」。(v1.7 前这里靠调低 H;那时让胜虚高才是
            # 「最不差的腿」,现在不是了。)
            "odds_handicap_H": 4.50, "odds_handicap_D": 3.80,
            "odds_handicap_A": 1.46,
            "bankroll": 1000.0, "kelly_fraction": 0.25,
            "record_session": True,
        }
        r = client.post("/api/v4/recommend/market-handicap", json=payload)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["best_ev"] is not None and b["best_ev"] <= 0  # all −EV
        assert b["best_stake"] == 0.0       # no ¥2 phantom stake
        assert b["recorded"] is False       # not recorded as a recommendation
        with sqlite3.connect(db) as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM recommendation_sessions"
            ).fetchone()[0]
        assert n == 0                       # ROI population stays clean


class TestMarketRepriceEndpoint:
    """V14 — /recommend/market-reprice: pure compute that lets a 市场模式 card
    re-price off a hand-typed LIVE Pinnacle line (de-vig 1X2 + 让球 board), NO
    DB. Reuses the validated implied_handicap_lines path."""

    def _payload(self, **over):
        p = {
            "psc_home": 2.36, "psc_draw": 3.35, "psc_away": 3.15,
            "psc_over25": 1.943, "psc_under25": 1.925, "ou_line": 2.25,
        }
        p.update(over)
        return p

    def test_returns_devig_1x2_and_full_board(self, client):
        r = client.post("/api/v4/recommend/market-reprice", json=self._payload())
        assert r.status_code == 200, r.text
        b = r.json()
        # de-vig 1X2 sums to 1, home is the slight favourite (2.36 < 3.15)
        s = b["p_home_1x2"] + b["p_draw_1x2"] + b["p_away_1x2"]
        assert abs(s - 1.0) < 1e-6
        assert b["p_home_1x2"] > b["p_away_1x2"]
        # full integer board −3..+3, every line a valid simplex
        assert [ln["line"] for ln in b["handicap_lines"]] == list(range(-3, 4))
        for ln in b["handicap_lines"]:
            assert abs(ln["p_home"] + ln["p_draw"] + ln["p_away"] - 1.0) < 1e-6
        # overround is the typed 1X2 vig (~4%), the dashboard's fat-finger check
        assert 0.0 < b["overround"] < 0.10

    def test_overround_flags_fat_finger(self, client):
        # swapped/garbage odds inflate the implied vig well past a real line
        r = client.post("/api/v4/recommend/market-reprice",
                        json=self._payload(psc_home=1.5, psc_draw=1.5, psc_away=1.5))
        assert r.status_code == 200
        assert r.json()["overround"] > 0.5     # ⇒ dashboard shows the ⚠

    def test_invalid_1x2_returns_422(self, client):
        r = client.post("/api/v4/recommend/market-reprice",
                        json={"psc_home": 1.0, "psc_draw": 0, "psc_away": -2})
        assert r.status_code == 422

    def test_no_db_write(self, client, tmp_path, monkeypatch):
        # reprice is pure compute — it must never touch the observation DB
        db = tmp_path / "obs.db"
        init_db(db)
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        r = client.post("/api/v4/recommend/market-reprice", json=self._payload())
        assert r.status_code == 200
        with sqlite3.connect(db) as conn:
            n = conn.execute("SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0]
        assert n == 0
