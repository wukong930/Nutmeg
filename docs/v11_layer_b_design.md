# Layer B — Quarterly Auto-Retrain (V11 Design Doc)

_Drafted 2026-05-25, V11 Phase 0. Adopted as V11 candidate per
2026-05-25 ML architecture discussion. Appears in 3/3 V11 branches.
This doc is the architecture spec; implementation happens at V11
Branch A W4, Branch B W1, or Branch C W3 depending on which branch
phase 1 picks._

---

## 1. What Layer B is

**Layer A** (V10 W2): adjusts a single post-hoc temperature scalar `T`
on the production model's 1X2 probabilities. Reactive drift correction.

**Layer B** (this doc): retrains the full CatBoost model on fresh data
every quarter, validates via walk-forward, ships through the same
artifact-side mechanism Layer A uses. Proactive model refresh.

The two layers compose:
```
Raw match features
       ↓
[ Layer B's current artifact ]    ← swapped quarterly when gate passes
       ↓
   (λ_h, λ_a)
       ↓
[ Layer A's T correction ]        ← swapped weekly when gate passes
       ↓
  Final 1X2 probabilities
       ↓
       Dashboard / CLI / recommendation pipeline
```

When Layer B deploys a new artifact, Layer A's `T` resets to 1.0
(identity) — new model needs fresh calibration.

---

## 2. Why Layer B

### What problem it solves

The production CatBoost model has been **unchanged since V5 W12**.
6 versions (V6 / V7 / V8 / V9 / V10 + post-v9 P1 chain) shipped on
top without ever retraining the base model. Each new season's data
got ingested but never fed back into training.

### Risk it accepts

Walk-forward on 2024/25 still showed log-loss 0.9960 vs Pinnacle
0.9904 (93% ceiling) — the model is **not obviously degrading**, but:
- It hasn't seen 2025/26 data at all
- It hasn't seen any 2026 transfer-window team changes
- Distribution shifts (rule changes, VAR adjustments, etc.) accumulate

Layer A's post-hoc T can correct **mean-level** drift. It cannot
correct **feature-relationship drift** (e.g., "lineup_recent_form" weight
should be higher for promoted teams now). Only retraining can.

### Why "quarterly" specifically

| Frequency | Pros | Cons |
|---|---|---|
| Weekly | Fastest drift correction | Massive overfit risk on 1-week data slice |
| Monthly | Reasonable cadence | Each retrain is ~1 hour; too disruptive for production |
| **Quarterly** | Aligns with European season boundaries; minimal overfit; manageable disruption | Slowest of the credible options |
| Yearly | Minimal risk | Too slow to track within-season drift (managerial changes, etc.) |

Quarterly = every 13 weeks. Matches football season rhythm (pre-season
break → first quarter; winter break → second; etc.) and gives enough
data accumulation (~80-150 new matches per major league per quarter)
to detect meaningful shifts.

---

## 3. Architecture (mirror of Layer A)

### Module layout

```
apps/api/src/nutmeg/v4/
  observation/
    auto_retrain.py        ← NEW. Core retrain logic + journal + artifact I/O.
                             Mirror of observation/auto_calibration.py.
  cli/
    auto_retrain.py        ← NEW. nutmeg-auto-retrain CLI.
                             Mirror of cli/auto_calibration.py.
  api/
    routes.py              ← EDIT. _artifact_path() checks for
                             live_artifact_pointer.json (similar to
                             how _load_correction() reads live_T_correction.json).

data/
  v4_model/                ← Unchanged. The "default" / "current production" artifact.
  v4_model/live_artifact_pointer.json  ← NEW. When present, redirects serving
                                          to point at data/v4_model_layer_b/<version>/.
  v4_model_layer_b/
    v_2026-Q3/             ← Quarterly artifact directory; same shape as v4_model/.
      model.cat
      metadata.json
      ...
    v_2026-Q4/
    v_2027-Q1/

scripts/
  setup_local_pipeline.sh  ← EDIT. Add 8th launchd job: quarterly_retrain.
  ...

docs/quarterly/
  retrain_<YYYY-QN>.md    ← Markdown report from each quarterly run.
```

### Database schema (mirrors `calibration_journal`)

