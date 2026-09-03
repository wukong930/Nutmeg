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
                                                   (10 × markets × regions;
                                                    实测见下)

Sport keys for our needs:
  soccer_uefa_champs_league                — UCL
  soccer_uefa_europa_league                — UEL (off-season Jun-Aug)
  soccer_uefa_europa_conference_league     — UECL (optional)

Cache strategy mirrors api_football.py: each fetch_* writes a JSON to
data/external/odds_api/<endpoint>/<params-hash>.json so repeated runs
don't burn quota. `refresh=True` bypasses cache.

Quota math (Starter tier 20K/month):
  ⚠️ **实测更正(2026-07-23)**:下面这行「10 quota each」是**基础倍率**,不是单价。
  真实计价 = 10 × markets × regions。我们的收盘锚口径 markets="h2h,totals"(2)×
  regions="eu"(1) ⇒ **20 额度/次**,是本节旧估算的 2 倍。
  测法(不额外花钱):免费端点 /v4/sports 的响应头带 x-requests-remaining,
  在一次历史调用前后各读一次,差值即真实单价。
  ⚠️ 另一坑:请求一个该 sport_key **没有赛事**的时刻(如 7 月问 UCL,当季 5 月已完
  赛、资格赛不在该 key 下),API 不报错,而是返回**最近可得的快照**——2026-07-23
  实测拿回 5 月 30 日的决赛。消费方必须按 commence_time 二次过滤,否则会把上赛季
  的线当成本场收盘价写进去(scripts/backfill_closing_gap.py 的窗口判定即为此)。

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
    # 体检 (2026-07-12) — 6 个市场模式联赛缺 sport key(注册表覆盖率警告)。/sports?all=true
    # live 核对:5 个有真 key(丹超/苏超/瑞士超 active=True;澳超/土超 现休赛 active=False,
    # 但 key 存在 → 加了 fetch fail-soft,复赛自激活,与 8 键批次同规律)。JPN_J2 = Odds
    # API 根本没有(只有 J1 soccer_japan_j_league,已映射到 JPN_J1)→ 故意留空。
    # ⚠️ 2026-08-08 —— 原文接的是「继续走 AF 镜像(市场模式设计内)」。这半句对 J2
    # **不可靠**,但我当天先写了一版更正说「AF 镜像也是空的、J2 两条路都空」,
    # ⛔ 那一版**当晚就被证伪**,现在这段是第二次改。两次都记在这里,因为错法比结论有用:
    #
    #   · 07:28Z 我数了缓存 90 场 + 两次 live refresh:06-08 之后逐场零家博彩。
    #   · 我拿**7 天后**的 fixture 1606606 返回零家,当成「排除了『太早所以还没发』」——
    #     🚨 **逻辑反了**。「临场才发」这个假说预测的**正是**7 天后为空。
    #     我用一个与假说相容的观测去「证伪」它,等于没测。
    #   · 13:00Z 复查:同一个 fixture 1606605 已有 **13 家含 Pinnacle**,
    #     AF 自己的 `odds_update` = 11:11Z ⇒ 开球前约 **23 小时**才发布。
    #
    # ⇒ 现在的说法(只说数到的):**AF 对 J2 覆盖稀疏且晚** —— 2026-08-08/09 那轮
    #   10 场里只有 1 场拿到线,且在临场 ~23h 才出现;另一场竞彩在卖的
    #   (Omiya vs Albirex)直到 T−2.5h 仍是零家、最终没等到。
    #   ⇒ 「有没有」取决于**问的时刻**,别再下「从不给」这种时间无关的断言。
    # ⇒ 实践后果不变:J2 随时可能在竞彩已开售时**没有** Pinnacle。
    #   这种场次走手填(`reason='jingcai_selling_no_pinnacle'` → 面板给手填入口),
    #   ⛔ 但仍然不许拿别的书商顶替 Pinnacle 凑一个 P 出来(那就是编造 +EV)。
    # 荷乙那条(见下面 2026-08-05 注)**仍然成立**:同样没 sport key,但 AF 有 Pinnacle
    # (08-08 当日 3/3 上了可定价区)⇒ 「缺 key ⇒ 走 AF 镜像」是**逐联赛**的经验事实,
    # 不是一条可以外推的规则。要断言某联赛有覆盖,就去数那个联赛自己的行。
    "DNK_SUPERLIGA":        "soccer_denmark_superliga",
    "SCO_PREMIERSHIP":      "soccer_spl",
    "SUI_SUPER_LEAGUE":     "soccer_switzerland_superleague",
    "AUS_A_LEAGUE":         "soccer_australia_aleague",
    "TUR_SUPER_LIG":        "soccer_turkey_super_league",
    # 补美职联+巴甲(2026-07-14)— 均 /sports?all=true live 核实 active=True。
    "USA_MLS":              "soccer_usa_mls",
    "BRA_SERIE_A":          "soccer_brazil_campeonato",
    # 补解放者杯 + 沙职(2026-08-09 owner)— /sports?all=true live 核实(175 个 sport 全表):
    #   · 解放者杯 `soccer_conmebol_copa_libertadores` **active=True**(南美赛季进行中);
    #   · 沙职     `soccer_saudi_arabia_pro_league`    active=False(8 月休赛),
    #     赛季 08-13 开打后按 8 键批次的规律自激活 —— fetch fail-soft 已就位。
    # 🚨 沙职这条**格外重要**:AF 对沙职**不给赔率**(未来场次 0 家;拿上赛季
    #    已打完的 5 场复验同样 0/5,所以不是「还没发」)⇒ Odds API 是它**唯一**的鲜线源。
    # ⛔ **欧超杯故意没有条目**:整个 175 个 sport 里没有 UEFA Super Cup(全表核过)。
    #    它只走 AF 镜像 —— 2026 那场 fixture 1583664 实测 13 家含 Pinnacle。
    #    ⚠️ 别把它读成「缺 key ⇒ AF 兜底」的规则(日乙同样缺 key 而 AF 也空)。
    "COPA_LIBERTADORES":    "soccer_conmebol_copa_libertadores",
    "SAU_PRO_LEAGUE":       "soccer_saudi_arabia_pro_league",
    # 补英联赛杯(2026-08-05)— /sports?all=true live 核实 active=True。
    # ⚠️ 同批注册的 **NED_EERSTE_DIVISIE(荷乙)故意没有条目**:整个 Odds API 只有
    # `soccer_netherlands_eredivisie`(荷甲),荷乙这个 sport **不存在**(174 个 sport
    # 全表核过)。同 JPN_J2 先例 —— 留空,走 AF 的 Pinnacle 镜像(实测 fixture
    # 1551741 有 Pinnacle),registry-coverage 记 warn 非 gap。
    # 别「补全」它:猜一个不存在的 key 只会让 fetch 每次 404 当空处理。
    "EFL_CUP":              "soccer_england_efl_cup",
    # ⛔ **韩国杯(KOR_FA_CUP)故意没有条目**(2026-08-18)— `/v4/sports?all=true` 175 个
    #    sport 全表 live 核过,韩国只有 `soccer_korea_kleague1`(K联赛),**没有**韩国杯这个
    #    sport。留空,走 AF(id=294)一路线;registry-coverage 记 sport-key warn 非 gap。
    #    同 欧超杯/荷乙/JPN_J2 先例:别猜一个不存在的 key(只会让 fetch 每次 404 当空)。
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


