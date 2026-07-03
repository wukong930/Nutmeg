"""nutmeg-ingest-jingcai-vote — capture 体彩 官方逐场散户支持比例 → jingcai_vote.

Pulls ``getVoteV1`` (HAD 胜平负 + HHAD 让球) — the GENUINE Chinese-retail crowd
direction (NOT 唯彩/Okooo's 必发(Betfair)-derived 买量, which is sharp money) — and
upserts one row per (match, pool) into ``jingcai_vote``. The source is FORWARD-ONLY
(no history → no backfill), so run DAILY near the 竞彩 freeze to accumulate the
panel; joined later to Pinnacle de-vig P + result it measures the 散户-bias / 软水
question. Read-only / personal / local; a fetch failure just writes 0 rows.
"""
from __future__ import annotations

import argparse
import logging


def harvest_votes_to_db(
    db_path, *, pool_codes: str = "HAD,HHAD", rows_by_pool: dict | None = None
) -> dict:
    """Upsert the current 支持比例 into jingcai_vote. Fetches per pool if
    ``rows_by_pool`` is None. Returns ``{seen, written: {pool: n}}``."""
    from nutmeg.v4.data.sources.sporttery import fetch_vote_support
    from nutmeg.v4.observation.jingcai_vote import parse_vote_row, record_jingcai_vote

    pools = [p.strip().upper() for p in pool_codes.split(",") if p.strip()]
    written: dict[str, int] = {}
    seen = 0
    for pool in pools:
        rows = (rows_by_pool or {}).get(pool) if rows_by_pool is not None \
            else fetch_vote_support(pool)
        rows = rows or []
        seen += len(rows)
        w = 0
        for raw in rows:
            kw = parse_vote_row(raw, pool)
            if kw:
                w += int(record_jingcai_vote(db_path, **kw))
        written[pool] = w
    return {"seen": seen, "written": written}


def watch_alarm_heartbeat(db_path, *, max_age_hours: float = 26.0) -> bool:
    """体检 2026-07-03 P0-2 — mutual watching. The system's ONLY push alarm
    (osascript) rides the tail of the daily_settle chain; if that chain dies,
    the alarm dies WITH it and we're back to "noticed weeks later by accident"
    (the wc_settle precedent). This CLI runs in an INDEPENDENT launchd job
    (sporttery_vote, 3 windows/day), so here we check the age of the
    data_freshness heartbeat file (written by the settle chain 13:00/20:00 →
    normal max gap ~17h; 26h = one missed day + slack) and pop a desktop
    notification if it's stale/missing. data_freshness in turn watches OUR
    table (jingcai_vote) — each job alarms for the other. Fail-soft: the
    watchdog must never break vote capture. Returns True if it alarmed."""
    import subprocess
    from datetime import UTC, datetime
    from pathlib import Path

    from nutmeg.v4.cli.data_freshness import HEARTBEAT_FILENAME
    try:
        hb = Path(db_path).resolve().parent / HEARTBEAT_FILENAME
        if hb.exists():
            age_h = (datetime.now(UTC).timestamp() - hb.stat().st_mtime) / 3600.0
            if age_h <= max_age_hours:
                return False
            msg = f"data_freshness 心跳 {age_h:.0f}h 未更新 — daily_settle 报警链可能整条死了"
        else:
            msg = "data_freshness 心跳文件缺失 — daily_settle 报警链可能没在跑"
        print(f"⚠️ 看门狗: {msg}")
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "⚠️ Nutmeg 报警链心跳"'],
            check=False, capture_output=True, timeout=10)
        return True
    except Exception:  # noqa: BLE001 — watchdog is best-effort by design
        logging.getLogger(__name__).warning("heartbeat watchdog failed", exc_info=True)
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="capture 体彩 散户支持比例 → jingcai_vote")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--pool-codes", default="HAD,HHAD", help="HAD(胜平负),HHAD(让球)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be written")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Run the alarm-chain watchdog FIRST — it must fire even when the vote
    # fetch itself fails (independence is the whole point).
    watch_alarm_heartbeat(args.db)

    from nutmeg.v4.data.sources.sporttery import fetch_vote_support
    from nutmeg.v4.observation.jingcai_vote import parse_vote_row

    pools = [p.strip().upper() for p in args.pool_codes.split(",") if p.strip()]
    rows_by_pool = {p: fetch_vote_support(p) for p in pools}
    seen = sum(len(v) for v in rows_by_pool.values())
    print(f"体彩 支持比例抓取: {seen} 行 ("
          + ", ".join(f"{p}={len(rows_by_pool[p])}" for p in pools) + ")")
    if not seen:
        print("  (端点无数据或失败 — 失败软,未写入)")
        return 0

    if args.dry_run:
        print("\n样例(将写入):")
        for p in pools:
            for raw in (rows_by_pool[p] or [])[:4]:
                kw = parse_vote_row(raw, p)
                if kw:
                    print(f"  [{p}] {kw['home_zh']} vs {kw['away_zh']} {kw['match_date']} "
                          f"· 支持 主{kw['h_support']}/平{kw['d_support']}/客{kw['a_support']}% "
                          f"· 票 {kw['h_count']}/{kw['d_count']}/{kw['a_count']} "
                          f"· EN {kw['home_team']}/{kw['away_team']}")
        print("\n(dry-run — 未写库)")
        return 0

    r = harvest_votes_to_db(args.db, pool_codes=args.pool_codes, rows_by_pool=rows_by_pool)
    print("\n写入 jingcai_vote: "
          + " · ".join(f"{p} {n}" for p, n in r["written"].items()))

    # Co-capture the Pinnacle line from odds_snapshots → locks the 软水 三料 join in
    # one table (散户支持 + 竞彩 SP + Pinnacle). Freeze-time run pins the freshest line.
    from nutmeg.v4.observation.jingcai_vote import backfill_vote_pinnacle
    pin = backfill_vote_pinnacle(args.db)
    print(f"协同 Pinnacle 回填(odds_snapshots → psc_*): {pin} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
