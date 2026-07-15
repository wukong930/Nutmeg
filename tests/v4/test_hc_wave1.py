"""体检 Wave 1(2026-07-15)回归锁 — sink 级 upsert 收口 / D7 时代过滤 / 哨兵自盲。

报告 = docs/health_check_2026-07-15.md「修复波次 · Wave 1」。每个测试对应一个
以前会静默吃数据的洞;红了 = 有人把洞挖回来了。
"""
from __future__ import annotations

import datetime as dt
import inspect
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------- W1-1 upsert 收口


class TestWcLogIdentityRefresh:
    def _pred(self, **kw):
        base = dict(fixture_id=7, kickoff_utc="2026-07-20T18:00:00+00:00",
                    home_team="Mexico", away_team="Ghana", p_home=0.5, p_draw=0.3,
                    p_away=0.2, source="blend")
        base.update(kw)
        return base

    def test_identity_columns_follow_source(self, tmp_path):
        from nutmeg.v4.observation.wc_log import record_wc_prediction
        db = tmp_path / "wc.db"
        record_wc_prediction(db, self._pred(), season=2026)
        # AF 改期跨日 + 改名:身份列必须跟着最新预测走(以前冻结在首见值,
        # settle 镜像用旧身份写 match_outcomes → rec 永久 still_unknown)
        record_wc_prediction(
            db, self._pred(kickoff_utc="2026-07-21T02:00:00+00:00",
                           home_team="México", away_team="Ghana"), season=2026)
        con = sqlite3.connect(db)
        md, h = con.execute(
            "SELECT match_date, home_team FROM wc_predictions").fetchone()
        assert md == "2026-07-21"
        assert h == "México"

    def test_settled_columns_survive_rerecord(self, tmp_path):
        from nutmeg.v4.observation.wc_log import (
            record_wc_prediction,
            settle_wc_prediction,
        )
        db = tmp_path / "wc.db"
        record_wc_prediction(db, self._pred(), season=2026)
        settle_wc_prediction(db, 7, home_goals=2, away_goals=1)
        record_wc_prediction(db, self._pred(p_home=0.55), season=2026)  # 日常 cron 重跑
        con = sqlite3.connect(db)
        row = con.execute(
            "SELECT home_goals, outcome, p_home FROM wc_predictions").fetchone()
        assert row[0] == 2 and row[1] == 0, "结算列不在 INSERT 列表 = 重记录不许碰"
        assert row[2] == 0.55


class TestPinnacleCloseNullFreeze:
    def test_null_snapshot_row_unfreezes_and_commence_propagates(self, tmp_path):
        from nutmeg.v4.observation import pinnacle_close_history as pch
        db = tmp_path / "p.db"
        row = {"home_team": "X", "away_team": "Y",
               "commence_time": "2026-07-20T10:00:00Z", "p_home": 2.0}
        assert pch.record_close(db, row, snapshot_utc="s1") == 1
        con = sqlite3.connect(db)
        con.execute("UPDATE pinnacle_close_history SET snapshot_utc=NULL")
        con.commit()
        row2 = {"home_team": "X", "away_team": "Y",
                "commence_time": "2026-07-20T11:30:00Z", "p_home": 2.1}
        pch.record_close(db, row2, snapshot_utc="s2")
        got = con.execute("SELECT snapshot_utc, commence_utc, p_home "
                          "FROM pinnacle_close_history").fetchone()
        # 修前:NULL > 比较永假 → 行永久冻结;commence_utc 不在 SET → 改时刻不传播
        assert got == ("s2", "2026-07-20T11:30:00Z", 2.1)

    def test_older_snapshot_still_rejected(self, tmp_path):
        from nutmeg.v4.observation import pinnacle_close_history as pch
        db = tmp_path / "p.db"
        row = {"home_team": "X", "away_team": "Y",
               "commence_time": "2026-07-20T10:00:00Z", "p_home": 2.0}
        pch.record_close(db, row, snapshot_utc="s5")
        pch.record_close(db, dict(row, p_home=9.9), snapshot_utc="s2")  # 更早的快照
        con = sqlite3.connect(db)
        assert con.execute("SELECT p_home FROM pinnacle_close_history").fetchone()[0] == 2.0


