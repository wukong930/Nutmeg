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

import re
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
    """One competition entry in the registry.

    `has_knockouts` and `has_group_stage` are INDEPENDENT, and the pair
    is what `is_knockout_fixture` dispatches on:

    - (True, False) → pure knockout cup (FAC, DFB_POKAL): every round is
      a knockout tie, so no round-label parsing is needed
    - (True, True) → group/league phase then knockouts (UCL, WC): the
      round label is the only thing that can tell the two apart
    - (False, True) → round-robin only (WC_QUAL_UEFA): never a knockout

    `has_group_stage` deliberately has no default — both candidate
    defaults are silently wrong for half the registry, so a new entry
    has to state it.
    """

    code: str                       # canonical V4 code (e.g. "UCL")
    display_zh: str                 # Chinese display name
    display_en: str                 # English display name
    competition_type: CompetitionType
    api_football_id: int | None     # None when not surfaced via API-Football
    has_knockouts: bool             # True if format includes knockout rounds
    has_group_stage: bool           # True if format has a non-knockout phase
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
        has_group_stage=True,   # group stage → 2024/25 Swiss "League Stage"
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
        has_group_stage=True,
        has_two_legged_ties=True,
    ),
    "UECL": Competition(
        code="UECL",
        display_zh="欧会杯 (UEFA 欧洲协会联赛)",
        display_en="UEFA Europa Conference League",
        competition_type="club_cup",
        api_football_id=848,
        has_knockouts=True,
        has_group_stage=True,
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
        has_group_stage=False,  # single-elimination from the qualifying rounds up
        has_two_legged_ties=False,  # FA Cup is single-leg with replays
        notes="Includes lower-division teams not in EPL/Championship train set",
    ),
    # ── 英格兰社区盾(2026-08-16 注册)──────────────────────────────────
    # ⚠️ `api_football_id=528` 是**从缓存实证**的,不是查表猜的:
    #    AF 缓存里含 "Shield" 的联赛有 **3 个**(528 England / 534 CONCACAF
    #    Caribbean Club Shield / 971 Kenya Shield Cup)⇒ **按名字匹配会撞车**。
    #    钉死它的是那场比赛本身:`2026-08-16T14:00Z Arsenal vs Manchester City
    #    · round=Final`,与竞彩记录(北京 22:00)逐字对上。
    # ⚠️ 三个格式布尔**实测**自同一份缓存(season=2026):
    #    轮次分布只有 `Final` × 1 ⇒ 无小组阶段;单场 ⇒ 非两回合。
    #    ⭐ 样本只有缓存里有的季 —— 结论强度以此为限,但社区盾是「上季联赛冠军 vs
    #      足总杯冠军」的**单场**赛制,与实测一致。
    "COMMUNITY_SHIELD": Competition(
        code="COMMUNITY_SHIELD",
        display_zh="社区盾 (英格兰)",
        display_en="FA Community Shield",
        competition_type="club_cup",
        api_football_id=528,
        has_knockouts=True,
        has_group_stage=False,
        has_two_legged_ties=False,
        notes=(
            "单场决赛(上季英超冠军 vs 足总杯冠军)。竞彩缩写「英社区盾」。"
            "⚠️ **不**进 CALENDAR_YEAR_LEAGUES:实测 season_for_date(2026-08-16) = 2026,"
            "与 AF 缓存标的 season 逐字一致(拉错季会静默返回 0 场)。同荷乙/沙职的判法。"
        ),
    ),
    "EFL_CUP": Competition(
        code="EFL_CUP",
        display_zh="联赛杯 (英格兰)",
        display_en="EFL Cup (Carabao Cup)",
        competition_type="club_cup",
        api_football_id=48,
        has_knockouts=True,
        # 纯淘汰赛,**实测**:season=2025 全 93 场的轮次只有 Preliminary Round /
        # 1st–4th Round / Quarter-finals / Semi-finals / Final —— 没有任何小组
        # 阶段标签。⇒ `is_knockout_fixture` 对它每一轮都返回 True,不碰字符串。
        has_group_stage=False,
        # ⚠️ 这个 True 是**实测**的,不是「我记得半决赛打两回合」:同一次拉取里
        # `Semi-finals` 的 Man City–Newcastle 与 Arsenal–Chelsea 各出现 2 次
        # ⇒ 两回合。其余轮次单场。(2026-08-05)
        has_two_legged_ties=True,
        notes=(
            "英联赛杯。竞彩写作「英联赛杯」。全部 92 家 EFL 俱乐部参赛 ⇒ 大量队伍不在"
            "训练集里,只走市场模式(Pinnacle de-vig)。⚠️ AF 的 `League Cup` 这个名字"
            "苏格兰(185)/埃及(895)/泰国(898) 都有,认 id=48 + country=England。"
        ),
    ),
    # ── 韩国杯 KOR_FA_CUP(2026-08-18 注册)────────────────────────────────
    # ⚠️ api_football_id=294 是 **live 核过 + 该场比赛钉死**的,不是查表猜:
    #    AF `/leagues?search=korea` 里 type=Cup · country=South-Korea **唯一**命中
    #    id=294「FA Cup」;再用比赛本身钉死 —— season=2026 的 55 场里有
    #    `2026-08-19T10:30Z FC Anyang vs Jeju United FC · Round of 16`,与竞彩
    #    「韩国杯」记录逐字对上(同 社区盾 用「那场比赛」钉 id 的做法)。
    # ⚠️ 三个格式布尔**实测**自 season=2026 全 55 场:轮次只有 1/128-finals /
    #    Round of 128/64/32/16 等淘汰轮、无任何小组标签 ⇒ 无小组阶段;同一对阵在
    #    一轮里只出现 1 次 ⇒ 非两回合。
    # ⚠️ Odds API **无**韩国杯 sport(`/v4/sports?all=true` 175 个全表 live 核过,
    #    韩国只有 `soccer_korea_kleague1`)⇒ sport-key 单元会 warn,同 JPN_J2/荷乙/欧超杯。
    #    观测到的 FC Anyang/Jeju United 已在 KOR_K_LEAGUE_1 段的 zh 字典里;杯赛含
    #    K2/K3/业余队,registry_coverage 会按 AF 全表报若干未映射(预期 warn,非硬缺口)。
    "KOR_FA_CUP": Competition(
        code="KOR_FA_CUP",
        display_zh="韩国杯 (韩国足总杯)",
        display_en="FA Cup (South Korea)",
        competition_type="club_cup",
        api_football_id=294,          # live: "FA Cup" (Cup/South-Korea), 2026-08-19 Anyang×Jeju 钉死
        has_knockouts=True,
        has_group_stage=False,        # 实测:55 场全淘汰轮,无小组
        has_two_legged_ties=False,    # 实测:无重复对阵 ⇒ 单场
        notes=(
            "竞彩写作「韩国杯」。AF id=294 由 2026-08-19 FC Anyang vs Jeju United "
            "(Round of 16) 钉死。韩国足球日历年制(2–11 月)⇒ **必须**进 "
            "CALENDAR_YEAR_LEAGUES(同 KOR_K_LEAGUE_1=292),否则年初的轮次按欧洲惯例算成 "
            "season−1,AF 返 0 场。Odds API 无此 sport(175 全表核)⇒ 只有 AF 一路线;"
            "含 K2/K3 等下级队,竞彩上架这些队时需照官方写法补 team_name_zh(⛔ 别猜译名)。"
        ),
    ),
    # 补(2026-09-01 owner 点名)。AF id=101 由**本地缓存**钉死,不是搜名字:
    # fixture 1567425 `2026-09-02T09:30 · Japan · J-League Cup · season=2026 ·
    # Vanraure Hachinohe vs Tochigi City (Round of 128)`。
    # ⚠️ 撞车:AF 全表叫「*League Cup*」的有 14 个(英 48 / 冰 168 / 苏 185 / 阿联酋 302
    #   / 爱尔兰 360 / 新加坡 505 …)—— **按名字匹配会 13 路撞车**,只有 id 101 是
    #   J-League Cup + Japan。日本另有 `102 Emperor Cup`(天皇杯)与 `548 Super Cup`,别混。
    "JPN_LEAGUE_CUP": Competition(
        code="JPN_LEAGUE_CUP",
        display_zh="日联赛杯 (J联赛杯)",
        display_en="J-League Cup",
        competition_type="club_cup",
        api_football_id=101,          # 本地缓存 fixture 1567425 钉死(见上)
        has_knockouts=True,
        # 实测(竞彩档案 **123 个 match_id** / 2021-2025,按赛季内统计):
        # 同一对阵重复 **29 组**,分布 {1 次: 65, 2 次: 29} ⇒ 两回合成立。
        # 🚨 这个数我错过**两次**,值得留着当反面教材:
        #   ① 跨 5 个赛季数得「80/84 组重复」—— 每季碰一次也会重复,说明不了两回合;
        #   ② 分赛季重算得「90 组」—— 仍然错:我按 `(match_id, 日期)` 去重,而**赔率
        #      跨午夜更新的比赛会占两个日期** ⇒ 同一场被数成两场。正确写法是
        #      `GROUP BY match_id`。改对后 90 → 29,结论不变但数字差 3 倍。
        #      (发现它是因为天皇杯量出「7 组重复」而单场淘汰赛不该有 —— 一查
        #       每组的 match_id 都相同。**是那个不合理的结果把前一个错误也带了出来**。)
        has_two_legged_ties=True,
        # ⚠️ **未测出**。改对计数后最大只有 ×2,而 ×2 与「两回合淘汰」和「主客场小组赛」
        #   **都相容** ⇒ 分不出来。本字段全仓**零消费者**,置 False 是默认值**不是结论**。
        #   (我上一版写 True,理由是「×3 只能由小组赛解释」—— 那个 ×3 是上面那个
        #    午夜假象造出来的,证据不存在。)
        has_group_stage=False,
        notes=(
            "竞彩写作「日联赛杯」(档案 `jingcai_odds_history.league_cn` 123 场 / "
            "`crown_close_history` 27 场 / `jingcai_vote` 用全称「日本联赛杯」)。"
            "月份分布 2–11 月、12/1 月为零 ⇒ **日历年制**,必须进 CALENDAR_YEAR_LEAGUES。"
            "Odds API 无此 sport(全仓只有 `soccer_japan_j_league` 一个日本 key)⇒ "
            "只走 AF 的 Pinnacle 镜像。⚠️ 本地 `_odds` 缓存里 league=101 **零行** —— "
            "但我们从没注册过它、也就从没去要过它的赔率,所以那个 0 **是构造性的**,"
            "不能当成「Pinnacle 不覆盖」的证据。上线后按本联赛**自己数一遍**。"
        ),
    ),
    # 补(2026-09-01 owner 点名,紧接日联赛杯)。AF id=102,**全表唯一**:
    # 本地 leagues catalog 里叫 "Emperor Cup" 的只有 `102 / Cup / Japan` 一条
    # (对比日联赛杯要在 14 个撞名的 "*League Cup*" 里挑,这个不用挑)。
    # 缓存实证:2026-08-19(24 场)+ 2026-08-26(32 场),season=2026。
    "JPN_EMPEROR_CUP": Competition(
        code="JPN_EMPEROR_CUP",
        display_zh="日天皇杯 (天皇杯)",
        display_en="Emperor Cup",
        competition_type="club_cup",
        api_football_id=102,
        has_knockouts=True,
        # 实测(竞彩档案 **66 个 match_id** / 2021-2025):赛季内同一对阵重复
        # **0 组** ⇒ 纯单场淘汰。与日联赛杯(29 组)形成干净对照。
        has_two_legged_ties=False,
        has_group_stage=False,        # 单场淘汰 + 0 重复 ⇒ 无小组赛
        notes=(
            "竞彩写作「日天皇杯」(`jingcai_odds_history` 66 场);⚠️ 皇冠档案写的是"
            "**「天皇杯」**(7 场)—— 两种写法都实证过,已把后者进 `_CN_SYNONYM`。"
            "月份分布 5–12 月、1–4 月为零 ⇒ **日历年制**(与日联赛杯的 2–11 月不同,"
            "但同样在一个日历年内)。Odds API 无此 sport ⇒ 只走 AF Pinnacle 镜像;"
            "⭐ 与日联赛杯不同,本地 `_odds` 缓存里 league=102 **有 5 场、其中 4 场带 "
            "Pinnacle** —— 这是注册前就有的独立证据,不是构造性的 0。"
        ),
    ),
    # ── 2026-08-09 owner 点名新增三个:解放者杯 / 欧超杯 / 沙职 ────────────
    # ⚠️ 三个 AF id 全部 **live 核过**(`/leagues?search=`),不是凭印象:
    # 「Super Cup」一个词搜出 **59 条**(德/土/埃/意/比/智/捷/沙都有),
    # 认 UEFA 那个必须看 id=531 + country=World。猜名字在这里必错。
    "COPA_LIBERTADORES": Competition(
        code="COPA_LIBERTADORES",
        display_zh="解放者杯 (南美)",
        display_en="CONMEBOL Copa Libertadores",
        competition_type="club_cup",
        api_football_id=13,          # live: "CONMEBOL Libertadores" (Cup/World)
        has_knockouts=True,
        has_group_stage=True,
        has_two_legged_ties=True,    # 淘汰赛两回合(决赛单场)
        notes=(
            "竞彩写作「解放者杯」(league_id=49),长档案 124 场 / 2021-08→2026-05。"
            "2-11 月跑完一个日历年 ⇒ **必须**进 CALENDAR_YEAR_LEAGUES,"
            "否则 3 月的比赛按欧洲惯例算成 season=去年,AF 返回 0 场。"
            "数据覆盖(2026-08-09 实测):Odds API `soccer_conmebol_copa_libertadores` "
            "active=True;AF 未来 21 天 16 场,首场 fixture 1547760 有 14 家含 Pinnacle。"
            "⚠️ 南美球队队名词典缺 46 个,补完前竞彩 SP 挂不上(只在参考区可见)。"
        ),
    ),
    "UEFA_SUPER_CUP": Competition(
        code="UEFA_SUPER_CUP",
        display_zh="欧超杯 (UEFA 超级杯)",
        display_en="UEFA Super Cup",
        competition_type="club_cup",
        api_football_id=531,         # live: "UEFA Super Cup" (Cup/World) —— 59 个同名里的这一个
        has_knockouts=True,
        has_group_stage=False,
        has_two_legged_ties=False,   # 单场决胜
        notes=(
            "⚠️ **一年只有一场**。竞彩长档案 5 年里只出现 2 次(2021-08-12 / 2025-08-14),"
            "所以任何按它做的统计都会是 N≈1 —— 别对它的样本量有幻想。"
            "⛔ Odds API **没有**这个 sport(2026-08-09 live 核 175 个 sport 全表)"
            "⇒ 只能走 AF 镜像。这次我核的是**那场比赛本身**:2026 那场 "
            "(fixture 1583664, PSG vs Aston Villa, 08-12 19:00Z)有 13 家含 Pinnacle。"
            "⭐ 不要把这条读成「缺 key ⇒ AF 兜底」的又一个例证 —— 那**不是规则**"
            "(日乙同样缺 key 而 AF 也空),要断言覆盖就去数那个联赛自己的行。"
        ),
    ),
    "COPA_DEL_REY": Competition(
        code="COPA_DEL_REY",
        display_zh="国王杯 (西班牙)",
        display_en="Copa del Rey (Spain)",
        competition_type="club_cup",
        api_football_id=143,
        has_knockouts=True,
        has_group_stage=False,
        has_two_legged_ties=False,
    ),
    "COPPA_ITALIA": Competition(
        code="COPPA_ITALIA",
        display_zh="意大利杯",
        display_en="Coppa Italia",
        competition_type="club_cup",
        api_football_id=137,
        has_knockouts=True,
        has_group_stage=False,
        has_two_legged_ties=True,
    ),
    "DFB_POKAL": Competition(
        code="DFB_POKAL",
        display_zh="德国杯",
        display_en="DFB-Pokal",
        competition_type="club_cup",
        api_football_id=81,
        has_knockouts=True,
        has_group_stage=False,
        has_two_legged_ties=False,
    ),
    "COUPE_DE_FRANCE": Competition(
        code="COUPE_DE_FRANCE",
        display_zh="法国杯",
        display_en="Coupe de France",
        competition_type="club_cup",
        api_football_id=66,
        has_knockouts=True,
        has_group_stage=False,
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
        has_group_stage=True,
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
        has_group_stage=True,   # incl. round-robin "Qualifying Round - N"
        has_two_legged_ties=False,
    ),
    "COPA_AMERICA": Competition(
        code="COPA_AMERICA",
        display_zh="美洲杯",
        display_en="CONMEBOL Copa America",
        competition_type="national_team_cup",
        api_football_id=9,
        has_knockouts=True,
        has_group_stage=True,
        has_two_legged_ties=False,
    ),
    "WC_QUAL_UEFA": Competition(
        code="WC_QUAL_UEFA",
        display_zh="世界杯欧洲区预选赛",
        display_en="World Cup Qualification (UEFA)",
        competition_type="national_team_cup",
        api_football_id=32,
        has_knockouts=False,  # round-robin groups
        has_group_stage=True,
        has_two_legged_ties=False,
    ),
}


