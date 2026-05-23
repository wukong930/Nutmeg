"""Tests for V6 W8 A/B report (lineup-aware vs lineup-free settlement slicing).

Seeds an observation DB with two sessions — one with
`response.model.with_lineups = True`, one without — settles parlays on both
sides, then verifies the slicing module correctly groups them.

Also covers the format_ab_card markdown rendering and the W8
`refresh_lineups._seasons_in_window` helper.
"""
import datetime as dt
import json

import pytest

from nutmeg.v4.cli.refresh_lineups import _seasons_in_window
from nutmeg.v4.observation import open_db, record_session, settle_unsettled, upsert_outcome
from nutmeg.v4.observation.ab_report import (
    ArtifactSlice,
    format_ab_card,
    slice_lineup_aware,
    slice_lineup_free,
)


# ---------- Seeding helpers ----------

def _make_response(*, with_lineups: bool | None, sel_a: str = "H", sel_b: str = "H",
                   teams: tuple[str, str, str, str] = ("Arsenal", "Liverpool", "Inter", "Fiorentina")):
    """Two-leg parlay; metadata.model.with_lineups controls the slice marker.

    Pass with_lineups=True/False to explicitly set the flag; pass None to
    leave it absent entirely (mimics legacy V5 W12 sessions before the
    lineup-aware artifact existed).
    """
    model: dict = {
        "training_cutoff": "2025-06-01",
        "trained_at_utc": "2026-05-22T09:00:00+00:00",
        "model_type": "catboost",
    }
    if with_lineups is True:
        model["with_lineups"] = True
        model["lineup_leagues"] = ["EPL", "ESP_LA_LIGA"]
    elif with_lineups is False:
        model["with_lineups"] = False
    # if None: omit the key entirely

    ah, aw, ih, iw = teams
    return {
        "generated_at_utc": "2026-05-22T10:00:00+00:00",
        "model": model,
        "bankroll": 1000.0,
        "n_fixtures": 2,
        "n_recommendations": 1,
        "single_match_predictions": [
            {"date": "2025-08-17", "league": "EPL", "home_team": ah, "away_team": aw,
             "lambda_home": 1.5, "lambda_away": 1.0,
             "p_home_1x2": 0.50, "p_draw_1x2": 0.25, "p_away_1x2": 0.25},
            {"date": "2025-08-17", "league": "ITA_SERIE_A", "home_team": ih, "away_team": iw,
             "lambda_home": 1.4, "lambda_away": 1.1,
             "p_home_1x2": 0.45, "p_draw_1x2": 0.28, "p_away_1x2": 0.27},
        ],
        "recommendations": [
            {"rank": 1, "k_legs": 2, "is_compound": False, "stake_units": 1,
             "kelly_recommended_stake": 10.0, "expected_return": 5.0,
             "hit_probability": 0.16, "ev_per_unit": 0.50, "log_growth": 0.02,
             "legs": [
                 {"match_id": f"EPL_{ah}_vs_{aw}", "market_type": "1x2",
                  "selections": [{"outcome": sel_a, "odds": 2.5, "probability": 0.5, "edge": 0.1}]},
                 {"match_id": f"ITA_SERIE_A_{ih}_vs_{iw}", "market_type": "1x2",
                  "selections": [{"outcome": sel_b, "odds": 3.0, "probability": 0.4, "edge": 0.1}]},
             ]},
        ],
    }


def _seed_one(db, *, with_lineups, sel_a, sel_b, teams, home_goals, away_goals_first, away_goals_second):
    """Record + settle ONE 2-leg parlay session."""
    resp = _make_response(with_lineups=with_lineups, sel_a=sel_a, sel_b=sel_b, teams=teams)
    record_session(db, request={}, response=resp)
    ah, aw, ih, iw = teams
    with open_db(db) as conn:
        upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                       home_team=ah, away_team=aw,
                       home_goals=home_goals, away_goals=away_goals_first)
        upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                       home_team=ih, away_team=iw,
                       home_goals=2, away_goals=away_goals_second)
        settle_unsettled(conn)


# ---------- _seasons_in_window helper (refresh_lineups) ----------

class TestSeasonsInWindow:
    def test_mid_season_single(self):
        # Feb 2025 → 2024/25 season → start year 2024
        d = dt.date(2025, 2, 1)
        assert _seasons_in_window(d, d) == [2024]

    def test_summer_break(self):
        # Late July 2024 → previous season already over, NEW season's start year is 2024
        # (month >= 7 → year)
        d = dt.date(2024, 7, 30)
        assert _seasons_in_window(d, d) == [2024]

    def test_pre_august(self):
        # Early July 2024 → still part of 23/24 season (start year 2023)
        d = dt.date(2024, 6, 30)
        assert _seasons_in_window(d, d) == [2023]

    def test_spanning_seasons(self):
        # July → September spans the season rollover
        start = dt.date(2024, 6, 15)  # 23/24 season
        end = dt.date(2024, 8, 20)    # 24/25 season
        assert _seasons_in_window(start, end) == [2023, 2024]


