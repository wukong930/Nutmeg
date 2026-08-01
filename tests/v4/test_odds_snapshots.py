"""体检 A1 — odds_snapshots append-only line history (the CLV foundation)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from nutmeg.v4.data.odds_parser import PINNACLE_BOOKMAKER_ID
from nutmeg.v4.observation.odds_snapshots import record_row_snapshot


def _row(**over) -> dict:
    base = {
        "date": "2026-06-11", "league": "WC",
        "home_team": "Mexico", "away_team": "South Africa",
        "psc_home": 1.65, "psc_draw": 3.90, "psc_away": 5.60,
        "psc_over25": 1.85, "psc_under25": 1.95, "ou_line": 2.5,
        "kickoff_utc": "2026-06-11T19:00:00+00:00",
        "odds_update": "2026-06-10T08:00:00+00:00",
    }
    base.update(over)
    return base


def _all(db: Path) -> list[tuple]:
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT psc_home, odds_update, source FROM odds_snapshots ORDER BY id"
        ).fetchall()


class TestRecordRowSnapshot:
    def test_first_insert(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101, source="ingest_odds")
        rows = _all(db)
        assert rows == [(1.65, "2026-06-10T08:00:00+00:00", "ingest_odds")]

    def test_unchanged_state_dedups(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(db, _row(), fixture_id=101) is False
        assert len(_all(db)) == 1

    def test_price_move_appends_both_rows_kept(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(db, _row(psc_home=1.70), fixture_id=101)
        prices = [r[0] for r in _all(db)]
        assert prices == [1.65, 1.70]  # append-only: history retained

    def test_fresh_odds_update_same_prices_is_new_state(self, tmp_path):
        # "line re-confirmed at T" is closing-line evidence — kept on purpose.
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(
            db, _row(odds_update="2026-06-11T18:00:00+00:00"), fixture_id=101)
        assert len(_all(db)) == 2

    def test_match_key_dedup_without_fixture_id(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row())
        assert record_row_snapshot(db, _row()) is False
        assert len(_all(db)) == 1

    def test_pending_row_skipped(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(
            db, _row(psc_home=None, psc_draw=None, psc_away=None),
            fixture_id=102) is False
        assert len(_all(db)) == 1

    def test_asian_handicap_json_stored(self, tmp_path, monkeypatch):
        import nutmeg.v4.data.odds_parser as op
        monkeypatch.setattr(
            op, "extract_asian_handicap",
            lambda env, bid=PINNACLE_BOOKMAKER_ID: {-1.5: {"home": 1.9, "away": 1.9}})
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101, envelope={"x": 1})
        with sqlite3.connect(db) as conn:
            (ah,) = conn.execute(
                "SELECT asian_handicap FROM odds_snapshots").fetchone()
        assert '"-1.5"' in ah and '"home": 1.9' in ah

    def test_never_raises_on_bad_db_path(self):
        assert record_row_snapshot(
            "/nonexistent_dir_xyz/obs.db", _row(), fixture_id=1) is False


class TestOddsSanityGuard:
    """体检 A1 (2026-07-01) — the shared CLV/soft-water sink must reject
    physically-impossible odds regardless of which producer emits them. Before
    the guard it stored 1.06/…/53.96, psc=0.5, psc=−3.0 (all returned True)."""

    def test_rejects_sub_unity_leg(self, tmp_path):
        # insert one valid row first so the table exists, then prove the bad one
        # is rejected AND does not append
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(), fixture_id=101)
        assert record_row_snapshot(db, _row(psc_home=0.5), fixture_id=102) is False
        assert len(_all(db)) == 1

    def test_rejects_negative_leg(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_draw=-3.0), fixture_id=101) is False

    def test_rejects_exactly_one(self, tmp_path):
        # a decimal odd of 1.0 means zero payout over stake — impossible
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_away=1.0), fixture_id=101) is False

    def test_rejects_nan_and_inf(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_home=float("nan")), fixture_id=1) is False
        assert record_row_snapshot(db, _row(psc_home=float("inf")), fixture_id=2) is False

    def test_rejects_absurd_ceiling(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_away=5000.0), fixture_id=101) is False

    def test_rejects_impossible_ou_leg(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_row_snapshot(db, _row(psc_over25=0.4), fixture_id=101) is False

    def test_accepts_legit_deep_mismatch(self, tmp_path):
        # A genuine minnow-vs-giant pre-match line (short fav + long dog) is
        # numerically indistinguishable from an in-play degenerate line by value,
        # so the sink guard MUST pass it — in-play detection is the kickoff/
        # commence_time guards' job (closing capture + overlay + readers), NOT
        # this odds-sanity backstop. Guarding this here would drop real lines.
        db = tmp_path / "obs.db"
        assert record_row_snapshot(
            db, _row(psc_home=1.03, psc_draw=17.0, psc_away=60.0), fixture_id=101)
        assert len(_all(db)) == 1


class TestGatherRowsHook:
    """The _gather_rows choke point feeds snapshots (one hook → every flow)."""

    def _wire(self, monkeypatch, fixture_id=777):
        from nutmeg.v4.cli import ingest_odds as mod
        envelope = {
            "fixture": {"id": fixture_id, "date": "2026-06-11T19:00:00+00:00",
                        "status": {"short": "NS"}},
            "teams": {"home": {"name": "Mexico"},
                      "away": {"name": "South Africa"}},
            "update": "2026-06-10T08:00:00+00:00",
            "bookmakers": [{
                "id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
                "bets": [{"id": 1, "name": "Match Winner", "values": [
                    {"value": "Home", "odd": "1.65"},
                    {"value": "Draw", "odd": "3.90"},
                    {"value": "Away", "odd": "5.60"},
                ]}],
            }],
        }
        monkeypatch.setattr(
            mod.api_football, "fetch_fixtures_for_date",
            lambda *a, **k: [envelope])
        monkeypatch.setattr(
            mod.api_football, "fetch_odds", lambda *a, **k: [envelope])
        return mod

    def test_gather_snapshots_once_then_dedups(self, tmp_path, monkeypatch):
        import datetime as dt
        mod = self._wire(monkeypatch)
        db = tmp_path / "obs.db"
        for _ in (1, 2):  # second pass = unchanged cache → no new state
            mod._gather_rows(
                ["WC"], dt.date(2026, 6, 11), cache_dir=tmp_path,
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                snapshot_db=db, snapshot_source="ingest_odds")
        rows = _all(db)
        assert len(rows) == 1 and rows[0][2] == "ingest_odds"

    def test_gather_without_snapshot_db_writes_nothing(self, tmp_path, monkeypatch):
        import datetime as dt
        mod = self._wire(monkeypatch)
        mod._gather_rows(
            ["WC"], dt.date(2026, 6, 11), cache_dir=tmp_path,
            bookmaker_id=PINNACLE_BOOKMAKER_ID,
            refresh_fixtures=False, refresh_odds=False)
        assert not (tmp_path / "obs.db").exists()


def test_captured_at_defaults_to_now(tmp_path):
    """实时 cron 不传该参 —— 默认路径必须还是「此刻」,不能被回填功能带偏。"""
    import datetime as dt
    db = tmp_path / "o.db"
    assert record_row_snapshot(db, _row(), source="closing")
    with sqlite3.connect(db) as conn:
        got = conn.execute("SELECT captured_at FROM odds_snapshots").fetchone()[0]
    delta = abs((dt.datetime.now(dt.UTC)
                 - dt.datetime.fromisoformat(got)).total_seconds())
    assert delta < 60, f"默认 captured_at 应≈现在,实得 {got}"


def test_explicit_captured_at_is_used_for_backfill(tmp_path):
    """历史回填必须能把行落在**它真正存在的时刻**。否则补回来的数据全戳成今天:
    空洞照旧显示为空洞,线史分析看到几十行挤在同一秒(2026-07-23 真踩过)。"""
    db = tmp_path / "o.db"
    assert record_row_snapshot(db, _row(), source="closing",
                               captured_at="2026-07-18T13:55:00+00:00")
    with sqlite3.connect(db) as conn:
        got = conn.execute("SELECT captured_at FROM odds_snapshots").fetchone()[0]
    assert got == "2026-07-18T13:55:00+00:00"


# ── odds_source 列(2026-07-23)────────────────────────────────────────────
# 起因:owner 问「OA 到底值不值那 20000 额度」——答不上来,因为这行价来自 OA
# 还是 AF 镜像只活在内存里,从不落库。加列后可回溯统计。

def test_odds_source_defaults_to_api_football(tmp_path):
    """没被 _apply_odds_api_overlay 打过标 = 走的 AF 镜像(gather 的默认底座)。"""
    db = tmp_path / "o.db"
    assert record_row_snapshot(db, _row(), source="cup_market")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT odds_source FROM odds_snapshots").fetchone()[0] \
            == "api_football"


def test_odds_source_records_the_overlay(tmp_path):
    """overlay 打了标就必须原样落库 —— 这一列存在的全部意义。"""
    db = tmp_path / "o.db"
    assert record_row_snapshot(db, _row(odds_source="odds_api"), source="cup_market")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT odds_source FROM odds_snapshots").fetchone()[0] \
            == "odds_api"


def test_migration_is_idempotent_and_spares_old_rows(tmp_path):
    """老库补列:重复调用只是几次 PRAGMA;已有行留 NULL —— 那批行确实无从追溯,
    伪造一个来源比留空更坏(留空至少诚实,统计时能排除)。"""
    from nutmeg.v4.observation.odds_snapshots import ensure_odds_snapshots
    db = tmp_path / "o.db"
    # 造一张「加列之前」的老表
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at TEXT NOT NULL,
            source TEXT NOT NULL, fixture_id INTEGER, league TEXT NOT NULL,
            match_date TEXT NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
            kickoff_utc TEXT, psc_home REAL NOT NULL, psc_draw REAL NOT NULL,
            psc_away REAL NOT NULL, ou_line REAL, psc_over REAL, psc_under REAL,
            asian_handicap TEXT, odds_update TEXT)""")
        conn.execute("INSERT INTO odds_snapshots (captured_at, source, league, "
                     "match_date, home_team, away_team, psc_home, psc_draw, psc_away) "
                     "VALUES ('2026-06-01T00:00:00+00:00','cup_market','WC','2026-06-01',"
                     "'A','B',2.0,3.0,4.0)")
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        ensure_odds_snapshots(conn)          # 幂等:复跑不炸
        cols = {r[1] for r in conn.execute("PRAGMA table_info(odds_snapshots)")}
        assert "odds_source" in cols
        assert conn.execute("SELECT odds_source FROM odds_snapshots").fetchone()[0] is None


