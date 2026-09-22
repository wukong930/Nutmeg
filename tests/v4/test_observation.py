"""Tests for v4 observation layer: store, recorder, settlement, ROI."""
import json
import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.observation import (
    open_db,
    record_session,
    settle_unsettled,
    upsert_outcome,
)
from nutmeg.v4.observation.roi import (
    compute_headline,
    group_by_k_legs,
    group_by_league,
    calibration_buckets,
)
from nutmeg.v4.observation.settlement import _outcome_1x2, _outcome_handicap_1x2


# ---------- Helpers ----------

def _response_with_one_2_leg(handicap_home=None, sel_a="H", sel_b="H", odds_a=2.5, odds_b=3.0):
    """Build a minimal recommend response with ONE 2-串-1 recommendation."""
    legs = [
        {
            "match_id": "EPL_TeamA_vs_TeamB",
            "market_type": "1x2",
            "selections": [{"outcome": sel_a, "odds": odds_a, "probability": 0.4, "edge": 0.1}],
        },
        {
            "match_id": "ITA_SERIE_A_TeamC_vs_TeamD",
            "market_type": "handicap_1x2" if handicap_home is not None else "1x2",
            "selections": [{"outcome": sel_b, "odds": odds_b, "probability": 0.4, "edge": 0.1}],
        },
    ]
    return {
        "generated_at_utc": "2026-05-22T10:00:00+00:00",
        "model": {"training_cutoff": "2025-06-01", "trained_at_utc": "2026-05-22T09:00:00+00:00"},
        "bankroll": 1000.0,
        "n_fixtures": 2,
        "n_recommendations": 1,
        "single_match_predictions": [
            {"date": "2025-08-17", "league": "EPL", "home_team": "TeamA", "away_team": "TeamB",
             "lambda_home": 1.5, "lambda_away": 1.0, "p_home_1x2": 0.50, "p_draw_1x2": 0.25, "p_away_1x2": 0.25},
            {"date": "2025-08-17", "league": "ITA_SERIE_A", "home_team": "TeamC", "away_team": "TeamD",
             "lambda_home": 1.4, "lambda_away": 1.1, "p_home_1x2": 0.45, "p_draw_1x2": 0.28, "p_away_1x2": 0.27,
             "handicap_home": handicap_home},
        ],
        "recommendations": [
            {"rank": 1, "k_legs": 2, "is_compound": False, "stake_units": 1,
             "kelly_recommended_stake": 10.0, "expected_return": 5.0,
             "hit_probability": 0.16, "ev_per_unit": 0.50, "log_growth": 0.02,
             "legs": legs},
        ],
    }


# ---------- Pure functions ----------

class TestOutcomeMath:
    def test_1x2_home(self):
        assert _outcome_1x2(2, 1) == "H"
    def test_1x2_draw(self):
        assert _outcome_1x2(1, 1) == "D"
    def test_1x2_away(self):
        assert _outcome_1x2(0, 1) == "A"

    def test_handicap_zero_equals_1x2(self):
        for hg, ag in [(2, 1), (1, 1), (0, 1), (3, 0)]:
            assert _outcome_handicap_1x2(hg, ag, 0) == _outcome_1x2(hg, ag)

    def test_handicap_minus_one(self):
        # 3-0 with home -1 → 3-1-0 = 2 → H
        assert _outcome_handicap_1x2(3, 0, -1) == "H"
        # 1-0 with home -1 → 1-1-0 = 0 → D
        assert _outcome_handicap_1x2(1, 0, -1) == "D"
        # 0-0 with home -1 → 0-1-0 = -1 → A
        assert _outcome_handicap_1x2(0, 0, -1) == "A"

    def test_handicap_plus_one(self):
        # 0-1 with home +1 → 0+1-1 = 0 → D
        assert _outcome_handicap_1x2(0, 1, 1) == "D"


# ---------- Schema + recording ----------

