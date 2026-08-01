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

    # ⚠️ 2026-08-01 —— 下面两条原本用「Inter Miami / Inter Miami CF」构造分裂。
    # 那天把分裂修到了 ingest 层(`odds_source_aliases`),`Inter Miami CF` 进了
    # 别名表 ⇒ 写进库时就被归一,精确 join 直接命中,**根本走不到 club-core 兜底**。
    # 歧义那条当场变红(好),但正例那条**照样绿** —— 它测的东西没了,而它不吭声。
    # 这才是危险的一半:红测试会喊,失去牙齿的绿测试不会。
    #
    # 所以改用**别名表故意没收的**真实撞车对(瑞超,见 UNRESOLVED_SPLITS),
    # 并在下面用 test_fixture_names_must_stay_unaliased 钉住这个前提:
    # 将来谁把它们补进别名表,那条会先红,而不是这两条悄悄变哑。
    _AMBIG = (("Servette FC", "FC St Gallen"), ("Servette", "FC ST. Gallen"))

    def _write(self, db, home, away, ph):
        return record_row_snapshot(db, {
            "date": "2026-07-22", "league": "SUI_SUPER_LEAGUE",
            "home_team": home, "away_team": away,
            "psc_home": ph, "psc_draw": 3.9, "psc_away": 4.2,
            "ou_line": 3.5, "psc_over25": 1.9, "psc_under25": 1.9,
            "kickoff_utc": "2026-07-22T23:30:00+00:00",
        }, source="closing", captured_at="2026-07-22T23:00:00+00:00")

    def test_fixture_names_must_stay_unaliased(self):
        """下面两条测试的前提:这些拼法**没有**被 ingest 层归一掉。

        一旦有了共现证据把它们补进 `ODDS_SOURCE_ALIASES`,精确 join 会命中,
        club-core 兜底就测不到了 —— 那时请换一对仍未收敛的名字,别删断言。
        """
        from nutmeg.v4.data.odds_source_aliases import canonical_team
        for h, a in self._AMBIG:
            for n in (h, a):
                assert canonical_team("SUI_SUPER_LEAGUE", n) == n, (
                    f"{n!r} 已进别名表 ⇒ 本类的 club-core 用例已失去牙齿,换名字")

    def test_close_found_across_the_spelling_split(self, tmp_path):
        """竞彩 `Servette` ↔ Pinnacle `Servette FC` —— 精确 join 落空后,
        club-core 兜底必须把这条收盘线找回来。"""
        import sqlite3

        from nutmeg.v4.cli.jingcai_staleness import _pinn_close
        db = tmp_path / "o.db"
        self._write(db, "Servette FC", "FC St Gallen", 1.8)
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            got = _pinn_close(conn, {"match_date": "2026-07-22",
                                     "home_team": "Servette",
                                     "away_team": "FC ST. Gallen"})
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
