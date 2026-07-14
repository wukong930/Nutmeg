"""nutmeg-registry-coverage — 「注册表/词典/字段清单即开关」的结构性疫苗.

体检 2026-07-03 元结论:24 条 P1 里过半是同一病根 — a league/team missing from
ONE registry (SPORT_KEYS / zh↔EN dict / AF league IDs / team tables) silently
degrades that slice, and the existing alarms only cover "全无" not "半坏"
(韩职 SP、韩职 sport key、瑞超队名、德乙 14/19 打不中 … all instances).

This tool diffs EVERY cell of the (cron league × registry) grid against the
LIVE API-Football team tables:

  • AF league-id registered        (league_id resolves)
  • Odds-API sport key registered  (SPORT_KEYS — the fresher-line overlay +
                                    closing-anchor reach)
  • AF team table non-empty        (current season; empty = AF not published
                                    yet OR a cached-empty bug)
  • zh↔EN dict reachability        (every AF team name reachable from some
                                    竞彩 中文名 through sporttery's reverse map
                                    + _EN_OVERRIDES — the invisible second
                                    failure mode: row written, join dead)

Run it after ANY dict/registry edit and let health_check.sh run it weekly.
Read-only; uses the AF cache (network only when a table is missing/stale-empty
per the fetch TTL, or with --refresh).

Exit code: 0 = no hard gaps (empty tables are WARN — AF publishes rosters on
its own schedule); 1 with --gate when any registry cell is missing or any
published team is dict-unreachable.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

# The cron league set — MUST mirror LEAGUES_EUROPEAN + LEAGUES_ASIAN in
# scripts/setup_local_pipeline.sh (tests/v4/test_registry_coverage.py has a
# tripwire that parses the script and asserts equality, so a cron-league edit
# that forgets this list goes red).
CRON_LEAGUES: tuple[str, ...] = (
    "EPL", "ESP_LA_LIGA", "ITA_SERIE_A", "GER_BUNDESLIGA", "FRA_LIGUE_1",
    "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B",
    "GER_2_BUNDESLIGA", "FRA_LIGUE_2", "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA",
    "BEL_PRO_LEAGUE",
    "JPN_J1",
)

# 竞彩-common market-mode leagues (V12 W8 expansion — served via Pinnacle
# de-vig, no model). 2026-07-04 lesson: 瑞超 sat OUTSIDE the coverage scope,
# and 竞彩 listed 7 matches whose zh spellings missed the dict → 6 silently
# dropped. NB the offline zh-reachability check can be GREEN while 竞彩's own
# spellings still miss (no 竞彩 roster endpoint exists to diff against) — the
# ingest-time 过半丢失 alarm is the catcher for that; this scope extension
# catches the OTHER cells (sport key / AF id / empty table / EN drift).
MARKET_MODE_LEAGUES: tuple[str, ...] = (
    "NOR_ELITESERIEN", "SWE_ALLSVENSKAN", "FIN_VEIKKAUSLIIGA",
    "DNK_SUPERLIGA", "KOR_K_LEAGUE_1", "JPN_J2", "AUS_A_LEAGUE",
    "SCO_PREMIERSHIP", "TUR_SUPER_LIG", "SUI_SUPER_LEAGUE",
    "USA_MLS", "BRA_SERIE_A",   # 补(2026-07-14)美洲市场模式
)


def check_league(league: str, *, refresh: bool = False) -> dict:
    """One coverage row: registry cells + dict-unreachable AF team names."""
    import contextlib

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.data.sources.api_football import (
        ApiFootballError,
        fetch_teams_for_league_season,
        league_id,
        season_for_date,
    )
    from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES, _ZH_TO_EN

    row: dict = {"league": league, "af_id": None, "sport_key": None,
                 "n_teams": None, "unreachable": [], "error": None}
    with contextlib.suppress(Exception):  # missing registry entry IS the finding
        row["af_id"] = league_id(league)
    row["sport_key"] = odds_api.SPORT_KEYS.get(league)
    if row["af_id"] is None:
        return row
    season = season_for_date(datetime.now(UTC).date(), league)
    try:
        teams = fetch_teams_for_league_season(league, season, refresh=refresh)
    except ApiFootballError as e:
        row["error"] = str(e)[:120]
        return row
    names = sorted(t["team"]["name"] for t in teams)
    row["n_teams"] = len(names)
    reachable = {_EN_OVERRIDES.get(en, en) for en in _ZH_TO_EN.values()}
    row["unreachable"] = [n for n in names if n not in reachable]
    return row


def run(leagues, *, refresh: bool = False) -> tuple[list[dict], list[str], list[str]]:
    """→ (rows, hard_gaps, warnings). Hard gap = a registry cell missing or a
    published team the dict can't reach; warning = empty/unfetched table."""
    rows, gaps, warns = [], [], []
    for lg in leagues:
        r = check_league(lg, refresh=refresh)
        rows.append(r)
        if r["af_id"] is None:
            gaps.append(f"{lg}: AF league-id 未注册 (_DOMESTIC_LEAGUE_IDS)")
        if r["sport_key"] is None:
            # A missing sport key is only a HARD gap for cron leagues (the
            # fresher-line overlay/closing anchor need it). Market-mode
            # leagues price off the AF mirror by design — warn, don't gate.
            if lg in CRON_LEAGUES:
                gaps.append(f"{lg}: Odds-API sport key 未注册 (SPORT_KEYS)")
            else:
                warns.append(f"{lg}: 无 Odds-API sport key (市场模式走 AF 镜像, 设计内)")
        if r["error"]:
            warns.append(f"{lg}: AF /teams 拉取失败 — {r['error']}")
        elif r["n_teams"] == 0:
            warns.append(f"{lg}: AF 队表为空 (当季未发布? TTL 会自动重试)")
        if r["unreachable"]:
            gaps.append(
                f"{lg}: {len(r['unreachable'])}/{r['n_teams']} 队 zh 字典打不中 → "
                + ", ".join(r["unreachable"][:6])
                + (" …" if len(r["unreachable"]) > 6 else "")
            )
    return rows, gaps, warns


