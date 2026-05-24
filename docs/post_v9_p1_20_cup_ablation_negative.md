# post-v9 P1#20 — Cup ablation **NEGATIVE**, V10 trigger #1 closed

_The 9-month wait dissolved by buying the right data. Result: cup
data UNION doesn't reliably improve domestic league predictions.
Ship gate (≥ 3/4 folds improving ≥ -0.001 log-loss) NOT met.
Decision: do NOT ship cup-aware artifact. V10 trigger #1 (cup
ablation) is now permanently closed via real data, not handwaving._

## TL;DR

```
Cutoff      Baseline   Cup-full    Δ log-loss   Verdict
2024-01-15  1.0017    0.9992      -0.0025      ✓ pass
2024-05-01  0.9963    0.9969      +0.0005      ✗ fail
2024-08-01  0.9971    0.9985      +0.0014      ✗ fail
2024-12-01  1.0029    1.0014      -0.0015      ✓ pass

Ship gate: ≥ 3/4 folds with ≥ -0.001 improvement
Result:    2/4 folds passed → ❌ DO NOT SHIP
```

**Project's 7th honest negative result** (after V5 W5/W6/W9, V6 W5
[pre-fix], V8 W4 [data wall], V9 W6).

## Why this is now answered, not deferred

Before P1#20: V8 W4 documented `/odds` is upcoming-only on
API-Football. Estimated 9 months for forward accumulation via daily
cron. Cup ablation = "wait and see".

After P1#20: bought The Odds API Starter tier ($30/mo, ~$30 for the
backfill), wrote 1 source module + 1 ingest CLI, ran 4-season
backfill in 5 minutes. **Verdict in 3 hours, not 9 months.**

## What does NOT ship

- ❌ Cup-aware artifact (`data/v4_model_cat_cup/`) — never trained,
  never will be (without compelling new evidence)
- ❌ Continued daily UCL/UEL Path A accumulation — the question it
  was meant to answer is now answered. The launchd `daily_odds` job
  CAN remove UCL/UEL from its leagues list if you want to save
  API-Football quota (~5-10 calls/day). Or keep them as is for
  observation continuity.

## What DOES ship (infrastructure now reusable)

1. **`nutmeg.v4.data.sources.odds_api`** — full Python client for The
   Odds API. Supports current + historical endpoints. Cache + quota
   logging built in. Reusable for any future cup/national-team odds
   needs.
2. **`nutmeg-ingest-cup-odds-via-odds-api`** — CLI to backfill any
   (league × season) combo from The Odds API. Configurable date
   range + skip-existing + unmatched-report.
3. **13 new team-name aliases** in the CLI's local map (Sporting
   Lisbon → Sporting CP, LOSC Lille → Lille, etc.) — covers the
   Odds-API → API-Football spelling gaps the existing
   CUP_TEAM_ALIASES didn't.
4. **`cup_ablation.py` bug fix** — original code read
   `pooled.get("n_test")` and `pooled.get("log_loss_gbm_temp")` but
   walk_forward actually returns `test_n_gbm` + nested dict
   `pooled["gbm_dc_temp"]["log_loss"]`. Original cup_ablation
   would have always returned NaN even if you HAD data. Now fixed.

## Diagnostic — what we learned about the cup signal

The 4 cutoffs show a pattern:

```
2024-01-15  (mid UCL group stage) → cup helps   ✓
2024-05-01  (UCL finals season)   → cup neutral ✗
2024-08-01  (pre-season summer)   → cup hurts   ✗
2024-12-01  (UCL group climax)    → cup helps   ✓
```

**Interpretation**: cup data only helps when the test window has
cup-active fixtures (Jan, Dec). When training+test windows are
predominantly domestic-only (summer cutoffs), adding cup data
DILUTES the team-state signal with cross-competition noise that
doesn't generalize back to league-only predictions.

Plus: 273/556 cup rows dropped due to unresolved team names in the
cross-league pool (Lincoln Red Imps, Crvena Zvezda etc. — small
clubs that play in cup qualifying but not in our 5 league
registries). The ablation effectively trained on 283 cup rows,
not 556.