# Knockout round labels API-Football emits in `fixture.league.round`.
# Used by `is_knockout_round(label)` to flag a fixture as knockout vs
# group-stage. Matches both English ("Round of 16") and abbreviations.
_KNOCKOUT_ROUND_TOKENS = (
    "round of",       # "Round of 16", "Round of 32", "Round of 128"
    "1st knockout",   # API-Football's 1st knockout round label
    "knockout",
    "quarter-final",
    "quarter-finals",
    "quarter final",
    "semi-final",
    "semi-finals",
    "semi final",
    "final",          # matches "Final", "3rd Place Final", "8th Finals"
    "play-off",
    "playoff",
)

# Named-stage tokens above only cover the LATE rounds. English cups number
# their early rounds instead ("1st Round" … "4th Round", "Preliminary
# Round"), and UEFA numbers its qualifiers ("1st Qualifying Round") — all
# single-elimination, none of them containing a token above. These two
# patterns catch that family.
_KNOCKOUT_ROUND_PATTERNS = (
    # "1st Round", "4th Round", "1st Qualifying Round", "5th Round Proper"
    re.compile(r"\b\d+(?:st|nd|rd|th)\b.*\bround\b"),
    # "Preliminary Round", "Preliminary round"
    re.compile(r"\bpreliminary\b.*\bround\b"),
)

