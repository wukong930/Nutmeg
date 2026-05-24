# V8 W6 — Dashboard single + pool tabs (Track D first piece)

_V6 W9 shipped `nutmeg-rec` interactive CLI for 单关/串关/复式 but
the dashboard only had a 串关 surface. V8 W6 closes the gap with two
new endpoints + two new dashboard tabs — same product flows, now
accessible via a web form for non-terminal users._

## What W6 ships

### 1. `POST /api/v4/recommend/single`

```bash
curl -X POST http://localhost:8000/api/v4/recommend/single \
  -H 'Content-Type: application/json' \
  -d '{
    "fixtures": [
      {"date": "2025-08-17", "league": "EPL",
       "home_team": "Arsenal", "away_team": "Liverpool",
       "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
       "odds_1x2_H": 2.50, "odds_1x2_D": 3.30, "odds_1x2_A": 2.80}
    ],
    "bankroll": 500.0,
    "top_per_match": 1
  }'
```

Returns:
```json
{
  "generated_at_utc": "...",
  "model": {...},
  "bankroll": 500.0,
  "n_fixtures": 1,
  "n_recommendations": 1,
  "tickets": [{
    "match_id": "EPL_Arsenal_vs_Liverpool",
    "market_type": "1x2",
    "outcome": "H",
    "odds": 2.50,
    "probability": 0.45,
    "ev_per_unit": 0.125,
    "stake": 24.0,           // ¥2-quantized
    "raw_kelly_stake": 24.3,
    "expected_return": 3.0
  }],
  "total_stake": 24.0,
  "total_expected_return": 3.0
}
```

Engine: same `recommend_singles` from V6 W9 — for each fixture builds
all 6 candidate Selections (1X2 × {H, D, A} + handicap_1x2 × {H, D, A}),
filters by `passes_recommendation_thresholds` (5% EV + 5% hit rate),
sizes via fractional Kelly, caps at ¥20k, quantizes to ¥2, keeps at
most `top_per_match` (1-3) per fixture sorted by EV desc.

### 2. `POST /api/v4/recommend/pool`

```bash
curl -X POST http://localhost:8000/api/v4/recommend/pool \
  -H 'Content-Type: application/json' \
  -d '{
    "fixtures": [
      {"date": "2025-08-17", "league": "EPL",
       "home_team": "Arsenal", "away_team": "Liverpool",
       "psc_home": 2.20, "psc_draw": 3.40, "psc_away": 3.40,
       "odds_1x2_H": 1.85, "odds_1x2_D": 3.20, "odds_1x2_A": 4.00,
       "pick": "1x2_H"},
      {"date": "2025-08-17", "league": "EPL",
       "home_team": "Man City", "away_team": "Brighton",
       "psc_home": 1.50, "psc_draw": 4.50, "psc_away": 6.00,
       "pick": "1x2_H"}
    ],
    "n": 2,
    "bankroll": 500.0
  }'
```

The `pick` field on each fixture is the user's pre-decided outcome
(one of `1x2_H/D/A` / `hc_H/D/A`). Pydantic enum validation rejects
anything else with 422.

Engine: same `recommend_pool` from V6 W3 — enumerates all C(M, N)
tickets, sizes each via independent Kelly + ¥2 quantize + ¥20k cap,
optionally rescales to fit `max_total_budget`. Returns ALL candidates
(sorted EV desc); UI filters to `stake > 0` for display.

### 3. Dashboard tab restructure

| # | Tab | Backend |
|---|---|---|
| ① | 单关 | `POST /recommend/single` (new W6) |
| ② | 串关 | `POST /recommend` (existing) |
| ③ | 复式 | `POST /recommend/pool` (new W6) |
| ④ | 录入结果 | `POST /observation/outcomes` |
| ⑤ | ROI 报告 | `GET /observation/roi` |
| ⑥ | 会话历史 | `GET /observation/sessions` |
| ⑦ | 规则说明 | `GET /rules` (V6 W10) |

The 单关 tab is now the default landing (was 串关). Subtitle
updated: "中国体彩 · 胜平负 + 让球胜平负 · 单关 / 串关 / 复式 全玩法推荐".

Each new tab has:
- Sample-data button (loads the V6 W9 demo fixtures into the
  textarea)
- Bankroll / Kelly fraction / mode-specific knobs
- Generate button → calls backend → renders results table

Pool tab also has `N (串关数)` and `总预算上限` inputs matching the
CLI's `--n` and `--max-total-budget`.

