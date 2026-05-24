# Nutmeg V10 Handoff — **TEMPLATE (pre-filled skeleton)**

_This is post-v9 P1#27. **V10 has not started.** This file exists
so that whenever a V10 trigger fires (see
[V10_ROADMAP_DRAFT.md](V10_ROADMAP_DRAFT.md)) the handoff structure
doesn't have to be re-derived from scratch._

## How to use this template

1. **Wait for a trigger.** Don't fill this in just because V9 ship +
   N weeks have passed. Triggers are listed in
   [V10_ROADMAP_DRAFT.md](V10_ROADMAP_DRAFT.md) §"Triggers — what
   would actually start V10".
2. **When a trigger fires**:
   - Rename this file to `V10_HANDOFF.md` (drop `_TEMPLATE`).
   - Rename `V10_ROADMAP_DRAFT.md` to `V10_ROADMAP.md`.
   - Replace every `🔲 TODO` marker with real content as V10 unfolds.
   - Replace every `⬜ PLACEHOLDER` marker with the trigger-specific
     reality (e.g., if Trigger 4 fired, V10's tracks will be the
     verdict-confirmation and follow-on work).
3. **Don't expand the structure unless needed.** V5-V9 handoffs all
   used the same 10-section layout. The pattern is mature. Adding
   sections is a smell — it usually means scope creep.
4. **Numbers section is the truth check.** When you fill in §5,
   if the V9→V10 delta is small (≤ 30 new tests, 0 new CLIs, 0
   production model changes), that's a sign V10 was actually a P1
   chain misnamed as a version. That's fine — but rename `V10` →
   `post-v9 P1#N` rather than letting a thin V10 ship.

---

## 1. What V10 was

⬜ PLACEHOLDER: which trigger fired?

| Trigger fired | Filled at V10 start |
|---|---|
| Trigger 1 (cup ablation re-test on new data) | 🔲 TODO |
| Trigger 2 (lineup ROI verdict confirmed/refuted by live data) | 🔲 TODO |
| Trigger 3 (new product gap surfaced) | 🔲 TODO |
| Trigger 4 (cross-source robustness check) | 🔲 TODO |
| Trigger 5 (platform-level change) | 🔲 TODO |

⬜ PLACEHOLDER: 2-3 sentences on what V10 is solving. Anchor to the
trigger above. If multiple triggers fired simultaneously, list both
but pick a primary.

Concrete shape estimate per V10_ROADMAP_DRAFT §"What V10 looks like
by trigger":
- 🔲 TODO: weeks (2-4 typical; only Trigger 3 might justify 12)
- 🔲 TODO: one-sentence deliverable
- 🔲 TODO: ship-gate criterion (what makes V10 "done")

## 2. Tracks (continued from V9 + N new)

| Track | Theme | V10 outcome |
|---|---|---|
| **A** | Lineup-aware ROI verdict | 🔲 TODO: still ⏳ / closed positive / closed negative |
| **B** | Cup-trained model | 🔲 TODO: ❄️ still frozen / Path A data sufficient / re-tested |
| **D** | Product polish | 🔲 TODO |
| **E** | Cleanup + tech debt | 🔲 TODO |
| **F** (new in V10) | 🔲 TODO theme | 🔲 TODO |

If no Track F was added, delete that row — V10 may extend V9 tracks
without introducing new ones.

## 3. Production state today

