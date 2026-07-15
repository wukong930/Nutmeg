"""nutmeg-score-ev-forward — forward (out-of-sample) test of correct-score +EV flags.

WHY: the backtest can only use API-Football's POST-match cached odds (not closing
lines) and can't model the can't-get-best-line / book-limit frictions, so it
over-states ROI. The V12 study found the trustworthy low-odds slice ≈ break-even
while the headline +71% was a longshot / stale-price artifact. This builds the
only honest test — snapshot the correct-score market for UPCOMING fixtures near
kickoff, settle on the 90' score, and accumulate a real OOS sample.

  --record  for upcoming fixtures, snapshot the +EV flags (replacing any prior
            snapshot for that fixture → the last pre-kickoff capture persists,
            i.e. ≈ closing). Run a few times a day via cron.
  --settle  fill the actual 90' result for finished, unsettled flags.
  --report  ROI / hit-rate / per-EV-bucket / bootstrap CI over settled flags.

Usage (env sourced for the API key):
    set -a && source .env && set +a
    nutmeg-score-ev-forward --record            # today's upcoming fixtures
    nutmeg-score-ev-forward --settle
    nutmeg-score-ev-forward --report
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from datetime import date as _date

from nutmeg.v4.cli.score_ev import ev_flags

DEFAULT_DB = "data/score_ev_forward.db"
UPCOMING = {"NS", "TBD"}
FINISHED = {"FT", "AET", "PEN"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS score_ev_flags (
    fixture_id  INTEGER NOT NULL,
    league      TEXT, home TEXT, away TEXT, kickoff_utc TEXT,
    match_date  TEXT NOT NULL,
    pred_home   INTEGER NOT NULL, pred_away INTEGER NOT NULL,
    model_p     REAL, odds REAL, book TEXT, ev REAL, prior_src TEXT,
    captured_at TEXT NOT NULL,
    actual_home INTEGER, actual_away INTEGER, won INTEGER, settled_at TEXT,
    PRIMARY KEY (fixture_id, pred_home, pred_away)
);
"""


def _conn(db: str) -> sqlite3.Connection:
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    c.execute(SCHEMA)
    # Migrate pre-prior_src DBs in place (SQLite has no ADD COLUMN IF NOT EXISTS).
    if "prior_src" not in {r[1] for r in c.execute("PRAGMA table_info(score_ev_flags)")}:
        c.execute("ALTER TABLE score_ev_flags ADD COLUMN prior_src TEXT")
    return c


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def do_record(args) -> int:
    from nutmeg.v4.data.sources import api_football as af
    from nutmeg.v4.model.market_handicap import DEFAULT_RHO
    rho = DEFAULT_RHO if args.rho is None else args.rho
    # 体检 Wave3 (P1#12 第 3 处) — UTC anchor, NEVER process-local date: the
    # local Asia/Shanghai date rolls at Beijing midnight (=16:00 UTC), so a
    # sleep-catch-up run in the 00:00–07:59 Beijing window would record for
    # the WRONG UTC day (the Spain/Portugal-vanish class; routes._utc_today).
    d = _date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    fx = af.fetch_fixtures_for_date(d, refresh=True)
    upcoming = [f for f in fx
                if ((f.get("fixture") or {}).get("status") or {}).get("short") in UPCOMING]
    now = _now()
    n_fix = n_flag = n_calls = 0
    src_tally: dict[str, int] = {}
    with _conn(args.db) as conn:
        for f in upcoming:
            if n_calls >= args.max_fixtures:
                break
            fid = (f.get("fixture") or {}).get("id")
            if fid is None:
                continue
            try:
                blob = af.fetch_odds(int(fid), refresh=True)
                n_calls += 1
                flags = ev_flags(blob, min_ev=args.min_ev,
                                 max_odds=args.max_odds, rho=rho)
            except Exception:  # noqa: BLE001 — one bad fixture must not abort the run
                continue
            if not flags:
                continue
            league = (f.get("league") or {}).get("name")
            h = ((f.get("teams") or {}).get("home") or {}).get("name")
            a = ((f.get("teams") or {}).get("away") or {}).get("name")
            ko = (f.get("fixture") or {}).get("date")
            # Replace this fixture's prior (unsettled) snapshot → keep the latest
            # pre-kickoff capture only (≈ closing once the cron stops re-touching it).
            conn.execute("DELETE FROM score_ev_flags WHERE fixture_id=? AND won IS NULL", (fid,))
            for fl in flags:
                # 体检 W1 2026-07-15 — 原为 INSERT OR REPLACE:改期重赛(完场→又回
                # UPCOMING)时上面的 DELETE 只清未结算行,REPLACE 撞已结算行会把
                # actual_*/won/settled_at 整行冲掉 = 销毁测量。改 upsert 只更新
                # 捕获列,结算四列不碰。
                conn.execute(
                    "INSERT INTO score_ev_flags (fixture_id,league,home,away,"
                    "kickoff_utc,match_date,pred_home,pred_away,model_p,odds,book,ev,"
                    "prior_src,captured_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(fixture_id,pred_home,pred_away) DO UPDATE SET "
                    "league=excluded.league, home=excluded.home, away=excluded.away, "
                    "kickoff_utc=excluded.kickoff_utc, match_date=excluded.match_date, "
                    "model_p=excluded.model_p, odds=excluded.odds, book=excluded.book, "
                    "ev=excluded.ev, prior_src=excluded.prior_src, "
                    "captured_at=excluded.captured_at",
                    (fid, league, h, a, ko, d.isoformat(), fl["home"], fl["away"],
                     fl["model_p"], fl["odds"], fl["book"], fl["ev"],
                     fl.get("prior_src"), now))
            src = flags[0].get("prior_src") or "?"
            src_tally[src] = src_tally.get(src, 0) + 1
            n_fix += 1
            n_flag += len(flags)
        conn.commit()
    tally = ", ".join(f"{k}×{v}" for k, v in sorted(src_tally.items())) or "—"
    print(f"record {d}: {len(upcoming)} 待开赛 · snapshot {n_fix} 场 / {n_flag} 个 +EV 比分 "
          f"(EV≥{args.min_ev:.0%}, 赔≤{args.max_odds:g}, odds 调用 {n_calls}) · 先验 {tally}")
    return 0


