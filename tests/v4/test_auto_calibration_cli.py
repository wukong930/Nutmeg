"""V10 W2 Day 2 — tests for nutmeg-auto-calibration CLI."""
from __future__ import annotations

from pathlib import Path

import pytest

from nutmeg.v4.cli.auto_calibration import main, render_markdown
from nutmeg.v4.observation.auto_calibration import DriftProposal
from tests.v4.test_auto_calibration import _seed_db_with_calibration_pairs


class TestRenderMarkdown:
    """Pure-function tests for the markdown card."""

    def test_ship_verdict_when_should_apply(self):
        prop = DriftProposal(
            proposed_T=1.15, current_T=1.0,
            log_loss_before=1.05, log_loss_after=1.02, log_loss_delta=0.03,
            p_value=0.04, n_train=50, n_holdout=12,
            train_window=("2026-05-01", "2026-05-18"),
            holdout_window=("2026-05-19", "2026-05-25"),
            should_apply=True, reason="ship gate PASSED",
        )
        md = render_markdown(prop, "test.db")
        assert "✅ SHIP" in md
        assert "1.1500" in md  # proposed T
        assert "ship gate PASSED" in md
        assert "Run with `--apply`" in md

    def test_hold_verdict_when_not_should_apply(self):
        prop = DriftProposal(
            proposed_T=1.20, current_T=1.0,
            log_loss_before=1.05, log_loss_after=1.04, log_loss_delta=0.01,
            p_value=0.45, n_train=50, n_holdout=12,
            should_apply=False, reason="bootstrap p too high",
        )
        md = render_markdown(prop, "test.db")
        assert "🛑 HOLD" in md
        assert "bootstrap p too high" in md
        assert "No change" in md

    def test_handles_nan_metrics_gracefully(self):
        prop = DriftProposal(
            proposed_T=1.0, current_T=1.0,
            log_loss_before=float("nan"), log_loss_after=float("nan"),
            log_loss_delta=float("nan"), p_value=float("nan"),
            n_train=5, n_holdout=0,
            should_apply=False, reason="insufficient train data",
        )
        md = render_markdown(prop, "test.db")
        assert "🛑 HOLD" in md
        # Renders without crashing; "n/a" appears in metric cells
        assert "n/a" in md

    def test_ship_gate_table_shows_both_checks(self):
        prop = DriftProposal(
            proposed_T=1.15, current_T=1.0,
            log_loss_before=1.05, log_loss_after=1.04,
            log_loss_delta=0.01, p_value=0.30,
            n_train=50, n_holdout=12,
            should_apply=False,
        )
        md = render_markdown(prop, "test.db")
        # Both ship-gate rows must appear
        assert "log-loss Δ ≥" in md
        assert "bootstrap p ≤" in md


class TestCliEndToEnd:
    """Real CLI invocations on a synthetic observation DB."""

    def test_dry_run_does_not_write_journal(self, tmp_path: Path, capsys):
        db = tmp_path / "obs.db"
        _seed_db_with_calibration_pairs(db, n=60, days_back_start=50, days_back_end=2)

        rc = main([
            "--db", str(db),
            "--lookback-weeks", "10",
            "--holdout-weeks", "2",
            "--min-samples", "20",
            "--n-bootstrap", "100",
            "--quiet",
        ])
        # rc 0 = ship gate didn't pass, OR 2 = passed.
        # On this synthetic data, bootstrap p often misses 0.10 threshold
        # because the holdout window is small — either outcome is valid.
        assert rc in (0, 2)

        # No journal entry should exist
        from nutmeg.v4.observation.auto_calibration import fetch_latest_journal_entry
        latest = fetch_latest_journal_entry(db)
        # Dry-run: the journal table may exist (ensure_calibration_journal
        # is idempotent) but should have no rows from this run.
        assert latest is None

    def test_apply_writes_journal_entry(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        _seed_db_with_calibration_pairs(db, n=60, days_back_start=50, days_back_end=2)

        rc = main([
            "--db", str(db),
            "--lookback-weeks", "10",
            "--holdout-weeks", "2",
            "--min-samples", "20",
            "--n-bootstrap", "100",
            "--apply",
            "--quiet",
        ])
        assert rc in (0, 2)

        from nutmeg.v4.observation.auto_calibration import fetch_latest_journal_entry
        latest = fetch_latest_journal_entry(db)
        assert latest is not None
        assert latest["action"] == "propose"
        assert latest["n_train"] > 0
        assert latest["proposed_T"] > 0

    def test_missing_db_returns_1(self, tmp_path: Path):
        rc = main([
            "--db", str(tmp_path / "nope.db"),
            "--quiet",
        ])
        assert rc == 1

    def test_writes_report_to_file(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        _seed_db_with_calibration_pairs(db, n=60, days_back_start=50, days_back_end=2)
        out = tmp_path / "report.md"

        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--out", str(out),
            "--quiet",
        ])
        assert rc in (0, 2)
        assert out.exists()
        body = out.read_text()
        assert "Auto-T Calibration Drift Report" in body
        assert "Ship gate" in body

    def test_exit_2_when_gate_passes_and_action_is_propose(self, tmp_path: Path):
        """Hard to deterministically trigger — but if it DOES pass, rc must be 2."""
        db = tmp_path / "obs.db"
        # Larger sample → more likely the gate passes
        _seed_db_with_calibration_pairs(db, n=200, days_back_start=50, days_back_end=2)

        rc = main([
            "--db", str(db),
            "--lookback-weeks", "10",
            "--holdout-weeks", "2",
            "--min-samples", "30",
            "--max-p-value", "0.5",  # loose to ensure pass on this small-sample synthetic
            "--n-bootstrap", "200",
            "--quiet",
        ])
        # With p_value threshold 0.5 and overconfident sharp=0.7 data,
        # the gate should pass → rc=2
        assert rc == 2


class TestCliArgparseDefaults:
    def test_default_lookback_8w(self):
        # Import default constants and ensure they match V10 W2 design
        from nutmeg.v4.cli.auto_calibration import (
            DEFAULT_LOOKBACK_WEEKS,
            DEFAULT_HOLDOUT_WEEKS,
            DEFAULT_MIN_SAMPLES,
        )
        assert DEFAULT_LOOKBACK_WEEKS == 8
        assert DEFAULT_HOLDOUT_WEEKS == 2
        assert DEFAULT_MIN_SAMPLES == 30
