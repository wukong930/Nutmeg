"""竞彩可投注刷新过滤 — the default 🔄 spends API quota ONLY on 竞彩-bettable matches.

``_gather_rows(bettable_refresh_only=True)`` builds the bettable team-pair set from
the jingcai_sp HAD SP on file, then refreshes (spends Odds API credit / API-Football
/odds) ONLY for leagues/fixtures on that set. Non-竞彩 → served from cache. The 全刷
escape hatch (``bettable_only=False`` → ``bettable_pairs=None``) refreshes everything.

These cover the two pure helpers the filter is built on; the per-league / per-fixture
wiring in ``_gather_rows`` reads ``_fixture_is_bettable`` exactly as tested here.
"""
from __future__ import annotations

from nutmeg.v4.cli.ingest_odds import _fixture_is_bettable, _load_bettable_pairs
from nutmeg.v4.data.sources.odds_api import _norm_team
from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp


def _fx(home: str, away: str) -> dict:
    return {"teams": {"home": {"name": home}, "away": {"name": away}}}


def test_none_filter_passes_every_fixture():
    # None = filter OFF (全刷 / a plain non-refresh load) → nothing is skipped.
    assert _fixture_is_bettable(_fx("Arsenal", "Chelsea"), None) is True


def test_membership_is_home_away_ordered():
    pairs = {(_norm_team("Arsenal"), _norm_team("Chelsea"))}
    assert _fixture_is_bettable(_fx("Arsenal", "Chelsea"), pairs) is True
    assert _fixture_is_bettable(_fx("Everton", "Fulham"), pairs) is False
    # the reverse fixture is a DIFFERENT match — order must matter.
    assert _fixture_is_bettable(_fx("Chelsea", "Arsenal"), pairs) is False


def test_missing_or_malformed_teams_not_bettable():
    pairs = {("arsenal", "chelsea")}
    assert _fixture_is_bettable({}, pairs) is False
    assert _fixture_is_bettable({"teams": {}}, pairs) is False
    assert _fixture_is_bettable({"teams": {"home": {}, "away": {}}}, pairs) is False


def test_load_pairs_none_db_disables_filter():
    # No observation DB configured → None → the caller refreshes everything
    # (can't consult a bettable list that doesn't exist; don't break 🔄).
    assert _load_bettable_pairs(None) is None


def test_load_pairs_unreadable_db_is_empty_skip_all():
    # fetch_sp_lookup swallows a DB read error into {} (best-effort), so an
    # unreadable path yields an EMPTY set, not None → the 🔄 skips every league
    # (0 quota) and the empty-list hint / 全刷 hatch recover. This matches the
    # owner's 「空集→不刷+提示」 choice and never surprise-spends credits.
    assert _load_bettable_pairs("/nonexistent-dir-xyz-42/obs.db") == set()


def test_load_pairs_from_had_sp(tmp_path):
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(
        db, match_date="2026-08-15", home_team="Arsenal", away_team="Chelsea",
        jc_home=2.1, jc_draw=3.3, jc_away=3.4, market="had",
    )
    pairs = _load_bettable_pairs(db)
    assert pairs == {(_norm_team("Arsenal"), _norm_team("Chelsea"))}
    assert _fixture_is_bettable(_fx("Arsenal", "Chelsea"), pairs) is True
    assert _fixture_is_bettable(_fx("Everton", "Fulham"), pairs) is False


def test_load_pairs_no_had_rows_is_empty_set_not_none(tmp_path):
    # Table exists (an HHAD-only row created it) but no HAD SP → empty SET, not
    # None: a 🔄 with nothing 竞彩-bettable then skips every league (0 quota),
    # which is distinct from the fail-open None above.
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(
        db, match_date="2026-08-15", home_team="Arsenal", away_team="Chelsea",
        jc_home=1.9, jc_draw=3.4, jc_away=3.5, handicap_home=-1, market="hhad",
    )
    pairs = _load_bettable_pairs(db)   # queries market="had"
    assert pairs == set()
    # empty set → no fixture is bettable → _gather_rows refreshes nothing.
    assert _fixture_is_bettable(_fx("Arsenal", "Chelsea"), pairs) is False
