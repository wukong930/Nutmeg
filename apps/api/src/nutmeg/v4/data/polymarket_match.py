"""Match Polymarket soccer GAME events to our API-Football fixtures.

Polymarket-first (maximizes scope): we enumerate every Polymarket soccer game
event, parse it into a (teams, date, outcomes) shape, then match the team pair
to an API-Football fixture on that date — so the detector covers whatever
Polymarket lists, not just our 13/22 modelled leagues.

Outcomes parsed per match (each match's markets are split across SEPARATE
Polymarket events — a base "A vs. B" moneyline event + a "A vs. B - More Markets"
event carrying the spread ladder + full-match O/U; we parse both and MERGE by
fixture):
- moneyline  HOME_WIN / AWAY_WIN / DRAW           ("Will X win on …?" / "…draw?")
- 让球       HANDICAP_HOME / HANDICAP_AWAY + line  ("Spread: X (-1.5)", 2-way half-line)
- 大小球     OVER / UNDER + line                   ("A vs. B: O/U 2.5", full-match total)
Team totals / corners / half markets are deliberately IGNORED.

The matching is DELIBERATELY conservative (the whole detector is worthless if it
mis-joins a women's/youth game onto a men's fixture):
- women / youth events are dropped up-front via the event ``seriesSlug``/title.
- both teams must resolve to the SAME fixture's two sides (fuzzy ≥ 0.86), else
  the event is skipped (no guess).

Network is injected (``fetch_fixtures_for_date``) so this module is unit-testable
with fixture/event literals and never hits the API in tests.
"""
from __future__ import annotations

import datetime as dt
import difflib
from functools import lru_cache
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from nutmeg.utils.team_canonical import normalize_name

log = logging.getLogger(__name__)

# Club-type tokens stripped to a "core" name before matching, so Polymarket's
# "Iwaki FC" / "FC Imabari" match API-Football's "Iwaki" / "Imabari" (the bare
# "FC" suffix otherwise drops the fuzzy ratio below 0.86 and the game is lost).
# Conservative set — only unambiguous club abbreviations; the both-teams-must-
# map-to-distinct-sides guard prevents over-merging.
_CLUB_TOKENS = frozenset({
    "fc", "cf", "sc", "ac", "afc", "fk", "sk", "cd", "ca", "bk", "sv",
    "vfb", "vfl", "nk", "hnk", "ks", "gks", "ud", "sd", "cp", "ec", "rc", "rcd",
})
_MATCH_FUZZY = 0.86
#: 前缀包含命中的置信度。低于 exact(1.0)、高于模糊闸,便于事后按 `match_confidence` 分层审计。
_CONTAIN_CONF = 0.95
#: 别名命中的置信度(第四级,最低)。分层是为了能**按方法审计**:
#: `SELECT match_method, COUNT(*) FROM polymarket_gaps GROUP BY 1`。
_ALIAS_CONF = 0.90
#: 出现在「多出来的 token」里就**拒绝**前缀包含 —— 预备队/青年队/女队。
#: 🚨 没有它,`swansea city` 会前缀命中 AF 的 `swansea city u21`(一队配自家 U21)。
#: 注意与 `_EXCLUDE_MARKERS` 的分工:那个查 **Poly 事件**的 series/title,
#: 这个查 **AF fixture** 队名多出来的词 —— 两侧都要挡,只挡一侧照样错配。
_RESERVE_TOKENS = frozenset({
    "u15", "u16", "u17", "u18", "u19", "u20", "u21", "u23",
    "b", "ii", "iii", "2", "reserves", "reserve", "youth", "junior",
    "w", "women", "womens", "ladies", "academy", "dev", "development",
})


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

# outcome_spec values the matcher emits.
HOME_WIN = "HOME_WIN"
AWAY_WIN = "AWAY_WIN"
DRAW = "DRAW"
HANDICAP_HOME = "HANDICAP_HOME"   # home covers `line` (e.g. line=-1.5 ⇒ home wins by ≥2)
HANDICAP_AWAY = "HANDICAP_AWAY"   # away covers `line`
OVER = "OVER"                     # total goals over `line`
UNDER = "UNDER"                   # total goals under `line`

# "Spread: Portugal (-1.5)" → team="Portugal", line=-1.5 (2-way half-line market).
_SPREAD_RE = re.compile(r"^Spread:\s*(?P<team>.+?)\s*\(\s*(?P<line>[-+]?\d+(?:\.\d+)?)\s*\)\s*$")
# Full-match total: the part after "<A> vs. <B>: " is EXACTLY "O/U <line>"
# (excludes team totals "… : Portugal O/U 2.5" and corners "… O/U 2.5 Corners").
_OU_FULL_RE = re.compile(r"^O/U\s+(?P<line>\d+(?:\.\d+)?)$")