class TestCrownFullColumnUpsert:
    def _rec(self, **kw):
        base = dict(match_id="A1", date="2026-07-15", home_zh="甲", away_zh="乙",
                    crown_1x2=(1.8, 3.5, 4.2), rangqiu=-1,
                    kickoff_utc="2026-07-15T12:00:00")
        base.update(kw)
        return base

    def test_rangqiu_survives_none_recapture(self, tmp_path):
        from nutmeg.v4.observation import crown_close_history as cch
        db = tmp_path / "c.db"
        cch.record_match(db, self._rec())
        cch.record_match(db, self._rec(rangqiu=None, crown_1x2=(1.9, 3.4, 4.0)))
        con = sqlite3.connect(db)
        rq, ch = con.execute(
            "SELECT rangqiu, c_home FROM crown_close_history").fetchone()
        assert rq == -1, "当天上午亲手漏掉的列:None 再捕不许抹线(体检 R2.5 活标本)"
        assert ch == 1.9

    def test_second_unique_migrates_match_id(self, tmp_path):
        from nutmeg.v4.observation import crown_close_history as cch
        db = tmp_path / "c.db"
        assert cch.record_match(db, self._rec()) == 1
        # 500 同一场换发新 match_id:修前 IntegrityError 被吃、行每次重抓重复丢
        assert cch.record_match(db, self._rec(match_id="B2")) == 1
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT match_id FROM crown_close_history").fetchall()
        assert rows == [("B2",)]


class TestScoreEvSettlePreserved:
    def test_rerecord_keeps_settled_columns(self, tmp_path, monkeypatch):
        from nutmeg.v4.cli import score_ev_forward as sef
        db = str(tmp_path / "s.db")
        with sef._conn(db) as conn:
            conn.execute(
                "INSERT INTO score_ev_flags (fixture_id,league,home,away,kickoff_utc,"
                "match_date,pred_home,pred_away,model_p,odds,book,ev,captured_at,"
                "actual_home,actual_away,won,settled_at) "
                "VALUES (1,'L','H','A','k','2026-07-14',2,1,0.1,8.0,'crown',0.06,'t0',"
                "2,1,1,'t1')")
            conn.commit()

        fx = {"fixture": {"id": 1, "status": {"short": "NS"},
                          "date": "2026-07-16T12:00:00+00:00"},
              "league": {"name": "L"},
              "teams": {"home": {"name": "H"}, "away": {"name": "A"}}}
        import nutmeg.v4.data.sources.api_football as af
        monkeypatch.setattr(af, "fetch_fixtures_for_date", lambda d, refresh: [fx])
        monkeypatch.setattr(af, "fetch_odds", lambda fid, refresh: {})
        # 改期重赛剧本:同一 (fixture,比分) 又被标 +EV → 撞已结算行
        monkeypatch.setattr(sef, "ev_flags", lambda blob, **kw: [
            {"home": 2, "away": 1, "model_p": 0.12, "odds": 7.5, "book": "crown",
             "ev": 0.08, "prior_src": "grid"}])
        args = SimpleNamespace(db=db, date="2026-07-16", min_ev=0.05, max_odds=26.0,
                               rho=None, max_fixtures=10)
        assert sef.do_record(args) == 0
        con = sqlite3.connect(db)
        won, odds = con.execute(
            "SELECT won, odds FROM score_ev_flags WHERE fixture_id=1").fetchone()
        assert won == 1, "修前 INSERT OR REPLACE 把已结算行的 won/settled_at 冲成 NULL"
        assert odds == 7.5, "捕获列仍应更新(upsert 只保结算四列)"


class TestJingcaiSpHandicapCoalesce:
    def test_handicap_survives_none_recapture(self, tmp_path):
        from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp
        db = tmp_path / "j.db"
        kw = dict(match_date="2026-07-16", home_team="H", away_team="A",
                  market="hhad", jc_home=1.8, jc_draw=3.5, jc_away=4.0)
        record_jingcai_sp(db, source="cron", handicap_home=-1, **kw)
        record_jingcai_sp(db, source="manual", handicap_home=None, **kw)  # 手填 re-pin
        con = sqlite3.connect(db)
        assert con.execute(
            "SELECT handicap_home FROM jingcai_sp").fetchone()[0] == -1