## Could a more aggressive intervention save this?

A "cup-active months only" filter could be added:
- Only include cup_data when test_cutoff is in [Sep-May]
- Skip cup_data for Jun-Aug cutoffs

This is mode-dependent training, more complex than the V8 W3
"always-on" design. The marginal gain (2 folds × ~0.002 log-loss =
~0.001 average improvement) is below the V5 W12 ±0.005 noise band.

**Decision: not worth the additional complexity.** Cup ablation
backlog item closed.

## Quota economics

| Item | Quota |
|---|---:|
| Plan total (monthly) | 20,000 |
| Used for backfill (4 seasons × 2 leagues = 264 calls × ~10) | ~1,640 |
| Remaining after backfill | 18,360 |
| Monthly cost (Starter tier) | $30 |
| **Cost per row of cup_odds** | **$0.054** |

556 cup_odds rows for $30. Even though the verdict is NEGATIVE, the
infrastructure investment was small and the answer is now permanent.

## Decision: keep or cancel The Odds API subscription?

The Starter tier is now **excess capacity** for the project:
- Cup ablation answered → done
- Forward UCL/UEL accumulation → no longer needed
- Daily cron already uses API-Football for league odds

| Decision | Reasoning |
|---|---|
| **Cancel subscription** (recommended) | Cup question answered; no other pending use. Save $30/mo = $360/yr. |
| Keep for "what if" | Future ablations on new markets (totals, BTTS, handicap) could reuse the infrastructure. Cost is real ($360/yr) for hypothetical value. |

Both are defensible. I'd lean cancel — the ROI on the next $360
is unclear without a specific question to answer.

## What this closes from the V10 backlog

V9_HANDOFF V10 trigger conditions:
- ~~Cup ablation triggers~~ → **CLOSED (negative)** ✓
- Lineup ROI verdict → already closed by P1#18 (positive ship) ✓
- New product gap → unchanged

**Both data-gated V10 triggers are now resolved.** V10 will only
start if a real product change (live in-play, new market, platform
migration) surfaces — which is genuinely a "wait for user direction"
condition, not a "wait for data" condition.

## Files touched in P1#20

```
apps/api/src/nutmeg/config.py                                [M] +odds_api_key setting
apps/api/src/nutmeg/v4/data/sources/odds_api.py              [+] HTTP client + parser (~300 lines)
apps/api/src/nutmeg/v4/cli/ingest_cup_odds_via_odds_api.py   [+] backfill CLI (~280 lines)
apps/api/src/nutmeg/v4/cli/cup_ablation.py                   [M] fix wrong dict-key lookups
pyproject.toml                                               [M] +CLI script entry
docs/post_v9_p1_20_cup_ablation_negative.md                  [+] this writeup
docs/post_v9_p1_20_cup_ablation_verdict.md                   [+] raw ablation output card
```

Plus 556 cup_odds parquets written under `data/external/cup_odds/`
(gitignored — large data files stay local).

## Implication for the project

The post-v9 P1 chain has now resolved **both** of the data-gated
V10 triggers (lineup ROI: positive ship at P1#18; cup ablation:
negative close at P1#20). The project is in genuine maintenance
mode now — no remaining "waiting on data" items, just "waiting on
direction".

This is the cleanest possible end state. 6+ months of project
backlog dissolved in ~24 hours of focused work by:
1. P1#16 — replacing failed GH Actions cron with working local pipeline
2. P1#17/18 — replacing 4-week wait with same-day backtest verdict
3. P1#20 — replacing 9-month wait with $30 of purchased data

## Lesson for future projects

**"Wait for data" is often a substitute for "we haven't checked what's
purchasable yet"**. The cup_odds gap had been documented as "9 months
of forward accumulation" since V8 W4. The actual cost was $30 + 3
hours. The marginal value of writing that check 6 months ago instead
of today is meaningful — but doing it now is still the right call
because the answer (negative) means the wait was going to be wasted
anyway.

Generalize: when a project enters "wait for data" mode, run a 30-min
"can we buy this" assessment. The answer might still be no, but the
times it's yes are extraordinarily valuable.
