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


class TestEveryServedLeagueHasBothTracks:
    """🚨 **分母护栏**(2026-08-17)。

    `TestEnToCnCoverage` 已经存在,而且它守的正是这个族(比甲)——
    但它的分母是 `_SP_CALC_LEAGUES`(**标准模式板**)。
    `JPN_J2` 是**市场模式**赛事,压根不在它的视野里 ⇒ 缺了 `JPN_J2 → 日乙` 这条映射
    整整没人发现,后果是:

        is_domestic_club_league("JPN_J2") = True   (EN 轨走竞赛注册表)
        is_domestic_club_league("日乙")    = False  (CN 轨走 allowlist,落 unknown)

    **同一个联赛按写法落进不同层**,校准报表把日乙的行归进「大赛」。

    ⭐ 这是本会话第三次栽在**分母**上:
      ① 计数断言数「我修了几处」而不是「存在几处」
      ② 调用点分母键用 (端点, 函数名) ⇒ 同函数第二个 fetch 折叠
      ③ 本条 —— 护栏的分母只有一块板
    ⇒ 分母必须是「**我们实际会拿到数据的全部联赛**」= 两块板的并集。
    """

    @staticmethod
    def _served():
        from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS, _SP_CALC_LEAGUES
        return sorted(set(_SP_CALC_LEAGUES) | set(_CUP_MARKET_COMPETITIONS))

    def test_the_denominator_is_both_boards_not_one(self):
        """前提自检:并集必须**真的大于**任一块板,否则本类退化成已有的那条。"""
        from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS, _SP_CALC_LEAGUES
        served = set(self._served())
        assert len(served) > len(set(_SP_CALC_LEAGUES)), "并集没比标准板大 —— 分母没扩展"
        assert len(served) > len(set(_CUP_MARKET_COMPETITIONS)), "并集没比市场板大"

    #: 已知缺中文映射的赛事(2026-08-17 钉)。**潜伏,今天零实害。**
    #:
    #: 实测:这 13 项在 `jingcai_sp` 里**一条中文行都没有** —— 竞彩从没上架过
    #: (或我们没以中文捕获过)。阳性对照确认查询有效:同一 join 对
    #: JPN_J1→日职(484 行)、FIN_VEIKKAUSLIIGA→芬超(5,926)、
    #: KOR_K_LEAGUE_1→韩职(2,932)全部命中。⇒「空」是真的空,不是查询坏了。
    #:
    #: ⛔ **为什么不现在补上**:补中文名必须有证据。这 13 项拿不到任何中文侧样本,
    #:    照英文猜译名是本仓红线(**错映射是静默污染,比缺映射更坏**)。
    #: ⭐ 正确的补法是**等它自己送上门**:竞彩首次上架时,`check_league_labels`
    #:    探针会以 `unknown` 报出**真实的中文串** —— 那才是证据。
    #:    这和「forward-only 源识别当天就建」是同一条纪律的两面。
    #: ⚠️ 注意 `DNK_SUPERLIGA` 在列 —— 它正是 `classify_league` docstring 里点名的
    #:    那个活例,存在至少三个月没人补,因为老护栏的分母看不见它。
    #: ⭐ 2026-09-01 —— 13 个里补掉 9 个,**全部照档案实证**(⛔ 无一条意译):
    #:    COPPA_ITALIA「意大利杯」777场+皇冠25+今日在售6 · DFB_POKAL「德国杯」837+23
    #:    · FAC「英足总杯」2085+53 · UECL「欧协联」1366+30 · COUPE_DE_FRANCE「法国杯」714+26
    #:    · WC_QUAL_UEFA「欧预赛」1279 · EURO「欧洲杯」602 · AUS_A_LEAGUE「澳超」5378+165
    #:    · COPA_DEL_REY 两源写法不同(竞彩「西国王杯」786 / 皇冠「国王杯」27)⇒
    #:      取竞彩口径作规范形,皇冠那个进 `_CN_SYNONYM`(同「日天皇杯/天皇杯」)。
    #: ⛔ 剩下 4 个**档案里零实证**,故意留缺口 —— 等竞彩上架、探针以 `unknown`
    #:    报出真实中文串那天再补。`DNK_SUPERLIGA` 仍在列(它就是那个活例)。
    _KNOWN_CN_GAPS = frozenset({
        "DNK_SUPERLIGA", "SCO_PREMIERSHIP", "SUI_SUPER_LEAGUE", "TUR_SUPER_LIG",
    })

    def test_no_new_league_loses_its_cn_mapping(self):
        """每个会拿到数据的联赛都必须有中文映射 —— 没有 ⇒ CN 轨落 unknown。

        已知缺口见 `_KNOWN_CN_GAPS`(带证据与理由)。**新增**的缺口打红。
        """
        from nutmeg.v4.data.league_labels import _EN_TO_CN
        missing = {lg for lg in self._served() if lg not in _EN_TO_CN}
        new = sorted(missing - self._KNOWN_CN_GAPS)
        assert not new, (
            f"🚨 新增赛事没有中文映射:{new}\n"
            f"   ⇒ cron 写中文的那些行会在 CN 轨落 `unknown`,掉出 P3 计数/校准分层。\n"
            f"   补映射**必须有中文侧证据**(⛔ 绝不照英文猜译名);拿不到证据就登记进"
            f" `_KNOWN_CN_GAPS` 并写明为什么。")

    def test_the_known_gap_list_does_not_go_stale(self):
        """清单里已经补上的要删掉 —— 陈旧的豁免名单会掩护真缺口。

        (老护栏留了三个月的 `DNK_SUPERLIGA` 就是这么活下来的,只是换了个机制。)
        """
        from nutmeg.v4.data.league_labels import _EN_TO_CN
        missing = {lg for lg in self._served() if lg not in _EN_TO_CN}
        stale = sorted(self._KNOWN_CN_GAPS - missing)
        assert not stale, f"这些已经有中文映射了,请从 `_KNOWN_CN_GAPS` 删掉:{stale}"

    def test_both_tracks_classify_every_served_league_the_same(self):
        """⭐ **真正的不变式**:同一个联赛,两种写法必须落进同一层。

        这条比「有没有映射」更强 —— 映射存在但两轨判定不同,同样会让一个联赛
        按写法分裂(而且更难发现,因为没有 `unknown` 可以报)。
        """
        from nutmeg.v4.data.league_labels import _EN_TO_CN, classify_league
        bad = []
        for en in self._served():
            cn = _EN_TO_CN.get(en)
            if cn is None:
                continue                       # 上一条负责报它
            if classify_league(en) != classify_league(cn):
                bad.append(f"{en}={classify_league(en)} vs {cn}={classify_league(cn)}")
        assert not bad, "🚨 两轨判定不一致(同一联赛按写法分裂):\n  " + "\n  ".join(bad)

    def test_j2_specifically(self):
        """2026-08-17 的那个活例 —— 留个具名的锚,便于回归时一眼认出。

        证据(不照名字猜):库里 8 行的队伍是 Omiya Ardija / Albirex Niigata /
        Montedio Yamagata / Tochigi City / Tokushima Vortis / Sagan Tosu /
        Blaublitz Akita / Kataller Toyama —— 全是 J2 俱乐部。
        """
        from nutmeg.v4.data.league_labels import classify_league, is_domestic_club_league
        assert classify_league("JPN_J2") == "domestic"
        assert classify_league("日乙") == "domestic"
        assert is_domestic_club_league("日乙") is True

    def test_afc_elite_is_excluded_not_unknown(self):
        """亚冠精英 = 洲际俱乐部杯赛 ⇒ `excluded`(不是 `unknown`,也不是 `domestic`)。

        证据:库里那 2 行是 Gangwon FC(韩)vs Gamba Osaka(日)—— 跨国俱乐部对阵,
        不可能是任何一国的国内联赛。与 解放者杯 / 欧超杯 同族。
        """
        from nutmeg.v4.data.league_labels import classify_league
        assert classify_league("亚冠精英") == "excluded"
