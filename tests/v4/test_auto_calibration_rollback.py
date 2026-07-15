"""V10 W2 Day 4 — tests for evaluate_active_correction + CLI auto-rollback."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pytest

from nutmeg.v4.cli.auto_calibration import main
from nutmeg.v4.observation.auto_calibration import (
    DEFAULT_ROLLBACK_LOG_LOSS_THRESHOLD,
    LIVE_T_CORRECTION_FILENAME,
    CalibrationPair,
    CorrectionEvaluation,
    DriftProposal,
    evaluate_active_correction,
    fetch_latest_journal_entry,
    load_artifact_correction,
    write_artifact_correction,
)
from tests.v4.test_auto_calibration import _seed_db_with_calibration_pairs


@pytest.fixture(autouse=True)
def _pre_era_fixtures_ok(monkeypatch):
    # 体检 W1(D7):合成 fixture 跨 2026-07-15 时代界 → 界推史前(同 test_auto_calibration.py)
    import nutmeg.v4.observation.prediction_log as _pl
    monkeypatch.setattr(_pl, "CURRENT_ARTIFACT_ERA_START", "2000-01-01T00:00:00")


def _plant_correction(
    artifact_dir: Path,
    T: float,
    *,
    days_ago: int = 30,
    current_T: float = 1.0,
) -> Path:
    """Plant a `live_T_correction.json` with `deployed_at_utc` shifted
    `days_ago` days into the past. Tests need this so the seeded
    calibration data falls AFTER the deploy time (otherwise
    evaluate_active_correction sees 0 post-deploy pairs).
    """
    prop = DriftProposal(proposed_T=T, current_T=current_T)
    path = write_artifact_correction(artifact_dir, prop)
    payload = json.loads(path.read_text())
    deployed_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=days_ago)
    payload["deployed_at_utc"] = deployed_at.isoformat()
    path.write_text(json.dumps(payload))
    return path


# ---------- evaluate_active_correction (pure) -------------------------------

class TestEvaluateActiveCorrection:
    def test_returns_none_eval_when_no_correction(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        # No DB rows; the function shouldn't even need to query when no
        # correction is loaded. Just make the artifact dir empty.
        _seed_db_with_calibration_pairs(db, n=10, days_back_start=20, days_back_end=2)

        ev = evaluate_active_correction(db, artifact_dir)
        assert ev.correction is None
        assert ev.should_rollback is False
        assert "no active correction" in ev.reason
        assert ev.n_pairs == 0

    def test_keeps_correction_when_no_post_deploy_data(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=20, days_back_start=50, days_back_end=20)
        # Plant a correction deployed JUST NOW — no data after deploy
        prop = DriftProposal(proposed_T=1.10)
        path = write_artifact_correction(artifact_dir, prop)
        # Force the deployed_at to be "now" so all DB data is pre-deploy
        payload = json.loads(path.read_text())
        payload["deployed_at_utc"] = dt.datetime.now(dt.UTC).isoformat()
        path.write_text(json.dumps(payload))

        ev = evaluate_active_correction(db, artifact_dir, lookback_weeks=1)
        assert ev.n_pairs == 0
        assert ev.should_rollback is False
        assert "no post-deploy data" in ev.reason
        assert ev.deployed_T == pytest.approx(1.10)

    def test_keeps_correction_when_deployed_beats_identity(self, tmp_path: Path):
        # Build a DB where the underlying probs are over-confident
        # (sharp=0.7), so a T>1 correction should HELP, not hurt.
        # → rollback should NOT trigger.
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=120, days_back_start=20, days_back_end=2)
        # Deploy a moderately-flattening T 30 days ago so seeded data is post-deploy
        _plant_correction(artifact_dir, T=1.30, days_ago=30)

        ev = evaluate_active_correction(
            db, artifact_dir, lookback_weeks=4,
            rollback_threshold=DEFAULT_ROLLBACK_LOG_LOSS_THRESHOLD,
        )
        assert ev.n_pairs > 0
        # With overconfident sharp data, T=1.3 should beat T=1.0
        # → delta = ll_deployed - ll_identity should be NEGATIVE (deployed wins)
        assert ev.delta < 0, (
            f"deployed T=1.3 should beat identity on over-confident data; "
            f"delta={ev.delta:.4f}"
        )
        assert ev.should_rollback is False
        assert "OK" in ev.reason

    def test_triggers_rollback_when_deployed_hurts(self, tmp_path: Path):
        # Deploy a BAD T (very sharp, T=0.5) — this should over-sharpen
        # the already-sharp probs and make log-loss WORSE than identity.
        # → rollback should trigger.
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=120, days_back_start=20, days_back_end=2)
        _plant_correction(artifact_dir, T=0.5, days_ago=30)

        ev = evaluate_active_correction(
            db, artifact_dir, lookback_weeks=4,
            rollback_threshold=DEFAULT_ROLLBACK_LOG_LOSS_THRESHOLD,
        )
        assert ev.n_pairs > 0
        # Deploying T=0.5 on already-sharp data hurts log-loss
        assert ev.delta > DEFAULT_ROLLBACK_LOG_LOSS_THRESHOLD, (
            f"T=0.5 should hurt vs identity; delta={ev.delta:.4f}"
        )
        assert ev.should_rollback is True
        assert "AUTO-ROLLBACK" in ev.reason

    def test_respects_custom_rollback_threshold(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=120, days_back_start=20, days_back_end=2)
        _plant_correction(artifact_dir, T=0.5, days_ago=30)

        # With a HUGE threshold, even bad T shouldn't trigger
        ev = evaluate_active_correction(
            db, artifact_dir, rollback_threshold=10.0, lookback_weeks=4,
        )
        assert ev.should_rollback is False


# ---------- CLI --auto-rollback flow ----------------------------------------

class TestCliAutoRollback:
    def test_warns_when_apply_missing(self, tmp_path: Path, caplog):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=60, days_back_start=50, days_back_end=2)
        # Plant a correction
        _plant_correction(artifact_dir, T=0.5, days_ago=30)

        import logging
        caplog.set_level(logging.WARNING)
        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--auto-rollback",  # without --apply
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        # Should NOT have rolled back (apply missing → skip check)
        assert (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()
        assert rc in (0, 2)
        assert any("--auto-rollback requires --apply" in r.message for r in caplog.records)

    def test_warns_when_deploy_artifact_missing(self, tmp_path: Path, caplog):
        db = tmp_path / "obs.db"
        _seed_db_with_calibration_pairs(db, n=60, days_back_start=50, days_back_end=2)

        import logging
        caplog.set_level(logging.WARNING)
        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--apply",
            "--auto-rollback",  # without --deploy-artifact
            "--quiet",
        ])
        assert rc in (0, 2)
        assert any("--auto-rollback requires --apply" in r.message for r in caplog.records)

    def test_no_correction_falls_through_to_propose(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=60, days_back_start=50, days_back_end=2)

        # No correction file → rollback check is no-op → propose runs normally
        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--apply",
            "--auto-rollback",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        assert rc in (0, 2)
        # Propose should have written a "propose" journal entry
        latest = fetch_latest_journal_entry(db, action="propose")
        assert latest is not None

    def test_auto_rollback_executes_when_correction_hurts(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=120, days_back_start=20, days_back_end=2)
        # Plant a bad correction (T=0.5 over-sharpens already-sharp data)
        _plant_correction(artifact_dir, T=0.5, days_ago=30)

        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--apply",
            "--auto-rollback",
            "--rollback-lookback-weeks", "4",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        # rc=0 means rollback short-circuited (no propose ran)
        assert rc == 0
        # Artifact file must be GONE
        assert not (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()
        # Journal must have a 'rollback' entry
        latest = fetch_latest_journal_entry(db, action="rollback")
        assert latest is not None
        assert latest["decision"] == 1
        assert "AUTO-ROLLBACK" in latest["reason"]
        # And NO 'propose' entry (short-circuit)
        propose_latest = fetch_latest_journal_entry(db, action="propose")
        assert propose_latest is None

    def test_auto_rollback_no_op_when_correction_is_good(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=120, days_back_start=20, days_back_end=2)
        # Plant a HELPFUL correction (T=1.3 flattens over-confident probs)
        _plant_correction(artifact_dir, T=1.30, days_ago=30)

        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--apply",
            "--auto-rollback",
            "--rollback-lookback-weeks", "4",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        # rc could be 0 or 2 — both fine. Key: artifact RETAINED.
        assert rc in (0, 2)
        assert (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()
        # The propose flow ran (didn't short-circuit)
        propose_latest = fetch_latest_journal_entry(db, action="propose")
        assert propose_latest is not None
        # current_T in the journal should reflect the deployed T (1.30),
        # NOT the CLI default 1.0 — because auto-rollback re-baselined it
        assert propose_latest["current_T"] == pytest.approx(1.30)

    def test_rollback_writes_report_to_file(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "art"
        artifact_dir.mkdir()
        report_out = tmp_path / "report.md"
        _seed_db_with_calibration_pairs(db, n=120, days_back_start=20, days_back_end=2)
        _plant_correction(artifact_dir, T=0.5, days_ago=30)

        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--apply",
            "--auto-rollback",
            "--rollback-lookback-weeks", "4",
            "--deploy-artifact", str(artifact_dir),
            "--out", str(report_out),
            "--quiet",
        ])
        assert rc == 0
        assert report_out.exists()
        body = report_out.read_text()
        assert "AUTO-ROLLBACK" in body
        assert "Post-deploy log-loss" in body
        assert "live_T_correction.json" in body
