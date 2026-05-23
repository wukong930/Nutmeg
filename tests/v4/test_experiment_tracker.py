"""Tests for nutmeg.v4.eval.experiment_tracker (V5 W10)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nutmeg.v4.eval.experiment_tracker import (
    ExperimentRecord,
    current_git_branch,
    current_git_sha,
    diff_experiments,
    format_diff_card,
    list_experiments,
    track_experiment,
)


def _fake_result(*, log_loss: float = 0.9971, ece: float = 0.018, hit_rate: float = 0.508,
                  ll_xgb: float | None = None, ll_cat: float | None = None,
                  cutoff: str = "2024-08-01"):
    """Mimic the shape returned by walk_forward.run_walk_forward."""
    pooled = {
        "test_n_full": 4792,
        "test_n_gbm": 4331,
        "pinnacle":     {"log_loss": 0.9942, "brier": 0.59, "hit_rate": 0.507, "ece": 0.011},
        "pinnacle_gbm": {"log_loss": 0.9904, "brier": 0.59, "hit_rate": 0.512, "ece": 0.012},
        "gbm_dc_temp":  {"log_loss": log_loss, "brier": 0.596, "hit_rate": hit_rate, "ece": ece},
    }
    if ll_xgb is not None:
        pooled["xgb_dc"] = {"log_loss": ll_xgb, "brier": 0.596, "hit_rate": 0.51, "ece": 0.015}
    if ll_cat is not None:
        pooled["cat_dc"] = {"log_loss": ll_cat, "brier": 0.595, "hit_rate": 0.511, "ece": 0.012}
    return {
        "per_league": [{"league": "EPL", "test_n": 380}],
        "pooled": pooled,
        "cfg": {
            "train_window_days": 540,
            "validation_window_days": 90,
            "test_cutoff": cutoff,
            "test_horizon_days": 400,
            "gbm_rho": -0.10,
        },
    }


class TestGitHelpers:
    def test_sha_returns_string(self) -> None:
        sha = current_git_sha()
        # Either a real SHA (7 hex chars in our repo) or our fallback label
        assert isinstance(sha, str) and len(sha) >= 1
        assert sha != ""

    def test_branch_returns_string(self) -> None:
        b = current_git_branch()
        assert isinstance(b, str) and b != ""


class TestTrackExperiment:
    def test_creates_directory_and_files(self, tmp_path: Path) -> None:
        result = _fake_result()
        rec = track_experiment(
            result, card_text="# fake card\n", experiments_dir=tmp_path
        )
        assert rec.experiment_dir.exists()
        # Three artifacts per experiment
        assert (rec.experiment_dir / "metadata.json").exists()
        assert (rec.experiment_dir / "pooled.json").exists()
        assert (rec.experiment_dir / "card.md").exists()
        # Card content preserved
        assert (rec.experiment_dir / "card.md").read_text() == "# fake card\n"

    def test_metadata_has_required_fields(self, tmp_path: Path) -> None:
        rec = track_experiment(
            _fake_result(),
            card_text=None,
            model_type="catboost",
            extra_metadata={"note": "ablation run"},
            experiments_dir=tmp_path,
        )
        meta = json.loads((rec.experiment_dir / "metadata.json").read_text())
        assert meta["model_type"] == "catboost"
        assert meta["sha"]
        assert meta["timestamp_utc"]
        assert meta["note"] == "ablation run"
        assert meta["cfg"]["train_window_days"] == 540

    def test_skips_card_when_none(self, tmp_path: Path) -> None:
        rec = track_experiment(_fake_result(), card_text=None, experiments_dir=tmp_path)
        assert not (rec.experiment_dir / "card.md").exists()

    def test_directory_name_format(self, tmp_path: Path) -> None:
        rec = track_experiment(_fake_result(), experiments_dir=tmp_path)
        name = rec.experiment_dir.name
        # <sha>_<YYYYmmddTHHMMSSZ>
        assert "_" in name
        sha, ts = name.split("_", 1)
        assert ts.endswith("Z") and "T" in ts


class TestListExperiments:
    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        assert list_experiments(tmp_path) == []

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path) -> None:
        ghost = tmp_path / "definitely-not-here"
        assert list_experiments(ghost) == []

    def test_returns_chronological_order(self, tmp_path: Path) -> None:
        # Track three experiments
        r1 = track_experiment(_fake_result(log_loss=0.9971), experiments_dir=tmp_path)
        # Force second SHA's timestamp to be later by sleeping briefly
        import time
        time.sleep(1.1)
        r2 = track_experiment(_fake_result(log_loss=0.9965), experiments_dir=tmp_path)
        time.sleep(1.1)
        r3 = track_experiment(_fake_result(log_loss=0.9960), experiments_dir=tmp_path)
        records = list_experiments(tmp_path)
        assert len(records) == 3
        # Order by directory name (which encodes timestamp lexically)
        assert records[0].experiment_dir.name <= records[1].experiment_dir.name
        assert records[1].experiment_dir.name <= records[2].experiment_dir.name

    def test_skips_directories_missing_files(self, tmp_path: Path) -> None:
        # Make a noise directory with no JSON
        (tmp_path / "abc_garbage").mkdir()
        # And a valid one
        track_experiment(_fake_result(), experiments_dir=tmp_path)
        records = list_experiments(tmp_path)
        assert len(records) == 1

    def test_skips_corrupt_json(self, tmp_path: Path) -> None:
        # Hand-build a corrupt experiment dir
        bad = tmp_path / "abc_corrupt"
        bad.mkdir()
        (bad / "metadata.json").write_text("not-valid-json")
        (bad / "pooled.json").write_text("{}")
        track_experiment(_fake_result(), experiments_dir=tmp_path)
        records = list_experiments(tmp_path)
        assert len(records) == 1  # only the valid one


class TestDiffExperiments:
    def test_delta_signed_correctly(self, tmp_path: Path) -> None:
        a = track_experiment(_fake_result(log_loss=0.9971), experiments_dir=tmp_path)
        b = track_experiment(_fake_result(log_loss=0.9960), experiments_dir=tmp_path)
        rows = diff_experiments(a, b, metric="log_loss")
        gbm_row = next(r for r in rows if r["slot"] == "gbm_dc_temp")
        assert gbm_row["a"] == pytest.approx(0.9971)
        assert gbm_row["b"] == pytest.approx(0.9960)
        # b improved → delta is negative
        assert gbm_row["delta"] == pytest.approx(-0.0011)

    def test_slot_absent_in_one(self, tmp_path: Path) -> None:
        a = track_experiment(_fake_result(), experiments_dir=tmp_path)
        b = track_experiment(_fake_result(ll_cat=0.9950), experiments_dir=tmp_path)
        rows = diff_experiments(a, b, metric="log_loss")
        cat_row = next(r for r in rows if r["slot"] == "cat_dc")
        assert cat_row["a"] is None
        assert cat_row["b"] == pytest.approx(0.9950)
        assert cat_row["delta"] is None  # can't compute delta with missing side

    def test_supports_ece_and_hit_rate(self, tmp_path: Path) -> None:
        a = track_experiment(_fake_result(ece=0.020), experiments_dir=tmp_path)
        b = track_experiment(_fake_result(ece=0.015), experiments_dir=tmp_path)
        rows_ece = diff_experiments(a, b, metric="ece")
        gbm = next(r for r in rows_ece if r["slot"] == "gbm_dc_temp")
        assert gbm["delta"] == pytest.approx(-0.005)


class TestFormatDiffCard:
    def test_contains_expected_sections(self, tmp_path: Path) -> None:
        a = track_experiment(_fake_result(log_loss=0.9971), experiments_dir=tmp_path)
        b = track_experiment(_fake_result(log_loss=0.9960, ll_cat=0.9950),
                              experiments_dir=tmp_path)
        card = format_diff_card(a, b)
        assert "Experiment diff" in card
        assert "log_loss" in card
        assert "ece" in card
        assert "hit_rate" in card
        assert "Test pool sizes" in card
        assert "gbm_dc_temp" in card
        assert "cat_dc" in card

    def test_handles_missing_card_md(self, tmp_path: Path) -> None:
        a = track_experiment(_fake_result(), card_text=None, experiments_dir=tmp_path)
        b = track_experiment(_fake_result(), card_text=None, experiments_dir=tmp_path)
        card = format_diff_card(a, b)
        # Should still render even without card.md files
        assert "Experiment diff" in card
