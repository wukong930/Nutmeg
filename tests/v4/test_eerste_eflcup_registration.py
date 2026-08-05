"""荷乙 + 英联赛杯注册进市场模式(owner 2026-08-05)。

## 为什么单开一个文件

注册一个市场模式竞赛要碰 7 个分散的地方,漏任何一个都是**静默丢场** ——
不报错,只是面板上没有。`TestMarketModeExpansion` 是 V12 W8 那批的模板,
但这两个竞赛在两点上和它不同,所以另起一档把差异钉死:

1. **英联赛杯是 cup,荷乙是 league** —— id 的落点不同(`CUP_COMPETITIONS`
   vs `_DOMESTIC_LEAGUE_IDS`),且 `_NON_DOMESTIC_CN` 只收前者。
2. **荷乙故意没有 Odds API sport key** —— 见下。

## 每个 id / key 的证据(不是查表猜的)

* 荷乙 = `Eerste Divisie` **id 89**,country=Netherlands。本地 fixtures 缓存实证
  (season 2025 与 2026 都在)。⚠️ 荷兰另有 `Tweede Divisie`=492,别串。
* 英联赛杯 = `League Cup` **id 48**,country=**England**。⚠️ 同名的 `League Cup`
  在苏格兰(185)/埃及(895)/泰国(898) 都存在 —— 只按名字挑必然挑错。
* 中文写法实证自 `crown_close_history.league_cn`:「荷乙」105 行、「英联赛杯」
  23 行。**不是**照联赛全名意译的。
* `soccer_england_efl_cup`:/sports?all=true live 核实 active=True。
* **荷乙没有 sport key**:整个 Odds API 174 个 sport 里,荷兰只有
  `soccer_netherlands_eredivisie`。同 `JPN_J2` 先例 —— 留空走 AF 的 Pinnacle
  镜像(实测 fixture 1551741 有 Pinnacle)。本文件**钉死这个空**,免得后人
  当成漏配去「补全」一个不存在的 key(那会让每次 fetch 404 当空)。
"""
from __future__ import annotations

import pytest

from nutmeg.v4.data.league_labels import _NON_DOMESTIC_CN, canonical_league
from nutmeg.v4.data.sources.api_football import (
    API_FOOTBALL_LEAGUE_IDS,
    CALENDAR_YEAR_LEAGUES,
    season_for_date,
)

NEW = ("NED_EERSTE_DIVISIE", "EFL_CUP")


class TestIdsPinnedWithEvidence:
    def test_ids_are_registered_and_pinned(self):
        """AF 静默改号 = 抓回另一个联赛且**不报错**,所以 id 必须钉死。"""
        assert API_FOOTBALL_LEAGUE_IDS["NED_EERSTE_DIVISIE"] == 89
        assert API_FOOTBALL_LEAGUE_IDS["EFL_CUP"] == 48

    def test_eerste_divisie_is_not_tweede_divisie(self):
        """⚠️ 荷兰有两个下级联赛,492 是 Tweede。挑错一个不会报错,只会全年错。"""
        assert API_FOOTBALL_LEAGUE_IDS["NED_EERSTE_DIVISIE"] != 492
        assert API_FOOTBALL_LEAGUE_IDS["NED_EERSTE_DIVISIE"] != \
            API_FOOTBALL_LEAGUE_IDS["NED_EREDIVISIE"]

    def test_cup_id_did_not_collide_with_the_other_league_cups(self):
        """⚠️ `League Cup` 这个名字苏格兰/埃及/泰国都有 —— 认 id 不认名字。"""
        assert API_FOOTBALL_LEAGUE_IDS["EFL_CUP"] not in (185, 895, 898)

    def test_cup_id_flows_through_the_derived_merge(self):
        """`API_FOOTBALL_LEAGUE_IDS` 是 `_merged_league_ids()` **派生**的 ——
        杯赛只写 `CUP_COMPETITIONS` 就够。这条守住那条派生链没断。"""
        from nutmeg.v4.data.competitions import CUP_COMPETITIONS
        assert CUP_COMPETITIONS["EFL_CUP"].api_football_id == 48
        assert API_FOOTBALL_LEAGUE_IDS["EFL_CUP"] == \
            CUP_COMPETITIONS["EFL_CUP"].api_football_id


