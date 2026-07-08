"""竞彩 HISTORICAL odds-movement source — getFixedBonusV1 (backfillable, no-auth).

2026-07-09: cracked the official gateway endpoint serving the FULL historical 竞彩
odds-movement series (open→every republish→close) for 胜平负/让球 + exotics + result,
keyed by ``matchId``, back to ~2017. Plain curl, no WAF, no anti-scrape — same
``/gateway/uniform/football/`` route as getMatchCalculatorV1/getVoteV1. This OVERTURNS
「竞彩 SP forward-only」 and de-gates the historical soft-water/S6/freeze-gap backtests
(pre-registered in ``docs/autumn_prereg_analysis_plan.md`` §H, frozen 2026-07-09;
`记忆 jingcai-fixedbonus-history-endpoint`). Read-only, personal analysis, FAIL-SOFT:
any network/parse failure logs a warning and returns None/[] — never raises.
"""
from __future__ import annotations

import contextlib
import logging
import math
import re
import time

import httpx

from nutmeg.v4.data.sources.sporttery import _BASE, _HEADERS, zh_to_canonical

log = logging.getLogger(__name__)

_EP = "/gateway/uniform/football/getFixedBonusV1.qry"
_EP_LIST = "/gateway/uniform/football/getUniformMatchResultV1.qry"


def fetch_match_list(begin_date: str, end_date: str, *, league_id: str = "",
                     page_no: int = 1, page_size: int = 100,
                     timeout: float = 15.0, retries: int = 3) -> dict | None:
    """One page of getUniformMatchResultV1 for the 竞彩 赛果开奖 archive over
    ``[begin_date, end_date]`` (both 'YYYY-MM-DD'), optional ``league_id`` server-side
    filter. Returns the ``value`` dict (``{matchResult, total, pages, pageNo, ...}``),
    or None (logged, never raised). This is the ENUMERATION endpoint (matchId list by
    date) behind ``www.sporttery.cn/jc/zqsgkj/``; archive ≥2020. Params/names verified
    live 2026-07-09 — `matchBeginDate`/`matchEndDate` (NOT startDate) + the full param
    set are all required or the server rejects with 参数不合法."""
    url = f"{_BASE}{_EP_LIST}"
    params = {
        "matchBeginDate": begin_date, "matchEndDate": end_date,
        "leagueId": league_id, "pageSize": page_size, "pageNo": page_no,
        "isFix": 0, "matchPage": 1, "teamId": 0, "everyPages": 10,
    }
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                return None
            return data.get("value") or {}
        except Exception as exc:  # noqa: BLE001 — fail-soft; never raise to caller
            if attempt < retries - 1:
                time.sleep(min(3 * 2 ** attempt, 45))  # 指数退避,riding out 节流
                continue
            log.warning("getUniformMatchResult failed (%s..%s): %s",
                        begin_date, end_date, exc)
            return None
    return None


def parse_match_list(value: dict | None) -> list[dict]:
    """``value.matchResult`` → ``[{match_id, league_id, league_cn, match_date}]``.
    Enumeration only (feed ``match_id`` to ``fetch_fixed_bonus`` for the odds series);
    ``matchDate`` here is the AUTHORITATIVE match date (better than the getFixedBonus
    close-date proxy). [] on empty/missing."""
    out: list[dict] = []
    for r in (value or {}).get("matchResult") or []:
        mid = r.get("matchId")
        if mid is None:
            continue
        out.append({
            "match_id": mid,
            "league_id": r.get("leagueId"),
            "league_cn": r.get("leagueNameAbbr") or r.get("leagueName"),
            "match_date": r.get("matchDate"),
        })
    return out


def iter_match_ids(begin_date: str, end_date: str, *, league_id: str = "",
                   page_size: int = 100, **kw):
    """Paginate getUniformMatchResultV1 over ``[begin_date, end_date]``, yielding each
    enumerated match dict (see ``parse_match_list``). Best-effort: a failed page ends
    iteration with what was collected (partial > nothing)."""
    v = fetch_match_list(begin_date, end_date, league_id=league_id, page_no=1,
                         page_size=page_size, **kw)
    if not v:
        return
    yield from parse_match_list(v)
    try:
        pages = int(v.get("pages") or 1)
    except (TypeError, ValueError):
        pages = 1
    for p in range(2, pages + 1):
        vp = fetch_match_list(begin_date, end_date, league_id=league_id,
                              page_no=p, page_size=page_size, **kw)
        if not vp:
            break
        yield from parse_match_list(vp)


