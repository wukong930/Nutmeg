"""Polymarket adapter — READ-ONLY (mispricing detector).

Pulls PUBLIC Polymarket data to compare prediction-market prices against our
Pinnacle de-vig "fair P". This module NEVER signs or places an order — it has
no wallet, no private key, no `py-clob-client` order methods. It is a
measurement instrument, not a trading bot.

Two public APIs, no credential:
- Gamma  (``gamma-api.polymarket.com``): EVENTS + market METADATA. A soccer
  *game* is one EVENT (e.g. "Sweden vs. Italy") grouping several binary markets
  ("Will Sweden win?", "...end in a draw?", "Will Italy win?") plus prop markets.
  Each market carries ``groupItemTitle`` (clean outcome label), ``outcomes``
  (["Yes","No"]), ``clobTokenIds`` ([yes_token, no_token]) and ``gameStartTime``.
  The event's ``seriesSlug`` is the competition + men/women signal (e.g.
  "fifa-friendly", "uefa-womens-world-cup-qualification"). Slow-moving → TTL-cached.
- CLOB   (``clob.polymarket.com``): LIVE orderbook — best bid/ask + depth per
  outcome token. Prices move → fetched fresh (cache bypassed).

Caching mirrors ``sources/api_football.py`` (per-call JSON under
data/external/polymarket/<endpoint>/<hash>.json) but adds a TTL: a cached
metadata file older than ``polymarket_metadata_ttl_seconds`` is a miss.
Price/book calls pass ``ttl_seconds=0`` → always live.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from nutmeg.config import get_settings

# Same transient-retry policy as api_football (one read timeout shouldn't abort
# a whole dry-run / cron pass).
_MAX_REQUEST_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1.5

log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/external/polymarket")

# The Gamma tag slug that returns soccer events (verified 2026-06-06).
SOCCER_TAG_SLUG = "soccer"


class PolymarketError(RuntimeError):
    """Raised on non-2xx, network failure after retries, or a bad payload."""


def _client(base_url: str) -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=base_url,
        timeout=settings.polymarket_timeout_seconds,
        headers={"Accept": "application/json"},
    )


def _cache_path(base_url: str, endpoint: str, params: dict[str, Any], cache_dir: Path) -> Path:
    host = base_url.split("//", 1)[-1].split("/", 1)[0]
    payload = json.dumps(
        {"h": host, "e": endpoint, "p": params}, sort_keys=True, default=str
    ).encode()
    h = hashlib.sha1(payload).hexdigest()[:12]
    safe = (host + endpoint).replace("/", "_").replace(":", "_")
    return cache_dir / safe / f"{h}.json"


def _request(
    base_url: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    *,
    ttl_seconds: float = 0.0,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> Any:
    """GET ``base_url + endpoint``; return parsed JSON (list or dict).

    ``ttl_seconds``: reuse a cached file only when it exists AND is younger than
    the TTL. ``0`` (default) ⇒ never read cache (always live — used for prices).
    ``refresh=True`` forces a live fetch.
    """
    params = params or {}
    cache_dir = Path(cache_dir)
    cf = _cache_path(base_url, endpoint, params, cache_dir)
    if (not refresh and ttl_seconds > 0 and cf.exists()
            and time.time() - cf.stat().st_mtime < ttl_seconds):
        return json.loads(cf.read_text())

    last_exc: Exception | None = None
    r = None
    for attempt in range(_MAX_REQUEST_ATTEMPTS):
        try:
            with _client(base_url) as c:
                r = c.get(endpoint, params=params)
            break
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt + 1 < _MAX_REQUEST_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
    if r is None:
        raise PolymarketError(
            f"{endpoint} network error after {_MAX_REQUEST_ATTEMPTS} attempts: {last_exc!r}"
        ) from last_exc
    if r.status_code != 200:
        raise PolymarketError(f"{endpoint} HTTP {r.status_code}: {r.text[:200]}")
    try:
        body = r.json()
    except json.JSONDecodeError as exc:
        raise PolymarketError(f"{endpoint} non-JSON body: {r.text[:200]}") from exc

    if ttl_seconds > 0:  # only persist cacheable (metadata) calls
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    return body


# ----- JSON-string field normalization ----------------------------------
# Gamma encodes several market fields as JSON STRINGS (e.g. outcomes='["Yes",
# "No"]', clobTokenIds='["0x..","0x.."]'). Decode them into real lists.

def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        s = value.strip()
        if s and s[0] in "[{":
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return value
    return value


def normalize_market(raw: dict[str, Any]) -> dict[str, Any]:
    """Decode a market's JSON-string fields → real lists."""
    m = dict(raw)
    for k in ("outcomes", "outcomePrices", "clobTokenIds"):
        if k in m:
            m[k] = _maybe_json(m[k])
    return m


