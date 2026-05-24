"""Tests for V8 W3 cross-league state seeding + integration with
Elo/form/pipeline/walk_forward/cup_ablation.
"""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.cli.cup_ablation import (
    VALID_MODES,
    _build_inputs_for_mode,
    format_ablation_report,
    main as ablation_main,
)
from nutmeg.v4.features.cross_league_state import (
    seed_elo_value,
    seed_form_deque,
    seed_form_last_date,
)
from nutmeg.v4.features.elo import build_elo_features
from nutmeg.v4.features.form import build_form_features
from nutmeg.v4.features.pipeline import build_feature_frame
from nutmeg.v4.eval.walk_forward import WalkForwardConfig


# ---------- seed_elo_value -------------------------------------------

class TestSeedEloValue:
    def test_same_league_existing_value_kept(self):
        state = {"EPL": {"Arsenal": 1750.0}}
        v = seed_elo_value(state, "EPL", "Arsenal", default=1500.0)
        assert v == 1750.0
        # No mutation
        assert state == {"EPL": {"Arsenal": 1750.0}}

    def test_cross_league_seed_when_missing_in_target_pool(self):
        state = {
            "ESP_LA_LIGA": {"Real Madrid": 1820.0},
        }
        v = seed_elo_value(state, "UCL", "Real Madrid", default=1500.0)
        assert v == 1820.0
        # Seeded into target pool for subsequent reads
        assert state["UCL"]["Real Madrid"] == 1820.0

    def test_default_when_team_unknown_anywhere(self):
        state = {"EPL": {"Arsenal": 1600.0}}
        v = seed_elo_value(state, "UCL", "Brand New FC", default=1500.0)
        assert v == 1500.0
        # No mutation (no source to seed from)
        assert "Brand New FC" not in state.get("UCL", {})

    def test_default_value_in_other_pool_not_seeded(self):
        # Source pool exists but holds the default value — shouldn't seed
        state = {"EPL": {"Random": 1500.0}}
        v = seed_elo_value(state, "UCL", "Random", default=1500.0)
        assert v == 1500.0


# ---------- seed_form_deque ------------------------------------------

class TestSeedFormDeque:
    def test_copies_non_empty_history(self):
        state = {
            ("EPL", "Arsenal"): deque([1.0, 2.0, 3.0], maxlen=6),
        }
        d = seed_form_deque(state, "UCL", "Arsenal", window=6)
        assert list(d) == [1.0, 2.0, 3.0]
        # Mutated into the cup pool
        assert list(state[("UCL", "Arsenal")]) == [1.0, 2.0, 3.0]

    def test_keeps_existing_cup_pool_value(self):
        state = {
            ("EPL", "Arsenal"): deque([1.0, 2.0], maxlen=6),
            ("UCL", "Arsenal"): deque([5.0], maxlen=6),  # existing cup value
        }
        d = seed_form_deque(state, "UCL", "Arsenal", window=6)
        # Should keep the UCL deque, not overwrite from EPL
        assert list(d) == [5.0]

    def test_empty_when_no_source(self):
        state = {}
        d = seed_form_deque(state, "UCL", "Mystery", window=6)
        assert len(d) == 0
        # State now has the empty deque written into it
        assert ("UCL", "Mystery") in state


# ---------- seed_form_last_date ---------------------------------------

class TestSeedFormLastDate:
    def test_cross_league_max_date(self):
        state = {
            ("EPL", "Arsenal"): pd.Timestamp("2024-10-05"),
            ("UCL_QUALIFY", "Arsenal"): pd.Timestamp("2024-08-01"),
        }
        d = seed_form_last_date(state, "UCL", "Arsenal")
        # Returns max across other-league pools
        assert d == pd.Timestamp("2024-10-05")

    def test_returns_own_when_exists(self):
        state = {("UCL", "Arsenal"): pd.Timestamp("2024-09-15")}
        d = seed_form_last_date(state, "UCL", "Arsenal")
        assert d == pd.Timestamp("2024-09-15")

    def test_none_when_no_source(self):
        d = seed_form_last_date({}, "UCL", "Mystery")
        assert d is None


# ---------- build_elo_features cross_league_seed integration --------

