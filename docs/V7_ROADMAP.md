# Nutmeg V7 Roadmap

_Generated 2026-05-24 after V6 ship + V6 W12 retrospective._

V6 closed the product gap (单关 / 串关 / 复式, 竞彩 rules, Chinese
dashboard, lineup-aware artifact, cup registry). V7 closes the
**operational loop** — currently every step (盘口 ingest, settlement,
ROI checking) requires user attention. V7 turns the daily flow into
"refresh + read the report".

The 4-week lineup-aware ROI verdict from V6 W8 is also still pending;
V7 W2 + the daily/weekly automation in V7 W1 + V7 W3 set it up to
actually close.

## Why V7 exists

| V6 produced... | ...but the user still has to... |
|---|---|
| 单关/串关/复式 recommenders | Manually type fixtures + odds CSV every day |
| Lineup-aware opt-in artifact (V6 W7) | Wait for real-bet data, with no auto-pipeline |
| A/B observation infrastructure (V6 W8) | Manually `record_outcome` after each match |
| Cup competition registry (V6 W11) | No cup-trained model — only side-channel cols |

V7 (3 tracks, ~6-8 weeks total) addresses these in priority order.

## Track C — 实时盘口 + 自动 settlement (V7 W1-W3)

The "remove daily friction" track. Once this lands the daily user flow
is "open dashboard → see recommendations → place bets → done".

| W | Theme | Deliverable | Status |
|---|---|---|---|
| **V7 W1** ✅ | `nutmeg-ingest-odds` CLI | Pull /odds per-fixture for today's leagues, parse via `odds_parser`, emit CSV in the shape `nutmeg-rec` expects. GH Actions daily cron uploads it as artifact. `nutmeg-rec --auto-fetch` mode bypasses the manual CSV step entirely. | shipped |
| **V7 W2** ✅ | `nutmeg-auto-settle` CLI | Pulls finished fixtures (FT/AET/PEN) from API-Football across leagues × past N days, upserts into `match_outcomes`, runs `settle_unsettled`. `--dry-run` mode for validation. Idempotent. Local-cron tool by design (observation DB is user-local). 30 new tests (520/520 V4 suite). See [v7_w2_auto_settle.md](archive/v7/v7_w2_auto_settle.md) | shipped |
| **V7 W3** ✅ | Weekly ROI report bundle | `nutmeg-weekly-report` CLI 把 roi-report + ab-report + live-vs-backtest 打包成一个调用; 输出 3 张卡到 docs/weekly/; exit code 透传 (2 = gap 越界, 触发 cron 告警); 设计为本地 cron (观测 DB 是本地的); 10 new tests (530/530 V4 suite). **Track C 闭环**: 用户日常步骤从 5 步压到 2 步. See [v7_w3_weekly_report.md](archive/v7/v7_w3_weekly_report.md) | shipped |

## Track A — Lineup ROI decision (depends on Track C)

After 4 weeks of automated daily-recommend + settle cycles produce
≥30 settled recs per lineup variant, the V6 W6 backtest improvement
(`recent_n_injuries`) can be live-validated.

| W | Theme | Deliverable | Status |
|---|---|---|---|
| V7 W4 | 4-week ROI accumulation | (gated on data — code already shipped in V6 W8 + V7 W3) | wait |
| V7 W5 | Decision + (maybe) default flip | `aware` ROI ≥ +5pp → flip `NUTMEG_V4_ARTIFACT_PATH` default to `data/v4_model_cat_lineups`. `aware` < +2pp → document the backtest-vs-live gap and keep V5 W12 default. | 1d |

## Track B — Cup-trained model (V7 W6-W8)

V6 W11 ship the side-channel cup feature columns but the GBM has zero
cup training data. Track B backfills.

