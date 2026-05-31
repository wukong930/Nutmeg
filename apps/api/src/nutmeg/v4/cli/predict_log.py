"""nutmeg-predict-log — V12 W8j.

Log the model's 1X2 prediction for every UPCOMING model-board match (no bet,
no 竞彩 SP), then settle finished ones. Powers nutmeg-predict-report
(hit-rate / calibration / vs-Pinnacle).

竞彩 lists few games, so most matches the user asks about are off-竞彩 — this
tracks whether the model's PREDICTION is good, decoupled from betting ROI.

Idempotent + cron-friendly: re-run daily. Re-logging an upcoming match updates
its probabilities (odds shift, model re-scores); a filled outcome is never
clobbered.

Examples:

    # Log next 2 days of model-board predictions + settle finished ones
    nutmeg-predict-log --db data/v4_observation.db --days 2

    # Preview without writing
    nutmeg-predict-log --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

from nutmeg.v4.observation.prediction_log import (
    ensure_league_predictions_table,
    record_league_prediction,
    settle_league_predictions,
)

log = logging.getLogger("nutmeg-predict-log")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Log + settle model-board predictions")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--days", type=int, default=2,
                    help="How many days ahead to log (default 2)")
    ap.add_argument("--no-settle", action="store_true",
                    help="Skip the post-log settle pass")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be logged; write nothing")
    args = ap.parse_args(argv)

    # Deferred imports: reuse the EXACT gather + scoring the sp-calc endpoint
    # uses, so logged predictions match what the dashboard shows.
    from nutmeg.v4.api.routes import (
        _SP_CALC_LEAGUES,
        _calc_predictions,
        _fixture_rows_to_inputs,
        get_artifact,
    )
    from nutmeg.v4.cli.ingest_odds import PINNACLE_BOOKMAKER_ID, _gather_rows

    art = get_artifact()
    if art is None:
        log.error("V4 model artifact not loaded; cannot predict")
        return 1

    if not args.dry_run:
        ensure_league_predictions_table(args.db)

    today = dt.datetime.now(dt.UTC).date()
    logged = 0
    for d in range(max(1, args.days)):
        on_date = today + dt.timedelta(days=d)
        try:
            rows, _n, _s = _gather_rows(
                _SP_CALC_LEAGUES, on_date,
                cache_dir=Path("data/external/api_football"),
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=False,
                require_odds=False, min_kickoff_buffer_minutes=5,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("gather failed for %s: %s", on_date, exc)
            continue
        scored = [r for r in rows if r.get("psc_home") is not None]
        if not scored:
            continue
        preds = _calc_predictions(art, _fixture_rows_to_inputs(scored))
        for p in preds:
            pd = p.model_dump() if hasattr(p, "model_dump") else dict(p)
            if args.dry_run:
                log.info(
                    "would log %s vs %s (%s %s) P=%.2f/%.2f/%.2f",
                    pd["home_team"], pd["away_team"], pd["league"], pd["date"],
                    pd["p_home_1x2"], pd["p_draw_1x2"], pd["p_away_1x2"],
                )
            else:
                record_league_prediction(args.db, pd)
            logged += 1

    log.info("%s %d model-board predictions",
             "would log" if args.dry_run else "logged", logged)

    if not args.no_settle and not args.dry_run:
        n = settle_league_predictions(args.db)
        log.info("settled %d predictions", n)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
