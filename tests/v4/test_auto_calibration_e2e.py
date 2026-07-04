"""V10 W2 Day 5 — end-to-end integration: full propose → deploy → serve →
rollback lifecycle for Layer A auto-T calibration drift correction.

These tests are the "trust but verify" layer: they exercise the same
code paths the weekly cron will execute against a real observation DB,
asserting that the CLI commands + serving code + journal table + auto-
rollback safety net compose correctly across multiple iterations.

Coverage:
  Test 1 — Bootstrap: empty DB → propose (no data) → record journal
  Test 2 — Deploy cycle: data accumulates → propose passes gate →
           --deploy writes artifact → serving picks up new T
  Test 3 — Auto-rollback: bad T deployed → fresh data shows it hurts
           → cron's --auto-rollback removes artifact + journals it
  Test 4 — Mtime cache: writing a NEW artifact takes effect on the
           next request without server restart
  Test 5 — Journal audit trail: 3 actions (propose/deploy/rollback)
           all present in the journal in temporal order
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
from pathlib import Path

import pytest

from nutmeg.v4.cli.auto_calibration import main as cli_main
from nutmeg.v4.observation.auto_calibration import (
    LIVE_T_CORRECTION_FILENAME,
    DriftProposal,
    ensure_calibration_journal,
    fetch_latest_journal_entry,
    load_artifact_correction,
    write_artifact_correction,
)
from nutmeg.v4.observation.store import open_db
from tests.v4.test_auto_calibration import _seed_db_with_calibration_pairs
from tests.v4.test_auto_calibration_rollback import _plant_correction


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "data" / "v4_model"


# ---------- Test 1: Bootstrap (empty DB, no correction) ---------------------

class TestBootstrap:
    def test_propose_with_no_data_records_insufficient_journal(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        # Empty DB — ensure the journal table exists but no calibration data
        ensure_calibration_journal(db)
        # Need at least the single_predictions/recommendation_sessions/
        # match_outcomes tables — open_db creates them all
        with open_db(db):
            pass

        rc = cli_main([
            "--db", str(db),
            "--n-bootstrap", "50",
            "--apply",
            "--quiet",
        ])
        # No data → can't propose → rc=0 (no-deploy-recommended)
        assert rc == 0
        # The journal should still get an "insufficient data" entry
        latest = fetch_latest_journal_entry(db)
        assert latest is not None
        assert latest["decision"] == 0
        assert latest["action"] == "propose"


# ---------- Test 2: Deploy cycle (gate pass → artifact written) -------------

class TestDeployCycle:
    def test_propose_then_deploy_writes_artifact(self, tmp_path: Path):
        """Cycle: propose (dry-run) → review → --action=deploy writes."""
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        # Synthetic over-confident data → propose should recommend T>1
        _seed_db_with_calibration_pairs(db, n=200, days_back_start=50, days_back_end=2)

        # Step 1: dry-run propose (no --apply, no --deploy-artifact)
        rc = cli_main([
            "--db", str(db),
            "--n-bootstrap", "200",
            "--max-p-value", "0.5",
            "--quiet",
        ])
        # On synthetic data the gate may or may not pass; both rc=0 and rc=2 OK
        assert rc in (0, 2)
        # Dry-run → no journal entry
        latest = fetch_latest_journal_entry(db)
        assert latest is None
        # No artifact
        assert not (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()

        # Step 2: deploy with --apply --action=deploy --deploy-artifact
        rc = cli_main([
            "--db", str(db),
            "--n-bootstrap", "200",
            "--max-p-value", "0.5",
            "--apply",
            "--action", "deploy",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        assert rc == 0  # --action=deploy → no rc=2 upgrade
        # Now both the journal AND the artifact should exist
        latest = fetch_latest_journal_entry(db, action="deploy")
        assert latest is not None
        assert latest["decision"] == 1
        assert latest["proposed_T"] > 0
        artifact_path = artifact_dir / LIVE_T_CORRECTION_FILENAME
        assert artifact_path.exists()
        payload = json.loads(artifact_path.read_text())
        assert payload["T"] == pytest.approx(latest["proposed_T"], abs=1e-6)
        assert "deployed_at_utc" in payload


# ---------- Test 3: Auto-rollback (bad T deployed → cron reverts) -----------

class TestAutoRollback:
    def test_full_rollback_lifecycle(self, tmp_path: Path):
        """A bad correction is planted; the weekly cron's --auto-rollback
        flag detects the harm + reverts + records a rollback journal."""
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=200, days_back_start=20, days_back_end=2)
        # Plant a bad correction 30 days ago (sharpens already-sharp data)
        _plant_correction(artifact_dir, T=0.5, days_ago=30)
        assert (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()

        # Simulate the weekly cron command
        rc = cli_main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--apply",
            "--auto-rollback",
            "--rollback-lookback-weeks", "4",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        # rc=0 → rollback short-circuited propose
        assert rc == 0
        # Artifact is GONE
        assert not (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()
        # Journal has a rollback entry
        rollback_entry = fetch_latest_journal_entry(db, action="rollback")
        assert rollback_entry is not None
        assert rollback_entry["decision"] == 1
        assert "AUTO-ROLLBACK" in rollback_entry["reason"]
        # No propose entry (short-circuited)
        propose_entry = fetch_latest_journal_entry(db, action="propose")
        assert propose_entry is None


# ---------- Test 4: Mtime cache invalidation (no server restart needed) -----

@pytest.mark.skipif(
    not ARTIFACT_PATH.exists(),
    reason="V4 model artifact not present (CI skips serving tests)",
)
class TestMtimeCacheInvalidation:
    def test_writing_new_artifact_takes_effect_without_restart(self, tmp_path: Path):
        """The serving layer's mtime cache means a fresh deploy is live
        on the very next request — no uvicorn restart required."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        tmp_art = tmp_path / "v4_model"
        shutil.copytree(ARTIFACT_PATH, tmp_art)
        os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(tmp_art)

        from nutmeg.v4.api import clear_artifact_cache, v4_router
        clear_artifact_cache()
        from nutmeg.v4.api.routes import _correction_cache
        _correction_cache.clear()

        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        client = TestClient(app)

        body = {
            "fixtures": [
                {"date": "2025-08-17", "league": "EPL",
                 "home_team": "Arsenal", "away_team": "Liverpool",
                 "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60},
            ],
        }

        # Round 1: no correction
        r1 = client.post("/api/v4/predictions/upcoming", json=body)
        assert r1.status_code == 200
        p1 = r1.json()["predictions"][0]
        baseline_ph = p1["p_home_1x2"]

        # Round 2: write T=1.4 correction
        write_artifact_correction(tmp_art, DriftProposal(proposed_T=1.4, current_T=1.0))
        # Note: NOT clearing _correction_cache — testing mtime-based invalidation
        r2 = client.post("/api/v4/predictions/upcoming", json=body)
        assert r2.status_code == 200
        p2 = r2.json()["predictions"][0]
        flat_ph = p2["p_home_1x2"]
        # The probability should have CHANGED (mtime triggered re-read)
        assert flat_ph != pytest.approx(baseline_ph, abs=1e-9), (
            "Mtime cache did not invalidate — new correction not applied. "
            f"baseline_ph={baseline_ph} flat_ph={flat_ph}"
        )

        # Round 3: bump artifact (rewrite with different T) — should re-read
        # again
        # Wait a tiny bit so mtime differs (some filesystems have 1s granularity)
        import time
        time.sleep(1.1)
        write_artifact_correction(tmp_art, DriftProposal(proposed_T=1.8, current_T=1.0))
        r3 = client.post("/api/v4/predictions/upcoming", json=body)
        p3 = r3.json()["predictions"][0]
        flatter_ph = p3["p_home_1x2"]
        # T=1.8 flattens more than T=1.4 → home prob shrinks further
        # (assuming Arsenal-Liverpool model output favors one side)
        assert flatter_ph != pytest.approx(flat_ph, abs=1e-9), (
            "Updating correction file didn't propagate via mtime cache. "
            f"flat_ph={flat_ph} flatter_ph={flatter_ph}"
        )


# ---------- Test 5: Journal audit trail across full lifecycle ---------------

class TestJournalAuditTrail:
    def test_three_actions_recorded_in_temporal_order(self, tmp_path: Path):
        """Run propose → deploy → rollback in sequence; verify the
        journal table preserves the full audit trail in the right
        order with the right action types."""
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        # Big-enough seed so all flows have data to work on
        _seed_db_with_calibration_pairs(db, n=200, days_back_start=20, days_back_end=2)

        # 1. Plain propose with --apply
        rc = cli_main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--max-p-value", "0.5",
            "--apply",
            "--quiet",
        ])
        assert rc in (0, 2)
        # 2. Deploy
        rc = cli_main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--max-p-value", "0.5",
            "--apply",
            "--action", "deploy",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        assert rc == 0
        # Verify artifact landed
        assert (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()
        # Backdate the artifact's deployed_at_utc so auto-rollback sees
        # post-deploy data (otherwise no pairs are "after" the just-now deploy)
        # Then plant a BAD T over the existing one
        artifact_path = artifact_dir / LIVE_T_CORRECTION_FILENAME
        payload = json.loads(artifact_path.read_text())
        payload["deployed_at_utc"] = (
            dt.datetime.now(dt.UTC) - dt.timedelta(days=30)
        ).isoformat()
        # Override T to a harmful value
        payload["T"] = 0.5
        artifact_path.write_text(json.dumps(payload))

        # 3. Auto-rollback
        rc = cli_main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--apply",
            "--auto-rollback",
            "--rollback-lookback-weeks", "4",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        assert rc == 0
        assert not artifact_path.exists()

        # Verify all 3 journal entries
        propose_entry = fetch_latest_journal_entry(db, action="propose")
        deploy_entry = fetch_latest_journal_entry(db, action="deploy")
        rollback_entry = fetch_latest_journal_entry(db, action="rollback")
        assert propose_entry is not None, "propose entry missing"
        assert deploy_entry is not None, "deploy entry missing"
        assert rollback_entry is not None, "rollback entry missing"
        # Temporal order check
        ts_propose = propose_entry["recorded_at"]
        ts_deploy = deploy_entry["recorded_at"]
        ts_rollback = rollback_entry["recorded_at"]
        assert ts_propose <= ts_deploy <= ts_rollback, (
            f"Journal entries out of order: "
            f"propose={ts_propose} deploy={ts_deploy} rollback={ts_rollback}"
        )
        # Rollback reason should call out auto-rollback
        assert "AUTO-ROLLBACK" in rollback_entry["reason"]


# ---------- Test 6: Launchd plist generation sanity check -------------------

class TestLaunchdPlistContent:
    def test_setup_script_includes_calibration_job(self):
        """Sanity check: the setup script registers the V10 W2 Day 4
        calibration job with the right command + schedule."""
        setup = (REPO_ROOT / "scripts" / "setup_local_pipeline.sh").read_text()
        # Label must be present
        assert "com.nutmeg.weekly_calibration_check" in setup
        # Should invoke the right CLI module
        assert "nutmeg.v4.cli.auto_calibration" in setup
        # Should use --apply + --auto-rollback + --deploy-artifact (the
        # weekly cron's actual invocation pattern)
        assert "--apply" in setup
        assert "--auto-rollback" in setup
        assert "--deploy-artifact" in setup
        # Monday = weekday 1
        # The install_job helper takes args: label hour minute weekday script
        # Find the line for our job and check it specifies weekday=1
        lines = setup.splitlines()
        idx = next(
            i for i, l in enumerate(lines)
            if 'install_job "com.nutmeg.weekly_calibration_check"' in l
        )
        # Next line should be "  3 0 1 \"
        sched_line = lines[idx + 1].strip()
        assert sched_line.startswith("3 0 1"), (
            f"expected '3 0 1 ...' (03:00 Monday), got {sched_line!r}"
        )

    def test_teardown_script_knows_about_calibration_job(self):
        teardown = (REPO_ROOT / "scripts" / "teardown_local_pipeline.sh").read_text()
        assert "com.nutmeg.weekly_calibration_check" in teardown

    def test_health_check_script_knows_about_calibration_job(self):
        health = (REPO_ROOT / "scripts" / "health_check.sh").read_text()
        # 体检 Wave3 (P1#14) — the job list is now DERIVED from the persisted
        # plists (glob), so the calibration job is covered by construction;
        # assert the mechanism instead of one hand-copied label.
        assert 'com.nutmeg.*.plist' in health
