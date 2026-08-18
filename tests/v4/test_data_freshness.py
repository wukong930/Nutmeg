"""Tests for nutmeg-data-freshness — the capture-table leak sentinel."""
from __future__ import annotations

import re
import sqlite3
from datetime import date

from nutmeg.v4.cli.data_freshness import (
    CAPTURE_TABLES,
    HEARTBEAT_FILENAME,
    SISTER_CAPTURE_TABLES,
    check_freshness,
    main,
)

TODAY = date(2026, 6, 17)


def _entry_key(table: str, where: str | None, name: str | None) -> str:
    return name or table


def _mk_db(tmp_path, rows: dict[str, list[str]], name: str = "obs.db"):
    """Build a temp observation DB (+ sister DBs) with the capture streams.

    `rows` is keyed by DISPLAY name (entry name or table). Sub-stream inserts
    also satisfy their WHERE filter (e.g. source='closing' rows get that col).
    """
    db = tmp_path / name
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    cols_by_table: dict[str, set[str]] = {}
    for table, col, _maxd, _crit, _note, where, _nm in CAPTURE_TABLES:
        cols_by_table.setdefault(table, set()).add(col)
        for wc in re.findall(r"(\w+)\s*(?:=|IS)", where or ""):
            cols_by_table[table].add(wc)
    for table, cols in cols_by_table.items():
        conn.execute(
            f"CREATE TABLE {table} ({', '.join(f'{c} TEXT' for c in sorted(cols))})"
        )
    for table, col, _maxd, _crit, _note, where, nm in CAPTURE_TABLES:
        key = _entry_key(table, where, nm)
        extra = dict(re.findall(r"(\w+)\s*=\s*'([^']*)'", where or ""))
        # 2026-08-18 — 支持 `X IS NOT NULL` 形态的子流过滤(如 open 心跳的
        # `jc_open_home IS NOT NULL`)。不塞非空值 ⇒ 该子流在合成库里**恒 0 行**,
        # 条目会被当成「表里没有数据」而不是「新鲜」⇒ `_all_today()` 造不出全绿。
        for _c in re.findall(r"(\w+)\s+IS\s+NOT\s+NULL", where or "", re.I):
            extra.setdefault(_c, "1")
        for v in rows.get(key, []):
            # ⚠️ `col` 必须**最后**赋值 —— 它才是这条被量的时间戳,不能被 extra 盖掉
            data = {**extra, col: v}
            conn.execute(
                f"INSERT INTO {table} ({','.join(data)}) "
                f"VALUES ({','.join('?' * len(data))})",
                tuple(data.values()),
            )
    conn.commit()
    conn.close()
    # Sister forward-only DBs live next to the main DB.
    for db_file, table, col, _maxd, _crit, _note in SISTER_CAPTURE_TABLES:
        sef = tmp_path / db_file
        if sef.exists():
            sef.unlink()
        sconn = sqlite3.connect(sef)
        sconn.execute(f"CREATE TABLE {table} ({col} TEXT)")
        for v in rows.get(table, []):
            sconn.execute(f"INSERT INTO {table} ({col}) VALUES (?)", (v,))
        sconn.commit()
        sconn.close()
    return db


def _all_today():
    fresh = {
        _entry_key(t, w, nm): ["2026-06-17"]
        for t, _c, _m, _cr, _n, w, nm in CAPTURE_TABLES
    }
    for _f, table, _c, _m, _cr, _n in SISTER_CAPTURE_TABLES:
        fresh[table] = ["2026-06-17"]
    return fresh