```sql
CREATE TABLE IF NOT EXISTS retrain_journal (
    journal_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at      TEXT NOT NULL,
    action           TEXT NOT NULL,         -- 'propose' | 'deploy' | 'rollback'
    artifact_version TEXT NOT NULL,         -- 'v_2026-Q3'
    artifact_path    TEXT NOT NULL,         -- absolute path
    log_loss_before  REAL,                  -- production on holdout
    log_loss_after   REAL,                  -- new model on holdout
    log_loss_delta   REAL,
    p_value          REAL,
    n_train          INTEGER,
    n_holdout        INTEGER,
    train_window     TEXT,                  -- "2023-08-01 → 2026-03-31"
    holdout_window   TEXT,                  -- "2026-04-01 → 2026-05-25"
    decision         INTEGER NOT NULL,      -- 1 = shipped, 0 = held
    reason           TEXT,
    prior_version    TEXT,                  -- the version this replaces / rolls back to
    extras_json      TEXT
)
```

### CLI surface (mirrors `nutmeg-auto-calibration`)

```bash
# Dry-run propose: train a candidate, evaluate, write journal entry
# but don't swap the live artifact
nutmeg-auto-retrain --db data/v4_observation.db --apply

# Deploy: train + ship (writes new dir + flips pointer)
nutmeg-auto-retrain --db data/v4_observation.db \
    --apply --action deploy \
    --artifact-base data/v4_model_layer_b

# Rollback: flip pointer back to prior version + delete L A's T correction
nutmeg-auto-retrain --db data/v4_observation.db \
    --apply --action rollback \
    --artifact-base data/v4_model_layer_b

# Weekly safety check: if last-deployed artifact's 4-week ROI is hurting,
# auto-rollback
nutmeg-auto-retrain --db data/v4_observation.db \
    --apply --auto-rollback \
    --artifact-base data/v4_model_layer_b
```

Exit codes mirror Layer A: 0 (normal) / 1 (setup error) / 2 (ship gate passed
but not yet deployed; caller can run --action=deploy next).

---

## 4. Walk-forward validation design

### Train / holdout split

Given the observation DB as of "today":

```
[ 3+ years of historical data ]   [ last 8 weeks ]
        ←─── train ───→            ←─ holdout ──→
```

- Train slice: from start of database up to (now - 8 weeks)
- Holdout slice: last 8 weeks of settled matches

8 weeks chosen because:
- ~120-200 matches per major league per 8 weeks = enough for bootstrap
- Short enough to detect recent drift
- Matches Layer A's `holdout_weeks=2` × 4 = same statistical horizon

### Comparison protocol

For each match in holdout:
1. Run the **current production artifact** (Layer A T-corrected) → `p_old`
2. Run the **newly-trained candidate artifact** (no T correction; raw) → `p_new`
3. Compute log-loss of each on the actual outcome
4. Bootstrap p-value: how often does p_new beat p_old on resamples?

Note: this **deliberately compares Layer B candidate WITHOUT Layer A T
correction** to the current production WITH Layer A T correction. The
candidate has to win on its own merits, not just because Layer A added
correction to its predecessor. After deploy, Layer A starts fresh
(`live_T_correction.json` deleted).

### Ship gate (tighter than Layer A)

| Check | Threshold | Why |
|---|---:|:---|
| Holdout log-loss Δ ≥ 0.002 | tighter than Layer A's 0.001 | New model is more disruptive than a T scalar — require clearer evidence |
| Bootstrap p ≤ 0.05 | tighter than Layer A's 0.10 | Same reason. 5% false-deploy budget. |
| n_train ≥ 5000 settled matches | hard floor | Below this, model has too few examples to estimate reliably |
| feature_schema_version match | hard match | If new features added since last retrain, must be opt-in via `--allow-schema-change` flag |

The schema-version gate prevents an automatic retrain from silently
including a new feature whose impact hasn't been validated.

---

## 5. Artifact-side handoff (the `live_artifact_pointer.json` pattern)

This is the **biggest architectural difference from Layer A**. Layer A
modifies a scalar at request time; Layer B has to swap out a multi-MB
model file. Doing this **atomically** + **without server restart** +
**with rollback capability** is the core engineering challenge.

### File layout

```
data/v4_model/                       ← The "default" artifact location
  metadata.json                      ← V5 W7 — model_type, gbm_rho, etc.
  model.cat / model.lgb              ← The actual model file
  live_T_correction.json             ← Layer A (optional, present when correction deployed)
  live_artifact_pointer.json         ← Layer B (optional, present when newer artifact deployed)

data/v4_model_layer_b/
  v_2026-Q3/
    metadata.json                    ← Same schema as data/v4_model/metadata.json
    model.cat
    layer_b_provenance.json          ← Layer B audit info (train window, ship gate verdict, etc.)
  v_2026-Q4/
    ...
```

### `live_artifact_pointer.json` schema

