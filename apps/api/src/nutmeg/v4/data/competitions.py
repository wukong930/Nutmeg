"""Cup + national-team competition registry — V6 W11.

Until W11 every competition was a domestic league. W11 adds the cup
tournaments (UCL, UEL, UECL, FAC, COPA) + national-team tournaments
(World Cup, Euro Championship, Copa America). The model itself remains
trained on league data only — cup features are surfaced as side-channel
columns so the GBM can learn a downweight on cup matches without being
trained directly on the (small, irregular) cup sample.

This module is the SINGLE PLACE that knows:
- which competition codes exist
- whether each is a league / club cup / national-team cup
- how to flag knockout vs group-stage rounds (when API-Football tells us)
- API-Football's numeric league ID per cup (V6 W1 had domestic leagues
  only; W11 adds the cups)

Downstream callers (cup_features, ingest CLIs, dashboard subtitle copy)
import from here rather than hard-coding magic codes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CompetitionType = Literal["league", "club_cup", "national_team_cup"]
"""High-level taxonomy.

- league: domestic round-robin league (EPL, La Liga, J1, etc.)
- club_cup: club-side cup tournament with knockout rounds and possibly
  cross-league pairings (UCL, UEL, UECL, FAC, etc.)
- national_team_cup: tournament between national teams (WC, EURO,
  COPA_AMERICA); player pool is different from clubs (much smaller
  sample of recent matches per team, neutral venues, etc.)
