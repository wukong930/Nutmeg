"""V10 W2 Day 1 — tests for auto-T calibration drift correction."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pytest

from nutmeg.v4.observation.auto_calibration import (
    CalibrationPair,
    DEFAULT_MAX_P_VALUE,
    DEFAULT_MIN_LOG_LOSS_GAIN,
    DriftProposal,
    apply_post_temperature,
    bootstrap_p_value,
    ensure_calibration_journal,
    fetch_latest_journal_entry,
    fit_post_temperature,
    load_calibration_pairs,
    log_loss_1x2,
    propose_drift_correction,
    record_calibration_journal,
    split_train_holdout,
)
from nutmeg.v4.observation.store import (
    insert_session,
    open_db,
    upsert_outcome,
)


@pytest.fixture(autouse=True)
def _pre_era_fixtures_ok(monkeypatch):
    # 体检 W1(D7)时代下界按真实生产史钉在 2026-07-15;本文件的合成 fixture 回填在
    # now−50d..now−1d,会跨过那条界。这些测试模拟「同一 artifact 的干净窗口」,把界
    # 推到史前;时代过滤本身的行为锁在 tests/v4/test_hc_wave1.py::TestEraFilter。
    import nutmeg.v4.observation.prediction_log as _pl
    monkeypatch.setattr(_pl, "CURRENT_ARTIFACT_ERA_START", "2000-01-01T00:00:00")


# ---------- pure-math tests ---------------------------------------------

class TestApplyPostTemperature:
    def test_identity_at_T_equals_1(self):
        p = np.array([0.5, 0.3, 0.2])
        np.testing.assert_allclose(apply_post_temperature(p, T=1.0), p, atol=1e-9)

    def test_flatten_at_T_greater_than_1(self):
        p = np.array([0.7, 0.2, 0.1])
        out = apply_post_temperature(p, T=2.0)
        # Highest prob shrinks; lowest grows; sum preserved
        assert out[0] < p[0]
        assert out[2] > p[2]
        assert abs(out.sum() - 1.0) < 1e-9

    def test_sharpen_at_T_less_than_1(self):
        p = np.array([0.5, 0.3, 0.2])
        out = apply_post_temperature(p, T=0.5)
        assert out[0] > p[0]
        assert out[2] < p[2]

    def test_2d_input(self):
        p = np.array([[0.5, 0.3, 0.2], [0.4, 0.4, 0.2]])
        out = apply_post_temperature(p, T=1.5)
        assert out.shape == (2, 3)
        np.testing.assert_allclose(out.sum(axis=1), 1.0, atol=1e-9)

    def test_handles_extreme_probabilities(self):
        # Near-zero prob shouldn't crash
        p = np.array([0.99, 0.005, 0.005])
        out = apply_post_temperature(p, T=1.0)
        assert np.isfinite(out).all()


class TestLogLoss1X2:
    def test_perfect_prediction(self):
        probs = np.array([[1.0, 0.0, 0.0]])
        outcomes = np.array([0])
        # Clipped, but should be near 0
        assert log_loss_1x2(probs, outcomes) < 0.001

    def test_uniform_prediction(self):
        probs = np.array([[1/3, 1/3, 1/3]])
        outcomes = np.array([0])
        assert log_loss_1x2(probs, outcomes) == pytest.approx(np.log(3), abs=1e-6)

    def test_skips_unplayed(self):
        probs = np.array([[0.5, 0.3, 0.2], [0.5, 0.3, 0.2]])
        outcomes = np.array([0, -1])
        # 1 row counts (log(0.5)), 1 skipped
        assert log_loss_1x2(probs, outcomes) == pytest.approx(-np.log(0.5))


class TestFitPostTemperature:
    def test_returns_T_close_to_1_for_well_calibrated_data(self):
        # Synthetic: probs match outcomes proportions → T ≈ 1
        rng = np.random.default_rng(42)
        n = 200
        true_probs = rng.dirichlet([3, 2, 2], n)
        outcomes = np.array([rng.choice(3, p=true_probs[i]) for i in range(n)])
        T = fit_post_temperature(true_probs, outcomes)
        # Should be near 1 (within the bounded search range)
        assert 0.7 < T < 1.5, f"T should be near 1; got {T}"

    def test_returns_T_greater_than_1_for_overconfident_data(self):
        # Inject overconfidence: sharpen probs but keep outcomes random
        rng = np.random.default_rng(42)
        n = 200
        # Generate "underlying" reasonable probs
        latent = rng.dirichlet([3, 2, 2], n)
        # Sharpen to make the SAVED probs over-confident
        sharp = apply_post_temperature(latent, T=0.5)
        # Outcomes drawn from the LATENT (true) distribution
        outcomes = np.array([rng.choice(3, p=latent[i]) for i in range(n)])
        # Optimal post-T should re-flatten (T > 1)
        T = fit_post_temperature(sharp, outcomes)
        assert T > 1.0, f"T should flatten overconfident data; got {T}"

    def test_returns_one_for_empty(self):
        assert fit_post_temperature(np.empty((0, 3)), np.array([], dtype=int)) == 1.0


class TestBootstrapPValue:
    def test_identical_T_gives_high_p(self):
        # T_old == T_new → p-value should be high (no improvement)
        rng = np.random.default_rng(0)
        n = 100
        probs = rng.dirichlet([2, 1, 1], n)
        outcomes = rng.integers(0, 3, n)
        p = bootstrap_p_value(probs, outcomes, T_old=1.0, T_new=1.0, n_bootstrap=200)
        # With identical T, log_loss equal → "T_new >= T_old" in EVERY resample
        assert p == 1.0

    def test_strongly_better_T_gives_low_p(self):
        # Build data where T=1.5 should be reliably better than T=0.5
        rng = np.random.default_rng(0)
        n = 500
        latent = rng.dirichlet([3, 2, 2], n)
        sharp = apply_post_temperature(latent, T=0.5)  # over-confident saved probs
        outcomes = np.array([rng.choice(3, p=latent[i]) for i in range(n)])
        p = bootstrap_p_value(sharp, outcomes, T_old=1.0, T_new=2.0, n_bootstrap=500)
        # T_new=2 reflattens; should reliably beat T_old=1 → low p
        assert p < 0.10, f"p-value should be < 0.10; got {p}"


# ---------- DB integration tests ----------------------------------------

def _seed_db_with_calibration_pairs(
    db_path: Path,
    n: int = 60,
    *,
    days_back_start: int = 50,
    days_back_end: int = 1,
) -> None:
    """Populate single_predictions + match_outcomes with synthetic data."""
    rng = np.random.default_rng(42)
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    dates_iso = [
        (now - dt.timedelta(days=int(d))).date().isoformat()
        for d in np.linspace(days_back_start, days_back_end, n)
    ]

    with open_db(db_path) as conn:
        for i in range(n):
            session_id = insert_session(
                conn,
                bankroll=1000.0,
                model_cutoff="2024-08-01",
                model_trained_at="2024-08-01T00:00:00+00:00",
                n_fixtures=1,
                n_recommendations=0,
                request={},
                metadata={"test": True},
            )
            # Backdate the session
            conn.execute(
                "UPDATE recommendation_sessions SET created_at=? WHERE session_id=?",
                ((now - dt.timedelta(days=int(np.linspace(days_back_start, days_back_end, n)[i]))).isoformat(), session_id),
            )
            # Synthesize a true probability and an outcome
            latent = rng.dirichlet([3, 2, 2])
            outcome = rng.choice(3, p=latent)
            # Insert a single_prediction with slightly overconfident probs
            sharp = apply_post_temperature(latent, T=0.7)
            conn.execute(
                """
                INSERT INTO single_predictions
                  (session_id, match_date, league, home_team, away_team,
                   lambda_home, lambda_away,
                   p_home_1x2, p_draw_1x2, p_away_1x2)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, dates_iso[i], "EPL",
                    f"Home{i}", f"Away{i}",
                    1.5, 1.0,
                    float(sharp[0]), float(sharp[1]), float(sharp[2]),
                ),
            )
            # Outcome: convert 0/1/2 to home_goals/away_goals
            if outcome == 0:
                hg, ag = 2, 1
            elif outcome == 1:
                hg, ag = 1, 1
            else:
                hg, ag = 1, 2
            upsert_outcome(
                conn,
                match_date=dates_iso[i],
                league="EPL",
                home_team=f"Home{i}",
                away_team=f"Away{i}",
                home_goals=hg,
                away_goals=ag,
            )


