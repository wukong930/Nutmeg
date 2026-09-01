"""多书商共识参照 —— 存储 / 计算 / 前端接线(2026-09-01)。

## 它回答的问题

owner 的原始需求:竞彩**封盘后**价格冻住而外盘还在动 —— 按封盘价算的 EV 还站得住吗?
实测封盘后主胜隐含概率漂移 **|漂移|>2pp 占 29%、>5pp 占 5%**(区间 [−12.4,+9.7]pp),
量级远大于所有 δ 校正。生产 EV 用的已经是**实时** Pinnacle,所以漂移本身吃进去了;
**本层补的是另一半:那次漂移是真信息,还是 Pinnacle 一家的抖动?**

⭐ 已测:单锚会**夸大** —— 法乙那场 Pinnacle 是 13 家里最看好客胜的,
单锚 EV **+16.7%** vs 13 家中位 **+8.8%** vs 最保守 **−0.6%**(近一倍)。

⛔ 63 场重叠样本**全是世界杯 + 全是缓存未过期的**,人口偏斜 ⇒ 只证明机制存在,
**不是**影响多大的估计 ⇒ 这一层永远不判闸。下面有一条测试专门钉死这件事。
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


# ── 存储层 ────────────────────────────────────────────────────────────────
def _books(pin=(2.10, 3.40, 3.60), other=(2.05, 3.50, 3.70)):
    return {"pinnacle": list(pin), "betfair_ex_eu": list(other),
            "williamhill": [2.08, 3.45, 3.65], "unibet_fr": [2.12, 3.38, 3.55],
            "marathonbet": [2.09, 3.42, 3.62]}


def _write(tmp_path, books, **kw):
    from nutmeg.v4.observation.book_snapshots import record_book_snapshot
    return record_book_snapshot(
        tmp_path / "obs.db", match_date="2026-09-01",
        home_team="West Ham", away_team="Wolves", books=books, **kw)


def test_a_snapshot_is_written_and_reread(tmp_path: Path) -> None:
    assert _write(tmp_path, _books()) is True
    conn = sqlite3.connect(tmp_path / "obs.db")
    n, blob = conn.execute("SELECT n_books, books FROM book_snapshots").fetchone()
    assert n == 5
    assert json.loads(blob)["pinnacle"] == [2.10, 3.40, 3.60]


def test_an_unchanged_line_state_is_not_re_written(tmp_path: Path) -> None:
    """⛔ cron 每天多窗跑,价格没动就不该在表里堆重复行(同 `odds_snapshots` 的态度)。"""
    assert _write(tmp_path, _books()) is True
    assert _write(tmp_path, _books()) is False
    conn = sqlite3.connect(tmp_path / "obs.db")
    assert conn.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0] == 1


def test_a_moved_line_is_written_again(tmp_path: Path) -> None:
    assert _write(tmp_path, _books()) is True
    assert _write(tmp_path, _books(pin=(2.30, 3.40, 3.20))) is True
    conn = sqlite3.connect(tmp_path / "obs.db")
    assert conn.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0] == 2


def test_insane_odds_are_gated_out(tmp_path: Path) -> None:
    """物理闸:(1.0, 1000] 之外的不收 —— 同 `odds_snapshots._sane_odds`。"""
    b = _books()
    b["broken"] = [0.5, 1.0, -3.0]
    b["also_broken"] = ["x", "y", "z"]
    assert _write(tmp_path, b) is True
    conn = sqlite3.connect(tmp_path / "obs.db")
    n, blob = conn.execute("SELECT n_books, books FROM book_snapshots").fetchone()
    assert n == 5, f"坏赔率没被闸掉:{json.loads(blob).keys()}"


def test_a_failure_never_raises(tmp_path: Path) -> None:
    """本模块契约:采集路径上**绝不抛**。"""
    from nutmeg.v4.observation.book_snapshots import record_book_snapshot
    assert record_book_snapshot(tmp_path / "nope" / "x.db", match_date="", home_team="",
                                away_team="", books={}) is False


# ── 计算层 ────────────────────────────────────────────────────────────────
def _pred(**kw):
    from nutmeg.v4.api.schemas import SinglePrediction
    base = dict(date=dt.date(2026, 9, 1), home_team="West Ham", away_team="Wolves",
                league="ENG_CHAMPIONSHIP", lambda_home=1.4, lambda_away=1.1,
                p_home_1x2=0.4, p_draw_1x2=0.3, p_away_1x2=0.3,
                jc_home=1.92, jc_draw=3.5, jc_away=3.1)
    base.update(kw)
    return SinglePrediction(**base)


def _attach(tmp_path, monkeypatch, books):
    from nutmeg.v4.api import routes
    _write(tmp_path, books)
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "obs.db"))
    p = _pred()
    routes._attach_book_consensus([p])
    return p


def test_consensus_excludes_pinnacle_itself(tmp_path, monkeypatch) -> None:
    """🚨 承重:共识**排除 Pinnacle**。

    含它的中位会被它拖着走 ⇒ 答不了「Pinnacle 是不是在自说自话」这个问题,
    而那正是这一层存在的唯一理由。
    构造:Pinnacle 是极端离群,其余 4 家一致 ⇒ 共识必须**完全不受它影响**。
    """
    tight = {"a": [3.0, 3.0, 3.0], "b": [3.0, 3.0, 3.0],
             "c": [3.0, 3.0, 3.0], "d": [3.0, 3.0, 3.0]}
    p_out = _attach(tmp_path, monkeypatch, {**tight, "pinnacle": [1.01, 100.0, 100.0]})
    assert p_out.bk_consensus is not None
    assert abs(p_out.bk_consensus[0] - 1 / 3) < 1e-9, p_out.bk_consensus
    assert p_out.bk_spread == [0.0, 0.0, 0.0], "其余 4 家完全一致,离散该是 0"
    assert p_out.bk_n == 5, "n 要算上 Pinnacle(它在场,只是不进共识)"


def test_too_few_books_gives_nothing(tmp_path, monkeypatch) -> None:
    """⛔ 2 家的「共识」不是共识 —— 少于闸值直接不给,而不是给一个弱的。"""
    p_out = _attach(tmp_path, monkeypatch, {"pinnacle": [2.1, 3.4, 3.6], "a": [2.0, 3.5, 3.7]})
    assert p_out.bk_consensus is None and p_out.bk_n is None


def test_spread_is_in_percentage_points(tmp_path, monkeypatch) -> None:
    """离散度的单位是 **pp**,不是小数 —— 前端直接按 pp 上色,单位错了阈值全废。"""
    spread = {"a": [2.0, 4.0, 4.0], "b": [2.0, 4.0, 4.0], "c": [2.5, 3.5, 3.5],
              "d": [2.5, 3.5, 3.5], "pinnacle": [2.2, 3.8, 3.8]}
    p_out = _attach(tmp_path, monkeypatch, spread)
    assert p_out.bk_spread is not None
    assert 1.0 < max(p_out.bk_spread) < 100.0, p_out.bk_spread


def test_a_missing_table_is_silent(tmp_path, monkeypatch) -> None:
    """新库还没这张表 ⇒ 静默跳过,⛔ 不许让卡片渲染失败。"""
    from nutmeg.v4.api import routes
    (tmp_path / "empty.db").touch()
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "empty.db"))
    p = _pred()
    routes._attach_book_consensus([p])
    assert p.bk_consensus is None


# ── 前端接线 ──────────────────────────────────────────────────────────────
def _html() -> str:
    return (REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text(encoding="utf-8")


def test_the_panel_never_feeds_the_gate() -> None:
    """🚨 承重:参照层**绝不进判闸/排序/串关**。

    支持它的 63 场样本人口偏斜(全世界杯 + 全缓存未过期)⇒ 只证明机制存在。
    这条钉的是「有人顺手把 bk_consensus 接进 evLo」。
    """
    h = _html()
    for fn in ("_boardLegs", "_parlayPool", "_sweetBoard"):
        i = h.find("function " + fn)
        if i < 0:
            continue
        body = h[i:i + 4000]
        assert "bk_consensus" not in body and "bk_low" not in body, (
            f"{fn} 里出现了 bk_* —— 参照层泄进了判闸路径")


@pytest.mark.parametrize("sel", [".spcalc-sp", ".cupsp"])
def test_the_refresh_uses_a_selector_that_actually_exists(sel: str) -> None:
    """🚨 我 2026-09-01 在这里栽过:按对称猜了 `.cupmkt-sp`,而真名是 `.cupsp`。

    猜错的后果是**静默失效** —— `querySelector` 返回 null ⇒ EV 格永远显示 `--`,
    不报错、不变红。⇒ 断言选择器在页面里**不止出现在我自己那行**。
    """
    h = _html()
    assert h.count(sel) > 1, f"{sel} 只出现一次 ⇒ 多半是只在刷新函数里,页面上根本没有"


def test_both_recalc_paths_refresh_the_panel() -> None:
    """手填竞彩 SP 后两条重算路都要刷新参照面板。

    ⚠️ 修的是一个真 bug:`_bkHtml` 是**渲染时烘进 HTML** 的,而 recalc 只改
    `#spcalc-ev-*` ⇒ 手填后真 EV 更新了、参照面板停在旧值。
    **两个数并排而其中一个是陈的,比不显示更坏** —— 它看起来像「共识不同意」,
    其实只是没跟上。
    """
    h = _html()
    for fn in ("_spcalcRecalc", "_cupRecalc"):
        i = h.index("function " + fn)
        assert "_bkEvRefresh" in h[i:i + 2500], f"{fn} 没接刷新"


def test_the_ev_cells_are_addressable() -> None:
    """就地更新的前提:EV 格子有 id。⛔ 不重渲整块 —— 那会把 <details> 收起来。"""
    h = _html()
    # ⚠️ 断言的是**行为形状**(格子有可寻址 id + 刷新函数按同一模式取它),
    #    不是某一行的字面量 —— 后者会因为换个拼法而假红。
    assert 'id="bk-ev-\' + idx + \'-\' + i + \'-c"' in h, "共识 EV 格没有 id"
    assert 'id="bk-ev-\' + idx + \'-\' + i + \'-l"' in h, "保守 EV 格没有 id"
    assert "getElementById('bk-ev-' + idx + '-' + i + '-' + pair[0])" in h, "刷新函数没按同一模式取格子"


# ── join 层(2026-09-01 抽出 `team_match` 后新增)──────────────────────────
def test_a_match_with_many_rows_still_resolves(tmp_path, monkeypatch) -> None:
    """🚨 回归:`book_snapshots` 是 **append-only**,同一场比赛有多行(线态变了就再写)。

    我第一版把唯一性闸写成 `len(cands) != 1` —— 数的是**行数**而不是**不同的比赛**
    ⇒ 任何被抓过两次的场次一律被拒。实测后果:**英冠 2→0、日职 5→0**,
    原本能用的两个联赛全废。

    ⭐⭐ 而**总数反而从 17 涨到 24**(别的联赛刚补进来)——**聚合量把回归盖住了**,
    是逐联赛那张表才看见的。同 memory `first-match-is-not-the-population`
    「聚合量不是指纹」。⇒ 唯一性判据必须先按队名对**折叠**,再判唯一。
    """
    from nutmeg.v4.api import routes
    _write(tmp_path, _books(), captured_at="2026-09-01T08:00:00+00:00")
    _write(tmp_path, _books(pin=(2.20, 3.35, 3.50)), captured_at="2026-09-01T12:00:00+00:00")
    conn = sqlite3.connect(tmp_path / "obs.db")
    assert conn.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0] == 2, "夹具没造出多行"
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "obs.db"))
    p = _pred()
    routes._attach_book_consensus([p])
    assert p.bk_consensus is not None, "同一场多行就解析不出 —— 唯一性闸又数成行数了"
    assert p.bk_captured_at == "2026-09-01T12:00:00+00:00", "没取最新那行"


def test_the_join_survives_long_vs_short_names(tmp_path, monkeypatch) -> None:
    """⭐ 承重:Odds API 用**全称**、盘面用 AF **短名**,join 必须过 `team_match`。

    裸 `_norm_team` 时实测 12 场英冠只通了 1 场(West Ham 那场碰巧两侧都短)。
    """
    from nutmeg.v4.api import routes
    from nutmeg.v4.observation.book_snapshots import record_book_snapshot
    record_book_snapshot(tmp_path / "obs.db", match_date="2026-09-01",
                         home_team="Lincoln City", away_team="Blackburn Rovers",
                         books=_books())
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "obs.db"))
    p = _pred(home_team="Lincoln", away_team="Blackburn", league="ENG_CHAMPIONSHIP")
    routes._attach_book_consensus([p])
    assert p.bk_consensus is not None, "全称↔短名对不上 —— join 没走 team_match"


def test_a_league_with_no_odds_api_sport_is_marked_not_silent(tmp_path, monkeypatch) -> None:
    """⚠️「这项赛事永远不会有」和「今天还没抓到」必须分开。

    不分开的话 owner 会一直等一个不会来的东西(日联赛杯/意大利杯/德国杯
    在 Odds API 上根本没有对应 sport,同 JPN_J2/荷乙缺 key)。
    """
    from nutmeg.v4.api import routes
    _write(tmp_path, _books())
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "obs.db"))
    p = _pred(league="JPN_LEAGUE_CUP")
    routes._attach_book_consensus([p])
    assert p.bk_unavailable is True and p.bk_consensus is None
    q = _pred(league="ENG_CHAMPIONSHIP")
    routes._attach_book_consensus([q])
    assert q.bk_unavailable is False, "有 sport_key 的不该被标成无源"


def test_the_shared_matcher_is_used_by_both_consumers() -> None:
    """⛔ 一处定义:`polymarket_match` 与共识 join 必须用**同一套**判据。

    2026-09-01 一天之内两个消费方各踩一次同一个病(全称 vs 短名)⇒
    复制第三份就是平行入口。`polymarket_match` 按原名转发,行为不变。
    """
    from nutmeg.v4.data import polymarket_match as pm
    from nutmeg.v4.data import team_match as tm
    assert pm._core is tm._core and pm._resolve is tm._resolve
    assert pm._prefix_extra is tm._prefix_extra
