# V7 Retrospective — what worked, what didn't, lessons for V8

_Ships with `v7.0-shipped`. Written at V7 closeout. Companion to
[V7_HANDOFF.md](V7_HANDOFF.md) — the handoff is "what V7 is"; this is
"what V7 taught us"._

## TL;DR

V7 succeeded as an **operational layer** over V6's product engine.
The user's daily prediction flow went from 5 manual steps to 2.
Three V6 verdicts that were stuck on "manual settlement" can now
close on their own.

The cup-trained model deliverable was honestly de-scoped: V7 shipped
all 4 data-layer pieces (registry + fixtures + features wiring +
odds) but the actual retrain + ablation + artifact ship is V8
territory. **That's not slippage — it's correct sequencing.** Rushing
a cup-trained model with missing upstream (team_canonical, training-
frame UNION) would have repeated V5 W5/W6/W9's "ship a false positive"
pattern.

## What worked

### 1. Parallel tracks instead of sequential weeks

V5 + V6 each ran 12 sequential weeks. V7 ran three tracks (C / A / B)
that overlapped. Track A waited on data; Track B did 3 weeks of
groundwork; Track C delivered immediate UX wins in W1-W3.

The win: **no week sat idle waiting for another week's data**. While
Track A's cron accumulates settlements, Track B made progress that
needs none of that data.

### 2. Daily friction got attacked first