# ⚠️ 下面每个 main() 调用都必须带 --no-quota,别删。
# 2026-07-15:`main()` 的返回码是 `1 if (crit_stale or quota_alarms) else 0`,而配额探针
# 打的是【线上】AF/Odds API。于是这些本该只测「新鲜度逻辑」的单元测试被真实世界耦合了:
#   · Odds API 月配额耗尽(credit 0)那天,断言 ==0 的两个直接转红 —— 跟被测逻辑无关;
#   · 更糟的是断言 ==1 的那几个会【因为配额告警而"通过"】,不是因为它们造的陈旧数据
#     ——即静默变成空测试,看着绿其实什么都没守。
# --no-quota 把探针关掉 → 每个测试只对自己声称在测的东西负责。配额本身该由 cron/
# health_check 在真实环境里报,不该由单元测试的返回码承担。
#
# 2026-08-05 同理补上 `--no-supply`:本文件测的是 **DB 表新鲜度**,但 `main()` 的
# 返回码把**生产**供应链探针也算进去了(artifact / 源树 / 未吸收比赛,全走真实
# 路径)。这层耦合一直是隐雷 —— 生产 artifact 哪天熬过 120 天红线,这里就会红,
# 而红的原因和本文件测的东西毫无关系。新加的「未吸收比赛」探针把它提前引爆了:
# 别的测试用裸 `os.environ[...]` 把 `NUTMEG_V4_ARTIFACT_PATH` 泄漏成 `data/v4_model`
# (遗留 LGB,cutoff 2025-06-01),对着生产源树落后 4871 场 ⇒ 报警 ⇒ 退出码 1。
# 症状是**只在跑全套时红、单跑绿**,而红的是另一个文件。
def test_all_fresh_exits_zero(tmp_path):
    db = _mk_db(tmp_path, _all_today())
    statuses = check_freshness(db, today=TODAY)
    assert all(not s.stale for s in statuses)
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota", "--no-supply"]) == 0


def test_critical_stale_exits_one(tmp_path):
    rows = _all_today()
    # Both the whole-table stream AND the closing sub-stream must be old to
    # stale the base entry (sub-stream rows live in the same table).
    rows["odds_snapshots"] = ["2026-06-05"]
    rows["odds_snapshots[closing]"] = ["2026-06-05"]
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots"].stale and by["odds_snapshots"].critical
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota", "--no-supply"]) == 1


def test_closing_substream_stale_behind_fresh_table(tmp_path):
    # 体检 P0-1 regression: other writers (cup_market/predict_log) keep the
    # whole-table max() green while the closing anchor dies. The sub-stream
    # entry must flag it anyway.
    rows = _all_today()
    rows["odds_snapshots"] = ["2026-06-17"]          # live writers, fresh
    rows["odds_snapshots[closing]"] = ["2026-06-05"]  # closing cron dead
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert not by["odds_snapshots"].stale
    assert by["odds_snapshots[closing]"].stale and by["odds_snapshots[closing]"].critical
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota", "--no-supply"]) == 1


def test_jc_open_substream_tracked_separately(tmp_path):
    """整表活着时,open 子流仍能被单独看见(P0-1 的原意)。

    ⚠️ 2026-08-18 改写。本条原来的注释写着:
        「jingcai_sp fresh (capture cron alive) but opened_at stalled
          (**open-SP sub-flow dead**) must flag the [open] stream only」
    —— 那句 `opened_at stalled ⇒ sub-flow dead` **正是被本次改动推翻的推断**。
    `opened_at` 是 set-once,它停 = 竞彩没上新场,而 cron 可能一直活着
    (2026-08-18 实测:那天红灯诊断「cron 可能静默死了」是错的)。
    ⇒ 子流可见性这个原意保留,但「哪一条才是 CRITICAL」交给下面两条专门的测试。
    """
    rows = _all_today()
    rows["jingcai_sp"] = ["2026-06-17"]
    rows["jingcai_sp[open]"] = ["2026-06-01"]
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert not by["jingcai_sp"].stale, "整表被子流的陈旧带红了 —— 子流没切开"
    assert by["jingcai_sp[open]"].stale, "子流停了却没被看见 —— P0-1 的病根回来了"


def test_listing_gap_alone_does_not_fail_the_gate(tmp_path):
    """🚨 **2026-08-18 那次假红的回归测试。**

    竞彩三天没上新场(周六→周二是常态)+ cron 一直在跑
    ⇒ `[open]` 报 warn,`[open-heartbeat]` 绿 ⇒ **体检整体不该失败**。

    旧设计在这个场景下 CRITICAL 红,并把原因写成「捕获 cron 可能静默死了」——
    诊断和事实相反。
    """
    rows = _all_today()
    rows["jingcai_sp[open]"] = ["2026-06-14"]          # 上新场停 3 天(常态空档)
    rows["jingcai_sp[open-heartbeat]"] = ["2026-06-17"]  # cron 今天还在跑
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert not by["jingcai_sp[open-heartbeat]"].stale, "心跳不该红 —— cron 活着"
    assert not by["jingcai_sp[open]"].critical, "上新场那条又变回 CRITICAL 了"
    assert main(["--db", str(db), "--today", "2026-06-17",
                 "--no-quota", "--no-supply"]) == 0, (
        "🚨 常态空档让体检失败了 —— 这正是 2026-08-18 的假红")


