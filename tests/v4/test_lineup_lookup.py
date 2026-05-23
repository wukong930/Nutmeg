"""Tests for nutmeg.v4.data.lineup_lookup (V6 W5+W6).

Focus on the leak-prevention helpers and the recent-injury counter —
the only feature subset that survived V6 W5+W6 ablation.
"""
from __future__ import annotations

import datetime as dt

import pytest

from nutmeg.v4.data.lineup_lookup import (
    DEFAULT_INJURY_WINDOW_DAYS,
    _filter_injuries_before,
    _recent_unique_injured_count,
)


def _injury(player_id: int, date_str: str) -> dict:
    """Build a minimal injury record shaped like API-Football /injuries."""
    return {
        "player": {"id": player_id, "name": f"P{player_id}"},
        "fixture": {"id": 0, "date": f"{date_str}T15:00:00+00:00"},
    }


class TestFilterInjuriesBefore:
    def test_keeps_only_past(self):
        records = [
            _injury(1, "2024-08-10"),
            _injury(2, "2024-09-01"),
            _injury(3, "2024-10-15"),
        ]
        result = _filter_injuries_before(records, "2024-09-15")
        assert {r["player"]["id"] for r in result} == {1, 2}

    def test_strict_less_than(self):
        # match_date itself is excluded (no leakage from same-day events)
        records = [_injury(1, "2024-09-15")]
        result = _filter_injuries_before(records, "2024-09-15")
        assert result == []

    def test_empty_list_passthrough(self):
        assert _filter_injuries_before([], "2024-09-15") == []

    def test_none_returns_none(self):
        assert _filter_injuries_before(None, "2024-09-15") is None

    def test_missing_date_field_filtered_out(self):
        # Records without a parseable date are conservatively dropped
        bad = {"player": {"id": 99}, "fixture": {}}
        records = [_injury(1, "2024-08-10"), bad]
        result = _filter_injuries_before(records, "2024-09-15")
        assert {r["player"]["id"] for r in result} == {1}


class TestRecentUniqueInjuredCount:
    def test_empty_inputs_zero(self):
        assert _recent_unique_injured_count(None, "2024-09-15") == 0
        assert _recent_unique_injured_count([], "2024-09-15") == 0

    def test_unique_players_in_window(self):
        # Match on 2024-10-01, window 30 days = back to 2024-09-01
        records = [
            _injury(1, "2024-09-15"),   # in window
            _injury(2, "2024-09-25"),   # in window
            _injury(1, "2024-09-20"),   # in window but same player → dedupe
            _injury(3, "2024-08-01"),   # out of window
            _injury(4, "2024-10-05"),   # AFTER match_date → must be excluded
        ]
        count = _recent_unique_injured_count(records, "2024-10-01", window_days=30)
        assert count == 2  # players 1 and 2

    def test_default_window_30_days(self):
        assert DEFAULT_INJURY_WINDOW_DAYS == 30
        records = [_injury(1, "2024-08-25")]  # 7 days before match
        assert _recent_unique_injured_count(records, "2024-09-01") == 1
        # Same record but match 60 days later → out of window
        assert _recent_unique_injured_count(records, "2024-10-30") == 0

    def test_custom_window(self):
        records = [_injury(1, "2024-07-15")]
        assert _recent_unique_injured_count(records, "2024-09-15", window_days=30) == 0
        assert _recent_unique_injured_count(records, "2024-09-15", window_days=90) == 1

    def test_invalid_match_date_returns_zero(self):
        records = [_injury(1, "2024-09-15")]
        assert _recent_unique_injured_count(records, "garbage") == 0

    def test_no_leak_at_boundary(self):
        # Player injured on the SAME day as match — must NOT be counted
        records = [_injury(1, "2024-09-15")]
        assert _recent_unique_injured_count(records, "2024-09-15") == 0

    def test_handles_missing_player_id(self):
        records = [
            {"player": {}, "fixture": {"date": "2024-09-15"}},  # no id → skipped
            _injury(1, "2024-09-15"),
        ]
        # Match date is 2024-09-20, so the 09-15 records are in window. Only the
        # one with a player_id is counted.
        assert _recent_unique_injured_count(records, "2024-09-20") == 1
