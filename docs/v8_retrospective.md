# V8 Retrospective — what worked, what didn't, lessons for V9

_Ships with `v8.0-shipped`. Written at V8 closeout. Companion to
[V8_HANDOFF.md](V8_HANDOFF.md) — the handoff is "what V8 is"; this is
"what V8 taught us"._

## TL;DR

V8 succeeded as the **finish-and-extend layer** over V7. Track B's
cup-trained model groundwork (started V7 W6) got its closing pieces —
team canonicalization, training-frame UNION, cross-league seeding,
ablation runner — though the actual ablation run + ship decision
remain data-gated for V9 W1.

The single biggest design payoff of V8: **opt-in flags throughout**.
Every new path (`--with-cup-data`, `--with-cup-features`,
`cross_league_seed`, dashboard 单关 / 复式) is off by default, so the
598 V4-V7 tests continued to pass unchanged through 5 weeks of code
changes that touched core ML modules (Elo, form, pipeline, walk-forward).
Zero baseline regression risk.

## What worked

### 1. Three independent tracks, parallel weeks

V7 introduced the "tracks > weeks" pattern; V8 doubled down. The 5
coding weeks split:

- **Track B finish** (W1, W2, W3) — sequential code work, each builds
  on the prior
- **Track D start** (W6, W7) — fully independent of Track B
- **W4, W5** — explicitly *not coded*, data-gated for V9

By interleaving B and D, no week sat idle. W6 (dashboard) and W7 (Elo)
shipped during weeks Track B's data-gated decisions would have idled.
V7's pattern wasn't a one-off; it's the right structure for late-stage
work where some tracks are infrastructure-complete but data-pending.

### 2. Opt-in flags caught my own naïve design

V8 W7's first cut had `feature_columns_with_cup()` auto-include the
lineup-validated cols. Looked clean: "if you're training with cup
features you probably want lineups too." But that would `KeyError`
when `--with-cup-features` was used without the lineup cache populated.

The realization came when writing the test for the flag-combination
matrix:

```
--with-cup-data    --with-cup-features    GBM cols
✗                  ✗                      39 (baseline)
✗                  ✓                      44 (+5 cup cols, all zero on league rows)
✓                  ✗                      39 (cup rows, no cup signal)
✓                  ✓                      44 (cup rows + cup signal)
```

The "cup_features without cup_data" combination only makes sense
because adding 5 zero columns is harmless. But it has to be the user's
choice, not automatic. **Independent flag toggling forced the
correct design**: `feature_columns_with_cup(include_lineups=False)`
explicitly composes.

The same lesson applied to V8 W3's `cross_league_seed` — auto-enabling
it for `--with-cup-data` is correct (cup rows always benefit from
cross-league seeding) but explicit at the API level. Users wiring
custom training paths can opt in/out independently.

### 3. Mirror-symmetric data layer modules

V7 W8 introduced `cup_odds` mirroring V7 W6's `cup_history`. V8 W7
extended the pattern with `national_team_elo` mirroring V5 W3's
per-club `clubelo`. Same API:
`normalize_*`, `<canonical>_parquet_path`, `write_*_parquet`,
`load_*_parquet`, `load_multi_season_*` (or `build_*_lookup`).

