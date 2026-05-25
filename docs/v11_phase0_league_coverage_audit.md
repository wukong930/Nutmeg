# V11 Phase 0 — League Coverage Audit + Expansion

_2026-05-25 (post-V10 W4, during V11 Phase 0 wait period)_

## TL;DR

The user asked "do we need to add more leagues to training?" Audit
revealed: **we already train on 13 leagues**, but the daily
operational flow (cron + dashboard) only surfaces 2-5. Today's commit
closes the gap with 3 small changes:

A. **Ingested Belgian Pro League** — the only missing league in
   `LEAGUE_NAMES` that lacked CSVs on disk. 5 seasons × ~307 matches.

B. **Expanded `daily_odds` + `daily_recommend` cron leagues**
   from 5 → 14 (post-Belgian). API budget still safe (~33 calls/day,
   free tier 100).

D. **Expanded dashboard default leagues** (`TodayRecommendationsRequest`)
   from `[EPL, La Liga]` → 14 trained leagues. Users now see today's
   recommendations across the full production-model coverage.

---

## Pre-audit assumption (what user thought)

"We probably only train on top 5 European leagues; need to add
Belgian / Eredivisie / Liga Portugal / second-tier / J League."

## Reality (what the audit found)

The production model trains on **13 leagues / 26,890 rows** out of the
box. football-data.co.uk CSVs cover all of these and have been ingested
since V5 W3 (2025-09). The gap was operational, not training.

| Layer | Pre-audit coverage | Post-audit coverage |
|---|:-:|:-:|
| Training data (football-data.co.uk CSVs) | 13 leagues | **14 leagues** (+ Belgian) |
| `data/v4_model_cat_lineups/` artifact | 13 leagues | **14 leagues** (retrained) |
| `nutmeg-recommend` CLI (with manual fixture input) | All trained leagues | unchanged (already worked) |
| `daily_odds` cron | 5 (top 5 European) | **14** |
| `daily_recommend` cron | 2 (EPL + La Liga) | **14** |
| `TodayRecommendationsRequest.leagues` default | 2 (EPL + La Liga) | **14** |
| API-Football league ID registry | 13 leagues | unchanged (already had all) |
| clubelo Elo coverage | 335 teams across 13 leagues | unchanged (already covered Belgian teams too) |

---

## Per-league training data sizes (post-Belgian ingest)

| Code | League | Rows | Notes |
|---|---|---:|---|
| `JPN_J1` | J League J1 | 4,523 | Calendar-year seasons (Mar-Dec); 12+ years accumulated |
| `ENG_CHAMPIONSHIP` | EFL Championship (English second-tier) | 2,760 | 24-team league = more matches per season than EPL |
| `ESP_SEGUNDA_DIVISION` | La Liga 2 | 2,310 | |
| `EPL` | English Premier League | 1,900 | |
| `ESP_LA_LIGA` | La Liga | 1,900 | |
| `ITA_SERIE_A` | Serie A | 1,900 | |
| `ITA_SERIE_B` | Serie B | 1,900 | |
| `FRA_LIGUE_2` | Ligue 2 | 1,825 | |
| `FRA_LIGUE_1` | Ligue 1 | 1,752 | |
| `BEL_PRO_LEAGUE` | Belgian Pro League | **1,542** | **NEW** in this audit |
| `NED_EREDIVISIE` | Eredivisie | 1,530 | |
| `GER_2_BUNDESLIGA` | 2. Bundesliga | 1,530 | |
| `GER_BUNDESLIGA` | Bundesliga | 1,530 | |
| `PRT_PRIMEIRA_LIGA` | Primeira Liga | 1,530 | |
| | **Total** | **28,432** | from 26,890 |

---

## Retrain results (post-Belgian)

```
Loading matches from data/historical_sources/football_data_co_uk ...
  loaded 28,432 matches
Training cutoff: 2024-08-01
  lineup cache: 1482 fixtures, 1482 with recent-injury counts
Building features ...
  Train: 22,671 matches    Val: 552 matches
Training CatBoost-λ (Poisson × 2; league as categorical; with lineup features) ...
  best_iter home=228, away=123
Fitting temperature calibrator on validation pool ...
  fitted T = 0.912 (nll: 0.9789 → 0.9781)
Capturing team state at cutoff ...
  404 (league, team) pairs across 14 leagues

Artifact saved to: data/v4_model_cat_lineups
Total elapsed: 10.8s
```

- Validation nll **0.9781** (after T calibration) — comparable to the
  pre-Belgian artifact's 24/25 EPL test set log-loss of 0.9960
