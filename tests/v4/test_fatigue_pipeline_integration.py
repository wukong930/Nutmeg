"""V12 Day 2 (post-V11 audit) — fatigue features in the training pipeline.

These tests verify the wiring added today:
  1. ``build_feature_frame(..., with_fatigue=True)`` appends the 12
     fatigue columns to the output frame
  2. ``build_feature_frame(..., with_fatigue=False)`` (default) does NOT
     include them — backward-compat for existing artifacts
  3. ``feature_columns_with_fatigue(...)`` returns the right column list
     for each lineup/cup combination

Inference-path support is covered by
``TestBuildFeaturesForFixturesFatigueInference`` below (V12 post-V11
audit): ``build_features_for_fixtures`` now mirrors the training pipeline
so a fatigue-trained artifact no longer KeyErrors at serving time.
"""
from __future__ import annotations

import pandas as pd
import pytest

from nutmeg.v4.features.pipeline import (
    FATIGUE_FEATURE_COLUMNS,
    GBM_FEATURE_COLUMNS,
    LINEUP_VALIDATED_COLUMNS,
    build_feature_frame,
    feature_columns_with_cup,
    feature_columns_with_fatigue,
    feature_columns_with_lineups,
)
from nutmeg.v4.features.cup_features import CUP_FEATURE_COLUMNS
from nutmeg.v4.model.persist import V4Artifact, build_features_for_fixtures


# ============ feature_columns_with_fatigue ============================

class TestFeatureColumnsWithFatigue:
    """Combinatorial test of the new column-list helper."""

    def test_default_adds_12_fatigue_cols(self):
        cols = feature_columns_with_fatigue()
        baseline = list(GBM_FEATURE_COLUMNS)
        # 12 fatigue cols appended
        assert len(cols) == len(baseline) + 12
        # All baseline cols still present
        for col in baseline:
            assert col in cols
        # All 12 fatigue cols present
        for col in FATIGUE_FEATURE_COLUMNS:
            assert col in cols

    def test_with_lineups_stacks_correctly(self):
        cols = feature_columns_with_fatigue(include_lineups=True)
        expected = len(GBM_FEATURE_COLUMNS) + len(LINEUP_VALIDATED_COLUMNS) + 12
        assert len(cols) == expected
        # Lineup cols also present
        for col in LINEUP_VALIDATED_COLUMNS:
            assert col in cols

    def test_with_cup_stacks_correctly(self):
        cols = feature_columns_with_fatigue(include_cup=True)
        expected = len(GBM_FEATURE_COLUMNS) + len(CUP_FEATURE_COLUMNS) + 12
        assert len(cols) == expected

    def test_with_lineups_and_cup_stacks_all(self):
        cols = feature_columns_with_fatigue(include_lineups=True, include_cup=True)
        expected = (len(GBM_FEATURE_COLUMNS)
                    + len(LINEUP_VALIDATED_COLUMNS)
                    + len(CUP_FEATURE_COLUMNS)
                    + 12)
        assert len(cols) == expected

    def test_default_baseline_unchanged_without_fatigue(self):
        """Existing column-list helpers must not include fatigue when not
        asked — backward-compat for artifacts trained before V12 Day 2."""
        baseline_cols = list(GBM_FEATURE_COLUMNS)
        lineup_cols = feature_columns_with_lineups()
        cup_cols = feature_columns_with_cup()
        for fat_col in FATIGUE_FEATURE_COLUMNS:
            assert fat_col not in baseline_cols
            assert fat_col not in lineup_cols
            assert fat_col not in cup_cols


# ============ build_feature_frame integration =========================

