"""未映射历史 append-only(2026-08-20)—— 让缺口能画成曲线,而不是只有当下一帧。

## 病史

`logs/sporttery_unmapped_latest.txt` **每次覆盖**。2026-08-20 想回答「词典缺口
到底有多大、在变好还是变坏」时发现:实时侧**一帧历史都没有**。
(同族:δ 校准仪表也只写 `_latest.md`,导致预注册里「连续两周变差」这条判据
在产物上根本判不了。)

## ⭐ 这次的关键设计:落**分母**,不只落分子

`_latest` 只记「哪几场没映射上」。三个月的分子攒起来**仍算不出缺口率** ——
那几天竞彩上架了多少场、哪些联赛,没人记。所以历史记录里带 ``by_league``
的在售总数。**这是本测试最该守的东西。**

## ⚠️ 两条链,两个分母

这份历史只覆盖**实时源**。竞彩**走势档案**用另一套更短的写法(实测四个实时写法
在档案里出现 0 次)⇒ 档案侧缺口(2026-08-20:比赛级 26.8% 两侧解不全)
**不能**用这份历史推,反之亦然。
"""
from __future__ import annotations

import json

import pytest


def _mk(tmp_path):
    (tmp_path / "data").mkdir()
    return str(tmp_path / "data" / "obs.db")


#: 一场解得出、两场解不出(其中日乙整联赛丢失)。⭐ 第 3 场**只坏主队一侧** ——
#: 「山形」映射得好好的,审查实测这类「被连坐」的队名占被点名者的 64%。
MATCHES = [
    {"home_en": "Mexico", "away_en": "South Africa", "league_cn": "欧冠",
     "match_date": "2026-07-07", "match_num": "周二001", "kickoff_utc": None,
     "home_cn": "墨西哥", "away_cn": "南非", "had": (1.7, 3.4, 4.5), "hhad": None},
    {"home_en": None, "away_en": None, "league_cn": "欧冠",
     "home_cn": "克拉克斯维克", "away_cn": "比森阿泰尔",
     "match_date": "2026-07-07", "match_num": "周二002",
     "had": (2.0, 3.0, 3.5), "hhad": None},
    {"home_en": None, "away_en": "Montedio Yamagata", "league_cn": "日乙",
     "home_cn": "枥木城", "away_cn": "山形",
     "match_date": "2026-07-07", "match_num": "周二003",
     "had": (2.0, 3.0, 3.5), "hhad": None},
]


def _lines(tmp_path):
    f = tmp_path / "logs" / "sporttery_unmapped_history.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_a_record_lands_with_the_denominator(tmp_path) -> None:
    """⭐ 承重:``by_league`` 必须同时有 n(在售)和 bad(未映射)。

    只有 bad 的话,这份历史就退化成 `_latest` 的时间序列 —— 那正是要修的病。
    """
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    harvest_to_db(_mk(tmp_path), matches=MATCHES, phase="open")
    rec, = _lines(tmp_path)
    assert rec["n_matches"] == 3 and rec["n_unmapped"] == 2
    assert rec["by_league"] == {"欧冠": {"n": 2, "bad": 1}, "日乙": {"n": 1, "bad": 1}}
    assert ["欧冠", "2026-07-07", "周二001"] in rec["matches_seen"]
    assert len(rec["matches_seen"]) == 3
    assert rec["gone"] == ["日乙"]          # 该联赛在售 1 场、全丢
    assert rec["phase"] == "open" and rec["trigger"] == "cli"
    assert rec["rows_written"] == {"had": 1, "hhad": 0}
    assert ["枥木城", "山形", "日乙", "2026-07-07", "周二003", "h"] in rec["names"]


def test_the_rate_is_actually_computable_from_the_file(tmp_path) -> None:
    """⭐ 行为断言(不是结构断言):从落盘的记录能**算出缺口率**。

    这是这份历史存在的全部理由 —— 所以断言就写成「算一遍」。
    """
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    harvest_to_db(_mk(tmp_path), matches=MATCHES)
    rec, = _lines(tmp_path)
    n = sum(v["n"] for v in rec["by_league"].values())
    bad = sum(v["bad"] for v in rec["by_league"].values())
    assert (n, bad, bad / n) == (3, 2, pytest.approx(2 / 3))