# API-Football suffixes every repeated-matchday phase with " - <N>":
# "Group A - 1", "Group Stage - 3", "League Stage - 8", "Regular Season -
# 12" — and, the trap this guard exists for, EURO's round-robin
# "Qualifying Round - 1" … "- 10" (250 rows in our own parquets). A
# knockout TIE never carries that suffix. The guard is scoped to
# _KNOCKOUT_ROUND_PATTERNS only, so it can never flip a label that the
# named-stage tokens already resolve to True.
_MATCHDAY_SUFFIX_RE = re.compile(r"-\s*\d+\s*$")


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
    """Label-only heuristic on API-Football's `fixture.league.round`.

    Prefer `is_knockout_fixture(code, label)` — for a pure-knockout cup
    the competition itself is the answer and no string needs parsing.
    This function is what that one falls back to for mixed-format
    competitions (UCL/WC/EURO), where the round label really is the only
    thing separating a group match from a knockout tie.

    Group-stage rounds look like "Group A - Matchday 3" or
    "Regular Season - 12"; knockout rounds either contain one of
    ``_KNOCKOUT_ROUND_TOKENS`` or match ``_KNOCKOUT_ROUND_PATTERNS``
    without a matchday suffix. Returns False for None / empty / NaN /
    any non-str type (pandas often hands us NaN-as-float when a column
    is missing).
    """
    if not isinstance(round_label, str):
        return False
    if not round_label:
        return False
    rl = round_label.lower()
    if any(tok in rl for tok in _KNOCKOUT_ROUND_TOKENS):
        return True
    if _MATCHDAY_SUFFIX_RE.search(rl):
        return False
    return any(pat.search(rl) for pat in _KNOCKOUT_ROUND_PATTERNS)


def is_knockout_fixture(competition_code: str, round_label: str | None = None) -> bool:
    """Is this fixture a knockout tie? Competition first, label second.

    Three-way dispatch on the registry, so the string heuristic only runs
    where it is actually load-bearing:

    - not a registered cup (league codes, unknown codes) → False
    - cup with no knockout phase (WC_QUAL_UEFA) → False
    - pure-knockout cup (FAC / EFL / COPA_DEL_REY / DFB_POKAL …) → True
      for EVERY round, including a missing label. "1st Round" of the FA
      Cup is as much a knockout as the final; the old label-only path
      called those group matches.
    - mixed group-then-knockout cup (UCL / UEL / WC / EURO) → defer to
      `is_knockout_round`, the only case where the label decides.
    """
    comp = CUP_COMPETITIONS.get(competition_code)
    if comp is None or not comp.has_knockouts:
        return False
    if not comp.has_group_stage:
        return True
    return is_knockout_round(round_label)


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
    "is_knockout_fixture",
    "cup_codes",
    "api_football_id_for_cup",
]