def render(rows: list[dict], gaps: list[str], warns: list[str]) -> str:
    lines = [f"# 注册表覆盖率 diff (cron 联赛 × SPORT_KEYS × AF 队表 × zh 字典) "
             f"— {datetime.now(UTC).date()}", ""]
    for r in rows:
        ok_id = "✓" if r["af_id"] else "✗"
        ok_sk = "✓" if r["sport_key"] else "✗"
        if r["error"]:
            teams = "拉取失败"
        elif r["n_teams"] is None:
            teams = "—"
        elif r["n_teams"] == 0:
            teams = "空表⚠"
        else:
            teams = f"{r['n_teams']}队"
        dic = ("—" if not r["n_teams"]
               else ("✓ 全可达" if not r["unreachable"]
                     else f"✗ {len(r['unreachable'])} 打不中"))
        lines.append(f"  {r['league']:22} AF_id {ok_id} · sport_key {ok_sk} · "
                     f"队表 {teams:8} · zh字典 {dic}")
    lines.append("")
    if gaps:
        lines.append("硬缺口 (该切片已静默降级):")
        lines += [f"  ✗ {g}" for g in gaps]
    if warns:
        lines.append("警告:")
        lines += [f"  ⚠ {w}" for w in warns]
    if not gaps and not warns:
        lines.append("判定: ✓ 注册表全格覆盖,无静默降级切片。")
    elif not gaps:
        lines.append("判定: ✓ 无硬缺口 (仅待发布队表)。")
    else:
        lines.append("判定: ✗ 有硬缺口 — 修对应注册表/字典后重跑。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="注册表覆盖率 diff — 缺格即报")
    p.add_argument("--leagues", default=None,
                   help="逗号分隔联赛码 (默认 = cron 全集)")
    p.add_argument("--refresh", action="store_true", help="强制重拉 AF 队表")
    p.add_argument("--gate", action="store_true",
                   help="有硬缺口时 exit 1 (给 health_check/cron 用)")
    args = p.parse_args(argv)

    leagues = ([s.strip() for s in args.leagues.split(",") if s.strip()]
               if args.leagues else list(CRON_LEAGUES) + list(MARKET_MODE_LEAGUES))
    rows, gaps, warns = run(leagues, refresh=args.refresh)
    print(render(rows, gaps, warns))
    return 1 if (args.gate and gaps) else 0


if __name__ == "__main__":
    sys.exit(main())
