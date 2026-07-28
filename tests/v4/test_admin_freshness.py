"""个人中心「数据新鲜度」面板 —— 锁住选表判据和探针不会静默失灵。

这个面板的失效模式很阴:某张表的时间列被改名 ⇒ 那一行静默变成「— 条 · —」,
读起来像「这个源没数据」而不是「探针坏了」。人看几次就学会忽略它。
"""
from __future__ import annotations

import sqlite3

import pytest

from nutmeg.v4.api.admin import _FRESHNESS_ROWS, _data_freshness


def test_every_probe_resolves_against_the_live_schema(tmp_path):
    """⭐ 每个 (表, 列) 必须真的存在 —— 列改名 ⇒ 该行静默变「—」,不报错。

    用真库(只读)。库不在就跳过,不假装通过。
    """
    import os

    from nutmeg.config import get_settings
    # 与 _data_freshness 同一条解析链:env 覆盖优先,否则 settings 默认。
    db = os.environ.get("NUTMEG_V4_OBSERVATION_DB", get_settings().v4_observation_db)
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        pytest.skip(f"观测库不可读({db}),跳过 schema 校验")
    with c:
        for table, col, label in _FRESHNESS_ROWS:
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            assert cols, f"「{label}」指向的表 {table} 不存在"
            assert col in cols, f"「{label}」的列 {table}.{col} 不存在 —— 该行会静默变「—」"


def test_labels_are_unique():
    """标签重复 ⇒ 面板上两行长得一样,分不清谁停了。"""
    labels = [lb for _, _, lb in _FRESHNESS_ROWS]
    assert len(labels) == len(set(labels))


def test_wc_predictions_is_probed_twice_on_purpose():
    """⚠️ 同表两行、**不同列**是有意的,不是重复条目 —— 别「去重」。

    `recorded_at` 只在有**新预测**时动;WC 停办后它必然陈旧,于是 daily_wc_settle
    是死是活完全看不出来。实测 settled_at=当天 而 recorded_at=07-19。
    """
    cols = {col for tbl, col, _ in _FRESHNESS_ROWS if tbl == "wc_predictions"}
    assert cols == {"recorded_at", "settled_at"}


def test_settlement_probe_is_present():
    """⭐ match_outcomes 是**唯一的赛果入口**(daily_settle)。

    它停了,所有捕获行照常绿,但 CLV 账本 / EV 排序 / δ 校准 / 抽水分解全部冻在
    旧结果上,**且不报错、只是 N 不涨**。删掉这一行 = 把那个盲区放回去。
    """
    assert any(t == "match_outcomes" for t, _, _ in _FRESHNESS_ROWS)


def test_static_backfill_archives_stay_out():
    """⛔ backfill 脚本写的静态档案**不许**进本面板 —— 进了就是永久假红。

    `pinnacle_close_history` / `crown_close_history` 由 scripts/backfill_*.py 写、
    没有任何 cron。把它们当「新鲜度」看,只会训练人忽略这一节。
    """
    tables = {t for t, _, _ in _FRESHNESS_ROWS}
    assert not tables & {"pinnacle_close_history", "crown_close_history"}


def test_freshness_returns_a_row_per_probe_plus_the_separate_db():
    """score_ev_forward.db 是**另一个库**,单独探 —— 行数应比常量多 1。"""
    rows = _data_freshness()
    if rows and "error" in rows[0]:
        pytest.skip(f"观测库不可读:{rows[0]['error']}")
    assert len(rows) == len(_FRESHNESS_ROWS) + 1
    assert any(r["table"] == "score_ev_flags" for r in rows)


# ── 同 cron 姊妹表并进主行(P2,2026-07-29)──────────────────────────────

def test_companion_keys_point_at_real_primary_rows():
    """⭐ 姊妹表挂在一个**存在的** (主表, 主列) 上 —— 挂错 = note 永不出现,静默。

    key 用 (表, 列) 而不是光表名:wc_predictions 出现两次,只按表名会撞。
    """
    from nutmeg.v4.api.admin import _FRESHNESS_COMPANIONS
    primaries = {(t, c) for t, c, _ in _FRESHNESS_ROWS}
    for key in _FRESHNESS_COMPANIONS:
        assert key in primaries, f"姊妹表挂在不存在的主行 {key} 上,note 永远不会出现"


def test_companion_tables_are_not_also_standalone_rows():
    """⚠️ 姊妹表**不许**同时再占一行 —— 那就成了同一个 cron 报两次。

    jingcai_exotic_sp 与 jingcai_sp 由同一个 cron 写、captured_at 逐秒相同,
    单独一行零告警价值、只是噪声。它的价值是修掉主行 13× 的低报。
    """
    from nutmeg.v4.api.admin import _FRESHNESS_COMPANIONS
    standalone = {t for t, _, _ in _FRESHNESS_ROWS}
    for ct, _, _ in _FRESHNESS_COMPANIONS.values():
        assert ct not in standalone, f"{ct} 既当姊妹表又单独占行 = 同一 cron 报两次"


def test_companion_tables_resolve_against_the_live_schema():
    """姊妹表/列改名 ⇒ note 静默消失,主行悄悄退回低报 13× —— 和主探针同一种阴。"""
    import os
    import sqlite3 as _sq

    from nutmeg.config import get_settings
    from nutmeg.v4.api.admin import _FRESHNESS_COMPANIONS
    db = os.environ.get("NUTMEG_V4_OBSERVATION_DB", get_settings().v4_observation_db)
    try:
        c = _sq.connect(f"file:{db}?mode=ro", uri=True)
    except _sq.OperationalError:
        pytest.skip(f"观测库不可读({db})")
    with c:
        for ct, ccol, _ in _FRESHNESS_COMPANIONS.values():
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({ct})")}
            assert cols, f"姊妹表 {ct} 不存在"
            assert ccol in cols, f"姊妹列 {ct}.{ccol} 不存在 —— note 会静默消失"


def test_frontend_renders_the_note():
    """后端给了 note、前端不渲染 = 白算。两处必须同步(与 _FRESHNESS_COMPANIONS 配对)。"""
    from pathlib import Path
    html = (Path(__file__).resolve().parents[2] / "apps/api/src/nutmeg/v4/api/static"
            / "dashboard.html").read_text(encoding="utf-8")
    assert "row.note" in html, "前端没渲染 note —— 后端的姊妹计数到不了屏幕上"
