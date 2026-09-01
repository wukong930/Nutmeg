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
# ⭐ 跨源队名匹配已抽到 `data/team_match.py`(2026-09-01)——**一处定义**。
# 它解决的问题跟 Polymarket 无关(Odds API/Poly 用全称、AF 用短名),同一天在
# 多书商共识那边又踩了一次 ⇒ 复制第三份就是平行入口。这里按原名转发,行为不变。
from nutmeg.v4.data.team_match import (  # noqa: F401  (对外保持原有符号)
    _ALIAS_CONF,
    _alias_any,
    _CLUB_TOKENS,
    _CONTAIN_CONF,
    _core,
    _MATCH_FUZZY,
    _prefix_extra,
    _RESERVE_TOKENS,
    _resolve,
)

log = logging.getLogger(__name__)


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