| W | Theme | Deliverable | Status |
|---|---|---|---|
| **V7 W6** ✅ | 杯赛历史 fixtures ingest | `data.cup_history` 数据层模块 (normalize_fixture / parquet roundtrip / multi-season concat / derive_round_flags); `nutmeg-ingest-cup-history` CLI (UCL/UEL/UECL/FAC/COPA_DEL_REY/COPPA_ITALIA/DFB_POKAL/COUPE_DE_FRANCE/WC/EURO/COPA_AMERICA/WC_QUAL_UEFA, 默认拒绝非 cup code); per-(league, season) parquet 输出; 29 new tests (559/559 V4 suite). See [v7_w6_cup_history_ingest.md](archive/v7/v7_w6_cup_history_ingest.md) | shipped |
| **V7 W7** ✅ | `feature_columns_with_cup()` + pipeline wiring | `feature_columns_with_cup(include_lineups=False/True)` 拆开 cup + lineup 独立; `build_feature_frame(cup_history_df=...)` 加 `_merge_cup_round_labels` left-join + 调 `build_cup_features`; `nutmeg-train --with-cup-features` + `--cup-leagues` / `--cup-seasons` / `--cup-history-dir` flags; 17 new tests (576/576 V4 suite). **多 fold ablation 推迟到 W8** (需先 backfill cup odds + reconcile team names). See [v7_w7_cup_features_pipeline.md](archive/v7/v7_w7_cup_features_pipeline.md) | shipped |
| **V7 W8** ✅ | 杯赛 odds backfill | `nutmeg.v4.data.cup_odds` 模块 (mirror of W6's cup_history: normalize / parquet roundtrip / multi-season concat / `merge_cup_fixtures_and_odds`); `nutmeg-ingest-cup-odds` CLI 读 W6 parquets → /odds (Pinnacle 默认) → per-(league, season) parquet; 22 new tests (598/598 V4 suite). **Track B groundwork 全部完成** — 实际 cup-trained ship 推到 V8 (需 team_canonical 扩展 + cup row UNION into training frame). See [v7_w8_cup_odds_ingest.md](archive/v7/v7_w8_cup_odds_ingest.md) | shipped |

## P2 — Stretch / opportunistic

These don't gate Tracks A/B/C but ship value if cycles allow.

- **National-team Elo**: clubelo's `/<NationCode>` endpoint; new
  `national_team_state` dict; cross-search in
  `find_team_state_cross_league`. Unblocks WC / Euro / Copa America
  predictions (currently fall back to "unknown team" path).
- **Auto API token rotation reminder**: GH Actions monthly job that
  hits `/status`, warns when last-rotated > 90 days.
- **Web UI for `nutmeg-rec`**: form wrapping `/api/v4/recommend`,
  `/api/v4/rules`, `/api/v4/predictions/upcoming` for non-terminal users.
- **Bake fixture cache for CI**: small EPL+La Liga lineup fixture set so
  GH Actions exercises the lineup-aware code paths (currently skipped).

## Numeric targets

| Metric | V6 ship | V7 target |
|---|---:|---:|
| Daily prompt steps (manual) | ~5 (refresh, ingest odds, run rec, place bets, record outcomes) | **≤2** (read recommendation, place bets) |
| Live-data → A/B card latency | ≥1 week (manual) | **≤1 day** (auto) |
| Cup match prediction coverage | side-channel cols only | trained model |
| 4-week lineup-aware ROI decision | pending | **closed** |
| log-loss (24/25, GBM-eligible) | 0.9960 | ≤ **0.9930** if lineup wins, else 0.9960 |
| V4 test count | 468 | 530+ |

## Tag plan

| Tag | When | Status |
|---|---|---|
| `v7.w1` | `nutmeg-ingest-odds` shipped | ✅ |
| `v7.w2` | `nutmeg-auto-settle` shipped | ✅ |
| `v7.w3` | Weekly ROI cron live | ✅ |
| `v7.w5` | Lineup ROI decision recorded | ⏳ (data-gated → V8) |
| `v7.w6` | Cup historical fixtures → parquet | ✅ |
| `v7.w7` | feature_columns_with_cup + pipeline wiring | ✅ |
| `v7.w8` | Cup historical odds backfill (Track B groundwork) | ✅ |
| `v7.0-shipped` | V7 closeout, V7_HANDOFF + retrospective | ✅ |

## Out of scope for V7

- Web UI rebuild beyond the form wrapper (V8+ if there's demand)
- Multi-user / SaaS posture (single user is the target)
- Additional markets (correct score, totals, HT-FT) — user explicitly
  skipped in V6 scope; same decision holds
- Postgres migration (SQLite is fine at single-user volume)
