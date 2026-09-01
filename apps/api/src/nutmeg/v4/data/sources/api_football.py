"""API-Football adapter — V6 W1.

Paid subscription ($19/mo Pro plan, 7.5k requests/day). Provides:
- fixtures (with status, score, half-time score)
- lineups (starting XI + substitutes; available ~1 hour pre-kickoff)
- injuries (current squad injury list)
- odds (multi-book pre-match 1X2 / handicap / O/U; NOT 中国竞彩 SP)

The credential lives in `.env` (gitignored) at `NUTMEG_API_FOOTBALL_KEY`.
All requests carry it as the `x-apisports-key` header.

Rate budget at Pro plan:
    7,500 calls/day = ~5 calls/min sustained.
    Daily workload: 13 leagues × 10 fixtures × {fixtures, odds, lineups,
    injuries} = ~500 calls/day. Headroom 15x.

Cache strategy:
    Each fetch_* writes a per-call JSON to
    data/external/api_football/<endpoint>/<params-hash>.json
    so repeated debugging hits don't burn quota. `refresh=True` bypasses
    cache (used by the daily cron).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from nutmeg.config import get_settings

# Transient-failure retry. A single read timeout / reset connection shouldn't
# abort a whole cron run — the daily settle died on one httpx.ReadTimeout
# (2026-05-31) and left the UCL final unsettled. 3 attempts with linear backoff.
_MAX_REQUEST_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1.5
# A 429 (rate limit) is transient — back off and retry, honoring Retry-After
# but never sleeping longer than this (a misbehaving header shouldn't hang a
# request for minutes).
_RETRY_AFTER_CAP_SECONDS = 10.0


log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/external/api_football")

# Upcoming fixtures are still being scheduled/confirmed by API-Football, so a
# cached fixtures-by-date result for today-or-later can go stale: a not-yet-listed
# match appears days later, but our "permanent-until-refresh" cache keeps serving
# the old (often EMPTY) result forever. That silently dropped the whole World Cup
# from 近期赛事 (2026-07-01: an empty WC list cached before the fixtures were
# confirmed masked them). So for today-or-later dates we refetch a cache older
# than this TTL; past dates are settled and cache forever. 6h keeps the active
# betting window fresh while bounding refetch cost (~100 league×date combos ×
# 4/day ≪ the 7.5k/day quota).
_UPCOMING_FIXTURE_TTL_SECONDS = 6 * 3600

# Opt-in freshness bound for fetch_odds (default None = permanent-until-refresh,
# so the cup-odds backfill + score_ev keep their permanent cache). The GATHER
# passes it so an upcoming fixture's odds don't serve days-stale for the leagues
# with no fresh-Pinnacle overlay — 8 of 14 daily leagues get their psc straight
# from this AF-mirror cache (体检 F1, fires when they restart in August). Odds
# are the direct EV input, so 2h is tighter than the fixture-schedule TTL.
_ODDS_CACHE_TTL_SECONDS = 2 * 3600


class ApiFootballError(RuntimeError):
    """Raised when the API returns a non-2xx, an error payload, or no key is set."""


# Process-wide persistent client (keep-alive). A fresh httpx.Client per request
# re-paid a TLS+TCP handshake every call (~300ms each CN→EU, measured); reusing
# one connection pool removes that. httpx.Client is thread-safe for requests, so
# the concurrent odds fetch in ingest_odds._gather_rows can share it.
_CLIENT_LOCK = threading.Lock()
_CLIENT: httpx.Client | None = None
_CLIENT_FOR: tuple[str, str, float] | None = None  # (base_url, key, timeout)


def _client() -> httpx.Client:
    global _CLIENT, _CLIENT_FOR
    settings = get_settings()
    if not settings.api_football_key:
        raise ApiFootballError(
            "NUTMEG_API_FOOTBALL_KEY is not set. Add it to .env or env vars."
        )
    want = (
        settings.api_football_base_url,
        settings.api_football_key,
        settings.api_football_timeout_seconds,
    )
    with _CLIENT_LOCK:
        if _CLIENT is None or _CLIENT.is_closed or want != _CLIENT_FOR:
            if _CLIENT is not None and not _CLIENT.is_closed:
                _CLIENT.close()
            _CLIENT = httpx.Client(
                base_url=want[0],
                headers={"x-apisports-key": want[1]},
                timeout=want[2],
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
            _CLIENT_FOR = want
        return _CLIENT


def _body_says_rate_limited(resp: httpx.Response) -> bool:
    """API-Football 的每分钟限流:HTTP **200** + body ``errors.rateLimit``。

    只认 ``rateLimit`` 这个键 —— 别的 errors(bug/token/plan…)都不是暂时的,
    重试它们只是白烧配额。解析失败一律返回 False:**不确定就不重试**,
    否则一个格式变化会让每个请求都退避 3 次。
    """
    try:
        errs = resp.json().get("errors")
    except Exception:  # noqa: BLE001 — 非 JSON body 不是限流
        return False
    return isinstance(errs, dict) and "rateLimit" in errs


def _retry_after_seconds(resp: httpx.Response, attempt: int) -> float:
    """Back-off before retrying a 429: honor a numeric Retry-After, else the
    linear backoff, capped at ``_RETRY_AFTER_CAP_SECONDS``."""
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            return min(float(ra), _RETRY_AFTER_CAP_SECONDS)
        except (TypeError, ValueError):
            pass  # HTTP-date form — fall back to linear backoff
    return _RETRY_BACKOFF_SECONDS * (attempt + 1)


def _cache_path(endpoint: str, params: dict[str, Any], cache_dir: Path) -> Path:
    """One JSON per (endpoint, params)."""
    payload = json.dumps(params, sort_keys=True, default=str).encode()
    h = hashlib.sha1(payload).hexdigest()[:12]
    safe_endpoint = endpoint.replace("/", "_")
    return cache_dir / safe_endpoint / f"{h}.json"


def _request(
    endpoint: str,
    params: dict[str, Any],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Make one API-Football request; cache by (endpoint, params).

    The API returns a JSON envelope with shape:
        { "get": ..., "parameters": ..., "errors": ..., "results": N,
          "response": [...] }

    We return ``response`` (the array of records) and raise if ``errors``
    is non-empty.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = _cache_path(endpoint, params, cache_dir)
    cf.parent.mkdir(parents=True, exist_ok=True)
    if cf.exists() and not refresh:
        try:
            return json.loads(cf.read_text())
        except (json.JSONDecodeError, OSError):
            # 体检 Wave3 (P2) — a half-written/corrupt cache used to crash the
            # caller FOREVER (the bad file never healed). Fall through to a
            # live fetch, whose atomic rewrite below replaces it.
            log.warning("corrupt cache %s — refetching", cf)

    # Retry transient network failures (read timeout / connection reset);
    # non-network errors (bad status, auth) fall through to raise immediately.
    last_exc: Exception | None = None
    r = None
    for attempt in range(_MAX_REQUEST_ATTEMPTS):
        try:
            r = _client().get(endpoint, params=params)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            r = None
            if attempt + 1 < _MAX_REQUEST_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue
        # 429 (rate limit) IS transient — the concurrent odds fetch can briefly
        # exceed API-Football's per-second cap. Back off (Retry-After) and retry
        # so a burst slows down instead of dropping the fixture. A 500/other 4xx
        # is NOT transient → break and raise below.
        if r.status_code == 429 and attempt + 1 < _MAX_REQUEST_ATTEMPTS:
            time.sleep(_retry_after_seconds(r, attempt))
            continue
        # ⭐ 2026-08-07 — API-Football 的**每分钟**限流不是 429,是
        # **HTTP 200 + body `errors: {"rateLimit": "Too many requests…"}`**。
        # 上面那条 429 分支对它完全失明 ⇒ 直接落到下面的 `errs` 检查 raise 掉。
        # 实测代价(logs/launchd/com.nutmeg.api_server.err.log,2026-08-07):
        # 一次手动刷新丢了 12 场、35 秒后另一次又丢 3 场,共 15 场 —— 每一场都
        # 变成 psc=None ⇒ 掉进「待开盘」⇒ **恰好在要下注那一刻从可投注区消失**。
        # 它和 429 同族(都是「慢一点再来」),所以用同一套退避重试。
        if (r.status_code == 200 and attempt + 1 < _MAX_REQUEST_ATTEMPTS
                and _body_says_rate_limited(r)):
            log.warning("%s hit AF per-minute rate limit (HTTP 200 + errors.rateLimit)"
                        " — backing off, attempt %d/%d",
                        endpoint, attempt + 1, _MAX_REQUEST_ATTEMPTS)
            time.sleep(_retry_after_seconds(r, attempt))
            continue
        break
    if r is None:
        raise ApiFootballError(
            f"{endpoint} network error after {_MAX_REQUEST_ATTEMPTS} attempts: "
            f"{last_exc!r}"
        ) from last_exc
    if r.status_code != 200:
        raise ApiFootballError(f"{endpoint} HTTP {r.status_code}: {r.text[:200]}")
    body = r.json()
    errs = body.get("errors")
    if errs:
        # api-sports puts errors in either {} (empty) or {key: msg}
        if isinstance(errs, dict) and errs:
            raise ApiFootballError(f"{endpoint} errors: {errs}")
        if isinstance(errs, list) and errs:
            raise ApiFootballError(f"{endpoint} errors: {errs}")

    response = body.get("response", [])
    # 体检 Wave3 (P2) — atomic write (tmp + rename): a crash/power-cut mid-write
    # used to leave a truncated JSON that poisoned every later cache read.
    _tmp = cf.with_name(f"{cf.name}.{os.getpid()}.tmp")
    _tmp.write_text(json.dumps(response, indent=2, ensure_ascii=False))
    _tmp.replace(cf)
    return response


# ----- league + season ID resolution ------------------------------------

# Mapping from our canonical league codes → API-Football league IDs.
# Acquired by calling /leagues with a name query and recording the IDs once.
# Reference: https://www.api-football.com/documentation-v3#tag/Leagues
_DOMESTIC_LEAGUE_IDS: dict[str, int] = {
    "EPL": 39,
    "ESP_LA_LIGA": 140,
    "ITA_SERIE_A": 135,
    "GER_BUNDESLIGA": 78,
    "FRA_LIGUE_1": 61,
    "ENG_CHAMPIONSHIP": 40,
    "ESP_SEGUNDA_DIVISION": 141,
    "ITA_SERIE_B": 136,
    "GER_2_BUNDESLIGA": 79,
    "FRA_LIGUE_2": 62,
    "NED_EREDIVISIE": 88,
    "PRT_PRIMEIRA_LIGA": 94,
    # post-V12 audit (2026-05-26): BEL_PRO_LEAGUE was missing here despite
    # being in our 14-league production training set (data/historical_sources
    # /football_data_co_uk/europe/<YY>YY/B1.csv covers 5 seasons of Belgian
    # Jupiler Pro League). The daily cron would silently skip every Belgian
    # match with "no API-Football league ID for 'BEL_PRO_LEAGUE'" — see
    # tests/v4/test_league_coverage.py for the guardrail.
    "BEL_PRO_LEAGUE": 144,   # Jupiler Pro League (Belgium)
    "JPN_J1": 98,
    # V12 W8 — 市场模式 expansion (2026-05-30). Not trained on; served via
    # market mode (Pinnacle de-vig 1X2 + reverse 让球). IDs verified against
    # API-Football /leagues?current=true. 竞彩-common + Pinnacle-priced.
    "NOR_ELITESERIEN": 103,     # Norway   (calendar-year)
    "SWE_ALLSVENSKAN": 113,     # Sweden   (calendar-year)
    "DNK_SUPERLIGA": 119,       # Denmark  (Jul–May, European)
    "FIN_VEIKKAUSLIIGA": 244,   # Finland  (calendar-year)
    "KOR_K_LEAGUE_1": 292,      # S. Korea (calendar-year)
    "JPN_J2": 99,               # Japan J2 (calendar-year)
    "AUS_A_LEAGUE": 188,        # Australia (Oct–May, European)
    "SCO_PREMIERSHIP": 179,     # Scotland (Aug–May, European)
    "TUR_SUPER_LIG": 203,       # Turkey   (Aug–May, European)
    "SUI_SUPER_LEAGUE": 207,    # Switzerland (Jul–May, European)
    # 补美职联+巴甲(2026-07-14 owner)— 美洲市场模式(竞彩深夜/凌晨窗常上架)。
    # id 对 AF /teams?season=2026 live 验证:253=MLS(30 队,豪门对得上)、
    # 71=巴甲(20 队);均日历年制(见 CALENDAR_YEAR_LEAGUES)。sport_key 已 live 核。
    "USA_MLS": 253,             # USA MLS (calendar-year, ≈Feb–Dec)
    "BRA_SERIE_A": 71,          # Brazil Série A (calendar-year, ≈Apr–Dec)
    # 补荷乙(2026-08-05 owner)— 竞彩写作「荷乙」(皇冠线史 105 行实证)。
    # id=89 对本地 fixtures 缓存实证(country=Netherlands,season 2025/2026 都在);
    # 荷兰另有 Tweede Divisie=492,别串。秋春制 ⇒ **不**进 CALENDAR_YEAR_LEAGUES
    # (实测 season_for_date(2026-08-07) = 2026,与 AF 标的 season 一致)。
    "NED_EERSTE_DIVISIE": 89,   # Eerste Divisie (Netherlands, Aug–May)
    # 补沙职(2026-08-09 owner)— 竞彩写作「沙职」(league_id=2068446,长档案 154 场
    # / 2025-10→2026-05)。id=307 对 AF `/leagues?search=Saudi` **live 核过**
    # (country=Saudi-Arabia, type=League, current season=2026);沙特另有
    # Division 1=308 / King's Cup=504 / Super Cup=826,别串。
    # 8 月–5 月跨年 ⇒ 欧洲惯例(season=开赛那年)正确,**不**进 CALENDAR_YEAR_LEAGUES。
    #
    # ⭐ 为什么放这里而不是 `CUP_COMPETITIONS`:它是**国内俱乐部联赛**。
    # 放进那个字典会踩两个真 bug —— `is_cup_competition()` 只看「在不在字典里」、
    # 不看 `competition_type`(competitions.py:332);而 `classify_league()` 的
    # `if s in CUP_COMPETITIONS: return "excluded"` 先命中,沙职会被从 δ 拟合的
    # 「国内联赛」人口里悄悄踢出去。同一段注释里明写着荷乙**不该**被排除,
    # 理由一模一样。(2026-08-09 我第一版就放错了,写在这里免得下次再犯。)
    "SAU_PRO_LEAGUE": 307,      # Saudi Pro League (Aug–May, European convention)
    # 体检(2026-06-10)— 国际友谊赛. The user records friendly bets via the
    # manual reverse calculator (e.g. Croatia vs Slovenia 6/7); without this
    # code the settle cron could NEVER fetch their results → permanent 未结算
    # orphans. id verified against the cached envelope (league id=10).
    "FRIENDLIES": 10,           # International friendlies (calendar-year)
}

# Cup + national-team competition IDs (V6 W11). Merged into the public
# API_FOOTBALL_LEAGUE_IDS dict below so existing callers using
# `league_id("UCL")` work without code changes.
def _merged_league_ids() -> dict[str, int]:
    from nutmeg.v4.data.competitions import CUP_COMPETITIONS
    merged = dict(_DOMESTIC_LEAGUE_IDS)
    for code, comp in CUP_COMPETITIONS.items():
        if comp.api_football_id is not None:
            merged[code] = comp.api_football_id
    return merged


API_FOOTBALL_LEAGUE_IDS: dict[str, int] = _merged_league_ids()


def league_id(canonical: str) -> int:
    if canonical not in API_FOOTBALL_LEAGUE_IDS:
        raise ApiFootballError(f"no API-Football league ID for {canonical!r}")
    return API_FOOTBALL_LEAGUE_IDS[canonical]


# Calendar-year leagues run within ONE calendar year (≈Feb–Dec), so the
# API-Football ``season`` param is the date's calendar year — NOT the European
# Aug–Jul "year the season started" convention. Add codes here as more
# calendar-year leagues (other Asian / Nordic / Americas) enter the set.
CALENDAR_YEAR_LEAGUES: frozenset[str] = frozenset({
    "JPN_J1",
    # V12 W8 — Nordic + K-League + J2 run ≈Feb–Nov (one calendar year). The
    # other new market-mode leagues (Denmark/Scotland/Turkey/Switzerland/
    # Australia) run Aug/Oct–May → the European heuristic is correct for them.
    "NOR_ELITESERIEN", "SWE_ALLSVENSKAN", "FIN_VEIKKAUSLIIGA",
    "KOR_K_LEAGUE_1", "JPN_J2",
    # 补(2026-07-14)— 美职联 Feb–Dec、巴甲 Apr–Dec 都在一个日历年内。
    "USA_MLS", "BRA_SERIE_A",
    # V14 — single-summer national-team tournaments are held within ONE
    # calendar year, so season = that year (WC 2026 = season 2026). Without
    # this, a June date falls to the Aug–Jul heuristic → year−1 (2026→2025) →
    # the API returns 0 WC fixtures, so the generic _gather_rows path (近期赛事
    # board + market-mode predict-log + daily_odds) silently MISSES the whole
    # World Cup. The WC-specific endpoints already use on_date.year directly;
    # this aligns the generic fixture fetch with them.
    "WC", "EURO", "COPA_AMERICA",
    # 补(2026-08-09)— 解放者杯 2-11 月跑完一个日历年;欧超杯是 8 月的单场赛事。
    # ⚠️ 解放者杯**必须**在这里:不然 3 月的比赛按欧洲惯例算成 season=去年,
    # AF 返回 0 场 —— 与 WC 那条注释记的「6 月落到 year−1 ⇒ 整届世界杯静默消失」同族。
    # ⛔ 沙职**不在**这里:8 月–5 月跨年,欧洲惯例(season=开赛那年)本来就对。
    "COPA_LIBERTADORES", "UEFA_SUPER_CUP",
    # 补(2026-08-18)— 韩国杯(KOR_FA_CUP)2–11 月日历年制,同 KOR_K_LEAGUE_1(292)。
    # season=2026 全 55 场落在一个日历年;不进这里则年初的 1/128~Round of 32 会被算成
    # season−1,AF 返 0 场(同 解放者杯 / WC 那条注释的族)。
    "KOR_FA_CUP",
    # 补(2026-09-01)— 日联赛杯(JPN_LEAGUE_CUP=101)。**实测**竞彩档案 123 场的
    # 月份分布:2月2 / 3月67 / 4月32 / 5月12 / 6月58 / 8月6 / 9月39 / 10月30 / 11月5,
    # **12 月与 1 月为零** ⇒ 一个日历年内跑完(AF catalog 也写 2025-03-20→2025-11-01)。
    # ⚠️ 不进这里的话,年初(2-4 月,占档案 **82%**)的轮次会按欧洲惯例算成 season−1,
    #   AF 返 **0 场且不报错** —— 这个家族的坑仓里已经踩过至少四次(WC/解放者杯/韩国杯/社区盾)。
    # ⚠️ 日本正在转秋春制:缓存里 J1 的 2026-08~09 场次已被 AF 标成 `season=2027`,
    #   而**同期的杯赛仍标 season=2026** ⇒ 杯赛目前还是日历年制。哪天它跟着转,这里要改。
    "JPN_LEAGUE_CUP",
    # 体检(2026-06-10)— friendlies are scheduled year-round; API-Football
    # tags them with the calendar year (cached envelope: season=2026).
    "FRIENDLIES",
})


def season_for_date(on_date: date, league_canonical: str | None = None) -> int:
    """API-Football ``season`` (the year a season started) for a date.

    European leagues run Aug–May, so a Jan–Jul date belongs to the *previous*
    year's season (2026-05 → 2025). Calendar-year leagues (J-League etc.) run
    within one calendar year, so the season is simply the date's year
    (2026-05 → 2026).

    Getting this wrong silently returns 0 fixtures: querying a J1 spring date
    under the European heuristic asks for the prior, already-finished season —
    which is exactly why next-day J1 fixtures went undetected (V12 W4 bug).
    """
    if league_canonical in CALENDAR_YEAR_LEAGUES:
        return on_date.year
    return on_date.year if on_date.month >= 7 else on_date.year - 1


# ----- fetchers ---------------------------------------------------------

def fetch_fixtures_for_date(
    on_date: date,
    league_canonical: str | None = None,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Pull all fixtures on the given UTC date, optionally filtered to one league."""
    params: dict[str, Any] = {"date": on_date.isoformat()}
    lid: int | None = None
    if league_canonical:
        lid = league_id(league_canonical)
        params["league"] = lid
        # Season is league-aware: European leagues use the Aug–Jul heuristic,
        # calendar-year leagues (J1 etc.) use the date's year. See
        # season_for_date — getting this wrong returns 0 fixtures.
        params["season"] = season_for_date(on_date, league_canonical)
    # Today-or-later fixtures are still being confirmed → a stale (often empty)
    # cache can mask a not-yet-listed match indefinitely. Force-refresh a cache
    # older than the TTL; if that refetch fails (network down), fall through to
    # the normal cached read so we're never worse than the permanent cache.
    if not refresh and on_date >= datetime.now(UTC).date():
        cf = _cache_path("/fixtures", params, Path(cache_dir))
        if cf.exists() and time.time() - cf.stat().st_mtime > _UPCOMING_FIXTURE_TTL_SECONDS:
            try:
                return _request("/fixtures", params, cache_dir=cache_dir, refresh=True)
            except ApiFootballError:
                pass  # keep the stale cache rather than break the board
    rows = _request("/fixtures", params, cache_dir=cache_dir, refresh=refresh)
    if lid is not None and not rows:
        rows = _confirm_absence_by_date(on_date, lid, league_canonical,
                                        cache_dir=cache_dir, refresh=refresh)
    return rows


