"""哨兵三修(2026-09-01)—— 起因是 owner 收到一条 13:01 的推送。

推送说「看 `logs/data_freshness_latest.md` 末行『报警类别』」,而我去看的时候
那个文件已经是 20:03 那轮**全绿**的报告 —— 13:00 报的到底是什么,**永久没了**。
排查完发现三个洞,一个比一个深:

  ① 探针一瞎,额度报警就**静默消失**:退出码只看 `quota_alarms`,而探针失败进的是
     另一个列表(2026-07-15 的设计:单轮抖动 ≠ 配额红线,不该推送)。代价是探针
     瞎着的那段时间,额度闸**无人监控且和健康长得一模一样**。实测当天:13:00 报
     额度、20:00 探针 ProxyError ⇒ quota_alarms 空 ⇒ 退出 0。
  ② 探针走了**它根本不需要的代理**:报的是 `ProxyError: 503`,而同一台机器上
     daemon 一个代理变量都没配却全天直连 Odds API 正常。httpx `trust_env=True`
     默认继承了 cron 环境的 `HTTPS_PROXY` ⇒ 白白多一个故障面。
  ③ 推送指的文件**每轮都被覆盖**:哨兵一天跑 3 轮(02:00/13:00/20:00)。
     这是 `59df1fd`(「文案指错了地方」)的下一层:文案指对了地方,
     但**地方到你去看的时候已经空了**。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import pytest

from nutmeg.v4.cli import data_freshness as df


def _now():
    return datetime.now().astimezone()


def _hist(tmp_path, records):
    p = tmp_path / "h.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                 encoding="utf-8")
    return p


# ── ① 探针失明 ────────────────────────────────────────────────────────────
def test_a_single_flake_never_alarms(tmp_path) -> None:
    """⛔ 承重:保留 2026-07-15 的设计 —— **单轮抖动不推送**。

    这条和下一条是一对:把阈值调到 0 会让 owner 每次网络打嗝都收到推送,
    而那正是当初把探针失败排除在退出码之外的原因。
    """
    now = _now()
    h = _hist(tmp_path, [{"ts": (now - timedelta(hours=2)).isoformat(),
                          "kinds": [], "probe_ok": True}])
    assert df.check_probe_blindness(h, probe_ok=False, now=now) == []


def test_persistent_blindness_does_alarm(tmp_path) -> None:
    """🚨 但连续 >24h 一次都读不到 ⇒ 必须响:那不是抖动,是「我们不知道额度是多少」
    这件事本身持续了一天,而这段时间报告和健康轮**完全一样**。"""
    now = _now()
    h = _hist(tmp_path, [{"ts": (now - timedelta(hours=30)).isoformat(),
                          "kinds": [], "probe_ok": True},
                         {"ts": (now - timedelta(hours=8)).isoformat(),
                          "kinds": [], "probe_ok": False}])
    out = df.check_probe_blindness(h, probe_ok=False, now=now)
    assert out and "失明" in out[0] and "额度闸等于没有" in out[0]


def test_a_successful_probe_this_round_clears_it(tmp_path) -> None:
    now = _now()
    h = _hist(tmp_path, [{"ts": (now - timedelta(hours=99)).isoformat(),
                          "kinds": [], "probe_ok": True}])
    assert df.check_probe_blindness(h, probe_ok=True, now=now) == []


def test_no_key_configured_is_not_blindness(tmp_path) -> None:
    """⚠️ `probe_ok` 三态里 **None ≠ False**:没配 key 是「压根没探」(测试/离线),
    把它算成失明会让每一台没有 key 的机器天天报警。"""
    now = _now()
    h = _hist(tmp_path, [{"ts": (now - timedelta(hours=99)).isoformat(),
                          "kinds": [], "probe_ok": True}])
    assert df.check_probe_blindness(h, probe_ok=None, now=now) == []


def test_a_fresh_install_never_alarms(tmp_path) -> None:
    """从来没成功过 ⇒ 多半是刚装/没配 key,不该吵。⛔ 别改成「没历史就报警」。"""
    now = _now()
    assert df.check_probe_blindness(None, probe_ok=False, now=now) == []
    h = _hist(tmp_path, [{"ts": (now - timedelta(hours=99)).isoformat(),
                          "kinds": [], "probe_ok": False}])
    assert df.check_probe_blindness(h, probe_ok=False, now=now) == []


def test_a_corrupt_history_line_does_not_break_the_alarm(tmp_path) -> None:
    """记账坏了绝不许**毁掉报警** —— 半行/脏行跳过,好行照读。"""
    now = _now()
    p = tmp_path / "h.jsonl"
    p.write_text(
        json.dumps({"ts": (now - timedelta(hours=40)).isoformat(),
                    "kinds": [], "probe_ok": True}) + "\n"
        + "{半行没写完\n", encoding="utf-8")
    assert df.check_probe_blindness(p, probe_ok=False, now=now)


def test_blindness_is_the_seventh_alarm_kind() -> None:
    assert "探针失明" in df._ALARM_KIND_LABELS
    line = df.alarm_kinds_line([], [], [], [], [], [], ["瞎了"])
    assert "探针失明" in line
    # ⛔ 全绿仍然不出类别行
    assert df.alarm_kinds_line([], [], [], [], [], [], []) == ""


# ── ② 探针不再被它不需要的代理拖瞎 ────────────────────────────────────────
def test_the_probe_tries_direct_first(monkeypatch) -> None:
    """直连优先 —— 报的是 ProxyError,而 daemon 无代理直连一直是通的。"""
    import httpx
    seen = []

    class R:
        headers = {"x-requests-remaining": "9999"}

        def json(self):
            return {"response": {"requests": {"current": 1, "limit_day": 100}}}

    def fake(url, **kw):
        seen.append(kw.get("trust_env"))
        return R()
    monkeypatch.setattr(httpx, "get", fake)
    monkeypatch.setenv("NUTMEG_ODDS_API_KEY", "k")
    monkeypatch.delenv("NUTMEG_API_FOOTBALL_KEY", raising=False)
    df.check_api_quota()
    assert seen == [False], f"第一发不是直连:{seen}"


def test_the_probe_falls_back_to_the_proxy(monkeypatch) -> None:
    """⛔ 不是简单禁掉代理:万一哪天只有代理能出去,写死直连就把探针永久钉死了。"""
    import httpx
    seen = []

    class R:
        headers = {"x-requests-remaining": "9999"}

    def fake(url, **kw):
        seen.append(kw.get("trust_env"))
        if kw.get("trust_env") is False:
            raise httpx.ConnectError("直连不通")
        return R()
    monkeypatch.setattr(httpx, "get", fake)
    monkeypatch.setenv("NUTMEG_ODDS_API_KEY", "k")
    monkeypatch.delenv("NUTMEG_API_FOOTBALL_KEY", raising=False)
    alarms, fails, ok = df.check_api_quota()
    assert seen == [False, True], f"没走兜底:{seen}"
    assert fails == [] and ok is True, "代理这条通了就不该算失败"


def test_both_paths_down_is_a_probe_failure(monkeypatch) -> None:
    import httpx

    def boom(url, **kw):
        raise httpx.ConnectError("都不通")
    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setenv("NUTMEG_ODDS_API_KEY", "k")
    monkeypatch.delenv("NUTMEG_API_FOOTBALL_KEY", raising=False)
    alarms, fails, ok = df.check_api_quota()
    assert alarms == [] and fails and ok is False


# ── ③ 报警存档不被健康轮抹掉 ──────────────────────────────────────────────
#
# ⚠️ 夹具必须造出**真正全绿**的一轮,否则「健康轮没抹掉存档」这条会恒真地绿
#    (第一版就栽在这:只建了 odds_snapshots 一张表,缺表也算停更 ⇒ 两轮都报警)。
#    ⛔ 不跨文件 import `test_data_freshness` 的 `_mk_db` —— 本仓没有测试互相
#    import 的先例,不开这个头;照 CAPTURE_TABLES 现场造一份精简的。

def _fresh_db(tmp_path, day: str):
    """按 CAPTURE_TABLES 造一份「每张表今天都有行」的观测库。"""
    import sqlite3
    from nutmeg.v4.cli.data_freshness import CAPTURE_TABLES, SISTER_CAPTURE_TABLES
    db = tmp_path / "obs.db"
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    cols: dict[str, set[str]] = {}
    for table, col, *_rest in CAPTURE_TABLES:
        where = _rest[3]
        cols.setdefault(table, set()).add(col)
        for wc in re.findall(r"(\w+)\s*(?:=|IS)", where or ""):
            cols[table].add(wc)
    for table, cs in cols.items():
        conn.execute(f"CREATE TABLE {table} ({', '.join(f'{c} TEXT' for c in sorted(cs))})")
    for table, col, *_rest in CAPTURE_TABLES:
        where = _rest[3]
        extra = dict(re.findall(r"(\w+)\s*=\s*'([^']*)'", where or ""))
        for c in re.findall(r"(\w+)\s+IS\s+NOT\s+NULL", where or "", re.I):
            extra.setdefault(c, "1")
        data = {**extra, col: day}     # ⚠️ col 最后赋值,不许被 extra 盖掉
        conn.execute(f"INSERT INTO {table} ({','.join(data)}) "
                     f"VALUES ({','.join('?' * len(data))})", tuple(data.values()))
    conn.commit()
    conn.close()
    for db_file, table, col, *_ in SISTER_CAPTURE_TABLES:
        f = tmp_path / db_file
        if f.exists():
            f.unlink()
        sc = sqlite3.connect(f)
        sc.execute(f"CREATE TABLE {table} ({col} TEXT)")
        sc.execute(f"INSERT INTO {table} ({col}) VALUES (?)", (day,))
        sc.commit()
        sc.close()
    return db


def _run(tmp_path, db, today):
    """⚠️ 四个 --no-* 全带上:本节测的是**存档/历史**,不是那几个探针。
    不关掉的话,生产 artifact 年龄之类的东西会让「健康轮」根本造不出来
    (`test_data_freshness.py` 头部那段注释记的就是这个耦合)。"""
    import subprocess
    import sys
    out = tmp_path / "data_freshness_latest.md"
    r = subprocess.run(
        [sys.executable, "-B", "-m", "nutmeg.v4.cli.data_freshness",
         "--db", str(db), "--out", str(out), "--today", today,
         "--no-quota", "--no-supply", "--no-league-labels", "--no-trickle"],
        capture_output=True, text=True)
    return r.returncode, out, r


def test_the_alarm_archive_survives_a_healthy_run(tmp_path) -> None:
    """🚨 本次三修里最贵的一条 —— 它就是 owner 那条 13:01 推送查不下去的原因。

    时序:13:00 报警 → 20:00 全绿 → 20:03 覆盖 `_latest.md` ⇒ 答案永久消失。
    ⇒ 报警轮另存一份,它**只会被下一次报警覆盖**。
    """
    db = _fresh_db(tmp_path, "2026-09-01")
    rc_bad, out, r = _run(tmp_path, db, "2026-12-01")     # 远期 ⇒ 全停更
    assert rc_bad == 1, f"夹具没造出报警 ⇒ 下面的断言恒真\n{r.stdout[-800:]}"
    archive = df.alarm_path_for(out)
    assert archive.exists(), "报警轮没有另存"
    stamped = archive.read_text(encoding="utf-8")
    assert "报警类别" in stamped

    rc_ok, _, r2 = _run(tmp_path, db, "2026-09-01")       # 健康轮
    assert rc_ok == 0, f"夹具没造出健康轮 ⇒ 本条什么也没证明\n{r2.stdout[-800:]}"
    assert archive.read_text(encoding="utf-8") == stamped, (
        "健康轮把报警存档抹掉了 —— 这正是要修的那个洞")


def test_no_archive_before_the_first_alarm(tmp_path) -> None:
    db = _fresh_db(tmp_path, "2026-09-01")
    rc, out, r = _run(tmp_path, db, "2026-09-01")
    assert rc == 0, r.stdout[-800:]
    assert not df.alarm_path_for(out).exists(), "全绿也存了档 ⇒ 存档失去意义"


def test_every_run_leaves_a_history_line(tmp_path) -> None:
    """有了逐轮历史,「上次报的是什么、报了多久」才答得出来
    —— 而这正是我这次答不出 13:00 的原因。"""
    db = _fresh_db(tmp_path, "2026-09-01")
    _run(tmp_path, db, "2026-12-01")
    _run(tmp_path, db, "2026-09-01")
    h = df.history_path_for(tmp_path / "data_freshness_latest.md")
    recs = [json.loads(x) for x in h.read_text(encoding="utf-8").splitlines()]
    assert len(recs) == 2, recs
    assert recs[0]["kinds"] and not recs[1]["kinds"], recs
    assert all("ts" in r for r in recs)


def test_the_report_says_which_round_it_is(tmp_path) -> None:
    """⚠️ 一天 3 轮,只写 today 的话 13:01 的推送和 20:03 的报告长得一样。"""
    db = _fresh_db(tmp_path, "2026-09-01")
    _, out, _ = _run(tmp_path, db, "2026-09-01")
    assert "运行于" in out.read_text(encoding="utf-8").splitlines()[0]


def test_exit_code_kinds_and_archive_share_one_source() -> None:
    """⭐ 退出码 / 类别行 / 存档判据必须**同一个来源**。

    三处各写一遍 `a or b or c…` 迟早会漂 —— 加第 7 类时就差点漏掉存档那处。
    """
    import inspect
    src = inspect.getsource(df.main)
    assert src.count("_any_alarm(") == 2, "退出码和存档判据没走同一个函数"
    assert "_alarm_kinds(" in src
    n = len(df._ALARM_KIND_LABELS)
    for i in range(n):
        groups = [[] for _ in range(n)]
        groups[i] = ["x"]
        assert df._any_alarm(*groups) is True, f"第 {i} 类没被算进退出码"
    assert df._any_alarm(*([[]] * n)) is False