def test_a_truly_dead_open_cron_still_fails_the_gate(tmp_path):
    """⭐ 阳性对照:放松了上新场那条之后,**真的 cron 死亡仍必须红**。

    没有这条,上一条就只是「把护栏关小」。
    """
    rows = _all_today()
    rows["jingcai_sp[open]"] = ["2026-06-17"]            # 竞彩照常上新场
    rows["jingcai_sp[open-heartbeat]"] = ["2026-06-10"]  # 但我们 7 天没抓了
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["jingcai_sp[open-heartbeat]"].stale
    assert by["jingcai_sp[open-heartbeat]"].critical, "心跳必须 CRITICAL,否则不 gate"
    assert main(["--db", str(db), "--today", "2026-06-17",
                 "--no-quota", "--no-supply"]) == 1, "cron 真死了却没让体检失败"


def test_sister_db_missing_is_critical_stale(tmp_path):
    db = _mk_db(tmp_path, _all_today())
    (tmp_path / "score_ev_forward.db").unlink()
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["score_ev_flags"].stale and by["score_ev_flags"].critical
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota", "--no-supply"]) == 1


def test_heartbeat_written_even_when_stale(tmp_path):
    # P0-2: the heartbeat proves the sentinel RAN (not that all is green) —
    # written on both the all-fresh and the critical-stale paths.
    rows = _all_today()
    rows["jingcai_vote"] = ["2026-06-01"]  # critical stale
    db = _mk_db(tmp_path, rows)
    hb = tmp_path / HEARTBEAT_FILENAME
    assert not hb.exists()
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota", "--no-supply"]) == 1
    assert hb.exists() and hb.read_text().strip()


def test_seasonal_old_does_not_gate(tmp_path):
    # A stale WARN table (league_predictions) must NOT fail the gate.
    rows = _all_today()
    rows["league_predictions"] = ["2026-06-01"]  # stale but non-critical
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["league_predictions"].stale and not by["league_predictions"].critical
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota", "--no-supply"]) == 0


def test_within_cadence_not_stale(tmp_path):
    # odds_snapshots cadence = 2d: a 2-day-old row is still fresh, 3-day is stale.
    rows = _all_today()
    rows["odds_snapshots"] = ["2026-06-15"]  # exactly 2d → OK
    rows["odds_snapshots[closing]"] = ["2026-06-15"]
    by = {s.table: s for s in check_freshness(_mk_db(tmp_path, rows, "a.db"), today=TODAY)}
    assert not by["odds_snapshots"].stale
    rows["odds_snapshots"] = ["2026-06-14"]  # 3d → stale
    rows["odds_snapshots[closing]"] = ["2026-06-14"]
    by = {s.table: s for s in check_freshness(_mk_db(tmp_path, rows, "b.db"), today=TODAY)}
    assert by["odds_snapshots"].stale


def test_missing_critical_table_is_stale(tmp_path):
    # Only a non-critical table exists; the missing CRITICAL ones must gate.
    db = tmp_path / "obs.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE league_predictions (recorded_at TEXT)")
    conn.execute("INSERT INTO league_predictions VALUES ('2026-06-17')")
    conn.commit()
    conn.close()
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots"].stale  # missing entirely → treated as stale
    assert by["odds_snapshots"].rows == 0
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota", "--no-supply"]) == 1


def test_empty_table_is_stale(tmp_path):
    rows = _all_today()
    # ⚠️ 2026-08-18 —— 原来这里**硬编码**要清空的子流(`jingcai_sp` + `[open]`)。
    # 加第三条子流(`[open-heartbeat]`,也写 `captured_at`)时它就静默失效了:
    # 整表条目量的是 `MAX(captured_at)`,而新子流照样往同一张表插带 captured_at 的行
    # ⇒ 表根本不空 ⇒ 断言反了却没人喊。
    # ⭐ 又是**分母**:该清的是「所有落在这张表上的条目」,从 `CAPTURE_TABLES` 推导,
    #    不是手写一份会过期的名单。
    for _t, _c, _m, _cr, _n, _w, _nm in CAPTURE_TABLES:
        if _t == "jingcai_sp":
            rows[_entry_key(_t, _w, _nm)] = []      # exists but empty
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["jingcai_sp"].stale and by["jingcai_sp"].days_stale is None
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota", "--no-supply"]) == 1