#: 2026-08-05 —— **「合法地返回 [] 」和「真的没有比赛」长得一模一样**,这一条修的就是它。
#:
#: 实测事故:J1 从 2026-08-07 起改秋春制,API-Football 把这批 fixture 标成
#: ``season=2027``,而 `season_for_date` 两个分支都给 2026(日历年分支 = 当年;
#: 欧洲启发式对 8 月也 = 当年)⇒ 带 league 过滤的查询**合法地**返回 ``[]``,
#: 缓存文件字面就是 2 字节的 ``[]``。面板上 J1 整个消失,而且没有任何报错。
#: ⚠️ 「把 JPN_J1 移出 CALENDAR_YEAR_LEAGUES」这个显而易见的修法**是错的** ——
#: 两个分支都产生不了 2027。
#:
#: 修法不是给每个联赛维护一张赛制切换表(那还是在猜),而是**让 API 自己说**:
#: 同一天**不带 league** 的查询覆盖全部联赛、且每个 fixture 自带 ``league.season``。
#: 实测 2026-08-07:324 场 / 142 个联赛,里面就有那 2 场 J1(season=2027)。
#:
#: 代价:每个日期最多**多打 1 次**(不带 league 的响应按日期缓存,当天所有联赛共用),
#: 换来的是 0 场从「可能是我 season 猜错了」变成**可证的缺席**。
def _confirm_absence_by_date(
    on_date: date,
    lid: int,
    league_canonical: str | None,
    *,
    cache_dir: Path,
    refresh: bool,
) -> list[dict[str, Any]]:
    """league+season 查询空了 → 用同日的**无过滤**查询复核,并按 league id 筛。"""
    import logging

    try:
        # league_canonical=None ⇒ 不带 league/season ⇒ 不会再触发本函数(无递归)
        all_rows = fetch_fixtures_for_date(
            on_date, None, cache_dir=cache_dir, refresh=refresh)
    except ApiFootballError:
        return []          # 网络/额度问题:退回「就是没有」,不比修复前更差
    hit = [r for r in all_rows if ((r.get("league") or {}).get("id")) == lid]
    if hit:
        # ⚠️ 必须喊出来。自愈而不告诉你 = 你永远不知道 season 表已经错了,
        # 直到某天连按日兜底也失效。同「零新增 ≠ 扫完了」。
        seasons = sorted({(r.get("league") or {}).get("season") for r in hit})
        logging.getLogger(__name__).warning(
            "season 推导错了:%s %s 按 season=%s 查得 0 场,而按日查回 %d 场"
            "(API 实际 season=%s)—— 已用按日结果兜住;该联赛可能改了赛制,"
            "去核对 CALENDAR_YEAR_LEAGUES / season_for_date",
            league_canonical, on_date,
            season_for_date(on_date, league_canonical), len(hit), seasons)
    return hit


