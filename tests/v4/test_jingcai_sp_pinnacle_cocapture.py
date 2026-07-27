"""捕获时 Pinnacle 补录(2026-07-27)—— sink 侧 + 历史回填。

病情:写 jingcai_sp 86% 行的 cron 读的是竞彩自己的源,手里没有 Pinnacle ⇒ 那些行
psc_* 全空(实测 32/469 = 7%),永远进不了 CLV 账本的**选中腿**计数。

本文件锁住三件事,其中第 2 件是承重的:
  1. sink 会补,但**调用方给的一律不覆盖**(面板传的是用户定价时看的那条线);
  2. ⭐ **绝不取比竞彩捕获更晚的 Pinnacle 快照** —— 账本用捕获时 EV 挑选中腿正是
     为了不含未来信息;一旦这道闸破,selected-CLV 会从「测量」静默退化成循环论证,
     而且**看不出来**(数字照样能算出来,只是不再有意义);
  3. 补录失败绝不打断竞彩捕获(本模块契约:NEVER raises out of the capture path)。
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.jingcai_sp import (
    backfill_jingcai_sp_pinnacle,
    fetch_jingcai_sp,
    record_jingcai_sp,
)

# booksum 1.1046 ∈ [1.10, 1.15] —— 过捕获端闸 1(编的三元组会被拒,先自检过)
_JC = {"jc_home": 1.70, "jc_draw": 3.40, "jc_away": 4.50}
_MATCH = {"match_date": "2026-06-20", "home_team": "Mexico", "away_team": "South Africa"}


def _snap(db, *, captured_at, psc_home, kickoff_utc=None, ou_line=2.75):
    with sqlite3.connect(db) as conn:
        from nutmeg.v4.observation.odds_snapshots import ensure_odds_snapshots
        ensure_odds_snapshots(conn)
        conn.execute(
            "INSERT INTO odds_snapshots (captured_at, source, league, match_date, "
            "home_team, away_team, kickoff_utc, psc_home, psc_draw, psc_away, "
            "ou_line, psc_over, psc_under) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (captured_at, "test", "WC", _MATCH["match_date"], _MATCH["home_team"],
             _MATCH["away_team"], kickoff_utc, psc_home, 4.43, 8.70,
             ou_line, 1.90, 1.95))


def _row(db):
    return fetch_jingcai_sp(db)[0]


def test_sink_corecords_when_caller_has_none(tmp_path):
    """cron 路径(不带 Pinnacle)——补录后该行能进选中腿计数。"""
    db = str(tmp_path / "obs.db")
    _snap(db, captured_at="2026-06-19T12:00:00+00:00", psc_home=1.43)
    assert record_jingcai_sp(db, **_MATCH, **_JC, source="sporttery") is True
    r = _row(db)
    assert r["psc_home"] == 1.43
    assert r["ou_line"] == 2.75
    assert r["psc_over"] == 1.90 and r["psc_under"] == 1.95


def test_caller_supplied_pinnacle_wins(tmp_path):
    """面板路径:用户定价时看的那条线才权威,补录不许覆盖。"""
    db = str(tmp_path / "obs.db")
    _snap(db, captured_at="2026-06-19T12:00:00+00:00", psc_home=1.43)
    assert record_jingcai_sp(
        db, **_MATCH, **_JC, source="market_mode",
        psc_home=1.61, psc_draw=4.00, psc_away=7.00) is True
    r = _row(db)
    assert r["psc_home"] == 1.61          # 调用方的值原样保留
    assert r["ou_line"] == 2.75           # 但空缺的 O/U 仍然补上了


def test_never_uses_a_later_snapshot(tmp_path):
    """⭐ 承重闸:更晚的快照必须被忽略,否则选中腿带 look-ahead。

    唯一可得的快照来自 2099 年(远晚于本次捕获)⇒ 宁可留空,也不能拿。
    """
    db = str(tmp_path / "obs.db")
    _snap(db, captured_at="2099-01-01T00:00:00+00:00", psc_home=9.99)
    assert record_jingcai_sp(db, **_MATCH, **_JC, source="sporttery") is True
    r = _row(db)
    assert r["psc_home"] is None, "取了未来的 Pinnacle —— selected-CLV 已成循环论证"
    assert r["ou_line"] is None


def test_never_uses_an_inplay_snapshot(tmp_path):
    """盘中滚球线(领先方 1.06)曾污染过姊妹表一次(体检 B1)。"""
    db = str(tmp_path / "obs.db")
    _snap(db, captured_at="2026-06-19T12:00:00+00:00", psc_home=1.06,
          kickoff_utc="2026-06-19T11:00:00+00:00")   # 捕获在开球之后 = 盘中
    assert record_jingcai_sp(db, **_MATCH, **_JC, source="sporttery") is True
    assert _row(db)["psc_home"] is None


def test_capture_survives_without_odds_snapshots(tmp_path):
    """odds_snapshots 不存在时,竞彩捕获照常成功(补录 fail-soft)。"""
    db = str(tmp_path / "obs.db")
    assert record_jingcai_sp(db, **_MATCH, **_JC, source="sporttery") is True
    r = _row(db)
    assert r["jc_home"] == 1.70 and r["psc_home"] is None


def test_backfill_uses_each_rows_own_capture_time(tmp_path):
    """⭐ 回填口径必须与新行一致 —— 按**该行自己的** captured_at 回查。

    混口径(回填用最新快照、新行用当时快照)会让账本一半干净一半带 look-ahead,
    比不补更坏:说不清哪些数还能用。
    """
    db = str(tmp_path / "obs.db")
    assert record_jingcai_sp(db, **_MATCH, **_JC, source="sporttery") is True
    with sqlite3.connect(db) as conn:   # 把它做成一条「2026-06-19 中午捕获」的旧行
        conn.execute("UPDATE jingcai_sp SET captured_at = ?",
                     ("2026-06-19T12:00:00+00:00",))
    _snap(db, captured_at="2026-06-19T09:00:00+00:00", psc_home=1.43)   # 捕获之前
    _snap(db, captured_at="2026-06-19T22:00:00+00:00", psc_home=9.99)   # 捕获之后

    assert backfill_jingcai_sp_pinnacle(db) == 1
    assert _row(db)["psc_home"] == 1.43, "回填取了该行捕获之后的线 = look-ahead"


def test_backfill_is_idempotent(tmp_path):
    """只写 NULL 列 —— 重复跑不改已有值,也不重复计数。"""
    db = str(tmp_path / "obs.db")
    assert record_jingcai_sp(
        db, **_MATCH, **_JC, source="market_mode",
        psc_home=1.61, psc_draw=4.00, psc_away=7.00) is True
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE jingcai_sp SET captured_at = ?",
                     ("2026-06-19T12:00:00+00:00",))
    _snap(db, captured_at="2026-06-19T09:00:00+00:00", psc_home=1.43)

    assert backfill_jingcai_sp_pinnacle(db) == 1
    assert _row(db)["psc_home"] == 1.61     # 手填的线没被回填覆盖
    assert _row(db)["ou_line"] == 2.75
    backfill_jingcai_sp_pinnacle(db)        # 二次跑
    assert _row(db)["psc_home"] == 1.61
