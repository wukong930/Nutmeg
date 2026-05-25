"""V10 W4 Day 1 — tests for the WC predictions audit log + CLI --record-to."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from nutmeg.v4.observation.wc_log import (
    WC_PREDICTIONS_SCHEMA,
    ensure_wc_predictions_table,
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
    source: str = "lightgbm_only",
    kickoff: str = "2026-06-11T19:00:00+00:00",
    psc: tuple[float, float, float] | None = None,
) -> dict:
    base = {
        "fixture_id": fixture_id,
        "kickoff_utc": kickoff,
        "round": "Group Stage - 1",
        "home_team": home,
        "away_team": away,
        "home_elo": 1860.0,
        "away_elo": 1524.0,
        "home_adv": 30.0,
        "has_pinnacle": psc is not None,
        "psc_home": psc[0] if psc else None,
        "psc_draw": psc[1] if psc else None,
        "psc_away": psc[2] if psc else None,
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "p_home_elo_only": 0.84,
        "p_draw_elo_only": 0.06,
        "p_away_elo_only": 0.10,
        "source": source,
    }
    if source == "blended":
        base["blend_alpha"] = 0.4
    return base


# ---------- ensure + record + fetch -----------------------------------------

class TestWcLogTable:
    def test_ensure_creates_table(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        ensure_wc_predictions_table(db)
        # Idempotent — second call is a no-op
        ensure_wc_predictions_table(db)
        # Confirm via fetch (empty → empty list, no error)
        assert fetch_wc_predictions(db) == []

    def test_record_then_fetch_roundtrip(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        pred = _make_prediction()
        # Add an unknown field to verify extras_json captures it
        pred["future_field_2027"] = "some-value"
        fid = record_wc_prediction(db, pred, season=2026)
        assert fid == 1489369

        rows = fetch_wc_predictions(db)
        assert len(rows) == 1
        row = rows[0]
        assert row["fixture_id"] == 1489369
        assert row["season"] == 2026
        assert row["match_date"] == "2026-06-11"
        assert row["home_team"] == "Mexico"
        assert row["away_team"] == "South Africa"
        assert row["p_home"] == pytest.approx(0.58)
        assert row["source"] == "lightgbm_only"
        assert row["outcome"] is None  # unsettled
        assert row["home_goals"] is None
        # extras_json captures unknown fields (forward-compat)
        extras = json.loads(row["extras_json"])
        assert extras["future_field_2027"] == "some-value"

    def test_no_extras_yields_null_extras_json(self, tmp_path: Path):
        """When prediction has only known fields, extras_json is NULL."""
        db = tmp_path / "obs.db"
        record_wc_prediction(db, _make_prediction(), season=2026)
        rows = fetch_wc_predictions(db)
        assert rows[0]["extras_json"] is None


# ---------- upsert (re-record overwrites) -----------------------------------

class TestUpsertSemantics:
    def test_re_record_overwrites_previous_row(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        # Initial: lightgbm_only with no Pinnacle odds
        pred1 = _make_prediction(p_home=0.58, source="lightgbm_only", psc=None)
        record_wc_prediction(db, pred1, season=2026)

        # Re-run: odds opened, blended with different probs
        pred2 = _make_prediction(
            p_home=0.62, p_draw=0.18, p_away=0.20,
            source="blended", psc=(1.75, 4.20, 4.80),
        )
        record_wc_prediction(db, pred2, season=2026)

        rows = fetch_wc_predictions(db)
        # Still only 1 row (PK upsert)
        assert len(rows) == 1
        row = rows[0]
        # Values reflect the SECOND call
        assert row["p_home"] == pytest.approx(0.62)
        assert row["source"] == "blended"
        assert row["psc_home"] == pytest.approx(1.75)
        assert row["blend_alpha"] == pytest.approx(0.4)

    def test_different_fixtures_produce_separate_rows(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        record_wc_prediction(db, _make_prediction(fixture_id=1), season=2026)
        record_wc_prediction(db, _make_prediction(fixture_id=2, home="Canada"), season=2026)
        rows = fetch_wc_predictions(db)
        assert len(rows) == 2
        assert {r["fixture_id"] for r in rows} == {1, 2}


# ---------- settle ----------------------------------------------------------

class TestSettleSemantics:
    def test_settle_fills_outcome_columns(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        record_wc_prediction(db, _make_prediction(fixture_id=1489369), season=2026)

        updated = settle_wc_prediction(
            db, fixture_id=1489369, home_goals=2, away_goals=1,
        )
        assert updated is True
        rows = fetch_wc_predictions(db, settled_only=True)
        assert len(rows) == 1
        row = rows[0]
        assert row["home_goals"] == 2
        assert row["away_goals"] == 1
        assert row["outcome"] == 0  # home win
        assert row["settled_at"] is not None

    def test_settle_outcome_calculation(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        # 3 separate fixtures, one each outcome
        for fid, hg, ag, expected in [(1, 3, 0, 0), (2, 1, 1, 1), (3, 0, 2, 2)]:
            record_wc_prediction(
                db, _make_prediction(fixture_id=fid), season=2026,
            )
            settle_wc_prediction(db, fid, home_goals=hg, away_goals=ag)
        rows = fetch_wc_predictions(db, settled_only=True)
        outcomes = {r["fixture_id"]: r["outcome"] for r in rows}
        assert outcomes == {1: 0, 2: 1, 3: 2}

    def test_settle_returns_false_when_no_row(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        ensure_wc_predictions_table(db)
        # Settle a fixture we never predicted
        assert settle_wc_prediction(db, 999, home_goals=1, away_goals=0) is False

    def test_resettle_overwrites_outcome(self, tmp_path: Path):
        """Useful when initial settle had bad data (e.g. wrong score)."""
        db = tmp_path / "obs.db"
        record_wc_prediction(db, _make_prediction(fixture_id=1), season=2026)
        settle_wc_prediction(db, 1, home_goals=2, away_goals=1)
        settle_wc_prediction(db, 1, home_goals=3, away_goals=1)
        rows = fetch_wc_predictions(db, settled_only=True)
        assert rows[0]["home_goals"] == 3


# ---------- fetch filters ---------------------------------------------------

class TestFetchFilters:
    def test_filter_by_season(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        record_wc_prediction(db, _make_prediction(fixture_id=1), season=2022)
        record_wc_prediction(db, _make_prediction(fixture_id=2), season=2026)
        assert {r["fixture_id"] for r in fetch_wc_predictions(db, season=2022)} == {1}
        assert {r["fixture_id"] for r in fetch_wc_predictions(db, season=2026)} == {2}

    def test_settled_only_filter(self, tmp_path: Path):
        db = tmp_path / "obs.db"
        record_wc_prediction(db, _make_prediction(fixture_id=1), season=2026)
        record_wc_prediction(db, _make_prediction(fixture_id=2), season=2026)
        settle_wc_prediction(db, 1, home_goals=1, away_goals=0)
        # fixture 2 unsettled
        assert len(fetch_wc_predictions(db)) == 2
        assert len(fetch_wc_predictions(db, settled_only=True)) == 1


# ---------- CLI --record-to integration -------------------------------------

class TestCliRecordTo:
    """The CLI invokes record_wc_prediction at the end of main() when
    --record-to is set. These tests stub the predict pipeline so the
    test doesn't need a real fixture cache / model training."""

    def test_record_to_flag_persists_predictions(self, tmp_path: Path):
        from nutmeg.v4.cli.wc_predict import main

        db = tmp_path / "obs.db"
        out_json = tmp_path / "out.json"

        # Mock the heavy lifting: training, snapshots, fetch.
        # We provide a synthetic predict-output that the CLI assembles.
        synthetic_fixtures = [{
            "fixture": {"id": 1001, "date": "2026-06-11T19:00:00+00:00"},
            "teams": {
                "home": {"name": "Mexico"},
                "away": {"name": "South Africa"},
            },
            "league": {"id": 1, "season": 2026, "round": "Group Stage - 1"},
        }]

        # Build a synthetic single prediction the recorder will see
        synthetic_pred = _make_prediction()

        # Patch the model + data layer so the CLI runs end-to-end
        with patch("nutmeg.v4.cli.wc_predict._train_combined_model") as m_train, \
             patch("nutmeg.v4.cli.wc_predict.load_elo_snapshot") as m_elo, \
             patch("nutmeg.v4.cli.wc_predict._predict_one_fixture") as m_pred, \
             patch("nutmeg.v4.data.sources.api_football.fetch_fixtures_for_league_season") as m_fix, \
             patch("pathlib.Path.glob") as m_glob:
            m_train.return_value = object()  # opaque model
            m_elo.return_value = {}
            m_fix.return_value = synthetic_fixtures
            m_pred.return_value = synthetic_pred
            # Pretend the eloratings snapshot directory has 1 file
            from pathlib import Path as _P
            m_glob.return_value = [_P("data/external/eloratings/eloratings_2026-05-25.parquet")]

            rc = main([
                "--date", "2026-06-11",
                "--out", str(out_json),
                "--record-to", str(db),
                "--quiet",
            ])

        assert rc == 0
        # JSON output should have been written
        assert out_json.exists()
        # And the DB should have 1 row
        rows = fetch_wc_predictions(db)
        assert len(rows) == 1
        assert rows[0]["fixture_id"] == 1489369
        assert rows[0]["season"] == 2026
        assert rows[0]["home_team"] == "Mexico"

    def test_record_to_failure_doesnt_block_json_output(self, tmp_path: Path):
        """If the recorder raises (corrupt DB, permission error, etc.),
        the CLI must still emit JSON + return 0. Verified by mocking
        record_wc_prediction to raise — JSON file should still land."""
        from nutmeg.v4.cli.wc_predict import main

        out_json = tmp_path / "out.json"
        db = tmp_path / "obs.db"

        with patch("nutmeg.v4.cli.wc_predict._train_combined_model") as m_train, \
             patch("nutmeg.v4.cli.wc_predict.load_elo_snapshot") as m_elo, \
             patch("nutmeg.v4.cli.wc_predict._predict_one_fixture") as m_pred, \
             patch("nutmeg.v4.data.sources.api_football.fetch_fixtures_for_league_season") as m_fix, \
             patch("nutmeg.v4.observation.wc_log.record_wc_prediction",
                   side_effect=RuntimeError("simulated DB failure")), \
             patch("pathlib.Path.glob") as m_glob:
            m_train.return_value = object()
            m_elo.return_value = {}
            m_fix.return_value = [{
                "fixture": {"id": 1, "date": "2026-06-11T19:00:00+00:00"},
                "teams": {"home": {"name": "X"}, "away": {"name": "Y"}},
                "league": {"id": 1, "season": 2026},
            }]
            m_pred.return_value = _make_prediction(fixture_id=1)
            from pathlib import Path as _P
            m_glob.return_value = [_P("data/external/eloratings/eloratings_2026-05-25.parquet")]

            rc = main([
                "--date", "2026-06-11",
                "--out", str(out_json),
                "--record-to", str(db),
                "--quiet",
            ])

        # Predict succeeded, JSON written, rc=0 even though persistence failed
        assert rc == 0
        assert out_json.exists()
        # The DB file was NOT created (since record_wc_prediction raised
        # before ensure_wc_predictions_table)
        assert not db.exists()