# Substrings (lower-cased) in an event's seriesSlug / title / slug that mark a
# women's or youth competition → exclude (men's-team name collision risk).
_EXCLUDE_MARKERS = (
    "women", "womens", "female", "feminine", "ladies", "girls",
    "u15", "u16", "u17", "u18", "u19", "u20", "u21", "u23",
    "youth", "junior", "-w-", " w ", "(w)",
)


@dataclass(frozen=True)
class MatchedMarket:
    outcome_spec: str          # HOME_WIN|AWAY_WIN|DRAW|HANDICAP_HOME|HANDICAP_AWAY|OVER|UNDER
    yes_token: str             # CLOB token whose YES resolves true on this outcome
    poly_question: str
    line: float | None = None  # handicap / O-U line (None for moneyline)


@dataclass(frozen=True)
class MatchedGame:
    fixture_id: int
    league: str
    home_team: str             # API-Football fixture home (the REAL home)
    away_team: str
    match_date: str            # ISO date (UTC) of kickoff
    kickoff_utc: str | None
    series_slug: str
    event_slug: str
    match_method: str          # "exact" | "fuzzy"
    match_confidence: float
    markets: list[MatchedMarket] = field(default_factory=list)


def is_excluded_event(event: dict) -> str | None:
    """Return an exclusion reason (women/youth) or None. Checked BEFORE matching."""
    blob = " ".join(
        str(event.get(k) or "") for k in ("seriesSlug", "title", "slug")
    ).lower()
    for mk in _EXCLUDE_MARKERS:
        if mk in blob:
            return f"excluded_series:{mk.strip('- ()')}"
    return None


def _split_title(title: str) -> tuple[str, str] | None:
    """'Portugal vs. Croatia' → ('Portugal','Croatia'); also strips a prop suffix
    so 'Portugal vs. Croatia - More Markets' → ('Portugal','Croatia') (the spread
    + O/U markets live under that suffixed event). Team A is before the separator
    so never carries the suffix; team B has any ' - <suffix>' trimmed."""
    t = (title or "").strip()
    for sep in (" vs. ", " vs ", " v. ", " @ "):
        if sep in t:
            a, b = t.split(sep, 1)
            a = a.strip()
            b = b.split(" - ", 1)[0].strip()  # trim prop suffix ("- More Markets" …)
            if a and b:
                return a, b
    return None


def _kickoff_date(event: dict) -> tuple[str | None, str | None]:
    """(iso_date, raw_kickoff) from the first game market's gameStartTime."""
    for m in event.get("markets") or []:
        gs = m.get("gameStartTime")
        if gs:
            return str(gs)[:10], str(gs)
    return None, None


def _full_match_ou_line(question: str) -> float | None:
    """Return the O/U line iff ``question`` is a FULL-MATCH total (not a team
    total / corners / half). e.g. 'A vs. B: O/U 2.5' → 2.5; 'A vs. B: B O/U 2.5'
    → None; 'A vs. B: B O/U 2.5 Corners' → None."""
    parts = question.split(": ", 1)
    if len(parts) != 2:
        return None
    m = _OU_FULL_RE.match(parts[1].strip())
    return float(m.group("line")) if m else None


@dataclass(frozen=True)
class ParsedEvent:
    team_a: str
    team_b: str
    match_date: str
    kickoff_utc: str | None
    series_slug: str
    event_slug: str
    # outcome label → (yes_token, question). Labels are the team name / "DRAW"
    # for moneyline, or ENCODED for props: "HCAP::<team>::<line>" (team covers
    # line), "OU::OVER::<line>" / "OU::UNDER::<line>". Decoded in match_to_fixture.
    outcomes: dict[str, tuple[str, str]]


