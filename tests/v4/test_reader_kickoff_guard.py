"""体检 B1/B2 (2026-07-01) — the odds_snapshots readers must skip an IN-PLAY
snapshot (captured at/after kickoff), so a leading team's live line
(1.06/…/53.96) never becomes the pinned close / CLV anchor. Producer guards
exist too; this is the durable reader defense.

Readers covered here:
  * backfill_vote_pinnacle          (jingcai_vote co-captured close)
  * jingcai_staleness._pinn_close   (clv / staleness close anchor)
  * line_origin._pinnacle_open_close (2026-09-01) — its close was gated but the
    BAND (lo/hi) was not, so an in-play line could still widen the range that
    staleness gets credited with. A wider band swallows more of the 竞彩 gap,
    driving the irreducible-domestic residual toward a false zero — a silent
    wrong ANSWER, not a crash. Gate the band and the close together or they drift.
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.odds_snapshots import ensure_odds_snapshots

_KO = "2026-08-01T18:00:00+00:00"


def _snap(conn, *, home, away, psc_home, psc_away, captured_at, kickoff_utc=_KO,
          psc_draw=5.0):
    conn.execute(
        "INSERT INTO odds_snapshots (captured_at, source, league, match_date, "
        "home_team, away_team, kickoff_utc, psc_home, psc_draw, psc_away) "
        "VALUES (?, 'closing', 'WC', '2026-08-01', ?, ?, ?, ?, ?, ?)",
        (captured_at, home, away, kickoff_utc, psc_home, psc_draw, psc_away))


def _seed_both(conn, home, away):
    # healthy PRE-KO close (older) + IN-PLAY line (newer, degenerate)
    _snap(conn, home=home, away=away, psc_home=2.2, psc_away=4.5,
          captured_at="2026-08-01T17:30:00+00:00")
    _snap(conn, home=home, away=away, psc_home=1.06, psc_away=53.96,
          captured_at="2026-08-01T19:00:00+00:00")   # captured AFTER kickoff


def test_backfill_skips_in_play_snapshot(tmp_path):
    from nutmeg.v4.observation.jingcai_vote import (
        backfill_vote_pinnacle,
        ensure_jingcai_vote_table,
    )
    db = tmp_path / "obs.db"
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        ensure_jingcai_vote_table(conn)
        _seed_both(conn, "Mexico", "Ecuador")
        conn.execute(
            "INSERT INTO jingcai_vote (captured_at, source, match_date, home_zh, "
            "away_zh, pool_code, home_team, away_team) VALUES "
            "('2026-08-01T00:00:00+00:00','sporttery','2026-08-01','墨西哥','厄瓜多尔',"
            "'HAD','Mexico','Ecuador')")
        conn.commit()

    backfill_vote_pinnacle(db)
    with sqlite3.connect(db) as conn:
        psc = conn.execute(
            "SELECT psc_home FROM jingcai_vote WHERE home_team='Mexico'").fetchone()[0]
    assert psc == 2.2   # the pre-KO close, NOT the 1.06 in-play line


def test_pinn_close_skips_in_play(tmp_path):
    from nutmeg.v4.cli.jingcai_staleness import _pinn_close
    db = tmp_path / "obs.db"
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        _seed_both(conn, "A", "B")
        conn.commit()
        close = _pinn_close(
            conn, {"match_date": "2026-08-01", "home_team": "A", "away_team": "B"})
    assert close is not None
    assert close[0] == 2.2   # pre-KO close, not the in-play 1.06


def test_null_kickoff_still_pinnable(tmp_path):
    # historical rows (kickoff_utc NULL, pre-2026-07-01) can't be judged → kept
    from nutmeg.v4.cli.jingcai_staleness import _pinn_close
    db = tmp_path / "obs.db"
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        _snap(conn, home="C", away="D", psc_home=1.9, psc_away=4.0,
              captured_at="2026-05-01T12:00:00+00:00", kickoff_utc=None)
        conn.commit()
        close = _pinn_close(
            conn, {"match_date": "2026-08-01", "home_team": "C", "away_team": "D"})
    assert close is not None and close[0] == 1.9


def _line_origin_band(tmp_path, rows):
    """Seed odds_snapshots with `rows` and return line_origin's per-key tuple."""
    from nutmeg.v4.cli.line_origin import _pinnacle_open_close
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "obs.db"
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        for r in rows:
            _snap(conn, home="Alpha FC", away="Beta FC", **r)
        conn.commit()
        out = _pinnacle_open_close(conn, "2000-01-01")
    assert len(out) == 1, out          # population is non-trivial: the match IS joined
    return next(iter(out.values()))    # (open_p, close_p, band_lo, band_hi, home, away)


