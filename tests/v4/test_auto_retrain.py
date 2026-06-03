"""V11 backlog #4 — tests for Layer B auto-retrain module + CLI + serving.

Mirrors the Layer A test layout (test_auto_calibration*.py):

  - Pure helpers (log-loss, bootstrap, ship gate, version label)
  - Journal schema + persistence
  - Artifact-pointer write/read/remove
  - CLI: propose / deploy / rollback flows
  - Serving: _artifact_path() honors pointer + mtime cache
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


# ============ Pure helpers ============================================

class TestLogLoss:
    def test_perfect_prediction_zero(self):
        from nutmeg.v4.observation.auto_retrain import log_loss_1x2
        probs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        out = np.array([0, 1, 2])
        assert log_loss_1x2(probs, out) < 1e-6

    def test_uniform_is_log3(self):
        from nutmeg.v4.observation.auto_retrain import log_loss_1x2
        probs = np.full((3, 3), 1.0 / 3.0)
        out = np.array([0, 1, 2])
        assert abs(log_loss_1x2(probs, out) - float(np.log(3.0))) < 1e-6

    def test_empty(self):
        from nutmeg.v4.observation.auto_retrain import log_loss_1x2
        probs = np.zeros((0, 3))
        out = np.array([], dtype=int)
        assert np.isnan(log_loss_1x2(probs, out))


class TestBootstrap:
    def test_b_strictly_better_low_p(self):
        """When B is uniformly better on every match, p ≈ 0."""
        from nutmeg.v4.observation.auto_retrain import bootstrap_p_value
        rng = np.random.default_rng(0)
        n = 100
        out = rng.integers(0, 3, size=n)
        # A predicts uniform, B always predicts the correct outcome at p=0.8
        a = np.full((n, 3), 1.0 / 3.0)
        b = np.full((n, 3), 0.1)
        b[np.arange(n), out] = 0.8
        p = bootstrap_p_value(a, b, out, n_iter=200)
        assert p < 0.05

    def test_a_strictly_better_high_p(self):
        from nutmeg.v4.observation.auto_retrain import bootstrap_p_value
        rng = np.random.default_rng(0)
        n = 100
        out = rng.integers(0, 3, size=n)
        # A is the better predictor here
        b = np.full((n, 3), 1.0 / 3.0)
        a = np.full((n, 3), 0.1)
        a[np.arange(n), out] = 0.8
        p = bootstrap_p_value(a, b, out, n_iter=200)
        assert p > 0.5

    def test_empty(self):
        from nutmeg.v4.observation.auto_retrain import bootstrap_p_value
        out = np.array([], dtype=int)
        empty = np.zeros((0, 3))
        # No samples → no claim — return 1.0
        assert bootstrap_p_value(empty, empty, out, n_iter=10) == 1.0


class TestShipGate:
    def test_all_thresholds_pass(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000,
            log_loss_after=0.995,
            p_value=0.02,
            n_train=10000,
            n_holdout=200,
        )
        assert ok is True
        assert "ship" in reason

    def test_too_few_train_matches(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000, log_loss_after=0.995,
            p_value=0.02, n_train=100, n_holdout=200,
        )
        assert ok is False
        assert "n_train" in reason

    def test_too_few_holdout_matches(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000, log_loss_after=0.995,
            p_value=0.02, n_train=10000, n_holdout=50,
        )
        assert ok is False
        assert "n_holdout" in reason

    def test_log_loss_delta_too_small(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000, log_loss_after=0.9995,  # only 0.5 milli
            p_value=0.02, n_train=10000, n_holdout=200,
        )
        assert ok is False
        assert "delta" in reason

    def test_p_value_too_high(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000, log_loss_after=0.995,
            p_value=0.20, n_train=10000, n_holdout=200,
        )
        assert ok is False
        assert "p_value" in reason

    def test_nan_log_loss_fails(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=float("nan"), log_loss_after=0.995,
            p_value=0.02, n_train=10000, n_holdout=200,
        )
        assert ok is False
        assert "NaN" in reason


class TestVersioning:
    def test_q1_label(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        assert current_quarter_version(dt.date(2026, 1, 15)) == "v_2026-Q1"
        assert current_quarter_version(dt.date(2026, 3, 31)) == "v_2026-Q1"

    def test_q2_label(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        assert current_quarter_version(dt.date(2026, 4, 1)) == "v_2026-Q2"
        assert current_quarter_version(dt.date(2026, 6, 30)) == "v_2026-Q2"

    def test_q3_label(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        assert current_quarter_version(dt.date(2026, 7, 1)) == "v_2026-Q3"

    def test_q4_label(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        assert current_quarter_version(dt.date(2026, 12, 31)) == "v_2026-Q4"

    def test_today_returns_string(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        v = current_quarter_version()
        assert v.startswith("v_")
        assert "-Q" in v


# ============ Journal persistence =====================================

@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "obs.db")


class TestJournal:
    def test_ensure_creates_table(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import ensure_retrain_journal
        ensure_retrain_journal(temp_db)
        # Idempotent — second call works too
        ensure_retrain_journal(temp_db)

    def test_record_propose(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import (
            record_retrain_journal, fetch_latest_journal_entry,
        )
        jid = record_retrain_journal(
            temp_db,
            action="propose",
            artifact_version="v_2026-Q3",
            artifact_path="/tmp/v_2026-Q3",
            log_loss_before=1.000, log_loss_after=0.995,
            log_loss_delta=0.005, p_value=0.02,
            n_train=12000, n_holdout=200,
            train_window=("2023-08-01", "2026-04-30"),
            holdout_window=("2026-05-01", "2026-06-30"),
            decision=True,
            reason="all gates passed",
        )
        assert jid >= 1
        row = fetch_latest_journal_entry(temp_db)
        assert row is not None
        assert row["action"] == "propose"
        assert row["artifact_version"] == "v_2026-Q3"
        assert row["decision"] == 1
        assert "2023-08-01 → 2026-04-30" in row["train_window"]

    def test_action_validation(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import record_retrain_journal
        with pytest.raises(ValueError):
            record_retrain_journal(
                temp_db, action="invalid",
                artifact_version="x", artifact_path="x",
            )

    def test_fetch_filters_by_action(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import (
            record_retrain_journal, fetch_latest_journal_entry,
        )
        record_retrain_journal(temp_db, action="propose",
                               artifact_version="v1", artifact_path="/x")
        record_retrain_journal(temp_db, action="deploy",
                               artifact_version="v2", artifact_path="/x")
        record_retrain_journal(temp_db, action="propose",
                               artifact_version="v3", artifact_path="/x")
        latest_propose = fetch_latest_journal_entry(temp_db, action="propose")
        assert latest_propose["artifact_version"] == "v3"
        latest_deploy = fetch_latest_journal_entry(temp_db, action="deploy")
        assert latest_deploy["artifact_version"] == "v2"

    def test_fetch_on_missing_db(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import fetch_latest_journal_entry
        missing = tmp_path / "does-not-exist.db"
        assert fetch_latest_journal_entry(missing) is None

    def test_nan_handled(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import (
            record_retrain_journal, fetch_latest_journal_entry,
        )
        record_retrain_journal(
            temp_db, action="propose",
            artifact_version="x", artifact_path="x",
            log_loss_before=float("nan"),  # should land as NULL not NaN
        )
        row = fetch_latest_journal_entry(temp_db)
        assert row["log_loss_before"] is None


# ============ Artifact pointer ========================================

class TestArtifactPointer:
    def test_write_creates_atomic(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            write_artifact_pointer, LIVE_ARTIFACT_POINTER_FILENAME,
        )
        out = write_artifact_pointer(
            tmp_path,
            version="v_2026-Q3",
            artifact_path=str(tmp_path / "v_2026-Q3"),
            previous_version="production_v5_w12",
            ship_gate_log_loss_delta=0.0024,
            ship_gate_p_value=0.018,
            n_train=12000, n_holdout=200,
            train_window=("2023-08-01", "2026-04-30"),
            holdout_window=("2026-05-01", "2026-06-30"),
        )
        assert out.name == LIVE_ARTIFACT_POINTER_FILENAME
        assert out.exists()
        payload = json.loads(out.read_text())
        assert payload["version"] == "v_2026-Q3"
        assert payload["ship_gate_log_loss_delta"] == 0.0024
        assert payload["ship_gate_p_value"] == 0.018
        # Atomic-write artifact — no .tmp left behind
        assert not (tmp_path / "live_artifact_pointer.tmp").exists()

    def test_load_returns_none_when_missing(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import load_artifact_pointer
        assert load_artifact_pointer(tmp_path) is None

    def test_load_round_trip(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            write_artifact_pointer, load_artifact_pointer,
        )
        write_artifact_pointer(
            tmp_path, version="v_2026-Q3",
            artifact_path=str(tmp_path / "target"),
            previous_version=None,
            ship_gate_log_loss_delta=0.003, ship_gate_p_value=0.04,
            n_train=10000, n_holdout=150,
            train_window=("2023-01-01", "2026-04-30"),
            holdout_window=("2026-05-01", "2026-06-30"),
        )
        ptr = load_artifact_pointer(tmp_path)
        assert ptr is not None
        assert ptr["version"] == "v_2026-Q3"
        assert ptr["previous_version"] == "production_v5_w12"

    def test_remove(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            write_artifact_pointer, remove_artifact_pointer,
        )
        write_artifact_pointer(
            tmp_path, version="v_x", artifact_path="x",
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert remove_artifact_pointer(tmp_path) is True
        assert remove_artifact_pointer(tmp_path) is False  # already gone

    def test_remove_layer_a_correction(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            remove_layer_a_correction, LAYER_A_CORRECTION_FILENAME,
        )
        # No file → False
        assert remove_layer_a_correction(tmp_path) is False
        # Create + remove
        (tmp_path / LAYER_A_CORRECTION_FILENAME).write_text('{"T": 1.05}')
        assert remove_layer_a_correction(tmp_path) is True
        assert not (tmp_path / LAYER_A_CORRECTION_FILENAME).exists()


# ============ Resolver ================================================

class TestResolveArtifactPath:
    def test_no_pointer_returns_base(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import resolve_effective_artifact_path
        assert resolve_effective_artifact_path(tmp_path) == str(tmp_path)

    def test_with_pointer_returns_target(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            write_artifact_pointer, resolve_effective_artifact_path,
        )
        target = tmp_path / "target"
        target.mkdir()
        write_artifact_pointer(
            tmp_path, version="v_x", artifact_path=str(target),
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert resolve_effective_artifact_path(tmp_path) == str(target)

    def test_pointer_to_missing_dir_falls_back(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            write_artifact_pointer, resolve_effective_artifact_path,
        )
        # Point to a non-existent target
        write_artifact_pointer(
            tmp_path, version="v_x",
            artifact_path="/does/not/exist",
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert resolve_effective_artifact_path(tmp_path) == str(tmp_path)


# ============ CLI integration =========================================

class TestCliPropose:
    def test_dry_run_returns_2_when_gate_fails(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        db = tmp_path / "obs.db"
        rc = main([
            "--db", str(db),
            "--action", "propose",
            "--log-loss-before", "1.000",
            "--log-loss-after", "0.999",  # only 0.001 — below threshold
            "--p-value", "0.02",
            "--n-train", "10000",
            "--n-holdout", "200",
        ])
        assert rc == 2  # ship gate not passed

    def test_dry_run_returns_0_when_gate_passes(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        db = tmp_path / "obs.db"
        rc = main([
            "--db", str(db),
            "--action", "propose",
            "--log-loss-before", "1.000",
            "--log-loss-after", "0.995",  # 5 milli-pt improvement
            "--p-value", "0.02",
            "--n-train", "10000",
            "--n-holdout", "200",
        ])
        assert rc == 0

    def test_apply_writes_journal_row(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import fetch_latest_journal_entry
        db = tmp_path / "obs.db"
        main([
            "--db", str(db), "--action", "propose", "--apply",
            "--log-loss-before", "1.000", "--log-loss-after", "0.995",
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
        ])
        row = fetch_latest_journal_entry(str(db))
        assert row is not None
        assert row["action"] == "propose"
        assert row["decision"] == 1

    def test_writes_report_when_out_given(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        out = tmp_path / "retrain.md"
        main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "propose",
            "--log-loss-before", "1.000", "--log-loss-after", "0.995",
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
            "--out", str(out),
        ])
        assert out.exists()
        md = out.read_text()
        assert "Layer B Quarterly Retrain" in md
        assert "🟢 **SHIP**" in md


class TestCliDeploy:
    def test_requires_candidate(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "deploy", "--apply",
            "--artifact-base", str(tmp_path / "base"),
        ])
        assert rc == 1

    def test_deploy_writes_pointer_and_clears_layer_a(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME, LAYER_A_CORRECTION_FILENAME,
        )
        base = tmp_path / "base"
        base.mkdir()
        candidate = tmp_path / "v_2026-Q3"
        candidate.mkdir()
        # Pre-existing Layer A correction
        (base / LAYER_A_CORRECTION_FILENAME).write_text('{"T": 1.05}')

        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "deploy", "--apply",
            "--candidate", str(candidate),
            "--artifact-base", str(base),
            "--version", "v_2026-Q3",
            "--log-loss-before", "1.000", "--log-loss-after", "0.995",
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
        ])
        assert rc == 0
        # Pointer was written
        assert (base / LIVE_ARTIFACT_POINTER_FILENAME).exists()
        # Layer A correction was cleared
        assert not (base / LAYER_A_CORRECTION_FILENAME).exists()

    def test_deploy_rejected_when_gate_fails(self, tmp_path):
        """AUDIT FIX (R4): deploy re-checks the ship gate. A candidate that does
        NOT pass (here log-loss WORSE than production) is refused with rc 2 and
        no pointer is written — propose-passing is no longer assumed at deploy."""
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME,
        )
        base = tmp_path / "base"
        base.mkdir()
        candidate = tmp_path / "v_2026-Q3"
        candidate.mkdir()
        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "deploy", "--apply",
            "--candidate", str(candidate), "--artifact-base", str(base),
            "--version", "v_2026-Q3",
            "--log-loss-before", "1.000", "--log-loss-after", "1.050",  # WORSE
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
        ])
        assert rc == 2
        assert not (base / LIVE_ARTIFACT_POINTER_FILENAME).exists()

    def test_deploy_override_gate_forces_through(self, tmp_path):
        """--override-gate lets an emergency manual deploy proceed despite a
        failing gate — the pointer is written (rc 0)."""
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME,
        )
        base = tmp_path / "base"
        base.mkdir()
        candidate = tmp_path / "v_2026-Q3"
        candidate.mkdir()
        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "deploy", "--apply", "--override-gate",
            "--candidate", str(candidate), "--artifact-base", str(base),
            "--version", "v_2026-Q3",
            "--log-loss-before", "1.000", "--log-loss-after", "1.050",  # WORSE
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
        ])
        assert rc == 0
        assert (base / LIVE_ARTIFACT_POINTER_FILENAME).exists()


class TestCliRollback:
    def test_rollback_clears_both_files(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME, LAYER_A_CORRECTION_FILENAME,
            write_artifact_pointer,
        )
        base = tmp_path / "base"
        base.mkdir()
        # Pre-populate pointer + Layer A correction
        write_artifact_pointer(
            base, version="v_2026-Q3", artifact_path=str(tmp_path / "target"),
            previous_version="production_v5_w12",
            ship_gate_log_loss_delta=0.003, ship_gate_p_value=0.04,
            n_train=10000, n_holdout=200,
            train_window=("", ""), holdout_window=("", ""),
        )
        (base / LAYER_A_CORRECTION_FILENAME).write_text('{"T": 1.05}')

        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "rollback", "--apply",
            "--artifact-base", str(base),
            "--reason", "ROI regressed > 5pp post-deploy",
        ])
        assert rc == 0
        assert not (base / LIVE_ARTIFACT_POINTER_FILENAME).exists()
        assert not (base / LAYER_A_CORRECTION_FILENAME).exists()

    def test_rollback_journal_row(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import fetch_latest_journal_entry
        base = tmp_path / "base"
        base.mkdir()
        db = tmp_path / "obs.db"
        main([
            "--db", str(db),
            "--action", "rollback", "--apply",
            "--artifact-base", str(base),
            "--reason", "test rollback",
        ])
        row = fetch_latest_journal_entry(str(db), action="rollback")
        assert row is not None
        assert "test rollback" in row["reason"]


# ============ Serving (routes._artifact_path) =========================

class TestServingResolution:
    def test_no_pointer_returns_default(self, monkeypatch, tmp_path):
        """Without a pointer file, _artifact_path falls back to env / default."""
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(tmp_path))
        # Clear cache between tests
        from nutmeg.v4.api import routes
        routes._pointer_cache.clear()
        result = routes._artifact_path()
        assert result == str(tmp_path)

    def test_pointer_redirects_to_target(self, monkeypatch, tmp_path):
        from nutmeg.v4.api import routes
        from nutmeg.v4.observation.auto_retrain import write_artifact_pointer
        routes._pointer_cache.clear()
        base = tmp_path / "base"
        target = tmp_path / "target"
        base.mkdir()
        target.mkdir()
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        write_artifact_pointer(
            base, version="v_x", artifact_path=str(target),
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert routes._artifact_path() == str(target)

    def test_pointer_to_missing_dir_falls_back(self, monkeypatch, tmp_path):
        from nutmeg.v4.api import routes
        from nutmeg.v4.observation.auto_retrain import write_artifact_pointer
        routes._pointer_cache.clear()
        base = tmp_path / "base"
        base.mkdir()
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        write_artifact_pointer(
            base, version="v_x", artifact_path="/does/not/exist",
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert routes._artifact_path() == str(base)

    def test_mtime_cache_returns_same_path(self, monkeypatch, tmp_path):
        """Two calls with no file change → same result (cache hit)."""
        from nutmeg.v4.api import routes
        from nutmeg.v4.observation.auto_retrain import write_artifact_pointer
        routes._pointer_cache.clear()
        base = tmp_path / "base"
        target = tmp_path / "target"
        base.mkdir()
        target.mkdir()
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        write_artifact_pointer(
            base, version="v_x", artifact_path=str(target),
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        a = routes._artifact_path()
        b = routes._artifact_path()
        assert a == b == str(target)


# ============ CLI registration ========================================

class TestCliRegistered:
    def test_pyproject_lists_nutmeg_auto_retrain(self):
        proj = (REPO_ROOT / "pyproject.toml").read_text()
        assert "nutmeg-auto-retrain" in proj
        assert "nutmeg.v4.cli.auto_retrain:main" in proj

    def test_help_works(self):
        from nutmeg.v4.cli.auto_retrain import main
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
