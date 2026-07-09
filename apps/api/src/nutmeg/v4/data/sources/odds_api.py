"""The Odds API adapter — post-v9 P1#20.

Paid subscription ($30/mo Starter tier, 20K requests/month). The
purpose-built fix for V8 W4's blocker: API-Football `/odds` is
upcoming-only, so 4 seasons of UCL/UEL closing odds had to come from
somewhere else. The Odds API has historical depth from mid-2020,
covering all of our target seasons.

Credentials live in `.env` (gitignored) at `NUTMEG_ODDS_API_KEY`.
The key is passed as a `?apiKey=...` query param (not a header).

Two endpoints used:

  /v4/sports/<sport_key>/odds/                   — current upcoming odds
  /v4/historical/sports/<sport_key>/odds/        — historical snapshots
                                                   (each call costs 10
                                                   quota units)

Sport keys for our needs:
  soccer_uefa_champs_league                — UCL
  soccer_uefa_europa_league                — UEL (off-season Jun-Aug)
  soccer_uefa_europa_conference_league     — UECL (optional)

Cache strategy mirrors api_football.py: each fetch_* writes a JSON to
data/external/odds_api/<endpoint>/<params-hash>.json so repeated runs
don't burn quota. `refresh=True` bypasses cache.

Quota math (Starter tier 20K/month):
  Historical call = 10 quota each
  UCL: ~20 matchday-snapshots × 4 seasons = ~80 calls × 10 = 800 quota
  UEL: ~25 matchday-snapshots × 4 seasons = ~100 calls × 10 = 1,000 quota
  Backfill total: ~180 calls = ~1,800 quota (9% of monthly budget)
  Daily forward: ~30 calls = ~300 quota (1.5%)

Response shape (current):
  [
    {
      "id": "fa66c5...", "sport_key": "soccer_uefa_champs_league",
      "commence_time": "2026-05-30T16:00:00Z",
      "home_team": "Paris Saint Germain", "away_team": "Arsenal",
      "bookmakers": [
        {"key": "marathonbet", "title": "Marathon Bet", ...,
         "markets": [
           {"key": "h2h", "last_update": "...",
            "outcomes": [
              {"name": "Arsenal", "price": 3.32},
              {"name": "Paris Saint Germain", "price": 2.34},
              {"name": "Draw", "price": 3.32}
            ]}
         ]}
      ]
    },
    ...
  ]

Response shape (historical) — wraps the same list in an envelope:
  {
    "timestamp": "2024-09-17T19:55:40Z",
    "previous_timestamp": "...", "next_timestamp": "...",
    "data": [<same fixture objects as current endpoint>]
  }
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from nutmeg.config import get_settings


log = logging.getLogger(__name__)
# Security(体检 2026-06-10): httpx logs the FULL request URL at INFO, and our
# Odds API key rides in the query string (?apiKey=…). A caller setting root
# logging to INFO (e.g. the ingest cron) would otherwise write the key into log
# files — silence httpx's request logging so the key never lands on disk.
logging.getLogger("httpx").setLevel(logging.WARNING)

DEFAULT_CACHE_DIR = Path("data/external/odds_api")

# 体检 F3 — a historical-snapshot request for a FUTURE timestamp returns the
# "latest available" line (not a fixed point), so its cache must expire; a past
# snapshot is immutable and caches forever. 6h keeps the WC-upcoming blend fresh.
_HISTORICAL_FUTURE_TTL_SECONDS = 6 * 3600

# Sport key mapping: V4 canonical cup code → Odds API sport key.
# Extend here when adding more competitions.
SPORT_KEYS: dict[str, str] = {
    # Cup / international (P1#20)
    "UCL":  "soccer_uefa_champs_league",
    "UEL":  "soccer_uefa_europa_league",
    "UECL": "soccer_uefa_europa_conference_league",
    "WC":   "soccer_fifa_world_cup",
    "EURO": "soccer_uefa_european_championship",
    # Top-5 European domestic leagues (P1#21 cross-source backtest)
    "EPL":            "soccer_epl",
    "ESP_LA_LIGA":    "soccer_spain_la_liga",
    "ITA_SERIE_A":    "soccer_italy_serie_a",
    "GER_BUNDESLIGA": "soccer_germany_bundesliga",
    "FRA_LIGUE_1":    "soccer_france_ligue_one",
    # 体检(2026-06-10)— in-season market-mode leagues confirmed live on The
    # Odds API /sports; used by the _gather_rows fresher-line overlay.
    "NOR_ELITESERIEN":   "soccer_norway_eliteserien",
    "SWE_ALLSVENSKAN":   "soccer_sweden_allsvenskan",
    "FIN_VEIKKAUSLIIGA": "soccer_finland_veikkausliiga",
    # 体检(2026-07-03)— 韩职 cards stayed on the stale AF mirror because the
    # league had NO sport key at all (the club-core fix only helps leagues that
    # HAVE a lookup). Probed /sports live: kleague1 active=True; j_league key
    # exists but active=False between rounds — fail-soft (fetch error → empty
    # lookup → AF fallback) until it self-activates. J1 is a trained league.
    "KOR_K_LEAGUE_1": "soccer_korea_kleague1",
    "JPN_J1":         "soccer_japan_j_league",
    # 体检 Wave2 (2026-07-04) — the daily-cron trained-league set was missing 8
    # of its 13 keys, so the fresher-line overlay NEVER ran for them (the 韩职
    # bug's batch siblings). All 8 probed live on /sports 2026-07-04; most show
    # active=False between seasons (same as j_league) — fetch fail-soft until
    # they self-activate in August.
    "ENG_CHAMPIONSHIP":     "soccer_efl_champ",
    "ESP_SEGUNDA_DIVISION": "soccer_spain_segunda_division",
    "ITA_SERIE_B":          "soccer_italy_serie_b",
    "GER_2_BUNDESLIGA":     "soccer_germany_bundesliga2",
    "FRA_LIGUE_2":          "soccer_france_ligue_two",
    "NED_EREDIVISIE":       "soccer_netherlands_eredivisie",
    "PRT_PRIMEIRA_LIGA":    "soccer_portugal_primeira_liga",
    "BEL_PRO_LEAGUE":       "soccer_belgium_first_div",
    # Add more as needed: FA Cup, Copa del Rey etc.
}


def build_psc_lookup_for_date_range(
    sport_key: str,
    start_date: str,   # YYYY-MM-DD
    end_date: str,     # YYYY-MM-DD
    *,
    snapshot_hour_utc: int = 23,
    refresh: bool = False,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    strict_bookmaker: str | None = None,
) -> dict[tuple[str, str, str], dict[str, float]]:
    """post-v9 P1#21: build a {(date, home, away) → psc_*} lookup by
    walking historical snapshots over a date range.

    Used by roi_backtest --odds-source odds_api to substitute Odds API
    closing odds for the football-data.co.uk Pinnacle closing odds the
    backtest defaults to.

    One snapshot per day at `snapshot_hour_utc` UTC. Each snapshot
    returns ALL fixtures around that time across the sport, so the
    quota cost is 10 × n_days, not 10 × n_fixtures.

    Pass ``strict_bookmaker="pinnacle"`` to skip fixtures where Pinnacle
    closing odds aren't available — required for apples-to-apples cross-
    source comparison with football-data.co.uk PSC (which is also
    Pinnacle CL). Without strict mode, the function silently falls back
    to softer books (marathonbet/unibet/etc.), inflating implied ROI.

    Returns dict keyed by (commence_date, home_team, away_team) where
    home/away are the Odds API spellings (caller may need alias mapping).
    """
    from datetime import date as _date, timedelta

    out: dict[tuple[str, str, str], dict[str, float]] = {}
    cur = _date.fromisoformat(start_date)
    end = _date.fromisoformat(end_date)
    while cur <= end:
        snap_iso = f"{cur.isoformat()}T{snapshot_hour_utc:02d}:00:00Z"
        try:
            envelope = fetch_historical_snapshot(
                sport_key, snap_iso, refresh=refresh, cache_dir=cache_dir,
            )
        except OddsApiError as e:
            # Off-season days return empty snapshots; just skip
            log.debug("no snapshot %s: %s", snap_iso, e)
            cur += timedelta(days=1)
            continue
        for fx in envelope.get("data", []):
            parsed = parse_fixture_to_h2h(fx, strict_key=strict_bookmaker)
            if not parsed:
                continue
            key = (
                parsed["commence_time"][:10],
                parsed["home_team"],
                parsed["away_team"],
            )
            # First write wins (snapshot is taken AFTER match — closing
            # state); duplicate keys across snapshots get same odds since
            # one fixture commences once.
            out.setdefault(key, {
                "psc_home": parsed["psc_home"],
                "psc_draw": parsed["psc_draw"],
                "psc_away": parsed["psc_away"],
                "bookmaker": parsed.get("bookmaker"),
            })
        cur += timedelta(days=1)
    return out


# Pinnacle isn't always in The Odds API's free regions; the Sharp-book
# proxy we prefer when Pinnacle is unavailable. Order = priority.
PREFERRED_BOOKMAKERS: tuple[str, ...] = (
    "pinnacle",          # gold standard
    "betfair_ex_uk",     # exchange = real traded prices
    "betfair_ex_eu",
    "marathonbet",       # often listed as sharp on EU markets
    "unibet_eu",
    "betclic_fr",
    "pmu_fr",
    "williamhill",
)


class OddsApiError(RuntimeError):
    """Raised on non-2xx, missing key, or parse failure."""


# Process-wide persistent client (keep-alive) — same rationale as
# api_football._client: skip the per-call TLS+TCP handshake.
_CLIENT_LOCK = threading.Lock()
_CLIENT: httpx.Client | None = None
_CLIENT_FOR: tuple[str, float] | None = None  # (base_url, timeout)


def _client() -> httpx.Client:
    global _CLIENT, _CLIENT_FOR
    settings = get_settings()
    if not settings.odds_api_key:
        raise OddsApiError(
            "NUTMEG_ODDS_API_KEY is not set. Add it to .env or env vars."
        )
    want = (settings.odds_api_base_url, settings.odds_api_timeout_seconds)
    with _CLIENT_LOCK:
        if _CLIENT is None or _CLIENT.is_closed or want != _CLIENT_FOR:
            if _CLIENT is not None and not _CLIENT.is_closed:
                _CLIENT.close()
            _CLIENT = httpx.Client(base_url=want[0], timeout=want[1])
            _CLIENT_FOR = want
        return _CLIENT


def _cache_path(endpoint: str, params: dict[str, Any], cache_dir: Path) -> Path:
    """One JSON per (endpoint, params). API key is excluded from the
    hash so cache survives key rotation."""
    redacted = {k: v for k, v in params.items() if k != "apiKey"}
    payload = json.dumps(redacted, sort_keys=True, default=str).encode()
    h = hashlib.sha1(payload).hexdigest()[:12]
    safe_endpoint = endpoint.strip("/").replace("/", "_")
    return cache_dir / safe_endpoint / f"{h}.json"


def _request(
    endpoint: str,
    params: dict[str, Any],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
    ttl_seconds: float | None = None,
) -> Any:
    """Make one Odds API request; cache by (endpoint, params).

    Returns the JSON-decoded body as-is. Historical endpoints return
    a dict envelope; current odds return a list. Callers handle both.

    ``ttl_seconds`` (live odds) — a cached file OLDER than this counts as a
    miss, so passive page loads reuse a recent pull but never serve a day-old
    line. ``refresh=True`` always refetches regardless of TTL.
    """
    settings = get_settings()
    cache_dir = Path(cache_dir)
    cf = _cache_path(endpoint, params, cache_dir)
    cf.parent.mkdir(parents=True, exist_ok=True)
    fresh_enough = True
    if ttl_seconds is not None and cf.exists():
        fresh_enough = (time.time() - cf.stat().st_mtime) <= ttl_seconds
    if cf.exists() and not refresh and fresh_enough:
        log.debug("cache hit %s", cf)
        try:
            return json.loads(cf.read_text())
        except (json.JSONDecodeError, OSError):
            # 体检 Wave3 (P2) — a half-written/corrupt cache used to crash the
            # caller FOREVER (the bad file never healed). Fall through to a
            # live fetch, whose atomic rewrite below replaces it.
            log.warning("corrupt cache %s — refetching", cf)

    # Attach key at request time; don't cache it
    full_params = {**params, "apiKey": settings.odds_api_key}
    r = _client().get(endpoint, params=full_params)
    if r.status_code != 200:
        # Surface API error code if present for easier debugging
        try:
            err_body = r.json()
            err_code = err_body.get("error_code", "")
            err_msg = err_body.get("message", r.text[:200])
            raise OddsApiError(
                f"{endpoint} HTTP {r.status_code} [{err_code}]: {err_msg}"
            )
        except (ValueError, KeyError):
            raise OddsApiError(f"{endpoint} HTTP {r.status_code}: {r.text[:200]}")

    body = r.json()
    # 体检 Wave3 (P2) — atomic write (tmp + rename): a crash/power-cut mid-write
    # used to leave a truncated JSON that poisoned every later cache read.
    _tmp = cf.with_name(f"{cf.name}.{os.getpid()}.tmp")
    _tmp.write_text(json.dumps(body, separators=(",", ":")))
    _tmp.replace(cf)
    # Log quota state
    quota_remaining = r.headers.get("x-requests-remaining", "?")
    last_cost = r.headers.get("x-requests-last", "?")
    log.info("✓ %s  cost=%s  remaining=%s", endpoint, last_cost, quota_remaining)
    return body


# ----- Current odds (cheap, 1 quota per call) ----------------------------

def fetch_current_odds(
    sport_key: str,
    *,
    regions: str = "eu",
    markets: str = "h2h",
    odds_format: str = "decimal",
    refresh: bool = False,
    ttl_seconds: float | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[dict[str, Any]]:
    """Fetch all UPCOMING fixtures with odds for one sport_key.

    `regions` is a comma-separated subset of {us, us2, uk, eu, au}.
    `markets` is comma-separated: h2h (=1X2) / spreads / totals / outrights.
    Default 'eu' + 'h2h' matches what we need for cup_odds backfill.
    """
    endpoint = f"sports/{sport_key}/odds"
    params = {"regions": regions, "markets": markets, "oddsFormat": odds_format}
    body = _request(endpoint, params, cache_dir=cache_dir, refresh=refresh,
                    ttl_seconds=ttl_seconds)
    if not isinstance(body, list):
        raise OddsApiError(f"unexpected response shape: {type(body).__name__}")
    return body


# API-Football and the Odds API spell a few teams differently enough that the
# accent-fold/alnum key still diverges (different word, order, or extra token),
# so the fresher-line overlay silently misses them → the card stays on the stale
# API-Football line. Collapse the known pairs to one canonical key. Measured WC
# pairs (体检 2026-06-12); extend via the same per-fixture overlay-miss diff.
_NORM_ALIAS: dict[str, str] = {
    # National teams (WC)
    "turkiye": "turkey",                # AF Türkiye  ↔ OA Turkey
    "capeverdeislands": "capeverde",    # AF Cape Verde Islands ↔ OA Cape Verde
    "congodr": "drcongo",               # AF Congo DR ↔ OA DR Congo
    "czechia": "czechrepublic",         # AF Czechia ↔ OA Czech Republic (捷克vs南非 overlay miss)
    # Veikkausliiga (FIN) — AF drops the FC/IFK/IF prefix or the city suffix the
    # Odds API keeps. AF key → OA key (体检 2026-06-12, the live overlay misses).
    "interturku": "fcinterturku",       # Inter Turku ↔ FC Inter Turku
    "ilves": "ilvestampere",            # Ilves ↔ Ilves Tampere
    "turkups": "tpsturku",              # Turku PS ↔ TPS Turku
    "ffjaro": "jaro",                   # FF Jaro ↔ Jaro
    "vps": "vpsvaasa",                  # VPS ↔ VPS Vaasa
    "kups": "kupskuopio",               # KuPS ↔ KuPS Kuopio
    "lahti": "fclahti",                 # Lahti ↔ FC Lahti
    "sjk": "sjkseinajoki",              # SJK ↔ SJK Seinäjoki
    "mariehamn": "ifkmariehamn",        # Mariehamn ↔ IFK Mariehamn
    "gnistan": "ifgnistan",             # Gnistan ↔ IF Gnistan
    # Allsvenskan (SWE) — Swedish GENITIVE: AF Halmstad ↔ OA Halmstads BK.
    # Morphology, so the club-core token-strip can't bridge it
    # ('halmstads' ≠ 'halmstad'); measured overlay miss 2026-07-03.
    "halmstad": "halmstadsbk",
    # K League 1 (KOR) — measured overlay misses 2026-07-03 (live kleague1 pull):
    # brand middle-token + a 2021 relocation the Odds API never renamed. Neither
    # is a legal-form token, so the club-core strip can't bridge them.
    "jeonbukmotors": "jeonbukhyundaimotors",   # AF Jeonbuk Motors ↔ OA Jeonbuk Hyundai Motors
    "gimcheonsangmufc": "sangjusangmufc",      # AF Gimcheon Sangmu FC ↔ OA Sangju Sangmu FC (旧名)
    # EPL — our canonical / 竞彩 zh_to_canonical uses the SHORT club name; the Odds
    # API keeps the FULL official name. Measured §H 竞彩↔Pinnacle join miss
    # 2026-07-09 (14/57 → these 7 were the entire gap). our short → OA long.
    "wolves": "wolverhamptonwanderers",        # Wolves ↔ Wolverhampton Wanderers
    "tottenham": "tottenhamhotspur",           # Tottenham ↔ Tottenham Hotspur
    "leicester": "leicestercity",              # Leicester ↔ Leicester City
    "ipswich": "ipswichtown",                  # Ipswich ↔ Ipswich Town
    "newcastle": "newcastleunited",            # Newcastle ↔ Newcastle United
    "westham": "westhamunited",                # West Ham ↔ West Ham United
    "brighton": "brightonandhovealbion",       # Brighton ↔ Brighton and Hove Albion
    # Eredivisie (NED) — 竞彩 canonical vs OA FC/city-suffix form. Measured §H
    # 竞彩↔Pinnacle join miss 2026-07-09. our → OA.
    "almerecityfc": "almerecity",              # Almere City FC ↔ Almere City
    "twente": "fctwenteenschede",              # Twente ↔ FC Twente Enschede
    "utrecht": "fcutrecht",                     # Utrecht ↔ FC Utrecht
    "peczwolle": "fczwolle",                    # PEC Zwolle ↔ FC Zwolle
    "heracles": "heraclesalmelo",              # Heracles ↔ Heracles Almelo
    # Primeira Liga (PRT) — 竞彩 short vs OA long/legal-form. (Sporting/AVS 竞彩
    # 无 canonical → 不别名,留 join 缺.)  our → OA.
    "boavista": "boavistaporto",               # Boavista ↔ Boavista Porto
    "scbraga": "braga",                        # SC Braga ↔ Braga
    "estrela": "cfestrela",                     # Estrela ↔ CF Estrela
    "moreirense": "moreirensefc",              # Moreirense ↔ Moreirense FC
    "rioave": "rioavefc",                       # Rio Ave ↔ Rio Ave FC
    "farense": "scfarense",                     # Farense ↔ SC Farense
    "guimaraes": "vitoriasc",                   # Guimarães ↔ Vitória SC
}


def _norm_team(name: str | None) -> str:
    """Accent-fold + alnum-only identity key for cross-source team matching
    ('Bosnia & Herzegovina' / 'Bosnia and Herzegovina' → 'bosniaandherzegovina'),
    then collapse known AF↔OA spelling pairs via ``_NORM_ALIAS``."""
    s = unicodedata.normalize("NFKD", (name or "").replace("&", " and "))
    s = "".join(c for c in s if not unicodedata.combining(c))
    key = "".join(ch for ch in s.lower() if ch.isalnum())
    return _NORM_ALIAS.get(key, key)


# Club LEGAL-FORM tokens drift between AF and the Odds API for Nordic clubs —
# measured SWE 2026-07-03: AF 'Sirius'↔OA 'IK Sirius', 'Hammarby FF'↔'Hammarby
# IF', 'Vasteras SK FK'↔'Västerås SK' — three overlay misses in ONE slate, each
# leaving its card on the hours-stale AF mirror. Per-team _NORM_ALIAS entries
# can't keep up with the class, so the lookup ALSO indexes a secondary
# "club-core" key with these standalone tokens dropped. Safety: a core
# collision is poisoned to None (see fetch_pinnacle_lookup) so a wrong-team
# patch is structurally impossible; pure-abbreviation names (AIK, GAIS) keep
# their exact key untouched.
_CLUB_TOKENS = frozenset({"if", "ik", "bk", "ff", "sk", "fk", "aif", "fc", "afc"})


def _club_core(name: str | None) -> str | None:
    """Secondary team key: accent-folded words minus club legal-form tokens
    ('IK Sirius' → 'sirius'). None when nothing usable remains ('FF')."""
    s = unicodedata.normalize("NFKD", (name or "").replace("&", " and "))
    s = "".join(c if c.isalnum() else " "
                for c in s.lower() if not unicodedata.combining(c))
    return "".join(w for w in s.split() if w not in _CLUB_TOKENS) or None


def _extract_totals(bookmaker: dict[str, Any]) -> tuple[float, float, float] | None:
    """(line, over_price, under_price) from a bookmaker's totals market;
    prefer the line closest to 2.5 when several are present."""
    best: tuple[float, float, float] | None = None
    for m in bookmaker.get("markets", []):
        if m.get("key") != "totals":
            continue
        over = under = line = None
        for o in m.get("outcomes", []):
            nm, pt, pr = o.get("name"), o.get("point"), o.get("price")
            if pr is None or pt is None:
                continue
            if nm == "Over":
                over, line = float(pr), float(pt)
            elif nm == "Under":
                under = float(pr)
        if (over is not None and under is not None and line is not None
                and (best is None or abs(line - 2.5) < abs(best[0] - 2.5))):
            best = (line, over, under)
    return best


def fetch_pinnacle_lookup(
    sport_key: str,
    *,
    regions: str = "eu",
    refresh: bool = False,
    ttl_seconds: float | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """体检(2026-06-10)— fresh Pinnacle 1X2 + O/U for every UPCOMING fixture of
    one sport_key, keyed by (norm_home, norm_away, commence_date) for matching
    against API-Football.

    A measured head-to-head showed The Odds API's Pinnacle line is ~3h fresher
    than API-Football's mirror; this is the lookup the ``_gather_rows`` overlay
    patches in. Pinnacle-STRICT: fixtures without a Pinnacle h2h are skipped (we
    never silently substitute a softer book for the sharp prior). Each record::

        {"home_team","away_team",            # Odds API spellings (debug)
         "psc_home","psc_draw","psc_away",   # Pinnacle 1X2 (vig included)
         "ou_line","psc_over","psc_under",   # Pinnacle O/U (None if unquoted)
         "last_update"}                      # Pinnacle's own line timestamp
    """
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    secondary: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    events = fetch_current_odds(
        sport_key, regions=regions, markets="h2h,totals",
        refresh=refresh, ttl_seconds=ttl_seconds, cache_dir=cache_dir,
    )
    for e in events:
        home, away = e.get("home_team"), e.get("away_team")
        date = (e.get("commence_time") or "")[:10]
        if not home or not away or not date:
            continue
        pin = next((b for b in e.get("bookmakers", [])
                    if (b.get("key") or "").lower() == "pinnacle"), None)
        if not pin:
            continue
        h2h = _extract_h2h(pin)
        teams = (h2h or {}).get("teams", {})
        ph, pa = teams.get(home), teams.get(away)
        if h2h is None or ph is None or pa is None:
            continue  # name resolution failed → skip (caller keeps AF line)
        rec: dict[str, Any] = {
            "home_team": home, "away_team": away,
            "psc_home": ph, "psc_draw": h2h["draw"], "psc_away": pa,
            "ou_line": None, "psc_over": None, "psc_under": None,
            "last_update": pin.get("last_update"),
            # Scheduled kickoff — lets the closing-line capture skip already-started
            # matches, whose Pinnacle odds have flipped to LIVE (a leading team →
            # degenerate 1.06/53.96 line) and must not be recorded as a "close".
            "commence_time": e.get("commence_time"),
        }
        tot = _extract_totals(pin)
        if tot:
            rec["ou_line"], rec["psc_over"], rec["psc_under"] = tot
        exact = (_norm_team(home), _norm_team(away), date)
        out[exact] = rec
        # Secondary keys: cartesian of each side's {exact, club-core} so a
        # MIXED pair still matches — AF 'Halmstad' exact-aliases the home
        # (→halmstadsbk) while its away 'Vasteras SK FK' needs the core key.
        hks, ch = [exact[0]], _club_core(home)
        if ch and ch != exact[0]:
            hks.append(ch)
        aks, ca = [exact[1]], _club_core(away)
        if ca and ca != exact[1]:
            aks.append(ca)
        for hk in hks:
            for ak in aks:
                if (hk, ak, date) != exact:
                    secondary.setdefault((hk, ak, date), []).append(rec)
    # Merge club-core keys: an exact key always wins (never shadowed); a core
    # COLLISION is poisoned to None so the overlay can never patch the wrong
    # team's odds — it just falls back to the AF line (honest staleness badge).
    for skey, recs in secondary.items():
        if skey not in out:
            out[skey] = recs[0] if len(recs) == 1 else None  # type: ignore[assignment]
    return out


# ----- Historical snapshot (expensive, 10 quota per call) -----------------

def fetch_historical_snapshot(
    sport_key: str,
    snapshot_iso: str,
    *,
    regions: str = "eu",
    markets: str = "h2h",
    odds_format: str = "decimal",
    refresh: bool = False,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> dict[str, Any]:
    """Fetch one historical snapshot at the given ISO timestamp.

    `snapshot_iso` must be ISO 8601 UTC, e.g. "2024-09-17T20:00:00Z".
    The API returns the snapshot closest in time to the request (not
    necessarily exactly at the requested time) along with `previous_timestamp`
    and `next_timestamp` for walking the timeline.

    Returns the FULL envelope dict; caller reads .data, .timestamp etc.
    """
    endpoint = f"historical/sports/{sport_key}/odds"
    params = {
        "regions": regions, "markets": markets,
        "oddsFormat": odds_format, "date": snapshot_iso,
    }
    # 体检 F3 — a FUTURE snapshot timestamp (WC-upcoming requests {d}T23:00Z for a
    # day not yet reached) resolves to the "latest available" line, which keeps
    # changing as KO approaches; caching it permanently under the future key
    # serves a ~1d-stale line. Refresh a future-key cache older than the TTL;
    # PAST snapshots are immutable → cache forever. Force-refresh failure falls
    # back to the stale cache (never worse than the permanent cache).
    effective_refresh = refresh
    if not refresh:
        try:
            snap_dt = datetime.fromisoformat(snapshot_iso.replace("Z", "+00:00"))
            if snap_dt.tzinfo is None:
                snap_dt = snap_dt.replace(tzinfo=UTC)
            if snap_dt > datetime.now(UTC):
                cf = _cache_path(endpoint, params, Path(cache_dir))
                if cf.exists() and (
                        time.time() - cf.stat().st_mtime > _HISTORICAL_FUTURE_TTL_SECONDS):
                    effective_refresh = True
        except (ValueError, TypeError):
            pass
    try:
        body = _request(endpoint, params, cache_dir=cache_dir, refresh=effective_refresh)
    except OddsApiError:
        if effective_refresh and not refresh:
            body = _request(endpoint, params, cache_dir=cache_dir, refresh=False)
        else:
            raise
    if not isinstance(body, dict) or "data" not in body:
        raise OddsApiError(
            f"unexpected historical response shape; got keys: "
            f"{list(body.keys()) if isinstance(body, dict) else type(body).__name__}"
        )
    return body


# ----- Parsing: Odds API fixture → cup_odds row ---------------------------

def _select_bookmaker_h2h(
    bookmakers: list[dict[str, Any]],
    *,
    strict_key: str | None = None,
) -> tuple[str | None, dict[str, float] | None]:
    """Walk PREFERRED_BOOKMAKERS in order, return the first that has an
    h2h market. Returns (bookmaker_key, {H: price, D: price, A: price}).

    If ``strict_key`` is provided (e.g. "pinnacle"), ONLY that
    bookmaker is acceptable — return None if it's missing. This is
    used by cross-source backtests to ensure apples-to-apples Pinnacle
    CL pricing (otherwise softer-book fallback inflates ROI).

    Falls back to the first bookmaker in the list if no preferred match
    (only when strict_key is None).
    """
    by_key = {b.get("key", "").lower(): b for b in bookmakers}
    if strict_key:
        if strict_key in by_key:
            h2h = _extract_h2h(by_key[strict_key])
            return (strict_key, h2h) if h2h else (None, None)
        return None, None
    for pref in PREFERRED_BOOKMAKERS:
        if pref in by_key:
            book = by_key[pref]
            h2h = _extract_h2h(book)
            if h2h:
                return pref, h2h
    # Fallback: any bookmaker with h2h
    for book in bookmakers:
        h2h = _extract_h2h(book)
        if h2h:
            return book.get("key"), h2h
    return None, None


def _extract_h2h(bookmaker: dict[str, Any]) -> dict[str, float] | None:
    """Pull H/D/A from a bookmaker's markets list."""
    for m in bookmaker.get("markets", []):
        if m.get("key") != "h2h":
            continue
        out = {}
        # Use home_team / away_team to map outcomes — names can match
        # either spelling order; "Draw" is reliably "Draw"
        for o in m.get("outcomes", []):
            name = o.get("name", "")
            price = o.get("price")
            if not name or price is None:
                continue
            if name == "Draw":
                out["draw"] = float(price)
            else:
                # Caller knows the fixture's home/away pair; just collect
                # by name and resolve outside
                out.setdefault("teams", {})[name] = float(price)
        # Need both teams + draw
        if "draw" in out and "teams" in out and len(out["teams"]) == 2:
            return out
    return None


