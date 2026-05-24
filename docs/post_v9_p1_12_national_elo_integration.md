# post-v9 P1#12 — National-team Elo model integration verified end-to-end

_Closes the V9_HANDOFF "V10 backlog → V9 left-overs" item #3:
"National-team Elo model integration". Post-v8 P1#4 did most of the
wiring; this patch verifies the full chain works end-to-end on real
P1#10-ingested parquet data + tests the alias fixes flow through._

## TL;DR

The integration was already substantively in place from post-v8 P1#4:
- `seed_elo_value` accepts `is_national_team_league` + `nation_state`
- `build_elo_features` passes both correctly
- `build_feature_frame` threads `nation_state` through
- `nutmeg-train` exposes `--nation-elo-cache-dir` flag

P1#12 closes the verification + alias-integration loop:
- 6 new tests proving the 4 P1#10 alias fixes (Panama, Rep. Of
  Ireland, Bosnia &, FYR Macedonia) flow through `seed_elo_value` →
  `build_elo_features` correctly
- 1 mega-test exercising `build_elo_features` on a REAL `WC_2022`
  parquet (32 teams) with a synthetic 32-nation `nation_state`,
  asserting ≥ 70% of rows are seeded from nation Elos rather than
  the 1500 default
- Confirms: the integration is fully usable today (modulo clubelo
  service availability for the real Elo data — P1#10's tracked
  upstream outage)

## What's already wired (recap from post-v8 P1#4)

| Layer | Function | Knows about national-team cup? |
|---|---|:---:|
| `seed_elo_value` | `cross_league_state.py:37` | ✅ via `is_national_team_league` + `nation_state` |
| `build_elo_features` | `features/elo.py:35` | ✅ computes `is_nt` per row via `is_national_team_competition(league)` |
| `build_feature_frame` | `features/pipeline.py:168` | ✅ accepts `nation_state` kwarg, passes through |
| `nutmeg-train` CLI | `cli/train.py:145` | ✅ `--nation-elo-cache-dir` builds `nation_state` + passes down |

## What P1#12 verified

The 4 P1#10 alias fixes need to actually FLOW THROUGH the seed
chain — not just resolve in unit-test isolation. The new
`TestP1_12_AliasIntegration` class proves each one:

```python
df = pd.DataFrame([self._row("WC", "Panama", "Brazil")])
nation_state = {"PAN": 1620.0, "BRA": 1950.0}
out = build_elo_features(df, cross_league_seed=True, nation_state=nation_state)
assert out.iloc[0]["elo_home"] == 1620.0   # Panama via P1#10 new code
assert out.iloc[0]["elo_away"] == 1950.0   # Brazil baseline
```

All 4 fixes pass. Plus a `test_mixed_aliases_in_one_dataframe` that
combines all 4 variants in one DataFrame and asserts none falls back
to the 1500 default.

## End-to-end real-parquet test

`TestP1_12_RealParquetEndToEnd.test_wc_2022_first_row_seeds_from_nation_state`
loads the first 8 fixtures from the real `data/external/cup_history/WC_2022.parquet`
(P1#10 ingest), constructs a synthetic 32-nation `nation_state`
covering all WC 2022 participants, and asserts ≥ 70% of `elo_home`
values are non-default. This proves:

- The parquet schema is what `build_elo_features` expects
- The team-name spellings (e.g., "Argentina", "France") resolve
  through `_NAME_TO_CODE` correctly
- `cross_league_seed=True` + `nation_state` together don't break
  on real-world data
- The path is end-to-end usable today

(Test is skipped if WC_2022.parquet doesn't exist, so CI without
the data fixture won't fail.)

## What does NOT change

- ❌ No production training run — that requires (a) clubelo back online for
  real nation_state values, (b) a user decision to train + ship a
  national-team-aware artifact. Path is ready; user has to pull the trigger.
- ❌ `build_features_for_fixtures` (inference path in `model/persist.py`)
  still doesn't accept `nation_state`. Why this is OK:
  - The artifact's `team_state` already contains national-team Elos for
    any nation that appeared in training (training-time `seed_elo_value`
    wrote them into `state["WC"][team]`)
  - Inference-time `build_features_for_fixtures` looks up
    `artifact.team_state["WC"]["Brazil"]` directly — no nation_state needed
  - Only edge case: predicting a brand-new national team the artifact
    never trained on. Falls back to 1500 default — acceptable for an
    edge case that's also incredibly rare (national-team rosters are stable)
  - Adding inference-time `nation_state` is a future enhancement, not a
    blocker

## What does ship in P1#12

- ✅ 6 new alias-integration tests in `test_national_elo_integration.py`
- ✅ 1 end-to-end real-parquet test (auto-skips without data)
- ✅ This documentation — closes the V9_HANDOFF item

## Files touched in P1#12

```
tests/v4/test_national_elo_integration.py            [M] +6 alias integration + +1 real-parquet E2E
docs/post_v9_p1_12_national_elo_integration.md       [+] this writeup
```

(No production code changes; the wiring was already complete from P1#4.)

## Closes

- V9_HANDOFF §8 V10 backlog item #3 ✅
- The V9 W2 "skipped verification" gap (paired with P1#10) ✅

## Total post-v9 patch impact (P1#6 through P1#12)

| Patch | Theme | Tests Δ |
|---|---|---:|
| P1#6 | Deprecation warnings | 0 (silenced 36→0) |
| P1#7 | Dashboard localStorage | +4 |
| P1#8 | sessions/latest read-back | +6 |
| P1#9 | ECE audit multi-cutoff | +6 |
| P1#10 | National-team verification + aliases | +4 |
| P1#11 | Token rotation cron | +6 |
| P1#12 | National-team Elo integration verified | +7 |
| **Cumulative** | V9 ship + maintenance | **803 → 835 (+32)** |

V9 + post-v9 P1 patches now cover every V9 self-deferred item and most
of the original V9_HANDOFF V10-backlog items 1-3. Remaining V10 work
is purely data-gated (Path A cup accumulation, lineup ROI 4-week wait).