# ---------- ab_report slicing ----------

class TestSlicingEmpty:
    def test_empty_db_returns_zero_both_sides(self, tmp_path):
        db = tmp_path / "obs.db"
        with open_db(db) as conn:
            free = slice_lineup_free(conn)
            aware = slice_lineup_aware(conn)
        assert isinstance(free, ArtifactSlice)
        assert isinstance(aware, ArtifactSlice)
        assert free.n_sessions == 0 and free.n_settled == 0
        assert aware.n_sessions == 0 and aware.n_settled == 0
        assert free.roi == 0.0 and aware.roi == 0.0


class TestSlicingByLineupFlag:
    def _seed_two_sided(self, db):
        # Lineup-aware session: both legs H → hit
        _seed_one(
            db, with_lineups=True, sel_a="H", sel_b="H",
            teams=("Arsenal", "Liverpool", "Inter", "Fiorentina"),
            home_goals=2, away_goals_first=0, away_goals_second=1,
        )
        # Lineup-free session 1: leg-a H, leg-b A → miss (Inter wins 2-1)
        _seed_one(
            db, with_lineups=None, sel_a="H", sel_b="A",
            teams=("Chelsea", "Spurs", "Milan", "Roma"),
            home_goals=2, away_goals_first=0, away_goals_second=1,
        )
        # Lineup-free session 2 with explicit with_lineups=False: another hit
        _seed_one(
            db, with_lineups=False, sel_a="H", sel_b="H",
            teams=("United", "City", "Juventus", "Lazio"),
            home_goals=1, away_goals_first=0, away_goals_second=1,
        )

    def test_aware_slice_only_picks_with_lineups_true(self, tmp_path):
        db = tmp_path / "obs.db"
        self._seed_two_sided(db)
        with open_db(db) as conn:
            aware = slice_lineup_aware(conn)
        assert aware.n_sessions == 1
        assert aware.n_settled == 1
        assert aware.n_hit == 1
        assert aware.n_miss == 0
        # 10 stake × 2.5 × 3.0 = 75 payout; profit 65
        assert aware.total_stake == pytest.approx(10.0)
        assert aware.total_payout == pytest.approx(75.0)
        assert aware.profit_loss == pytest.approx(65.0)
        assert aware.roi == pytest.approx(6.5)

    def test_free_slice_picks_missing_and_false(self, tmp_path):
        db = tmp_path / "obs.db"
        self._seed_two_sided(db)
        with open_db(db) as conn:
            free = slice_lineup_free(conn)
        # 2 sessions: one missing-key + one explicit-false
        assert free.n_sessions == 2
        assert free.n_settled == 2
        assert free.n_hit == 1   # the explicit-false hit
        assert free.n_miss == 1  # the missing-key miss
        assert free.total_stake == pytest.approx(20.0)
        # one hit at 75 payout, one miss at 0 payout
        assert free.total_payout == pytest.approx(75.0)
        assert free.profit_loss == pytest.approx(55.0)
        assert free.roi == pytest.approx(55.0 / 20.0)

    def test_predicted_and_actual_hit_rates(self, tmp_path):
        db = tmp_path / "obs.db"
        self._seed_two_sided(db)
        with open_db(db) as conn:
            aware = slice_lineup_aware(conn)
            free = slice_lineup_free(conn)
        # All recs have hit_probability=0.16
        assert aware.avg_hit_p_predicted == pytest.approx(0.16)
        assert free.avg_hit_p_predicted == pytest.approx(0.16)
        # aware: 1/1 hit, free: 1/2 hit
        assert aware.actual_hit_rate == pytest.approx(1.0)
        assert free.actual_hit_rate == pytest.approx(0.5)


class TestSlicingTimeWindow:
    def test_start_iso_filters_out_old_sessions(self, tmp_path):
        db = tmp_path / "obs.db"
        # Record a session, then read its actual created_at to construct
        # an iso cutoff strictly AFTER it. Since created_at is "now", a
        # future iso will exclude everything.
        _seed_one(
            db, with_lineups=True, sel_a="H", sel_b="H",
            teams=("Arsenal", "Liverpool", "Inter", "Fiorentina"),
            home_goals=2, away_goals_first=0, away_goals_second=1,
        )
        # 100 years in the future → everything excluded
        far_future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365 * 100)).isoformat(timespec="seconds")
        with open_db(db) as conn:
            aware = slice_lineup_aware(conn, start_iso=far_future)
        assert aware.n_sessions == 0
        assert aware.n_settled == 0