class TestBuildEloWithSeed:
    def _df(self):
        # 2 EPL matches then 1 UCL match where the UCL teams come from
        # different domestic pools
        return pd.DataFrame([
            {"date": pd.Timestamp("2024-08-15"), "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "home_goals": 3, "away_goals": 1},
            {"date": pd.Timestamp("2024-08-20"), "league": "GER_BUNDESLIGA",
             "home_team": "Bayern Munich", "away_team": "Dortmund",
             "home_goals": 2, "away_goals": 2},
            {"date": pd.Timestamp("2024-09-15"), "league": "UCL",
             "home_team": "Arsenal", "away_team": "Bayern Munich",
             "home_goals": 0, "away_goals": 1},
        ])

    def test_seed_off_cup_row_uses_defaults(self):
        # Without seeding the UCL row sees both teams at initial 1500
        out = build_elo_features(self._df(), cross_league_seed=False)
        ucl = out[out["league"] == "UCL"].iloc[0]
        # Default initial is 1500.0
        assert ucl["elo_home"] == 1500.0
        assert ucl["elo_away"] == 1500.0

    def test_seed_on_cup_row_picks_up_domestic_elo(self):
        out = build_elo_features(self._df(), cross_league_seed=True)
        ucl = out[out["league"] == "UCL"].iloc[0]
        # Arsenal won 3-1 in EPL → Elo > 1500
        # Bayern drew 2-2 vs Dortmund → Elo ≈ ~1500 (modest change)
        assert ucl["elo_home"] != 1500.0, "Arsenal should have post-EPL Elo"
        # Arsenal's EPL win means Elo > 1500
        assert ucl["elo_home"] > 1500.0


# ---------- build_form_features cross_league_seed integration -------

class TestBuildFormWithSeed:
    def _df(self):
        # Several EPL matches for Arsenal, then UCL match
        return pd.DataFrame([
            {"date": pd.Timestamp("2024-08-15"), "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "home_goals": 3, "away_goals": 1,
             "home_shots": 12, "away_shots": 8,
             "home_shots_on_target": 5, "away_shots_on_target": 3},
            {"date": pd.Timestamp("2024-08-25"), "league": "EPL",
             "home_team": "Chelsea", "away_team": "Arsenal",
             "home_goals": 1, "away_goals": 2,
             "home_shots": 10, "away_shots": 11,
             "home_shots_on_target": 4, "away_shots_on_target": 6},
            {"date": pd.Timestamp("2024-09-15"), "league": "UCL",
             "home_team": "Arsenal", "away_team": "Bayern Munich",
             "home_goals": 0, "away_goals": 1,
             "home_shots": 9, "away_shots": 14,
             "home_shots_on_target": 3, "away_shots_on_target": 7},
        ])

    def test_seed_off_cup_form_empty(self):
        out = build_form_features(self._df(), cross_league_seed=False)
        ucl = out[out["league"] == "UCL"].iloc[0]
        # Arsenal's UCL row sees empty form → NaN
        assert pd.isna(ucl["form_home_goals_for_n"])

    def test_seed_on_cup_form_pulls_epl(self):
        out = build_form_features(self._df(), cross_league_seed=True)
        ucl = out[out["league"] == "UCL"].iloc[0]
        # Arsenal had 2 EPL games (scored 3 + 2 = 5 goals across them)
        assert not pd.isna(ucl["form_home_goals_for_n"])
        assert ucl["form_home_goals_for_n"] == pytest.approx(2.5)


# ---------- pipeline + walk_forward integration ----------------------

class TestPipelineCrossLeague:
    def test_build_feature_frame_accepts_flag(self):
        # Minimal smoke: build_feature_frame should accept cross_league_seed
        # without error on a tiny league-only df
        from nutmeg.v4.data.schema import MATCH_COLUMNS
        df = pd.DataFrame([
            {**{c: None for c in MATCH_COLUMNS},
             "date": pd.Timestamp("2024-08-15"),
             "league": "EPL", "season": 2024,
             "home_team": "Arsenal", "away_team": "Liverpool",
             "home_goals": 1, "away_goals": 0,
             "psc_home": 2.0, "psc_draw": 3.5, "psc_away": 4.0,
             "ps_home": 2.0, "ps_draw": 3.5, "ps_away": 4.0,
             "b365c_home": 2.0, "b365c_draw": 3.5, "b365c_away": 4.0,
             "avgc_home": 2.0, "avgc_draw": 3.5, "avgc_away": 4.0,
             "psc_over25": 2.05, "psc_under25": 1.80,
             "result_1x2": "H", "ht_home_goals": 0, "ht_away_goals": 0,
             "home_shots": 10, "away_shots": 8,
             "home_shots_on_target": 4, "away_shots_on_target": 2,
             "home_corners": 5, "away_corners": 3,
             "home_yellow": 1, "away_yellow": 2,
             "home_red": 0, "away_red": 0,
             "ahch": 0.0, "pcahh": 2.0, "pcaha": 1.85},
        ])
        out = build_feature_frame(df, clubelo_history=pd.DataFrame(),
                                   cross_league_seed=True)
        # Sanity: the EPL row has the basic form/elo cols
        assert "elo_home" in out.columns
        assert "form_home_goals_for_n" in out.columns

    def test_walk_forward_config_accepts_cross_league_seed(self):
        cfg = WalkForwardConfig(cross_league_seed=True, cup_history_df=None)
        # Just verify the dataclass accepts the new fields
        assert cfg.cross_league_seed is True
        assert cfg.cup_history_df is None


# ---------- cup_ablation CLI -----------------------------------------

class TestCupAblationModes:
    def test_valid_modes_constant(self):
        assert set(VALID_MODES) == {"baseline", "cup_data", "cup_features", "cup_full"}

    def test_baseline_returns_unchanged_df(self, tmp_path):
        league_df = pd.DataFrame([
            {"league": "EPL", "home_team": "A", "away_team": "B"},
        ])
        df, cup_hist, seed = _build_inputs_for_mode(
            league_df, "baseline",
            cup_history_dir=tmp_path, cup_odds_dir=tmp_path,
            cup_leagues=["UCL"], cup_seasons=[2024],
        )
        assert df is league_df
        assert cup_hist is None
        assert seed is False


class TestCupAblationCLIParse:
    def test_invalid_mode_returns_2(self, tmp_path):
        rc = ablation_main([
            "--modes", "nonsense",
            "--out", str(tmp_path / "out.md"),
            "--quiet",
        ])
        assert rc == 2

    def test_missing_data_returns_1(self, tmp_path):
        rc = ablation_main([
            "--data", str(tmp_path / "nope"),
            "--cutoffs", "2024-08-01",
            "--modes", "baseline",
            "--out", str(tmp_path / "out.md"),
            "--quiet",
        ])
        assert rc == 1

    def test_unparseable_cutoff_returns_2(self, tmp_path):
        rc = ablation_main([
            "--cutoffs", "twenty twenty four",
            "--modes", "baseline",
            "--out", str(tmp_path / "out.md"),
            "--quiet",
        ])
        assert rc == 2


# ---------- format_ablation_report -----------------------------------

class TestFormatAblationReport:
    def _rows(self, cup_full_delta: float = -0.0015):
        """Generate ablation rows with a configurable cup_full improvement."""
        rows = []
        for cutoff_str in ("2024-01-15", "2024-05-01", "2024-08-01", "2024-12-01"):
            cutoff = pd.Timestamp(cutoff_str)
            base_ll = 0.9960
            rows.append({"cutoff": cutoff, "mode": "baseline",
                         "result": {"n_test": 1000, "log_loss_gbm_temp": base_ll,
                                    "brier_gbm_temp": 0.59, "hit_rate_gbm": 0.51}})
            rows.append({"cutoff": cutoff, "mode": "cup_full",
                         "result": {"n_test": 1000,
                                    "log_loss_gbm_temp": base_ll + cup_full_delta,
                                    "brier_gbm_temp": 0.58, "hit_rate_gbm": 0.52}})
        return rows

    def test_card_has_ship_gate_section(self):
        card = format_ablation_report(
            self._rows(cup_full_delta=-0.0015),
            cup_leagues=["UCL", "UEL"], cup_seasons=[2021, 2022, 2023, 2024],
        )
        assert "## Ship gate" in card
        # All 4 folds improve by 0.0015 ≤ -0.001 → PASS
        assert "Gate PASSED" in card

    def test_gate_fails_when_no_improvement(self):
        card = format_ablation_report(
            self._rows(cup_full_delta=+0.0005),
            cup_leagues=["UCL"], cup_seasons=[2024],
        )
        assert "Gate NOT passed" in card
