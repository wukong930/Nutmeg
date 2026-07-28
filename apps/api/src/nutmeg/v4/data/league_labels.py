"""Canonical league labels for cross-writer grouping (体检 2026-07-02).

``jingcai_sp`` has TWO writers with different league vocabularies: the
sporttery capture stores 竞彩 Chinese abbreviations (英超/芬超/世界杯…) while
the dashboard 记一笔 path (source=market_mode) stores V4 EN league codes
(EPL/FIN_VEIKKAUSLIIGA/WC…). Grouping by the RAW string therefore splits one
league into two groups — it dilutes per-league N and adds a spurious member
to the CLV-gate BHY-FDR family (measured 2026-07-02: 芬超 40 rows +
FIN_VEIKKAUSLIIGA 8 rows were ONE league in two gate groups).

Fix at the shared READER (the same altitude rule as ``national_match_key``:
repair the join/grouping layer once, not each producer). Canonical form = the
竞彩 Chinese abbreviation — dominant in captured rows and what the ledger
prints. Unknown labels pass through unchanged (fail-open: never lose a group,
a NEW synonym shows up as its own group and is added here when observed —
pre-read label audit in docs/autumn_prereg_analysis_plan.md §8).
"""
from __future__ import annotations

# V4 EN league code → 竞彩 Chinese abbrev. The first 13 are the production
# artifact's training universe (team_state.json union of data/v4_model +
# data/v4_model_cat) — also the pre-registered confirmatory family
# (docs/autumn_prereg_analysis_plan.md §2).
_EN_TO_CN: dict[str, str] = {
    "EPL": "英超",
    "ENG_CHAMPIONSHIP": "英冠",
    "ESP_LA_LIGA": "西甲",
    "ESP_SEGUNDA_DIVISION": "西乙",
    "GER_BUNDESLIGA": "德甲",
    "GER_2_BUNDESLIGA": "德乙",
    "ITA_SERIE_A": "意甲",
    "ITA_SERIE_B": "意乙",
    "FRA_LIGUE_1": "法甲",
    "FRA_LIGUE_2": "法乙",
    "NED_EREDIVISIE": "荷甲",
    "PRT_PRIMEIRA_LIGA": "葡超",
    "JPN_J1": "日职",
    # non-trained labels OBSERVED in jingcai_sp (exploratory-only leagues)
    "WC": "世界杯",
    "FIN_VEIKKAUSLIIGA": "芬超",
    "SWE_ALLSVENSKAN": "瑞超",
    "KOR_K_LEAGUE_1": "韩职",   # sporttery 缩写 = 韩职 (体检 2026-07-03)
    # 2026-07-25 — 表落后于现实的 5 对。前 3 对在 jingcai_sp 里**实测撞上了**
    # (两种标签同时存在 = 同一联赛被劈成两组,正是本模块开头描述的那个病):
    "NOR_ELITESERIEN": "挪超",   # 挪超 Tromso/KFUM/Rosenborg ∪ NOR_… Molde/Viking
    "UCL": "欧冠",               # 欧冠 KI Klaksvik/Omonia ∪ UCL Kairat/The New Saints
    "UEL": "欧罗巴",             # ⭐ 最硬证据:两边**同一批队**(Vojvodina、CSKA Sofia)
    # 后 2 对是**防御性**补:BRA_SERIE_A / USA_MLS 目前在 jingcai_sp 里尚未出现
    # (这两个联赛还没被手填过),但 market_mode 一写就是 EN 代码 —— 队伍池已核实
    # (巴甲 Botafogo/Vitoria/Bahia;美职 Chicago Fire/St. Louis City/Seattle)。
    "BRA_SERIE_A": "巴甲",
    "USA_MLS": "美职",
}

# Chinese synonyms (full names / variants) → the same canonical abbrev.
# Only VERIFIED-or-defensive entries; anything else passes through fail-open.
_CN_SYNONYM: dict[str, str] = {
    "瑞典超级联赛": "瑞超",   # observed in jingcai_vote.league_cn 2026-07-02
    "日职联": "日职",          # common variant of the J1 abbrev
}

#: The 13-league confirmatory universe (canonical CN form) — the production
#: artifact's training face. Pre-registered: only these leagues can CONFIRM.
TRAINED_LEAGUES_CN: frozenset[str] = frozenset({
    "英超", "英冠", "西甲", "西乙", "德甲", "德乙",
    "意甲", "意乙", "法甲", "法乙", "荷甲", "葡超", "日职",
})

