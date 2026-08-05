"""联赛标签双轨:补漏 + 探针 + 回填(owner 2026-08-05)。

## 起因

我先跟 owner 说「`jingcai_sp.league` 两套词汇会让读取方静默漏一半」。审计之后
这句话**部分是错的**:12 个绕过 `canonical_league` 的读取方**没有一个**在 SQL 里
按 league 过滤或分组 —— 它们只是把 label 透传。线上没有因此算错的地方。

真会出错的是**临时查询**,而我自己当天就踩了:拿 13 个 V4 代码查 `jingcai_sp`
得到 0 行,而 cron 写的是中文,86% 的行根本没被问到。**0 行长得和「没有数据」
一模一样**。同族见 [[health-check-guardrails]] 的「零新增 ≠ 扫完了」。

## 审计翻出来的真 bug

`_EN_TO_CN` 漏了 `BEL_PRO_LEAGUE`:
  · 生产 artifact `v4_model_cat/team_state.json` 有 14 个联赛(含它),
    而本表的注释说自己取自「v4_model ∪ v4_model_cat」—— 并集就是 14,表里只有 13。
  · 后果:中文轨 `classify_league('比甲')` → `unknown` → `is_domestic_club_league`
    False → 比甲的 cron 行整个掉出 δ 的 P3 预注册计数。
  · 这正是 `classify_league` docstring 里拿丹超举的那个「活例」—— 活例本身就在
    表里躺着,没人发现。**因为设计好的 unknown 警报从来没接线。**

⇒ 本文件最要紧的是 `TestTableCannotDriftFromProduction`:表是手工推导的,
所以它**必然**会再漂一次。守住推导关系,而不是守住当前这 14 个字面量。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.cli.backfill_league_labels import TABLES, plan
from nutmeg.v4.cli.backfill_league_labels import main as backfill_main
from nutmeg.v4.cli.data_freshness import _LEAGUE_TRACK_TABLES, check_league_labels
from nutmeg.v4.data.league_labels import (
    _EN_TO_CN,
    TRAINED_LEAGUES_CN,
    audit_label_tracks,
    canonical_league,
    classify_league,
    is_domestic_club_league,
    league_filter_variants,
)

REPO = Path(__file__).resolve().parents[2]


class TestTableCannotDriftFromProduction:
    """⭐ 结构性守卫 —— 比「补上比甲」本身重要。

    表当初就是照 artifact 手抄的,抄漏了一个。再抄一次还会漏。所以钉的是
    **推导关系**(表 ⊇ 生产在用的联赛集),不是当前这 14 个字面量。
    """

    def test_covers_every_league_the_model_board_serves(self):
        from nutmeg.v4.api.routes import _SP_CALC_LEAGUES
        missing = [lg for lg in _SP_CALC_LEAGUES if lg not in _EN_TO_CN]
        assert not missing, (
            f"标准模式在服务这些联赛,但 _EN_TO_CN 不认识它们的 EN 代码: {missing}。"
            f"cron 写的中文行会掉出按人口的计数(比甲 2026-08-05 就是这么漏的)")

    def test_covers_every_league_in_the_production_artifact(self):
        """表自己的注释说取自「v4_model ∪ v4_model_cat 的 team_state」。
        那就按这句话验 —— 注释和它产出的表对不上,正是当初那个 bug。"""
        union: set[str] = set()
        for d in ("data/v4_model_cat", "data/v4_model"):
            p = REPO / d / "team_state.json"
            if p.exists():
                union |= {k for k in json.loads(p.read_text()) if k.isascii() and k.isupper()}
        if not union:
            pytest.skip("无 artifact(CI 环境)")
        missing = sorted(union - set(_EN_TO_CN))
        assert not missing, f"artifact 训练面里有,而 _EN_TO_CN 没有: {missing}"

    def test_trained_set_is_exactly_the_table_minus_non_leagues(self):
        """`TRAINED_LEAGUES_CN` 是**手写**的第二份清单 ⇒ 它也会漂。
        钉死它和 `_EN_TO_CN` 的关系:训练面 = 表里的国内联赛。"""
        from nutmeg.v4.api.routes import _SP_CALC_LEAGUES
        served = {_EN_TO_CN[lg] for lg in _SP_CALC_LEAGUES}
        assert served <= TRAINED_LEAGUES_CN, (
            f"服务中的联赛不在训练面清单里: {sorted(served - TRAINED_LEAGUES_CN)}")
        # ⚠️ 反向**不**要求相等:日职在两个 artifact 的 team_state 里,属于训练面;
        # 服务侧 V12 W7 把它移出模型盘走市场模式。两个集合本就不必相等 ——
        # 我差点拿服务集去删训练集。
        assert "日职" in TRAINED_LEAGUES_CN


class TestBelgianLeagueNoLongerFallsOutOfCounts:
    def test_cn_track_classifies_as_domestic(self):
        assert classify_league("比甲") == "domestic"
        assert is_domestic_club_league("比甲") is True

    def test_both_tracks_agree(self):
        """EN 轨走注册表、中文轨走 allowlist —— 两轨对同一个联赛必须同答案,
        否则同一场比赛按谁写的入库决定算不算数。"""
        assert classify_league("BEL_PRO_LEAGUE") == classify_league("比甲")

    def test_brazil_cup_is_excluded_not_unknown(self):
        """探针上线第一天报出来的。国内**杯赛**:不是国家队、不是洲际杯,
        但同样不在 δ 的联赛人口里(结构对应物 COPA_DEL_REY = club_cup)。"""
        assert classify_league("巴西杯") == "excluded"
        assert is_domestic_club_league("巴西杯") is False
        assert classify_league("巴甲") == "domestic", "别把联赛连坐进去"


class TestFilterVariants:
    def test_one_vocabulary_reaches_the_other(self):
        """⭐ 这条就是我 2026-08-05 踩的坑的回归测试。"""
        v = league_filter_variants(["GER_2_BUNDESLIGA"])
        assert "德乙" in v and "GER_2_BUNDESLIGA" in v
        assert league_filter_variants(["德乙"]) == v, "两种写法必须展开成同一个集合"

    def test_a_bare_string_is_rejected_not_silently_iterated(self):
        """传字符串 → 逐字符迭代 → 退化成子串判断。
        同 [[health-check-guardrails]] 里 `leagues="all"` 那个洞。"""
        with pytest.raises(TypeError):
            league_filter_variants("德乙")

    def test_unknown_label_maps_to_itself_not_to_nothing(self):
        """fail-open:没见过的标签至少还能查到它自己,不会静默变成空集合。"""
        assert league_filter_variants(["丹超"]) == {"丹超"}


class TestAuditDetectsBothDiseases:
    def test_split_is_reported_with_all_spellings(self):
        a = audit_label_tracks(["芬超", "FIN_VEIKKAUSLIIGA", "德乙"])
        assert a["split"] == [("芬超", ["FIN_VEIKKAUSLIIGA", "芬超"])]

    def test_no_split_when_single_track(self):
        assert audit_label_tracks(["芬超", "德乙", "英超"])["split"] == []

    def test_unknown_is_reported(self):
        assert audit_label_tracks(["德乙", "丹超"])["unknown"] == ["丹超"]

    def test_known_labels_are_not_reported_as_unknown(self):
        assert audit_label_tracks(["德乙", "比甲", "世界杯", "巴西杯"])["unknown"] == []

    def test_bare_string_rejected(self):
        with pytest.raises(TypeError):
            audit_label_tracks("德乙")


def _mk_db(tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    """(league, match_date, home, away) → 一个最小的 jingcai_sp 库。

    UNIQUE 键照抄真库:``(match_date, home_team, away_team, market)`` —— 见
    `test_league_is_not_part_of_any_unique_key`,那条拿**真 schema** 验这件事。
    """
    tmp_path.mkdir(parents=True, exist_ok=True)   # 差分用例传的是子目录
    db = tmp_path / "obs.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE jingcai_sp (
        id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at TEXT NOT NULL,
        source TEXT NOT NULL, league TEXT, match_date TEXT NOT NULL,
        home_team TEXT NOT NULL, away_team TEXT NOT NULL, market TEXT NOT NULL DEFAULT 'had',
        UNIQUE(match_date, home_team, away_team, market))""")
    for lg, d, h, a in rows:
        conn.execute("INSERT INTO jingcai_sp (captured_at, source, league, match_date,"
                     " home_team, away_team) VALUES ('t','s',?,?,?,?)", (lg, d, h, a))
    conn.commit()
    conn.close()
    return db