# ---------- format_ab_card rendering ----------

class TestFormatCard:
    def _zero_slice(self, label):
        return ArtifactSlice(
            label=label, n_sessions=0, n_settled=0, n_hit=0, n_partial=0, n_miss=0,
            total_stake=0.0, total_payout=0.0, profit_loss=0.0, roi=0.0,
            avg_hit_p_predicted=0.0, actual_hit_rate=0.0,
        )

    def test_empty_card_says_no_data(self):
        card = format_ab_card(self._zero_slice("free"), self._zero_slice("aware"))
        assert "No settled recommendations yet" in card
        assert "lineup-free" in card and "lineup-aware" in card

    def test_small_sample_warning(self):
        free = ArtifactSlice(
            "free", n_sessions=5, n_settled=10, n_hit=3, n_partial=0, n_miss=7,
            total_stake=100.0, total_payout=120.0, profit_loss=20.0, roi=0.2,
            avg_hit_p_predicted=0.3, actual_hit_rate=0.3,
        )
        aware = ArtifactSlice(
            "aware", n_sessions=5, n_settled=10, n_hit=4, n_partial=0, n_miss=6,
            total_stake=100.0, total_payout=140.0, profit_loss=40.0, roi=0.4,
            avg_hit_p_predicted=0.4, actual_hit_rate=0.4,
        )
        card = format_ab_card(free, aware, weeks=4)
        assert "Sample size still small" in card
        assert "(last 4 weeks)" in card

    def test_aware_winner_blurb(self):
        # Both sides ≥30 settled → triggers diff interpretation
        free = ArtifactSlice(
            "free", n_sessions=20, n_settled=40, n_hit=14, n_partial=0, n_miss=26,
            total_stake=400.0, total_payout=380.0, profit_loss=-20.0, roi=-0.05,
            avg_hit_p_predicted=0.35, actual_hit_rate=0.35,
        )
        aware = ArtifactSlice(
            "aware", n_sessions=20, n_settled=40, n_hit=18, n_partial=0, n_miss=22,
            total_stake=400.0, total_payout=460.0, profit_loss=60.0, roi=0.15,
            avg_hit_p_predicted=0.40, actual_hit_rate=0.45,
        )
        card = format_ab_card(free, aware)
        assert "lineup-aware leads" in card

    def test_free_winner_blurb(self):
        free = ArtifactSlice(
            "free", n_sessions=20, n_settled=40, n_hit=18, n_partial=0, n_miss=22,
            total_stake=400.0, total_payout=460.0, profit_loss=60.0, roi=0.15,
            avg_hit_p_predicted=0.40, actual_hit_rate=0.45,
        )
        aware = ArtifactSlice(
            "aware", n_sessions=20, n_settled=40, n_hit=14, n_partial=0, n_miss=26,
            total_stake=400.0, total_payout=380.0, profit_loss=-20.0, roi=-0.05,
            avg_hit_p_predicted=0.35, actual_hit_rate=0.35,
        )
        card = format_ab_card(free, aware)
        assert "lineup-free leads" in card

    def test_tie_blurb(self):
        # Both ROI within ±2pp (diff = 0.01 = 1pp)
        free = ArtifactSlice(
            "free", n_sessions=20, n_settled=40, n_hit=16, n_partial=0, n_miss=24,
            total_stake=400.0, total_payout=416.0, profit_loss=16.0, roi=0.04,
            avg_hit_p_predicted=0.4, actual_hit_rate=0.4,
        )
        aware = ArtifactSlice(
            "aware", n_sessions=20, n_settled=40, n_hit=16, n_partial=0, n_miss=24,
            total_stake=400.0, total_payout=420.0, profit_loss=20.0, roi=0.05,
            avg_hit_p_predicted=0.4, actual_hit_rate=0.4,
        )
        card = format_ab_card(free, aware)
        assert "no clear winner" in card


# ---------- refresh_lineups CLI parses ----------

class TestRefreshLineupsCLIParse:
    """We only test argparse + the seasons helper here; the actual fetch
    is end-to-end exercised by test_api_football_adapter and locally.
    """

    def test_default_args(self):
        # Direct call into _seasons_in_window covers the only pure logic
        # in main() apart from the API loop.
        today = dt.date.today()
        earliest = today - dt.timedelta(days=3)
        seasons = _seasons_in_window(earliest, today)
        assert isinstance(seasons, list)
        assert all(2018 <= s <= today.year for s in seasons)