# ── Quota/auth breaker ────────────────────────────────────────────────────────
# The Odds API fails ACCOUNT-WIDE: once the plan's credits are gone, every
# endpoint answers 401 [OUT_OF_USAGE_CREDITS] until the quota resets, and a
# failed call caches nothing — so the next caller re-asks and pays the same
# ~0.4s round-trip to be told the same thing. The 市场模式 overlay asks once per
# (sport × day): 17 sports × 7 days = 119 calls, which is fine when they hit the
# TTL cache (`_oa_refresh_decision`: "the OA feed is date-independent, so later
# days reuse that fresh cache") but degenerates to 119 live 401s once the cache
# ages past the TTL with the quota dead. MEASURED 2026-07-17 on
# /predictions/cup-market?days=7: 45.2s of 48.0s wall, and the E2E suite red
# because the page never reaches networkidle inside Playwright's 30s.
#
# One 401 tells us the rest of the sweep is pointless, so trip a breaker and
# fail the remainder locally. Deliberately NOT a stale-cache fallback: the
# `ttl_seconds` gate exists so a passive load "never serves a day-old line"
# (see _request), and the overlay is optional — an empty lookup degrades to the
# API-Football mirror, which is the intended graceful path. This only makes the
# degrade cheap. 401 ONLY (bad key / out of credits — both terminal until a
# human acts, same read as odds_api_history's `if r.status_code in (401, 422)`);
# a 5xx or timeout stays retryable. The cooldown self-heals after a top-up.
_BREAKER_COOLDOWN_SECONDS = 900.0
_breaker_until = 0.0   # time.monotonic() deadline; 0.0 = closed