# ── 「国内俱乐部联赛」谓词(prereg v1.8 §2 P3,2026-07-27)────────────────────
# 为什么要在这里加:δ₋₂ 的 P3 检验必须**只用俱乐部联赛计数** —— δ 是在国内联赛
# (football-data 各国 CSV + 皇冠)上拟合的,大赛不在那个人口里。实测教训:
# 2026-07 捕到的 15 场 −2 里 **10 场是世界杯**,而世界杯小组赛的实力悬殊场次
# 血洗率异常(5-0/5-0/4-0),拿它们验 δ₋₂ 等于在另一个人口上验。
#
# ⚠️ **不能裸用 `competitions.competition_type_of`** —— 它只认 EN code。本表的
# league 列是**双轨**的(cron 写中文占 86%),中文标签进去会对**所有东西**返回
# "league",世界杯/欧冠/欧罗巴全部被静默算成联赛。我差点就这么写了。
#
# 设计:**allowlist + fail-CLOSED**。分组用的 `canonical_league` 是 fail-open
# (不丢组),但**计数一个预注册人口时 fail-open 是错的** —— 一个没见过的标签
# 宁可不计,也不能默认当联赛混进去。新联赛出现时它会掉出计数,这是**响亮的
# 少数**(N 涨得比预期慢),不是静默污染。
_NON_DOMESTIC_CN: frozenset[str] = frozenset({
    "世界杯", "欧洲杯", "美洲杯", "亚洲杯", "非洲杯", "世预赛", "欧国联",  # 国家队
    "欧冠", "欧罗巴", "欧协联",                                           # 洲际俱乐部杯
})

#: 已知的国内俱乐部联赛(canonical CN)—— P3 计数的合法人口(中文轨)。
DOMESTIC_LEAGUES_CN: frozenset[str] = frozenset(
    set(_EN_TO_CN.values()) | set(_CN_SYNONYM.values())
) - _NON_DOMESTIC_CN


def classify_league(label: str | None) -> str:
    """``'domestic'`` | ``'excluded'`` | ``'unknown'`` —— P3 计数的三态判定。

    **三态而非布尔**,因为两种「不计入」的后果完全不同:
      · ``excluded`` = 已知的大赛/洲际杯 → 本来就该排除,静默即可
      · ``unknown``  = 没见过的标签 → **必须被报出来**。丹超(DNK_SUPERLIGA)
        就是活例:它是国内联赛、竞彩也上架,但 ``_EN_TO_CN`` 没收录中文缩写
        ⇒ cron 写的中文行会掉出计数。悄悄少算 N 和悄悄混入错人口一样坏。

    双轨:EN code 走 V4 竞赛注册表(``CUP_COMPETITIONS`` 列全了杯赛/国家队);
    中文走 allowlist —— ⚠️ **中文绝不能裸用 `competition_type_of`**,它只认 EN,
    中文进去会对**所有东西**返回 ``"league"``,世界杯/欧冠会被算成联赛(实测)。
    """
    from nutmeg.v4.data.competitions import CUP_COMPETITIONS, competition_type_of

    s = str(label or "").strip()
    if not s:
        return "unknown"
    if s.isascii() and s.isupper():                 # EN code 轨
        if s in CUP_COMPETITIONS:
            return "excluded"
        return "domestic" if competition_type_of(s) == "league" else "excluded"
    cn = canonical_league(s)                        # 中文轨
    if cn in _NON_DOMESTIC_CN:
        return "excluded"
    return "domestic" if cn in DOMESTIC_LEAGUES_CN else "unknown"


def is_domestic_club_league(label: str | None) -> bool:
    """P3 计数是否计入该标签。``unknown`` 一律**不计入**(fail-closed)——
    与 `canonical_league` 的 fail-open **故意相反**:那个给分组用(丢组比多组坏),
    这个给**预注册计数**用(混入错人口比少算坏)。用 `classify_league` 看清原因。
    """
    return classify_league(label) == "domestic"


def canonical_league(label: str | None) -> str:
    """RAW league label (any writer's vocabulary) → canonical CN abbrev.

    Fail-open: an unmapped label returns itself (stripped) so no group is ever
    silently dropped — a new synonym surfaces as its own group and gets added
    to the tables above when observed."""
    if not label or not str(label).strip():
        return "(未标联赛)"
    s = str(label).strip()
    return _EN_TO_CN.get(s) or _CN_SYNONYM.get(s) or s
