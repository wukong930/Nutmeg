"""竞彩可投注刷新过滤 — the default 🔄 spends API quota ONLY on 竞彩-bettable matches.

``_gather_rows(bettable_refresh_only=True)`` builds the bettable team-pair set from
the jingcai_sp HAD SP on file, then refreshes (spends Odds API credit / API-Football
/odds) ONLY for leagues/fixtures on that set. Non-竞彩 → served from cache. The 全刷
escape hatch (``bettable_only=False`` → ``bettable_pairs=None``) refreshes everything.

These cover the two pure helpers the filter is built on; the per-league / per-fixture
wiring in ``_gather_rows`` reads ``_fixture_is_bettable`` exactly as tested here.
"""
from __future__ import annotations

from nutmeg.v4.cli.ingest_odds import (
    _fixture_is_bettable,
    _load_bettable_pairs,
    _oa_refresh_decision,
)
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


def test_oa_refresh_fires_on_first_bettable_day_not_day0():
    # 2026-07-09 回归复现(芬超 VPS-SJK):可投注场在「明天」(d=1),今天(d=0)
    # 该联赛无可投注 → 旧的 `d == 0` 门永远不刷。新逻辑:d=0 判 False(该日无
    # 可投注),d=1 判 True(首次出现可投注)→ 修复。
    pairs = {(_norm_team("VPS"), _norm_team("SJK"))}
    refreshed: set[str] = set()
    d0_fixtures = []                                   # 今天芬超无赛程
    d1_fixtures = [_fx("VPS", "SJK")]                  # 明天 VPS-SJK 可投注
    assert _oa_refresh_decision(True, pairs, d0_fixtures, "soccer_fin", refreshed) is False
    assert _oa_refresh_decision(True, pairs, d1_fixtures, "soccer_fin", refreshed) is True
    assert refreshed == {"soccer_fin"}


def test_oa_refresh_dedups_one_pull_per_sport():
    # 同一 sport 多天都有可投注 → 只第一次强刷(Wave1 经济性保留)。
    pairs = {(_norm_team("France"), _norm_team("Morocco")),
             (_norm_team("Spain"), _norm_team("Belgium"))}
    refreshed: set[str] = set()
    d0 = [_fx("France", "Morocco")]
    d1 = [_fx("Spain", "Belgium")]
    assert _oa_refresh_decision(True, pairs, d0, "soccer_wc", refreshed) is True
    assert _oa_refresh_decision(True, pairs, d1, "soccer_wc", refreshed) is False


def test_oa_refresh_filter_off_still_one_pull():
    # 全刷(bettable_pairs=None):d=0 刷、d≥1 走去重集 → 与旧 d==0 行为等价。
    refreshed: set[str] = set()
    assert _oa_refresh_decision(True, None, [], "soccer_epl", refreshed) is True
    assert _oa_refresh_decision(True, None, [_fx("A", "B")], "soccer_epl", refreshed) is False
    assert _oa_refresh_decision(False, None, [], "soccer_x", set()) is False


def test_load_pairs_counts_handicap_only_as_bettable(tmp_path):
    """让球-only 场次 = 可投注(2026-07-17 修;本测试原来断言的正是那个 bug)。

    竞彩 SP 有下限(实测 1.13):主队 fair P 高到胜平负 SP 跌破它时,竞彩**只上
    让球盘** —— 那场照样能买。原口径「只查 market='had'」把这类场判成不可投注 →
    🔄 跳过它们(线不刷新)+ 前端掉进参考区。实测 188 场里 19 场(10.1%)如此,
    且全是一边倒的大场(15/19 是世界杯)。owner 实报:挪超 Bodo/Glimt(Pinnacle
    1.14 → 胜平负 SP 卖不了)vs Fredrikstad,竞彩只上让球 -2。
    """
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(
        db, match_date="2026-08-15", home_team="Arsenal", away_team="Chelsea",
        jc_home=1.9, jc_draw=3.4, jc_away=3.5, handicap_home=-1, market="hhad",
    )
    pairs = _load_bettable_pairs(db)
    assert pairs == {(_norm_team("Arsenal"), _norm_team("Chelsea"))}
    assert _fixture_is_bettable(_fx("Arsenal", "Chelsea"), pairs) is True


def test_load_pairs_empty_db_is_empty_set_not_none(tmp_path):
    # 表存在但两个 market 都没行 → empty SET, not None:🔄 跳过每个联赛(0 配额),
    # 与上面 fail-open 的 None 严格区分(「空集→不刷+提示」是 owner 定的)。
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(   # 建表用,随后清空
        db, match_date="2026-08-15", home_team="Arsenal", away_team="Chelsea",
        jc_home=1.9, jc_draw=3.4, jc_away=3.5, market="had",
    )
    import sqlite3
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM jingcai_sp")
    pairs = _load_bettable_pairs(db)
    assert pairs == set()
    assert _fixture_is_bettable(_fx("Arsenal", "Chelsea"), pairs) is False


def test_load_pairs_unions_both_markets(tmp_path):
    # 前端 _isJcBettable(dashboard.html)= had || hhad;后端必须同口径,否则
    # 「面板显示可投注、🔄 却跳过它」= 卡片挂着一条永不刷新的陈旧线。
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(
        db, match_date="2026-08-15", home_team="Arsenal", away_team="Chelsea",
        jc_home=2.1, jc_draw=3.3, jc_away=3.4, market="had",
    )
    record_jingcai_sp(
        db, match_date="2026-08-15", home_team="Spain", away_team="Saudi Arabia",
        jc_home=1.9, jc_draw=3.4, jc_away=3.5, handicap_home=-2, market="hhad",
    )
    pairs = _load_bettable_pairs(db)
    assert pairs == {(_norm_team("Arsenal"), _norm_team("Chelsea")),
                     (_norm_team("Spain"), _norm_team("Saudi Arabia"))}
