"""nutmeg-ingest-eloratings — V14.

Snapshot national-team Elo from eloratings.net → the parquet the WC model
actually reads:

    data/external/eloratings/eloratings_<date>.parquet
    columns: rank, country_code, elo, elo_1y_ago   (~244 nations, 2-letter codes)

`load_elo_snapshot` (used by wc_predict + /predictions/wc + wc_training_frame)
picks the LATEST eloratings_*.parquet by filename. Re-running this CLI drops a
fresh dated snapshot, so the WC model's national-strength prior stays current
through the tournament.

NOTE: this is a DIFFERENT source/file from `nutmeg-ingest-national-elo`, which
writes per-nation clubelo histories to data/external/clubelo_national/ and does
NOT refresh this snapshot. Before V14 there was no CLI for THIS file — it was a
one-off manual ingest, so the snapshot silently went stale.

Idempotent + cron-friendly: writes eloratings_<today>.parquet; a same-day re-run
is a no-op unless --refresh. Designed for a weekly launchd job.

Examples:

    # Drop today's snapshot (no-op if it already exists)
    nutmeg-ingest-eloratings

    # Force re-fetch + overwrite today's snapshot
    nutmeg-ingest-eloratings --refresh
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

import httpx
import pandas as pd

log = logging.getLogger("ingest-eloratings")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

WORLD_TSV_URL = "https://www.eloratings.net/World.tsv"
DEFAULT_DIR = Path("data/external/eloratings")
_COLUMNS = ["rank", "country_code", "elo", "elo_1y_ago"]


def parse_world_tsv(text: str) -> pd.DataFrame:
    """eloratings.net World.tsv (tab-separated, no header) → the 4-column
    snapshot schema. Relevant columns: 0=rank, 2=2-letter country code,
    3=current Elo, 5=Elo one year ago. Trailing form/goal columns are ignored.
    Rows that don't parse cleanly are skipped (robust to the odd blank line).
    """
    rows: list[dict] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        code = parts[2].strip()
        if not code:
            continue
        try:
            rows.append({
                "rank": int(parts[0]),
                "country_code": code,
                "elo": float(parts[3]),
                "elo_1y_ago": float(parts[5]),
            })
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows, columns=_COLUMNS)


def fetch_world_tsv(*, timeout: float = 20.0) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(WORLD_TSV_URL)
        resp.raise_for_status()
        return resp.text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Snapshot national-team Elo from eloratings.net (WC model source)")
    ap.add_argument("--out-dir", default=str(DEFAULT_DIR))
    ap.add_argument("--refresh", action="store_true",
                    help="Re-fetch + overwrite today's snapshot")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    if args.quiet:
        log.setLevel(logging.WARNING)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eloratings_{dt.date.today().isoformat()}.parquet"
    if out_path.exists() and not args.refresh:
        log.info("today's snapshot already exists: %s (use --refresh)", out_path)
        return 0

    try:
        text = fetch_world_tsv()
    except Exception as exc:  # noqa: BLE001
        log.error("fetch failed: %s", exc)
        return 1

    df = parse_world_tsv(text)
    # Guard: the real table has ~240 nations. A tiny parse means the TSV format
    # changed — refuse to overwrite a good snapshot with garbage.
    if len(df) < 100:
        log.error("parsed only %d nations (expected ~240) — TSV format may have "
                  "changed; NOT writing", len(df))
        return 1

    df.to_parquet(out_path, index=False)
    log.info("wrote %s (%d nations)", out_path, len(df))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
