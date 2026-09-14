"""亚冠精英 + 亚运女足注册(2026-09-14 横幅:「整个联赛的在售场次全部解不出」)。

## 为什么单独一个文件

`test_fixture_anchored_zh_overrides.py` 的 `PINNED` 是给**情况①**(队在系统里、
只是竞彩换了写法)设计的,每条要填 `already_ok`(同场已解出的那一侧)。
本批是**情况②:整队不在词典** ⇒ 补 `team_name_zh.py`,而且亚运女足那场
**两侧都是新的**,`already_ok` 无从填起。形状不同,别硬塞进那张表。

## 三条的锚强度**不一样** —— 这个文件的主要工作就是把差别钉住

① `Pakhtakor` ← 棉农:第①档锚(当前在售那场本身)。开球时刻 / 赛事 /
   **已解出的主队**三者同时对上,且该时刻该赛事主队唯一。
   ⭐ 顺带印证「意译 vs 音译」:Paxtakor 在乌兹别克语里就是「棉农」——
   按音猜(帕赫塔科尔)必错,而按音猜正是最容易顺手做的那件事。

② `China W` / `Hong Kong W`:**队实体锚住了,赛事没锚住**。AF 名册里两个实体带稳定
   id,但 fixture 缓存里**没有亚运女足这个赛事**(`Asian Games` 只有男足 U23)。
   ⇒ 名字是对的,但 join 不到东西。这条限制**必须写成断言**,不能只写在注释里 ——
   哪天 AF 开始发女足亚运,这条会红,提醒人回来重新判。

## ⚠️ 补完不等于能下注

odds_snapshots 的 39 个联赛里**既无亚冠精英也无亚运女足** ⇒ 这两场算不出 EV。
横幅看不见这条链,所以这里替它看着。
(🚨 查这件事时我用 `league LIKE '%ELITE%'` 命中了 NOR_ELITE**SERIEN** —— 又一次
 语法代理测语义属性。本文件的断言按**精确集合**判,不用 LIKE。)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.data.sources.sporttery import _ZH_OVERRIDES, zh_to_canonical
from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH, lookup_zh

REPO = Path(__file__).resolve().parents[2]
_AF_FIXTURES = REPO / "data/external/api_football/_fixtures"

#: 竞彩中文(全称 + 简称)→ 英文规范名。本文件所有断言从这张表自动展开。
REGISTERED: dict[str, str] = {
    "棉农": "Pakhtakor",
    "中国女足": "China W",
    "中国女": "China W",
    "中国香港女足": "Hong Kong W",
    "中国港女": "Hong Kong W",
}
#: 进 `team_name_zh`(情况②,一处同时修 join 和显示)的那三条。
DISPLAY: dict[str, str] = {
    "Pakhtakor": "棉农",
    "China W": "中国女足",
    "Hong Kong W": "中国香港女足",
}


def _af_rows():
    """AF fixture 缓存里的 (kickoff, 赛事名, 主, 客, id)。worktree 没 data/ ⇒ skip。"""
    if not _AF_FIXTURES.is_dir():
        pytest.skip("没有 AF fixture 缓存(worktree)")
    out = []
    for f in _AF_FIXTURES.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        for fx in (d.get("response") if isinstance(d, dict) else d) or []:
            if not isinstance(fx, dict):
                continue
            fi, tm, lg = fx.get("fixture") or {}, fx.get("teams") or {}, fx.get("league") or {}
            out.append((str(fi.get("date") or "")[:19], lg.get("name"),
                        (tm.get("home") or {}).get("name"), (tm.get("away") or {}).get("name"),
                        fi.get("id"), (tm.get("home") or {}).get("id"),
                        (tm.get("away") or {}).get("id")))
    # 🚨 人口非平凡:缓存空了的话下面每条断言都空洞为真
    assert len(out) > 10_000, f"AF 缓存只有 {len(out)} 条,测不出东西"
    return out


@pytest.mark.parametrize("zh", sorted(REGISTERED))
def test_every_registered_name_resolves(zh: str) -> None:
    assert zh_to_canonical(zh) == REGISTERED[zh]


@pytest.mark.parametrize("en", sorted(DISPLAY))
def test_display_side_too(en: str) -> None:
    """情况②补在 `team_name_zh` 的理由就是**一处同时修 join 和显示**。

    只补 `_ZH_OVERRIDES` 会变成「join 通了、卡片仍显示英文名」。
    """
    assert lookup_zh(en) == DISPLAY[en]


@pytest.mark.parametrize("zh", sorted(REGISTERED))
def test_no_collision_in_either_direction(zh: str) -> None:
    en = REGISTERED[zh]
    owners = [k for k, v in TEAM_NAME_ZH.items() if v == zh]
    assert owners in ([], [en]), f"中文名 {zh} 被别的队占了:{owners}"
    # 男足那三条必须原样不动(`China`/`China PR`→中国、`Hong Kong`→香港)
    assert TEAM_NAME_ZH.get("China") == "中国"
    assert TEAM_NAME_ZH.get("China PR") == "中国"
    assert TEAM_NAME_ZH.get("Hong Kong") == "香港"


def test_the_two_abbreviations_went_to_the_override_table() -> None:
    """简称属于「竞彩换了种写法」⇒ `_ZH_OVERRIDES`;全称属于情况② ⇒ `team_name_zh`。

    放错地方不会立刻坏,但会让下一个人读不出这批是怎么判的类。
    """
    assert _ZH_OVERRIDES.get("中国女") == "China W"
    assert _ZH_OVERRIDES.get("中国港女") == "Hong Kong W"
    assert "中国女足" not in _ZH_OVERRIDES, "全称该走 team_name_zh(它还要负责显示)"


class TestTheAnchorsAreRealNotStories:
    """⭐ 注释里的锚必须能被数据证实 —— 否则它只是一段我写的说辞。"""

    def test_pakhtakor_is_pinned_by_the_on_sale_fixture_itself(self) -> None:
        rows = _af_rows()
        ko, comp = "2026-09-14T18:15:00", "AFC Champions League Elite"
        same_slot = [r for r in rows if r[0] == ko and r[1] == comp]
        assert same_slot, f"缓存里没有 {comp} {ko} 的场次 —— 锚不成立"
        # 竞彩那场主队 = 吉达国民,词典里本来就解得出
        assert zh_to_canonical("吉达国民") == "Al-Ahli Jeddah"
        mine = [r for r in same_slot if r[2] == "Al-Ahli Jeddah"]
        assert len(mine) == 1, (
            f"该时刻该赛事以 Al-Ahli Jeddah 为主的场次有 {len(mine)} 场 —— "
            "锚要求**唯一**,不唯一就不能据此断定对手")
        # ⭐ 断言要和**被测对象**挂钩:不是「缓存里写着 Pakhtakor」(那是缓存的事实),
        #    而是「我们把棉农映射成了 fixture 说的那个名字」。
        #    实测:原来写死成 `== "Pakhtakor"` 时,把词典改成别的球队**这条照样绿** ——
        #    它验的是 AF,不是我们。(判据:改了被测对象,这条断言会不会变。)
        assert zh_to_canonical("棉农") == mine[0][3], (
            f"词典把棉农映射成 {zh_to_canonical('棉农')!r},而同场唯一的对手是 {mine[0][3]!r}")

    def test_the_two_women_entities_exist_with_stable_ids(self) -> None:
        rows = _af_rows()
        ids = {}
        for _, _, h, a, _, hid, aid in rows:
            for nm, tid in ((h, hid), (a, aid)):
                if nm in ("China W", "Hong Kong W"):
                    ids.setdefault(nm, set()).add(tid)
        # 同上:断言挂在**我们的映射**上,不是挂在缓存的字面值上。
        for zh, want_id in (("中国女足", 1723), ("中国香港女足", 17896)):
            en = zh_to_canonical(zh)
            assert ids.get(en) == {want_id}, (
                f"{zh} → {en!r},但该名字在 AF 缓存里的 id 是 {ids.get(en)}(应为 {{{want_id}}})"
                " —— 要么映射错了,要么 AF 改了实体")

    def test_af_distinguishes_age_grades_so_the_senior_name_is_unambiguous(self) -> None:
        """`China PR U20 W` 单独存在 ⇒ 不带后缀的 `China W` 就是成年队,没有歧义。

        没有这条,「China W 是成年国家队」只是我的断言。
        """
        names = {r[2] for r in _af_rows()} | {r[3] for r in _af_rows()}
        assert "China PR U20 W" in names, "AF 不区分年龄组的话,China W 的语义就不确定了"


class TestTheHonestLimits:
    """🚨 把「补完能买到什么」写成断言 —— 免得下一个人以为横幅闭嘴=能下注了。"""

    def test_the_womens_asian_games_is_not_in_the_fixture_cache(self) -> None:
        """所以 `China W` 这条**join 不到东西**,只保证名字对。

        这条红了 = AF 开始发女足亚运了 ⇒ 回来重新判该用哪个实体。
        """
        rows = _af_rows()
        ag = {(r[2], r[3]) for r in rows if r[1] == "Asian Games"}
        assert ag, "人口非平凡:缓存里连男足亚运都没有,这条测不出东西"
        assert all(h.endswith(" U23") and a.endswith(" U23") for h, a in ag), (
            f"Asian Games 里出现了非 U23 的条目 —— 可能是女足进来了:{ag}")

    def test_neither_competition_has_any_odds_coverage(self) -> None:
        """⇒ 这两场算不出 EV。⚠️ 用**精确集合**判,不用 LIKE:

        我查这件事时用 `league LIKE '%ELITE%'` 命中了 NOR_ELITE**SERIEN** 4024 行,
        差点报成「亚冠精英有覆盖」。
        """
        db = REPO / "data/v4_observation.db"
        if not db.exists():
            pytest.skip("没有观测库")
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            lgs = {r[0] for r in c.execute("select distinct league from odds_snapshots") if r[0]}
        assert len(lgs) > 20, f"人口非平凡:只有 {len(lgs)} 个联赛"
        for bad in ("AFC_CHAMPIONS_LEAGUE_ELITE", "AFC_CL_ELITE", "ASIAN_GAMES", "ASIAD"):
            assert bad not in lgs
        assert not any(x.endswith("_W") or x.startswith("W_") for x in lgs), \
            f"出现了女足联赛 —— 覆盖变了,回来重判:{lgs}"
