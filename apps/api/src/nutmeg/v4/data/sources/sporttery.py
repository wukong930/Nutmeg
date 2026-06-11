"""中国体育彩票 (竞彩) odds source — the soft-book SP feed.

竞彩 publishes its frozen SP (胜平负/让球/比分/半全场) through a PUBLIC, no-auth
consumer JSON endpoint used by the official site/app:

    https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry

This is the OTHER gateway route — the ``/gateway/jc/...`` one sits behind a
Tencent WAF (403 from any non-browser client), but ``/gateway/uniform/...`` is
served cleanly to plain HTTP clients, even from a foreign datacenter IP. No
cookie, no token, no WAF circumvention — we read the same public odds the app
shows everyone.

Used ONLY for personal, local, low-frequency analysis (the 竞彩 staleness map).
Read-only — never touches the user's betting account. FAIL-SOFT by design: any
network/parse/endpoint-change failure logs a warning and returns ``[]`` so a
broken scrape can never take down the rest of the pipeline. The endpoint is
undocumented and internal — treat a sudden empty/changed response as "they moved
it", not an error to crash on.
"""
from __future__ import annotations

import contextlib
import json
import logging
import time
from pathlib import Path

import httpx

from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH

log = logging.getLogger(__name__)

_BASE = "https://webapi.sporttery.cn"
_ENDPOINT = "/gateway/uniform/football/getMatchCalculatorV1.qry"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.lottery.gov.cn/",
    "Origin": "https://www.lottery.gov.cn",
}
_DEFAULT_CACHE = "data/external/sporttery"

# 竞彩 中文全名 → our canonical (API-Football English) name, reversed from the
# display dict (740 entries → ~98% of 竞彩 teams). A few 竞彩-only names the dict
# lacks can be patched here; unmapped teams are skipped (logged) by the ingest.
_ZH_TO_EN: dict[str, str] = {}
for _en, _zh in TEAM_NAME_ZH.items():
    _ZH_TO_EN.setdefault(_zh, _en)
_ZH_OVERRIDES: dict[str, str] = {
    # 竞彩-only Chinese names absent from TEAM_NAME_ZH (extend as e.g. 刚果(金) surface)
}
_ZH_TO_EN.update(_ZH_OVERRIDES)

# TEAM_NAME_ZH's English keys don't all match the LIVE convention odds_snapshots /
# the frontend use (API-Football names), so a few 竞彩 rows wouldn't join the
# Pinnacle line + settler. Correct the measured synonym gaps (体检 2026-06-12,
# diffed against the live name universe). Extend when a new 竞彩 row reports
# no_close despite a played match.
_EN_OVERRIDES: dict[str, str] = {
    # National teams (WC) — TEAM_NAME_ZH's English came from the elo source, which
    # names them differently from the live WC gather.
    "Korea Republic": "South Korea",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Cape Verde": "Cape Verde Islands",
    "Turkey": "Türkiye",
    # Club leagues — the gather stores RAW API-Football names (club prefixes /
    # accents / abbreviations); sporttery's reverse-map output is the cleaned
    # form. Pre-validated against fetch_teams_for_league_season over the top-5 +
    # 英冠/葡超 (体检 2026-06-12, 0 conflicts / 0 unmatched) so 竞彩 league rows
    # join the Pinnacle line when the European season resumes. Same offline diff
    # extends it for any new league.
    "Augsburg": "FC Augsburg",
    "Bayern Munich": "Bayern München",
    "Bochum": "VfL Bochum",
    "Borussia Monchengladbach": "Borussia Mönchengladbach",
    "Braga": "SC Braga",
    "Brest": "Stade Brestois 29",
    "Elversberg": "SV Elversberg",
    "Estrela Amadora": "Estrela",
    "Freiburg": "SC Freiburg",
    "Gil Vicente": "GIL Vicente",
    "Heidenheim": "1. FC Heidenheim",
    "Hoffenheim": "1899 Hoffenheim",
    "Mainz 05": "FSV Mainz 05",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Oxford": "Oxford United",
    "Paris SG": "Paris Saint Germain",
    "Porto": "FC Porto",
    "Roma": "AS Roma",
    "Saint-Etienne": "Saint Etienne",
    "Sheffield United": "Sheffield Utd",
    "St. Pauli": "FC St. Pauli",
    "Verona": "Hellas Verona",
    "Vitoria Guimaraes": "Guimaraes",
    "Wolfsburg": "VfL Wolfsburg",
}


