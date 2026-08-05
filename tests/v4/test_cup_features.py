"""Tests for V6 W11 cup + national-team competition support.

Two modules:
  1. nutmeg.v4.data.competitions — registry + helpers
  2. nutmeg.v4.features.cup_features — feature columns + cross-league
     team_state lookup

Plus a sanity check that the cup IDs landed in
API_FOOTBALL_LEAGUE_IDS so `league_id("UCL")` works.
"""
from __future__ import annotations

import pandas as pd
import pytest

from nutmeg.v4.data.competitions import (
    CUP_COMPETITIONS,
    Competition,
    api_football_id_for_cup,
    competition_type_id,
    competition_type_of,
    cup_codes,
    has_two_legged_format,
    is_club_cup_competition,
    is_cup_competition,
    is_knockout_fixture,
    is_knockout_round,
    is_national_team_competition,
)
from nutmeg.v4.data.sources.api_football import API_FOOTBALL_LEAGUE_IDS, league_id
from nutmeg.v4.features.cup_features import (
    CUP_FEATURE_COLUMNS,
    build_cup_features,
    derive_cup_features_single,
    display_zh,
    find_team_state_cross_league,
    lookup_cup_team_pair,
)


# ---------- Registry --------------------------------------------------

class TestCompetitionRegistry:
    def test_known_cup_codes(self):
        # Spot-check the major ones the V6 roadmap called out
        codes = cup_codes()
        for expected in ("UCL", "UEL", "UECL", "FAC", "WC", "EURO",
                         "COPA_AMERICA", "COPPA_ITALIA", "DFB_POKAL"):
            assert expected in codes

    def test_each_entry_is_competition(self):
        for code, comp in CUP_COMPETITIONS.items():
            assert isinstance(comp, Competition)
            assert comp.code == code
            assert comp.display_zh   # non-empty Chinese label
            assert comp.display_en
            assert comp.competition_type in (
                "league", "club_cup", "national_team_cup"
            )

    def test_is_cup_competition(self):
        assert is_cup_competition("UCL")
        assert is_cup_competition("WC")
        assert not is_cup_competition("EPL")
        assert not is_cup_competition("UNKNOWN_CODE")

    def test_national_vs_club_cup_partition(self):
        # Every cup is either club or national, never both
        for code in cup_codes():
            n = is_national_team_competition(code)
            c = is_club_cup_competition(code)
            assert (n or c) and not (n and c), f"{code} type partition broken"

    def test_competition_type_of_falls_through_to_league(self):
        assert competition_type_of("EPL") == "league"
        assert competition_type_of("UCL") == "club_cup"
        assert competition_type_of("WC") == "national_team_cup"

    def test_competition_type_id_encoding(self):
        # Stable encoding used by the GBM categorical
        assert competition_type_id("EPL") == 0
        assert competition_type_id("UCL") == 1
        assert competition_type_id("WC") == 2

    def test_has_two_legged_format(self):
        assert has_two_legged_format("UCL")
        assert has_two_legged_format("UEL")
        # FA Cup is single-leg with replays
        assert not has_two_legged_format("FAC")
        # World Cup is single venue
        assert not has_two_legged_format("WC")
        # League codes return False
        assert not has_two_legged_format("EPL")


