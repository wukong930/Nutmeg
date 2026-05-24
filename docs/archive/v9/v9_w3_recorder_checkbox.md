# V9 W3 — Dashboard recorder checkbox actually plumbed

_Closes the V5 W11-era no-op: the "记录到观测库" checkbox on the 串关
tab existed but was never read by JS or honored by the endpoint. V8 W6
added 单关 + 复式 tabs without checkboxes at all. V9 W3 unifies them
with a two-gate design (env + request flag) and visible feedback._

## What W3 ships

### Two-gate recording

Both must be true for an endpoint to write to the observation DB:

| Gate | Lives in | Default |
|---|---|---|
| Server enable | `NUTMEG_V4_OBSERVATION_DB` env var | unset (recording disabled) |
| Request opt-in | `request.record_session: bool` | False |

This matters because the env-only approach (post-V8 P1#5) recorded
**every** request — including local-dev test calls. The W3 design
lets the user (or a script) opt-in per request, while the env var
still governs whether any recording is even possible.

| Server `NUTMEG_V4_OBSERVATION_DB` | Request `record_session` | Result |
|:---:|:---:|---|
| unset | any | no record |
| set | False | no record |
| set | True | recorded |

### Schemas (`nutmeg.v4.api.schemas`)

Three request models gain `record_session: bool = False`:

- `RecommendRequest` (串关, V4 W8 path)
- `SingleRecommendRequest` (V8 W6 单关)
- `PoolRecommendRequest` (V8 W6 复式)

### Routes (`nutmeg.v4.api.routes`)

- New helper `_should_record_session(req_record_flag) -> Optional[str]`
  returns the DB path iff **both** gates are satisfied. Endpoints use
  truthiness check.
- All 3 endpoints (`/recommend`, `/recommend/single`, `/recommend/pool`)
  call the helper after building the response, before returning.
- 串关 endpoint **now records at all** (was a V5 W11 no-op for 4 years
  of conversations). CLI `nutmeg-recommend --record-to` continues to
  work independently for command-line workflows.
- Recording failures caught + logged; never break the response.

### Dashboard (`api/static/dashboard.html`)

- 单关 tab: new `<input id="single-record-session" type="checkbox">` next
  to the Kelly fraction input
- 复式 tab: new `<input id="pool-record-session" type="checkbox">`
- 串关 tab: existing `record-session` checkbox JS reads its `.checked`
  state and posts into the request body
- All 3 success branches append "· 📝 已请求录入观测库" to the status
  line when the box is checked, so the user has visible confirmation
  the request opted in (separate from whether the server-side env
  actually persisted)

### Tooltip

Each checkbox has `title="需要服务器设 NUTMEG_V4_OBSERVATION_DB 环境变量才会真正落库"`.
Surfaces the second gate so users don't expect web-only configuration.

## What W3 doesn't do

- **No persistent confirmation indicator.** The status text shows "请求
  录入" but doesn't query a `/api/v4/observation/sessions/latest`
  endpoint to confirm. Trade-off: would need a synchronous read-back
  after the write; out of scope for this minimal W3.
- **No checkbox state persistence across page reloads.** Box resets on
  refresh. Trade-off: would need localStorage; small, deferred.
- **No CLI side.** `nutmeg-recommend --record-to` and `nutmeg-rec`
  already have CLI-side recording. This W3 is web-side only.
- **No prediction/upcoming endpoint.** `/predictions/upcoming` doesn't
  record (it's prediction-only, no recommendation rows to settle).

## Behavior change from post-V8 P1#5

Post-V8 P1#5 made `/recommend/single` + `/pool` auto-record on env alone.
V9 W3 **tightened** this to require the request flag too.

Practical impact: if a user had `NUTMEG_V4_OBSERVATION_DB` set since
the P1#5 commit, the same scripts that used to auto-record now need
`record_session: true` in the request body to keep recording.

V9 W3 documented this in the V9 retrospective as **deliberate**: the
env-only path was too coarse for daily-cron + manual-test workflows
sharing the same server. The two `test_recorder_single_pool.py` tests
that asserted env-only recording were updated to add the request flag.

## Tests

`tests/v4/test_record_session_gate.py` — 20 tests:

| Group | Coverage |
|---|---|
| `TestSchemaDefault` (3) | `record_session` defaults to False on all 3 request models |
| `TestShouldRecordSessionHelper` (4) | All 4 (env, req) combinations: both on → DB path; env off → None; req off → None; both off → None |
| `TestRecommendEndpointGate` (4) | /recommend 4 combos × 1 endpoint (E2E with real artifact) |
| `TestSingleEndpointGate` (3) | /recommend/single 3 critical combos |
| `TestPoolEndpointGate` (3) | /recommend/pool 3 critical combos |
| `TestDashboardWiring` (3) | 3 checkboxes present in HTML, JS posts `record_session:` field, "已请求录入观测库" feedback in 3 success branches |

Plus the 2 P1#5 endpoint tests updated to opt-in via the new field
(behavior change documented above).

Full V4 suite: **759/759 passing** (739 pre-V9-W3 + 20 new W3).

## Files touched in W3

```
apps/api/src/nutmeg/v4/api/schemas.py              [M] +record_session on 3 models
apps/api/src/nutmeg/v4/api/routes.py               [M] +_should_record_session helper;
                                                      /recommend now records; /single +
                                                      /pool use double-gate
apps/api/src/nutmeg/v4/api/static/dashboard.html   [M] +2 checkboxes (单关, 复式);
                                                      3 JS POSTs include record_session;
                                                      3 status branches show feedback
tests/v4/test_record_session_gate.py               [+] 20 tests
tests/v4/test_recorder_single_pool.py              [M] 3 tests updated for double-gate
docs/v9_w3_recorder_checkbox.md                    [+] (this file)
docs/V9_ROADMAP.md                                 [M] W3 ✅
```

## Next: V9 W4 — CI fixture cache

Three V* retrospectives (V6, V7, V8) noted CI doesn't exercise
`--with-lineups` / `--with-cup-data` paths because the API-Football
cache isn't in CI. V9 W4 bakes a minimal cache so GH Actions actually
runs the lineup-aware training path end-to-end. Estimated 1-2 days.
