# V6 Retrospective — what worked, what didn't, lessons for V7

_Ships with `v6.0-shipped`. Written at W12 closeout. Companion to
[V6_HANDOFF.md](V6_HANDOFF.md) — the handoff is "what V6 is"; this is
"what V6 taught us"._

## TL;DR

V6 succeeded as a **product-led layer** over V5's science engine. Every
week shipped something user-facing. Multi-fold validation methodology
(inherited from V5 W5/W6/W9 lessons) caught one major data leak (V6 W5)
and steered us to a real improvement (V6 W6 `recent_n_injuries`).

The 4-week live ROI gate hasn't closed yet — the infrastructure ships;
the answer waits on real-bet data. **That's a feature, not a bug**: V5's
pattern was "more parameters + small val → overfit", and rushing a
"lineup wins" verdict from one ablation would have repeated it.

## What worked

### 1. Product-led weekly slices

V5 mixed science weeks and refactor weeks. V6 stuck to "every week
ships something the user can use **next Saturday**":

- W3 → 复式过关 CLI (lottery's most popular product)
- W4 → ¥2/¥20k/EV-gate constants
- W9 → 单关/串关/复式 interactive menu
- W10 → Chinese rules tab in the dashboard

This forced ruthless scope discipline — couldn't slip into "let me
also rebuild the temperature scaling" tangents because Saturday was
the deadline.

### 2. Multi-fold validation as default

V5's painful lessons (W5 market dynamics, W6 stacker, W9 per-league T
all failed multi-season validation despite single-fold positive signals)
went into V6 W6's methodology design: **4 cutoffs × 2 leagues** before
ANY feature ships into production code.

The result: V6 W5's 9-col lineup set was found to be 7-of-9 bad. The
"good" one was actually a leak. The salvaged feature (`recent_n_injuries`)
needed 3-of-4 fold confirmation before wiring into
`feature_columns_with_lineups()`. Zero false positives shipped.

### 3. Leak hunting as a habit

V6 W5's "−0.0105 log-loss improvement!" was 100% data leakage —
`/injuries` returns the entire season, including events that hadn't
happened on the match date. Catching this required:

1. Suspicion of any single-fold result that's "too good"
2. Investigating the data flow (where does the value come from?)
3. Hardening: `_filter_injuries_before` strict `<` comparison; explicit
   drop of records with empty/missing date
4. Re-running with the fix and seeing the result vanish

V5's similar W5 / W6 / W9 stories trained the habit. The cost: 2 days
of investigation. The save: not shipping a fake feature.

### 4. Lottery rules as one frozen dataclass

V6 W4's `JINGCAI_DEFAULT` dataclass is the single source of truth for
the lottery's structural constants. Every recommend flow imports the
same thresholds; the dashboard's `/api/v4/rules` endpoint serializes
the same dataclass. No "magic 0.05" floating around the codebase.

This paid off immediately: V6 W9's `single_match.recommend_singles`
shipped in 1 day because the threshold / cap / quantize machinery was
already factored. V6 W10's dashboard rules tab needed zero rule-text
duplication — fetched live from `/api/v4/rules`.

### 5. Default = unchanged

V6 W7's lineup-aware artifact ships as **opt-in** (`--with-lineups`).
The V5 W12 CatBoost default stays untouched until W8 live ROI confirms
the backtest direction.

This means:
- Existing automation didn't break on V6 W7's release
- A/B has a real control (the V5 W12 model exactly as shipped)
- Rollback is `git checkout v5.0-shipped` + retraining; no migration

Same discipline as V5 W12 (CatBoost default flip was conditional on
multi-season wins). Both V5 and V6 stuck to it.

### 6. Side-channel features for cup support (V6 W11)

Could have tried "retrain on cup data" and seen log-loss tank from
the small UCL sample. Instead: ship 5 zero-on-existing-data columns
that the GBM can pick up later when V7 backfills cup training data.

Cup matches enter the recommend pipeline today (with cross-league
team_state lookup) using the existing league-trained artifact. Result:
zero regression on shipped predictions, zero new training surface, V7
just has to add training rows.

## What didn't work

### 1. Lineup features as initially designed (V6 W2 → W5)

V6 W2 shipped 9 lineup feature columns based on intuition: XI present
flags, formation compactness for 19 formations, injury counts, XI
minutes-share. The W5 ablation found 7 of 9 fail under leak controls;
the 2 surviving signals (one of which was the leak) didn't even make
sense together.

**Why it failed**: the W2 design was guess-driven (which lineup
intuitions look promising) rather than data-driven (which lineup
signals had ALREADY been validated in published soccer xG / Elo
research). We didn't search the literature first.