class TestKnockoutRoundDetection:
    @pytest.mark.parametrize("label", [
        "Round of 16",
        "round of 16",
        "Round of 32",
        "Quarter-finals",
        "Semi-finals",
        "Final",
        "1st Knockout Round",
        "Play-off Round",
    ])
    def test_knockout_labels(self, label):
        assert is_knockout_round(label)

    @pytest.mark.parametrize("label", [
        "Group A - Matchday 1",
        "Regular Season - 12",
        "Matchday 5",
        None,
        "",
    ])
    def test_non_knockout_labels(self, label):
        assert not is_knockout_round(label)

    # The English-cup early rounds the token list used to miss. These 9
    # labels are the full round vocabulary API-Football returned for the
    # EFL Cup (league 48) season=2025 — all 93 fixtures, pulled 2026-08-05,
    # not invented. The FA Cup (already registered) emits the same family,
    # so it has been mis-flagging its early rounds since V6 W11.
    @pytest.mark.parametrize("label", [
        "Preliminary Round",
        "1st Round",
        "2nd Round",
        "3rd Round",
        "4th Round",
        "Quarter-finals",
        "Semi-finals",
        "Final",
        "Round of 128",
    ])
    def test_english_cup_round_labels(self, label):
        assert is_knockout_round(label)

    # Labels lifted verbatim from our own cup_history parquets (UCL/UEL/
    # EURO/WC/COPA_AMERICA), so the heuristic is pinned against real data
    # on both sides.
    @pytest.mark.parametrize("label", [
        "Preliminary round",          # UCL, lowercase variant
        "1st Qualifying Round",       # UCL/UEL two-legged qualifier
        "2nd Qualifying Round",
        "3rd Qualifying Round",
        "Knockout Round Play-offs",
        "Play-offs",
        "3rd Place Final",
        "8th Finals",                 # WC 2018's Round-of-16 spelling
        "Qualifying Play-offs Path A - Semi-Finals",
    ])
    def test_real_knockout_labels_from_parquets(self, label):
        assert is_knockout_round(label)

    @pytest.mark.parametrize("label", [
        "Group Stage - 1",
        "Group A - 6",
        "League Stage - 8",           # UCL/UEL 2024/25 Swiss phase
        # The trap: EURO qualifying is round-robin, 10 matchdays, 250 rows
        # in our parquets. "1st Qualifying Round" above is a knockout tie;
        # this is not. The trailing " - <N>" matchday suffix is what tells
        # them apart.
        "Qualifying Round - 1",
        "Qualifying Round - 10",
    ])
    def test_real_group_labels_from_parquets(self, label):
        assert not is_knockout_round(label)


class TestKnockoutFixtureDispatch:
    """Competition-first dispatch — the registry answers where it can."""

    @pytest.mark.parametrize("label", [
        "Preliminary Round",
        "1st Round",
        "2nd Round",
        "3rd Round",
        "4th Round",
        "Quarter-finals",
        "Semi-finals",
        "Final",
        "Round of 128",
    ])
    def test_pure_knockout_cup_every_round(self, label):
        # FA Cup has no group phase, so the competition decides and the
        # label never gets a vote.
        assert is_knockout_fixture("FAC", label)

    def test_pure_knockout_cup_without_label(self):
        # The point of the competition layer: still right when the round
        # label is missing entirely.
        assert is_knockout_fixture("FAC", None)
        assert is_knockout_fixture("DFB_POKAL")

    def test_group_stage_cup_defers_to_label(self):
        assert is_knockout_fixture("UCL", "Round of 16")
        assert not is_knockout_fixture("UCL", "Group Stage - 1")
        assert not is_knockout_fixture("UCL", "League Stage - 8")
        assert not is_knockout_fixture("EURO", "Qualifying Round - 3")
        # …and a group-stage cup with no label stays 0 rather than
        # guessing.
        assert not is_knockout_fixture("UCL", None)

    def test_no_knockout_phase_never_fires(self):
        # Round-robin qualifying: has_knockouts=False wins over any label.
        assert not is_knockout_fixture("WC_QUAL_UEFA", "Final")

    def test_non_cup_codes(self):
        assert not is_knockout_fixture("EPL", "Round of 16")
        assert not is_knockout_fixture("NOT_A_CODE", "Final")

    def test_registry_group_stage_flags(self):
        # Pure-knockout domestic cups — this is what makes the early
        # rounds resolve without string parsing.
        for code in ("FAC", "COPA_DEL_REY", "COPPA_ITALIA",
                     "DFB_POKAL", "COUPE_DE_FRANCE"):
            assert CUP_COMPETITIONS[code].has_group_stage is False
        # Group/league phase then knockouts.
        for code in ("UCL", "UEL", "UECL", "WC", "EURO", "COPA_AMERICA"):
            assert CUP_COMPETITIONS[code].has_group_stage is True
        # has_knockouts is not a substitute for has_group_stage: UCL has
        # both, which is exactly why the label heuristic still exists.
        assert CUP_COMPETITIONS["UCL"].has_knockouts is True
        assert CUP_COMPETITIONS["WC_QUAL_UEFA"].has_knockouts is False