```json
{
  "version": "v_2026-Q3",
  "artifact_path": "data/v4_model_layer_b/v_2026-Q3",
  "deployed_at_utc": "2026-07-01T06:00:00+00:00",
  "previous_version": "production_v5_w12",
  "shipped_via": "nutmeg-auto-retrain --action=deploy",
  "ship_gate_log_loss_delta": 0.0024,
  "ship_gate_p_value": 0.018,
  "n_train": 12450,
  "n_holdout": 187,
  "train_window": ["2023-08-01", "2026-04-30"],
  "holdout_window": ["2026-05-01", "2026-06-30"]
}
```

### Serving layer change (`routes.py`)

`_artifact_path()` currently returns `os.environ.get("NUTMEG_V4_ARTIFACT_PATH", "data/v4_model")`.

After Layer B ships:

```python
def _artifact_path() -> str:
    """Resolve the effective artifact directory.

    Honors Layer B's live_artifact_pointer.json if present.
    Falls through to the env var / default if not.

    Mtime-cached like _load_correction() — fresh deploy takes effect
    on the next request without server restart.
    """
    base = os.environ.get("NUTMEG_V4_ARTIFACT_PATH", "data/v4_model")
    pointer_path = Path(base) / "live_artifact_pointer.json"
    try:
        mtime = pointer_path.stat().st_mtime
    except FileNotFoundError:
        _pointer_cache.pop(base, None)
        return base
    cached = _pointer_cache.get(base)
    if cached and cached[0] == mtime:
        return cached[1] or base
    try:
        pointer = json.loads(pointer_path.read_text())
        target = pointer.get("artifact_path")
        if target and Path(target).is_dir():
            _pointer_cache[base] = (mtime, target)
            return target
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("could not parse %s: %s — using base", pointer_path, exc)
    _pointer_cache[base] = (mtime, None)
    return base
```

### Why a pointer file instead of overwriting `data/v4_model/`?

Three reasons:

1. **Atomicity** — writing a small JSON pointer is atomic; replacing a multi-MB `model.cat` is not. A request mid-write could load a corrupted artifact.

2. **Rollback** — if Layer B's new artifact starts hurting ROI 2 weeks after deploy, rollback = delete the pointer file. The prior artifact is still on disk at `data/v4_model/`, untouched.

3. **Provenance** — V5 W12 production artifact stays at `data/v4_model/` forever. Each Layer B artifact lives under its own quarter-named dir. Easy to inspect history (`ls data/v4_model_layer_b/`).

---

## 6. Auto-rollback design (Layer B's safety net)

### Trigger condition

Layer A rollback: post-deploy log-loss > identity by 0.003 on ≥1 settled pair.

Layer B rollback: **post-deploy ROI drops > 5pp vs prior artifact on
4-week settled window**. Layer B operates at the model level, not the
calibration level — log-loss alone isn't the right signal (could be
better log-loss but worse ROI if calibration shifts incentives).

### Concrete check

Run `nutmeg-ab-report --weeks 4 --db data/v4_observation.db` for:
- The 4 weeks before Layer B deploy (using the prior artifact's
  recommendations recorded in `recommendation_sessions`)
- The 4 weeks after Layer B deploy

If post-deploy ROI is > 5pp worse, trigger rollback.

5pp threshold is a placeholder — calibrate at first run with real
distributions.

### Rollback execution

```
1. Delete data/v4_model/live_artifact_pointer.json
2. Delete data/v4_model/live_T_correction.json (Layer A reset)
3. Write retrain_journal row with action='rollback'
4. Write docs/quarterly/retrain_<YYYY-QN>_rollback.md
```

Serving immediately reverts to `data/v4_model/` on next request via
mtime-cached `_artifact_path()`.

### Interaction with Layer A

When Layer B rolls back, **Layer A also resets** to identity. Two reasons:
- Old T was calibrated against the now-rolled-back model
- New default model needs Layer A to re-calibrate from scratch

In CLI terms: Layer B's rollback action atomically deletes BOTH
`live_artifact_pointer.json` AND `live_T_correction.json`.

---

## 7. Interaction with Layer A — full state machine

```
State                          live_T_correction.json   live_artifact_pointer.json
─────────────────────────────  ──────────────────────   ──────────────────────────
Pristine production            absent                   absent
Layer A deployed, B never ran  present, T≠1.0           absent
Layer B deployed, A reset      absent (B reset it)      present, version=v_2026-Q3
Both layers active             present, T fits new B    present
Layer A rolled back            absent                   present
Layer B rolled back            absent (auto-cleared)    absent
```

