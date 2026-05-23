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
| V7 W2 | `nutmeg-auto-settle` CLI | Each evening: pull yesterday's final scores from API-Football `/fixtures` (status=FT/AET/PEN), upsert into `match_outcomes`, trigger `settle_unsettled`. Wire into GH Actions cron. | 2-3d |
| V7 W3 | Weekly ROI report cron | Extend `weekly-bench.yml` to call `nutmeg-roi-report` + `nutmeg-ab-report --weeks 4` + `nutmeg-live-vs-backtest`; commit cards to `docs/weekly/`. **Triggers the V6 W8 lineup-aware ROI verdict to actually close.** | 1d |

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
| V7 W6 | UCL/UEL fixtures ingest | 3-4 seasons of UCL + UEL fixtures + lineups via existing `nutmeg-ingest-lineups`. Cup-aware variant of `build_lineup_lookup`. | 3-4d |
| V7 W7 | `feature_columns_with_cup()` integration | Wire the 5 W11 side-channel cols into a new feature set; multi-fold ablation (4 cutoffs × {EPL+UCL, ESP_LA_LIGA+UCL, ITA_SERIE_A+UCL, club_cup_pooled}) | 4-5d |
| V7 W8 | Cup-aware artifact ship | `nutmeg-train --with-cup-features` → opt-in `data/v4_model_cat_cup/`. A/B vs default on cup-fixture predictions. | 2-3d |

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

| Tag | When |
|---|---|
| `v7.w1` | `nutmeg-ingest-odds` shipped (this week) |
| `v7.w2` | `nutmeg-auto-settle` shipped |
| `v7.w3` | Weekly ROI cron live |
| `v7.w5` | Lineup ROI decision recorded |
| `v7.w8` | Cup-aware artifact ship |
| `v7.0-shipped` | V7 W8 close, V7_HANDOFF written |

## Out of scope for V7

- Web UI rebuild beyond the form wrapper (V8+ if there's demand)
- Multi-user / SaaS posture (single user is the target)
- Additional markets (correct score, totals, HT-FT) — user explicitly
  skipped in V6 scope; same decision holds
- Postgres migration (SQLite is fine at single-user volume)