**Lesson**: for V7's "national-team Elo" feature, start with what
published clubelo / 538-style models use, then ablate. Don't roll our
own intuition-driven feature set when prior art exists.

### 2. API token in chat history

The API-Football token was pasted in conversation during V6 W1. It's
gitignored in `.env` (chmod 600) but the chat history exposed it. The
user was advised to rotate.

**Lesson**: never paste any production credential — get into the habit
of `.env.example` placeholders + a separate channel for the real
value. The W1 design supports zero-downtime rotation but it should be
done.

### 3. CI doesn't exercise lineup-aware path

`tests/v4/test_e2e.py::TestE2ECatBoostLineups` skips when the API-
Football cache isn't populated. GH Actions CI doesn't have the cache,
so the lineup-aware training + inference paths get zero CI coverage.

**Lesson**: V7 should bake a tiny lineup fixture cache (a single
EPL+ESP_LA_LIGA day) into the repo so CI exercises the path. Not real
data — just enough to verify the build_lineup_features →
feature_columns_with_lineups → predict_lambdas pipeline doesn't crash.

### 4. Settle-on-outcome still manual

`nutmeg-record-outcome` requires the user to type in goals after each
match. Without this, settlements don't accumulate and `nutmeg-ab-report`
can't fill in. V6 W8's ROI gate is gated on this manual loop closing.

**Lesson**: V7 should auto-fetch final scores from API-Football
(already paid for) and call `record_outcome` automatically. Should be
a ~20-line CLI on top of the W1 adapter.

## Patterns that held up from V5

1. **Multi-fold validation before shipping** (V5 W5/W6/W9 → V6 W6).
   Single-cutoff results are dangerous.
2. **Document negative results in detail** (V5 ablation files, V6
   W5/W6 docs). Future you won't re-tread.
3. **Opt-in for new features; defaults stable** (V5 W12 CatBoost flip;
   V6 W7 `--with-lineups`).
4. **One frozen dataclass per "rules" concept** (V5 had its own; V6's
   JINGCAI_DEFAULT extended this).
5. **Every week ships a tag + a doc** (V5.w1...v5.w12, V6.w1...v6.w11).
   The git log IS the project history.

## V7 starting points

These are the obvious next moves, prioritized:

1. **Close the live ROI loop** — record-outcome automation + run
   `nutmeg-ab-report` weekly for 4 weeks. Decision: promote lineup-aware
   to default OR document why backtest didn't translate.
2. **Cup-trained model** — backfill 3-4 seasons of UCL / WC / FA Cup
   fixtures + odds; multi-fold validate the 5 cup feature columns;
   ship retrained artifact.
3. **National-team Elo** — start with clubelo's national-team endpoint;
   wire into the cross-league team_state lookup.
4. **Live odds ingest** — `nutmeg-ingest-odds` CLI hitting API-Football
   at T-60min; replaces the manual fixtures CSV step.
5. **Web UI for `nutmeg-rec`** — V6 W9 ships CLI only. A simple
   form-based web UI (single page calling the existing FastAPI
   endpoints) would close the "no terminal" gap for non-developer
   users.

## Numbers

| Metric | V5 ship | V6 ship | Δ |
|---|---:|---:|---:|
| V4 tests passing | 282 | **468** | +186 |
| LoC (apps/api/src/nutmeg/v4/) | ~6,500 | ~8,400 | +1,900 |
| CLIs in `pyproject.toml` | 9 | **14** | +5 |
| API endpoints | 8 | 9 | +1 (/rules) |
| Feature columns available | 39 (default) | 39 + 2 (opt-in lineup) | +2 |
| Lottery products supported | 1 (串关) | 3 (单关 + 串关 + 复式) | +2 |
| Competition codes registered | 13 (domestic only) | 25 (13 leagues + 12 cups) | +12 |
| Shipped artifact | v4_model_cat (untouched) | + v4_model_cat_lineups (opt-in) | +1 |
| Backtest log-loss (24/25) | 0.9960 | 0.9960 (unchanged default) | 0.0 |
| Backtest log-loss with lineups (24/25 EPL) | n/a | 0.9919 (W6 fold) | −0.0041 |
| Live ROI verdict | n/a | **pending** | data-gated |

## Closing thought

V6's most important deliverable isn't any single feature — it's the
**discipline of catching V5's pattern from the inside**.

V5 W5 / W6 / W9 each shipped a "promising single-fold result" and
multi-season validation caught it. V6 W5 was the same story: a
"−0.0105 lineup improvement" that vanished under leak controls. The
methodology — multi-fold + leak hunting + opt-in defaults — turned a
career of one-week-confidence-then-disappointment into a culture of
"show me 3+ folds before I'll ship it".

That culture is what V7 inherits.
