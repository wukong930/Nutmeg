"""season 推导错 ⇒ 合法返回 []:按日兜底 + 喊出来(owner 2026-08-05)。

## 事故

owner 报「竞彩 08-07 上架了日职,我们面板一场都没有」。溯源到**第三类**原因 ——
不是「没有比赛」,也不是「没去抓」,是**「去抓了,但问错了赛季」**:

J1 从 2026-08-07 起改秋春制,API-Football 把这批 fixture 标成 ``season=2027``,
而 `season_for_date` 给 2026 ⇒ ``/fixtures?date=2026-08-07&league=98&season=2026``
**合法地**返回 ``[]``。实测两个缓存文件并排:

    {"date":"2026-08-07"}                          → 324 场 / 142 联赛,含 2 场 J1
    {"date":"2026-08-07","league":98,"season":2026} → []  (文件字面 2 字节)

那 2 场:``Yokohama F. Marinos vs Kashima`` / ``Gamba Osaka vs Urawa``,
``league.season = 2027``、``round = "Regular Season - 1"``(新赛季第 1 轮)。

⚠️ **显而易见的修法是错的**:把 `JPN_J1` 移出 `CALENDAR_YEAR_LEAGUES` 不管用 ——
日历年分支给 `on_date.year`=2026,欧洲启发式对 8 月也给 2026,**两个分支都产生
不了 2027**。所以本文件**特意**有一条用例钉住这一点。

## 修法与它守的性质

不给每个联赛维护赛制切换表(那还是在猜),而是**让 API 自己说**:league 查询空了
就用同日**无过滤**查询复核 —— 它覆盖全部联赛、每个 fixture 自带 `league.season`。
⇒ 「0 场」从「可能是我 season 猜错了」变成**可证的缺席**。同族见
[[health-check-guardrails]] 的「零新增 ≠ 扫完了」。

自愈必须**喊出来**:静默兜住等于你永远不知道 season 表已经错了。
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from nutmeg.v4.data.sources import api_football as af

#: 真实形状(抄自 `_fixtures/e73c6e9a8739.json` 里那两条)
_J1 = [
    {"fixture": {"id": 1, "date": "2026-08-07T10:25:00+00:00"},
     "league": {"id": 98, "name": "J1 League", "season": 2027,
                "round": "Regular Season - 1"},
     "teams": {"home": {"name": "Yokohama F. Marinos"}, "away": {"name": "Kashima"}}},
    {"fixture": {"id": 2, "date": "2026-08-07T10:30:00+00:00"},
     "league": {"id": 98, "name": "J1 League", "season": 2027,
                "round": "Regular Season - 1"},
     "teams": {"home": {"name": "Gamba Osaka"}, "away": {"name": "Urawa"}}},
]
_OTHERS = [
    {"fixture": {"id": 9, "date": "2026-08-07T18:30:00+00:00"},
     "league": {"id": 79, "name": "2. Bundesliga", "season": 2026},
     "teams": {"home": {"name": "VfL Bochum"}, "away": {"name": "Hertha BSC"}}},
]


@pytest.fixture
def cdir(tmp_path):
    #: 真目录 —— `fetch_fixtures_for_date` 的 TTL 分支会 `Path(cache_dir)`,
    #: 传 None 直接抛。桩只该替换 HTTP,不该改变它周围的前提。
    return tmp_path


@pytest.fixture
def api(monkeypatch):
    """把 `_request` 换成一个**按参数分派**的假 API,记录每次调用。

    ⚠️ 桩打在 HTTP 边界上,`fetch_fixtures_for_date` / `_confirm_absence_by_date`
    / `season_for_date` 全部走真实代码 —— 被测的是它们的协作,不是桩。
    """
    calls: list[dict] = []

    def fake_request(path, params, *, cache_dir=None, refresh=False):
        calls.append(dict(params))
        if "league" not in params:
            return _J1 + _OTHERS                    # 无过滤:全都有
        # 带 league+season:只有 season 对上才给
        want = {98: 2027, 79: 2026}.get(params["league"])
        if params.get("season") == want:
            return [r for r in _J1 + _OTHERS if r["league"]["id"] == params["league"]]
        return []                                    # ← 事故现场:合法的空
    monkeypatch.setattr(af, "_request", fake_request)
    return calls


D = date(2026, 8, 7)


class TestTheOriginalBug:
    def test_our_season_guess_is_wrong_for_j1(self):
        """先钉死病因本身:我们算 2026,API 说 2027。"""
        assert af.season_for_date(D, "JPN_J1") == 2026
        assert {r["league"]["season"] for r in _J1} == {2027}

    def test_neither_branch_can_produce_2027(self):
        """⭐ 钉死「显而易见的修法是错的」。

        把 JPN_J1 移出 `CALENDAR_YEAR_LEAGUES` 之后走欧洲启发式 —— 8 月 ≥ 7
        ⇒ 还是 `on_date.year` = 2026。两条路都到不了 2027,所以不能靠调这张表修。
        """
        assert af.season_for_date(D, "JPN_J1") == 2026            # 日历年分支
        assert af.season_for_date(D, "EPL") == 2026               # 欧洲启发式分支
        assert af.season_for_date(D, None) == 2026                # 无联赛


class TestFallbackRecoversThem:
    def test_j1_fixtures_come_back(self, api, cdir):
        rows = af.fetch_fixtures_for_date(D, "JPN_J1", cache_dir=cdir)
        assert len(rows) == 2, "按日兜底没把 J1 捞回来"
        assert {r["teams"]["home"]["name"] for r in rows} == {
            "Yokohama F. Marinos", "Gamba Osaka"}

    def test_fallback_filters_to_the_asked_league(self, api, cdir):
        """兜底不是「把当天 324 场全塞回去」—— 只筛出问的那个联赛。"""
        rows = af.fetch_fixtures_for_date(D, "JPN_J1", cache_dir=cdir)
        assert all(r["league"]["id"] == 98 for r in rows)
        assert not any(r["league"]["id"] == 79 for r in rows)

    def test_costs_exactly_one_extra_call(self, api, cdir):
        """第一次带 league+season(空)+ 一次不带 league。不多打。"""
        af.fetch_fixtures_for_date(D, "JPN_J1", cache_dir=cdir)
        assert len(api) == 2, api
        assert api[0]["league"] == 98 and api[0]["season"] == 2026
        assert "league" not in api[1] and "season" not in api[1]

    def test_no_fallback_when_the_league_query_already_worked(self, api, cdir):
        """season 对得上的联赛照旧一次调用 —— 不给正常路径加成本。"""
        rows = af.fetch_fixtures_for_date(D, "GER_2_BUNDESLIGA", cache_dir=cdir)
        assert len(rows) == 1 and len(api) == 1, api

    def test_genuinely_absent_league_still_returns_empty(self, api, cdir):
        """⭐ 兜底**不许**把「真的没有」变成「有」。

        问一个当天确实没比赛的联赛:两次调用都空 ⇒ 返回 []。
        这条红了就说明兜底在瞎捞。
        """
        rows = af.fetch_fixtures_for_date(D, "EPL", cache_dir=cdir)
        assert rows == []
        assert len(api) == 2, "该复核的还是要复核(0 场必须是可证的)"

    def test_no_infinite_recursion(self, api, cdir):
        """兜底自己调的是**不带 league** 的那条路 ⇒ 不会再触发兜底。"""
        af.fetch_fixtures_for_date(D, None, cache_dir=cdir)
        assert len(api) == 1


class TestItShoutsInsteadOfHealingSilently:
    def test_warns_with_the_real_season(self, api, cdir, caplog):
        """⚠️ 自愈而不告诉你 = 你永远不知道 season 表已经错了。
        告警里必须带**真实 season**,否则看到告警也不知道该改成什么。"""
        import logging
        with caplog.at_level(logging.WARNING):
            af.fetch_fixtures_for_date(D, "JPN_J1", cache_dir=cdir)
        # `caplog.records[i].message` 已经是格式化后的,再 `% args` 会二次格式化;
        # `getMessage()` 才是「取最终文本」的正道。
        msg = "\n".join(r.getMessage() for r in caplog.records)
        assert "JPN_J1" in msg and "2027" in msg, msg
        assert "2026" in msg, "没说我们问的是哪个 season,没法对照"

    def test_silent_when_the_league_is_genuinely_absent(self, api, cdir, caplog):
        """真的没比赛不该报警 —— 老误报的护栏最后会被删掉。"""
        import logging
        with caplog.at_level(logging.WARNING):
            af.fetch_fixtures_for_date(D, "EPL", cache_dir=cdir)
        assert not [r for r in caplog.records if "season" in r.getMessage()], caplog.records


class TestDegradesSafely:
    def test_network_failure_falls_back_to_empty_not_a_crash(self, monkeypatch, cdir):
        """兜底那一跳失败(断网/额度耗尽)⇒ 退回「就是没有」,不比修复前更差。"""
        def boom(path, params, *, cache_dir=None, refresh=False):
            if "league" in params:
                return []
            raise af.ApiFootballError("network down")
        monkeypatch.setattr(af, "_request", boom)
        assert af.fetch_fixtures_for_date(D, "JPN_J1", cache_dir=cdir) == []


def test_the_real_cache_still_shows_the_bug_shape(tmp_path):
    """拿**真缓存**核一次形状(存在才跑)—— 桩再像也不是真的。"""
    from pathlib import Path
    empty = Path("data/external/api_football/_fixtures/47cf61db5176.json")
    allday = Path("data/external/api_football/_fixtures/e73c6e9a8739.json")
    if not (empty.exists() and allday.exists()):
        pytest.skip("真缓存不在(CI)")
    assert json.loads(empty.read_text()) == [], "那份 league+season 的缓存不再是空的"
    rows = json.loads(allday.read_text())
    j1 = [r for r in rows if r["league"]["id"] == 98]
    assert j1, "同日无过滤缓存里没有 J1 —— 前提变了,本文件的事故叙述要重查"
    assert {r["league"]["season"] for r in j1} == {2027}
