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
        "nec nijmegen": "NEC Nijmegen",
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
        "sporting cp": "Sporting",
        "sporting clube de portugal": "Sporting",
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
    fuzzy_threshold: float = 0.86,
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
    # 4. fuzzy
    matches = difflib.get_close_matches(name_norm, list(pool_norm.keys()), n=1, cutoff=fuzzy_threshold)
    if matches:
        canonical = pool_norm[matches[0]]
        ratio = difflib.SequenceMatcher(None, name_norm, matches[0]).ratio()
        return CanonicalLookupResult(canonical, "fuzzy", ratio)
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