class TestProbe:
    def test_reports_a_planted_split(self, tmp_path):
        db = _mk_db(tmp_path, [("芬超", "2026-08-01", "A", "B"),
                               ("FIN_VEIKKAUSLIIGA", "2026-08-02", "C", "D")])
        info, alarms = check_league_labels(db)
        assert any("芬超" in a and "劈成" in a for a in alarms), alarms
        assert any("jingcai_sp.league" in i for i in info)

    def test_silent_when_single_track(self, tmp_path):
        db = _mk_db(tmp_path, [("芬超", "2026-08-01", "A", "B"),
                               ("德乙", "2026-08-02", "C", "D")])
        assert check_league_labels(db)[1] == [], "单轨误报 = 老误报的护栏最后会被删掉"

    def test_reports_unknown_label(self, tmp_path):
        db = _mk_db(tmp_path, [("丹超", "2026-08-01", "A", "B")])
        assert any("丹超" in a for a in check_league_labels(db)[1])

    def test_missing_db_is_skipped_not_alarmed(self, tmp_path):
        info, alarms = check_league_labels(tmp_path / "nope.db")
        assert alarms == [] and info, "CI 无 data/ 时不该报警"

    def test_missing_table_is_skipped_not_alarmed(self, tmp_path):
        db = tmp_path / "empty.db"
        sqlite3.connect(db).close()
        assert check_league_labels(db)[1] == []

    def test_probe_and_backfill_watch_the_same_tables(self):
        """探针报了却没工具修 / 有工具却没人报,都是半个闭环。"""
        assert _LEAGUE_TRACK_TABLES == TABLES

    def test_alarm_rides_the_nonzero_exit(self, tmp_path, monkeypatch):
        """报警必须让 `main()` 退出非零 —— cron 链靠它推送。
        只 print 不改退出码 = 警报写在没人看的日志里。

        ⚠️ 第一版是拿子进程跑真 CLI 断言 `returncode == 1` —— **它是空的**:
        临时库里 9 张采集表都不存在、全被判 critical stale,exit 本来就是 1。
        变异「把 label_alarms 从退出条件里删掉」照样绿(2026-08-05 实测)。
        分不出「因为我的报警」和「因为别的报警」= 又一个「分不出没有和没去看」。

        改法:把 `check_freshness` 打桩成空(它**不是**被测对象),让 label_alarms
        成为退出码的唯一可能来源,再用**劈开 vs 单轨**两种输入做差分 —— 只有
        一边非零才算数。
        """
        from nutmeg.v4.cli import data_freshness as df

        monkeypatch.setattr(df, "check_freshness", lambda *a, **k: [])
        split = _mk_db(tmp_path / "s", [("芬超", "2026-08-01", "A", "B"),
                                        ("FIN_VEIKKAUSLIIGA", "2026-08-02", "C", "D")])
        clean = _mk_db(tmp_path / "c", [("芬超", "2026-08-01", "A", "B"),
                                        ("德乙", "2026-08-02", "C", "D")])
        argv = ["--no-quota", "--no-supply", "--porcelain"]
        assert df.main(["--db", str(split), *argv]) == 1, "劈开了却退出 0"
        assert df.main(["--db", str(clean), *argv]) == 0, (
            "单轨也退出非零 ⇒ 这条断言测的不是我的报警")

    def test_probe_can_be_switched_off(self, tmp_path, monkeypatch):
        """`--no-league-labels` 得真能关 —— 开关不生效的探针没法在事故中让路。"""
        from nutmeg.v4.cli import data_freshness as df

        monkeypatch.setattr(df, "check_freshness", lambda *a, **k: [])
        split = _mk_db(tmp_path / "s", [("芬超", "2026-08-01", "A", "B"),
                                        ("FIN_VEIKKAUSLIIGA", "2026-08-02", "C", "D")])
        argv = ["--db", str(split), "--no-quota", "--no-supply", "--porcelain"]
        assert df.main(argv) == 1
        assert df.main([*argv, "--no-league-labels"]) == 0