def test_append_only_never_overwrites(tmp_path) -> None:
    """⛔ 同日多轮不许互相覆盖 —— 竞彩分批上架,轮与轮之间的差异本身是信号。

    这条红了 = 又把 `_latest` 的病犯了一遍,只是换了个文件名。
    """
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    db = _mk(tmp_path)
    harvest_to_db(db, matches=MATCHES, phase="open")
    harvest_to_db(db, matches=MATCHES[:1], phase="close")
    a, b = _lines(tmp_path)
    assert (a["n_unmapped"], a["phase"]) == (2, "open"), "第一轮被后一轮改写了"
    assert (b["n_unmapped"], b["phase"]) == (0, "close")


def test_empty_fetch_still_records_a_row(tmp_path) -> None:
    """⭐ 与 `_latest` **故意相反**:0 场也落一行。

    `_latest` 遇到 0 场不刷新,是怕把上次报告洗成 ✅ 假绿。历史要的是反过来的东西 ——
    没有这一行,「抓到 0 场 / cron 没跑 / 写失败 / 开关关掉」四态在文件上**完全同形**
    (审查逐字节证实 sha256 相同)。读的时候按 `n_matches > 0` 过滤即可。
    """
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    db = _mk(tmp_path)
    harvest_to_db(db, matches=[])
    rec, = _lines(tmp_path)
    assert rec["n_matches"] == 0 and rec["by_league"] == {}
    # 而 `_latest` 仍然不被创建/刷新 —— 两条链两条约定,别搞混
    assert not (tmp_path / "logs" / "sporttery_unmapped_latest.txt").exists()


def test_write_failure_never_breaks_ingest(tmp_path) -> None:
    """Fail-soft:历史写不进去也绝不能打断入库(与 `_write_unmapped_report` 同约定)。"""
    from nutmeg.v4.cli import ingest_sporttery as mod
    db = _mk(tmp_path)
    (tmp_path / "logs").mkdir()
    # 用一个**文件**占住 jsonl 的父目录位置,使 mkdir/open 必失败
    bad = tmp_path / "logs" / "boom"
    bad.write_text("x")
    orig = mod._UNMAPPED_HISTORY_RELPATH
    mod._UNMAPPED_HISTORY_RELPATH = "logs/boom/h.jsonl"
    try:
        r = mod.harvest_to_db(db, matches=MATCHES)
    finally:
        mod._UNMAPPED_HISTORY_RELPATH = orig
    assert r["unmapped"] == 2, "写历史失败把入库打断了"


def test_summarize_unmapped_contract_unchanged(tmp_path) -> None:
    """⛔ 承重:这次改动**不许**动 `summarize_unmapped` 的返回契约 ——
    面板横幅(routes.py)和十余处测试都在读它。分母是在写历史时另算的。"""
    from nutmeg.v4.cli.ingest_sporttery import summarize_unmapped
    s = summarize_unmapped(MATCHES)
    assert set(s) == {"unmapped", "gone", "partial", "alarm_bits"}