class TestPredictionLogSinkGuards:
    def _pred(self, **kw):
        base = dict(date="2026-07-16", league="EPL", home_team="H", away_team="A",
                    kickoff_utc="2026-07-16T18:00:00", market_mode=False,
                    p_home_1x2=0.5, p_draw_1x2=0.3, p_away_1x2=0.2,
                    psc_home=1.9, psc_draw=3.6, psc_away=4.1)
        base.update(kw)
        return base

    def test_psc_survives_pinnacle_outage_relog(self, tmp_path):
        from nutmeg.v4.observation.prediction_log import (
            fetch_league_predictions,
            record_league_prediction,
        )
        db = str(tmp_path / "o.db")
        record_league_prediction(db, self._pred())
        record_league_prediction(  # Pinnacle 断供窗口的再记录(现在就是这种日子)
            db, self._pred(psc_home=None, psc_draw=None, psc_away=None,
                           kickoff_utc=None, p_home_1x2=0.52))
        row = fetch_league_predictions(db)[0]
        assert row["psc_home"] == 1.9, "sharp 基准不许被 NULL 冲掉(sink 级守卫)"
        assert row["kickoff_utc"] == "2026-07-16T18:00:00"
        assert row["p_home"] == 0.52


# ---------------------------------------------------------------- W1-2 时代过滤


class TestEraFilter:
    def test_fetch_defaults_to_current_era(self, tmp_path):
        from nutmeg.v4.observation.prediction_log import (
            fetch_league_predictions as fetch,
        )
        from nutmeg.v4.observation.prediction_log import record_league_prediction
        db = str(tmp_path / "e.db")
        frozen_when = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)  # 冻结盘时代
        record_league_prediction(
            db, dict(date="2026-07-01", league="EPL", home_team="H1", away_team="A1",
                     p_home_1x2=0.4, p_draw_1x2=0.3, p_away_1x2=0.3),
            recorded_at=frozen_when)
        record_league_prediction(
            db, dict(date="2026-07-16", league="EPL", home_team="H2", away_team="A2",
                     p_home_1x2=0.5, p_draw_1x2=0.3, p_away_1x2=0.2))
        assert len(fetch(db)) == 1, "测量读者默认只吃当代(D7 冻结时代污染)"
        assert len(fetch(db, current_era_only=False)) == 2, "考古读全史要显式开"

    def test_auto_calibration_carries_era_bound(self):
        # 行为由上面的 fetch 测试锁;这里锁「两条喂料臂都接了时代下界」的源码事实
        # (竞彩 session 流的行为测试需要三表 fixture,不值得——臂漏接一眼可查)。
        from nutmeg.v4.observation import auto_calibration as ac
        src = inspect.getsource(ac.load_calibration_pairs)
        assert src.count("CURRENT_ARTIFACT_ERA_START") >= 2, (
            "竞彩 session 流与 league_predictions 流必须都卡时代下界 — "
            "只修一臂 = 报告 R2.5 点名的「修坏的那列」模式"
        )


# ---------------------------------------------------------------- W1-3 哨兵自盲


class TestNameSentinelSelfBlind:
    def test_all_days_failed_raises(self):
        from nutmeg.v4.cli.name_sentinel import SentinelBlindError, scan

        def boom(d):
            raise ConnectionError("AF down")
        with pytest.raises(SentinelBlindError):
            scan(days=2, fetch_fixtures=boom, fetch_lookup=lambda k: {},
                 sport_keys={"EPL": "soccer_epl"}, resolve_lid=lambda c: 39)

    def test_main_writes_failure_report_and_exits_1(self, tmp_path, monkeypatch):
        from nutmeg.v4.cli import name_sentinel as ns

        def blind_scan(**kw):
            raise ns.SentinelBlindError("AF fixtures 全数拉取失败(2/2 天)")
        monkeypatch.setattr(ns, "scan", blind_scan)
        report = tmp_path / "r.txt"
        rc = ns.main(["--report", str(report), "--quiet"])
        assert rc == 1
        text = report.read_text()
        assert "⛔" in text and "探测失败" in text, "latest 文件必须写失败,不能停在旧 ✅"

    def test_zero_scanned_is_inconclusive_not_green(self):
        from nutmeg.v4.cli.name_sentinel import format_report
        out = format_report([], 0, 0, "2026-07-15 12:00")
        assert "✅" not in out
        assert "无结论" in out

    def test_partial_failure_still_scans(self):
        from nutmeg.v4.cli.name_sentinel import scan
        calls = {"n": 0}

        def flaky(d):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("blip")
            return []
        mismatches, nc, scanned = scan(
            days=2, fetch_fixtures=flaky, fetch_lookup=lambda k: {},
            sport_keys={"EPL": "soccer_epl"}, resolve_lid=lambda c: 39)
        assert mismatches == []  # 单日失败可容,不升级


