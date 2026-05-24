"""V9 W6 — walk_forward CatBoost calibration integration.

The W6 ablation produced a negative result (per-class isotonic
catastrophically over-fits; temperature is neutral). But the
infrastructure W6 added — `cal_cat_temp` + `cal_cat_iso` calibrators
in walk_forward with their `cat_dc_temp` / `cat_dc_iso` pooled arrays
+ summaries — should remain wired correctly so future researchers
can re-run the comparison without re-writing the harness.

These tests use the existing test fixture data (football-data.co.uk
tree) and verify shapes + presence, not values, since the value-level
verdict belongs in the multi-cutoff ablation card.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.data.ingest import load_all_matches
from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "data" / "historical_sources" / "football_data_co_uk"


pytestmark = pytest.mark.skipif(
    not DATA_PATH.exists(),
    reason="football-data tree not present (skip on CI without data fixture)",
)


@pytest.fixture(scope="module")
def wf_result():
    df = load_all_matches(str(DATA_PATH))
    cfg = WalkForwardConfig(
        test_cutoff=pd.Timestamp("2024-08-01"),
        with_ensemble=True,
    )
    return run_walk_forward(df, cfg)


class TestPooledArrays:
    def test_cat_dc_temp_present_and_shape_matches(self, wf_result):
        arrays = wf_result["pooled_arrays"]
        assert "cat_dc_temp" in arrays
        # Should align with cat_dc (or be empty if cat_dc itself is empty)
        if len(arrays["cat_dc"]) > 0:
            assert arrays["cat_dc_temp"].shape == arrays["cat_dc"].shape

    def test_cat_dc_iso_present_and_shape_matches(self, wf_result):
        arrays = wf_result["pooled_arrays"]
        assert "cat_dc_iso" in arrays
        if len(arrays["cat_dc"]) > 0:
            assert arrays["cat_dc_iso"].shape == arrays["cat_dc"].shape

    def test_cat_calibrated_rows_sum_to_one(self, wf_result):
        # Per-class isotonic + renormalize → rows sum to 1
        # Temperature: softmax → rows sum to 1
        for key in ("cat_dc_temp", "cat_dc_iso"):
            arr = wf_result["pooled_arrays"][key]
            if len(arr) == 0:
                continue
            row_sums = arr.sum(axis=1)
            np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)


class TestPooledSummary:
    def test_cat_dc_temp_summary_present(self, wf_result):
        pooled = wf_result["pooled"]
        assert "cat_dc_temp" in pooled
        # Must have the same metric keys as cat_dc (log_loss, brier, etc)
        if pooled["cat_dc"] is not None:
            assert pooled["cat_dc_temp"] is not None
            assert set(pooled["cat_dc_temp"].keys()) == set(pooled["cat_dc"].keys())

    def test_cat_dc_iso_summary_present(self, wf_result):
        pooled = wf_result["pooled"]
        assert "cat_dc_iso" in pooled
        if pooled["cat_dc"] is not None:
            assert pooled["cat_dc_iso"] is not None


class TestCalibratorsReturned:
    def test_cat_T_in_calibrators(self, wf_result):
        cals = wf_result["calibrators"]
        assert "cat_T" in cals
        T = cals["cat_T"]
        # Per the ablation results, T should be a finite positive float
        # within the bounds (0.3, 5.0) used by fit_temperature_1x2
        assert T is not None
        assert 0.3 < float(T) < 5.0

    def test_cat_iso_n_train_in_calibrators(self, wf_result):
        cals = wf_result["calibrators"]
        assert "cat_iso_n_train" in cals
        n = cals["cat_iso_n_train"]
        # Should be the number of val rows used to fit isotonic
        assert n is not None
        assert n >= 100   # threshold in walk_forward


class TestPerLeagueRows:
    def test_each_league_row_has_cat_dc_temp_field(self, wf_result):
        for row in wf_result["per_league"]:
            # cat_dc_temp must be present (None is OK for leagues w/o ensemble rows)
            assert "cat_dc_temp" in row
            assert "cat_dc_iso" in row


# ---------- ablation CLI smoke test ----------------------------------

class TestAblationCLI:
    def test_format_card_contains_verdict(self):
        """The ablation card writer should produce a verdict section
        regardless of which branch triggers. Uses synthetic rows so
        we don't re-run walk_forward inside this test."""
        from nutmeg.v4.cli.cat_calibration_ablation import _format_card

        # All-positive iso deltas → no-fix verdict
        rows = [
            {
                "cutoff": "2024-08-01", "n": 4331,
                "pinnacle_ll": 0.99, "cat_raw_ll": 0.995,
                "cat_temp_ll": 0.995, "cat_iso_ll": 1.08,
                "pinnacle_target_ll": 0.047, "cat_raw_target_ll": 0.055,
                "cat_temp_target_ll": 0.059, "cat_iso_target_ll": 0.068,
                "pinnacle_target_n": 540, "cat_raw_target_n": 620,
                "cat_temp_target_n": 620, "cat_iso_target_n": 620,
                "cat_T": 0.85,
            },
        ]
        card = _format_card(rows, ["2024-08-01"])
        assert "Verdict" in card
        assert "no-fix" in card or "ship-iso" in card or "marginal" in card

    def test_ship_iso_verdict_when_all_cutoffs_improve(self):
        from nutmeg.v4.cli.cat_calibration_ablation import _format_card
        rows = []
        for cutoff in ("2022-08-01", "2023-08-01", "2024-08-01"):
            rows.append({
                "cutoff": cutoff, "n": 4000,
                "pinnacle_ll": 0.99, "cat_raw_ll": 0.995,
                "cat_temp_ll": 0.993,
                "cat_iso_ll": 0.985,   # ← consistently better than raw
                "pinnacle_target_ll": 0.047, "cat_raw_target_ll": 0.055,
                "cat_temp_target_ll": 0.053, "cat_iso_target_ll": 0.045,
                "pinnacle_target_n": 540, "cat_raw_target_n": 620,
                "cat_temp_target_n": 620, "cat_iso_target_n": 620,
                "cat_T": 0.95,
            })
        card = _format_card(rows, ["2022-08-01", "2023-08-01", "2024-08-01"])
        assert "ship-iso" in card
        assert "0.0005" in card or "wire isotonic" in card

    def test_no_fix_verdict_matches_actual_w6_pattern(self):
        from nutmeg.v4.cli.cat_calibration_ablation import _format_card
        # The actual W6 numbers — should produce "no-fix"
        rows = [
            {"cutoff": "2022-08-01", "n": 4884,
             "pinnacle_ll": 0.994, "cat_raw_ll": 0.9984,
             "cat_temp_ll": 0.9977, "cat_iso_ll": 1.0454,
             "pinnacle_target_ll": 0.0438, "cat_raw_target_ll": 0.0506,
             "cat_temp_target_ll": 0.0516, "cat_iso_target_ll": 0.0396,
             "pinnacle_target_n": 542, "cat_raw_target_n": 619,
             "cat_temp_target_n": 619, "cat_iso_target_n": 619,
             "cat_T": 0.9563},
            {"cutoff": "2023-08-01", "n": 4767,
             "pinnacle_ll": 0.9865, "cat_raw_ll": 0.9898,
             "cat_temp_ll": 0.9894, "cat_iso_ll": 1.0900,
             "pinnacle_target_ll": 0.0448, "cat_raw_target_ll": 0.0488,
             "cat_temp_target_ll": 0.0533, "cat_iso_target_ll": 0.0773,
             "pinnacle_target_n": 530, "cat_raw_target_n": 600,
             "cat_temp_target_n": 600, "cat_iso_target_n": 600,
             "cat_T": 0.8655},
            {"cutoff": "2024-08-01", "n": 4331,
             "pinnacle_ll": 0.9904, "cat_raw_ll": 0.9960,
             "cat_temp_ll": 0.9965, "cat_iso_ll": 1.0855,
             "pinnacle_target_ll": 0.0473, "cat_raw_target_ll": 0.0556,
             "cat_temp_target_ll": 0.0590, "cat_iso_target_ll": 0.0687,
             "pinnacle_target_n": 542, "cat_raw_target_n": 619,
             "cat_temp_target_n": 619, "cat_iso_target_n": 619,
             "cat_T": 0.8521},
        ]
        card = _format_card(rows, ["2022-08-01", "2023-08-01", "2024-08-01"])
        assert "no-fix" in card
        assert "Close ECE-vs-log-loss" in card or "structural" in card.lower()
