"""Tests for 散户拥挤曲线 (exploration #3) — the vote-snapshot summarizer."""
from __future__ import annotations

from nutmeg.v4.model.vote_crowding import MatchSeries, summarize


def _series(home, snaps):
    return MatchSeries("2026-08-10", home, "away", snaps)


def test_single_snapshot_has_no_trajectory():
    s = _series("A", [("2026-08-10T03:00:00", (50.0, 30.0, 20.0))])
    assert s.n == 1
    assert s.drift == (0.0, 0.0, 0.0)
    res = summarize([s])
    assert res.n_matches == 1
    assert res.n_series == 0
    assert res.mean_drift_pp == 0.0


def test_drift_and_bandwagon_direction():
    # crowd piles onto the (early-favourite) home leg: 50 → 62, away drains 30 → 18
    snaps = [
        ("2026-08-10T03:00:00", (50.0, 20.0, 30.0)),
        ("2026-08-10T09:00:00", (56.0, 20.0, 24.0)),
        ("2026-08-10T15:00:00", (62.0, 20.0, 18.0)),
    ]
    s = _series("A", snaps)
    assert s.fav_early == 0                      # home leads at first snapshot
    assert abs(s.fav_support_delta - 12.0) < 1e-9  # +12pp toward kickoff
    assert s.drift == (12.0, 0.0, 12.0)
    res = summarize([s])
    assert res.n_series == 1
    assert res.max_drift_pp == 12.0
    assert res.bandwagon_frac == 1.0             # early-fav support rose → bandwagon


def test_contrarian_drains_favourite():
    # early favourite (home 55) LOSES support toward kickoff → not bandwagon
    snaps = [
        ("2026-08-10T03:00:00", (55.0, 25.0, 20.0)),
        ("2026-08-10T15:00:00", (48.0, 25.0, 27.0)),
    ]
    res = summarize([_series("A", snaps)])
    assert res.n_series == 1
    assert res.bandwagon_frac == 0.0


def test_mixed_and_empty():
    assert summarize([]).n_series == 0
    bandwagon = _series("A", [("t1", (50.0, 20.0, 30.0)), ("t2", (60.0, 20.0, 20.0))])
    contrarian = _series("B", [("t1", (55.0, 25.0, 20.0)), ("t2", (45.0, 25.0, 30.0))])
    single = _series("C", [("t1", (40.0, 30.0, 30.0))])
    res = summarize([bandwagon, contrarian, single])
    assert res.n_matches == 3
    assert res.n_series == 2                      # single-snap match excluded
    assert res.bandwagon_frac == 0.5             # 1 of 2 series is bandwagon
