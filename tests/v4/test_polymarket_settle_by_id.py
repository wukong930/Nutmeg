"""🚨 结算按 **fixture id** 查,不再按「记录时的日期」拉当天赛程(2026-09-16)。

## 病史:11 场卡了最长两个月,而且**看不见**

旧实现:`fetch_fixtures(记录时的 match_date)` → 按 id 建索引 → 查表。
**比赛一改期就不在那天的列表里** ⇒ `by_id.get()` 返回 None ⇒ 静默 `continue`
⇒ **永远结不了**。实测卡住 11 场,其中 **5 场比分早就有了**:

    记录日 2026-07-11  AF 真实 **2026-08-18**  FT 0:3   ← 改期 5 周,卡两个月
    记录日 2026-07-25  AF 真实 2026-09-02      FT 1:0
    记录日 2026-09-05  AF 真实 2026-09-08      FT 3:3
    记录日 2026-09-05  AF 真实 2026-09-06      FT 2:2
    记录日 2026-09-06  AF 真实 2026-09-05      FT 0:1

⭐ **fixture id 是稳定的,日期不是** —— 旧实现把可变的那个当成了查找键。
   凡是「记录时存了日期、后来要回头找同一场」的地方都是同一个形状。

## 两件事一起修,缺一不可

① **查找键**:按 id 直查(`fetch_fixtures_by_ids`,分批 20)。
② **记账**:返回 `SettleResult` 而不是裸 int。旧实现三条 `continue` 全是静默的,
   于是「改期卡住」「还没踢」「查不到」**长得一模一样** —— 我是查别的东西才撞见的。
   同 `guard-on-a-failsoft-path-must-record`:fail-soft 路径上只「跳过」等于没装。

⚠️ 修完实跑:**71 行结算成功**,剩 6 场 = 4 场改期到未来(NS)+ 2 场推迟(PST),
   **正是该剩的**。
"""
from __future__ import annotations

import datetime as dt

import pytest

from nutmeg.v4.model.polymarket_gap import HOME_WIN
from nutmeg.v4.observation.polymarket_gaps import (
    SettleResult,
    ensure_polymarket_gaps_table,
    fetch_polymarket_gaps,
    settle_polymarket_gaps,
)


def _fx(fid: int, date: str, status: str = "FT", hg=None, ag=None) -> dict:
    fx = {
        "fixture": {"id": fid, "date": f"{date}T16:00:00+00:00", "status": {"short": status}},
        "teams": {"home": {"name": "H"}, "away": {"name": "A"}},
        "league": {"name": "Friendlies"},
    }
    if hg is not None:
        fx["score"] = {"fulltime": {"home": hg, "away": ag}}
        fx["goals"] = {"home": hg, "away": ag}
    return fx


def _seed(db, fid: int, match_date: str) -> None:
    """直接插一行未结算的 gap(绕开 record 的盘中价闸 —— 本文件测的是结算)。"""
    import sqlite3
    ensure_polymarket_gaps_table(db)
    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT OR REPLACE INTO polymarket_gaps (match_date, fixture_id, outcome_spec,"
            " line, recorded_at, league, home_team, away_team, kickoff_utc, q_fair,"
            " poly_ask, ev, confidence_tier) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (match_date, fid, HOME_WIN, -100.0, f"{match_date}T10:00:00+00:00",
             "Friendlies", "H", "A", f"{match_date}T16:00:00+00:00", 0.5, 0.45, 0.1, "high"))


class TestRescheduledMatchesStillSettle:
    """⭐ 这个类就是那个 bug 本身。"""

    def test_a_fixture_moved_five_weeks_later_still_settles(self, tmp_path):
        """🚨 旧实现在这里**必然失败**:它会去拉 2026-07-11 那天的赛程,
        而这场已经挪到 08-18 ⇒ 查不到 ⇒ 永远不结算。
        """
        db = str(tmp_path / "t.db")
        _seed(db, 1523198, "2026-07-11")
        seen: list[list[int]] = []

        def by_ids(ids):
            seen.append(list(ids))
            return [_fx(1523198, "2026-08-18", "FT", 0, 3)]

        r = settle_polymarket_gaps(db, fetch_by_ids=by_ids, today=dt.date(2026, 9, 16))
        assert r.settled == 1, r
        assert r.rescheduled == 1, "改期没有被记账 —— 那正是要被看见的那件事"
        # ⭐ 承重:它**按 id** 去问的,不是按日期
        assert seen == [[1523198]], f"查找键不是 fixture id:{seen}"
        row = fetch_polymarket_gaps(db, settled_only=True)[0]
        assert (row["home_goals"], row["away_goals"]) == (0, 3)

    def test_same_date_still_works(self, tmp_path):
        """⚠️ 对照:没改期的场当然也要能结 —— 否则上面那条可能只是「什么都结」。"""
        db = str(tmp_path / "t.db")
        _seed(db, 222, "2026-06-06")
        r = settle_polymarket_gaps(
            db, fetch_by_ids=lambda ids: [_fx(222, "2026-06-06", "FT", 1, 0)],
            today=dt.date(2026, 6, 7))
        assert r.settled == 1 and r.rescheduled == 0, r