@pytest.fixture
def tiny_match_frame() -> pd.DataFrame:
    """A 6-row, 2-team, 1-league frame with enough columns for the
    full feature pipeline (market + form + elo + xg-lite + clubelo).

    Same shape as the production training frame after `load_all_matches`.
    """
    # Include opening odds (ps_*) so build_market_dynamics_features doesn't
    # complain. In real training frame these come from the historical CSV
    # ingest; for the test we just mirror closing odds as a 1:1 proxy.
    psc_h = [1.50, 1.70, 2.10, 4.00, 1.60, 2.40]
    psc_d = [4.20, 3.80, 3.40, 3.50, 4.00, 3.40]
    psc_a = [7.50, 5.50, 3.40, 1.95, 6.00, 3.10]
    return pd.DataFrame({
        "date": pd.to_datetime([
            "2024-08-17", "2024-08-24", "2024-08-31",   # Arsenal 3 home matches
            "2024-09-07", "2024-09-14", "2024-09-21",   # ... 2-week gap then dense
        ]),
        "league": ["EPL"] * 6,
        "home_team": ["Arsenal"] * 6,
        "away_team": ["Wolves", "Brighton", "Tottenham", "Liverpool", "Leicester", "Chelsea"],
        "home_goals": [2, 1, 1, 0, 3, 2],
        "away_goals": [0, 2, 1, 0, 1, 1],
        "psc_home":   psc_h,
        "psc_draw":   psc_d,
        "psc_away":   psc_a,
        "ps_home":    psc_h,   # opening = closing in test data
        "ps_draw":    psc_d,
        "ps_away":    psc_a,
        "psc_over25": [1.85, 1.80, 1.95, 1.80, 1.85, 1.90],
        "psc_under25":[2.00, 2.05, 1.90, 2.05, 2.00, 1.95],
        "ahch":       [-1.0, -0.75, -0.25, 0.5, -1.0, -0.5],
        "home_shots":   [12, 10, 14, 8, 18, 15],
        "away_shots":   [5, 8, 13, 14, 6, 11],
        "home_shots_ot":[5, 4, 6, 2, 8, 6],
        "away_shots_ot":[1, 3, 4, 5, 2, 4],
    })


class TestBuildFeatureFrameWithFatigue:

    def test_default_does_not_include_fatigue_cols(self, tiny_match_frame):
        """Default (with_fatigue=False) preserves backward compat."""
        out = build_feature_frame(tiny_match_frame)
        for fat_col in FATIGUE_FEATURE_COLUMNS:
            assert fat_col not in out.columns, (
                f"backward-compat broken: {fat_col} appeared without flag"
            )

    def test_with_fatigue_appends_12_cols(self, tiny_match_frame):
        """with_fatigue=True adds all 12 fatigue columns."""
        out = build_feature_frame(tiny_match_frame, with_fatigue=True)
        for fat_col in FATIGUE_FEATURE_COLUMNS:
            assert fat_col in out.columns, f"missing fatigue col: {fat_col}"
        # Frame must still have same number of rows
        assert len(out) == len(tiny_match_frame)

    def test_fatigue_values_are_sensible(self, tiny_match_frame):
        """On a 6-row Arsenal-only home-fixture series, fatigue cols
        should fire as expected: matches_in_30day should grow over time."""
        out = build_feature_frame(tiny_match_frame, with_fatigue=True)
        m30 = out["fatigue_home_matches_in_30day"].tolist()
        # Row 0: no prior matches → 0
        assert m30[0] == 0
        # By row 5: Arsenal has been playing weekly → should be ≥ 4
        assert m30[5] >= 4, f"expected ≥4 matches in last 30 days by row 5, got {m30[5]}"

    def test_fatigue_short_rest_3day_inactive_on_weekly_pattern(self, tiny_match_frame):
        """Arsenal plays once per week in this fixture set; no row should
        have short_rest_3day=1 (which would require <=3 days between matches)."""
        out = build_feature_frame(tiny_match_frame, with_fatigue=True)
        assert (out["fatigue_home_short_rest_3day"] == 0).all()


# ============ Train CLI flag wiring ===================================

class TestTrainCliFatigueFlag:
    """Verify the `--with-fatigue` flag is registered in train.py argparse.
    A full training subprocess test would take ~10 minutes (real CatBoost
    fit on 30k+ rows); here we just confirm the argparse surface."""

    def test_flag_registered(self):
        import argparse
        import subprocess
        import sys
        from pathlib import Path

        REPO_ROOT = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "nutmeg.v4.cli.train", "--help"],
            cwd=REPO_ROOT,
            env={"PYTHONPATH": str(REPO_ROOT / "apps" / "api" / "src"),
                 "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0
        assert "--with-fatigue" in result.stdout, (
            f"--with-fatigue not in --help. stdout tail:\n{result.stdout[-500:]}"
        )
        # The help text must mention "fatigue" so users find it
        assert "fatigue" in result.stdout.lower()


# ====== Inference-path fatigue support (V12 post-V11 audit) ===========
# Closes the train/inference skew this file's header used to flag as
# "deferred to Day 4". build_features_for_fixtures must emit the 12
# fatigue columns when the artifact was trained with fatigue, else
# predict_lambdas (which slices feature_df[artifact.feature_columns])
# raises KeyError at serving time.

def _bare_artifact(metadata: dict) -> V4Artifact:
    """Minimal artifact for build_features_for_fixtures, which reads only
    metadata / team_state / elo_*; the boosters are never invoked here."""
    return V4Artifact(
        metadata=metadata,
        feature_columns=[],
        booster_home=None,
        booster_away=None,
        temperature_T=None,
        team_state={},
        model_type="catboost",
        cat_features=["league"],
    )


@pytest.fixture
def tiny_fixtures() -> pd.DataFrame:
    """Two upcoming fixtures with the minimum columns the inference path
    needs (no prior history carried in the frame itself)."""
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-09-21", "2024-09-21"]),
        "league": ["EPL", "EPL"],
        "home_team": ["Arsenal", "Chelsea"],
        "away_team": ["Chelsea", "Arsenal"],
        "psc_home": [1.80, 2.20],
        "psc_draw": [3.60, 3.40],
        "psc_away": [4.20, 3.10],
    })


