"""``polymarket_gaps`` 盘中价入库闸(2026-09-02)。

实测病情见 ``observation/polymarket_gaps`` 模块头:生产库 9,074 行里 1,294 行
(14.3%,已结算子集 20.4%)的 ``recorded_at`` 晚于 ``kickoff_utc``,而
``confidence_tier`` 一条都挡不住。

本文件的**核心断言不是「拒写」而是「拒写不覆盖」** —— PK 不含 ``recorded_at`` +
``ON CONFLICT DO UPDATE``,所以开球后那次 cron 的真实伤害是把 T−3h 那条合法赛前
观测原地冲掉。只测「返回 False」会漏掉这一整半,而那一半才是出血点。
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re

from nutmeg.v4.data.polymarket_match import AWAY_WIN, DRAW, HOME_WIN, MatchedGame, MatchedMarket
from nutmeg.v4.model.polymarket_gap import compute_gaps
from nutmeg.v4.observation.polymarket_gaps import (
    _is_inplay,
    fetch_polymarket_gaps,
    record_polymarket_gap,
)

KICKOFF = dt.datetime(2026, 6, 6, 16, 0, tzinfo=dt.UTC)
PRE = KICKOFF - dt.timedelta(hours=2)      # 合法赛前观测
POST = KICKOFF + dt.timedelta(hours=1)     # 盘中(第 46 分钟左右)


def _book(ask: float, *, depth_shares: float = 2000.0) -> dict:
    bid = round(ask - 0.02, 4)
    return {
        "asks": [{"price": str(round(ask + 0.02, 4)), "size": "100"},
                 {"price": str(ask), "size": str(depth_shares)}],
        "bids": [{"price": "0.01", "size": "50"},
                 {"price": str(bid), "size": str(depth_shares)}],
    }


def _game(*, kickoff: str = "2026-06-06 16:00:00+00") -> MatchedGame:
    return MatchedGame(
        fixture_id=111, league="Friendlies",
        home_team="Sierra Leone", away_team="Liberia",
        match_date="2026-06-06", kickoff_utc=kickoff,
        series_slug="fifa-friendly", event_slug="fif-sle-lbr-2026-06-06",
        match_method="exact", match_confidence=1.0,
        markets=[MatchedMarket(HOME_WIN, "tokH", "Will Sierra Leone win?"),
                 MatchedMarket(DRAW, "tokD", "Will it end in a draw?"),
                 MatchedMarket(AWAY_WIN, "tokA", "Will Liberia win?")],
    )


def _gaps(*, ask: float, at: dt.datetime, kickoff: str = "2026-06-06 16:00:00+00") -> list:
    """三腿 gap,``at`` 同时当作 Pinnacle 报价的新鲜度基准。"""
    return compute_gaps(
        _game(kickoff=kickoff), (0.50, 0.25, 0.25),
        {"tokH": _book(ask), "tokD": _book(0.30), "tokA": _book(0.40)},
        (at - dt.timedelta(hours=1)).isoformat(), now=at,
    )


class TestInplayRejected:
    def test_post_kickoff_write_is_rejected_and_leaves_no_row(self, tmp_path):
        db = str(tmp_path / "obs.db")
        gaps = _gaps(ask=0.40, at=POST)
        assert gaps, "人口非平凡:compute_gaps 必须真的产出腿,否则下面全是空洞为真"

        wrote = [record_polymarket_gap(db, g, recorded_at=POST) for g in gaps]

        assert wrote == [False] * len(gaps)
        assert fetch_polymarket_gaps(db) == []

    def test_pre_kickoff_write_still_lands(self, tmp_path):
        db = str(tmp_path / "obs.db")
        gaps = _gaps(ask=0.40, at=PRE)
        assert gaps

        wrote = [record_polymarket_gap(db, g, recorded_at=PRE) for g in gaps]

        assert wrote == [True] * len(gaps)
        assert len(fetch_polymarket_gaps(db)) == len(gaps)

    def test_gate_instant_is_the_stored_instant(self, tmp_path):
        """判闸用的时刻与写进 ``recorded_at`` 的时刻必须是同一个值。

        闸读一次钟、写又读一次钟 ⇒ 两次之间跨过开球的那条行既过了闸又存了个赛后
        时刻(closing_odds 那次赛前/赛后竞态)。
        """
        db = str(tmp_path / "obs.db")
        g = _gaps(ask=0.40, at=PRE)[0]
        assert record_polymarket_gap(db, g, recorded_at=PRE) is True

        stored = fetch_polymarket_gaps(db)[0]["recorded_at"]
        assert dt.datetime.fromisoformat(stored) == PRE


class TestRejectedWriteDoesNotClobber:
    """🚨 出血点:拒写必须**保住**同键上那条赛前行,而不只是「自己不写」。"""

    def test_inplay_write_cannot_overwrite_the_prematch_row(self, tmp_path):
        db = str(tmp_path / "obs.db")
        pre = _gaps(ask=0.40, at=PRE)[0]
        assert record_polymarket_gap(db, pre, recorded_at=PRE) is True
        before = fetch_polymarket_gaps(db)[0]

        # 同一 (match_date, fixture_id, outcome_spec, line) 键,开球后再来一次:
        # 一颗进球后 ask 从 0.40 跳到 0.88 —— 正是会伪装成大 EV 的那种行。
        post = _gaps(ask=0.88, at=POST)[0]
        assert (post["outcome_spec"] if isinstance(post, dict) else post.outcome_spec) \
            == (before["outcome_spec"]), "两次必须落在同一个 PK 上,否则这个测试是空的"

        assert record_polymarket_gap(db, post, recorded_at=POST) is False

        rows = fetch_polymarket_gaps(db)
        assert len(rows) == 1
        after = rows[0]
        # 赛前那条**逐列**没动 —— 只断言行数会放过「原地覆盖」这一整类。
        for col in ("recorded_at", "poly_ask", "ev", "confidence_tier", "poly_mid"):
            assert after[col] == before[col], f"{col} 被盘中价覆盖了"

    def test_control_a_second_prematch_write_does_still_refresh(self, tmp_path):
        """对照组:闸不能顺手把**合法**的重复采集也冻住(价格会动,赛前刷新是本意)。"""
        db = str(tmp_path / "obs.db")
        assert record_polymarket_gap(db, _gaps(ask=0.40, at=PRE)[0], recorded_at=PRE) is True
        first = fetch_polymarket_gaps(db)[0]

        later = PRE + dt.timedelta(minutes=30)
        assert record_polymarket_gap(db, _gaps(ask=0.55, at=later)[0], recorded_at=later) is True

        rows = fetch_polymarket_gaps(db)
        assert len(rows) == 1
        assert rows[0]["poly_ask"] != first["poly_ask"], "赛前刷新被闸误杀了"


class TestBoundaryAndFailOpen:
    def test_exactly_at_kickoff_is_rejected(self):
        """容差 = 0。开球后 15 分钟内完全可能已经进球 ⇒ 正宽限会放进最毒的那批。"""
        assert _is_inplay("2026-06-06 16:00:00+00", KICKOFF) is True
        assert _is_inplay("2026-06-06 16:00:00+00", KICKOFF - dt.timedelta(seconds=1)) is False

    def test_unknown_or_unparseable_kickoff_fails_open(self):
        for bad in (None, "", "TBD", "2026-13-45", 0):
            assert _is_inplay(bad, POST) is False, f"{bad!r} 不该吃掉整批采集"

    def test_naive_kickoff_is_read_as_utc(self):
        """库里 155 行是裸时刻(全是 NWSL/MLS/Liga Pro 的 00:00 UTC 开球,是真时刻
        不是占位符)—— 按本地时区读会把判据整体平移 8 小时。"""
        assert _is_inplay("2026-06-06 16:00:00", KICKOFF + dt.timedelta(minutes=1)) is True
        assert _is_inplay("2026-06-06 16:00:00", KICKOFF - dt.timedelta(minutes=1)) is False

    def test_fail_open_row_still_carries_kickoff_for_the_consumer(self, tmp_path):
        """fail-open 的代价必须可见:落进来的行仍带 ``kickoff_utc``,消费方还能自己判。"""
        db = str(tmp_path / "obs.db")
        g = _gaps(ask=0.40, at=POST, kickoff="TBD")[0]
        assert record_polymarket_gap(db, g, recorded_at=POST) is True
        assert fetch_polymarket_gaps(db)[0]["kickoff_utc"] == "TBD"


class TestNoSecondWritePath:
    """闸放在唯一出口才有意义 —— 第二条 INSERT 路径会绕过它,而且不会有人发现。

    人口**自己发现**(扫整个包),不是写死名单:写死的名单会随新文件悄悄失效。
    """

    def test_only_one_insert_path_into_the_table(self):
        pkg = pathlib.Path("apps/api/src/nutmeg")
        assert pkg.is_dir(), "人口非平凡:包路径必须存在,否则下面 0 命中空洞为真"
        files = list(pkg.rglob("*.py"))
        assert len(files) > 50, f"人口非平凡:只扫到 {len(files)} 个文件,发现器坏了"

        pat = re.compile(r"INSERT\s+INTO\s+polymarket_gaps", re.I)
        hits = sorted(p for p in files if pat.search(p.read_text(encoding="utf-8")))

        assert hits, "人口非平凡:一条 INSERT 都没找到 ⇒ 是发现器坏了,不是没有写入路径"
        assert [p.name for p in hits] == ["polymarket_gaps.py"], (
            f"出现了第二条写入路径,它绕过盘中价闸:{[str(p) for p in hits]}")


class TestReadOutletFiltersLegacyInplayRows:
    """写入闸只挡新增;**存量 1,294 行**是它上线前写的,每个消费方都还会读到。

    ⭐ 修在唯一读出口 `fetch_polymarket_gaps`,不逐消费方打补丁,也不动存量数据。
    """

    def _seed(self, db):
        """一条赛前行 + 一条盘中行。⚠️ 盘中那条必须**绕过写入闸**直接落库,否则
        这个测试测的是闸而不是读出口 —— 那样它会空洞为真。"""
        import sqlite3

        from nutmeg.v4.observation.polymarket_gaps import ensure_polymarket_gaps_table
        pre = _gaps(ask=0.40, at=PRE)[0]
        assert record_polymarket_gap(db, pre, recorded_at=PRE) is True
        ensure_polymarket_gaps_table(db)
        with sqlite3.connect(db) as conn:      # 直插:模拟闸上线**之前**写下的那批
            conn.execute(
                "INSERT INTO polymarket_gaps (match_date, fixture_id, outcome_spec, line,"
                " recorded_at, kickoff_utc, q_fair, poly_ask, ev, confidence_tier)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("2026-06-06", 111, "DRAW", -100.0, POST.isoformat(timespec="seconds"),
                 "2026-06-06 16:00:00+00", 0.25, 0.98, -0.745, "high"))

    def test_legacy_inplay_rows_are_not_served(self, tmp_path):
        db = str(tmp_path / "obs.db")
        self._seed(db)

        allrows = fetch_polymarket_gaps(db, include_inplay=True)
        served = fetch_polymarket_gaps(db)

        # 🚨 人口非平凡:脏行必须真的在库里,否则「过滤掉了」空洞为真
        assert len(allrows) == 2, f"种子没落库,后面全是空断言:{allrows}"
        assert any(r["outcome_spec"] == "DRAW" for r in allrows), "盘中那条没进库"

        assert len(served) == 1
        assert served[0]["outcome_spec"] == "HOME_WIN", "被服务的应是赛前那条"

    def test_prematch_rows_are_not_over_filtered(self, tmp_path):
        """对照组:出口不能顺手把合法赛前行也滤掉(过滤器最常见的坏法是过严)。"""
        db = str(tmp_path / "obs.db")
        for g in _gaps(ask=0.40, at=PRE):
            assert record_polymarket_gap(db, g, recorded_at=PRE) is True
        assert len(fetch_polymarket_gaps(db)) == 3

    def test_row_whose_kickoff_is_unparseable_is_still_served(self, tmp_path):
        """fail-open 在读出口也必须成立 —— 坏时刻不该让整行消失。"""
        db = str(tmp_path / "obs.db")
        g = _gaps(ask=0.40, at=POST, kickoff="TBD")[0]
        assert record_polymarket_gap(db, g, recorded_at=POST) is True
        assert len(fetch_polymarket_gaps(db)) == 1

    def test_string_compare_would_have_gotten_this_wrong(self):
        """🚨 钉住那个陷阱本身:两列字面量格式不同,裸字符串比会判反。

        `recorded_at` 用 `T` 分隔、`kickoff_utc` 用空格 ⇒ `T`(0x54) > ` `(0x20)
        ⇒ 同一天的行,**开球前 4 小时**会被判成「已开球」。所以过滤必须解析后再比。
        """
        from nutmeg.v4.observation.polymarket_gaps import _is_inplay, _parse_utc
        rec, ko = "2026-06-30T17:21:12+00:00", "2026-06-30 21:00:00+00"

        assert not (rec < ko), "前提变了:这两个字面量的裸比较已不再判反,本条要重写"
        assert _is_inplay(ko, _parse_utc(rec)) is False, "解析后必须判成赛前"