# ── 上游拼法归一(2026-08-01)──────────────────────────────────────────────

class TestUpstreamNameCanonicalisation:
    """两个上游对同一支队用不同英文名 ⇒ **收盘线静默叠加不上盘面那一行**。

    API-Football 走 `cup_market`(盘面正典)· Odds API 走 `closing`。
    实测 9 联赛 61 个名字只在 closing 侧出现。join 不通、CLV 少数据,
    **而且没有任何报错** —— 与本项目反复踩的「沉默的错误答案」同族。

    修在**唯一 sink** `record_row_snapshot`(Altitude:不逐生产者打补丁)。
    """

    def _row(self, home, away, league="USA_MLS"):
        return {"date": "2026-08-01", "league": league, "home_team": home,
                "away_team": away, "kickoff_utc": "2026-08-01T23:30:00Z",
                "psc_home": 2.0, "psc_draw": 3.4, "psc_away": 3.8}

    def test_sink_rewrites_closing_spelling_to_the_gather_one(self, tmp_path):
        from nutmeg.v4.observation.odds_snapshots import record_row_snapshot
        db = tmp_path / "o.db"
        assert record_row_snapshot(db, self._row("Charlotte FC", "LA Galaxy"))
        got = sqlite3.connect(db).execute(
            "SELECT home_team, away_team FROM odds_snapshots").fetchone()
        # ⭐ LA Galaxy 是**反例**:10 组双拼法里 9 组「短名是正典」,它恰好相反。
        assert got == ("Charlotte", "Los Angeles Galaxy")

    def test_unknown_names_pass_through_untouched(self, tmp_path):
        """⛔ 表里没有的名字**原样通过,绝不猜** —— 猜错是静默污染,比缺映射更坏。

        新分裂由 `scripts/derive_odds_name_aliases.py` 探测器报出来,不在写入路径上推断。
        """
        from nutmeg.v4.observation.odds_snapshots import record_row_snapshot
        db = tmp_path / "o.db"
        assert record_row_snapshot(db, self._row("Brand New FC", "Another New SC"))
        got = sqlite3.connect(db).execute(
            "SELECT home_team, away_team FROM odds_snapshots").fetchone()
        assert got == ("Brand New FC", "Another New SC")

    def test_sink_does_not_mutate_the_caller_row(self, tmp_path):
        """调用方的 dict 还要写 CSV / 喂别的消费者 —— 就地改会波及它们。"""
        from nutmeg.v4.observation.odds_snapshots import record_row_snapshot
        row = self._row("Charlotte FC", "LA Galaxy")
        record_row_snapshot(tmp_path / "o.db", row)
        assert row["home_team"] == "Charlotte FC", "sink 把调用方的 row 改了"

    def test_alias_table_has_no_self_loops(self):
        """key == value 说明推导时漏了「同名对照组」的过滤,表会白白变大。"""
        from nutmeg.v4.data.odds_source_aliases import ODDS_SOURCE_ALIASES
        loops = {k: v for k, v in ODDS_SOURCE_ALIASES.items() if k[1] == v}
        assert not loops, f"自环:{loops}"

    def test_alias_is_idempotent(self):
        """归一后的名字再归一必须不变 —— 否则回填会随重跑次数漂移。"""
        from nutmeg.v4.data.odds_source_aliases import ODDS_SOURCE_ALIASES, canonical_team
        for (lg, _old), new in ODDS_SOURCE_ALIASES.items():
            assert canonical_team(lg, new) == new, f"{lg}/{new} 不是不动点"

    def test_unresolved_list_is_pinned_so_it_cant_grow_silently(self):
        """⚠️ 7 条共现证据不足、**故意留空**。钉住数量:再多一条就红。

        这条防的正是今天反复出现的形状 —— 缺口悄悄变大而没有任何东西喊。
        新的分裂要么补进别名表(要有证据),要么显式改这个数字。
        """
        from nutmeg.v4.data.odds_source_aliases import UNRESOLVED_SPLITS
        assert len(UNRESOLVED_SPLITS) == 7, (
            f"未收敛项从 7 变成 {len(UNRESOLVED_SPLITS)}:{UNRESOLVED_SPLITS}\n"
            "跑 scripts/derive_odds_name_aliases.py 看新分裂,有证据才补。")

    def test_sport_key_league_is_normalised_to_the_v4_code(self, tmp_path):
        """⚠️ league 列自己也有两套词汇 —— 队名归一要先过它,否则整个查表落空。

        `closing_odds` 写 `"league": sk`,上一行是 `SPORT_KEYS.get(sk, sk)` 这种
        「宽进」写法:调用方传原始 sport_key 时它原样落库。实测 47 行(closing 侧
        2%)是 `soccer_usa_mls`,盘面侧写 `USA_MLS` ⇒ 别名表按 (联赛, 队名) 查,
        **一条都命不中**,而归一看起来还是「修好了」(日志绿、测试绿)。
        """
        from nutmeg.v4.observation.odds_snapshots import record_row_snapshot
        db = tmp_path / "o.db"
        assert record_row_snapshot(db, self._row(
            "Charlotte FC", "LA Galaxy", league="soccer_usa_mls"))
        assert sqlite3.connect(db).execute(
            "SELECT league, home_team, away_team FROM odds_snapshots").fetchone() == (
            "USA_MLS", "Charlotte", "Los Angeles Galaxy")

    def test_unknown_league_passes_through(self, tmp_path):
        """认不出的 league 原样留着 —— 同「表里没有的队名不猜」一条纪律。"""
        from nutmeg.v4.data.odds_source_aliases import canonical_league
        assert canonical_league("soccer_made_up_liga") == "soccer_made_up_liga"
        assert canonical_league("USA_MLS") == "USA_MLS"
        assert canonical_league(None) is None

    def test_sport_key_reverse_lookup_is_unambiguous(self):
        """反查 sport_key→V4 码必须 1:1。一对多就是**猜**,不是解析。

        实测 30 条 0 个一对多;新增 SPORT_KEYS 条目若撞车,这里先红。
        """
        import collections

        from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
        inv = collections.Counter(SPORT_KEYS.values())
        dup = {k: n for k, n in inv.items() if n > 1}
        assert not dup, f"sport_key 反查一对多 ⇒ canonical_league 会猜错:{dup}"
