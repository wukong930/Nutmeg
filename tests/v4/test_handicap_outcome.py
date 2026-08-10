"""让球后结果 `handicap_outcome` —— 唯一实现 + 结算落库(2026-08-10)。

## 起因

复盘上周末让球腿时发现:`settle_jingcai_sp` 结算**让球行**时,写进 `ft_outcome`
的是 `_ft_outcome()` 的**原始 1X2 结果** —— 那段 UPDATE 完全不看 `market` 列。

⚠️ 那个值**不是错的**:90′ 的 1X2 结果对让球行也是事实。它是个**陷阱** ——
列名 `ft_outcome`、类型 INTEGER、值域 {0,1,2},三样都长得像能直接拿来算让球
命中率。实测 **404 行里 217 行(53.7%)结论是反的**(−1 线 54% / +1 线 52%)。

⭐ 真正的病灶不是「有人写错了」:这条三行规则在仓库里本来就有**三份独立实现**
(`delta_calibration` / `handicap_delta_homogeneity` / `jingcai_staleness`),
代数上全对 —— 正因为谁都有一份,**没人拥有它**,所以第四个该有它的地方
(结算写入)压根没实现,也没人发现。同族:「加列同步补 SET」。

⇒ 修法是**收成一个** + 落一列,不是再加第四份。

## 这些测试守什么

① 规则本身(表驱动,含边界:0:0 让一球、恰好抵消、缺比分)
② 结算路径**真的**把 `hc_outcome` 写进去了,且**只**写让球行
③ 库里已有的值与唯一实现一致 —— 任何地方漂了都会红
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.model.market_handicap import HANDICAP_OUTCOME_LABELS, handicap_outcome

# (主进, 客进, 让球, 期望标签) —— 手算,不是从代码抄的
_CASES = [
    # −1 线:主队让一球
    (2, 0, -1, "让胜"),      # 净胜 2 → 让后 +1
    (1, 0, -1, "让平"),      # 净胜 1 → 让后 0,**恰好抵消**
    (0, 0, -1, "让负"),
    (3, 1, -1, "让胜"),
    (0, 3, -1, "让负"),
    # +1 线:主队受让一球
    (1, 1, 1, "让胜"),       # 平 → 受让后 +1
    (0, 1, 1, "让平"),       # 输 1 → 受让后 0,**恰好抵消**
    (0, 2, 1, "让负"),
    (2, 0, 1, "让胜"),
    # −2 线
    (2, 0, -2, "让平"),
    (3, 0, -2, "让胜"),
    (1, 0, -2, "让负"),
]


@pytest.mark.parametrize(("hg", "ag", "line", "want"), _CASES)
def test_the_rule_itself(hg: int, ag: int, line: int, want: str) -> None:
    """让球后主队净胜球 = (主进 − 客进) + 让球线;>0 让胜 / =0 让平 / <0 让负。

    ⭐ 两个「恰好抵消」的用例是承重的 —— 让平就是这一格,而它正是
    owner 2026-08-10 问「是不是分多了」的那条腿。
    """
    got = handicap_outcome(hg, ag, line)
    assert got is not None
    assert HANDICAP_OUTCOME_LABELS[got] == want


@pytest.mark.parametrize(("hg", "ag", "line"), [
    (None, 0, -1), (0, None, -1), (0, 0, None), (None, None, None),
])
def test_missing_input_degrades_to_none(hg, ag, line) -> None:
    """缺任何一项 → None,不猜。⛔ 返回 0 会被静默读成「让胜」。"""
    assert handicap_outcome(hg, ag, line) is None


def test_it_disagrees_with_the_raw_1x2_result_where_it_should() -> None:
    """🚨 这条测试存在的理由:证明 `ft_outcome` 和 `hc_outcome` **不是一回事**。

    主 1:0 客、主让一球 —— 原始 1X2 是**主胜**(0),让球后是**让平**(1)。
    谁把 `ft_outcome` 当让球结果用,这一场就会被算成「押主赢了」而实际是走盘。
    """
    hg, ag, line = 1, 0, -1
    raw_1x2 = 0                                   # 主胜(_ft_outcome 会写这个)
    assert handicap_outcome(hg, ag, line) == 1    # 让平
    assert handicap_outcome(hg, ag, line) != raw_1x2


class TestSettleWritesIt:
    """结算路径的行为断言 —— 不是「源码里有没有 hc_outcome 这串字符」。"""

    def _db(self, tmp_path: Path) -> Path:
        from nutmeg.v4.observation.jingcai_sp import ensure_jingcai_sp_table
        db = tmp_path / "obs.db"
        with sqlite3.connect(db) as c:
            ensure_jingcai_sp_table(c)
            for market, hc in (("hhad", -1), ("had", None)):
                c.execute(
                    "INSERT INTO jingcai_sp (source, match_date, home_team, away_team,"
                    " market, handicap_home, captured_at)"
                    " VALUES ('test','2026-08-08','A','B',?,?,'x')",
                    (market, hc))
        return db

    def test_hhad_gets_the_handicap_result_and_had_stays_null(
        self, tmp_path: Path,
    ) -> None:
        """主 1:0 客 · 让一球 ⇒ 让球行 hc_outcome=1(让平)、ft_outcome=0(主胜);
        1X2 行 hc_outcome 必须**保持 NULL**。

        空包弹:把 settle 里的 `hc=` 那行改回 `hc = None` ⇒ 第一条断言立刻红。
        """
        import datetime as dt

        from nutmeg.v4.observation.jingcai_sp import settle_jingcai_sp

        db = self._db(tmp_path)
        fx = {"fixture": {"status": {"short": "FT"}},
              "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
              "score": {"fulltime": {"home": 1, "away": 0}}}
        # ⭐ `fetch_fixtures` 是 settle 自己的**参数**(默认才去打 AF),
        #   所以直接传桩 —— 比 monkeypatch 模块属性可靠(那个属性根本不存在)。
        n = settle_jingcai_sp(db, today=dt.date(2026, 8, 9),
                              fetch_fixtures=lambda d: [fx])
        assert n == 2, f"两行都该被结算,实际 {n}"

        with sqlite3.connect(db) as c:
            c.row_factory = sqlite3.Row
            rows = {r["market"]: r for r in c.execute(
                "SELECT market, ft_outcome, hc_outcome FROM jingcai_sp")}
        assert rows["hhad"]["hc_outcome"] == 1, "让球行没拿到让平"
        assert rows["hhad"]["ft_outcome"] == 0, "ft_outcome 该仍是原始 1X2(主胜)"
        assert rows["had"]["hc_outcome"] is None, "1X2 行不该有 hc_outcome"


def test_stored_values_match_the_single_implementation() -> None:
    """🚨 漂移捕手:库里每一行 `hc_outcome` 都必须等于唯一实现的输出。

    ⭐ 断言的是**性质**不是某个数 —— 无论以后谁在哪里改了算法,只要落库值
    和 `handicap_outcome()` 分家,这条就红。这比「查源码里还有没有第四份拷贝」
    可靠得多(那是语法代理测语义属性,本仓踩过三次)。

    没有观测库时跳过(CI 上没有这个文件)。
    """
    db = Path("data/v4_observation.db")
    if not db.exists():
        pytest.skip("没有观测库 —— 这条只在本地有意义")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, home_goals, away_goals, handicap_home, hc_outcome, market "
            "FROM jingcai_sp WHERE hc_outcome IS NOT NULL").fetchall()
    finally:
        con.close()
    if not rows:
        pytest.skip("库里还没有 hc_outcome —— 结算跑过一轮后这条才有意义")

    bad = [r["id"] for r in rows
           if handicap_outcome(r["home_goals"], r["away_goals"],
                               r["handicap_home"]) != r["hc_outcome"]]
    assert not bad, f"{len(bad)} 行的 hc_outcome 与唯一实现不一致(id 前 5: {bad[:5]})"

    stray = [r["id"] for r in rows if (r["market"] or "") != "hhad"]
    assert not stray, f"非让球行被写了 hc_outcome:{stray[:5]}"
