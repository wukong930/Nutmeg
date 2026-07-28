"""P3 计数人口谓词(prereg v1.8 §2.1)—— 只用国内俱乐部联赛。

⭐ 核心那条:**中文标签绝不能裸用 `competition_type_of`**。它只认 EN code,
中文进去会对**所有东西**返回 "league" ⇒ 世界杯/欧冠被静默算成国内联赛。
2026-07 捕到的 15 场 −2 里 10 场是世界杯 —— 这个 bug 会让 P3 的人口整个失真,
而且**不会报错、数字看起来完全正常**。下面第一个测试就是钉死它的。
"""
from __future__ import annotations

import pytest

from nutmeg.v4.data.competitions import competition_type_of
from nutmeg.v4.data.league_labels import classify_league, is_domestic_club_league


@pytest.mark.parametrize("cn", ["世界杯", "欧冠", "欧罗巴"])
def test_chinese_cup_labels_are_not_counted(cn):
    """⭐ 中文大赛标签必须 excluded —— 裸用 competition_type_of 会漏掉它们。"""
    assert classify_league(cn) == "excluded"
    assert not is_domestic_club_league(cn)
    # 反证:注册表对中文确实返回 "league" —— 所以谓词不能只靠它
    assert competition_type_of(cn) == "league", (
        "若这条挂了,说明注册表已支持中文 —— 那 classify_league 的双轨可以简化")


@pytest.mark.parametrize("label", ["WC", "UCL", "UEL"])
def test_en_cup_codes_are_not_counted(label):
    assert classify_league(label) == "excluded"


@pytest.mark.parametrize("label", ["瑞超", "挪超", "英超", "SWE_ALLSVENSKAN",
                                   "NOR_ELITESERIEN", "EPL", "DNK_SUPERLIGA"])
def test_domestic_leagues_counted_in_both_vocabularies(label):
    """双轨:cron 写中文、面板写 EN,同一个联赛两边都必须计入。"""
    assert classify_league(label) == "domestic"


def test_unknown_is_its_own_state_not_silently_domestic():
    """⭐ 三态的意义:「没见过」必须可见,不能混进 domestic 也不该等同 excluded。

    丹超是活例 —— 国内联赛、竞彩上架,但中文缩写未收录 ⇒ cron 写的中文行会掉出
    计数。悄悄少算 N 和悄悄混入错人口一样坏,所以它得有自己的类别被报出来。
    """
    assert classify_league("丹超") == "unknown"
    assert not is_domestic_club_league("丹超")
    assert classify_league("某个没见过的联赛") == "unknown"


@pytest.mark.parametrize("label", [None, "", "   "])
def test_empty_label_is_unknown_not_domestic(label):
    """空标签 fail-closed —— 绝不能因为「没写联赛」就默认计入。"""
    assert classify_league(label) == "unknown"
    assert not is_domestic_club_league(label)


def test_predicate_is_fail_closed_by_construction():
    """is_domestic_club_league 只对 'domestic' 为真 —— unknown/excluded 都不计入。"""
    for lab in ("丹超", "世界杯", "", None, "XYZ_NOT_A_LEAGUE_中文混"):
        assert is_domestic_club_league(lab) == (classify_league(lab) == "domestic")
