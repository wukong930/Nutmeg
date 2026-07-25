"""竞彩 SP 线史(2026-07-25)—— 「13 次抓、1 次留」的修复。

病史:sporttery_evening 17:00-23:00 每 30 分抓一次(13 次/天),但 jingcai_sp 是
UPSERT,13 次全覆盖同一行 → 盘中变化写进去又被自己冲掉。抓取成本照付,数据全丢。
后果:前向期根本没法回答「竞彩真的冻结了多久」—— 拿仅存的 vote 快照测,81/81 场
「最后一次变盘 == 最后一次观测」= 100% 右审查,量到的是我们的观测节奏不是竞彩行为。
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp
from nutmeg.v4.observation.jingcai_sp_snapshots import record_jingcai_sp_snapshot


def _snaps(db) -> list[tuple]:
    """表不存在 = 一条都没写进去(拒写路径下 ensure 压根没跑到)→ 空列表。"""
    with sqlite3.connect(db) as c:
        try:
            return c.execute(
                "SELECT jc_home, jc_draw, jc_away, source, market "
                "FROM jingcai_sp_snapshots ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            return []


def _future(hours: float = 6) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=hours)).isoformat()


class TestAppendOnlyAndDedup:
    def test_line_movement_is_kept_not_overwritten(self, tmp_path):
        """核心:同一场三次不同报价 → 三行。这正是 jingcai_sp 丢掉的东西。"""
        db = tmp_path / "o.db"
        for h, d, a in ((2.04, 3.03, 3.23), (2.09, 3.05, 3.10), (2.07, 3.05, 3.14)):
            record_jingcai_sp_snapshot(
                db, match_date="2026-08-01", home_team="A", away_team="B",
                market="had", jc_home=h, jc_draw=d, jc_away=a,
                kickoff_utc=_future(), source="sporttery_evening")
        got = _snaps(db)
        assert len(got) == 3, "线动了三次就该留三行"
        assert [r[0] for r in got] == [2.04, 2.09, 2.07]

    def test_unchanged_line_does_not_append(self, tmp_path):
        """13 次抓同一个价只留 1 行 —— 加密采样不该让表爆炸。"""
        db = tmp_path / "o.db"
        for _ in range(13):
            record_jingcai_sp_snapshot(
                db, match_date="2026-08-01", home_team="A", away_team="B",
                market="had", jc_home=2.04, jc_draw=3.03, jc_away=3.23,
                kickoff_utc=_future(), source="sporttery_evening")
        assert len(_snaps(db)) == 1

    def test_handicap_line_move_counts_as_a_change(self, tmp_path):
        """让球盘:赔率没动但**线**动了,也是一次变盘,不能被去重吃掉。"""
        db = tmp_path / "o.db"
        for hc in (-1, -2):
            record_jingcai_sp_snapshot(
                db, match_date="2026-08-01", home_team="A", away_team="B",
                market="hhad", jc_home=2.04, jc_draw=3.03, jc_away=3.23,
                handicap_home=hc, kickoff_utc=_future(), source="sporttery_evening")
        assert len(_snaps(db)) == 2

    def test_markets_are_tracked_separately(self, tmp_path):
        db = tmp_path / "o.db"
        for m in ("had", "hhad"):
            record_jingcai_sp_snapshot(
                db, match_date="2026-08-01", home_team="A", away_team="B",
                market=m, jc_home=2.04, jc_draw=3.03, jc_away=3.23,
                kickoff_utc=_future(), source="sporttery_evening")
        assert {r[4] for r in _snaps(db)} == {"had", "hhad"}


class TestPostKickoffGate:
    def test_post_kickoff_reading_is_refused(self, tmp_path):
        """闸 3 —— 今天现学的。jingcai_vote_snapshots 14% 的行在开球后且 jc_* 还在
        变,直接把「最后一次变盘 → 开球」算成**负数**。停售后的读数不是可下注的价,
        进了这张表就会毒死它唯一的用途。"""
        db = tmp_path / "o.db"
        past = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)).isoformat()
        ok = record_jingcai_sp_snapshot(
            db, match_date="2026-08-01", home_team="A", away_team="B",
            market="had", jc_home=2.04, jc_draw=3.03, jc_away=3.23,
            kickoff_utc=past, source="sporttery_evening")
        assert ok is False
        assert _snaps(db) == []

    def test_unknown_kickoff_fails_open(self, tmp_path):
        """kickoff 未知 → 放行(与捕获端 _past_kickoff 的 fail-open 一致);
        消费方另有 captured_at < kickoff_utc 可用。"""
        db = tmp_path / "o.db"
        assert record_jingcai_sp_snapshot(
            db, match_date="2026-08-01", home_team="A", away_team="B",
            market="had", jc_home=2.04, jc_draw=3.03, jc_away=3.23,
            kickoff_utc=None, source="market_mode") is True


class TestWiredIntoSharedSink:
    def test_capture_writes_both_the_upsert_and_the_snapshot(self, tmp_path):
        """挂在 record_jingcai_sp 里 —— 四个 sporttery cron 全过它,一处接通全接通。"""
        db = tmp_path / "o.db"
        assert record_jingcai_sp(
            db, match_date="2026-08-01", home_team="A", away_team="B",
            jc_home=2.04, jc_draw=3.03, jc_away=3.23,
            kickoff_utc=_future(), source="sporttery_evening") is True
        assert len(_snaps(db)) == 1
        # 再抓一次、价变了 → upsert 覆盖旧行,但快照多一行
        record_jingcai_sp(
            db, match_date="2026-08-01", home_team="A", away_team="B",
            jc_home=2.07, jc_draw=3.05, jc_away=3.14,
            kickoff_utc=_future(), source="sporttery_evening")
        with sqlite3.connect(db) as c:
            n_canon = c.execute("SELECT COUNT(*) FROM jingcai_sp").fetchone()[0]
        assert n_canon == 1, "canonical 表照旧 UPSERT 只留一行"
        assert len(_snaps(db)) == 2, "线史留住了两个状态"

    def test_booksum_reject_never_reaches_the_snapshot(self, tmp_path):
        """闸 1 继承:booksum 出带的脏值在 record_jingcai_sp 就被拒,
        走不到快照 —— 别让线史变成脏值的避风港。"""
        db = tmp_path / "o.db"
        assert record_jingcai_sp(
            db, match_date="2026-08-01", home_team="A", away_team="B",
            jc_home=2.04, jc_draw=3.03, jc_away=7.25,   # 真实基底 + RCA 同款手滑腿
            kickoff_utc=_future(), source="sporttery_evening") is False
        assert _snaps(db) == []

    def test_hand_priced_match_still_records_the_observation(self, tmp_path):
        """⚠️ 这条是设计要点:protect_manual 挡的是「别覆盖你的手填」,
        但 cron 确实观测到了竞彩的真实报价 —— 那正是冻结缺口要的移动数据,
        不该因为不覆盖就连观测一起丢。快照写在 protect_manual 分支**之前**。"""
        db = tmp_path / "o.db"
        record_jingcai_sp(                      # 先手填
            db, match_date="2026-08-01", home_team="A", away_team="B",
            jc_home=2.04, jc_draw=3.03, jc_away=3.23,
            kickoff_utc=_future(), source="market_mode")
        record_jingcai_sp(                      # cron 再来,带保护
            db, match_date="2026-08-01", home_team="A", away_team="B",
            jc_home=1.97, jc_draw=3.23, jc_away=3.20,
            kickoff_utc=_future(), source="sporttery_evening", protect_manual=True)
        with sqlite3.connect(db) as c:
            canon = c.execute("SELECT jc_home FROM jingcai_sp").fetchone()[0]
        assert canon == 2.04, "手填仍是 canonical,没被覆盖"
        assert len(_snaps(db)) == 2, "但 cron 那次观测必须留下来"
        assert _snaps(db)[1][0] == 1.97
