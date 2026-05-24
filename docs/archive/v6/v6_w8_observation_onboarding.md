# V6 W8 — Live observation onboarding

_Daily lineup refresh + lineup-aware A/B report. The pipeline you set up
once, then leave running while real bets accumulate. After ≥ 4 weeks of
settlements the A/B card answers: did the lineup-aware artifact actually
beat the V5 W12 default in production, or was V6 W6's `−0.0020 log-loss`
finding a backtest-only mirage?_

## What W8 ships

| Piece | Purpose |
|---|---|
| `nutmeg-refresh-lineups` CLI | Daily incremental pull of fixtures + lineups (+ optional injuries) from API-Football. Idempotent; cached fixtures skip the API call so re-runs cost nothing. |
| `.github/workflows/daily-recommend.yml` | GH Actions cron, 06:00 UTC daily. Runs `nutmeg-refresh-lineups`, uploads the daily summary JSON as a 14-day-retention artifact. **No data is committed** — cache files stay gitignored. Heartbeat + early-warning if the API token dies. |
| `nutmeg.v4.observation.ab_report` | Library: slices the observation DB by the `model.with_lineups` flag persisted in `metadata_json`, returns per-side ROI / hit-rate / payout. |
| `nutmeg-ab-report` CLI | Renders the markdown comparison card. |
| `tests/v4/test_ab_report.py` | 15 tests covering slicing, time-window filtering, card rendering, season helper. |

## How the slice works

Every recommend session writes a `recommendation_sessions` row including
`metadata_json` — a JSON blob copied from the recommend response's
`model` dict. When the artifact is the V6 W7 lineup-aware one,
`metadata.with_lineups = true` lives there. The A/B slicer uses
SQLite's `json_extract`:

```sql
-- lineup-aware
json_extract(r.metadata_json, '$.model.with_lineups') = 1
-- lineup-free (V5 W12 default OR explicit false)
json_extract(r.metadata_json, '$.model.with_lineups') IS NULL
   OR json_extract(r.metadata_json, '$.model.with_lineups') = 0
```

The two slices are mutually exclusive: every settled rec falls in exactly
one bucket.

## Setting up the cron — three flavors

### 1. GitHub Actions (recommended — heartbeat + low-friction)

1. Repo Settings → Secrets and variables → Actions → New repository secret.
   Name: `NUTMEG_API_FOOTBALL_KEY`, value: your token.
2. Push the W8 workflow (already done by V6 W8 commit).
3. First run: Actions tab → "Daily Lineup Refresh" → "Run workflow" to
   verify before the 06:00 UTC schedule kicks in.
4. Failures email the repo owner. If the token expires, you find out at
   06:01 UTC, not when tonight's recommend silently uses stale data.

The cron does NOT call `nutmeg-recommend` — real bets need a human in
the loop (and your bankroll). It only freshens the cache; you run the
recommend locally when you're ready to place.

### 2. Local crontab (for the actual prediction cache)

GH Actions refreshes a SEPARATE checkout from yours. To have fresh
lineup data on your laptop for tonight's recommend, run the same
command on your machine. Example crontab line (run 07:00 local):

```
0 7 * * * cd ~/Nutmeg && PYTHONPATH=apps/api/src .venv/bin/python \
    -m nutmeg.v4.cli.refresh_lineups --leagues EPL,ESP_LA_LIGA \
    --days 3 --cache-dir data/external/api_football \
    --include-injuries --quiet >> /tmp/nutmeg-refresh.log 2>&1
```

### 3. Pre-bet manual

Before a recommend session:

```bash
nutmeg-refresh-lineups --leagues EPL,ESP_LA_LIGA --days 2 --include-injuries
nutmeg-recommend --fixtures path/to/today.csv --bankroll 1000 \
    --artifact data/v4_model_cat_lineups
```

The `--artifact data/v4_model_cat_lineups` tells `recommend` to use the
lineup-aware artifact (V6 W7); leaving it out keeps the V5 W12 default.

## Producing the A/B card

After enough real bets have settled (target: 4 weeks, ≥ 30 each side):

```bash
nutmeg-ab-report --db data/v4_observation.db --weeks 4 \
    --out docs/weekly/$(date -u +%Y-W%V)-ab.md
```

Sample output (zero data, the pipeline-set-up state right after W8):

