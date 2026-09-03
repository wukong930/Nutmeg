"""`nutmeg-book-consensus-review` —— 多书商共识事后复盘的三条承重契约。

这个 CLI 的价值全在**它拒绝做什么**上,所以测试也钉那三条:
口径不许分叉 · 样本不够不许出聚合数 · 漏斗不许撒谎。
"""
from __future__ import annotations

import re
from pathlib import Path

from nutmeg.v4.cli import book_consensus_review as R

SRC = Path("apps/api/src/nutmeg/v4/cli/book_consensus_review.py")


def test_the_league_reverse_map_is_a_bijection():
    """🚨 `jingcai_sp.league` 是竞彩**中文缩写**、`SPORT_KEYS` 按 **EN 码**索引 ——
    两套词汇。不转换的话每一场都会被标成 `bk_unavailable`,而那看起来和
    「Odds API 没有这项赛事」一模一样(第一版就这么静默丢了全部 16 场)。

    反查表必须是双射,否则会静默取错一个 EN 码。
    """
    from nutmeg.v4.data.league_labels import _EN_TO_CN
    assert len(set(_EN_TO_CN.values())) == len(_EN_TO_CN), (
        "`_EN_TO_CN` 不再是双射 —— `_en_league` 的反查会静默取错")
    # 行为断言:真的转得出来,而且转出来的码 `SPORT_KEYS` 认得
    from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
    assert R._en_league("英冠") == "ENG_CHAMPIONSHIP"
    assert SPORT_KEYS.get(R._en_league("英冠")), "转出来的码拿不到 sport_key"
    assert R._en_league("不存在的联赛") == "不存在的联赛", "转不出来必须 fail-open"
    assert R._en_league(None) == ""


def test_it_does_not_reimplement_the_consensus():
    """⛔ 口径同源:共识必须由生产的 `_attach_book_consensus` 挂,本文件不许自己算。

    复刻会在生产改口径时静默分叉 —— 这一层刚因为「比例归一 vs WPO」两把尺子
    并排吃过亏(逐场共识位移中位 1.17pp ≈ EV 3.5pp)。
    """
    src = SRC.read_text(encoding="utf-8")
    assert "_attach_book_consensus" in src, "没调生产函数 ⇒ 口径迟早分叉"
    # 🚨 人口非平凡:确认这些字眼在生产文件里**确实存在**,否则下面的「不存在」空洞为真
    prod = Path("apps/api/src/nutmeg/v4/api/routes.py").read_text(encoding="utf-8")
    for token in ("statistics", "median", "min("):
        assert token in prod, f"生产文件里没有 {token!r} ⇒ 这条断言在测一个不存在的东西"
    body = re.sub(r'""".*?"""', "", src, flags=re.S)          # 去掉 docstring 再查
    for token in ("median(", "_st.", "1.0 / float("):
        assert token not in body, f"复盘 CLI 自己实现了 {token!r} ⇒ 口径会分叉"


def test_it_refuses_to_aggregate_below_the_floor(capsys):
    """🚨 承重:样本不够时**不许出任何聚合百分比**。

    一个 N=16 的百分比会被记住,而它的置信区间不会。
    """
    assert R._MIN_N_FOR_AGGREGATE >= 50, "下限被调低了 —— 会开始出噪声数字"
    matches = [{"match_date": "2026-09-01", "league": "英冠", "home_team": "A",
                "away_team": "B", "jc_home": 2.0, "jc_draw": 3.4, "jc_away": 3.6,
                "ft_outcome": 0, "pin": [0.5, 0.25, 0.25], "cons": [0.49, 0.26, 0.25],
                "low": [0.47, 0.24, 0.23], "spread": [2.0, 1.5, 1.8],
                "n_books": 20, "captured_at": "2026-09-01T13:00:00+00:00"}]
    import unittest.mock as mock
    with mock.patch.object(R, "_load", return_value=(matches * 3, {"人口": 3})):
        R.main(["--db", "x"])
    out = capsys.readouterr().out
    assert "不出聚合数字" in out
    # ⚠️ 不能断言「输出里没有 Brier 这个词」—— 拒绝文案自己就提到了它
    #    (我第一版这么写,当场假红)。要断言的是**没有算出来的值**。
    assert not re.search(r"Brier.*单锚\s+0\.\d", out), "样本不够却打印了 Brier 数值"
    assert "共识在命中腿上更高" not in out


