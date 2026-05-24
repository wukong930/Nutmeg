# Nutmeg V8 Roadmap

_Generated 2026-05-24 after V7 ship + V7 retrospective._

V7 closed the operational loop (Track C) and laid the cup-trained
model groundwork (Track B). V8 finishes Track B and reads Track A's
verdict. After V8, the project is in **maintenance mode** until a
new product gap appears.

## Why V8 exists

| V7 left behind... | ...V8 closes by... |
|---|---|
| Lineup-aware ROI verdict — pending 4 weeks of data | Reading `nutmeg-ab-report --weeks 4` once data is in |
| Cup-trained artifact — groundwork shipped, retrain not done | UNION cup rows into training frame + multi-fold ablation + ship |
| Cup teams unmapped to V4 canonical names | `team_canonical` global lookup + `CUP_TEAM_ALIASES` (W1) |
| Dashboard 单关 / 复式 surfaces | Web UI / tab additions (V6 W9 punted to CLI only) |
| National-team Elo missing | clubelo `/<NationCode>` ingest + cross-search in `find_team_state_cross_league` |

## Tracks

Same parallel-tracks pattern V7 introduced — the data-gated bits don't
block the code-gated bits.

### Track B closeout (cup-trained model)

| W | Theme | Deliverable | Status |
|---|---|---|---|
| **V8 W1** ✅ | `team_canonical` global lookup | `to_v4_canonical_global` no-league-hint variant; `CUP_TEAM_ALIASES` catch-all; `build_global_team_pool` union helper; `nutmeg-canonical-report-cup` diagnostic CLI. 24 new tests (622/622 V4 suite). See [v8_w1_team_canonical_global.md](v8_w1_team_canonical_global.md) | shipped |
| **V8 W2** ✅ | Cup row UNION into 训练 frame | `nutmeg.v4.data.cup_training`: `build_cup_training_rows` (cup_history × cup_odds → MATCH_COLUMNS schema, applies `to_v4_canonical_global`, pads NaN cols, copies Pinnacle into alt-book proxies); `union_league_and_cup` (concat + 时间排序); `nutmeg-train --with-cup-data` flag (与 W7 `--with-cup-features` 独立 — data vs features). 20 new tests (642/642 V4 suite). **W3 ablation 前若 Elo NaN on cup rows, 需先 cross-league team_state walker**. See [v8_w2_cup_data_union.md](v8_w2_cup_data_union.md) | shipped |
| **V8 W3** ✅ | Cross-league seeding + ablation runner | `nutmeg.v4.features.cross_league_state` (seed_elo_value / seed_form_deque / seed_form_last_date); `build_elo_features` + `build_form_features` + `build_feature_frame` + `WalkForwardConfig` 加 `cross_league_seed` flag (默认 off, 全 V4-V7 测试零变); `nutmeg-train --with-cup-data` 自动 enable seeding; `nutmeg-cup-ablation` CLI 跑 4 fold × 4 mode (baseline / cup_data / cup_features / cup_full), 输出 markdown 卡 + 自动 ship gate (≥ 3/4 folds improve ≥ -0.001 log-loss). 23 new tests (665/665 V4 suite). See [v8_w3_cross_league_seeding_ablation.md](v8_w3_cross_league_seeding_ablation.md) | shipped |
| V8 W4 | Cup-aware artifact ship | If W3 gate passes: train + persist `data/v4_model_cat_cup/`. A/B against default on UCL fixtures. | 2-3d |

### Track A close

| W | Theme | Deliverable | Status |
|---|---|---|---|
| V8 W5 | Lineup-aware verdict | Read 4-week `nutmeg-ab-report` once cron data accumulated. Promote / hold / investigate per V6 W8 decision matrix. | 1-2d, gated on data |

### Track D — new (product polish)

| W | Theme | Deliverable | Status |
|---|---|---|---|
| V8 W6 | Web form wrapping `nutmeg-rec` | HTML form on the dashboard calling `/api/v4/recommend` + `/api/v4/rules` + `/api/v4/predictions/upcoming` → renders markdown card | 4-5d |
| V8 W7 | National-team Elo | clubelo `/<NationCode>` ingest; new `national_team_state` dict; integrate with W11 `find_team_state_cross_league` | 3-4d |
| V8 W8 | V8 ship | `V8_HANDOFF.md` + retrospective + `v8.0-shipped` tag | 2d |

## Numeric targets

| Metric | V7 ship | V8 target |
|---|---:|---:|
| Lineup ROI verdict | pending | **recorded** |
| Cup-trained artifact | groundwork only | **shipped or null-result documented** |
| Dashboard products | 串关 only (单关/复式 CLI) | + form wrapper for all three |
| log-loss (24/25) | 0.9960 | ≤ 0.9930 if any track wins |
| V4 test count | 598 | 700+ |

## Tag plan

| Tag | When | Status |
|---|---|---|
| **V8 W1** ✅ | `team_canonical` global lookup | shipped |
| V8 W2 | Cup row UNION | |
| V8 W3 | Ablation results | |
| V8 W4 | (conditional) cup-aware artifact ship | |
| V8 W5 | Lineup verdict recorded | data-gated |
| V8 W6 | Web form wrapper | |
| V8 W7 | National-team Elo | |
| `v8.0-shipped` | V8 closeout | |

## Out of scope for V8

- Postgres migration (single user, SQLite still fine)
- Multi-user / SaaS
- Markets beyond 1X2 + handicap (user explicitly skipped in V6)
- Live in-play betting