class TestBackfill:
    def test_league_is_not_part_of_any_unique_key(self):
        """⚠️ 回填「不会撞键」这句话必须**在真 schema 上**验,不能靠推断。
        改 `odds_snapshots` 的队名时撞键是真会发生的(那次要写碰撞跳过);
        这次不会,理由是 league 不在键里 —— 那就把这个理由本身钉住。"""
        db = REPO / "data/v4_observation.db"
        if not db.exists():
            pytest.skip("无观测库")
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            for table, col in TABLES:
                idx = conn.execute(f"PRAGMA index_list({table})").fetchall()
                for row in idx:
                    if not row[2]:                     # 非 UNIQUE 索引不管
                        continue
                    cols = [r[2] for r in conn.execute(f"PRAGMA index_info({row[1]})")]
                    assert col not in cols, (
                        f"{table} 的 UNIQUE 索引 {row[1]} 含 {col} ⇒ 回填可能撞键,"
                        f"得先加碰撞跳过再改")
        finally:
            conn.close()

    def test_dry_run_changes_nothing(self, tmp_path):
        db = _mk_db(tmp_path, [("FIN_VEIKKAUSLIIGA", "2026-08-01", "A", "B")])
        assert backfill_main(["--db", str(db)]) == 0
        conn = sqlite3.connect(db)
        assert conn.execute("SELECT league FROM jingcai_sp").fetchone()[0] == "FIN_VEIKKAUSLIIGA"
        conn.close()

    def test_apply_canonicalises_and_is_idempotent(self, tmp_path):
        db = _mk_db(tmp_path, [("FIN_VEIKKAUSLIIGA", "2026-08-01", "A", "B"),
                               ("芬超", "2026-08-02", "C", "D")])
        assert backfill_main(["--db", str(db), "--apply", "--no-backup"]) == 0
        conn = sqlite3.connect(db)
        try:
            assert {r[0] for r in conn.execute("SELECT league FROM jingcai_sp")} == {"芬超"}
            assert plan(conn) == [], "跑第二遍还有活干 = 不幂等"
        finally:
            conn.close()

    def test_unmapped_labels_are_left_alone(self, tmp_path):
        """fail-open:认不出来的原样不动,由探针报成 unknown 让人来判。
        ⛔ 绝不猜一个规范形填进去 —— 猜错会把两个联赛静默合并。"""
        db = _mk_db(tmp_path, [("丹超", "2026-08-01", "A", "B")])
        backfill_main(["--db", str(db), "--apply", "--no-backup"])
        conn = sqlite3.connect(db)
        assert conn.execute("SELECT league FROM jingcai_sp").fetchone()[0] == "丹超"
        conn.close()

    def test_writer_provenance_is_preserved(self, tmp_path):
        """只改 league。`source` 列是「谁写的」的唯一记录,动它就把溯源弄丢了。"""
        db = _mk_db(tmp_path, [("FIN_VEIKKAUSLIIGA", "2026-08-01", "A", "B")])
        backfill_main(["--db", str(db), "--apply", "--no-backup"])
        conn = sqlite3.connect(db)
        assert conn.execute("SELECT source FROM jingcai_sp").fetchone()[0] == "s"
        conn.close()

    def test_apply_writes_a_backup_by_default(self, tmp_path):
        db = _mk_db(tmp_path, [("FIN_VEIKKAUSLIIGA", "2026-08-01", "A", "B")])
        backfill_main(["--db", str(db), "--apply"])
        assert list(tmp_path.glob("obs.db.bak-*-pre-league-canon")), "没自备份"

    def test_says_it_scanned_when_there_is_nothing_to_do(self, tmp_path, capsys):
        """「零改动」必须说清是**扫过了**才零。同「零新增 ≠ 扫完了」。"""
        db = _mk_db(tmp_path, [("芬超", "2026-08-01", "A", "B")])
        backfill_main(["--db", str(db)])
        out = capsys.readouterr().out
        assert "无需回填" in out and "jingcai_sp" in out

    def test_canonical_direction_comes_from_the_shared_helper(self, tmp_path):
        """回填方向 = `canonical_league`,不另写一套映射(两套一定会分叉)。"""
        db = _mk_db(tmp_path, [("UEL", "2026-08-01", "A", "B")])
        conn = sqlite3.connect(db)
        try:
            assert [c[3] for c in plan(conn)] == [canonical_league("UEL")]
        finally:
            conn.close()