def parse_fixture_to_h2h(
    fixture: dict[str, Any],
    *,
    strict_key: str | None = None,
) -> dict[str, Any] | None:
    """Take one Odds API fixture object, return a normalized dict:

        {
          "commence_time": "2024-09-17T19:00:00Z",
          "home_team": "AC Milan",
          "away_team": "Liverpool",
          "bookmaker": "marathonbet",
          "psc_home": 17.0, "psc_draw": 5.7, "psc_away": 1.25,
        }

    Returns None if no usable h2h market across the bookmakers.

    Pass ``strict_key="pinnacle"`` to require Pinnacle Closing Line and
    skip fixtures where Pinnacle isn't quoted (used by cross-source
    backtest for apples-to-apples PSC comparison).
    """
    home = fixture.get("home_team")
    away = fixture.get("away_team")
    commence = fixture.get("commence_time")
    if not home or not away or not commence:
        return None
    bms = fixture.get("bookmakers", [])
    if not bms:
        return None

    bm_key, h2h = _select_bookmaker_h2h(bms, strict_key=strict_key)
    if not h2h:
        return None
    teams_prices = h2h["teams"]
    # Direct match
    if home in teams_prices and away in teams_prices:
        ph, pa = teams_prices[home], teams_prices[away]
    else:
        # Spelling mismatch between fixture-level and outcome-level
        # (some bookmakers use shortened/alternate names). The outcomes
        # come back in a stable order: typically [home, away, draw] or
        # [away, home, draw], so we can match by position. We pre-filtered
        # to exactly 2 teams + 1 draw in _extract_h2h, so 2 team prices
        # are unambiguously home/away — just need to figure out which is
        # which. Use string similarity as the tiebreaker.
        team_names = list(teams_prices.keys())
        if len(team_names) != 2:
            return None
        # Pick the closer match to "home" as home
        def _similarity(a: str, b: str) -> float:
            from difflib import SequenceMatcher
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()
        sim_home_to_0 = _similarity(home, team_names[0])
        sim_home_to_1 = _similarity(home, team_names[1])
        if sim_home_to_0 >= sim_home_to_1:
            ph, pa = teams_prices[team_names[0]], teams_prices[team_names[1]]
        else:
            ph, pa = teams_prices[team_names[1]], teams_prices[team_names[0]]
    return {
        "commence_time": commence,
        "home_team": home,
        "away_team": away,
        "bookmaker": bm_key,
        "psc_home": ph,
        "psc_draw": h2h["draw"],
        "psc_away": pa,
    }


__all__ = [
    "DEFAULT_CACHE_DIR",
    "SPORT_KEYS",
    "PREFERRED_BOOKMAKERS",
    "OddsApiError",
    "fetch_current_odds",
    "fetch_historical_snapshot",
    "parse_fixture_to_h2h",
    "build_psc_lookup_for_date_range",
]