class TestStore:
    def test_open_db_creates_schema(self, tmp_path):
        db = tmp_path / "x.db"
        with open_db(db) as conn:
            tables = [r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
        for expected in ("recommendation_sessions", "single_predictions",
                         "parlay_recommendations", "match_outcomes", "settlements"):
            assert expected in tables

    def test_record_session(self, tmp_path):
        db = tmp_path / "obs.db"
        sid = record_session(db, request={"foo": "bar"}, response=_response_with_one_2_leg())
        assert sid == 1
        with open_db(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM single_predictions").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM parlay_recommendations").fetchone()[0] == 1


# ---------- Settlement ----------

class TestSettlement:
    def test_settle_with_no_outcomes_still_unknown(self, tmp_path):
        db = tmp_path / "obs.db"
        record_session(db, request={}, response=_response_with_one_2_leg())
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 0
        assert counts["still_unknown"] == 1

    def test_settle_full_hit(self, tmp_path):
        db = tmp_path / "obs.db"
        # Both selections = H
        record_session(db, request={}, response=_response_with_one_2_leg(sel_a="H", sel_b="H"))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                            home_team="TeamA", away_team="TeamB",
                            home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                            home_team="TeamC", away_team="TeamD",
                            home_goals=3, away_goals=1)
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        with open_db(db) as conn:
            s = conn.execute("SELECT * FROM settlements").fetchone()
        assert s["hit"] == 1
        assert s["stake"] == 10.0
        assert s["actual_payout"] == pytest.approx(10.0 * 2.5 * 3.0)
        assert s["profit_loss"] == pytest.approx(10.0 * 2.5 * 3.0 - 10.0)

    def test_settle_miss(self, tmp_path):
        db = tmp_path / "obs.db"
        record_session(db, request={}, response=_response_with_one_2_leg(sel_a="H", sel_b="A"))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                            home_team="TeamA", away_team="TeamB",
                            home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                            home_team="TeamC", away_team="TeamD",
                            home_goals=3, away_goals=1)  # H, not A
        with open_db(db) as conn:
            settle_unsettled(conn)
            s = conn.execute("SELECT * FROM settlements").fetchone()
        assert s["hit"] == 0
        assert s["actual_payout"] == 0.0
        assert s["profit_loss"] == -10.0

    def test_settle_handicap(self, tmp_path):
        db = tmp_path / "obs.db"
        # Second leg handicap -1, select H. If home wins by 2+ → H wins.
        record_session(db, request={},
                        response=_response_with_one_2_leg(handicap_home=-1, sel_a="H", sel_b="H"))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                            home_team="TeamA", away_team="TeamB",
                            home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                            home_team="TeamC", away_team="TeamD",
                            home_goals=2, away_goals=0)  # 2-1-0 = 1 > 0 → H
        with open_db(db) as conn:
            settle_unsettled(conn)
            s = conn.execute("SELECT * FROM settlements").fetchone()
        assert s["hit"] == 1

    def test_settle_idempotent(self, tmp_path):
        """Calling settle_unsettled twice should not duplicate settlements."""
        db = tmp_path / "obs.db"
        record_session(db, request={}, response=_response_with_one_2_leg(sel_a="H", sel_b="H"))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                            home_team="TeamA", away_team="TeamB",
                            home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                            home_team="TeamC", away_team="TeamD",
                            home_goals=3, away_goals=1)
            settle_unsettled(conn)
        with open_db(db) as conn:
            counts2 = settle_unsettled(conn)
            n = conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]
        assert counts2["settled"] == 0  # already settled, nothing new
        assert n == 1


# ---------- ROI ----------

