"""V11 Phase 0 — tests for the fatigue_features skeleton."""
from __future__ import annotations

import pandas as pd
import pytest

from nutmeg.v4.features.fatigue_features import (
    EURO_MIDWEEK_COMPETITIONS,
    OUTPUT_COLUMNS,
    TeamHistory,
    build_fatigue_features,
    euro_midweek_flag,
    long_rest_flag,
    matches_count_in_window,
    short_rest_flag,
    third_match_in_window,
)


# ---------- TeamHistory ----------------------------------------------------

class TestTeamHistory:
    def test_empty_history(self):
        h = TeamHistory()
        assert h.last_match() is None
        assert h.matches_within(pd.Timestamp("2026-05-25"), 30) == []

    def test_add_then_query(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-20"), "EPL")
        h.add(pd.Timestamp("2026-05-22"), "UCL")
        h.add(pd.Timestamp("2026-05-25"), "EPL")
        # The latest
        last = h.last_match()
        assert last == (pd.Timestamp("2026-05-25"), "EPL")
        # Matches within 4 days of 2026-05-25 — cutoff is 5-21 (inclusive)
        # 5-25 itself excluded (strict <); 5-22 included; 5-20 excluded (5 days ago)
        within = h.matches_within(pd.Timestamp("2026-05-25"), 4)
        assert len(within) == 1
        assert within[0] == (pd.Timestamp("2026-05-22"), "UCL")
        # Widen to 7 days: now 5-20, 5-22 both included
        within = h.matches_within(pd.Timestamp("2026-05-25"), 7)
        assert len(within) == 2

    def test_matches_within_excludes_current(self):
        """matches_within is strict < current_date (a match doesn't
        count as a 'prior' for itself)."""
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-25"), "EPL")
        within = h.matches_within(pd.Timestamp("2026-05-25"), 7)
        assert within == []

    def test_prune_older_than(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-04-01"), "EPL")
        h.add(pd.Timestamp("2026-04-15"), "EPL")
        h.add(pd.Timestamp("2026-05-15"), "EPL")
        h.prune_older_than(pd.Timestamp("2026-05-01"))
        # Only the May 15 entry remains
        assert h.last_match()[0] == pd.Timestamp("2026-05-15")
        within = h.matches_within(pd.Timestamp("2026-05-25"), 60)
        assert len(within) == 1


# ---------- short_rest_flag ------------------------------------------------

class TestShortRestFlag:
    def test_no_recent_match(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-10"), "EPL")
        # Current 5-25, last match was 15 days ago → not within 3 or 5
        assert short_rest_flag(h, pd.Timestamp("2026-05-25"), 3) == 0
        assert short_rest_flag(h, pd.Timestamp("2026-05-25"), 5) == 0

    def test_match_within_3_days(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-23"), "EPL")
        # 2 days ago — within 3 days
        assert short_rest_flag(h, pd.Timestamp("2026-05-25"), 3) == 1
        assert short_rest_flag(h, pd.Timestamp("2026-05-25"), 5) == 1

    def test_match_4_days_ago_not_within_3(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-21"), "EPL")
        # 4 days ago — outside 3-day window, inside 5-day
        assert short_rest_flag(h, pd.Timestamp("2026-05-25"), 3) == 0
        assert short_rest_flag(h, pd.Timestamp("2026-05-25"), 5) == 1


# ---------- long_rest_flag -------------------------------------------------

class TestLongRestFlag:
    def test_no_history_returns_0(self):
        h = TeamHistory()
        assert long_rest_flag(h, pd.Timestamp("2026-05-25"), 14) == 0

    def test_recent_match_not_long_rest(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-20"), "EPL")
        # 5 days ago — well below 14
        assert long_rest_flag(h, pd.Timestamp("2026-05-25"), 14) == 0

    def test_old_match_is_long_rest(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-01"), "EPL")
        # 24 days ago
        assert long_rest_flag(h, pd.Timestamp("2026-05-25"), 14) == 1

    def test_exactly_14_days_is_long_rest(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-11"), "EPL")
        # Exactly 14 days
        assert long_rest_flag(h, pd.Timestamp("2026-05-25"), 14) == 1


# ---------- euro_midweek_flag ----------------------------------------------

class TestEuroMidweekFlag:
    def test_no_euro_in_window(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-22"), "EPL")  # domestic, not Euro
        assert euro_midweek_flag(h, pd.Timestamp("2026-05-25"), 4) == 0

    def test_ucl_in_window(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-22"), "UCL")
        assert euro_midweek_flag(h, pd.Timestamp("2026-05-25"), 4) == 1

    def test_uel_in_window(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-23"), "UEL")
        assert euro_midweek_flag(h, pd.Timestamp("2026-05-25"), 4) == 1

    def test_uecl_in_window(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-23"), "UECL")
        assert euro_midweek_flag(h, pd.Timestamp("2026-05-25"), 4) == 1

    def test_canonical_alias(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-22"), "UEFA_CHAMPIONS_LEAGUE")
        assert euro_midweek_flag(h, pd.Timestamp("2026-05-25"), 4) == 1

    def test_euro_outside_window_doesnt_count(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-15"), "UCL")
        # 10 days ago — outside 4-day window
        assert euro_midweek_flag(h, pd.Timestamp("2026-05-25"), 4) == 0


# ---------- third_match_in_window ------------------------------------------

class TestThirdMatchInWindow:
    def test_no_prior_matches(self):
        h = TeamHistory()
        assert third_match_in_window(h, pd.Timestamp("2026-05-25"), 8) == 0

    def test_one_prior_match(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-22"), "EPL")
        # Current match is the 2nd — not 3rd yet
        assert third_match_in_window(h, pd.Timestamp("2026-05-25"), 8) == 0

    def test_two_prior_makes_this_third(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-20"), "EPL")
        h.add(pd.Timestamp("2026-05-23"), "UCL")
        # Current match is 3rd in 8 days
        assert third_match_in_window(h, pd.Timestamp("2026-05-25"), 8) == 1

    def test_old_matches_dont_count(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-05"), "EPL")
        h.add(pd.Timestamp("2026-05-10"), "EPL")
        # Both are >8 days ago; current is 1st in 8-day window
        assert third_match_in_window(h, pd.Timestamp("2026-05-25"), 8) == 0


# ---------- matches_count_in_window ----------------------------------------

class TestMatchesCount:
    def test_empty_history(self):
        h = TeamHistory()
        assert matches_count_in_window(h, pd.Timestamp("2026-05-25"), 30) == 0

    def test_counts_matches_in_range(self):
        h = TeamHistory()
        h.add(pd.Timestamp("2026-05-01"), "EPL")
        h.add(pd.Timestamp("2026-05-08"), "EPL")
        h.add(pd.Timestamp("2026-05-15"), "EPL")
        h.add(pd.Timestamp("2026-05-22"), "EPL")
        # All within 30 days
        assert matches_count_in_window(h, pd.Timestamp("2026-05-25"), 30) == 4
        # Only last 14 days
        assert matches_count_in_window(h, pd.Timestamp("2026-05-25"), 14) == 2


# ---------- build_fatigue_features (vectorized walk-in-time) ---------------

class TestBuildFatigueFeatures:
    def _make_df(self, rows: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df

    def test_output_columns_present(self):
        df = self._make_df([
            {"date": "2026-05-25", "home_team": "A", "away_team": "B", "league": "EPL"},
        ])
        out = build_fatigue_features(df)
        for col in OUTPUT_COLUMNS:
            assert col in out.columns

    def test_first_match_has_zero_features(self):
        """A team's first ever match has no history → all flags 0."""
        df = self._make_df([
            {"date": "2026-05-25", "home_team": "A", "away_team": "B", "league": "EPL"},
        ])
        out = build_fatigue_features(df)
        row = out.iloc[0]
        for col in OUTPUT_COLUMNS:
            assert row[col] == 0

    def test_back_to_back_matches_flag_short_rest(self):
        """A played EPL on May 22, then plays again on May 25 (3 days later)."""
        df = self._make_df([
            {"date": "2026-05-22", "home_team": "A", "away_team": "B", "league": "EPL"},
            {"date": "2026-05-25", "home_team": "A", "away_team": "C", "league": "EPL"},
        ])
        out = build_fatigue_features(df)
        # First match: A has no prior history
        assert out.iloc[0]["fatigue_home_short_rest_3day"] == 0
        # Second match: A played 3 days ago
        assert out.iloc[1]["fatigue_home_short_rest_3day"] == 1
        assert out.iloc[1]["fatigue_home_short_rest_5day"] == 1

    def test_ucl_then_domestic_flags_euro_midweek(self):
        """A plays UCL Tuesday, then EPL Saturday → euro_midweek_4day=1."""
        df = self._make_df([
            {"date": "2026-05-19", "home_team": "A", "away_team": "X", "league": "UCL"},   # Tue
            {"date": "2026-05-23", "home_team": "A", "away_team": "B", "league": "EPL"},   # Sat
        ])
        out = build_fatigue_features(df)
        # 2nd match: A played UCL 4 days ago
        assert out.iloc[1]["fatigue_home_euro_midweek_4day"] == 1

    def test_three_matches_in_8_days_flags_third_match(self):
        df = self._make_df([
            {"date": "2026-05-18", "home_team": "A", "away_team": "B", "league": "EPL"},
            {"date": "2026-05-21", "home_team": "A", "away_team": "C", "league": "UCL"},
            {"date": "2026-05-25", "home_team": "A", "away_team": "D", "league": "EPL"},
        ])
        out = build_fatigue_features(df)
        # First two: no prior 2-in-window
        assert out.iloc[0]["fatigue_home_third_match_8day"] == 0
        assert out.iloc[1]["fatigue_home_third_match_8day"] == 0
        # Third: A has played 2 prior matches in last 8 days → this is 3rd
        assert out.iloc[2]["fatigue_home_third_match_8day"] == 1

    def test_matches_in_30day_counter(self):
        df = self._make_df([
            {"date": "2026-04-25", "home_team": "A", "away_team": "B", "league": "EPL"},
            {"date": "2026-05-02", "home_team": "A", "away_team": "C", "league": "EPL"},
            {"date": "2026-05-15", "home_team": "A", "away_team": "D", "league": "EPL"},
            {"date": "2026-05-25", "home_team": "A", "away_team": "E", "league": "EPL"},
        ])
        out = build_fatigue_features(df)
        # 4th match: A has played 3 in last 30 days
        assert out.iloc[3]["fatigue_home_matches_in_30day"] == 3

    def test_away_team_features_computed(self):
        df = self._make_df([
            {"date": "2026-05-22", "home_team": "X", "away_team": "A", "league": "UCL"},
            {"date": "2026-05-25", "home_team": "B", "away_team": "A", "league": "EPL"},
        ])
        out = build_fatigue_features(df)
        # In the 2nd row, A is AWAY; A played UCL 3 days ago
        assert out.iloc[1]["fatigue_away_short_rest_3day"] == 1
        assert out.iloc[1]["fatigue_away_euro_midweek_4day"] == 1
        # And A is NOT home in the 2nd row, so home flags should be 0
        # (unless B coincidentally has history; B has none here)
        assert out.iloc[1]["fatigue_home_short_rest_3day"] == 0

    def test_independent_team_histories(self):
        """Teams' histories don't bleed into each other."""
        df = self._make_df([
            {"date": "2026-05-22", "home_team": "A", "away_team": "B", "league": "UCL"},
            {"date": "2026-05-25", "home_team": "A", "away_team": "C", "league": "EPL"},
            {"date": "2026-05-25", "home_team": "C", "away_team": "D", "league": "EPL"},
        ])
        out = build_fatigue_features(df)
        # Row 2: A is home, played UCL 3 days ago → euro_midweek=1
        assert out.iloc[1]["fatigue_home_euro_midweek_4day"] == 1
        # Row 3: C is home; C had a match on 5/25 (the row 2 away appearance)
        # but match dates are equal → strict < excludes → no prior history
        # Actually wait: row 2 happened "first" (depending on order), but
        # row 3 also has date 2026-05-25. The same-day match in row 2 is
        # NOT prior to row 3's date. C's only entry is from row 2 (same day).
        # Same-day matches are excluded → no flag.
        assert out.iloc[2]["fatigue_home_short_rest_3day"] == 0

    def test_competition_column_falls_back_to_league(self):
        # No 'competition' column → uses 'league' for euro detection
        df = self._make_df([
            {"date": "2026-05-22", "home_team": "A", "away_team": "B", "league": "UCL"},
            {"date": "2026-05-25", "home_team": "A", "away_team": "C", "league": "EPL"},
        ])
        out = build_fatigue_features(df)
        assert out.iloc[1]["fatigue_home_euro_midweek_4day"] == 1

    def test_explicit_competition_column(self):
        # Provides 'competition' column; that takes precedence
        df = pd.DataFrame([
            {"date": "2026-05-22", "home_team": "A", "away_team": "B",
             "league": "EPL", "competition": "UCL"},
            {"date": "2026-05-25", "home_team": "A", "away_team": "C",
             "league": "EPL", "competition": "EPL"},
        ])
        df["date"] = pd.to_datetime(df["date"])
        out = build_fatigue_features(df)
        # First match's competition was UCL → flag fires on row 2
        assert out.iloc[1]["fatigue_home_euro_midweek_4day"] == 1


# ---------- EURO_MIDWEEK_COMPETITIONS table sanity -------------------------

class TestEuroCompetitionsTable:
    def test_three_canonical_competitions_present(self):
        assert "UCL" in EURO_MIDWEEK_COMPETITIONS
        assert "UEL" in EURO_MIDWEEK_COMPETITIONS
        assert "UECL" in EURO_MIDWEEK_COMPETITIONS

    def test_canonical_aliases_present(self):
        assert "UEFA_CHAMPIONS_LEAGUE" in EURO_MIDWEEK_COMPETITIONS
        assert "UEFA_EUROPA_LEAGUE" in EURO_MIDWEEK_COMPETITIONS
        assert "UEFA_CONFERENCE_LEAGUE" in EURO_MIDWEEK_COMPETITIONS
