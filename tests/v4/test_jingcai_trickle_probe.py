"""竞彩历史涓流进度探针(2026-08-08)。

## 它为什么存在

2026-07-20:看到「连续 56 轮零新增」⇒ 判定「覆盖齐了」⇒ **主动退休了这个 job**。
那个零是脚本里 END 写成常量导致的**数学必然**,不是覆盖齐 —— 静默丢了
10.5 个月 / 4,751 场,日志天天绿,直到 owner 问一场具体比赛的历史 EV 才暴露。

END 那个 bug 已修(`_end_date()`)。但**当时没有任何东西能回答「它扫完了吗」** ——
2026-08-08 owner 又问了一次同样的问题,我是手工数联赛构成、翻日志、算游标速度
才答出来的。这个探针把那次手工分析变成常驻读数。

## 承重的是**哪个**断言

不是「stored_rows 是不是 0」。是:

    enumerated > 0 且 stored_rows == 0  →  真·扫完了(去看了,确实没东西)
    enumerated == 0                     →  **没去看**(限流/403/空响应)

**两者的 stored_rows 都是 0,长得一模一样,结论相反。**
`test_the_two_zeros_are_told_apart` 就是钉这一条 —— 它一红,探针就退回成
2026-07-20 那个会骗人的读数。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from nutmeg.v4.cli.data_freshness import check_jingcai_trickle

NOW = dt.datetime(2026, 8, 8, 12, 0)


def _row(**kw) -> dict:
    base = {
        "ran_at": (NOW - dt.timedelta(hours=6)).isoformat(timespec="seconds"),
        "window_start": "2021-09-19", "window_end": "2021-09-25",
        "cursor_next": "2021-09-26", "begin": "2021-08-01", "end": "2026-08-06",
        "days_remaining": 1775, "wrapped": False,
        "enumerated": 75, "in_scope": 75, "fetched": 32,
        "stored_rows": 282, "skipped": 43, "failed": 0,
    }
    base.update(kw)
    return base


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "logs" / "jingcai_trickle_status.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    return p


def test_the_two_zeros_are_told_apart(tmp_path: Path) -> None:
    """⭐⭐ 本文件的**唯一承重断言**。两组数据只差 `enumerated` 一个字段,
    `stored_rows` 都是 0 —— 判定必须相反。"""
    done = [_row(enumerated=80, stored_rows=0, days_remaining=0,
                 cursor_next="2026-08-06")] * 7
    blind = [_row(enumerated=0, in_scope=0, fetched=0, stored_rows=0,
                  days_remaining=0, cursor_next="2026-08-06")] * 7

    _i_done, a_done = check_jingcai_trickle(_write(tmp_path / "a", done), now=NOW)
    i_blind, a_blind = check_jingcai_trickle(_write(tmp_path / "b", blind), now=NOW)

    assert not a_done, f"「去看了,确实没东西」被误报成问题:{a_done}"
    assert any("扫完了" in x for x in _i_done), "真扫完了却没说可以退休"

    assert a_blind, (
        "⛔ `enumerated == 0` 没有报警 —— 探针退回成 2026-07-20 那个会骗人的读数了。"
        "零新增在这里意味着**没去看**,不是没东西可看")
    assert any("没去看" in x for x in a_blind), a_blind
    assert not any("扫完了" in x for x in i_blind), (
        "把「没去看」说成了「扫完了」—— 这正是丢掉 4,751 场的那句话")


def test_still_working_reports_progress_and_measured_eta(tmp_path: Path) -> None:
    """ETA 必须由**实测推进速度**算,不是假设 cron 频率。"""
    rows = [
        _row(ran_at=(NOW - dt.timedelta(days=3)).isoformat(timespec="seconds"),
             cursor_next="2021-08-29", days_remaining=1817),
        _row(ran_at=(NOW - dt.timedelta(hours=6)).isoformat(timespec="seconds"),
             cursor_next="2021-09-26", days_remaining=1775),
    ]
    info, alarms = check_jingcai_trickle(_write(tmp_path, rows), now=NOW)
    assert not alarms, alarms
    joined = " ".join(info)
    assert "1775" in joined, "没报剩余天数"
    assert "ETA" in joined, "没报 ETA"
    # 28 天历史 / 2.75 天日历 ≈ 10 天历史/天 ⇒ ETA ≈ 174 天
    assert "天历史/天" in joined


def test_stopped_running_is_an_alarm(tmp_path: Path) -> None:
    """回填停了 = 缺口不会自己合上。cron 挂掉必须响。"""
    rows = [_row(ran_at=(NOW - dt.timedelta(days=5)).isoformat(timespec="seconds"))]
    _info, alarms = check_jingcai_trickle(_write(tmp_path, rows), now=NOW)
    assert any("没跑" in a for a in alarms), alarms


def test_missing_status_distinguishes_ci_from_never_ran(tmp_path: Path) -> None:
    """⚠️ 「没有状态文件」自己也有两种意思,不能一律跳过 ——
    那会把这个探针变成它自己要防的那种假信号。"""
    # ① logs/ 都没有 = CI/测试环境 ⇒ 跳过,不报警
    _i, a = check_jingcai_trickle(tmp_path / "nope" / "x.jsonl", now=NOW)
    assert not a, "CI 环境不该报警"
    # ② logs/ 在但文件没有 = job 装了从没成功跑过 ⇒ 报警
    (tmp_path / "logs").mkdir()
    _i2, a2 = check_jingcai_trickle(tmp_path / "logs" / "x.jsonl", now=NOW)
    assert a2, "job 从没跑过却不报警 —— 「没有状态」被读成了「没在跑因为跑完了」"


def test_throttling_is_an_alarm(tmp_path: Path) -> None:
    """大量 failed = 可能被 sporttery 限流/封 IP,进度读数会虚高。"""
    rows = [_row(enumerated=50, failed=30, stored_rows=10)] * 3
    _info, alarms = check_jingcai_trickle(_write(tmp_path, rows), now=NOW)
    assert any("限流" in a for a in alarms), alarms


def test_probe_failure_is_not_silence() -> None:
    """探针自己炸了必须走 alarms —— 零 info 零 alarm 在报告里长得和「一切正常」
    一模一样(同 `check_model_supply_chain` 2026-08-07 那次的理由)。"""
    src = (Path(__file__).resolve().parents[2]
           / "apps/api/src/nutmeg/v4/cli/data_freshness.py").read_text(encoding="utf-8")
    seg = src[src.index("if not args.no_trickle:"):]
    seg = seg[:seg.index("if args.porcelain")]
    assert "except Exception" in seg and "trickle_alarms = [" in seg, (
        "涓流探针没有 try/except → 它一抛异常,整份报告丢失而心跳照常写 = 假绿")
    # ⚠️ 2026-08-08 —— 这条我第一版写成 `"or trickle_alarms" in src`,**是假护栏**:
    #    那个子串在 `if trickle_info or trickle_alarms:`(**打印**条件)里也出现,
    #    所以把退出码里的那份删掉,断言照样绿(变异 M6 抓到的)。
    #    改成只看**退出码那一行**。同族:语法代理测语义属性。
    ret = src[src.index("    return 1 if ("):]
    ret = ret[:ret.index("else 0") + 6]
    assert "trickle_alarms" in ret, (
        f"涓流报警没有同乘非零退出 ⇒ 推送不会触发。退出码那行现在是:{ret!r}")


def test_producer_and_consumer_agree_on_the_fields(tmp_path: Path, monkeypatch) -> None:
    """⭐ 端到端:**跑真的生产者**写一行,再喂给真的消费者。

    变异 M7 暴露的洞:此前所有用例都是我手搓的状态行,
    生产者少写一个字段(比如 `enumerated`)**一条测试都不会红** ——
    而少的正好是那条承重判据的输入。
    """
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "_trickle_under_test", root / "scripts/jingcai_history_trickle.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_trickle_under_test"] = mod
    spec.loader.exec_module(mod)          # 注:模块顶层会清 6 个代理 env,测试进程内无害

    # ⚠️ 必须跑 **`main()`**,不能直接调 `_write_status` ——
    #    字段列表在 `main()` 体内,直接调 helper 等于测试自己把字段补上了,
    #    生产者少写一个照样绿(我第一版就是这么写的,变异 M7 当场戳穿)。
    out = tmp_path / "logs" / "s.jsonl"
    monkeypatch.setattr(mod, "STATUS", out)
    monkeypatch.setattr(mod, "CURSOR", tmp_path / "cursor.txt")
    monkeypatch.setattr(mod, "backfill", lambda *a, **k: {
        "enumerated": 75, "in_scope": 75, "fetched": 32,
        "stored_rows": 282, "skipped": 43, "failed": 0})
    assert mod.main() == 0

    rows = [json.loads(x) for x in out.read_text().splitlines() if x.strip()]
    assert len(rows) == 1, rows
    # 消费者真正读的那几个键,生产者一个都不能少
    for k in ("ran_at", "cursor_next", "days_remaining",
              "enumerated", "stored_rows", "failed"):
        assert k in rows[0], (
            f"生产者没写 `{k}` —— 消费者读不到它。"
            f"少了 `enumerated` 时,「没去看」和「扫完了」就再也分不开了")

    info, alarms = check_jingcai_trickle(out, now=dt.datetime.now())
    assert not alarms, f"生产者刚写的行喂给消费者就报警 —— 两边对不上:{alarms}"
    assert any("游标" in x for x in info), "消费者没读到进度"