# ---------- API-Football integration ----------------------------------

class TestApiFootballCupIds:
    def test_cup_ids_merged(self):
        for code in ("UCL", "UEL", "UECL", "WC", "EURO", "FAC"):
            assert code in API_FOOTBALL_LEAGUE_IDS
            assert isinstance(API_FOOTBALL_LEAGUE_IDS[code], int)

    def test_league_id_works_for_cups(self):
        # Spot-checks against well-known API-Football IDs
        assert league_id("UCL") == 2
        assert league_id("UEL") == 3
        assert league_id("WC") == 1
        assert league_id("EURO") == 4

    def test_domestic_leagues_unchanged(self):
        # V6 W1's IDs preserved
        assert league_id("EPL") == 39
        assert league_id("ESP_LA_LIGA") == 140
        assert league_id("JPN_J1") == 98

    def test_api_football_id_helper(self):
        assert api_football_id_for_cup("UCL") == 2
        assert api_football_id_for_cup("UNKNOWN") is None


# ---------- Cup features ----------------------------------------------

class TestDeriveCupFeaturesSingle:
    def test_league_match_all_zero(self):
        f = derive_cup_features_single("EPL", round_label="Regular Season - 5")
        assert f["is_cup_match"] == 0.0
        assert f["is_knockout"] == 0.0
        assert f["is_two_legged"] == 0.0
        assert f["is_national_team_match"] == 0.0
        assert f["competition_type_id"] == 0.0

    def test_ucl_group_stage(self):
        f = derive_cup_features_single("UCL", "Group A - Matchday 3")
        assert f["is_cup_match"] == 1.0
        assert f["is_knockout"] == 0.0
        assert f["is_two_legged"] == 1.0
        assert f["is_national_team_match"] == 0.0
        assert f["competition_type_id"] == 1.0

    def test_ucl_round_of_16(self):
        f = derive_cup_features_single("UCL", "Round of 16")
        assert f["is_cup_match"] == 1.0
        assert f["is_knockout"] == 1.0
        assert f["is_two_legged"] == 1.0
        assert f["competition_type_id"] == 1.0

    def test_world_cup_final(self):
        f = derive_cup_features_single("WC", "Final")
        assert f["is_cup_match"] == 1.0
        assert f["is_knockout"] == 1.0
        # WC is single-venue, NOT two-legged
        assert f["is_two_legged"] == 0.0
        assert f["is_national_team_match"] == 1.0
        assert f["competition_type_id"] == 2.0

    def test_no_round_label_still_emits_structural_flags(self):
        f = derive_cup_features_single("UEL", round_label=None)
        assert f["is_cup_match"] == 1.0
        # Without a round label we can't tell knockout/group
        assert f["is_knockout"] == 0.0
        # But two-legged is a structural property of the competition
        assert f["is_two_legged"] == 1.0

    def test_fa_cup_early_round_is_knockout(self):
        # Was 0 before the competition-first dispatch: "3rd Round" hit no
        # token in the old label list, so 84 of the EFL Cup's 93 fixtures
        # (and the FA Cup equivalents) trained as non-knockout.
        f = derive_cup_features_single("FAC", "3rd Round")
        assert f["is_cup_match"] == 1.0
        assert f["is_knockout"] == 1.0
        assert f["is_two_legged"] == 0.0
        assert f["competition_type_id"] == 1.0

    def test_fa_cup_without_round_label_is_knockout(self):
        # Pure-knockout cup — the competition answers, so a missing label
        # is not a reason to emit 0.
        f = derive_cup_features_single("FAC", round_label=None)
        assert f["is_knockout"] == 1.0


