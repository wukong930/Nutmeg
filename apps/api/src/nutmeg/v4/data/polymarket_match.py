"""Match Polymarket soccer GAME events to our API-Football fixtures.

Polymarket-first (maximizes scope): we enumerate every Polymarket soccer game
event, parse it into a (teams, date, moneyline outcomes) shape, then match the
team pair to an API-Football fixture on that date — so the detector covers
whatever Polymarket lists, not just our 13/22 modelled leagues.

The matching is DELIBERATELY conservative (the whole detector is worthless if it
mis-joins a women's/youth game onto a men's fixture):
- women / youth events are dropped up-front via the event ``seriesSlug``/title
  (the market QUESTION carries no gender marker — "Will Sweden win?" — only the
  series does, e.g. "uefa-womens-world-cup-qualification").
- both teams must resolve to the SAME fixture's two sides (fuzzy ≥ 0.86), else
  the event is skipped (no guess).

Network is injected (``fetch_fixtures_for_date``) so this module is unit-testable
with fixture/event literals and never hits the API in tests.
"""
from __future__ import annotations

import datetime as dt
import difflib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

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

# outcome_spec values the matcher emits (moneyline). OVER/UNDER may be added
# later from the over/under prop markets.
HOME_WIN = "HOME_WIN"
AWAY_WIN = "AWAY_WIN"
DRAW = "DRAW"

# Substrings (lower-cased) in an event's seriesSlug / title / slug that mark a
# women's or youth competition → exclude (men's-team name collision risk).
_EXCLUDE_MARKERS = (
    "women", "womens", "female", "feminine", "ladies", "girls",
    "u15", "u16", "u17", "u18", "u19", "u20", "u21", "u23",
    "youth", "junior", "-w-", " w ", "(w)",
)


@dataclass(frozen=True)
class MatchedMarket:
    outcome_spec: str          # HOME_WIN | AWAY_WIN | DRAW
    yes_token: str             # CLOB token whose YES resolves true on this outcome
    poly_question: str


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
    """'Sierra Leone vs. Liberia' → ('Sierra Leone','Liberia').

    Returns None for prop events whose title carries a ' - <prop>' suffix
    (e.g. 'A vs. B - Exact Score') — those aren't the moneyline event.
    """
    t = (title or "").strip()
    if " - " in t:  # prop event (Exact Score / Halftime Result / ...)
        return None
    for sep in (" vs. ", " vs ", " v. ", " @ "):
        if sep in t:
            a, b = t.split(sep, 1)
            a, b = a.strip(), b.strip()
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


@dataclass(frozen=True)
class ParsedEvent:
    team_a: str
    team_b: str
    match_date: str
    kickoff_utc: str | None
    series_slug: str
    event_slug: str
    # outcome label (team name or "DRAW") → (yes_token, question)
    outcomes: dict[str, tuple[str, str]]


def parse_event(event: dict) -> ParsedEvent | None:
    """Parse a Polymarket soccer game event into teams + moneyline outcomes.

    Returns None if it's not a clean moneyline event (prop-only, no teams, no
    date, or no Win/Draw markets). Does NOT apply the women/youth gate — call
    ``is_excluded_event`` first.
    """
    teams = _split_title(event.get("title") or "")
    if teams is None:
        return None
    team_a, team_b = teams
    iso_date, kickoff = _kickoff_date(event)
    if not iso_date:
        return None

    outcomes: dict[str, tuple[str, str]] = {}
    for m in event.get("markets") or []:
        if not m.get("gameStartTime"):
            continue
        toks = m.get("clobTokenIds") or []
        if not toks:
            continue
        yes_token = str(toks[0])  # outcomes == ["Yes","No"] → token[0] is YES
        git = (m.get("groupItemTitle") or "").strip()
        q = (m.get("question") or "").lower()
        if "end in a draw" in q or git.lower().startswith("draw"):
            outcomes["DRAW"] = (yes_token, m.get("question") or "")
        elif ("win on" in q or " win" in q) and git:
            # groupItemTitle is the team name for a "Will <team> win?" market
            outcomes[git] = (yes_token, m.get("question") or "")
        # else: prop (exact score / halftime / over-under) → ignore for now
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
    return None


def match_to_fixture(parsed: ParsedEvent, fixtures: list[dict]) -> MatchedGame | None:
    """Match the parsed event's team pair to one fixture; map outcomes to the
    fixture's home/away. Conservative: both teams must resolve to the SAME
    fixture's two DISTINCT sides (core-exact or fuzzy ≥ 0.86), else None."""
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
        markets: list[MatchedMarket] = []
        for label, (yes_token, question) in parsed.outcomes.items():
            if label == "DRAW":
                spec = DRAW
            elif _core(label) == _core(parsed.team_a):
                spec = HOME_WIN if side_a == "home" else AWAY_WIN
            elif _core(label) == _core(parsed.team_b):
                spec = HOME_WIN if side_b == "home" else AWAY_WIN
            else:
                continue
            markets.append(MatchedMarket(spec, yes_token, question))
        if not markets:
            return None
        conf = min(ra[2], rb[2])
        method = "exact" if conf >= 0.999 else "fuzzy"
        return MatchedGame(
            fixture_id=int(row["fixture_id"]), league=row["league"],
            home_team=row["home"], away_team=row["away"],
            match_date=parsed.match_date, kickoff_utc=parsed.kickoff_utc,
            series_slug=parsed.series_slug, event_slug=parsed.event_slug,
            match_method=method, match_confidence=conf, markets=markets,
        )
    return None


def collect_matched_games(
    events: list[dict],
    fetch_fixtures_for_date: Callable[[dt.date], list[dict]],
    *,
    report_unmatched: bool = False,
) -> tuple[list[MatchedGame], list[dict]]:
    """Top-level: parse + exclude + match every event. Groups by date so the
    day's fixtures are fetched once. Returns (matched_games, unmatched_audit).

    ``fetch_fixtures_for_date(date) -> list[fixture]`` is injected (defaults to
    API-Football in the CLI). Unmatched/excluded events are collected for the
    ``--report-unmatched`` audit so we can grow coverage, never silently.
    """
    # Group events by kickoff date (skip excluded / unparseable up-front).
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
    return matched, unmatched


__all__ = [
    "HOME_WIN", "AWAY_WIN", "DRAW",
    "MatchedMarket", "MatchedGame", "ParsedEvent",
    "is_excluded_event", "parse_event", "match_to_fixture", "collect_matched_games",
]
