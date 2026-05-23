"""Tests for V7 W7 — cup features wired into the training pipeline.

Layers:
  1. `feature_columns_with_cup(include_lineups=False/True)` — column list
     composition
  2. `_merge_cup_round_labels` — join cup-history into a training frame
  3. `build_feature_frame(cup_history_df=...)` — end-to-end feature build
     adds the 5 cup cols; default flow unchanged
  4. `nutmeg-train --with-cup-features` — argparse acceptance + the
     flag-combination logic
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from nutmeg.v4.cli.train import main as train_main
from nutmeg.v4.features.cup_features import CUP_FEATURE_COLUMNS
from nutmeg.v4.features.pipeline import (
    GBM_FEATURE_COLUMNS,
    LINEUP_VALIDATED_COLUMNS,
    _merge_cup_round_labels,
    build_feature_frame,
    feature_columns_with_cup,
    feature_columns_with_lineups,
)


# ---------- feature_columns_with_cup -----------------------------------

class TestFeatureColumnsWithCup:
    def test_default_excludes_lineup_cols(self):
        cols = feature_columns_with_cup()
        # Cup cols included
        for c in CUP_FEATURE_COLUMNS:
            assert c in cols
        # Lineup validated cols NOT included by default (keeps cup wiring
        # independent of lineup wiring)
        for c in LINEUP_VALIDATED_COLUMNS:
            assert c not in cols

    def test_include_lineups_stacks_both(self):
        cols = feature_columns_with_cup(include_lineups=True)
        for c in CUP_FEATURE_COLUMNS:
            assert c in cols
        for c in LINEUP_VALIDATED_COLUMNS:
            assert c in cols

    def test_base_cols_always_present(self):
        # GBM_FEATURE_COLUMNS is the V5 baseline; must survive in both modes
        cols_a = feature_columns_with_cup(include_lineups=False)
        cols_b = feature_columns_with_cup(include_lineups=True)
        for c in GBM_FEATURE_COLUMNS:
            assert c in cols_a
            assert c in cols_b

    def test_default_count_arithmetic(self):
        assert len(feature_columns_with_cup(include_lineups=False)) == \
            len(GBM_FEATURE_COLUMNS) + len(CUP_FEATURE_COLUMNS)
        assert len(feature_columns_with_cup(include_lineups=True)) == \
            len(GBM_FEATURE_COLUMNS) + len(LINEUP_VALIDATED_COLUMNS) + len(CUP_FEATURE_COLUMNS)


# ---------- _merge_cup_round_labels ------------------------------------

class TestMergeCupRoundLabels:
    def _league_df(self):
        # A minimal training frame: 3 rows, 2 leagues
        return pd.DataFrame([
            {"date": pd.Timestamp("2024-11-05"), "league": "UCL",
             "home_team": "Real Madrid", "away_team": "Bayern Munich"},
            {"date": pd.Timestamp("2024-11-05"), "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool"},
            {"date": pd.Timestamp("2024-11-06"), "league": "UCL",
             "home_team": "Inter", "away_team": "Arsenal"},
        ])

    def _cup_history_df(self):
        # Only the UCL Real Madrid match — Inter-Arsenal and EPL rows
        # have no cup-history counterpart
        return pd.DataFrame([
            {"date": pd.Timestamp("2024-11-05"), "league": "UCL",
             "home_team": "Real Madrid", "away_team": "Bayern Munich",
             "round_label": "Round of 16"},
        ])

    def test_left_join_preserves_all_rows(self):
        out = _merge_cup_round_labels(self._league_df(), self._cup_history_df())
        assert len(out) == 3
        assert "round_label" in out.columns

    def test_matched_row_picks_up_round(self):
        out = _merge_cup_round_labels(self._league_df(), self._cup_history_df())
        rm_row = out[out["home_team"] == "Real Madrid"].iloc[0]
        assert rm_row["round_label"] == "Round of 16"

    def test_unmatched_row_has_none_round(self):
        out = _merge_cup_round_labels(self._league_df(), self._cup_history_df())
        epl_row = out[out["home_team"] == "Arsenal"].iloc[0]
        # EPL Arsenal-Liverpool isn't in cup-history → round_label is NaN
        assert pd.isna(epl_row["round_label"])

    def test_empty_cup_history_still_emits_round_col(self):
        out = _merge_cup_round_labels(self._league_df(), pd.DataFrame())
        assert "round_label" in out.columns
        assert out["round_label"].isna().all()

    def test_none_cup_history_still_emits_round_col(self):
        out = _merge_cup_round_labels(self._league_df(), None)
        assert "round_label" in out.columns
        assert out["round_label"].isna().all()

    def test_iso_date_string_vs_datetime_match(self):
        # cup-history may have date as datetime (after load_multi_season)
        # OR as string. Both should join correctly.
        league = self._league_df()
        cup = pd.DataFrame([
            {"date": "2024-11-05", "league": "UCL",
             "home_team": "Real Madrid", "away_team": "Bayern Munich",
             "round_label": "Round of 16"},
        ])
        out = _merge_cup_round_labels(league, cup)
        rm_row = out[out["home_team"] == "Real Madrid"].iloc[0]
        assert rm_row["round_label"] == "Round of 16"


# ---------- build_feature_frame integration ----------------------------

class TestBuildFeatureFrameCupHistory:
    def _seed_training_df(self):
        # Minimal df with the canonical MATCH_COLUMNS schema for
        # build_market_features etc. 2 EPL + 1 UCL fixture; pad optional
        # market columns with sensible defaults so downstream builders
        # don't choke.
        rows = []
        for date, season, league, home, away, ph, pd_, pa in [
            ("2024-10-05", 2024, "EPL", "Arsenal", "Liverpool", 2.10, 3.40, 3.50),
            ("2024-10-12", 2024, "EPL", "Chelsea", "Spurs", 2.30, 3.30, 3.10),
            ("2024-11-05", 2024, "UCL", "Real Madrid", "Bayern Munich", 1.90, 3.80, 4.00),
        ]:
            rows.append({
                "date": pd.Timestamp(date), "season": season,
                "league": league,
                "home_team": home, "away_team": away,
                "home_goals": 2, "away_goals": 1, "result_1x2": "H",
                "ht_home_goals": 1, "ht_away_goals": 0,
                "home_shots": 12, "away_shots": 8,
                "home_shots_on_target": 5, "away_shots_on_target": 3,
                "home_corners": 6, "away_corners": 4,
                "home_yellow": 1, "away_yellow": 2,
                "home_red": 0, "away_red": 0,
                # Closing odds (3 books worth — fall-back coverage)
                "psc_home": ph, "psc_draw": pd_, "psc_away": pa,
                "ps_home": ph, "ps_draw": pd_, "ps_away": pa,
                "b365c_home": ph, "b365c_draw": pd_, "b365c_away": pa,
                "avgc_home": ph, "avgc_draw": pd_, "avgc_away": pa,
                "psc_over25": 1.95, "psc_under25": 1.90,
                "ahch": 0.0, "pcahh": 2.0, "pcaha": 1.85,
            })
        return pd.DataFrame(rows)

    def _cup_history(self):
        return pd.DataFrame([
            {"date": pd.Timestamp("2024-11-05"), "league": "UCL",
             "home_team": "Real Madrid", "away_team": "Bayern Munich",
             "round_label": "Round of 16"},
        ])

    def test_without_cup_history_no_cup_cols(self, tmp_path):
        df = self._seed_training_df()
        out = build_feature_frame(df, clubelo_history=pd.DataFrame())
        # By default no cup cols on the frame
        for c in CUP_FEATURE_COLUMNS:
            assert c not in out.columns

    def test_with_cup_history_adds_all_5_cols(self, tmp_path):
        df = self._seed_training_df()
        out = build_feature_frame(
            df, clubelo_history=pd.DataFrame(),
            cup_history_df=self._cup_history(),
        )
        for c in CUP_FEATURE_COLUMNS:
            assert c in out.columns

    def test_league_rows_get_zero_for_cup_cols(self, tmp_path):
        df = self._seed_training_df()
        out = build_feature_frame(
            df, clubelo_history=pd.DataFrame(),
            cup_history_df=self._cup_history(),
        )
        epl_rows = out[out["league"] == "EPL"]
        for c in CUP_FEATURE_COLUMNS:
            assert (epl_rows[c] == 0.0).all(), f"{c} should be 0 on EPL rows"

    def test_cup_row_picks_up_knockout_flag(self, tmp_path):
        df = self._seed_training_df()
        out = build_feature_frame(
            df, clubelo_history=pd.DataFrame(),
            cup_history_df=self._cup_history(),
        )
        ucl_row = out[out["league"] == "UCL"].iloc[0]
        assert ucl_row["is_cup_match"] == 1.0
        assert ucl_row["is_knockout"] == 1.0   # "Round of 16" → knockout
        assert ucl_row["is_two_legged"] == 1.0  # UCL R16 is two-legged
        assert ucl_row["is_national_team_match"] == 0.0
        assert ucl_row["competition_type_id"] == 1.0  # club_cup

    def test_empty_cup_history_zero_cup_cols_everywhere(self, tmp_path):
        df = self._seed_training_df()
        out = build_feature_frame(
            df, clubelo_history=pd.DataFrame(),
            cup_history_df=pd.DataFrame(),
        )
        for c in CUP_FEATURE_COLUMNS:
            assert c in out.columns
            # UCL row still says is_cup_match=1 because the LEAGUE itself
            # is cup-classified — round_label just stays None so knockout
            # flag is 0
            if c == "is_cup_match":
                ucl_count = (out[out["league"] == "UCL"][c] == 1.0).sum()
                assert ucl_count == 1
            if c == "is_knockout":
                # No round_label → can't tell knockout → 0 for all
                assert (out[c] == 0.0).all()


# ---------- nutmeg-train --with-cup-features --------------------------

class TestTrainArgParsing:
    """We only test argparse acceptance — the actual training is
    exhaustively covered by test_e2e."""

    def test_with_cup_features_parses(self, capsys):
        # Invalid --data path will trip the load_all_matches call. We
        # just want to verify argparse accepts the flag.
        rc = train_main([
            "--data", "/nonexistent/path",
            "--with-cup-features",
            "--cup-leagues", "UCL,UEL",
            "--cup-seasons", "2022,2023,2024",
            "--quiet",
        ])
        # Either non-zero return from load failure, OR success — but
        # crucially: NOT a SystemExit from argparse rejecting the flag
        assert rc in (0, 1, 2)

    def test_both_flags_parse_together(self):
        rc = train_main([
            "--data", "/nonexistent/path",
            "--with-lineups",
            "--with-cup-features",
            "--quiet",
        ])
        # Same: argparse accepts both flags together; failure comes from
        # downstream data missing
        assert rc in (0, 1, 2)
