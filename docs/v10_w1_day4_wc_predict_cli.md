# V10 W1 Track B Day 4 — nutmeg-wc-predict CLI

_Generated 2026-05-25. Wraps Day 3's model into a runnable CLI;
day-of WC predictions with optional live Pinnacle blend._

## CLI contract

```
nutmeg-wc-predict --date YYYY-MM-DD [--season YYYY] [--alpha 0.4]
                  [--train-seasons 2018,2022] [--fetch-current-odds]
                  [--out PATH] [--quiet]
```

Pipeline:
1. Train `NationalTeamModel` on combined WC seasons (default 2018+2022,
   128 matches) — re-trains each call (~1 sec; cheaper than caching)
2. Load latest `data/external/eloratings/eloratings_*.parquet`
3. `fetch_fixtures_for_league_season("WC", season)` → all fixtures
4. Filter to the requested date
5. (Optional) `--fetch-current-odds` → pull Pinnacle from Odds API
   with `strict_bookmaker="pinnacle"` (apples-to-apples filtering)
6. For each fixture:
   - Look up home/away Elo (alias-tolerant via 52-team map)
   - Predict via LightGBM (with log-Pinnacle features when available)
   - If Pinnacle present: blend with `α=0.4`
7. Output JSON

## Live smoke — 2026 WC opener

```
$ nutmeg-wc-predict --date 2026-06-11 --quiet
{
  "date": "2026-06-11",
  "season": 2026,
  "n_fixtures": 1,
  "predictions": [{
    "fixture_id": ...,
    "kickoff_utc": "2026-06-11T19:00:00+00:00",
    "round": "Group Stage - 1",
    "home_team": "Mexico",
    "away_team": "South Africa",
    "home_elo": 1860, "away_elo": 1524, "elo_diff": 336,
    "home_adv": 30.0,
    "has_pinnacle": false,
    "p_home": 0.582, "p_draw": 0.201, "p_away": 0.217,
    "p_home_elo_only": 0.841, "p_draw_elo_only": 0.057, "p_away_elo_only": 0.102,
    "source": "lightgbm_only"
  }],
  ...
}
```

**Mexico vs South Africa (2026-06-11)**:
- LightGBM model: Mexico 58%, Draw 20%, S. Africa 22%
- Pure Elo: Mexico 84%, Draw 6%, S. Africa 10%

The LightGBM is much more conservative than pure Elo. This is realistic
for tournament openers where favorites often play cagey + Elo's high
spreads are systematically miscalibrated for intl matches.

## Live smoke — 2026-06-14 (5 fixtures with Pinnacle blend)

```
$ nutmeg-wc-predict --date 2026-06-14 --fetch-current-odds --quiet
```

| Match | p_H | p_D | p_A | source |
|---|---:|---:|---:|---|
| Haiti vs Scotland | 30% | 16% | 54% | blend(α=0.4) |
| Australia vs Türkiye | 23% | 25% | 52% | blend(α=0.4) |
| Germany vs Curaçao | 57% | 20% | 22% | lightgbm_only |
| Netherlands vs Japan | 39% | 26% | 36% | blend(α=0.4) |
| Ivory Coast vs Ecuador | 20% | 24% | 56% | blend(α=0.4) |

4/5 fixtures successfully blended with Pinnacle. The Germany vs Curaçao
row fell back to `lightgbm_only` — fixture-source disagreement: Odds API
has "Germany vs Ivory Coast" for that slot (probably the playoff bracket
isn't fully locked in yet at either provider). Acceptable: predict what
API-Football says, fall back to model-only when no odds match.

## Engineering details

### Alias-tolerant Pinnacle lookup

API-Football uses official spellings; Odds API drops diacritics:

```python
TEAM_AF_TO_ODDS_ALIASES = {
    "Türkiye": ["Turkey"],
    "Curaçao": ["Curacao"],
}
```

Extends `_pinnacle_lookup_with_aliases()` to try all alias combinations
when the direct (home, away) lookup misses. Easy to add more entries
when the 2026 WC bracket locks in.

### Host advantage handling

WC 2026 is 3 hosts (USA / Mexico / Canada). Per-team bonus 30 Elo
(smaller than single-host's typical 50; matches are spread across
3 countries so home-crowd effect dilutes).

| Season | Host(s) | Bonus per host match |
|---|---|---:|
| 2018 | Russia | +50 |
| 2022 | Qatar | +50 |
| 2026 | USA / Mexico / Canada | +30 each |

### Re-training cheap, model not persisted

LightGBM trains on 128 rows in ~1 second. Not worth the complexity of
artifact persistence + version bump on every eloratings refresh. Just
retrain per CLI call.

### Quota cost per prediction run

| Source | Cost |
|---|---:|
| API-Football fixtures (per season, cached) | 1 call first run, 0 after |
| The Odds API (per `--fetch-current-odds`) | 10 quota (~$0.015) |
| Eloratings TSV scrape | $0 (public, no auth) |

Daily prediction cron would cost ~10 quota/day during WC = ~310 total
across the tournament. Well within The Odds API Starter tier (20K/mo).

## What's deferred to Day 5

1. **Dashboard "WC 预测" tab** consuming `/api/v4/predictions/wc`
   (a new HTTP endpoint wrapping this CLI's logic)
2. **2026 dry run** — predict all 72 known group-stage fixtures, sanity
   check that favorites look like favorites
3. **W1 ship + tag `v10.w1`** (currently 2026-05-25; target 2026-05-31)

## Test coverage

11 new tests in `tests/v4/test_wc_predict_cli.py`:

- **TestPinnacleAliasLookup** (5): direct match, home/away alias,
  diacritic edge case, no-match fallback
- **TestCliArgumentParsing** (4): date required, invalid date → exit 2,
  default alpha = 0.4 (Day 3 walk-forward verdict), 2026 hosts present
- **TestCliEndToEnd** (2, skipif training data missing): real model
  trained on 128 rows + synthetic fixture mock → checks JSON schema,
  home_adv applied to Mexico, Mexico favored, probs sum to 1

## Files

```
apps/api/src/nutmeg/v4/cli/wc_predict.py       [+] 260 lines, the CLI
apps/api/src/nutmeg/v4/data/sources/api_football.py
                                               [M] +fetch_fixtures_for_league_season
pyproject.toml                                  [M] +nutmeg-wc-predict script
tests/v4/test_wc_predict_cli.py                 [+] 11 tests
docs/v10_w1_day4_wc_predict_cli.md             [+] this writeup
```

## V10 W1 progress now: 4/5 Track B days done

| Track A | Track B |
|---|---|
| ✅ Day 1: UX audit | ✅ Day 1: WC fixtures ingest |
| ✅ Day 2: endpoint | ✅ Day 2: eloratings + join |
| ✅ Day 3: new tab | ✅ Day 3: model + walk-forward |
| ✅ Day 4: 高级 ▾ fold | ✅ Day 4: CLI + alias-tolerant blend |
| ⏳ Day 5: Playwright E2E | ⏳ Day 5: dashboard tab + dry run |

W1 ship target: 2026-05-31 with `v10.w1` tag. On schedule.
