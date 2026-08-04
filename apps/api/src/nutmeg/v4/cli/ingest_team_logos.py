"""nutmeg-ingest-team-logos — download team logo PNGs from API-Football.

V11 P1-FE#2 Day 2 — one-shot ingest. For each (league, season) pair,
calls API-Football ``/teams`` to harvest logo URLs, then downloads each
PNG to ``data/external/team_logos/<slug>.png``.

Usage:

    # Single league
    nutmeg-ingest-team-logos --league EPL --season 2024

    # Top-5 European leagues (most common case)
    nutmeg-ingest-team-logos \\
        --league EPL --league ESP_LA_LIGA --league ITA_SERIE_A \\
        --league GER_BUNDESLIGA --league FRA_LIGUE_1 \\
        --season 2024

API budget:
    - 1 call per (league, season) for the team list
    - 1 download per team (cached; skips if already downloaded)
    Total for top-5 leagues + 2024-25 season ≈ 5 + 96 = 101 calls.
    Negligible on API-Football Pro / Tier 2 plans.

Logos already on disk are skipped (idempotent re-runs).

--------------------------------------------------------------------------
``--from-fixture-cache`` — 第二个来源(2026-08-04)
--------------------------------------------------------------------------
``/teams?league=<杯赛>`` **只返回正赛名单**。实测 UCL 2026 给 36 队,而资格赛
的 ``Olympiakos Piraeus`` / ``Sparta Praha`` 已经在盘面上了却不在这 36 个里 ⇒
按 /teams 补队徽,**每年资格赛都会漏一批**,而且症状是「有的队没圆标」这种
没人会当 bug 报的样子。

已缓存的 ``/fixtures`` 响应每行都带 ``teams.{home,away}.logo``,覆盖包括资格赛
在内的所有实际出场球队(实测 8,374 支)。本模式从那里取 URL,**0 次 API-Football
调用**(media.api-sports.io 是图床,不吃配额)。

⚠️ 缓存里 7,405 支没有本地 PNG —— 全下是错的。所以本模式**强制**按
「会出现在盘面上的人口」过滤:观测库 ``odds_snapshots`` + ``jingcai_sp`` 里出现过
的队名。这和本项目「统计量只在会下注的人口上算」是同一条纪律。
国家队(``lookup_elo_code`` 认得的)跳过 —— 面板给它们渲染国旗 emoji,不是圆标。
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code
from nutmeg.v4.data.sources import api_football
from nutmeg.v4.data.team_logos import logo_path

log = logging.getLogger("ingest_team_logos")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def _download_logo(url: str, dest: Path, *, timeout: float = 15.0) -> bool:
    """Download a single logo. Returns True on success, False on failure.

    Skips if dest already exists (idempotent).
    """
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            r = c.get(url)
        if r.status_code != 200:
            log.warning("logo HTTP %s for %s", r.status_code, url)
            return False
        # Sniff content-type briefly — accept image/*; reject HTML error pages
        ctype = r.headers.get("content-type", "")
        if not ctype.startswith("image/"):
            log.warning("non-image content-type %s for %s", ctype, url)
            return False
        dest.write_bytes(r.content)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("logo download failed %s → %s", url, e)
        return False


def _extract_team_records(
    teams_response: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """From the /teams response, return (api_name, logo_url) tuples.

    API-Football payload shape:
        [{ "team": { "id": int, "name": str, "logo": str }, "venue": {...} }, …]
    """
    out: list[tuple[str, str]] = []
    for rec in teams_response:
        t = rec.get("team") or {}
        name = t.get("name")
        logo = t.get("logo")
        if name and logo:
            out.append((str(name), str(logo)))
    return out


def _logo_urls_from_fixture_cache(api_cache_dir: Path) -> dict[str, str]:
    """{team name: logo URL} harvested from every cached ``/fixtures`` response.

    Covers whoever actually played — including cup qualifiers that ``/teams``
    omits. Reads only; costs no API quota.
    """
    out: dict[str, str] = {}
    for f in (api_cache_dir / "_fixtures").rglob("*.json"):
        try:
            payload = json.loads(f.read_text())
        except (OSError, ValueError):
            continue  # a truncated/partial cache file must not abort the sweep
        items = payload if isinstance(payload, list) else (payload.get("response") or [])
        for fx in items:
            if not isinstance(fx, dict):
                continue
            for side in ("home", "away"):
                t = ((fx.get("teams") or {}).get(side)) or {}
                if t.get("name") and t.get("logo"):
                    out.setdefault(str(t["name"]), str(t["logo"]))
    return out


def _bettable_team_names(db_path: Path) -> set[str]:
    """Team names that have appeared on a board — the population worth a crest.

    ``odds_snapshots`` + ``jingcai_sp``; a missing table is not fatal (a fresh
    checkout has neither).
    """
    names: set[str] = set()
    if not db_path.exists():
        return names
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for table in ("odds_snapshots", "jingcai_sp"):
            for col in ("home_team", "away_team"):
                try:
                    names |= {
                        r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM {table}") if r[0]
                    }
                except sqlite3.Error:
                    continue
    finally:
        conn.close()
    return names


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V11 P1-FE#2 — download team logos from API-Football"
    )
    p.add_argument(
        "--league",
        action="append",
        help="V4 canonical league code (repeatable). E.g. --league EPL --league ESP_LA_LIGA",
    )
    p.add_argument(
        "--season",
        type=int,
        help="Season start year (e.g. 2024 for 2024-25)",
    )
    p.add_argument(
        "--from-fixture-cache",
        action="store_true",
        help="Harvest logo URLs from cached /fixtures instead of /teams (0 API calls). "
             "Covers cup qualifiers that /teams omits. Filtered to the bettable "
             "population in --observation-db; national teams are skipped (flag emoji).",
    )
    p.add_argument(
        "--observation-db",
        default="data/v4_observation.db",
        help="Observation DB supplying the bettable population for --from-fixture-cache",
    )
    p.add_argument(
        "--out-dir",
        default="data/external/team_logos",
        help="Where to save logo PNGs (default: data/external/team_logos)",
    )
    p.add_argument(
        "--api-cache-dir",
        default="data/external/api_football",
        help="API-Football cache dir for /teams responses",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch /teams responses (does NOT re-download already-cached logos)",
    )
    p.add_argument(
        "--throttle-ms",
        type=int,
        default=200,
        help="Delay between logo downloads in milliseconds (default 200)",
    )
    args = p.parse_args(argv)
    if not args.from_fixture_cache and not (args.league and args.season):
        p.error("--league and --season are required unless --from-fixture-cache is given")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    api_cache_dir = Path(args.api_cache_dir)

    total_teams = 0
    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    if args.from_fixture_cache:
        urls = _logo_urls_from_fixture_cache(api_cache_dir)
        pop = _bettable_team_names(Path(args.observation_db))
        # Report every narrowing step. A mode that silently drops 7k names
        # would read as "covered everything" when it covered 0.3% of them.
        log.info("[fixture-cache] %d teams with a logo URL", len(urls))
        log.info("[fixture-cache] %d names in the bettable population", len(pop))
        cand = {n: u for n, u in urls.items() if n in pop}
        nations = {n for n in cand if lookup_elo_code(n) is not None}
        log.info(
            "[fixture-cache] %d in both; skipping %d national teams (flag emoji) → %d to try",
            len(cand), len(nations), len(cand) - len(nations),
        )
        unresolved = sorted(n for n in pop if not logo_path(n, cache_dir=out_dir).exists()
                            and n not in urls)
        if unresolved:
            log.info("[fixture-cache] no URL anywhere for %d name(s): %s",
                     len(unresolved), ", ".join(unresolved))
        records = sorted((n, u) for n, u in cand.items() if n not in nations)
    else:
        records = []

    for api_name, url in records:
        total_teams += 1
        dest = logo_path(api_name, cache_dir=out_dir)
        if dest.exists() and dest.stat().st_size > 0:
            total_skipped += 1
            continue
        if _download_logo(url, dest):
            total_downloaded += 1
            log.info("  ✓ %s → %s", api_name, dest.name)
        else:
            total_failed += 1
        if args.throttle_ms > 0:
            time.sleep(args.throttle_ms / 1000.0)

    for league in args.league or []:
        log.info("[%s/%d] fetching team list…", league, args.season)
        try:
            resp = api_football.fetch_teams_for_league_season(
                league,
                args.season,
                cache_dir=api_cache_dir,
                refresh=args.refresh,
            )
        except api_football.ApiFootballError as e:
            log.error("[%s] %s — skipping", league, e)
            continue

        records = _extract_team_records(resp)
        log.info("[%s/%d] %d teams from /teams", league, args.season, len(records))

        for api_name, url in records:
            total_teams += 1
            # Save under the API name's slug. Dashboard does the same
            # `slug(home_team)` lookup at render time. Cases where the
            # V4 canonical name slugs to something different fall back
            # to the 2-letter initials circle (still looks polished).
            dest = logo_path(api_name, cache_dir=out_dir)
            if dest.exists() and dest.stat().st_size > 0:
                total_skipped += 1
                continue
            ok = _download_logo(url, dest)
            if ok:
                total_downloaded += 1
                log.info("  ✓ %s → %s", api_name, dest.name)
            else:
                total_failed += 1
            if args.throttle_ms > 0:
                time.sleep(args.throttle_ms / 1000.0)

    log.info("=" * 60)
    log.info("Total teams seen:    %d", total_teams)
    log.info("Newly downloaded:    %d", total_downloaded)
    log.info("Skipped (cached):    %d", total_skipped)
    log.info("Failed:              %d", total_failed)
    log.info("Logo cache:          %s", out_dir.resolve())
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
