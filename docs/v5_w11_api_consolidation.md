# V5 W11 — API surface consolidation

_Surface the W7 (CatBoost backend) + W8 (snapshot phases) work through the
HTTP API, and add a lightweight predictions-only endpoint for the
dashboard / mobile clients that don't need the parlay enumeration._

## Background

W2 already deleted the entire `apps/api/src/nutmeg/api/` legacy v1 route
tree along with the Next.js frontend, so the original W11 task of "remove
v1" is moot. The remaining product gaps the V5_ROADMAP called out were:

1. A way for clients to fetch model predictions without paying the parlay
   enumeration cost
2. Exposing W7 `model_type` so callers know which backend produced the
   prediction
3. Threading W8 `snapshot_phase` through the API so recording can be
   labelled correctly
4. An HTTP wrapper around W8's `live_vs_backtest` so dashboards and
   external monitors can poll it

This week closes all four.

## What's new

### `POST /api/v4/predictions/upcoming`

A lightweight cousin of `/api/v4/recommend`. Same `fixtures` body shape,
but the response is just per-fixture lambdas + 1X2 + (optional) handicap
probabilities — no Kelly, no parlay enumeration.

Use cases:
- Dashboard "tomorrow's matches" panel
- Mobile clients that show probabilities and let the user choose stakes
  manually
- Cheap warm-up call for cache priming

```http
POST /api/v4/predictions/upcoming
Content-Type: application/json

{
  "fixtures": [
    {"date": "2025-08-17", "league": "EPL",
     "home_team": "Arsenal", "away_team": "Liverpool",
     "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60}
  ]
}
```

Response:

```json
{
  "generated_at_utc": "2026-05-23T03:00:00+00:00",
  "model": {
    "model_type": "catboost",
    "cat_features": ["league"],
    "trained_at_utc": "2024-08-01T00:00:00+00:00",
    ...
  },
  "n_fixtures": 1,
  "predictions": [
    {
      "home_team": "Arsenal", "away_team": "Liverpool", "league": "EPL",
      "date": "2025-08-17",
      "lambda_home": 1.23, "lambda_away": 1.37,
      "p_home_1x2": 0.42, "p_draw_1x2": 0.27, "p_away_1x2": 0.31,
      "handicap_home": null, "p_home_handicap": null,
      "p_draw_handicap": null, "p_away_handicap": null
    }
  ]
}
```

Distinguishes from `/recommend` by:
- No `recommendations` field in the response
- No `bankroll` / `top_n` / `min_*` in the request
- Always returns 200 with empty `predictions: []` for empty fixtures input
  (the recommend path requires at least 1 fixture)

### `GET /api/v4/observation/live-vs-backtest`

Read-only GET endpoint that mirrors what `nutmeg-live-vs-backtest` CLI
returns but without running a full walk_forward (which would be too
expensive in an HTTP path). Backtest comparison stays in the CLI; this
endpoint is for the *live* slice.

Query params:
- `weeks` (int, default 4) — live window
- `snapshot_phase` (str, optional) — filter to one phase

Returns 200 with stats + empty counts when DB is fresh, or 503 with detail
when the configured DB doesn't exist.

### Schema additions

- `HealthResponse.model_type` — surfaces W7 backend identity in health
- `ModelInfo.model_type` / `cat_features` — same, in every recommend +
  predictions response
- `RecommendRequest.snapshot_phase` (Literal `pre_close | closing | post_close`,
  default `closing`) — typed so pydantic rejects invalid values at 422

## Architecture state after W11

```
GET  /api/v4/health                          — backend identity + artifact status
GET  /api/v4/dashboard                       — single-file HTML UI
POST /api/v4/recommend                       — full Kelly + parlay
POST /api/v4/predictions/upcoming            — NEW (W11) lightweight
GET  /api/v4/observation/health              — DB status
GET  /api/v4/observation/roi                 — headline + per-k-legs + per-league
GET  /api/v4/observation/sessions            — recent sessions
POST /api/v4/observation/outcomes            — batch results + auto-settle
GET  /api/v4/observation/live-vs-backtest    — NEW (W11) live slice
```

No `/api/v1/*` — those were removed in W2.

## Tests

11 new tests (282 total):

`tests/v4/test_api.py` (+8):
- `TestPredictionsUpcoming` — basic shape, no `recommendations` field,
  `model_type` surfaced, handicap optional both ways, empty fixtures
  returns 200 with empty list
- `TestRecommendSnapshotPhase` — accepts `pre_close`, rejects `bogus` at 422

`tests/v4/test_observation_api.py` (+4):
- `TestLiveVsBacktestEndpoint` — 503 when no DB, shape with populated DB,
  `snapshot_phase` filter, within-tolerance default when no backtest provided

## What W11 doesn't do (intentionally)

- **`predictions/upcoming` doesn't fetch live odds.** It's a pure
  prediction endpoint; the client supplies fixtures + closing odds in
  the body. Live odds ingest is blocked by W3 (OddsPortal Cloudflare;
  understat JS-rendered) and remains W12-deferred behind the
  `--model cat`-style flag-it-when-it-exists approach.
- **No production migration of the default to CatBoost.** Still W7's
  call — the W8 observation cron needs to compare lgb vs cat in
  live conditions before flipping the default in W12.

Total V4 suite: **282/282 passing**.