def zh_to_canonical(zh_name: str | None) -> str | None:
    """竞彩 Chinese full name → our canonical English name (matching the live
    odds_snapshots / settler convention), or None if unmapped."""
    if not zh_name:
        return None
    en = _ZH_TO_EN.get(zh_name.strip())
    return _EN_OVERRIDES.get(en, en) if en else None


def _cache_path(pool_codes: str, channel: str, cache_dir: str | Path) -> Path:
    d = Path(cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    safe = pool_codes.replace(",", "-")
    return d / f"matchcalc_{safe}_{channel}.json"


def _request(
    pool_codes: str,
    channel: str,
    *,
    cache_dir: str | Path,
    refresh: bool,
    ttl_seconds: int | None,
    timeout: float = 15.0,
    retries: int = 3,
) -> dict | None:
    """GET the uniform endpoint with TTL cache + retries. Returns the parsed
    JSON dict, or None on any failure (logged, never raised)."""
    cache = _cache_path(pool_codes, channel, cache_dir)
    if not refresh and cache.exists() and ttl_seconds is not None:
        age = time.time() - cache.stat().st_mtime
        if age < ttl_seconds:
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass  # corrupt cache → fall through to a live fetch

    url = f"{_BASE}{_ENDPOINT}"
    params = {"poolCode": pool_codes, "channel": channel}
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                log.warning("sporttery API not success: %s", data.get("errorMessage"))
                return None
            with contextlib.suppress(OSError):
                cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except Exception as exc:  # noqa: BLE001 — fail-soft; never raise to the caller
            if attempt < retries - 1:
                time.sleep(1.0 + attempt)
                continue
            log.warning("sporttery fetch failed (%s): %s", url, exc)
            return None
    return None


def _odds3(pool: dict | None):
    """(h, d, a) floats from a had/hhad pool, or None if incomplete."""
    if not pool:
        return None
    try:
        h, d, a = float(pool["h"]), float(pool["d"]), float(pool["a"])
    except (KeyError, TypeError, ValueError):
        return None
    return (h, d, a)


def fetch_lottery_matches(
    *,
    pool_codes: str = "had,hhad",
    channel: str = "c",
    refresh: bool = False,
    ttl_seconds: int | None = 3600,
    cache_dir: str | Path = _DEFAULT_CACHE,
) -> list[dict]:
    """Current 竞彩 football matches with frozen SP. Each dict:
    ``{match_date, match_num, league_cn, home_cn, away_cn, home_en, away_en,
    had: (h,d,a)|None, hhad: (h,d,a,goalLine)|None}``. ``*_en`` is the canonical
    English name (None if unmapped). Returns [] on any failure (fail-soft)."""
    data = _request(pool_codes, channel, cache_dir=cache_dir, refresh=refresh,
                    ttl_seconds=ttl_seconds)
    if not data:
        return []
    out: list[dict] = []
    try:
        for grp in data.get("value", {}).get("matchInfoList", []) or []:
            for g in (grp.get("subMatchList") or []):
                had = _odds3(g.get("had"))
                hhad_pool = g.get("hhad") or {}
                hhad3 = _odds3(hhad_pool)
                hhad = None
                if hhad3 is not None:
                    try:
                        line = int(hhad_pool.get("goalLine"))
                    except (TypeError, ValueError):
                        line = None
                    if line is not None:
                        hhad = (*hhad3, line)
                home_cn = g.get("homeTeamAllName")
                away_cn = g.get("awayTeamAllName")
                out.append({
                    "match_date": g.get("matchDate"),
                    "match_num": g.get("matchNumStr"),
                    "league_cn": g.get("leagueAbbName") or g.get("leagueAllName"),
                    "home_cn": home_cn, "away_cn": away_cn,
                    "home_en": zh_to_canonical(home_cn),
                    "away_en": zh_to_canonical(away_cn),
                    "had": had, "hhad": hhad,
                })
    except Exception:  # noqa: BLE001 — a parse failure must not raise
        log.warning("sporttery parse failed", exc_info=True)
        return []
    return out