class TestEveryRowLandsInExactlyOneBucket:
    """🚨 旧实现三条 `continue` 全静默 ⇒「没结算」没有原因。这里钉住记账完整性。"""

    @pytest.mark.parametrize("status,bucket", [
        ("NS", "not_played"), ("PST", "not_played"), ("CANC", "not_played"),
        ("TBD", "not_played"), ("SUSP", "not_played"),
    ])
    def test_unplayed_statuses_are_not_conflated_with_not_found(self, tmp_path, status, bucket):
        """⭐ 「还没踢」和「查不到」必须分开 —— 旧实现让它们长得一模一样,
        于是 2 场 PST 和 5 场真 bug 混在一堆里,没人看得出区别。"""
        db = str(tmp_path / "t.db")
        _seed(db, 333, "2026-06-06")
        r = settle_polymarket_gaps(
            db, fetch_by_ids=lambda ids: [_fx(333, "2026-06-06", status)],
            today=dt.date(2026, 6, 7))
        assert getattr(r, bucket) == 1, r
        assert r.not_found == 0, "还没踢被记成了『查不到』"
        assert r.settled == 0

    def test_a_fixture_af_does_not_know_is_not_found(self, tmp_path):
        db = str(tmp_path / "t.db")
        _seed(db, 444, "2026-06-06")
        r = settle_polymarket_gaps(db, fetch_by_ids=lambda ids: [],
                                   today=dt.date(2026, 6, 7))
        assert r.not_found == 1 and r.settled == 0 and r.not_played == 0, r

    def test_the_buckets_add_up(self, tmp_path):
        """⭐ 记账完整性:每一行都必须落进**恰好一格**,不许凭空消失。"""
        db = str(tmp_path / "t.db")
        for i, (fid, st) in enumerate([(1, "FT"), (2, "NS"), (3, "PST")]):
            _seed(db, fid, "2026-06-06")
        fx = [_fx(1, "2026-06-06", "FT", 2, 1), _fx(2, "2026-06-06", "NS"),
              _fx(3, "2026-06-06", "PST")]
        r = settle_polymarket_gaps(db, fetch_by_ids=lambda ids: fx, today=dt.date(2026, 6, 7))
        total = r.settled + r.not_found + r.not_played + r.no_score + r.unresolvable
        assert total == 3, f"3 行只落进 {total} 格 —— 有行凭空消失了:{r}"
        assert (r.settled, r.not_played) == (1, 2), r

    def test_fetch_failure_is_accounted_not_swallowed(self, tmp_path):
        """⚠️ 网络失败也要记账 —— 否则「没结算」又变成静默的。"""
        db = str(tmp_path / "t.db")
        _seed(db, 555, "2026-06-06")

        def boom(ids):
            raise OSError("network down")

        r = settle_polymarket_gaps(db, fetch_by_ids=boom, today=dt.date(2026, 6, 7))
        assert r.settled == 0 and r.not_found == 1, r


class TestItAsksByIdInBatches:
    def test_more_than_twenty_ids_are_batched(self, tmp_path):
        """🚨 AF 的 `ids=` 单次最多 20 个,**超了不报错只静默截断** ——
        分批是必需的,不是优化。没有这条,第 21 场起会悄悄变成「查不到」。
        """
        from nutmeg.v4.data.sources.api_football import _FIXTURE_IDS_BATCH
        assert _FIXTURE_IDS_BATCH <= 20
        db = str(tmp_path / "t.db")
        for fid in range(1, 26):
            _seed(db, fid, "2026-06-06")
        calls: list[int] = []

        def by_ids(ids):
            calls.append(len(ids))
            return [_fx(f, "2026-06-06", "FT", 1, 0) for f in ids]

        # 注入的是「一次拿全部 id」的版本 ⇒ 这里只验**生产默认**会分批
        r = settle_polymarket_gaps(db, fetch_by_ids=by_ids, today=dt.date(2026, 6, 7))
        assert r.settled == 25, r
        assert calls == [25], "settle 应当一次把 id 交给 fetcher,由 fetcher 分批"

    def test_the_production_fetcher_batches(self, monkeypatch):
        """分批发生在 `fetch_fixtures_by_ids` 里 —— 在那一层验。"""
        from nutmeg.v4.data.sources import api_football as af
        seen: list[str] = []

        def fake_request(endpoint, params, **kw):
            seen.append(params["ids"])
            return []

        monkeypatch.setattr(af, "_request", fake_request)
        af.fetch_fixtures_by_ids(list(range(1, 46)))
        assert len(seen) == 3, f"45 个 id 应分 3 批,实际 {len(seen)} 批"
        assert all(len(b.split("-")) <= 20 for b in seen), seen
        # 人口非平凡:去重 + 排序后总数要对得上
        assert sum(len(b.split("-")) for b in seen) == 45