class TestServedInMarketModeOnly:
    def test_both_in_market_mode(self):
        from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS
        for lg in NEW:
            assert lg in _CUP_MARKET_COMPETITIONS, f"{lg} 不在市场模式集 ⇒ 静默不出卡"

    def test_neither_enters_the_model_board(self):
        """两者都没训练过 ⇒ 绝不能进模型盘,否则是拿 OOD 模型定价。"""
        from nutmeg.v4.api.routes import _SP_CALC_LEAGUES
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        for lg in NEW:
            assert lg not in _SP_CALC_LEAGUES
            assert lg not in TodayRecommendationsRequest().leagues


class TestSeasonConvention:
    def test_neither_is_calendar_year(self):
        """荷乙 Aug–May、英联赛杯 Aug–Feb ⇒ 都走欧洲启发式。"""
        for lg in NEW:
            assert lg not in CALENDAR_YEAR_LEAGUES

    def test_season_matches_what_af_actually_tags(self):
        """⭐ 这条是 J1 那次事故的疫苗:`season_for_date` 猜错 ⇒ 查询**合法地**
        返回 [],看起来像「没有比赛」。荷乙 08-07 首轮实测 AF 标 season=2026。"""
        import datetime as dt
        assert season_for_date(dt.date(2026, 8, 7), "NED_EERSTE_DIVISIE") == 2026
        assert season_for_date(dt.date(2026, 8, 7), "EFL_CUP") == 2026


class TestLabels:
    @pytest.mark.parametrize(("zh", "en"), [
        ("荷乙", "NED_EERSTE_DIVISIE"),
        ("英联赛杯", "EFL_CUP"),
    ])
    def test_zh_and_en_collapse_to_one_group(self, zh, en):
        """双轨:cron 写中文、market_mode 写 EN。不收敛 = per-league 闸把一个
        联赛当两个成员数。中文写法取自皇冠线史实证,不是意译。"""
        assert canonical_league(zh) == canonical_league(en)

    def test_only_the_cup_is_non_domestic(self):
        """⭐ 两者在 `_NON_DOMESTIC_CN` 上**必须分开**:

        英联赛杯是国内俱乐部**杯赛** ⇒ 不在 δ 的拟合人口里(δ 拟合在各国联赛
        CSV 上)。荷乙是国内俱乐部**联赛** ⇒ 正是该计数的人口 —— 「模型没训练
        它」和「它是不是联赛」是两件事,别混。
        """
        assert "英联赛杯" in _NON_DOMESTIC_CN
        assert "荷乙" not in _NON_DOMESTIC_CN


class TestOddsSourcing:
    def test_efl_cup_has_a_live_verified_sport_key(self):
        from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
        assert SPORT_KEYS["EFL_CUP"] == "soccer_england_efl_cup"

    def test_eerste_divisie_deliberately_has_no_sport_key(self):
        """⭐ 钉死一个**故意的空**。

        Odds API 全表 174 个 sport,荷兰只有 `soccer_netherlands_eredivisie`。
        这个空不是漏配 —— 后人若「补全」一个猜出来的 key,fetch 会每次 404,
        而 404 在这套代码里长得和「空结果」一模一样(见 [[curl-404-masquerades
        -as-empty-result]]),等于把一个已知的降级换成一个查不出的静默失败。

        它靠 AF 的 Pinnacle 镜像出线,代价是线更旧一些 —— 那是数据现实。
        """
        from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
        assert "NED_EERSTE_DIVISIE" not in SPORT_KEYS
        assert not any("eerste" in v.lower() for v in SPORT_KEYS.values())

    def test_sport_key_values_stay_unique(self):
        """反向查表要能唯一定位 —— 新键不许和已有键撞。"""
        from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
        vals = list(SPORT_KEYS.values())
        assert len(vals) == len(set(vals)), \
            [v for v in vals if vals.count(v) > 1]


class TestCoverageSweep:
    def test_eerste_divisie_is_swept_by_registry_coverage(self):
        from nutmeg.v4.cli.registry_coverage import MARKET_MODE_LEAGUES
        assert "NED_EERSTE_DIVISIE" in MARKET_MODE_LEAGUES

    def test_dashboard_knows_both_labels_and_colors(self):
        """前端缺映射不会报错,只会显示裸代码 + 灰色 —— 静默难看。"""
        from pathlib import Path
        dash = (Path(__file__).resolve().parents[2]
                / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text()
        for token in ("NED_EERSTE_DIVISIE: '荷乙'", "EFL_CUP: '英联赛杯'",
                      "NED_EERSTE_DIVISIE: '#", "EFL_CUP: '#"):
            assert token in dash, token