### 4. Pydantic schemas

```python
class SingleRecommendRequest(BaseModel):
    fixtures: list[FixtureOddsInput]
    bankroll: float = 1000.0
    top_per_match: int = 1                   # 1..3
    kelly_fraction: float = 0.25
    max_stake_fraction: float = 0.05

class PoolFixturePick(FixtureOddsInput):
    pick: Literal["1x2_H", "1x2_D", "1x2_A", "hc_H", "hc_D", "hc_A"]

class PoolRecommendRequest(BaseModel):
    fixtures: list[PoolFixturePick]
    n: int                                    # 1..8
    bankroll: float = 1000.0
    max_total_budget: Optional[float] = None
    kelly_fraction: float = 0.25
    max_stake_fraction_per_ticket: float = 0.05
```

Plus `SingleTicketResponse`, `SingleRecommendResponse`,
`PoolTicketResponse`, `PoolRecommendResponse`.

## What W6 doesn't do

- **No bet placement.** Same footer on every result: "系统不进行
  自动投注; 推荐仅供参考." (Identical policy to V6 W9 CLI.)
- **No auto-fetch on the web UI.** The CLI has `--auto-fetch`
  (V7 W1) but the web form still requires the user to paste
  fixtures JSON. A separate web-side auto-fetch endpoint could
  drive this from `nutmeg-ingest-odds` but adds an API key
  exposure surface; deferred.
- **No session recording yet.** The existing 串关 tab can record
  to the observation DB via the `record-session` checkbox; the new
  单关 / 复式 tabs don't. Future: extend `observation/recorder` to
  understand single + pool response shapes.
- **No cup-aware artifact integration.** The V8 W6 endpoints use
  whatever `NUTMEG_V4_ARTIFACT_PATH` points to — V5 W12 CatBoost
  default. Switching to a cup-aware artifact (V8 W4 if the
  ablation passes) is the env-var change.

## Tests

`tests/v4/test_recommend_single_pool_api.py` — 17 tests:

| Group | Coverage |
|---|---|
| `TestSingleEndpointShape` (4) | 503 when no artifact; top_per_match range 1..3; min 1 fixture; bankroll > 0 |
| `TestPoolEndpointShape` (3) | 503 when no artifact; n range 1..8; pick enum validation |
| `TestSingleEndpointE2E` (1) | Real artifact: returns valid envelope + per-ticket schema; stake is ¥2-multiple; expected_return == stake × ev_per_unit |
| `TestPoolEndpointE2E` (2) | C(M,N) enumeration; tickets sorted EV desc; n > m → 422 |
| `TestDashboardSinglePoolTabs` (7) | Tab labels (① 单关 / ② 串关 / ③ 复式); panel IDs; endpoint paths wired; form input IDs; render JS functions defined; Chinese market labels; POOL_SAMPLE includes hc_H pick |

Full V4 suite: **682/682 passing** (665 prior + 17 new W6; V6 W10
test updated for the renumbered rules tab).

## Files touched in W6

```
apps/api/src/nutmeg/v4/api/routes.py                  [M] +2 endpoints + helpers
apps/api/src/nutmeg/v4/api/schemas.py                 [M] +4 request/response models
apps/api/src/nutmeg/v4/api/static/dashboard.html      [M] tab restructure (3 new tabs);
                                                          tab-single + tab-pool panels;
                                                          single/pool JS handlers +
                                                          renderers + POOL_SAMPLE
tests/v4/test_recommend_single_pool_api.py            [+] 17 tests
tests/v4/test_rules_endpoint.py                       [M] fix tab-number assertion
                                                          (rules moved ⑤ → ⑦)
docs/V8_ROADMAP.md                                    [M] W6 ✅
docs/v8_w6_dashboard_single_pool.md                   [+] (this file)
```

## Next: V8 W7 — national-team Elo

V8 W7 (Track D second piece):
1. `nutmeg.v4.data.sources.clubelo.fetch_national_team_elo(country)` —
   wraps `http://api.clubelo.com/<NationCode>` endpoint
2. New `national_team_state` dict — keyed by country code (e.g. "ENG",
   "BRA", "ARG")
3. Integrate with V6 W11's `find_team_state_cross_league` so WC / Euro
   / Copa America fixtures (currently fall back to unknown-team path)
   get real per-team signal
4. `nutmeg-ingest-national-elo` CLI

Estimated 3-4 days.