def test_the_aggregate_kicks_in_above_the_floor(capsys):
    """⚠️ 对照组:够了就必须真的出数 —— 否则上一条可能只是因为它永远不出数。"""
    import unittest.mock as mock
    m = {"match_date": "2026-09-01", "league": "英冠", "home_team": "A", "away_team": "B",
         "jc_home": 2.0, "jc_draw": 3.4, "jc_away": 3.6, "ft_outcome": 0,
         "pin": [0.5, 0.25, 0.25], "cons": [0.49, 0.26, 0.25], "low": [0.47, 0.24, 0.23],
         "spread": [2.0, 1.5, 1.8], "n_books": 20, "captured_at": "2026-09-01T13:00:00+00:00"}
    with mock.patch.object(R, "_load",
                           return_value=([dict(m)] * R._MIN_N_FOR_AGGREGATE, {"人口": 0})):
        R.main(["--db", "x"])
    out = capsys.readouterr().out
    assert "Brier" in out and "不出聚合数字" not in out


def test_it_measures_accuracy_not_roi():
    """⛔ 这一层只显示不判闸 ⇒ 没有「按共识下注」的人口 ⇒ 不许算 ROI。"""
    r = R.analyze([{"pin": [0.5, 0.25, 0.25], "cons": [0.49, 0.26, 0.25], "ft_outcome": 0}])
    assert set(r) == {"n", "共识在命中腿上更高", "Brier_单锚", "Brier_共识"}
    assert not any("roi" in k.lower() or "收益" in k for k in r)


def test_load_actually_converts_the_league_end_to_end(tmp_path):
    """🚨 上面那条只测了 `_en_league` **本身**,没测 `_load` 真的调了它 ——
    空包弹「把调用换回 `r['league']`」当场溜过去了,而那正是我踩过的 bug:
    16 场全被标成 `bk_unavailable`,看起来和「Odds API 没这项赛事」一模一样。

    ⇒ 这条走**端到端**:库里放一场中文联赛的比赛,`_load` 必须把它带出来。
    """
    import json
    import sqlite3

    db = str(tmp_path / "obs.db")
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE jingcai_sp (market TEXT, match_date TEXT, league TEXT,
        home_team TEXT, away_team TEXT, jc_home REAL, jc_draw REAL, jc_away REAL,
        psc_home REAL, psc_draw REAL, psc_away REAL, ft_outcome INT)""")
    conn.execute("""CREATE TABLE book_snapshots (captured_at TEXT, match_date TEXT,
        home_team TEXT, away_team TEXT, n_books INT, books TEXT)""")
    # ⚠️ league 存的是竞彩**中文缩写** —— 这就是被测的那个转换
    conn.execute("INSERT INTO jingcai_sp VALUES ('had','2026-09-01','英冠','Burnley',"
                 "'Middlesbrough',2.0,3.4,3.6,1.95,3.5,3.7,0)")
    books = {f"bk{i}": [2.0 + i * 0.02, 3.4, 3.6] for i in range(8)}
    conn.execute("INSERT INTO book_snapshots VALUES (?,?,?,?,?,?)",
                 ("2026-09-01T13:00:00+00:00", "2026-09-01", "Burnley",
                  "Middlesbrough", len(books), json.dumps(books)))
    conn.commit(); conn.close()

    matches, funnel = R._load(db, None, None)

    assert funnel["竞彩已结算(有 SP + 有 Pinnacle 锚)"] == 1, "人口非平凡:那一场必须进来"
    assert len(matches) == 1, (
        f"中文联赛名没被转成 EN 码 ⇒ 整场被标成「未接入」而静默消失。漏斗:{funnel}")
    assert matches[0]["cons"], "共识没挂上"
