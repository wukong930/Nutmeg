"""Map external data-source team names → V4 canonical team names.

V4 (football-data.co.uk) uses abbreviated team names: "Man United", "Ath Bilbao",
"M'gladbach", "Nott'm Forest". External sources use full names: "Manchester United",
"Athletic Club", "Borussia Monchengladbach", "Nottingham Forest".

This module provides:
- normalize_name(): strip punctuation/accents, lowercase, collapse whitespace
- TEAM_ALIASES: hand-curated dict {external_name → v4_canonical_name} per league
- to_v4_canonical(name, league): primary lookup with fuzzy fallback
- unmatched_names(...): tool to diagnose missing mappings during ingest

The aliases dict is intentionally hand-curated rather than auto-derived: leagues
have small team counts (~20–30) so this stays maintainable, and the cost of
a wrong fuzzy match (silent join failure) is much higher than the cost of
adding an explicit alias when ingest reports it as unmatched.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass


def normalize_name(name: str) -> str:
    """Lower-case, strip accents/punctuation, collapse whitespace.

    Used as the matching key everywhere; never stored as a canonical name itself.
    """
    if name is None:
        return ""
    # Strip diacritics: "Atlético" → "Atletico"
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    # Lowercase + replace separators with space (apostrophes/dots/dashes/parens/&)
    cleaned = ascii_only.lower()
    cleaned = cleaned.replace("&", " and ")
    for ch in "'.-(),":
        cleaned = cleaned.replace(ch, " ")
    return " ".join(cleaned.split())


# {league_code: {normalized_external_name: v4_canonical_name}}
# Curated from observed football-data.co.uk names vs understat/clubelo conventions.
TEAM_ALIASES: dict[str, dict[str, str]] = {
    "EPL": {
        "manchester united": "Man United",
        "manchester city": "Man City",
        "nottingham forest": "Nott'm Forest",
        "sheffield united": "Sheffield United",
        "west bromwich albion": "West Brom",
        "west ham united": "West Ham",
        "wolverhampton wanderers": "Wolves",
        "tottenham hotspur": "Tottenham",
        "brighton hove albion": "Brighton",
        "brighton and hove albion": "Brighton",
        "newcastle united": "Newcastle",
        "leicester city": "Leicester",
        "leeds united": "Leeds",
        "norwich city": "Norwich",
        "ipswich town": "Ipswich",
        "luton town": "Luton",
    },
    "ESP_LA_LIGA": {
        "athletic club": "Ath Bilbao",
        "athletic bilbao": "Ath Bilbao",
        "atletico madrid": "Ath Madrid",
        "atletico de madrid": "Ath Madrid",
        "real betis": "Betis",
        "celta vigo": "Celta",
        "rcd espanyol": "Espanol",
        "espanyol": "Espanol",
        "real sociedad": "Sociedad",
        "real valladolid": "Valladolid",
        "deportivo alaves": "Alaves",
        "ud almeria": "Almeria",
        "ud las palmas": "Las Palmas",
        "ud leganes": "Leganes",
        "rayo vallecano": "Vallecano",
        "girona fc": "Girona",
    },
    "ITA_SERIE_A": {
        "ac milan": "Milan",
        "internazionale": "Inter",
        "inter milan": "Inter",
        "as roma": "Roma",
        "ssc napoli": "Napoli",
        "ss lazio": "Lazio",
        "atalanta bc": "Atalanta",
        "juventus fc": "Juventus",
        "torino fc": "Torino",
        "ac monza": "Monza",
        "us lecce": "Lecce",
        "como 1907": "Como",
        "hellas verona": "Verona",
        "udinese calcio": "Udinese",
        "venezia fc": "Venezia",
    },
    "GER_BUNDESLIGA": {
        "bayern munchen": "Bayern Munich",
        "fc bayern munchen": "Bayern Munich",
        "borussia dortmund": "Dortmund",
        "rb leipzig": "RB Leipzig",
        "bayer leverkusen": "Leverkusen",
        "bayer 04 leverkusen": "Leverkusen",
        "eintracht frankfurt": "Ein Frankfurt",
        "vfb stuttgart": "Stuttgart",
        "1 fc koln": "FC Koln",
        "fc koln": "FC Koln",
        "borussia monchengladbach": "M'gladbach",
        "monchengladbach": "M'gladbach",
        "borussia m gladbach": "M'gladbach",
        "vfl wolfsburg": "Wolfsburg",
        "sc freiburg": "Freiburg",
        "tsg hoffenheim": "Hoffenheim",
        "1899 hoffenheim": "Hoffenheim",
        "werder bremen": "Werder Bremen",
        "sv werder bremen": "Werder Bremen",
        "fc augsburg": "Augsburg",
        "1 fsv mainz 05": "Mainz",
        "mainz 05": "Mainz",
        "1 fc heidenheim": "Heidenheim",
        "fc heidenheim": "Heidenheim",
        "vfl bochum": "Bochum",
        "fc st pauli": "St Pauli",
        "holstein kiel": "Holstein Kiel",
        "union berlin": "Union Berlin",
        "1 fc union berlin": "Union Berlin",
        "schalke 04": "Schalke 04",
    },
    "FRA_LIGUE_1": {
        "paris saint germain": "Paris SG",
        "paris saint germain fc": "Paris SG",
        "olympique de marseille": "Marseille",
        "olympique marseille": "Marseille",
        "olympique lyonnais": "Lyon",
        "as monaco": "Monaco",
        "lille osc": "Lille",
        "stade rennais": "Rennes",
        "stade rennais fc": "Rennes",
        "ogc nice": "Nice",
        "stade brestois 29": "Brest",
        "fc nantes": "Nantes",
        "stade de reims": "Reims",
        "rc lens": "Lens",
        "rc strasbourg alsace": "Strasbourg",
        "rc strasbourg": "Strasbourg",
        "fc toulouse": "Toulouse",
        "le havre ac": "Le Havre",
        "le havre": "Le Havre",
        "angers sco": "Angers",
        "as saint etienne": "St Etienne",
        "saint etienne": "St Etienne",
        "montpellier hsc": "Montpellier",
        "auxerre": "Auxerre",
    },
    "NED_EREDIVISIE": {
        "psv eindhoven": "PSV Eindhoven",
        "fc utrecht": "Utrecht",
        "fc twente": "Twente",
        "feyenoord": "Feyenoord",
        "ajax": "Ajax",
        "az alkmaar": "AZ Alkmaar",
        "az": "AZ Alkmaar",
        "sparta rotterdam": "Sparta Rotterdam",
        "go ahead eagles": "Go Ahead Eagles",
        # ⚠️ 目标必须是 team_state 里真实存在的键。这条曾写成 "NEC Nijmegen"
        # (football-data 用的是 "Nijmegen")—— 别名存在但指向池外,等于没写,
        # 而且比没写更坏:表里有一行,看起来像已经处理过了。2026-08-05 修。
        "nec nijmegen": "Nijmegen",
        "rkc waalwijk": "Waalwijk",
        "fc groningen": "Groningen",
        "willem ii": "Willem II",
        "almere city fc": "Almere City",
        "fortuna sittard": "For Sittard",
        "heracles almelo": "Heracles",
        "pec zwolle": "Zwolle",
    },
    "PRT_PRIMEIRA_LIGA": {
        "fc porto": "Porto",
        "sl benfica": "Benfica",
        # 同「指向池外」的死别名:football-data 管葡体叫 "Sp Lisbon",不叫
        # "Sporting"。葡超豪门因此一直吃 1500 占位 Elo。2026-08-05 修。
        "sporting cp": "Sp Lisbon",
        "sporting clube de portugal": "Sp Lisbon",
        "sc braga": "Sp Braga",
        "vitoria sc": "Guimaraes",
        "vitoria de guimaraes": "Guimaraes",
        "rio ave fc": "Rio Ave",
        "boavista fc": "Boavista",
        "casa pia ac": "Casa Pia",
        "estoril praia": "Estoril",
        "estrela amadora": "Estrela",
        "gd estoril praia": "Estoril",
        "famalicao": "Famalicao",
        "fc famalicao": "Famalicao",
        "gd chaves": "Chaves",
        "santa clara": "Santa Clara",
        "moreirense fc": "Moreirense",
    },
    # ── 以下 6 个联赛此前**完全没有别名块** ───────────────────────────────
    # 它们都在 14 个训练联赛之内,但别名表只覆盖了顶级联赛 ⇒ 服务侧队名解析
    # 一直靠 fuzzy 兜底,而 fuzzy 在服务侧已被关掉(见 `resolve_serving_name`)。
    #
    # 这批条目**不是手写猜的**,是 2026-08-05 用两条可复核的判据筛出来的:
    #   ① 归一化后词元包含,且在该联赛 team_state 池内**唯一**;
    #   ② 目标必须出现在 football-data 该联赛**最新赛季**的名单里。
    # 判据②拦掉了三条看起来很像、其实是升降级换人的毒配对:
    #   "Rouen" ↛ "Quevilly Rouen"(两家不同俱乐部,后者 2324 后就不在队列)
    #   "SK Beveren" ↛ "Waasland-Beveren"(2021 之后消失,就算真是改名也已陈旧)
    #   "ADO Den Haag" ↛ "Den Haag"(已降级)
    # 纯前缀差异("VfL Bochum"→"Bochum")不在这里 —— 那由 `_affix_core` 规则
    # 自动处理,写进表里反而会随赛季腐烂。
    "BEL_PRO_LEAGUE": {
        "standard liege": "Standard",
        "union st gilloise": "St. Gilloise",
        "zulte waregem": "Waregem",
    },
    "ENG_CHAMPIONSHIP": {
        "hull city": "Hull",
    },
    "ESP_SEGUNDA_DIVISION": {
        "deportivo la coruna": "La Coruna",
        "racing santander": "Santander",
    },
    "FRA_LIGUE_2": {
        "clermont foot": "Clermont",
        # ⚠️ 别名表按联赛分 ⇒ 球队降级就丢映射。这条在 FRA_LIGUE_1 里早就有,
        # 圣埃蒂安降到乙级后又要重写一遍。补一条比让它吃 1500 便宜。
        "saint etienne": "St Etienne",
    },
    "GER_2_BUNDESLIGA": {
        "arminia bielefeld": "Bielefeld",
        "karlsruher sc": "Karlsruhe",       # 形容词式词尾,剥前缀规则够不着
        "dynamo dresden": "Dresden",
        "eintracht braunschweig": "Braunschweig",
    },
    "JPN_J1": {
        "fagiano okayama": "Okayama",
        "kashima": "Kashima Antlers",
        "kyoto sanga": "Kyoto",
        "machida zelvia": "Machida",
        "urawa": "Urawa Reds",
    },
}


# V8 W1 — Cup-team aliases. Cup competitions (UCL, UEL, etc.) bring teams
# from multiple leagues into one fixture; the per-league TEAM_ALIASES isn't
# enough because the API-Football name for "Manchester United" needs to
# resolve to the V4 canonical "Man United" regardless of whether the row
# is from EPL or a UCL match. CUP_TEAM_ALIASES is the catch-all global
# alias map — falls back to walking every per-league dict via
# `to_v4_canonical_global`.
#
# Add entries here when `nutmeg-canonical-report-cup` reports unmatched
# names. Keep both the API-Football canonical form ("Manchester United")
# AND any common alternates ("Man Utd") because the lookup tries the
# normalized form against each.
CUP_TEAM_ALIASES: dict[str, str] = {
    # English teams in cup competitions
    "manchester united": "Man United",
    "man united": "Man United",
    "manchester city": "Man City",
    "man city": "Man City",
    "tottenham hotspur": "Tottenham",
    "newcastle united": "Newcastle",
    "leicester city": "Leicester",
    "leeds united": "Leeds",
    "wolverhampton wanderers": "Wolves",
    "nottingham forest": "Nott'm Forest",
    "west ham united": "West Ham",
    "west bromwich albion": "West Brom",
    # Spanish
    "real madrid cf": "Real Madrid",
    "fc barcelona": "Barcelona",
    "atletico madrid": "Ath Madrid",
    "atletico de madrid": "Ath Madrid",
    "athletic club": "Ath Bilbao",
    "athletic bilbao": "Ath Bilbao",
    # Italian
    "ac milan": "Milan",
    "internazionale": "Inter",
    "inter milan": "Inter",
    "juventus fc": "Juventus",
    "ssc napoli": "Napoli",
    # German
    "fc bayern munchen": "Bayern Munich",
    "bayern munchen": "Bayern Munich",
    "borussia dortmund": "Dortmund",
    "rb leipzig": "RB Leipzig",
    "bayer 04 leverkusen": "Leverkusen",
    "bayer leverkusen": "Leverkusen",
    # French
    "paris saint germain": "Paris SG",
    "paris saint germain fc": "Paris SG",
    "psg": "Paris SG",
    "olympique de marseille": "Marseille",
    "olympique lyonnais": "Lyon",
    "as monaco": "Monaco",
    # Portuguese
    "fc porto": "Porto",
    "sl benfica": "Benfica",
    "sporting cp": "Sporting",
    "sporting clube de portugal": "Sporting",
    "sc braga": "Sp Braga",
    # Dutch
    "psv eindhoven": "PSV Eindhoven",
    "afc ajax": "Ajax",
    "feyenoord rotterdam": "Feyenoord",
}


@dataclass(frozen=True)
class CanonicalLookupResult:
    """Result of a team-name lookup attempt.

    - canonical: the resolved V4 canonical name, or None if not found
    - method: how it was resolved ('exact', 'alias', 'fuzzy', 'unmatched')
    - confidence: 1.0 for exact/alias, fuzzy similarity (0..1), 0.0 for unmatched
    """

    canonical: str | None
    method: str
    confidence: float


def to_v4_canonical(
    name: str,
    league: str,
    v4_team_pool: Iterable[str],
    fuzzy_threshold: float | None = 0.86,
) -> CanonicalLookupResult:
    """Resolve an external team name to its V4 canonical name.

    Precedence:
        1. Exact match against v4_team_pool (case-sensitive — V4 is consistent)
        2. Normalized match against v4_team_pool (handles "Atletico" vs "Atlético")
        3. Alias lookup in TEAM_ALIASES[league]
        4. Fuzzy match (difflib SequenceMatcher) against v4_team_pool
           — returns None if best ratio < fuzzy_threshold

    fuzzy_threshold of 0.86 is conservative; lower threshold causes silent
    wrong joins (e.g., "Real Madrid" vs "Real Sociedad" ratio ~0.79).

    ``fuzzy_threshold=None`` **disables step 4 entirely** — the lookup becomes
    fully deterministic. 服务侧走的就是这条(见 `resolve_serving_name`):
    「关掉模糊」是一个**有名字的状态**,不是「把阈值调到恰好不可达」——
    后者会在有人改动第 4 级时静默失效。
    """
    if not name:
        return CanonicalLookupResult(None, "unmatched", 0.0)
    pool = list(v4_team_pool)
    if not pool:
        return CanonicalLookupResult(None, "unmatched", 0.0)
    # 1. exact
    if name in pool:
        return CanonicalLookupResult(name, "exact", 1.0)
    # 2. normalized exact
    name_norm = normalize_name(name)
    pool_norm = {normalize_name(t): t for t in pool}
    if name_norm in pool_norm:
        return CanonicalLookupResult(pool_norm[name_norm], "exact", 1.0)
    # 3. alias
    league_aliases = TEAM_ALIASES.get(league, {})
    if name_norm in league_aliases:
        canonical = league_aliases[name_norm]
        if canonical in pool:
            return CanonicalLookupResult(canonical, "alias", 1.0)
    # 4. fuzzy (opt-out: None ⇒ 到此为止,只走确定性的三级)
    if fuzzy_threshold is None:
        return CanonicalLookupResult(None, "unmatched", 0.0)
    matches = difflib.get_close_matches(name_norm, list(pool_norm.keys()), n=1, cutoff=fuzzy_threshold)
    if matches:
        canonical = pool_norm[matches[0]]
        ratio = difflib.SequenceMatcher(None, name_norm, matches[0]).ratio()
        return CanonicalLookupResult(canonical, "fuzzy", ratio)
    return CanonicalLookupResult(None, "unmatched", 0.0)


#: 俱乐部**法定形式**记号。football-data.co.uk 一律剥掉("VfL Bochum" → "Bochum"、
#: "1. FC Nürnberg" → "Nurnberg"),而 API-Football 保留完整注册名。
#:
#: ⚠️ 这张表**只收法律形式/社团后缀**,绝不收任何地名、队名词或队伍身份标记:
#:   · 不收 ``b`` / ``ii`` —— 预备队标记有意义,剥掉会把 "Sociedad B" 并进 "Sociedad"。
#:   · 不收 ``club`` —— "Club Brugge KV" 剥掉 ``kv`` 后已与 "Club Brugge" 相等,
#:     多剥一个只会让 "Cercle Brugge" 之类更容易撞上。
#: 表越小越安全:每多一个词元,就多一次把两支不同球队折叠成同一个 core 的机会。
_LEGAL_FORM_TOKENS = frozenset({
    "fc", "sc", "sv", "vfl", "vfb", "spvgg", "kv", "kvc", "bsc", "tsg", "fsv", "msv",
    "ad", "cf", "cd", "ud", "rc", "ca", "ac", "as", "ss", "ssc", "sk", "afc", "cfc",
    "1",
})
#: 队名里的成立年份:"Hannover 96" / "Darmstadt 98" / "Schalke 04"。两侧**对称**
#: 剥离后再比,所以 "FC Schalke 04" 和 "Schalke 04" 都归到 ``("schalke",)``。
_FOUNDING_YEAR = re.compile(r"^(0[0-9]|1[0-9]|[5-9][0-9])$")


def _affix_core(name: str) -> tuple[str, ...]:
    """归一化后剥掉法定形式记号与成立年份,返回剩下的词元。

    这是一条**规则**,不是逐队的猜测:它只能删掉封闭表里的记号,没法把
    "Kashima" 变成 "Tokushima"。配合调用方的「池内唯一」要求即可安全使用。
    """
    return tuple(
        tok for tok in normalize_name(name).split()
        if tok not in _LEGAL_FORM_TOKENS and not _FOUNDING_YEAR.match(tok)
    )


def resolve_serving_name(
    name: str,
    league: str,
    v4_team_pool: Iterable[str],
) -> CanonicalLookupResult:
    """服务侧队名解析 —— **全确定性,没有模糊那一级**。

    `to_v4_canonical` 的前三级(精确 / 归一化精确 / 别名)原样复用,第四级把
    ``fuzzy`` 换成 `_affix_core` + 池内唯一。

    ## 为什么服务侧必须关掉 fuzzy(2026-08-05 实测)

    拿 203 个 API-Football 队名对 14 个联赛的 ``team_state`` 量了一遍:

    * fuzzy@0.86 在 81 条缺失里只捞回 **2** 条(2.5%),却要承担全部误配风险;
    * 把阈值降到能捞回东西的高度,毒配对同时进来 —— ``VfL Bochum → Bochum``
      (对)和 ``Kashima → Tokushima``(错)**相似度都是 0.750**,不存在能把
      两者分开的阈值;
    * 降阈值后它还**优先挑错的**:``Kashima Antlers`` 就在池子里,但 ratio
      仅 0.636,排在 ``Tokushima``(0.750)之后 —— 正确答案在场却选错。

    ⇒ 高阈值几乎修不动东西,低阈值在正确答案在场时选错,两头都不成立。

    `_affix_core` 则捞回 23 条且逐条复核全对,因为它只删封闭表里的法定记号,
    构造不出跨球队的折叠。见 [[cross-source-team-name-mismatch]]。
    """
    pool = list(v4_team_pool)
    hit = to_v4_canonical(name, league, pool, fuzzy_threshold=None)
    if hit.canonical is not None:
        return hit
    core = _affix_core(name)
    if not core:
        return CanonicalLookupResult(None, "unmatched", 0.0)
    cands = [t for t in pool if _affix_core(t) == core]
    if len(cands) == 1:
        return CanonicalLookupResult(cands[0], "affix", 1.0)
    return CanonicalLookupResult(None, "unmatched", 0.0)


def report_unmatched(
    external_names: Iterable[str],
    league: str,
    v4_team_pool: Iterable[str],
    fuzzy_threshold: float = 0.86,
) -> list[tuple[str, CanonicalLookupResult]]:
    """For each external name, report its resolution. Useful for ingest dry-run.

    Returns a list of (external_name, result) for ALL inputs (matched + unmatched),
    so callers can grep ``[r for r in results if r[1].canonical is None]``.
    """
    pool = list(v4_team_pool)
    return [
        (name, to_v4_canonical(name, league, pool, fuzzy_threshold))
        for name in external_names
    ]


# ---------- V8 W1 — cross-league / cup-team lookup --------------------

def build_global_team_pool(
    league_team_pools: dict[str, Iterable[str]],
) -> list[str]:
    """Union every league's V4 team pool into one flat sorted list.

    Used as the lookup pool for cup matches where the team's native
    league isn't known a priori (UCL Real Madrid vs Bayern → need to
    find both teams across La Liga + Bundesliga pools).

    Duplicate canonical names across leagues are de-duplicated. Order
    is alphabetical so the output is stable for tests and diagnostics.
    """
    union: set[str] = set()
    for teams in league_team_pools.values():
        for t in teams:
            if t:
                union.add(t)
    return sorted(union)


def to_v4_canonical_global(
    name: str,
    global_team_pool: Iterable[str],
    *,
    fuzzy_threshold: float = 0.86,
) -> CanonicalLookupResult:
    """Resolve a cup-match team name to its V4 canonical name (any league).

    Search precedence:
        1. Exact match against `global_team_pool`
        2. Normalized exact (handles accents / punctuation)
        3. Lookup in `CUP_TEAM_ALIASES` (cup-specific catch-all map)
        4. Walk every per-league `TEAM_ALIASES` dict — first hit that
           resolves to a name actually in the global pool wins
        5. Fuzzy match against the global pool

    The V8 W1 design choice: cup teams DON'T know their native league at
    join time, so the per-league `to_v4_canonical` API doesn't fit.
    `to_v4_canonical_global` walks all alias dicts, returning the first
    that resolves into the union pool. Add to `CUP_TEAM_ALIASES` when
    `nutmeg-canonical-report-cup` reports unmatched names.
    """
    if not name:
        return CanonicalLookupResult(None, "unmatched", 0.0)
    pool = list(global_team_pool)
    if not pool:
        return CanonicalLookupResult(None, "unmatched", 0.0)

    # 1. exact
    if name in pool:
        return CanonicalLookupResult(name, "exact", 1.0)

    # 2. normalized exact
    name_norm = normalize_name(name)
    pool_norm = {normalize_name(t): t for t in pool}
    if name_norm in pool_norm:
        return CanonicalLookupResult(pool_norm[name_norm], "exact", 1.0)

    # 3. cup-specific alias
    if name_norm in CUP_TEAM_ALIASES:
        canonical = CUP_TEAM_ALIASES[name_norm]
        if canonical in pool:
            return CanonicalLookupResult(canonical, "alias", 1.0)

    # 4. walk per-league aliases (the catch-all for teams not in CUP_TEAM_ALIASES)
    for league_aliases in TEAM_ALIASES.values():
        if name_norm in league_aliases:
            canonical = league_aliases[name_norm]
            if canonical in pool:
                return CanonicalLookupResult(canonical, "alias", 1.0)

    # 5. fuzzy
    matches = difflib.get_close_matches(
        name_norm, list(pool_norm.keys()), n=1, cutoff=fuzzy_threshold,
    )
    if matches:
        canonical = pool_norm[matches[0]]
        ratio = difflib.SequenceMatcher(None, name_norm, matches[0]).ratio()
        return CanonicalLookupResult(canonical, "fuzzy", ratio)

    return CanonicalLookupResult(None, "unmatched", 0.0)


def report_unmatched_global(
    external_names: Iterable[str],
    global_team_pool: Iterable[str],
    *,
    fuzzy_threshold: float = 0.86,
) -> list[tuple[str, CanonicalLookupResult]]:
    """Cross-league sibling of `report_unmatched`. Cup-ingest diagnostic."""
    pool = list(global_team_pool)
    return [
        (name, to_v4_canonical_global(name, pool, fuzzy_threshold=fuzzy_threshold))
        for name in external_names
    ]