def do_settle(args) -> int:
    from nutmeg.v4.data.sources import api_football as af
    with _conn(args.db) as conn:
        rows = conn.execute(
            "SELECT DISTINCT fixture_id, match_date FROM score_ev_flags WHERE won IS NULL"
        ).fetchall()
        by_date: dict[str, set[int]] = {}
        for r in rows:
            by_date.setdefault(r["match_date"], set()).add(r["fixture_id"])
        n = 0
        now = _now()
        for md, fids in by_date.items():
            try:
                fx = af.fetch_fixtures_for_date(_date.fromisoformat(md), refresh=True)
            except Exception:  # noqa: BLE001
                continue
            for f in fx:
                fid = (f.get("fixture") or {}).get("id")
                st = ((f.get("fixture") or {}).get("status") or {}).get("short")
                g = f.get("goals") or {}
                if fid in fids and st in FINISHED and g.get("home") is not None:
                    gh, ga = int(g["home"]), int(g["away"])
                    cur = conn.execute(
                        "UPDATE score_ev_flags SET actual_home=?, actual_away=?, "
                        "won=CASE WHEN pred_home=? AND pred_away=? THEN 1 ELSE 0 END, "
                        "settled_at=? WHERE fixture_id=? AND won IS NULL",
                        (gh, ga, gh, ga, now, fid))
                    n += cur.rowcount
        conn.commit()
    print(f"settle: 结算了 {n} 个 +EV 比分")
    return 0


def _roi(bets):
    s = len(bets)
    r = sum(o for o, w, _ in bets if w)
    return ((r - s) / s if s else float("nan")), s, sum(w for _, w, _ in bets)


def do_report(args) -> int:
    import numpy as np
    with _conn(args.db) as conn:
        rows = conn.execute(
            "SELECT fixture_id, odds, won, ev, prior_src FROM score_ev_flags "
            "WHERE won IS NOT NULL"
        ).fetchall()
    if not rows:
        print("还没有已结算的 +EV 比分。先跑 --record(每天几次)+ --settle(赛后)攒样本。")
        return 0
    by_fix: dict[int, list] = {}
    src_tally: dict[str, int] = {}
    for r in rows:
        by_fix.setdefault(r["fixture_id"], []).append((r["odds"], r["won"], r["ev"]))
        src_tally[r["prior_src"] or "?"] = src_tally.get(r["prior_src"] or "?", 0) + 1
    allb = [b for v in by_fix.values() for b in v]
    R, N, W = _roi(allb)
    tally = ", ".join(f"{k}×{v}" for k, v in sorted(src_tally.items()))
    print(f"前向 OOS 样本: {len(by_fix)} 场 / {N} 个 +EV 比分注 (已结算) · 先验 {tally}")
    print(f"总 ROI: {R * 100:+.1f}%   命中 {W}/{N} ({W / N * 100:.1f}%)")
    if len(by_fix) >= 20:
        rng = np.random.default_rng(0)
        fids = list(by_fix)
        vals = []
        for _ in range(3000):
            samp = rng.choice(len(fids), len(fids), replace=True)
            bets = [b for k in samp for b in by_fix[fids[k]]]
            if bets:
                s = len(bets)
                vals.append((sum(o for o, w, _ in bets if w) - s) / s)
        lo, hi = np.percentile(vals, [5, 95])
        verdict = "✅ 显著为正" if lo > 0 else "❌ 含 0/负 → 未证明 edge"
        print(f"90% 置信区间(按比赛重采样): [{lo * 100:+.0f}%, {hi * 100:+.0f}%]  → {verdict}")
    else:
        print(f"(样本仅 {len(by_fix)} 场 < 20,暂不算置信区间——继续攒。)")
    for nm, lo, hi in [("+5~30%", 0.05, 0.30), ("+30~100%", 0.30, 1.0), (">100%", 1.0, 9e9)]:
        bb = [b for b in allb if lo <= b[2] < hi]
        if bb:
            rr, nn, ww = _roi(bb)
            print(f"  {nm:>9}: n={nn:4d} 命中{ww}({ww / nn * 100:.1f}%) ROI {rr * 100:+.0f}%")
    print("\n注: 这是 OOS 前向样本(近闭盘快照 + 真实结算),比回测可信。攒够几周再下结论。")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Forward OOS test of correct-score +EV flags")
    ap.add_argument("--db", default=DEFAULT_DB)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--record", action="store_true", help="snapshot upcoming fixtures")
    g.add_argument("--settle", action="store_true", help="settle finished flags")
    g.add_argument("--report", action="store_true", help="ROI + CI over settled flags")
    ap.add_argument("--date", default=None, help="record target date (default today)")
    ap.add_argument("--min-ev", type=float, default=0.05)
    ap.add_argument("--max-odds", type=float, default=80.0)
    ap.add_argument("--max-fixtures", type=int, default=250,
                    help="record: cap odds calls per run (API budget guard)")
    ap.add_argument("--rho", type=float, default=None)
    args = ap.parse_args(argv)
    if args.record:
        return do_record(args)
    if args.settle:
        return do_settle(args)
    return do_report(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
