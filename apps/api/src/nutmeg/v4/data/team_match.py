"""跨源队名匹配 —— **一处定义**(2026-09-01 从 `polymarket_match` 抽出)。

## 为什么抽出来

这套判据是给 Polymarket 建的,但它解决的问题**跟 Polymarket 无关**:
不同数据源对同一支球队用不同长度的名字。

    Odds API / Polymarket  用**全称**   `Lincoln City` · `Preston North End`
    API-Football           用**短名**   `Lincoln`      · `Preston`
    而两者的编辑距离恰好落在模糊闸 0.86 **之下**(0.69–0.80)

2026-09-01 一天之内在**两个**消费方各踩一次:
  · `polymarket_match` —— 今天 8 场英冠 8/8 全丢(修后匹配率 76→145);
  · `_attach_book_consensus` —— 多书商共识 12 场英冠只对上 1 场。
⇒ 复制第三份 = 平行入口,只会分裂口径(本仓当天已因此吃过三次亏)。

## 四级判据(⛔ 顺序不能变,越靠后越宽)

    ① core 精确        `_core` 剥掉 FC/CF/SC… 后逐字相等
    ② 模糊 ≥ 0.86      difflib
    ③ **前缀包含**      短的必须是长的**前缀**,且多出的 token 不是预备队标记
    ④ **别名表**        复用 `odds_source_aliases`(202 条,联赛无关且零歧义)

## 🚨 为什么**不能**靠放宽模糊阈值解决

    `derby county`  的最近邻是 `newport county`    **0.69**
    `swansea city`  的最近邻是 `swansea city u21`  **0.86**
    `wolverhampton wanderers` 的最近邻是**乌拉圭杯的** `wanderers` **0.56**

任何放宽都会同时打开这三种错配。**错映射是静默污染,比缺映射更坏。**
"""
from __future__ import annotations

import difflib
from functools import lru_cache

from nutmeg.utils.team_canonical import normalize_name

# Club-type tokens stripped to a "core" name before matching, so Polymarket's
# "Iwaki FC" / "FC Imabari" match API-Football's "Iwaki" / "Imabari" (the bare
# "FC" suffix otherwise drops the fuzzy ratio below 0.86 and the game is lost).
# Conservative set — only unambiguous club abbreviations; the both-teams-must-
# map-to-distinct-sides guard prevents over-merging.
_CLUB_TOKENS = frozenset({
    "fc", "cf", "sc", "ac", "afc", "fk", "sk", "cd", "ca", "bk", "sv",
    "vfb", "vfl", "nk", "hnk", "ks", "gks", "ud", "sd", "cp", "ec", "rc", "rcd",
})


#: 出现在「多出来的 token」里就**拒绝**前缀包含 —— 预备队/青年队/女队。
#: 🚨 没有它,`swansea city` 会前缀命中 AF 的 `swansea city u21`(一队配自家 U21)。
#: 注意与 `_EXCLUDE_MARKERS` 的分工:那个查 **Poly 事件**的 series/title,
#: 这个查 **AF fixture** 队名多出来的词 —— 两侧都要挡,只挡一侧照样错配。
_RESERVE_TOKENS = frozenset({
    "u15", "u16", "u17", "u18", "u19", "u20", "u21", "u23",
    "b", "ii", "iii", "2", "reserves", "reserve", "youth", "junior",
    "w", "women", "womens", "ladies", "academy", "dev", "development",
})


_MATCH_FUZZY = 0.86


#: 前缀包含命中的置信度。低于 exact(1.0)、高于模糊闸,便于事后按 `match_confidence` 分层审计。
_CONTAIN_CONF = 0.95


#: 别名命中的置信度(第四级,最低)。分层是为了能**按方法审计**:
#: `SELECT match_method, COUNT(*) FROM polymarket_gaps GROUP BY 1`。
_ALIAS_CONF = 0.90


def _prefix_extra(a: str, b: str) -> list[str] | None:
    """短的那个是长的**前缀**时返回长的多出来的 token,否则 None。

    ⭐ 为什么是**前缀**而不是「子集」或「包含」:
      · `west ham` 是 `west ham united` 的前缀 ✅(要的)
      · `wanderers` 是 `bolton wanderers` 的**后缀**不是前缀 ⇒ 拒 ✅
        —— 否则它会同时命中 `bolton wanderers` 和 `wolverhampton wanderers`,
        两支不同的队共用一个 AF 短名 `wanderers`。
      · `derby county` vs `newport county` 互不为前缀 ⇒ 拒 ✅
        —— 这两个的编辑距离是 **0.69**,任何「把模糊闸放宽到 0.65」的修法都会把
        Derby 配到 Newport 上。**错映射比缺映射更坏**,所以不动阈值。
    """
    ta, tb = a.split(), b.split()
    if not ta or not tb or len(ta) == len(tb):
        return None
    short, long_ = (ta, tb) if len(ta) < len(tb) else (tb, ta)
    if long_[:len(short)] != short:
        return None
    return long_[len(short):]


def _core(name: str) -> str:
    """Normalized name with club-type tokens stripped (FC/CF/SC…), e.g.
    'Iwaki FC' → 'iwaki', 'FC Imabari' → 'imabari'. Falls back to the full
    normalized name when stripping would leave nothing."""
    norm = normalize_name(name)
    toks = [t for t in norm.split() if t not in _CLUB_TOKENS]
    return " ".join(toks) if toks else norm