Transitions:

```
nutmeg-auto-calibration --action=deploy --deploy-artifact data/v4_model
    → writes live_T_correction.json

nutmeg-auto-retrain --action=deploy --artifact-base data/v4_model_layer_b
    → writes live_artifact_pointer.json
    → DELETES live_T_correction.json (if present)
    → Layer A's next Monday cron will re-propose from scratch

nutmeg-auto-retrain --action=rollback
    → deletes live_artifact_pointer.json
    → ALSO deletes live_T_correction.json (Layer A reset)
```

---

## 8. Cron scheduling

### Quarterly retrain trigger

Add 8th launchd job to `setup_local_pipeline.sh`:

```bash
# Job 8: Quarterly auto-retrain (1st of Jan/Apr/Jul/Oct at 06:00)
# Runs the propose flow; user reviews + decides to deploy.
install_job "com.nutmeg.quarterly_retrain" \
  6 0 "1" "*" "1,4,7,10" \   # NOTE: launchd doesn't support "every 3 months"
                              # natively; need workaround — see below
  "$ENV_PREFIX && mkdir -p docs/quarterly && \
   $VENV_PY -m nutmeg.v4.cli.auto_retrain \
     --db $DB_PATH --apply \
     --artifact-base data/v4_model_layer_b \
     --out docs/quarterly/retrain_\$(date +%Y-Q\$((($(date +%-m)-1)/3+1))).md \
     || true"
```

**launchd workaround**: macOS launchd's `StartCalendarInterval` doesn't
support "every 3 months". Options:

1. **Run weekly, check date in script** — cron fires every Monday but
   the script's first line checks `date +%-d -le 7` AND `date +%-m`
   is in `(1,4,7,10)`. Cron only does work in the right week.

2. **Use four separate jobs** — `quarterly_retrain_q1`, `q2`, `q3`,
   `q4` each on their respective month-1 dates.

Recommendation: **Option 1** (single weekly cron, script self-gates).
Simpler to install / uninstall; one log file; easier to manually
trigger via `launchctl kickstart`.

### Weekly auto-rollback check (separate job)

Layer A's `weekly_calibration_check` already runs Mon 03:00. Layer B's
auto-rollback should run **after** Layer A's check so journal entries
land in temporal order:

```bash
# Job 9: Layer B auto-rollback check (Mon 03:30, 30 min after Layer A)
install_job "com.nutmeg.weekly_retrain_rollback_check" \
  3 30 1 "" "" \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.auto_retrain \
     --db $DB_PATH --apply --auto-rollback \
     --artifact-base data/v4_model_layer_b || true"
```

Daily timeline after Layer B ships:
```
02:00  daily_wc_settle
03:00  weekly_calibration_check (Mon only)
03:30  weekly_retrain_rollback_check (Mon only)
04:00  weekly_gate (Sun only)
06:00  quarterly_retrain (Mondays in months 1/4/7/10 only)
09:00  daily_wc_predict
14:00  daily_odds
15:00  daily_recommend
```

---

## 9. Storage + cleanup policy

Each Layer B artifact: ~5-30 MB (CatBoost model + metadata + ROC
fixtures).

Quarterly = ~100MB/year accumulation.

**Cleanup policy** (V11 backlog, not blocking):
- Keep the last 4 artifacts (1 year of quarterlies) for rollback availability
- Older than that → move to `data/v4_model_layer_b/_archive/`
- Older than 2 years → delete

Not implemented at Branch B W1; tracked as V12 follow-up.

---

## 10. Open design questions (resolved before implementation)

These should be answered at V11 Branch B W1 kickoff, not in this draft:

| Q | Tentative answer | Where to decide |
|---|---|---|
| Does Layer B retrain include the `--with-lineups` / `--with-cup-features` flags? | Yes — match current production's training command exactly | V11 Branch B W1 Day 1 |
| What if Layer B's first run finds the production model is BETTER than a fresh retrain? | Expected on first run (production has been overfit to its full training set). Document as "held"; don't ship | V11 Branch B W1 Day 2 |
| How long does one retrain actually take? | TBD — measure at first dry-run. If > 30 min, launchd timeout matters | V11 Branch B W1 Day 1 |
| Should Layer B include calibration (per-league T, isotonic) as part of training? | No — those are V9 W6 ablation territory, kept separate | V11 Branch B W1 Day 2 |
| What's the seed strategy for reproducibility? | Use V5 W7's `seed=42` constant | V11 Branch B W1 Day 1 |
| Multi-model variants (CatBoost vs LightGBM)? | Layer B retrains the **current default only** (CatBoost since V5 W12). Multi-arm is V12+ | V11 Branch B W1 Day 1 |