class TestLoadCalibrationPairs:
    def test_returns_empty_for_no_data(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        with open_db(db):
            pass  # init schema
        pairs = load_calibration_pairs(db, weeks=4)
        assert pairs == []

    def test_loads_seeded_data(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        _seed_db_with_calibration_pairs(db, n=50)
        pairs = load_calibration_pairs(db, weeks=10)
        assert len(pairs) == 50
        for p in pairs[:3]:
            assert 0 < p.p_home < 1
            assert p.outcome in (0, 1, 2)

    def test_filters_by_week_window(self, tmp_path: Path):
        # Half within 2 weeks, half outside
        db = tmp_path / "obs.db"
        _seed_db_with_calibration_pairs(db, n=30, days_back_start=40, days_back_end=1)
        # 2-week lookback should drop the older half
        pairs_2w = load_calibration_pairs(db, weeks=2)
        pairs_10w = load_calibration_pairs(db, weeks=10)
        assert len(pairs_2w) < len(pairs_10w)

    def test_includes_model_board_prediction_log(self, tmp_path: Path):
        """V12 W8j — Layer A also feeds off league_predictions (the big
        model-board stream). model_mode=0 rows only: market-mode p_* are the
        Pinnacle de-vig, not model output, and must not calibrate the model."""
        from nutmeg.v4.observation.prediction_log import (
            record_league_prediction,
            settle_league_predictions,
        )
        db = tmp_path / "obs.db"
        with open_db(db):
            pass  # init base schema
        now = dt.datetime.now(dt.UTC)
        recent = (now - dt.timedelta(days=3)).date().isoformat()

        def mk(home: str, away: str, market_mode: bool) -> None:
            # ESP_LA_LIGA (top division) is never in a playoff window, so the
            # B3 playoff filter stays inert here — this test isolates the
            # market_mode dimension. (ESP_SEGUNDA_DIVISION would make `recent`
            # land in a playoff window on some run-dates and drop both rows.)
            record_league_prediction(str(db), {
                "date": recent, "league": "ESP_LA_LIGA",
                "home_team": home, "away_team": away, "kickoff_utc": None,
                "market_mode": market_mode,
                "p_home_1x2": 0.5, "p_draw_1x2": 0.3, "p_away_1x2": 0.2,
                "psc_home": 2.0, "psc_draw": 3.4, "psc_away": 3.6,
            })
        mk("Aaa", "Bbb", False)   # model-mode  → feeds calibration
        mk("Ccc", "Ddd", True)    # market-mode → must be excluded
        fx = [
            {"teams": {"home": {"name": n[0]}, "away": {"name": n[1]}},
             "fixture": {"status": {"short": "FT"}},
             "score": {"fulltime": {"home": 2, "away": 0}},
             "goals": {"home": 2, "away": 0}}
            for n in [("Aaa", "Bbb"), ("Ccc", "Ddd")]
        ]
        settle_league_predictions(str(db), fetch_fixtures=lambda d, lg: fx,
                                  today=now.date())
        keys = {(p.home_team, p.away_team) for p in load_calibration_pairs(db, weeks=4)}
        assert ("Aaa", "Bbb") in keys       # model-mode prediction feeds Layer A
        assert ("Ccc", "Ddd") not in keys   # market-mode (de-vig) excluded

    def test_excludes_playoff_blended_from_calibration(self, tmp_path: Path,
                                                       monkeypatch):
        """AUDIT FIX (B3): playoff/barrage league_predictions rows carry a
        70%-Pinnacle-blended 1X2 (_calc_predictions), NOT pure model output.
        Even though they are logged market_mode=0, they must never feed Layer A
        calibration — re-detected at read time and skipped. detect_playoff is
        monkeypatched so the verdict is deterministic regardless of run-date
        (the real calendar windows drift relative to `now`)."""
        import nutmeg.v4.observation.auto_calibration as ac
        from nutmeg.v4.observation.prediction_log import (
            record_league_prediction,
            settle_league_predictions,
        )
        monkeypatch.setattr(
            ac, "detect_playoff",
            lambda lg, d: object() if lg == "PLAYOFF_LG" else None,
        )
        db = tmp_path / "obs.db"
        with open_db(db):
            pass  # init base schema
        now = dt.datetime.now(dt.UTC)
        recent = (now - dt.timedelta(days=3)).date().isoformat()

        def mk(league: str, home: str, away: str) -> None:
            record_league_prediction(str(db), {
                "date": recent, "league": league,
                "home_team": home, "away_team": away, "kickoff_utc": None,
                "market_mode": False,  # both logged as model-board rows
                "p_home_1x2": 0.5, "p_draw_1x2": 0.3, "p_away_1x2": 0.2,
                "psc_home": 2.0, "psc_draw": 3.4, "psc_away": 3.6,
            })
        mk("NORMAL_LG", "Norm", "Al")    # pure model → feeds calibration
        mk("PLAYOFF_LG", "Play", "Off")  # playoff-blended → must be excluded
        fx = [
            {"teams": {"home": {"name": n[0]}, "away": {"name": n[1]}},
             "fixture": {"status": {"short": "FT"}},
             "score": {"fulltime": {"home": 2, "away": 0}},
             "goals": {"home": 2, "away": 0}}
            for n in [("Norm", "Al"), ("Play", "Off")]
        ]
        settle_league_predictions(str(db), fetch_fixtures=lambda d, lg: fx,
                                  today=now.date())
        keys = {(p.home_team, p.away_team)
                for p in load_calibration_pairs(db, weeks=4)}
        assert ("Norm", "Al") in keys        # pure model feeds Layer A
        assert ("Play", "Off") not in keys   # playoff-blended excluded


class TestSplitTrainHoldout:
    def test_holdout_is_most_recent(self):
        # Build 10 pairs spanning 10 weeks; holdout_weeks=2 → last 2 weeks
        now = dt.datetime.now(dt.UTC)
        pairs = [
            CalibrationPair(
                match_date=(now - dt.timedelta(weeks=w)).date().isoformat(),
                league="EPL", home_team="A", away_team="B",
                p_home=0.5, p_draw=0.3, p_away=0.2, outcome=0,
            )
            for w in range(10)  # weeks 0-9 ago
        ]
        train, holdout = split_train_holdout(pairs, holdout_weeks=2, as_of=now)
        # Holdout = weeks 0, 1, 2 (boundary inclusive); train = weeks 3-9
        # The "2 weeks ago" cutoff means anything on or after that date.
        assert len(holdout) == 3
        assert len(train) == 7
        # Holdout should be the MOST RECENT (smallest week-back)
        holdout_dates = sorted(p.match_date for p in holdout)
        train_dates = sorted(p.match_date for p in train)
        assert holdout_dates[0] > train_dates[-1]  # all holdout > all train


# ---------- Orchestrator -----------------------------------------------

class TestProposeDriftCorrection:
    def test_insufficient_data_returns_no_apply(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        with open_db(db):
            pass
        prop = propose_drift_correction(db, lookback_weeks=4, min_samples=30)
        assert prop.should_apply is False
        assert "insufficient" in prop.reason.lower()

    def test_overconfident_data_proposes_T_above_one(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        # Seed 60 overconfident pairs spanning 8 weeks
        _seed_db_with_calibration_pairs(db, n=80, days_back_start=55, days_back_end=2)
        prop = propose_drift_correction(
            db, lookback_weeks=10, holdout_weeks=2,
            min_samples=20, n_bootstrap=200,
        )
        # Should propose T > 1.0 (flatten overconfident sharp=0.7 probs)
        assert prop.proposed_T > 1.0, f"Expected T>1 for overconfident data; got {prop.proposed_T}"
        assert prop.n_train > 0
        # log-loss improvement on holdout should be positive (T flattens the
        # over-sharp probs that we baked in via sharp=0.7)
        assert prop.log_loss_delta > 0, (
            f"Expected positive log-loss improvement; got delta={prop.log_loss_delta}"
        )


# ---------- Audit journal ----------------------------------------------

class TestCalibrationJournal:
    def test_ensure_table_idempotent(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        ensure_calibration_journal(db)
        ensure_calibration_journal(db)  # second call is no-op
        with open_db(db) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='calibration_journal'"
            ).fetchall()
            assert len(rows) == 1

    def test_record_and_fetch_roundtrip(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        prop = DriftProposal(
            proposed_T=1.15, current_T=1.0,
            log_loss_before=1.05, log_loss_after=1.02, log_loss_delta=0.03,
            p_value=0.04, n_train=50, n_holdout=12,
            train_window=("2026-05-01", "2026-05-18"),
            holdout_window=("2026-05-19", "2026-05-25"),
            should_apply=True, reason="ship gate passed",
        )
        journal_id = record_calibration_journal(db, prop, action="propose")
        assert journal_id is not None
        latest = fetch_latest_journal_entry(db, action="propose")
        assert latest is not None
        assert latest["proposed_T"] == 1.15
        assert latest["decision"] == 1
        assert latest["reason"] == "ship gate passed"
        assert latest["n_train"] == 50

    def test_handles_nan_log_loss_fields(self, tmp_path: Path):
        """When proposal has NaN log_loss (e.g. insufficient data),
        the journal should still record (NULL in DB) — no crash."""
        db = tmp_path / "obs.db"
        prop = DriftProposal(
            proposed_T=1.0, current_T=1.0,
            log_loss_before=float("nan"), log_loss_after=float("nan"),
            log_loss_delta=float("nan"), p_value=float("nan"),
            n_train=0, n_holdout=0,
            should_apply=False, reason="insufficient data",
        )
        journal_id = record_calibration_journal(db, prop, action="propose")
        latest = fetch_latest_journal_entry(db)
        assert latest["decision"] == 0
        assert latest["log_loss_delta"] is None


class TestContaminationFilter:
    """体检 Wave2 — Layer A must only eat MODEL-engine probabilities. 9 of the
    40 live pairs were market-mode (Pinnacle de-vig P) / manual (zero-P) rows
    riding into the temperature fit."""

    def _seed_one(self, conn, *, model_type, p=(0.5, 0.3, 0.2), tag="X"):
        session_id = insert_session(
            conn, bankroll=1000.0, model_cutoff="2024-08-01",
            model_trained_at="2024-08-01T00:00:00+00:00", n_fixtures=1,
            n_recommendations=0, request={}, metadata={},
            model_type=model_type,
        )
        d = dt.datetime.now(dt.UTC).date().isoformat()
        conn.execute(
            "INSERT INTO single_predictions (session_id, match_date, league,"
            " home_team, away_team, lambda_home, lambda_away,"
            " p_home_1x2, p_draw_1x2, p_away_1x2) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (session_id, d, "EPL", f"H{tag}", f"A{tag}", 1.5, 1.0, *p),
        )
        upsert_outcome(conn, match_date=d, league="EPL", home_team=f"H{tag}",
                       away_team=f"A{tag}", home_goals=2, away_goals=1)

    def test_market_and_zero_p_rows_excluded(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        with open_db(db) as conn:
            self._seed_one(conn, model_type="catboost", tag="model")
            self._seed_one(conn, model_type="lightgbm", tag="legacy")
            self._seed_one(conn, model_type="market_handicap", tag="mkt")
            self._seed_one(conn, model_type="manual", p=(0.0, 0.0, 0.0), tag="man")
            self._seed_one(conn, model_type="user_directional_combo", tag="usr")
        pairs = load_calibration_pairs(db, weeks=4)
        teams = {p.home_team for p in pairs}
        assert teams == {"Hmodel", "Hlegacy"}, (
            f"contamination filter leaked/over-dropped: {teams}"
        )
