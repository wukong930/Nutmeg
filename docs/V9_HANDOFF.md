# Nutmeg V9 Handoff

_Last updated: 2026-05-24 (V9 ship / `v9.0-shipped` tag)_

Single source of truth for V9 — the 6-week mini-version that intentionally
broke the V5-V8 12-week cadence (V8 retrospective: "项目接近 maintenance
mode"). Read this first when picking up the project; then [V8_HANDOFF.md](V8_HANDOFF.md)
for the cup model + national-team Elo groundwork, then back through V7 / V6 / V5 / V4.

---

## 1. What V9 was

V9 starts from a different place than V5/V6/V7/V8:

| Signal entering V9 | What it meant |
|---|---|
| V8 W4 cup ablation NOT RUNNABLE (data block) | Track B frozen pending data |
| V8 W5 lineup ROI verdict still pending | Track A gated on ≥ 4 weeks of cron settlements |
| Post-V8 P1#4 + P1#5 already shipped | The two highest-priority code patches done before V9 began |
| V4 default model unchanged for 3 versions | Production stable; no urgent model issues |
| Daily user flow at 2 manual steps (V7 closeout) | Operational UX solved |

V9's actual situation: **a handful of medium-priority code items + a lot
of waiting for data**. Explicitly designed as a flexible 4-6 week
mini-version — "ship when ready, not on Friday".

Six weekly tags shipped (W1, W3, W4, W5, W6 + ship — no W2 because the
planned national-team Elo verification was bumped). One **6th project
negative result** (W6 calibration fix).

## 2. Tracks (continued from V8 + one new)

| Track | Theme | V9 outcome |
|---|---|---|
| **A** | Lineup-aware ROI verdict | ⏳ Still data-gated. V9 W1 extended daily cron to forward-accumulate UCL+UEL odds for ~9 months → V10 |
| **B** | Cup-trained model | ❄️ **FROZEN** (V8 W4 doc'd block); Path A live accumulation started V9 W1 |
| **D** | Product polish | Dashboard recorder checkbox plumbed (W3); cup half of CI fixture cache deferred |
| **E** (new) | Cleanup + paying down debt | CI fixture cache (W4), ECE audit (W5), calibration fix attempt (W6) |

## 3. Production state today

| Layer | Default | Notes |
|---|---|---|
| Model backend | CatBoost (V5 W12 default — **still unchanged through V6-V9**) | Lineup-aware + cup-aware variants both opt-in |
| Daily flow | 2 manual steps + extended daily cron (UCL+UEL) | V9 W1 daily-recommend.yml |
| Dashboard tabs | ① 单关 / ② 串关 / ③ 复式 / ④ 录入结果 / ⑤ ROI / ⑥ 会话 / ⑦ 规则 (V9 W3 added record-session checkboxes to all 3 betting tabs) | |
| Observation recording | Two-gate (NUTMEG_V4_OBSERVATION_DB env + per-request record_session) | V9 W3 tightened from post-V8 P1#5 |
| CI coverage | NEW: e2e lineup path with baked 1.4 MB API-Football cache | V9 W4 closed lineup half of 3-retrospective backlog |
| ECE backlog | **CLOSED** — V9 W5 audit + W6 fix attempt | 6th project negative result |

## 4. What V9 shipped (week by week)

### W1 — Path A (forward live accumulation) + V9_ROADMAP ✅ `v9.w1`

- Extended `.github/workflows/daily-recommend.yml` league list to include
  UCL (`UEFA_CHAMPIONS_LEAGUE`) + UEL (`UEFA_EUROPA_LEAGUE`) so the
  daily cron starts accumulating cup odds for V10's eventual cup-ablation
  retry (V8 W4 documented that `/odds` is upcoming-only — only forward
  accumulation works)
- `docs/V9_ROADMAP.md` — explicit "this version is different" plan;
  introduces Track E and the 4 V9 design principles

### W3 — Dashboard recorder checkbox plumbed ✅ `v9.w3`

_(W2 — planned national-team Elo verification — skipped; would have
been another V8 W4-style data-block writeup, low marginal value)._

- Adds `record_session: bool = False` to 3 request models
  (`RecommendRequest`, `SingleRecommendRequest`, `PoolRecommendRequest`)
- `_should_record_session(req_record_flag)` helper — DB writes only
  when **both** `NUTMEG_V4_OBSERVATION_DB` env AND request flag are on
- `/recommend` (串关) NOW records — was V5 W11 no-op for 4 years
- Dashboard 单关 + 复式 gain checkboxes; 串关 checkbox JS now actually
  reads `.checked` and posts into request body
- Tightens post-V8 P1#5 (which had env-only auto-record — too coarse
  for daily-cron + manual-test workflows sharing one server)
- 20 new tests
- See [v9_w3_recorder_checkbox.md](archive/v9/v9_w3_recorder_checkbox.md)

### W4 — CI fixture cache (lineup-path end-to-end) ✅ `v9.w4`

- 1.4 MB API-Football cache subset committed (5 EPL 24/25 fixtures + 5
  lineup payloads + 10 team-season injuries)
- New `test_e2e_lineup_with_cache.py` — `build_lineup_lookup_from_cache`
  → `build_recent_injury_lookup` → `build_lineup_features` chain runs
  end-to-end on real data in CI
- Closes the **lineup half** of the CI gap V6 W12 / V7 / V8 retrospectives
  all flagged. Cup half stays open until Path A (V9 W1) accumulates
  ~250 cup_odds rows (~9 months)
- 12 new tests
- See [v9_w4_ci_fixture_cache.md](archive/v9/v9_w4_ci_fixture_cache.md)

### W5 — ECE-vs-log-loss per-bucket Brier audit ✅ `v9.w5`

The mystery V5 W12 noted: CatBoost ECE (0.0120) is slightly BETTER than
Pinnacle (0.0123), yet log-loss is 0.0056 WORSE. 3 retrospectives
listed; none acted.

- New `nutmeg.v4.eval.bucket_decomp` module — pure analysis, per-bucket
  Brier + log-loss decomposition binned on `p(true_class)`
- `walk_forward.run_walk_forward()` now returns `pooled_arrays` for
  downstream audits
- `nutmeg-ece-audit` CLI — runs walk-forward + writes markdown card
- Verdict on cutoff=2024-08-01 (n=4,331): **🎯 concentrated bucket**:
  `(0.6, 0.8]` contributes +0.0082 (more than total +0.0056 gap).
  CatBoost places 619 rows there vs Pinnacle's 542
- 21 new tests
- See [v9_w5_ece_audit_writeup.md](archive/v9/v9_w5_ece_audit_writeup.md) +
  [v9_w5_ece_audit.md](archive/v9/v9_w5_ece_audit.md) (data)

### W6 — Calibration fix attempt — ❌ NEGATIVE ✅ `v9.w6`

- `walk_forward` adds `cal_cat_temp` + `cal_cat_iso` fitted on val pool;
  pooled summary + `pooled_arrays` + per-league rows expose
  `cat_dc_temp` and `cat_dc_iso`
- `nutmeg-cat-calibration-ablation` CLI — multi-cutoff verdict runner
- Result across 3 cutoffs (2022/2023/2024-08-01):
  - **isotonic** improved 0/3 cutoffs (mean Δ +0.0789 log-loss — catastrophic)
  - **temperature** improved 2/3 cutoffs (mean Δ -0.0001 — noise)
- Verdict: **structural information gap, not fixable miscalibration**.
  The 619 vs 542 row population delta in (0.6, 0.8] is real signal
  CatBoost picks up that Pinnacle deliberately dampens — calibrating
  would erase real edge
- **No production change.** Raw `cat_dc` stays the V5 W12 default
- ECE-vs-log-loss mystery (3 retrospectives' backlog) **PERMANENTLY
  CLOSED**
- 11 new tests
- See [v9_w6_calibration_negative.md](archive/v9/v9_w6_calibration_negative.md) +
  [v9_w6_calibration_ablation.md](archive/v9/v9_w6_calibration_ablation.md)

## 5. Numbers (V8 → V9)

| Metric | V8 ship | V9 ship | Δ |
|---|---:|---:|---:|
| V4 tests passing | 713 (~739 after post-v8 P1#4+5) | **803** | +90 from V8 ship, +64 from post-v8 baseline |
| CLIs in `pyproject.toml` | 23 | **25** | +2 (ece-audit, cat-calibration-ablation) |
| API endpoints | 11 | 11 | unchanged |
| Dashboard tabs | 7 | 7 | unchanged (W3 added checkboxes, not tabs) |
| Cup_odds parquets non-empty | 0 | 0 (V8 W4 block stands; Path A accumulating) | structural |
| Lineup ROI verdict | pending | pending (data-gated → V10) | unchanged |
| ECE audit | open | **answered** (negative) | resolved |
| CI lineup-path coverage | 0% | end-to-end smoke pass | resolved |
| Production CatBoost default | unchanged through V5-V8 | **still unchanged through V9** | unchanged |
| Documented negative results | 5 | **6** (V9 W6 added) | +1 |

### Backtest (still unchanged from V5 W12 → V9 ship)

V9 didn't retrain. The production CatBoost artifact stays exactly where
V5 W12 left it. The W6 negative result confirmed it shouldn't move.

| Cutoff | Pinnacle | CatBoost (default, unchanged since V5 W12) |
|--------|---------:|--------------------:|
| 22/23 | 0.9940 | 0.9984 |
| 23/24 | 0.9865 | 0.9898 |
| 24/25 | 0.9904 | **0.9960** |

## 6. V9 new CLIs

```
nutmeg-ece-audit                  (W5) Per-bucket Brier + log-loss decomposition
nutmeg-cat-calibration-ablation   (W6) Multi-cutoff CatBoost calibration ablation
```

## 7. V9 new modules

```
nutmeg.v4.eval.bucket_decomp                       (W5) Per-bucket Brier + log-loss decomp
nutmeg.v4.cli.ece_audit                            (W5)
nutmeg.v4.cli.cat_calibration_ablation             (W6)
```

Modified for V9:
```
.github/workflows/daily-recommend.yml              (W1) +UCL +UEL leagues
apps/api/src/nutmeg/v4/api/schemas.py              (W3) +record_session on 3 models
apps/api/src/nutmeg/v4/api/routes.py               (W3) +_should_record_session helper
apps/api/src/nutmeg/v4/api/static/dashboard.html   (W3) +2 checkboxes, JS rewiring
apps/api/src/nutmeg/v4/eval/walk_forward.py        (W5) +pooled_arrays
                                                   (W6) +cal_cat_temp/iso, +cat_dc_temp/iso
```

## 8. V10 backlog

### Data-gated decisions (still ⏳)

1. **Lineup ROI verdict** — same as V8 W5: needs ≥ 4 weeks of cron
   settlements. V9 W1's extension of the daily cron to UCL+UEL also
   contributes to this accumulation
2. **Cup-aware artifact decision** — needs ~250+ cup_odds rows
   accumulated forward via Path A (V9 W1). Realistic timeline ~9
   months from V9 ship. **Don't start V10 just to wait on this** — it's
   genuinely a long pole

### V9 left-overs

3. **National-team Elo model integration** — V8 W7 shipped the data
   layer + post-V8 P1#4 wired `seed_elo_value` to accept `nation_state`,
   but `build_elo_features` still needs the routing logic for
   `competition_type_of(row.league) == "national_team_cup"` rows.
   Originally V9 W2; skipped because the verification path needed
   WC/EURO fixture data we don't have. Low priority

### Product polish (Track D continuation)

4. **Dashboard checkbox state persistence across page reloads**
   (V9 W3 chose not to add localStorage). Trivial; deferred
5. **Confirmation indicator** for "did the server actually persist?"
   on record-session — would need synchronous read-back; deferred

### Tech debt (Track E continuation)

6. **Multi-snapshot odds capture** for V5 W5's drift features (V7
   backlog, still dormant)
7. **Bayesian hierarchical** for small-sample leagues (V7 backlog,
   still untested)
8. **API token rotation** — V6 W8 advisory still standing as a
   recurring operational concern

## 9. Tests

**803/803 V4 tests passing** on `v9.0-shipped`:

```bash
PYTHONPATH=apps/api/src python -m pytest tests/v4/ -q
```

V9 added 4 new test files (~64 tests; post-v8 P1#4+5 contributed ~26
before V9 W1 started):

| Module | Tests | Coverage |
|---|---:|---|
| `test_record_session_gate.py` | 20 | 3 schemas default, 4-combo gate helper, 3 endpoints × 3-4 combos, dashboard wiring |
| `test_e2e_lineup_with_cache.py` | 12 | end-to-end lineup pipeline on baked API-Football cache; smoke + feature shape |
| `test_bucket_decomp.py` | 21 | per-bucket decomposition, weighted-ll sum consistency, audit card formats |
| `test_walk_forward_cat_calibration.py` | 11 | cal_cat_temp/iso wiring, pooled_arrays/summary shape, ablation card verdict heuristic |

## 10. Tags + milestones

| Tag | Date | Meaning |
|-----|------|---------|
| `v8.0-shipped` | 2026-05-24 | V8 closeout (entry point for V9) |
| `v8.w4` | 2026-05-24 | (documented as part of post-V8 + V8 W4 negative writeup) |
| `v9.w1` | 2026-05-24 | Path A daily cron + V9_ROADMAP |
| `v9.w3` | 2026-05-24 | Dashboard recorder checkbox plumbed |
| `v9.w4` | 2026-05-24 | CI fixture cache |
| `v9.w5` | 2026-05-24 | ECE audit (concentrated bucket found) |
| `v9.w6` | 2026-05-24 | Calibration fix attempt (negative) |
| `v9.0-shipped` | 2026-05-24 | V9 complete |

The git log from `v8.0-shipped` to `v9.0-shipped` is the complete record
of how V9 unfolded.

---

**Welcome to V10** (whenever it arrives — see [v9_retrospective.md](v9_retrospective.md) for the trigger conditions).