def _trip_breaker() -> None:
    global _breaker_until
    _breaker_until = time.monotonic() + _BREAKER_COOLDOWN_SECONDS


def _breaker_remaining() -> float:
    """Seconds the breaker stays open; 0.0 when closed (calls allowed)."""
    return max(0.0, _breaker_until - time.monotonic())


def reset_quota_breaker() -> None:
    """Close the breaker now — for tests, and for a caller that knows the quota
    was topped up and doesn't want to wait out the cooldown."""
    global _breaker_until
    _breaker_until = 0.0


def _cache_path(endpoint: str, params: dict[str, Any], cache_dir: Path) -> Path:
    """One JSON per (endpoint, params). API key is excluded from the
    hash so cache survives key rotation."""
    redacted = {k: v for k, v in params.items() if k != "apiKey"}
    payload = json.dumps(redacted, sort_keys=True, default=str).encode()
    h = hashlib.sha1(payload).hexdigest()[:12]
    safe_endpoint = endpoint.strip("/").replace("/", "_")
    return cache_dir / safe_endpoint / f"{h}.json"


#: {endpoint: 上一次真发请求并写盘成功的 unix 时刻}。⚠️ **进程内状态,不落盘** ——
#: 它回答的是「在**这一次进程**里,刚才那次拉取是不是真的花了钱」,不是「缓存有多新」。
#: 两者不同:缓存可能是别的进程 30 秒前写的,那时读它同样零成本,但本进程没法知道,
#: 而**漏判是安全方向**(少采一次快照),误判才会花钱。
_LAST_LIVE: dict[str, float] = {}


def _odds_endpoint(sport_key: str) -> str:
    """当前赔率的 endpoint 路径。**唯一构造点** —— `was_last_odds_pull_live` 和
    `fetch_current_odds` 必须拼出同一个字符串,所以只许有一份实现。
    ⛔ 调用方别自己 `f"sports/{sk}/odds"`:两份字面量会悄悄漂开,而漂开的后果是
    判据**静默常闭**(长得和「今天没比赛」一样),不会有人发现。"""
    return f"sports/{sport_key}/odds"


def was_last_odds_pull_live(sport_key: str, *, within_seconds: float = 300.0) -> bool:
    """本进程刚刚真拉过这个 sport 的当前赔率(并写盘成功)?

    给「读同一份缓存」的旁路消费方(多书商快照)判断自己是不是**零边际成本**。
    """
    return was_last_call_live(_odds_endpoint(sport_key), within_seconds=within_seconds)


def was_last_call_live(endpoint: str, *, within_seconds: float = 300.0) -> bool:
    """本进程刚刚(``within_seconds`` 内)真拉过 ``endpoint`` 并写盘成功?

    用途:让「读同一份缓存」的旁路消费方知道自己是**零边际成本**的。
    ⚠️ 时间窗不是缓存 TTL —— 它防的是「同一进程跑了很久、几小时前那次拉取被当成
    刚刚」。默认 5 分钟远大于一轮采集的耗时,又远小于任何 TTL。
    """
    t = _LAST_LIVE.get(endpoint)
    return t is not None and (time.time() - t) <= within_seconds


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

    # Checked AFTER the cache read: a fresh cache is still served with the
    # breaker open — this only suppresses the pointless live call.
    open_for = _breaker_remaining()
    if open_for > 0.0:
        raise OddsApiError(
            f"{endpoint} not attempted: Odds API quota/auth breaker open for "
            f"another {open_for:.0f}s (a previous call returned 401)"
        )

    # Attach key at request time; don't cache it
    full_params = {**params, "apiKey": settings.odds_api_key}
    r = _client().get(endpoint, params=full_params)
    if r.status_code != 200:
        if r.status_code == 401:
            _trip_breaker()
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
    # ⭐ 记一笔「这个 endpoint 刚被**真的**拉了一次、缓存刚被重写」。
    #    消费方(多书商快照)靠它判断「现在读缓存是零边际成本的」——
    #    ⛔ **判据必须问这里,不许调用方自己手抄 params 去比对缓存 mtime**:
    #    那是语法代理,`fetch_current_odds` 的默认参数一漂,判据就静默常闭,
    #    而「静默常闭」在这条路上长得和「今天没比赛」一模一样。
    _LAST_LIVE[endpoint] = time.time()
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
    endpoint = _odds_endpoint(sport_key)
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
# 俱乐部法人形式后缀 —— 折叠 core key 时剔除。原为北欧口径;2026-07-23 补 cf/sc
# (美洲用法:Club de Fútbol / Sporting Club),因为 owner 实报「迈阿密国际 vs 芝加哥」
# 没进盘面,根因是 `Inter Miami`(竞彩侧)≠ `Inter Miami CF`(Pinnacle 行)——
# `cf` 不在表里,core 没折叠成同一个,join 落空。
# **加 token 前实测过误并**(374 个队名跑全表):+cf 只多 1 组(正是迈阿密),
# +cf,sc 多 4 组(Chapecoense/Columbus Crew/Inter Miami/St. Louis City)——
# 四组**全是同一支队,零误并**。ac/cd/ud 再加不产生任何新折叠 = 纯投机,不加。
# 改这张表前请重跑那个误并测量:core 变宽会同时影响实盘 overlay 的二级键。
_CLUB_TOKENS = frozenset({"if", "ik", "bk", "ff", "sk", "fk", "aif", "fc", "afc",
                          "cf", "sc"})


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



