"""名字错配哨兵 — AF↔Odds API team-name mismatch detector.

The fresher-line overlay (``ingest_odds``) joins each API-Football fixture to the
Odds API Pinnacle line by *normalized team name*. When the two feeds spell a team
differently past ``_norm_team``'s accent-fold (Türkiye/Turkey, VPS/VPS Vaasa, Congo
DR/DR Congo …), the join silently misses and that match keeps the STALE
API-Football line → wrong EV on the card. This bit WC + Veikkausliiga before a user
noticed the stale cards.

The sentinel proactively diffs the two feeds per league so we add a ``_NORM_ALIAS``
entry BEFORE a stale card surprises us. It distinguishes a *name mismatch* (the
fixture IS on the Odds API, one team name differs → fixable with an alias) from
*not covered* (the Odds API simply lacks the fixture → not our bug). Read-only,
fail-soft: any network/parse failure for a league is skipped, never raised.

See [[cross-source-team-name-mismatch]] in memory for the recurring pattern.
"""
from __future__ import annotations

import argparse
import datetime
import logging
from pathlib import Path

log = logging.getLogger(__name__)
_DEFAULT_REPORT = "logs/name_sentinel_latest.txt"


class SentinelBlindError(RuntimeError):
    """探测器自己失明(AF fixtures 全数拉取失败)— 与「扫描通过」严格区分。

    体检 W1 2026-07-15:以前 fetch 失败被吞成空列表 → 「没比赛 = 没 mismatch」
    假绿。哨兵坏了必须坏得响(报告文件写失败 + exit 1),否则监控本身成为盲区。
    """


def _real_lookup(sport_key: str) -> dict:
    from nutmeg.v4.data.sources.odds_api import fetch_pinnacle_lookup
    return fetch_pinnacle_lookup(sport_key, ttl_seconds=3600)


def scan(
    *,
    days: int = 4,
    today: datetime.date | None = None,
    fetch_fixtures=None,
    fetch_lookup=None,
    leagues: list[str] | None = None,
    sport_keys: dict[str, str] | None = None,
    resolve_lid=None,
) -> tuple[list[dict], int, int]:
    """Return ``(mismatches, n_not_covered, n_leagues_scanned)``.

    ``mismatches``: list of ``{league, fixture, date, af_team, oa_suggestion}`` —
    AF teams whose normalized name doesn't reach the Odds API key, but the fixture
    IS on the Odds API under a different name (the actionable, alias-fixable case).
    Network only via the injected fetchers (testable); every league fail-soft.
    """
    from nutmeg.v4.data.sources import api_football
    from nutmeg.v4.data.sources.odds_api import SPORT_KEYS, _norm_team
    fetch_fixtures = fetch_fixtures or api_football.fetch_fixtures_for_date
    fetch_lookup = fetch_lookup or _real_lookup
    sport_keys = sport_keys or SPORT_KEYS
    resolve_lid = resolve_lid or api_football.league_id
    today = today or datetime.date.today()

    # Fixtures fetched ONCE per day (not per league) — the overlay is per-league,
    # but a day's fixtures cover every league.
    day_fx: dict[datetime.date, list] = {}
    n_fetch_failed = 0
    for off in range(days):
        d = today + datetime.timedelta(days=off)
        try:
            day_fx[d] = fetch_fixtures(d) or []
        except Exception:  # noqa: BLE001 — 单日失败可容(下面有全盲闸)
            # 体检 W1 2026-07-15 — 以前静默吞:fixtures 拉不到 = 「没比赛」= 没
            # mismatch = 假绿。单日失败留 log 继续;全部失败在循环后升级为异常。
            log.warning("name sentinel: fixtures fetch failed for %s", d, exc_info=True)
            day_fx[d] = []
            n_fetch_failed += 1
    if days > 0 and n_fetch_failed == days:
        # 哨兵自盲闸:探测器自己坏了必须响,绝不能把「看不见」报成「没问题」。
        raise SentinelBlindError(
            f"AF fixtures 全数拉取失败({days}/{days} 天)— 本次扫描无结论")

    mismatches: list[dict] = []
    not_covered = 0
    scanned = 0
    for code in (leagues or list(sport_keys)):
        sport_key = sport_keys.get(code)
        if not sport_key:
            continue
        try:
            lid = resolve_lid(code)
        except Exception:  # noqa: BLE001 — no AF league id mapping → skip
            continue
        try:
            lk = fetch_lookup(sport_key)
        except Exception:  # noqa: BLE001 — Odds API hiccup → skip this league
            continue
        if not lk:
            continue  # off-season / no OA fixtures
        scanned += 1
        oa_orig: dict[str, str] = {}
        for k, v in lk.items():
            oa_orig.setdefault(k[0], (v or {}).get("home_team"))
            oa_orig.setdefault(k[1], (v or {}).get("away_team"))
        for d, fixtures in day_fx.items():
            diso = d.isoformat()
            same_date = [k for k in lk if k[2] == diso]
            if not same_date:
                continue
            for fx in fixtures:
                if ((fx.get("league") or {}).get("id")) != lid:
                    continue
                teams = fx.get("teams") or {}
                home = (teams.get("home") or {}).get("name")
                away = (teams.get("away") or {}).get("name")
                if not home or not away:
                    continue
                h, a = _norm_team(home), _norm_team(away)
                if (h, a, diso) in lk:
                    continue  # overlay will match → fine
                # Miss. Name mismatch (fixture in OA, one name differs) vs not covered?
                onematch = [k for k in same_date if h in (k[0], k[1]) or a in (k[0], k[1])]
                if not onematch:
                    not_covered += 1
                    continue
                k = onematch[0]
                af_team = home if h not in (k[0], k[1]) else away
                oa_key = k[0] if k[0] not in (h, a) else k[1]
                mismatches.append({
                    "league": code, "fixture": f"{home} vs {away}", "date": diso,
                    "af_team": af_team, "oa_suggestion": oa_orig.get(oa_key),
                })
    return mismatches, not_covered, scanned