# the in-play line: leader at 1.06, the loser out at 53.96 — devigs to roughly
# (0.93, 0.06, 0.01), i.e. FAR outside any pre-match band this fixture can produce.
_IN_PLAY = dict(psc_home=1.06, psc_draw=15.00, psc_away=53.96,
                captured_at="2026-08-01T19:00:00+00:00")
_PRE_OPEN = dict(psc_home=2.10, psc_draw=3.40, psc_away=3.60,
                 captured_at="2026-08-01T10:00:00+00:00")
_PRE_CLOSE = dict(psc_home=1.95, psc_draw=3.50, psc_away=4.00,
                  captured_at="2026-08-01T17:30:00+00:00")


def test_line_origin_band_excludes_in_play_snapshot(tmp_path):
    """The band must span ONLY the pre-kickoff snapshots. Ungated, the in-play
    line pushes band_hi[主] 0.50→0.93 and band_lo[客] 0.23→0.01, handing staleness
    a range the pre-match market never offered."""
    op, cl, lo, hi, _, _ = _line_origin_band(
        tmp_path, [_PRE_OPEN, _PRE_CLOSE, _IN_PLAY])

    # ① THE claim: the band stays inside the pre-kickoff envelope. These are the
    #    assertions the blank round must go red on (in-play values ≈0.93/0.06/0.01).
    assert hi[0] < 0.55, f"in-play line widened the 主 band ceiling: {hi[0]:.4f}"
    assert lo[1] > 0.20, f"in-play line dropped the 平 band floor: {lo[1]:.4f}"
    assert lo[2] > 0.20, f"in-play line dropped the 客 band floor: {lo[2]:.4f}"

    # ② structural: only two pre-KO snapshots exist, so the band IS their min/max.
    for i in range(3):
        assert abs(lo[i] - min(op[i], cl[i])) < 1e-12
        assert abs(hi[i] - max(op[i], cl[i])) < 1e-12

    # ③ the pre-kickoff range itself is UNCHANGED — open/close were already gated
    #    correctly, so the fix must not have moved them.
    ref_op, ref_cl, ref_lo, ref_hi, _, _ = _line_origin_band(
        tmp_path / "ctl", [_PRE_OPEN, _PRE_CLOSE])
    assert op == ref_op and cl == ref_cl
    assert lo == ref_lo and hi == ref_hi


def test_line_origin_in_play_line_is_genuinely_degenerate():
    """Anti-vacuity: proves the fixture has POWER. Independent of the gate (it
    de-vigs the raw prices, not the band), so it stays GREEN on a revert and
    cannot steal the blank round's red from the band assertions above."""
    from nutmeg.v4.model.devig import devig_1x2
    p = devig_1x2(_IN_PLAY["psc_home"], _IN_PLAY["psc_draw"], _IN_PLAY["psc_away"])
    assert p is not None
    assert p[0] > 0.85 and p[2] < 0.05   # would blow the band open if admitted
    for pre in (_PRE_OPEN, _PRE_CLOSE):  # ...and the pre-KO lines are ordinary
        q = devig_1x2(pre["psc_home"], pre["psc_draw"], pre["psc_away"])
        assert q is not None and 0.40 < q[0] < 0.55 and 0.20 < q[2] < 0.30


def test_line_origin_band_keeps_null_kickoff_rows(tmp_path):
    """Over-gating guard: historical rows (kickoff_utc NULL) can't be judged, so
    they must still seed and widen the band — the band is built lazily on the
    first admitted row, and a NULL-kickoff-only match must not come back empty."""
    op, cl, lo, hi, _, _ = _line_origin_band(tmp_path, [
        dict(_PRE_OPEN, kickoff_utc=None), dict(_PRE_CLOSE, kickoff_utc=None)])
    assert lo is not None and hi is not None
    for i in range(3):
        assert abs(lo[i] - min(op[i], cl[i])) < 1e-12
        assert abs(hi[i] - max(op[i], cl[i])) < 1e-12
    assert op != cl   # both rows were admitted, so movement is observable


