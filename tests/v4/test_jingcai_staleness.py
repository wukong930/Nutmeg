"""竞彩 staleness analysis — EV(Pinnacle-close × 竞彩SP) candidate + realized ROI."""
from __future__ import annotations

import datetime as dt

from nutmeg.v4.cli.jingcai_staleness import _devig3, _roi, analyze
from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp, settle_jingcai_sp
from nutmeg.v4.observation.odds_snapshots import record_row_snapshot


def _fx(home, away, hg, ag):
    return {
        "fixture": {"status": {"short": "FT"}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {"fulltime": {"home": hg, "away": ag}},
        "goals": {"home": hg, "away": ag},
    }


def _snapshot_pinn_close(db, *, fixture_id, h, d, a):
    record_row_snapshot(db, {
        "psc_home": h, "psc_draw": d, "psc_away": a,
        "date": "2026-06-20", "league": "WC",
        "home_team": "Mexico", "away_team": "South Africa",
        "ou_line": 2.5, "psc_over25": 1.9, "psc_under25": 1.9,
        "odds_update": "2026-06-20T18:00:00Z", "kickoff_utc": None,
    }, fixture_id=fixture_id, source="test")


def test_devig3():
    p = _devig3(2.0, 4.0, 4.0)
    assert p is not None and abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1]  # shorter price → higher prob


def _seed(db, jc_home):
    # jc_draw/jc_away 取值让三元组落在 booksum 带 [1.10,1.15] 内(捕获端闸 2026-07-19)
    record_jingcai_sp(
        db, match_date="2026-06-20", home_team="Mexico", away_team="South Africa",
        jc_home=jc_home, jc_draw=3.25, jc_away=3.35,
        psc_home=1.90, psc_draw=3.6, psc_away=4.4,  # Pinnacle AT CAPTURE
        fixture_id=12345, league="WC")
    settle_jingcai_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 2, 0)],
                      today=dt.date(2026, 6, 21))


def test_candidate_detected_and_realized(tmp_path):
    db = str(tmp_path / "obs.db")
    # 竞彩 prices home @1.95; Pinnacle CLOSE drifts to P_home≈0.585 (1.70/4.0/6.0)
    _seed(db, jc_home=1.95)
    _snapshot_pinn_close(db, fixture_id=12345, h=1.70, d=4.0, a=6.0)
    rep = analyze(db)
    assert rep["n_settled"] == 1 and rep["no_close"] == 0
    assert len(rep["candidates"]) == 1
    c = rep["candidates"][0]
    assert c["pick"] == "主胜" and c["won"] is True   # home won 2-0
    assert c["ev"] > 0.05 and abs(c["profit"] - 0.95) < 1e-9
    n, wr, roi = _roi(rep["candidates"])
    assert (n, wr) == (1, 1.0) and abs(roi - 0.95) < 1e-9


def test_no_candidate_when_no_edge(tmp_path):
    db = str(tmp_path / "obs.db")
    _seed(db, jc_home=1.90)              # close P_home≈0.485 → 0.485×1.90−1 ≈ −0.08
    _snapshot_pinn_close(db, fixture_id=12345, h=2.10, d=3.6, a=4.4)
    rep = analyze(db)
    assert rep["n_settled"] == 1 and rep["candidates"] == []


def test_no_pinnacle_close_is_skipped(tmp_path):
    db = str(tmp_path / "obs.db")
    _seed(db, jc_home=1.95)              # settled, but NO odds_snapshot recorded
    rep = analyze(db)
    assert rep["no_close"] == 1 and rep["candidates"] == []


