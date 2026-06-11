"""名字错配哨兵 — detect AF↔Odds API team-name mismatches the overlay would miss."""
from __future__ import annotations

import datetime as dt

from nutmeg.v4.cli.name_sentinel import format_report, scan


def _scan(fixtures, lk, **kw):
    day = dt.date(2026, 6, 12)
    return scan(
        days=1, today=day, leagues=["L"], sport_keys={"L": "k"},
        resolve_lid=lambda c: 1,
        fetch_fixtures=lambda d: fixtures.get(d, []),
        fetch_lookup=lambda sk: lk,
        **kw,
    )


def test_flags_name_mismatch_with_suggestion():
    """OA has the fixture under 'Newteam FC'; AF calls it 'Newteam' → overlay miss
    that IS fixable with an alias, so it's reported with the OA suggestion."""
    day = dt.date(2026, 6, 12)
    lk = {("newteamfc", "rivalfc", "2026-06-12"):
          {"home_team": "Newteam FC", "away_team": "Rival FC"}}
    fixtures = {day: [{"league": {"id": 1},
                       "teams": {"home": {"name": "Newteam"}, "away": {"name": "Rival FC"}}}]}
    m, nc, sc = _scan(fixtures, lk)
    assert sc == 1 and nc == 0 and len(m) == 1
    assert m[0]["af_team"] == "Newteam" and m[0]["oa_suggestion"] == "Newteam FC"


def test_exact_match_not_flagged():
    day = dt.date(2026, 6, 12)
    lk = {("alpha", "beta", "2026-06-12"): {"home_team": "Alpha", "away_team": "Beta"}}
    fixtures = {day: [{"league": {"id": 1},
                       "teams": {"home": {"name": "Alpha"}, "away": {"name": "Beta"}}}]}
    assert _scan(fixtures, lk) == ([], 0, 1)


def test_not_covered_is_not_a_name_bug():
    """An AF fixture absent from the Odds API (no team overlaps) is 'not covered',
    not a name mismatch — it must NOT pollute the actionable alias list."""
    day = dt.date(2026, 6, 12)
    lk = {("alpha", "beta", "2026-06-12"): {"home_team": "Alpha", "away_team": "Beta"}}
    fixtures = {day: [{"league": {"id": 1},
                       "teams": {"home": {"name": "Gamma"}, "away": {"name": "Delta"}}}]}
    m, nc, sc = _scan(fixtures, lk)
    assert m == [] and nc == 1


def test_fail_soft_on_lookup_error():
    def boom(sk):
        raise RuntimeError("odds api down")
    out = scan(days=1, today=dt.date(2026, 6, 12), leagues=["L"], sport_keys={"L": "k"},
               resolve_lid=lambda c: 1, fetch_fixtures=lambda d: [], fetch_lookup=boom)
    assert out == ([], 0, 0)            # league skipped, never raises


def test_report_formats():
    assert "无名字错配" in format_report([], 0, 3, "t")
    r = format_report(
        [{"league": "X", "fixture": "A vs B", "date": "2026-06-12",
          "af_team": "A", "oa_suggestion": "A FC"}], 1, 2, "t")
    assert "A FC" in r and "_NORM_ALIAS" in r
