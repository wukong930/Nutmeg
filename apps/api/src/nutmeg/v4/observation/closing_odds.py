"""Closing-line Pinnacle capture — snapshot the Odds-API Pinnacle lookup straight
into ``odds_snapshots(source='closing')``, bypassing the cup-market gather (whose
fixture-matching drops most matches → it writes ~nothing right now). Run frequently
(cron, every ~30 min) so EVERY match gets a Pinnacle line captured close to its own
kickoff = the true CLOSE — the correct anchor for CLV + the de-noised soft-water
comparison (③ found the gather-side anchor was median ~5h stale). Forward-only,
append-only (record_row_snapshot dedups on line-state), fail-soft.

Team names: ``fetch_pinnacle_lookup`` returns Odds-API display names. Most already
match the jingcai_vote / odds_snapshots canonical (France=France, Ivory Coast=Ivory
Coast …); only a few national-team word-order/synonym diffs do not. We apply a SMALL
measured alias (``_ODDS_API_ALIAS``) aligned to the JOIN TARGET's naming — extend it
when a new mismatch surfaces (see 记忆 cross-source-team-name-mismatch). The heavier
`team_canonical` fuzzy pool is deliberately NOT used here: it needs multi-step pool
construction and a closing capture must stay light + reliable.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)


def _parse_iso(s: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (accepting a trailing 'Z') to an aware UTC
    datetime, or None if absent/malformed."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

# Odds-API team name → our canonical (the name jingcai_vote / odds_snapshots use, =
# API-Football EN via zh_to_canonical). Only the measured mismatches; identity
# otherwise. Extend as new ones appear in the closing run's "unmatched" log.
_ODDS_API_ALIAS: dict[str, str] = {
    "DR Congo": "Congo DR",
    # 体检 B3 (2026-07-01, measured): every other source (竞彩, cup_market,
    # predict_log, jingcai_sp) + the elo table spell it "Cape Verde Islands"; only
    # the Odds-API closing capture wrote the outlier "Cape Verde", so the freshest
    # anchor silently un-joined jingcai_vote (Argentina v Cape Verde Islands).
    "Cape Verde": "Cape Verde Islands",
}


def _canon(name: str | None) -> str | None:
    if not name:
        return None
    return _ODDS_API_ALIAS.get(name.strip(), name.strip())


def capture_closing_pinnacle(
    db_path: str | Path,
    sport_keys,
    *,
    refresh: bool = True,
    now: datetime | None = None,
) -> dict:
    """For each sport (short key like 'WC'/'UCL' or a raw odds-api sport_key),
    fetch the current Pinnacle lookup and append each quotable *pre-kickoff* match
    as a ``source='closing'`` snapshot. Returns ``{sport_key: rows_written}``.
    Fail-soft per sport — a fetch failure just writes 0 for that sport.

    PRE-KICKOFF ONLY: once a match starts, The Odds API serves LIVE Pinnacle odds
    (a leading team → a degenerate 1.06/53.96 line). Recording those as a "close"
    poisons the CLV ledger and the soft-water scan (2026-07-01: an in-play capture
    produced a phantom +87% EV leg). We skip any match whose kickoff is at/​before
    ``now``; a match with no parseable kickoff is skipped too (can't prove it's
    pre-match). The last snapshot taken before kickoff remains the true close."""
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation.odds_snapshots import record_row_snapshot

    now = now or datetime.now(UTC)
    out: dict[str, int] = {}
    for sk in sport_keys:
        sport_key = odds_api.SPORT_KEYS.get(sk, sk)
        try:
            lookup = odds_api.fetch_pinnacle_lookup(sport_key, refresh=refresh)
        except Exception:  # noqa: BLE001 — fail-soft; one sport's failure isn't fatal
            log.warning("closing-odds fetch failed for %s (%s)", sk, sport_key,
                        exc_info=True)
            out[sk] = 0
            continue
        written = 0
        skipped_live = 0
        for key, e in (lookup or {}).items():
            kickoff = _parse_iso(e.get("commence_time"))
            if kickoff is None or kickoff <= now:
                skipped_live += 1  # already kicked off (live odds) or unknown KO
                continue
            date = key[2] if isinstance(key, tuple) and len(key) >= 3 else e.get("date")
            row = {
                "date": date,
                "league": sk,
                "home_team": _canon(e.get("home_team")),
                "away_team": _canon(e.get("away_team")),
                "psc_home": e.get("psc_home"),
                "psc_draw": e.get("psc_draw"),
                "psc_away": e.get("psc_away"),
                "ou_line": e.get("ou_line"),
                "psc_over25": e.get("psc_over"),
                "psc_under25": e.get("psc_under"),
                "odds_update": e.get("last_update"),
                "kickoff_utc": e.get("commence_time"),
            }
            if not (row["date"] and row["home_team"] and row["away_team"]):
                continue
            written += int(record_row_snapshot(db_path, row, source="closing"))
        if skipped_live:
            log.info("closing-odds %s: skipped %d already-started/unknown-KO match(es)",
                     sk, skipped_live)
        out[sk] = written
    return out