def test_hhad_reverse_fit_candidate_and_realized(tmp_path):
    """让球: reverse-fit Pinnacle's cover P at the 竞彩 line from its CLOSE 1X2+O/U,
    +EV candidate, realized via (margin + handicap)."""
    from nutmeg.v4.model.market_handicap import devig_over, implied_handicap_lines
    db = str(tmp_path / "obs.db")
    _snapshot_pinn_close(db, fixture_id=12345, h=1.50, d=4.0, a=6.0)   # strong home + O/U 1.9/1.9
    # the 让胜 cover P at line −1, computed the SAME way the analysis does
    fair = _devig3(1.50, 4.0, 6.0)
    p_letwin = implied_handicap_lines(
        fair[0], fair[1], fair[2], devig_over(1.9, 1.9), ou_line=2.5, lines=(-1,))[0][1]
    jc_letwin = round(1.12 / p_letwin, 2)            # ⇒ EV ≈ +12% on 让胜
    # 让平/让负 filler 动态取值:booksum ≈ 1.13(带内),不再用会触发捕获闸的 2.0/2.0
    filler = round(2.0 / (1.13 - 1.0 / jc_letwin), 2)
    record_jingcai_sp(
        db, match_date="2026-06-20", home_team="Mexico", away_team="South Africa",
        jc_home=jc_letwin, jc_draw=filler, jc_away=filler,
        market="hhad", handicap_home=-1, fixture_id=12345)
    # home wins 3-0 → margin 3, +(−1) = 2 > 0 → 让胜 covered (idx 0)
    settle_jingcai_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 3, 0)],
                      today=dt.date(2026, 6, 21))
    rep = analyze(db)
    hh = [c for c in rep["candidates"] if c["market"] == "hhad"]
    assert hh, "no 让球 candidate produced"
    win = next(c for c in hh if c["pick"] == "让胜")
    assert win["ev"] > 0.05 and win["won"] is True
    assert abs(win["profit"] - (jc_letwin - 1.0)) < 1e-9


def test_hhad_realized_loss_when_not_covered(tmp_path):
    """让胜 at −1 but home only wins 1-0 (margin 1, +(−1)=0 → 让平) → 让胜 loses."""
    db = str(tmp_path / "obs.db")
    _snapshot_pinn_close(db, fixture_id=99, h=1.50, d=4.0, a=6.0)
    record_jingcai_sp(
        db, match_date="2026-06-20", home_team="Mexico", away_team="South Africa",
        jc_home=4.2, jc_draw=2.24, jc_away=2.24,   # jc_home huge → 让胜 +EV(booksum 1.131)
        market="hhad", handicap_home=-1, fixture_id=99)
    settle_jingcai_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 1, 0)],
                      today=dt.date(2026, 6, 21))
    rep = analyze(db)
    win = next(c for c in rep["candidates"] if c["market"] == "hhad" and c["pick"] == "让胜")
    assert win["won"] is False and win["profit"] == -1.0   # push on the line → 让胜 lost


def test_pinn_close_national_team_alias_fallback(tmp_path):
    """When the exact (date, home, away) join misses, _pinn_close resolves national
    teams via the elo-code alias: 竞彩 'Czech Republic' joins Pinnacle's 'Czechia'
    close. A club name (no elo code) must NOT alias-guess (stays autumn-gated)."""
    import sqlite3

    from nutmeg.v4.cli.jingcai_staleness import _pinn_close
    db = str(tmp_path / "obs.db")
    record_row_snapshot(db, {
        "psc_home": 1.85, "psc_draw": 3.5, "psc_away": 4.6,
        "date": "2026-06-25", "league": "WC",
        "home_team": "Czechia", "away_team": "Mexico",          # Pinnacle spelling
        "ou_line": 2.5, "psc_over25": 1.9, "psc_under25": 1.9,
        "odds_update": "2026-06-25T18:00:00Z", "kickoff_utc": None,
    }, fixture_id=None, source="test")
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        got = _pinn_close(c, {"fixture_id": None, "match_date": "2026-06-25",
                              "home_team": "Czech Republic", "away_team": "Mexico"})
        assert got is not None and abs(got[0] - 1.85) < 1e-9   # alias resolved → close found
        # not a national team → no elo code → must not guess a join
        assert _pinn_close(c, {"fixture_id": None, "match_date": "2026-06-25",
                               "home_team": "Some Club", "away_team": "Mexico"}) is None


