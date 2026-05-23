"""End-to-end integration tests:
    1. Train a small model from CSV → save to temp dir
    2. Load artifact → predict on demo fixtures → output recommendations
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "historical_sources" / "football_data_co_uk"
DEMO_FIXTURES = REPO_ROOT / "data" / "demo" / "today_fixtures.csv"


def _run_module(mod: str, *args: str) -> subprocess.CompletedProcess:
    """Invoke a v4 CLI as a subprocess to test the actual command-line path."""
    env = {"PYTHONPATH": str(REPO_ROOT / "apps" / "api" / "src"),
           "PYTHONWARNINGS": "ignore"}
    return subprocess.run(
        [sys.executable, "-m", mod, *args],
        cwd=str(REPO_ROOT), env=env,
        capture_output=True, text=True, timeout=120,
    )


@pytest.mark.skipif(not DATA_DIR.exists(), reason="historical data not present")
class TestE2E:
    @pytest.fixture(scope="class")
    def trained_model_dir(self, tmp_path_factory):
        """Train once for the whole class.

        Explicitly pins to --model lgb because TestE2E asserts on the
        lightgbm-specific .txt artifact filenames. The TestE2ECatBoost class
        below covers the catboost path. After W12, default is `cat`, so this
        is the explicit-fallback-to-lgb test.
        """
        out_dir = tmp_path_factory.mktemp("v4_model")
        result = _run_module(
            "nutmeg.v4.cli.train",
            "--cutoff", "2024-08-01",
            "--out", str(out_dir),
            "--model", "lgb",
            "--quiet",
        )
        assert result.returncode == 0, f"train failed: {result.stderr}"
        return out_dir

    def test_artifact_files_exist(self, trained_model_dir):
        for name in ["booster_home.txt", "booster_away.txt",
                     "metadata.json", "temperature.json", "team_state.json"]:
            assert (trained_model_dir / name).exists(), f"missing: {name}"

    def test_artifact_metadata_sane(self, trained_model_dir):
        meta = json.loads((trained_model_dir / "metadata.json").read_text())
        assert "feature_columns" in meta
        assert len(meta["feature_columns"]) >= 20  # we have 24
        assert meta["metadata"]["n_train"] > 1000

    def test_team_state_has_known_teams(self, trained_model_dir):
        state = json.loads((trained_model_dir / "team_state.json").read_text())
        # EPL must exist and contain Arsenal
        assert "EPL" in state
        assert "Arsenal" in state["EPL"]
        arsenal = state["EPL"]["Arsenal"]
        # Strong premier league team — Elo should be well above initial 1500
        assert arsenal["elo"] > 1700

    @pytest.mark.skipif(not DEMO_FIXTURES.exists(), reason="demo fixtures not present")
    def test_recommend_markdown_output(self, trained_model_dir, tmp_path):
        out_file = tmp_path / "rec.md"
        result = _run_module(
            "nutmeg.v4.cli.recommend",
            "--fixtures", str(DEMO_FIXTURES),
            "--model", str(trained_model_dir),
            "--bankroll", "1000",
            "--top-n", "5",
            "--out", str(out_file),
        )
        assert result.returncode == 0, f"recommend failed: {result.stderr}"
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "今日推荐组合" in content
        assert "单场预测" in content
        # 8 fixtures should produce 8 table rows in the predictions section
        assert content.count(" vs ") >= 8

    @pytest.mark.skipif(not DEMO_FIXTURES.exists(), reason="demo fixtures not present")
    def test_recommend_json_output_schema(self, trained_model_dir, tmp_path):
        out_file = tmp_path / "rec.json"
        result = _run_module(
            "nutmeg.v4.cli.recommend",
            "--fixtures", str(DEMO_FIXTURES),
            "--model", str(trained_model_dir),
            "--bankroll", "1000",
            "--top-n", "3",
            "--format", "json",
            "--out", str(out_file),
        )
        assert result.returncode == 0, f"recommend failed: {result.stderr}"
        data = json.loads(out_file.read_text(encoding="utf-8"))
        # Top-level schema
        for key in ("generated_at_utc", "model", "bankroll", "n_fixtures",
                    "single_match_predictions", "recommendations"):
            assert key in data, f"missing top-level key: {key}"
        assert data["n_fixtures"] == 8
        # Each prediction has lambdas
        for p in data["single_match_predictions"]:
            assert p["lambda_home"] > 0
            assert p["lambda_away"] > 0
            assert p["lambda_home"] < 10
            assert p["lambda_away"] < 10
        # Recommendation schema
        for r in data["recommendations"]:
            for key in ("rank", "k_legs", "stake_units", "kelly_recommended_stake",
                        "hit_probability", "ev_per_unit", "legs"):
                assert key in r, f"recommendation missing: {key}"
            assert 2 <= r["k_legs"] <= 8
            assert r["ev_per_unit"] > 0  # only +EV survives
            assert r["hit_probability"] >= 0.05
            for leg in r["legs"]:
                assert leg["market_type"] in ("1x2", "handicap_1x2")
                for s in leg["selections"]:
                    assert s["outcome"] in ("H", "D", "A")
                    assert s["odds"] > 1.0

    @pytest.mark.skipif(not DEMO_FIXTURES.exists(), reason="demo fixtures not present")
    def test_recommendations_ranked_by_log_growth(self, trained_model_dir, tmp_path):
        out_file = tmp_path / "rec.json"
        result = _run_module(
            "nutmeg.v4.cli.recommend",
            "--fixtures", str(DEMO_FIXTURES),
            "--model", str(trained_model_dir),
            "--bankroll", "1000",
            "--top-n", "10",
            "--format", "json",
            "--out", str(out_file),
        )
        data = json.loads(out_file.read_text())
        # log_growth should be non-increasing
        growths = [r["log_growth"] for r in data["recommendations"]]
        for i in range(len(growths) - 1):
            assert growths[i] >= growths[i + 1] - 1e-9, "ranking not sorted by log_growth"


@pytest.mark.skipif(not DATA_DIR.exists(), reason="historical data not present")
class TestE2ECatBoost:
    """V5 W7: same train→recommend round-trip but with `--model cat`.

    Verifies that the CatBoost backend produces a working artifact (cbm files
    plus metadata.json with model_type='catboost') and that recommend.py
    auto-detects the type via load_artifact and predicts successfully.
    """

    @pytest.fixture(scope="class")
    def trained_model_dir_cat(self, tmp_path_factory):
        out_dir = tmp_path_factory.mktemp("v5_cat_model")
        result = _run_module(
            "nutmeg.v4.cli.train",
            "--cutoff", "2024-08-01",
            "--out", str(out_dir),
            "--model", "cat",
            "--quiet",
        )
        assert result.returncode == 0, f"cat train failed: {result.stderr}"
        return out_dir

    def test_cat_artifact_files(self, trained_model_dir_cat):
        # CatBoost binary format (.cbm) instead of lightgbm (.txt)
        for name in ["booster_home.cbm", "booster_away.cbm",
                     "metadata.json", "temperature.json", "team_state.json"]:
            assert (trained_model_dir_cat / name).exists(), f"missing: {name}"
        # And the .txt files should NOT exist (we don't dual-write)
        assert not (trained_model_dir_cat / "booster_home.txt").exists()

    def test_cat_metadata_has_model_type(self, trained_model_dir_cat):
        meta = json.loads((trained_model_dir_cat / "metadata.json").read_text())
        assert meta["model_type"] == "catboost"
        assert "league" in meta["cat_features"]
        # league should appear in the feature column list passed to CatBoost
        assert "league" in meta["feature_columns"]
        # ... and the V4 numeric features are still there
        assert "market_p_home" in meta["feature_columns"]
        assert "elo_home" in meta["feature_columns"]

    @pytest.mark.skipif(not DEMO_FIXTURES.exists(), reason="demo fixtures not present")
    def test_cat_recommend_produces_predictions(self, trained_model_dir_cat, tmp_path):
        out_file = tmp_path / "rec_cat.json"
        result = _run_module(
            "nutmeg.v4.cli.recommend",
            "--fixtures", str(DEMO_FIXTURES),
            "--model", str(trained_model_dir_cat),
            "--bankroll", "1000",
            "--top-n", "5",
            "--format", "json",
            "--out", str(out_file),
        )
        assert result.returncode == 0, f"cat recommend failed: {result.stderr}"
        data = json.loads(out_file.read_text())
        # Per-match lambdas valid and finite
        assert len(data["single_match_predictions"]) == 8
        for p in data["single_match_predictions"]:
            assert 0.05 <= p["lambda_home"] <= 8.0
            assert 0.05 <= p["lambda_away"] <= 8.0

    def test_round_trip_load_artifact(self, trained_model_dir_cat):
        """Direct API path: train CLI wrote → load_artifact reads → predict_lambdas works."""
        import sys
        sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))
        from nutmeg.v4.data.ingest import load_all_matches
        from nutmeg.v4.features import build_feature_frame
        from nutmeg.v4.model.persist import load_artifact, predict_lambdas

        art = load_artifact(trained_model_dir_cat)
        assert art.model_type == "catboost"
        assert art.cat_features == ["league"]

        # Predict on a slice of historical data
        df = load_all_matches(REPO_ROOT / "data" / "historical_sources" / "football_data_co_uk")
        feats = build_feature_frame(df.head(50))
        lambdas = predict_lambdas(art, feats)
        assert lambdas.shape == (50, 2)
        # Reasonable football lambdas
        assert (lambdas >= 0.05).all() and (lambdas <= 8.0).all()
        # Some variation across leagues (sanity: not constant)
        assert lambdas[:, 0].std() > 0.1