This is a maintenance compounding win:
- Writing W7 was fast because the pattern was rote
- Tests structure was rote
- Documentation structure was rote
- Future modules (V9's possible national-team fixture ingest?) will
  reuse it

When the third instance of a pattern lands, the pattern itself is
worth documenting. Worth a future "data-layer module template" doc
if V9 needs a fourth.

### 4. The diagnostic-CLI pattern

V8 W1 shipped `nutmeg-canonical-report-cup` not to do the work, but to
**surface the work the user needs to do**. Same pattern as
V5 W3's `report_unmatched`: scan, report, suggest the file + line the
human should edit.

This pays off when the canonicalization data is hand-curated (as it
should be — V4-era silent-wrong-join lessons). The CLI doesn't
auto-add aliases; it shows you which ones to add. Human stays in
the loop on the high-stakes call.

V8 W3's `nutmeg-cup-ablation` follows the same shape: doesn't
auto-ship the artifact, just produces the markdown card with the
ship-gate verdict + tells you what to do based on which verdict
came out.

### 5. Honest data-gating

V8 W4 and W5 are explicitly not closed. The retrospective doesn't
pretend they "almost shipped." They're cleanly handed off:

- W4 has a 4-step user runbook in V8_HANDOFF § 4
- W5 has the V6 W8 decision matrix referenced explicitly

V5 W5 / W6 / W9, V6 W5, V7 W4-W5 all taught the same lesson: don't
fake a ship from incomplete data. The retrospective writes the
gates as "infrastructure complete, decision-by-user" rather than
"in progress" so V9 W1's reader knows exactly what's owed.

### 6. ECE 0.0120 < Pinnacle's 0.0123 puzzle still in the V9 backlog

V5 W12 first noticed: CatBoost's calibration ECE is slightly BETTER
than Pinnacle's, but log-loss is 0.0056 worse. This is mentioned
in V6_HANDOFF + V7_HANDOFF backlogs and is in V8's too. **Three V*
retrospectives later it's still on the list.**

That's not a failure — it's a recognition that some investigation
questions don't fit weekly ship cadence. They wait for a slack week
or a specific signal (a per-bucket Brier audit, when someone has 1-2
days free). The list-it-and-revisit pattern works as long as it's
not a way of forgetting.

## What didn't work / honest gaps

### 1. The cup-trained model still isn't trained

V7 estimated cup-aware artifact ship in V7 W8. V7 W8 honestly de-scoped
to "groundwork complete." V8 was meant to close. W1/W2/W3 shipped the
code, but the actual ablation + decision waits on the user running
3 commands locally:

```bash
nutmeg-ingest-cup-history  --leagues UCL,UEL --seasons 2021,2022,2023,2024
nutmeg-ingest-cup-odds     --leagues UCL,UEL --seasons 2021,2022,2023,2024
nutmeg-cup-ablation
```

**Counter-argument**: each iteration shipped real, complete code. V9
W1 is `nutmeg-cup-ablation` + read verdict + train or document — a
1-2 day task. The 1.5-version slip is in calendar time, not work.

But the user paid for API-Football specifically expecting cup
predictions to work. Saying "the infrastructure is ready" is true
but not the answer they wanted at end-of-V6. V9 W1 needs to actually
run.

### 2. National-team Elo isn't wired into the model

V8 W7 ships the data layer + ingest + 68-nation registry. The model
doesn't use any of it yet. `build_elo_features` still falls back to
the "unknown team" path for WC / Euro fixtures.

The integration is one targeted change (~20 lines + tests):

```python
if competition_type_of(row.league) == "national_team_cup":
    code, elo = lookup_nation_elo(nation_state, row.home_team)
    if elo is not None:
        # seed instead of using default
```

V9 should do this. The reason W7 didn't: it needs WC / EURO fixture
data in the training set, which requires running ingest-cup-history
for those competitions. Pure code without data exercise wasn't worth
shipping in a tight W7.

### 3. Dashboard 单关 / 复式 doesn't record sessions

The existing 串关 tab can checkbox `record-session` to log to the
observation DB. V8 W6's new 单关 / 复式 tabs don't. Future: extend
`observation/recorder` to understand the new response shapes
(`SingleRecommendResponse`, `PoolRecommendResponse`).

This breaks Track A's data-collection symmetry: users who place 单关
bets via the dashboard can't get those into the A/B report or ROI
card. CLI users (via `nutmeg-rec`) have the same gap.

V9 if any user actually places 单关 via the web.

### 4. CI still doesn't exercise --with-cup-data / --with-lineups end-to-end

Same gap V6 + V7 noted. CI runs tests; tests skip the lineup/cup paths
when cache is absent. The pragmatic fix is small fixture caches baked
into the repo, but it's never been the priority.

V9 should batch this with other "fix the long tail of CI gaps" work.

### 5. ECE vs log-loss mystery still un-investigated

Three retrospectives mentioned this; zero have looked. V9 should
either (a) schedule the per-bucket Brier audit as a Yom Kippur task,
or (b) explicitly note "we accept this as not worth investigating"
and remove from backlog.

## Patterns that held up from V5+V6+V7

1. **Multi-fold validation discipline.** V8 W3's `nutmeg-cup-ablation`
   builds this in by construction — the ship-gate is 3/4 folds,
   matching V6 W6's `recent_n_injuries` methodology. No single-cutoff
   "promising" results allowed.
2. **Opt-in for new features; defaults stable.** Every V8 path is
   off by default. The V5 W12 CatBoost default has now survived V6,
   V7, V8 untouched.
3. **One frozen dataclass / module per concept.** V8 W7's
   `national_team_elo` is its own module; doesn't modify the
   per-club `clubelo`. Same separation as V8 W2's `cup_training`
   vs V7 W6's `cup_history`.
4. **Every week ships a tag + a doc.** V8 has 5 weekly docs +
   V8_HANDOFF + this retrospective. Plus V8_ROADMAP.md updated to
   show W4/W5 as ⏳ data-gated.
5. **"What W$N doesn't do" sections.** Every weekly doc explicitly
   lists the deliberate gaps. V9 inherits clean expectations.
6. **Tracks > weeks.** V8 ran B-finish (W1-W3) + D-start (W6-W7) in
   parallel because B's decisions were data-gated. Don't pretend
   sequential.

## New pattern V8 surfaced

### Mirror-symmetric data-layer modules

V7 W8's `cup_odds` mirrored W6's `cup_history`. V8 W7's
`national_team_elo` mirrored V5 W3's per-club `clubelo`. Three
instances established a pattern that's worth a template:

```
def normalize_<thing>(raw, key, ...) -> dict | None:
    ...
def <canonical>_parquet_path(out_dir, key, ...) -> Path:
    ...
def write_<thing>_parquet(rows, path) -> Path:
    ...
def load_<thing>_parquet(path) -> pd.DataFrame:
    ...  # returns empty schema-only when missing
def load_multi_<key>_<thing>(out_dir, *keys) -> pd.DataFrame:
    ...
def lookup_<thing>(state, name) -> tuple[Optional[code], Optional[value]]:
    ...
```

Plus a `nutmeg-ingest-<thing>` CLI that:
- Skips cached entries unless `--refresh`
- Throttles politely (250ms default)
- Writes empty parquet for "tried but no data" semantics
- Exit 1 on any failure

If V9 ingests a 4th data layer, follow the template.

## V9 starting points

Listed by likely value, highest first:

1. **Run cup ablation + decide.** Execute the W4 4-step workflow.
   Read verdict. Train + ship artifact OR document negative result.
2. **Read lineup verdict** (if 4 weeks of cron data exist). Same
   pattern as #1.
3. **National-team Elo model integration**: extend `build_elo_features`
   to call `lookup_nation_elo` for `competition_type_of() == "national_team_cup"`
   rows. ~20 lines + tests.
4. **Ingest WC / EURO / COPA_AMERICA fixture data** via existing V7 W6
   + W8 CLIs so #3 has data to train on.
5. **Observation recording for 单关 / 复式**: extend
   `observation/recorder` to accept the V8 W6 response shapes.
6. **CI fixture cache** to exercise `--with-cup-data` /
   `--with-lineups` paths.
7. **Per-bucket Brier audit** (ECE-vs-log-loss mystery) — V5 W12's
   original observation, three retrospectives unread.

## Numbers (V7 → V8)

| Metric | V7 ship | V8 ship | Δ |
|---|---:|---:|---:|
| V4 tests | 598 | **713** | +115 |
| CLIs | 19 | **23** | +4 |
| API endpoints | 9 | **11** | +2 |
| Dashboard tabs | 5 | **7** | +2 |
| Modules added | — | 6 (3 data, 3 CLI) | +6 |
| Cup data layers | 4 | 6 | +2 |
| Nations registered | 0 | 68 | +68 |
| Production CatBoost default | unchanged | unchanged | 0 |
| Lineup verdict | pending | pending | 0 (data-gated) |
| Cup-aware artifact | groundwork | code complete; decision pending | infra++ |

## Closing thought

V8's discipline isn't any single feature — it's the **continued
refusal to ship false positives**. V5 / V6 / V7 each shipped negative
ablations (W5 market dynamics, W6 stacker, W9 per-league T, V6 W5
lineup leak, V6 W6 cup-features only partial improvement). V8 didn't
even run the cup ablation yet — but the infrastructure makes the
verdict obvious when it does run. **No verdict will be invented; the
ablation will produce one.**

That's V8's contribution: not the artifact ship, but the gate that
gives V9 a one-bit answer. Either the gate fires green and we ship,
or it fires red and we document. Both are progress. Neither is
optimism.

V9 W1's first command is `nutmeg-cup-ablation`. That's the discipline.
