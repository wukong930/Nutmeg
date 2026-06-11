"""nutmeg-predict-log — V12 W8j (+ V14 市场模式).

Log the 1X2 prediction for every UPCOMING match (no bet, no 竞彩 SP), then settle
finished ones. Powers nutmeg-predict-report (hit-rate / calibration / vs-Pinnacle).

Two boards, one table (league_predictions, distinguished by market_mode):
- Model board: the 13 trained domestic leagues → independent CatBoost P (market_mode=0).
- Market mode: cups / J1 / J2 / 北欧 / 国际赛 (_CUP_MARKET_COMPETITIONS) → Pinnacle
  de-vig P (market_mode=1; OOD for the model). Without this, J1/J2/cup predictions
  — most of what the user actually watches — were never accumulated, so their
  hit-rate / calibration / CLV could never be measured.

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
        _CUP_MARKET_COMPETITIONS,
        _SP_CALC_LEAGUES,
        _calc_predictions,
        _fixture_rows_to_inputs,
        _row_to_market_prediction,
        get_artifact,
    )
    from nutmeg.v4.cli.ingest_odds import (
        PINNACLE_BOOKMAKER_ID,
        _gather_rows,
        _odds_api_available,
    )

    art = get_artifact()
    if not args.dry_run:
        ensure_league_predictions_table(args.db)

    today = dt.datetime.now(dt.UTC).date()
    cache = Path("data/external/api_football")

    def _gather(leagues: list[str], on_date: dt.date):
        return _gather_rows(
            leagues, on_date, cache_dir=cache, bookmaker_id=PINNACLE_BOOKMAKER_ID,
            refresh_fixtures=False, refresh_odds=False,
            require_odds=False, min_kickoff_buffer_minutes=5,
            # 体检 A1 — the 3×/day cron doubles as the line-history sampler.
            snapshot_db=(None if args.dry_run else args.db),
            snapshot_source="predict_log",
            # 体检(2026-06-10)— fresher Pinnacle line via Odds API (TTL-cached).
            use_odds_api=_odds_api_available(),
        )

    def _emit(prediction: dict, tag: str) -> None:
        if args.dry_run:
            log.info(
                "would log [%s] %s vs %s (%s %s) P=%.2f/%.2f/%.2f", tag,
                prediction["home_team"], prediction["away_team"],
                prediction["league"], prediction["date"],
                prediction["p_home_1x2"], prediction["p_draw_1x2"],
                prediction["p_away_1x2"],
            )
        else:
            record_league_prediction(args.db, prediction)

    # --- Model board (13 trained leagues) — independent model P; needs artifact.
    logged = 0
    if art is None:
        log.warning("V4 artifact not loaded; logging market-mode only (no model board)")
    else:
        for d in range(max(1, args.days)):
            on_date = today + dt.timedelta(days=d)
            try:
                rows, _n, _s = _gather(_SP_CALC_LEAGUES, on_date)
            except Exception as exc:  # noqa: BLE001
                log.warning("model gather failed for %s: %s", on_date, exc)
                continue
            scored = [r for r in rows if r.get("psc_home") is not None]
            if not scored:
                continue
            for p in _calc_predictions(art, _fixture_rows_to_inputs(scored)):
                _emit(p.model_dump() if hasattr(p, "model_dump") else dict(p), "模型")
                logged += 1

    # --- Market mode (cups / J1 / J2 / 北欧 / 国际赛…) — pure Pinnacle de-vig,
    # NO model (OOD). Logged with market_mode=1 so the report excludes them from
    # the model-vs-sharp comparison but still scores hit-rate + calibration.
    mkt = 0
    for d in range(max(1, args.days)):
        on_date = today + dt.timedelta(days=d)
        try:
            rows, _n, _s = _gather(_CUP_MARKET_COMPETITIONS, on_date)
        except Exception as exc:  # noqa: BLE001
            log.warning("market-mode gather failed for %s: %s", on_date, exc)
            continue
        for r in rows:
            mp = _row_to_market_prediction(r)  # None when no Pinnacle 1X2 → skip
            if mp is None:
                continue
            _emit(mp.model_dump(), "市场模式")
            mkt += 1

    log.info("%s %d model + %d market-mode predictions",
             "would log" if args.dry_run else "logged", logged, mkt)

    if not args.no_settle and not args.dry_run:
        n = settle_league_predictions(args.db)
        log.info("settled %d predictions", n)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