class TestROI:
    def _setup_three_settled(self, db_path):
        """Helper: 3 different 2-leg parlays, 2 hit, 1 miss."""
        team_pairs = [("Arsenal","Liverpool","Inter","Fiorentina"),
                       ("Chelsea","Spurs","Milan","Roma"),
                       ("United","City","Juventus","Lazio")]
        for i, ((sel_a, sel_b, hg, ag), tp) in enumerate(zip([
            ("H", "H", 2, 0),
            ("H", "A", 2, 0),
            ("H", "H", 1, 0),
        ], team_pairs)):
            resp = _response_with_one_2_leg(sel_a=sel_a, sel_b=sel_b)
            ah, aw, ih, iw = tp
            resp["single_match_predictions"][0]["home_team"] = ah
            resp["single_match_predictions"][0]["away_team"] = aw
            resp["single_match_predictions"][1]["home_team"] = ih
            resp["single_match_predictions"][1]["away_team"] = iw
            resp["recommendations"][0]["legs"][0]["match_id"] = f"EPL_{ah}_vs_{aw}"
            resp["recommendations"][0]["legs"][1]["match_id"] = f"ITA_SERIE_A_{ih}_vs_{iw}"
            record_session(db_path, request={}, response=resp)
            with open_db(db_path) as conn:
                upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                                home_team=ah, away_team=aw,
                                home_goals=hg, away_goals=ag)
                upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                                home_team=ih, away_team=iw,
                                home_goals=3, away_goals=1)
        with open_db(db_path) as conn:
            settle_unsettled(conn)

    def test_headline(self, tmp_path):
        db = tmp_path / "obs.db"
        self._setup_three_settled(db)
        with open_db(db) as conn:
            h = compute_headline(conn)
        assert h.n_settled == 3
        assert h.n_hit == 2
        assert h.n_miss == 1
        assert h.total_stake == 30.0  # 3 × 10
        # Each hit pays 10 × 2.5 × 3 = 75, two hits = 150 payout; profit = 150 - 30 = 120
        assert h.total_payout == pytest.approx(150.0)
        assert h.profit_loss == pytest.approx(120.0)
        assert h.roi == pytest.approx(4.0)

    def test_group_by_k_legs(self, tmp_path):
        db = tmp_path / "obs.db"
        self._setup_three_settled(db)
        with open_db(db) as conn:
            by_k = group_by_k_legs(conn)
        assert len(by_k) == 1
        assert by_k[0]["k_legs"] == 2
        assert by_k[0]["n"] == 3

    def test_group_by_league(self, tmp_path):
        db = tmp_path / "obs.db"
        self._setup_three_settled(db)
        with open_db(db) as conn:
            by_lg = group_by_league(conn)
        # First leg's league should be EPL (matches our test setup)
        leagues = {r["league"] for r in by_lg}
        assert "EPL" in leagues

    def test_calibration(self, tmp_path):
        db = tmp_path / "obs.db"
        self._setup_three_settled(db)
        with open_db(db) as conn:
            cal = calibration_buckets(conn, n_bins=5)
        # We have predictions around 0.16 → should fall in 0-20% bucket
        assert len(cal) >= 1
        for b in cal:
            assert 0 <= b["avg_predicted"] <= 1
            assert 0 <= b["actual_hit_rate"] <= 1