# ── 闸的**边界** + 充足性判据(2026-09-02 补:空包弹发现这两发变异全绿)──────

#: 恰好落在开球点那一秒的快照 —— 已经开赛,不是赛前价。
_AT_KICKOFF = dict(psc_home=1.06, psc_draw=15.00, psc_away=53.96,
                   captured_at=_KO)


def test_a_snapshot_exactly_at_kickoff_is_in_play_not_pre_match(tmp_path):
    """🚨 `cap == ko` 必须**算滚球**,不是赛前。

    空包弹实测:把判据 `cap < ko` 放宽一档改成 `cap <= ko`,**全套照绿** ——
    也就是说「恰好等于开球点」这个边界从来没被测过。而它一放行,那条
    1.06/15.00/53.96 的畸形线就会**同时**成为 close 并把 band 撑到 P≈0.93,
    于是任何竞彩报价都落在区间内 ⇒ 「不可约本土」残差被压成假零 ——
    这正是本模块存在的全部理由所要防的那件事。

    ⚠️ 真库里 `kickoff_utc` 有两种字面(`…Z` 与 `…+00:00`),而这条比较是
    **字符串序**;本夹具用的 `_KO` 与写入格式一致,所以测的是判据本身。
    """
    open_p, close_p, lo, hi, _h, _a = _line_origin_band(
        tmp_path / "at_ko", [_PRE_OPEN, _PRE_CLOSE, _AT_KICKOFF])
    # close 必须是赛前那条(1.95 侧),不是畸形线
    assert close_p[0] < 0.6, f"开球点那条被当成了收盘:{close_p}"
    # band 上界不许被畸形线撑开
    assert hi[0] < 0.7, f"band 被开球点那条撑宽了:lo={lo} hi={hi}"
    assert open_p[0] > 0.4, open_p


def test_in_play_rows_do_not_prop_up_the_two_capture_requirement(tmp_path):
    """🚨 充足性判据的**分母**里不许混进喂不进计算的行。

    `_pinnacle_open_close` 要求「≥2 个不同快照」。原来 `caps.add(cap)` 在赛前闸
    **之前**,于是 1 个赛前 + N 个滚球 ⇒ caps=N+1 过关,而 band/open/close 全部
    来自那 1 个赛前快照 ⇒ open==close、band 塌成一个点:**一个退化样本冒充
    充足样本**,而下游拿它去算「陈旧 vs 本土」的分解。

    ⭐ 实测(2026-08 起 1,419 场):真库里靠滚球行凑够 ≥2 的 **0 场** ⇒ 这个改动
    今天零代价。改的是**规则自洽**(docstring 自己说「一道闸管全部」)和那个
    将来会咬人的口子 —— 所以只能用合成夹具钉,真数据钉不出来。
    """
    from nutmeg.v4.cli.line_origin import _pinnacle_open_close
    db = tmp_path / "prop" / "obs.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    later_in_play = dict(_IN_PLAY, captured_at="2026-08-01T20:00:00+00:00")
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        for r in (_PRE_CLOSE, _IN_PLAY, later_in_play):   # 1 赛前 + 2 滚球
            _snap(conn, home="Alpha FC", away="Beta FC", **r)
        conn.commit()
        out = _pinnacle_open_close(conn, "2000-01-01")
    assert out == {}, (
        f"只有 1 个赛前快照的比赛通过了「≥2」判据:{out}\n"
        f"⇒ 它的 open==close、band 塌成一点,而下游会当成一个正常样本用")


def test_two_genuine_pre_kickoff_captures_still_qualify(tmp_path):
    """⭐ 负对照:两个**真赛前**快照照常通过。

    没有这条,把判据写成「一律不通过」也能让上面那条绿 —— 那样整个 CLI 就废了。
    """
    open_p, close_p, lo, hi, _h, _a = _line_origin_band(
        tmp_path / "ok", [_PRE_OPEN, _PRE_CLOSE])
    assert open_p != close_p, "两个不同赛前快照却给出同一个 open/close"
    assert lo[0] < hi[0], f"band 塌成了一个点:lo={lo} hi={hi}"