V7 W1's `nutmeg-ingest-odds` killed the most-error-prone manual step
(typing fixtures CSV by hand). V7 W2's `nutmeg-auto-settle` killed
the most-skipped manual step (typing yesterday's scores). V7 W3's
weekly bundle killed the "I'll run the reports later" procrastination
loop.

**Ordering mattered**: W2 (settle) needs W1 (ingest) because both go
through API-Football and the cache layer; W3 (reports) needs both W1
+ W2 because the data has to flow before the reports show anything.
Doing them in W1→W2→W3 order meant each week's user-visible win
compounded.

### 3. Local cron > GH Actions for stateful work

V6 W8's cron was GH Actions (heartbeat + odds canary). V7 W2 + W3
went **local cron** because the observation DB is user-local — GH
Actions can't write to it without committing the binary back into
git, which creates merge hell.

The clean separation:
- **GH Actions**: stateless work (bench cards on committed CSVs;
  odds-CSV artifact; daily summary JSON). Heartbeat / canary.
- **Local cron**: stateful work (observation DB writes, weekly
  report cards). User-owned, user-private.

This separation also implicitly answers a privacy question: real-bet
data stays on the user's machine, doesn't leak through the public
repo's Actions logs.

### 4. Honest scope on Track B

The original V7 W8 plan said "ship `data/v4_model_cat_cup/`
artifact." When the W6/W7 work made clear that real cup training
needed (a) team_canonical cup extension + (b) cup row UNION into
`load_all_matches`, **V7 W8 explicitly de-scoped to "groundwork
complete"** and pushed retrain/ablation/ship to V8.

Two consequences:
1. V7 still shipped useful, complete pieces every week
2. V8 starts with a clear, well-documented bottleneck

The alternative (cramming everything into W8) would have either
slipped the timeline or shipped a half-built ablation.

### 5. Symmetric data layer for cup_history + cup_odds

V7 W8's `data.cup_odds` mirrors V7 W6's `data.cup_history` API:
`normalize_*`, `<canonical>_parquet_path`, `write_*_parquet`,
`load_*_parquet`, `load_multi_season_*`. Same parameter names. Same
return shapes for empty/missing files.

This made the W7 wiring trivial: `merge_cup_fixtures_and_odds` is
a 10-line helper because both sides have `api_football_id`. It also
makes V8's UNION-into-training-frame easy: same loader pattern.

### 6. Per-flag independence in nutmeg-train

V7 W7 explicitly made `--with-cup-features` and `--with-lineups`
independent. `feature_columns_with_cup(include_lineups=False)`
returns 44 cols; `(include_lineups=True)` returns 46. The user can
combine them via flags; the code paths don't tangle.

This caught a bug I almost shipped: my first cut had
`feature_columns_with_cup()` auto-include lineup cols, which would
`KeyError` when `--with-cup-features` was used without the lineup
cache. The independent-flag design forced the realization.

## What didn't work / honest gaps

### 1. The 4-week ROI verdict is still pending

V7's biggest deliverable was **infrastructure for** the lineup
verdict to close. The verdict itself can't close until ≥4 weeks of
real bets accumulate. As of V7 ship, the cron is running but
settlement data is at week 0.

This is **expected by design** (you can't fake data). But it means
the V7 ship doesn't yet answer the original V6 W8 question. V8 W1's
first task is to read `nutmeg-ab-report --weeks 4` and finally
record the verdict.

### 2. Track B groundwork shipped but the model didn't

V7 W6/W7/W8 are clean ML data infrastructure. They don't produce a
better model on their own — V8 W1-W3 work is needed to actually
union cup rows into training, reconcile team names, run the multi-
fold ablation, and (maybe) ship the cup-aware artifact.

Counter-argument: **the V7 work was the harder part**. Building the
cup data store + the feature wiring + the merge helper is multi-week
work; the V8 finish line is 1-2 weeks if no nasty surprises emerge.

### 3. Team-name reconciliation pushed to V8

V7 W7's `_merge_cup_round_labels` joins on
`(date, league, home_team, away_team)`. API-Football names and
football-data.co.uk names usually align, but edge cases like
"Man United" vs "Manchester United" exist. The merge silently
drops mismatches.

V8 needs to scan all V7 W6+W8 parquets against the V5 W3
`team_canonical` map and extend it. Effort: 1-2 days but tedious.

### 4. CI still doesn't exercise --with-cup-features end-to-end

The W7 tests cover argparse acceptance and `build_feature_frame`
column emission, but they don't run a full `nutmeg-train
--with-cup-features` end-to-end (which needs cup parquets baked
into the repo or fetched in CI — neither acceptable).

Same gap as V6 had with `--with-lineups`. The pragmatic fix is
to ship a tiny fixture cache in the repo for both paths — V8
could batch these.

### 5. No actual cup data has been ingested yet

V7 W6 + W8 ship the **CLI**, not the data. The user runs
`nutmeg-ingest-cup-history --leagues UCL,UEL --seasons 2021,2022,2023,2024`
once at V8 W1 to actually pull. Same for `nutmeg-ingest-cup-odds`.
~8 + 1320 API calls; comfortable within the Pro plan budget.

This is correct — caches shouldn't be in git. But it's a "remember
to do this" step on the V8 starter checklist.

## Patterns that held up from V5+V6

1. **Multi-fold validation before shipping any ML claim.** V7 didn't
   retrain (correctly), so didn't violate this. V8 will.
2. **Opt-in for new features; defaults stable.** V7's
   `--with-cup-features` mirrors V6's `--with-lineups`. Same pattern.
3. **One frozen dataclass / module per concept.** V7's `cup_history`
   and `cup_odds` modules extended V6 W11's `competitions` registry
   without modifying it.
4. **Every week ships a tag + a doc.** V7 has 6 weekly docs +
   V7_HANDOFF + this retrospective. The git log IS the project
   history.
5. **Honest documentation of what each week DOESN'T do.** Every
   weekly doc has a "What W$N doesn't do" section. V8's expectations
   start from those explicit gaps, not from optimistic blanks.

## New pattern V7 introduced

### Tracks > Weeks

V5 + V6 ran 12 sequential weeks with one theme each. V7 ran three
parallel tracks. This worked because:

- Track A is data-gated → can't be made go faster
- Track B is multi-week sequential → blocking on it would idle Track C
- Track C is independent → can complete entirely on its own

For V8, the same logic suggests:
- Track A (verdict): single 1-week sprint once data ready
- Track B finish (cup-aware ship): ~2-3 weeks sequential
- New track for P2 items (national-team Elo, dashboard 单关/复式
  surfaces, etc.): opportunistic

Don't pretend you can run 12 sequential weeks when reality has
data-gated and independent work.

## V8 starting points

Listed by likely value, highest first:

1. **Run `nutmeg-ingest-cup-history` + `nutmeg-ingest-cup-odds` for
   real.** UCL + UEL × 4 seasons = ~1320 API calls. Pre-req for
   everything else in Track B.
2. **Read the lineup-aware ROI verdict** if 4 weeks of cron data have
   accumulated. Promote default or document the gap.
3. **Team-name reconciliation**: extend `team_canonical` to cover
   cup teams. Scan + map. 1-2 days.
4. **Cup row UNION into `load_all_matches`**: extend training data
   loader. Run multi-fold ablation. Ship cup-aware artifact if
   ≥ 3/4 folds improve.
5. **Web UI for `nutmeg-rec`**: form-based wrapper. Closes the
   "non-terminal users" gap.
6. **National-team Elo**: clubelo's `/<NationCode>` endpoint. Unblocks
   WC / Euro predictions.

## Numbers (V6 → V7)

| Metric | V6 ship | V7 ship | Δ |
|---|---:|---:|---:|
| V4 tests | 468 | **598** | +130 |
| CLIs | 14 | **19** | +5 |
| Modules added | — | 8 (3 data, 5 CLI) | +8 |
| Daily user manual steps | 5 | **2** | -3 |
| Live-data → A/B card latency | ≥1 week | ≤1 day | -6 days |
| Cup data layers complete | 1 (V6 W11 registry) | **4** (+ fixtures + features wiring + odds) | +3 |
| Tracks shipped | 1 (sequential weeks) | **3** (C ✅ A ⏳ B ✅) | parallelized |
| Backtest log-loss (24/25) | 0.9960 | 0.9960 (unchanged default) | 0.0 |
| Lineup ROI verdict | pending | pending (still data-gated) | unchanged |
| Cup-trained artifact | not started | **groundwork complete** | +infrastructure |

## Closing thought

V7's most important deliverable isn't any single CLI — it's the
**discipline of de-scoping cleanly when the upstream isn't ready**.

V5 W5 / W6 / W9 shipped negative ablations and labeled them
honestly. V6 W5 caught a data leak and labeled it. V7 W7 + W8
faced the same fork: "ship the cup-aware artifact" was the
original W8 plan, but the upstream pieces (team_canonical, training-
frame UNION) weren't ready. The honest move was to ship the
groundwork, de-scope the artifact, and explicitly tell V8 "your
job".

That discipline — building tools you trust BECAUSE they don't
overpromise — is what V8 inherits.

Track A is patient. Track B is queued. Track C closed the loop.
That's V7.