class TestBuildCupFeaturesDataFrame:
    def test_appends_all_five_columns(self):
        df = pd.DataFrame([
            {"league": "EPL",  "round": "Regular Season - 1"},
            {"league": "UCL",  "round": "Round of 16"},
            {"league": "WC",   "round": "Group A - Matchday 1"},
        ])
        out = build_cup_features(df)
        for col in CUP_FEATURE_COLUMNS:
            assert col in out.columns
        # League row is all-zero
        assert out.iloc[0]["is_cup_match"] == 0.0
        # UCL R16 row triggers cup + knockout + two-legged
        assert out.iloc[1]["is_cup_match"] == 1.0
        assert out.iloc[1]["is_knockout"] == 1.0
        assert out.iloc[1]["is_two_legged"] == 1.0
        # WC group stage: cup + national, no knockout, no two-legged
        assert out.iloc[2]["is_cup_match"] == 1.0
        assert out.iloc[2]["is_national_team_match"] == 1.0
        assert out.iloc[2]["is_knockout"] == 0.0
        assert out.iloc[2]["is_two_legged"] == 0.0

    def test_no_round_column_gracefully_handled(self):
        df = pd.DataFrame([
            {"league": "UCL"},  # No 'round' column
        ])
        out = build_cup_features(df)
        assert out.iloc[0]["is_cup_match"] == 1.0
        # No round → no knockout flag, but two-legged structural flag fires
        assert out.iloc[0]["is_knockout"] == 0.0
        assert out.iloc[0]["is_two_legged"] == 1.0

    def test_original_df_untouched(self):
        df = pd.DataFrame([{"league": "UCL", "round": "Final"}])
        original_cols = set(df.columns)
        build_cup_features(df)
        # Returned a copy; original cols only
        assert set(df.columns) == original_cols


# ---------- Cross-league team_state resolution ----------------------------

class TestCrossLeagueTeamLookup:
    def _state(self):
        # Mimic the V4 team_state shape: dict[league][team] = state
        return {
            "ESP_LA_LIGA": {"Real Madrid": "rm_state", "Getafe": "gf_state"},
            "GER_BUNDESLIGA": {"Bayern Munich": "bm_state"},
            "EPL": {"Arsenal": "ars_state"},
        }

    def test_finds_in_preferred_league_first(self):
        s = self._state()
        # Real Madrid is in La Liga; passing the preferred hint short-circuits
        assert find_team_state_cross_league(s, "Real Madrid", "ESP_LA_LIGA") == "rm_state"

    def test_falls_back_across_leagues(self):
        s = self._state()
        # No preferred → walks every league
        assert find_team_state_cross_league(s, "Bayern Munich") == "bm_state"

    def test_returns_none_for_unknown(self):
        s = self._state()
        assert find_team_state_cross_league(s, "Unknown FC") is None

    def test_lookup_cup_pair_resolves_both(self):
        s = self._state()
        # UCL fixture: Real Madrid vs Bayern Munich, neither is keyed
        # under 'UCL' but both are findable across leagues
        h, a = lookup_cup_team_pair(s, "UCL", "Real Madrid", "Bayern Munich")
        assert h == "rm_state"
        assert a == "bm_state"

    def test_lookup_league_pair_keeps_strict_keying(self):
        s = self._state()
        # League fixture: stays inside the league's dict (no cross-search)
        h, a = lookup_cup_team_pair(s, "ESP_LA_LIGA", "Real Madrid", "Getafe")
        assert h == "rm_state"
        assert a == "gf_state"

    def test_lookup_league_pair_returns_none_when_team_misnamed(self):
        s = self._state()
        # Strict league lookup does NOT cross-search even if the team
        # exists elsewhere
        h, a = lookup_cup_team_pair(s, "ESP_LA_LIGA", "Real Madrid", "Bayern Munich")
        assert h == "rm_state"
        assert a is None


# ---------- display_zh ----------------------------------------------------

class TestDisplayZh:
    def test_known_cup_has_chinese(self):
        assert "欧冠" in display_zh("UCL")
        assert "世界杯" in display_zh("WC")
        assert "足总杯" in display_zh("FAC")

    def test_unknown_falls_back_to_code(self):
        assert display_zh("EPL") == "EPL"
        assert display_zh("UNKNOWN") == "UNKNOWN"