```markdown
# A/B: lineup-free vs lineup-aware (last 4 weeks)

| Metric | lineup-free (V5 W12 default) | lineup-aware (V6 W7) | Δ (aware − free) |
|---|---:|---:|---:|
| Sessions | 0 | 0 | +0 |
| Settled recs | 0 | 0 | +0 |
| Hits / Partial / Miss | 0/0/0 | 0/0/0 | — |
| Total stake | ¥0.00 | ¥0.00 | ¥+0.00 |
| Total payout | ¥0.00 | ¥0.00 | ¥+0.00 |
| P/L | ¥+0.00 | ¥+0.00 | ¥+0.00 |
| **ROI** | **+0.00%** | **+0.00%** | **+0.00pp** |
| Predicted hit-rate | 0.00% | 0.00% | +0.00pp |
| Actual hit-rate | 0.00% | 0.00% | +0.00pp |

_No settled recommendations yet — pipeline is set up but waiting on real-bet data._
```

Once data accumulates the blurb at the bottom interprets the diff:

- `< 30` settlements on either side → "sample size still small — read
  the diff with caution"
- `|ROI diff| < 2pp` → "no clear winner on this window"
- aware > free by ≥ 2pp → "lineup-aware leads — confirms V6 W6 backtest direction"
- free > aware by ≥ 2pp → "lineup-free leads — lineup artifact may need re-evaluation"

## How the W8 decision unfolds

After 4 weeks of dual-artifact recommends (alternate which one you use
per session, OR run both and bet only one — your choice; both methods
populate distinct slices because each recommend records its own session):

| Card says... | Decision |
|---|---|
| aware leads by ≥ 5pp ROI AND both n ≥ 30 | Promote `data/v4_model_cat_lineups` to default. Update `NUTMEG_V4_ARTIFACT_PATH`. V6 W6 confirmed in production. |
| diff within ±2pp | Keep V5 W12 default. The lineup feature isn't worth the API cost. Document for V7. |
| free leads by ≥ 5pp | Investigate: cache freshness gap? `recent_n_injuries` overfit to backtest cutoffs? Re-validate offline before re-shipping. |
| Either side n < 30 | Wait another week. Don't decide on small samples. |

## What W8 doesn't include

- **Auto-trigger on outcomes**: settlements still require manual
  `nutmeg-record-outcome` calls (or a future ingest of final-score CSVs).
  The A/B card only counts SETTLED recs; an unsettled rec sits in
  `parlay_recommendations` but doesn't show up in the slice.
- **Dual-recommend in one cron**: the daily workflow only refreshes the
  cache. Running `nutmeg-recommend` twice (lineup-free + lineup-aware)
  per fixture set is an obvious extension but requires real-bet
  semantics (do you place BOTH? Just one?) the user has to decide.
- **Per-league A/B**: the slicer aggregates across all leagues. For
  per-league cuts, extend `_slice_for_predicate` with an extra
  `r.metadata_json` predicate or join `single_predictions.league`.

## Risks tracked

1. **API token expiry**: the GH Actions cron is the alarm. Repo owner
   gets an email on first failure. Mitigation: 24-hour SLA on token
   rotation.
2. **Cache divergence between cloud + laptop**: GH Actions refreshes a
   throw-away checkout. Your laptop's cache stays in lockstep ONLY if
   you also run the local crontab in §2 above. If you forget, your
   tonight's recommend uses yesterday's lineups (still works — graceful
   zero-injury default — but slightly stale signal).
3. **Settlement lag**: real-bet 竞彩 results post hours after kickoff,
   but the user must enter them. If `record_outcome` lags by days,
   the W8 4-week window may have fewer than 30 settled on each side.
   Set a calendar reminder to record outcomes every Monday.

## Files touched in W8

```
.github/workflows/daily-recommend.yml             [+]
apps/api/src/nutmeg/v4/cli/ab_report.py           [+]
apps/api/src/nutmeg/v4/cli/refresh_lineups.py     [+] (created earlier in W8)
apps/api/src/nutmeg/v4/observation/ab_report.py   [+]
pyproject.toml                                    [M] (+2 CLI scripts)
tests/v4/test_ab_report.py                        [+] (15 tests)
docs/V6_ROADMAP.md                                [M] (W8 ✅)
docs/v6_w8_observation_onboarding.md              [+] (this file)
```

Total V4 suite: **393/393 passing** (378 prior + 15 new W8 tests).

## Next: V6 W9

User-flow interactive CLI. `nutmeg-rec` walks the user through
single / 串关 / 复式 selection → bankroll → ticket recommendation,
gated by V6 W4 lottery rules (¥2 unit, ¥20k cap, ≤8 legs).
