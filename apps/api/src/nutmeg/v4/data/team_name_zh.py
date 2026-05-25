"""V11 P1-FE#2 — Chinese team names for top-5 European leagues.

Static dictionary mapping V4 canonical team names (`to_v4_canonical_*`
output) to their Chinese names. Covers ~100 teams across:

- 英超 EPL (English Premier League) — 20 teams
- 西甲 ESP_LA_LIGA (Spanish La Liga) — 20 teams
- 意甲 ITA_SERIE_A (Italian Serie A) — 20 teams
- 德甲 GER_BUNDESLIGA (German Bundesliga) — 18 teams
- 法甲 FRA_LIGUE_1 (French Ligue 1) — 18 teams

The frontend uses ``lookup_zh()`` (or its JS equivalent fetched from
``/api/v4/team-name-zh``) to render Chinese names when ``locale == 'zh'``.
Teams outside the top-5 fall through unchanged (English shown).

Naming conventions:
- Use mainland Chinese conventions (e.g. 曼联 not 曼徹斯特聯; 拜仁 not 拜仁慕尼黑 in cards)
- Compact display: prefer the short form people actually use
- For ambiguous abbreviations (e.g. 莱斯特/莱切) we keep them
  disambiguated where the canonical name does so
"""
from __future__ import annotations

from typing import Dict


# ============ Premier League (英超) ===================================
_EPL: Dict[str, str] = {
    "Arsenal": "阿森纳",
    "Aston Villa": "阿斯顿维拉",
    "Bournemouth": "伯恩茅斯",
    "Brentford": "布伦特福德",
    "Brighton": "布莱顿",
    "Chelsea": "切尔西",
    "Crystal Palace": "水晶宫",
    "Everton": "埃弗顿",
    "Fulham": "富勒姆",
    "Ipswich": "伊普斯维奇",
    "Leicester": "莱斯特城",
    "Liverpool": "利物浦",
    "Man City": "曼城",
    "Man United": "曼联",
    "Newcastle": "纽卡斯尔",
    "Nottingham Forest": "诺丁汉森林",
    "Southampton": "南安普顿",
    "Tottenham": "热刺",
    "West Ham": "西汉姆",
    "Wolves": "狼队",
    # Common variant spellings that survive canonical normalization
    "Manchester City": "曼城",
    "Manchester United": "曼联",
}


# ============ La Liga (西甲) ==========================================
_LA_LIGA: Dict[str, str] = {
    "Real Madrid": "皇家马德里",
    "Barcelona": "巴塞罗那",
    "Atletico Madrid": "马德里竞技",
    "Athletic Bilbao": "毕尔巴鄂",
    "Real Sociedad": "皇家社会",
    "Real Betis": "皇家贝蒂斯",
    "Sevilla": "塞维利亚",
    "Villarreal": "比利亚雷亚尔",
    "Girona": "赫罗纳",
    "Valencia": "瓦伦西亚",
    "Mallorca": "马洛卡",
    "Osasuna": "奥萨苏纳",
    "Las Palmas": "拉斯帕尔马斯",
    "Celta Vigo": "塞尔塔",
    "Espanyol": "西班牙人",
    "Getafe": "赫塔费",
    "Rayo Vallecano": "巴列卡诺",
    "Leganes": "莱加内斯",
    "Alaves": "阿拉维斯",
    "Valladolid": "巴利亚多利德",
}


# ============ Serie A (意甲) ==========================================
_SERIE_A: Dict[str, str] = {
    "Inter": "国际米兰",
    "Juventus": "尤文图斯",
    "AC Milan": "AC米兰",
    "Milan": "AC米兰",                # legacy variant
    "Napoli": "那不勒斯",
    "Atalanta": "亚特兰大",
    "Roma": "罗马",
    "Lazio": "拉齐奥",
    "Fiorentina": "佛罗伦萨",
    "Bologna": "博洛尼亚",
    "Torino": "都灵",
    "Genoa": "热那亚",
    "Monza": "蒙扎",
    "Udinese": "乌迪内斯",
    "Como": "科莫",
    "Verona": "维罗纳",
    "Cagliari": "卡利亚里",
    "Empoli": "恩波利",
    "Lecce": "莱切",
    "Parma": "帕尔马",
    "Venezia": "威尼斯",
}