def fetch_fixtures_for_league_season(
    league_canonical: str,
    season: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """V10 W1 Track B Day 4 — pull ALL fixtures for one (league, season).

    Returns both NS (upcoming) and FT (finished) fixtures. Used by the
    WC predict CLI which needs the full tournament schedule, not just
    one day. The season-based query is also more cache-friendly for
    repeated calls within a tournament window.
    """
    params = {
        "league": league_id(league_canonical),
        "season": season,
    }
    # Same staleness class as fetch_fixtures_for_date (fixed 2026-07-01): a
    # still-active season keeps gaining confirmed fixtures, but the permanent
    # cache froze them — the WC-vanish bug reachable via this un-hardened path
    # (previously only saved by daily_wc_settle's --refresh coupling). Refresh a
    # cache older than the TTL for the current/recent season (start year ≥ last
    # year also covers in-progress European Aug–May seasons); older seasons are
    # settled → cache forever. Network-fail → fall back to the stale cache.
    if not refresh and season >= datetime.now(UTC).year - 1:
        cf = _cache_path("/fixtures", params, Path(cache_dir))
        if cf.exists() and time.time() - cf.stat().st_mtime > _UPCOMING_FIXTURE_TTL_SECONDS:
            try:
                return _request("/fixtures", params, cache_dir=cache_dir, refresh=True)
            except ApiFootballError:
                pass
    return _request("/fixtures", params, cache_dir=cache_dir, refresh=refresh)


def fetch_lineups(
    fixture_id: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Two-element list: home team + away team lineup (starting XI + subs).

    Available roughly 1 hour pre-kickoff. Returns empty when not yet published.
    """
    return _request("/fixtures/lineups", {"fixture": fixture_id},
                    cache_dir=cache_dir, refresh=refresh)


def fetch_injuries(
    team_id: int,
    season: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Current injury list for a team in a season."""
    return _request("/injuries", {"team": team_id, "season": season},
                    cache_dir=cache_dir, refresh=refresh)


def _odds_has_prices(rows: list[dict[str, Any]] | None) -> bool:
    """True iff an /odds payload carries at least one bookmaker entry.

    「空」不只是 ``[]`` —— AF 也可能给回带 fixture 壳但 ``bookmakers`` 全空的行,
    两者对下游(psc 解析)同样是零价。"""
    return any(isinstance(r, dict) and r.get("bookmakers") for r in (rows or []))


def _cached_odds_with_prices(cf: Path) -> list[dict[str, Any]] | None:
    """The cached /odds payload, only when it has usable prices; else None
    (missing / corrupt / price-less cache ⇒ nothing worth protecting)."""
    if not cf.exists():
        return None
    try:
        rows = json.loads(cf.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return rows if isinstance(rows, list) and _odds_has_prices(rows) else None


def fetch_odds(
    fixture_id: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
    max_age_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Pre-match odds across all books carried by API-Football for one fixture.

    ``max_age_seconds`` is opt-in (default None = permanent-until-refresh, so the
    cup-odds backfill + score_ev keep their permanent cache and never re-hit the
    quota for thousands of settled fixtures). When set, a cache older than it is
    refetched — the gather passes it so a fixture's odds don't serve days-stale
    for leagues without a fresh-Pinnacle overlay (体检 F1). Network-fail → stale
    fallback, so we're never worse than the permanent cache.

    体检 2026-07-17(挪超 Bodo/Glimt 消失案)—「**空的成功也是失败**」:AF 会在
    临近开赛时下架赛前赔率;到龄重拉恰好落进这个窗口时拿回 ``[]``,旧实现把它当
    合法数据写缓存 ⇒ 下午还在的好线被空响应静默冲掉 → fixture 掉进待开盘 →
    竞彩 SP 不再 join → 可投注区恰在**下注窗口**抹掉场次。现在:重拉(到龄或
    显式 refresh)返回**无可用价**而旧缓存有价 ⇒ 写回旧缓存并照常返回;线龄由
    卡片 odds_update 徽章如实标注(>2h ⚠️陈旧),临场真价走手填。恢复后 mtime
    落在当下 ⇒ 下次到龄重拉自然退避一个 max_age,不会每请求一发。
    同族先例:clubelo 空 body 闸、W2-2 空队表 TTL。"""
    params = {"fixture": fixture_id}
    cf = _cache_path("/odds", params, Path(cache_dir))
    stale_due = (
        not refresh and max_age_seconds is not None
        and cf.exists() and time.time() - cf.stat().st_mtime > max_age_seconds
    )
    if refresh or stale_due:
        prior = _cached_odds_with_prices(cf)
        try:
            fresh = _request("/odds", params, cache_dir=cache_dir, refresh=True)
        except ApiFootballError:
            if stale_due:
                return _request("/odds", params, cache_dir=cache_dir)
            # ⭐ 2026-08-07 — 以前这里是裸 `raise`,理由是「用户明确要求新的,
            # 拿不到就别假装」。听起来对,实测代价是**反过来的**:
            # 上抛 → `_fetch_odds_safe` 收成 ('err', exc) → `_gather_rows` 把
            # odds_payload 置空 → psc=None → 该场掉进「待开盘」⇒
            # **你点刷新,结果想下注的那场从可投注区消失了。**
            # 而旧缓存并不是「假装」:卡片上的 odds_update 徽章会如实标线龄
            # (>2h 显示 ⚠️陈旧),所以回落是**降级可见**,上抛是**静默消失**。
            # 同一份取舍 2026-07-17 已经在「空响应」那条路上做过一次(见上面
            # 挪超 Bodo/Glimt 案),这里补齐另一半:失败也别把好线冲掉。
            if prior is not None:
                log.warning(
                    "AF /odds refresh failed for fixture %s — serving prior cache "
                    "(%d rows); the card's odds_update badge marks it stale",
                    fixture_id, len(prior),
                )
                return prior
            raise
        if prior is not None and not _odds_has_prices(fresh):
            # _request 刚用空响应覆盖了缓存 —— 同款原子写把旧内容恢复回去
            _tmp = cf.with_name(f"{cf.name}.{os.getpid()}.tmp")
            _tmp.write_text(json.dumps(prior, indent=2, ensure_ascii=False))
            _tmp.replace(cf)
            log.warning(
                "AF /odds went empty for fixture %s — keeping prior cache "
                "(%d rows); AF delists pre-match odds near kickoff",
                fixture_id, len(prior),
            )
            return prior
        return fresh
    return _request("/odds", params, cache_dir=cache_dir, refresh=refresh)


def fetch_status() -> dict[str, Any]:
    """Subscription status; useful for cron health checks."""
    return _request("/status", {})  # singleton response, len=1


def fetch_teams_for_league_season(
    league_canonical: str,
    season: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """All teams in a league + season — used to harvest logo URLs.

    Each record contains ``team`` (id/name/logo) + ``venue``. V11 P1-FE#2
    uses this to ingest team logos for the dashboard.
    """
    params = {"league": league_id(league_canonical), "season": season}
    # 体检 Wave2 — an EMPTY team table for the current/upcoming season means
    # "not listed yet", not truth (TUR/AUS 2026 were cached as [] forever).
    # A permanent empty cache hands the autumn dictionary-coverage diff a fake
    # green light. Same today-or-later TTL pattern as fetch_fixtures_for_date:
    # retry a stale empty cache, fall back to it if the refetch fails.
    if not refresh and season >= datetime.now(UTC).year - 1:
        cf = _cache_path("/teams", params, Path(cache_dir))
        if (
            cf.exists()
            and time.time() - cf.stat().st_mtime > _UPCOMING_FIXTURE_TTL_SECONDS
        ):
            try:
                if json.loads(cf.read_text()) == []:
                    return _request("/teams", params, cache_dir=cache_dir, refresh=True)
            except ApiFootballError:
                pass  # keep the stale cache rather than break the caller
            except (json.JSONDecodeError, OSError):
                pass
    return _request("/teams", params, cache_dir=cache_dir, refresh=refresh)


def fetch_team_squad_stats(
    team_id: int,
    season: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Per-player season stats for a team's full squad.

    Used by V6 W2 lineup features to compute `xi_minutes_share`: of the
    11 players starting today, how much of this season's starting-XI
    workload are they collectively responsible for? Sub-1.0 indicates
    rotation / rest / injury-driven changes (less reliable XI), 1.0
    means today's XI mirrors the season's most-trusted XI.

    The endpoint returns one record per (player, league) — we filter
    to the requested league and aggregate by player_id outside.
    """
    return _request("/players", {"team": team_id, "season": season},
                    cache_dir=cache_dir, refresh=refresh)


def compute_xi_minutes_share(
    starting_xi_player_ids: list[int],
    squad_stats: list[dict[str, Any]],
) -> float:
    """Given today's starting XI (player IDs) and the season squad stats,
    compute the fraction of total season-starting minutes those 11 players
    contributed.

    Returns 1.0 when starting_xi is empty (no XI to evaluate yet) — caller
    should pair with the lineup_present_flag to interpret.
    Returns 0.5 (safe placeholder) when squad_stats is empty.
    """
    if not starting_xi_player_ids:
        return 1.0
    if not squad_stats:
        return 0.5

    total_starts = 0
    xi_starts = 0
    xi_set = set(starting_xi_player_ids)
    for record in squad_stats:
        player_id = record.get("player", {}).get("id")
        stats_list = record.get("statistics", [])
        # API-Football returns multiple stats blobs per player (one per
        # competition). Sum starts across all of them.
        player_starts = sum(
            (s.get("games", {}).get("lineups") or 0) for s in stats_list
        )
        total_starts += player_starts
        if player_id in xi_set:
            xi_starts += player_starts

    if total_starts <= 0:
        return 0.5
    # Normalize: max is 11 * (total_starts / 11) = total_starts when the
    # team's 11 most-used players are starting; ratio is xi_starts / max_possible
    return min(1.0, max(0.0, xi_starts / total_starts))


__all__ = [
    "API_FOOTBALL_LEAGUE_IDS",
    "ApiFootballError",
    "fetch_fixtures_for_date",
    "fetch_lineups",
    "fetch_injuries",
    "fetch_odds",
    "fetch_status",
    "fetch_team_squad_stats",
    "compute_xi_minutes_share",
    "league_id",
]