# ── 俱乐部别名兜底(2026-07-23)────────────────────────────────────────────
# 病史:owner 实报「迈阿密国际 vs 芝加哥」不在可投注列表。根因**不在竞彩词典**,
# 而在我们自己库里同一支队有两种拼写:竞彩侧解析成 `Inter Miami`,那场的 Pinnacle
# 行写的是 `Inter Miami CF`(closing 走 OA、cup_market 走 AF 镜像,规范不同),
# 精确 (date, home, away) join 直接落空 → CLV 台账报「无收盘线」。
#
# 两层一起才修好,缺一不可:
#   ① _CLUB_TOKENS 原是北欧口径,没有 `cf`/`sc` → core 折不到一起
#   ② _pinn_close 原本只有 国家队 别名兜底(注释写着俱乐部「autumn-gated」)

class TestClubCoreCloseFallback:
    def test_club_tokens_fold_the_americas_suffixes(self):
        """加 cf/sc 前实测过误并(374 个队名跑全表):+cf 只多 1 组=迈阿密;
        +cf,sc 多 4 组且**全是同一支队**;ac/cd/ud 不产生新折叠 = 投机,没加。
        改这张表请重跑那个测量 —— core 变宽会同时影响实盘 overlay 的二级键。"""
        from nutmeg.v4.data.sources.odds_api import _club_core
        assert _club_core("Inter Miami CF") == _club_core("Inter Miami")
        assert _club_core("Columbus Crew SC") == _club_core("Columbus Crew")
        # 原有北欧口径不能被破坏
        assert _club_core("IK Sirius") == _club_core("Sirius")

    # ⚠️ 这些用例的**前提是「库里存在一个 sink 不会归一掉的拼法分裂」**,而这个前提
    # 被推翻过两次:
    #   2026-08-01 原用「Inter Miami / Inter Miami CF」,当天分裂修进了 ingest 层
    #     ⇒ 写进库时就被归一、精确 join 直接命中、**根本走不到 club-core 兜底**。
    #     歧义那条当场变红(好),正例那条**照样绿** —— 它测的东西没了却不吭声。
    #   2026-08-04 换用的「别名表故意没收的真实撞车对」(瑞超)也补进别名表了,
    #     `UNRESOLVED_SPLITS` 归零 ⇒ **已经没有「仍未收敛的真实名字」可换**。
    #
    # 所以这次不再去找一对「碰巧还没被收」的真名 —— 那等于把前提押在别人不动手上。
    # 改成:**合成联赛码 + 真实拼法**。`_LEAGUE` 既不是 `soccer_*` 也不是 V4 码,
    # `canonical_team` 查 (联赛, 队名) 必然落空 ⇒ sink 对它永远是 no-op,
    # 别名表怎么长都不会把这两行折叠掉。名字仍用真的,因为要测的是 `_club_core`
    # 对真实后缀/大小写/句点的折叠。
    #
    # 而且不靠注释保证:下面 test_the_fixture_really_lands_as_two_rows 直接**读回
    # 库里的内容**断言,前提坏了会先红在那条上,而不是让结论悄悄反转。
    _LEAGUE = "TEST_SPELLING_SPLIT"
    _AMBIG = (("Servette FC", "FC St Gallen"), ("Servette", "FC ST. Gallen"))

    def _write(self, db, home, away, ph):
        return record_row_snapshot(db, {
            "date": "2026-07-22", "league": self._LEAGUE,
            "home_team": home, "away_team": away,
            "psc_home": ph, "psc_draw": 3.9, "psc_away": 4.2,
            "ou_line": 3.5, "psc_over25": 1.9, "psc_under25": 1.9,
            "kickoff_utc": "2026-07-22T23:30:00+00:00",
        }, source="closing", captured_at="2026-07-22T23:00:00+00:00")

    def test_the_fixture_really_lands_as_two_rows(self, tmp_path):
        """前提断言(行为版,不是字符串版):两种拼法进库后必须**仍是两对**。

        歧义闸的判据是 `len({(home, away)}) != 1`;要是 sink 把两行归一成同一对,
        歧义就不存在了、`test_ambiguous_core_never_guesses` 会静默变成在测正例。
        钉的是**库里真实落了什么**,所以别名表/sink 怎么改都瞒不过去。
        """
        import sqlite3
        db = tmp_path / "o.db"
        for (home, away), ph in zip(self._AMBIG, (1.8, 2.4), strict=True):
            self._write(db, home, away, ph)
        pairs = set(sqlite3.connect(db).execute(
            "SELECT home_team, away_team FROM odds_snapshots").fetchall())
        assert pairs == set(self._AMBIG), (
            f"落库的不是两对原样拼法而是 {pairs} ⇒ 本类的歧义用例已失去牙齿。"
            "多半是 _LEAGUE 撞上了真实联赛码、被别名表归一了,换一个合成码。")

    def test_close_found_across_the_spelling_split(self, tmp_path):
        """竞彩 `Servette` ↔ Pinnacle `Servette FC` —— 精确 join 落空后,
        club-core 兜底必须把这条收盘线找回来。

        ⚠️ 顺带断言精确 join **确实**落空:否则这条根本没走到兜底,
        测的是 `_pinn_close` 的第一段而不是它要测的第三段。"""
        import sqlite3

        from nutmeg.v4.cli.jingcai_staleness import _pinn_close
        db = tmp_path / "o.db"
        self._write(db, "Servette FC", "FC St Gallen", 1.8)
        q = {"match_date": "2026-07-22", "home_team": "Servette",
             "away_team": "FC ST. Gallen"}
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            assert not conn.execute(
                "SELECT 1 FROM odds_snapshots WHERE match_date=? AND home_team=? "
                "AND away_team=?", (q["match_date"], q["home_team"], q["away_team"])
            ).fetchone(), "精确 join 命中了 ⇒ 这条没在测 club-core 兜底"
            got = _pinn_close(conn, q)
        assert got is not None, "club-core 兜底没接上"
        assert got[0] == 1.8

    def test_ambiguous_core_never_guesses(self, tmp_path):
        """同日两场不同赛事共享同一 core 对 → 放弃,不猜。
        错 join 是静默污染,比缺 join 更坏(缺了至少哨兵会响)。

        查询键**两边都不精确命中**任何一行,才逼得走 core 兜底并撞上歧义闸。"""
        import sqlite3

        from nutmeg.v4.cli.jingcai_staleness import _pinn_close
        db = tmp_path / "o.db"
        for (home, away), ph in zip(self._AMBIG, (1.8, 2.4), strict=True):
            self._write(db, home, away, ph)
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            got = _pinn_close(conn, {"match_date": "2026-07-22",
                                     "home_team": "Servette",
                                     "away_team": "FC St Gallen"})
        assert got is None, "歧义时必须放弃,绝不猜"

    def test_in_play_row_still_excluded(self, tmp_path):
        """体检 B2 的开球后守卫在兜底层同样生效 —— 别从别名这条路把 LIVE 线放进来。"""
        import sqlite3

        from nutmeg.v4.cli.jingcai_staleness import _pinn_close
        db = tmp_path / "o.db"
        record_row_snapshot(db, {
            "date": "2026-07-22", "league": "USA_MLS",
            "home_team": "Inter Miami CF", "away_team": "Chicago Fire",
            "psc_home": 1.06, "psc_draw": 15.0, "psc_away": 53.96,   # 典型滚球退化线
            "ou_line": 3.5, "psc_over25": 1.9, "psc_under25": 1.9,
            "kickoff_utc": "2026-07-22T23:30:00+00:00",
        }, source="closing", captured_at="2026-07-23T00:10:00+00:00")  # 开球之后
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            got = _pinn_close(conn, {"match_date": "2026-07-22",
                                     "home_team": "Inter Miami",
                                     "away_team": "Chicago Fire"})
        assert got is None, "开球后的 LIVE 线不许经别名兜底混进收盘价"