def test_the_denominator_is_per_match_not_per_round(tmp_path) -> None:
    """🚨 承重(blocker)—— **跨轮**聚合必须能还原真实的「比赛数」,不是「轮次×场」。

    一天跑 ~16 轮,一场比赛在售 1–3.3 天(世界杯 3.29 vs 欧罗巴 1.00)⇒ 裸求和被
    **在售时长**加权,逐联赛放大 16–54×。审查实测:按裸 `bad` 排「先补哪个联赛」,
    12 个联赛错位 8.9 个、top-1 在 5/20 个种子里翻掉。

    ⭐ 断言写成**真的跨轮算一遍**,而不是查某个字段存在 —— 我第一版就是查字段,
    结果把 `matches_seen` 换成裸计数时测试**照样绿**(单轮内两者恒等)。
    """
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    db = _mk(tmp_path)
    for _ in range(5):                       # 同一批比赛被 5 轮反复抓到
        harvest_to_db(db, matches=MATCHES)
    recs = _lines(tmp_path)

    naive = sum(r["by_league"]["欧冠"]["n"] for r in recs)
    assert naive == 10, "裸求和应该被轮次放大(5 轮 × 2 场)"

    # 真正要能做到的事:从文件还原「欧冠这段窗口一共上架了几场、几场没映射上」
    all_ids = {tuple(x) for r in recs for x in r["matches_seen"] if x[0] == "欧冠"}
    bad_ids = {(n[2], n[3], n[4]) for r in recs for n in r["names"] if n[2] == "欧冠"}
    assert (len(all_ids), len(bad_ids)) == (2, 1), "跨轮去重后应是 2 场在售 / 1 场坏"
    assert len(bad_ids) / len(all_ids) == 0.5, "缺口率跨轮可算且不被轮次污染"


def test_match_num_is_in_the_dedup_key(tmp_path) -> None:
    """⛔ (联赛, 日期) **不是**唯一键 —— 实测竞彩档案里 54.7% 的格子装不止一场(最多 16)。

    少了 `match_num`,同日同联赛的多场会被折叠成一场,分母塌陷。
    """
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    same_day = [dict(m, league_cn="欧冠", match_date="2026-07-07",
                     match_num=f"周二{i:03d}") for i, m in enumerate(MATCHES, 1)]
    harvest_to_db(_mk(tmp_path), matches=same_day)
    rec, = _lines(tmp_path)
    ids = {tuple(x) for x in rec["matches_seen"]}
    assert len(ids) == 3, f"同日同联赛 3 场被折叠成 {len(ids)} 场 —— 去重键少了 match_num"


def test_side_records_which_half_is_broken(tmp_path) -> None:
    """🚨 承重 —— 一场未映射通常只坏一侧,另一侧被连坐。

    审查实测:被点名的 116 个队名里 **74 个(64%)本身映射得好好的**,
    逐队计数中位虚高 ×32。⛔ 「读时拿词典再筛一遍」是假补救(词典近乎纯增,
    用窗口末的词典去筛会把真缺口筛成 0)⇒ 必须**在写的时候**就记下坏的是哪侧。
    """
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    harvest_to_db(_mk(tmp_path), matches=MATCHES)
    rec, = _lines(tmp_path)
    by = {n[0]: n[5] for n in rec["names"]}
    assert by["克拉克斯维克"] == "ha", "两侧都坏"
    assert by["枥木城"] == "h", "只有主队坏 —— 客队「山形」是被连坐的"
    # 能据此还原「真正坏掉的队名」,不把无辜队友算进去
    broken = {n[0] for n in rec["names"] if "h" in n[5]} | {n[1] for n in rec["names"] if "a" in n[5]}
    assert "山形" not in broken and "枥木城" in broken


def test_write_failure_leaves_a_trace(tmp_path, caplog) -> None:
    """⛔ 别退回静默 `pass`。这份数据结构上无法回溯、且今天**没有任何读者**
    ⇒ 静默失败 = 永久空洞且无人知晓(审查实测:`logs/` chmod 555 时 `_latest`
    的 `write_text` 照常成功而 `open("a")` 创建新文件失败 —— 体检全绿)。"""
    import logging
    from nutmeg.v4.cli import ingest_sporttery as mod
    db = _mk(tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "boom").write_text("x")
    orig = mod._UNMAPPED_HISTORY_RELPATH
    mod._UNMAPPED_HISTORY_RELPATH = "logs/boom/h.jsonl"
    try:
        with caplog.at_level(logging.WARNING):
            r = mod.harvest_to_db(db, matches=MATCHES)
    finally:
        mod._UNMAPPED_HISTORY_RELPATH = orig
    assert r["unmapped"] == 2, "写历史失败把入库打断了"
    assert any("未映射历史写入失败" in x.message for x in caplog.records), "失败没留痕"