@lru_cache(maxsize=1)
def _alias_any() -> dict[str, str]:
    """`odds_source_aliases` 的**联赛无关**反查:`core(源名) → core(AF 名)`。

    ⭐ 为什么复用那张表而不是新建一本:它已经有 218 条,且**是从赛事共现推导的**
    (`scripts/derive_odds_name_aliases.py`,自带对照组:两侧本来同名的 93 支队
    应当映射到自己,实测全对)。今天这批英冠它全都覆盖:
    `West Ham United→West Ham` · `Derby County→Derby` · `Preston North End→Preston`
    · `Sheffield United→Sheffield Utd` · `Wolverhampton Wanderers→Wolves`。
    ⛔ 再造一本 Poly 专用字典 = 平行入口,只会分裂口径(本仓反复踩)。

    ⚠️ **但那张表是 Odds-API↔AF 推出来的,Polymarket 是第三个源** —— 拿来用是外推。
    三道约束把外推的风险摁住:
      ① 只在**所有联赛键都指向同一目标**时才收(键是 `(联赛码, 名字)`;
         同一个名字在不同联赛指向不同 AF 名 ⇒ 有歧义 ⇒ **整条丢弃**);
      ② 它是**第四级**判据,exact / fuzzy / 前缀 都没中才用;
      ③ 下游 `match_to_fixture` 的唯一性闸仍然生效,配错会被「多个候选」拒掉。
    命中记 `match_method="alias"`,可事后按方法分层审计。
    """
    from nutmeg.v4.data.odds_source_aliases import ODDS_SOURCE_ALIASES
    by_name: dict[str, set[str]] = {}
    for (_lg, src), dst in ODDS_SOURCE_ALIASES.items():
        by_name.setdefault(_core(src), set()).add(_core(dst))
    return {k: next(iter(v)) for k, v in by_name.items() if len(v) == 1}


def _resolve(name: str, cores: dict[str, tuple[str, str]]) -> tuple[str, str, float] | None:
    """Resolve a team name against {core → (side, original)} → (side, original,
    confidence) or None. Core-exact first, then fuzzy ≥ _MATCH_FUZZY (conservative
    — still rejects Real Madrid ↔ Real Sociedad ≈ 0.79)."""
    c = _core(name)
    if c in cores:
        side, orig = cores[c]
        return side, orig, 1.0
    m = difflib.get_close_matches(c, list(cores), n=1, cutoff=_MATCH_FUZZY)
    if m:
        side, orig = cores[m[0]]
        return side, orig, difflib.SequenceMatcher(None, c, m[0]).ratio()
    # 第三级:前缀包含(2026-09-01)。Poly 用**全称**、AF 用**短名**,而两者的编辑
    # 距离恰好落在 0.86 闸之下 —— 实测今天 8 场英冠 **8/8 全丢**:
    #     Derby County FC     → `derby county`     vs AF `derby`      0.69 ❌
    #     West Ham United FC  → `west ham united`  vs AF `west ham`   0.70 ❌
    #     Norwich City FC     → `norwich city`     vs AF `norwich`    0.74 ❌
    #     Birmingham City FC  → `birmingham city`  vs AF `birmingham` 0.80 ❌
    # ⛔ 修法**不是**放宽阈值:`derby county` 的最近邻是 `newport county`(0.69),
    #    `swansea city` 的最近邻是 `swansea city u21`(0.86)—— 放宽会同时打开错配。
    # ⇒ 用**前缀 + 预备队闸 + 唯一性**三重约束,见 `_prefix_extra`。
    hits = []
    for k in cores:
        extra = _prefix_extra(c, k)
        if extra is None or any(t in _RESERVE_TOKENS for t in extra):
            continue
        hits.append(k)
    if len(hits) == 1:          # 歧义一律拒 —— 宁可缺,不可错
        side, orig = cores[hits[0]]
        return side, orig, _CONTAIN_CONF
    # 第四级:复用 `odds_source_aliases`(见 `_alias_any`)。修的是**绰号**这一类
    # —— `Wolves` 不是 `Wolverhampton Wanderers` 的截断,前缀规则结构上修不了。
    # ⚠️ 那条名字的最近邻是**乌拉圭杯的 `Wanderers`**(0.56),再次说明为什么
    #    不能靠放宽模糊闸解决。
    aliased = _alias_any().get(c)
    if aliased and aliased in cores:
        side, orig = cores[aliased]
        return side, orig, _ALIAS_CONF
    return None

def same_team(a: str, b: str) -> str | None:
    """两个源的队名指的是同一支球队吗?→ 命中的判据名,否则 None。

    这是给**只需要判同异**的消费方的简化入口(如多书商共识的 join);
    需要「解析到 fixture 的哪一侧」的用 `_resolve`。

    ⚠️ 返回判据名而不是 bool —— 消费方可以据此分层审计
    (`exact` 最硬,`alias` 最宽)。
    """
    ca, cb = _core(a), _core(b)
    if ca == cb:
        return "exact"
    if difflib.SequenceMatcher(None, ca, cb).ratio() >= _MATCH_FUZZY:
        return "fuzzy"
    extra = _prefix_extra(ca, cb)
    if extra is not None and not any(t in _RESERVE_TOKENS for t in extra):
        return "prefix"
    al = _alias_any()
    if al.get(ca) == cb or al.get(cb) == ca:
        return "alias"
    return None


__all__ = ["same_team"]