# ============ Bundesliga (德甲) =======================================
_BUNDESLIGA: Dict[str, str] = {
    "Bayern Munich": "拜仁慕尼黑",
    "Bayer Leverkusen": "勒沃库森",
    "Borussia Dortmund": "多特蒙德",
    "Dortmund": "多特蒙德",            # variant
    "RB Leipzig": "莱比锡红牛",
    "Eintracht Frankfurt": "法兰克福",
    "Frankfurt": "法兰克福",            # variant
    "VfB Stuttgart": "斯图加特",
    "Stuttgart": "斯图加特",            # variant
    "Borussia Monchengladbach": "门兴格拉德巴赫",
    "Monchengladbach": "门兴格拉德巴赫", # variant
    "Hoffenheim": "霍芬海姆",
    "Mainz 05": "美因茨",
    "Mainz": "美因茨",                  # variant
    "Wolfsburg": "沃尔夫斯堡",
    "Werder Bremen": "云达不莱梅",
    "Bremen": "云达不莱梅",             # variant
    "Augsburg": "奥格斯堡",
    "Freiburg": "弗赖堡",
    "Union Berlin": "柏林联合",
    "Heidenheim": "海登海姆",
    "St. Pauli": "圣保利",
    "St Pauli": "圣保利",                # variant
    "Holstein Kiel": "霍尔斯坦基尔",
    "Bochum": "波鸿",
    "Koln": "科隆",                     # may appear in archived data
    "Cologne": "科隆",                  # English variant
}


# ============ Ligue 1 (法甲) ==========================================
_LIGUE_1: Dict[str, str] = {
    "Paris SG": "巴黎圣日耳曼",
    "Paris Saint Germain": "巴黎圣日耳曼",
    "PSG": "巴黎圣日耳曼",
    "Marseille": "马赛",
    "Monaco": "摩纳哥",
    "Lyon": "里昂",
    "Lille": "里尔",
    "Nice": "尼斯",
    "Lens": "朗斯",
    "Rennes": "雷恩",
    "Strasbourg": "斯特拉斯堡",
    "Toulouse": "图卢兹",
    "Nantes": "南特",
    "Reims": "兰斯",
    "Brest": "布雷斯特",
    "Auxerre": "欧塞尔",
    "Le Havre": "勒阿弗尔",
    "Angers": "昂热",
    "Montpellier": "蒙彼利埃",
    "Saint-Etienne": "圣埃蒂安",
    "Saint Etienne": "圣埃蒂安",
}


# ============ Combined lookup =========================================
TEAM_NAME_ZH: Dict[str, str] = {}
TEAM_NAME_ZH.update(_EPL)
TEAM_NAME_ZH.update(_LA_LIGA)
TEAM_NAME_ZH.update(_SERIE_A)
TEAM_NAME_ZH.update(_BUNDESLIGA)
TEAM_NAME_ZH.update(_LIGUE_1)


def lookup_zh(team_name: str) -> str:
    """Return Chinese name for a canonical team, else input unchanged.

    Parameters
    ----------
    team_name : str
        V4 canonical team name (output of ``to_v4_canonical_*`` family).

    Returns
    -------
    str
        Chinese name if registered, else the input string verbatim.
        Empty / None input returns empty string.

    Examples
    --------
    >>> lookup_zh("Arsenal")
    '阿森纳'
    >>> lookup_zh("Some Unknown FC")
    'Some Unknown FC'
    >>> lookup_zh("")
    ''
    """
    if not team_name:
        return ""
    return TEAM_NAME_ZH.get(team_name, team_name)


def coverage_by_league() -> Dict[str, int]:
    """Return per-league entry count (for diagnostics + tests)."""
    return {
        "EPL": len(_EPL),
        "ESP_LA_LIGA": len(_LA_LIGA),
        "ITA_SERIE_A": len(_SERIE_A),
        "GER_BUNDESLIGA": len(_BUNDESLIGA),
        "FRA_LIGUE_1": len(_LIGUE_1),
        "TOTAL": len(TEAM_NAME_ZH),
    }