---

## 11. Test plan

Mirror Layer A's test layout:

| File | Coverage |
|---|---|
| `tests/v4/test_auto_retrain.py` | Pure-function: train slice / holdout slice / walk-forward / bootstrap p-value (mirror `test_auto_calibration.py`) |
| `tests/v4/test_auto_retrain_cli.py` | CLI: dry-run / --apply / --action variants (mirror `test_auto_calibration_cli.py`) |
| `tests/v4/test_auto_retrain_serving.py` | Serving: `live_artifact_pointer.json` mtime cache (mirror `test_auto_calibration_serving.py`) |
| `tests/v4/test_auto_retrain_rollback.py` | Auto-rollback logic (mirror `test_auto_calibration_rollback.py`) |
| `tests/v4/test_auto_retrain_e2e.py` | Full lifecycle: propose → deploy → ROI check → rollback. Use synthetic small artifacts to keep test fast |

Estimated test count: **~70-80 new tests** (Layer A added 75; Layer B
has more state machine complexity → expect more).

---

## 12. Migration / rollout plan (when V11 Branch B/C executes)

### Branch B W1 (or Branch C W3) day-by-day

| Day | Deliverable |
|---|---|
| 1 | Module skeleton + retrain_journal schema + write/load/read functions + tests for those |
| 2 | Walk-forward training pipeline + ship gate logic + tests |
| 3 | CLI + markdown report renderer + tests |
| 4 | Auto-rollback evaluator + serving integration (`_artifact_path()` update) + tests |
| 5 | E2E integration tests + launchd jobs + first dry-run + tag |

This mirrors V10 W2's Layer A 5-day structure. Same testing rigor.

### First quarterly run protocol (cautious)

When Layer B is operational and the calendar hits the next quarter
boundary:

1. **First firing** = `--action=propose` only (default). No deploy.
2. **User reads** `docs/quarterly/retrain_<YYYY-QN>.md`. Inspects:
   - Train window (should be wide enough)
   - Holdout size (should be ≥100 matches)
   - Log-loss delta (should be ≥ +0.002 to consider deploy)
   - Bootstrap p-value (should be ≤ 0.05)
3. **If looks good**: user manually runs `--action=deploy`.
4. **Next 4 weeks**: auto-rollback check fires each Monday. If ROI
   drops > 5pp vs prior artifact, automatic revert.
5. **After 4 clean weeks**: deploy is confirmed; next quarterly fires
   normally.

This protocol means **Layer B's first deploy decision is gated on
human review**. Auto-deploy might come at V12 once we've seen 2-3
quarterly cycles work cleanly.

---

## 13. Risk register

| Risk | Severity | Mitigation |
|---|:-:|---|
| First retrain ships a worse model | M | Ship gate (Δ≥0.002 + p≤0.05) blocks; manual review further protects |
| Auto-rollback fires too eagerly during legitimate distribution shift | M | 5pp threshold is conservative; can tighten/loosen at first run |
| Storage growth (artifact dir explodes) | L | Cleanup policy (§9); audit at V12 |
| Layer A's deployed T was good and rollback wastes it | L | Document this; manual rollback retains T if needed |
| Walk-forward overfits to 8-week holdout window | M | Could rotate holdout (use multiple non-overlapping 8-week windows); V12 enhancement |
| Retrain takes > launchd timeout (typically 10 min default) | L | Set `Timeout` in plist to 3600s = 1 hour |
| New feature added between retrains breaks the model | M | feature_schema_version gate (§4); fail-safe to abort retrain |

---

## 14. What this doc deliberately doesn't cover

- Specific hyperparameter tuning logic (use existing V5 W7 settings)
- Multi-model variant selection (LGBM vs CatBoost vs ensembles — V12+)
- Distributional shift detection beyond log-loss (KL divergence on
  feature distributions — V12+ research)
- Federated / online learning approaches (V13+, hypothetical)

Layer B is deliberately the **simplest credible auto-retrain mechanism**.
Keep it boring; iterate later.

---

## 15. Sign-off

This design is approved at draft level by:
- 2026-05-25 conversation: user accepted Layer B over MCMC as the
  V11 model architecture investment

Next step: implementation at V11 Branch B W1 (if WC verdict lands
45-55%) or Branch C W3 (if WC <45%) or Branch A W4 groundwork only
(if WC ≥55%, where MCMC + national-team expansion takes priority).