def fetch_book_lookup(
    sport_key: str,
    *,
    regions: str = "eu",
    refresh: bool = False,
    ttl_seconds: float | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> dict[tuple[str, str, str], dict[str, tuple[float, float, float]]]:
    """**全部**书商的 1X2,键同 `fetch_pinnacle_lookup`:``(norm_home, norm_away, date)``
    → ``{bookmaker_key: (home, draw, away)}``(含 vig 的十进制赔率)。

    ## 为什么要它

    我们**每场已经收到 15–22 家**的报价(2026-09-01 实测:113 场里每场 4–24 家,
    中位 ~18),但 `fetch_pinnacle_lookup` 只留 Pinnacle 一家,其余随 TTL 缓存过期
    **一起丢掉**。⇒ 实测竞彩在售 693 场里,`odds_api` 来源的 351 场**只有 1%**
    还能找回多书商数据 —— 不是覆盖不够,是**没存**。

    用途是给单锚做**离散度**参照,已测两条:
      · 单锚会夸大:法乙那场 Pinnacle 是 13 家里最看好客胜的 ⇒
        单锚 EV **+16.7%** vs 13 家中位 **+8.8%** vs 最保守 **−0.6%**;
      · 63 场重叠样本上,「Pinnacle 过 +5% 闸而 17 家共识不过」的腿有 **5** 条
        (Canada 客胜 +5.6%→−0.7% · Panama 平局 +9.0%→+3.4% …)。
    ⛔ 但那 63 场**全是世界杯 + 全是缓存没过期的**,人口偏斜 ⇒ 只能当「机制存在」
    的证据,**不是**「影响多大」的估计。⇒ 先存,攒够了在完整人口上重量。

    ⭐ **零额外调用、零额外配额**:`fetch_current_odds` 是 TTL 缓存的,而且同一批
    事件调用方刚刚才取过 —— 这里只是把**本来就丢掉的那部分**读出来。

    ⚠️ 与 `fetch_pinnacle_lookup` 的区别:那个是 **Pinnacle-STRICT**(没有 Pinnacle
    就跳过整场,绝不拿软书顶 sharp 先验);这里**全收**,因为它的用途是**离散度**
    不是先验。⛔ 别拿本函数的输出当 P 喂进 EV —— 那会绕过 Pinnacle-STRICT 这条设计。
    """
    out: dict[tuple[str, str, str], dict[str, tuple[float, float, float]]] = {}
    events = fetch_current_odds(
        sport_key, regions=regions, markets="h2h,totals",
        refresh=refresh, ttl_seconds=ttl_seconds, cache_dir=cache_dir,
    )
    for e in events:
        home, away = e.get("home_team"), e.get("away_team")
        date = (e.get("commence_time") or "")[:10]
        if not home or not away or not date:
            continue
        key = (_norm_team(home), _norm_team(away), date)
        books: dict[str, tuple[float, float, float]] = {}
        for b in e.get("bookmakers", []) or []:
            bk = (b.get("key") or "").lower()
            if not bk:
                continue
            h2h = _extract_h2h(b)
            if not h2h:
                continue
            teams = h2h.get("teams", {})
            ph, pa, pd_ = teams.get(home), teams.get(away), h2h.get("draw")
            if ph is None or pa is None or pd_ is None:
                continue
            if not all(isinstance(x, (int, float)) and x > 1.0 for x in (ph, pd_, pa)):
                continue
            books[bk] = (float(ph), float(pd_), float(pa))
        if books:
            out[key] = books
    return out

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
    "reset_quota_breaker",
    "fetch_current_odds",
    "fetch_historical_snapshot",
    "parse_fixture_to_h2h",
    "build_psc_lookup_for_date_range",
]
