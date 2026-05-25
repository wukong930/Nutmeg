"""V10 W4 Day 2 — tests for nutmeg-wc-settle and nutmeg-wc-report."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import patch

import pytest

from nutmeg.v4.cli.wc_report import main as report_main, render_markdown
from nutmeg.v4.cli.wc_settle import (
    _extract_finished_rows,
    main as settle_main,
)
from nutmeg.v4.observation.wc_log import (
    fetch_wc_predictions,
    record_wc_prediction,
    settle_wc_prediction,
)


# ---------- helpers ---------------------------------------------------------

def _make_prediction(
    fixture_id: int = 1489369,
    home: str = "Mexico",
    away: str = "South Africa",
    p_home: float = 0.58,
    p_draw: float = 0.20,
    p_away: float = 0.22,
    kickoff: str = "2026-06-11T19:00:00+00:00",
) -> dict:
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": kickoff,
        "round": "Group Stage - 1",
        "home_team": home,
        "away_team": away,
        "home_elo": 1860.0,
        "away_elo": 1524.0,
        "home_adv": 30.0,
        "has_pinnacle": False,
        "psc_home": None,
        "psc_draw": None,
        "psc_away": None,
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "p_home_elo_only": 0.84,
        "p_draw_elo_only": 0.06,
        "p_away_elo_only": 0.10,
        "source": "lightgbm_only",
    }


def _make_api_fixture(
    fixture_id: int = 1489369,
    home: str = "Mexico",
    away: str = "South Africa",
    home_goals: int | None = 2,
    away_goals: int | None = 1,
    status: str = "FT",
) -> dict:
    return {
        "fixture": {
            "id": fixture_id,
            "date": "2026-06-11T19:00:00+00:00",
            "status": {"short": status},
        },
        "teams": {
            "home": {"name": home},
            "away": {"name": away},
        },
        "goals": {"home": home_goals, "away": away_goals},
        "league": {"id": 1, "season": 2026},
    }


# ---------- wc_settle._extract_finished_rows --------------------------------

class TestExtractFinishedRows:
    def test_keeps_FT_AET_PEN(self):
        rows = _extract_finished_rows([
            _make_api_fixture(1, status="FT"),
            _make_api_fixture(2, status="AET", home_goals=3, away_goals=2),
            _make_api_fixture(3, status="PEN", home_goals=1, away_goals=1),
        ])
        assert {r["fixture_id"] for r in rows} == {1, 2, 3}

    def test_drops_non_finished(self):
        rows = _extract_finished_rows([
            _make_api_fixture(1, status="NS"),
            _make_api_fixture(2, status="LIVE"),
            _make_api_fixture(3, status="HT"),
            _make_api_fixture(4, status="PST"),
            _make_api_fixture(5, status="FT"),
        ])
        assert {r["fixture_id"] for r in rows} == {5}

    def test_drops_missing_goals(self):
        # Status says finished but goals are None → defensive skip
        rows = _extract_finished_rows([
            _make_api_fixture(1, status="FT", home_goals=None, away_goals=None),
            _make_api_fixture(2, status="FT", home_goals=2, away_goals=1),
        ])
        assert {r["fixture_id"] for r in rows} == {2}

    def test_drops_missing_fixture_id(self):
        bad = _make_api_fixture(1)
        bad["fixture"]["id"] = None
        rows = _extract_finished_rows([bad, _make_api_fixture(2)])
        assert {r["fixture_id"] for r in rows} == {2}


# ---------- wc_settle CLI end-to-end ----------------------------------------

class TestSettleCli:
    def test_settles_recorded_predictions(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        # Record 2 predictions
        record_wc_prediction(db, _make_prediction(fixture_id=1), season=2026)
        record_wc_prediction(db, _make_prediction(fixture_id=2, home="Canada"), season=2026)

        # Mock API-Football to return both as finished
        api_response = [
            _make_api_fixture(1, home_goals=2, away_goals=1),
            _make_api_fixture(2, home="Canada", home_goals=1, away_goals=1),
        ]
        with patch(
            "nutmeg.v4.data.sources.api_football.fetch_fixtures_for_league_season",
            return_value=api_response,
        ):
            rc = settle_main(["--db", str(db), "--seasons", "2026", "--quiet"])

        assert rc == 0
        # Both should now be settled
        rows = fetch_wc_predictions(db, settled_only=True)
        assert len(rows) == 2
        outcomes = {r["fixture_id"]: (r["home_goals"], r["away_goals"], r["outcome"])
                    for r in rows}
        assert outcomes[1] == (2, 1, 0)  # home win
        assert outcomes[2] == (1, 1, 1)  # draw

    def test_skips_unknown_fixtures(self, tmp_path: Path):
        """If API returns a finished fixture we never predicted, settle skips it."""
        db = tmp_path / "obs.db"
        record_wc_prediction(db, _make_prediction(fixture_id=1), season=2026)

        api_response = [
            _make_api_fixture(1, home_goals=2, away_goals=0),
            _make_api_fixture(999, home="X", away="Y", home_goals=3, away_goals=1),
        ]
        with patch(
            "nutmeg.v4.data.sources.api_football.fetch_fixtures_for_league_season",
            return_value=api_response,
        ):
            rc = settle_main(["--db", str(db), "--seasons", "2026", "--quiet"])

        assert rc == 0
        rows = fetch_wc_predictions(db, settled_only=True)
        assert len(rows) == 1  # only fixture 1
        assert rows[0]["fixture_id"] == 1

    def test_dry_run_writes_nothing(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        record_wc_prediction(db, _make_prediction(fixture_id=1), season=2026)
        with patch(
            "nutmeg.v4.data.sources.api_football.fetch_fixtures_for_league_season",
            return_value=[_make_api_fixture(1, home_goals=2, away_goals=1)],
        ):
            rc = settle_main([
                "--db", str(db), "--seasons", "2026",
                "--dry-run", "--quiet",
            ])
        assert rc == 0
        # Outcome columns still NULL
        rows = fetch_wc_predictions(db)
        assert rows[0]["outcome"] is None
        assert rows[0]["home_goals"] is None

    def test_missing_db_returns_1(self, tmp_path: Path):
        rc = settle_main(["--db", str(tmp_path / "nope.db"), "--quiet"])
        assert rc == 1

    def test_bad_seasons_arg_returns_1(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        # Need to create the DB first so the existence check passes
        record_wc_prediction(db, _make_prediction(), season=2026)
        rc = settle_main([
            "--db", str(db),
            "--seasons", "not-a-number",
            "--quiet",
        ])
        assert rc == 1


# ---------- wc_report — pure function ---------------------------------------

class TestRenderMarkdown:
    def _settled_row(
        self, fid: int, ph: float, pd: float, pa: float,
        outcome: int, kickoff: str = "2026-06-11T19:00:00+00:00",
    ) -> dict:
        # The shape matches fetch_wc_predictions output
        return {
            "fixture_id": fid,
            "recorded_at": "2026-05-25T00:00:00+00:00",
            "season": 2026,
            "match_date": kickoff[:10],
            "kickoff_utc": kickoff,
            "round": "Group Stage",
            "home_team": f"Home{fid}",
            "away_team": f"Away{fid}",
            "home_elo": 1800.0,
            "away_elo": 1700.0,
            "home_adv": 30.0,
            "p_home": ph, "p_draw": pd, "p_away": pa,
            "psc_home": None, "psc_draw": None, "psc_away": None,
            "source": "lightgbm_only",
            "blend_alpha": None,
            "home_goals": 1 if outcome == 0 else (0 if outcome == 2 else 1),
            "away_goals": 0 if outcome == 0 else (1 if outcome == 2 else 1),
            "outcome": outcome,
            "settled_at": "2026-06-11T22:00:00+00:00",
            "extras_json": None,
        }

    def test_empty_rows_returns_informational(self):
        md = render_markdown([], season=2026)
        assert "No settled matches yet" in md

    def test_only_pending_rows_shows_informational_only(self):
        """All pending → no headline / per-match table, just the
        informational short-circuit message. The summary line still
        mentions "Pending" in the row count, but no full section."""
        row = self._settled_row(1, 0.5, 0.3, 0.2, outcome=None)
        row["outcome"] = None
        row["home_goals"] = None
        row["away_goals"] = None
        md = render_markdown([row], season=2026)
        assert "No settled matches yet" in md
        # No headline / per-match section — short-circuit returned early
        assert "## Headline" not in md
        assert "## Settled matches" not in md
        # Pending matches section also doesn't appear (short-circuit)
        assert "## Pending matches" not in md

    def test_headline_metrics_present_when_settled(self):
        rows = [
            self._settled_row(1, 0.60, 0.25, 0.15, outcome=0),  # tip H, correct
            self._settled_row(2, 0.40, 0.40, 0.20, outcome=0),  # tip H or D, correct only if H
            self._settled_row(3, 0.30, 0.30, 0.40, outcome=2),  # tip A, correct
        ]
        md = render_markdown(rows, season=2026)
        assert "Log-loss" in md
        assert "Hit-rate" in md
        # 2 out of 3 correct (rows 1 and 3); row 2's tip is whichever of H/D
        # the implementation picks deterministically — accept 2/3 or 1/3
        assert "/3" in md

    def test_calibration_bucket_table_when_n_ge_10(self):
        rows = [
            self._settled_row(i, 0.5, 0.3, 0.2, outcome=i % 3)
            for i in range(15)
        ]
        md = render_markdown(rows, season=2026)
        assert "Calibration check" in md
        assert "Confidence bucket" in md

    def test_no_calibration_table_when_n_under_10(self):
        rows = [self._settled_row(i, 0.5, 0.3, 0.2, outcome=0) for i in range(5)]
        md = render_markdown(rows, season=2026)
        assert "Calibration check" not in md

    def test_settled_and_pending_sections(self):
        settled = self._settled_row(1, 0.5, 0.3, 0.2, outcome=0)
        pending = self._settled_row(2, 0.5, 0.3, 0.2, outcome=None)
        pending["outcome"] = None
        pending["home_goals"] = None
        pending["away_goals"] = None
        md = render_markdown([settled, pending], season=2026)
        assert "Settled matches" in md
        assert "Pending matches" in md


# ---------- wc_report CLI ---------------------------------------------------

class TestReportCli:
    def test_writes_report_to_file(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        out = tmp_path / "report.md"
        # Plant 1 settled prediction
        record_wc_prediction(db, _make_prediction(fixture_id=1), season=2026)
        settle_wc_prediction(db, 1, home_goals=2, away_goals=1)

        rc = report_main([
            "--db", str(db),
            "--season", "2026",
            "--out", str(out),
            "--quiet",
        ])
        assert rc == 0
        body = out.read_text()
        assert "WC 2026" in body
        assert "Hit-rate" in body
        assert "Mexico" in body

    def test_missing_db_returns_1(self, tmp_path: Path):
        rc = report_main(["--db", str(tmp_path / "nope.db"), "--quiet"])
        assert rc == 1
