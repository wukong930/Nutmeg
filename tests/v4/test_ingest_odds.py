"""Tests for V7 W1 odds_parser + ingest_odds CLI.

Two layers:
  1. data.odds_parser — pure parsing functions on hand-crafted /odds
     envelopes (no IO, no API)
  2. cli.ingest_odds — _gather_rows via mocked api_football fetchers,
     CSV roundtrip via _write_csv
"""
from __future__ import annotations

import csv
import datetime as dt
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from nutmeg.v4.cli import ingest_odds as ingest_odds_mod
from nutmeg.v4.cli.ingest_odds import (
    CSV_COLUMNS,
    _gather_rows,
    _write_csv,
    render_rows_as_csv,
)
from nutmeg.v4.data.odds_parser import (
    BET365_BOOKMAKER_ID,
    BET_MATCH_WINNER,
    PINNACLE_BOOKMAKER_ID,
    extract_1x2_odds,
    extract_over_under,
    extract_over_under_25,
    fixture_envelope_to_csv_row,
)


# ---------- Fixture builders -----------------------------------------

def _envelope(
    *,
    fixture_id: int = 123,
    home: str = "Arsenal",
    away: str = "Liverpool",
    iso_date: str = "2025-08-17T15:00:00+00:00",
    bookmakers: list[dict] | None = None,
) -> dict:
    return {
        "fixture": {"id": fixture_id, "date": iso_date},
        "league": {"id": 39, "name": "Premier League"},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "bookmakers": bookmakers or [],
    }


def _bookmaker_with_1x2(
    *,
    book_id: int = PINNACLE_BOOKMAKER_ID,
    h: str = "2.10", d: str = "3.40", a: str = "3.50",
) -> dict:
    return {
        "id": book_id,
        "name": "Pinnacle",
        "bets": [
            {
                "id": BET_MATCH_WINNER,
                "name": "Match Winner",
                "values": [
                    {"value": "Home", "odd": h},
                    {"value": "Draw", "odd": d},
                    {"value": "Away", "odd": a},
                ],
            },
        ],
    }


def _bookmaker_with_1x2_and_ou(
    *,
    book_id: int = PINNACLE_BOOKMAKER_ID,
    over: str = "2.05",
    under: str = "1.80",
) -> dict:
    bm = _bookmaker_with_1x2(book_id=book_id)
    bm["bets"].append({
        "id": 5,
        "name": "Goals Over/Under",
        "values": [
            {"value": "Over 2.5", "odd": over},
            {"value": "Under 2.5", "odd": under},
            {"value": "Over 1.5", "odd": "1.40"},  # other lines ignored
            {"value": "Under 1.5", "odd": "2.80"},
        ],
    })
    return bm


def _bookmaker_quarter_ou_only(
    *, book_id: int = PINNACLE_BOOKMAKER_ID,
) -> dict:
    """V12 W8b — an Asian-only ladder: main total = 2.25, NO 2.5 line.
    Mirrors Pinnacle's J1 quote where 'Over 2.5' simply isn't offered."""
    bm = _bookmaker_with_1x2(book_id=book_id)
    bm["bets"].append({
        "id": 5,
        "name": "Goals Over/Under",
        "values": [
            {"value": "Over 2.0", "odd": "1.63"},
            {"value": "Under 2.0", "odd": "2.38"},
            {"value": "Over 2.25", "odd": "1.909"},   # main (most balanced)
            {"value": "Under 2.25", "odd": "1.980"},
            {"value": "Over 2.75", "odd": "2.59"},
            {"value": "Under 2.75", "odd": "1.54"},
        ],
    })
    return bm


# ---------- extract_1x2_odds ------------------------------------------