| Layer | Default | Notes |
|---|---|---|
| Model backend | 🔲 TODO (likely still V5 W12 CatBoost unless trigger reversed P1#18) | |
| Default artifact path | 🔲 TODO (`data/v4_model_cat_lineups` post-P1#18; revisit if Trigger 4 → negative) | |
| Daily flow | 🔲 TODO manual steps + 🔲 TODO launchd jobs (4 as of P1#24; possibly more if Trigger 3) | |
| Dashboard tabs | 🔲 TODO (7 as of P1#15; add if Trigger 3 brought new game type) | |
| Observation recording | Two-gate (NUTMEG_V4_OBSERVATION_DB env + per-request record_session) | unchanged unless Trigger 5 |
| CI coverage | 🔲 TODO (nutmeg-ci + weekly-bench + playwright + monthly-token-check + daily-recommend; possibly + new from V10) | |
| ECE backlog | CLOSED (V9 W6) | unchanged unless a fundamentally new audit was attempted |
| Cup-aware artifact | 🔲 TODO (NEGATIVE-CLOSED P1#20; only re-opens if Trigger 1 brought new method) | |

## 4. What V10 shipped (week by week)

### W1 — 🔲 TODO ✅ `v10.w1`

🔲 TODO: 3-5 bullet points on what landed in W1. Match the V9
handoff's per-week structure:
- Code change in module X
- Test count Δ
- Decision made (with link to a docs/v10_w1_*.md write-up)

If W1 was small and W2 is big, that's fine — V9's W1 was half a
day too.

### W2 — 🔲 TODO ✅ `v10.w2`

🔲 TODO

### W3 (or final week) — 🔲 TODO ✅ `v10.w3`

🔲 TODO

If V10 is truly only 2-4 weeks, stop here. Don't pad with W4-W12
just because V5-V8 had 12 weeks each.

### Negative-result writeups in V10

🔲 TODO: list any V10-era negative results (running count from V9 = 6).
Project tradition: every negative result gets a structured writeup
under `docs/v10_w<N>_*_negative.md`. See V5/V6/V8/V9 W6 for templates.

## 5. Numbers (V9 → V10)

| Metric | V9 ship | V10 ship | Δ |
|---|---:|---:|---:|
| V4 tests passing | 803 (+ post-v9 P1 patches → 🔲 TODO at V10 start) | 🔲 TODO | 🔲 TODO |
| CLIs in `pyproject.toml` | 25 (+ post-v9 → 🔲 TODO) | 🔲 TODO | 🔲 TODO |
| API endpoints | 11 | 🔲 TODO | 🔲 TODO |
| Dashboard tabs | 7 | 🔲 TODO | 🔲 TODO |
| Launchd jobs | 4 (after P1#24) | 🔲 TODO | 🔲 TODO |
| GH Actions workflows | 5 (after P1#26) | 🔲 TODO | 🔲 TODO |
| Lineup ROI verdict | shipped w/ caveat (P1#18 + P1#21) | 🔲 TODO (closed firm? still caveated?) | — |
| Cup-aware artifact | NEGATIVE-CLOSED (P1#20) | 🔲 TODO (still closed? re-opened?) | — |
| Production model retraining | 0 (since V5 W12) | 🔲 TODO | 🔲 TODO |
| Documented negative results | 6 (V9 ship) | 🔲 TODO | 🔲 TODO |

### Backtest deltas

🔲 TODO if V10 retrained. If not, copy this disclaimer:

> V10 didn't retrain. The production CatBoost artifact stays exactly
> where V5 W12 left it. Pinnacle and CatBoost benchmark numbers
> reproduce V9 ship's table unchanged.

| Cutoff | Pinnacle | CatBoost (default, unchanged since V5 W12) |
|--------|---------:|--------------------:|
| 22/23 | 0.9940 | 0.9984 |
| 23/24 | 0.9865 | 0.9898 |
| 24/25 | 0.9904 | 0.9960 |

## 6. V10 new CLIs

🔲 TODO. Format:
```
nutmeg-<name>                     (W<n>) one-line description
```

If V10 added zero CLIs, write "none" — that's a valid outcome for a
maintenance-style or single-deliverable version.

## 7. V10 new modules

🔲 TODO. Format:
```
nutmeg.v4.<path>                       (W<n>) one-line description
```

Modified for V10:
```
🔲 TODO list of touched files
```

## 8. V11 backlog

### Data-gated decisions (still ⏳)

🔲 TODO: list anything V10 left open that needs more data. Carry
forward from V10_ROADMAP_DRAFT's trigger list — mark which fired
in V10 and which still gate V11.

### V10 left-overs

🔲 TODO: any V10 work item that was planned but skipped. Mark
priority (high/med/low) for V11 pickup.

### Product polish (Track D continuation)

🔲 TODO

### Tech debt (Track E continuation)

🔲 TODO. Carry forward from V9 backlog items 6-8 (multi-snapshot
odds, Bayesian hierarchical, API token rotation) — note which V10
addressed, if any.

### V11 trigger conditions

🔲 TODO: mirror V10_ROADMAP_DRAFT's §"Triggers" section but updated
for the post-V10 reality. Most likely outcome: same triggers minus
the one V10 closed, plus any new ones V10 surfaced.

## 9. Tests

**🔲 TODO/🔲 TODO V4 tests passing** on `v10.0-shipped`:

```bash
PYTHONPATH=apps/api/src python -m pytest tests/v4/ -q
```

V10 added 🔲 TODO new test files (~🔲 TODO tests):

| Module | Tests | Coverage |
|---|---:|---|
| 🔲 TODO | 🔲 TODO | 🔲 TODO |

If V10 added zero tests (pure docs/ops version), write that
explicitly. Don't fabricate test counts.

## 10. Tags + milestones

| Tag | Date | Meaning |
|-----|------|---------|
| `v9.0-shipped` | 2026-05-?? | V9 closeout (entry point for V10) |
| 🔲 TODO post-v9 P1 patches between v9.0-shipped and V10 W1 | — | (running tally — see [post_v9_p1_index.md](post_v9_p1_index.md)) |
| `v10.w1` | 🔲 TODO | 🔲 TODO |
| `v10.w2` | 🔲 TODO | 🔲 TODO |
| `v10.0-shipped` | 🔲 TODO | V10 complete |

The git log from `v9.0-shipped` to `v10.0-shipped` is the complete
record of how V10 unfolded — including the post-v9 P1 chain that
ran during the V10-wait.

---

**Welcome to V11** (whenever it arrives — see
[v10_retrospective.md](v10_retrospective.md) for the trigger
conditions, and rename this entire file's V10→V11 references
when promoting the V11 template).

---

## Companion files V10 should produce

When V10 actually ships, these files should exist alongside this one
(by analogy to V9):

- `docs/V10_ROADMAP.md` — the actual roadmap (renamed from `_DRAFT`)
- `docs/v10_retrospective.md` — written at ship
- `docs/v10_w<N>_<topic>.md` — one per week, mirroring `docs/v9_w<N>_*.md`
- `docs/v10_w<N>_<topic>_negative.md` — for any negative-result weeks

If V11 also gets a template, the next iteration should `cp` this
file to `V11_HANDOFF_TEMPLATE.md` and bump every `V10` →`V11` /
`V9` → `V10`. Roughly 5 minutes of find-and-replace.