def _rows(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        # /events → {"data": [...]};/events/keyset → {"events": [...], "next_cursor": …}
        return body.get("data") or body.get("events") or []
    return []


# ----- public fetchers ---------------------------------------------------

def fetch_events(
    *,
    tag_slug: str = SOCCER_TAG_SLUG,
    closed: bool = False,
    start_date_min: str | None = None,
    start_date_max: str | None = None,
    limit: int = 100,
    offset: int = 0,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Gamma /events (list). Each event groups a game's markets. TTL-cached.

    ``start_date_min``/``start_date_max`` are ISO date strings (e.g. "2026-06-06")
    bounding the event start (≈ kickoff for game events).
    """
    settings = get_settings()
    params: dict[str, Any] = {
        "tag_slug": tag_slug,
        "closed": str(closed).lower(),
        "limit": limit,
        "offset": offset,
        "order": "startDate",
        "ascending": "true",
    }
    if start_date_min:
        params["start_date_min"] = start_date_min
    if start_date_max:
        params["start_date_max"] = start_date_max
    body = _request(
        settings.polymarket_gamma_base_url,
        "/events",
        params,
        ttl_seconds=settings.polymarket_metadata_ttl_seconds,
        refresh=refresh,
    )
    out = []
    for ev in _rows(body):
        e = dict(ev)
        e["markets"] = [normalize_market(m) for m in (ev.get("markets") or [])]
        out.append(e)
    return out



def fetch_events_keyset(
    *,
    tag_slug: str = SOCCER_TAG_SLUG,
    closed: bool = False,
    start_time_min: str | None = None,
    start_time_max: str | None = None,
    limit: int = 100,
    after_cursor: str | None = None,
    refresh: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """Gamma **/events/keyset** —— 游标分页,**没有 offset 上限**。→ (events, next_cursor)

    ## 为什么必须换到它(2026-09-01)

    `/events` 的 offset 分页在 ≥2100 返 422(Polymarket 弃用了它,错误信息直接
    点名 keyset)。而我们按 `startDate` **升序** + `closed=false` 翻页 ⇒ 浅页全是
    **已开球却没关闭**的旧市场,它们只增不减。实测墙内 **95.6%** 是过去的比赛
    (889 个开球在 30 天前以上),今天的比赛被挤到墙**后面** ⇒ 每轮只捞到 ~20 个
    可用赛事(峰值 344),抓取量从 ~140 行/天塌到 ~10 行/天,**塌了 10 天没人发现**
    (cron 退出码 0、`check_freshness` 一路绿 —— 见 `check_volume_cliff`)。

    ⭐ **`start_time_min/max` 才是按开球筛的参数**,实测 limit=100 时窗口内命中
    **100/100**;而 `start_date_min` 返回 **0 条**(它筛的是事件创建/上架日期,
    与开球中位差 **1085h**;`endDate` 才 ≈ 开球,中位差 0.00h、85% 在 1h 内)。
    ⇒ 模块历史上「`start_date_min` 不可靠」那条警告是**对的**,只是当年的结论停在
    「所以只能全量翻页」,没往下找对的字段。

    ⚠️ 参数名 `after_cursor` 来自 **`/openapi.json`**(283KB,一直都在),不是猜的。
    我猜过 7 个名字(cursor/next_cursor/nextCursor/after/…)**全部静默返回第一页**
    —— 服务端对未知查询参数不报错,于是「翻了 80 页拿到 100 条」而循环毫无察觉。
    ⇒ 见下面 `fetch_soccer_game_events` 里那条**必须有的**翻页前进断言。
    """
    settings = get_settings()
    params: dict[str, Any] = {
        "tag_slug": tag_slug,
        "closed": str(closed).lower(),
        "limit": limit,
    }
    if start_time_min:
        params["start_time_min"] = start_time_min
    if start_time_max:
        params["start_time_max"] = start_time_max
    if after_cursor:
        params["after_cursor"] = after_cursor
    body = _request(
        settings.polymarket_gamma_base_url,
        "/events/keyset",
        params,
        ttl_seconds=settings.polymarket_metadata_ttl_seconds,
        refresh=refresh,
    )
    out = []
    for ev in _rows(body):
        e = dict(ev)
        e["markets"] = [normalize_market(m) for m in (ev.get("markets") or [])]
        out.append(e)
    cursor = body.get("next_cursor") if isinstance(body, dict) else None
    return out, (str(cursor) if cursor else None)


def _is_game_event(event: dict[str, Any]) -> bool:
    """True iff the event has at least one market with a ``gameStartTime`` —
    i.e. an actual scheduled match, not a futures/award/prop event."""
    return any(m.get("gameStartTime") for m in (event.get("markets") or []))


def event_kickoff_date(event: dict[str, Any]) -> str | None:
    """ISO date (UTC) of the event's first game market's ``gameStartTime``."""
    for m in event.get("markets") or []:
        gs = m.get("gameStartTime")
        if gs:
            return str(gs)[:10]
    return None


def _in_window(event: dict[str, Any], start: str, end: str | None) -> bool:
    kd = event_kickoff_date(event)
    if kd is None:
        return False
    return kd >= start and (end is None or kd <= end)


#: keyset 分页的硬上限(防跑飞)。服务端按开球筛之后按窗口大小走,撞上会 warning。
_KEYSET_MAX_PAGES = 200
#: `max_events` 的默认值 —— 它是**保险丝不是配额**。
#: ⚠️ 旧值 3000 是 offset 时代为「全量翻页」定的;换成服务端按开球筛之后,
#: 它反而成了**新的静默截断点**:实测未来 7 天就有 3000+ 个赛事,正好被切在整数上。
#: 「量刚好等于上限」和「真的只有这么多」长得一模一样 —— 所以撞上必须喊。
_KEYSET_FUSE = 20000


def fetch_soccer_game_events(
    *,
    start_date_min: str,
    end_date: str | None = None,
    max_events: int = _KEYSET_FUSE,
    page_size: int = 100,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """开球落在 [start_date_min, end_date] 的所有足球 GAME events(全联赛)。

    走 **/events/keyset + `start_time_min/max`**(见 `fetch_events_keyset` 的
    docstring:为什么必须换、以及 `start_date_min` 为什么是错的字段)。
    服务端已按开球筛,代码里仍再过一道 `_in_window` —— 服务端语义变了要能兜住。

    ## 2026-09-01 之前的实现踩了什么

    旧实现用 `/events` 的 offset 分页 + `order=startDate&ascending=true`。
    Polymarket 在 offset≥2100 返 422;2026-07-15 的修复**接住 422 并接受已抓到的页**,
    理由写作「深页全是远期比赛 ⇒ 撞墙=到底了」。那句话当时对、后来假:
    升序下**浅页是最老的未关闭市场**,它们越堆越多,把今天的比赛挤到墙后面。
    ⇒ 那次修复**消除了症状、保留了病因,并且移除了唯一的告警**(422 不再穿透),
    于是 2026-08-23 起抓取量塌 10 倍而 cron 一路绿灯。
    ⭐ 通用教训:把「炸给你看」改成「安静少给你」之前,先问**谁来告诉我它降级了**。
    """
    lo = f"{start_date_min}T00:00:00Z"
    hi = f"{end_date}T23:59:59Z" if end_date else None
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor: str | None = None
    pages = 0
    while len(out) < max_events and pages < _KEYSET_MAX_PAGES:
        page, nxt = fetch_events_keyset(
            limit=page_size, after_cursor=cursor,
            start_time_min=lo, start_time_max=hi, refresh=refresh,
        )
        pages += 1
        if not page:
            break
        ids = {str(e.get("id")) for e in page if e.get("id") is not None}
        # 🚨 **翻页前进断言** —— 没有它,一个不生效的游标参数会让循环无限拿第一页
        # 而毫不知情。2026-09-01 实犯:我猜了 7 个游标参数名,服务端对未知查询参数
        # **不报错**,于是「翻了 80 页、拉了 467MB,累计仍是 100 条」跑完才发现。
        # ⇒ 任何游标/偏移循环的第一条断言必须是「这一页和已见过的不一样」。
        if ids and ids <= seen:
            log.error(
                "Polymarket keyset 第 %d 页没有前进(%d 条全是见过的)—— "
                "游标参数可能失效了;停止翻页,本轮只用已抓到的 %d 个赛事",
                pages, len(ids), len(out))
            break
        seen |= ids
        out.extend(
            e for e in page
            if _is_game_event(e) and _in_window(e, start_date_min, end_date)
        )
        if not nxt or len(page) < page_size:
            break
        cursor = nxt
    if len(out) >= max_events:
        log.warning(
            "Polymarket keyset 撞到 max_events=%d 的保险丝 —— **结果被截断了**,"
            "窗口内真实赛事数 ≥ 这个值。⛔ 别把它读成「就这么多」;"
            "要么缩小 --days,要么调高保险丝", max_events)
    if pages >= _KEYSET_MAX_PAGES:
        log.warning(
            "Polymarket keyset 翻到上限 %d 页仍未结束 —— 服务端窗口过滤可能没生效,"
            "查 start_time_min/max 是否还被支持", _KEYSET_MAX_PAGES)
    log.info("Polymarket keyset: %d 页 · 窗口内赛事 %d", pages, len(out))
    return out

def fetch_price(token_id: str, *, side: str = "sell", refresh: bool = True) -> float | None:
    """CLOB best price for one outcome token. ``side`` is the side of the RESTING
    book (Polymarket semantics): ``side="sell"`` = best ASK = the actionable cost
    to BUY a YES share; ``side="buy"`` = best BID. The mispricing engine uses the
    ASK (``best_ask(fetch_orderbook(...))``) as the EV denominator — prefer that
    over this helper. LIVE (cache bypassed). Returns None on an empty/illiquid
    book or a degenerate (≤0 or ≥1) price."""
    settings = get_settings()
    body = _request(
        settings.polymarket_clob_base_url,
        "/price",
        {"token_id": token_id, "side": side},
        ttl_seconds=0.0,
        refresh=refresh,
    )
    if not isinstance(body, dict):
        return None
    try:
        p = float(body.get("price"))
    except (TypeError, ValueError):
        return None
    return p if 0.0 < p < 1.0 else None


def fetch_orderbook(token_id: str, *, refresh: bool = True) -> dict[str, Any] | None:
    """CLOB orderbook for one token: ``{"bids":[{price,size}], "asks":[...]}``.
    LIVE (cache bypassed). Used to measure depth at the ask (liquidity)."""
    settings = get_settings()
    body = _request(
        settings.polymarket_clob_base_url,
        "/book",
        {"token_id": token_id},
        ttl_seconds=0.0,
        refresh=refresh,
    )
    return body if isinstance(body, dict) else None


def best_ask(book: dict[str, Any] | None) -> tuple[float, float] | None:
    """(ask_price, size_at_ask) from an orderbook, or None. CLOB ``asks`` are
    ordered worst→best (highest price first), so the best ask is the LAST one."""
    if not book:
        return None
    asks = book.get("asks") or []
    if not asks:
        return None
    try:
        best = asks[-1]
        return float(best["price"]), float(best.get("size") or 0.0)
    except (TypeError, ValueError, KeyError):
        return None


def best_bid(book: dict[str, Any] | None) -> tuple[float, float] | None:
    """(bid_price, size) — CLOB ``bids`` are ordered worst→best (lowest first),
    so the best bid is the LAST one. None on empty book."""
    if not book:
        return None
    bids = book.get("bids") or []
    if not bids:
        return None
    try:
        best = bids[-1]
        return float(best["price"]), float(best.get("size") or 0.0)
    except (TypeError, ValueError, KeyError):
        return None


def mid_price(book: dict[str, Any] | None) -> float | None:
    """(best_bid + best_ask) / 2, or None if either side is empty."""
    ba, bb = best_ask(book), best_bid(book)
    if ba is None or bb is None:
        return None
    return (ba[0] + bb[0]) / 2.0


def ask_depth_usd(book: dict[str, Any] | None, *, within: float = 0.02) -> float:
    """Total USD notional resting on the ask within ``within`` of the best ask —
    a liquidity proxy (thin book ⇒ unactionable edge). 0.0 on empty book."""
    ba = best_ask(book)
    if ba is None:
        return 0.0
    best_px, _ = ba
    total = 0.0
    for lvl in book.get("asks") or []:
        try:
            px, sz = float(lvl["price"]), float(lvl.get("size") or 0.0)
        except (TypeError, ValueError, KeyError):
            continue
        if px <= best_px + within:
            total += px * sz
    return total


__all__ = [
    "PolymarketError",
    "SOCCER_TAG_SLUG",
    "fetch_events",
    "fetch_soccer_game_events",
    "event_kickoff_date",
    "fetch_price",
    "fetch_orderbook",
    "best_ask",
    "ask_depth_usd",
    "normalize_market",
]
