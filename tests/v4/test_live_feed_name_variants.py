"""实时竞彩源的队名写法 —— 与历史档案**不是同一套**(2026-08-11)。

## 起因

2026-08-09 我用比分锚定从 `jingcai_odds_history`(走势档案)补了 59 条队名。
两天后「竞彩队名解不出」横幅仍点名 4 场,而其中三支队**看起来**已经补过了:

| 实时源写法 | 走势档案写法 | 同一支队 |
|---|---|---|
| 里瓦达维亚独立 | 里独立 | Independ. Rivadavia |
| 波特诺山丘 | 波特诺 | Cerro Porteno |
| 巴黎圣日尔曼 | 巴黎圣曼 | Paris Saint Germain |

⭐ **实时竞彩源用的写法比历史档案更长。** 从档案锚出来的映射对实时链**不生效** ——
两边都得在表里。只补一边,横幅会在另一条链上继续点名,而人会以为「已经修过了」。

⚠️ 还有一条差一个字的:`巴黎圣日尔曼` vs 词典原有的 `巴黎圣日**耳**曼`(尔/耳,
同音异形)。这种最容易被眼睛跳过而误判成「已经有了」。

## 锚(全部同场唯一,零翻译)

· 三条靠**同场另一侧已解** + 该日该联赛**唯一**匹配的 AF 赛程
· `采列`/`亚拉腊` 两侧都不解 ⇒ 靠**开球时刻**:那天竞彩上架 8 场欧冠、7 场已解,
  AF 有 10 场 ⇒ 缩到 3 个候选(17:00/18:00/18:15Z),竞彩记的是 **18:15Z** ⇒ 唯一
· 前三条与 2026-08-09 从历史档案锚出的结果**完全一致** —— 两条独立路径互证

## ⚠️ 补完之后还差两步(横幅看不见它们)

① **重启 API** —— 词典在进程启动时建表
② **ingest 重跑** —— 解不出的场次当初**根本没写进 `jingcai_sp`**(实测 0 行),
   补词典不会追溯地把它们补进去。⇒ 「横幅绿了」≠「竞彩 SP 挂上了」。
"""
from __future__ import annotations

import pytest

from nutmeg.v4.data.sources.sporttery import zh_to_canonical

#: (实时源中文, 期望英文) —— 锚见文件头,不是按音译写的
_LIVE_VARIANTS = [
    ("里瓦达维亚独立", "Independ. Rivadavia"),
    ("波特诺山丘", "Cerro Porteno"),
    ("巴黎圣日尔曼", "Paris Saint Germain"),
    ("亚拉腊", "Ararat-Armenia"),
    ("采列", "Celje"),
]

#: 同一支队在**走势档案**里的写法 —— 两套都必须继续解得出
_ARCHIVE_VARIANTS = [
    ("里独立", "Independ. Rivadavia"),
    ("波特诺", "Cerro Porteno"),
    ("巴黎圣曼", "Paris Saint Germain"),
]


@pytest.mark.parametrize(("zh", "want"), _LIVE_VARIANTS)
def test_live_feed_spelling_resolves(zh: str, want: str) -> None:
    """实时竞彩源的写法必须解得出 —— 否则横幅点名、竞彩 SP 挂不上。"""
    assert zh_to_canonical(zh) == want


@pytest.mark.parametrize(("zh", "want"), _ARCHIVE_VARIANTS)
def test_archive_spelling_still_resolves(zh: str, want: str) -> None:
    """🚨 承重:补实时写法**不许**把档案写法挤掉。

    两条链读的是同一张表,而 `_ZH_TO_EN` 用 `setdefault` 建 —— 一个中文名只能有
    一个英文值,但**两个中文名可以指向同一支队**。这条测试钉住「两套并存」。
    空包弹:把档案那条从 `TEAM_NAME_ZH` 删掉 ⇒ 立刻红。
    """
    assert zh_to_canonical(zh) == want


def test_the_two_spellings_agree() -> None:
    """长短两种写法必须指向**同一支队** —— 分家就说明其中一条锚错了。"""
    pairs = [("里瓦达维亚独立", "里独立"), ("波特诺山丘", "波特诺"),
             ("巴黎圣日尔曼", "巴黎圣曼")]
    for long_, short in pairs:
        assert zh_to_canonical(long_) == zh_to_canonical(short) is not None, \
            f"{long_} 与 {short} 解出的不是同一支队"


def test_the_homophone_variant_is_distinct_from_the_dict_spelling() -> None:
    """⚠️ `巴黎圣日尔曼`(竞彩)与 `巴黎圣日耳曼`(词典)差一个字,两个都得解得出。

    这条存在是因为它**看起来已经有了** —— 只差「尔/耳」,肉眼扫过去会以为重复。
    """
    assert zh_to_canonical("巴黎圣日尔曼") == "Paris Saint Germain"
    assert zh_to_canonical("巴黎圣日耳曼") == "Paris Saint Germain"
    assert "巴黎圣日尔曼" != "巴黎圣日耳曼"          # 真的是两个不同字符串