def parse_event(event: dict) -> ParsedEvent | None:
    """Parse a Polymarket soccer game event → teams + outcomes (moneyline from the
    base event; 让球 + full-match O/U from the '- More Markets' event).

    Returns None if no teams / no date / no recognised markets. Does NOT apply the
    women/youth gate — call ``is_excluded_event`` first.
    """
    title = event.get("title") or ""
    teams = _split_title(title)
    if teams is None:
        return None
    team_a, team_b = teams
    iso_date, kickoff = _kickoff_date(event)
    if not iso_date:
        return None
    # Moneyline win/draw markets only exist on the BASE event (no " - " suffix);
    # gating on that stops a prop market like "X to win the second half?" from
    # being mistaken for the match-winner.
    is_base = " - " not in title

    outcomes: dict[str, tuple[str, str]] = {}
    for m in event.get("markets") or []:
        if not m.get("gameStartTime"):
            continue
        toks = m.get("clobTokenIds") or []
        if not toks:
            continue
        q_raw = m.get("question") or ""
        q = q_raw.lower()
        git = (m.get("groupItemTitle") or "").strip()
        t0 = str(toks[0])  # outcomes[0]'s YES token
        if is_base and ("end in a draw" in q or git.lower().startswith("draw")):
            outcomes["DRAW"] = (t0, q_raw)
        elif is_base and (("win on" in q or " win" in q) and git):
            outcomes[git] = (t0, q_raw)  # groupItemTitle is the team name
        elif (sm := _SPREAD_RE.match(q_raw)) is not None and len(toks) >= 2:
            # 2-way half-line: outcomes[0]=named team covers `line`; outcomes[1]=
            # other team covers the opposite (+|line|). Capture BOTH tradeable sides.
            team = sm.group("team").strip()
            line = float(sm.group("line"))
            others = m.get("outcomes") or []
            outcomes[f"HCAP::{team}::{line}"] = (t0, q_raw)
            if len(others) >= 2:
                outcomes[f"HCAP::{str(others[1]).strip()}::{-line}"] = (str(toks[1]), q_raw)
        elif (ou := _full_match_ou_line(q_raw)) is not None and len(toks) >= 2:
            outcomes[f"OU::OVER::{ou}"] = (t0, q_raw)          # outcomes[0]=Over
            outcomes[f"OU::UNDER::{ou}"] = (str(toks[1]), q_raw)  # outcomes[1]=Under
        # else: exact score / halftime / team-total / corners → ignore
    if not outcomes:
        return None
    return ParsedEvent(
        team_a=team_a, team_b=team_b, match_date=iso_date, kickoff_utc=kickoff,
        series_slug=str(event.get("seriesSlug") or ""),
        event_slug=str(event.get("slug") or ""),
        outcomes=outcomes,
    )


def _fixture_rows(fixtures: list[dict]) -> list[dict]:
    rows = []
    for fx in fixtures:
        teams = fx.get("teams") or {}
        hn = (teams.get("home") or {}).get("name")
        an = (teams.get("away") or {}).get("name")
        if not (hn and an):
            continue
        rows.append({
            "fixture_id": (fx.get("fixture") or {}).get("id"),
            "home": hn, "away": an,
            "league": (fx.get("league") or {}).get("name") or "",
            "kickoff": (fx.get("fixture") or {}).get("date"),
        })
    return rows


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


def match_to_fixture(parsed: ParsedEvent, fixtures: list[dict]) -> MatchedGame | None:
    """Match the parsed event's team pair to one fixture; map outcomes to the
    fixture's home/away. Conservative: both teams must resolve to the SAME
    fixture's two DISTINCT sides (core-exact / fuzzy ≥ 0.86 / 前缀包含), else None.

    🚨 **唯一性闸(2026-09-01)**：原来是「**第一个**两队都 resolve 的 fixture 就返回」。
    在只有 exact+fuzzy 的年代还算安全，加了前缀包含之后就不是了 —— 一个更宽的判据
    配上「取第一个」= 静默地挑一个碰巧排在前面的 fixture。现在**收集全部候选，
    多于一个一律拒**。宁可缺，不可错（错映射是静默污染，比缺映射更坏）。
    """
    cands: list[MatchedGame] = []
    for row in _fixture_rows(fixtures):
        cores = {
            _core(row["home"]): ("home", row["home"]),
            _core(row["away"]): ("away", row["away"]),
        }
        if len(cores) < 2:  # both fixture teams share a core → degenerate, skip
            continue
        ra = _resolve(parsed.team_a, cores)
        rb = _resolve(parsed.team_b, cores)
        if ra is None or rb is None or ra[0] == rb[0]:
            continue  # a team unmatched, or both mapped to the same side → reject

        side_a, side_b = ra[0], rb[0]

        def _team_side(name: str) -> str | None:
            if _core(name) == _core(parsed.team_a):
                return side_a
            if _core(name) == _core(parsed.team_b):
                return side_b
            r = _resolve(name, cores)
            return r[0] if r else None

        markets: list[MatchedMarket] = []
        for label, (yes_token, question) in parsed.outcomes.items():
            if label == "DRAW":
                markets.append(MatchedMarket(DRAW, yes_token, question))
            elif label.startswith("HCAP::"):
                _, team, line_s = label.split("::", 2)
                side = _team_side(team)
                if side is None:
                    continue
                spec = HANDICAP_HOME if side == "home" else HANDICAP_AWAY
                markets.append(MatchedMarket(spec, yes_token, question, line=float(line_s)))
            elif label.startswith("OU::"):
                _, ou, line_s = label.split("::", 2)
                markets.append(MatchedMarket(
                    OVER if ou == "OVER" else UNDER, yes_token, question, line=float(line_s)))
            else:  # team name → moneyline
                side = _team_side(label)
                if side is None:
                    continue
                markets.append(MatchedMarket(
                    HOME_WIN if side == "home" else AWAY_WIN, yes_token, question))
        if not markets:
            continue
        conf = min(ra[2], rb[2])
        method = ("exact" if conf >= 0.999
                  else "prefix" if conf == _CONTAIN_CONF
                  else "alias" if conf == _ALIAS_CONF else "fuzzy")
        cands.append(MatchedGame(
            fixture_id=int(row["fixture_id"]), league=row["league"],
            home_team=row["home"], away_team=row["away"],
            match_date=parsed.match_date, kickoff_utc=parsed.kickoff_utc,
            series_slug=parsed.series_slug, event_slug=parsed.event_slug,
            match_method=method, match_confidence=conf, markets=markets,
        ))
    if len(cands) > 1:
        log.warning("polymarket-match: %s 同时匹配到 %d 个 fixture(%s)"
                    " —— **拒绝**，宁可缺不可错",
                    parsed.event_slug, len(cands),
                    ", ".join(str(c.fixture_id) for c in cands))
    return cands[0] if len(cands) == 1 else None