# ---------------------------------------------------------------- W1-4 供应链探针


class TestModelSupplyChainProbe:
    def test_fresh_artifact_no_alarm(self, tmp_path):
        from nutmeg.v4.cli.data_freshness import check_model_supply_chain
        art = tmp_path / "art"
        art.mkdir()
        (art / "metadata.json").write_text('{"trained_at_utc": "2026-07-10T07:00:00"}')
        info, alarms = check_model_supply_chain(
            dt.date(2026, 7, 15), artifact_dir=art,
            sources_dir=tmp_path / "nope", external_dir=tmp_path / "nope2")
        assert alarms == []
        assert any("5d" in line for line in info)

    def test_stale_artifact_alarms(self, tmp_path):
        from nutmeg.v4.cli.data_freshness import check_model_supply_chain
        art = tmp_path / "art"
        art.mkdir()
        (art / "metadata.json").write_text('{"trained_at_utc": "2024-08-01T00:00:00"}')
        _, alarms = check_model_supply_chain(
            dt.date(2026, 7, 15), artifact_dir=art,
            sources_dir=tmp_path / "nope", external_dir=tmp_path / "nope2")
        assert alarms and "重训" in alarms[0], "724 天冻结的病根:artifact 超龄必须响"

    def test_missing_dirs_skip_quietly(self, tmp_path):
        # CI/测试环境无 data/ — 缺目录 = 跳过,绝不假报警
        from nutmeg.v4.cli.data_freshness import check_model_supply_chain
        info, alarms = check_model_supply_chain(
            dt.date(2026, 7, 15), artifact_dir=tmp_path / "a",
            sources_dir=tmp_path / "b", external_dir=tmp_path / "c")
        assert alarms == []
        assert any("不存在" in line for line in info)

    def test_empty_source_tree_alarms(self, tmp_path):
        from nutmeg.v4.cli.data_freshness import check_model_supply_chain
        src = tmp_path / "src"
        src.mkdir()  # 目录在、CSV 全无 = 训练无粮
        _, alarms = check_model_supply_chain(
            dt.date(2026, 7, 15), artifact_dir=tmp_path / "nope", sources_dir=src,
            external_dir=tmp_path / "nope2")
        assert alarms and "CSV" in alarms[0]


# ---------------------------------------------------------------- W1-5 计数曝光(源码锁)


class TestCountersPresent:
    """行为需要重 fixture 的计数点,锁源码事实:计数/警告语句在场。"""

    def test_persist_counts_served_defaults(self):
        import nutmeg.v4.model.persist as persist
        src = inspect.getsource(persist)
        assert "unknown_teams" in src and "_REST_DAYS_OOD" in src
        assert "served-with-defaults" in src

    def test_measurement_clis_log_fit_drops(self):
        import nutmeg.v4.cli.clv_ledger as clv
        import nutmeg.v4.cli.jingcai_staleness as js
        import nutmeg.v4.observation.handicap_triples as ht
        for mod in (clv, js, ht):
            src = inspect.getsource(mod)
            assert "拟合失败" in src, f"{mod.__name__} 的 fit-drop 必须留痕"

    def test_settle_counts_join_misses(self):
        from nutmeg.v4.observation.prediction_log import settle_league_predictions
        src = inspect.getsource(settle_league_predictions)
        assert "join_miss" in src


# ---------------------------------------------------------------- W1-6 运维脚本


class TestOpsScripts:
    def test_teardown_excludes_trickle(self):
        sh = Path("scripts/teardown_local_pipeline.sh").read_text()
        assert "TEARDOWN_EXCLUDE" in sh
        assert "com.nutmeg.jingcai_history_trickle" in sh, (
            "campaign job 误删 = setup 装不回、回填永久中断(F-TRICKLE)"
        )

    def test_setup_refuses_when_jobs_disabled(self):
        sh = Path("scripts/setup_local_pipeline.sh").read_text()
        assert "print-disabled" in sh
        assert "resume_odds_crons.sh" in sh, (
            "重跑 setup 不许复活被有意暂停的 odds cron(F-RERUN)"
        )
