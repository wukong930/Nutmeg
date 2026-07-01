"""体检 A1 — odds_snapshots append-only line history (the CLV foundation)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from nutmeg.v4.data.odds_parser import PINNACLE_BOOKMAKER_ID
from nutmeg.v4.observation.odds_snapshots import record_row_snapshot


def _row(**over) -> dict:
    base = {
        "date": "2026-06-11", "league": "WC",
        "home_team": "Mexico", "away_team": "South Africa",
        "psc_home": 1.65, "psc_draw": 3.90, "psc_away": 5.60,
        "psc_over25": 1.85, "psc_under25": 1.95, "ou_line": 2.5,
        "kickoff_utc": "2026-06-11T19:00:00+00:00",
        "odds_update": "2026-06-10T08:00:00+00:00",
    }
    base.update(over)
    return base


def _all(db: Path) -> list[tuple]:
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT psc_home, odds_update, source FROM odds_snapshots ORDER BY id"
        ).fetchall()


class TestRecordRowSnapshot:
    def test_first_insert(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101, source="ingest_odds")
        rows = _all(db)
        assert rows == [(1.65, "2026-06-10T08:00:00+00:00", "ingest_odds")]

    def test_unchanged_state_dedups(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(db, _row(), fixture_id=101) is False
        assert len(_all(db)) == 1

    def test_price_move_appends_both_rows_kept(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(db, _row(psc_home=1.70), fixture_id=101)
        prices = [r[0] for r in _all(db)]
        assert prices == [1.65, 1.70]  # append-only: history retained

    def test_fresh_odds_update_same_prices_is_new_state(self, tmp_path):
        # "line re-confirmed at T" is closing-line evidence — kept on purpose.
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(
            db, _row(odds_update="2026-06-11T18:00:00+00:00"), fixture_id=101)
        assert len(_all(db)) == 2

    def test_match_key_dedup_without_fixture_id(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row())
        assert record_row_snapshot(db, _row()) is False
        assert len(_all(db)) == 1

    def test_pending_row_skipped(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(
            db, _row(psc_home=None, psc_draw=None, psc_away=None),
            fixture_id=102) is False
        assert len(_all(db)) == 1

    def test_asian_handicap_json_stored(self, tmp_path, monkeypatch):
        import nutmeg.v4.data.odds_parser as op
        monkeypatch.setattr(
            op, "extract_asian_handicap",
            lambda env, bid=PINNACLE_BOOKMAKER_ID: {-1.5: {"home": 1.9, "away": 1.9}})
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101, envelope={"x": 1})
        with sqlite3.connect(db) as conn:
            (ah,) = conn.execute(
                "SELECT asian_handicap FROM odds_snapshots").fetchone()
        assert '"-1.5"' in ah and '"home": 1.9' in ah

    def test_never_raises_on_bad_db_path(self):
        assert record_row_snapshot(
            "/nonexistent_dir_xyz/obs.db", _row(), fixture_id=1) is False


class TestOddsSanityGuard:
    """体检 A1 (2026-07-01) — the shared CLV/soft-water sink must reject
    physically-impossible odds regardless of which producer emits them. Before
    the guard it stored 1.06/…/53.96, psc=0.5, psc=−3.0 (all returned True)."""

    def test_rejects_sub_unity_leg(self, tmp_path):
        # insert one valid row first so the table exists, then prove the bad one
        # is rejected AND does not append
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(db, _row(psc_home=0.5), fixture_id=102) is False
        assert len(_all(db)) == 1

    def test_rejects_negative_leg(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_draw=-3.0), fixture_id=101) is False

    def test_rejects_exactly_one(self, tmp_path):
        # a decimal odd of 1.0 means zero payout over stake — impossible
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_away=1.0), fixture_id=101) is False

    def test_rejects_nan_and_inf(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_home=float("nan")), fixture_id=1) is False
        assert record_row_snapshot(db, _row(psc_home=float("inf")), fixture_id=2) is False

    def test_rejects_absurd_ceiling(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_away=5000.0), fixture_id=101) is False

    def test_rejects_impossible_ou_leg(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_over25=0.4), fixture_id=101) is False

    def test_accepts_legit_deep_mismatch(self, tmp_path):
        # A genuine minnow-vs-giant pre-match line (short fav + long dog) is
        # numerically indistinguishable from an in-play degenerate line by value,
        # so the sink guard MUST pass it — in-play detection is the kickoff/
        # commence_time guards' job (closing capture + overlay + readers), NOT
        # this odds-sanity backstop. Guarding this here would drop real lines.
        db = tmp_path / "obs.db"
        assert record_row_snapshot(
            db, _row(psc_home=1.03, psc_draw=17.0, psc_away=60.0), fixture_id=101)
        assert len(_all(db)) == 1


class TestGatherRowsHook:
    """The _gather_rows choke point feeds snapshots (one hook → every flow)."""

    def _wire(self, monkeypatch, fixture_id=777):
        from nutmeg.v4.cli import ingest_odds as mod
        envelope = {
            "fixture": {"id": fixture_id, "date": "2026-06-11T19:00:00+00:00",
                        "status": {"short": "NS"}},
            "teams": {"home": {"name": "Mexico"},
                      "away": {"name": "South Africa"}},
            "update": "2026-06-10T08:00:00+00:00",
            "bookmakers": [{
                "id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
                "bets": [{"id": 1, "name": "Match Winner", "values": [
                    {"value": "Home", "odd": "1.65"},
                    {"value": "Draw", "odd": "3.90"},
                    {"value": "Away", "odd": "5.60"},
                ]}],
            }],
        }
        monkeypatch.setattr(
            mod.api_football, "fetch_fixtures_for_date",
            lambda *a, **k: [envelope])
        monkeypatch.setattr(
            mod.api_football, "fetch_odds", lambda *a, **k: [envelope])
        return mod

    def test_gather_snapshots_once_then_dedups(self, tmp_path, monkeypatch):
        import datetime as dt
        mod = self._wire(monkeypatch)
        db = tmp_path / "obs.db"
        for _ in (1, 2):  # second pass = unchanged cache → no new state
            mod._gather_rows(
                ["WC"], dt.date(2026, 6, 11), cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                snapshot_db=db, snapshot_source="ingest_odds")
        rows = _all(db)
        assert len(rows) == 1 and rows[0][2] == "ingest_odds"

    def test_gather_without_snapshot_db_writes_nothing(self, tmp_path, monkeypatch):
        import datetime as dt
        mod = self._wire(monkeypatch)
        mod._gather_rows(
            ["WC"], dt.date(2026, 6, 11), cache_dir=tmp_path,
            bookmaker_id=PINNACLE_BOOKMAKER_ID,
            refresh_fixtures=False, refresh_odds=False)
        assert not (tmp_path / "obs.db").exists()