"""


@dataclass(frozen=True)
class Competition:
    """One competition entry in the registry."""

    code: str                       # canonical V4 code (e.g. "UCL")
    display_zh: str                 # Chinese display name
    display_en: str                 # English display name
    competition_type: CompetitionType
    api_football_id: int | None     # None when not surfaced via API-Football
    has_knockouts: bool             # True if format includes knockout rounds
    has_two_legged_ties: bool       # True if any round is home-and-away
    notes: str = ""


# --- Cup + national-team registry ---------------------------------------

# IDs taken from API-Football's /leagues catalog (well-known constants).
# https://www.api-football.com/documentation-v3#tag/Leagues
CUP_COMPETITIONS: dict[str, Competition] = {
    # Club cups — UEFA
    "UCL": Competition(
        code="UCL",
        display_zh="欧冠 (UEFA 冠军联赛)",
        display_en="UEFA Champions League",
        competition_type="club_cup",
        api_football_id=2,
        has_knockouts=True,
        has_two_legged_ties=True,
        notes="Cross-league: clubs from multiple European leagues",
    ),
    "UEL": Competition(
        code="UEL",
        display_zh="欧联 (UEFA 欧罗巴联赛)",
        display_en="UEFA Europa League",
        competition_type="club_cup",
        api_football_id=3,
        has_knockouts=True,
        has_two_legged_ties=True,
    ),
    "UECL": Competition(
        code="UECL",
        display_zh="欧会杯 (UEFA 欧洲协会联赛)",
        display_en="UEFA Europa Conference League",
        competition_type="club_cup",
        api_football_id=848,
        has_knockouts=True,
        has_two_legged_ties=True,
    ),

    # Domestic club cups
    "FAC": Competition(
        code="FAC",
        display_zh="足总杯 (英格兰)",
        display_en="FA Cup (England)",
        competition_type="club_cup",
        api_football_id=45,
        has_knockouts=True,
        has_two_legged_ties=False,  # FA Cup is single-leg with replays
        notes="Includes lower-division teams not in EPL/Championship train set",
    ),
    "EFL_CUP": Competition(
        code="EFL_CUP",
        display_zh="联赛杯 (英格兰)",
        display_en="EFL Cup (Carabao Cup)",
        competition_type="club_cup",
        api_football_id=48,
        has_knockouts=True,
        # ⚠️ 这个 True 是**实测**的,不是「我记得半决赛打两回合」:拉 season=2025
        # 全 93 场,`Semi-finals` 里 Man City–Newcastle 与 Arsenal–Chelsea 各出现
        # 2 次 ⇒ 两回合。其余轮次单场。(2026-08-05)
        has_two_legged_ties=True,
        notes=(
            "英联赛杯。竞彩写作「英联赛杯」。全部 92 家 EFL 俱乐部参赛 ⇒ 大量队伍不在"
            "训练集里,只走市场模式(Pinnacle de-vig)。⚠️ AF 的 `League Cup` 这个名字"
            "苏格兰(185)/埃及(895)/泰国(898) 都有,认 id=48 + country=England。"
        ),
    ),
    "COPA_DEL_REY": Competition(
        code="COPA_DEL_REY",
        display_zh="国王杯 (西班牙)",
        display_en="Copa del Rey (Spain)",
        competition_type="club_cup",
        api_football_id=143,
        has_knockouts=True,
        has_two_legged_ties=False,
    ),
    "COPPA_ITALIA": Competition(
        code="COPPA_ITALIA",
        display_zh="意大利杯",
        display_en="Coppa Italia",
        competition_type="club_cup",
        api_football_id=137,
        has_knockouts=True,
        has_two_legged_ties=True,
    ),
    "DFB_POKAL": Competition(
        code="DFB_POKAL",
        display_zh="德国杯",
        display_en="DFB-Pokal",
        competition_type="club_cup",
        api_football_id=81,
        has_knockouts=True,
        has_two_legged_ties=False,
    ),
    "COUPE_DE_FRANCE": Competition(
        code="COUPE_DE_FRANCE",
        display_zh="法国杯",
        display_en="Coupe de France",
        competition_type="club_cup",
        api_football_id=66,
        has_knockouts=True,
        has_two_legged_ties=False,
    ),

    # National team tournaments
    "WC": Competition(
        code="WC",
        display_zh="世界杯",
        display_en="FIFA World Cup",
        competition_type="national_team_cup",
        api_football_id=1,
        has_knockouts=True,
        has_two_legged_ties=False,
        notes="Single venue, group stage + knockouts",
    ),
    "EURO": Competition(
        code="EURO",
        display_zh="欧洲杯",
        display_en="UEFA European Championship",
        competition_type="national_team_cup",
        api_football_id=4,
        has_knockouts=True,
        has_two_legged_ties=False,
    ),
    "COPA_AMERICA": Competition(
        code="COPA_AMERICA",
        display_zh="美洲杯",
        display_en="CONMEBOL Copa America",
        competition_type="national_team_cup",
        api_football_id=9,
        has_knockouts=True,
        has_two_legged_ties=False,
    ),
    "WC_QUAL_UEFA": Competition(
        code="WC_QUAL_UEFA",
        display_zh="世界杯欧洲区预选赛",
        display_en="World Cup Qualification (UEFA)",
        competition_type="national_team_cup",
        api_football_id=32,
        has_knockouts=False,  # round-robin groups
        has_two_legged_ties=False,
    ),
}


# Knockout round labels API-Football emits in `fixture.league.round`.
# Used by `is_knockout_round(label)` to flag a fixture as knockout vs
# group-stage. Matches both English ("Round of 16") and abbreviations.
_KNOCKOUT_ROUND_TOKENS = (
    "round of",       # "Round of 16", "Round of 32"
    "1st knockout",   # API-Football's 1st knockout round label
    "knockout",
    "quarter-final",
    "quarter-finals",
    "quarter final",
    "semi-final",
    "semi-finals",
    "semi final",
    "final",          # matches "Final", "3rd-place final" etc.
    "play-off",
    "playoff",
)


# --- Public helpers -----------------------------------------------------

def is_cup_competition(code: str) -> bool:
    """True for any club cup or national-team cup; False for league codes."""
    return code in CUP_COMPETITIONS


def is_national_team_competition(code: str) -> bool:
    comp = CUP_COMPETITIONS.get(code)
    return bool(comp and comp.competition_type == "national_team_cup")


def is_club_cup_competition(code: str) -> bool:
    comp = CUP_COMPETITIONS.get(code)
    return bool(comp and comp.competition_type == "club_cup")


def competition_type_of(code: str) -> CompetitionType:
    """Return the competition's type. Unknown codes fall through to 'league'.

    The fall-through is intentional — pre-W11 callers pass canonical
    league codes like 'EPL' which were never in this registry. Returning
    'league' keeps them working unchanged.
    """
    comp = CUP_COMPETITIONS.get(code)
    return comp.competition_type if comp else "league"


def competition_type_id(code: str) -> int:
    """Numeric encoding used as a GBM categorical feature.

    0 = league, 1 = club_cup, 2 = national_team_cup.
    """
    ct = competition_type_of(code)
    return {"league": 0, "club_cup": 1, "national_team_cup": 2}[ct]


def has_two_legged_format(code: str) -> bool:
    """True if the competition format allows home-and-away ties."""
    comp = CUP_COMPETITIONS.get(code)
    return bool(comp and comp.has_two_legged_ties)


def is_knockout_round(round_label: str | None) -> bool:
    """Heuristic on API-Football's `fixture.league.round` string.

    Group-stage rounds look like "Group A - Matchday 3" or
    "Regular Season - 12"; knockout rounds contain one of
    ``_KNOCKOUT_ROUND_TOKENS``. Returns False for None / empty / NaN /
    any non-str type (pandas often hands us NaN-as-float when a column
    is missing).
    """
    if not isinstance(round_label, str):
        return False
    if not round_label:
        return False
    rl = round_label.lower()
    return any(tok in rl for tok in _KNOCKOUT_ROUND_TOKENS)


def cup_codes() -> list[str]:
    """Return all registered cup codes (sorted, stable)."""
    return sorted(CUP_COMPETITIONS.keys())


def api_football_id_for_cup(code: str) -> int | None:
    """Return API-Football's numeric league ID for the cup, or None."""
    comp = CUP_COMPETITIONS.get(code)
    return comp.api_football_id if comp else None


__all__ = [
    "CompetitionType",
    "Competition",
    "CUP_COMPETITIONS",
    "is_cup_competition",
    "is_national_team_competition",
    "is_club_cup_competition",
    "competition_type_of",
    "competition_type_id",
    "has_two_legged_format",
    "is_knockout_round",
    "cup_codes",
    "api_football_id_for_cup",
]
