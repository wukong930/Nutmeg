"""nutmeg-wc-predict — V10 W1 Track B Day 4.

Generate 1X2 predictions for WC fixtures on a given date.

Pipeline:
  1. Train NationalTeamModel on WC 2018 + 2022 combined (128 matches)
  2. Load fixtures for (league=WC, season=YEAR) from API-Football
  3. Filter to the requested date
  4. For each fixture: look up home/away Elo, predict via model
  5. If --fetch-current-odds: pull Pinnacle from Odds API, apply
     bayesian_blend(α=0.4) for final probabilities
  6. Output JSON

Examples:

    # Predict 2026 WC opener (Mexico vs South Africa, 2026-06-11)
    nutmeg-wc-predict --date 2026-06-11

    # Same but pull live Pinnacle odds for the blend
    nutmeg-wc-predict --date 2026-06-11 --fetch-current-odds

    # Save to a file
    nutmeg-wc-predict --date 2026-06-11 --out /tmp/wc_2026_06_11.json

    # Different season (e.g., retroactive check on WC 2022)
    nutmeg-wc-predict --date 2022-11-20 --season 2022

post-v9 caveat (from V10 W1 Track B Day 3 walk-forward):
  Best-case log-loss on WC 2022 = 0.9802 (blend α=0.4).
  Realistic 2026 expectation: hit-rate 50-52%, not 56%.
  Small-sample tournament variance is real.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code
from nutmeg.v4.data.wc_training_frame import (
    build_wc_training_frame,
    load_elo_snapshot,
)
from nutmeg.v4.model.national_team_predict import (
    NationalTeamModel,
    bayesian_blend,
    elo_to_1x2_probs,
    market_implied_probs,
    outcomes_from_goals,
)


log = logging.getLogger("nutmeg-wc-predict")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# Per V10 W1 Day 3 walk-forward verdict
DEFAULT_BLEND_ALPHA = 0.4

# API-Football → Odds API team-name aliases (Odds API drops diacritics).
# Extend as new mismatches surface in the WC 2026 fixture list.
TEAM_AF_TO_ODDS_ALIASES: dict[str, list[str]] = {
    "Türkiye": ["Turkey"],
    "Curaçao": ["Curacao"],
}


def _pinnacle_lookup_with_aliases(
    home: str, away: str, lookup: dict[tuple[str, str], dict],
) -> dict | None:
    """Try (home, away) plus diacritic-stripped aliases."""
    candidates = [(home, away)]
    for h_alias in TEAM_AF_TO_ODDS_ALIASES.get(home, []):
        candidates.append((h_alias, away))
    for a_alias in TEAM_AF_TO_ODDS_ALIASES.get(away, []):
        candidates.append((home, a_alias))
    # Both aliased
    for h_alias in TEAM_AF_TO_ODDS_ALIASES.get(home, []):
        for a_alias in TEAM_AF_TO_ODDS_ALIASES.get(away, []):
            candidates.append((h_alias, a_alias))
    for pair in candidates:
        if pair in lookup:
            return lookup[pair]
    return None

# Host country hint per WC. For 3-country 2026 (USA/MEX/CAN), apply
# home advantage only when the home team is one of these three; smaller
# bonus than single-host because matches are spread.
HOST_COUNTRIES = {
    2018: {"Russia": 50.0},
    2022: {"Qatar": 50.0},
    2026: {"USA": 30.0, "Mexico": 30.0, "Canada": 30.0},
}


def _train_combined_model(
    seasons: list[int],
    host_countries: dict[str, float] | None = None,
) -> NationalTeamModel:
    """Train on combined WC seasons for production inference."""
    dfs = []
    for season in seasons:
        try:
            dfs.append(build_wc_training_frame(season))
        except FileNotFoundError as exc:
            log.warning("Skipping WC %d: %s", season, exc)
    if not dfs:
        raise RuntimeError(
            "No training data available. "
            "Run: nutmeg-ingest-cup-history --leagues WC --seasons 2018,2022"
        )

    combined = pd.concat(dfs, ignore_index=True)
    y = outcomes_from_goals(combined["home_goals"], combined["away_goals"])
    mask = combined["home_elo"].notna() & combined["away_elo"].notna() & (y >= 0)
    combined_ok = combined[mask].reset_index(drop=True)
    y_ok = y[mask]
    log.info(
        "Training on %d matches (WC seasons: %s)",
        len(combined_ok), ", ".join(map(str, seasons)),
    )

    model = NationalTeamModel()
    # If only one host, pass it; for multi-host (2026), the model only
    # learns "host bonus" generically. Production inference handles
    # the multi-host case via host_country at predict time.
    primary_host = None
    primary_adv = 50.0
    if host_countries:
        primary_host = next(iter(host_countries.keys()))
        primary_adv = host_countries[primary_host]
    model.fit(combined_ok, y_ok, host_country=primary_host, host_advantage=primary_adv)
    return model


def _predict_one_fixture(
    fixture: dict,
    model: NationalTeamModel,
    elo: dict[str, dict[str, float]],
    hosts: dict[str, float],
    pinnacle_h2h: dict | None = None,
    alpha: float = DEFAULT_BLEND_ALPHA,
) -> dict:
    """Generate probabilities for a single fixture.

    fixture: API-Football fixture object
    elo: {country_code: {elo: ..., rank: ...}} from snapshot
    hosts: {team_name: home_advantage_pts}
    pinnacle_h2h: optional {home_team, away_team, psc_home, psc_draw, psc_away}
    """
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]

    h_code = lookup_elo_code(home)
    a_code = lookup_elo_code(away)
    h_elo = float(elo.get(h_code, {}).get("elo", 1500.0)) if h_code else 1500.0
    a_elo = float(elo.get(a_code, {}).get("elo", 1500.0)) if a_code else 1500.0
    home_adv = hosts.get(home, 0.0)

    has_pin = pinnacle_h2h is not None
    psc_h = float(pinnacle_h2h["psc_home"]) if has_pin else float("nan")
    psc_d = float(pinnacle_h2h["psc_draw"]) if has_pin else float("nan")
    psc_a = float(pinnacle_h2h["psc_away"]) if has_pin else float("nan")

    # Build a 1-row dataframe for model.predict_proba
    df = pd.DataFrame([{
        "home_team": home,
        "away_team": away,
        "home_elo": h_elo,
        "away_elo": a_elo,
        "psc_home": psc_h if has_pin else np.nan,
        "psc_draw": psc_d if has_pin else np.nan,
        "psc_away": psc_a if has_pin else np.nan,
    }])

    # Use the host_country hint per-row (passed at fit time was the
    # primary host; at predict time we hint with actual home country).
    is_host = home in hosts
    lgb_probs = model.predict_proba(
        df,
        host_country=home if is_host else None,
        host_advantage=home_adv if is_host else 0.0,
    )

    # Blend with Pinnacle if available
    if has_pin:
        pin_probs = market_implied_probs(
            pd.Series([psc_h]), pd.Series([psc_d]), pd.Series([psc_a]),
        )
        final = bayesian_blend(lgb_probs, pin_probs, alpha=alpha)[0]
        source = f"blend(α={alpha})"
    else:
        # No Pinnacle → pure model (which itself is LightGBM with
        # log_pin_* features set to log(1/3) fallback). Also produce
        # closed-form Elo as a sanity reference.
        final = lgb_probs[0]
        source = "lightgbm_only"

    # Compute Elo-only baseline for transparency
    elo_only = elo_to_1x2_probs(h_elo, a_elo, home_adv=home_adv)

    return {
        "fixture_id":     fixture["fixture"]["id"],
        "kickoff_utc":    fixture["fixture"]["date"],
        "round":          fixture["league"].get("round"),
        "home_team":      home,
        "away_team":      away,
        "home_elo":       h_elo,
        "away_elo":       a_elo,
        "elo_diff":       h_elo - a_elo,
        "home_adv":       home_adv,
        "has_pinnacle":   has_pin,
        "psc_home":       psc_h if has_pin else None,
        "psc_draw":       psc_d if has_pin else None,
        "psc_away":       psc_a if has_pin else None,
        "p_home":         float(final[0]),
        "p_draw":         float(final[1]),
        "p_away":         float(final[2]),
        "p_home_elo_only": float(elo_only[0]),
        "p_draw_elo_only": float(elo_only[1]),
        "p_away_elo_only": float(elo_only[2]),
        "source":         source,
    }


def _build_pinnacle_lookup_for_date(
    on_date: dt.date,
) -> dict[tuple[str, str], dict]:
    """Pull WC odds snapshots from The Odds API for the date and build a
    {(home_team, away_team): {psc_*}} lookup. Returns empty dict on any
    error (network, quota, missing key) — caller handles gracefully.
    """
    try:
        from nutmeg.v4.data.sources.odds_api import (
            SPORT_KEYS,
            build_psc_lookup_for_date_range,
        )
    except ImportError:
        log.warning("Odds API module not importable; skipping live odds fetch")
        return {}

    sport_key = SPORT_KEYS.get("WC")
    if not sport_key:
        log.warning("WC sport_key not in SPORT_KEYS; skipping live odds fetch")
        return {}

    iso = on_date.isoformat()
    try:
        lookup = build_psc_lookup_for_date_range(
            sport_key, iso, iso, strict_bookmaker="pinnacle"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Odds API fetch failed: %s — falling back to model-only", exc)
        return {}

    # Convert (date, home, away) → (home, away)
    out = {}
    for (_d, home, away), psc in lookup.items():
        out[(home, away)] = psc
    log.info("Pinnacle odds available for %d fixtures on %s", len(out), iso)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V10 W1 — WC 1X2 predictions")
    p.add_argument("--date", required=True, help="YYYY-MM-DD (UTC)")
    p.add_argument(
        "--season", type=int, default=None,
        help="WC season year (default: derived from --date)",
    )
    p.add_argument(
        "--train-seasons", default="2018,2022",
        help="Comma-separated training seasons (default 2018,2022)",
    )
    p.add_argument(
        "--alpha", type=float, default=DEFAULT_BLEND_ALPHA,
        help=f"Blend weight: alpha × LightGBM + (1-alpha) × Pinnacle "
             f"(default {DEFAULT_BLEND_ALPHA}, per V10 W1 Day 3 walk-forward)",
    )
    p.add_argument(
        "--fetch-current-odds", action="store_true",
        help="Pull current Pinnacle odds from The Odds API and apply the blend",
    )
    p.add_argument(
        "--out", default="-",
        help="Output JSON path; '-' for stdout (default)",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    try:
        on_date = dt.date.fromisoformat(args.date)
    except ValueError as exc:
        log.error("invalid --date: %s", exc)
        return 2

    season = args.season or on_date.year   # WC is named by host year

    # 1. Train model on combined historical seasons
    train_seasons = [int(s.strip()) for s in args.train_seasons.split(",")]
    try:
        host_hint = HOST_COUNTRIES.get(train_seasons[0])
        model = _train_combined_model(train_seasons, host_countries=host_hint)
    except Exception as exc:
        log.error("training failed: %s", exc)
        return 1

    # 2. Load eloratings snapshot
    snapshots = sorted(Path("data/external/eloratings").glob("eloratings_*.parquet"))
    if not snapshots:
        log.error(
            "No eloratings snapshot found. "
            "Run the scraper (see docs/v10_w1_day2_wc_training_join.md)."
        )
        return 1
    elo = load_elo_snapshot(snapshots[-1])
    log.info("Using eloratings snapshot: %s (%d nations)", snapshots[-1].name, len(elo))

    # 3. Fetch fixtures
    from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_league_season
    try:
        all_fixtures = fetch_fixtures_for_league_season("WC", season)
    except Exception as exc:
        log.error("could not fetch WC %d fixtures: %s", season, exc)
        return 1

    on_iso = on_date.isoformat()
    today_fixtures = [
        f for f in all_fixtures
        if f.get("fixture", {}).get("date", "").startswith(on_iso)
    ]
    log.info(
        "Found %d/%d fixtures on %s (full season: %d total)",
        len(today_fixtures), len(all_fixtures), on_iso, len(all_fixtures),
    )

    if not today_fixtures:
        log.warning("No fixtures on %s — nothing to predict", on_iso)
        result = {
            "date": on_iso,
            "season": season,
            "n_fixtures": 0,
            "predictions": [],
            "training_set_size": "unknown",
            "blend_alpha": args.alpha,
            "host_country_hint": HOST_COUNTRIES.get(season, {}),
        }
        _write_output(result, args.out)
        return 0

    # 4. Optional live odds fetch
    pinnacle_lookup = {}
    if args.fetch_current_odds:
        pinnacle_lookup = _build_pinnacle_lookup_for_date(on_date)

    # 5. Predict per fixture
    season_hosts = HOST_COUNTRIES.get(season, {})
    preds = []
    for fx in today_fixtures:
        home = fx["teams"]["home"]["name"]
        away = fx["teams"]["away"]["name"]
        # Pinnacle lookup with alias tolerance (Türkiye → Turkey etc.)
        pin = _pinnacle_lookup_with_aliases(home, away, pinnacle_lookup)
        preds.append(
            _predict_one_fixture(
                fx, model, elo, season_hosts,
                pinnacle_h2h=pin, alpha=args.alpha,
            )
        )

    result = {
        "date": on_iso,
        "season": season,
        "n_fixtures": len(preds),
        "predictions": preds,
        "blend_alpha": args.alpha,
        "host_country_hint": season_hosts,
        "elo_snapshot": snapshots[-1].name,
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
    }
    _write_output(result, args.out)
    return 0


def _write_output(result: dict, out_path: str) -> None:
    payload = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if out_path == "-":
        print(payload)
    else:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload)
        log.info("wrote %d bytes → %s", len(payload), out_path)


if __name__ == "__main__":
    sys.exit(main())