def format_report(mismatches: list[dict], not_covered: int, scanned: int, stamp: str) -> str:
    head = [
        f"名字错配哨兵 — {stamp}",
        f"扫描 {scanned} 联赛(有 OA)· 疑似错配 {len(mismatches)} · 未覆盖 {not_covered}",
        "",
    ]
    if not mismatches:
        if scanned == 0:
            # 体检 W1 — 0 联赛可扫(全休赛/OA 无盘/lookup 全失败)是「无结论」,
            # 不是「无错配」;别发 ✅ 把空扫描洗成绿灯。
            head.append("➖ 0 联赛可扫 — 本次无结论(休赛期正常;赛季中连续出现要查 OA)。")
            return "\n".join(head)
        head.append("✅ 无名字错配 — 有 OA 覆盖的赛事都能 join 鲜线。")
        return "\n".join(head)
    head.append("⚠️ 这些 AF 队名 join 不到 Odds API(叠加层会漏 → 卡片陈旧)。加 _NORM_ALIAS:")
    for m in mismatches:
        sg = f' → OA: "{m["oa_suggestion"]}"' if m.get("oa_suggestion") else " → (OA 名未定)"
        head.append(f'  [{m["league"]}] {m["date"]} {m["fixture"]}:  "{m["af_team"]}"{sg}')
    return "\n".join(head)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="AF↔Odds API team-name mismatch sentinel")
    p.add_argument("--days", type=int, default=4)
    p.add_argument("--report", default=_DEFAULT_REPORT)
    p.add_argument("--quiet", action="store_true", help="write the report file only")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        mismatches, not_covered, scanned = scan(days=a.days)
    except SentinelBlindError as exc:
        # 探测失败也要写进 latest 文件(它是持久通道,health_check 读它)——
        # 否则文件停在上次的 ✅,盲跑期间没人知道哨兵瞎了。
        report = f"名字错配哨兵 — {stamp}\n⛔ 探测失败:{exc}\n(这不是绿灯 — 查 AF key/网络)"
        rc = 1
    else:
        report = format_report(mismatches, not_covered, scanned, stamp)
        rc = 0
    try:
        path = Path(a.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report + "\n", encoding="utf-8")
    except OSError:
        pass
    if not a.quiet:
        print(report)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