def _merge_by_fixture(games: list[MatchedGame]) -> list[MatchedGame]:
    """A match's moneyline + '- More Markets' events resolve to the SAME fixture
    as two MatchedGames; union their markets into one. Dedup markets by
    (outcome_spec, line, yes_token) keeping the first."""
    merged: dict[int, MatchedGame] = {}
    for g in games:
        if g.fixture_id not in merged:
            merged[g.fixture_id] = g
            continue
        ex = merged[g.fixture_id]
        seen = {(m.outcome_spec, m.line, m.yes_token) for m in ex.markets}
        extra = [m for m in g.markets
                 if (m.outcome_spec, m.line, m.yes_token) not in seen]
        merged[g.fixture_id] = replace(
            ex, markets=ex.markets + extra,
            series_slug=ex.series_slug or g.series_slug,
            kickoff_utc=ex.kickoff_utc or g.kickoff_utc,
        )
    return list(merged.values())


def collect_matched_games(
    events: list[dict],
    fetch_fixtures_for_date: Callable[[dt.date], list[dict]],
    *,
    report_unmatched: bool = False,
) -> tuple[list[MatchedGame], list[dict]]:
    """Top-level: parse + exclude + match every event, then merge same-fixture
    events (moneyline + more-markets). Groups by date so the day's fixtures are
    fetched once. Returns (matched_games, unmatched_audit).

    ``fetch_fixtures_for_date(date) -> list[fixture]`` is injected (defaults to
    API-Football in the CLI). Unmatched/excluded events are collected for the
    ``--report-unmatched`` audit so we can grow coverage, never silently.
    """
    by_date: dict[str, list[ParsedEvent]] = {}
    unmatched: list[dict] = []
    for ev in events:
        reason = is_excluded_event(ev)
        if reason:
            if report_unmatched:
                unmatched.append({"slug": ev.get("slug"), "reason": reason})
            continue
        parsed = parse_event(ev)
        if parsed is None:
            if report_unmatched:
                unmatched.append({"slug": ev.get("slug"), "reason": "unparseable_or_prop"})
            continue
        by_date.setdefault(parsed.match_date, []).append(parsed)

    matched: list[MatchedGame] = []
    fixtures_cache: dict[str, list[dict]] = {}
    for date_str, parsed_list in sorted(by_date.items()):
        try:
            d = dt.date.fromisoformat(date_str)
        except ValueError:
            continue
        if date_str not in fixtures_cache:
            try:
                fixtures_cache[date_str] = fetch_fixtures_for_date(d)
            except Exception as exc:  # noqa: BLE001
                log.warning("polymarket-match: fixtures fetch failed for %s: %s", date_str, exc)
                fixtures_cache[date_str] = []
        fixtures = fixtures_cache[date_str]
        for parsed in parsed_list:
            mg = match_to_fixture(parsed, fixtures)
            if mg is None:
                if report_unmatched:
                    unmatched.append({
                        "slug": parsed.event_slug,
                        "reason": "no_fixture",
                        "teams": f"{parsed.team_a} vs {parsed.team_b}",
                        "date": parsed.match_date,
                    })
                continue
            matched.append(mg)
    return _merge_by_fixture(matched), unmatched


__all__ = [
    "HOME_WIN", "AWAY_WIN", "DRAW",
    "HANDICAP_HOME", "HANDICAP_AWAY", "OVER", "UNDER",
    "MatchedMarket", "MatchedGame", "ParsedEvent",
    "is_excluded_event", "parse_event", "match_to_fixture", "collect_matched_games",
]
