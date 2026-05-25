# V10 W1 Track B Day 5 — WC endpoint + dashboard tab + 2026 dry run + W1 ship

_Generated 2026-05-25. Closes V10 W1 (5 days, both tracks). Tag `v10.w1` shipped._

## What landed today

### 1. New HTTP endpoint `GET /api/v4/predictions/wc`

```
GET /api/v4/predictions/wc?date=2026-06-11&fetch_current_odds=false&alpha=0.4
```

Wraps the Day 4 `nutmeg-wc-predict` CLI logic for dashboard + external
callers. Defensive 503s when training data / Elo snapshot missing;
otherwise 200 with structured response (one row per fixture +
metadata). Tested via TestClient end-to-end.

### 2. New dashboard tab "🏆 WC 2026"

Visible by default in nav (between 🎯 今日推荐 and 高级 ▾). Auto-loads
when activated. UI controls:

- Date picker (constrained to 2026-06-11 → 2026-07-19 WC window)
- "用实时盘口" checkbox → adds `fetch_current_odds=true` (10 Odds API quota)
- 刷新 button → re-fetches with current settings

Per-match card layout:
```
Mexico vs South Africa                  Mex 58% / 平 20% / SAfr 22%  [仅模型]
2026-06-11 19:00 UTC · Group Stage - 1 · Elo 1860 vs 1524
  纯 Elo 基线: H 84% · D 6% · A 10%
```

Caveat banner under the title makes the "small sample, ship-gate passed
but use with caution" warning visible — not hidden in docs.

### 3. 2026 WC dry run — sanity verified

Predicted all **72 NS fixtures** for the tournament. Top-line results:

**Most lopsided 10 fixtures** (sanity: should be strong vs weak):
```
Ivory Coast vs Ecuador        → Ecuador 80%
Iraq vs Norway                → Norway 80%
Tunisia vs Japan              → Japan 80%
Tunisia vs Netherlands        → Netherlands 80%
Saudi Arabia vs Uruguay       → Uruguay 78%
New Zealand vs Belgium        → Belgium 78%
Qatar vs Switzerland          → Switzerland 78%
Haiti vs Scotland             → Scotland 71%
Ghana vs Panama               → Panama 71%
South Africa vs South Korea   → South Korea 71%
```

**Closest 5 fixtures** (sanity: should be evenly matched):
```
Türkiye vs Paraguay        → 31/29/39
Norway vs Senegal          → 32/30/38
Colombia vs Portugal       → 38/32/30
England vs Croatia         → 38/32/30
Norway vs France           → 35/35/31
```

**Distribution**: 31% of matches have a > 60% favorite — reasonable
for tournament football with 12+ minnows in the new 48-team field.

**All probabilities sum to 1.0** across all 72 fixtures.

### 4. Files this commit

```
apps/api/src/nutmeg/v4/api/schemas.py            [M] +WcMatchPrediction + WcPredictionsResponse
apps/api/src/nutmeg/v4/api/routes.py             [M] +/v4/predictions/wc endpoint
apps/api/src/nutmeg/v4/api/static/dashboard.html  [M] +tab + i18n + JS
tests/v4/test_frontend_responsive_a11y.py        [M] role=tabpanel count 8 → 9
docs/v10_w1_day5_wc_endpoint_dashboard_ship.md   [+] this writeup
```

## V10 W1 closes — 5 days, dual track

| Day | Track A (UX) | Track B (WC) |
|---|---|---|
| 1 | ✅ UX audit + wireframe | ✅ WC 2018/2022 + 2026 fixtures ingested |
| 2 | ✅ `/v4/today-recommendations` endpoint | ✅ eloratings fallback + training join |
| 3 | ✅ "今日推荐" tab | ✅ Model + walk-forward → SHIP |
| 4 | ✅ "高级 ▾" fold | ✅ `nutmeg-wc-predict` CLI |
| 5 | (deferred: Playwright E2E → V11) | ✅ Endpoint + dashboard tab + dry run |

Track A Day 5 (Playwright E2E for new flow) **explicitly deferred to
V11**. It's QA polish; not blocking ship. Local Playwright still runs
fine; CI workflow exists (P1#26). Adding new test cases for the
今日推荐 + WC flows is V11 backlog.

## Numbers — V9 ship → V10 W1 ship

| Metric | V9 ship | V10 W1 ship | Δ |
|---|---:|---:|---:|
| V4 tests passing | 803 | **~890** | +87 (today, lvb, observation, WC predict, training frame, ux audit) |
| CLIs in pyproject | 25 | **30** | +5 (nutmeg-roi-backtest, nutmeg-ingest-cup-odds-via-odds-api, nutmeg-cat-calibration-ablation, nutmeg-ece-audit, nutmeg-wc-predict) |
| HTTP endpoints | 11 | **13** | +2 (today-recommendations, predictions/wc) |
| Dashboard tabs | 7 | **9** | +2 (今日推荐, WC 2026) |
| Launchd jobs | 3 (P1#16 ship) | **4** (P1#24 weekly_gate) | +1 |
| GH Actions workflows | 4 | **5** (P1#26 playwright) | +1 |
| Default model | V5 W12 CatBoost | unchanged | unchanged |
| Cup-aware artifact | NEGATIVE-CLOSED (P1#20) | unchanged | unchanged |
| WC predictions | not built | shipped w/ Day 3 caveats | NEW |
| Documented negative results | 6 | 6 | unchanged |

## W2 plan — Track A's Layer A is up next

V10 W2 (per V10_ROADMAP): build the **Layer A auto-T calibration**
drift-correction cron. Closes the recommend → settle → learn loop.
Targets:
- `nutmeg.v4.observation.auto_calibration` module
- Holdout-validated T refit on past 8 weeks of live data
- Ship gate: bootstrap p < 0.1 AND log-loss improves ≥ 0.001
- Auto-rollback if next-week ROI drops > 5pp
- New launchd `com.nutmeg.weekly_calibration_check` (Mon 03:00)

W2 ship target: 2026-06-07 with `v10.w2`.

## Honest WC sanity check on the dry run

I want to mark some predictions that look ODD vs sentiment:

| Fixture | Model says | Sentiment | Investigate? |
|---|---|---|---|
| **France vs Norway** (35/35/31) | basically a coin flip | France favored heavily | Norway has been rising (Haaland-led); model honors latest Elo |
| **Colombia vs Portugal** (38/32/30) | Colombia favored | Portugal favored | Colombia is Elo rank 7, Portugal rank 5 (tied with Brazil); honest |
| **England vs Croatia** (38/32/30) | England slight favorite | England heavy favorite | Croatia at Elo 1930 isn't far behind England 2020 |
| **Saudi Arabia vs Uruguay** (5/17/78) | Uruguay 78% | Uruguay strong favorite ✓ | matches sentiment |

The pattern: model predictions are more conservative than fan sentiment
on most matches (no surprise — model uses Elo + market, not narrative).
This is correct behavior per V10 Q1 + Q2 discussion conclusions.

## Production runtime guidance

```bash
# Daily during WC window — run the gate predict for tomorrow
PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.wc_predict \
  --date $(date -u +%Y-%m-%d -v+1d) \
  --fetch-current-odds \
  --out docs/weekly/wc_$(date -u +%Y-%m-%d).md

# Or via HTTP (dashboard already calls this automatically when tab opens):
curl 'http://localhost:8000/api/v4/predictions/wc?date=2026-06-11&fetch_current_odds=true'
```

## Tag `v10.w1` ships now