class TestExtract1x2:
    def test_happy_path_pinnacle(self):
        env = _envelope(bookmakers=[_bookmaker_with_1x2()])
        odds = extract_1x2_odds(env, PINNACLE_BOOKMAKER_ID)
        assert odds == {"H": 2.10, "D": 3.40, "A": 3.50}

    def test_missing_bookmaker_returns_none(self):
        env = _envelope(bookmakers=[_bookmaker_with_1x2(book_id=BET365_BOOKMAKER_ID)])
        # Asking for Pinnacle on a Bet365-only envelope → None
        assert extract_1x2_odds(env, PINNACLE_BOOKMAKER_ID) is None

    def test_picks_correct_bookmaker_when_multiple(self):
        env = _envelope(bookmakers=[
            _bookmaker_with_1x2(book_id=BET365_BOOKMAKER_ID, h="2.20", d="3.30", a="3.20"),
            _bookmaker_with_1x2(book_id=PINNACLE_BOOKMAKER_ID, h="2.10", d="3.40", a="3.50"),
        ])
        odds_p = extract_1x2_odds(env, PINNACLE_BOOKMAKER_ID)
        odds_b = extract_1x2_odds(env, BET365_BOOKMAKER_ID)
        assert odds_p == {"H": 2.10, "D": 3.40, "A": 3.50}
        assert odds_b == {"H": 2.20, "D": 3.30, "A": 3.20}

    def test_book_missing_match_winner_returns_none(self):
        bm = {"id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
              "bets": [{"id": 99, "name": "Some other bet", "values": []}]}
        env = _envelope(bookmakers=[bm])
        assert extract_1x2_odds(env, PINNACLE_BOOKMAKER_ID) is None

    def test_partial_outcomes_returns_none(self):
        bm = {
            "id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
            "bets": [{
                "id": BET_MATCH_WINNER, "name": "Match Winner",
                "values": [
                    {"value": "Home", "odd": "2.10"},
                    {"value": "Draw", "odd": "3.40"},
                    # Away missing
                ],
            }],
        }
        assert extract_1x2_odds(_envelope(bookmakers=[bm])) is None

    def test_unparseable_odd_skipped_then_returns_none(self):
        bm = _bookmaker_with_1x2(h="notanumber")
        assert extract_1x2_odds(_envelope(bookmakers=[bm])) is None

    def test_odd_le_one_treated_as_missing(self):
        bm = _bookmaker_with_1x2(h="1.00")  # sentinel "no quote"
        assert extract_1x2_odds(_envelope(bookmakers=[bm])) is None

    def test_extra_value_labels_ignored(self):
        bm = {
            "id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
            "bets": [{
                "id": BET_MATCH_WINNER, "name": "Match Winner",
                "values": [
                    {"value": "Home", "odd": "2.10"},
                    {"value": "Draw", "odd": "3.40"},
                    {"value": "Away", "odd": "3.50"},
                    {"value": "Garbage label", "odd": "9.99"},
                ],
            }],
        }
        assert extract_1x2_odds(_envelope(bookmakers=[bm])) == {
            "H": 2.10, "D": 3.40, "A": 3.50,
        }


# ---------- extract_over_under_25 ------------------------------------

class TestExtractOU25:
    def test_happy_path(self):
        env = _envelope(bookmakers=[_bookmaker_with_1x2_and_ou()])
        out = extract_over_under_25(env, PINNACLE_BOOKMAKER_ID)
        assert out == (2.05, 1.80)

    def test_only_other_lines_returns_none(self):
        bm = {
            "id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
            "bets": [{
                "id": 5, "name": "Goals Over/Under",
                "values": [
                    {"value": "Over 1.5", "odd": "1.40"},
                    {"value": "Under 1.5", "odd": "2.80"},
                ],
            }],
        }
        assert extract_over_under_25(_envelope(bookmakers=[bm])) is None

    def test_missing_bookmaker_returns_none(self):
        env = _envelope(bookmakers=[])
        assert extract_over_under_25(env) is None


# ---------- extract_over_under (main line, V12 W8b) -------------------

class TestExtractOverUnderMainLine:
    def test_prefers_2_5_when_present(self):
        env = _envelope(bookmakers=[_bookmaker_with_1x2_and_ou(over="2.05", under="1.80")])
        assert extract_over_under(env, PINNACLE_BOOKMAKER_ID) == (2.5, 2.05, 1.80)

    def test_falls_back_to_most_balanced_line(self):
        # No 2.5 quoted → pick the line whose over/under are most even (2.25).
        env = _envelope(bookmakers=[_bookmaker_quarter_ou_only()])
        line, over, under = extract_over_under(env, PINNACLE_BOOKMAKER_ID)
        assert line == 2.25
        assert (over, under) == (1.909, 1.980)

    def test_incomplete_pair_skipped(self):
        bm = {
            "id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
            "bets": [{
                "id": 5, "name": "Goals Over/Under",
                "values": [{"value": "Over 2.25", "odd": "1.91"}],  # no under
            }],
        }
        assert extract_over_under(_envelope(bookmakers=[bm])) is None

    def test_missing_bookmaker_returns_none(self):
        assert extract_over_under(_envelope(bookmakers=[])) is None