def test_porcelain_format(tmp_path, capsys):
    db = _mk_db(tmp_path, _all_today())
    # --no-quota:本测试只管输出【格式】。放开探针会去打线上 API(慢+依赖网络),
    # 且配额告警行可能混进正在解析的 porcelain 输出里。
    main(["--db", str(db), "--today", "2026-06-17", "--porcelain", "--no-quota", "--no-supply"])
    out = capsys.readouterr().out
    assert "OK\todds_snapshots\t" in out
    assert "OK\todds_snapshots[closing]\t" in out
    assert "OK\tjingcai_sp\t" in out
    assert "OK\tscore_ev_flags\t" in out
    # critical flag column = 1 for odds_snapshots
    line = next(r for r in out.splitlines() if r.startswith("OK\todds_snapshots\t"))
    assert line.split("\t")[5] == "1"


def test_missing_db_exits_one(tmp_path, capsys):
    # --no-quota:今天库不存在会早退返回 1,加不加都过。但【配额告警同样返回 1】——
    # 万一哪天早退逻辑坏了,这条会靠配额"过"= 假绿。关掉探针才是真在测早退。
    assert main(["--db", str(tmp_path / "nope.db"), "--no-quota", "--no-supply"]) == 1


def test_epoch_timestamp_handled(tmp_path):
    # A capture table storing epoch ints (not ISO text) must still parse.
    import datetime as _dt

    epoch = int(_dt.datetime(2026, 6, 17, 12, 0, tzinfo=_dt.UTC).timestamp())
    rows = _all_today()
    rows.pop("odds_snapshots")
    rows.pop("odds_snapshots[closing]")
    db = _mk_db(tmp_path, rows)
    conn = sqlite3.connect(db)
    # INTEGER column (epoch), unlike the TEXT tables _mk_db builds.
    conn.execute("DROP TABLE odds_snapshots")
    conn.execute("CREATE TABLE odds_snapshots (captured_at INTEGER, source TEXT)")
    conn.execute(
        "INSERT INTO odds_snapshots (captured_at, source) VALUES (?, 'closing')",
        (epoch,),
    )
    conn.commit()
    conn.close()
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots"].last_day == "2026-06-17"
    assert not by["odds_snapshots"].stale
    assert by["odds_snapshots[closing]"].last_day == "2026-06-17"


# ── 内部空洞检测(2026-07-23)──────────────────────────────────────────────
# 病史:Odds API 配额 07-13 耗尽 → closing 子流断 9 天 → 07-22 换 key 当天补上
# → 哨兵立刻绿(最后 0d),9 天的洞永远没人看见。recency 只答「现在断没断」。

def test_interior_gap_found_behind_a_green_light(tmp_path):
    """核心回归:最后一天有数据(不 stale),但中间的洞必须被看见。"""
    rows = _all_today()
    rows["odds_snapshots[closing]"] = [
        "2026-06-05", "2026-06-06",                       # 洞之前
        # 06-07 … 06-15 缺 9 天(复刻真实剧本)
        "2026-06-16", "2026-06-17",                       # 洞之后 + 今天
    ]
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    s = by["odds_snapshots[closing]"]
    assert not s.stale, "最后一天有数据 → recency 该是绿的(这正是它看不见洞的原因)"
    assert s.gaps == [("2026-06-07", "2026-06-15", 9)]


def test_interior_gap_does_not_gate(tmp_path):
    """洞里的数据已永久丢失,补不回来 —— 天天红灯只会训练出忽视。只报不拦。"""
    rows = _all_today()
    rows["odds_snapshots[closing]"] = ["2026-06-05", "2026-06-16", "2026-06-17"]
    db = _mk_db(tmp_path, rows)
    assert main(["--db", str(db), "--today", "2026-06-17",
                 "--no-quota", "--no-supply"]) == 0


def test_short_gaps_below_threshold_stay_quiet(tmp_path):
    """1-2 天空档是良性的(那天没球/cron 错峰)。实测:阈值放到 1 天会命中 6 处,
    其中 5 处是这种噪声 —— 所以 MIN_GAP_DAYS=3。"""
    rows = _all_today()
    rows["odds_snapshots[closing]"] = [
        "2026-06-10", "2026-06-12",   # 缺 06-11(1 天)
        "2026-06-15", "2026-06-17",   # 缺 06-13/14(2 天)
    ]
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots[closing]"].gaps == []


def test_seasonal_streams_are_not_gap_checked(tmp_path):
    """非 critical = 季节性(夏歇/仅赛会期),不写数据是设计如此不是故障。
    2026-07-23 实测:没有这条豁免,wc_predictions 当场报两个假洞。"""
    rows = _all_today()
    rows["wc_predictions"] = ["2026-06-01", "2026-06-17"]   # 中间空 15 天
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["wc_predictions"].gaps == []