def fetch_fixed_bonus(match_id: int | str, *, timeout: float = 15.0,
                      retries: int = 3) -> dict | None:
    """``value`` dict of getFixedBonusV1 for ``match_id``, or None (logged, never
    raised). None on: network fail / not-success / empty ``oddsHistory`` (a
    non-竞彩 match or an archive-gap id — both return success=True but no had)."""
    url = f"{_BASE}{_EP}"
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params={"matchId": str(match_id)},
                             headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                return None
            val = data.get("value") or {}
            oh = val.get("oddsHistory") or {}
            if not (oh.get("hadList") or oh.get("hhadList")):
                return None  # empty = non-竞彩 / archive gap
            return val
        except Exception as exc:  # noqa: BLE001 — fail-soft; never raise to caller
            if attempt < retries - 1:
                time.sleep(min(3 * 2 ** attempt, 45))  # 指数退避,riding out 节流
                continue
            log.warning("getFixedBonus fetch failed (mid=%s): %s", match_id, exc)
            return None
    return None


def _series(rows: list | None) -> list[dict]:
    """``[{h,d,a,updateDate,updateTime,goalLine,...}]`` → cleaned rows ordered
    open→close (feed order). Drops any row without a plausible 3-way triple
    (同 sporttery ``_odds3``:1.0 < x ≤ 1000,防封盘占位/垃圾)."""
    out: list[dict] = []
    for r in rows or []:
        try:
            h, d, a = float(r["h"]), float(r["d"]), float(r["a"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(x) and 1.0 < x <= 1000.0 for x in (h, d, a)):
            continue
        gl = r.get("goalLine")
        try:
            gl = int(gl) if gl not in (None, "") else None
        except (TypeError, ValueError):
            gl = None
        dt = f"{r.get('updateDate', '')} {r.get('updateTime', '')}".strip()
        out.append({"update_dt": dt, "h": h, "d": d, "a": a, "goal_line": gl})
    return out


def _score(val: dict) -> tuple[int | None, int | None]:
    """(home_goals, away_goals) from ``sectionsNo999`` ('1:1'), else (None, None)."""
    m = re.fullmatch(r"(\d+):(\d+)", (val.get("sectionsNo999") or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def parse_fixed_bonus(val: dict) -> dict | None:
    """getFixedBonusV1 ``value`` → normalized match dict, or None if no usable
    had/hhad series. Shape::

        {match_id, close_date, open_date, league_id, league_cn,
         home_zh, away_zh, home_team, away_team,   # *_team = canonical EN | None
         home_goals, away_goals,                    # None if unplayed/unknown
         single: {'had':0/1,'hhad':0/1},
         series: {'had': [{update_dt,h,d,a,goal_line}, ...],  # open→close
                  'hhad': [...]}}

    NB: getFixedBonus carries NO explicit kickoff/match date — ``close_date`` (last
    publish, ~5min pre-KO) is the match-day proxy; exact kickoff needs a separate
    getMatchHeadV1 call (deferred to the Pinnacle-join step, prereg §H.2)."""
    oh = val.get("oddsHistory") or {}
    had = _series(oh.get("hadList"))
    hhad = _series(oh.get("hhadList"))
    if not (had or hhad):
        return None
    anchor = had or hhad
    single: dict[str, int] = {}
    for s in (oh.get("singleList") or []):
        code = str(s.get("poolCode") or "").lower()
        if code and s.get("single") is not None:
            with contextlib.suppress(TypeError, ValueError):
                single[code] = int(s["single"])
    home_zh = oh.get("homeTeamAbbName") or oh.get("homeTeamAllName")
    away_zh = oh.get("awayTeamAbbName") or oh.get("awayTeamAllName")
    hg, ag = _score(val)
    return {
        "match_id": oh.get("matchId"),
        "open_date": (anchor[0]["update_dt"].split(" ")[0] or None),
        "close_date": (anchor[-1]["update_dt"].split(" ")[0] or None),
        "league_id": oh.get("leagueId"),
        "league_cn": oh.get("leagueAbbName") or oh.get("leagueAllName"),
        "home_zh": home_zh, "away_zh": away_zh,
        "home_team": zh_to_canonical(home_zh), "away_team": zh_to_canonical(away_zh),
        "home_goals": hg, "away_goals": ag,
        "single": single,
        "series": {"had": had, "hhad": hhad},
    }


def fetch_and_parse(match_id: int | str, **kw) -> dict | None:
    """Convenience: ``fetch_fixed_bonus`` then ``parse_fixed_bonus``; None if either
    yields nothing (a gap id / non-竞彩 match)."""
    val = fetch_fixed_bonus(match_id, **kw)
    return parse_fixed_bonus(val) if val else None