# ---------- fixture_envelope_to_csv_row -------------------------------

class TestFixtureEnvelopeToRow:
    def test_full_payload(self):
        env = _envelope(bookmakers=[_bookmaker_with_1x2_and_ou()])
        fixture_record = {
            "fixture": {"id": 123, "date": "2025-08-17T15:00:00+00:00"},
            "teams": {"home": {"name": "Arsenal"},
                      "away": {"name": "Liverpool"}},
        }
        row = fixture_envelope_to_csv_row(fixture_record, env, "EPL")
        assert row is not None
        assert row["date"] == "2025-08-17"
        assert row["league"] == "EPL"
        assert row["home_team"] == "Arsenal"
        assert row["away_team"] == "Liverpool"
        assert row["psc_home"] == 2.10
        assert row["psc_draw"] == 3.40
        assert row["psc_away"] == 3.50
        assert row["psc_over25"] == 2.05
        assert row["psc_under25"] == 1.80

    def test_captures_odds_update_timestamp(self):
        # V14 — the /odds payload's 'update' (when API-Football last refreshed
        # this Pinnacle snapshot) rides onto the row so the 市场模式 card can
        # surface the line's age (API-Football trails Pinnacle.com by hours).
        env = _envelope(bookmakers=[_bookmaker_with_1x2()])
        env["update"] = "2025-08-17T13:00:00+00:00"
        fixture_record = {
            "fixture": {"id": 123, "date": "2025-08-17T15:00:00+00:00"},
            "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Liverpool"}},
        }
        row = fixture_envelope_to_csv_row(fixture_record, env, "EPL")
        assert row["odds_update"] == "2025-08-17T13:00:00+00:00"

    def test_odds_update_none_when_absent(self):
        env = _envelope(bookmakers=[_bookmaker_with_1x2()])  # no 'update' key
        fixture_record = {
            "fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
        }
        row = fixture_envelope_to_csv_row(fixture_record, env, "EPL")
        assert row["odds_update"] is None

    def test_no_odds_envelope_returns_none(self):
        fixture_record = {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
                          "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}
        assert fixture_envelope_to_csv_row(fixture_record, None, "EPL") is None

    def test_envelope_without_1x2_returns_none(self):
        # Envelope present but bookmaker lacks Match Winner → drop the row
        bm = {"id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
              "bets": [{"id": 99, "name": "Other", "values": []}]}
        env = _envelope(bookmakers=[bm])
        fixture_record = {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
                          "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}
        assert fixture_envelope_to_csv_row(fixture_record, env, "EPL") is None

    def test_partial_payload_no_ou(self):
        env = _envelope(bookmakers=[_bookmaker_with_1x2()])
        fixture_record = {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
                          "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}
        row = fixture_envelope_to_csv_row(fixture_record, env, "EPL")
        assert row is not None
        assert "psc_over25" not in row
        assert "psc_under25" not in row
        assert "ou_line" not in row  # no O/U → no line stamped

    def test_2_5_line_stamps_ou_line_2_5(self):
        env = _envelope(bookmakers=[_bookmaker_with_1x2_and_ou(over="2.05", under="1.80")])
        fixture_record = {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
                          "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}
        row = fixture_envelope_to_csv_row(fixture_record, env, "EPL")
        # 2.5 present → unchanged psc + ou_line == 2.5 (validated path intact).
        assert row["psc_over25"] == 2.05
        assert row["psc_under25"] == 1.80
        assert row["ou_line"] == 2.5

    def test_quarter_only_falls_back_to_main_line(self):
        """V12 W8b — when 2.5 is absent, capture the main (2.25) line so the
        market-reverse 让球 keeps an O/U anchor instead of a weaker 1X2 fit."""
        env = _envelope(bookmakers=[_bookmaker_quarter_ou_only()])
        fixture_record = {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
                          "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}
        row = fixture_envelope_to_csv_row(fixture_record, env, "JPN_J1")
        assert row["ou_line"] == 2.25
        assert row["psc_over25"] == 1.909
        assert row["psc_under25"] == 1.980

    def test_no_1x2_emits_pending_row_when_not_required(self):
        # V12 W6 — require_1x2_odds=False keeps the fixture as a 待开盘 row
        # (psc_* = None + metadata) instead of dropping it, so 近期赛事 can
        # list it until Pinnacle opens.
        bm = {"id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
              "bets": [{"id": 99, "name": "Other", "values": []}]}
        env = _envelope(bookmakers=[bm])
        fixture_record = {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
                          "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}
        row = fixture_envelope_to_csv_row(
            fixture_record, env, "EPL", require_1x2_odds=False)
        assert row is not None
        assert row["home_team"] == "A" and row["away_team"] == "B"
        assert row["psc_home"] is None
        assert row["psc_draw"] is None
        assert row["psc_away"] is None
        assert row["kickoff_utc"] == "2025-08-17T15:00:00+00:00"

    def test_none_envelope_emits_pending_row_when_not_required(self):
        fixture_record = {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
                          "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}
        row = fixture_envelope_to_csv_row(
            fixture_record, None, "EPL", require_1x2_odds=False)
        assert row is not None
        assert row["psc_home"] is None
        # Default (require_1x2_odds=True) still drops it.
        assert fixture_envelope_to_csv_row(fixture_record, None, "EPL") is None


# ---------- CLI _gather_rows (mocked api_football) -----------------

class TestGatherRows:
    def _patch_fixtures(self, by_league: dict[str, list[dict]]):
        def fake_fetch_fixtures(on_date, league_canonical=None, **kw):
            return by_league.get(league_canonical, [])
        return patch.object(
            ingest_odds_mod.api_football,
            "fetch_fixtures_for_date",
            side_effect=fake_fetch_fixtures,
        )

    def _patch_odds(self, by_fixture_id: dict[int, dict | None]):
        def fake_fetch_odds(fixture_id, **kw):
            env = by_fixture_id.get(fixture_id)
            return [env] if env is not None else []
        return patch.object(
            ingest_odds_mod.api_football,
            "fetch_odds",
            side_effect=fake_fetch_odds,
        )

    def test_two_leagues_three_fixtures(self, tmp_path):
        fixtures = {
            "EPL": [
                {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
                 "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Liverpool"}}},
                {"fixture": {"id": 2, "date": "2025-08-17T17:30:00+00:00"},
                 "teams": {"home": {"name": "Chelsea"}, "away": {"name": "Spurs"}}},
            ],
            "ESP_LA_LIGA": [
                {"fixture": {"id": 3, "date": "2025-08-17T20:00:00+00:00"},
                 "teams": {"home": {"name": "Real Madrid"}, "away": {"name": "Getafe"}}},
            ],
        }
        odds = {
            1: _envelope(bookmakers=[_bookmaker_with_1x2(h="2.10", d="3.40", a="3.50")]),
            2: _envelope(bookmakers=[_bookmaker_with_1x2(h="2.60", d="3.30", a="2.80")]),
            3: _envelope(bookmakers=[_bookmaker_with_1x2_and_ou()]),
        }
        with self._patch_fixtures(fixtures), self._patch_odds(odds):
            rows, n_calls, n_skipped = _gather_rows(
                ["EPL", "ESP_LA_LIGA"],
                dt.date(2025, 8, 17),
                cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False,
                refresh_odds=False,
            )
        assert len(rows) == 3
        # 2 league /fixtures + 3 /odds = 5 calls
        assert n_calls == 5
        assert n_skipped == 0
        # First row checks
        assert rows[0]["home_team"] == "Arsenal"
        assert rows[0]["psc_home"] == 2.10
        # La Liga row has O/U
        la_row = next(r for r in rows if r["league"] == "ESP_LA_LIGA")
        assert la_row["psc_over25"] == 2.05

    def test_fixtures_without_pinnacle_skipped(self, tmp_path):
        fixtures = {"EPL": [
            {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
             "teams": {"home": {"name": "A"}, "away": {"name": "B"}}},
            {"fixture": {"id": 2, "date": "2025-08-17T15:00:00+00:00"},
             "teams": {"home": {"name": "C"}, "away": {"name": "D"}}},
        ]}
        odds = {
            1: _envelope(bookmakers=[_bookmaker_with_1x2()]),
            # Fixture 2 only has Bet365 — requesting Pinnacle → skipped
            2: _envelope(bookmakers=[
                _bookmaker_with_1x2(book_id=BET365_BOOKMAKER_ID),
            ]),
        }
        with self._patch_fixtures(fixtures), self._patch_odds(odds):
            rows, _, n_skipped = _gather_rows(
                ["EPL"], dt.date(2025, 8, 17),
                cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
            )
        assert len(rows) == 1
        assert n_skipped == 1

    def test_empty_odds_response_skipped(self, tmp_path):
        fixtures = {"EPL": [
            {"fixture": {"id": 1, "date": "2025-08-17T15:00:00+00:00"},
             "teams": {"home": {"name": "A"}, "away": {"name": "B"}}},
        ]}
        with self._patch_fixtures(fixtures), self._patch_odds({1: None}):
            rows, _, n_skipped = _gather_rows(
                ["EPL"], dt.date(2025, 8, 17),
                cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
            )
        assert rows == []
        assert n_skipped == 1


# ---------- V12 W0 Plan A: kickoff buffer filter ---------------------

class TestKickoffBufferFilter:
    """V12 W0 (2026-05-28) — `_gather_rows` filters out already-kicked-off
    fixtures so the morning + afternoon cron waves produce different
    optimal solutions. Without this, the 14:00 cron would still include
    a J1 match that started at 12:00 (with stale closing odds).
    """

    def _patch_fixtures(self, by_league):
        def fake(on_date, league_canonical=None, **kw):
            return by_league.get(league_canonical, [])
        return patch.object(
            ingest_odds_mod.api_football,
            "fetch_fixtures_for_date",
            side_effect=fake,
        )

    def _patch_odds(self, by_fixture_id):
        def fake(fixture_id, **kw):
            env = by_fixture_id.get(fixture_id)
            return [env] if env is not None else []
        return patch.object(
            ingest_odds_mod.api_football,
            "fetch_odds",
            side_effect=fake,
        )

    def _fixture(self, fid, hour_offset, status="NS", home="Home", away="Away"):
        """Build a fixture dict with kickoff = now + hour_offset hours."""
        now = dt.datetime(2026, 5, 28, 10, 0, 0, tzinfo=dt.UTC)  # fixed clock
        kickoff = now + dt.timedelta(hours=hour_offset)
        return {
            "fixture": {
                "id": fid,
                "date": kickoff.isoformat(),
                "status": {"short": status, "long": "..."},
            },
            "teams": {"home": {"name": home}, "away": {"name": away}},
        }

    def test_buffer_zero_disables_filter_legacy_behavior(self, tmp_path):
        """min_kickoff_buffer_minutes=0 → all fixtures included (legacy)."""
        fixtures = {
            "EPL": [self._fixture(1, hour_offset=5, status="NS"),
                    self._fixture(2, hour_offset=-2, status="FT")],  # already done
        }
        odds = {
            1: _envelope(bookmakers=[_bookmaker_with_1x2()]),
            2: _envelope(bookmakers=[_bookmaker_with_1x2()]),
        }
        now = dt.datetime(2026, 5, 28, 10, 0, 0, tzinfo=dt.UTC)
        with self._patch_fixtures(fixtures), self._patch_odds(odds):
            rows, _, _ = _gather_rows(
                ["EPL"], dt.date(2026, 5, 28),
                cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                min_kickoff_buffer_minutes=0,
                now_utc=now,
            )
        assert len(rows) == 2  # no filtering applied

    def test_filter_drops_already_started_fixtures(self, tmp_path):
        """status != NS/TBD/POSTP → dropped pre-emptively (saves /odds call)."""
        fixtures = {
            "EPL": [
                self._fixture(1, hour_offset=5, status="NS",
                              home="Future", away="Match"),
                self._fixture(2, hour_offset=-2, status="FT",
                              home="Already", away="Done"),
                self._fixture(3, hour_offset=-0.5, status="IN_PLAY",
                              home="In", away="Play"),
            ],
        }
        odds = {1: _envelope(bookmakers=[_bookmaker_with_1x2()])}
        now = dt.datetime(2026, 5, 28, 10, 0, 0, tzinfo=dt.UTC)
        with self._patch_fixtures(fixtures), self._patch_odds(odds):
            rows, n_calls, n_skipped = _gather_rows(
                ["EPL"], dt.date(2026, 5, 28),
                cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                min_kickoff_buffer_minutes=30,
                now_utc=now,
            )
        assert len(rows) == 1
        assert rows[0]["home_team"] == "Future"
        assert n_skipped == 2  # FT + IN_PLAY skipped pre-flight
        # /odds API only called for the 1 viable fixture (saves quota)
        # api_calls = 1 fixtures + 1 odds = 2
        assert n_calls == 2

    # ── keep_started(2026-09-03)———————————————————————————————
    # owner 实报:一场比赛开球前 5 分钟还在卡片上,**一按 🔄 就整张消失**。
    # 根因:上面那个开球闸的 `continue` 同时做了两件事,而注释声明的目的只有第一件
    # (「skip API /odds call ... to save quota」)—— 它顺带把**行**也删了。
    # 而前端的同款闸只是把它移出「可投注」分组、卡片还在 ⇒ 同一条规则,
    # 一边降级一边删除。`keep_started=True` 把两件事拆开。

    def test_keep_started_emits_a_row_without_spending_quota(self, tmp_path):
        """🚨 承重:出行,但**不发 /odds 请求**(零额外配额是这条改动的前提)。"""
        fixtures = {"EPL": [
            self._fixture(1, hour_offset=5, status="NS", home="Future", away="Match"),
            self._fixture(2, hour_offset=-0.2, status="NS", home="Just", away="Started"),
        ]}
        odds = {1: _envelope(bookmakers=[_bookmaker_with_1x2()]),
                2: _envelope(bookmakers=[_bookmaker_with_1x2()])}
        now = dt.datetime(2026, 5, 28, 10, 0, 0, tzinfo=dt.UTC)
        with self._patch_fixtures(fixtures), self._patch_odds(odds) as m:
            rows, n_calls, _ = _gather_rows(
                ["EPL"], dt.date(2026, 5, 28), cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                require_odds=False, min_kickoff_buffer_minutes=5,
                keep_started=True, now_utc=now,
            )
        by = {r["home_team"]: r for r in rows}
        assert set(by) == {"Future", "Just"}, f"已开赛那场没留下:{list(by)}"
        assert by["Just"].get("started") is True, "留下了但没打 started 标记"
        assert by["Future"].get("started") in (None, False), "把没开赛的也标成已开赛了"
        # 🚨 零额外配额:/odds 只对没开赛那场调过一次
        called = [c.args[0] for c in m.call_args_list]
        assert called == [1], f"给已开赛的场发了付费请求:{called}"

    def test_default_still_drops_it_so_the_cron_is_unchanged(self, tmp_path):
        """⚠️ 对照组:默认 `keep_started=False` 必须**照旧删行**。

        `cli/predict_log.py` 那条 cron 依赖「删行」产生上午/下午两套不同的推荐集
        (见 `_gather_rows` docstring 的 V12 W0 那段)。改服务路径不能顺手改它。
        """
        fixtures = {"EPL": [
            self._fixture(1, hour_offset=5, status="NS", home="Future", away="Match"),
            self._fixture(2, hour_offset=-0.2, status="NS", home="Just", away="Started"),
        ]}
        odds = {1: _envelope(bookmakers=[_bookmaker_with_1x2()])}
        now = dt.datetime(2026, 5, 28, 10, 0, 0, tzinfo=dt.UTC)
        with self._patch_fixtures(fixtures), self._patch_odds(odds):
            rows, _, n_skipped = _gather_rows(
                ["EPL"], dt.date(2026, 5, 28), cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                require_odds=False, min_kickoff_buffer_minutes=5,
                now_utc=now,
            )
        assert [r["home_team"] for r in rows] == ["Future"]
        assert n_skipped == 1

    def test_started_rows_carry_no_pinnacle_line(self, tmp_path):
        """已开赛的行 `psc_*` 必须为空 —— 它没被拉过赔率,凭空有线就是数据造假。"""
        fixtures = {"EPL": [self._fixture(2, hour_offset=-0.2, status="NS",
                                          home="Just", away="Started")]}
        now = dt.datetime(2026, 5, 28, 10, 0, 0, tzinfo=dt.UTC)
        with self._patch_fixtures(fixtures), self._patch_odds({}):
            rows, _, _ = _gather_rows(
                ["EPL"], dt.date(2026, 5, 28), cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                require_odds=False, min_kickoff_buffer_minutes=5,
                keep_started=True, now_utc=now,
            )
        assert len(rows) == 1 and rows[0]["psc_home"] is None

    def test_filter_drops_kickoff_within_buffer(self, tmp_path):
        """status=NS but kickoff is within buffer → still dropped.

        Use case: 30 min buffer applied at 14:00 — a 14:15 kickoff with
        status still "NS" is too close, drop it (no time to actually bet).
        """
        fixtures = {
            "EPL": [
                self._fixture(1, hour_offset=5, status="NS", home="Far"),
                # 15 minutes from "now" — inside the 30-min buffer
                self._fixture(2, hour_offset=0.25, status="NS", home="Imminent"),
            ],
        }
        odds = {
            1: _envelope(bookmakers=[_bookmaker_with_1x2()]),
        }
        now = dt.datetime(2026, 5, 28, 10, 0, 0, tzinfo=dt.UTC)
        with self._patch_fixtures(fixtures), self._patch_odds(odds):
            rows, _, n_skipped = _gather_rows(
                ["EPL"], dt.date(2026, 5, 28),
                cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                min_kickoff_buffer_minutes=30,
                now_utc=now,
            )
        assert len(rows) == 1
        assert rows[0]["home_team"] == "Far"
        assert n_skipped == 1

    def test_morning_vs_afternoon_wave_scenario(self, tmp_path):
        """E2E: same fixture set, two different `now_utc` → different output.

        This is the V12 W0 Plan A core scenario:
          - 10:00 morning wave: includes J1 12:00 + EU 20:00 (both upcoming)
          - 15:00 afternoon wave: J1 already at FT, only EU 20:00 remains
        """
        j1_match = {
            "fixture": {
                "id": 100,
                "date": "2026-05-28T12:00:00+00:00",
                "status": {"short": "NS", "long": "Not Started"},
            },
            "teams": {"home": {"name": "Greuther Furth"},
                      "away": {"name": "Tokyo"}},
        }
        eu_match = {
            "fixture": {
                "id": 200,
                "date": "2026-05-28T20:00:00+00:00",
                "status": {"short": "NS", "long": "Not Started"},
            },
            "teams": {"home": {"name": "Arsenal"},
                      "away": {"name": "Liverpool"}},
        }
        odds = {
            100: _envelope(bookmakers=[_bookmaker_with_1x2()]),
            200: _envelope(bookmakers=[_bookmaker_with_1x2()]),
        }

        # MORNING WAVE — 10:00 UTC: both J1 + EU are upcoming
        with self._patch_fixtures({"EPL": [j1_match, eu_match]}), \
             self._patch_odds(odds):
            morning_rows, _, _ = _gather_rows(
                ["EPL"], dt.date(2026, 5, 28),
                cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                min_kickoff_buffer_minutes=30,
                now_utc=dt.datetime(2026, 5, 28, 10, 0, 0, tzinfo=dt.UTC),
            )
        assert len(morning_rows) == 2
        teams_morning = {r["home_team"] for r in morning_rows}
        assert teams_morning == {"Greuther Furth", "Arsenal"}

        # AFTERNOON WAVE — 15:00 UTC: J1 is at FT, only EU remains
        j1_finished = dict(j1_match)
        j1_finished["fixture"] = dict(j1_match["fixture"])
        j1_finished["fixture"]["status"] = {"short": "FT", "long": "Match Finished"}
        with self._patch_fixtures({"EPL": [j1_finished, eu_match]}), \
             self._patch_odds(odds):
            afternoon_rows, _, _ = _gather_rows(
                ["EPL"], dt.date(2026, 5, 28),
                cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                min_kickoff_buffer_minutes=30,
                now_utc=dt.datetime(2026, 5, 28, 15, 0, 0, tzinfo=dt.UTC),
            )
        assert len(afternoon_rows) == 1
        assert afternoon_rows[0]["home_team"] == "Arsenal"


# ---------- CSV roundtrip --------------------------------------------

class TestCsvWrite:
    def test_render_rows_as_csv_roundtrips_via_pandas(self):
        rows = [
            {"date": "2025-08-17", "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "psc_home": 2.10, "psc_draw": 3.40, "psc_away": 3.50,
             "psc_over25": 2.05, "psc_under25": 1.80},
            {"date": "2025-08-17", "league": "EPL",
             "home_team": "Chelsea", "away_team": "Spurs",
             "psc_home": 2.60, "psc_draw": 3.30, "psc_away": 2.80},
        ]
        csv_text = render_rows_as_csv(rows)
        # Header
        first_line = csv_text.splitlines()[0]
        for col in ("date", "league", "home_team", "psc_home",
                    "psc_over25", "handicap_home"):
            assert col in first_line
        # Roundtrip via pandas
        df = pd.read_csv(StringIO(csv_text))
        assert len(df) == 2
        assert df.iloc[0]["home_team"] == "Arsenal"
        assert float(df.iloc[0]["psc_home"]) == 2.10
        # NaN in the lottery-specific cols (left blank)
        assert pd.isna(df.iloc[0]["odds_1x2_H"])

    def test_empty_rows_writes_header_only(self):
        csv_text = render_rows_as_csv([])
        lines = csv_text.strip().splitlines()
        # Exactly one line (the header) for empty input
        assert len(lines) == 1
        assert "date" in lines[0]

    def test_write_to_file_path(self, tmp_path):
        target = tmp_path / "sub" / "out.csv"
        rows = [{"date": "2025-08-17", "league": "EPL",
                 "home_team": "A", "away_team": "B",
                 "psc_home": 2.0, "psc_draw": 3.0, "psc_away": 4.0}]
        _write_csv(rows, target)
        assert target.exists()
        text = target.read_text()
        assert "Arsenal" not in text  # sanity
        assert "EPL" in text

    def test_csv_columns_constant_includes_lottery_blanks(self):
        # Schema includes handicap + lottery odds columns (left blank
        # in the auto-generated output; user fills at bet time)
        for col in ("handicap_home", "odds_1x2_H", "odds_1x2_D", "odds_1x2_A",
                    "odds_handicap_H", "odds_handicap_D", "odds_handicap_A"):
            assert col in CSV_COLUMNS


def test_overlay_skips_started_match_live_odds():
    """体检 A2 (2026-07-01) — the odds_api overlay must NOT patch a match that has
    already kicked off: post-KO the Odds API serves in-play odds (a leading team →
    a degenerate 1.06/53.96 line). Pre-KO it patches; post-KO it skips."""
    import datetime as dt

    from nutmeg.v4.cli.ingest_odds import _apply_odds_api_overlay
    from nutmeg.v4.data.sources.odds_api import _norm_team

    row = {"home_team": "Mexico", "away_team": "Ecuador", "date": "2026-08-01",
           "psc_home": 2.0, "psc_draw": 3.2, "psc_away": 3.8}
    rec = {"psc_home": 1.06, "psc_draw": 15.0, "psc_away": 53.96,  # in-play line
           "ou_line": None, "last_update": "x",
           "commence_time": "2026-08-01T18:00:00Z"}
    oa = {(_norm_team("Mexico"), _norm_team("Ecuador"), "2026-08-01"): rec}

    pre = dict(row)
    assert _apply_odds_api_overlay(
        pre, oa, now=dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.UTC)) is True
    assert pre["psc_home"] == 1.06   # pre-KO → overlaid

    post = dict(row)
    assert _apply_odds_api_overlay(
        post, oa, now=dt.datetime(2026, 8, 1, 20, 0, tzinfo=dt.UTC)) is False
    assert post["psc_home"] == 2.0   # post-KO → skipped, row untouched


class TestUtcDateAnchors:
    """体检 2026-07-03 (CLI layer, follows tests/v4/test_api.py) — fixture-date
    windows anchored on the process-local date (Asia/Shanghai) roll at Beijing
    midnight (16:00 UTC) and ask for TOMORROW's fixtures, dropping the
    late-night EU slate (UTC 16:00-23:59 kickoffs = Beijing 00:00-07:59).
    ingest_odds --date and rec --auto-fetch both feed the UTC-interpreted
    fetch_fixtures_for_date, so their defaults must anchor on UTC."""

    def test_no_local_date_today_in_fixture_window_clis(self):
        import inspect

        from nutmeg.v4.cli import ingest_odds, rec

        for mod in (ingest_odds, rec):
            src = inspect.getsource(mod)
            assert ".date.today()" not in src, (
                f"{mod.__name__} uses process-local date.today() — fixture "
                "dates are UTC; use ingest_odds._utc_today() (Beijing-midnight "
                "premature-drop bug, 2026-07-03)")

    def test_utc_today_is_utc(self):
        assert ingest_odds_mod._utc_today() == dt.datetime.now(dt.UTC).date()

    def test_date_default_resolves_to_utc_today(self):
        """main() with no --date must gather for the UTC date, not the local one."""
        seen: dict = {}

        def fake_gather(leagues, on_date, **kw):
            seen["date"] = on_date
            return [], 0, 0

        with patch.object(ingest_odds_mod, "_gather_rows", side_effect=fake_gather):
            rc = ingest_odds_mod.main(["--leagues", "EPL", "--out", "-", "--quiet"])
        assert rc == 0
        assert seen["date"] == dt.datetime.now(dt.UTC).date()
