"""nutmeg-polymarket-gaps — READ-ONLY Polymarket mispricing detector.

Enumerates Polymarket soccer GAME markets, matches each to an API-Football
fixture, de-vigs Pinnacle's 1X2 → fair ``q``, compares to the Polymarket ASK
``p`` → EV = q/p − 1, confidence-tiers each gap (favorite-flip → excluded), and
logs the series so we can later MEASURE whether the edges were real.

HONEST BY CONSTRUCTION — this places NO orders. A surfaced gap is **+EV that
CARRIES RISK, not risk-free arbitrage**, and ``q`` is only as good as the
(possibly stale) Pinnacle line behind it. Most liquid Polymarket prices are
efficient (≈ the sharp), so empty/low-edge output is the expected, honest result.

Examples:
    # Preview the next 3 days of gaps, write nothing
    nutmeg-polymarket-gaps --days 3 --dry-run

    # Log gaps + settle finished ones (cron-friendly, idempotent)
    nutmeg-polymarket-gaps --days 3

    # Only show high-confidence +EV ≥ 5%
    nutmeg-polymarket-gaps --days 3 --dry-run --min-ev 0.05 --tier high
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging

log = logging.getLogger("nutmeg-polymarket-gaps")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

_BANNER = (
    "Polymarket 错价探测(只读) — +EV ≠ 无风险套利;q 来自可能过期的 Pinnacle 去 vig。"
    "不接钱包、不下单。"
)
_SPEC_ZH = {"HOME_WIN": "主胜", "AWAY_WIN": "客胜", "DRAW": "平局",
            "HANDICAP_HOME": "让主", "HANDICAP_AWAY": "让客", "OVER": "大", "UNDER": "小"}
_TIER_RANK = {"excluded": 0, "low": 1, "medium": 2, "high": 3}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only Polymarket mispricing detector")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--days", type=int, default=3, help="Days ahead to scan (default 3)")
    ap.add_argument("--min-ev", type=float, default=0.0,
                    help="Only DISPLAY gaps with EV ≥ this (logging records all)")
    ap.add_argument("--tier", choices=["low", "medium", "high"], default=None,
                    help="Only DISPLAY gaps at this confidence tier or above")
    ap.add_argument("--no-settle", action="store_true", help="Skip the settle pass")
    ap.add_argument("--dry-run", action="store_true", help="Print only; write nothing")
    ap.add_argument("--report-unmatched", action="store_true",
                    help="Also print Polymarket events that did not match a fixture")
    args = ap.parse_args(argv)

    from nutmeg.v4.data.polymarket_match import collect_matched_games
    from nutmeg.v4.data.sources import api_football as af
    from nutmeg.v4.data.sources import polymarket as pm
    from nutmeg.v4.model.polymarket_gap import gaps_for_game, sort_gaps
    from nutmeg.v4.observation.polymarket_gaps import (
        ensure_polymarket_gaps_table,
        record_polymarket_gap,
        settle_polymarket_gaps,
    )

    log.info(_BANNER)
    today = dt.datetime.now(dt.UTC).date()
    end = today + dt.timedelta(days=max(1, args.days))

    try:
        events = pm.fetch_soccer_game_events(
            start_date_min=today.isoformat(), end_date=end.isoformat(),
            refresh=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Polymarket fetch failed: %s", exc)
        return 1
    log.info("Polymarket soccer game events: %d", len(events))

    matched, unmatched = collect_matched_games(
        events, lambda d: af.fetch_fixtures_for_date(d),
        report_unmatched=args.report_unmatched,
    )
    log.info("matched to fixtures: %d (skipped/excluded: %d)", len(matched), len(unmatched))

    all_gaps = []
    for game in matched:
        all_gaps.extend(gaps_for_game(
            game,
            fetch_odds=lambda fid: af.fetch_odds(fid),
            fetch_book=lambda tok: pm.fetch_orderbook(tok),
        ))
    all_gaps = sort_gaps(all_gaps)
    log.info("gaps computed (matched games with a Pinnacle line): %d", len(all_gaps))

    # Persist EVERY gap (the measurement denominator), regardless of EV/tier.
    if not args.dry_run:
        ensure_polymarket_gaps_table(args.db)
        # 逐条记账:拒写是 fail-soft(返回 False + warning),不记就等于没装 —— 一次
        # 静默的全量拒写会长得和「今天没比赛」一模一样。
        written = sum(1 for g in all_gaps if record_polymarket_gap(args.db, g))
        rejected = len(all_gaps) - written
        log.info("logged %d gaps to %s", written, args.db)
        if rejected:
            log.warning("盘中价拒写 %d/%d 条(观测时刻已过开球,见 observation/"
                        "polymarket_gaps 模块头)", rejected, len(all_gaps))

    # Display filtered.
    floor = _TIER_RANK.get(args.tier, 0)
    shown = [g for g in all_gaps
             if g.ev >= args.min_ev and _TIER_RANK[g.confidence_tier] >= floor]
    if not shown:
        log.info("no gaps to display at EV≥%.0f%% tier≥%s — this is the honest, "
                 "common result (liquid Polymarket ≈ efficient).",
                 args.min_ev * 100, args.tier or "low")
    else:
        print("\n  比赛 / 结果        | 公允q  Poly ask   EV     置信   深度$   新鲜  原因")
        print("  " + "-" * 84)
        for g in shown:
            fresh = f"{g.freshness_hours:.0f}h" if g.freshness_hours is not None else "?"
            match = f"{g.home_team[:9]:9}v{g.away_team[:9]:9}"
            spec = _SPEC_ZH.get(g.outcome_spec, g.outcome_spec)
            if g.line is not None:
                _f = "+g" if g.outcome_spec.startswith("HANDICAP") else "g"
                spec = f"{spec}{g.line:{_f}}"
            why = ",".join(g.reasons) or "-"
            print(f"  {match} {spec:8}| {g.q_fair*100:4.1f}%  {g.poly_ask:.2f}  "
                  f"{g.ev:+6.1%}  {g.confidence_tier:8} {g.depth_usd:6.0f} {fresh:4} {why}")
        print(f"\n  显示 {len(shown)}/{len(all_gaps)} 条。+EV 含风险,非套利。")

    if args.report_unmatched and unmatched:
        from collections import Counter
        rc = Counter(u["reason"].split(":")[0] for u in unmatched)
        log.info("unmatched reasons: %s", dict(rc))

    if not args.no_settle and not args.dry_run:
        n = settle_polymarket_gaps(args.db)
        log.info("settled %d gaps", n)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
