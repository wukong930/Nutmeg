# V8 W4 — Cup ablation NOT RUNNABLE: historical odds unavailable

_Negative result from a real attempt, 2026-05-24. The V7 W8 +
V8 W2/W3 infrastructure works correctly, but the underlying data
source assumption was wrong. Track B's cup-aware artifact ship is
**blocked on data, not code**, and the blocker is structural to
API-Football's Pro plan rather than fixable on our side._

## What happened

V7 W8 shipped `nutmeg-ingest-cup-odds` to backfill per-fixture Pinnacle
1X2 odds via API-Football's `/odds` endpoint. The CLI's design assumed
`/odds?fixture=<fid>` returns closing odds for past matches — same
way `/fixtures?id=<fid>` returns finished match metadata.

V8 W4 ran the full pipeline end-to-end against UCL + UEL × 4 seasons:

```bash
nutmeg-ingest-cup-history --leagues UCL,UEL --seasons 2021,2022,2023,2024
# → 1,719 finished cup fixtures in 8 API calls

nutmeg-ingest-cup-odds --leagues UCL,UEL --seasons 2021,2022,2023,2024 \
    --throttle-ms 150
# → 1,719 API calls completed successfully (200 OK each)
# → 0 odds rows persisted across all 8 (league, season) parquets
```

**Every single `/odds?fixture=<fid>` returned an empty response array
for finished cup matches.** Investigation confirmed this isn't a
bookmaker-filter issue or a cup-specific quirk:

```python
# Most recent UCL fixtures
fid=1374812 PSG vs Inter (2025-05-31): 0 envelopes
fid=1371731 PSG vs Arsenal (2025-05-07): 0 envelopes
fid=1371733 Inter vs Barcelona (2025-05-06): 0 envelopes

# Comparison: random EPL fixture from Aug 2024
fid=1208022 (an EPL match): 0 envelopes

# Probe for an alternate historical endpoint
/odds/history → 404 "The Odds/history endpoint does not exist"
```

`/odds` is **upcoming-only by design**. Once a match finishes,
API-Football drops the pre-match odds from the endpoint. There's no
paid `/odds/history` either — the Pro plan ($19/mo) doesn't include
historical odds at all.

This was not discoverable until we ran the full ingest, because:
- `/odds?fixture=<fid>` returns 200 (not 404) even when the response
  array is empty. The CLI counted "200 OK" as a successful call.
- The 8 `/fixtures` calls in W6 worked correctly because `/fixtures`
  is history-friendly. Only `/odds` is upcoming-only.
- Our V7 W8 unit tests mocked `/odds` with hand-crafted envelopes, so
  none of them exercised the live empty-response behavior.

## Why this is a hard ceiling

| Workaround attempted | Result |
|---|---|
| Use a different bookmaker (Bet365 / Unibet) | `/odds` returns 0 envelopes regardless — no book is queried because there's nothing for ANY book |
| `/odds/history` endpoint | 404, doesn't exist on API-Football |
| Cross-reference football-data.co.uk for UCL/UEL closing odds | football-data.co.uk's CSV catalog covers domestic leagues only; UCL/UEL not in the corpus |
| Use V4 model's own `market_p_*` as a proxy for cup rows | Circular — would train the model on its own outputs |
| Scrape OddsPortal historical | V5 W3 found it Cloudflare-blocked (the pre-existing V5 attempt) |

The blocker is **structural**: cup-aware ML training requires
historical odds (psc_home/draw/away → market features → primary GBM
signal), and we have no way to get those without either:
1. A different paid API tier or service
2. Multi-season forward accumulation via V7 W1's live `nutmeg-ingest-odds`
   (would take 1 full UCL season ≈ 250 matches to be useful)

## What V8 W4's ship-gate verdict is

Per V8 W3's `nutmeg-cup-ablation` runbook, the verdict gate was:
"≥ 3/4 folds improve by ≥ −0.001 log-loss → ship `data/v4_model_cat_cup/`".

**Actual outcome**: ablation **cannot be executed** because:
- `build_cup_training_rows` (V8 W2) inner-joins fixtures × odds; both
  sides must have data
- All 8 `cup_odds` parquets are empty
- `merge_cup_fixtures_and_odds(how="inner")` produces 0 rows
- The training frame UNION (V8 W2) adds 0 cup rows
- `--with-cup-data` becomes a no-op relative to baseline
- The 4 ablation modes (baseline / cup_data / cup_features / cup_full)
  collapse to 2 (baseline ≡ cup_data; cup_features ≡ cup_full)

**Decision**: V8 W4 ships this writeup as the verdict. No
`data/v4_model_cat_cup/` artifact gets trained. Track B closes here
until a viable historical odds source is found.

## What still works (V7 W8 + V8 W2/W3 not wasted)

The infrastructure remains useful for any future fix:

| Component | Status |
|---|---|
| `nutmeg-ingest-cup-history` (V7 W6) | ✅ Works perfectly — 1,719 fixtures + scores backfilled in 8 calls |
| Cup-history parquets on disk | ✅ Real data, exercisable by future scoring/Elo work |
| `team_canonical` global lookup (V8 W1) | ✅ Validated on real cup-team names (158 unique teams across UCL+UEL: 38 exact, 20 alias, 1 fuzzy false-positive [Rangers→Angers], 154 unmatched outside V4 corpus) |
| `cup_training` module + UNION (V8 W2) | ✅ Code path correct; will work the moment cup_odds parquets aren't empty |
| `cross_league_state` seeding (V8 W3) | ✅ Independent of cup data; benefits any future cross-league training |
| `nutmeg-cup-ablation` runner | ✅ Will produce verdict cards when given non-empty cup_odds |

