"""服务侧队名解析:关掉 fuzzy,补上法定记号剥离(owner 2026-08-05)。

## 事故

`persist.build_features_for_fixtures` 里查 Elo/form 的那两行是**裸 `dict.get`**:

    sh = teams.get(row.home_team)

而 `team_state` 的键来自 football-data.co.uk("Bochum" / "Hertha" / "Sp Lisbon"),
服务侧喂进来的是 API-Football 的完整注册名("VfL Bochum" / "Hertha BSC" /
"Sporting CP")。实测 203 个队名对 14 个训练联赛的 team_state:**81 个对不上
(39.9%)**,全部静默吃 `elo_initial`=1500 + form 全 NaN。

08-05 当天 8 条腿里 3 条中招,单腿 P 偏 5~9pp(Club Brugge 真实 Elo 1870.7 是
比甲最高,却按 1500 算)。`docs/health_check_2026-07-15.md:213` 早就记过这个
不对称,07-15 只落了计数器,没落解析。

## 为什么服务侧**必须**关掉 fuzzy(这是本文件的核心)

`to_v4_canonical` 第 4 级是 difflib 模糊匹配。量下来:

* fuzzy@0.86 在 81 条缺失里只捞回 **2** 条(2.5%),风险全担、收益几乎没有;
* 降阈值到能捞回东西的高度,毒配对同时进来 —— ``VfL Bochum → Bochum``(对)
  和 ``Kashima → Tokushima``(错)**相似度都是 0.750**,不存在能分开两者的阈值;
* 更糟的是降阈值之后它**优先挑错的**:``Kashima Antlers`` 就在池子里,但
  ratio 只有 0.636,排在 ``Tokushima``(0.750)后面 —— 正确答案在场却选错。

两头都不成立:高阈值几乎修不动东西,低阈值在正确答案在场时选错。

⇒ 换成 `_affix_core`:只删封闭表里的法定形式记号("VfL"/"1. FC"/"BSC"/成立年份),
删完要求**精确相等且池内唯一**。它构造不出跨球队的折叠 —— 没有任何前缀能把
"Kashima" 变成 "Tokushima"。实测捞回 19 条,逐条复核全对。

## 剩下的靠**可复核的**别名,不是靠记忆

词元包含("Standard Liege"→"Standard")能再捞一批,但它**不安全**:同一条规则
会产出 ``Rouen → Quevilly Rouen``,而这是两家不同的俱乐部。判掉它靠的不是
「我知道它们不一样」,是一条纯数据的闸:**目标必须出现在该联赛 football-data
最新赛季的名单里**。Quevilly Rouen 最后一次出现在 2324,ADO Den Haag 已降级,
Waasland-Beveren 停在 2021 —— 三条全被拦下。

同族见 [[cross-source-team-name-mismatch]] 与 [[health-check-guardrails]]。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nutmeg.utils.team_canonical import (
    TEAM_ALIASES,
    _affix_core,
    resolve_serving_name,
    to_v4_canonical,
)

REPO = Path(__file__).resolve().parents[2]
TEAM_STATE = REPO / "data/v4_model_cat/team_state.json"


class TestFuzzyIsOffAtServing:
    """⭐ 承重条:模糊那一级在服务侧必须够不着。"""

    def test_no_threshold_separates_the_good_pair_from_the_poisoned_one(self):
        """⭐ 承重条:**不存在**能同时收下对的、挡住错的那个阈值。

        实测 difflib ratio(归一化后):

            vfl bochum → bochum            0.750   ✅ 对
            kashima    → tokushima         0.750   🚨 两家不同俱乐部

        一模一样。所以「把阈值调到某个刚好的位置」这条路是不存在的 ——
        不是调参问题,是这个相似度量本身分不开。
        """
        import difflib
        good = difflib.SequenceMatcher(None, "vfl bochum", "bochum").ratio()
        poison = difflib.SequenceMatcher(None, "kashima", "tokushima").ratio()
        assert good == poison == 0.75

    def test_lowering_the_threshold_picks_poison_over_the_correct_answer(self):
        """⭐ 而且降阈值之后,fuzzy 会**优先**挑那个错的。

        ``Kashima Antlers`` 就在池子里,但长度差太多 ⇒ ratio 只有 0.636,
        排在 ``Tokushima``(0.750)后面。⇒ 降阈值不只是「放进来一些噪声」,
        是在**正确答案在场时选错**。

        ⚠️ 生产阈值 0.86 上 ``Kashima`` 两个都够不着(0.750/0.636 都 <0.86),
        所以老路径是「解不出」而非「解错」—— 但那个阈值同时也捞不回
        ``VfL Bochum``,即 81 条缺失里只修得动 2 条。两头都不成立才是结论。
        """
        pool = ["Kashima Antlers", "Tokushima", "Kashiwa Reysol"]
        # ⚠️ 用一个**没有别名**的联赛键 —— JPN_J1 已经有 kashima 别名,会在
        # 第 3 级就命中,fuzzy 根本轮不上(这正是修复后的生产行为)。
        assert to_v4_canonical("Kashima", "NO_ALIASES", pool, fuzzy_threshold=0.7).canonical \
            == "Tokushima"
        assert to_v4_canonical("Kashima", "NO_ALIASES", pool).canonical is None  # @0.86 解不出
        # 而生产走的是别名,和阈值无关,拿到对的
        assert resolve_serving_name("Kashima", "JPN_J1", pool).canonical == "Kashima Antlers"

    def test_serving_refuses_what_a_lowered_threshold_would_accept(self):
        """把正确答案拿走、只留毒项 —— 服务侧必须解不出。"""
        pool = ["Tokushima", "Kashiwa Reysol", "Verdy"]
        assert resolve_serving_name("Kashima", "NO_ALIASES", pool).canonical is None
        assert to_v4_canonical("Kashima", "NO_ALIASES", pool, fuzzy_threshold=0.7).canonical \
            == "Tokushima"

    def test_never_returns_fuzzy_as_a_method(self):
        """行为断言:扫真实 team_state,没有任何一条走 fuzzy 出来。"""
        if not TEAM_STATE.exists():
            pytest.skip("生产 artifact 不在(CI)")
        ts = json.loads(TEAM_STATE.read_text())
        methods = set()
        for lg, teams in ts.items():
            pool = list(teams)
            for name in list(pool)[:40]:
                methods.add(resolve_serving_name(name, lg, pool).method)
        assert "fuzzy" not in methods, methods

    def test_none_threshold_disables_step_four(self):
        """`fuzzy_threshold=None` 是**有名字的关闭态**,不是「调到恰好不可达」。"""
        pool = ["Tokushima"]
        assert to_v4_canonical("Kashima", "X", pool, fuzzy_threshold=0.5).canonical == "Tokushima"
        assert to_v4_canonical("Kashima", "X", pool, fuzzy_threshold=None).canonical is None


class TestAffixRule:
    def test_the_three_legs_that_were_actually_broken(self):
        """08-05 当天真的在吃 1500 的那三条腿。"""
        bel = ["Club Brugge", "Cercle Brugge", "Kortrijk", "Standard"]
        ger = ["Bochum", "Hertha", "Schalke 04", "Hannover"]
        assert resolve_serving_name("Club Brugge KV", "BEL_PRO_LEAGUE", bel).canonical \
            == "Club Brugge"
        assert resolve_serving_name("VfL Bochum", "GER_2_BUNDESLIGA", ger).canonical == "Bochum"
        assert resolve_serving_name("Hertha BSC", "GER_2_BUNDESLIGA", ger).canonical == "Hertha"

    def test_founding_year_is_stripped_symmetrically(self):
        """"FC Schalke 04" 与 "Schalke 04" 要归到同一个 core;
        而 "Hannover 96" → "Hannover"(池内没带年份)也要成立。"""
        pool = ["Schalke 04", "Hannover"]
        assert resolve_serving_name("FC Schalke 04", "GER", pool).canonical == "Schalke 04"
        assert resolve_serving_name("Hannover 96", "GER", pool).canonical == "Hannover"

    def test_ambiguous_core_is_refused_not_guessed(self):
        """剥完撞上两支队 ⇒ 宁可不解,不许挑一个。"""
        pool = ["Brugge", "SV Brugge"]          # 两者 core 都是 ("brugge",)
        assert resolve_serving_name("FC Brugge", "X", pool).canonical is None

    def test_reserve_markers_are_not_stripped(self):
        """⭐ ``b`` / ``ii`` **故意**不在剥离表里 —— 剥掉会把预备队并进一队。

        这是「表越小越安全」的具体一条:多收一个词元就多一次折叠机会。
        """
        assert _affix_core("Sociedad B") != _affix_core("Sociedad")
        pool = ["Sociedad"]
        assert resolve_serving_name("Real Sociedad II", "ESP_SEGUNDA_DIVISION", pool).canonical \
            is None

    def test_no_prefix_can_turn_one_club_into_another(self):
        """规则的安全性来自「只删封闭表里的词」,不是来自阈值。"""
        for raw, other in [("Kashima", "Tokushima"), ("Rouen", "Rodez"), ("Nantes", "Angers")]:
            assert _affix_core(raw) != _affix_core(other)

    def test_pool_has_no_self_collision(self):
        """🔒 真 team_state 里,剥离规则不能把任何两支队折叠成同一个 core。

        这条红了 = 剥离表收得太宽,某个联赛里两支队开始互相冒充。
        """
        if not TEAM_STATE.exists():
            pytest.skip("生产 artifact 不在(CI)")
        ts = json.loads(TEAM_STATE.read_text())
        collisions = []
        for lg, teams in ts.items():
            seen: dict[tuple, str] = {}
            for t in teams:
                core = _affix_core(t)
                if core in seen:
                    collisions.append((lg, seen[core], t))
                seen[core] = t
        assert not collisions, collisions


class TestAliasTableIntegrity:
    def test_every_alias_target_exists_in_that_league_pool(self):
        """⭐ 别名指向池外 = 死别名,比没写更坏 —— 表里有一行,看起来像处理过了。

        修这条时真抓到 3 个:``nec nijmegen → "NEC Nijmegen"``(实际是 "Nijmegen")、
        ``sporting cp → "Sporting"``(实际是 "Sp Lisbon",葡超豪门一直吃 1500)。
        """
        if not TEAM_STATE.exists():
            pytest.skip("生产 artifact 不在(CI)")
        ts = json.loads(TEAM_STATE.read_text())
        dead = [
            (lg, k, v)
            for lg, m in TEAM_ALIASES.items() if lg in ts
            for k, v in m.items() if v not in ts[lg]
        ]
        assert not dead, f"别名目标不在对应联赛 team_state 内:{dead}"

    def test_alias_keys_are_normalized(self):
        """键必须是 `normalize_name` 之后的形式,否则永远查不中。"""
        from nutmeg.utils.team_canonical import normalize_name
        bad = [(lg, k) for lg, m in TEAM_ALIASES.items() for k in m if normalize_name(k) != k]
        assert not bad, bad

    def test_the_gated_pairs_stayed_out(self):
        """⭐ 三条被「最新赛季名单」闸拦下的毒配对,不许偷偷回到表里。

        它们长得非常像真别名 —— 词元包含成立、池内唯一也成立 —— 只有
        「目标已经不在该联赛现役名单」这条数据判据能识别。
        """
        forbidden = {
            ("FRA_LIGUE_2", "rouen"),               # FC Rouen ≠ Quevilly Rouen
            ("BEL_PRO_LEAGUE", "sk beveren"),       # Waasland-Beveren 2021 后消失
            ("NED_EREDIVISIE", "ado den haag"),     # Den Haag 已降级
        }
        present = {(lg, k) for lg, k in forbidden if k in TEAM_ALIASES.get(lg, {})}
        assert not present, f"被闸拦下的配对回到别名表了:{present}"


class TestServingPathUsesIt:
    """光有 resolver 不算修好 —— 要证明 `persist` 那条路真的走它。"""

    def test_features_resolve_api_football_names(self):
        if not TEAM_STATE.exists():
            pytest.skip("生产 artifact 不在(CI)")
        from nutmeg.v4.model.persist import build_features_for_fixtures, load_artifact
        art = load_artifact(str(REPO / "data/v4_model_cat"))
        df = pd.DataFrame([
            dict(league="GER_2_BUNDESLIGA", date=pd.Timestamp("2026-08-07"),
                 home_team="VfL Bochum", away_team="Hertha BSC",
                 psc_home=2.2, psc_draw=3.4, psc_away=3.2),
            dict(league="BEL_PRO_LEAGUE", date=pd.Timestamp("2026-08-08"),
                 home_team="Club Brugge KV", away_team="Kortrijk",
                 psc_home=1.3, psc_draw=5.5, psc_away=9.0),
        ])
        out = build_features_for_fixtures(art, df)
        assert (out["elo_home"] != art.elo_initial).all(), "主队仍在吃 1500 占位"
        assert (out["elo_away"] != art.elo_initial).all(), "客队仍在吃 1500 占位"
        # Club Brugge 是比甲最强队,Elo 必须明显高于对手 —— 若名字解析回退,
        # 两边都会是 1500,这条差值断言同时也守住了「没有静默退化成占位」。
        assert out.loc[1, "elo_home"] - out.loc[1, "elo_away"] > 200

    def test_genuinely_unknown_team_still_gets_defaults(self):
        """兜底**不许**把「真没训练过」变成「有」—— 升班马就该吃默认值。"""
        if not TEAM_STATE.exists():
            pytest.skip("生产 artifact 不在(CI)")
        from nutmeg.v4.model.persist import build_features_for_fixtures, load_artifact
        art = load_artifact(str(REPO / "data/v4_model_cat"))
        df = pd.DataFrame([
            dict(league="GER_2_BUNDESLIGA", date=pd.Timestamp("2026-08-07"),
                 home_team="Zzz Nonexistent FC", away_team="Bochum",
                 psc_home=2.2, psc_draw=3.4, psc_away=3.2),
        ])
        out = build_features_for_fixtures(art, df)
        assert out.loc[0, "elo_home"] == art.elo_initial
        assert out.loc[0, "elo_away"] != art.elo_initial
