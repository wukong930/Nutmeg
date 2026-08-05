"""V10 W2 Day 3 — tests for the artifact-side T correction + serving wiring."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from nutmeg.v4.combo.selections import MatchInput, build_selections_from_match
from nutmeg.v4.observation.auto_calibration import (
    DriftProposal,
    LIVE_T_CORRECTION_FILENAME,
    apply_correction_to_probs,
    load_artifact_correction,
    remove_artifact_correction,
    write_artifact_correction,
)
from tests.v4.test_auto_calibration import _seed_db_with_calibration_pairs


@pytest.fixture(autouse=True)
def _pre_era_fixtures_ok(monkeypatch):
    # 体检 W1(D7):合成 fixture 跨 2026-07-15 时代界 → 界推史前(同 test_auto_calibration.py)
    import nutmeg.v4.observation.prediction_log as _pl
    monkeypatch.setattr(_pl, "CURRENT_ARTIFACT_ERA_START", "2000-01-01T00:00:00")


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "data" / "v4_model"


# ---------- Pure-function: write/load/remove roundtrip ----------------------

class TestArtifactCorrectionRoundtrip:
    def test_write_then_load_returns_payload(self, tmp_path: Path):
        prop = DriftProposal(
            proposed_T=1.12, current_T=1.0,
            log_loss_before=1.05, log_loss_after=1.02, log_loss_delta=0.03,
            p_value=0.04, n_train=60, n_holdout=14,
            train_window=("2026-05-01", "2026-05-18"),
            holdout_window=("2026-05-19", "2026-05-25"),
            should_apply=True, reason="ship gate PASSED",
        )
        path = write_artifact_correction(tmp_path, prop)
        assert path == tmp_path / LIVE_T_CORRECTION_FILENAME
        assert path.exists()

        loaded = load_artifact_correction(tmp_path)
        assert loaded is not None
        assert loaded["T"] == pytest.approx(1.12)
        assert loaded["previous_T"] == pytest.approx(1.0)
        assert loaded["n_train"] == 60
        assert loaded["n_holdout"] == 14
        assert loaded["log_loss_delta"] == pytest.approx(0.03)
        assert loaded["reason"] == "ship gate PASSED"
        assert "deployed_at_utc" in loaded
        assert loaded["train_window"] == ["2026-05-01", "2026-05-18"]

    def test_load_returns_none_when_missing(self, tmp_path: Path):
        assert load_artifact_correction(tmp_path) is None

    def test_load_returns_none_for_nonexistent_dir(self, tmp_path: Path):
        assert load_artifact_correction(tmp_path / "nope") is None

    def test_load_tolerates_corrupt_file(self, tmp_path: Path, caplog):
        (tmp_path / LIVE_T_CORRECTION_FILENAME).write_text("not-json{")
        # Should NOT raise — graceful degrade to None
        assert load_artifact_correction(tmp_path) is None

    def test_remove_returns_true_when_present(self, tmp_path: Path):
        prop = DriftProposal(proposed_T=1.05)
        write_artifact_correction(tmp_path, prop)
        assert remove_artifact_correction(tmp_path) is True
        assert not (tmp_path / LIVE_T_CORRECTION_FILENAME).exists()

    def test_remove_returns_false_when_absent(self, tmp_path: Path):
        assert remove_artifact_correction(tmp_path) is False

    def test_write_to_missing_dir_raises(self, tmp_path: Path):
        prop = DriftProposal(proposed_T=1.05)
        with pytest.raises(FileNotFoundError):
            write_artifact_correction(tmp_path / "nope", prop)

    def test_handles_nan_metrics_in_payload(self, tmp_path: Path):
        prop = DriftProposal(
            proposed_T=1.0, current_T=1.0,
            log_loss_before=float("nan"), log_loss_after=float("nan"),
            log_loss_delta=float("nan"), p_value=float("nan"),
            n_train=5, n_holdout=0,
            should_apply=False, reason="insufficient data",
        )
        path = write_artifact_correction(tmp_path, prop)
        loaded = json.loads(path.read_text())
        assert loaded["log_loss_before"] is None
        assert loaded["log_loss_after"] is None
        assert loaded["p_value"] is None


# ---------- apply_correction_to_probs ---------------------------------------

class TestApplyCorrectionToProbs:
    def test_none_correction_is_passthrough(self):
        p = np.array([0.5, 0.3, 0.2])
        np.testing.assert_array_equal(apply_correction_to_probs(p, None), p)

    def test_T_equal_1_is_passthrough(self):
        p = np.array([0.5, 0.3, 0.2])
        out = apply_correction_to_probs(p, {"T": 1.0})
        np.testing.assert_allclose(out, p, atol=1e-9)

    def test_T_greater_than_1_flattens(self):
        p = np.array([0.7, 0.2, 0.1])
        out = apply_correction_to_probs(p, {"T": 1.5})
        assert out[0] < p[0]  # biggest shrinks
        assert out[2] > p[2]  # smallest grows
        assert abs(out.sum() - 1.0) < 1e-9

    def test_T_less_than_1_sharpens(self):
        p = np.array([0.5, 0.3, 0.2])
        out = apply_correction_to_probs(p, {"T": 0.7})
        assert out[0] > p[0]
        assert out[2] < p[2]

    def test_missing_T_key_defaults_to_identity(self):
        p = np.array([0.5, 0.3, 0.2])
        out = apply_correction_to_probs(p, {})
        # No T → treated as T=1 → identity
        np.testing.assert_allclose(out, p, atol=1e-9)


# ---------- selections.build_selections_from_match (correction) -------------

def _basic_match() -> MatchInput:
    return MatchInput(
        match_id="m1",
        lambda_home=1.6,
        lambda_away=1.2,
        rho=-0.10,
        handicap_home=-1,
        odds_1x2={"H": 2.10, "D": 3.30, "A": 3.50},
        odds_handicap_1x2={"H": 2.40, "D": 3.10, "A": 2.80},
    )


class TestBuildSelectionsWithCorrection:
    def test_none_correction_matches_legacy_output(self):
        # Backward compat: correction=None must produce identical Selections
        m = _basic_match()
        a = build_selections_from_match(m)
        b = build_selections_from_match(m, correction=None)
        assert [(s.outcome, s.market_type, round(s.probability, 9))
                for s in a] == [(s.outcome, s.market_type, round(s.probability, 9))
                                for s in b]

    def test_T_equal_1_is_identity(self):
        m = _basic_match()
        a = build_selections_from_match(m)
        b = build_selections_from_match(m, correction={"T": 1.0})
        for sa, sb in zip(a, b):
            assert sa.outcome == sb.outcome
            assert abs(sa.probability - sb.probability) < 1e-9

    def test_T_greater_than_1_flattens_1x2(self):
        m = _basic_match()
        base = build_selections_from_match(m)
        flat = build_selections_from_match(m, correction={"T": 1.5})
        # Find the H selection (the home favorite — highest prob in 1x2)
        base_1x2 = {s.outcome: s for s in base if s.market_type == "1x2"}
        flat_1x2 = {s.outcome: s for s in flat if s.market_type == "1x2"}
        # T=1.5 should flatten — the largest 1x2 prob shrinks
        max_outcome = max(base_1x2, key=lambda k: base_1x2[k].probability)
        min_outcome = min(base_1x2, key=lambda k: base_1x2[k].probability)
        assert flat_1x2[max_outcome].probability < base_1x2[max_outcome].probability
        assert flat_1x2[min_outcome].probability > base_1x2[min_outcome].probability

    def test_correction_also_applied_to_handicap(self):
        m = _basic_match()
        base = build_selections_from_match(m)
        flat = build_selections_from_match(m, correction={"T": 1.5})
        # Compare handicap_1x2 H selection probs — flatten same direction
        base_hc = {s.outcome: s for s in base if s.market_type == "handicap_1x2"}
        flat_hc = {s.outcome: s for s in flat if s.market_type == "handicap_1x2"}
        max_o = max(base_hc, key=lambda k: base_hc[k].probability)
        assert flat_hc[max_o].probability < base_hc[max_o].probability


# ---------- recommend_combinations / recommend_singles correction kwarg -----

class TestComboRecommendersAcceptCorrection:
    def test_recommend_combinations_passes_correction_through(self):
        from nutmeg.v4.combo.recommend import recommend_combinations
        m = _basic_match()
        # Same match × 4 to enable parlay generation
        ms = [
            MatchInput(match_id=f"m{i}", lambda_home=1.6, lambda_away=1.2, rho=-0.10,
                       odds_1x2={"H": 2.10, "D": 3.30, "A": 3.50})
            for i in range(4)
        ]
        base = recommend_combinations(ms, bankroll=500.0, k_min=2, k_max=2,
                                       min_kelly_stake=0.0, min_hit_probability=0.0)
        flat = recommend_combinations(ms, bankroll=500.0, k_min=2, k_max=2,
                                       min_kelly_stake=0.0, min_hit_probability=0.0,
                                       correction={"T": 1.5})
        # T=1.5 flattens → home probs drop → parlays where home is the
        # favored leg should have LOWER hit_probability than baseline.
        # (Not required for every parlay; assert at least one differs.)
        if base and flat:
            base_h = max(r.parlay.hit_probability for r in base)
            flat_h = max(r.parlay.hit_probability for r in flat)
            assert flat_h != pytest.approx(base_h, abs=1e-9)

    def test_recommend_singles_passes_correction_through(self):
        from nutmeg.v4.combo.single_match import recommend_singles
        ms = [_basic_match()]
        base = recommend_singles(ms, bankroll=500.0, apply_thresholds=False)
        flat = recommend_singles(ms, bankroll=500.0, apply_thresholds=False,
                                 correction={"T": 1.5})
        # The selections under flatten should have different probs
        if base.tickets and flat.tickets:
            base_probs = sorted([t.selection.probability for t in base.tickets])
            flat_probs = sorted([t.selection.probability for t in flat.tickets])
            assert base_probs != pytest.approx(flat_probs, abs=1e-9)


# ---------- CLI --deploy-artifact behavior -----------------------------------

class TestCliDeployArtifact:
    def test_deploys_when_gate_passes(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=200, days_back_start=50, days_back_end=2)

        from nutmeg.v4.cli.auto_calibration import main
        rc = main([
            "--db", str(db),
            "--lookback-weeks", "10",
            "--holdout-weeks", "2",
            "--min-samples", "30",
            "--max-p-value", "0.5",   # loose to ensure pass on synthetic
            "--n-bootstrap", "200",
            "--apply",
            "--action", "deploy",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        # rc must be 0 when --action=deploy and gate passes (no upgrade to 2)
        assert rc == 0
        # The artifact correction file must exist
        path = artifact_dir / LIVE_T_CORRECTION_FILENAME
        assert path.exists()
        payload = json.loads(path.read_text())
        assert payload["T"] > 0
        assert payload["n_train"] > 0

    def test_no_write_when_propose_action(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=200, days_back_start=50, days_back_end=2)

        from nutmeg.v4.cli.auto_calibration import main
        rc = main([
            "--db", str(db),
            "--n-bootstrap", "200",
            "--apply",
            "--action", "propose",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        # rc can be 0 or 2 — both fine. Key assertion: no artifact written
        assert rc in (0, 2)
        assert not (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()

    def test_rollback_removes_existing_file(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=80, days_back_start=50, days_back_end=2)

        # Plant a correction file first
        prop = DriftProposal(proposed_T=1.10)
        write_artifact_correction(artifact_dir, prop)
        assert (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()

        from nutmeg.v4.cli.auto_calibration import main
        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--apply",
            "--action", "rollback",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        assert rc in (0, 2)
        # Rollback must have deleted the file regardless of gate verdict
        assert not (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()

    def test_deploy_artifact_without_apply_is_noop(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        _seed_db_with_calibration_pairs(db, n=80, days_back_start=50, days_back_end=2)

        from nutmeg.v4.cli.auto_calibration import main
        # No --apply → no journal write AND no artifact write
        rc = main([
            "--db", str(db),
            "--n-bootstrap", "100",
            "--deploy-artifact", str(artifact_dir),
            "--quiet",
        ])
        assert rc in (0, 2)
        assert not (artifact_dir / LIVE_T_CORRECTION_FILENAME).exists()


# ---------- End-to-end: serving applies correction ---------------------------

@pytest.mark.skipif(
    not ARTIFACT_PATH.exists(),
    reason="V4 model artifact not present (CI skips end-to-end serving check)",
)
class TestServingEndToEnd:
    """When live_T_correction.json is present in the artifact dir, the
    serving endpoints should return DIFFERENT 1X2 probs from the no-
    correction baseline.

    Uses tmp copy of the artifact dir so we don't pollute prod data."""

    def test_correction_changes_predictions_upcoming_probs(self, tmp_path: Path, monkeypatch):
        import shutil

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        # Clone artifact into a tmp dir we own
        tmp_art = tmp_path / "v4_model"
        shutil.copytree(ARTIFACT_PATH, tmp_art)
        # ⚠️ 2026-08-05:这里原来是裸 `os.environ[...] = ...`,不还原 ⇒ 之后同一
        # 进程里所有测试都指着这个**跑完就被删掉的 tmp 目录**。用 monkeypatch
        # (自动还原)。事故形态见 test_recommend_single_pool_api 里的注释:
        # 全套红、单跑绿,而红的是另一个文件。
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(tmp_art))

        from nutmeg.v4.api import clear_artifact_cache, v4_router
        clear_artifact_cache()
        # Also clear the per-process correction cache so the fresh dir is read
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

        # 1) Baseline (no correction file)
        r1 = client.post("/api/v4/predictions/upcoming", json=body)
        assert r1.status_code == 200, r1.text
        p1 = r1.json()["predictions"][0]
        base_ph, base_pd, base_pa = p1["p_home_1x2"], p1["p_draw_1x2"], p1["p_away_1x2"]
        assert abs(base_ph + base_pd + base_pa - 1.0) < 1e-6

        # 2) Plant a flattening correction (T=1.5)
        prop = DriftProposal(proposed_T=1.5, current_T=1.0)
        write_artifact_correction(tmp_art, prop)
        _correction_cache.clear()  # force re-read on next request

        r2 = client.post("/api/v4/predictions/upcoming", json=body)
        assert r2.status_code == 200, r2.text
        p2 = r2.json()["predictions"][0]
        corr_ph, corr_pd, corr_pa = p2["p_home_1x2"], p2["p_draw_1x2"], p2["p_away_1x2"]
        assert abs(corr_ph + corr_pd + corr_pa - 1.0) < 1e-6

        # T=1.5 flattens → max prob shrinks, min prob grows
        base = [base_ph, base_pd, base_pa]
        corr = [corr_ph, corr_pd, corr_pa]
        i_max = max(range(3), key=lambda k: base[k])
        i_min = min(range(3), key=lambda k: base[k])
        assert corr[i_max] < base[i_max], (
            f"flatten should shrink max prob; base={base} corr={corr}"
        )
        assert corr[i_min] > base[i_min], (
            f"flatten should grow min prob; base={base} corr={corr}"
        )

        # 3) Remove and verify we're back to baseline
        remove_artifact_correction(tmp_art)
        _correction_cache.clear()

        r3 = client.post("/api/v4/predictions/upcoming", json=body)
        p3 = r3.json()["predictions"][0]
        assert abs(p3["p_home_1x2"] - base_ph) < 1e-9