- 404 (league, team) pairs ← 14 leagues × ~28 teams average
- Training: 10.8 seconds. No infrastructure stress at all.
- The model `with_lineups: true` flag preserved. Lineup features still
  only apply to EPL + La Liga (`lineup_leagues` config). The other 12
  leagues use NaN sentinels for lineup features — model handles this
  fine via CatBoost's native missing-value support.

---

## Out of scope (deliberately not done)

### 中超 (Chinese Super League) — user explicitly excluded
Cultural / tactical / market-shape differences with European leagues
are too large; adding it would require either (a) a separate model
or (b) heavy per-league T calibration that we haven't validated.
Deferred indefinitely.

### South American (Brazilian Série A, Argentine Liga) — user excluded
Same reasoning as 中超. Plus clubelo doesn't cover them well, and
Pinnacle's market signal is weaker.

### MLS / K League — not on user's list
Could be added later if user prioritizes. K League is closest to
J League architecturally; would be ~3-4 hours of work.

### UCL / UEL / UECL — cup ablation closed negative (P1#20)
The model **can** predict cup matches (most cup teams are in our
training data via their domestic appearances), but a CUP-SPECIFIC
model failed P1#20's walk-forward. Daily cron deliberately excludes
cups because: (a) ablation said no value, (b) saves ~10 API calls/day.

If user wants UCL/UEL predictions in dashboard despite the negative
ablation, that's a V12 product decision: surface the predictions with
a clear "cup-mode confidence is lower than domestic" caveat. Not
done today.

### Lineup features beyond EPL+La Liga
`lineup_leagues` config still `EPL, ESP_LA_LIGA` only. Lineup data
for other leagues requires:
- API-Football lineup endpoint coverage (varies by league)
- Cache build (~24 hours of API calls per league per season)
- Per-league lineup feature ablation
Out of scope for this audit; Branch B candidate.

---

## API budget impact

| Metric | Pre-audit | Post-audit | Notes |
|---|---:|---:|---|
| `daily_odds` leagues fetched | 5 | 14 | |
| `/fixtures` calls per day | 5 | 14 | one per league |
| `/odds` calls per day (avg, depends on match count) | ~15-25 | ~25-40 | varies by match day; second-tier leagues add ~3-5/league |
| Total estimated daily calls | 20-30 | 40-55 | Free tier: 100/day |
| Burn rate vs limit | 30% | ~55% | comfortable buffer |
| Risk of hitting limit | very low | low | spike on heavy match days (Sat) could go higher; monitor first week |

If we hit the 100/day limit, the fallback is to drop second-tier
leagues from `daily_odds` on heavy days. Not implementing that gate
preemptively — let the first heavy weekend establish the real
distribution.

---

## Files changed in this audit

| File | Change |
|---|---|
| `data/historical_sources/football_data_co_uk/europe/{2021,2122,2223,2324,2425}/B1.csv` | NEW (5 files, ~1.5 MB total) |
| `data/v4_model_cat_lineups/{booster_*.cbm, metadata.json, ...}` | Retrained with Belgian rows included |
| `scripts/setup_local_pipeline.sh` | Lines 132-142: daily_odds + daily_recommend leagues 5→14 |
| `apps/api/src/nutmeg/v4/api/schemas.py` | `TodayRecommendationsRequest.leagues` default 2→14 |
| `docs/v11_phase0_league_coverage_audit.md` | NEW (this file) |

Total: ~50 lines of code change + 5 CSV downloads + 1 retrain.

---

## Next operational step (user)

On the user's local machine (not auto-done here):

```bash
# Re-install launchd jobs with the expanded league list
./scripts/teardown_local_pipeline.sh
./scripts/setup_local_pipeline.sh
./scripts/health_check.sh   # confirm all 7 jobs loaded
```

After the first 14:00 `daily_odds` cron fires with the new league list,
verify `logs/launchd/com.nutmeg.daily_odds.out.log` shows fixtures
fetched across all 14 leagues + no API rate-limit errors.

If rate-limited: edit `scripts/setup_local_pipeline.sh` to drop
the second-tier (`ESP_SEGUNDA_DIVISION` etc.) on heavy match days,
or upgrade API-Football to a paid tier.

---

## Verification

```
1166/1166 V4 non-Playwright tests pass     ✓
14/14 leagues in production training        ✓
14/14 leagues in cron + dashboard default   ✓
Retrain elapsed: 10.8s                       ✓
Production artifact updated atomically      ✓
```