def test_stream_prehistory_is_not_a_gap(tmp_path):
    """刚开张的流:它出生之前的那段不是洞,扫描起点必须取该流首日。"""
    rows = _all_today()
    rows["jingcai_vote"] = ["2026-06-16", "2026-06-17"]     # 只有两天历史
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["jingcai_vote"].gaps == []


def test_gap_emitted_in_porcelain(tmp_path, capsys):
    """health_check.sh 靠 GAP 前缀渲染;字段顺序是 GAP<tab>名<tab>起<tab>止<tab>天数。"""
    rows = _all_today()
    rows["odds_snapshots[closing]"] = ["2026-06-05", "2026-06-16", "2026-06-17"]
    db = _mk_db(tmp_path, rows)
    main(["--db", str(db), "--today", "2026-06-17", "--porcelain",
          "--no-quota", "--no-supply"])
    gap_lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if ln.startswith("GAP\t")]
    # 子流的行与整表的行都会出现:_mk_db 把 closing 行写进同一张 odds_snapshots,
    # 所以这个夹具里整表确实也有同一个洞 —— 两条都对,按名字取 closing 那条。
    by_name = {ln.split("\t")[1]: ln.split("\t")[2:] for ln in gap_lines}
    assert by_name["odds_snapshots[closing]"] == ["2026-06-06", "2026-06-15", "10"]


# ---------------------------------------------------------------- 探针炸了 ≠ 供应链没问题

class TestSupplyProbeFailureIsNotSilence:
    """⭐ 心跳在第 598 行就写掉了,供应链探针在第 602 行 —— 中间没有 try/except。

    探针抛一个异常 ⇒ 整份报告(采集表新鲜度、配额、联赛标签)全丢、退出码是个
    traceback,而 vote-cron 看门狗看到的是一条**新鲜的心跳**,判定「哨兵健在」。
    「哨兵跑了但什么都没说」和「哨兵说一切正常」在看门狗眼里一模一样。

    同函数里 pandas / pyarrow 的 import 都有 try/except,唯独这条没有 —— 而
    2026-08-07 接进来的 `observation.auto_retrain`(拖 numpy)正是这条路上第一个
    真实会抛的东西:我们自己把它点亮了。

    ⛔ 兜住 ≠ 咽下。零 info 零 alarm 在报告里长得和「一切正常」一模一样,所以
    探针自己坏了必须走 **alarms**(它同乘非零退出),不是静默跳过。
    """

    def _boom(self, monkeypatch):
        import nutmeg.v4.cli.data_freshness as df

        def _explode(*a, **kw):
            raise RuntimeError("numpy 装坏了")

        monkeypatch.setattr(df, "check_model_supply_chain", _explode)

    def test_report_survives_and_says_the_probe_died(self, tmp_path, capsys, monkeypatch):
        self._boom(monkeypatch)
        db = _mk_db(tmp_path, _all_today())

        rc = main(["--db", str(db), "--today", "2026-06-17", "--no-quota"])

        out = capsys.readouterr().out
        assert "RuntimeError" in out and "没有被检查" in out, (
            f"探针死了,报告里必须说清哪一块没查:{out}")
        assert "odds_snapshots" in out, f"其余报告不该被一个探针带走:{out}"
        assert rc == 1, "探针坏了要非零退出 —— 否则 cron 认为体检通过"

    def test_heartbeat_alone_cannot_mean_all_clear(self, tmp_path, monkeypatch):
        """看门狗只看心跳文件。心跳照写(哨兵确实跑了),但退出码必须把
        「跑了」和「没事」分开 —— 这两件事合并就是 wc_settle 死了三周的形状。"""
        self._boom(monkeypatch)
        db = _mk_db(tmp_path, _all_today())

        rc = main(["--db", str(db), "--today", "2026-06-17", "--no-quota"])

        assert (tmp_path / HEARTBEAT_FILENAME).exists(), "心跳仍要写:哨兵确实跑过"
        assert rc != 0, "而退出码必须说「没事」不成立"

    def test_no_supply_flag_still_skips_without_touching_the_probe(
            self, tmp_path, monkeypatch):
        """`--no-supply` 是跳过,不是「跑了再兜」—— 炸弹不该被引爆。"""
        self._boom(monkeypatch)
        db = _mk_db(tmp_path, _all_today())
        assert main(["--db", str(db), "--today", "2026-06-17",
                     "--no-quota", "--no-supply"]) == 0
