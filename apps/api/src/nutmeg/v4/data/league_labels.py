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


def canonical_league(label: str | None) -> str:
    """RAW league label (any writer's vocabulary) → canonical CN abbrev.

    Fail-open: an unmapped label returns itself (stripped) so no group is ever
    silently dropped — a new synonym surfaces as its own group and gets added
    to the tables above when observed."""
    if not label or not str(label).strip():
        return "(未标联赛)"
    s = str(label).strip()
    return _EN_TO_CN.get(s) or _CN_SYNONYM.get(s) or s
