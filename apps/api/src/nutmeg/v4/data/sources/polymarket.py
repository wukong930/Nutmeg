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
        return body.get("data", []) or []
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


def fetch_soccer_game_events(
    *,
    start_date_min: str,
    end_date: str | None = None,
    max_events: int = 3000,
    page_size: int = 100,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """All soccer GAME events (matches with a kickoff in [start_date_min, end_date])
    across EVERY league Polymarket lists — J2, La Liga 2, Serie B, Chinese Super
    League, World Cup, friendlies, etc.

    IMPORTANT: the Gamma /events ``start_date_min`` query param is unreliable for
    game events — it filters on the event's creation/startDate (a season-start or
    listing date), NOT the kickoff, and silently dropped whole leagues (J2, La
    Liga 2 …) when we tried it. So we paginate the FULL soccer tag and window by
    the MARKET ``gameStartTime`` in code. Men/women + competition filtering still
    happens downstream in polymarket_match (via ``seriesSlug``).
    """
    out: list[dict[str, Any]] = []
    offset = 0
    while offset < max_events:
        try:
            page = fetch_events(limit=page_size, offset=offset, refresh=refresh)
        except PolymarketError as exc:
            # 体检 W0 2026-07-15 — Polymarket 弃用深 offset 分页(offset≥2100 →
            # 422 "use /events/keyset")。以前没接这个异常:它穿透整个 run,已抓的
            # 页全部作废、零写入、exit 0 → cron 绿灯空转 4 天(07-12 起 —— 恰是
            # soccer 开放事件数涨过 2100 的那天)。events 按 startDate 升序,深页
            # 全是远期比赛 → 撞墙 = 视为「到底了」,接受已抓的近期页;其它错误照旧抛。
            if "offset too large" in str(exc):
                log.warning(
                    "Polymarket offset cap hit at %d — accepting %d events fetched "
                    "so far (deeper pages are far-future)", offset, len(out))
                break
            raise
        if not page:
            break
        out.extend(e for e in page if _is_game_event(e) and _in_window(e, start_date_min, end_date))
        if len(page) < page_size:
            break
        offset += page_size
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
