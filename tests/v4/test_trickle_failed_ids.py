"""涓流失败的**逐场留痕** + 补回验证(2026-08-24)。

## 病史

体检报「最近 7 轮:枚举 1071 · 新增 0 行 · **失败 3**」。查下来:

* 「新增 0 行」**合法** —— `fetched=0` 且 `skipped≈enumerated`,那些窗口全已在库;
  且 `end` 在推进(08-17→08-22)⇒ 不是 2026-07-20 那个「END 写成常量」的假信号。
* 失败是**逐场**的:全历史 236 轮 / 枚举 18,756 / 失败 **68**(0.36%),零星。
* 架构本来就会自愈:失败 ⇒ 没入库 ⇒ 游标绕回起点 re-sweep 时不被
  `skip_existing` 跳过 ⇒ 重抓(`scripts/jingcai_history_trickle.py:149-150`)。

🚨 **但 `wrapped=True` 的轮次是 0/236 —— 那条自愈路径从没在生产跑过。**
而当时只有计数、没有 id ⇒ 绕回之后**验不了**补上了哪些:
**「补上了但那些场本来就没数据」和「绕回根本没生效」在 `stored_rows` 上同形。**
⇒ 本次把间接判据换成直接的:记 matchId,拿它去库里查。

## ⚠️ 实现时差点犯的同形错误

`jingcai_odds_history` 在 **`v4_jingcai_history.db`**,不在观测库。传错库 ⇒
查询空 ⇒ 「0 已补回」和「真的没补回」**长得一模一样**。所以库/表不在时
一律报「**未查**」,绝不报 0。本模块最承重的断言就是这条。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def _status(tmp_path: Path, rounds: list[list[str]]) -> Path:
    p = tmp_path / "st.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for i, ids in enumerate(rounds):
            fh.write(json.dumps({
                "ran_at": f"2026-08-{20+i:02d}T03:00:00", "cursor_next": f"2025-12-{1+i:02d}",
                "end": "2026-08-22", "days_remaining": 100, "enumerated": 10,
                "stored_rows": 0, "skipped": 10, "failed": len(ids), "failed_ids": ids,
            }) + "\n")
    return p


def _hist_db(tmp_path: Path, stored: list[str] | None) -> Path:
    """stored=None ⇒ 建库但**不建表**;否则建表并塞入这些 match_id。"""
    p = tmp_path / "hist.db"
    c = sqlite3.connect(p)
    if stored is not None:
        c.execute("CREATE TABLE jingcai_odds_history (match_id TEXT)")
        c.executemany("INSERT INTO jingcai_odds_history VALUES (?)", [(x,) for x in stored])
    c.commit(); c.close()
    return p


def _run(status: Path, hist: Path | str):
    from datetime import datetime
    from nutmeg.v4.cli.data_freshness import check_jingcai_trickle
    info, _ = check_jingcai_trickle(
        status, now=datetime.fromisoformat("2026-08-25T03:00:00"), history_db=hist)
    return [l for l in info if "失败逐场留痕" in l or "待补 matchId" in l]


# ── 承重 ──────────────────────────────────────────────

def test_missing_db_says_not_checked_never_zero(tmp_path) -> None:
    """🚨 全案最承重:库不在时必须说「**未查**」,**绝不能**说「0 已补回」。

    后者会让「绕回没生效」伪装成「补回情况正常」—— 本仓反复栽的那个同形陷阱。
    """
    out = _run(_status(tmp_path, [["m1", "m2"]]), tmp_path / "nope.db")
    assert out and "未查" in out[0], f"库不在却没说未查:{out}"
    assert "已补回 0" not in out[0], "库不在却报了「已补回 0」"


def test_missing_table_also_says_not_checked(tmp_path) -> None:
    """同上:库在但表不在(比如换了 checkout)⇒ 仍然是「未查」。

    ⚠️ 缺表时走的是 `except sqlite3.Error`,而 SQL 抛的
    `no such table: jingcai_odds_history` **本身**就说了未查、也点名了表。
    ⇒ 空包弹实测:另加一道显式的表存在检查**分不出任何差别**(拆掉它测试仍全绿)
    ⇒ 那道检查是死代码,已删。本条断言守的是**兜底路径**给出的消息质量。
    """
    out = _run(_status(tmp_path, [["m1"]]), _hist_db(tmp_path, None))
    assert out and "未查" in out[0], f"表不在却没说未查:{out}"
    assert "jingcai_odds_history" in out[0], f"没点名缺的是哪张表:{out}"


def test_it_counts_recovered_and_outstanding(tmp_path) -> None:
    """⭐ 这就是绕回之后要看的那个数:哪些补回了、哪些还没。"""
    st = _status(tmp_path, [["m1", "m2"], ["m3"]])
    out = _run(st, _hist_db(tmp_path, ["m1", "m3"]))          # m2 还没补
    assert "累计 3 场" in out[0] and "已补回 2" in out[0] and "待补 1" in out[0], out
    assert any("m2" in l for l in out), f"待补的 id 没被点名:{out}"


def test_ids_dedupe_across_rounds(tmp_path) -> None:
    """同一场在两轮都失败 ⇒ 只算一次,否则「累计」会虚高。"""
    out = _run(_status(tmp_path, [["m1"], ["m1"]]), _hist_db(tmp_path, []))
    assert "累计 1 场" in out[0], out


def test_no_ids_names_the_since_date(tmp_path) -> None:
    """⛔ 承重:没有 id 时必须说清「留痕自 X 起」。

    否则「0 条」会被读成「历史上那 68 场失败都补回来了」—— 而它们**根本没有 id**,
    压根没被查过。这是「没有」和「没去看」的又一次同形。
    """
    out = _run(_status(tmp_path, [[], []]), _hist_db(tmp_path, []))
    assert "0 条" in out[0] and "留痕自" in out[0], out
    assert "之前的失败只有计数" in out[0], "没说清历史失败不在覆盖范围内"


def test_backfill_records_and_caps_failed_ids() -> None:
    """写入侧:`backfill` 的 stat 带 `failed_ids`,且有 50 的上限。"""
    import inspect

    from nutmeg.v4.cli import ingest_jingcai_history as m
    src = inspect.getsource(m.backfill)
    assert '"failed_ids": []' in src, "stat 里没有 failed_ids"
    assert 'len(stat["failed_ids"]) < 50' in src, "没有上限 ⇒ 一轮大面积失败会写爆状态文件"
