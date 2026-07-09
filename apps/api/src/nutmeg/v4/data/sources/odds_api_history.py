"""Odds API 历史快照 — 真 Pinnacle 收盘(§H 确诊 CLV 用).

`/v4/historical/sports/{sport}/odds?date=<ISO>` 返回该 sport 在(或紧邻)某时刻的赔率
快照。用于给历史竞彩场配**真 Pinnacle 1X2 + 大小球收盘**(= prereg 冻结口径 `_pinn_close`
的 WPO 去vig + hhad 由 1X2+O/U DC 反推 cover-P;`docs/autumn_prereg_analysis_plan.md`
§H)。成本 10 credits/市场/调用(h2h+totals=20);限定切片(EPL 一季 ~数千 credits,17k
额度内)。500 兔子洞的干净替代(`记忆 jingcai-fixedbonus-history-endpoint`)。

外网:走代理(不清)。key = `NUTMEG_ODDS_API_KEY`。FAIL-SOFT。
"""
from __future__ import annotations

import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

_BASE = "https://api.the-odds-api.com/v4"


def _key() -> str | None:
    return os.environ.get("NUTMEG_ODDS_API_KEY")


def fetch_historical(sport_key: str, date_iso: str, *, markets: str = "h2h,totals",
                     regions: str = "eu", timeout: float = 30.0,
                     retries: int = 3) -> dict | None:
    """Historical odds snapshot for ``sport_key`` at/just-before ``date_iso`` (ISO8601
    UTC, e.g. '2024-08-17T14:00:00Z'). Returns the parsed dict
    (``{timestamp, previous_timestamp, next_timestamp, data:[matches]}``) or None
    (logged, never raised). Cost = 10 × #markets credits; read
    ``x-requests-last``/``-remaining`` from the response headers to track spend."""
    key = _key()
    if not key:
        log.warning("NUTMEG_ODDS_API_KEY not set — historical fetch skipped")
        return None
    url = f"{_BASE}/historical/sports/{sport_key}/odds"
    params = {"apiKey": key, "regions": regions, "markets": markets,
              "oddsFormat": "decimal", "date": date_iso}
    for attempt in range(retries):
        try:
            r = httpx.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                d = r.json()
                d["_cost"] = r.headers.get("x-requests-last")
                d["_remaining"] = r.headers.get("x-requests-remaining")
                return d
            if r.status_code in (401, 422):  # bad key / bad params — don't retry
                log.warning("historical %s: HTTP %s %s", sport_key, r.status_code,
                            r.text[:120])
                return None
        except Exception as exc:  # noqa: BLE001 — fail-soft
            if attempt < retries - 1:
                time.sleep(1.0 + attempt)
                continue
            log.warning("historical fetch failed (%s @ %s): %s", sport_key, date_iso, exc)
            return None
    return None


def _pinnacle(match: dict) -> dict | None:
    """Pinnacle's bookmaker block from a match, or None if absent."""
    for b in match.get("bookmakers") or []:
        if b.get("key") == "pinnacle":
            return b
    return None


def parse_pinnacle_close(snapshot: dict) -> list[dict]:
    """Snapshot → per-match Pinnacle close::

        [{commence_time, home_team, away_team,
          p_home, p_draw, p_away,     # Pinnacle 1X2 decimal odds (None if no h2h)
          ou_line, over, under}]      # Pinnacle main-line O/U (None if no totals)

    Only matches where Pinnacle quoted h2h are returned (need the 1X2 for CLV)."""
    out: list[dict] = []
    for m in (snapshot or {}).get("data") or []:
        pin = _pinnacle(m)
        if not pin:
            continue
        home, away = m.get("home_team"), m.get("away_team")
        ph = pd = pa = None
        oul = over = under = None
        for mk in pin.get("markets") or []:
            if mk.get("key") == "h2h":
                for o in mk.get("outcomes") or []:
                    nm, pr = o.get("name"), o.get("price")
                    if nm == home:
                        ph = pr
                    elif nm == away:
                        pa = pr
                    elif nm == "Draw":
                        pd = pr
            elif mk.get("key") == "totals":
                # main line = the (single) point offered; over/under prices
                for o in mk.get("outcomes") or []:
                    if o.get("name") == "Over":
                        over, oul = o.get("price"), o.get("point")
                    elif o.get("name") == "Under":
                        under = o.get("price")
        if ph and pd and pa:  # need the full 1X2 triple
            out.append({
                "commence_time": m.get("commence_time"),
                "home_team": home, "away_team": away,
                "p_home": ph, "p_draw": pd, "p_away": pa,
                "ou_line": oul, "over": over, "under": under,
            })
    return out
