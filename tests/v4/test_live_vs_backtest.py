"""Tests for nutmeg.v4.observation.live_vs_backtest + the migration logic
in nutmeg.v4.observation.store that adds snapshot_phase / model_type to v1
databases.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nutmeg.v4.observation import live_vs_backtest as lvb
from nutmeg.v4.observation.store import (
    SCHEMA_VERSION,
    insert_parlay_recommendation,
    insert_session,
    insert_settlement,
    open_db,
)

# ---- schema migration ----------------------------------------------------

class TestSchemaMigration:
    """A pre-W8 v1 DB (no snapshot_phase, no model_type) must round-trip through
    open_db() and gain the new columns, defaulted to 'closing' / 'lightgbm'.
    """

    def _build_v1_db(self, path: Path) -> None:
        """Hand-write a v1 schema (mirror of pre-W8 SCHEMA_SQL minus the new cols)."""
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE recommendation_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                bankroll REAL NOT NULL,
                model_cutoff TEXT,
                model_trained_at TEXT,
                n_fixtures INTEGER NOT NULL,
                n_recommendations INTEGER NOT NULL,
                request_json TEXT NOT NULL,
                metadata_json TEXT
            );
            CREATE TABLE single_predictions (
                prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER, match_date TEXT, league TEXT,
                home_team TEXT, away_team TEXT,
                lambda_home REAL, lambda_away REAL,
                p_home_1x2 REAL, p_draw_1x2 REAL, p_away_1x2 REAL,
                handicap_home INTEGER, p_home_handicap REAL,
                p_draw_handicap REAL, p_away_handicap REAL
            );
            CREATE TABLE parlay_recommendations (
                rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER, rank INTEGER, k_legs INTEGER,
                is_compound INTEGER, stake_units INTEGER, kelly_stake REAL,
                expected_return REAL, hit_probability REAL,
                ev_per_unit REAL, log_growth REAL, legs_json TEXT
            );
            CREATE TABLE match_outcomes (
                outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_date TEXT, league TEXT, home_team TEXT, away_team TEXT,
                home_goals INTEGER, away_goals INTEGER, recorded_at TEXT,
                UNIQUE(match_date, league, home_team, away_team)
            );
            CREATE TABLE settlements (
                settlement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rec_id INTEGER UNIQUE, settled_at TEXT, hit INTEGER,
                stake REAL, actual_payout REAL, profit_loss REAL,
                details_json TEXT
            );
        """)
        # Insert a v1-style row (no snapshot_phase column referenced)
        conn.execute(
            """INSERT INTO recommendation_sessions
               (created_at, bankroll, model_cutoff, model_trained_at,
                n_fixtures, n_recommendations, request_json, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("2024-01-01T12:00:00+00:00", 1000.0, "2023-12-01", "2023-12-15",
             5, 3, "{}", "{}")
        )
        conn.commit()
        conn.close()

    def test_migration_adds_snapshot_phase(self, tmp_path: Path) -> None:
        db = tmp_path / "v1.db"
        self._build_v1_db(db)

        # Opening with open_db() should migrate
        with open_db(db) as conn:
            cur = conn.execute("PRAGMA table_info(recommendation_sessions)")
            cols = {row["name"] for row in cur.fetchall()}
            assert "snapshot_phase" in cols
            assert "model_type" in cols

            # Existing row backfilled to 'closing' / 'lightgbm'
            row = conn.execute(
                "SELECT snapshot_phase, model_type FROM recommendation_sessions"
            ).fetchone()
            assert row["snapshot_phase"] == "closing"
            assert row["model_type"] == "lightgbm"

            ver = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'version'"
            ).fetchone()
            assert ver["value"] == str(SCHEMA_VERSION)

    def test_idempotent(self, tmp_path: Path) -> None:
        """Running open_db twice must not error (ALTER ADD COLUMN would fail
        on a re-run if we weren't checking PRAGMA first)."""
        db = tmp_path / "v1.db"
        self._build_v1_db(db)
        with open_db(db):
            pass
        # second open should be a no-op
        with open_db(db) as conn:
            cur = conn.execute("PRAGMA table_info(recommendation_sessions)")
            cols = {row["name"] for row in cur.fetchall()}
            assert "snapshot_phase" in cols


class TestInsertSessionPhases:
    def test_default_phase(self, tmp_path: Path) -> None:
        with open_db(tmp_path / "obs.db") as conn:
            sid = insert_session(
                conn, bankroll=1000.0, model_cutoff=None, model_trained_at=None,
                n_fixtures=5, n_recommendations=2, request={}, metadata={}
            )
            row = conn.execute(
                "SELECT snapshot_phase, model_type FROM recommendation_sessions WHERE session_id=?",
                (sid,)
            ).fetchone()
            assert row["snapshot_phase"] == "closing"
            assert row["model_type"] == "lightgbm"

    def test_explicit_phase(self, tmp_path: Path) -> None:
        with open_db(tmp_path / "obs.db") as conn:
            sid = insert_session(
                conn, bankroll=1000.0, model_cutoff=None, model_trained_at=None,
                n_fixtures=5, n_recommendations=2, request={}, metadata={},
                snapshot_phase="pre_close", model_type="catboost",
            )
            row = conn.execute(
                "SELECT snapshot_phase, model_type FROM recommendation_sessions WHERE session_id=?",
                (sid,)
            ).fetchone()
            assert row["snapshot_phase"] == "pre_close"
            assert row["model_type"] == "catboost"

    def test_invalid_phase_rejected(self, tmp_path: Path) -> None:
        with open_db(tmp_path / "obs.db") as conn, pytest.raises(
            ValueError, match="snapshot_phase must"
        ):
            insert_session(
                conn, bankroll=1000.0, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=0, request={}, metadata={},
                snapshot_phase="bogus",
            )


# ---- live_vs_backtest core logic -----------------------------------------

@pytest.fixture
def seed_obs_db(tmp_path: Path):
    """Populate a fresh observation DB with a handful of settlements at
    different snapshot phases for slice tests."""
    db = tmp_path / "obs.db"
    now = datetime.now(UTC)

    with open_db(db) as conn:
        # Manually insert sessions with crafted created_at so windowing works
        for days_ago, phase in [
            (1, "closing"), (3, "closing"), (5, "pre_close"),
            (14, "closing"), (30, "closing"),  # 30-day-old should fall outside 2-week window
        ]:
            ts = (now - timedelta(days=days_ago)).isoformat()
            conn.execute(
                """INSERT INTO recommendation_sessions
                   (created_at, bankroll, model_cutoff, model_trained_at,
                    n_fixtures, n_recommendations, request_json, metadata_json,
                    snapshot_phase, model_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, 1000.0, "2024-08-01", "2024-08-01T00:00:00+00:00",
                 4, 2, "{}", "{}", phase, "lightgbm"),
            )
            sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            # One winning and one losing recommendation per session
            for j, (hit, stake, payout, hit_p) in enumerate([
                (1, 100.0, 250.0, 0.4),
                (0, 100.0, 0.0, 0.4),
            ]):
                rid = insert_parlay_recommendation(
                    conn, sid, rank=j+1, k_legs=2, is_compound=False,
                    stake_units=1, kelly_stake=stake,
                    expected_return=payout - stake, hit_probability=hit_p,
                    ev_per_unit=0.05, log_growth=0.001, legs=[],
                )
                insert_settlement(
                    conn, rec_id=rid, hit=hit, stake=stake,
                    actual_payout=payout, profit_loss=payout - stake,
                )
    return db


def _insert_settled_session(
    conn,
    *,
    with_lineups: bool | None,
    hit: int,
    stake: float,
    payout: float,
    hit_probability: float = 0.4,
) -> int:
    metadata = {}
    if with_lineups is not None:
        metadata = {"model": {"with_lineups": with_lineups}}
    sid = insert_session(
        conn,
        bankroll=1000.0,
        model_cutoff="2024-08-01",
        model_trained_at="2024-08-01T00:00:00+00:00",
        n_fixtures=2,
        n_recommendations=1,
        request={},
        metadata=metadata,
        model_type="catboost",
    )
    rid = insert_parlay_recommendation(
        conn,
        sid,
        rank=1,
        k_legs=2,
        is_compound=False,
        stake_units=1,
        kelly_stake=stake,
        expected_return=payout - stake,
        hit_probability=hit_probability,
        ev_per_unit=0.05,
        log_growth=0.001,
        legs=[],
    )
    insert_settlement(
        conn,
        rec_id=rid,
        hit=hit,
        stake=stake,
        actual_payout=payout,
        profit_loss=payout - stake,
    )
    created_at = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE recommendation_sessions SET created_at=? WHERE session_id=?",
        (created_at, sid),
    )
    return sid


class TestSliceLiveSettled:
    def test_filters_by_window(self, seed_obs_db: Path) -> None:
        # 2-week window — should include 4 sessions (days_ago: 1, 3, 5, 14)
        start, end = lvb._window_bounds(weeks=2)
        with open_db(seed_obs_db) as conn:
            live = lvb.slice_live_settled(conn, start_iso=start, end_iso=end)
        # NB: 14 days ago is on the boundary; pytest tolerance: at least 3.
        assert live.n_sessions >= 3
        assert live.n_settled == live.n_sessions * 2  # 2 recs per session
        assert live.n_hit == live.n_sessions

    def test_filters_by_phase(self, seed_obs_db: Path) -> None:
        start, end = lvb._window_bounds(weeks=2)
        with open_db(seed_obs_db) as conn:
            pre = lvb.slice_live_settled(
                conn, start_iso=start, end_iso=end, snapshot_phase="pre_close"
            )
            closing = lvb.slice_live_settled(
                conn, start_iso=start, end_iso=end, snapshot_phase="closing"
            )
        assert pre.n_sessions == 1   # the day-5 entry
        assert closing.n_sessions >= 2

    def test_roi_math(self, seed_obs_db: Path) -> None:
        start, end = lvb._window_bounds(weeks=2)
        with open_db(seed_obs_db) as conn:
            live = lvb.slice_live_settled(conn, start_iso=start, end_iso=end)
        # Each session: 1 hit (stake 100, payout 250 → +150) + 1 miss (stake 100 → -100)
        # Net per session = +50; stake per session = 200; ROI = 25%.
        assert live.roi == pytest.approx(0.25)
        assert live.actual_hit_rate == pytest.approx(0.5)

    def test_filters_by_model_arm(self, tmp_path: Path) -> None:
        db = tmp_path / "obs.db"
        with open_db(db) as conn:
            _insert_settled_session(
                conn, with_lineups=True, hit=1, stake=100.0, payout=250.0
            )
            _insert_settled_session(
                conn, with_lineups=False, hit=0, stake=100.0, payout=0.0
            )
            _insert_settled_session(
                conn, with_lineups=None, hit=0, stake=100.0, payout=0.0
            )

            start, end = lvb._window_bounds(weeks=2)
            all_live = lvb.slice_live_settled(
                conn, start_iso=start, end_iso=end, model_arm="all"
            )
            aware = lvb.slice_live_settled(
                conn, start_iso=start, end_iso=end, model_arm="lineup_aware"
            )
            free = lvb.slice_live_settled(
                conn, start_iso=start, end_iso=end, model_arm="lineup_free"
            )

        assert all_live.n_settled == 3
        assert aware.n_sessions == 1
        assert aware.n_settled == 1
        assert aware.actual_hit_rate == pytest.approx(1.0)
        assert aware.roi == pytest.approx(1.5)
        assert free.n_sessions == 2
        assert free.n_settled == 2
        assert free.actual_hit_rate == pytest.approx(0.0)

    def test_invalid_model_arm_rejected(self, seed_obs_db: Path) -> None:
        start, end = lvb._window_bounds(weeks=2)
        with open_db(seed_obs_db) as conn, pytest.raises(ValueError, match="model_arm must"):
            lvb.slice_live_settled(
                conn, start_iso=start, end_iso=end, model_arm="unknown"
            )


class TestBacktestSliceFromPooled:
    def test_extracts_gbm_temp(self) -> None:
        pooled = {
            "test_n_full": 4792,
            "test_n_gbm": 4331,
            "gbm_dc_temp": {
                "log_loss": 0.9971, "brier": 0.5961, "hit_rate": 0.508, "ece": 0.0185,
            }
        }
        b = lvb.backtest_slice_from_pooled(pooled, cutoff="2024-08-01")
        assert b is not None
        assert b.cutoff == "2024-08-01"
        assert b.test_n_gbm == 4331
        assert b.log_loss == pytest.approx(0.9971)

    def test_none_when_no_gbm(self) -> None:
        assert lvb.backtest_slice_from_pooled({"test_n_full": 100}, cutoff="x") is None


class TestRoiBacktestSliceFromDb:
    def test_extracts_lineup_aware_reference(self, tmp_path: Path) -> None:
        db = tmp_path / "roi_backtest.db"
        with open_db(db) as conn:
            _insert_settled_session(
                conn, with_lineups=True, hit=1, stake=100.0, payout=225.0,
                hit_probability=0.35,
            )
            _insert_settled_session(
                conn, with_lineups=False, hit=0, stake=100.0, payout=0.0,
                hit_probability=0.30,
            )

        ref = lvb.roi_backtest_slice_from_db(db, arm="lineup_aware")
        assert ref.source == "roi_backtest"
        assert ref.label == "lineup-aware ROI backtest"
        assert ref.n_sessions == 1
        assert ref.n_settled == 1
        assert ref.roi == pytest.approx(1.25)
        assert ref.hit_rate == pytest.approx(1.0)
        assert ref.avg_hit_p_predicted == pytest.approx(0.35)
        assert ref.log_loss is None

    def test_missing_db_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="ROI backtest DB not found"):
            lvb.roi_backtest_slice_from_db(tmp_path / "missing.db")


class TestComputeGap:
    def _live(self, hit_rate: float = 0.5) -> lvb.LiveSlice:
        return lvb.LiveSlice(
            n_sessions=10, n_settled=20, n_hit=10, n_partial=0, n_miss=10,
            total_stake=2000, total_payout=2400, profit_loss=400, roi=0.20,
            avg_hit_p_predicted=0.45, actual_hit_rate=hit_rate,
        )

    def _backtest(self, hit_rate: float = 0.50) -> lvb.BacktestSlice:
        return lvb.BacktestSlice(
            cutoff="2024-08-01", test_n_full=4800, test_n_gbm=4300,
            log_loss=0.9971, hit_rate=hit_rate, ece=0.018,
        )

    def test_within_tolerance(self) -> None:
        report = lvb.compute_gap(self._live(0.52), self._backtest(0.50))
        # gap = +2 pp → within ±5
        assert report.over_tolerance is False
        assert report.hit_rate_gap_pp == pytest.approx(2.0)

    def test_over_tolerance_positive(self) -> None:
        report = lvb.compute_gap(self._live(0.60), self._backtest(0.50))
        assert report.over_tolerance is True
        assert report.hit_rate_gap_pp == pytest.approx(10.0)

    def test_over_tolerance_negative(self) -> None:
        report = lvb.compute_gap(self._live(0.40), self._backtest(0.50))
        assert report.over_tolerance is True
        assert report.hit_rate_gap_pp == pytest.approx(-10.0)

    def test_no_backtest_means_within(self) -> None:
        report = lvb.compute_gap(self._live(0.50), None)
        assert report.over_tolerance is False
        assert report.hit_rate_gap_pp is None

    def test_roi_reference_gap_uses_roi_and_hit_rate(self) -> None:
        backtest = lvb.BacktestSlice(
            cutoff="roi-backtest",
            test_n_full=100,
            test_n_gbm=100,
            log_loss=None,
            hit_rate=0.50,
            ece=None,
            source="roi_backtest",
            label="lineup-aware ROI backtest",
            n_sessions=20,
            n_settled=100,
            roi=0.14,
        )
        report = lvb.compute_gap(self._live(0.52), backtest)
        assert report.hit_rate_gap_pp == pytest.approx(2.0)
        assert report.roi_gap_pp == pytest.approx(6.0)
        assert report.over_tolerance is True

    def test_no_live_samples_does_not_alert(self) -> None:
        live = lvb.LiveSlice(
            n_sessions=0, n_settled=0, n_hit=0, n_partial=0, n_miss=0,
            total_stake=0.0, total_payout=0.0, profit_loss=0.0, roi=0.0,
            avg_hit_p_predicted=0.0, actual_hit_rate=0.0,
        )
        backtest = lvb.BacktestSlice(
            cutoff="roi-backtest",
            test_n_full=100,
            test_n_gbm=100,
            log_loss=None,
            hit_rate=0.50,
            ece=None,
            source="roi_backtest",
            label="lineup-aware ROI backtest",
            n_sessions=20,
            n_settled=100,
            roi=0.14,
        )
        report = lvb.compute_gap(live, backtest)
        assert report.hit_rate_gap_pp is None
        assert report.roi_gap_pp is None
        assert report.over_tolerance is False


class TestFormatReport:
    def test_contains_expected_sections(self, seed_obs_db: Path) -> None:
        report = lvb.run(
            str(seed_obs_db),
            weeks=2,
            backtest_pooled={
                "test_n_full": 4792, "test_n_gbm": 4331,
                "gbm_dc_temp": {
                    "log_loss": 0.9971, "brier": 0.5961, "hit_rate": 0.50, "ece": 0.018
                },
            },
            backtest_cutoff="2024-08-01",
        )
        out = lvb.format_report(report, weeks=2, as_of_iso="2025-01-15 10:00 UTC")
        assert "Live vs Backtest" in out
        assert "## Live (real-bet) slice" in out
        assert "## Backtest slice" in out
        assert "## Gap" in out

    def test_roi_backtest_reference_format(self, tmp_path: Path) -> None:
        live_db = tmp_path / "live.db"
        ref_db = tmp_path / "roi_backtest.db"
        with open_db(live_db) as conn:
            _insert_settled_session(
                conn, with_lineups=True, hit=1, stake=100.0, payout=220.0,
                hit_probability=0.45,
            )
        with open_db(ref_db) as conn:
            _insert_settled_session(
                conn, with_lineups=True, hit=1, stake=100.0, payout=210.0,
                hit_probability=0.40,
            )

        report = lvb.run(
            str(live_db),
            weeks=2,
            backtest_pooled=None,
            backtest_cutoff=None,
            live_model_arm="lineup_aware",
            roi_backtest_db=ref_db,
            roi_backtest_arm="lineup_aware",
        )
        out = lvb.format_report(report, weeks=2, as_of_iso="2025-01-15 10:00 UTC")
        assert report.backtest is not None
        assert report.backtest.source == "roi_backtest"
        assert "historical ROI replay" in out
        assert "ROI gap (live - backtest)" in out