V8 W2's `build_cup_training_rows` even handled the empty-odds case
gracefully — `merge_cup_fixtures_and_odds(how="inner")` returns an
empty DataFrame and the rest of the pipeline no-ops cleanly. No
crash; just no signal.

## What V9 should do

Three paths, listed by likelihood × cost:

### Path A — Live forward accumulation (lowest effort)
Extend V7 W1's `nutmeg-ingest-odds` daily cron to include UCL + UEL
when fixtures fire. After 1 UCL season (~250 matches Aug–May), the
cup_odds cache has enough to retry the ablation. **No new code, no
new paid service**, but a 9-month wait.

```bash
nutmeg-ingest-odds --leagues EPL,ESP_LA_LIGA,UCL,UEL --date $(date -I)
```

### Path B — Find a paid historical odds source
- **Sportradar Trading Odds API**: starts at ~$200/mo, includes historical
- **OddsPortal data dump** (third-party, hardcoded snapshot) — irregular
- **Betfair Exchange historical** — free with account, but exchange
  prices ≠ traditional bookmaker (different vig structure)

V9 task: cost/benefit analysis, then either subscribe + reingest or
freeze Track B.

### Path C — Accept and freeze Track B
Document Track B as "infrastructure complete, data unavailable on
current tier". The cup-aware artifact is the only delivery that
needed historical cup odds; everything else V8 shipped (national-team
Elo, dashboard tabs, cross-league seeding) remains useful. V9 focuses
elsewhere (Track A close, national-team Elo model integration with
actual WC/Euro fixtures, etc.).

**Recommended**: Path A + Path C in parallel. Start the forward
accumulation now (~5 lines of cron change), document Track B as
frozen pending data, move on.

## Pattern check: V5-V8 negative-result discipline

This is the project's **5th documented negative result**:

| Iteration | Theme | Why it failed |
|---|---|---|
| V5 W5 | Market-dynamics drift features | 3/3 seasons worse log-loss; Pinnacle closing already absorbs drift |
| V5 W6 | LogReg ensemble stacker | 3/3 seasons worse; correlated bases + small val |
| V5 W9 | Per-league temperature | 3/3 seasons worse; 90-day val too sparse |
| V6 W5 | Lineup features (initial 9-col set) | 7/9 features failed; 1 was a leak; salvaged 1 |
| **V8 W4** | **Cup-aware artifact** | **Historical odds unavailable from API-Football** |

The pattern V5/V6 retrospectives wrote: "5 versions of negative
findings shipped means the methodology works — wrong ideas get caught
early, documented, and don't re-ship as silent technical debt." V8 W4
extends the pattern. The cost of catching this at the data layer (a
2-hour ingest run + 1 hour writeup) is far less than the cost of
shipping a "cup-aware" artifact trained on empty cup data.

## Files touched in W4

```
docs/v8_w4_cup_ablation_negative.md    [+] (this file)
docs/V8_ROADMAP.md                     [M] W4 marked ❌ (negative outcome)
```

No code changes — the V8 W2/W3 code was correct; the data assumption
was wrong. Cup-odds parquets on disk are kept (empty) as evidence:

```
data/external/cup_history/UCL_2021.parquet  (218 fixtures)  → gitignored
data/external/cup_history/UCL_2022.parquet  (214 fixtures)  → gitignored
... (8 files, 1,719 total finished fixtures)
data/external/cup_odds/UCL_2021.parquet     (0 rows — confirmed empty)
... (8 empty files)
```

## Verification — how to reproduce

```bash
# 1. Pull a known UCL fixture's odds (will return 0 envelopes)
PYTHONPATH=apps/api/src python -c "
from nutmeg.v4.data.sources import api_football
print(len(api_football.fetch_odds(1374812, refresh=True)))
"
# Expected: 0

# 2. Probe /odds/history (will return 404)
PYTHONPATH=apps/api/src python -c "
from nutmeg.v4.data.sources import api_football
api_football._request('/odds/history', {'fixture': 1374812}, refresh=True)
"
# Expected: ApiFootballError: '/odds/history' endpoint does not exist.

# 3. Confirm: an EPL fixture from 2024 also returns 0 envelopes
PYTHONPATH=apps/api/src python -c "
from nutmeg.v4.data.sources import api_football
import datetime as dt
fixtures = api_football.fetch_fixtures_for_date(dt.date(2024, 8, 17), 'EPL')
fid = fixtures[0]['fixture']['id']
print(f'EPL fid={fid}: {len(api_football.fetch_odds(fid, refresh=True))} envelopes')
"
# Expected: 0
```

All three confirm: **`/odds` is upcoming-only; no path to historical
cup odds on the API-Football Pro tier**.

## Bottom line

V8 W4 is a negative result. The cup-aware artifact won't ship in V8.
Track B closes with infrastructure complete and a data-layer block
documented. V9 W1's first task is the **path A vs path B vs path C
decision** above — same shape as V5 W12's paid-data decision and
V8 W7's national-team Elo model-integration deferral.

The V5/V6/V7/V8 methodology held: no false positive shipped. The
2-hour cost was the methodology working as designed.