class TestBuildFeaturesForFixturesFatigueInference:

    def test_flagged_artifact_produces_all_12_fatigue_cols(self, tiny_fixtures):
        """Regression guard: a fatigue-trained artifact (metadata flag) gets
        all 12 fatigue columns at inference — no KeyError downstream."""
        art = _bare_artifact({"with_fatigue": True})
        out = build_features_for_fixtures(
            art, tiny_fixtures, clubelo_history=pd.DataFrame()
        )
        for col in FATIGUE_FEATURE_COLUMNS:
            assert col in out.columns, f"missing fatigue col at inference: {col}"
        # The exact slice predict_lambdas performs must not raise.
        out[FATIGUE_FEATURE_COLUMNS]  # noqa: B018 — KeyError guard

    def test_default_artifact_has_no_fatigue_cols(self, tiny_fixtures):
        """Backward-compat: artifacts without the flag (e.g. the current
        production lineup-aware model) get NO fatigue columns."""
        art = _bare_artifact({"with_lineups": True})  # deliberately no with_fatigue
        out = build_features_for_fixtures(
            art, tiny_fixtures, clubelo_history=pd.DataFrame()
        )
        for col in FATIGUE_FEATURE_COLUMNS:
            assert col not in out.columns

    def test_with_fatigue_param_forces_columns(self, tiny_fixtures):
        """Explicit with_fatigue=True works even when metadata lacks it."""
        art = _bare_artifact({})
        out = build_features_for_fixtures(
            art, tiny_fixtures, clubelo_history=pd.DataFrame(), with_fatigue=True
        )
        for col in FATIGUE_FEATURE_COLUMNS:
            assert col in out.columns

    def test_no_history_means_zero_flags_but_columns_present(self, tiny_fixtures):
        """With no match_history the flags are 0 ('no signal'), but the
        columns still exist (that's what prevents the KeyError)."""
        art = _bare_artifact({"with_fatigue": True})
        out = build_features_for_fixtures(
            art, tiny_fixtures, clubelo_history=pd.DataFrame()
        )
        assert (out["fatigue_home_matches_in_30day"] == 0).all()
        assert (out["fatigue_home_third_match_8day"] == 0).all()

    def test_match_history_fires_congestion_flags(self, tiny_fixtures):
        """Recent matches supplied → congestion flags fire. Arsenal played
        twice in the 8 days before the 2024-09-21 fixture (one of them a
        UCL midweek), so it's the 3rd match in 8 days with a euro-midweek
        flag, and matches_in_30day >= 2."""
        history = pd.DataFrame({
            "date": pd.to_datetime(["2024-09-15", "2024-09-18"]),
            "league": ["EPL", "UCL"],
            "home_team": ["Arsenal", "Arsenal"],
            "away_team": ["Everton", "Bayern"],
        })
        art = _bare_artifact({"with_fatigue": True})
        out = build_features_for_fixtures(
            art, tiny_fixtures, clubelo_history=pd.DataFrame(),
            match_history=history,
        )
        # Row 0 = Arsenal at home with 2 prior matches in the window.
        assert out.loc[0, "fatigue_home_matches_in_30day"] >= 2
        assert out.loc[0, "fatigue_home_third_match_8day"] == 1
        # UCL on 2024-09-18 (3 days prior) → euro-midweek flag fires.
        assert out.loc[0, "fatigue_home_euro_midweek_4day"] == 1
        # Row 1 = Arsenal away → its congestion shows on the away side.
        assert out.loc[1, "fatigue_away_third_match_8day"] == 1