class TestNullableLambdasV3:
    """🚨 2026-09-22 — λ 缺失时写 NULL,**不编 0.0**。

    ## 病史

    `single_predictions.lambda_home` 原本是 `REAL NOT NULL`,于是非模型会话
    (`manual_bet` / `market_handicap`)被逼着写 **`0.0`** —— 一个**长得完全合法
    的数**。`AVG(lambda_home)` 不会报错,只会悄悄偏低。
    同族已经咬过一次:Layer A 温度校准的拟合池混进过全零 1X2,
    「9 of the 40 live pairs were such poison」(体检 Wave2),修法是允许清单。
    ⇒ 允许清单是对的,但**每个新消费者都得记得加**。这条从源头去掉那个谎。

    ⭐ 同本仓 `odds_source` 那条的理由:没有可推断的值就留 NULL,
       **诚实地说「不知道」**。
    """

    def _prod_db(self):
        db = Path(__file__).resolve().parents[2] / "data/v4_observation.db"
        if not db.exists():
            pytest.skip("观测库不在这个 checkout 里")
        return db

    def test_no_row_carries_a_fabricated_lambda(self) -> None:
        """⭐ 结论:库里不许再有 `λ <= 0`。"""
        import sqlite3
        conn = sqlite3.connect(f"file:{self._prod_db()}?mode=ro", uri=True)
        n_all = conn.execute("SELECT COUNT(*) FROM single_predictions").fetchone()[0]
        assert n_all >= 100, f"人口非平凡:只有 {n_all} 行"
        bad = conn.execute(
            "SELECT COUNT(*) FROM single_predictions "
            "WHERE lambda_home <= 0 OR lambda_away <= 0").fetchone()[0]
        assert bad == 0, f"{bad} 行带着编出来的 λ<=0 —— 迁移没跑,或者有写入方还在编 0.0"

    def test_model_rows_always_have_a_real_lambda(self) -> None:
        """⭐ 反向:模型行**必须**有 λ。NULL 只属于非模型行。"""
        import sqlite3
        conn = sqlite3.connect(f"file:{self._prod_db()}?mode=ro", uri=True)
        n = conn.execute("""
            SELECT COUNT(*) FROM single_predictions s
            JOIN recommendation_sessions r ON r.session_id = s.session_id
            WHERE r.model_type IN ('catboost','lightgbm')
              AND (s.lambda_home IS NULL OR s.lambda_away IS NULL)""").fetchone()[0]
        assert n == 0, f"{n} 行是模型行却没有 λ —— 那是真的丢了数据,不是「没有」"

    def test_lambda_positive_is_NOT_a_valid_model_row_predicate(self) -> None:
        """🚨 **本类最要紧的一条** —— 钉住一个**活的反例**。

        我 2026-09-22 做总进球校准时,第一版人口写的是 `lambda_home > 0`。
        那是个**代理**:它假设「有正的 λ ⇒ 是模型算的」。

        库里已经有反例:`user_directional_combo` 会话带着**手填**的 λ
        (1.31 / 1.89 —— 两位小数是它的指纹,模型 λ 是 1.142398766… 那种全精度)。
        ⇒ 代理会把它们放进模型人口,而**不会有任何东西报错**。

        正确判据永远是 `model_type`。这条断言在反例消失那天会红 ——
        那时该重读本注释再决定,**别顺手把断言删掉**。
        """
        import sqlite3
        conn = sqlite3.connect(f"file:{self._prod_db()}?mode=ro", uri=True)
        n = conn.execute("""
            SELECT COUNT(*) FROM single_predictions s
            JOIN recommendation_sessions r ON r.session_id = s.session_id
            WHERE s.lambda_home > 0
              AND r.model_type IS NOT NULL
              AND r.model_type NOT IN ('catboost','lightgbm')""").fetchone()[0]
        assert n > 0, (
            "库里已经没有「非模型行带正 λ」的反例了 —— 本条的理由要重查。"
            "⚠️ 别因此就认为 `λ>0` 变安全了:它依然是个代理。")

    def test_the_manual_bet_writer_writes_NULL_not_zero(self, tmp_path) -> None:
        """🚨 承重:钉住**写入方**,不只是库的当前状态。

        上面两条查的是库里有没有 λ<=0 —— 但库已经被迁移修好了。
        如果写入方退回 `0.0`,要等到下一次手工记注单、再等到有人跑那条断言
        才会发现。这条直接打写入方。
        """
        import sqlite3
        from nutmeg.v4.observation.recorder import record_manual_bet
        db = tmp_path / "m.db"
        record_manual_bet(db, bet={
            "league": "EPL", "match_date": "2026-01-01",
            "home_team": "A", "away_team": "B",
            "market_type": "1x2", "outcome": "H",
            "odds": 2.0, "probability": 0.55, "stake": 100.0, "bankroll": 1000.0,
        })
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT lambda_home, lambda_away, p_home_1x2 FROM single_predictions").fetchone()
        assert row is not None, "手工注单没写出 single_predictions 行"
        assert row[0] is None and row[1] is None, f"λ 又被编成了 {row[0]!r}/{row[1]!r}"
        assert row[2] is None, f"模型 1X2 又被编成了 {row[2]!r}"

    def test_the_second_run_writes_nothing_at_all(self, tmp_path) -> None:
        """🚨 幂等**不等于**无害重复 —— 这条钉「第二次一行都不写」。

        变异检验实测:把那句 `if not info.get("lambda_home", 0): return` 拿掉,
        上面那条「幂等且不丢行」**照样全绿** —— 因为重复重建也会得到同样的结果,
        只是每次 `open_db` 都白重建一次 798 行的表。而 27 个 launchd cron
        一直在开这个库。
        ⇒ 用 `total_changes` 当行为探针:已经迁移过的库上再调一次,写入行数必须是 0。
        """
        import sqlite3
        from nutmeg.v4.observation.store import _migrate_nullable_lambdas, open_db
        db = tmp_path / "idem.db"
        c = sqlite3.connect(db)
        c.executescript("""
            CREATE TABLE recommendation_sessions (session_id INTEGER PRIMARY KEY, model_type TEXT);
            CREATE TABLE single_predictions (
                prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL, match_date TEXT NOT NULL, league TEXT NOT NULL,
                home_team TEXT NOT NULL, away_team TEXT NOT NULL,
                lambda_home REAL NOT NULL, lambda_away REAL NOT NULL,
                p_home_1x2 REAL NOT NULL, p_draw_1x2 REAL NOT NULL, p_away_1x2 REAL NOT NULL,
                handicap_home INTEGER, p_home_handicap REAL, p_draw_handicap REAL, p_away_handicap REAL);
            INSERT INTO recommendation_sessions VALUES (1,'catboost');
            INSERT INTO single_predictions
              (session_id,match_date,league,home_team,away_team,lambda_home,lambda_away,
               p_home_1x2,p_draw_1x2,p_away_1x2)
            VALUES (1,'2026-01-01','EPL','A','B',1.5,1.2,0.5,0.3,0.2);
        """)
        c.commit(); c.close()
        with open_db(db):                      # 第一次:真迁移
            pass
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        before = conn.total_changes
        _migrate_nullable_lambdas(conn)        # 第二次:必须是 no-op
        assert conn.total_changes == before, (
            f"已迁移的库上又写了 {conn.total_changes - before} 行 —— 幂等守卫没生效,"
            f"每次 open_db 都会白重建一次整张表")
        conn.close()

    def test_the_migration_is_idempotent_and_loses_nothing(self, tmp_path) -> None:
        """⭐ 重建表最怕丢行。用**旧 schema** 的合成库跑两遍。"""
        import sqlite3
        from nutmeg.v4.observation.store import open_db
        db = tmp_path / "old.db"
        c = sqlite3.connect(db)
        c.executescript("""
            CREATE TABLE recommendation_sessions (session_id INTEGER PRIMARY KEY, model_type TEXT);
            CREATE TABLE single_predictions (
                prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL, match_date TEXT NOT NULL, league TEXT NOT NULL,
                home_team TEXT NOT NULL, away_team TEXT NOT NULL,
                lambda_home REAL NOT NULL, lambda_away REAL NOT NULL,
                p_home_1x2 REAL NOT NULL, p_draw_1x2 REAL NOT NULL, p_away_1x2 REAL NOT NULL,
                handicap_home INTEGER, p_home_handicap REAL, p_draw_handicap REAL, p_away_handicap REAL);
            INSERT INTO recommendation_sessions VALUES (1,'catboost'),(2,'manual');
            INSERT INTO single_predictions
              (session_id,match_date,league,home_team,away_team,lambda_home,lambda_away,
               p_home_1x2,p_draw_1x2,p_away_1x2)
            VALUES (1,'2026-01-01','EPL','A','B',1.5,1.2,0.5,0.3,0.2),
                   (2,'2026-01-01','EPL','C','D',0.0,0.0,0.0,0.0,0.0);
        """)
        c.commit(); c.close()
        for _ in range(2):
            with open_db(db):
                pass
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        assert c.execute("SELECT COUNT(*) FROM single_predictions").fetchone()[0] == 2, "重建丢行了"
        lam = c.execute("SELECT lambda_home FROM single_predictions ORDER BY prediction_id").fetchall()
        assert lam[0][0] == 1.5, "真 λ 被改了"
        assert lam[1][0] is None, "编出来的 0.0 没有变成 NULL"
        p = c.execute("SELECT p_home_1x2 FROM single_predictions ORDER BY prediction_id").fetchall()
        assert p[0][0] == 0.5 and p[1][0] is None
        assert c.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0] == "3"

