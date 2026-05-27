"""Tests for v4.data.playoff_context — V12 W0 P0 follow-up.

The module is a coarse hard-coded heuristic; tests anchor:
  (1) the two specific fixtures from the 2026-05-26 real bet that
      triggered this work
  (2) basic boundary semantics (inclusive endpoints, league mismatch,
      out-of-window dates)
  (3) tolerant input handling (date object vs string, ISO with time)
"""
from __future__ import annotations

from datetime import date

import pytest

from nutmeg.v4.data.playoff_context import (
    PlayoffWindow,
    all_windows,
    detect_playoff,
)


# ─────────────────────────────────────────────────────────────────
# The two real fixtures that triggered V12 W0 playoff-awareness work
# ─────────────────────────────────────────────────────────────────

def test_fra_ligue1_2026_05_26_is_playoff():
    """法甲 Saint-Étienne vs Nice on 2026-05-26 — Ligue 1 barrage."""
    w = detect_playoff("FRA_LIGUE_1", "2026-05-26")
    assert w is not None
    assert w.league == "FRA_LIGUE_1"
    assert "barrage" in w.context.lower()


def test_ger_2_bundesliga_2026_05_26_is_playoff():
    """德乙 Fürth vs Essen on 2026-05-26 — 2.BL Relegations-Playoff."""
    w = detect_playoff("GER_2_BUNDESLIGA", "2026-05-26")
    assert w is not None
    assert w.league == "GER_2_BUNDESLIGA"
    assert "playoff" in w.context.lower() or "barrage" in w.context.lower()


# ─────────────────────────────────────────────────────────────────
# Boundary + lookup semantics
# ─────────────────────────────────────────────────────────────────

def test_inclusive_start_endpoint():
    """`start` date itself returns a window (inclusive lower bound)."""
    w = detect_playoff("FRA_LIGUE_1", "2026-05-22")  # exact start
    assert w is not None


def test_inclusive_end_endpoint():
    """`end` date itself returns a window (inclusive upper bound)."""
    w = detect_playoff("FRA_LIGUE_1", "2026-06-02")  # exact end
    assert w is not None


def test_before_window_returns_none():
    """Date strictly before all `FRA_LIGUE_1` windows → None."""
    assert detect_playoff("FRA_LIGUE_1", "2026-05-21") is None


def test_after_window_returns_none():
    """Date strictly after all `FRA_LIGUE_1` windows → None."""
    assert detect_playoff("FRA_LIGUE_1", "2026-06-03") is None


def test_league_without_window_returns_none():
    """A league with no windows configured returns None for any date."""
    # EPL has no playoff windows registered (it's not promotion/relegation
    # via playoff — bottom 3 simply drop)
    assert detect_playoff("EPL", "2026-05-26") is None


def test_unknown_league_returns_none():
    """Garbage league code is just None (no exception)."""
    assert detect_playoff("FOO_BAR", "2026-05-26") is None


# ─────────────────────────────────────────────────────────────────
# Tolerant input handling
# ─────────────────────────────────────────────────────────────────

def test_accepts_date_object():
    w = detect_playoff("FRA_LIGUE_1", date(2026, 5, 26))
    assert w is not None


def test_accepts_iso_with_time_component():
    """Common API-Football fixture timestamps have T suffix."""
    w = detect_playoff("FRA_LIGUE_1", "2026-05-26T20:00:00+00:00")
    assert w is not None


# ─────────────────────────────────────────────────────────────────
# all_windows() diagnostic helper
# ─────────────────────────────────────────────────────────────────

def test_all_windows_returns_list_of_dataclasses():
    items = all_windows()
    assert len(items) > 0
    assert all(isinstance(w, PlayoffWindow) for w in items)


def test_all_windows_covers_expected_leagues():
    """Sanity check that the 9 European leagues we curated are present."""
    leagues = {w.league for w in all_windows()}
    expected = {
        "FRA_LIGUE_1", "FRA_LIGUE_2",
        "GER_BUNDESLIGA", "GER_2_BUNDESLIGA",
        "ENG_CHAMPIONSHIP",
        "ESP_SEGUNDA_DIVISION",
        "ITA_SERIE_B",
        "NED_EREDIVISIE",
        "PRT_PRIMEIRA_LIGA",
        "BEL_PRO_LEAGUE",
    }
    missing = expected - leagues
    assert not missing, f"Expected leagues not in windows: {missing}"


def test_all_windows_have_valid_iso_dates():
    """Every window's start ≤ end and both parse as ISO YYYY-MM-DD."""
    from datetime import date as _d
    for w in all_windows():
        s = _d.fromisoformat(w.start)
        e = _d.fromisoformat(w.end)
        assert s <= e, f"{w.league}: start {w.start} > end {w.end}"


def test_all_windows_have_non_empty_context():
    for w in all_windows():
        assert w.context.strip(), f"{w.league}: empty context"
        assert w.model_bias_note.strip(), f"{w.league}: empty model_bias_note"
