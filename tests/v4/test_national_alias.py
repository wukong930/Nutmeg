"""体检 D1 (2026-07-01) — national-team synonym canonicalizer + its effect on the
settle join. API-Football returns 'Czechia'; 竞彩 stored 'Czech Republic', so the
bare-name settle join never matched → 44 rows stayed unsettled with results in-hand.
"""
from __future__ import annotations

import datetime as dt

from nutmeg.utils.team_canonical import normalize_name
from nutmeg.v4.data.national_alias import national_match_key
from nutmeg.v4.observation.jingcai_sp import (
    fetch_jingcai_sp,
    record_jingcai_sp,
    settle_jingcai_sp,
)


def _fx(home, away, hg, ag):
    return {
        "fixture": {"status": {"short": "FT"}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {"fulltime": {"home": hg, "away": ag}},
        "goals": {"home": hg, "away": ag},
    }


class TestNationalMatchKey:
    def test_czech_variants_collapse_to_one_key(self):
        assert national_match_key("Czech Republic") == national_match_key("Czechia")

    def test_identity_for_aligned_names(self):
        # non-national / already-aligned names pass through as plain normalize_name
        assert national_match_key("Germany") == normalize_name("Germany")
        assert national_match_key("Real Madrid") == normalize_name("Real Madrid")

    def test_none_and_empty_safe(self):
        assert national_match_key(None) == ""
        assert national_match_key("") == ""


def test_settle_matches_across_czech_synonym(tmp_path):
    """竞彩 'Czech Republic' ↔ API-Football 'Czechia' now settles."""
    db = tmp_path / "obs.db"
    record_jingcai_sp(db, match_date="2026-06-18", home_team="Czech Republic",
                      away_team="South Africa", jc_home=2.1, jc_draw=3.2, jc_away=3.6)

    n = settle_jingcai_sp(
        db, fetch_fixtures=lambda d: [_fx("Czechia", "South Africa", 1, 1)],
        today=dt.date(2026, 6, 26))
    assert n == 1
    r = fetch_jingcai_sp(db, settled=True)[0]
    assert (r["home_goals"], r["away_goals"], r["ft_outcome"]) == (1, 1, 1)  # draw


def test_settle_robust_to_either_api_spelling(tmp_path):
    # both sides route through the key, so it settles regardless of which spelling
    # API-Football returns on a given day (it has used BOTH for Czechia).
    db = tmp_path / "obs.db"
    record_jingcai_sp(db, match_date="2026-06-25", home_team="Czechia",
                      away_team="Mexico", jc_home=3.4, jc_draw=3.3, jc_away=2.1)
    n = settle_jingcai_sp(
        db, fetch_fixtures=lambda d: [_fx("Czech Republic", "Mexico", 0, 3)],
        today=dt.date(2026, 6, 26))
    assert n == 1


def test_non_synonym_mismatch_still_does_not_settle(tmp_path):
    # guard against over-aliasing: a genuinely different team must NOT match
    db = tmp_path / "obs.db"
    record_jingcai_sp(db, match_date="2026-06-18", home_team="Brazil",
                      away_team="Japan", jc_home=1.5, jc_draw=3.7, jc_away=5.0)
    n = settle_jingcai_sp(
        db, fetch_fixtures=lambda d: [_fx("Czechia", "South Africa", 1, 1)],
        today=dt.date(2026, 6, 26))
    assert n == 0
