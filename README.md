# Nutmeg

Nutmeg is a football probability prediction platform. This repository currently
contains the backend skeleton, market settlement layer, Poisson score model
baseline, accuracy learning loop, and frontend MVP from the V2 documents.

The product goal is accuracy, traceability, and calibration. Nutmeg does not
implement automated betting, wallet, payments, deposit or withdrawal flows, or
profit-certainty claims.

## Implemented Scope

Implemented scope:

- Project skeleton.
- FastAPI backend skeleton.
- Core PostgreSQL migration script.
- Competition configuration YAML structure.
- Poisson lambda estimate interface and score probability grid model.
- Tail probability metrics and Top N score extraction.
- Prediction snapshot model with model, feature, calibration, and prediction
  timestamps.
- Market settlement and probability resolver interfaces for 1X2, Asian 1X2,
  CN handicap 1X2, European handicap 1X2, Asian handicap, and correct score.
- Score grid to market probability conversion.
- File-backed prediction snapshot persistence for local deterministic testing.
- Parlay optimizer core for single-selection and multiple-selection tickets:
  atomic expansion, unit stake, total stake, hit probability, expected payout,
  EV, ROI, budget validation, placeholder risk scoring, and explanation payloads.
- Multiple-selection budget pruning now uses a budget-constrained quality search
  to preserve the highest-value outcome subset under the user's max budget,
  while keeping locked outcomes intact and recording internal pruning metrics.
- Accuracy Learning Loop MVP: post-match evaluator, 1X2 Brier score, 1X2 log
  loss, prediction-vs-result comparison, score probability/rank lookup, error
  tag classification, calibration bucket storage, model comparison stub, and
  backtest run schemas.
- Recommendation upset policy v3.1: separates protective upset directions from
  fragile-favorite avoidance, then feeds that signal into candidate scoring,
  multiple-selection optimization, global planning, and final answer arbitration.
- Accuracy summary aggregation: deterministic evaluation-event repository,
  competition/market/window/model filters, calibration bucket rollups, error
  type summaries, and model comparison payload generation for the Accuracy API.
- Postgres Accuracy repository contract: SQL-backed row mapping for
  `prediction_evaluations`, `calibration_buckets`, and
  `model_comparison_reports`, plus a repository-agnostic summary service.
- Configurable Accuracy Summary repository mode: local mock fixtures by
  default, or Postgres reads through `NUTMEG_ACCURACY_REPOSITORY=postgres`.
- Accuracy Learning Loop write contract: post-match evaluation persistence,
  1X2 calibration bucket upserts, backtest run storage, and model comparison
  report storage for Postgres.
- Probability calibration profile-gate/profile-grid CLIs now support compact
  stdout summaries, profile-grid in-run transform-report and baseline-backtest
  reuse for large historical calibration searches, plus candidate-level
  progress JSONL for long-running grids, while preserving full JSON report
  artifacts through `--output-path`.
- Frontend MVP: fixture list, fixture detail, 1X2 probability display,
  handicap probability display, Top 5 score display, upset alerts, parlay
  recommendation page, model version/prediction timestamp metadata, and data
  quality badges.
- Frontend v2.1 design plan intake: `Nutmeg_docs_v2/Nutmeg_Frontend_Design_Spec.md`
  is now part of the execution plan for future FE-01 through FE-08 work.
- Frontend FE-01 design foundation: centralized light/dark-ready tokens,
  responsive app shell/navigation, and Card, Badge, Tabs, Tooltip, and Table
  primitives for the Quant Sports Lab interface direction.
- Frontend FE-02 match list MVP: scannable match cards with compact 1X2
  probability triptych, risk/data-quality badges, main handicap line, Top score
  hint, model metadata, and competition/date-oriented filter controls.
- Frontend FE-03 match detail MVP: reusable MatchHeader, full 1X2
  ProbabilityTriptych, compact PredictionTrace, TopScores panel with score
  probability tooltip, and compact ModelFingerprint.
- Frontend FE-04 market visualization: MarketGapChart, HandicapResolverPanel,
  compact/advanced ScoreGridHeatmap, and basic MarketMovementTimeline with
  explicit missing-history states.
- Frontend FE-05 Upset Watch: filterable upset list, FavoriteFragilityPanel,
  risk contribution bars, explanation drawer, and required risk microcopy that
  frames upset alerts as observations rather than outcomes.
- Frontend FE-06 Parlay Lab MVP: ParlayBuilder inputs, multi-selection leg
  preview, ParlayExpansionTree atomic bet display, ParlayEvaluationPanel, stake
  and total-cost metrics, correlation penalty, and volatility risk copy.
- Frontend FE-07 Accuracy Lab MVP: CalibrationCurve, BrierTrend,
  LogLossTrend, model version selector, and evaluation window display for
  probability-quality review.
- Frontend FE-08 copy and compliance pass: global research-only risk notice,
  required parlay/upset/score risk copy, table captions for probability
  diagnostics, and static checks against forbidden guarantee language.
- Phase 9 acceptance hardening: end-to-end mock MVP integration flow,
  Playwright dashboard/detail/parlay/accuracy/upset checks, and a public VPS
  acceptance script for API and page markers.
- Phase 10 production-data preparation: provider authorization records,
  provider adapter governance interfaces, weighted data-quality scoring,
  competition beta/production readiness gates, parlay data-quality blocking,
  and model promotion/rollback evidence stubs.
- Phase 10 football-data.org adapter skeleton: token-safe v4 client,
  competition/match/team fetch methods, unsupported capability guards for odds
  and lineup data, raw provider payload persistence, provider sync run audit,
  and football-data match normalization.
- Phase 10 SportMonks availability preparation: token-safe adapter skeleton for
  fixture lineups and team injuries, lineup/injury normalizers, raw payload
  audit, sync-run audit, Postgres writes to `lineup_snapshots` and
  `player_availability_snapshots`, normalized `provider_observations` for
  lineup/injury fields, and fixture-level availability freshness guards for
  API/parlay flows.
- Phase 10 Feature Snapshot productionization: as-of-time feature snapshot
  builder for fixture reliability, odds coverage, lineup/injury coverage,
  historical stats completeness, provider consistency, and data freshness;
  Postgres `feature_snapshots` write repository; prediction explanation payloads
  with source snapshot refs; and local Accuracy seed flow linked through
  `feature_snapshot_id`.
- Phase 10 prematch prediction pipeline: Postgres writer for model versions,
  score grids, and prediction snapshots; coverage-aware mock prematch pipeline
  that persists feature snapshots before prediction snapshots; audited
  `prediction_job_runs`; and guarded admin endpoints for dry-run or committed
  prematch prediction generation.
- Phase 10 canonical fixture prediction pipeline: reads provider-synced Nutmeg
  fixtures from Postgres by kickoff window, derives Poisson lambdas from
  `aggregate_context_json` when present, otherwise from as-of-time historical
  team-strength aggregates when each team has enough settled samples, falling
  back to a documented competition baseline only for cold starts. The pipeline
  preserves Dixon-Coles v1.5-compatible metadata and writes the same
  feature/grid/prediction snapshot chain as mock prematch jobs.
- Phase 10 prematch operations workflow: guarded admin endpoint and top-level
  `prematch_workflow_runs` audit table that chains canonical/mock prematch
  prediction generation with stored-market-prediction parlay generation. The
  workflow keeps child `prediction_job_runs`, generated prediction snapshot
  IDs, parlay recommendation IDs, warnings, timing, and dry-run state
  traceable.
- Phase 10 provider sync workflow: guarded admin endpoint and
  `provider_sync_workflow_runs` audit table that orchestrates explicit
  football-data.org fixture sync, The Odds API event odds sync, SportMonks
  lineup/injury sync, and optional prematch workflow execution. Each run records
  child provider sync IDs, raw payload IDs, canonical fixture IDs, counts,
  warnings, timing, and dry-run state.
- Phase 10 provider operations visibility: read-only provider entity mapping API,
  lookup indexes for provider/canonical mapping review, persisted review-run
  audit storage, and a frontend Provider Ops page that surfaces provider
  authorization, competition readiness, mapping summary, recent mapping records,
  and manual review issues without exposing secrets or running syncs.
- Phase 10 provider workflow template operations: active template update and
  soft-archive endpoints, Provider Ops load/update/archive controls, and
  dry-run operator approval audit records linked to workflow run IDs. The
  Provider Ops template editor supports multiple explicit odds and availability
  tasks in one dry-run template, with a task review matrix that shows explicit
  IDs and scoped preflight issues before execution.
- Phase 10 provider sync dry-run rehearsal: explicit-ID Provider Sync workflows
  can use deterministic local provider samples when dry-run mode is enabled and
  real provider keys are absent. This keeps VPS operator approval and audit
  flows testable without storing data-source secrets.
- Phase 10 provider runtime readiness: admin-only runtime key status API and
  Provider Ops view show whether each data-source key is configured, whether
  dry-runs will use real providers or deterministic samples, and whether commit
  sync is blocked. Secret values are never returned.
- Phase 10 provider runtime monitoring: `provider_runtime_snapshots`
  migration, admin-only monitor endpoints, and a Provider Ops read-only table
  track probe status, latency, error-rate, rate-limit placeholders, fallback
  use, and next actions without storing provider secrets.
- Phase 10 provider runtime alerts: monitoring responses now include
  alert-level, P0/P1/P2 alert rows, and documented thresholds for provider
  error rate, provider latency, and fallback usage.
- Phase 10 provider runtime incidents: `provider_runtime_incident_reports`
  stores alert summaries from monitoring snapshots, and VPS helpers can run the
  non-live monitor from cron without exposing admin tokens in logs.
- Phase 10 provider authorization review governance:
  `provider_authorization_reviews` audit records, `last_reviewed_at` /
  `next_review_due_at` registry fields, admin-only review list/write endpoints,
  and Provider Ops terms-review visibility for allowed use, data retention,
  historical-data, and redistribution decisions.
- Phase 10 provider conflict governance: `provider_conflict_events` and
  trusted provider priority schema, dry-run conflict evaluation from mapping
  review evidence, quality-score impact estimates for provider consistency, and
  Provider Ops visibility for conflict events and priority policy.
- Phase 10 provider observation conflict detection: normalized
  `provider_observations` storage for synced fixtures/results/odds/lineups/
  injuries, idempotent open-conflict persistence, dry-run observation conflict
  evaluation, and canonical feature snapshots that can reduce
  provider-consistency quality from open fixture conflict events.
- Dixon-Coles v1.5 skeleton: log-linear lambda estimate interface with
  attack/defense parameters, home advantage, context adjustments, exponential
  time-decay placeholder, safe `rho` low-score adjustment, non-negative
  normalized score-grid generation, and automatic score-grid dispatch when a
  lambda estimate carries `rho`.
- Dixon-Coles offline training entrance: as-of-time frozen train/validation
  windows, weighted attack/defense parameter baseline, documented exponential
  time decay, deterministic `rho` grid search using negative weighted log
  likelihood, score-grid regression checks, and a structured candidate training
  report for later backtest persistence.
- Dixon-Coles backtest persistence bridge: converts offline training reports
  into `BacktestRunSchema`, metrics and calibration payloads for
  `model_backtest_runs`, and candidate-vs-baseline model comparison stubs that
  stay in `needs_review` while Brier score or calibration metrics are missing.
- Accuracy Lab frontend: model/window/competition/market filters, core
  accuracy metrics, market and competition breakdowns, calibration buckets,
  error type distribution, and model comparison status display.
- API contract bridge: typed FastAPI responses for fixtures, fixture
  predictions, score grids, upsets, parlay recommendations, parlay evaluation,
  expanded accuracy summary, and competitions, plus a frontend API client with
  validated fallback data.
- V3.1 recommendation benchmark operations: core validation, benchmark matrix,
  scheduled benchmark, persisted benchmark history, quality gate, combined
  cycle runner, baseline preflight, cross-strategy benchmark comparison, paired
  strategy benchmark runner, successor/validity/upset-aware gate checks, and
  Postgres-compatible optional-filter queries for local accuracy regression
  evidence.
- V3.1 historical sample coverage audit: local frozen suite inventory for core
  football-data.co.uk history, market-movement feature samples, and context
  signal samples, with fixture coverage, feature-family coverage, readiness
  flags, and cross-suite gap detection.
- V3.1 derived-market historical candidates: complete 1X2 frozen slices can be
  expanded into shadow Chinese handicap 1X2, European handicap 1X2, and
  correct-score candidates, then replayed through the same final-answer
  backtest and quality-gate path.
- V3.1 final-answer market concentration audit: historical final answers can be
  checked for single-market dominance, true mixed-market answer coverage, and
  non-regression in hit rate, ROI, profit/loss, Brier, log-loss, and
  calibration error.
- V3.1 expanded A-league market-feature suite: Eredivisie, Primeira Liga,
  Championship, 2. Bundesliga, Serie B, Segunda Division, and Ligue 2 now have
  five frozen football-data.co.uk seasons each, competition config entries, and
  a 35-slice market-movement suite for shadow feature learning.
- V3.1 competition admission gate: new competition suites must pass final-answer
  hit/ROI, per-competition ROI, feature holdout, and coverage evidence before
  entering default recommendations or the training pool.
- V3.1 beta-quality lane evidence: historical backtests can keep the global
  data-quality floor at `80` while allowing one audited lower-quality
  competition band through additional probability, odds, edge, calibration,
  odds-stability, and volatility guards. This is an opt-in shadow path and does
  not change the default recommendation profile.
- V3.1 beta-quality probability repair evidence: the beta-lane shadow path can
  optionally lift under-confident lower-quality candidates toward a capped
  market-implied probability floor, then block promotion unless final-answer
  hit, ROI, P&L, and probability-quality gates all hold.
- V3.1 beta-lane local calibration profile evidence: the same shadow path can
  add a segment-local uplift using market gap, data-quality gap, and odds
  stability inputs, producing a focused accepted ITA Serie B candidate while
  remaining blocked from default promotion until rolling/holdout admission.
- V3.1 beta-lane rolling admission: focused local-calibration profiles now pass
  through overall, competition, season, and rolling-window folds before any
  runtime proposal; the current ITA Serie B profile remains shadow-only because
  evidence is too concentrated and several fold-level probability gates fail.
- V3.1 beta-lane season/regime throttling: beta-quality lane and probability
  repair can now be scoped to audited season ids and competition season-index
  windows. Rolling windows from the same league season share one competition
  season index, so exposure limits describe seasons rather than arbitrary slice
  counts. The latest ITA Serie B season-regime grid accepted 15 shadow
  candidates, but rolling admission remains `shadow_only`.
- V3.1 J1 closing-only feature samples: football-data.co.uk worldwide CSV rows
  with only closing odds can be frozen as explicit closing-only feature slices
  without pretending they contain opening-to-closing market movement.
- V3.1 final answer arbitration: global best recommendations are selected
  through a dedicated backend arbitrator that compares singles, parlays,
  multiples, handicap markets, and correct-score candidates by EV, hit
  probability, risk, data quality, and budget efficiency without exposing
  internal strategy labels.
- V3.1 dynamic mixed-market recommendation invariant: a user-facing 2x1-8x1
  recommendation is a single global answer built from the best per-fixture
  selections, not a pre-fixed market silo. One parlay can dynamically mix
  ordinary 1X2, Chinese or European handicap 1X2, correct score, single-choice
  legs, and multiple-choice legs when the combined answer is stronger and stays
  inside the user's budget and rule constraints. Historical suite replay and
  the suite quality gate now summarize and can require dynamic mixed-market,
  handicap, correct-score, and multiple-choice final answers. Benchmark
  quality gates and benchmark cycles also pass through those historical-suite
  final-answer market metrics and can optionally require minimum dynamic-mixed,
  handicap, correct-score, or multiple-choice coverage.
- V3.2 Asian-handicap prematch-feature shadow comparison and role search:
  1X2-only market movement samples can be compared against 1X2 plus
  Asian-handicap movement in the Poisson prematch-feature walk-forward path,
  and the Asian-handicap movement contribution can be searched by weight and
  minimum movement delta before any production profile change.
- V3.1 expanded A-league rolling-window calibration evidence: the same
  market-odds-band profile gate was replayed on 210 expanded-league windows.
  The strict gate selected no competitions; an include-rejected diagnostic
  regressed final-answer hit rate and ROI, so this profile remains blocked
  outside the five-major-league shadow evidence lane.
- V3.1 minimal answer page: the frontend consumes the public `answer_set`
  envelope and keeps the ordinary path focused on one primary answer, necessary
  backups, budget, risk, data quality, model timestamp, and selected-fixture
  upset notices.
- API stubs for fixtures, predictions, score grid, parlays, upsets, accuracy,
  and competitions.
- Unit and integration tests for implemented milestone behavior.

Out of scope:

- Fully authorized production provider integration and scheduled ingestion.
- Automated betting or real-money betting placement.
- Full Dixon-Coles training.
- Fully optimized Dixon-Coles parameters, automated weekly retraining, and
  calibrated automatic model activation. The current Dixon-Coles training path
  is a deterministic offline entrance with simplified weighted attack/defense
  fitting plus persisted backtest, comparison, and promotion-review artifacts;
  it is still not a production optimizer.
- Automated scheduled feature/prediction generation jobs and real
  historical-stat feature providers.
- Full trained team-strength lambda model for arbitrary provider-synced
  fixtures. The current canonical pipeline now uses a transparent rolling
  result attack/defense baseline, but it is not yet fitted, calibrated, or
  time-decayed like the future Dixon-Coles training path.
- Full model retraining automation, rollback execution automation, and
  calibration model fitting.
- Full Accuracy Learning Loop automation.
- Live database connection pooling for the Accuracy API. The Postgres read path
  uses a small synchronous executor per query and does not yet pool
  connections.
- Production frontend polish and real API wiring.
- Live odds streaming.

## Local Setup

This project uses Python 3.12+ and `uv`.

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Run the API locally:

```bash
uvicorn nutmeg.main:app --reload --app-dir apps/api/src
```

The Accuracy Summary API defaults to deterministic local fixtures:

```bash
export NUTMEG_ACCURACY_REPOSITORY=mock
```

To read accuracy summaries from Postgres tables such as
`prediction_evaluations`, `calibration_buckets`, and
`model_comparison_reports`, configure:

```bash
export NUTMEG_ACCURACY_REPOSITORY=postgres
export NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg
export NUTMEG_DATABASE_CONNECT_TIMEOUT_SECONDS=3
```

Run the internal recommendation core validation chain as a repeatable local
diagnostic:

```bash
uv run nutmeg-recommendation-core-validation \
  --as-of-time-utc 2026-05-04T12:00:00Z \
  --lookback-hours 24 \
  --pass-type 6x1 \
  --mode multiple
```

The command prints JSON and defaults to dry-run. It runs Global Best, the
prematch recommendation pipeline, core replay, and recommendation chain
integrity in one window. Use
`--skip-*` flags to isolate a stage, `--commit` only when persistence is
intended, and `--save-audit` only when the prematch pipeline audit row should be
written. Chain integrity is read-only and blocks only through internal warning
and gate metrics; use `--skip-chain-integrity` only for isolated debugging.

Run an internal recommendation benchmark matrix across fixed pass types,
single/multiple modes, and budget levels:

```bash
uv run nutmeg-recommendation-benchmark \
  --as-of-time-utc 2026-05-04T12:00:00Z \
  --pass-types 2x1,4x1,6x1,8x1 \
  --modes single,multiple \
  --budgets 10,20,50
```

The benchmark command also defaults to dry-run. It calls the core validation
runner once per matrix scenario and aggregates selected-count, replay-ready,
chain-integrity-ready, critical chain issue, settled-run, final-hit, ROI, and
warning metrics for development review. Add `--include-prematch-pipeline` only
when incident/recompute/report checks should be included for every scenario.
Add `--save-report` to persist the benchmark JSON into
`recommendation_benchmark_runs`; persisted runs include a comparison against the
latest previous report with the same benchmark matrix.

Run the same benchmark matrix as a cron-friendly daily or weekly schedule:

```bash
uv run nutmeg-recommendation-benchmark-schedule \
  --schedule-name daily-core \
  --cadence daily \
  --run-at-utc 2026-05-10T00:00:00Z \
  --window-count 7 \
  --pass-types 2x1,4x1,6x1,8x1 \
  --modes single,multiple \
  --budgets 10,20,50
```

The schedule command expands the requested cadence into fixed `as_of_time`
windows, then delegates to the benchmark runner. It defaults to dry-run and
does not store reports unless `--save-report` is provided. Use it from cron or
another scheduler after Postgres sample data is available.

Evaluate the latest persisted benchmark report against internal quality gates:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --benchmark-key recommendation_benchmark:replace-with-key \
  --min-completed-ratio 0.95 \
  --max-failed-count 0 \
  --min-core-replay-ready-ratio 0.70 \
  --max-chain-integrity-critical-issue-count 0 \
  --min-successor-chain-evaluation-passed-ratio 1.0 \
  --max-successor-chain-critical-issue-count 0 \
  --max-successor-chain-ambiguous-source-count 0 \
  --max-ambiguous-successor-source-count 0 \
  --max-stale-recommendation-count 0 \
  --max-successor-recompute-required-count 0 \
  --min-final-hit-sample-size 10 \
  --min-final-hit-rate 0.50 \
  --min-upset-capture-sample-size 3 \
  --min-upset-capture-rate 0.30
```

The gate command reads `recommendation_benchmark_runs`, prints a JSON report,
and exits non-zero when a configured threshold fails. Chain integrity critical
issues fail the gate by default, so source/successor cycles, duplicate active
successors, and missing source links cannot become trusted accuracy evidence.
The gate also checks successor-chain evaluation when configured, including the
ratio of scenarios whose effective leaf-run evaluation passed, successor-chain
critical issues, ambiguous sources, and source-status-sync pressure. Lifecycle
quality checks cover ambiguous successor sources, stale recommendations, and
runs that still require successor recompute. Upset capture thresholds use
settled upset opportunity samples when the benchmark summary contains those
metrics. It is intended for internal cron/CI review after scheduled benchmark
reports have been persisted.

For the current short-odds guarded replacement candidate, use the named runtime
profile switch preset instead of manually wiring the switch and staged replay
artifacts:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --benchmark-key recommendation_benchmark:replace-with-key \
  --runtime-profile-switch-preset short_odds_candidate_v1 \
  --allow-missing-history
```

The preset points to the switch-ready staged profile evidence and its shadow
replay report, requires staged-only evidence, and keeps default production
profile writes out of the benchmark gate.

For the current final-answer segment penalty holdout candidate, use the named
runtime replay preset. This preset points to the GER regime runtime replay
report, requires the replay to remain `holdout_replay_passed`, and does not
require runtime production allowance because the absolute ROI floor is still
not met:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --final-answer-segment-penalty-runtime-replay-preset final_answer_segment_penalty_ger_regime_holdout_v1 \
  --allow-missing-history
```

The local gate smoke is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_runtime_replay_benchmark_gate_smoke_v1.json`.
It passes with `gate_key=recommendation_benchmark_quality_gate:all:any`,
`final_answer_segment_penalty_runtime_replay_status=holdout_replay_passed`,
`final_answer_segment_penalty_runtime_replay_holdout_allowed=true`,
`final_answer_segment_penalty_runtime_replay_runtime_allowed=false`, ROI delta
`+0.07033333333333333`, hit-count delta `+2`, and harm count `0`.

The benchmark gate can also require the scoped replacement reranker admission
artifact before treating a benchmark cycle as quality-approved:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --benchmark-key recommendation_benchmark:replace-with-key \
  --replacement-reranker-shadow-admission-report-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_scoped_competition_admission_quality_edge_v1.json \
  --require-replacement-reranker-shadow-admission \
  --require-replacement-reranker-scoped-evidence \
  --min-replacement-reranker-scope-final-answer-count 19 \
  --min-replacement-reranker-shadow-final-answer-count 17 \
  --min-replacement-reranker-changed-from-model-top-count 5 \
  --min-replacement-reranker-hit-delta-vs-model-top 1 \
  --min-replacement-reranker-profit-loss-delta-vs-model-top 4.0 \
  --min-replacement-reranker-roi-delta-vs-model-top 0.10 \
  --max-replacement-reranker-harm-count-vs-model-top 0 \
  --max-replacement-reranker-final-hit-harm-count-vs-model-top 0 \
  --max-replacement-reranker-profit-loss-harm-count-vs-model-top 0 \
  --max-replacement-reranker-failed-fold-count 0 \
  --min-replacement-reranker-active-competition-fold-count 2 \
  --min-replacement-reranker-active-season-fold-count 3 \
  --min-replacement-reranker-active-rolling-fold-count 4
```

This check reads the admission report only as internal quality evidence. It
requires the report to be accepted, scoped, no-harm versus model-top, and fold
stable; it does not write a production profile and does not change the public
recommendation response.

Run the scheduled benchmark and quality gate as one internal cycle:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --schedule-name daily-core \
  --cadence daily \
  --run-at-utc 2026-05-12T00:00:00Z \
  --window-count 7 \
  --pass-types 2x1,4x1,6x1,8x1 \
  --budgets 10,20,50 \
  --save-report \
  --save-cycle-report \
  --gate-min-completed-ratio 0.95 \
  --gate-min-core-replay-ready-ratio 0.70 \
  --gate-max-chain-integrity-critical-issue-count 0 \
  --gate-min-successor-chain-evaluation-passed-ratio 1.0 \
  --gate-max-successor-chain-critical-issue-count 0 \
  --gate-max-successor-chain-ambiguous-source-count 0 \
  --gate-max-ambiguous-successor-source-count 0 \
  --gate-max-stale-recommendation-count 0 \
  --gate-max-successor-recompute-required-count 0 \
  --gate-runtime-profile-switch-preset short_odds_candidate_v1 \
  --gate-final-answer-segment-penalty-runtime-replay-preset final_answer_segment_penalty_ger_regime_holdout_v1 \
  --gate-replacement-reranker-shadow-admission-report-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_scoped_competition_admission_quality_edge_v1.json \
  --gate-require-replacement-reranker-shadow-admission \
  --gate-require-replacement-reranker-scoped-evidence \
  --gate-min-replacement-reranker-scope-final-answer-count 19 \
  --gate-min-replacement-reranker-shadow-final-answer-count 17 \
  --gate-min-replacement-reranker-changed-from-model-top-count 5 \
  --gate-min-replacement-reranker-hit-delta-vs-model-top 1 \
  --gate-min-replacement-reranker-profit-loss-delta-vs-model-top 4.0 \
  --gate-min-replacement-reranker-roi-delta-vs-model-top 0.10 \
  --gate-max-replacement-reranker-harm-count-vs-model-top 0 \
  --gate-max-replacement-reranker-final-hit-harm-count-vs-model-top 0 \
  --gate-max-replacement-reranker-profit-loss-harm-count-vs-model-top 0 \
  --gate-max-replacement-reranker-failed-fold-count 0 \
  --gate-min-replacement-reranker-active-competition-fold-count 2 \
  --gate-min-replacement-reranker-active-season-fold-count 3 \
  --gate-min-replacement-reranker-active-rolling-fold-count 4
```

The cycle command delegates to the schedule runner first, then evaluates the
quality gate against the generated benchmark key. Use `--save-report` when the
gate should evaluate the current run; without it, the gate reads the latest
already persisted report for that benchmark key. Use `--save-cycle-report` to
persist the combined schedule + quality-gate result into
`recommendation_benchmark_cycle_runs`; that cycle report includes historical
suite gate, lifecycle smoke, source-status-sync, and failed-check summary fields
for trend review. The runtime profile switch preset also adds
`runtime_profile_switch_preset` and the staged replay metrics to the gate and
cycle summaries, and cycle keys that use the preset include
`runtime_profile_switch_preset:short_odds_candidate_v1` so stricter staged
profile evidence cannot be mixed with older cycle histories. The bootstrap cycle
smoke artifact is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_benchmark_cycle_preset_smoke_v1.json`.
The explicit no-harm runtime-profile-switch smoke artifact is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_benchmark_cycle_explicit_harm_smoke_v1.json`;
it keeps final-hit harm and profit/loss harm as separate zero-tolerance fields
inside the cycle summary.
The segment-penalty runtime replay preset adds
`final_answer_segment_penalty_runtime_replay_preset` and holdout replay metrics
to the same gate and cycle summaries; cycle keys using it include
`final_answer_segment_penalty_runtime_replay_preset:final_answer_segment_penalty_ger_regime_holdout_v1`.
The replacement reranker admission flags attach scoped no-harm/fold-stability
evidence to the same gate and cycle summaries; they still do not write a
production profile or expose internal strategy text.

Check whether the local Postgres database is ready for a real benchmark
baseline:

```bash
uv run nutmeg-recommendation-benchmark-preflight
```

The preflight command is read-only. It checks database connectivity, required
recommendation/benchmark tables, and existing benchmark history count. A warning
for empty history is expected before the first saved baseline; connection or
schema failures must be fixed before `benchmark-cycle --save-report` can create
usable evidence.

For a fresh local Postgres benchmark baseline, create the local role/database,
apply migrations with `psql`, then run preflight and a minimal saved cycle:

```bash
psql -h localhost -d postgres <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nutmeg') THEN
    CREATE ROLE nutmeg LOGIN PASSWORD 'nutmeg';
  END IF;
END $$;
SQL

createdb -h localhost -O nutmeg nutmeg

for migration in db/migrations/*.sql; do
  PGPASSWORD=nutmeg psql -h localhost -U nutmeg -d nutmeg \
    -v ON_ERROR_STOP=1 -f "$migration"
done

NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-benchmark-preflight

NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-benchmark-cycle \
    --schedule-name local-empty-smoke \
    --cadence once \
    --run-at-utc 2026-05-12T00:00:00Z \
    --pass-types 2x1 \
    --modes single \
    --budgets 10 \
    --save-report \
    --allow-missing-history \
    --no-fail-process
```

On an empty database the cycle should complete its scenario but fail the quality
gate for missing replay/final-hit evidence. That is expected until fixtures,
predictions, candidate pools, recommendation runs, and settled results are
loaded.

Seed a deterministic local football sample and create a real recommendation
benchmark baseline:

```bash
NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-baseline-seed

NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-benchmark-cycle \
    --schedule-name local-seeded-single-matrix \
    --cadence once \
    --run-at-utc 2026-05-12T00:00:00Z \
    --pass-types 2x1,4x1,6x1,8x1 \
    --modes single \
    --budgets 10 \
    --competition-id BENCH_V3 \
    --model-version poisson-v3.1-baseline \
    --commit \
    --save-report \
    --allow-missing-history \
    --gate-min-core-replay-ready-ratio 1 \
    --gate-min-final-hit-sample-size 4 \
    --gate-min-final-hit-rate 0.5
```

The seed command writes eight deterministic benchmark fixtures, feature
snapshots, prediction snapshots, 1X2 odds snapshots, and result rows. It keeps
fixtures pre-match eligible for the as-of-time query while result rows exist for
replay, so this path is for local regression evidence only. The default
`happy_path` profile keeps the model's strongest 1X2 legs aligned with the
settled outcomes. Available stress profiles are:

- `mixed_outcomes`: keeps the same predictions but flips several deeper settled
  results for hit/miss regression checks.
- `upset_stress`: flips several strong favorites into draws or losses to test
  cold-result sensitivity.
- `adverse_odds`: keeps settled results aligned with the model but reprices
  model-favorite 1X2 outcomes against the model edge, so value/ROI gates can
  catch high-probability but poor-price recommendations.
- `low_quality_filter`: lowers selected top fixtures below the default data
  quality threshold so the planner must use the remaining pool.
- `missing_result`: omits result rows for selected fixtures to verify replay
  readiness and unresolved settlement handling.

Use `--no-reset` to append another seed pass; the default reset removes prior
generated recommendation runs for all known seeded fixture IDs before rewriting
the selected sample profile.

The `value_first` recommendation strategy now uses a value-aware policy: when
`min_model_edge` is not explicitly set, it defaults to filtering out negative
model-edge candidates and gives model edge more weight than raw probability.
This is useful with `adverse_odds`, where `accuracy_first` may still prefer a
high-probability favorite while `value_first` should prefer a lower-probability
but better-priced alternative.

Persisted benchmark reports can be compared across strategies with the internal
strategy comparison CLI. This is meant for backend accuracy evidence only; it
does not change the ordinary recommendation response or show strategy details to
users.

```bash
NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-benchmark-strategy-compare \
    --candidate-strategy value_first \
    --baseline-strategy accuracy_first \
    --min-roi-delta 0 \
    --min-final-hit-sample-size 4
```

Because benchmark keys include the strategy, compare exact saved runs with
`--candidate-benchmark-key` and `--baseline-benchmark-key` when needed. The
comparison still verifies that both reports used the same as-of windows, pass
types, modes, budgets, scenario count, and dry-run setting unless
`--no-require-matrix-match` is explicitly set.

To run both strategies against the same matrix and compare the current outputs
in one command, use the paired runner. Add `--commit --save-report
--save-pair-report` when the run should create durable benchmark and pair
comparison evidence in Postgres.

```bash
NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-benchmark-strategy-pair \
    --schedule-name local-adverse-odds-value-pair \
    --cadence once \
    --run-at-utc 2026-05-12T00:00:00Z \
    --pass-types 2x1,4x1 \
    --modes multiple \
    --budgets 10 \
    --competition-id BENCH_V3 \
    --model-version poisson-v3.1-baseline \
    --baseline-strategy accuracy_first \
    --candidate-strategy value_first \
    --commit \
    --save-report \
    --save-pair-report \
    --min-roi-delta 0 \
    --min-final-hit-sample-size 4
```

Recent saved pair comparison reports can be read through the admin API:

```bash
curl "http://localhost:8000/api/v1/recommendations/benchmark-strategy-pairs?baseline_strategy=accuracy_first&candidate_strategy=value_first&limit=10" \
  -H "X-Nutmeg-Admin-Token: $NUTMEG_ADMIN_API_TOKEN"
```

The global best endpoint now applies a dedicated final answer arbitrator before
returning `answer` and `alternatives`. The arbitrator compares eligible 1x1,
2x1-8x1, single/multiple, handicap, and correct-score options by expected
value, hit probability, risk, data quality, budget efficiency, and fixture
depth. It records an internal `final_answer_arbitration` payload for audit, but
does not expose strategy selection details to the ordinary user path.
The internal arbitration payload also records whether the selected 2x1-8x1
answer is a dynamic mixed-market answer, which market types are present, and
how many fixtures contain multiple-choice legs, so regression tests can catch
any accidental return to single-market recommendation silos.
Historical recommendation backtests carry the same audit into `summary_json`,
and `nutmeg-recommendation-historical-suite-quality-gate` can enforce minimum
candidate counts or rates for dynamic mixed-market, handicap, correct-score,
and multiple-choice final answers.
Persisted benchmark quality gates and benchmark cycles pass through the same
historical-suite metrics under `historical_suite_*` keys and expose optional
thresholds for dynamic mixed-market, handicap, correct-score, and multiple-choice
final answers. The default thresholds remain non-blocking until the historical
window has enough non-1X2 market coverage.

`POST /recommendations/generate` and `POST /recommendations/global-best` also
return an `answer_set` envelope for the public path. It keeps one primary
answer plus at most two distinct, budget-safe backups. Internal planner,
strategy, upset-policy, and arbitration diagnostics stay in audit/replay
payloads instead of the ordinary recommendation response.

The dashboard and parlay pages now render that public envelope directly. The
default screen shows the current answer, budget, unit amount, pass structure,
selected legs, risk, data quality, model version, prediction time, selected-leg
upset notices, and necessary backups. Candidate pools and parameter controls
are available behind disclosures so the ordinary path stays answer-first.

When a multiple-selection parlay exceeds `max_budget`, the optimizer now runs a
budget-constrained quality search before falling back to greedy projection for
very large candidate sets. The pruning payload records original/optimized stake,
atomic bet counts, quality score delta, and removed option diagnostics so future
backtests can judge whether budget trimming helped or hurt accuracy.

For larger 2x1-8x1 candidate pools, the recommendation path also runs an
internal integer-style solver. Small matrices are searched exactly; larger
matrices use budget-bucketed dynamic programming to keep strong fixture
combinations that a plain beam search can discard too early. The solver output
stays in internal explanation payloads and is not shown as a user-facing
strategy label.

The solver quality function is calibration-aware. It penalizes combinations
made from low-calibration longshots and fragile favorites, so the default
accuracy-first path will not replace a steadier answer purely because a rare
upset combination has a large payout.

Calibrated upset exposure is handled as the matching positive path. A draw or
underdog candidate can reduce its longshot penalty only when probability,
calibration, data quality, model confidence, odds stability, and volatility
thresholds are all acceptable. This keeps cold-match capture available without
turning the optimizer into a payout chaser.

Upset signals are now interpreted before they influence the recommendation
score. A draw or underdog-side signal can add protection quality, while a
favorite with high fragility is treated as an avoidance penalty. The public
answer stays simple; the internal payload records only the diagnostic scores
needed for replay and backtesting.

Historical recommendation backtests can run against frozen local slices without
touching provider APIs. The sample below uses real Euro 2024 knockout results
with local frozen odds/probability inputs, then reports final-hit, ROI,
calibration, Brier/log-loss, and upset-capture metrics:

```bash
uv run nutmeg-recommendation-historical-backtest \
  configs/recommendations/historical_slices/euro_2024_knockout_sample.json \
  --pass-types 1x1,2x1,3x1 \
  --modes single,multiple \
  --max-budget 8
```

To compare the current solver-backed optimizer against the heuristic baseline
on the same frozen slice, add `--compare-solver`:

```bash
uv run nutmeg-recommendation-historical-backtest \
  configs/recommendations/historical_slices/euro_2024_knockout_sample.json \
  --pass-types 2x1,3x1,4x1 \
  --modes single,multiple \
  --max-budget 8 \
  --compare-solver
```

The comparison output reports final-hit, ROI, profit/loss, Brier, log-loss,
calibration, and upset-capture deltas. This is an internal accuracy loop tool;
it does not change the ordinary user-facing answer copy.

Multiple frozen slices can be evaluated as one aggregate gate by passing more
than one slice path or adding `--suite`. Suite mode runs the heuristic baseline
and solver candidate on every slice, then reports aggregate final-hit, ROI,
profit/loss, Brier/log-loss, calibration, upset-capture, final-answer-change,
and solver-selected counts:

```bash
uv run nutmeg-recommendation-historical-backtest \
  configs/recommendations/historical_slices/euro_2024_knockout_sample.json \
  configs/recommendations/historical_slices/euro_2024_knockout_sample.json \
  --pass-types 2x1,3x1,4x1 \
  --modes single,multiple \
  --max-budget 8 \
  --suite
```

For a hard pass/fail gate over that same historical suite, use the dedicated
suite gate command. By default it blocks mixed/regressed suite status and
final-hit, Brier, log-loss, or calibration regressions; stricter runs can
require solver influence or final-answer changes:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  configs/recommendations/historical_slices/euro_2024_knockout_sample.json \
  --pass-types 2x1,3x1,4x1 \
  --modes single,multiple \
  --max-budget 8 \
  --min-final-hit-sample-size 1 \
  --min-final-hit-rate-delta 0 \
  --max-brier-score-delta 0 \
  --max-log-loss-delta 0 \
  --max-mean-calibration-error-delta 0
```

The process exits non-zero when the gate fails unless `--no-fail-process` is
set. This is intended for internal accuracy checks, not user-facing copy.

Historical suites can also be registered as manifests under
`configs/recommendations/historical_suites/`. The manifest keeps slice paths
and metadata together so CI or local checks do not need long positional path
lists:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/euro_2024_knockout_suite.json \
  --pass-types 2x1,3x1,4x1 \
  --modes single,multiple \
  --max-budget 8 \
  --min-final-hit-sample-size 1 \
  --no-fail-process
```

The default Euro 2024 manifest remains a stable knockout baseline. A separate
upset-pressure suite is available for stress testing favorite fragility and
calibration tradeoffs. It uses public Euro 2024 group-stage results with local
frozen probability/odds inputs. The default gate now expects the solver-backed
path to reject uncalibrated longshot overrides; stricter runs that require
solver influence may still fail, which is useful when explicitly testing how
much cold-match exposure the optimizer is allowed to take:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json \
  --pass-types 2x1 \
  --modes single \
  --max-budget 4 \
  --min-final-hit-sample-size 1 \
  --no-fail-process
```

To expand the frozen historical sample set from public football-data.co.uk
season CSV files, use the dedicated importer. It reads local CSV files such as
`E0.csv`, selects a complete 1X2 odds triplet (`AvgC*`, `Avg*`, `MaxC*`,
`B365C*`, etc.), converts the odds into no-vig market-implied probabilities,
and writes standard Nutmeg `HistoricalRecommendationSlice` JSON:

```bash
uv run nutmeg-recommendation-football-data-co-uk-import \
  ~/Downloads/E0.csv ~/Downloads/SP1.csv \
  --output-dir /tmp/nutmeg_football_data_slices \
  --competition-id EPL \
  --as-of-time-utc 2023-08-10T12:00:00Z \
  --season 2023-2024 \
  --slice-id-prefix fdcuk \
  --manifest-path configs/recommendations/historical_suites/euro_2024_knockout_suite.json \
  --manifest-tag football-data-co-uk \
  --manifest-note "Local historical CSV import dry-run"
```

Manifest refresh is a dry-run unless `--write-manifest` is supplied. These
imports are for repeatable backtest sample expansion; they do not call live
provider APIs and do not represent a production prediction model by themselves.
Worldwide files such as Japan `JPN.csv` use `Home`/`Away`/`HG`/`AG`/`Res`
instead of `HomeTeam`/`AwayTeam`/`FTHG`/`FTAG`/`FTR`; the importer accepts both
shapes. Use `--source-season` to filter a combined multi-year file into one
season slice:

```bash
uv run nutmeg-recommendation-football-data-co-uk-import \
  /tmp/football_data_co_uk/JPN.csv \
  --output-dir /tmp/nutmeg_football_data_slices \
  --competition-id JPN_J1 \
  --as-of-time-utc 2025-01-01T00:00:00Z \
  --season 2025 \
  --source-season 2025
```

The first real historical suite lives at
`configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json`.
It contains 30 completed-season slices: EPL, La Liga, Bundesliga, Serie A,
Ligue 1, and Japan J1, five seasons each. Re-run the coverage gate with:

```bash
uv run nutmeg-recommendation-historical-sample-quality \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --min-fixture-count 300 \
  --require-market-probability \
  --min-data-quality-score 80
```

The expanded A-league market-feature suite lives at
`configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_market_feature_suite.json`.
It covers Eredivisie, Primeira Liga, Championship, 2. Bundesliga, Serie B,
Segunda Division, and Ligue 2 from 2020-2021 through 2024-2025. The frozen
source CSV files are under `data/historical_sources/football_data_co_uk/europe`;
the generated suite has 35 slices and 2,520 fixtures with opening-to-closing 1X2
odds movement. The first shadow holdout report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_market_feature_holdout_parameter_learning_v1.json`;
it improves Brier/log-loss slightly but keeps the feature weights shadow-only
because hit rate is flat and ECE regresses.

Before a newly expanded competition suite enters the default recommendation path
or model training pool, run the competition admission gate. It consumes the
final-answer gate, feature holdout, and coverage audit artifacts and produces a
single backend decision:

```bash
uv run nutmeg-recommendation-competition-admission-gate \
  --final-answer-gate-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_candidate48_window4_1x1_to_8x1_admission_gate_v1.json \
  --feature-learning-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_market_feature_holdout_parameter_learning_v1.json \
  --coverage-audit-report configs/recommendations/historical_reports/historical_sample_coverage_audit_v4.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_competition_admission_gate_v1.json \
  --gate-id expanded-a-leagues-admission-v3.1 \
  --min-final-hit-sample-size 35 \
  --min-final-hit-rate 0.55 \
  --min-roi -0.30 \
  --min-competition-roi -0.50 \
  --no-fail-process
```

The first expanded A-league admission report has
`report_key=competition_admission_gate:6d4325ae733b1d76` and decision
`shadow_only`: production recommendations and training-pool admission are
blocked, while research/shadow evaluation remains allowed. The final-answer
sample size is sufficient at 35, but hit rate is only `0.42857142857142855`,
final-hit delta is `-0.11428571428571427`, ROI delta is
`-0.32571428571428573`, and the worst competition ROI is `-1.0` for Ligue 2.

The expanded A-league suite also has a shadow-only competition profile evidence
report at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_candidate48_window4_competition_profile_evidence_v1.json`
with `report_key=historical_competition_profile_evidence:53e6f730f5617dbe`.
It compares `1x1` through `8x1` single/multiple scenarios against the current
final answer for each expanded league. The report returns `accepted_count=0`,
`retained_count=7`, and no accepted profile adjustments, so
`configs/recommendations/competition_recommendation_profiles.json` must remain
unchanged for these leagues. Negative baseline ROI remains in Segunda Division,
Ligue 2, Serie B, and Primeira Liga. The report now records aggregated warning
counts in `summary_json.warning_counts`; all 476 warnings are
`insufficient_distinct_fixture_candidates`, confirming that this suite is still
too thin for robust long-parlay profile promotion even though it remains useful
for shadow research.

To increase the final-answer sample size without fetching new data, generate
rolling-window slices from the frozen expanded A-league market-feature suite:

```bash
uv run nutmeg-recommendation-historical-slice-window \
  --input-suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_market_feature_suite.json \
  --output-dir configs/recommendations/historical_slices/enriched_features/football_data_co_uk_expanded_a_leagues_rolling_windows \
  --suite-manifest-output-path configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --report-output-path configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_generation_v1.json \
  --suite-id football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1 \
  --suite-name "Football-Data.co.uk expanded A-league rolling-window suite" \
  --window-fixture-count 12 \
  --stride-fixture-count 12 \
  --min-fixture-count 8
```

The first rolling-window generation report has
`report_key=historical_slice_windowing:f6b57960e7ad63fd` and produces 210
slices / 2,520 fixture exposures, with 30 windowed final-answer samples for each
expanded league. The matching sample-quality report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_sample_quality_v1.json`
and passes with 210/210 slices. A bounded top-1 candidate final-answer gate is
stored at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate8_top1_final_answer_gate_v1.json`;
it passes with `candidate_final_hit_sample_size=210`,
`candidate_final_hit_rate=0.6142857142857143`, `candidate_roi=-0.07852380952380954`,
and worst competition ROI `-0.21166666666666673` for Serie B. The fuller
candidate12/window4 solver-backed lane is now also runnable after optimizer
state caching, lightweight exact-search scoring, and a lower exact-search state
cutoff. Its report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_final_answer_gate_v1.json`
with `gate_key=historical_recommendation_suite_quality_gate:3e1861f6211b860a`;
it passes with `candidate_final_hit_sample_size=210`,
`candidate_final_hit_rate=0.6476190476190476`,
`candidate_roi=-0.051904761904761905`, and worst competition ROI
`-0.1586666666666666` for Serie B.

Rolling-window competition profile evidence is stored at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate8_top1_competition_profile_evidence_v1.json`
with `report_key=historical_competition_profile_evidence:18e2fc047101db25`.
It returns `accepted_count=0`, `retained_count=7`, and `warning_count=0`; every
expanded league still retains the current final answer profile. The fuller
candidate12/window4 evidence report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_evidence_v1.json`
with `report_key=historical_competition_profile_evidence:c4109a3055614571`.
It accepts two shadow profile candidates: Segunda Division and Serie B both move
to `2x1:multiple` under the evidence lane, while the other five expanded leagues
retain the current final answer. The rolling admission gate report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_competition_admission_gate_v1.json`
with `report_key=competition_admission_gate:ee598bb519d15f3a` and decision
`shadow_only`. Final-answer metrics pass, but `--block-feature-regression`
keeps production recommendations and training-pool admission disabled because
the feature holdout still regresses expected calibration error. The
candidate12/window4 admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_admission_gate_v1.json`
with `report_key=competition_admission_gate:4a230feb19e97e78`; it remains
`shadow_only` for the same feature ECE warning even though final-answer blockers
are clear. To convert accepted profile evidence into a governed proposal without
touching the default profile config, run:

```bash
uv run nutmeg-recommendation-competition-profile-proposal \
  --profile-evidence-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_evidence_v1.json \
  --admission-gate-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_admission_gate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_proposal_v1.json \
  --profile-version v3_1_expanded_a_leagues_candidate12_window4_shadow_profiles_v1 \
  --min-historical-final-hit-sample-size 30 \
  --no-fail-process
```

The proposal report has
`report_key=competition_profile_proposal:0d3a35495cf9c9db`,
`status=shadow_only`, and `proposal_count=2`. It keeps
`production_recommendation_allowed=false`, so these profile candidates remain
internal research evidence until the admission gate clears the feature ECE
blocker.

Prematch feature parameter learning now has calibration guards for both training
selection and holdout validation:
`--max-training-expected-calibration-error-delta` and
`--max-validation-expected-calibration-error-delta`. Candidates that improve the
selected metric but regress ECE are blocked during training selection; if a
selected adjustment regresses ECE on the holdout, the learner falls back to the
no-op profile for that competition instead of promoting a harmful feature
weight. The guarded expanded A-league report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_market_feature_holdout_parameter_learning_ece_guard_v1.json`
with `report_key=historical_prematch_feature_parameter_learning:94b22195f077af56`.
It keeps all 7 competitions learned, validates on 504 fixtures, improves Brier
by `-0.00043080713012932925`, log loss by `-0.0005125302118312858`, hit rate by
`+0.005952380952381042`, and improves ECE by `-0.0031896046210417237`.
Championship and Primeira Liga fall back to no-op because their candidate
feature weights regressed holdout calibration.

Using the ECE-guarded feature report, the candidate12/window4 expanded A-league
admission gate is now accepted:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_admission_gate_ece_guard_v1.json`
has `report_key=competition_admission_gate:afc9cc5485cd3bf5`,
`production_recommendation_allowed=true`, `training_pool_allowed=true`, no
blockers, and no warnings. The corresponding governed profile proposal is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_proposal_ece_guard_v1.json`
with `report_key=competition_profile_proposal:cdd2826dcb49a81a`,
`status=production_ready`, and two accepted profile adjustments:
Segunda Division and Serie B move to `2x1:multiple`. The default profile config
is not changed by this proposal artifact.

To promote a production-ready proposal into the default internal profile set,
use the guarded promotion CLI:

```bash
uv run nutmeg-recommendation-competition-profile-promote \
  --current-profile-path configs/recommendations/competition_recommendation_profiles.json \
  --profile-proposal-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_proposal_ece_guard_v1.json \
  --profile-output-path configs/recommendations/competition_recommendation_profiles.json \
  --report-output-path configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_promotion_ece_guard_v1.json \
  --promoted-profile-version v3_1_competition_profiles_football_data_co_uk_2026_05_15_ece_guard_expanded_a_leagues_v1
```

The promotion report has
`report_key=competition_profile_promotion:5fd04151b08005c1`,
`status=promoted`, no blockers, and no warnings. The default profile set now has
6 internal profiles and includes the production-admitted expanded A-league
adjustments for Segunda Division and Serie B. A post-promotion default-path
candidate12/window4 gate is stored at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_post_profile_promotion_final_answer_gate_v1.json`
with `gate_key=historical_recommendation_suite_quality_gate:4a47eab0e94a352d`;
it passes with `candidate_final_hit_rate=0.6904761904761905`,
`candidate_roi=0.024854310344827577`, `candidate_profit_loss=17.298599999999993`,
and no warnings. The matching post-promotion admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_post_profile_promotion_competition_admission_gate_v1.json`
with `report_key=competition_admission_gate:f2df755c3c3f93b5` and remains
`accepted` with production recommendations and the training pool allowed.

After the expanded A-league promotion, the default recommendation path was
rebalanced to keep upset signals diagnostic-only. The global planner,
budget-constrained optimizer, and final-answer arbitrator no longer give a
positive score boost for `upset_quality`; that signal remains in payloads for
backend review, while the score weight moves back to hit probability, ROI, and
candidate quality. The core-first gate is stored at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_first_final_answer_gate_v1.json`.
It passes with `candidate_final_hit_rate=0.6952380952380952`,
`candidate_roi=-0.0022417391304347836`, `candidate_profit_loss=-1.5468000000000006`,
`final_hit_rate_delta=0.023809523809523836`, `roi_delta=0.016747517067912325`,
and no warnings. The matching admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_first_competition_admission_gate_v1.json`
with `report_key=competition_admission_gate:be825211fc4fea4f`; it remains
`accepted`. This keeps the product direction accuracy-first while leaving ROI
stability as the next core tuning target.

A follow-up core ROI rebalance keeps upset signals diagnostic-only and shifts
the final-answer hit-probability/ROI weights from `0.18`/`0.23` to
`0.15`/`0.26`. The accepted report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_roi_rebalanced_final_answer_gate_v1.json`;
it preserves `candidate_final_hit_rate=0.6952380952380952` while improving
`candidate_roi` to `-0.0003745454545454577` and `candidate_profit_loss` to
`-0.24720000000000208`, with `roi_delta=0.012878844375963018`,
`profit_loss_delta=9.136199999999999`, and no warnings. A harder negative ROI
penalty and a stronger global ROI shift did not pass the same historical gate,
so neither was retained. The matching admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_roi_rebalanced_competition_admission_gate_v1.json`
with `report_key=competition_admission_gate:215cd8c26f83c1a9`; it remains
`accepted`.

The next core-quality pass promotes a narrow, competition-scoped value guard
instead of changing global weights. `CompetitionRecommendationProfile` now
supports internal final-answer value guards, and the default Segunda Division
profile applies a small penalty only to low-probability, high-odds, clearly
negative-edge legs. This is not exposed as user-facing strategy text. The
production default-path gate is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_esp_segunda_value_guard_gate_v1.json`
with `gate_key=historical_recommendation_suite_quality_gate:e161c76fdf5df5ed`;
it passes with `candidate_final_hit_rate=0.6952380952380952`,
`candidate_roi=0.04383464052287581`, `candidate_profit_loss=26.8268`,
`ESP_SEGUNDA_DIVISION` ROI `0.07470694444444427`, and no warnings. This keeps
the V3.1-183 hit rate while moving realized ROI from near break-even to
positive on the same 210-slice suite.

A follow-up production value guard targets Championship only. Diagnostics showed
the drag came from medium-price, negative-edge Championship legs, so the default
profile now adds a narrow internal guard for probability `0.45-0.58`, odds
`1.75-2.20`, and model edge below `-0.02`. The production gate is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_eng_championship_value_guard_gate_v1.json`
with `gate_key=historical_recommendation_suite_quality_gate:a2f100868dc7444e`;
it preserves `candidate_final_hit_rate=0.6952380952380952`, lifts
`candidate_roi` to `0.049685760517799354`, and lifts `candidate_profit_loss` to
`30.7058`. Championship ROI improves from `-0.156` to
`-0.08304545454545446`. The matching admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_eng_championship_value_guard_competition_admission_gate_v1.json`
with `report_key=competition_admission_gate:34fcd1b659385665`; it is accepted
with no blockers or warnings.

The following Ligue 2 / 2. Bundesliga ablation did not promote a new production
guard. Current diagnostics show both leagues still have narrow medium-price
loss drivers, but the tested guards either leave the final answer unchanged or
trade away ROI. The best Ligue 2 accuracy-only variant raised final hit rate to
`0.7` but reduced ROI to `0.042357407407407406`, so it was not promoted under
the no-hit-regression and no-ROI-regression production rule. The relevant gate
artifacts are stored under
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ligue2_*_value_guard_*.json`
and
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ger_2_bundesliga_*_value_guard_*.json`.

The follow-up candidate replacement audit uses the same marginal contribution
engine through the clearer alias `nutmeg-recommendation-candidate-replacement-audit`.
For `FRA_LIGUE_2` and `GER_2_BUNDESLIGA`, it focuses only on missed final-answer
legs with probability `<0.55`, odds `1.75-2.30`, and model edge `<-0.02`:

```bash
uv run nutmeg-recommendation-candidate-replacement-audit \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ger_loss_driver_candidate_replacement_audit_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 4 \
  --scenario-candidate-fixture-buffer 4 \
  --focus-competitions FRA_LIGUE_2,GER_2_BUNDESLIGA \
  --max-replacement-candidates-per-leg 8 \
  --target-probability-max 0.55 \
  --target-min-decimal-odds 1.75 \
  --target-max-decimal-odds 2.30 \
  --target-max-model-edge -0.02 \
  --missed-legs-only
```

The report has `report_key=historical_candidate_marginal_audit:980bf20d81542c6f`.
It examines 60 final answers, finds 7 targeted missed legs, and simulates 56
replacement candidates. All 7 had hindsight replacement opportunities, but the
model-top replacement improved actual profit/loss only 2 times and had average
hit-probability delta `-0.02910240956504262`. This keeps the finding in the
diagnostic lane: replacement candidates exist, but the scorer does not yet rank
them reliably enough to promote an automatic replacement policy.

The follow-up reranker diagnostic compares each model-top replacement against
the hindsight actual-best replacement and reports the ranking bias directly:

```bash
uv run nutmeg-recommendation-replacement-reranker-diagnostics \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ger_loss_driver_candidate_replacement_audit_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ger_replacement_reranker_diagnostics_v1.json \
  --min-actual-best-profit-loss-delta 0 \
  --min-profit-loss-gap 0 \
  --max-report-items 50
```

The report has
`report_key=historical_replacement_reranker_diagnostics:249e538c1eb1a346`.
It evaluates 7 target bad-leg replacement opportunities. In all 7 cases the
actual-best replacement ranked below the model-top replacement; the average rank
gap is `5.142857142857143` and the average profit/loss gap is
`4.988571428571428`. The actual-best replacement is also lower probability in
all 7 cases, higher odds in all 7 cases, higher risk in all 7 cases, and lower
candidate score in 6 of 7 cases. This means the current replacement scorer is
still over-preferring safer/high-probability choices relative to realized
replacement upside. The finding remains hindsight-only evidence and does not
change the production profile.

The weight experiment turns that diagnosis into an offline pre-match reranker
test. It scores each replacement candidate only with visible pre-match fields
such as probability, odds, model edge, candidate score, replacement quality,
expected hit probability, expected ROI, risk score, and prior rank. Actual hit,
actual return, profit/loss delta, and hindsight decision fields are explicitly
excluded from scoring:

```bash
uv run nutmeg-recommendation-replacement-reranker-weight-experiment \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ger_loss_driver_candidate_replacement_audit_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ger_replacement_reranker_weight_experiment_v1.json \
  --min-actual-best-profit-loss-delta 0 \
  --min-profit-loss-gap 0 \
  --min-evaluated-item-count 5 \
  --max-hit-probability-regression-rate 0 \
  --min-average-profit-loss-delta-vs-model-top 0 \
  --max-report-items 80
```

The report has
`report_key=historical_replacement_reranker_weight_experiment:a82c7177db014c0b`.
It evaluates 7 eligible FRA/GER bad-leg opportunities across 5 profiles. The
accuracy-first watchlist profile is `quality_edge_blend_v1`: it improves 1 of 7
items versus the current model-top replacement, harms 0 of 7, raises simulated
actual-hit count from 2 to 3, and improves average profit/loss delta versus
model-top by `0.5599999999999999`. It is not promoted because 1 of 7 items has a
hit-probability regression. The more aggressive `odds_tempered_value_v1` has the
largest average profit/loss gain (`2.6028571428571428`) but regresses hit
probability in all 7 items and harms 1 item versus model-top, so it remains a
negative control rather than a production candidate.

The strict hit-probability guard run applies the same experiment to the larger
five-season marginal audit and filters each profile candidate unless its
expected hit probability is at least the current model-top replacement:

```bash
uv run nutmeg-recommendation-replacement-reranker-weight-experiment \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_reranker_weight_experiment_hit_guard_v1.json \
  --min-actual-best-profit-loss-delta 0 \
  --min-profit-loss-gap 0 \
  --min-candidate-hit-probability-delta-vs-model-top 0 \
  --min-evaluated-item-count 30 \
  --max-hit-probability-regression-rate 0 \
  --min-average-profit-loss-delta-vs-model-top 0 \
  --max-report-items 160
```

The report has
`report_key=historical_replacement_reranker_weight_experiment:c0c3ad5e8e29696d`.
It evaluates 72 eligible replacement opportunities across 5 profiles and
filters 876 candidates through the per-item hit-probability guard. Every
non-baseline profile falls back to the current model-top replacement on all 72
items, so `best_profile_id` is `null` and all experimental profiles are
rejected. This is an important negative result: under a strict no-hit-probability
regression rule, the current candidate pool does not provide enough alternative
replacements for a safer reranker promotion.

The tolerance grid then tests small per-item expected hit-probability deficits
without changing the production profile:

```bash
uv run nutmeg-recommendation-replacement-reranker-tolerance-grid \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_reranker_tolerance_grid_v1.json \
  --hit-probability-delta-thresholds 0,-0.005,-0.01,-0.02 \
  --min-actual-best-profit-loss-delta 0 \
  --min-profit-loss-gap 0 \
  --min-evaluated-item-count 30 \
  --min-average-profit-loss-delta-vs-model-top 0 \
  --min-simulated-actual-hit-delta-vs-baseline 0 \
  --min-replacement-leg-actual-hit-delta-vs-baseline 0 \
  --max-harm-count-vs-model-top 0 \
  --max-report-items-per-experiment 160
```

The report has
`report_key=historical_replacement_reranker_tolerance_grid:5fcb781576e92c3d`.
It evaluates 20 threshold/profile candidates and promotes none. It finds 11
watchlist candidates: the `-0.005` and `-0.01` thresholds let several profiles
change 7 of 72 opportunities with no actual-hit regression and no harm, but the
average profit/loss improvement is only `0.002672753899999991` at `-0.005` and
`0.00329775389999999` at `-0.01`. The `edge_value_v1` profile at `-0.02`
regresses actual hits by 5 and harms 5 items, so the tolerance grid confirms
that wider hit-probability tolerance is not a safe production route.

The combined core + expanded A-league replacement audit broadens that question
to the current medium-price negative-edge loss-driver segment. The audit CLI
now accepts repeated `--suite-manifest` arguments, so the same target filter can
run over the 240-slice combined holdout:

```bash
uv run nutmeg-recommendation-candidate-replacement-audit \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --max-replacement-candidates-per-leg 5 \
  --target-probability-min 0.45 \
  --target-probability-max 0.65 \
  --target-min-decimal-odds 1.60 \
  --target-max-decimal-odds 2.30 \
  --target-max-model-edge -0.02 \
  --missed-legs-only
```

The report has `report_key=historical_candidate_marginal_audit:72a403b5062990d7`.
It covers 240 final answers across 13 competitions and identifies 67 targeted
missed selected legs. Those legs produce 150 replacement simulations, 29
hindsight replacement opportunities, and 30 current model-top replacements. The
current model-top replacement improves actual profit/loss in 12 cases, harms 0
cases, and has `average_model_top_profit_loss_delta=1.556`; the average
hindsight-best profit/loss delta is much larger at `4.4446666666666665`. This
means replacement opportunities are real, but the ranking is leaving value on
the table.

The corresponding combined reranker diagnostic is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_diagnostics_v1.json`
with `report_key=historical_replacement_reranker_diagnostics:370bc72b9f66d048`.
It evaluates 27 replacement opportunities and finds that the actual-best
replacement is ranked below the model-top replacement in 26 of them. The average
profit/loss gap is `3.2096296296296294`; the actual-best candidate is generally
lower probability (`average_probability_gap=-0.07498851947570966`), higher odds
(`average_decimal_odds_gap=0.39518518518518525`), and higher risk. The largest
sample groups are `FRA_LIGUE_2` with 10 items and `ENG_CHAMPIONSHIP` with 7.

The combined tolerance grid is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_tolerance_grid_v1.json`
with `report_key=historical_replacement_reranker_tolerance_grid:f67b02ee584c14bf`.
It promotes no profile candidates, but it creates 12 watchlist candidates. At a
`-0.02` per-item expected hit-probability tolerance, several profiles improve 4
of 27 items versus model-top, harm 0, raise simulated actual-hit count from 10
to 11, and improve average profit/loss versus model-top by
`0.15185185185185185`. This is not production-ready, but it gives the next
non-ITA_SERIE_B direction: build a stricter, segment-scoped replacement reranker
gate around controlled hit-probability tolerance rather than another broad
penalty.

The follow-up controlled shadow gate converts that watchlist into a final-answer
level hard gate without changing the production profile:

```bash
uv run nutmeg-recommendation-replacement-reranker-shadow-gate \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json \
  --tolerance-grid-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_tolerance_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_shadow_gate_quality_edge_v1.json \
  --enable-shadow-gate \
  --profile-id quality_edge_blend_v1 \
  --hit-probability-delta-threshold -0.02 \
  --min-final-answer-count 20 \
  --min-changed-from-model-top-count 4 \
  --min-final-answer-hit-delta-vs-model-top 0 \
  --min-replacement-leg-hit-delta-vs-model-top 0 \
  --min-profit-loss-delta-vs-model-top 0 \
  --min-roi-delta-vs-model-top 0 \
  --max-harm-count-vs-model-top 0 \
  --min-average-hit-probability-delta-vs-model-top -0.02 \
  --max-report-items 120
```

The report has
`report_key=historical_replacement_reranker_shadow_gate:02fc9b2156cc8b88` and
`status=shadow_gate_passed`. It evaluates 27 targeted final answers from the
combined replacement audit, reranks 5 away from the current model-top
replacement, moves final-answer hits from 10 to 11, improves profit/loss versus
model-top by `4.1`, improves ROI by `0.07592592592592592`, and records
`harm_count_vs_model_top=0`. The source tolerance candidate is
`quality_edge_blend_v1:hit_probability_delta>=-0.02` with status `watchlist`.
This remains a diagnostic/shadow artifact because the source audit is a
missed-leg loss-driver surface; it does not change production recommendations or
public responses.

The rolling/competition admission step reruns the same shadow gate across
competition, season, and rolling-window folds:

```bash
uv run nutmeg-recommendation-replacement-reranker-shadow-admission \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json \
  --tolerance-grid-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_tolerance_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_shadow_admission_quality_edge_v1.json \
  --profile-id quality_edge_blend_v1 \
  --hit-probability-delta-threshold -0.02 \
  --min-overall-final-answer-count 20 \
  --min-overall-changed-from-model-top-count 4 \
  --min-overall-final-answer-hit-delta-vs-model-top 0 \
  --min-overall-replacement-leg-hit-delta-vs-model-top 0 \
  --min-overall-profit-loss-delta-vs-model-top 0 \
  --min-overall-roi-delta-vs-model-top 0 \
  --max-overall-harm-count-vs-model-top 0 \
  --min-overall-average-hit-probability-delta-vs-model-top -0.02 \
  --min-fold-final-answer-count 1 \
  --min-fold-changed-from-model-top-count 1 \
  --min-fold-final-answer-hit-delta-vs-model-top 0 \
  --min-fold-replacement-leg-hit-delta-vs-model-top 0 \
  --min-fold-profit-loss-delta-vs-model-top 0 \
  --min-fold-roi-delta-vs-model-top 0 \
  --max-fold-harm-count-vs-model-top 0 \
  --min-fold-average-hit-probability-delta-vs-model-top -0.025 \
  --min-active-competition-fold-count 2 \
  --min-active-season-fold-count 3 \
  --min-active-rolling-fold-count 2 \
  --rolling-window-slice-count 8 \
  --rolling-window-step 4 \
  --max-failed-fold-count 0 \
  --max-report-folds 160
```

The report has
`report_key=historical_replacement_reranker_shadow_admission:4fa36ac7a44baf41`
and `status=accepted`. It keeps the same overall shadow result
(`27` final answers, `5` changed from model-top, hit delta `+1`, profit/loss
delta `+4.1`, ROI delta `+0.07592592592592592`, harm `0`) and validates it with
`2` active competition folds, `3` active season folds, `6` active rolling folds,
and `failed_fold_count=0`. This is strong enough to preserve the profile as a
runtime-profile candidate artifact, but not enough to write it into the default
production profile because the trigger surface is still the missed-leg audit.

The scoped competition admission variant keeps the same missed-leg diagnostic
surface but restricts the evidence to the two competitions where active
competition folds actually passed:

```bash
uv run nutmeg-recommendation-replacement-reranker-shadow-admission \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json \
  --tolerance-grid-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_tolerance_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_scoped_competition_admission_quality_edge_v1.json \
  --profile-id quality_edge_blend_v1 \
  --hit-probability-delta-threshold -0.02 \
  --scope-competition-ids ENG_CHAMPIONSHIP,FRA_LIGUE_2 \
  --min-overall-final-answer-count 15 \
  --min-overall-changed-from-model-top-count 4 \
  --min-active-competition-fold-count 2 \
  --min-active-season-fold-count 2 \
  --min-active-rolling-fold-count 2 \
  --rolling-window-slice-count 6 \
  --rolling-window-step 3 \
  --max-failed-fold-count 0 \
  --max-report-folds 160
```

The report has
`report_key=historical_replacement_reranker_shadow_admission:5b0010f37937a30e`
and `status=accepted`. The scoped audit covers 19 items from
`ENG_CHAMPIONSHIP` and `FRA_LIGUE_2`; the resulting shadow gate evaluates 17
final answers, changes 5 model-top replacements, improves final-answer hits by
`+1`, improves profit/loss by `+4.1`, improves ROI by
`+0.12058823529411763`, and keeps `harm_count_vs_model_top=0`. It also passes
`2` active competition folds, `3` active season folds, `4` active rolling folds,
and records `failed_fold_count=0`. This does not expose an internal strategy to
users or promote the profile to production; it gives the backend governance
layer a tighter evidence window for any future runtime candidate review.

The same scoped competition admission now emits explicit no-harm counters for
model-top replacements. The explicit-harm report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_scoped_competition_admission_explicit_harm_guard_v1.json`
with `report_key=historical_replacement_reranker_shadow_admission:7c42370ef7dce5ec`.
It remains `accepted`, keeps the same 17 final answers and 5 changed model-top
replacements, improves hits by `+1`, profit/loss by `+4.1`, ROI by
`+0.12058823529411763`, and keeps `harm_count_vs_model_top=0`,
`overall_final_hit_harm_count_vs_model_top=0`, and
`overall_profit_loss_harm_count_vs_model_top=0`. The matching benchmark gate
smoke is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_benchmark_gate_explicit_harm_smoke_v1.json`;
the cycle smoke is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_benchmark_cycle_explicit_harm_smoke_v1.json`.
Both pass, with only the expected cycle bootstrap warnings when no current
benchmark report is saved. These reports are internal quality evidence only:
no default profile write, no public response change, no frontend surface, no
VPS/API dependency, and no automated betting behavior.

The pre-match replacement surface check removes the `--missed-legs-only`
condition and adds original-recommendation baseline guards to the shadow gate and
admission CLIs. This answers the stricter runtime question: can the reranker
operate on all eligible pre-match medium-price negative-edge legs without
hurting the answer the system would otherwise have given?

```bash
uv run nutmeg-recommendation-candidate-replacement-audit \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_audit_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --max-replacement-candidates-per-leg 5 \
  --target-probability-min 0.45 \
  --target-probability-max 0.65 \
  --target-min-decimal-odds 1.60 \
  --target-max-decimal-odds 2.30 \
  --target-max-model-edge -0.02
```

The pre-match surface audit has
`report_key=historical_candidate_marginal_audit:7d42d0accf5d702f`. It covers
240 final answers and 128 selected legs, including both hits and misses. The
current model-top replacement improves 25 cases but harms 23, with
`average_model_top_profit_loss_delta=-0.26567164179104474`, so this broader
surface is not safe by default.

The associated tolerance grid is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_tolerance_grid_v1.json`
with `report_key=historical_replacement_reranker_tolerance_grid:bf4edee83bfbcfb0`.
It promotes no production candidate and leaves 12 watchlist profiles.

The stricter pre-match shadow gate is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_shadow_gate_quality_edge_v1.json`
with `report_key=historical_replacement_reranker_shadow_gate:bed6f41f90788e80`.
It improves versus model-top replacement (`+4` final-answer hits and `+16.32`
profit/loss), but fails the original baseline: final-answer hit delta `-4`,
profit/loss delta `-5.539999999999999`, and
`harm_count_vs_original=19`.

The corresponding admission report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_shadow_admission_quality_edge_v1.json`
with `report_key=historical_replacement_reranker_shadow_admission:8a018cc726205159`.
It is `status=rejected`, `runtime_profile_candidate_allowed=false`, and
`shadow_allowed=false`; 18 active folds fail once the original recommendation
baseline is enforced. This closes the current pre-match promotion attempt: the
reranker remains useful diagnostic evidence, but it must not be enabled on the
runtime pre-match surface until a profile can beat both model-top and original
recommendations without harm.

The replacement reranker admission and periodic quality gate now also separate
the source surface from the score outcome. Admission reports emit
`source_surface_kind`, `source_surface_missed_legs_only`, and a nested
`source_surface` summary; benchmark gate and benchmark cycle can require this
with `--require-replacement-reranker-prematch-source-surface` and
`--gate-require-replacement-reranker-prematch-source-surface`. The source-surface
guard report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_shadow_admission_source_surface_guard_v1.json`
with `report_key=historical_replacement_reranker_shadow_admission:9d3a78550b962ccd`.
It proves the input is the full pre-match replacement surface
(`source_surface_kind=prematch_replacement_surface`,
`source_surface_missed_legs_only=false`, `selected_leg_count=128`) while still
rejecting runtime promotion because the original baseline remains harmed:
`overall_hit_delta_vs_original=-4`,
`overall_profit_loss_delta_vs_original=-5.539999999999999`,
`overall_final_hit_harm_count_vs_original=15`, and `failed_fold_count=18`. This
prevents a missed-leg diagnostic admission from being treated as production
candidate evidence.

## V3.1 Replacement Reranker Prematch Scope Search

The pre-match replacement reranker can now be tested across narrower competition
scopes before any runtime profile candidate is considered. The scope search reads
the full pre-match replacement audit and tolerance grid, runs the existing
shadow admission gate for each competition subset, and keeps the original
final-answer no-harm checks enabled. It is an internal evidence tool only; it
does not change default profiles or public recommendation responses.

CLI:

```bash
uv run nutmeg-recommendation-replacement-reranker-prematch-scope-search \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_audit_v1.json \
  --tolerance-grid-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_tolerance_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_replacement_reranker_scope_search_v1.json \
  --profile-id quality_edge_blend_v1 \
  --hit-probability-delta-threshold -0.02 \
  --min-scope-competition-count 1 \
  --max-scope-competition-count 3 \
  --min-overall-final-answer-count 8 \
  --min-overall-changed-from-model-top-count 2 \
  --min-active-season-fold-count 2 \
  --rolling-window-slice-count 4 \
  --rolling-window-step 2 \
  --max-failed-fold-count 0
```

Generated report:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_replacement_reranker_scope_search_v1.json`.
It produced
`report_key=replacement_reranker_prematch_scope_search:e40f39beac45055f`,
`status=no_admitted_scope`, `scope_candidate_count=26`,
`accepted_scope_count=0`, `shadow_only_scope_count=0`, and
`rejected_scope_count=26`.

The best near-miss scope was `ENG_CHAMPIONSHIP`: 12 shadow final answers,
2 changed from model-top, `overall_hit_delta_vs_original=+4`,
`overall_roi_delta_vs_original=+0.6975`, and
`overall_profit_loss_delta_vs_original=+16.74`. It still failed promotion
because original no-harm was violated (`overall_harm_count_vs_original=1`,
`overall_profit_loss_harm_count_vs_original=1`) and 4 folds failed. Across all
26 scopes the dominant blockers were original-baseline harm and failed folds,
so the current pre-match replacement reranker line should remain blocked rather
than narrowed into production.

The replacement calibration segment diagnostic then locates where the
hindsight-best replacement candidates are being under-ranked:

```bash
uv run nutmeg-recommendation-replacement-calibration-segments \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_calibration_segments_v1.json \
  --min-actual-best-profit-loss-delta 0 \
  --min-profit-loss-delta-vs-model-top 0 \
  --min-group-sample-size 3 \
  --min-average-profit-loss-delta-vs-model-top 0 \
  --max-average-hit-probability-delta-vs-model-top 0 \
  --min-simulated-actual-hit-delta-count-vs-model-top 0 \
  --min-replacement-leg-hit-delta-count-vs-model-top 0 \
  --max-report-groups 160 \
  --max-report-observations 80
```

The report has
`report_key=historical_replacement_calibration_segments:e069fa77943911fa`.
It evaluates 72 actual-best replacement observations and 49 segment groups.
The key finding is that the opportunity is not mainly in long-shot candidates:
71 of 72 observations are short-odds replacements with average probability
`0.8050430455446482`, average odds `1.1947887323943662`, average hit-probability
delta versus model-top `-0.01299728611241547`, and actual-hit delta `+23` versus
model-top. La Liga, EPL, Ligue 1, Serie A, Bundesliga, and J1 all show positive
actual-hit deltas in this short-odds under-ranking pattern. This points the next
work toward league/odds-band calibration of high-probability short-price
candidates, not toward relaxing long-shot value rules.

The short-odds shadow rerank experiment then tests that calibration hypothesis
without changing production recommendations:

```bash
uv run nutmeg-recommendation-replacement-short-odds-shadow-rerank \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_shadow_rerank_v1.json \
  --focus-competitions EPL,ESP_LA_LIGA,FRA_LIGUE_1,GER_BUNDESLIGA,ITA_SERIE_A \
  --min-candidate-hit-probability-delta-vs-model-top -0.015 \
  --max-candidate-hit-probability-delta-vs-model-top 0 \
  --min-replacement-probability 0.55 \
  --max-replacement-decimal-odds 1.75 \
  --min-decimal-odds-delta-vs-model-top 0 \
  --min-evaluated-item-count 30 \
  --max-report-items 80
```

The report has
`report_key=historical_short_odds_shadow_rerank:a6fe1f607f91c830`.
It evaluates 66 focused replacement opportunities and keeps
`production_recommendation_changed=false`. The strongest shadow profile,
`max_short_odds_within_deficit_v1`, changes 64 opportunities, improves actual
hits by `+16`, captures 41 hindsight-best replacements, and has average
profit/loss delta `+0.8762040286242423` versus model-top. It is still only a
watchlist profile because it has 5 harmful replacements and depends on a small
expected hit-probability deficit. EPL, Ligue 1, Serie A, and Bundesliga are
positive with no harm under this shadow rule; La Liga needs a separate guard
before any production gate should be attempted.

The per-competition gate readiness pass splits that shadow signal before any
production or final-answer gate change:

```bash
uv run nutmeg-recommendation-replacement-short-odds-competition-gate \
  --shadow-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_shadow_rerank_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_competition_gate_v1.json \
  --profile-ids max_short_odds_within_deficit_v1 \
  --min-evaluated-item-count 5 \
  --min-changed-count-vs-model-top 1 \
  --min-simulated-actual-hit-delta-count-vs-model-top 1 \
  --min-replacement-leg-hit-delta-count-vs-model-top 1 \
  --min-average-profit-loss-delta-vs-model-top 0 \
  --min-average-hit-probability-delta-vs-model-top -0.015 \
  --max-harm-count-vs-model-top 0 \
  --max-report-candidates 80
```

The report has
`report_key=historical_short_odds_competition_gate:3397bc2ff3258934`.
It marks EPL, Ligue 1, Serie A, and Bundesliga as `final_answer_gate_ready`
for the next offline gate, with combined hit delta `+15`, harm count `0`, and
average profit/loss delta `+0.9219471921672727`. La Liga is
`isolated_rejected` because its short-odds shadow corridor still has 5 harmful
replacements. This remains a no-production-change readiness artifact.

The final-answer shadow gate then rebuilds full short-odds shadow items from
the audit report and applies the ready-competition set only. It limits each
final answer to one replacement and keeps La Liga isolated:

```bash
uv run nutmeg-recommendation-replacement-short-odds-final-answer-gate \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --competition-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_competition_gate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_final_answer_gate_v1.json \
  --profile-id max_short_odds_within_deficit_v1 \
  --selection-rule highest_candidate_hit_probability \
  --min-changed-final-answer-count 5 \
  --min-final-answer-hit-delta-count-vs-original 0 \
  --min-profit-loss-delta-vs-original 0 \
  --min-average-hit-probability-delta-vs-original -0.02 \
  --max-harm-count-vs-original 0 \
  --min-replacement-probability 0.55 \
  --max-replacement-decimal-odds 1.75 \
  --min-candidate-hit-probability-delta-vs-model-top -0.015 \
  --max-candidate-hit-probability-delta-vs-model-top 0 \
  --min-decimal-odds-delta-vs-model-top 0 \
  --max-report-items 80
```

The report has
`report_key=historical_short_odds_final_answer_gate:03a2e45b6e358651`.
It is a `final_answer_shadow_candidate` with 16 changed final answers,
final-answer hit delta `+2`, profit/loss delta `+6.410503984`, and harm count
`0`. The average expected hit-probability delta is `-0.01697510863389533`, so
the next step must be a stricter holdout/suite gate before any production
profile promotion.

The suite gate then merges those 16 changed final answers back into the full
30-answer marginal audit suite. Unchanged answers remain baseline, so this is a
full-suite shadow check rather than a changed-only report:

```bash
uv run nutmeg-recommendation-replacement-short-odds-suite-gate \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --final-answer-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_final_answer_gate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_suite_gate_v1.json \
  --min-final-answer-count 30 \
  --min-changed-final-answer-count 5 \
  --min-final-answer-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --max-harm-count-vs-original 0 \
  --min-average-hit-probability-delta-vs-original -0.02 \
  --max-report-changed-items 80
```

The report has `report_key=historical_short_odds_suite_gate:93a0dc3ef86ec7da`
and passes all shadow gates. Across 30 final answers, the candidate improves
final-hit count from 20 to 22, hit rate from `0.6666666666666666` to
`0.7333333333333333`, profit/loss from `3.0106614248000034` to
`9.421165408800004`, and ROI from `0.05017769041333339` to
`0.15701942348000006`, with harm count `0`. This is still not a production
profile change; it is the evidence needed for a governed proposal step.

The governed production proposal step converts the passed shadow gates into an
auditable proposal artifact. It does not edit
`configs/recommendations/competition_recommendation_profiles.json`; a separate
promotion step is required before runtime behavior changes:

```bash
uv run nutmeg-recommendation-replacement-short-odds-production-proposal \
  --suite-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_suite_gate_v1.json \
  --final-answer-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_final_answer_gate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_v1.json \
  --min-final-answer-count 30 \
  --min-changed-final-answer-count 5 \
  --min-final-answer-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --max-harm-count-vs-original 0 \
  --min-average-hit-probability-delta-vs-original -0.02
```

The proposal report has
`report_key=historical_short_odds_production_proposal:e516991cb2166604` and
`status=production_proposal_ready`. It allows only EPL, Ligue 1, Bundesliga,
and Serie A, explicitly excludes La Liga, requires max one replacement per
final answer, keeps the short-odds guard at probability `>=0.55` and decimal
odds `<=1.75`, and records rollback conditions for any harm, hit-rate
regression, ROI regression, profit/loss regression, hit-probability tolerance
breach, isolated-competition leakage, or source-report mismatch. The proposal
keeps `production_recommendation_changed=false`.

Before any runtime promotion, run a smoke check against the current default
profile. This creates only an audit report and a temporary profile-set payload;
it does not write `configs/recommendations/competition_recommendation_profiles.json`:

```bash
uv run nutmeg-recommendation-replacement-short-odds-promotion-smoke \
  --current-profile-path configs/recommendations/competition_recommendation_profiles.json \
  --production-proposal-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_v1.json \
  --promoted-profile-version v3_1_short_odds_replacement_promotion_smoke_v1 \
  --min-allowed-competition-count 4 \
  --max-replacements-per-final-answer 1 \
  --min-replacement-probability 0.55 \
  --max-replacement-decimal-odds 1.75 \
  --min-average-hit-probability-delta-vs-original -0.02 \
  --max-harm-count-vs-original 0
```

The smoke report has
`report_key=historical_short_odds_promotion_smoke:d9bbc89fe4e355d2` and passes.
It validates the proposal status, source report key chain, no runtime profile
write, no public-response change, no user-facing strategy text, current profile
compatibility, allowed/excluded competition separation, short-odds constraints,
no-harm evidence, and rollback conditions. The temporary payload keeps the
existing seven default competition profiles unchanged and adds one internal
`short_odds_replacement_rules` entry for audit only.

The runtime shadow replay loader is the next stricter gate. It reads the
temporary `short_odds_replacement_rules` payload behind an explicit
`--enable-shadow-replay` flag and replays the rule using only runtime-style rule
constraints, not production writes:

```bash
uv run nutmeg-recommendation-replacement-short-odds-runtime-shadow-replay \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_v1.json \
  --enable-shadow-replay \
  --rule-ids short_odds_final_answer_replacement_v1 \
  --min-final-answer-count 30 \
  --min-changed-final-answer-count 5 \
  --min-final-answer-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --max-harm-count-vs-original 0 \
  --min-average-hit-probability-delta-vs-original -0.02 \
  --max-report-items 80
```

This stricter runtime-style replay currently fails:
`report_key=historical_short_odds_runtime_shadow_replay:bc73fc902f95cad3`,
`status=shadow_replay_failed`, final-answer hits move from 20 to 19, ROI moves
from `0.05017769041333339` to `0.016496010146666722`, profit/loss delta is
`-2.020900816`, and harm count is `1`. The harmful case is Ligue 1 2024-2025:
the shadow replacement changes a previously hit final answer into a miss. This
blocks runtime promotion even though production and public responses remain
unchanged. The next work should tighten the runtime guard rather than promote
the current rule.

The first tightened runtime guard adds a candidate-level floor against the
current final-answer hit probability before override arbitration. It is still a
shadow-only replay and does not write production profiles:

```bash
uv run nutmeg-recommendation-replacement-short-odds-runtime-shadow-replay \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_candidate_guard_v1.json \
  --enable-shadow-replay \
  --rule-ids short_odds_final_answer_replacement_v1 \
  --min-final-answer-count 30 \
  --min-changed-final-answer-count 5 \
  --min-final-answer-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --max-harm-count-vs-original 0 \
  --min-average-hit-probability-delta-vs-original -0.02 \
  --min-candidate-hit-probability-delta-vs-original -0.025
```

The guarded replay passes with
`report_key=historical_short_odds_runtime_shadow_replay:ade3aa8e4bfbc02b`:
30 final answers, 17 changed answers, hit count preserved at 20, ROI delta
`+0.017638871546666643`, profit/loss delta `+1.058332292799999`, harm count
`0`, and average hit-probability delta `-0.014697457992009506`. This is useful
evidence, but the default production profile is still unchanged.

The guarded production proposal chain now requires that runtime replay evidence
too. The proposal command accepts `--runtime-shadow-replay-report` and writes
the candidate-level guard into `constraints_json`:

```bash
uv run nutmeg-recommendation-replacement-short-odds-production-proposal \
  --suite-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_suite_gate_v1.json \
  --final-answer-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_final_answer_gate_v1.json \
  --runtime-shadow-replay-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_candidate_guard_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_candidate_guard_v1.json \
  --min-candidate-hit-probability-delta-vs-original -0.025
```

The guarded proposal passes with
`report_key=historical_short_odds_production_proposal:981893da164fc151`. The
follow-up promotion smoke also passes:
`historical_short_odds_promotion_smoke:25b74e16e1f785a9`. A final runtime
replay using that smoke artifact, without a CLI guard override, passes as
`historical_short_odds_runtime_shadow_replay:29fe012ab7b293a6`; the guard is
read from the temporary rule itself. Production and public responses remain
unchanged.

The guarded rule also has a rolling/holdout admission gate. It reruns the same
temporary rule over competition folds, season folds, and rolling windows:

```bash
uv run nutmeg-recommendation-replacement-short-odds-rolling-admission \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_candidate_guard_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_rolling_admission_candidate_guard_v1.json \
  --rule-ids short_odds_final_answer_replacement_v1 \
  --min-active-competition-fold-count 4 \
  --min-active-season-fold-count 5 \
  --min-active-rolling-fold-count 4 \
  --rolling-window-final-answer-count 12 \
  --rolling-window-step 6
```

This admission passes with
`report_key=historical_short_odds_rolling_admission:6ff5f39ad9130544`:
20 folds were evaluated, 13 were active, and 0 active folds failed. The active
coverage includes 4 competition folds, 5 season folds, and 4 rolling-window
folds. Overall hit count stays 20, ROI delta is `+0.017638871546666643`,
profit/loss delta is `+1.058332292799999`, and harm count remains `0`. The
report is still evidence only; no default production profile is written.

The rolling admission report is now part of the governed proposal and smoke
chain. The proposal accepts a `--rolling-admission-report` source and requires
accepted rolling evidence, zero failed active folds, and active competition,
season, and rolling-window coverage before it can be marked ready:

```bash
uv run nutmeg-recommendation-replacement-short-odds-production-proposal \
  --suite-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_suite_gate_v1.json \
  --final-answer-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_final_answer_gate_v1.json \
  --runtime-shadow-replay-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_promotion_candidate_guard_v1.json \
  --rolling-admission-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_rolling_admission_candidate_guard_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_rolling_admission_v1.json \
  --min-candidate-hit-probability-delta-vs-original -0.025 \
  --min-rolling-active-competition-fold-count 4 \
  --min-rolling-active-season-fold-count 5 \
  --min-rolling-active-rolling-fold-count 4
```

This proposal passes as
`historical_short_odds_production_proposal:f08a4fca608f2f00`; it carries
`rolling_admission=historical_short_odds_rolling_admission:6ff5f39ad9130544`
and `runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:29fe012ab7b293a6`
as source keys. The promotion smoke then passes as
`historical_short_odds_promotion_smoke:b56b086691698ecf` with no runtime profile
write, no public response change, and no production recommendation change. A
post-smoke runtime replay using that temporary payload passes as
`historical_short_odds_runtime_shadow_replay:7141915996a29cb6`: 30 final
answers, 17 changed answers, hit-rate delta `0`, ROI delta
`+0.017638871546666643`, profit/loss delta `+1.058332292799999`, and harm
count `0`.

The short-odds replacement evidence chain now separates final-hit harm from
profit/loss harm instead of relying only on the legacy compatibility
`harm_count_vs_original` field. The explicit-harm replay is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_explicit_harm_guard_v1.json`
with `report_key=historical_short_odds_runtime_shadow_replay:03efacfb60b79d89`;
it passes with 30 final answers, 17 changed answers, hit-rate delta `0`, ROI
delta `+0.017638871546666643`, profit/loss delta `+1.058332292799999`,
`harm_count_vs_original=0`, `final_hit_harm_count_vs_original=0`, and
`profit_loss_harm_count_vs_original=0`. The matching rolling admission report
is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_rolling_admission_explicit_harm_guard_v1.json`
with `report_key=historical_short_odds_rolling_admission:73ec1f43f192febe`;
it is accepted with 4 active competition folds, 5 active season folds, 4 active
rolling folds, zero failed folds, and the same three no-harm counts at `0`.
The governed production proposal
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_explicit_harm_guard_v1.json`
is `production_proposal_ready` as
`historical_short_odds_production_proposal:7d6a51fccc6f60d8`; it keeps
`ESP_LA_LIGA` excluded and does not write the default profile, change public
responses, or introduce automated betting behavior.

The final pre-promotion gate builds a candidate runtime profile artifact from
the governed proposal, rolling admission, promotion smoke, linked runtime
replay, and post-smoke runtime replay. It still does not write the default
profile:

```bash
uv run nutmeg-recommendation-replacement-short-odds-runtime-profile-promote \
  --current-profile-path configs/recommendations/competition_recommendation_profiles.json \
  --production-proposal-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_rolling_admission_v1.json \
  --promotion-smoke-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_rolling_admission_v1.json \
  --runtime-shadow-replay-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_promotion_candidate_guard_v1.json \
  --post-promotion-runtime-shadow-replay-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_rolling_admission_v1.json \
  --rolling-admission-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_rolling_admission_candidate_guard_v1.json \
  --profile-output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_candidate_v1.json \
  --report-output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_promotion_v1.json \
  --promoted-profile-version v3_1_short_odds_replacement_runtime_profile_candidate_v1
```

The gate passes as
`historical_short_odds_runtime_profile_promotion:a673be0bf1c52d82` with
`promotion_ready=true`, one internal `short_odds_replacement_rules` entry, and
no blockers. A direct runtime replay against the candidate profile itself also
passes as `historical_short_odds_runtime_shadow_replay:81b919a9034435cb`, with
the same 30 final answers, 17 changed answers, hit-rate delta `0`, ROI delta
`+0.017638871546666643`, profit/loss delta `+1.058332292799999`, and harm
count `0`.

The controlled activation gate turns that candidate into a separate activated
profile artifact without touching the default profile:

```bash
uv run nutmeg-recommendation-replacement-short-odds-runtime-profile-activate \
  --current-profile-path configs/recommendations/competition_recommendation_profiles.json \
  --candidate-runtime-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_candidate_v1.json \
  --runtime-profile-promotion-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_promotion_v1.json \
  --candidate-runtime-shadow-replay-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_runtime_profile_candidate_v1.json \
  --activated-profile-output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_v1.json \
  --report-output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_activation_v1.json \
  --activated-profile-version v3_1_competition_profiles_short_odds_runtime_enabled_candidate_v1
```

This passes as
`historical_short_odds_runtime_profile_activation:0599897930eec3cf` with
`activation_ready=true`, one internal short-odds replacement rule, all source
keys linked, and `default_profile_written=false`. A replay against the activated
artifact passes as `historical_short_odds_runtime_shadow_replay:8b865425230f1f07`:
30 final answers, 17 changed answers, hit-rate delta `0`, ROI delta
`+0.017638871546666643`, profit/loss delta `+1.058332292799999`, and harm
count `0`.

The switch/apply gate is the explicit handoff before any default-profile
write. By default it only stages the profile and emits an audit report:

```bash
uv run nutmeg-recommendation-replacement-short-odds-runtime-profile-switch \
  --current-profile-path configs/recommendations/competition_recommendation_profiles.json \
  --activated-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_v1.json \
  --activation-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_activation_v1.json \
  --activated-runtime-shadow-replay-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_activated_profile_candidate_v1.json \
  --staged-profile-output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_staged_v1.json \
  --report-output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_v1.json
```

This passes as `historical_short_odds_runtime_profile_switch:ad81a85d16cbb696`
with `switch_ready=true`, one internal short-odds replacement rule, no blockers,
and `default_profile_written=false`. A staged-profile replay also passes as
`historical_short_odds_runtime_shadow_replay:8b865425230f1f07`, with the same
30 final answers, 17 changed answers, hit-rate delta `0`, ROI delta
`+0.017638871546666643`, profit/loss delta `+1.058332292799999`, and harm
count `0`. Actual default-profile writes require both `--write-default-profile`
and `--confirm-default-profile-write`.

The persisted benchmark quality gate can require the same switch evidence,
including separate final-hit and profit/loss no-harm counters, so a scheduled
quality cycle can fail before any staged runtime profile drifts out of policy:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --allow-missing-history \
  --runtime-profile-switch-report-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_v1.json \
  --runtime-profile-switch-replay-report-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_switch_staged_v1.json \
  --require-runtime-profile-switch-gate \
  --min-runtime-profile-switch-rule-count 1 \
  --min-runtime-profile-switch-allowed-competition-count 4 \
  --min-runtime-profile-switch-final-answer-count 30 \
  --min-runtime-profile-switch-changed-final-answer-count 5 \
  --min-runtime-profile-switch-final-answer-hit-rate-delta 0 \
  --min-runtime-profile-switch-roi-delta 0 \
  --min-runtime-profile-switch-profit-loss-delta 0 \
  --max-runtime-profile-switch-harm-count-vs-original 0 \
  --max-runtime-profile-switch-final-hit-harm-count-vs-original 0 \
  --max-runtime-profile-switch-profit-loss-harm-count-vs-original 0 \
  --min-runtime-profile-switch-average-hit-probability-delta -0.02
```

The local bootstrap smoke, written to
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_benchmark_gate_smoke_v1.json`,
passes with `gate_key=recommendation_benchmark_quality_gate:all:any`,
`runtime_profile_switch_ready=true`,
`runtime_profile_switch_replay_passed=true`, `default_profile_written=false`,
and no failed checks. The only warning is the expected bootstrap warning for no
persisted benchmark history.

The explicit-harm promotion-to-cycle chain is stored as separate stage reports:
promotion smoke `historical_short_odds_promotion_smoke:f295bb3e0327d68d`,
runtime profile promotion `historical_short_odds_runtime_profile_promotion:38f936543f007a07`,
activation `historical_short_odds_runtime_profile_activation:926a919521159cf1`,
switch `historical_short_odds_runtime_profile_switch:044049ee150b67eb`, staged
replay `historical_short_odds_runtime_shadow_replay:404bc07376801595`,
benchmark gate `recommendation_benchmark_quality_gate:all:any`, and cycle
`recommendation_benchmark_cycle:explicit-harm-smoke:once:gate`. The staged
replay covers 30 final answers, changes 17, keeps ROI delta at
`+0.017638871546666643`, profit/loss delta at `+1.058332292799999`, and keeps
`harm_count_vs_original`, `final_hit_harm_count_vs_original`, and
`profit_loss_harm_count_vs_original` all at `0`. These reports remain internal
evidence only: no default profile write, no public response change, no frontend
surface, no VPS/API dependency, and no automated betting behavior.

For a lightweight recommendation-channel smoke over the same suite:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --pass-types 2x1 \
  --modes single \
  --max-budget 4 \
  --min-slice-count 30 \
  --min-comparison-count 30 \
  --min-final-hit-sample-size 30 \
  --max-warning-count 1
```

For league/season diagnostics, use the report builder. The first committed
report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_solver_single_2x1_diagnostics.json`;
it groups the 30-slice suite by overall, competition, season, and
competition+season:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_solver_single_2x1_diagnostics.json \
  --pass-types 2x1 \
  --modes single \
  --unit-stake 2 \
  --max-budget 4 \
  --min-data-quality-score 80
```

Large full-matrix diagnostics over `2x1` through `8x1` with `multiple` mode and
solver search should use both a bounded candidate pool and a per-scenario
fixture window. The routine lane below keeps the top 48 fixture pools globally,
at most 2 outcomes per fixture, and only opens each pass type to `leg_count + 4`
fixtures during scenario search:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_full_matrix_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4
```

This bounded matrix is a smoke/diagnostic lane, not a final model claim. With
the current accuracy guardrails, the matching suite gate passes without
regressing baseline hit rate, ROI, Brier, log loss, or calibration:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --min-slice-count 30 \
  --min-comparison-count 30 \
  --min-final-hit-sample-size 30 \
  --min-candidate-final-hit-rate 0.60 \
  --min-candidate-roi 0.0 \
  --min-competition-candidate-roi -0.30 \
  --max-warning-count 2
```

The latest run uses final-answer-only hit accounting: one settled final answer
per historical slice, with scenario-level hit data kept only as diagnostics. It
also applies the data-driven competition profile in
`configs/recommendations/competition_recommendation_profiles.json` for leagues
where the frozen five-season diagnostics support a different final-answer
shape. It reports `suite_status=unchanged`,
`candidate_final_hit_sample_size=30`,
`candidate_final_hit_rate=0.6666666666666666`,
`candidate_roi=0.05017769041333339`,
`candidate_profit_loss=3.0106614248000034`,
`candidate_brier_score=0.24445905503052764`,
`candidate_log_loss=0.683178240140196`,
`candidate_mean_calibration_error=0.47697612791196814`,
`failed_checks=[]`, and `warnings=[]`. That means the full 2x1-8x1 lane now
passes a 30-slice final-answer quality gate with both an absolute hit-rate floor
and an absolute ROI floor. The same gate also records per-competition ROI and
currently uses J1 as the weakest league guardrail at
`worst_competition_candidate_roi=-0.27603999999999995`. It also reports
correlation exposure diagnostics for repeated team/market exposures:
`correlated_final_answer_count=25` and
`max_final_answer_correlation_exposure=5`. Use
`--max-final-answer-correlation-exposure` only for explicit stress gates; it is
not enabled in the default lane because the first broad penalty experiment
reduced final-answer hit rate.

To audit whether league-specific final-answer profiles should change, run the
competition profile evidence report. It compares every `2x1` through `8x1`
single/multiple scenario against the current final answer for each league and
only recommends a replacement when hit count is preserved and ROI/P&L strictly
improve:

```bash
uv run nutmeg-recommendation-competition-profile-evidence \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_competition_profile_evidence.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4
```

The current report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_competition_profile_evidence.json`
with `report_key=historical_competition_profile_evidence:d05026a8233ec4cd`.
It returns `accepted_count=0` and `retained_count=6`, so the current
competition profile should not be changed from this evidence lane. It also
confirms the current negative baseline ROI leagues are `ESP_LA_LIGA`,
`GER_BUNDESLIGA`, and `JPN_J1`; J1's top ROI alternative is `6x1:single`, but
it is rejected because hit count would fall from 2/5 to 1/5.

To audit final-answer accuracy and ROI by recommendation segment before tuning,
run the final-answer segment audit. It groups only the actual final answer by
pass type, mode, scenario, leg count, odds band, hit-probability band,
competition, and market mix:

```bash
uv run nutmeg-recommendation-final-answer-segment-audit \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --min-segment-sample-size 3 \
  --top-segment-limit 12 \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_audit_v1.json
```

The current report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_audit_v1.json`
with `report_key=historical_final_answer_segment_audit:744d6c2cb24b6be3`.
It covers 30 final answers, reports overall hit rate
`0.7666666666666667`, and still shows negative ROI
`-0.0862312646666666`. The strongest loss-driver segments are short odds
`1.00-1.30`, `ESP_LA_LIGA`, `GER_BUNDESLIGA`, and `3x1:single`, which gives
the next tuning pass a precise target without changing production behavior.

The same audit can now optionally emit interaction segments and read multiple
suite manifests. This is useful for separating broad symptoms from precise
final-answer loss drivers, for example `competition + pass_type`,
`competition + odds_band`, and `pass_type + hit_probability_band`.

```bash
uv run nutmeg-recommendation-final-answer-segment-audit \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --min-segment-sample-size 8 \
  --top-segment-limit 25 \
  --include-interaction-segments \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_interaction_audit_v1.json
```

The combined interaction report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_interaction_audit_v1.json`
with `report_key=historical_final_answer_segment_audit:8ca377bfdae112e0`.
It covers 240 final answers from the core 5-season suite and expanded
A-league rolling-window suite. Overall hit rate is `0.7125`, overall ROI is
`-0.0542119502479339`, and `segment_count=164`.

The strongest loss drivers are no longer just broad league names. The top
segments are `hit_probability_band:0.40-0.55` and
`pass_type_hit_probability_band:1x1:0.40-0.55`, both with 30 samples,
hit rate `0.4`, ROI `-0.2816666666666666`, and profit/loss `-16.9`.
The most actionable interaction segments are
`competition_hit_probability_band:ENG_CHAMPIONSHIP:0.40-0.55`
and `competition_odds_band:ENG_CHAMPIONSHIP:1.60-2.00`. Strong positive
counterexamples are `pass_type_hit_probability_band:1x1:0.70-0.85`,
`competition:PRT_PRIMEIRA_LIGA`, and `competition:NED_EREDIVISIE`.
The next quality-function search should target the 1x1 medium-probability /
medium-odds loss band without penalizing those positive counterexamples.

The segment-penalty grid can now read multiple suite manifests in one run and
write a JSONL progress trace. It can also checkpoint full candidate results to
JSONL and reuse them on the next run, so an interrupted heavy grid does not have
to recompute completed candidates. Use this for slower full-history tuning so a
run can show baseline/candidate timing instead of looking stalled:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_eng_championship_medium_probability_odds_smoke_v1.json \
  --progress-jsonl-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_eng_championship_medium_probability_odds_smoke_v1.jsonl \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --pass-type-group 1x1 \
  --mode-group single \
  --competition-group ENG_CHAMPIONSHIP \
  --min-hit-probability-values 0.40 \
  --max-hit-probability-values 0.55 \
  --min-odds-product-values 1.60 \
  --max-odds-product-values 2.00 \
  --strength-values 0.01,0.02,0.04 \
  --min-penalty-option-count 1 \
  --min-final-hit-count-delta 0 \
  --min-final-hit-rate-delta 0 \
  --min-candidate-roi 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0 \
  --max-brier-score-delta 0 \
  --max-log-loss-delta 0 \
  --max-mean-calibration-error-delta 0
```

For recoverable runs, add a candidate checkpoint path. Existing matching
candidates in the same checkpoint are reused automatically; newly evaluated
candidates are appended as they finish:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --baseline-cache-dir configs/recommendations/historical_reports/segment_penalty_baseline_cache \
  --candidate-checkpoint-jsonl-path configs/recommendations/historical_reports/segment_penalty_candidate_checkpoint.jsonl \
  --progress-jsonl-path configs/recommendations/historical_reports/segment_penalty_progress.jsonl \
  --output-path configs/recommendations/historical_reports/segment_penalty_partial_or_final_report.json \
  --candidate-start-index 0 \
  --candidate-limit 6
```

Completed final reports can also seed a later run with `--reuse-report`. Cached
candidates are reused only when the candidate index and segment specification
match the current grid, so stale candidates from a different grid shape are
ignored.

The baseline suite can be cached separately through `--baseline-cache-dir`.
The cache key includes slice IDs, as-of times, baseline backtest options,
optimizer profiles, and the competition profile version. Use
`--no-read-baseline-cache` or `--no-write-baseline-cache` when you need to force
a fresh baseline or run a read-only replay. Reports expose
`baseline_cache_key`, `baseline_cache_status`, and `baseline_cache_written`.

The current ENG Championship medium-probability / medium-odds smoke report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_eng_championship_medium_probability_odds_smoke_v1.json`.
It evaluates 240 historical slices and 3 penalty strengths. All 3 candidates
are rejected. Strengths `0.01` and `0.02` each touch 7 options but regress ROI
by `-0.0077523610635415255` and profit/loss by `-6.0`; strength `0.04` raises
final hits by `+1` but regresses ROI by `-0.014442118376404744`, profit/loss by
`-12.544600000000003`, and Brier/log-loss/calibration. The gate therefore
keeps this precise ENG Championship penalty out of runtime/default paths. The
progress trace is stored beside the report and records 10 events, including
baseline timing (`256.60484` seconds), candidate timing (`847.654192` seconds),
and total grid timing (`1104.268835` seconds).

Historical backtests now also have an opt-in final-answer segment penalty for
those audited segments. The first segment-penalty grid is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_grid_v1.json`.
It compares the default solver final-answer lane against three targeted
penalty profiles. The `ESP_LA_LIGA`/`GER_BUNDESLIGA` `3x1:single` profile is
the only accuracy-preserving candidate: it touches 10 options, raises final
hits from `23/30` to `25/30`, improves ROI by `+0.04619413333333332`, and
improves profit/loss by `+2.7716479999999994`, but its absolute ROI is still
negative at `-0.04003713133333328`. The global high-hit short-odds profile
turns ROI positive (`0.051277690413333396`) but loses one final hit, so it stays
rejected under the accuracy-first rule.

The segment penalty search is now a formal CLI/report instead of a manual
script. To reproduce the focused `ESP_LA_LIGA`/`GER_BUNDESLIGA` `3x1:single`
grid, run:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_profile_grid_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --pass-type-group 3x1 \
  --mode-group single \
  --competition-group ESP_LA_LIGA,GER_BUNDESLIGA \
  --min-hit-probability-values none,0.85 \
  --max-average-leg-decimal-odds-values none,1.30 \
  --strength-values 0.04,0.08,0.12,0.16
```

The current formal report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_profile_grid_v1.json`
with `report_key=historical_final_answer_segment_penalty_grid:4a075200a8708024`.
It evaluates 16 focused candidates, accepts 8, and rejects the 8 candidates
with `min_hit_probability=0.85` because they touch no options and provide no
objective improvement. The best accepted candidate is the broad
`ESP_LA_LIGA`/`GER_BUNDESLIGA` `3x1:single` penalty at strength `0.04`: it
touches 10 options, raises final hits from `23/30` to `25/30`, improves ROI by
`+0.04619413333333332`, improves profit/loss by `+2.7716479999999994`, and
improves Brier/log-loss/calibration. Its absolute ROI remains negative at
`-0.04003713133333328`, so it stays an opt-in historical experiment rather than
a default production rule.

Before a segment penalty can advance, run the rolling admission gate. It
replays the selected grid candidate against overall, competition, season, and
rolling-window folds:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-rolling-admission \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --grid-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_profile_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_rolling_admission_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --min-overall-final-answer-count 30 \
  --min-active-competition-fold-count 2 \
  --min-active-season-fold-count 2 \
  --min-active-rolling-fold-count 1 \
  --rolling-window-slice-count 12 \
  --rolling-window-step 6 \
  --no-fail-process
```

The current admission report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_rolling_admission_v1.json`
with
`report_key=historical_final_answer_segment_penalty_rolling_admission:697061e5cf9f7fae`.
It is `shadow_only`: overall metrics pass (`23/30` to `25/30`, ROI delta
`+0.04619413333333332`, no harmed final answers), but `failed_fold_count=5`.
The failed folds are seasons `2020-2021`, `2021-2022`, `2022-2023`, and the
first two rolling windows; each has no hit-count regression but negative
ROI/P&L deltas. Competition folds pass: `ESP_LA_LIGA` is neutral and
`GER_BUNDESLIGA` contributes the full `+2` hit delta. The candidate therefore
remains research-only until the early-season/rolling-window ROI leakage is
removed.

The next focused pass narrowed the segment to `GER_BUNDESLIGA` only. The grid
report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_only_grid_v1.json`
with `report_key=historical_final_answer_segment_penalty_grid:54e91b36dfa5bb2f`.
It accepts all 10 candidates; the best candidate is `GER_BUNDESLIGA` /
`3x1` / `single` / strength `0.02` / max average leg odds `1.30`. It touches
5 options, raises final hits from `23/30` to `25/30`, improves ROI by
`+0.051691999999999995`, and improves profit/loss by `+3.10152`. The rolling
admission report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_only_rolling_admission_v1.json`
with
`report_key=historical_final_answer_segment_penalty_rolling_admission:a3f5bb31bbd09a43`.
It remains `shadow_only`: failed folds drop from 5 to 4, but seasons
`2020-2021` and `2022-2023` plus the first two rolling windows still show
negative ROI/P&L deltas.

Historical final-answer segment penalties now also support an explicit season
filter. The filter is opt-in and remains historical/backtest-only. To reproduce
the season-aware focused grid, run:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_season_aware_grid_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --pass-type-group 3x1 \
  --mode-group single \
  --competition-group GER_BUNDESLIGA \
  --season-group 2021-2022,2023-2024,2024-2025 \
  --season-group 2023-2024,2024-2025 \
  --season-group 2024-2025 \
  --min-hit-probability-values none \
  --max-average-leg-decimal-odds-values none,1.30 \
  --strength-values 0.02,0.04,0.08,0.12,0.16
```

The season-aware grid report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_season_aware_grid_v1.json`
with `report_key=historical_final_answer_segment_penalty_grid:44c5a6eaf19c8279`.
It evaluates 30 candidates and accepts all 30. The best candidate is
`GER_BUNDESLIGA` / `3x1` / `single` / seasons
`2021-2022,2023-2024,2024-2025` / strength `0.02`: it touches 3 options,
raises final hits from `23/30` to `25/30`, improves ROI by
`+0.07033333333333333`, improves profit/loss by `+4.220000000000001`, and
reduces the absolute loss to `-0.953875879999996`. Its absolute ROI is still
negative at `-0.015897931333333268`.

The season-aware rolling admission report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_season_aware_rolling_admission_v1.json`
with
`report_key=historical_final_answer_segment_penalty_rolling_admission:10639a7c285c4066`.
It is `accepted` with `failed_fold_count=0`, 1 active competition fold,
3 active season folds, and 4 active rolling-window folds. Overall final hits
move from `23/30` to `25/30`, ROI delta is `+0.07033333333333333`, profit/loss
delta is `+4.220000000000001`, and no previously correct final answer is
harmed. This is useful evidence that the previous leakage was season/window
specific, but it is not a production default by itself because historical
season IDs are hindsight filters and must be converted into forward-safe
season-phase or regime features before promotion.

The first forward-safe conversion replaces explicit historical season IDs with
a per-competition season index. This lets the backtest ask whether a rule only
applies after enough prior seasons exist for that competition, without naming
future seasons directly:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_grid_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --pass-type-group 3x1 \
  --mode-group single \
  --competition-group GER_BUNDESLIGA \
  --min-competition-season-index-values none,2,3,4,5 \
  --min-hit-probability-values none \
  --max-average-leg-decimal-odds-values none,1.30 \
  --strength-values 0.02,0.04,0.08
```

The regime grid report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_grid_v1.json`
with `report_key=historical_final_answer_segment_penalty_grid:f613460c80a0f11b`.
The best candidate is `GER_BUNDESLIGA` / `3x1` / `single` /
`min_competition_season_index=4` / strength `0.02`. It touches 2 options,
raises final hits from `23/30` to `25/30`, improves ROI by
`+0.07033333333333333`, improves profit/loss by `+4.220000000000001`, and
does not use explicit `season_ids`.

Segment penalty grid reports now also support original final-answer no-harm
gates. `--max-final-hit-harm-count-vs-baseline` and
`--max-profit-loss-harm-count-vs-baseline` compare each candidate against the
unmodified baseline final answer by signature, then reject aggregate-positive
candidates that locally damage original correct or profitable answers. The
stricter GER regime rerun is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_v1.json`
with `report_key=historical_final_answer_segment_penalty_grid:daace3dcb237c122`.
It evaluates 30 candidates, accepts 12, and rejects 18 via
`segment_penalty:profit_loss_harm_count_above_threshold`. The best accepted
candidate remains the forward-safe `GER_BUNDESLIGA` / `3x1` / `single` /
`min_competition_season_index=4` / strength `0.02` rule: it changes 2 final
answers versus baseline, raises final hits by `+2`, improves ROI by
`+0.07033333333333333`, improves profit/loss by `+4.220000000000001`, and has
`final_hit_harm_count_vs_baseline=0` plus
`profit_loss_harm_count_vs_baseline=0`. This strengthens the holdout evidence
without changing production defaults.

The same original no-harm checks are now carried through the downstream
promotion evidence chain. The stricter rolling admission report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_rolling_admission_v1.json`
with
`report_key=historical_final_answer_segment_penalty_rolling_admission:8fc3817d5f5a6bca`.
It is `accepted`, has `failed_fold_count=0`, and preserves the grid deltas:
`final_answer_hit_delta_count=+2`, `roi_delta=+0.07033333333333333`,
`profit_loss_delta=+4.220000000000001`,
`final_hit_harm_count_vs_baseline=0`, and
`profit_loss_harm_count_vs_baseline=0`.

The governed proposal report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_production_proposal_v1.json`
with
`report_key=historical_final_answer_segment_penalty_production_proposal:1acd8067619d4d2e`.
It remains `holdout_only`: source linkage, rolling admission, forward-safe
competition-season-index filtering, final-answer hit delta, ROI/P&L deltas,
probability-quality deltas, fold count, and both original no-harm checks pass;
only absolute `candidate_roi=-0.015897931333333268` fails the runtime floor of
`0.0`. The generated runtime-profile candidate is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_runtime_profile_candidate_v1.json`.

Runtime replay of that profile is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_runtime_replay_v1.json`
with
`report_key=historical_final_answer_segment_penalty_runtime_replay:416f7f6d44178207`.
It is `holdout_replay_passed`, not runtime-enabled, for the same absolute ROI
reason. It replays the profile with `final_hit_harm_count_vs_baseline=0` and
`profit_loss_harm_count_vs_baseline=0`, so the no-harm interpretation is now
consistent from grid to rolling admission to proposal to runtime replay.

Benchmark quality gates and benchmark cycles also read the explicit no-harm
fields. The segment penalty runtime replay preset now points at the original
harm guard replay artifact and applies both
`max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline`
and
`max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline`
with default threshold `0`. The compatibility
`final_answer_segment_penalty_runtime_replay_harm_count` field is still emitted,
but cycle summaries now also include
`final_answer_segment_penalty_runtime_replay_final_hit_harm_count` and
`final_answer_segment_penalty_runtime_replay_profit_loss_harm_count`.

A local benchmark-gate smoke report is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_benchmark_gate_smoke_v1.json`.
It reads
`report_key=historical_final_answer_segment_penalty_runtime_replay:416f7f6d44178207`,
passes with `failed_checks=[]`, and records both explicit no-harm counts as
`0`.

Segment penalty grid search now also supports an absolute candidate ROI floor
via `--min-candidate-roi`. This prevents a rule from being accepted solely
because it improves ROI relative to a worse baseline while still losing money
in absolute terms. The first focused probe is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_positive_roi_floor_probe_v1.json`
with `report_key=historical_final_answer_segment_penalty_grid:78f194bae48b41ea`.
It checks 12 forward-safe `3x1` / `single` candidates across `EPL`,
`ESP_LA_LIGA`, and `GER_BUNDESLIGA` using `min_competition_season_index=4`,
strengths `0.02,0.08`, and `min_candidate_roi=0.0`. All 12 candidates are
rejected by `segment_penalty:candidate_roi_below_floor`. The best rejected
candidate is still the GER regime rule: it raises final hits from `23/30` to
`25/30`, improves ROI by `+0.07033333333333333`, improves profit/loss by
`+4.220000000000001`, and has both explicit no-harm counts at `0`, but its
absolute `candidate_roi=-0.015897931333333268`; therefore it remains holdout
evidence rather than a production/default recommendation rule. Larger positive
ROI searches should be run in smaller batches or after adding progress/cache
support to the grid runner.

Validate the same candidate with the rolling admission gate:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-rolling-admission \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --grid-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_rolling_admission_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --min-overall-final-answer-count 30 \
  --min-active-competition-fold-count 1 \
  --min-active-season-fold-count 2 \
  --min-active-rolling-fold-count 2 \
  --rolling-window-slice-count 12 \
  --rolling-window-step 6 \
  --no-fail-process
```

The regime rolling admission report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_rolling_admission_v1.json`
with
`report_key=historical_final_answer_segment_penalty_rolling_admission:9008173a87654d81`.
It is `accepted` with `failed_fold_count=0`, 1 active competition fold,
2 active season folds, and 2 active rolling-window folds. Overall final hits
move from `23/30` to `25/30`, ROI delta is `+0.07033333333333333`,
profit/loss delta is `+4.220000000000001`, and no previously correct final
answer is harmed. Rolling admission preserves the suite-level competition
season index map inside every fold, so `min_competition_season_index=4` stays
global rather than being recomputed from each fold subset.

The production proposal gate converts the accepted regime evidence into a
governed runtime-profile artifact, while still blocking production if absolute
ROI has not crossed the configured floor:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-production-proposal \
  --grid-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_grid_v1.json \
  --rolling-admission-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_rolling_admission_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_production_proposal_v1.json \
  --profile-output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_runtime_profile_candidate_v1.json \
  --proposal-id final_answer_segment_penalty_ger_regime_v1 \
  --proposed-profile-version v3_1_final_answer_segment_penalty_ger_regime_runtime_profile_candidate_v1 \
  --min-final-answer-count 30 \
  --min-changed-final-answer-count 2 \
  --min-penalty-option-count 2 \
  --min-final-answer-hit-count-delta 0 \
  --min-final-answer-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --min-candidate-roi 0 \
  --max-harm-count-vs-baseline 0 \
  --min-active-competition-fold-count 1 \
  --min-active-season-fold-count 2 \
  --min-active-rolling-fold-count 2 \
  --max-failed-fold-count 0 \
  --no-fail-process
```

The current proposal report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_production_proposal_v1.json`
with
`report_key=historical_final_answer_segment_penalty_production_proposal:4adacd774931b31d`.
It is `holdout_only`: source linkage, rolling admission, no-hindsight season
IDs, hit-rate delta, ROI delta, profit/loss delta, Brier/log-loss/calibration,
harm count, and fold gates all pass. The only failed check is
`candidate_roi`, because the absolute ROI is `-0.015897931333333268` against a
runtime proposal floor of `0.0`.

The generated holdout profile artifact is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_runtime_profile_candidate_v1.json`.
It contains one `final_answer_segment_penalty_rules` entry for
`GER_BUNDESLIGA` / `3x1` / `single` / `min_competition_season_index=4`, but
`proposed_production_enabled=false`. This is intentional: the rule is allowed
to enter expanded holdout validation, not default runtime recommendations.

The holdout profile can be consumed by the runtime-style replay gate before it
is considered for any later promotion. The replay loader accepts the generated
profile artifact, applies the selected `final_answer_segment_penalty_rules`
through the same historical backtest options that a runtime profile would
populate, and compares the candidate replay against the unmodified baseline:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-runtime-replay \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_runtime_profile_candidate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_runtime_replay_v1.json \
  --enable-shadow-replay \
  --rule-ids final_answer_segment_penalty_ger_regime_v1 \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --min-final-answer-count 30 \
  --min-changed-final-answer-count 2 \
  --min-penalty-option-count 2 \
  --min-final-answer-hit-count-delta 0 \
  --min-final-answer-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --min-candidate-roi 0 \
  --max-harm-count-vs-baseline 0 \
  --no-fail-process
```

The current runtime replay report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_runtime_replay_v1.json`
with
`report_key=historical_final_answer_segment_penalty_runtime_replay:92d04fa3b0fa6c7e`.
It is `holdout_replay_passed`: the replay reproduces the expected improvement
from `23/30` to `25/30` final-answer hits, changes 2 final answers, touches 2
penalty options, improves ROI by `+0.07033333333333333`, improves profit/loss
by `+4.220000000000001`, improves Brier/log-loss/calibration, and harms no
previously correct final answer. The only failed production replay check is
still absolute `candidate_roi`, because the candidate ROI is
`-0.015897931333333268` against a `0.0` floor. Therefore this remains a
holdout-only artifact, not a production runtime rule or default profile change.

The runtime replay report is now consumable by the persisted benchmark quality
gate through the `final_answer_segment_penalty_ger_regime_holdout_v1` preset:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --allow-missing-history \
  --final-answer-segment-penalty-runtime-replay-preset final_answer_segment_penalty_ger_regime_holdout_v1 \
  --no-fail-process \
  > configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_runtime_replay_benchmark_gate_smoke_v1.json
```

The smoke report passes with no gate failed checks while still carrying the
underlying replay's `candidate_roi` failed check as holdout context. This keeps
the candidate visible to cycle quality review without allowing it to become a
runtime production rule.

The runtime replay CLI also accepts repeated `--suite-manifest` arguments, so a
candidate can be checked against a larger combined holdout without hand-expanding
slice paths. The current combined core + expanded A-league holdout run uses the
30-slice core suite plus the 210-slice expanded rolling-window suite:

```bash
uv run nutmeg-recommendation-final-answer-segment-penalty-runtime-replay \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_runtime_profile_candidate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_ger_regime_runtime_replay_multi_manifest_v1.json \
  --enable-shadow-replay \
  --rule-ids final_answer_segment_penalty_ger_regime_v1 \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --min-final-answer-count 240 \
  --min-changed-final-answer-count 1 \
  --min-penalty-option-count 1 \
  --min-final-answer-hit-count-delta 0 \
  --min-final-answer-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --min-candidate-roi 0 \
  --max-harm-count-vs-baseline 0 \
  --no-fail-process
```

The combined holdout report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_ger_regime_runtime_replay_multi_manifest_v1.json`
with
`report_key=historical_final_answer_segment_penalty_runtime_replay:1d4acf9275a81d72`.
It covers 240 final answers, improves hits from `171` to `173`, improves ROI by
`+0.005812672176308535`, improves profit/loss by `+4.219999999999999`, improves
Brier/log-loss/calibration, and harms no previously correct final answer. The
only failed replay check is still absolute `candidate_roi`, because the
candidate ROI is `-0.04839927807162534`. Therefore the larger holdout confirms
that the rule is not hurting this sample, but it still remains holdout-only and
does not change the default production profile.

The combined replay can be attached to the benchmark gate as custom evidence:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --allow-missing-history \
  --final-answer-segment-penalty-runtime-replay-report-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_ger_regime_runtime_replay_multi_manifest_v1.json \
  --require-final-answer-segment-penalty-runtime-replay \
  --min-final-answer-segment-penalty-runtime-replay-rule-count 1 \
  --min-final-answer-segment-penalty-runtime-replay-selected-rule-count 1 \
  --max-final-answer-segment-penalty-runtime-replay-selected-rule-count 1 \
  --min-final-answer-segment-penalty-runtime-replay-final-answer-count 240 \
  --min-final-answer-segment-penalty-runtime-replay-changed-final-answer-count 1 \
  --min-final-answer-segment-penalty-runtime-replay-penalty-option-count 1 \
  --min-final-answer-segment-penalty-runtime-replay-hit-count-delta 0 \
  --min-final-answer-segment-penalty-runtime-replay-hit-rate-delta 0 \
  --min-final-answer-segment-penalty-runtime-replay-roi-delta 0 \
  --min-final-answer-segment-penalty-runtime-replay-profit-loss-delta 0 \
  --max-final-answer-segment-penalty-runtime-replay-brier-score-delta 0 \
  --max-final-answer-segment-penalty-runtime-replay-log-loss-delta 0 \
  --max-final-answer-segment-penalty-runtime-replay-calibration-error-delta 0 \
  --max-final-answer-segment-penalty-runtime-replay-harm-count-vs-baseline 0 \
  --no-fail-process \
  > configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_runtime_replay_benchmark_gate_v1.json
```

That gate artifact passes with no gate-level failed checks while preserving the
underlying replay's `candidate_roi` failure in the evidence payload.

To explain where the negative ROI is coming from, run final-answer loss
diagnostics. This report looks only at the final answer that users would have
received, then stratifies selected legs by league, season, scenario, odds band,
probability band, model edge, favorite fragility, repeated-team exposure, and
miss reason:

```bash
uv run nutmeg-recommendation-historical-loss-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_negative_roi_loss_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --negative-roi-only
```

The current negative-ROI report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_negative_roi_loss_diagnostics.json`
with `report_key=historical_final_answer_loss_diagnostics:58c9c6e2afe267d9`.
It covers 15 final answers, 50 selected legs, and 12 missed legs across
`ESP_LA_LIGA`, `GER_BUNDESLIGA`, and `JPN_J1`. The strongest pattern is not a
long-parlay depth problem: Spain and J1 misses concentrate in high-probability,
short-price market favorites with negative average model edge. Spain's missed
favorite legs average probability `0.8430433904231802`, odds
`1.1383333333333334`, and model edge `-0.03604493476159015`; J1's corresponding
misses average probability `0.7444733773935501`, odds `1.2650000000000001`,
and model edge `-0.05082513856382101`. This points the next experiment toward a
short-price favorite / negative-edge guardrail rather than another profile
length change.

The loss diagnostics CLI also accepts repeated `--suite-manifest` arguments.
To diagnose the same 240-slice core + expanded holdout surface used by the
combined segment-penalty replay:

```bash
uv run nutmeg-recommendation-historical-loss-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_negative_roi_loss_diagnostics_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --negative-roi-only
```

The combined report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_negative_roi_loss_diagnostics_v1.json`
with `report_key=historical_final_answer_loss_diagnostics:b40863827184c835`.
It reads 240 input slices and filters to 140 negative-ROI final answers across
`ENG_CHAMPIONSHIP`, `EPL`, `ESP_LA_LIGA`, `FRA_LIGUE_2`,
`GER_2_BUNDESLIGA`, `GER_BUNDESLIGA`, `ITA_SERIE_A`, and `ITA_SERIE_B`.
The strongest loss groups are now expanded-league problems, not only the
earlier top-league short-price issue: `ENG_CHAMPIONSHIP:1x1:single` loses
`-11.060000000000002` on 29 final answers, while `ITA_SERIE_B:2x1:multiple`
loses `-9.263999999999996` on 17 final answers. The top missed-leg cluster is
`ITA_SERIE_B` negative-edge fragile favorites: 81 selected legs, 47 missed
legs, average probability `0.42325862406623477`, odds
`2.4504938271604937`, model edge `-0.02814340644544755`, and favorite
fragility `0.37690740740740747`. This points the next core experiment toward
competition-scoped medium-price / negative-edge value guards or final-answer
arbitrator weights for `ITA_SERIE_B` and `ENG_CHAMPIONSHIP`, not a global
hard filter and not a production profile promotion.

The historical suite quality gate also accepts repeated `--suite-manifest`
arguments, so final-answer quality-signal candidates can be checked against the
same combined holdout. The current `ITA_SERIE_B` medium-price negative-edge
candidate is:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_medium_price_negative_edge_quality_signal_s004_gate_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --final-answer-quality-signal-penalty \
  --final-answer-quality-signal-penalty-strength 0.04 \
  --final-answer-quality-signal-probability-min 0.45 \
  --final-answer-quality-signal-probability-max 0.58 \
  --final-answer-quality-signal-min-decimal-odds 1.60 \
  --final-answer-quality-signal-max-decimal-odds 2.20 \
  --final-answer-quality-signal-max-model-edge -0.02 \
  --final-answer-quality-signal-competitions ITA_SERIE_B \
  --min-slice-count 240 \
  --min-comparison-count 240 \
  --min-final-hit-sample-size 240 \
  --min-candidate-roi 0 \
  --min-final-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --max-brier-score-delta 0 \
  --max-log-loss-delta 0 \
  --max-mean-calibration-error-delta 0 \
  --min-final-answer-changed-count 1 \
  --no-fail-process
```

The combined gate report has
`gate_key=historical_recommendation_suite_quality_gate:6020922b088e1f60` and
is intentionally `failed` only on absolute `candidate_roi`. It improves final
hit rate by `+0.016666666666666607`, ROI by `+0.014017427253866812`,
profit/loss by `+10.4528`, Brier/log-loss/calibration, and changes 59 final
answers. The candidate ROI is still `-0.008001802090395471`, so this remains a
holdout improvement signal rather than a production candidate.

The corresponding `ENG_CHAMPIONSHIP` widened medium-price experiment is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_eng_championship_medium_price_negative_edge_quality_signal_s004_gate_v1.json`
with `gate_key=historical_recommendation_suite_quality_gate:cb74051b937a6f8a`.
It reaches positive absolute ROI (`0.00838336890855458`) and improves final-hit
rate, but it regresses ROI delta by `-0.008787113052229746` and profit/loss by
`-6.575800000000004`, so it is rejected. This is the current boundary for the
next tuning pass: `ITA_SERIE_B` needs enough lift to clear absolute ROI, while
`ENG_CHAMPIONSHIP` must not trade away existing baseline profit.

The final-answer quality-signal profile grid now also accepts repeated
`--suite-manifest` arguments and an explicit `--min-candidate-roi` floor, so
combined holdout profile searches can reject candidates that improve relative
metrics but fail absolute ROI expectations. A narrow `ITA_SERIE_B` follow-up
grid was run on the 240-slice core + expanded holdout:

```bash
uv run nutmeg-recommendation-final-answer-quality-signal-profile-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_partial3_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --competition-group ITA_SERIE_B \
  --probability-min-values 0.48,0.50 \
  --probability-max-values 0.58 \
  --min-decimal-odds-values 1.75 \
  --max-decimal-odds-values 2.00,2.20 \
  --max-model-edge-values -0.03 \
  --score-max-values 1.0 \
  --strength-values 0.04 \
  --min-candidate-roi 0 \
  --min-affected-leg-count 1 \
  --min-final-hit-count-delta 0 \
  --min-final-hit-rate-delta 0 \
  --min-roi-delta 0 \
  --min-profit-loss-delta 0 \
  --max-brier-score-delta 0 \
  --max-log-loss-delta 0 \
  --max-mean-calibration-error-delta 0 \
  --min-objective-roi-delta 0 \
  --candidate-start-index 0 \
  --candidate-limit 3 \
  --candidate-cache-dir tmp/quality-signal-profile-grid-cache/ita-serie-b-narrow-combined-v1
```

The partial report has
`report_key=historical_final_answer_quality_signal_profile_grid:4c2cb3b36cd64c8c`.
It covers 3 of 4 generated candidates, reuses 3 cache hits, accepts none, and
rejects all candidates for `roi_regressed`, `profit_loss_regressed`, and
`objective_improvement_missing`. The current baseline remains stronger on the
same 240-slice combined holdout:
`baseline_candidate_final_hit_rate=0.7041666666666667`,
`baseline_candidate_roi=0.0173867918452381`, and
`baseline_candidate_profit_loss=11.683924120000004`. The best tested narrow
candidate is still positive ROI (`0.013402247964601778`) but trails baseline
by `roi_delta=-0.003984543880636323` and
`profit_loss_delta=-2.597199999999999`, so it is retained as rejected holdout
evidence rather than a production profile candidate. The fourth candidate was
later rerun with `--candidate-indices 3` and merged with the partial report:

```bash
uv run nutmeg-recommendation-final-answer-quality-signal-profile-grid-merge \
  configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_partial3_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_index3_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_full_v1.json
```

The completed report has
`report_key=historical_final_answer_quality_signal_profile_grid:071443ec74add7db`,
`candidate_count=4`, `accepted_count=0`, `rejected_count=4`,
`missing_candidate_indices=[]`, and `is_full_grid=true`. Candidate index 3 has
the same result as the first three candidates:
`candidate_roi=0.013402247964601778`, `candidate_profit_loss=9.086724120000005`,
`roi_delta=-0.003984543880636323`, and
`profit_loss_delta=-2.597199999999999`. This closes the current
`ITA_SERIE_B` narrow medium-price negative-edge direction as rejected holdout
evidence; it should not be expanded further without a materially different
feature or scoring hypothesis.

A follow-up original-harm guard rerun is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_original_harm_guard_v1.json`.
It uses the same 240-slice combined holdout and candidate index 3, with
`max_final_hit_harm_count_vs_baseline=0` and
`max_profit_loss_harm_count_vs_baseline=0`. The report has
`report_key=historical_final_answer_quality_signal_profile_grid:6ca9f8bf1adeaa7c`,
`candidate_count=1`, `accepted_count=0`, and `rejected_count=1`. The candidate
keeps final hit count flat (`final_hit_harm_count_vs_baseline=0`) but changes
one final answer and creates one local P&L harm
(`profit_loss_harm_count_vs_baseline=1`), so it is rejected for
`quality_signal_profile:profit_loss_harm_count_above_threshold` in addition to
ROI/profit regression and missing objective improvement. This keeps the
quality-signal path in the research lane and protects the current original
baseline from localized damage.

For diagnosis, the profile grid can now optionally emit per-slice comparison
items with `--include-comparison-items`, `--comparison-item-filter`, and
`--comparison-item-limit`. A focused harm-item rerun is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_harm_items_v1.json`
with `report_key=historical_final_answer_quality_signal_profile_grid:15873fa95734415f`.
It keeps `candidate_count=1`, `accepted_count=0`, and `rejected_count=1`, but
adds one diagnostic item. The only localized harm is
`football_data_co_uk_ita_serie_b_2022_2023_market_features_v1_rolling_window_v1_003`:
the original answer is `1x1:single` on Cagliari vs Modena home win with
`profit_loss=+1.62`; the quality-signal candidate changes the answer to
`2x1:multiple` across Cagliari vs Modena and Brescia vs Perugia, keeps
`actual_hit=true`, but expands stake from `2.0` to `8.0` and lowers P&L to
`-0.9771999999999998`. This shows the current quality-signal failure is a
multiple-selection stake-efficiency problem, not a missed-outcome problem.

Historical final-answer ranking now has an opt-in stake-efficiency experiment
for this failure mode. `HistoricalRecommendationBacktestOptions` exposes
`final_answer_stake_efficiency_guard`,
`final_answer_stake_efficiency_penalty_strength`,
`final_answer_stake_efficiency_max_stake_multiplier`,
`final_answer_stake_efficiency_min_roi`,
`final_answer_stake_efficiency_modes`, and
`final_answer_stake_efficiency_scope`; the default remains disabled. The first
global rerun is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_stake_efficiency_guard_v1.json`
with `report_key=historical_final_answer_quality_signal_profile_grid:e39d534fa5d01ff7`.
It prevented the localized comparison-item harm but penalized 720 final-answer
options and pulled the recomputed candidate baseline to
`candidate_roi=-0.03392955525` and `candidate_profit_loss=-16.28618652`, so it
is a rejected global strategy.

A narrower `quality_signal_affected` scope is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_scoped_stake_efficiency_guard_v1.json`
with `report_key=historical_final_answer_quality_signal_profile_grid:8003cbc023c3f56b`.
This avoids baseline stake-efficiency penalties, but the candidate still
regresses (`final_hit_harm_count_vs_baseline=6`,
`profit_loss_harm_count_vs_baseline=6`,
`roi_delta=-0.04763484264968282`, `profit_loss_delta=-27.165399999999998`).
Conclusion: stake-efficiency penalty is retained only as a default-off
diagnostic/negative result; it must not be promoted into runtime or production
profiles without a stronger no-harm candidate.

Profile grid runs now also have an optional baseline cache. This is separate
from the per-candidate cache and is controlled by `--baseline-cache-dir`,
`--no-baseline-cache-read`, and `--no-baseline-cache-write`. The cache key uses
the historical slice IDs/as-of timestamps, baseline backtest options, optimizer
profiles, and current competition profile version, then stores the full
baseline suite as `baseline-*.json`. A local smoke run against the Euro 2024
knockout suite wrote
`tmp/quality-signal-profile-grid-cache/baseline-smoke-baseline/baseline-ca172ee8f30117ed.json`;
the second run reported `baseline_cache_status=hit`,
`baseline_cache_written=false`, `cache_hit_count=1`, and `cache_miss_count=0`.
This only speeds historical profile-grid iteration; it does not change the
default recommendation profile or user-facing final answer.

For recovery after a long or interrupted grid run, the same CLI now accepts
explicit candidate indices:

```bash
uv run nutmeg-recommendation-final-answer-quality-signal-profile-grid \
  --suite-manifest configs/recommendations/historical_suites/euro_2024_knockout_suite.json \
  --output-path tmp/quality_signal_profile_grid_candidate_indices_smoke.json \
  --pass-types 1x1,2x1 \
  --modes single \
  --unit-stake 2 \
  --max-budget 4 \
  --min-probability 0.1 \
  --competition-group TEST \
  --candidate-indices 0 \
  --candidate-cache-dir tmp/quality-signal-profile-grid-cache/baseline-smoke-candidates \
  --baseline-cache-dir tmp/quality-signal-profile-grid-cache/baseline-smoke-baseline
```

The smoke report writes `candidate_selection_mode=explicit_indices`,
`requested_candidate_indices=[0]`, `candidate_indices=[0]`,
`baseline_cache_status=hit`, and `cache_hit_count=1`. Reports now also expose
`missing_candidate_indices`, `unmatched_requested_candidate_indices`,
`next_candidate_start_index`, and `is_full_grid`, which makes it clear which
indices still need to be rerun or merged after a partial batch.

That guardrail now exists as an explicit experiment switch, but it is not part
of the default recommendation lane. To reproduce the rejected experiment:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_price_negative_edge_guardrail_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --short-price-negative-edge-guardrail
```

With the current default thresholds (`max_decimal_odds=1.35`,
`min_probability=0.70`, `max_model_edge=0.0`), the experiment excludes 1023
candidate predictions and fails the historical quality gate:
`candidate_final_hit_rate=0.3`, `candidate_roi=-0.0932132567533331`,
`candidate_profit_loss=-5.592795405199986`, and worst league ROI
`GER_BUNDESLIGA=-1.0`. This is intentionally retained only as an auditable
opt-in guardrail and a negative result; it should not be enabled for ordinary
recommendations without a better threshold/profile backed by the full suite.

A softer league-scoped variant keeps candidates in the pool and adds an
internal favorite-fragility penalty instead of deleting the leg:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_price_negative_edge_soft_penalty_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --short-price-negative-edge-soft-penalty \
  --short-price-negative-edge-soft-penalty-strength 1.0 \
  --short-price-negative-edge-soft-penalty-competitions ESP_LA_LIGA,GER_BUNDESLIGA,JPN_J1
```

This experiment penalizes 392 candidate predictions in the negative-ROI
leagues only. It preserves the current final-answer hit rate and ROI
(`candidate_final_hit_rate=0.6666666666666666`,
`candidate_roi=0.05017769041333343`) but changes one final answer and slightly
regresses Brier/log-loss/calibration, so the quality gate still rejects it:
`failed_checks=[suite_status,brier_score_delta,log_loss_delta,mean_calibration_error_delta]`.
Keep it as a threshold-learning tool; do not enable it by default until a
future report improves ROI or upset capture without worsening probability
quality.

The threshold-learning grid now has its own report generator. The first run is
kept as a diagnostic no-regression study: it compares the current baseline
against soft-penalty threshold candidates and rejects any candidate that
lowers final-answer hit rate, ROI/profit, Brier/log-loss, calibration, or
upset capture. A small numerical comparison epsilon is used so floating-point
noise does not masquerade as ROI drift:

```bash
uv run nutmeg-recommendation-short-price-threshold-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_price_threshold_grid.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --competition-group ESP_LA_LIGA,GER_BUNDESLIGA,JPN_J1 \
  --max-decimal-odds-values 1.35 \
  --min-probability-values 0.70 \
  --max-model-edge-values 0.0 \
  --strength-values 0.5,1.0 \
  --no-require-objective-improvement
```

The current five-season grid covers 30 slices, 10,738 fixtures, and 32,214
1X2 predictions. It accepts the league-scoped `strength=0.5` candidate as a
safe no-regression profile: 392 candidate predictions are penalized, final
hit rate remains `0.6666666666666666`, ROI remains effectively unchanged at
`0.05017769041333337`, Brier improves by `-0.0003504407805396681`, log loss
improves by `-0.000774349548274933`, and mean calibration error improves by
`-0.0003137825950302875`. The `strength=1.0` candidate is rejected because it
changes one final answer and its suite status regresses. This is still an
experiment lane, not a default user-facing policy, because ROI and upset
capture have not improved.

The promotion gate has been tightened so new threshold candidates must now
produce a real objective gain before they are accepted: ROI or upset capture
rate must improve, while hit rate, profit, Brier, log loss, calibration, and
upset capture must not regress. Use `--no-require-objective-improvement` only
for diagnostic no-regression studies, not for candidate promotion:

```bash
uv run nutmeg-recommendation-short-price-threshold-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_price_strict_threshold_grid.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --competition-group ESP_LA_LIGA \
  --competition-group GER_BUNDESLIGA \
  --competition-group JPN_J1 \
  --max-decimal-odds-values 1.25,1.35 \
  --min-probability-values 0.70 \
  --max-model-edge-values 0.0 \
  --strength-values 0.25,0.5
```

The strict five-season grid evaluates 12 league-specific candidates. All 12
are rejected by the objective gate. The best rejected candidate is
`GER_BUNDESLIGA`, `max_decimal_odds=1.35`, `min_probability=0.70`,
`strength=0.5`: it penalizes 205 predictions and improves Brier
(`-0.00019856722742114807`), log loss (`-0.0004669054683600349`), and
calibration (`-0.00014320983078552896`), but ROI and upset capture remain
flat. This means the short-price penalty is useful diagnostic evidence, but
not yet a production recommendation improvement.

Final-answer quality-signal diagnostics now provide the next layer of evidence
before any recommendation weights are changed. The report inspects only the
legs selected by the final answer and groups them by candidate score band,
component score band, reason code, probability band, odds band, model-edge band,
and competition-specific probability/odds/model-edge bands:

```bash
uv run nutmeg-recommendation-quality-signal-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_quality_signal_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --min-group-selected-leg-count 5
```

The current report has
`report_key=historical_quality_signal_diagnostics:1a61f64c7b1f3c3b`. It covers
30 final answers, 105 selected legs, 15 missed legs, and the same global
final-answer metrics as the active historical lane:
`final_answer_hit_rate=0.6666666666666666`,
`leg_hit_rate=0.8571428571428571`, and `roi=0.05017769041333331`.
The strongest warning is no longer generic short-price exposure; it is
competition-specific. `competition_odds_band:JPN_J1:short_price` is the worst
group with `selected_leg_count=7`, `leg_hit_rate=0.5714285714285714`, and
`roi=-0.5677`. Spain's short-price group also stays negative
(`roi=-0.21856938688000013`), while EPL and Ligue 1 short-price groups are
positive. This means the next tuning target should be a competition/odds/probability
profile, not a global short-price rule.

The J1 closing-only shadow sample has its own quality-signal report:
`configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_quality_signal_diagnostics.json`
with `report_key=historical_quality_signal_diagnostics:fec4d6565a3afbfb`.
It covers 5 final answers and 10 selected legs. In that closing-only baseline,
`competition_probability_band:JPN_J1:medium` is strongest
(`roi=1.4806499999999998`, `leg_hit_rate=1.0`), while
`competition_probability_band:JPN_J1:high` is weaker
(`roi=0.11420000000000001`, `leg_hit_rate=0.8333333333333334`). Keep this as
profile evidence only; the sample remains closing-only shadow evidence.

Historical backtests now also have an opt-in final-answer quality-signal
penalty. This experiment adjusts only final-answer arbitration, not candidate
generation, and targets selected legs with probability in `[0.65, 0.80)`,
decimal odds up to `1.35`, and negative model edge:

```bash
uv run nutmeg-recommendation-historical-backtest \
  <slice-json> \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --final-answer-quality-signal-penalty \
  --final-answer-quality-signal-penalty-strength 0.04 \
  --final-answer-quality-signal-probability-min 0.65 \
  --final-answer-quality-signal-probability-max 0.80 \
  --final-answer-quality-signal-max-decimal-odds 1.35 \
  --final-answer-quality-signal-max-model-edge 0.0
```

The five-season summary report is stored at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_penalty_summary.json`.
The profile is rejected: final-answer hit rate stays flat at
`0.6666666666666666`, but ROI drops from `0.05017769041333339` to
`0.023057690413333387`, profit/loss drops by `-1.6272000000000002`, and
Brier/log loss/calibration all regress. Keep the signal as an opt-in research
tool only; it is not a production default.

Final-answer quality-signal profile search converts that opt-in penalty into
explicit historical candidates. It can scope the risk rule by competition,
probability band, odds cap, model edge cap, and penalty strength, then rejects
any candidate that fails the same final-answer hit-rate, ROI/profit,
Brier/log-loss, calibration, upset-capture, and original-candidate no-harm
guardrails:

```bash
uv run nutmeg-recommendation-final-answer-quality-signal-profile-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_j1_closing_only_feature_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_final_answer_quality_signal_profile_grid.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --competition-group JPN_J1 \
  --probability-min-values 0.65 \
  --probability-max-values 0.80 \
  --max-decimal-odds-values 1.35 \
  --max-model-edge-values 0.0 \
  --strength-values 0.04
```

The J1 closing-only shadow report has
`report_key=historical_final_answer_quality_signal_profile_grid:47f6034432ba20ba`.
Its baseline remains aligned with the J1 quality-signal diagnostic
(`candidate_final_hit_rate=0.8`, `candidate_roi=0.66078`,
`candidate_profit_loss=6.6078`). The scoped profile touches 2 final-answer
legs, but final hit rate, ROI/profit, Brier/log loss, calibration, and upset
capture are all unchanged, so the objective gate rejects it with
`quality_signal_profile:objective_improvement_missing`. Keep this as evidence
that J1 short-price/high-probability risk exists, not as a promoted default
rule. Full five-season profile-grid search should be batched or cached before
promotion work because repeated suite runs are currently expensive.

The same profile grid can now be split into resumable batches and backed by a
per-candidate cache:

```bash
uv run nutmeg-recommendation-final-answer-quality-signal-profile-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch0_v1.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --competition-group JPN_J1 \
  --competition-group ESP_LA_LIGA \
  --competition-group GER_BUNDESLIGA \
  --probability-min-values 0.65 \
  --probability-max-values 0.80 \
  --max-decimal-odds-values 1.35 \
  --max-model-edge-values 0.0 \
  --strength-values 0.04 \
  --candidate-start-index 0 \
  --candidate-limit 1 \
  --candidate-cache-dir /tmp/nutmeg_v3149_quality_signal_profile_grid_cache
```

The first core batch report is
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch0_v1.json`
with `report_key=historical_final_answer_quality_signal_profile_grid:40ce28f6c174effc`.
It covers candidate index `[0]` out of 3 generated candidates, writes one cache
entry, and rejects the JPN_J1 candidate: 5 affected final-answer legs, but
`final_hit_rate_delta=0.0`, `roi_delta=0.0`, and `profit_loss_delta=0.0`.
The reused run at
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch0_reused_v1.json`
hits that cache entry (`cache_hit_count=1`, `cache_miss_count=0`).

Batch reports can be merged with:

```bash
uv run nutmeg-recommendation-final-answer-quality-signal-profile-grid-merge \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch0_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_partial_merge_v1.json
```

The partial merge has
`report_key=historical_final_answer_quality_signal_profile_grid:4cbb2aac970ed60f`,
`candidate_count=1`, `total_grid_candidate_count=3`,
`missing_candidate_indices=[1,2]`, and `is_full_grid=false`. This proves the
runner can now resume and merge long profile searches; it still does not
promote any user-facing rule.

The remaining core batches complete the three-candidate full grid:

```bash
uv run nutmeg-recommendation-final-answer-quality-signal-profile-grid-merge \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch0_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch1_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch2_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_full_merge_v1.json
```

The full merge has
`report_key=historical_final_answer_quality_signal_profile_grid:c0a6997b1a729148`,
`candidate_count=3`, `accepted_count=0`, `rejected_count=3`,
`missing_candidate_indices=[]`, and `is_full_grid=true`. JPN_J1 touches 5
affected final-answer legs but does not improve final hit rate, ROI, profit, or
probability quality. ESP_LA_LIGA and GER_BUNDESLIGA touch 0 final-answer legs
under this exact `[0.65,0.80)`, odds `<=1.35`, negative-edge profile; Spain
also regresses Brier/log-loss/calibration. The full-grid result rejects all
three candidates and keeps the signal in the research lane.

Candidate-level marginal contribution diagnostics provide the next audit layer:
for each leg selected by the final answer, the tool simulates replacing that
one leg with the best available historical candidate-pool alternatives under
the same pass type, unit stake, and budget. This is an offline audit only; the
actual replacement result is hindsight evidence and must not be treated as a
live recommendation policy.

```bash
uv run nutmeg-recommendation-marginal-contribution-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --max-replacement-candidates-per-leg 5
```

The five-season audit covers 30 final answers, 105 selected legs, and 439
replacement simulations. It finds 77 hindsight replacement opportunities, but
the model-top replacement improves actual profit/loss only 45 times and harms
it 25 times; the average model-top profit/loss delta is `-0.5301794921276191`.
The useful conclusion is not "replace more legs"; it is that replacement
opportunities must be grouped by narrower pre-match signals before any policy
can be promoted.

Marginal signal grouping turns the audit into candidate profiles. The default
accuracy-first run requires sample size, improvement rate, harm-rate control,
positive average profit/loss delta, and non-negative average hit-probability
delta:

```bash
uv run nutmeg-recommendation-marginal-signal-groups \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_signal_groups.json \
  --min-sample-size 3 \
  --min-improvement-rate 0.55 \
  --max-harm-rate 0.30 \
  --min-average-profit-loss-delta 0.0 \
  --min-average-hit-probability-delta 0.0
```

The five-season signal-group report evaluates 52 groups from 105 model-top
replacement simulations. No group qualifies as a profile candidate under the
accuracy-first threshold. One group enters watchlist:
`replacement_quality_band:medium_high`, with 30 samples, improvement rate
`0.6333333333333333`, harm rate `0.16666666666666666`, and average
profit/loss delta `0.04303112439999996`, but it is rejected for promotion
because average hit-probability delta is negative
(`-0.016327490883081178`).

The stricter accuracy-preserving signal run filters out every replacement whose
individual hit-probability delta is negative:

```bash
uv run nutmeg-recommendation-marginal-signal-groups \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_accuracy_preserving_signal_groups.json \
  --min-sample-size 1 \
  --min-improvement-rate 0.55 \
  --max-harm-rate 0.30 \
  --min-average-profit-loss-delta 0.0 \
  --min-average-hit-probability-delta 0.0 \
  --min-replacement-hit-probability-delta 0.0
```

This stricter run keeps only 5 of 105 model-top replacements and filters out
100. All 5 retained replacements harm actual profit/loss, so the report has
`profile_candidate_count=0`, `watchlist_count=0`, and `rejected_count=30`.
This is a useful negative result: generic one-leg replacement is not a safe
path under an accuracy-preserving constraint.

Marginal loss-driver grouping reads the same audit from the other direction:
instead of asking which model-top replacement should be promoted, it asks which
selected-leg profiles are producing enough misses and hindsight replacement
space to deserve a future guard or quality-function experiment.

```bash
uv run nutmeg-recommendation-marginal-loss-driver-groups \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_groups.json \
  --min-sample-size 3 \
  --min-miss-rate 0.20 \
  --min-actual-replacement-opportunity-rate 0.30 \
  --min-average-actual-best-profit-loss-delta 0.0
```

The five-season loss-driver report has
`report_key=historical_marginal_loss_driver_groups:3daad8e49fd0ba0c`,
`group_count=28`, `guard_candidate_count=8`, `watchlist_count=16`, and
`rejected_count=4`. It confirms 105 selected legs, 15 missed legs, and 77
hindsight replacement opportunities. The strongest guard candidate is
`profile:JPN_J1|2x1|probability:high|odds:short|edge:negative|score:medium_high`
with 7 selected legs, miss rate `0.2857142857142857`, replacement-opportunity
rate `0.7142857142857143`, and average actual-best profit/loss delta
`1.3739142857142856`. Its average model-top replacement profit/loss delta is
still negative (`-0.5576857142857142`), so this report should feed a future
guard/penalty experiment rather than direct replacement promotion.

The final-answer quality-signal shadow profile can now include selected-score
ranges, allowing a loss-driver profile to be tested without promoting it:

```bash
uv run nutmeg-recommendation-final-answer-quality-signal-profile-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_guard_profile_grid_2x1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --baseline-optimizer-profile solver \
  --candidate-optimizer-profile solver \
  --competition-group JPN_J1 \
  --probability-min-values 0.65 \
  --probability-max-values 0.80 \
  --max-decimal-odds-values 1.50 \
  --max-model-edge-values -0.02 \
  --score-min-values 0.55 \
  --score-max-values 0.65 \
  --strength-values 0.02,0.04,0.06,0.08
```

This targeted 2x1 five-season shadow report has
`report_key=historical_final_answer_quality_signal_profile_grid:634768004b28b7ae`,
`candidate_count=4`, `accepted_count=0`, and `rejected_count=4`. The profile
affects 8 final-answer legs. Strengths `0.02`, `0.04`, and `0.06` leave final
hit rate, ROI, profit/loss, Brier, log loss, calibration, and upset capture
unchanged, so they are rejected for missing objective improvement. Strength
`0.08` regresses ROI by `-0.14257555555555557`, profit/loss by `-11.9726`,
Brier by `0.005398144750212774`, and log loss by `0.013878363066985089`.
The result keeps this guard in the research lane.

Candidate-pool guardrail ablation tests the same loss-driver before the
optimizer selects legs. This compares baseline solver output with solver output
after excluding the candidate profile; it is still a shadow historical test,
not a production rule.

```bash
uv run nutmeg-recommendation-marginal-loss-driver-candidate-guardrail-ablation \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_candidate_guardrail_ablation_2x1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --competitions JPN_J1 \
  --probability-min 0.65 \
  --probability-max 0.80 \
  --max-decimal-odds 1.50 \
  --max-model-edge -0.02
```

The targeted report has
`report_key=historical_marginal_loss_driver_candidate_guardrail_ablation:4b717f5de4b06c19`,
`excluded_candidate_count=54`, and `final_answer_changed_count=4`. It improves
final hit rate from `0.6666666666666666` to `0.7`, ROI from
`-0.1422633333333333` to `-0.015709999999999964`, and profit/loss by `7.5932`.
However, Brier regresses by `0.01049985766342787`, log loss regresses by
`0.02261384605737571`, and mean calibration error regresses by
`0.008196395368522957`. The report is rejected by the accuracy-first gate:
better settlement results alone are not enough when probability quality gets
worse.

The candidate-pool guardrail also supports optional quality caps:
`--max-calibration-score`, `--max-model-confidence-score`, and
`--max-odds-stability-score` in the ablation CLI, with matching
`--marginal-loss-driver-candidate-guardrail-max-*` flags in historical
backtests. A calibration-capped JPN_J1 run was written to
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_candidate_guardrail_ablation_2x1_calibration_cap.json`.
It has
`report_key=historical_marginal_loss_driver_candidate_guardrail_ablation:e3804b4ecbab617b`,
`excluded_candidate_count=0`, `final_answer_changed_count=0`, and is rejected
for `excluded_candidate_count_too_low` plus missing objective improvement. The
current free historical sample gives this loss-driver profile no useful quality
score spread, so hard quality caps are implemented for future richer samples
but do not promote a default rule now.

The same guardrail ablation now supports multiple `--suite-manifest` arguments
and original-answer protection counters. The protection counters record whether
the candidate filter hurts the baseline final answer on a per-slice basis, so a
candidate cannot pass just because aggregate ROI rises while accuracy falls.

```bash
uv run nutmeg-recommendation-marginal-loss-driver-candidate-guardrail-ablation \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_prob45_65_negative_edge_original_protected_candidate_guardrail_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --competitions ENG_CHAMPIONSHIP,EPL,ESP_LA_LIGA,FRA_LIGUE_2,GER_2_BUNDESLIGA,GER_BUNDESLIGA,ITA_SERIE_A,ITA_SERIE_B \
  --probability-min 0.45 \
  --probability-max 0.65 \
  --max-decimal-odds 2.30 \
  --max-model-edge -0.02 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0
```

The combined report has
`report_key=historical_marginal_loss_driver_candidate_guardrail_ablation:b8517ed3ed0386fc`
and is rejected. It excludes `3,422` negative-edge candidates and changes `103`
final answers. Aggregate ROI improves from `0.0173867918452381` to
`0.1513340493442623`, and profit/loss improves by `99.0926`, but final-answer
hits fall from `169` to `166`. The original-protection counters catch the real
risk: `final_hit_harm_count_vs_baseline=23` and
`profit_loss_harm_count_vs_baseline=29`. Brier, log loss, and mean calibration
error also regress, so this broad candidate filter is not allowed into runtime.

Narrow candidate-pool guardrail grid search can now enumerate smaller
competition/probability/odds/edge filters without recalculating the baseline for
each candidate. The grid is evidence-only: accepted candidates still need a real
objective improvement gate before any runtime profile change.

```bash
uv run nutmeg-recommendation-marginal-loss-driver-candidate-guardrail-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_candidate_guardrail_grid_smoke_v1.json \
  --pass-types 2x1 \
  --modes single \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --competition-group EPL \
  --probability-min-values 0.45 \
  --probability-max-values 0.65 \
  --max-decimal-odds-values 2.30 \
  --max-model-edge-values=-0.02 \
  --candidate-limit 1 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0 \
  --no-require-objective-improvement
```

The smoke report has
`report_key=historical_marginal_loss_driver_candidate_guardrail_grid:4e35f287cfebc9d0`,
`slice_count=30`, `fixture_count=10738`, `candidate_count=1`, and
`accepted_count=1` under the relaxed objective setting above. The EPL candidate
excludes `618` low-edge candidates but changes `0` final answers: baseline and
candidate both hit `20/30`, ROI remains `-0.1422633333333333`, and
original-answer harm counters stay at `0`. This proves the grid runner and
original-protection checks work, but it is a no-op behaviorally; the next useful
run should expand candidate indices/competitions and require objective
improvement.

For combined core + expanded rolling-window evidence, the grid supports
explicit candidate indices and a merge command so long searches can be resumed
in batches:

```bash
uv run nutmeg-recommendation-marginal-loss-driver-candidate-guardrail-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_candidate_guardrail_grid_batch0_v1.json \
  --pass-types 2x1 \
  --modes single \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --competition-group ENG_CHAMPIONSHIP \
  --competition-group FRA_LIGUE_2 \
  --competition-group GER_2_BUNDESLIGA \
  --competition-group ITA_SERIE_B \
  --probability-min-values 0.45,0.55 \
  --probability-max-values 0.55,0.65 \
  --max-decimal-odds-values 2.30 \
  --max-model-edge-values=-0.02 \
  --candidate-indices 0,1,2,3 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0
```

Batch reports for indices `0-3`, `4-7`, and `8-11` were merged into
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_candidate_guardrail_grid_full_v1.json`.
The merged report has
`report_key=historical_marginal_loss_driver_candidate_guardrail_grid:f33da1941ff953a6`,
`slice_count=240`, `fixture_count=13258`, `candidate_count=12`,
`evaluated_candidate_count=12`, `accepted_count=0`, and `warnings=[]`.
All candidate indices are present and `is_full_grid=true`.

The best rejected candidate is `FRA_LIGUE_2` with probability `[0.45,0.65)`.
It improves final hits by `+2`, ROI by `+0.08798333333333334`, and profit/loss
by `+42.232000000000006`, but it also harms `6` baseline final-hit slices,
harms `6` baseline profit/loss slices, and regresses Brier/log-loss. The full
grid therefore confirms the original-protection rule: even attractive aggregate
ROI cannot promote a filter that damages the user's trusted final answer.

Soft-demotion treatment grid is available for the same loss-driver profile. It
keeps candidates in the pool and applies an internal score penalty instead of
deleting them:

```bash
uv run nutmeg-recommendation-marginal-loss-driver-candidate-soft-penalty-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_candidate_soft_penalty_grid_2x1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --competitions JPN_J1 \
  --probability-min 0.65 \
  --probability-max 0.80 \
  --max-decimal-odds 1.50 \
  --max-model-edge -0.02 \
  --strength-values 0.05,0.10,0.20,0.35,0.50,0.75,1.0
```

The five-season report has
`report_key=historical_marginal_loss_driver_candidate_soft_penalty_grid:b1389665e13ddb11`,
`candidate_count=7`, `accepted_count=0`, and `rejected_count=7`. All strengths
touch `54` candidates. Strength `0.05` changes one final answer and almost no
settlement metrics, but Brier/log-loss/calibration still regress slightly.
Strength `0.10` improves final hit rate by `0.033333333333333326`, ROI by
`0.07136`, and profit/loss by `4.281600000000001`, but Brier regresses by
`0.004005740311252698`, log loss by `0.008078043465645224`, and mean
calibration error by `0.0037233608721274347`. Stronger treatments match the
hard guardrail settlement gain but also reproduce its probability-quality
regression. Current decision: keep this as a shadow diagnostic, not a default
recommendation rule.

The soft-demotion grid now supports repeated `--suite-manifest` inputs and
original-protection harm counters, matching the hard guardrail evidence chain.
It also reports where penalized candidates drop out of the path:
`penalized_candidate_pool_count`,
`penalized_completed_scenario_selected_candidate_count`,
`penalized_final_answer_count`, and `penalized_final_answer_leg_count`.

The combined core + expanded rolling-window report for the best hard-filter
reject (`FRA_LIGUE_2`, probability `[0.45,0.65)`) is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_prob45_65_candidate_soft_penalty_fixture_exposure_v1.json`.
It has
`report_key=historical_marginal_loss_driver_candidate_soft_penalty_grid:ca09d2f26ee8f3cf`,
`slice_count=240`, `fixture_count=13258`, `prediction_count=39774`,
`candidate_count=9`, `accepted_count=0`, and `rejected_count=9`. All strengths
from `0.00` through `1.0` touch `124` eligible candidates, but
`penalized_candidate_pool_count=0`,
`penalized_fixture_exposure_rankable_candidate_count=0`,
`penalized_completed_scenario_selected_candidate_count=0`,
`penalized_final_answer_count=0`, and `final_answer_changed_count=0`. This is a
useful diagnosis: the current candidate-level score penalty is not merely too
weak; this segment is filtered before fixture-level ranking. The aggregate
exclusion reason is `{"data_quality_too_low": 124}`. Hard delete can still
change later recommendations by reshaping fixture-level pool composition, but
candidate-level soft penalty cannot affect candidates blocked by the data
quality gate. The path remains diagnostic-only; the next useful work is data
quality calibration or competition/segment-specific quality gating, not higher
soft-penalty strength.

Data-quality threshold sensitivity evidence is available for the same
`FRA_LIGUE_2` loss-driver profile. It fixes the production-like baseline at
`min_data_quality_score=80` and compares lower thresholds without changing the
default recommendation profile:

```bash
uv run nutmeg-recommendation-marginal-loss-driver-data-quality-threshold-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_prob45_65_data_quality_threshold_grid_v1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --strategy accuracy_first \
  --unit-stake 2 \
  --max-budget 64 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --competitions FRA_LIGUE_2 \
  --probability-min 0.45 \
  --probability-max 0.65 \
  --max-decimal-odds 2.30 \
  --max-model-edge -0.02 \
  --baseline-min-data-quality-score 80 \
  --candidate-min-data-quality-score-values 80,75,70,60,50 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0
```

The combined report has
`report_key=historical_marginal_loss_driver_data_quality_threshold_grid:f175d13c4f91cea4`,
`candidate_count=5`, `accepted_count=0`, and `rejected_count=5`. Thresholds
`80` and `75` still exclude all `124` target candidates as
`data_quality_too_low`. Thresholds `70`, `60`, and `50` make all `124` target
candidates rankable and place `29` final answers on the target profile, but
final-answer hit rate drops from `20/30` to `132/240`
(`-0.11666666666666659`), aggregate profit/loss falls by `-88.88400000000001`,
and `114` slices harm profit/loss versus the fixed `80` baseline. This rules
out a broad global threshold reduction. The next useful path is
competition/source-specific data-quality calibration or a beta-quality lane
with stricter final-answer protection.

Per-competition data-quality threshold experiments are supported through a
separate grid. This keeps the global baseline at `80` and lowers the quality
threshold for one competition at a time:

```bash
uv run nutmeg-recommendation-competition-data-quality-threshold-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_lower_league_data_quality_threshold_grid_v1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --strategy accuracy_first \
  --unit-stake 2 \
  --max-budget 64 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --baseline-min-data-quality-score 80 \
  --competitions FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B,ESP_SEGUNDA_DIVISION,ENG_CHAMPIONSHIP \
  --candidate-min-data-quality-score-values 75,70,60,50 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0
```

The lower-league combined report has
`report_key=historical_competition_data_quality_threshold_grid:7d1bae77b334dceb`,
`candidate_count=20`, `accepted_count=0`, and `rejected_count=20`. Threshold
`75` admits no new predictions in these slices. Thresholds `70`, `60`, and
`50` admit `1080` predictions and `360` fixtures per tested lower league, but
all five leagues fail the accuracy gate: final-answer hit rate regresses by
`-0.21666666666666662` for `FRA_LIGUE_2`, `-0.16666666666666663` for
`GER_2_BUNDESLIGA`, `-0.033333333333333326` for `ITA_SERIE_B`,
`-0.016666666666666607` for `ESP_SEGUNDA_DIVISION`, and
`-0.09999999999999998` for `ENG_CHAMPIONSHIP`. Even the best rejected
candidate, `ESP_SEGUNDA_DIVISION@50`, still has profit/loss harm in `16`
slices and probability-quality regressions. Current decision: no lower-league
quality threshold override is promotable. The next path is not a broader
threshold search; it is calibration or scoring work inside the newly admitted
`70-79` quality band.

The beta-quality lane turns that next path into an explicit shadow experiment.
The global baseline remains `min_data_quality_score=80`; each candidate lowers
one competition to `70` while requiring extra controls for probability, odds,
model edge, model confidence, calibration, odds stability, and volatility:

```bash
uv run nutmeg-recommendation-competition-data-quality-beta-lane-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_lower_league_data_quality_beta_lane_grid_edge_wide_v1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --strategy accuracy_first \
  --unit-stake 2 \
  --max-budget 64 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --baseline-min-data-quality-score 80 \
  --beta-min-data-quality-score-values 70 \
  --competitions FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B,ESP_SEGUNDA_DIVISION,ENG_CHAMPIONSHIP \
  --beta-min-probability-values 0.45,0.50 \
  --beta-max-decimal-odds-values 2.30,2.80 \
  --beta-min-model-edge-values=-0.10,-0.05,-0.02 \
  --beta-min-model-confidence-score-values 0.66 \
  --beta-min-calibration-score-values 0.70 \
  --beta-min-odds-stability-score-values 0.90,0.95 \
  --beta-max-volatility-penalty-values 0.08,0.05 \
  --min-beta-lane-prediction-count 1 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0
```

The edge-wide lower-league report has
`report_key=historical_competition_data_quality_beta_lane_grid:b0fb093f71be692a`,
`candidate_count=240`, `accepted_count=0`, and `rejected_count=240`. Unlike the
stricter first pass, the lane now admits real candidates: the best rejected
candidate is `ITA_SERIE_B@70` with `12` beta-lane predictions over `12`
fixtures, improving final-answer samples from `20/30` to `21/31`, ROI by
`+0.04222139784946237`, and profit/loss by `+2.3332000000000006`. It is still
blocked because Brier score, log loss, and mean calibration error regress. The
decision is therefore evidence-positive but not promotable: the `70-79` band
can contain useful settlement results, but it needs calibration repair before
default recommendations can trust it.

The same beta-lane grid can run an opt-in local probability repair. The repair
only applies to beta-lane candidates whose market-implied probability is above
the model probability, then lifts the candidate probability toward that
pre-match market anchor by a capped amount:

```bash
uv run nutmeg-recommendation-competition-data-quality-beta-lane-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_probability_repair_grid_v1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --strategy accuracy_first \
  --unit-stake 2 \
  --max-budget 64 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --baseline-min-data-quality-score 80 \
  --beta-min-data-quality-score-values 70 \
  --competitions ITA_SERIE_B \
  --beta-min-probability-values 0.50 \
  --beta-max-decimal-odds-values 2.80 \
  --beta-min-model-edge-values=-0.05 \
  --beta-min-model-confidence-score-values 0.66 \
  --beta-min-calibration-score-values 0.70 \
  --beta-min-odds-stability-score-values 0.95 \
  --beta-max-volatility-penalty-values 0.05 \
  --probability-repair-strength-values 0.0,0.25,0.50,0.75,1.0 \
  --probability-repair-max-delta-values 0.0,0.02,0.04,0.06 \
  --probability-repair-min-market-probability-delta-values 0.0,0.01 \
  --min-beta-lane-prediction-count 1 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0
```

The focused ITA Serie B repair report has
`report_key=historical_competition_data_quality_beta_lane_grid:d04728e3f1843d23`,
`candidate_count=40`, `accepted_count=0`, and `rejected_count=40`. The best
candidate repairs `12` beta-lane candidates, with `2` repaired candidates in
the final answer, and keeps the same settlement lift as the un-repaired lane:
`21/31` hits, ROI delta `+0.04222139784946237`, and profit/loss delta
`+2.3332000000000006`. The repair improves probability quality versus the
unrepaired lane (`brier_score_delta` drops from about `+0.00419` to
`+0.00218`, `log_loss_delta` from about `+0.00846` to `+0.00436`, and
calibration delta from about `+0.00569` to `+0.00391`) but still does not pass
the no-regression gate. A delta-wide follow-up
`report_key=historical_competition_data_quality_beta_lane_grid:0c3281c86120bf6c`
showed that larger caps no longer change the result, so the next useful work is
a proper beta-lane-local calibration model rather than more cap tuning.

The beta-lane repair profile now also supports segment-local uplift terms. These
terms are still opt-in and only apply after the beta-lane guards pass; they can
combine market gap, a fixed local uplift, lower-quality-band distance, odds
stability, a max probability cap, and a max adjustment delta:

```bash
uv run nutmeg-recommendation-competition-data-quality-beta-lane-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_local_calibration_profile_grid_stronger_v1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --strategy accuracy_first \
  --unit-stake 2 \
  --max-budget 64 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --baseline-min-data-quality-score 80 \
  --beta-min-data-quality-score-values 70 \
  --competitions ITA_SERIE_B \
  --beta-min-probability-values 0.50 \
  --beta-max-decimal-odds-values 2.80 \
  --beta-min-model-edge-values=-0.05 \
  --beta-min-model-confidence-score-values 0.66 \
  --beta-min-calibration-score-values 0.70 \
  --beta-min-odds-stability-score-values 0.95 \
  --beta-max-volatility-penalty-values 0.05 \
  --probability-repair-strength-values 1.0 \
  --probability-repair-max-delta-values 0.18,0.22,0.26 \
  --probability-repair-min-market-probability-delta-values 0.01 \
  --probability-repair-extra-uplift-values 0.08,0.10 \
  --probability-repair-data-quality-gap-weight-values 0.02,0.04 \
  --probability-repair-odds-stability-weight-values 0.0 \
  --probability-repair-max-probability-values 0.98 \
  --min-beta-lane-prediction-count 1 \
  --max-final-hit-harm-count-vs-baseline 0 \
  --max-profit-loss-harm-count-vs-baseline 0
```

The stronger local-calibration report has
`report_key=historical_competition_data_quality_beta_lane_grid:547c9df8d223c9c9`,
`candidate_count=12`, `accepted_count=12`, and `rejected_count=0`. The best
focused shadow candidate keeps the same final-answer settlement improvement
(`21/31` hits, ROI delta `+0.04222139784946237`, profit/loss delta
`+2.3332000000000006`, and zero local harm) while turning probability quality
positive: `brier_score_delta=-0.003415333355129946`,
`log_loss_delta=-0.007117418622229588`, and
`mean_calibration_error_delta=-0.002453394268102871`. This is the first
accepted beta-lane local-calibration candidate, but it is still a focused
shadow result for `ITA_SERIE_B`; it should go through rolling/holdout admission
before any runtime profile proposal.

That admission step is now explicit:

```bash
uv run nutmeg-recommendation-competition-data-quality-beta-lane-rolling-admission \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --grid-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_local_calibration_profile_grid_stronger_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_local_calibration_profile_rolling_admission_v1.json \
  --pass-types 2x1 \
  --modes single,multiple \
  --strategy accuracy_first \
  --unit-stake 2 \
  --max-budget 64 \
  --min-probability 0.15 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --optimizer-profile solver \
  --baseline-min-data-quality-score 80 \
  --min-overall-final-answer-count 30 \
  --min-overall-beta-lane-prediction-count 12 \
  --min-overall-probability-repair-candidate-count 12 \
  --min-overall-probability-repair-final-answer-selected-candidate-count 2 \
  --min-active-competition-fold-count 1 \
  --min-active-season-fold-count 2 \
  --min-active-rolling-fold-count 2 \
  --rolling-window-slice-count 12 \
  --rolling-window-step 6
```

The rolling admission report has
`report_key=historical_competition_data_quality_beta_lane_rolling_admission:a593425db4453821`
and keeps the overall candidate positive, but returns `status=shadow_only`
with `candidate_profile_allowed=false`. Overall still passes: `31` final
answers, `12` beta-lane predictions, `12` repaired candidates, `2` repaired
final-answer selections, hit delta `+1`, ROI delta `+0.04222139784946237`,
profit/loss delta `+2.3332000000000006`, and negative Brier/log-loss/mean
calibration deltas. The admission gate blocks promotion because the evidence is
too concentrated: only `1` active season fold clears the exposure threshold,
and `4` active folds fail strict fold-level probability-quality checks. The
profile therefore remains useful shadow evidence, not a runtime/default profile.

For favorite-fragility experiments, historical backtests can now derive
fixture-level 1X2 market context on the fly:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_market_context_experiment_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals
```

This opt-in lane derives internal favorite/not-win, draw-pressure, short-price,
and fragile-favorite-band signals from each frozen 1X2 fixture. The first
five-season run kept the final answer unchanged:
`candidate_final_hit_rate=0.6666666666666666`,
`candidate_roi=0.05017769041333343`, and
`candidate_upset_capture_rate=0.0`. Keep it as an experiment flag until a
stratified profile improves final-answer ROI or upset capture without lowering
hit rate.

Upset capture profiles turn the frozen historical backtest into a final-answer
miss/capture map for cold-match learning. The tool looks only at upset
opportunities that actually matched the final result, then classifies whether
the final answer captured the same outcome, selected the wrong outcome in the
same fixture, or ignored that fixture entirely:

```bash
uv run nutmeg-recommendation-upset-capture-profiles \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_capture_profiles.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --upset-threshold 0.35 \
  --min-group-sample-size 3
```

The five-season report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_capture_profiles.json`
has `report_key=historical_upset_capture_profiles:e27984fa9be71491`. It
finds `opportunity_count=1340`, `capture_count=0`, `capture_rate=0.0`,
`not_selected_count=1325`, `selected_wrong_fixture_count=15`, and
`selected_favorite_miss_count=15`. The main leak is therefore not only
"selected a fragile favorite"; it is that true upset candidates almost never
enter the final-answer lane. The next safe experiment should expand or reserve
upset-aware candidate exposure under a strict no-regression gate, not promote a
generic high-odds override.

Historical backtests now support an opt-in upset exposure reserve. The reserve
adds high-protection upset fixtures back into the compressed candidate pool and
scenario pool without changing the default route:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_exposure_reserve1_single_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single \
  --candidate-optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --upset-exposure-reserve \
  --upset-exposure-reserve-fixture-count 1 \
  --upset-exposure-reserve-max-candidates-per-fixture 1 \
  --upset-exposure-reserve-min-protection-score 0.45 \
  --upset-exposure-reserve-min-probability 0.15
```

The single-mode five-season reserve report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_exposure_reserve1_single_diagnostics.json`
has `report_key=historical_recommendation_diagnostic:8f9aff40905c1467`.
It adds `598` reserve candidates to candidate pools, but final answers select
`0` reserve candidates, so final hit rate, ROI, Brier, log loss, calibration,
and upset capture stay unchanged. This proves the first half of the path:
candidate exposure is possible and accuracy-neutral, but selection scoring still
rejects every reserve leg. Do not promote this as a strategy; the next
experiment must be an explicit upset-aware scoring or final-answer lane with the
same no-regression gate.

Historical backtests also support an opt-in upset-aware final-answer lane. This
lane is separate from the ordinary compressed candidate pool: when enabled, it
builds an extra final-answer option from pre-match upset-protection candidates
and lets the normal final-answer arbitrator decide whether it should win. It is
off by default and should be treated as a diagnostics route until historical
quality gates accept a profile:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_final_answer_lane1_single_boost008_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single \
  --candidate-optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --upset-final-answer-lane \
  --upset-final-answer-lane-pass-type 1x1 \
  --upset-final-answer-lane-candidate-limit 24 \
  --upset-final-answer-lane-min-protection-score 0.45 \
  --upset-final-answer-lane-min-probability 0.15 \
  --upset-final-answer-lane-score-boost 0.08
```

The five-season `score_boost=0.08` report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_final_answer_lane1_single_boost008_diagnostics.json`
has `report_key=historical_recommendation_diagnostic:be5632a578d255b3`.
It generated `720` upset-lane candidates, completed the lane on all `30`
slices, and selected the lane as the final answer in `2` slices. However, the
absolute route regressed versus the prior accepted single-only baseline:
candidate final hit rate was `0.6333333333333333`, ROI was
`-0.012842309586666663`, and upset capture stayed `0`. A strict gate with
`--min-candidate-final-hit-rate 0.66`, `--min-candidate-roi 0.0`, and
`--min-upset-final-answer-lane-selected-candidate-count 1` failed with
`gate_key=historical_recommendation_suite_quality_gate:2a3fdcc3fd6baf1f`.

The weaker `score_boost=0.05` report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_final_answer_lane1_single_boost005_diagnostics.json`
has `report_key=historical_recommendation_diagnostic:c999ba99afdefc36`.
It is accuracy-neutral, matching the accepted `0.6666666666666666` final hit
rate and `0.05017769041333343` ROI, but selects `0` lane candidates. Current
conclusion: the final-answer lane mechanism is wired and measurable, but the
available boost profiles are not ready for default recommendation use.

The lane can also apply quality gates before arbitration. These gates are
opt-in and filter by model edge, calibration, model confidence, odds stability,
volatility, probability, odds cap, and the existing data-quality floor:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_final_answer_lane_quality_edge008_odds5_boost015_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single \
  --candidate-optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --upset-final-answer-lane \
  --upset-final-answer-lane-pass-type 1x1 \
  --upset-final-answer-lane-candidate-limit 24 \
  --upset-final-answer-lane-min-protection-score 0.45 \
  --upset-final-answer-lane-min-probability 0.18 \
  --upset-final-answer-lane-max-decimal-odds 5.0 \
  --upset-final-answer-lane-min-model-edge -0.008 \
  --upset-final-answer-lane-min-calibration-score 0.70 \
  --upset-final-answer-lane-min-model-confidence-score 0.66 \
  --upset-final-answer-lane-min-odds-stability-score 0.72 \
  --upset-final-answer-lane-max-volatility-penalty 0.08 \
  --upset-final-answer-lane-score-boost 0.15
```

The quality-gated five-season report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_final_answer_lane_quality_edge008_odds5_boost015_diagnostics.json`
has `report_key=historical_recommendation_diagnostic:1fef2c6a24ac2580`.
It narrows the lane to `82` candidates, completes `11` lane scenarios, and
selects the lane as final answer once. It still fails absolute promotion gates:
candidate final hit rate is `0.6333333333333333`, ROI is
`-0.022142309586666662`, and upset capture remains `0`. The strict gate
`historical_recommendation_suite_quality_gate:7e538d33fba3664a` fails on
`candidate_final_hit_rate` and `candidate_roi`.

Current conclusion: quality gates are now implemented and measurable, but the
current frozen sample does not justify promoting a cold-lane profile. Next work
should stop increasing static boost and instead audit the one selected quality
lane case plus near-miss lane options to learn which candidate features would
need to change before cold-lane answers can pass absolute accuracy gates.

The upset lane audit turns those selected/near-miss cases into a separate
evidence report. It compares the lane answer against the actual final answer
when the lane was a near miss, or against the best non-lane answer when the lane
won arbitration:

```bash
uv run nutmeg-recommendation-upset-lane-audit \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_quality_edge008_odds5_boost015_audit.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --upset-final-answer-lane \
  --upset-final-answer-lane-pass-type 1x1 \
  --upset-final-answer-lane-candidate-limit 24 \
  --upset-final-answer-lane-min-protection-score 0.45 \
  --upset-final-answer-lane-min-probability 0.18 \
  --upset-final-answer-lane-max-decimal-odds 5.0 \
  --upset-final-answer-lane-min-model-edge -0.008 \
  --upset-final-answer-lane-min-calibration-score 0.70 \
  --upset-final-answer-lane-min-model-confidence-score 0.66 \
  --upset-final-answer-lane-min-odds-stability-score 0.72 \
  --upset-final-answer-lane-max-volatility-penalty 0.08 \
  --upset-final-answer-lane-score-boost 0.15 \
  --min-group-sample-size 2 \
  --top-case-limit 10
```

The report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_quality_edge008_odds5_boost015_audit.json`
has `report_key=historical_upset_lane_audit:996e9a3810322f3d`. It covers
`30` slices: `11` completed lane cases, `10` near misses, `1` selected lane,
and `19` failed lanes with no quality-qualified candidate. The lane candidate
pool has `82` candidates. Among completed lane cases, `3` would have improved
actual profit/loss, `6` would have harmed it, and `2` were unchanged; average
profit/loss delta is `-0.19960310225454583` and average hit-probability delta
is `-0.29104771694624254`.

The useful signal is narrow: all `3` improving near misses sit in the profile
`near_miss + actual_improved + edge_neg_0_01_0 + odds_3_5_5_0`, with average
profit/loss delta `6.532838463999998`. They are Bundesliga 2021-2022,
Bundesliga 2022-2023, and EPL 2022-2023 cases. The selected lane case was
harmful: Ligue 1 2023-2024 selected `Lens vs Lyon away_win` and lost
`-4.3392` profit/loss versus the best non-lane comparison. Current conclusion:
do not promote a global lane boost. The next useful step is a competition/profile
guard that can test the three improving near-miss profile without admitting the
six harmful cases.

The upset lane can now be guarded by the audited competition/profile shape:
minimum odds, maximum odds, minimum model edge, maximum model edge, competition
allowlist, and competition denylist. Defaults are unset, so existing lane
experiments keep their previous behavior unless these flags are passed:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single \
  --candidate-optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --upset-final-answer-lane \
  --upset-final-answer-lane-pass-type 1x1 \
  --upset-final-answer-lane-candidate-limit 24 \
  --upset-final-answer-lane-min-protection-score 0.45 \
  --upset-final-answer-lane-min-probability 0.18 \
  --upset-final-answer-lane-min-decimal-odds 3.5 \
  --upset-final-answer-lane-max-decimal-odds 5.0 \
  --upset-final-answer-lane-min-model-edge -0.008 \
  --upset-final-answer-lane-max-model-edge 0.0 \
  --upset-final-answer-lane-competitions GER_BUNDESLIGA \
  --upset-final-answer-lane-min-calibration-score 0.70 \
  --upset-final-answer-lane-min-model-confidence-score 0.66 \
  --upset-final-answer-lane-min-odds-stability-score 0.72 \
  --upset-final-answer-lane-max-volatility-penalty 0.08 \
  --upset-final-answer-lane-score-boost 0.25
```

The guarded Bundesliga report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_diagnostics.json`
has `report_key=historical_recommendation_diagnostic:17a09b92d6017255`.
It narrows the lane to `2` candidates and selects both as final answers.
The absolute five-season metrics are: final hit rate
`0.6666666666666666`, ROI `0.2894364904133333`, profit/loss
`17.366189424799998`, and upset capture rate `0.0014925373134328358`.
The matching quality gate
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_gate.json`
passes with `gate_key=historical_recommendation_suite_quality_gate:54a7c4112597a705`
using final hit `>= 0.66`, ROI `>= 0.0`, worst competition ROI `>= -0.30`,
and at least one selected lane candidate.

The guarded audit report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_audit.json`
has `report_key=historical_upset_lane_audit:00b63639c5ddd7d2`.
It confirms `2` completed lane cases, `2` selected lanes, `2` actual
improvements, and `0` harms; average profit/loss delta is `7.177764`.
Both selected cases are Bundesliga 2021-2022 / 2022-2023 Mainz upset outcomes.

Current conclusion: the guarded profile is the first cold-lane experiment that
passes the existing absolute gate and improves ROI on the frozen sample.
However, it still lowers hit probability and worsens Brier/log-loss/calibration
versus the no-lane full-matrix baseline, so it remains an opt-in historical
profile rather than a default user recommendation rule.

For promotion, run the stricter profile reference gate. It reruns the same
candidate profile and compares it against the same matrix with upset lane
disabled, so ROI gains cannot hide Brier/log-loss/calibration regression:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single \
  --candidate-optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --upset-final-answer-lane \
  --upset-final-answer-lane-pass-type 1x1 \
  --upset-final-answer-lane-candidate-limit 24 \
  --upset-final-answer-lane-min-protection-score 0.45 \
  --upset-final-answer-lane-min-probability 0.18 \
  --upset-final-answer-lane-min-decimal-odds 3.5 \
  --upset-final-answer-lane-max-decimal-odds 5.0 \
  --upset-final-answer-lane-min-model-edge -0.008 \
  --upset-final-answer-lane-max-model-edge 0.0 \
  --upset-final-answer-lane-competitions GER_BUNDESLIGA \
  --upset-final-answer-lane-min-calibration-score 0.70 \
  --upset-final-answer-lane-min-model-confidence-score 0.66 \
  --upset-final-answer-lane-min-odds-stability-score 0.72 \
  --upset-final-answer-lane-max-volatility-penalty 0.08 \
  --upset-final-answer-lane-score-boost 0.25 \
  --profile-reference-no-upset-lane \
  --min-slice-count 30 \
  --min-comparison-count 30 \
  --min-final-hit-sample-size 30 \
  --min-candidate-final-hit-rate 0.66 \
  --min-candidate-roi 0.0 \
  --min-competition-candidate-roi -0.30 \
  --min-upset-final-answer-lane-selected-candidate-count 1 \
  --min-profile-reference-final-hit-rate-delta 0.0 \
  --min-profile-reference-roi-delta 0.0 \
  --min-profile-reference-profit-loss-delta 0.0 \
  --max-profile-reference-brier-score-delta 0.0 \
  --max-profile-reference-log-loss-delta 0.0 \
  --max-profile-reference-mean-calibration-error-delta 0.0 \
  --min-profile-reference-upset-capture-rate-delta 0.0
```

The strict profile gate report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_strict_profile_gate.json`
has `gate_key=historical_recommendation_suite_quality_gate:00f30c7cc52b792b`
and fails as intended. The guarded profile improves ROI by
`0.23925880000000002`, profit/loss by `14.355528000000001`, and upset capture
rate by `0.0014925373134328358` versus no-lane, but it regresses Brier by
`0.03629450461001202`, log loss by `0.08298307783901859`, and mean calibration
error by `0.03256475053701974`. Current promotion decision: keep this profile
as evidence and do not enable it by default.

The upset lane now also supports an opt-in calibration-preserving arbitration
guard:

```bash
--upset-final-answer-lane-max-hit-probability-deficit 0.20
```

When set, a cold-lane final-answer option may still be generated and audited,
but it cannot win final-answer arbitration if its expected hit probability falls
more than the configured amount below the best non-lane answer. The threshold
is disabled by default, so previous lane experiments remain reproducible unless
this flag is passed.

The guarded Bundesliga profile was rerun with a `0.20` hit-probability-deficit
limit. The diagnostic report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_calibration_guard020_diagnostics.json`
has `report_key=historical_recommendation_diagnostic:828b08a0ceb077be`.
It still finds `2` lane candidates and `2` completed lane options, but both are
blocked by the calibration guard. Final selected lane count falls to `0`, and
the overall metrics return to the no-lane full-matrix baseline: final hit rate
`0.6666666666666666`, ROI `0.05017769041333343`, profit/loss
`3.0106614248000056`, Brier `0.24445905503052764`, log loss
`0.683178240140196`, mean calibration error `0.47697612791196814`, and upset
capture rate `0.0`.

The matching audit report
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_calibration_guard020_audit.json`
has `report_key=historical_upset_lane_audit:4ca23f43bbc05b73`.
Both prior selected Mainz upset cases become near-misses instead of final
answers. They remain useful research evidence (`actual_improvement_count=2`,
`actual_harm_count=0`, average profit/loss delta `7.177764`), but their expected
hit-probability deltas are too negative for this guard:
`-0.524289475240393` and `-0.45265304087019453`.

The profile reference gate with the same guard was saved to
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_calibration_guard020_strict_profile_gate.json`.
It passes with
`gate_key=historical_recommendation_suite_quality_gate:a5134d72dbc423f9`
because all profile-reference deltas are `0.0`, while
`candidate_upset_final_answer_lane_calibration_guard_blocked_option_count=2`.
This is a safety result, not a promotion result: the guard prevents the known
calibration regression by refusing to select the lane, so the next step is to
find a lower-deficit cold profile rather than weaken the guard.

The upset lane audit now includes profile-candidate screening. Composite
profile groups can be promoted to `profile_candidate` only when they meet
explicit evidence thresholds for sample size, actual improvement rate, harm
rate, average profit/loss delta, hit-probability delta, and optional
Brier/log-loss/calibration deltas. The new CLI flags are:

```bash
--min-profile-candidate-sample-size 1 \
--min-profile-candidate-improvement-rate 0.55 \
--max-profile-candidate-harm-rate 0.25 \
--min-profile-candidate-average-profit-loss-delta 0.0 \
--min-profile-candidate-average-hit-probability-delta -0.20 \
--max-profile-candidate-average-brier-score-delta 0.0 \
--max-profile-candidate-average-log-loss-delta 0.0 \
--max-profile-candidate-average-calibration-error-delta 0.0
```

The five-season low-deficit search report was saved to
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_low_deficit_profile_search.json`
with `report_key=historical_upset_lane_audit:3142dcfa4c7768ec`.
It evaluated the quality-gated lane without final-answer boost and found
`82` lane candidates, `11` completed lane observations, `3` actual
improvements, `6` harms, and `2` unchanged cases. No profile passed the strict
candidate thresholds (`profile_candidate_count=0`).

The nearest rejected profile remains
`profile:near_miss:actual_improved:edge_neg_0_01_0:odds_3_5_5_0`.
It has `3` observations, improvement rate `1.0`, harm rate `0.0`, and average
profit/loss delta `6.532838463999998`, but average hit-probability delta is
`-0.41282563598777067` and average Brier/log-loss/calibration deltas are all
positive. Current decision: useful research signal, not an allowed final-answer
profile.

The low-deficit search can now be repeated across a controlled profile grid
instead of one hand-picked lane configuration:

```bash
uv run nutmeg-recommendation-upset-lane-profile-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_low_deficit_v1.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single \
  --optimizer-profile solver \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 80 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --upset-final-answer-lane-pass-type 1x1 \
  --upset-final-answer-lane-candidate-limit 24 \
  --upset-final-answer-lane-min-protection-score 0.45 \
  --upset-final-answer-lane-min-calibration-score 0.70 \
  --upset-final-answer-lane-min-model-confidence-score 0.66 \
  --upset-final-answer-lane-min-odds-stability-score 0.72 \
  --upset-final-answer-lane-max-volatility-penalty 0.08 \
  --competition-group GER_BUNDESLIGA \
  --competition-group EPL \
  --lane-min-probability-values 0.18,0.22 \
  --lane-min-decimal-odds-values none \
  --lane-max-decimal-odds-values 4.5,5.0 \
  --lane-min-model-edge-values=-0.008 \
  --lane-max-model-edge-values 0.0 \
  --lane-max-hit-probability-deficit-values 0.20 \
  --lane-score-boost-values 0.25 \
  --min-group-sample-size 1 \
  --top-case-limit 10 \
  --min-profile-candidate-sample-size 1 \
  --min-profile-candidate-improvement-rate 0.55 \
  --max-profile-candidate-harm-rate 0.25 \
  --min-profile-candidate-average-profit-loss-delta 0.0 \
  --min-profile-candidate-average-hit-probability-delta=-0.20 \
  --max-profile-candidate-average-brier-score-delta 0.0 \
  --max-profile-candidate-average-log-loss-delta 0.0 \
  --max-profile-candidate-average-calibration-error-delta 0.0
```

The first five-season profile-grid report has
`report_key=historical_upset_lane_profile_grid:3f9f48455a3ce147`. It evaluated
`8` league/threshold candidates across Bundesliga and EPL and accepted `0`
profiles under the strict accuracy-first screen. The closest candidate was
Bundesliga with minimum probability `0.18`, maximum odds `5.0`, model edge
range `[-0.008, 0.0]`, hit-probability deficit guard `0.20`, and lane boost
`0.25`; it produced `2` completed lane observations and both were actual
improvements, but the underlying audit still had `profile_candidate_count=0`
because the hit-probability and probability-quality deltas failed the candidate
thresholds. Current decision: keep the grid tool for reproducible threshold
learning, but do not enable any searched upset lane profile by default.

Profile-grid reports now also include aggregated rejection diagnostics:
`rejection_reason_counts`, `profile_rejection_reason_counts`, and
`competition_summary_json`. These fields make wider league scans easier to
review without reading every candidate object by hand.

A six-league narrow grid was saved to
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_six_leagues_narrow_v1.json`
with `report_key=historical_upset_lane_profile_grid:45cf062a032a0c2e`.
It evaluated `12` candidates across EPL, La Liga, Bundesliga, Serie A,
Ligue 1, and Japan J1, and accepted `0` profiles. Global rejection counts were
`no_profile_candidates=12`, `no_lane_candidates=8`, and
`no_completed_lane=8`. The closest candidate remained Bundesliga
`lane_min_model_edge=-0.008`, with `2` completed observations, `2`
improvements, `0` harms, and `0` profile candidates.

League-level diagnostics from the same report:

```text
EPL: 72 lane candidates, 5 completed, 1 improvement, 3 harms
ESP_LA_LIGA: 7 lane candidates, 3 completed, 0 improvements, 2 harms
GER_BUNDESLIGA: 2 lane candidates, 2 completed, 2 improvements, 0 harms
FRA_LIGUE_1: 1 lane candidate, 1 completed, 0 improvements, 1 harm
ITA_SERIE_A: 0 lane candidates
JPN_J1: 0 lane candidates
```

The profile-level rejection counters show the main blockers:
hit-probability delta below threshold, Brier/log-loss/calibration deltas above
threshold, and insufficient improvement rate. Current decision: do not promote
any upset lane profile; next work should either improve the signal quality or
make the grid runner cache/parallelize larger searches before exploring wider
threshold ranges.

Profile-grid runs can now be split into resumable candidate batches and backed
by a per-candidate cache:

```bash
uv run nutmeg-recommendation-upset-lane-profile-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_cache_batch_v1.json \
  --competition-group EPL \
  --competition-group ESP_LA_LIGA \
  --competition-group GER_BUNDESLIGA \
  --competition-group ITA_SERIE_A \
  --competition-group FRA_LIGUE_1 \
  --competition-group JPN_J1 \
  --lane-min-probability-values 0.18 \
  --lane-min-decimal-odds-values none \
  --lane-max-decimal-odds-values 5.0 \
  --lane-min-model-edge-values=-0.008,-0.004 \
  --lane-max-model-edge-values 0.0 \
  --lane-max-hit-probability-deficit-values 0.20 \
  --lane-score-boost-values 0.25 \
  --candidate-start-index 0 \
  --candidate-limit 2 \
  --candidate-cache-dir /tmp/nutmeg_v3119_profile_grid_cache
```

`candidate_start_index` and `candidate_limit` select a stable slice from the
full grid, while `candidate_cache_dir` stores each evaluated candidate under a
hash of its audit options. Re-running the same batch reuses matching candidate
JSON instead of rebuilding the underlying historical audit. Use
`--no-candidate-cache-read` or `--no-candidate-cache-write` when a one-off
fresh run is needed.

The cache smoke reports were saved to
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_cache_batch_v1.json`
and
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_cache_batch_reused_v1.json`.
Both cover candidate indices `[0, 1]` from a `12` candidate six-league narrow
grid. The first run had `cache_hit_count=0`, `cache_miss_count=2`, and
`cache_write_count=2`; the second run had `cache_hit_count=2`,
`cache_miss_count=0`, and `cache_write_count=0`. This is a tooling result only:
the batch still accepted `0` profiles, and no upset lane rule is promoted by
default.

Batch reports can be merged after separate runs:

```bash
uv run nutmeg-recommendation-upset-lane-profile-grid-merge \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_part0_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_part1_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_partial_v1.json
```

The merge report preserves sorted candidate indices, aggregate rejection
diagnostics, aggregate cache counts, source report keys, missing indices, and
whether the merged set covers the full grid. The five-season merge smoke report
has `report_key=historical_upset_lane_profile_grid:6f55525248d4c09f`, merges
candidate indices `[0, 1, 2, 3]` from a `12` candidate six-league narrow grid,
and correctly reports `missing_candidate_indices=[4,5,6,7,8,9,10,11]` with
`is_full_grid=false`. It still accepts `0` profiles; this is only an execution
and review workflow upgrade.

The remaining six-league narrow-grid batches were then run and merged into a
full batch report:

```bash
uv run nutmeg-recommendation-upset-lane-profile-grid-merge \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_part0_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_part1_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_part2_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_part3_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_part4_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_part5_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_full_v1.json
```

The full merged report has
`report_key=historical_upset_lane_profile_grid:95b3760460c165bd`,
`candidate_indices=[0,1,2,3,4,5,6,7,8,9,10,11]`,
`missing_candidate_indices=[]`, `duplicate_candidate_indices=[]`, and
`is_full_grid=true`. It accepted `0` profiles and rejected all `12`, with the
same blockers as the direct narrow-grid run: `no_profile_candidates=12`,
`no_lane_candidates=8`, `no_completed_lane=8`, and profile-level failures on
hit-probability delta plus Brier/log-loss/calibration deltas. The best rejected
candidate remains Bundesliga `lane_min_model_edge=-0.008`, with `2` completed
observations, `2` improvements, `0` harms, and `profile_candidate_count=0`.

The wider six-league grid has now started through the same batch/cache/merge
route. The first four batches cover candidate indices `[0..23]`, which are the
EPL and La Liga portions of the `72` candidate wider grid:

```bash
uv run nutmeg-recommendation-upset-lane-profile-grid-merge \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part0_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part1_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part2_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part3_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_epl_laliga_partial_v1.json
```

The partial report has
`report_key=historical_upset_lane_profile_grid:2f6173f53a87c57e`,
`total_grid_candidate_count=72`, `candidate_count=24`, `is_full_grid=false`,
and `accepted_count=0`. EPL produced `266` lane candidates, `29` completed
lane observations, `12` improvements, `12` harms, and `5` unchanged cases.
The best rejected wider-grid candidate is EPL with `lane_min_probability=0.22`,
`lane_max_decimal_odds=5.0`, and `lane_min_model_edge=-0.012`; it has `5`
completed observations, `3` improvements, `1` harm, and average profit/loss
delta `2.604468801279999`, but still has `profile_candidate_count=0` because
profile-level probability quality gates fail. La Liga remains negative in this
partial scan: `17` completed observations, `0` improvements, `8` harms, and
`9` unchanged cases.

The second wider-grid batch set covers candidate indices `[24..47]`, which are
the Bundesliga and Serie A portions of the same `72` candidate grid:

```bash
uv run nutmeg-recommendation-upset-lane-profile-grid-merge \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part4_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part5_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part6_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part7_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_bundesliga_seriea_partial_v1.json
```

This partial report has
`report_key=historical_upset_lane_profile_grid:9edb43d3c88221f7`,
`candidate_count=24`, and `accepted_count=0`. Bundesliga produced `189` lane
candidates, `20` completed observations, `5` improvements, `7` harms, and `8`
unchanged cases. Serie A produced `186` lane candidates, `14` completed
observations, `2` improvements, `9` harms, and `3` unchanged cases. The best
rejected candidate remains Bundesliga with `lane_min_probability=0.18`,
`lane_max_decimal_odds=5.0`, and `lane_min_model_edge=-0.008`; it has `2`
completed observations, `2` improvements, `0` harms, and average profit/loss
delta `7.177764`, but average hit-probability delta is `-0.4884712580552938`
and `profile_candidate_count=0`.

The final wider-grid batch set covers candidate indices `[48..71]`, which are
the Ligue 1 and Japan J1 portions:

```bash
uv run nutmeg-recommendation-upset-lane-profile-grid-merge \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part8_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part9_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part10_v1.json \
  configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_part11_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_ligue1_j1_partial_v1.json
```

This partial report has
`report_key=historical_upset_lane_profile_grid:f331a09f55e734e6`,
`candidate_count=24`, and `accepted_count=0`. Ligue 1 produced `176` lane
candidates, `13` completed observations, `1` improvement, `12` harms, and `0`
unchanged cases. Japan J1 produced `27` lane candidates, `5` completed
observations, `1` improvement, `1` harm, and `3` unchanged cases.

All `72` wider-grid candidates were then merged into
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_full_v1.json`.
The full report has `report_key=historical_upset_lane_profile_grid:84aa4eb3d496c199`,
`missing_candidate_indices=[]`, `duplicate_candidate_indices=[]`,
`is_full_grid=true`, and `accepted_count=0`. The best rejected candidate is
EPL with `lane_min_probability=0.22`, `lane_max_decimal_odds=5.0`, and
`lane_min_model_edge=-0.012`; it has `5` completed observations, `3`
improvements, `1` harm, average profit/loss delta `2.604468801279999`, and
average hit-probability delta `-0.2796759789427041`. It still has
`profile_candidate_count=0`, so no upset lane profile is promoted by default.

An EPL-only probability-quality repair grid was then run to test whether tighter
hit-probability guards and higher probability thresholds can preserve the EPL
profit signal while reducing probability-quality regression. The search covered
`48` candidates with `lane_min_probability` values `0.22`, `0.24`, and `0.26`,
maximum odds `4.5` and `5.0`, model-edge floors `-0.012` and `-0.008`, and
hit-probability deficit guards `0.08`, `0.12`, `0.16`, and `0.20`.

The full repair report was saved to
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_epl_quality_repair_full_v1.json`
with `report_key=historical_upset_lane_profile_grid:fe5d3f5420e3a1e0`.
It produced `48` rejected candidates and `0` accepted profiles. The best
candidate stayed the same shape as the wider-grid EPL candidate:
`lane_min_probability=0.22`, `lane_max_decimal_odds=5.0`,
`lane_min_model_edge=-0.012`, and `hit_probability_deficit_guard=0.20`. It has
`5` completed observations, `3` improvements, `1` harm, average profit/loss
delta `2.604468801279999`, and average hit-probability delta
`-0.2796759789427041`.

The repair grid did not reduce the profile-quality failures: all `48` closest
profiles failed Brier, log-loss, calibration, and hit-probability delta gates.
Current decision: tighter guards alone do not repair the EPL cold-lane signal.
The next useful work is signal calibration, such as adding an EPL-specific
probability-quality adjustment or a separate score component that penalizes the
observed hit-probability gap before the candidate reaches profile screening.

That signal-calibration component now exists as
`nutmeg.recommendations.upset_signal_calibration`. It turns observed cold-profile
metrics such as average hit-probability delta, Brier delta, log-loss delta, and
calibration-error delta into a `risk_score` and `reliability_score`. Candidate
ranking now subtracts `upset_signal_calibration_risk`, exposes
`upset_signal_reliability` for diagnostics, and keeps the component internal to
the recommendation engine. The historical upset final-answer lane can also be
guarded before candidate selection with
`--upset-final-answer-lane-max-signal-calibration-risk` and
`--upset-final-answer-lane-min-signal-reliability-score`; the same options are
available in the upset-lane audit, profile-grid, historical diagnostics, and
suite-gate CLIs. This is a safety rail for accuracy-first cold-lane research,
not a default promotion of any EPL profile.

A focused stop-loss verification was then run against the known EPL
best-rejected cold-lane shape instead of widening the grid again. The report
was saved to
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_epl_signal_calibration_guard_v1.json`
with `report_key=historical_upset_lane_profile_grid:9c92dbfc4c4b3313`.
It covers the full 30-slice football-data.co.uk suite but only one EPL grid
candidate: `lane_min_probability=0.22`, `lane_max_decimal_odds=5.0`,
`lane_min_model_edge=-0.012`, `lane_max_hit_probability_deficit=0.20`,
`max_signal_calibration_risk=0.20`, and `min_signal_reliability_score=0.80`.
The guard reduced lane exposure for that shape to `13` lane candidates and `5`
completed observations, but the candidate was still rejected with
`profile_candidate_count=0`. The closest profile still failed hit-probability,
Brier, log-loss, and calibration gates.

Current decision: stop the cold-lane profile-search loop. The signal calibration
guard is useful as an internal safety rail, but the historical evidence still
does not support promoting an EPL cold profile. The next accuracy work should
move back to prediction-model and sample-quality improvements rather than
another upset-threshold grid.

The first prediction-quality follow-up is a historical probability calibration
report, exposed through `nutmeg-accuracy-historical-probability-calibration`.
It reads frozen historical slices and groups observations by model,
calibration version, competition, market, outcome, and probability bucket. The
report emits expected calibration error, Brier score, log loss, and optional
deltas against the stored market-implied probability baseline:

```bash
uv run nutmeg-accuracy-historical-probability-calibration \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_v1.json \
  --min-bucket-sample-size 30 \
  --min-group-sample-size 120 \
  --max-expected-calibration-error 0.08 \
  --max-brier-score-delta-vs-market 0.02 \
  --max-log-loss-delta-vs-market 0.05 \
  --top-group-limit 12
```

The football-data.co.uk core-suite report has
`report_key=historical_probability_calibration:b7cbd05db3b74567`. It covers
`30` slices, `10,738` fixtures, and `32,214` 1X2 observations with
`overall_expected_calibration_error=0.020886649543952595`,
`overall_brier_score=0.19450693189653426`, and
`overall_log_loss=0.5734563773558601`. No group exceeded the configured
calibration or market-delta thresholds. The most miscalibrated groups are still
modest, led by Serie A away wins with ECE `0.04035417786328266`.

Interpretation: the current frozen football-data.co.uk suite is primarily a
no-vig market-implied probability benchmark, not an independent predictive
model. It is good enough as a calibration baseline and guardrail. The next
modeling step should compare a walk-forward Poisson/Dixon-Coles-compatible
score-grid model against this benchmark and only then fit league/market
calibration transforms.

The calibration layer now also has a shadow transform runner. It learns
competition/outcome/probability-bucket actual frequencies on training seasons,
applies the transform only to the latest held-out season, and compares the
calibrated candidate against the original frozen probabilities:

```bash
uv run nutmeg-accuracy-historical-probability-calibration-transform \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_transform_v1.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50 \
  --min-calibrated-probability 0.01 \
  --max-calibrated-probability 0.95 \
  --max-brier-score-delta 0.0 \
  --max-log-loss-delta 0.0 \
  --max-expected-calibration-error-delta 0.0
```

The report has
`report_key=historical_probability_calibration_transform:d2faccb727c77702`.
It covers all six competitions, `2,132` held-out fixtures, and `104` usable
calibration buckets. Overall, the transform slightly regressed the no-vig
baseline: hit rate `0.5337711069418386` vs `0.5361163227016885`, Brier
`0.5795079692472372` vs `0.5791437500706367`, log loss
`0.9739091280225523` vs `0.9730922524293841`, and ECE
`0.03817676000003683` vs `0.03737794058402302`.

Two league holdouts did pass the non-regression gate: La Liga and Serie A. EPL,
Ligue 1, Bundesliga, and J1 were rejected due to hit/Brier/log-loss/ECE
regressions. Current decision: keep the calibration transform shadow-only. It
is useful evidence for per-competition calibration profiles, but the aggregate
result does not support a global default calibration transform.

Accepted per-competition calibration profiles can be pushed through a
final-answer gate with
`nutmeg-recommendation-historical-probability-calibration-profile-gate`. The
gate reruns the transform, selects only competitions whose transform holdout
decision is `accepted`, applies the calibration only to those competitions'
held-out slices, and then compares baseline versus calibrated final answers
with the same optimizer profile:

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_profile_gate_v1.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --derive-market-context-signals \
  --min-final-hit-sample-size 2 \
  --no-fail-process
```

The report has
`report_key=historical_probability_calibration_profile_gate:4a34bf07c90a46d7`.
It selected `ESP_LA_LIGA` and `ITA_SERIE_A`, rejected the other four
competitions, adjusted `760` held-out fixtures, and skipped none. The
final-answer gate rejected the profile: suite status was `regressed`, final hit
rate delta was `-0.5`, ROI delta was `-0.51`, profit/loss delta was `-2.04`,
Brier delta was `0.35321256192032685`, log-loss delta was
`0.8726533265588203`, and mean calibration error delta was
`0.38340428675644883`.

Current decision: even accepted single-match calibration profiles must remain
shadow-only until they also pass the final-answer gate. The next calibration
work should search narrower profiles, such as blend, bucket, outcome, or
odds-band profiles, and keep the same final-answer gate as the promotion
barrier.

That narrower search is available through
`nutmeg-recommendation-historical-probability-calibration-profile-grid`. It
enumerates outcome bands, probability bands, decimal-odds bands, and blend
weights, then sends each profile through the same shadow final-answer gate. The
grid can also require that a candidate actually changes the final answer, which
prevents no-op probability tweaks from looking like promotion candidates:

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_profile_grid_v1.json \
  --blend-weights 0.25,0.50 \
  --target-outcome-groups home_win,draw,away_win \
  --probability-bands 0.00:0.35,0.35:0.65,0.65:1.00 \
  --decimal-odds-bands all \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --derive-market-context-signals \
  --min-final-hit-sample-size 2 \
  --min-final-hit-rate-delta 0.0 \
  --min-final-answer-changed-count 1 \
  --max-brier-score-delta 0.0 \
  --max-log-loss-delta 0.0 \
  --max-mean-calibration-error-delta 0.0 \
  --no-fail-process
```

The strict report has
`report_key=historical_probability_calibration_profile_grid:0a9b9d01107fb223`.
It covered `30` slices, `10,738` fixtures, and `18` profile candidates. No
candidate was accepted once `min_final_answer_changed_count=1` was enforced:
`17` candidates failed because the final answer was unchanged, `2` high-draw
profiles adjusted no fixtures, and the only profile that changed a final answer
regressed final hit rate by `-0.5`, ROI by `-0.55`, profit/loss by `-2.2`,
Brier by `0.3557566506573265`, log loss by `0.8899590598308735`, and mean
calibration error by `0.3630651064045382`.

Current decision: narrow probability calibration profiles remain shadow-only
and should not be promoted. The useful learning is negative but important:
current bucket calibration either does not affect the final answer, or hurts it
when it does. The next accuracy work should move back toward better pre-match
features and model probability quality, while keeping this final-answer gate as
the promotion barrier.

The runtime candidate model now keeps the probability basis explicit:
`model_probability` stores the raw model estimate, `calibrated_probability`
stores an optional calibrated estimate, `probability_source` records whether
the candidate is currently using the raw or calibrated value, and `probability`
remains the effective value consumed by scoring and parlay math. Migration
`db/migrations/0045_recommendation_candidate_probability_basis.sql` adds the
same fields to stored recommendation candidates and candidate-pool replay
items.

`nutmeg.recommendations.candidate_probability_calibration` provides the first
runtime adapter for that basis. It applies a calibration profile only to
complete 1X2 candidate groups, adjusts matching outcomes from historical
probability buckets, renormalizes home/draw/away back to 1.0, and records the
bucket/profile metadata on each adjusted candidate. The adapter supports
`active` mode, which changes the effective probability, and `shadow` mode,
which stores the calibrated estimate without changing the recommendation path.
It is infrastructure for future admitted calibration profiles, not a default
production profile.

Historical shadow evidence can be exported into that runtime shape with
`nutmeg-recommendation-historical-probability-calibration-profile-artifact`.
The command reruns the historical profile gate, emits a
`CandidateProbabilityCalibrationProfile` only when the final-answer gate passes
by default, and writes a separate profile JSON when `--profile-output-path` is
provided:

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-artifact \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_profile_artifact_v1.json \
  --profile-output-path configs/recommendations/profiles/football_data_co_uk_core_5_seasons_probability_calibration_profile_shadow_v1.json \
  --profile-mode shadow \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --derive-market-context-signals \
  --min-final-hit-sample-size 2
```

Use `--allow-failed-final-answer-gate` only for diagnostics. A generated
profile remains an internal artifact until a later rolling-admission step
allows `active` mode.

That rolling-admission step is available through
`nutmeg-recommendation-historical-probability-calibration-profile-rolling-admission`.
It reruns the profile artifact over the full slice set, then over competition,
cumulative season-cutoff, and rolling-season folds. The command only writes a
runtime profile to `--profile-output-path` when the overall final-answer gate
and the required active folds pass:

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-rolling-admission \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_profile_rolling_admission_v1.json \
  --profile-output-path configs/recommendations/profiles/football_data_co_uk_core_5_seasons_probability_calibration_profile_active_candidate_v1.json \
  --profile-mode active \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --derive-market-context-signals \
  --min-final-hit-sample-size 2 \
  --min-active-competition-fold-count 1 \
  --min-active-season-cutoff-fold-count 1 \
  --min-active-rolling-fold-count 1
```

This remains an internal staging gate. It does not change the default runtime
profile, expose the strategy to users, contact data providers, use VPS, or
perform betting actions.

The persisted benchmark quality gate can also consume that rolling-admission
artifact. This keeps probability-calibration profile evidence visible in the
same periodic gate/cycle used for final-answer accuracy, without switching the
default profile:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --probability-calibration-profile-rolling-admission-report-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_profile_rolling_admission_v1.json \
  --require-probability-calibration-profile-rolling-admission \
  --min-probability-calibration-profile-overall-adjusted-fixture-count 1 \
  --min-probability-calibration-profile-overall-bucket-count 1 \
  --max-probability-calibration-profile-failed-fold-count 0 \
  --min-probability-calibration-profile-active-competition-fold-count 1 \
  --min-probability-calibration-profile-active-season-cutoff-fold-count 1 \
  --min-probability-calibration-profile-active-rolling-fold-count 1
```

The cycle runner exposes the same options with a `--gate-` prefix and carries
the admission key/status, candidate/shadow allowance, profile mode, overall
gate result, adjusted-fixture count, bucket count, failed folds, and active
fold counts into the cycle summary.

That walk-forward Poisson benchmark is now available through
`nutmeg-accuracy-historical-poisson-walk-forward`. It uses only previously
completed matches in the same competition, estimates
`lambda_home` / `lambda_away` from rolling team attack and defense strength,
builds the Poisson score grid, derives 1X2 probabilities, and compares the
result against the frozen no-vig market baseline:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_poisson_walk_forward_v1.json \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --prediction-sample-limit 20
```

The report has `report_key=historical_poisson_walk_forward:2cc340200767a5ac`.
It covers `10,092` validation fixtures and skips `646` cold-start fixtures
(`360` insufficient prior matches, `286` insufficient team samples). The
Poisson baseline currently trails the no-vig market baseline: hit rate
`0.5073325406262386` vs `0.5273483947681332`, Brier
`0.6057444149168055` vs `0.5844665736444945`, log loss
`1.0130755990679576` vs `0.9815234496797939`, and ECE
`0.027728941457527193` vs `0.01103425592844241`.

Current decision: keep this Poisson model as a shadow benchmark only. The next
accuracy step should improve the independent score model before recommendation
promotion, likely by adding stronger recency weighting, home/away split
strength, draw-rate correction, and then a Dixon-Coles low-score adjustment
rather than calibrating this weaker baseline into the final answer path.

The walk-forward CLI now supports model-layer ablations through
`--lambda-method`, `--recency-half-life-days`, `--home-away-split-weight`, and
`--draw-correction-weight`. A small real-history check showed that venue split
and recency weighting did not improve the current rolling-strength baseline,
while draw-rate correction helped calibration and loss metrics modestly:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_poisson_walk_forward_draw_correction_v1.json \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --draw-correction-weight 0.40 \
  --model-version poisson-walk-forward-team-strength-draw-corrected-v3.1 \
  --feature-version rolling-results-team-strength-v1 \
  --calibration-version draw-rate-correction-v3.1 \
  --prediction-sample-limit 20
```

The draw-corrected report has
`report_key=historical_poisson_walk_forward:841ac3b530358e1f`. It keeps the
same `10,092` validation fixtures. Against the previous Poisson report, Brier
improves from `0.6057444149168055` to `0.6043922102783101`, log loss from
`1.0130755990679576` to `1.0112627965553094`, ECE from
`0.027728941457527193` to `0.021687848218462428`, and hit rate from
`0.5073325406262386` to `0.5078279825604439`.

It still trails the market baseline: Brier delta `0.019925636633815635`, log
loss delta `0.029739346875515493`, hit-rate delta `-0.019520412207689297`, and
ECE delta `0.010653592290020018`. Current decision: draw correction is worth
keeping as a modeling candidate, but the independent score model remains
shadow-only. The next high-value step is a Dixon-Coles low-score adjustment or
learned league-level draw correction, evaluated through the same walk-forward
report before any recommendation-path promotion.

The same walk-forward report now supports a Dixon-Coles low-score score-grid
variant with `--score-grid-family dixon_coles_low_score` and
`--dixon-coles-rho`. A rho check over the 30-slice suite showed the most useful
candidate at `rho=-0.05` combined with the existing `0.40` draw correction:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_dixon_coles_low_score_draw_correction_v1.json \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --score-grid-family dixon_coles_low_score \
  --dixon-coles-rho -0.05 \
  --draw-correction-weight 0.40 \
  --model-version dc-low-score-walk-forward-draw-corrected-v3.1 \
  --feature-version rolling-results-team-strength-v1 \
  --calibration-version dc-low-score-draw-rate-correction-v3.1 \
  --prediction-sample-limit 20
```

The report has `report_key=historical_poisson_walk_forward:2d013c7606569252`.
Compared with the draw-corrected Poisson candidate, Brier improves slightly from
`0.6043922102783101` to `0.604297481894781` and ECE improves from
`0.021687848218462428` to `0.019689866978712472`. Log loss is slightly worse
than draw-only (`1.0114250769828232` vs `1.0112627965553094`) and hit rate is
also slightly lower (`0.5075307173999207` vs `0.5078279825604439`).

Current decision: Dixon-Coles low-score tau is useful and now wired into the
benchmark harness, but it is not a promotion signal yet. It still trails the
market baseline on every core overall metric. The next modeling step should
learn league-level draw or rho parameters on rolling training windows instead
of hand-picking one global rho.

League-level parameter learning is now available through
`nutmeg-accuracy-historical-poisson-parameter-learning`. It groups historical
slices by competition, uses earlier seasons to select a draw/rho candidate, and
then evaluates only the held-out latest season for that competition:

```bash
uv run nutmeg-accuracy-historical-poisson-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_league_parameter_learning_v1.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --selection-metric brier_score_delta \
  --candidate-draw-correction-weights 0.0,0.4 \
  --candidate-dixon-coles-rhos=-0.1,-0.05,0.05 \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30
```

The report has
`report_key=historical_poisson_parameter_learning:5e51516b78a44d66`. It learned
parameters for all six competitions and validated on `2,062` held-out fixtures.
Selected candidates varied by league, but all remained shadow-only. Overall
holdout metrics still trail the no-vig baseline: hit rate `0.5155189136760426`
vs `0.5368574199806013`, Brier `0.5963543439254799` vs
`0.5790496105941644`, log loss `0.9979609649544126` vs
`0.9730819333695456`, and ECE `0.03948378116718108` vs
`0.03676958063070931`.

Current decision: the parameter-learning harness is useful because it prevents
same-sample self-selection, but the current independent model still lacks the
signal needed to beat the market baseline. The next accuracy work should add
stronger football features, such as team form splits, rest/travel congestion,
injury/lineup placeholders, and odds movement features, before further
promotion attempts.

The parameter-learning harness now also supports explicit recency and
home/away split candidate grids, plus a regression fix for `rho=0.0`
Dixon-Coles candidates. That zero-rho value is an important no-correlation
control and is now preserved instead of being replaced by the default
`-0.05`.

```bash
uv run nutmeg-accuracy-historical-poisson-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --lambda-method enhanced_weighted_home_away \
  --candidate-draw-correction-weights 0,0.4 \
  --candidate-dixon-coles-rhos=-0.15,-0.1,-0.05,0,0.05 \
  --candidate-recency-half-life-days none,180 \
  --candidate-home-away-split-weights 0,0.35 \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --min-validation-sample-size 100 \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_dixon_recency_homeaway_parameter_learning_v1.json
```

The report has
`report_key=historical_poisson_parameter_learning:8a927bc93bf9af94`. It learned
all six competitions over `48` candidates and `2,062` held-out validation
fixtures. Selected candidates included league-specific Dixon-Coles rho values:
EPL selected `rho=0.05` with `recency=180` and `homeaway=0.35`; La Liga and
Bundesliga selected `rho=-0.10`; Ligue 1 selected `rho=-0.05`; Serie A selected
`rho=-0.15`; J1 selected the now-preserved `rho=0.0` control.

Current decision: this confirms that league-specific rho selection is wired and
auditable, but the independent score model still does not beat the no-vig
market baseline. Overall holdout deltas remain negative for promotion:
hit-rate delta `-0.01988360814742962`, Brier delta
`0.017899808518411997`, log-loss delta `0.026275751597732877`, and ECE delta
`0.002622442220782048`. Keep this report as research evidence only; do not use
it as the default recommendation model.

The walk-forward benchmark also supports a shadow
`shrunken_weighted_home_away` lambda method. It starts from the enhanced
home/away attack-defense estimate, then shrinks both lambdas back toward the
league home/away scoring baseline according to each team's available sample
count. This guards against small-sample goal-rate extremes while keeping the
output compatible with the same Poisson and Dixon-Coles score-grid path:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_shrunken_homeaway_walk_forward_v1.json \
  --lambda-method shrunken_weighted_home_away \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --home-away-split-weight 0.50 \
  --strength-shrinkage-matches 16 \
  --draw-correction-weight 0.40
```

The direct report has
`report_key=historical_poisson_walk_forward:56dfb35da3e2f13d` over `10,092`
validation fixtures. It remains worse than the no-vig market baseline: hit rate
`0.503170828378914` vs `0.5273483947681332`, Brier
`0.6071231825444314` vs `0.5844665736444945`, log loss
`1.014332843568345` vs `0.9815234496797939`, and ECE
`0.019920656218396827` vs `0.01103425592844241`.

The league-level parameter-learning harness can search the shrinkage strength
as well:

```bash
uv run nutmeg-accuracy-historical-poisson-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_shrunken_homeaway_parameter_learning_v1.json \
  --lambda-method shrunken_weighted_home_away \
  --disable-dixon-coles-candidates \
  --candidate-draw-correction-weights 0.4 \
  --candidate-recency-half-life-days none,90,180 \
  --candidate-home-away-split-weights 0,0.25,0.5 \
  --candidate-strength-shrinkage-matches 0,4,8,16,32 \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --selection-metric brier_score_delta
```

The holdout report has
`report_key=historical_poisson_parameter_learning:cc5d87111e84d2bd`. It learned
all six competitions over `45` candidates and `2,062` validation fixtures. The
selected candidates improved ECE versus the market baseline
(`0.03380747875681132` vs `0.03676958063070931`), but hit rate, Brier, and log
loss were still worse: hit-rate delta `-0.016973811833171593`, Brier delta
`0.017853313509368585`, and log-loss delta `0.025729941585761362`.

Current decision: keep sample shrinkage as an auditable shadow modeling
candidate only. It reduces some calibration error in holdout but does not
improve the decisive accuracy metrics, so it must not enter the final-answer
gate, rolling admission, runtime profile, or default recommendation path.

The walk-forward benchmark now also supports `ema_form_adjusted`, a shadow
form-signal candidate that uses an exponentially weighted recent-results
readout instead of the flat form window. It records the weighted form values
and half-life in sampled predictions and lambda metadata:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_ema_form_walk_forward_v1.json \
  --lambda-method ema_form_adjusted \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --form-window-matches 8 \
  --ema-form-half-life-matches 2.5 \
  --form-adjustment-weight 0.05 \
  --draw-correction-weight 0.40
```

The direct report has
`report_key=historical_poisson_walk_forward:5dc85381f61194ef` over `10,092`
validation fixtures. It is still worse than the market baseline: hit rate
`0.5077288941736029` vs `0.5273483947681332`, Brier
`0.6046293875247349` vs `0.5844665736444945`, log loss
`1.0118809846457184` vs `0.9815234496797939`, and ECE
`0.023136779439429198` vs `0.01103425592844241`.

The parameter-learning harness can search EMA form half-life and adjustment
weight:

```bash
uv run nutmeg-accuracy-historical-poisson-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_ema_form_parameter_learning_v1.json \
  --lambda-method ema_form_adjusted \
  --disable-dixon-coles-candidates \
  --candidate-draw-correction-weights 0.4 \
  --candidate-form-adjustment-weights 0,0.03,0.06 \
  --candidate-ema-form-half-life-matches 1.5,3,6 \
  --candidate-home-away-split-weights 0,0.25 \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --selection-metric brier_score_delta
```

The holdout report has
`report_key=historical_poisson_parameter_learning:b40f93be6236cfa1`. It learned
all six competitions over `18` candidates and `2,062` validation fixtures.
Overall holdout deltas were negative: hit-rate delta
`-0.020368574199805978`, Brier delta `0.017477499811174413`, log-loss delta
`0.02505075403543877`, and ECE delta `0.004577506240668147`.

Current decision: keep EMA form as negative shadow evidence. Recent-results
form, even with exponential weighting and league-level holdout selection, is
not enough to improve the independent score model and must not be promoted.

The walk-forward benchmark also supports a shadow
`season_weighted_home_away` lambda method. It keeps the enhanced home/away
attack-defense estimator, carries slice season metadata into historical result
samples, and down-weights prior-season matches through `--prior-season-weight`
while reporting current-season and prior-season sample counts:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_season_weighted_homeaway_walk_forward_v1.json \
  --lambda-method season_weighted_home_away \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --prior-season-weight 0.35 \
  --draw-correction-weight 0.40 \
  --model-version poisson-walk-forward-season-weighted-homeaway-v3.1 \
  --feature-version rolling-results-season-weighted-team-strength-v1 \
  --calibration-version draw-rate-correction-v3.1
```

The direct report has
`report_key=historical_poisson_walk_forward:328cf41d5a2ca041` over `10,092`
validation fixtures. It remains worse than the market baseline: hit rate
`0.5068370986920333` vs `0.5273483947681332`, Brier
`0.6045842748037896` vs `0.5844665736444945`, log loss
`1.0115588497403782` vs `0.9815234496797939`, and ECE
`0.02240207049918595` vs `0.01103425592844241`.

The parameter-learning harness can search the prior-season weight on holdout
seasons:

```bash
uv run nutmeg-accuracy-historical-poisson-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_season_weighted_homeaway_parameter_learning_v1.json \
  --lambda-method season_weighted_home_away \
  --disable-dixon-coles-candidates \
  --candidate-draw-correction-weights 0.4 \
  --candidate-prior-season-weights 0.15,0.35,0.55,0.75,1.0 \
  --candidate-home-away-split-weights 0,0.25 \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --selection-metric brier_score_delta
```

The holdout report has
`report_key=historical_poisson_parameter_learning:bb5e1ac81f09ca06`. It learned
all six competitions over `10` candidates and `2,062` validation fixtures.
Overall holdout deltas were still negative: hit-rate delta
`-0.021823472356934936`, Brier delta `0.01748070353879594`,
log-loss delta `0.025242404643045946`, and ECE delta
`0.0004404169183554879`.

Current decision: keep season weighting as negative shadow evidence. Simple
same-season preference is not enough to improve the independent score model,
so it must not enter the final-answer gate, rolling admission, runtime
profile, or default recommendation path.

The walk-forward benchmark also supports `hierarchical_weighted_home_away`, a
shadow team-strength candidate that shrinks each team's attack and defense
strengths toward the league baseline before composing the fixture lambdas. This
differs from `shrunken_weighted_home_away`, which shrinks the final lambdas
after the matchup estimate has already been produced:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_hierarchical_homeaway_walk_forward_v1.json \
  --lambda-method hierarchical_weighted_home_away \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --home-away-split-weight 0.50 \
  --strength-shrinkage-matches 16 \
  --draw-correction-weight 0.40 \
  --model-version poisson-walk-forward-hierarchical-homeaway-v3.1 \
  --feature-version rolling-results-hierarchical-team-strength-v1 \
  --calibration-version draw-rate-correction-v3.1
```

The direct report has
`report_key=historical_poisson_walk_forward:a2f9e2cebff070dc` over `10,092`
validation fixtures. It still trails the market baseline: hit rate
`0.5052516845025763` vs `0.5273483947681332`, Brier
`0.6060744634399309` vs `0.5844665736444945`, log loss
`1.0128672704954003` vs `0.9815234496797939`, and ECE
`0.018210936593020085` vs `0.01103425592844241`.

The parameter-learning harness can search the hierarchical shrinkage strength
on holdout seasons:

```bash
uv run nutmeg-accuracy-historical-poisson-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_hierarchical_homeaway_parameter_learning_v1.json \
  --lambda-method hierarchical_weighted_home_away \
  --disable-dixon-coles-candidates \
  --candidate-draw-correction-weights 0.4 \
  --candidate-home-away-split-weights 0,0.25 \
  --candidate-strength-shrinkage-matches 0,4,8,16,32 \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --selection-metric brier_score_delta
```

The holdout report has
`report_key=historical_poisson_parameter_learning:22dc985a449d0051`. It learned
all six competitions over `10` candidates and `2,062` validation fixtures.
Overall holdout deltas stayed negative: hit-rate delta
`-0.01891367604267702`, Brier delta `0.017693039458025805`,
log-loss delta `0.025243681207295254`, and ECE delta
`0.0011185969355606215`.

Current decision: keep hierarchical attack/defense shrinkage as negative
shadow evidence. It can reduce some overconfident extremes, but it does not
improve decisive accuracy metrics and must not enter the final-answer gate,
rolling admission, runtime profile, or default recommendation path.

The walk-forward benchmark now includes a `form_rest_adjusted` lambda method
for shadow testing coarse pre-match features that are available in the frozen
historical slices. It starts from the enhanced home/away lambda estimate, adds
recent form points, recent goal-difference, and rest-day/congestion adjustment
factors, and records those inputs in both the sampled prediction payload and
lambda metadata:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_form_rest_feature_ablation_v1.json \
  --lambda-method form_rest_adjusted \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --draw-correction-weight 0.40 \
  --form-window-matches 6 \
  --form-adjustment-weight 0.05 \
  --rest-adjustment-weight 0.0 \
  --rest-reference-days 6.0 \
  --max-lambda-adjustment 0.25 \
  --model-version poisson-walk-forward-form-rest-shadow-v3.1 \
  --feature-version rolling-results-form-rest-v1 \
  --calibration-version draw-rate-correction-v3.1 \
  --prediction-sample-limit 20
```

The report has `report_key=historical_poisson_walk_forward:7197442bc806ff75`.
It covers the same `10,092` validation fixtures and `646` cold-start skips.
The best nonzero form/rest candidate from the small grid did not improve the
draw-corrected Poisson baseline: hit rate `0.5071343638525565`, Brier
`0.6046054175361606`, log loss `1.0118793885213073`, and ECE
`0.0232334508477062`. The prior zero-weight draw-corrected baseline remains
better at Brier `0.6043922102783101`, log loss `1.0112627965553094`, and ECE
`0.021687848218462428`.

Current decision: keep `form_rest_adjusted` as an auditable shadow feature
harness only. Coarse recent-results form and rest-day signals are not enough to
promote the independent score model. Injury/lineup and odds-movement features
remain placeholders until the sample set contains structured lineup/news inputs
or pre-match odds time series rather than only frozen market snapshots.

The walk-forward benchmark now also supports a strictly shadow
`prematch_feature_adjusted` lambda method. It starts from the
`form_rest_adjusted` base lambda estimate, reads
`FeatureSnapshot.features_json.prematch_context`, and conservatively adjusts
`lambda_home` / `lambda_away` using odds movement, lineup strength,
availability risk, draw risk, and semantic risk. The output records the
pre-adjustment lambdas, adjustment factors, reason codes, and readout payload so
the candidate can be audited before any promotion discussion:

```bash
uv run nutmeg-accuracy-historical-poisson-walk-forward \
  --suite-manifest configs/recommendations/historical_suites/nutmeg_enriched_prematch_feature_suite.json \
  --lambda-method prematch_feature_adjusted \
  --min-prior-matches 6 \
  --min-team-matches 2 \
  --max-training-results 60 \
  --min-prematch-feature-data-quality-score 80 \
  --prematch-feature-odds-movement-weight 0.60 \
  --prematch-feature-lineup-strength-weight 0.08 \
  --prematch-feature-availability-risk-weight 0.03 \
  --prematch-feature-draw-risk-weight 0.04 \
  --prematch-feature-semantic-risk-weight 0.02 \
  --max-prematch-feature-lambda-adjustment 0.12
```

Current decision: this is a core prediction-quality experiment only. Missing or
low-quality feature snapshots are skipped by default, and the method remains
shadow-only; it does not change the default recommendation path, the final
answer arbitrator, or any runtime profile. Promotion would require the existing
sample readiness, rolling admission, benchmark gate, and final-answer no-harm
checks to pass on real frozen samples.

The league-level parameter-learning harness can now include
`prematch_feature_adjusted` candidates as well. It searches conservative
prematch odds-movement, draw-risk, and max-lambda-adjustment weights on
training seasons, then validates only on the latest held-out season.

```bash
uv run nutmeg-accuracy-historical-poisson-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_prematch_lambda_parameter_learning_v1.json \
  --lambda-method prematch_feature_adjusted \
  --disable-dixon-coles-candidates \
  --candidate-draw-correction-weights 0.4 \
  --candidate-prematch-feature-odds-movement-weights 0,0.1,0.25,0.5 \
  --candidate-prematch-feature-draw-risk-weights 0,0.01 \
  --candidate-max-prematch-feature-lambda-adjustments 0.02,0.04,0.08 \
  --min-prematch-feature-data-quality-score 70 \
  --prematch-feature-lineup-strength-weight 0 \
  --prematch-feature-availability-risk-weight 0 \
  --prematch-feature-semantic-risk-weight 0
```

Generated evidence:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_sample_readiness_market_movement_v1.json`
is `accepted` for market-movement readiness with `600` fixtures, `25`
competition-season cells, and `sample_ready_allowed=true`. The direct
prematch-lambda walk-forward report is
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_prematch_lambda_walk_forward_v1.json`
with `report_key=historical_poisson_walk_forward:f515fa36b49b483f`.
The holdout parameter-learning report is
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_prematch_lambda_parameter_learning_v1.json`
with `report_key=historical_poisson_parameter_learning:c21d0631112f4895`.

Current decision: do not promote this prematch-lambda candidate. On the
25-slice market-feature suite the direct candidate improves hit count by one
and improves ECE, but Brier and log loss are slightly worse than the form/rest
control. The holdout-selected candidates are still worse than the no-vig market
baseline overall: hit-rate delta `-0.07216494845360821`, Brier delta
`0.08808789778821091`, and log-loss delta `0.1330986332277656`. Keep the
interface and reports as negative evidence; the next useful modeling work
should add real lineup/availability/news context or improve the independent
team-strength model before more prematch-lambda tuning.

The league-level parameter-learning harness can also evaluate
`form_rest_adjusted` candidates on true holdout seasons. Use this when testing
coarse historical form/rest features so the candidate is chosen on training
seasons and judged only on the latest held-out season:

```bash
uv run nutmeg-accuracy-historical-poisson-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_form_rest_parameter_learning_v1.json \
  --lambda-method form_rest_adjusted \
  --disable-dixon-coles-candidates \
  --candidate-draw-correction-weights 0.0,0.4 \
  --candidate-form-adjustment-weights 0.0,0.03,0.05 \
  --candidate-rest-adjustment-weights 0.0,0.02 \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --selection-metric brier_score_delta \
  --min-prior-matches 60 \
  --min-team-matches 5 \
  --max-training-results 380 \
  --max-goals 8 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --form-window-matches 6 \
  --rest-reference-days 6.0 \
  --max-lambda-adjustment 0.25 \
  --model-version-prefix learned-form-rest-shadow-v3.1 \
  --feature-version rolling-results-form-rest-v1 \
  --calibration-version-prefix learned-form-rest-draw-v3.1
```

The report has
`report_key=historical_poisson_parameter_learning:4d275877a21441b4`. It learned
all six competitions over `2,062` held-out fixtures with `12` candidates. The
selected weights were mostly zero: `poisson_draw_0_4_form_0_0_rest_0_0` was
selected for three competitions, `poisson_draw_0_4_form_0_0_rest_0_02` for two,
and `poisson_draw_0_4_form_0_03_rest_0_0` for one.

Overall holdout metrics still trail the no-vig market baseline: hit rate
`0.5126091173617847` vs `0.5368574199806013`, Brier `0.5963756626118645` vs
`0.5790496105941644`, log loss `0.9978066048074087` vs
`0.9730819333695456`, and ECE `0.04012862021286022` vs
`0.03676958063070931`.

Current decision: form/rest is now wired into the proper holdout learning loop,
but it remains shadow-only. Do not promote coarse recent-results form or rest
signals into the default recommendation path; move next toward richer frozen
lineup, injury, news, and opening-to-closing odds movement samples or
calibration-layer improvements.

Structured pre-match feature snapshots are now available for those higher-value
inputs. The feature layer can represent expected or confirmed lineup confidence,
availability and key-player absence scores, pre-match odds movement time
series, and LLM-assisted semantic signals such as rotation hints or press
conference injury hints. These signals are stored inside standard
`FeatureSnapshot.features_json` under `prematch_context`, with source references
kept in `source_snapshot_refs["prematch"]`.

Historical slice CSVs may now include an optional `feature_snapshot_json` column
containing a full serialized `FeatureSnapshot`. The builder validates that the
snapshot fixture matches the CSV fixture, carries it into `HistoricalFixture`,
and reports `feature_snapshot_fixture_count` in the build summary. Existing CSVs
without that column remain compatible.

Example historical fixture feature payload shape:

```json
{
  "fixture_id": "hist_feature_001",
  "feature_time_utc": "2026-05-08T17:45:00Z",
  "feature_version": "features-v3.1-prematch-structured",
  "features_json": {
    "prematch_context": {
      "lineup": {"lineup_type": "expected", "expected_lineup_confidence": 0.82},
      "availability": {"key_player_absence_score": 0.35},
      "odds_movement": [
        {
          "market_type": "1x2",
          "outcome": "home_win",
          "opening_prob": 0.45,
          "current_prob": 0.52,
          "movement_direction": "probability_shortened"
        }
      ],
      "semantic_signals": []
    }
  },
  "source_snapshot_refs": {"prematch": {}},
  "data_quality_score": 93.9
}
```

Current decision: this is schema and sample-path groundwork, not a promoted
prediction model. The next accuracy step is to collect or synthesize repeatable
historical samples with these fields populated, then run the existing
walk-forward and holdout gates before any recommendation-path use.

Structured feature samples can be checked with the historical feature
completeness gate before they are allowed into model experiments:

```bash
uv run nutmeg-recommendation-historical-feature-completeness \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --min-feature-snapshot-coverage 1.0 \
  --min-lineup-coverage 0.80 \
  --min-availability-coverage 0.80 \
  --min-odds-movement-coverage 0.80 \
  --min-source-ref-coverage 1.0 \
  --min-average-feature-data-quality-score 80 \
  --no-fail-process
```

This gate reads only frozen `HistoricalRecommendationSlice` data. It does not
call providers, does not score recommendations, and does not promote a model.
It reports fixture-level coverage for `feature_snapshot`, `prematch_context`,
lineup, availability, odds movement, semantic/news signals, source refs,
feature timestamp leakage, and feature data-quality floors. Existing slices
without `feature_snapshot_json` are expected to fail this gate; that failure is
useful because it prevents incomplete feature samples from being mistaken for an
accuracy experiment.

A deterministic enriched pre-match feature sample is available through
`nutmeg-recommendation-enriched-feature-sample`. It creates a local six-fixture
`HistoricalRecommendationSlice`, with every fixture carrying lineup,
availability, odds movement, semantic/news signal, source refs, and data-quality
payloads:

```bash
uv run nutmeg-recommendation-enriched-feature-sample \
  --output-path configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json \
  --completeness-output-path configs/recommendations/historical_reports/nutmeg_enriched_prematch_feature_completeness_v1.json \
  --suite-manifest-output-path configs/recommendations/historical_suites/nutmeg_enriched_prematch_feature_suite.json
```

Generated artifacts:

```text
configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json
configs/recommendations/historical_suites/nutmeg_enriched_prematch_feature_suite.json
configs/recommendations/historical_reports/nutmeg_enriched_prematch_feature_completeness_v1.json
```

The completeness report has
`completeness_key=historical_feature_completeness:nutmeg_enriched_prematch_feature_sample_v1:4b546bf8b7b4738d`.
It passes with `fixture_count=6`, `feature_snapshot_coverage=1.0`,
`lineup_coverage=1.0`, `availability_coverage=1.0`,
`odds_movement_coverage=1.0`, `semantic_signal_coverage=1.0`, and
`source_ref_coverage=1.0`.

Current decision: this enriched slice is still synthetic and local. Its purpose
is to keep the feature chain reproducible before real provider history is
available. It should be used for schema, completeness, and ablation smoke tests,
not as evidence that the model is more accurate.

Structured pre-match features can now be read by a shadow ablation report:

```bash
uv run nutmeg-accuracy-prematch-feature-ablation \
  --suite-manifest configs/recommendations/historical_suites/nutmeg_enriched_prematch_feature_suite.json \
  --output-path configs/recommendations/historical_reports/nutmeg_enriched_prematch_feature_ablation_v1.json \
  --min-feature-data-quality-score 80 \
  --min-bucket-sample-size 1 \
  --prediction-sample-limit 10
```

The report compares the frozen 1X2 probabilities in the historical slice with a
shadow-only feature-adjusted probability set. It reads only
`FeatureSnapshot.features_json.prematch_context`, extracts lineup strength,
tracked-outcome fragility, odds movement, draw risk, semantic pre-match risk,
and market volatility, then records the probability shifts and reason codes per
fixture.

Generated smoke report:

```text
configs/recommendations/historical_reports/nutmeg_enriched_prematch_feature_ablation_v1.json
```

On the deterministic enriched sample, the shadow candidate produced
`report_key=historical_prematch_feature_ablation:b878f826577c892c`,
`validation_count=6`, `skipped_count=0`, `hit_rate=0.8333333333333334` versus
baseline `0.6666666666666666`, Brier `0.44620143425059156` versus
`0.4938333333333333`, Log loss `0.7882092451011932` versus
`0.8545397472949539`, and ECE `0.24920562935895518` versus
`0.37333333333333335`.

Current decision: this is still a synthetic ablation smoke test. It proves that
the structured feature payload can flow into a scored, auditable accuracy report;
it does not promote a feature model and does not change the recommendation
default path. The next accuracy step is to attach the same feature schema to
real frozen historical samples and rerun this report beside the walk-forward and
holdout gates.

A first real frozen market-movement feature sample is now available from the
local `football-data.co.uk` EPL 2024-2025 CSV. It uses opening no-vig 1X2
probabilities as the frozen baseline and stores opening-to-closing 1X2 movement
inside `FeatureSnapshot`. The source does not include lineup, injury, or
semantic/news fields, so those coverages intentionally remain `0.0`.

```bash
uv run nutmeg-recommendation-football-data-co-uk-feature-sample \
  data/historical_sources/football_data_co_uk/europe/2425/E0.csv \
  --output-path configs/recommendations/historical_slices/enriched_features/football_data_co_uk_epl_2024_2025_market_features_v1.json \
  --completeness-output-path configs/recommendations/historical_reports/football_data_co_uk_epl_2024_2025_market_feature_completeness_v1.json \
  --suite-manifest-output-path configs/recommendations/historical_suites/football_data_co_uk_market_feature_sample_suite.json \
  --slice-id football_data_co_uk_epl_2024_2025_market_features_v1 \
  --competition-id EPL \
  --season 2024-2025 \
  --max-rows 24 \
  --min-feature-data-quality-score 70
```

Generated artifacts:

```text
configs/recommendations/historical_slices/enriched_features/football_data_co_uk_epl_2024_2025_market_features_v1.json
configs/recommendations/historical_suites/football_data_co_uk_market_feature_sample_suite.json
configs/recommendations/historical_reports/football_data_co_uk_epl_2024_2025_market_feature_completeness_v1.json
configs/recommendations/historical_reports/football_data_co_uk_epl_2024_2025_market_feature_ablation_v1.json
```

The completeness gate passes with `fixture_count=24`,
`feature_snapshot_coverage=1.0`, `odds_movement_coverage=1.0`,
`source_ref_coverage=1.0`, and feature data quality `73.5`. Lineup,
availability, and semantic coverage are `0.0` by design because this source
does not provide those fields.

The real 24-fixture shadow ablation is deliberately mixed rather than promoted:
candidate hit rate improved from `0.625` to `0.6666666666666666`, but Brier moved
from `0.4795315326263354` to `0.47978713153959185`, Log loss from
`0.8277912610283363` to `0.82791739935502`, and ECE from
`0.117560706129223` to `0.11932341264735305`.

Current decision: market movement is now wired into a real frozen feature
sample, but this evidence is not strong enough for recommendation-path use. It
should remain shadow-only until the sample is expanded across seasons/leagues
and combined with real lineup/injury/news features.

The market-movement sample path can now be expanded in batch across multiple
`football-data.co.uk` CSVs:

```bash
uv run nutmeg-recommendation-football-data-co-uk-feature-batch \
  data/historical_sources/football_data_co_uk/europe/2021/D1.csv \
  data/historical_sources/football_data_co_uk/europe/2021/E0.csv \
  data/historical_sources/football_data_co_uk/europe/2021/F1.csv \
  data/historical_sources/football_data_co_uk/europe/2021/I1.csv \
  data/historical_sources/football_data_co_uk/europe/2021/SP1.csv \
  --output-dir configs/recommendations/historical_slices/enriched_features/football_data_co_uk_market_features_multi \
  --completeness-output-dir configs/recommendations/historical_reports/football_data_co_uk_market_features_multi \
  --suite-manifest-output-path configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --max-rows-per-slice 24
```

The current generated suite contains the five major European leagues across
five local seasons: `25` slices, `600` fixtures, and `25` passing market-feature
completeness reports. Japan is not included in this market-movement suite yet:
the local `JPN.csv` only has closing-style odds columns for this feature path,
so it cannot support opening-to-closing movement without a different source or
an explicitly separate closing-only experiment.

Structured pre-match feature parameters can be evaluated with a shadow-only
grid:

```bash
uv run nutmeg-accuracy-prematch-feature-ablation-grid \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_ablation_grid_v1.json \
  --prediction-sample-limit 0 \
  --min-feature-data-quality-score 70
```

The grid report has
`report_key=historical_prematch_feature_ablation_grid:a8e20d22f795bdc3`.
It evaluated `144` parameter candidates over `600` fixtures. The best ranked
shadow candidate improved hit rate from `0.5416666666666666` to
`0.5533333333333333`, Brier from `0.5715089430682542` to
`0.5705712576436532`, log loss from `0.9607358728994643` to
`0.9592187227885163`, and ECE from `0.053777544137493485` to
`0.04884178687920516`.

Current decision: this is stronger than the 24-fixture smoke result, but it is
still market-derived and shadow-only. It can guide future feature weights, not
replace the default recommendation path. Promotion still needs held-out samples,
real lineup/injury/news coverage, and final-answer quality gates.

The same market-movement feature weights can now be learned with
competition-level holdout validation, rather than selected on the same sample
they are judged on:

```bash
uv run nutmeg-accuracy-prematch-feature-parameter-learning \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-training-sample-size 80 \
  --min-validation-sample-size 20 \
  --selection-metric brier_score_delta \
  --min-feature-data-quality-score 70 \
  --max-probability-shifts 0,0.03,0.06 \
  --odds-movement-weights 0,0.25,0.5 \
  --tracked-fragility-weights 0,0.5 \
  --lineup-strength-weights 0 \
  --draw-signal-weights 0,0.25 \
  --bucket-size 0.10 \
  --min-bucket-sample-size 10 \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_holdout_parameter_learning_v1.json
```

The holdout report has
`report_key=historical_prematch_feature_parameter_learning:308c08aaeab87c39`.
It learned five competitions over `36` candidates and validated on `120`
fixtures from the held-out 2024-2025 slices. The overall hit-rate delta improved
by `0.008333333333333304`, but Brier, log loss, and ECE regressed slightly:
Brier delta `0.0004473167414803525`, log-loss delta
`0.0005245535841910121`, and ECE delta `0.0009742248303094281`.

Current decision: opening-to-closing movement is a real signal, especially in
La Liga and Bundesliga in this small holdout, but it is not stable enough to
promote. Keep it as shadow evidence until the sample grows beyond 24 fixtures
per league-season and includes lineup/injury/news features.

Those grid candidates can now be evaluated through a final-answer-only quality
gate:

```bash
uv run nutmeg-recommendation-historical-prematch-feature-final-answer-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --grid-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_ablation_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_final_answer_gate_v1.json \
  --top-candidate-limit 5 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --no-fail-process
```

This gate applies each selected grid candidate to a shadow copy of the frozen
historical slices, reruns the final-answer backtest, and sends the resulting
candidate-vs-baseline suite through the existing historical quality gate. The
current report has
`report_key=historical_prematch_feature_final_answer_gate:306b253b38ca326d`.
It evaluated the top `5` grid candidates over the same `25` slices and `600`
fixtures. None passed the strict final-answer gate. The best final-answer
candidate improved hit rate from `0.60` to `0.64`, ROI from `-0.07` to `0.048`,
and profit/loss by `5.9`, but regressed final-answer Brier by
`0.010490767824201636`, log loss by `0.02175303651542737`, and mean calibration
error by `0.009851059345951763`.

Current decision: this is an important correction. The same feature grid that
looked good on single-match 1X2 metrics does not pass the final-answer gate
under calibration constraints. It remains shadow-only and must not be promoted
to the default recommendation path.

The final-answer gate can now be wrapped by a compact periodic quality cycle:

```bash
uv run nutmeg-recommendation-historical-prematch-feature-quality-cycle \
  --final-answer-gate-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_final_answer_gate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_quality_cycle_v1.json \
  --no-fail-process
```

The current cycle report has
`cycle_key=historical_prematch_feature_quality_cycle:df81abdec5044134` and
`status=failed`. It summarizes the same `25` slices and `600` fixtures without
embedding the full gate report. The blocker is explicit:
`passing_candidate_count=0`; the best candidate still fails `suite_status`,
`brier_score_delta`, `log_loss_delta`, and `mean_calibration_error_delta`.

Current decision: the periodic quality cycle is working as a guardrail. It
should fail until a feature candidate improves final answer quality without
calibration regression. This does not change the default recommendation path.

The persisted benchmark quality gate can consume the compact quality-cycle
artifact as one more periodic accuracy evidence input:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --prematch-feature-quality-cycle-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_quality_cycle_v1.json \
  --require-prematch-feature-quality-cycle \
  --min-prematch-feature-quality-cycle-slice-count 25 \
  --min-prematch-feature-quality-cycle-fixture-count 600 \
  --min-prematch-feature-quality-cycle-evaluated-candidate-count 5 \
  --min-prematch-feature-quality-cycle-passing-candidate-count 1 \
  --max-prematch-feature-quality-cycle-warning-count 0 \
  --max-prematch-feature-quality-cycle-best-brier-score-delta 0.0 \
  --max-prematch-feature-quality-cycle-best-log-loss-delta 0.0 \
  --max-prematch-feature-quality-cycle-best-calibration-error-delta 0.0
```

The combined benchmark cycle exposes the same options with a `--gate-` prefix.
Its summary carries the prematch feature cycle key/status, final-answer gate
key, grid key, slice/fixture/candidate counts, best candidate, failed quality
checks, warning count, and best Brier/log-loss/calibration deltas. A failed
prematch feature cycle remains a blocker when attached as evidence; it does not
activate feature weights or expose internal feature strategy to users.

Prematch feature candidates can also be wrapped in a stricter rolling admission
gate before they are considered for any staged runtime path:

```bash
uv run nutmeg-recommendation-historical-prematch-feature-rolling-admission \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --grid-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_ablation_grid_v1.json \
  --sample-readiness-report-path configs/recommendations/historical_reports/prematch_feature_sample_readiness_market_movement_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_admission_v1.json \
  --require-sample-readiness \
  --top-candidate-limit 5 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --min-overall-passing-candidate-count 1 \
  --min-fold-passing-candidate-count 1 \
  --min-active-competition-fold-count 1 \
  --min-active-season-cutoff-fold-count 1 \
  --min-active-rolling-fold-count 1 \
  --rolling-window-season-count 3 \
  --no-fail-process
```

The admission report evaluates the same frozen grid candidates over the overall
sample, competition folds, cumulative season cutoffs, and rolling season
windows. It returns `accepted`, `shadow_only`, or `rejected`; only `accepted`
sets `candidate_feature_allowed=true`. This is still an internal guardrail: it
does not activate feature weights, does not modify the default recommendation
path, and does not add any user-facing strategy explanation.
If a sample-readiness report is attached, `shadow_only` or `rejected` readiness
keeps the rolling-admission output out of candidate-allowed status even when the
final-answer gate itself looks clean.

The persisted benchmark quality gate and benchmark cycle can consume that
rolling-admission artifact as strict staged evidence:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --prematch-feature-rolling-admission-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_admission_v1.json \
  --prematch-feature-sample-readiness-report-path configs/recommendations/historical_reports/prematch_feature_sample_readiness_market_movement_v1.json \
  --require-prematch-feature-rolling-admission \
  --require-prematch-feature-sample-readiness \
  --min-prematch-feature-sample-ready-fixture-count 500 \
  --min-prematch-feature-sample-ready-competition-count 3 \
  --min-prematch-feature-rolling-admission-overall-evaluated-candidate-count 5 \
  --min-prematch-feature-rolling-admission-overall-passing-candidate-count 1 \
  --max-prematch-feature-rolling-admission-failed-fold-count 0 \
  --min-prematch-feature-rolling-admission-active-competition-fold-count 1 \
  --min-prematch-feature-rolling-admission-active-season-cutoff-fold-count 1 \
  --min-prematch-feature-rolling-admission-active-rolling-fold-count 1 \
  --max-prematch-feature-rolling-admission-overall-brier-score-delta 0.0 \
  --max-prematch-feature-rolling-admission-overall-log-loss-delta 0.0 \
  --max-prematch-feature-rolling-admission-overall-calibration-error-delta 0.0
```

The benchmark cycle exposes the same options with `--gate-` prefixes, including
`--gate-prematch-feature-sample-readiness-report-path`. If an attached
sample-readiness or rolling-admission report is `shadow_only` or `rejected`, the
gate fails instead of treating it as neutral evidence. This keeps unstable or
under-covered prematch feature candidates out of staged recommendation paths
until their sample coverage and fold-level final-answer metrics are clean.

The raw opening-to-closing movement signal can now be diagnosed before any
feature-weight or recommendation-policy change is considered:

```bash
uv run nutmeg-accuracy-historical-market-movement-signal-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_signal_diagnostics_v1.json \
  --min-abs-probability-delta 0.0 \
  --movement-direction-epsilon 0.001 \
  --delta-bands 0.00:0.01,0.01:0.03,0.03:0.06,0.06: \
  --opening-probability-bands 0.00:0.25,0.25:0.45,0.45:0.65,0.65:1.00 \
  --min-group-sample-size 20
```

The report has
`report_key=historical_market_movement_signal_diagnostics:4afa1b5a35b0c710`.
It covers the same `25` slices and `600` fixtures, producing `1,800` outcome
movement observations and `600` strongest-fixture-movement observations. Overall
closing probabilities improve the binary outcome score only slightly:
`closing_improved_rate=0.5033333333333333`,
`brier_score_delta=-0.0005550790758561686`, and
`log_loss_delta=-0.0015181205557339705`.

Useful segments exist, but they are uneven. Ligue 1 away-win movement has
`closing_improved_rate=0.6083333333333333` and Brier delta
`-0.004886555980174734`; strongest shortened movements have Brier delta
`-0.0023954857567937693`. Large probability moves above `0.06` are negative in
this sample, with Brier delta `0.008271203266298488`. Serie A movement is also
negative overall, with Brier delta `0.0012113756405588427`.

Current decision: opening-to-closing movement contains real signal, but it is
not globally safe. It should be used as a diagnostic and future segmented
feature candidate, not as a direct probability replacement or default
recommendation factor.

Segmented market-movement candidates can now be evaluated as shadow-only
probability adjustments and must pass both single-match metrics and final-answer
quality gates:

```bash
uv run nutmeg-recommendation-historical-market-movement-segment-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --diagnostics-report-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_signal_diagnostics_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_gate_v1.json \
  --top-positive-segment-limit 6 \
  --min-segment-sample-size 20 \
  --movement-weight 0.50 \
  --max-probability-shift 0.08 \
  --min-single-match-sample-size 10 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --strategy accuracy_first \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --max-outcomes-per-fixture 2 \
  --max-candidates-per-fixture 3 \
  --optimizer-profile solver \
  --min-final-hit-rate-delta 0 \
  --max-brier-score-delta 0 \
  --max-log-loss-delta 0 \
  --max-mean-calibration-error-delta 0 \
  --no-fail-process
```

The current report has
`report_key=historical_market_movement_segment_gate:77d3815ce33c9953`.
It evaluated `6` positive diagnostic segments across `25` slices and `600`
fixtures; `3` candidates were accepted and `3` rejected. The best accepted
candidate is `delta_band:0.03:0.06`, adjusting `174` fixtures and `522`
1X2 predictions. Its single-match deltas improved hit rate by
`0.04022988505747127`, Brier by `-0.003199226213764339`, and log loss by
`-0.0056378590359547065`. Its final-answer gate also passed with Brier delta
`-0.0010253961702982317`, log-loss delta `-0.0021553046169603407`, and mean
calibration error delta `-0.001045519383702287`.

Current decision: medium opening-to-closing probability moves are now a
promising shadow feature candidate, but only at the segmented gate level. The
default recommendation path remains unchanged until this candidate is replayed
through broader samples and successor-chain quality gates.

The segment gate can now be wrapped in a compact lifecycle quality cycle before
any promotion discussion. The cycle requires an accepted candidate, requires the
best candidate to change at least one final answer, and keeps the successor-chain
evaluation hook explicit:

```bash
uv run nutmeg-recommendation-historical-market-movement-segment-quality-cycle \
  --segment-gate-report-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_gate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_quality_cycle_v1.json \
  --min-accepted-candidate-count 1 \
  --min-best-final-answer-changed-count 1 \
  --min-best-final-hit-rate-delta 0 \
  --max-best-brier-score-delta 0 \
  --max-best-log-loss-delta 0 \
  --max-best-mean-calibration-error-delta 0 \
  --no-fail-process
```

The current offline cycle has
`cycle_key=historical_market_movement_segment_quality_cycle:802cfe3f4712bdc7`
and `status=passed`. It summarizes the segment gate report above:
`accepted_count=3`, best segment `delta_band:0.03:0.06`, and
`best_final_answer_changed_count=1`. All best-candidate final-answer metric
checks passed. No persisted successor-chain evaluation report was attached in
this offline run, so `successor_chain_evaluation_present=false` and that check
is skipped. Use `--require-successor-chain-evaluation` with a
`--successor-chain-evaluation-report-path` once persisted recommendation runs
exist for the same promotion candidate.

The strict lifecycle form is:

```bash
nutmeg-recommendation-successor-chain-evaluate \
  --window-start-utc 2026-05-01T00:00:00Z \
  --window-end-utc 2026-05-13T00:00:00Z \
  --pass-type 6x1 \
  --mode single \
  --output-path configs/recommendations/historical_reports/market_movement_segment_successor_chain_evaluation_v1.json \
  --min-effective-leaf-count 1 \
  --min-active-edge-count 1 \
  --max-critical-issue-count 0 \
  --max-ambiguous-successor-source-count 0 \
  --max-source-status-sync-required-count 0

uv run nutmeg-recommendation-historical-market-movement-segment-quality-cycle \
  --segment-gate-report-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_gate_v1.json \
  --successor-chain-evaluation-report-path configs/recommendations/historical_reports/market_movement_segment_successor_chain_evaluation_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_quality_cycle_strict_v1.json \
  --require-successor-chain-evaluation \
  --min-accepted-candidate-count 1 \
  --min-best-final-answer-changed-count 1 \
  --min-best-final-hit-rate-delta 0 \
  --max-best-brier-score-delta 0 \
  --max-best-log-loss-delta 0 \
  --max-best-mean-calibration-error-delta 0 \
  --min-successor-effective-leaf-count 1 \
  --min-successor-active-edge-count 1 \
  --max-successor-critical-issue-count 0 \
  --max-successor-ambiguous-source-count 0 \
  --max-successor-source-status-sync-required-count 0 \
  --no-fail-process
```

Run the strict form against a database that contains the relevant persisted
recommendation runs. A local isolated smoke used a temporary Nutmeg Postgres
container and did not touch the separate `zeus` containers. It produced
`configs/recommendations/historical_reports/local_successor_chain_evaluation_smoke_v1.json`
and
`configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_quality_cycle_strict_smoke_v1.json`.
The successor-chain smoke passed with `run_count=2`, `effective_leaf_count=1`,
`active_edge_count=1`, `chain_integrity_critical_issue_count=0`, and
`source_status_sync_required_count=0`. The strict segment cycle then passed
with
`cycle_key=historical_market_movement_segment_quality_cycle:117f2c25fa748e34`,
`successor_chain_evaluation_present=true`, and
`successor_chain_evaluation_passed=true`.

The persisted lifecycle smoke now runs the same lifecycle through the real
recommendation writers instead of hand-built SQL rows:

```bash
NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
uv run nutmeg-recommendation-persisted-lifecycle-smoke \
  --commit \
  --output-path configs/recommendations/historical_reports/local_persisted_lifecycle_smoke_v1.json
```

The command is write-safe by default and only executes the seed, source
recommendation, locked leg, successor recompute, source-status sync, and
successor-chain evaluation steps when `--commit` is present. The local isolated
smoke used a temporary Nutmeg Postgres container, left the separate `zeus`
containers untouched, and passed with `source_recommendation_run_id=1`,
`successor_recommendation_run_id=2`, `locked_fixture_ids=["bench_v3_001"]`,
`effective_leaf_count=1`, `active_edge_count=1`,
`chain_integrity_critical_issue_count=0`, and
`source_status_sync_required_count=0`.

The segment quality cycle can now require that persisted lifecycle smoke report
as an additional gate:

```bash
uv run nutmeg-recommendation-historical-market-movement-segment-quality-cycle \
  --segment-gate-report-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_gate_v1.json \
  --successor-chain-evaluation-report-path configs/recommendations/historical_reports/local_successor_chain_evaluation_smoke_v1.json \
  --persisted-lifecycle-smoke-report-path configs/recommendations/historical_reports/local_persisted_lifecycle_smoke_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_quality_cycle_persisted_lifecycle_smoke_v1.json \
  --require-successor-chain-evaluation \
  --require-persisted-lifecycle-smoke \
  --min-accepted-candidate-count 1 \
  --min-best-final-answer-changed-count 1 \
  --min-best-final-hit-rate-delta 0 \
  --max-best-brier-score-delta 0 \
  --max-best-log-loss-delta 0 \
  --max-best-mean-calibration-error-delta 0 \
  --min-successor-effective-leaf-count 1 \
  --min-successor-active-edge-count 1 \
  --max-successor-critical-issue-count 0 \
  --max-successor-ambiguous-source-count 0 \
  --max-successor-source-status-sync-required-count 0 \
  --min-persisted-lifecycle-effective-leaf-count 1 \
  --min-persisted-lifecycle-active-edge-count 1 \
  --max-persisted-lifecycle-critical-issue-count 0 \
  --max-persisted-lifecycle-source-status-sync-required-count 0
```

The current combined strict cycle passed with
`cycle_key=historical_market_movement_segment_quality_cycle:33ca81de702b8ac1`,
`persisted_lifecycle_smoke_present=true`,
`persisted_lifecycle_source_status_synced=true`,
`persisted_lifecycle_effective_leaf_count=1`, and no failed checks. This is
still a shadow-only promotion guardrail, not a default recommendation strategy
change.

The larger historical suite gate can consume that strict lifecycle cycle report
so historical final-answer metrics and lifecycle readiness fail or pass together:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_suite_gate_with_lifecycle_v1.json \
  --lifecycle-quality-cycle-report-path configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_quality_cycle_persisted_lifecycle_smoke_v1.json \
  --require-lifecycle-quality-cycle \
  --min-lifecycle-effective-leaf-count 1 \
  --min-lifecycle-active-edge-count 1 \
  --max-lifecycle-critical-issue-count 0 \
  --max-lifecycle-source-status-sync-required-count 0 \
  --pass-types 2x1 \
  --modes single \
  --max-budget 4 \
  --min-slice-count 30 \
  --min-comparison-count 30 \
  --min-final-hit-sample-size 30 \
  --max-warning-count 1
```

The current 30-slice suite gate passed with
`gate_key=historical_recommendation_suite_quality_gate:96133aaf34afdaa7`,
`lifecycle_quality_cycle_present=true`, `lifecycle_quality_cycle_passed=true`,
`lifecycle_source_status_synced=true`, `lifecycle_effective_leaf_count=1`, and
no failed checks.

The persisted benchmark quality gate can now consume that historical suite gate
artifact as promotion evidence. This lets a scheduled benchmark fail if the
latest frozen final-answer suite, lifecycle cycle, or persisted lifecycle smoke
is missing or stale:

```bash
uv run nutmeg-recommendation-benchmark-quality-gate \
  --historical-suite-quality-gate-report-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_suite_gate_with_lifecycle_v1.json \
  --require-historical-suite-quality-gate \
  --min-historical-suite-slice-count 30 \
  --min-historical-suite-comparison-count 30 \
  --max-historical-suite-failed-check-count 0 \
  --min-historical-suite-lifecycle-effective-leaf-count 1 \
  --min-historical-suite-lifecycle-active-edge-count 1 \
  --max-historical-suite-lifecycle-critical-issue-count 0 \
  --max-historical-suite-lifecycle-source-status-sync-required-count 0
```

The same checks are available on the scheduled cycle runner with the `--gate-`
prefix, for example
`--gate-historical-suite-quality-gate-report-path` and
`--gate-require-historical-suite-quality-gate`. This is still an internal
quality gate; it does not expose strategy details to users or enable the
shadow market-movement candidate by default.

Market-movement runtime activation evidence can also be attached to the
scheduled cycle. This keeps a staged runtime rule inside the recurring
quality-gate surface without writing the default profile or changing ordinary
recommendation responses:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --gate-market-movement-runtime-activation-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_risk_filter_runtime_activation_preflight_v1.json \
  --gate-require-market-movement-runtime-activation \
  --gate-min-market-movement-runtime-activation-rule-count 1 \
  --gate-min-market-movement-runtime-activation-selected-rule-count 1 \
  --gate-max-market-movement-runtime-activation-selected-rule-count 1 \
  --gate-min-market-movement-runtime-activation-adjusted-fixture-count 120 \
  --gate-min-market-movement-runtime-activation-adjusted-prediction-count 360 \
  --gate-max-market-movement-runtime-activation-brier-score-delta 0 \
  --gate-max-market-movement-runtime-activation-log-loss-delta 0 \
  --gate-max-market-movement-runtime-activation-calibration-delta 0
```

The cycle summary carries `market_movement_runtime_activation_*` fields for
status, selected rule ids, selected segment groups, adjusted coverage,
final-hit/ROI/P&L deltas, probability-quality deltas, blockers, and
default/production/public change flags. The staged activation profile remains
an internal candidate until future frozen-sample cycles keep passing the same
no-harm gates.

The staged activation now also has a reusable sample-expansion gate. It consumes
the activation preflight, the market-movement sample-readiness report, and the
expanded A-leagues coverage audit, then emits one report that the benchmark
quality gate can require with
`--market-movement-runtime-activation-sample-expansion-report-path` and
`--require-market-movement-runtime-activation-sample-expansion`:

```bash
uv run nutmeg-recommendation-historical-market-movement-runtime-activation-sample-expansion \
  --activation-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_risk_filter_runtime_activation_preflight_v1.json \
  --sample-readiness-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_sample_readiness_market_movement_v1.json \
  --coverage-audit-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_derived_market_coverage_audit_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_sample_expansion_v1.json
```

The generated base report passes the hard sample checks with 3,120 combined
fixtures, 235 frozen slices, 12 competitions, and 60 competition-season cells.
Before replay-batch evidence is attached it remains `shadow_only`, not
promotion-ready, because the active rule is still a single La Liga segment and
its adjusted-fixture share is below the promotion threshold. This keeps the
expanded samples inside the quality-gate chain without changing the default
recommendation path.

The next direct replay expansion step derives concrete shadow-replay rules from
stable scope-refinement segments. The generated segment expansion report selects
four replay candidates and writes a staged-only profile; it still does not write
the default profile or expose any strategy details to users:

```bash
uv run nutmeg-recommendation-historical-market-movement-runtime-activation-segment-expansion \
  --sample-expansion-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_sample_expansion_v1.json \
  --scope-refinement-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_risk_filter_scope_refinement_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_v1.json \
  --profile-output-path configs/recommendations/profiles/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_profile_v1.json
```

The selected candidates cover 934 adjusted fixtures and 2,802 adjusted
predictions across the five core leagues. The first candidate,
`strongest_movement_direction:probability_shortened`, also passes a direct
runtime replay on the core market-feature suite with 248 adjusted fixtures,
744 adjusted predictions, final-hit/ROI/P&L deltas of 0.0, and improved Brier,
log-loss, and calibration deltas:

```bash
uv run nutmeg-recommendation-historical-market-movement-risk-filter-runtime-replay \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --rule-profile configs/recommendations/profiles/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_profile_v1.json \
  --enable-shadow-replay \
  --require-profile-runtime-shadow-allowed \
  --rule-ids market_movement_runtime_segment_expansion_strongest_movement_direction_probability_shortened_v1 \
  --min-adjusted-fixture-count 240 \
  --min-adjusted-prediction-count 720 \
  --max-brier-score-delta 0 \
  --max-log-loss-delta 0 \
  --max-mean-calibration-error-delta 0 \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_top_replay_v1.json
```

All four segment-expansion candidates now have direct runtime replay reports,
and the batch gate can attach them to the recurring benchmark quality surface:

```bash
uv run nutmeg-recommendation-historical-market-movement-runtime-activation-segment-replay-batch-gate \
  --segment-expansion-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_v1.json \
  --runtime-replay-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_top_replay_v1.json \
  --runtime-replay-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_opening_band_replay_v1.json \
  --runtime-replay-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_home_win_replay_v1.json \
  --runtime-replay-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_la_liga_drifted_replay_v1.json \
  --min-replay-report-count 4 \
  --min-passed-replay-count 4 \
  --min-distinct-rule-count 4 \
  --min-distinct-segment-count 4 \
  --min-covered-selected-segment-count 4 \
  --min-total-adjusted-fixture-count 1200 \
  --min-total-adjusted-prediction-count 3600 \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_replay_batch_gate_v1.json
```

The base batch report is `watchlist` but passed: all four replay reports pass
with 1,323 adjusted fixtures / 3,969 adjusted predictions, no final-hit/ROI/P&L
regression, and improved weighted Brier/log-loss/calibration deltas. It remains
not production-promotion-ready until the upstream sample-expansion gate includes
the replay-batch evidence.

The replay-batch evidence can now be attached back into the sample-expansion
gate as effective promotion coverage:

```bash
uv run nutmeg-recommendation-historical-market-movement-runtime-activation-sample-expansion \
  --activation-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_risk_filter_runtime_activation_preflight_v1.json \
  --sample-readiness-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_sample_readiness_market_movement_v1.json \
  --coverage-audit-report configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_derived_market_coverage_audit_v1.json \
  --segment-replay-batch-gate-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_replay_batch_gate_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_sample_expansion_segment_replay_ready_v1.json
```

That generated ready report keeps the original activation metrics visible, but
uses the ready replay batch as supplemental effective evidence: 1 replay-batch
gate, 1,323 effective adjusted fixtures, 3,969 effective adjusted predictions,
5 effective segment keys, and a 42.4% effective adjusted/combined fixture
ratio. It is `sample_expansion_ready`, promotion-ready, and still reports no
default/production/public recommendation changes. Re-running segment expansion
and the batch gate from this ready sample-expansion evidence produces
`football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_sample_ready_v1.json`
and
`football_data_co_uk_market_feature_market_movement_runtime_activation_segment_replay_batch_gate_sample_ready_v1.json`.
The latter is `segment_replay_batch_ready` with no watchlist items.

The recurring benchmark cycle can now forward both market-movement expansion
layers into the quality gate:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --cycle-preset v3_2_market_movement_segment_replay_batch_gate_v1 \
  --gate-market-movement-runtime-activation-sample-expansion-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_sample_expansion_segment_replay_ready_v1.json \
  --gate-require-market-movement-runtime-activation-sample-expansion \
  --gate-market-movement-runtime-activation-segment-replay-batch-gate-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_market_movement_runtime_activation_segment_replay_batch_gate_sample_ready_v1.json \
  --gate-require-market-movement-runtime-activation-segment-replay-batch-gate \
  --gate-min-market-movement-runtime-activation-segment-replay-batch-report-count 4 \
  --gate-min-market-movement-runtime-activation-segment-replay-batch-passed-count 4 \
  --gate-min-market-movement-runtime-activation-segment-replay-batch-adjusted-fixture-count 1200 \
  --gate-min-market-movement-runtime-activation-segment-replay-batch-adjusted-prediction-count 3600
```

The cycle summary carries `market_movement_activation_sample_expansion_*` and
`market_movement_segment_replay_batch_*` fields, including effective
replay-batch coverage counts, so periodic runs can reject missing or regressing
replay-batch evidence without exposing internal strategy details to users.
The `v3_2_market_movement_segment_replay_batch_gate_v1` preset fixes the
current minimums at 4 replay reports, 4 passed reports, 1,200 adjusted fixtures,
and 3,600 adjusted predictions.

Frozen lineup, availability, and semantic/news CSV inputs can now be merged into
an existing historical slice without changing the core slice schema:

```bash
uv run nutmeg-recommendation-historical-prematch-context-enrich \
  configs/recommendations/historical_slices/enriched_features/euro_2024_knockout_builder_base_v1.json \
  --lineup-csv configs/recommendations/historical_feature_inputs/euro_2024_knockout_lineup_context_sample.csv \
  --availability-csv configs/recommendations/historical_feature_inputs/euro_2024_knockout_availability_context_sample.csv \
  --semantic-csv configs/recommendations/historical_feature_inputs/euro_2024_knockout_semantic_context_sample.csv \
  --output-path configs/recommendations/historical_slices/enriched_features/euro_2024_knockout_prematch_context_enriched_v1.json \
  --completeness-output-path configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_completeness_v1.json \
  --suite-manifest-output-path configs/recommendations/historical_suites/euro_2024_knockout_prematch_context_suite.json \
  --slice-id euro_2024_knockout_prematch_context_enriched_v1 \
  --name "Euro 2024 knockout prematch context enriched sample" \
  --historical-stats-completeness 0.82 \
  --provider-consistency 0.88 \
  --min-fixture-count 2 \
  --min-lineup-coverage 1.0 \
  --min-availability-coverage 1.0 \
  --min-semantic-signal-coverage 1.0 \
  --min-source-ref-coverage 1.0 \
  --min-feature-data-quality-score 45 \
  --min-average-feature-data-quality-score 50
```

The current local context sample passes feature completeness with `2` fixtures:
lineup coverage `1.0`, availability coverage `1.0`, semantic signal coverage
`1.0`, source-ref coverage `1.0`, minimum feature data quality `72.8`, and
average feature data quality `73.6`. Odds-movement coverage is `0.0` for this
sample because it is specifically testing lineup / availability / semantic
inputs; the football-data.co.uk market-movement suite remains the separate
odds-movement sample path.

Current decision: this is an ingestion and completeness harness for real frozen
prematch context, not a promotion signal. These features still need historical
coverage, ablation, final-answer gates, and the quality cycle before they can
affect the default recommendation path.

The context-enriched slice can now be evaluated by the prematch feature
ablation report with explicit context-only signal accounting:

```bash
uv run nutmeg-accuracy-prematch-feature-ablation \
  configs/recommendations/historical_slices/enriched_features/euro_2024_knockout_prematch_context_enriched_v1.json \
  --output-path configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_ablation_v1.json \
  --min-feature-data-quality-score 45 \
  --prediction-sample-limit 10
```

The current smoke report has
`report_key=historical_prematch_feature_ablation:58c09594e4287492`. It covers
`2` fixtures and remains shadow-only. The sample improves Brier from `0.4799` to
`0.46039391991215806`, log loss from `0.841004302634468` to
`0.8153975149900965`, and ECE from `0.35999999999999993` to
`0.3518685067636364`; hit rate stays `0.5`. The report now exposes
`signal_family_counts={lineup:2, availability:2, semantic:2}`,
`context_only_no_odds_movement=2`, average lineup strength `0.2325525`, average
key-player absence `0.11499999999999999`, and average semantic risk `0.34`.

Current decision: this proves the lineup / availability / semantic readout can
be quantified and audited in the accuracy layer. The sample is far too small
for promotion, so the result must remain a smoke check only.

The same context-only sample now runs through the final-answer gate and compact
quality cycle as a shadow-only smoke path:

```bash
uv run nutmeg-accuracy-prematch-feature-ablation-grid \
  --suite-manifest configs/recommendations/historical_suites/euro_2024_knockout_prematch_context_suite.json \
  --output-path configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_ablation_grid_v1.json \
  --min-feature-data-quality-score 45 \
  --max-probability-shifts 0,0.04,0.08,0.12 \
  --odds-movement-weights 0 \
  --tracked-fragility-weights 0,0.5,1.0 \
  --lineup-strength-weights 0,0.35,0.7 \
  --draw-signal-weights 0,0.25,0.35 \
  --prediction-sample-limit 0
```

```bash
uv run nutmeg-recommendation-historical-prematch-feature-final-answer-gate \
  --suite-manifest configs/recommendations/historical_suites/euro_2024_knockout_prematch_context_suite.json \
  --grid-report-path configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_ablation_grid_v1.json \
  --output-path configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_final_answer_gate_v1.json \
  --top-candidate-limit 5 \
  --pass-types 1x1,2x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --min-final-hit-sample-size 10 \
  --no-fail-process
```

```bash
uv run nutmeg-recommendation-historical-prematch-feature-quality-cycle \
  --final-answer-gate-report-path configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_final_answer_gate_v1.json \
  --output-path configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_quality_cycle_v1.json \
  --no-fail-process
```

The context grid report has
`report_key=historical_prematch_feature_ablation_grid:40d260c5a3f58d72` and
evaluates `108` candidates over `2` fixtures. The best single-market candidate
improves Brier by `-0.03213051596268668`, log loss by
`-0.04522327928165426`, and ECE by `-0.015646069599999923`, with unchanged hit
rate. The final-answer gate has
`report_key=historical_prematch_feature_final_answer_gate:52ddd3b4db526e7a`;
it evaluates the top `5` candidates, but `passing_candidate_count=0` because
the strict sample-size guard fails `final_hit_sample_size` against the explicit
minimum of `10`. The quality cycle has
`cycle_key=historical_prematch_feature_quality_cycle:90f2e4a9ca65b08c` and
`status=failed` for the same reason.

Current decision: context signals are now wired all the way to the final-answer
quality guardrail, but this 2-fixture sample is intentionally blocked from
promotion. It remains a smoke path for future larger frozen lineup, availability,
and semantic/news historical slices.

Japan J1 can now be added to the structured sample inventory as a closing-only
feature suite. This is useful for J1 final-answer baselines and sample coverage,
but it is explicitly not opening-to-closing market movement:

```bash
uv run nutmeg-recommendation-football-data-co-uk-feature-batch \
  data/historical_sources/football_data_co_uk/japan/JPN.csv \
  --output-dir configs/recommendations/historical_slices/enriched_features/football_data_co_uk_j1_closing_only_features \
  --completeness-output-dir configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_features \
  --suite-manifest-output-path configs/recommendations/historical_suites/football_data_co_uk_j1_closing_only_feature_suite.json \
  --suite-id football_data_co_uk_j1_closing_only_feature_suite_v1 \
  --name "Football-Data.co.uk J1 closing-only feature suite" \
  --feature-source-kind closing_only \
  --prediction-time-policy slice_start \
  --source-season 2021 \
  --source-season 2022 \
  --source-season 2023 \
  --source-season 2024 \
  --source-season 2025 \
  --max-rows-per-slice 120 \
  --min-feature-data-quality-score 55
```

The generated J1 closing-only suite has `5` slices and `600` fixtures. It uses
`prediction_time_policy=slice_start` so the frozen closing-only shadow pool can
be replayed as a season-level baseline; this is not live availability evidence.
It has complete 1X2 coverage, feature snapshot coverage `1.0`, and source-ref
coverage `1.0`; its `odds_time_series_coverage` is `0.0`, which keeps it out
of market-movement promotion gates.

To evaluate that J1 baseline through the final-answer optimizer and persist the
quality report:

```bash
uv run nutmeg-recommendation-historical-diagnostics \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_j1_closing_only_feature_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_full_matrix_diagnostics.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 55 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4

uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_j1_closing_only_feature_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_full_matrix_gate.json \
  --pass-types 2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 64 \
  --min-data-quality-score 55 \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 2 \
  --scenario-candidate-fixture-buffer 4 \
  --min-slice-count 5 \
  --min-comparison-count 5 \
  --min-final-hit-sample-size 5 \
  --min-candidate-final-hit-rate 0.60 \
  --min-candidate-roi 0.0 \
  --min-solver-selected-scenario-count 5 \
  --max-warning-count 0
```

The current J1 shadow baseline report has
`report_key=historical_recommendation_diagnostic:cfaf4fd312418df9` with
`candidate_final_hit_rate=0.8`, `candidate_roi=0.6607800000000001`, and
`candidate_profit_loss=6.607800000000001` over `5` final-answer samples. The
quality gate has
`gate_key=historical_recommendation_suite_quality_gate:67bbe58060776814` and
passes with no failed checks. A short-price negative-edge guard probe excludes
`18` candidates but lowers the shadow result to `candidate_final_hit_rate=0.6`
and `candidate_roi=0.43620000000000003`, so it should not be globally promoted
without a per-competition/odds-band profile.

To make the historical data coverage explicit before adding more model logic,
run the frozen sample coverage audit:

```bash
uv run nutmeg-recommendation-historical-sample-coverage-audit \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_j1_closing_only_feature_suite.json \
  --suite-manifest configs/recommendations/historical_suites/euro_2024_knockout_prematch_context_suite.json \
  --output-path configs/recommendations/historical_reports/historical_sample_coverage_audit_v3.json \
  --min-final-answer-fixture-count 100
```

The current audit has
`audit_key=historical_sample_coverage_audit:597d8d6c9eac1baf`. It inventories
`61` frozen slices and `11940` fixtures across four sources. The core
football-data.co.uk suite has `30` slices and `10738` fixtures with complete
1X2 coverage, so it is suitable for final-answer historical backtests, but it
does not carry structured `FeatureSnapshot` payloads. The market-feature suite
has `25` slices and `600` fixtures with feature snapshot coverage `1.0`,
odds time-series coverage `1.0`, and source-ref coverage `1.0`, so it is
suitable for market-movement feature experiments, but it lacks lineup,
availability, and semantic/news coverage. The J1 closing-only suite has `5`
slices and `600` fixtures with feature snapshot coverage `1.0`, but
odds time-series coverage `0.0`; it is sample-ready for baselines, not
market-movement ready. The context suite has `2` fixtures with lineup,
availability, and semantic coverage `1.0`, but it is intentionally not
final-answer sample ready.

Current decision: the downloaded historical data is part of the core
verification path, but different suites answer different questions. The next
accuracy work should expand frozen context coverage and avoid treating
closing-only J1 odds as movement evidence.

The coverage audit now also records historical prediction market coverage:
`prediction_count_by_market`, fixture counts by market, complete-market fixture
counts, non-1X2 fixture coverage, handicap/correct-score fixture coverage, and
dynamic mixed-candidate fixture coverage. A fresh dynamic-market audit is saved
at
`configs/recommendations/historical_reports/historical_sample_coverage_dynamic_market_audit_v1.json`
with `audit_key=historical_sample_coverage_audit:550c7de743df788f`. It covers
`306` slices and `16980` fixtures across six sources. The important result is
plain: all frozen historical predictions are still `1x2` only
(`prediction_count_by_market` contains only `1x2` for every source), so
`dynamic_mixed_candidate_ready_source_ids`, `handicap_candidate_ready_source_ids`,
and `correct_score_candidate_ready_source_ids` are all empty. This does not
invalidate the dynamic mixed final-answer engine; it identifies the next core
data gap. Before hard dynamic-mixed benchmark thresholds can be raised, the
historical slice builder needs to materialize handicap and correct-score
prediction candidates from score grids or imported historical market lines.

Shadow derived-market slices can now be generated from existing frozen 1X2
historical predictions:

```bash
uv run nutmeg-recommendation-historical-derived-market-candidates \
  configs/recommendations/historical_slices/euro_2024_knockout_sample.json \
  --output-slice-path configs/recommendations/historical_slices/derived_markets/euro_2024_knockout_sample_derived_markets_v1.json \
  --report-output-path configs/recommendations/historical_reports/euro_2024_knockout_sample_derived_market_candidates_v1.json \
  --cn-handicaps=-1,1 \
  --european-handicaps=-1,1 \
  --correct-score-top-n 5
```

The tool uses fixture lambda metadata when present; otherwise it derives a
shadow Poisson score grid from the complete 1X2 probabilities and then exports
Chinese handicap 1X2, European handicap 1X2, and correct-score Top N
`HistoricalMarketPrediction` candidates. The Euro 2024 sample smoke generated
`119` non-1X2 predictions across `7` fixtures: `42` Chinese handicap, `42`
European handicap, and `35` correct-score candidates. A matching coverage audit
at
`configs/recommendations/historical_reports/euro_2024_knockout_sample_derived_market_coverage_audit_v1.json`
marks the derived slice dynamic-mixed, handicap, and correct-score candidate
ready. A backtest smoke at
`configs/recommendations/historical_reports/euro_2024_knockout_sample_derived_market_backtest_smoke_v1.json`
confirms the historical recommendation engine can consume the derived markets
with `allowed_markets=1x2,cn_handicap_1x2,european_handicap_1x2,correct_score`.
This is still shadow evidence with fair model-derived odds, not paid historical
provider handicap odds.

Before using those coverage sources for prematch-feature learning or admission,
run the sample readiness gate. It consumes the coverage audit and returns
`accepted`, `shadow_only`, or `rejected` for a target profile such as
`market_movement` or `full_prematch_context`:

```bash
uv run nutmeg-recommendation-historical-prematch-feature-sample-readiness \
  --coverage-audit-report-path configs/recommendations/historical_reports/historical_sample_coverage_audit_v3.json \
  --target-profile market_movement \
  --min-ready-fixture-count 500 \
  --min-ready-competition-count 3 \
  --min-ready-season-count 2 \
  --min-odds-time-series-coverage 0.80 \
  --min-source-ref-coverage 1.0 \
  --output-path configs/recommendations/historical_reports/prematch_feature_sample_readiness_market_movement_v1.json \
  --no-fail-process
```

Use `target_profile=full_prematch_context` only when the source has frozen
lineup, availability, semantic/news, odds time-series, source-ref, and complete
1X2 coverage. A `shadow_only` report may still be useful for internal research,
but it must not be treated as permission to promote prematch-feature candidates
into the default recommendation path.
The rolling-admission CLI and benchmark quality gate can consume this same
artifact, so sample readiness becomes part of the prematch-feature promotion
chain rather than a separate manual note.

To expand the frozen historical sample set from canonical Nutmeg rows, use the
CSV slice builder instead of hand-writing slice JSON. Required CSV columns are `fixture_id`,
`kickoff_time_utc`, `home_team_name`, `away_team_name`, `actual_home_goals`,
`actual_away_goals`, `prediction_time_utc`, `model_version`, `outcome`,
`probability`, and `decimal_odds`; optional columns cover feature/calibration
versions, market probability, edge, data quality, upset scores, line/side, and
JSON metadata:

```bash
uv run nutmeg-recommendation-historical-slice-build \
  configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv \
  --output-path /tmp/euro_2024_builder_sample.json \
  --slice-id euro_2024_builder_sample_v1 \
  --name "Euro 2024 builder sample" \
  --competition-id UEFA_EURO \
  --as-of-time-utc 2024-06-29T12:00:00Z \
  --season 2024 \
  --result-source "UEFA Euro 2024 public match records, builder sample" \
  --odds-source "Frozen consensus-style decimal odds CSV sample" \
  --prediction-source "Frozen Nutmeg-style probabilities CSV sample"
```

After a slice is generated and reviewed, register it in a suite manifest with
the refresh command. It dry-runs by default; add `--write` after checking the
summary:

```bash
uv run nutmeg-recommendation-historical-suite-refresh \
  configs/recommendations/historical_suites/euro_2024_knockout_suite.json \
  /tmp/euro_2024_builder_sample.json \
  --tag euro_2024 \
  --tag builder_sample \
  --note "Generated from canonical CSV input"
```

```bash
uv run nutmeg-recommendation-historical-suite-refresh \
  configs/recommendations/historical_suites/euro_2024_knockout_suite.json \
  /tmp/euro_2024_builder_sample.json \
  --tag euro_2024 \
  --tag builder_sample \
  --note "Generated from canonical CSV input" \
  --write
```

For local batch expansion, the sample pipeline chains all three steps:
CSV build, manifest refresh, and suite gate. It writes generated slice JSON
files to `--output-dir`, dry-runs the manifest unless `--write-manifest` is
set, and exits non-zero if the gate fails unless `--no-fail-process` is set:

```bash
uv run nutmeg-recommendation-historical-sample-pipeline \
  configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv \
  --output-dir /tmp/nutmeg_historical_slices \
  --manifest-path configs/recommendations/historical_suites/euro_2024_knockout_suite.json \
  --competition-id UEFA_EURO \
  --as-of-time-utc 2024-06-29T12:00:00Z \
  --season 2024 \
  --result-source "UEFA Euro 2024 public match records, pipeline sample" \
  --odds-source "Frozen consensus-style decimal odds CSV sample" \
  --prediction-source "Frozen Nutmeg-style probabilities CSV sample" \
  --slice-id-prefix pipeline \
  --manifest-tag pipeline \
  --pass-types 2x1 \
  --modes single \
  --max-budget 4 \
  --min-final-hit-sample-size 1 \
  --no-fail-process
```

The pipeline now runs sample coverage checks before manifest refresh and suite
gate. A generated slice must pass fixture uniqueness, kickoff/as-of timestamp
checks, complete 1X2 coverage, probability-sum tolerance, and odds coverage.
If sample quality fails, manifest writes are suppressed and suite gate is
skipped unless `--allow-sample-quality-failures` is set.

You can run the sample quality gate directly against slice paths or a suite
manifest:

```bash
uv run nutmeg-recommendation-historical-sample-quality \
  --suite-manifest configs/recommendations/historical_suites/euro_2024_knockout_suite.json \
  --min-fixture-count 1 \
  --require-market-probability \
  --min-data-quality-score 70
```

For a small multiple-selection smoke:

```bash
NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-benchmark-cycle \
    --schedule-name local-seeded-multiple-smoke \
    --cadence once \
    --run-at-utc 2026-05-12T00:00:00Z \
    --pass-types 2x1,4x1 \
    --modes multiple \
    --budgets 10 \
    --competition-id BENCH_V3 \
    --model-version poisson-v3.1-baseline \
    --commit \
    --save-report \
    --allow-missing-history \
    --gate-min-core-replay-ready-ratio 1 \
    --gate-min-final-hit-sample-size 2 \
    --gate-min-final-hit-rate 0.5
```

To exercise mixed outcome history, reseed with the stress profile and rerun the
same benchmark keys:

```bash
NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-baseline-seed --profile mixed_outcomes

NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-benchmark-cycle \
    --schedule-name local-seeded-mixed-single-matrix \
    --cadence once \
    --run-at-utc 2026-05-12T00:00:00Z \
    --pass-types 2x1,4x1,6x1,8x1 \
    --modes single \
    --budgets 10 \
    --competition-id BENCH_V3 \
    --model-version poisson-v3.1-baseline \
    --commit \
    --save-report \
    --allow-missing-history \
    --gate-min-core-replay-ready-ratio 1 \
    --gate-min-final-hit-sample-size 4 \
    --gate-min-final-hit-rate 0.2 \
    --no-fail-process
```

The mixed single matrix is expected to complete and settle, but it may fail the
quality gate because `history_status=regressed` is intentionally treated as a
blocking signal. That failure is useful evidence: it proves the saved benchmark
history can detect degraded final-hit and ROI results instead of only proving the
pipeline runs.

For targeted edge-profile smoke runs, keep reports unsaved and restore the
default seed afterward:

```bash
NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-baseline-seed --profile upset_stress

NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-benchmark-cycle \
    --schedule-name local-upset-stress-profile-smoke \
    --cadence once \
    --run-at-utc 2026-05-12T00:00:00Z \
    --pass-types 2x1,4x1 \
    --modes single \
    --budgets 10 \
    --competition-id BENCH_V3 \
    --model-version poisson-v3.1-baseline \
    --commit \
    --skip-gate

NUTMEG_DATABASE_URL=postgresql://nutmeg:nutmeg@localhost:5432/nutmeg \
  uv run nutmeg-recommendation-baseline-seed --profile happy_path
```

Recent persisted benchmark reports can be read through the admin API:

```bash
curl "http://localhost:8000/api/v1/recommendations/benchmark-runs?limit=10" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

Use optional `benchmark_key` and `strategy` query parameters to narrow the
history query. This endpoint is for internal accuracy review only.

The prematch lifecycle replay covers cross-day continuation cases. When a 6x1
has day-one fixtures locked or already started, the stage payload keeps those
locked fixtures as constraints and exposes the still-open fixtures in
`continuation_fixture_ids` with `remaining_open_leg_count`. The same continuation
fields are emitted by the in-memory lifecycle backtest, persisted lifecycle
replay, and saved prematch change report JSON. This is the internal contract for
scenarios such as A/B being confirmed on day one while C/D/E/F continue to be
recalculated for day two and later:

```bash
uv run pytest apps/api/tests/unit/test_recommendation_lifecycle_backtest.py -q
uv run pytest apps/api/tests/unit/test_recommendation_lifecycle_replay.py \
  apps/api/tests/unit/test_recommendation_prematch_report.py -q
uv run pytest \
  apps/api/tests/integration/test_api.py::test_recommendation_prematch_change_report_endpoint_runs_report \
  -q
uv run pytest \
  apps/api/tests/integration/test_api.py::test_recommendation_api_chain_locks_legs_and_reports_continuation \
  -q
uv run pytest apps/api/tests/unit/test_recommendation_successor.py -q
uv run pytest \
  apps/api/tests/integration/test_api.py::test_recommendation_successor_recompute_endpoint_runs_locked_successor \
  -q
```

A local Postgres smoke can be run by temporarily creating a committed 6x1
recommendation run from the deterministic seed, calling `POST
/recommendations/{id}/lock-leg` for the user-preserved A/B legs, then calling
`POST /recommendations/prematch-change-report` in `dry_run` mode. Reset with
`nutmeg-recommendation-baseline-seed --profile happy_path` after the smoke to
clean the temporary recommendation rows. The expected signal is HTTP 200 with
`locked_preservation_stage_count=1`, `continuation_stage_count=1`, and
`final_remaining_open_leg_count=4` for a 6x1 with two locked legs.

To generate the next persisted answer from a partially locked recommendation,
call `POST /recommendations/{id}/successor-recompute`. The runner reloads the
source run, preserves active locked legs by fixture, market, and outcome, reuses
the source candidate query and budget unless explicitly overridden, and stores a
successor recommendation when `dry_run=false`. For the local deterministic 6x1
smoke, the expected signal after locking two legs is a ready successor answer
with two locked fixture ids and four continuation fixture ids.

The prematch pipeline can also drive this path. `POST
/recommendations/recompute-trigger` keeps `trigger_locked_successors=false` by
default for backward-compatible incident-only behavior. `POST
/recommendations/prematch-pipeline` defaults `trigger_locked_successors=true`,
so a source run with active locked legs can produce a successor run even when no
provider incident affects it. This keeps the dynamic recommendation lifecycle on
the core pipeline while preserving the user's locked constraints.

Evaluation and core replay now use an effective leaf-run metric view for these
chains. The source run stays in lifecycle replay for audit, but once a
non-invalidated successor points to it through
`internal_trace.successor_recompute.source_recommendation_run_id`, pending
evaluation, strategy governance, and core replay ROI/hit-rate summaries count
only the successor leaf run. This prevents A/B locked continuation recomputes
from double-counting both the old and new final answers.

The in-memory effective-chain helper also handles multi-hop successor chains:
`source -> successor -> successor` contributes only the final effective leaf to
core replay metrics. Invalidated successors are recorded for audit but do not
supersede their source run, which keeps a withdrawn recompute from removing the
last valid recommendation from evaluation.

Core replay now also records recommendation validity windows. A run can be
`valid`, `valid_locked`, `superseded`, `invalidated`, `historical`,
`expired_kickoff`, or `stale_incident` for the replay `as_of_time`. The model
uses existing run status, selected fixture kickoff times, lifecycle events, and
successor trace data. If a locked run has started fixtures but still has future
open legs, the summary marks it as requiring a successor recompute instead of
showing the old full ticket as the current answer.

Use the internal chain integrity endpoint to diagnose source/successor graph
quality before trusting a benchmark window:

```bash
curl -X POST "http://localhost:8000/api/v1/recommendations/chain-integrity" \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{
    "window_start_utc": "2026-05-01T00:00:00Z",
    "window_end_utc": "2026-05-13T00:00:00Z",
    "pass_type": "6x1",
    "mode": "single"
  }'
```

The report is read-only. It flags missing sources, cycles, multiple active
successors, successors that predate their source, and source runs that should be
status-synced to `superseded`. Critical issues mean the recommendation chain is
not ready for accuracy evidence; status-sync warnings are surfaced for operator
review rather than mutating historical runs automatically.

For a standalone read-only gate over the same source/successor lifecycle, use
the successor chain evaluator. It combines chain integrity with the effective
leaf-run metric view, so an accuracy cycle can fail fast if a source run and its
successor would both be counted as trusted evidence:

```bash
nutmeg-recommendation-successor-chain-evaluate \
  --window-start-utc 2026-05-01T00:00:00Z \
  --window-end-utc 2026-05-13T00:00:00Z \
  --pass-type 6x1 \
  --mode single \
  --output-path configs/recommendations/historical_reports/successor_chain_evaluation_v1.json \
  --min-effective-leaf-count 1 \
  --max-critical-issue-count 0 \
  --max-ambiguous-successor-source-count 0
```

The evaluator is read-only. It reports effective leaf run IDs, superseded source
IDs, invalidated successors ignored for metrics, ambiguous successor sources,
and optional source-status-sync pressure. It is an internal accuracy gate, not
ordinary user-facing recommendation copy.

After a chain integrity report is free of critical issues, use the internal
source status sync endpoint to repair source run lifecycle status. It defaults
to `dry_run=true`; set `dry_run=false` only for an explicit operator commit. The
sync only moves source runs currently in `current` or `locked` to `superseded`
and records a lifecycle event with successor ids for audit:

```bash
curl -X POST "http://localhost:8000/api/v1/recommendations/source-status-sync" \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{
    "window_start_utc": "2026-05-01T00:00:00Z",
    "window_end_utc": "2026-05-13T00:00:00Z",
    "pass_type": "6x1",
    "mode": "single",
    "dry_run": true
  }'
```

The same repair path is available as an internal CLI for repeatable maintenance.
It also defaults to dry-run; add `--commit` only after reviewing the JSON output:

```bash
nutmeg-recommendation-source-status-sync \
  --window-start-utc 2026-05-01T00:00:00Z \
  --window-end-utc 2026-05-13T00:00:00Z \
  --pass-type 6x1 \
  --mode single
```

For football-data.org provider experiments, keep the key in the environment
only:

```bash
export NUTMEG_FOOTBALL_DATA_API_KEY=replace-with-local-key
export NUTMEG_API_FOOTBALL_API_KEY=replace-with-local-key
export NUTMEG_THE_ODDS_API_KEY=replace-with-local-key
export NUTMEG_SPORTMONKS_API_KEY=replace-with-local-key
```

The football-data.org adapter uses `https://api.football-data.org/v4` by
default. The Odds API adapter uses `https://api.the-odds-api.com/v4` by default.
The API-Football adapter uses `https://v3.football.api-sports.io` by default.
The SportMonks adapter uses `https://api.sportmonks.com/v3` by default. Nutmeg
stores raw provider responses for auditability, but does not store API key values.

Provider fixture sync is disabled by default. To run a controlled admin dry-run
that fetches and normalizes football-data.org fixtures without writing canonical
tables:

```bash
export NUTMEG_PROVIDER_SYNC_ENABLED=true
export NUTMEG_ADMIN_API_TOKEN=replace-with-local-secret
curl -X POST http://localhost:8000/api/v1/providers/football-data.org/sync/fixtures \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"provider_competition_id":"PL","canonical_competition_id":"EPL","season":"2025","dry_run":true}'
```

To persist normalized competitions, seasons, teams, fixtures, results, and
provider mappings to Postgres, set `"dry_run": false`. Commit sync requires an
explicit `canonical_competition_id` so provider IDs are mapped intentionally.

The Odds API event odds sync follows the same guarded pattern. It fetches one
provider event at a time and requires an explicit Nutmeg fixture id:

```bash
curl -X POST http://localhost:8000/api/v1/providers/the-odds-api/sync/event-odds \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"sport_key":"soccer_epl","provider_event_id":"event-id","canonical_fixture_id":"fix_epl_001","regions":"eu","markets":"h2h,spreads","dry_run":true}'
```

To persist odds, set `"dry_run": false`. The sync writes raw payloads,
`provider_entity_mappings`, and `odds_snapshots` with `snapshot_time_utc`,
bookmaker, market type, line, side, decimal odds, implied probability, fair
probability, and overround.

SportMonks fixture availability sync follows the same guarded pattern. It
fetches one provider fixture's lineup payload and the selected teams' injury
payloads, then normalizes both as time snapshots:

```bash
curl -X POST http://localhost:8000/api/v1/providers/sportmonks/sync/fixture-availability \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"provider_fixture_id":"fixture-id","canonical_fixture_id":"fix_epl_001","team_mappings":[{"provider_team_id":"home-provider-team","canonical_team_id":"fd_team_57"},{"provider_team_id":"away-provider-team","canonical_team_id":"fd_team_64"}],"dry_run":true}'
```

To persist availability snapshots, set `"dry_run": false`. The sync writes raw
payloads, `provider_entity_mappings`, `lineup_snapshots`, and
`player_availability_snapshots`, plus normalized `provider_observations` for
lineup type, starter probability, starter status, injury status, injury reason,
and expected return date. Team mappings are explicit so provider IDs are not
silently treated as canonical Nutmeg IDs.

After odds snapshots are stored, inspect competition-level coverage and freshness:

```bash
curl "http://localhost:8000/api/v1/providers/odds/coverage?competition_id=EPL&window_days=90&max_snapshot_lag_hours=24"
```

The coverage report returns 1X2 coverage, handicap coverage, fresh snapshot
coverage, bookmaker counts, and a `data_quality_component_patch` containing the
odds-related inputs for the documented Nutmeg data quality score.

To inspect fixture-level odds blockers without writing data:

```bash
curl "http://localhost:8000/api/v1/providers/odds/gaps?competition_id=EPL&provider=the-odds-api&window_days=90&max_snapshot_lag_hours=168&limit=50"
```

The gap report joins fixture coverage, stored `the-odds-api` mappings, and odds
snapshot freshness. Items are labeled as `provider_event_unavailable`,
`no_odds`, `missing_market`, `stale_odds`, or `unmapped` and include a
recommended operator action. When The Odds API does not expose a provider event
for a canonical fixture, the gap payload also includes fallback provider
candidates so the operator can decide whether to probe SportMonks or plan an
API-Football adapter without weakening the canonical fixture model. On the VPS
operator path, run:

```bash
make provider-odds-gap-report-vps
```

To inspect whether SportMonks can recover `provider_event_unavailable` gaps
without writing data, run the admin-only fallback probe:

```bash
curl -X POST http://localhost:8000/api/v1/providers/odds/fallback-probe/sportmonks \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"competition_id":"EPL","primary_provider":"the-odds-api","window_days":90,"max_snapshot_lag_hours":168,"limit":50,"live_provider_probe":false}'
```

The default probe is read-only and does not call SportMonks live odds; it checks
whether SportMonks fixture mappings exist for the current gap set. Set
`"live_provider_probe": true` only for an operator-approved real provider probe.
The VPS helper uses the same safe default:

```bash
make provider-fallback-odds-probe-vps
```

If the probe reports `provider_event_unavailable` plus missing SportMonks
fixture mappings, run the SportMonks discovery/backfill helper. It is dry-run by
default and can now discover the recommended SportMonks league and season before
calling the fixture mapping bootstrap:

```bash
make provider-sportmonks-mapping-backfill-vps
```

The backfill helper calls `/providers/mappings/backfill/sportmonks-fixtures`,
which combines the read-only SportMonks discovery step with the existing guarded
bootstrap. The default recommendation threshold is
`NUTMEG_SPORTMONKS_MAPPING_AUTO_DISCOVERY=true` and a minimum competition score
of `0.75`, so partial-name matches from another country are listed for review
but are not treated as safe mapping inputs.

```bash
NUTMEG_SPORTMONKS_MAPPING_COMPETITION_ID=replace-with-league-id \
NUTMEG_SPORTMONKS_MAPPING_SEASON_ID=replace-with-season-id \
NUTMEG_SPORTMONKS_MAPPING_AUTO_DISCOVERY=false \
make provider-sportmonks-mapping-bootstrap-vps
```

This helper is dry-run by default. Set
`NUTMEG_SPORTMONKS_MAPPING_COMMIT=true` only after reviewing the dry-run match
summary; committed mappings use `sportmonks` as the provider and `fixture` as
the entity type.

API-Football is available as the next fallback when SportMonks coverage does
not include the target league:

```bash
make provider-api-football-discovery-vps
make provider-api-football-mapping-bootstrap-vps
```

The discovery helper is read-only and should return the API-Football league and
season IDs before any commit. The mapping helper defaults to EPL league `39` and
season `2025`, runs dry-run by default, and only persists mappings when
`NUTMEG_API_FOOTBALL_MAPPING_COMMIT=true` is set after operator review. Free
API-Football plans can be season-limited; in that case the helper reports a
skipped/limited status and no provider mappings are written.

To run a competition onboarding assessment that uses stored odds snapshots for
the odds, handicap, and freshness components:

```bash
curl -X POST http://localhost:8000/api/v1/providers/onboarding/assessments \
  -H "Content-Type: application/json" \
  -d '{"competition_id":"EPL","competition_name":"Premier League","target_stage":"beta","window_days":90,"max_snapshot_lag_hours":24,"schedule_coverage":0.99,"result_coverage":0.995,"lineup_injury_coverage":0.7,"historical_stats_completeness":0.82,"provider_consistency":0.93,"historical_sample_size":420,"complete_seasons":1,"market_resolver_tests_passed":true,"score_grid_generation_passed":true,"dry_run":true}'
```

Set `"dry_run": false` and include `X-Nutmeg-Admin-Token` to persist the
assessment into `competition_onboarding_assessments`. Non-odds quality inputs are
supplied explicitly; odds coverage, handicap coverage, and freshness are derived
from stored `odds_snapshots` as of the requested time.

On the VPS operator path, after mapped odds have been committed, run:

```bash
make provider-onboarding-assessment-vps
```

The script persists a beta-stage onboarding assessment using the future 90-day
operating window. The non-odds quality inputs can be overridden with
`NUTMEG_ONBOARDING_*` environment variables; the odds, handicap, and freshness
components still come from stored odds snapshots.

Latest persisted assessments can be read back through:

```bash
curl "http://localhost:8000/api/v1/providers/onboarding/assessments/latest?competition_id=EPL&limit=10"
```

Provider entity mappings can be reviewed through a read-only endpoint:

```bash
curl "http://localhost:8000/api/v1/providers/mappings?provider=football-data.org&entity_type=fixture&limit=50"
```

The response includes recent mapping rows and a provider/entity-type summary.
It only exposes provider IDs, canonical IDs, confidence, and timestamps; it does
not expose provider secrets and does not trigger synchronization.

To bootstrap The Odds API event IDs from football-data.org fixtures, use the
admin-only fixture mapping bootstrap:

```bash
curl -X POST http://localhost:8000/api/v1/providers/mappings/bootstrap/the-odds-api-fixtures \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"provider_competition_id":"PL","canonical_competition_id":"EPL","season":"2025","sport_key":"soccer_epl","regions":"eu","markets":"h2h","dry_run":true}'
```

The bootstrap fetches football-data.org fixtures and The Odds API sport events
from the provider events endpoint, then matches by kickoff time plus normalized
home/away team names. This allows Nutmeg to establish fixture mappings before
odds are available for every event. Set
`"dry_run": false` to persist unambiguous `the-odds-api` fixture mappings. It
does not expose provider secrets and does not place bets or call odds sync for
individual events.

After mapped fixtures have been reviewed, the guarded mapped odds sync can fetch
The Odds API odds in an `eventIds` batch and persist auditable odds snapshots:

```bash
curl -X POST http://localhost:8000/api/v1/providers/the-odds-api/sync/mapped-event-odds \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"canonical_competition_id":"EPL","sport_key":"soccer_epl","regions":"eu","markets":"h2h,spreads","max_mappings":50,"dry_run":true}'
```

Set `"dry_run": false` only after provider mappings and the dry-run coverage
have passed operator review. Commit requests must also include
`"operator_approved": true`; an optional `"operator_approval_note"` is stored in
the provider sync run metadata so the write has an audit trail. The sync writes
per-event raw payloads, `odds_snapshots`, and normalized
`provider_observations`; repeated runs upsert the same provider/bookmaker/
market/line/outcome/snapshot timestamp instead of duplicating odds rows. It does
not place bets or alter predictions. The `/providers` page exposes separate
dry-run and commit forms so the write path remains explicit. On the VPS operator
path, run:

```bash
make provider-odds-sync-vps
```

To run the current gap-remediation sequence on the VPS:

```bash
make provider-gap-remediation-vps
```

This runs mapping bootstrap, guarded mapped odds commit, and odds gap readback
in order for the Nutmeg deployment. It does not alter unrelated containers or
projects.

To run the manual reconciliation review without changing mappings:

```bash
curl -X POST http://localhost:8000/api/v1/providers/mappings/review \
  -H "Content-Type: application/json" \
  -d '{"provider":"football-data.org","entity_type":"fixture","dry_run":true,"limit":1000}'
```

The review flags low-confidence mappings, same-provider canonical collisions,
and stale mapping evidence. Set `"dry_run": false` with `X-Nutmeg-Admin-Token`
to persist an audit row in `provider_mapping_review_runs`; the endpoint does not
auto-merge, auto-split, or rewrite provider mappings.

Latest persisted mapping review runs can be inspected through:

```bash
curl "http://localhost:8000/api/v1/providers/mappings/reviews/latest?limit=10"
```

Provider conflict governance evaluates review evidence against the trusted
provider priority policy, includes recent normalized provider observations, and
estimates the provider-consistency quality impact:

```bash
curl -X POST http://localhost:8000/api/v1/providers/conflicts/evaluate \
  -H "Content-Type: application/json" \
  -d '{"entity_type":"fixture","include_observations":true,"observation_lookback_hours":168,"dry_run":true,"limit":1000}'
```

Set `"dry_run": false` with `X-Nutmeg-Admin-Token` to persist open
`provider_conflict_events`. This records evidence, trusted provider selection,
and `data_quality_score_delta`; it does not automatically change mappings,
fixture data, odds, or predictions. Persisting the same still-open conflict is
idempotent, so operator-controlled scheduled checks do not duplicate the same
quality penalty.

Latest persisted conflict events can be inspected through:

```bash
curl "http://localhost:8000/api/v1/providers/conflicts/latest?status=open&limit=20"
```

After manual review, update the event resolution status with the admin token:

```bash
curl -X PATCH http://localhost:8000/api/v1/providers/conflicts/602/resolution \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"resolution_status":"resolved","resolution_note":"trusted provider payload reviewed"}'
```

The Provider Ops web page exposes the same guarded conflict operations through
server actions. Configure `NUTMEG_ADMIN_API_TOKEN` in the web runtime for API
access and `NUTMEG_PROVIDER_OPS_UI_TOKEN` for the page-level unlock gate. Until
Provider Ops is unlocked, the page shows only read-only state and hides write
controls. After unlock, server actions still verify the signed UI session before
calling admin APIs, and the operator name is stamped into supported approval or
review notes without exposing either token to the browser.

Provider Ops also writes a unified operator audit trail to
`provider_ops_audit_events`. The log records unlock, lock, and guarded admin
action attempts with operator name, request path, outcome, and redacted metadata;
it never stores API key, UI token, or provider credential values. Inspect recent
events through `GET /api/v1/ops/provider-audit/events` with the admin token, or
unlock Provider Ops to view the same trail on the page.

Canonical prematch feature snapshots read open fixture conflict events as a
provider-consistency signal. The impact is traceable in
`features_json.coverage.provider_conflicts` and `source_snapshot_refs`.

`/api/v1/providers/status` uses mock governance data by default. Set
`NUTMEG_PROVIDER_GOVERNANCE_REPOSITORY=postgres` to merge the latest persisted
competition onboarding assessments into the Provider status response. If the
Postgres read is unavailable, the endpoint falls back to the mock governance
snapshot and marks the response as fallback data.

Provider authorization reviews are admin-only audit records. Use them to record
terms checks, allowed use, rate limits, retention permissions, historical-data
permissions, redistribution permissions, owner, and next review due date without
storing provider secrets:

```bash
curl -X POST http://localhost:8000/api/v1/providers/authorizations/reviews \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{
    "provider_name": "api-football",
    "review_reference": "manual-2026-05-08",
    "review_status": "research_only",
    "terms_url": "https://www.api-football.com/terms",
    "allowed_use": "fixture_result_fallback_research_dry_run",
    "rate_limit": "free_plan_provider_defined",
    "next_review_due_at_utc": "2026-11-04T00:00:00Z",
    "evidence_json": {"source": "manual_terms_review"},
    "notes": "Free plan retained as research-only until contract review."
  }'
```

The endpoint updates `provider_authorizations.last_reviewed_at` and
`next_review_due_at` while keeping the review log queryable through
`GET /api/v1/providers/authorizations/reviews`. Provider Ops reads the guarded
review log only after the UI access gate is unlocked and
`NUTMEG_ADMIN_API_TOKEN` is configured for the web runtime.

Parlay recommendations respect the documented data-quality guardrails: fixtures
with `data_quality_score < 50` are skipped, and requests with
`exclude_beta_competitions=true` skip candidate tickets containing beta fixtures.
Skipped candidates are returned as neutral `warnings` in the recommendation
response.

For a local smoke loop against the Docker Postgres database, run the mock
Accuracy seed/evaluation workflow after migrations are loaded:

```bash
python -m nutmeg.accuracy.local_postgres_runner
```

Then start the API with `NUTMEG_ACCURACY_REPOSITORY=postgres` and call
`/api/v1/accuracy/summary` to read the persisted evaluation rows.

The write-side Accuracy job endpoint is disabled by default. For a controlled
local post-match evaluation run against Postgres, enable it explicitly:

```bash
export NUTMEG_ACCURACY_REPOSITORY=postgres
export NUTMEG_ACCURACY_JOBS_ENABLED=true
export NUTMEG_ADMIN_API_TOKEN=replace-with-local-secret
curl -X POST http://localhost:8000/api/v1/accuracy/jobs/run \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"job_type":"mock_postgres_e2e","reset":true}'
```

The endpoint seeds deterministic mock fixtures, stores prediction snapshots,
persists post-match evaluations, updates calibration buckets, and writes a
model comparison report. Each run is recorded in `accuracy_job_runs` with
status, timing, output counts, and any failure message. To inspect recent runs:

```bash
curl http://localhost:8000/api/v1/accuracy/jobs/runs \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

This flow does not place bets or execute real-money actions.

The same guarded endpoint can run a Dixon-Coles v1.5 training/backtest pass
from canonical `fixtures` + `results`. It reads only matches settled before the
requested as-of time, freezes train/validation windows, and defaults to
`dry_run: true` so operators can inspect the selected `rho` and sample counts
before writing `model_backtest_runs` or `model_comparison_reports`:

```bash
curl -X POST http://localhost:8000/api/v1/accuracy/jobs/run \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{
    "job_type": "dixon_coles_training_backtest",
    "reset": false,
    "dry_run": true,
    "competition_id": "EPL",
    "as_of_time_utc": "2026-05-08T00:00:00Z",
    "train_window_days": 365,
    "validation_window_days": 90,
    "promotion_minimum_sample_size": 300
  }'
```

Set `dry_run` to `false` only for an intentional operator-triggered persistence
run after baseline and promotion-gate evidence have been supplied. Candidate
promotion remains a review artifact in `model_promotion_reviews`; the job does
not automatically activate a model version.

For the weekly training pipeline, use the same guarded endpoint with the
operator-controlled scheduler stub. This writes the weekly plan into the
`accuracy_job_runs.metadata_json` audit payload and reuses the Dixon-Coles
training/backtest path. It does not install cron or any background scheduler:

```bash
curl -X POST http://localhost:8000/api/v1/accuracy/jobs/run \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{
    "job_type": "weekly_dixon_coles_training_pipeline",
    "reset": false,
    "dry_run": true,
    "competition_id": "EPL",
    "as_of_time_utc": "2026-05-08T01:00:00Z",
    "weekly_scheduled_for_utc": "2026-05-08T02:00:00Z",
    "weekly_run_label": "weekly-epl-dc",
    "train_window_days": 365,
    "validation_window_days": 90
  }'
```

The write-side prematch prediction job endpoint is also disabled by default. It
uses stored odds, lineup, and injury snapshot freshness to build feature
snapshots, then writes score grids and prediction snapshots. Enable it only for
controlled local or VPS operations:

```bash
export NUTMEG_PROVIDER_GOVERNANCE_REPOSITORY=postgres
export NUTMEG_PREDICTION_JOBS_ENABLED=true
export NUTMEG_ADMIN_API_TOKEN=replace-with-local-secret
curl -X POST http://localhost:8000/api/v1/predictions/jobs/run \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"job_type":"mock_prematch_predictions","fixture_ids":["fix_epl_001"],"dry_run":true,"max_snapshot_lag_hours":24}'
```

For provider-synced canonical fixtures, use the windowed canonical job:

```bash
curl -X POST http://localhost:8000/api/v1/predictions/jobs/run \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"job_type":"canonical_prematch_predictions","competition_id":"EPL","window_hours":72,"dry_run":true,"max_snapshot_lag_hours":24,"limit":100}'
```

Set `"dry_run": false` only after canonical fixtures exist in Postgres through
provider sync or deterministic seed data. Canonical jobs enforce an odds quality
gate by default: fixtures without any stored 1X2 odds snapshot are skipped, while
stale odds or missing handicap odds are surfaced as warnings and reflected in the
feature snapshot data-quality score. Pass `"enforce_odds_quality_gate": false`
only for controlled diagnostics. Each run is recorded in
`prediction_job_runs` with generated IDs, data-quality scores, skipped fixtures,
warnings, timing, and failure status. To inspect recent runs:

If canonical fixture context includes `rho`, the prediction snapshot uses the
Dixon-Coles v1.5 low-score adjustment path and records `rho` plus any
`time_decay_weight` in `model_notes`. For canonical fixtures without stored
`aggregate_context_json` lambdas, the job
queries settled historical results in the same competition with
`kickoff_time_utc` and `settled_at` no later than the prediction timestamp. If
both teams meet the configured minimum sample count, lambdas are derived from
rolling attack and defense strength; otherwise the competition cold-start
baseline is used and documented in the prediction explanation payload.

The offline Dixon-Coles training helpers live in `nutmeg.modeling` and are pure
functions for now. They accept historical matches, freeze a train/validation
window relative to `as_of_time_utc`, estimate transparent attack/defense
parameters, select `rho` by negative weighted log likelihood, and return a
report. `nutmeg.accuracy` includes bridge helpers that convert that report into
a walk-forward `BacktestRunSchema`, persistable metrics/calibration payloads,
and a candidate-vs-baseline comparison stub. When Brier score or calibration
metrics have not yet been computed, the comparison deliberately stays in
`needs_review`.

```bash
curl http://localhost:8000/api/v1/predictions/jobs/runs \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

For a controlled one-shot prematch operations workflow, enable the guarded
workflow endpoint. It runs the same audited prediction job first and then, for
the generated fixture set, attempts stored-market-prediction parlay generation.
The top-level result is recorded in `prematch_workflow_runs`.

```bash
export NUTMEG_PREDICTION_JOBS_ENABLED=true
export NUTMEG_PREMATCH_WORKFLOW_ENABLED=true
export NUTMEG_PARLAY_REPOSITORY=postgres
export NUTMEG_ADMIN_API_TOKEN=replace-with-local-secret
curl -X POST http://localhost:8000/api/v1/ops/prematch/run \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{
    "prediction_job_type": "canonical_prematch_predictions",
    "competition_id": "EPL",
    "window_hours": 72,
    "dry_run": true,
    "run_parlay_generation": true,
    "parlay_pass_type": "2x1"
  }'
```

Committed workflow runs require stored canonical fixtures, odds snapshots, an
admin token, and `NUTMEG_PARLAY_REPOSITORY=postgres`. The workflow still does
not schedule itself and does not place bets. Recent workflow audit records can
be inspected through:

```bash
curl http://localhost:8000/api/v1/ops/prematch/runs \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

To orchestrate explicit provider sync tasks in one audited operation, enable
the provider sync workflow. The workflow does not discover matches or provider
event IDs by itself; operators must pass the exact fixture, event, and team
mappings to keep provider identity mapping reviewable.

```bash
export NUTMEG_PROVIDER_SYNC_ENABLED=true
export NUTMEG_PROVIDER_SYNC_WORKFLOW_ENABLED=true
export NUTMEG_ADMIN_API_TOKEN=replace-with-local-secret
curl -X POST http://localhost:8000/api/v1/ops/provider-sync/run \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{
    "dry_run": true,
    "fixture_sync": {
      "provider_competition_id": "PL",
      "canonical_competition_id": "EPL",
      "season": "2025"
    },
    "odds_syncs": [
      {
        "sport_key": "soccer_epl",
        "provider_event_id": "event-id",
        "canonical_fixture_id": "fd_fixture_123"
      }
    ],
    "availability_syncs": [
      {
        "provider_fixture_id": "sportmonks-fixture-id",
        "canonical_fixture_id": "fd_fixture_123",
        "team_mappings": [
          {"provider_team_id": "home-provider-team", "canonical_team_id": "fd_team_57"},
          {"provider_team_id": "away-provider-team", "canonical_team_id": "fd_team_64"}
        ]
      }
    ],
    "run_conflict_detection": true,
    "conflict_observation_lookback_hours": 168,
    "conflict_limit": 1000
  }'
```

To run prediction generation immediately after the provider syncs, also enable
`NUTMEG_PREDICTION_JOBS_ENABLED=true` and `NUTMEG_PREMATCH_WORKFLOW_ENABLED=true`,
then set `"run_prematch_workflow": true` with a `prematch` object.

For local or VPS rehearsal without data-source API keys, enable the explicit
mock dry-run fallback:

```bash
export NUTMEG_PROVIDER_SYNC_MOCK_DRY_RUN_ENABLED=true
```

When this flag is enabled, dry-run provider tasks use deterministic Nutmeg
sample payloads only if the corresponding provider key is absent. The response
warnings include `mock_dry_run_sample_used:no_api_key`, no external provider is
called, and no raw provider payloads or canonical sync writes are committed by
the child tasks.

Runtime key readiness can be checked with the admin token:

```bash
curl http://localhost:8000/api/v1/providers/runtime/credentials \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

The response reports `key_configured`, `dry_run_mode`, `commit_mode`,
`runtime_env_var`, and next action per provider. It deliberately returns only
booleans and environment variable names, not API key values.

Provider runtime monitoring reads the latest persisted snapshot per provider:

```bash
curl "http://localhost:8000/api/v1/providers/runtime/monitoring?limit=20" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

To record a non-live monitoring snapshot from the same runtime probes:

```bash
curl -X POST http://localhost:8000/api/v1/providers/runtime/monitoring/snapshot \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"live_probe":false}'
```

The monitoring payload stores probe status, latency, derived error-rate,
rate-limit placeholders, fallback flags, and next action hints. It never stores
API key, token, password, or credential values.

Monitoring responses include `alert_level`, `alerts`, and `thresholds`.
Alert rows are read-only operational hints for P0/P1/P2 incident triage; they
do not trigger betting or provider writes. Alert thresholds can be tuned with
environment variables:

```bash
export NUTMEG_PROVIDER_RUNTIME_LATENCY_P2_MS=1500
export NUTMEG_PROVIDER_RUNTIME_LATENCY_P1_MS=5000
export NUTMEG_PROVIDER_RUNTIME_ERROR_RATE_P1=1.0
export NUTMEG_PROVIDER_RUNTIME_PLAN_LIMIT_P2=0.5
export NUTMEG_PROVIDER_RUNTIME_FALLBACK_USAGE_RATE_P1=0.5
export NUTMEG_PROVIDER_RUNTIME_INCIDENT_RETENTION_DAYS=90
export NUTMEG_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_ENABLED=false
export NUTMEG_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_ADAPTER=provider_ops
export NUTMEG_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_DRY_RUN=true
export NUTMEG_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_WEBHOOK_URL=
```

For a VPS non-live monitoring snapshot:

```bash
make provider-runtime-monitoring-vps
```

Set `NUTMEG_PROVIDER_RUNTIME_LIVE_PROBE=true` only when an operator explicitly
wants the VPS script to perform live provider probes.

The same script records an incident report when the alert level meets
`NUTMEG_PROVIDER_RUNTIME_INCIDENT_THRESHOLD` (default `P1`). To install the VPS
cron entry, run:

```bash
make provider-runtime-monitoring-cron-vps
```

The cron entry is written to `/etc/cron.d/nutmeg-provider-runtime-monitoring`
and appends non-secret output to `/opt/nutmeg/logs/provider-runtime-monitoring.log`.
The incident report API is admin-only:

```bash
curl http://localhost:8000/api/v1/providers/runtime/monitoring/incidents \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

Provider Ops displays runtime incident reports when the page is unlocked, plus
a 30-day default summary/trend window from the same admin-only API. The trend
response fills every date in the requested window, including zero-incident days.
Override the window, page, or filters with query parameters such as
`/providers/runtime/monitoring/incidents?limit=20&offset=20&lookback_days=14&incident_status=open&alert_level=P1`.
Operators can mark an incident as `acknowledged`, `resolved`, `ignored`, or
reopened as `open`; the update records reviewer, timestamps, resolution note,
and a notification stub payload without sending external messages or storing
provider secrets. The status API is admin-only:

```bash
curl -X PATCH http://localhost:8000/api/v1/providers/runtime/monitoring/incidents/77/status \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -H "X-Nutmeg-Operator: provider-ops-reviewer" \
  -d '{"incident_status":"resolved","resolution_note":"Provider recovered after plan review."}'
```

When the incident record endpoint creates a new report, it also evaluates the
notification adapter and writes `notification_status` plus a non-secret
`notification_payload_json` back to the same report. The default remains closed:
`NUTMEG_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_ENABLED=false` records
`not_configured`. Enabling the `provider_ops` adapter with dry-run disabled
marks the internal Provider Ops notification as `sent` without external
delivery. The `webhook` adapter is schema-ready only; with dry-run enabled it
records `skipped`, and without a destination it records `not_configured`. Do not
store webhook URLs, API keys, or tokens in payload metadata.

The local/VPS monitor also prunes old incident reports through the admin-only
retention endpoint after each run. Override the cron/helper retention window
with `NUTMEG_PROVIDER_RUNTIME_RETENTION_DAYS`; if omitted, the backend uses
`NUTMEG_PROVIDER_RUNTIME_INCIDENT_RETENTION_DAYS`.

VPS provider helper scripts that call admin-only APIs use a shared redacting
request helper. If an API call fails, the scripts print the request path, status
code, and a short response/error summary, but not the admin token or provider
secrets. This is intentional so cron logs and terminal output remain safe to
share during incident triage.

Successful VPS helper and cron runs also post a non-secret summary to the
admin-only Provider Ops run history endpoint:

```bash
curl http://localhost:8000/api/v1/ops/provider-runs \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

The run history stores `run_name`, `status`, `duration_ms`, `exit_code`, a
sanitized `summary_json`, and a short output excerpt. Helper scripts install a
shared shell `ERR` trap after the admin token is loaded, so unexpected exits are
recorded as `failure` whenever the API is reachable. It is displayed in Provider
Ops when the page is unlocked, separate from the human operator audit trail.

For a live credential probe, use the admin-only runtime probe endpoint:

```bash
curl "http://localhost:8000/api/v1/providers/runtime/probes?live=true" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

Without `live=true`, this endpoint only reports key presence. With `live=true`,
Nutmeg performs low-cost provider probes for supported adapters and still
returns only status, counts, and non-secret metadata. API-Football uses a
low-cost Premier League league discovery probe.

The API-key application checklist is also admin-only:

```bash
curl http://localhost:8000/api/v1/providers/runtime/api-key-checklist \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

Recommended free/trial order for the first real-provider dry-run:

1. football-data.org free key for fixtures/results:
   `NUTMEG_FOOTBALL_DATA_API_KEY`
   ([apply](https://www.football-data.org/client/register),
   [docs](https://docs.football-data.org/general/v4/policies.html)).
2. SportMonks trial key for lineups/injuries:
   `NUTMEG_SPORTMONKS_API_KEY`
   ([apply](https://my.sportmonks.com/register),
   [docs](https://docs.sportmonks.com/football)).
3. The Odds API free key for odds API plumbing:
   `NUTMEG_THE_ODDS_API_KEY`
   ([site](https://the-odds-api.com/),
   [docs](https://the-odds-api.com/liveapi/guides/v4/)).
   Its free tier may not cover soccer EPL odds, so treat it as a key/setup
   smoke until soccer coverage is confirmed.
4. API-Football free key for future broad fixture/result coverage research:
   `NUTMEG_API_FOOTBALL_API_KEY`
   ([apply](https://dashboard.api-football.com/register),
   [docs](https://www.api-football.com/documentation-v3)).
   Nutmeg lists this because the V2 docs identify API-Football as a production
   provider candidate, but the adapter is still planned rather than active.

To evaluate provider observations from the same synced fixtures before the
prematch workflow runs, set `"run_conflict_detection": true`. The workflow reads
recent `provider_observations`, writes open `provider_conflict_events` only when
`"dry_run": false`, and reuses existing open conflict events for idempotency.
Use `conflict_observation_lookback_hours` and `conflict_limit` to tune the
observation window.

Recent provider workflow audit records and a single run detail can be inspected
through:

```bash
curl http://localhost:8000/api/v1/ops/provider-sync/runs \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"

curl http://localhost:8000/api/v1/ops/provider-sync/runs/501 \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret"
```

Operators can validate explicit provider IDs before a dry-run and save reviewed
ID sets as reusable templates:

```bash
curl -X POST http://localhost:8000/api/v1/ops/provider-sync/preflight \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"dry_run": true, "odds_syncs": [{"sport_key": "soccer_epl", "provider_event_id": "event-id", "canonical_fixture_id": "fd_fixture_123"}]}'

curl -X POST http://localhost:8000/api/v1/ops/provider-sync/templates \
  -H "Content-Type: application/json" \
  -H "X-Nutmeg-Admin-Token: replace-with-local-secret" \
  -d '{"template_name": "EPL explicit IDs dry-run", "dry_run": true, "odds_syncs": [{"sport_key": "soccer_epl", "provider_event_id": "event-id", "canonical_fixture_id": "fd_fixture_123"}]}'
```

Provider Ops also exposes a guarded dry-run form for this workflow after the
page-level access gate is unlocked. The form
requires explicit provider competition, event, fixture, and team mapping IDs;
it does not discover matches, schedule itself, or provide a committed sync
button. The form supports preflight validation, template saving, and multiple
odds or availability tasks per dry-run template. Saved templates include a
task review matrix so operators can inspect provider IDs, canonical IDs, team
mapping counts, and scoped preflight issues before loading or executing a
dry-run. The run history can be expanded to inspect audit metadata, child sync
run IDs, raw payload IDs, warnings, and error payloads. Saved templates can be
loaded back into the dry-run form for operator review; dry-run execution still requires the
operator approved dry-run checkbox and never performs committed sync writes.
Templates can be updated or archived from Provider Ops, and dry-run approvals
are written to `provider_sync_workflow_operator_approvals` so an operator
decision can be linked back to the workflow run and reviewed later.

Provider Ops also includes a Prediction Quality Gate panel. It calls the
admin-only canonical prediction job in `dry_run` mode, keeps the odds quality
gate enabled by default, and reports generated fixtures, skipped fixtures, and
warnings from stored odds snapshots. The panel does not commit prediction
snapshots and does not place bets.

Provider Ops also includes an Odds Coverage Gaps panel. It is read-only and
surfaces fixture-level `provider_event_unavailable`, `no_odds`, `stale_odds`,
missing market, and unmapped provider mapping blockers so the next operator
action is visible before another prediction dry-run. Provider-event unavailable
rows include fallback provider candidates when a secondary provider can be
probed or planned for coverage recovery. A separate Fallback Odds Probe panel
shows whether SportMonks mappings exist and whether any read-only live probe has
found normalized 1X2 or handicap odds that could be queued for a future
operator-reviewed snapshot sync.

Provider Ops also includes a Mapped Odds Sync dry-run panel. It uses reviewed
`the-odds-api` fixture mappings to batch-check `eventIds`, normalized odds
counts, and odds coverage without writing `odds_snapshots`. Persisting mapped
odds remains an intentional operator action through the guarded API or
`make provider-odds-sync-vps`.
After that commit, `make provider-odds-gap-report-vps` confirms remaining
fixture-level blockers, and `make provider-onboarding-assessment-vps` refreshes
the persisted competition readiness row used by Provider Ops.

Provider Ops now starts with a Runbook panel that summarizes the operator chain:
runtime keys, fixture mappings, odds coverage, prediction quality gate, and
conflict governance. It is read-only and computes the current blocker from
existing API responses so the dry-run controls stay explicit and auditable.

To run the full migration + seed + readback smoke in one command:

```bash
python -m nutmeg.accuracy.postgres_smoke
```

To run the same smoke in an isolated temporary Docker container without using a
fixed host port:

```bash
make smoke-postgres
# or
scripts/accuracy-postgres-smoke.sh
```

The live Postgres integration test is opt-in:

```bash
NUTMEG_RUN_POSTGRES_SMOKE=1 pytest apps/api/tests/integration/test_accuracy_postgres_smoke.py
```

Open:

```text
http://localhost:8000/api/v1/health
http://localhost:8000/api/v1/fixtures
http://localhost:8000/api/v1/fixtures/fix_epl_001/prediction
http://localhost:8000/api/v1/upsets
http://localhost:8000/api/v1/accuracy/summary
http://localhost:8000/api/v1/providers/status
http://localhost:8000/api/v1/providers/mappings
http://localhost:8000/api/v1/providers/mappings/reviews/latest
http://localhost:8000/api/v1/providers/conflicts/latest
http://localhost:8000/docs
```

Run tests:

```bash
pytest
```

Run linting and type checks:

```bash
ruff check .
mypy apps/api/src
```

Run the frontend MVP locally:

```bash
cd apps/web
npm install
export NUTMEG_API_BASE_URL=http://localhost:8000/api/v1
npm run dev -- --port 3001
```

If the API is not running, non-recommendation pages can still use deterministic
local fixtures. The final-answer path no longer falls back to old parlay mock
recommendations by default. For local UI-only checks without an API, enable the
explicit development fallback:

```bash
export NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS=true
```

Do not enable that flag for ordinary production traffic; production should read
`answer_set` from the recommendation API.

Open:

```text
http://localhost:3001/dashboard
http://localhost:3001/fixtures/fix_epl_001
http://localhost:3001/parlays
http://localhost:3001/upsets
http://localhost:3001/accuracy
http://localhost:3001/providers
```

Run frontend checks:

```bash
cd apps/web
npm run typecheck
npm run lint
npm run build
npm run e2e:install
npm run e2e
```

Start PostgreSQL, Redis, and the API with Docker Compose:

```bash
docker compose up --build
```

The migration script at `db/migrations/0001_core_schema.sql` is mounted into
the PostgreSQL container as initialization SQL.

## VPS Deployment

The VPS deployment uses `docker-compose.vps.yml`, local-only service ports, and
nginx for the public domain. The VPS compose profile enables the guarded
Provider Sync dry-run workflow and seeds one explicit-ID dry-run review
template; it still does not schedule syncs, place bets, or expose provider
secrets. The scripts require SSH key access; do not store VPS passwords in the
repository.

```bash
export NUTMEG_DEPLOY_TARGET=root@156.236.76.121
make deploy-vps
make smoke-vps
make acceptance-vps
```

Optional deployment flags:

```bash
export NUTMEG_SEED_ACCURACY=1      # seed deterministic Accuracy test rows
export NUTMEG_PROVIDER_SYNC_WORKFLOW_ENABLED=false  # hide Provider Sync workflow
export NUTMEG_PROVIDER_SYNC_MOCK_DRY_RUN_ENABLED=false  # require real provider keys for dry-runs
export NUTMEG_DEPLOY_NGINX=0       # skip nginx config update
export NUTMEG_PUBLIC_BASE_URL=https://goodmood.mcpup.top
```

The VPS scripts only operate on the configured Nutmeg remote directory and
`nutmeg` Docker Compose project. They do not remove or modify unrelated
containers.

To exercise Provider Sync readiness on the VPS, run:

```bash
make provider-sync-dry-run-vps
```

The script reads the Nutmeg admin token from the VPS `.env`, checks runtime
credentials, calls the live probe endpoint when keys are configured, and executes
an operator-approved dry-run. Without data-source API keys it uses deterministic
mock samples. With a football-data.org key it runs a real fixture dry-run and
uses provider probes for odds and availability keys until valid provider event
IDs are mapped.

After keys are configured, the VPS mapping bootstrap can persist football-data.org
fixtures and high-confidence The Odds API fixture mappings:

```bash
make provider-mapping-bootstrap-vps
```

This script commits the current EPL football-data.org fixture set, bootstraps
The Odds API event-to-fixture mappings, and runs a dry-run mapping review to
guard against critical mapping conflicts.

SportMonks fixture mapping bootstrap is available as a separate guarded helper.
By default it uses auto-discovery to find the SportMonks league and season IDs
and then runs the bootstrap in dry-run mode:

```bash
make provider-sportmonks-mapping-backfill-vps
```

```bash
NUTMEG_SPORTMONKS_MAPPING_COMMIT=true \
make provider-sportmonks-mapping-backfill-vps
```

Omit `NUTMEG_SPORTMONKS_MAPPING_COMMIT=true` for the default dry-run. To force
explicit reviewed IDs instead of discovery, set
`NUTMEG_SPORTMONKS_MAPPING_AUTO_DISCOVERY=false` with
`NUTMEG_SPORTMONKS_MAPPING_COMPETITION_ID` and
`NUTMEG_SPORTMONKS_MAPPING_SEASON_ID`.

API-Football fixture mapping bootstrap follows the same dry-run-first pattern
and is useful when SportMonks trial coverage does not include the target
competition:

```bash
make provider-api-football-discovery-vps
make provider-api-football-mapping-bootstrap-vps
```

Set `NUTMEG_API_FOOTBALL_MAPPING_COMMIT=true` only after reviewing the dry-run
match count and ambiguity count. Free API-Football plans can be season-limited;
when the requested season is blocked, Nutmeg reports a limited/skipped status
instead of writing mappings.

## V3.1 Quality-Signal Watchlist Probe

The final-answer quality-signal profile grid now has an opt-in watchlist lane
for near-ROI-floor candidates. A rejected candidate is only placed on the
watchlist when its blocking reason is the absolute `candidate_roi` floor and it
still satisfies no-harm plus final-hit, ROI, and profit/loss delta thresholds.
The watchlist does not promote a runtime rule, does not change the default
profile, and is not exposed to ordinary users.

Smoke report:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_medium_price_negative_edge_quality_signal_watchlist_grid_smoke_v1.json`.
It covers the combined core plus expanded A-leagues suite with a lighter
`1x1,2x1,3x1` single-only replay. Result:
`report_key=historical_final_answer_quality_signal_profile_grid:f4d8c3d1fbd43079`,
`accepted_count=0`, `watchlist_count=0`, `candidate_roi=-0.0466076`, and the
candidate was rejected by `candidate_roi_below_floor` plus
`objective_improvement_missing`. This confirms the new lane stays strict when a
quality-signal penalty does not improve the final answer.

## V3.1 Quality-Signal Progress Trace

The same profile-grid CLI can now write a JSONL progress trace with
`--progress-jsonl-path`. The trace records grid start, baseline completion,
candidate start/completion, cache status, candidate status, rejection reasons,
watchlist state, and elapsed seconds. This is intended for long full-grid
historical runs, so a slow candidate leaves recoverable evidence instead of a
silent wait.

Smoke artifacts:
`configs/recommendations/historical_reports/euro_2024_quality_signal_profile_grid_progress_smoke_v1.json`
and
`configs/recommendations/historical_reports/euro_2024_quality_signal_profile_grid_progress_smoke_v1.jsonl`.
The smoke run produced `progress_event_count=5`,
`report_key=historical_final_answer_quality_signal_profile_grid:8a803597476d4bf1`,
`baseline_evaluation_elapsed_seconds=0.002443`, and
`candidate_evaluation_elapsed_seconds=0.002845`.

## V3.1 Quality-Signal Light Batch Search

Two bounded combined-suite searches now exercise the progress trace on real
historical slices:

- `configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_quality_signal_light_batch_a_v1.json`
- `configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_quality_signal_light_batch_b_v1.json`
- `configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_quality_signal_light_batch_summary_v1.json`

The search covers `ITA_SERIE_B`, `ENG_CHAMPIONSHIP`, `FRA_LIGUE_2`, and
`ESP_SEGUNDA_DIVISION` with the medium-price negative-edge quality-signal
penalty. Batch A uses `1x1,2x1,3x1` single recommendations; Batch B uses
`4x1,5x1,6x1,7x1,8x1` single recommendations. Across 8 candidates, the result
is `accepted_count=0`, `watchlist_count=0`, and `rejected_count=8`.

Batch A affected candidate legs but did not change the final answer. Batch B
changed up to 5 final answers for some competitions but produced no hit, ROI,
or profit/loss improvement and stayed below the absolute ROI floor. This keeps
the fixed quality-signal penalty out of the production/default path and points
the next search back toward replacement/value-guard or a narrower model signal.

## V3.1 Short-Odds Replacement Rule Manifest

The short-odds replacement evidence chain now has a reusable internal rule
manifest layer. `nutmeg.recommendations.short_odds_replacement_rules` owns the
runtime rule model, typed constraint parsing, competition allow/exclude checks,
and a manifest report builder. The existing runtime shadow replay uses the same
loader, so staged rules no longer live only inside offline replay code.

CLI:

```bash
uv run nutmeg-recommendation-short-odds-replacement-rule-manifest \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_explicit_harm_guard_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_odds_replacement_rule_manifest_explicit_harm_guard_v1.json \
  --enable-shadow-replay \
  --min-rule-count 1 \
  --min-allowed-competition-count 4
```

Generated report:
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_odds_replacement_rule_manifest_explicit_harm_guard_v1.json`.
It produced
`report_key=short_odds_replacement_rule_manifest:352bd292399a9b33`,
`status=ready`, `selected_rule_count=1`, `enabled_rule_count=1`,
`allowed_competition_ids=EPL,FRA_LIGUE_1,GER_BUNDESLIGA,ITA_SERIE_A`,
`excluded_competition_ids=ESP_LA_LIGA`, and `blockers=[]`.

The manifest verifies passed runtime shadow evidence, accepted rolling
admission, no production/public response change, explicit no-harm constraints,
and upstream source report keys. It is still an internal staging artifact: it
does not write the default profile, does not change the public final answer,
does not add automated betting, and must not be exposed as user-facing strategy
text.

## V3.1 Short-Odds Final-Answer Adapter

The staged short-odds rule can now be exercised through an explicit opt-in
final-answer adapter. The adapter receives an existing `RecommendationSelection`,
a scored candidate pool, and a `ShortOddsRuntimeRuleSet`; when enabled it may
replace at most one unlocked leg, then recomputes the full parlay evaluation
with `evaluate_parlay`. By default it is disabled and is not wired into the
ordinary recommendation path.

CLI smoke:

```bash
uv run nutmeg-recommendation-short-odds-final-answer-adapter-smoke \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_explicit_harm_guard_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_odds_final_answer_adapter_smoke_explicit_harm_guard_v1.json \
  --enable-adapter \
  --enable-shadow-replay \
  --competition-id EPL
```

Generated smoke:
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_odds_final_answer_adapter_smoke_explicit_harm_guard_v1.json`.
It produced `report_key=short_odds_final_answer_adapter:900269ab3becc4c4`,
`status=applied`, `selected_rule_count=1`, `eligible_candidate_count=1`,
`default_path_changed=false`, and `public_response_changed=false`. In the
deterministic smoke fixture the adapter replaced `adapter_selected_a` with
`adapter_replacement_c`, taking `hit_probability_delta=-0.00648` while improving
`roi_delta=+0.02679264` and `expected_value_delta=+0.05358528`.

The smoke uses a deterministic candidate fixture with the real activated
short-odds rule profile. It proves the execution adapter can apply the staged
rule and recompute the final-answer selection, but it still does not publish the
change to users, does not write the default profile, and does not place bets.

## V3.1 Global Planner Short-Odds Adapter Branch

The global final-answer planner now has a default-off short-odds adapter branch.
When `short_odds_adapter_enabled=false`, the planner behaves as before. When it
is enabled with `short_odds_adapter_shadow_only=true`, the planner evaluates the
adapter and records an internal summary, but keeps the selected final answer
unchanged. Only explicit opt-in with `short_odds_adapter_shadow_only=false` may
replace the best option, and the replacement is then re-scored and re-arbitrated
inside the global planner.

Generated smoke:
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_global_planner_short_odds_adapter_branch_smoke_v1.json`.
It compares `default_disabled`, `shadow_only`, and `explicit_opt_in` on the same
deterministic planner candidate pool with the real activated short-odds rule
profile. The default and shadow paths both selected `B,A`, so
`default_path_changed=false` and `shadow_path_changed=false`; the explicit
opt-in path selected `B,C`, so `explicit_opt_in_changed=true`.

The public API sanitizer also strips `short_odds_final_answer_adapter` from
recommendation explanations, matching the product rule that ordinary users see
the final answer, not the internal strategy. This branch remains an internal
quality staging path: it does not write the default profile, does not enable
automated betting, does not touch VPS/deployment, and does not introduce any
guaranteed-profit language.

## V3.1 Global Planner Short-Odds Adapter Gate

The planner adapter branch is now wired into the historical quality-gate path.
`nutmeg-recommendation-global-planner-short-odds-adapter-gate` combines the
planner branch smoke report with the real-history runtime shadow replay report,
then `nutmeg-recommendation-benchmark-quality-gate` and
`nutmeg-recommendation-benchmark-cycle` can consume the resulting report as
formal cycle evidence.

CLI gate:

```bash
uv run nutmeg-recommendation-global-planner-short-odds-adapter-gate \
  --planner-branch-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_global_planner_short_odds_adapter_branch_smoke_v1.json \
  --runtime-shadow-replay-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_switch_staged_explicit_harm_guard_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_global_planner_short_odds_adapter_gate_v1.json
```

Generated gate:
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_global_planner_short_odds_adapter_gate_v1.json`.
It produced `report_key=global_planner_short_odds_adapter_gate:5e5847f5ba9d4166`,
`status=passed`, `planner_default_path_changed=false`,
`planner_shadow_path_changed=false`, `planner_explicit_opt_in_changed=true`,
`runtime_final_answer_count=30`, `runtime_changed_final_answer_count=17`,
`runtime_final_answer_hit_rate_delta=0.0`, `runtime_roi_delta=+0.0176388715`,
`runtime_profit_loss_delta=+1.0583322928`, and zero runtime harm counts against
the original final answers.

The cycle summary now carries the planner adapter gate key, status, path-change
guards, real-history final-answer counts, ROI delta, and no-harm counters. This
keeps the short-odds adapter inside the internal quality process: the default
planner path is still closed, public responses stay sanitized, production
recommendations are unchanged unless explicitly opted in, and the system still
does not place bets or promise profit.

## V3.1 Short-Odds Adapter Sample Expansion

The short-odds planner adapter now has a supplemental sample-expansion gate. It
combines the core planner adapter gate with one or more additional runtime
shadow replay reports and separates safety from promotion readiness: a wider
sample can be safe to keep researching while still being blocked from promotion
if it does not activate replacements.

The runtime shadow replay also treats a no-change replay as
`average_hit_probability_delta_vs_original=0.0`, which avoids turning an
unchanged shadow path into a false probability-loss failure.

Expanded A-league probe:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_runtime_shadow_replay_expanded_probe_v1.json`.
It produced `report_key=historical_short_odds_runtime_shadow_replay:72a9022e7324777a`,
`status=shadow_replay_passed`, `final_answer_count=56`,
`changed_final_answer_count=0`, and zero hit-rate/ROI/profit-loss deltas with no
harm counts.

CLI sample-expansion gate:

```bash
uv run nutmeg-recommendation-global-planner-short-odds-adapter-sample-expansion \
  --base-gate-report configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_global_planner_short_odds_adapter_gate_v1.json \
  --supplemental-runtime-shadow-replay-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_runtime_shadow_replay_expanded_probe_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_global_planner_short_odds_adapter_sample_expansion_v1.json
```

Generated expansion report:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_global_planner_short_odds_adapter_sample_expansion_v1.json`.
It produced
`report_key=global_planner_short_odds_adapter_sample_expansion:d6af7accf570d9b7`,
`status=research_only`, `passed=true`, `promotion_ready=false`,
`combined_final_answer_count=86`, `combined_changed_final_answer_count=17`,
`combined_final_answer_hit_rate_delta=0.0`, `combined_roi_delta=+0.0032266228`,
and zero combined harm counts. The only watchlist item is
`supplemental_changed_final_answer_count`, because the expanded sample covered
56 eligible final answers but did not activate any replacement. This keeps the
adapter in internal research/staging, not user-facing production.

The same sample-expansion report is now visible to the main benchmark quality
gate and benchmark cycle summary. By default it is treated as optional evidence:
`research_only` reports can pass safety checks without implying promotion. Use
`--require-global-planner-short-odds-adapter-sample-expansion` when a cycle must
attach the evidence, and add
`--require-global-planner-short-odds-adapter-sample-expansion-promotion-ready`
only when the release/promotion decision explicitly requires an activated
sample. The cycle CLI exposes the same options with the `--gate-` prefix, so
saved cycle reports can carry the sample-expansion key, status, promotion flag,
combined final-answer counts, ROI delta, harm count, and watchlist checks.

## V3.1 Short-Odds Adapter Activation Gap

The short-odds adapter now has a dedicated activation-gap diagnostic. It reads a
candidate marginal audit plus the staged short-odds rule profile, then explains
why the current rule does or does not activate on the audited final-answer
surface. The report keeps two views separate:

- current rule path: the exact staged rule, including its existing competition
  allowlist and constraints
- probe path: the same constraints replayed against the audited competition set
  to see whether a safe activation candidate exists

CLI:

```bash
uv run nutmeg-recommendation-short-odds-adapter-activation-gap \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_explicit_harm_guard_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_gap_v1.json \
  --min-probe-changed-final-answer-count 1 \
  --min-probe-roi-delta 0 \
  --min-probe-profit-loss-delta 0 \
  --max-probe-harm-count-vs-original 0 \
  --max-probe-final-hit-harm-count-vs-original 0 \
  --max-probe-profit-loss-harm-count-vs-original 0
```

Generated report:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_gap_v1.json`.
It produced `report_key=short_odds_adapter_activation_gap:6d4ee6d30173eb69`
and `status=activation_candidate_found`, but this remains a diagnostic result,
not a promotion. The current rule path had `competition_not_allowed=67` because
the audited expanded legs were in `ENG_CHAMPIONSHIP`, `ESP_SEGUNDA_DIVISION`,
`FRA_LIGUE_2`, `GER_2_BUNDESLIGA`, and `ITA_SERIE_B`, while the staged
short-odds rule is only allowed for `EPL`, `FRA_LIGUE_1`, `GER_BUNDESLIGA`, and
`ITA_SERIE_A`.

The probe path found only one safe activation, in `FRA_LIGUE_2`, with
`probe_changed_final_answer_count=1`, `probe_final_answer_hit_rate_delta=0.01785714285714285`,
`probe_roi_delta=0.012537313432835803`, `probe_profit_loss_delta=3.36`, and
zero harm counts. The larger blocker after relaxing the competition allowlist is
`replacement_probability_below_floor=119`, with `model_top_missing=37` audited
items. This means the current short-odds rule should stay staged; the next
useful search is a narrower expanded-league rule/threshold candidate, not a
default-path rollout.

## V3.1 Short-Odds Adapter Activation Grid

The activation gap can now be followed by a bounded threshold grid. The grid
replays the staged short-odds adapter against the audited expanded-league
surface, temporarily replacing only the internal probe competition set and a
small set of rule thresholds. It keeps the normal recommendation path,
production profile, and public response unchanged.

CLI:

```bash
uv run nutmeg-recommendation-short-odds-adapter-activation-grid \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_explicit_harm_guard_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_grid_v1.json \
  --min-replacement-probability-values 0.55,0.53,0.50,0.48 \
  --max-replacement-decimal-odds-values 1.75,1.90,2.10 \
  --min-candidate-hit-probability-delta-vs-model-top-values=-0.015,-0.03,-0.05,-0.08 \
  --min-candidate-hit-probability-delta-vs-original-values=-0.025,-0.05,-0.08 \
  --min-changed-final-answer-count 2 \
  --min-average-hit-probability-delta-vs-original -0.05 \
  --max-harm-count-vs-original 0 \
  --max-final-hit-harm-count-vs-original 0 \
  --max-profit-loss-harm-count-vs-original 0
```

Generated report:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_grid_v1.json`.
It produced `report_key=short_odds_adapter_activation_grid:dfe7705790dcd175`,
`status=accepted_candidate_found`, `candidate_count=144`, `accepted_count=31`,
and `rejected_count=113`. The best candidate changed 7 of 56 eligible final
answers, with `final_answer_hit_rate_delta=0.0535714285714286`,
`roi_delta=0.041194029850746244`, `profit_loss_delta=11.039999999999996`, and
zero final-hit/profit-loss harm counts. Its probe thresholds were
`min_replacement_probability=0.48`, `max_replacement_decimal_odds=2.10`,
`min_candidate_hit_probability_delta_vs_model_top=-0.05`, and
`min_candidate_hit_probability_delta_vs_original=-0.08`.

This is a positive internal evidence artifact, not a production rollout. The
candidate still needs rolling-window admission or holdout replay before it can
be considered for any staged profile promotion.

## V3.1 Short-Odds Adapter Activation Grid Admission

Grid candidates now have a dedicated admission wrapper. It reads the activation
grid report, rebuilds temporary candidate rule sets from the selected threshold
combinations, and sends them through the existing short-odds rolling admission
checks. This keeps the evaluation contract shared with the core short-odds rule
promotion path.

CLI:

```bash
uv run nutmeg-recommendation-short-odds-adapter-activation-grid-admission \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_explicit_harm_guard_v1.json \
  --grid-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_grid_admission_v1.json \
  --max-candidate-count 5 \
  --min-overall-final-answer-count 50 \
  --min-overall-changed-final-answer-count 5 \
  --min-overall-average-hit-probability-delta-vs-original=-0.05 \
  --min-fold-average-hit-probability-delta-vs-original=-0.05 \
  --min-active-competition-fold-count 3 \
  --min-active-season-fold-count 2 \
  --min-active-rolling-fold-count 2 \
  --max-failed-fold-count 0
```

Generated report:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_grid_admission_v1.json`.
It produced
`report_key=short_odds_adapter_activation_grid_admission:1e776f28f992c238`,
`status=shadow_only_candidates`, `accepted_candidate_count=0`,
`shadow_only_candidate_count=4`, and `rejected_candidate_count=1`.

The best grid candidate stayed shadow-only: it had 4 active competition folds,
3 active season folds, and 6 active rolling folds, but failed 3 folds due to
`average_hit_probability_delta_below_threshold`. This means the candidate is a
real improvement signal, but not stable enough for staged promotion yet.

## V3.1 Short-Odds Adapter Activation Scope Search

Activation grid candidates can now be re-tested under narrower competition
scopes. The scope search reads the same grid report, rebuilds each temporary
candidate rule, then tries competition subsets through the existing rolling
admission checks. This is still an internal evidence path; it does not change
the default profile or public recommendation response.

CLI:

```bash
uv run nutmeg-recommendation-short-odds-adapter-activation-scope-search \
  --audit-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json \
  --rule-profile configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_explicit_harm_guard_v1.json \
  --grid-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_grid_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_search_v1.json \
  --max-source-candidate-count 5 \
  --min-scope-competition-count 1 \
  --max-scope-competition-count 4 \
  --min-overall-final-answer-count 50 \
  --min-overall-changed-final-answer-count 2 \
  --min-overall-average-hit-probability-delta-vs-original=-0.05 \
  --min-fold-average-hit-probability-delta-vs-original=-0.05 \
  --min-active-competition-fold-count 1 \
  --min-active-season-fold-count 2 \
  --min-active-rolling-fold-count 2 \
  --max-failed-fold-count 0
```

Generated report:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_search_v1.json`.
It produced
`report_key=short_odds_adapter_activation_scope_search:ee7b5353ee598b57`,
`status=accepted_scope_found`, `scope_candidate_count=56`,
`accepted_scope_count=1`, `shadow_only_scope_count=43`, and
`rejected_scope_count=12`.

The accepted scope came from the best grid candidate but narrowed the allowed
competitions to `ESP_SEGUNDA_DIVISION` and `FRA_LIGUE_2`. It changed 2 final
answers with `final_answer_hit_rate_delta=0.01785714285714285`,
`roi_delta=0.013432835820895495`, `profit_loss_delta=3.5999999999999943`,
`average_hit_probability_delta_vs_original=-0.028398806513397407`, and
`failed_fold_count=0`. This is a stable scoped signal, but the changed-answer
count is still too small for profile promotion without more historical support.

## V3.1 Short-Odds Adapter Activation Scope Supplemental Validation

The accepted discovery scope can now be checked against supplemental scope-search
reports before anyone treats it as a promotion candidate. The validator matches
the same competition scope across reports, requires supplemental non-regression,
and records why a scope is blocked.

CLI:

```bash
uv run nutmeg-recommendation-short-odds-adapter-activation-scope-supplemental \
  --base-scope-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_search_v1.json \
  --supplemental-scope-report configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_search_prematch_surface_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_supplemental_validation_v1.json \
  --scope-competition-ids ESP_SEGUNDA_DIVISION,FRA_LIGUE_2 \
  --min-supplemental-changed-final-answer-count 2 \
  --min-total-changed-final-answer-count 4 \
  --max-supplemental-failed-fold-count 0
```

Generated report:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_supplemental_validation_v1.json`.
It produced
`report_key=short_odds_adapter_activation_scope_supplemental:6234bc086c5d5932`
and `status=supplemental_blocked`. The discovery scope changed 2 final answers
with positive hit-rate/ROI/P&L deltas, but the prematch-surface supplemental
report changed 7 final answers with `final_answer_hit_rate_delta=-0.02020202020202022`,
`roi_delta=-0.01502564102564103`, `profit_loss_delta=-5.86`,
`harm_count_vs_original=3`, and `failed_fold_count=6`.

Current decision: the `ESP_SEGUNDA_DIVISION + FRA_LIGUE_2` short-odds scope is
blocked for promotion. It remains useful as a diagnostic of where the discovery
sample was overfitting, but it should not be carried into default or staged
runtime profiles.

## V3.1 Market-Odds-Band Probability Calibration Shadow Mode

The historical probability calibration transform can now learn buckets by either
model probability or normalized market-implied probability. The default remains
`probability_bucket`; the new `market_odds_band` mode uses stored
`market_probability` first, falls back to `1 / decimal_odds`, normalizes the
1X2 market probabilities, and then chooses the calibration bucket. Reports now
record `segment_mode` and sampled predictions include
`applied_segment_probabilities` so the chosen odds band is auditable.

CLI:

```bash
uv run nutmeg-accuracy-historical-probability-calibration-transform \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_market_odds_band_calibration_transform_v1.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --segment-mode market_odds_band \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50
```

Generated core-suite report:
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_market_odds_band_calibration_transform_v1.json`.
It produced
`report_key=historical_probability_calibration_transform:21b793fffa477488`,
`validation_count=2132`, `usable_calibration_bucket_count=104`,
`accepted_competition_count=2`, and `rejected_competition_count=4`. The overall
candidate regressed the no-vig baseline by the same amount as the earlier
probability-bucket transform: hit rate `0.5337711069418386` vs
`0.5361163227016885`, Brier `0.5795079692472372` vs `0.5791437500706367`,
log loss `0.9739091280225523` vs `0.9730922524293841`, and ECE
`0.03817676000003683` vs `0.03737794058402302`.

Interpretation: the core five-season suite stores no-vig market probabilities
as the frozen prediction baseline, so model probability and market odds band are
effectively the same segmentation. This is a valid chain check, not a model
gain.

A second shadow report was generated on the existing market-feature multi-season
suite, where model probability and market-implied probability can differ:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_calibration_transform_v1.json`.
It produced
`report_key=historical_probability_calibration_transform:5212d49d3b0319f8`,
`validation_count=120`, `usable_calibration_bucket_count=6`, and no accepted
competition because each league holdout had only 24 validation fixtures. Overall
hit rate was unchanged at `0.5583333333333333`; Brier improved from
`0.5524644257949949` to `0.5518169200189179`; log loss improved from
`0.9307340402994833` to `0.9286776662145748`; ECE was unavailable because all
validation observation buckets were below the configured sample threshold.

Current decision: keep market-odds-band calibration shadow-only. The runtime
candidate calibration profile and profile artifact path now carry `segment_mode`,
but no default or staged recommendation profile is changed. The next useful step
is a larger real prematch feature sample or a final-answer gate specifically for
market-odds-band profiles, not another small bucket search.

## V3.1 Market-Odds-Band Profile Final-Answer Gate

The probability calibration profile gate, profile grid, runtime artifact builder,
and rolling admission CLI now all expose `--segment-mode`. The profile gate also
exposes `--min-final-answer-changed-count`, matching the stricter grid/artifact
promotion path. This prevents probability-only improvements from being counted as
useful when the user's final answer is unchanged.

Core five-season gate:

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_market_odds_band_probability_calibration_profile_gate_v1.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 100 \
  --segment-mode market_odds_band \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --derive-market-context-signals \
  --min-final-hit-sample-size 2 \
  --no-fail-process
```

Generated report:
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_market_odds_band_probability_calibration_profile_gate_v1.json`.
It produced
`report_key=historical_probability_calibration_profile_gate:2201a0e6496c32fc`
and failed the final-answer gate. Selected competitions were `ESP_LA_LIGA` and
`ITA_SERIE_A`; the suite status was `regressed`; `final_answer_changed_count=2`,
`final_hit_rate_delta=-0.5`, `roi_delta=-0.51`, `profit_loss_delta=-2.04`,
`brier_score_delta=0.35321256192032685`,
`log_loss_delta=0.8726533265588201`, and
`mean_calibration_error_delta=0.38340428675644883`.

Market-feature exploratory gate:

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_strict_v1.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 20 \
  --segment-mode market_odds_band \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --derive-market-context-signals \
  --min-final-hit-sample-size 4 \
  --min-final-answer-changed-count 1 \
  --no-fail-process
```

Generated strict report:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_strict_v1.json`.
It produced
`report_key=historical_probability_calibration_profile_gate:befcf70fc624d96f`.
The exploratory transform selected `BUNDESLIGA`, `EPL`, `LA_LIGA`, and
`SERIE_A`, adjusted 96 fixtures, and improved Brier/log-loss/calibration
metrics, but `final_answer_changed_count=0`. With the stricter changed-answer
requirement the gate correctly failed on `final_answer_changed_count`.

Current decision: market-odds-band profile calibration remains blocked from any
default or staged recommendation path. It can improve probability diagnostics on
thin market-feature samples, but it has not yet improved the actual final answer.
The next core step should target final-answer candidate generation or a larger
real prematch feature sample where calibrated probabilities can actually change
the selected answer without hurting hit rate.

V3.2 model-quality shadow gate:

`nutmeg-recommendation-historical-probability-calibration-profile-model-quality-gate`
now separates probability-quality evidence from recommendation activation. It
consumes a shadow probability-calibration profile gate report and can accept the
profile as model-quality evidence when Brier score, log loss, and calibration
error improve while final-hit, ROI, and P/L do not regress. By default it also
requires `final_answer_changed_count=0`, so this gate cannot be mistaken for a
runtime recommendation promotion.

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-model-quality-gate \
  --profile-gate-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_strict_v1.json \
  --report-output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_model_quality_gate_v1.json \
  --gate-id market-feature-multi-season-market-odds-band-calibration-model-quality-v1 \
  --min-selected-competition-count 4 \
  --min-adjusted-slice-count 4 \
  --min-adjusted-fixture-count 96 \
  --max-skipped-fixture-count 0 \
  --max-final-answer-changed-count 0
```

The generated report is
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_model_quality_gate_v1.json`
with
`report_key=historical_probability_calibration_profile_model_quality_gate:7d615dd017fddefb`.
Status is `model_quality_ready`: it covers 4 selected competitions, 4 adjusted
slices, 96 adjusted fixtures, 0 skipped fixtures, 0 changed final answers,
final-hit / ROI / P&L deltas of `0.0`, Brier delta
`-0.013140475792027984`, log-loss delta `-0.027925615774599954`, and mean
calibration-error delta `-0.00851611160713972`.

Current decision: this is a useful probability-quality shadow win, not a product
answer change. It does not write any default profile, does not enable production
recommendations, and does not alter the public recommendation response. The next
step is to use it as a guardrail for later candidate-generation experiments.

Recurring benchmark gate attachment:

`recommendation_benchmark_quality_gate_v3_1` and
`recommendation_benchmark_cycle_v3_1` now consume
`probability_calibration_profile_model_quality_gate_*` evidence. The gate can
require the report, require `model_quality_ready`, enforce selected competition,
adjusted slice/fixture, skipped fixture, unchanged final-answer, final-hit,
ROI, P/L, Brier, log-loss, and calibration-error thresholds, and then expose the
same summary fields through cycle reports. This keeps probability-model
improvements inside the recurring no-regression surface without changing the
default recommendation path or exposing internal strategy details to users.

Example:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --allow-missing-history \
  --probability-calibration-profile-model-quality-gate-report-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_model_quality_gate_v1.json \
  --require-probability-calibration-profile-model-quality-gate \
  --min-probability-calibration-profile-model-quality-selected-competition-count 4 \
  --min-probability-calibration-profile-model-quality-adjusted-slice-count 4 \
  --min-probability-calibration-profile-model-quality-adjusted-fixture-count 96 \
  --max-probability-calibration-profile-model-quality-skipped-fixture-count 0 \
  --max-probability-calibration-profile-model-quality-final-answer-changed-count 0
```

## V3.1 Final-Answer Sensitivity Audit

Final-answer gate reports can now be audited for arbitration sensitivity. The
audit compares the selected final answer with the nearest distinct runner-up in
each historical slice, then records the score gap, hit-probability gap,
winner/runner-up actual hit result, ROI/profit deltas, and diagnostic codes. It
is an internal diagnostic, not a production strategy switch.

CLI:

```bash
uv run nutmeg-recommendation-final-answer-sensitivity-audit \
  --profile-gate-report configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_strict_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_final_answer_sensitivity_audit_v1.json \
  --side candidate \
  --max-near-miss-score-gap 0.03 \
  --top-near-miss-limit 20
```

Generated market-feature sensitivity report:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_final_answer_sensitivity_audit_v1.json`.
It produced
`report_key=historical_final_answer_sensitivity_audit:287b78d2f5b38aa1`.
Among 4 final answers, only 1 had a distinct runner-up
(`runner_up_coverage_rate=0.25`), no near misses were within the 0.03 score
gap, no runner-up had higher hit probability, and there were no actionable
near-misses. Diagnostic codes were `candidate_generation_sparse`,
`no_near_miss_margin`, `no_higher_hit_probability_runner_up`, and
`no_actionable_near_miss`.

Generated core-suite sensitivity report:
`configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_market_odds_band_final_answer_sensitivity_audit_v1.json`.
It produced
`report_key=historical_final_answer_sensitivity_audit:5e22a55a40e82ae1`.
Among 2 final answers, both had distinct runner-ups, but no near-miss was within
the 0.03 score gap, no runner-up had higher hit probability, and there were no
actionable near-misses. The average score gap was `0.04517080269425944`.

Current decision: this points away from directly tweaking final-answer weights.
The stronger bottleneck is candidate/option generation coverage: probability
calibration cannot improve the user answer if there are too few distinct
alternatives, or if alternatives do not offer higher hit probability. The next
step should expand final-answer option generation and scenario coverage before
another arbitrator-weight or calibration grid.

## V3.1 Season-Aware Calibration Holdout

Probability calibration transform and profile-gate holdout splitting now treat
`holdout_season_count` as seasons, not raw slice count. This matters once a
season is split into multiple rolling-window slices: the last holdout season's
full set of windows now stays together in validation, while training season
requirements are counted by distinct season. Slices without season metadata keep
the legacy slice-count fallback.

## V3.1 Final-Answer Scenario Variants

Historical backtests now support shadow scenario variants through
`final_answer_scenario_variant_count`. The default is `1`, so existing backtests
and runtime recommendation paths are unchanged. When enabled, the backtest runs
the base scenario, excludes the selected fixture IDs, then tries `#variantN`
alternatives for the same pass type and mode. Only successful variants become
final-answer candidates; failed variants stop silently so sparse slices do not
create extra warning noise.

CLI example:

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_variants_v1.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 20 \
  --segment-mode market_odds_band \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --final-answer-scenario-variant-count 3 \
  --derive-market-context-signals \
  --min-final-hit-sample-size 4 \
  --min-final-answer-changed-count 1 \
  --no-fail-process
```

Generated scenario-variant gate report:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_variants_v1.json`.
It produced `report_key=historical_probability_calibration_profile_gate:ccf62801d3d7577d`.
The gate still failed because `final_answer_changed_count=0`, although Brier,
log loss, and mean calibration error improved. Only one successful variant was
created across the four validation slices, which confirms the current blocker is
still sparse historical as-of candidate coverage.

Generated follow-up sensitivity report:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_scenario_variants_sensitivity_audit_v1.json`.
It produced `report_key=historical_final_answer_sensitivity_audit:794858857afb2539`.
Runner-up coverage stayed at `0.25`, with no near misses and no higher-hit
runner-up. Current decision: keep this as shadow evidence only, and move the
next core pass toward rolling-window or multi-fixture validation slices before
spending more time on final-answer weight tuning.

## V3.1 Rolling-Window Market-Feature Gate

The five-major-league market-feature suite was expanded into rolling 12-fixture
candidate windows:

```bash
uv run nutmeg-recommendation-historical-slice-window \
  --input-suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json \
  --output-dir configs/recommendations/historical_slices/enriched_features/football_data_co_uk_market_feature_rolling_windows \
  --suite-manifest-output-path configs/recommendations/historical_suites/football_data_co_uk_market_feature_rolling_window_suite_v1.json \
  --report-output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_window_generation_v1.json \
  --suite-id football_data_co_uk_market_feature_rolling_window_suite_v1 \
  --suite-name "Football-Data.co.uk market-feature rolling-window suite" \
  --window-fixture-count 12 \
  --stride-fixture-count 12 \
  --min-fixture-count 8
```

Generation report:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_window_generation_v1.json`.
It produced `report_key=historical_slice_windowing:c1777276c60ac8f2`,
`50` windowed slices, `600` fixture exposures, and no skipped windows.

The market-odds-band profile gate was then run on the rolling-window suite:

```bash
uv run nutmeg-recommendation-historical-probability-calibration-profile-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_market_feature_rolling_window_suite_v1.json \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_window_market_odds_band_probability_calibration_profile_gate_v1.json \
  --holdout-season-count 1 \
  --min-training-season-count 4 \
  --min-validation-sample-size 20 \
  --segment-mode market_odds_band \
  --bucket-size 0.10 \
  --min-bucket-sample-size 30 \
  --blend-weight 0.50 \
  --pass-types 1x1,2x1,3x1,4x1 \
  --modes single,multiple \
  --optimizer-profile solver \
  --candidate-fixture-limit 48 \
  --max-candidates-per-fixture 3 \
  --final-answer-scenario-variant-count 3 \
  --derive-market-context-signals \
  --min-final-hit-sample-size 8 \
  --min-final-answer-changed-count 1 \
  --no-fail-process
```

Generated gate report:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_window_market_odds_band_probability_calibration_profile_gate_v1.json`.
It produced `report_key=historical_probability_calibration_profile_gate:7675d712a9fa0ed8`
and passed the shadow final-answer gate. The validation set included `8`
windowed final-answer samples, `final_answer_changed_count=1`,
`final_hit_rate_delta=0.125`, `profit_loss_delta=29.0672`,
`brier_score_delta=-0.04661320380327549`,
`log_loss_delta=-0.0997748715249252`, and
`mean_calibration_error_delta=-0.05349339821915783`.

Follow-up sensitivity audit:
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_window_market_odds_band_final_answer_sensitivity_audit_v1.json`.
It produced `report_key=historical_final_answer_sensitivity_audit:27beaf0bde0fb433`.
Runner-up coverage improved to `1.0`; there were `2` near misses, no higher-hit
runner-up, and no actionable near-miss.

Current decision: this is positive core evidence, but still shadow-only. The
sample has only `8` final answers, so the next step is to repeat this
season-aware rolling-window gate on expanded A-league or core+expanded suites
before promoting any calibration profile.

## V3.1 Expanded A-League Rolling-Window Gate

The same season-aware `market_odds_band` profile gate was replayed on the
expanded A-league rolling-window suite:
`configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json`.
That suite contains `210` enabled rolling-window slices and `2520` fixture
exposures across Championship, 2. Bundesliga, Serie B, Segunda Division,
Ligue 2, Eredivisie, and Primeira Liga.

Strict transform report:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_probability_calibration_transform_v1.json`.
It produced `report_key=historical_probability_calibration_transform:4aa769d7dbf0a69b`,
`validation_count=504`, `usable_calibration_bucket_count=61`, and
`accepted_competition_count=0`. Every expanded league had enough validation
samples, but each one failed at least one no-harm probability-quality check.

Strict profile-gate report:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_probability_calibration_profile_gate_v1.json`.
It produced `report_key=historical_probability_calibration_profile_gate:ccafab6604805e06`.
Because no transform competition was accepted, no final-answer suite was run and
`passed_final_answer_gate=false`.

For diagnosis only, the rejected transform competitions were temporarily
included in a shadow final-answer gate:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_probability_calibration_profile_gate_include_rejected_v1.json`.
It produced `report_key=historical_probability_calibration_profile_gate:50113a24c21b73e7`
over `42` final-answer samples. The result regressed:
`final_hit_rate_delta=-0.0714285714285714`, `final_hit_count_delta=-3`,
`roi_delta=-0.08172722222222226`, `profit_loss_delta=-5.406000000000002`,
`brier_score_delta=0.002012583982812177`,
`log_loss_delta=0.0036296001769993147`, and
`mean_calibration_error_delta=0.0067897609632306954`. It changed `20` final
answers, which proves the candidate path is active, but the changes hurt the
user-facing result.

The sensitivity audit for that diagnostic report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_final_answer_sensitivity_audit_include_rejected_v1.json`
with `report_key=historical_final_answer_sensitivity_audit:7de1fb9e9812725b`.
Runner-up coverage was `1.0`, near-miss rate was `0.9047619047619048`, and
`actionable_near_miss_count=15`; this shows there are enough alternatives, but
the current calibration/arbitration profile is not selecting them safely.

A narrower diagnostic on 2. Bundesliga, Eredivisie, and Primeira Liga is stored
at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_probability_calibration_profile_gate_neutral_profit_scope_v1.json`
with `report_key=historical_probability_calibration_profile_gate:86cf39d4234797c0`.
That scope kept final-answer hit rate flat and improved ROI
(`roi_delta=0.0188888888888889`, `profit_loss_delta=0.6800000000000002`), but
still failed Brier, log-loss, calibration-error, and suite-status checks.

Current decision: the five-major-league rolling-window positive signal does not
generalize to the expanded A-league suite. No default, staged, runtime, frontend,
or public recommendation path is changed. The next core step is a
competition/odds-band admission search that blocks Spanish Segunda, Ligue 2,
and weak probability-quality folds instead of promoting one broad calibration
profile.

Follow-up narrow admission search:

- Outcome/probability grid:
  `configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_neutral_profit_scope_profile_grid_v1.json`
  with `report_key=historical_probability_calibration_profile_grid:70886c7b46565f6c`.
  It evaluated `9` candidates over 2. Bundesliga, Eredivisie, and Primeira
  Liga, using home/draw/away plus low/mid/high probability bands. It accepted
  `0` candidates. Most candidates did not change the final answer; the only
  probability-moving high-home band regressed Brier/log-loss/calibration.
- Odds-band grid:
  `configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_neutral_profit_scope_odds_band_profile_grid_v1.json`
  with `report_key=historical_probability_calibration_profile_grid:bb03f5f4bf73313e`.
  It evaluated `4` odds-band candidates and accepted `0`. The best candidate
  improved Brier and log loss slightly in the `1.35:1.70` decimal-odds band, but
  still changed `0` final answers and slightly worsened calibration error.
- Single-league gates confirmed the split:
  2. Bundesliga changed `2` final answers and improved ROI by
  `0.02833333333333335`, but regressed Brier, log loss, and calibration error.
  Eredivisie changed `1` final answer with no hit/ROI movement, but also
  regressed all three probability-quality metrics. Primeira Liga improved Brier
  by `-0.0034884987884234997`, log loss by `-0.009744519830393428`, and
  calibration error by `-0.006379478673712635`, but changed `0` final answers.
  A strict `blend_weight=0.25` transform-selected Ligue 2 gate also changed `0`
  final answers and regressed probability quality.

Current decision after the narrow search: there is still no expanded A-league
market-odds-band calibration profile that both changes the user's final answer
and passes no-harm probability checks. Keep the profile shadow-only and do not
promote it. The next useful engineering step is to add reusable baseline cache /
summary-only output for probability calibration profile-grid runs, then broaden
the search more cheaply across competition groups and odds bands.

Follow-up calibration-search ergonomics:

The profile-gate and profile-grid CLIs now accept `--stdout-summary-only`.
The option leaves full `--output-path` JSON artifacts unchanged, but prints a
compact stdout payload for long-running searches. Profile-gate compact output
keeps the report key, selected/rejected competitions, slice and fixture counts,
final-answer gate result, aggregate suite deltas, failed quality checks, and
warnings while omitting bulky suite manifests and per-comparison details.
Profile-grid compact output keeps grid counts, the best candidate, top
candidates, accepted candidates, rejection summaries, and warnings while
omitting each candidate's full nested report payload.

This is an engineering acceleration only. It does not change probability
calibration math, final-answer arbitration, recommendation results, report
keys, quality-gate pass/fail rules, runtime defaults, frontend behavior, or
promotion status. The broader market-odds-band calibration profile remains
shadow-only until it passes no-harm probability quality and final-answer
quality gates on real historical slices.

Follow-up transform-report reuse:

Profile-grid runs now reuse the probability calibration transform report within
the same grid execution whenever candidates share the same historical slices and
transform options. In practice, all candidates under the same blend weight and
calibration segmentation can share one transform report, so wider
outcome/probability/odds-band grids no longer rebuild identical calibration
bucket evidence for every candidate.

The report now records `transform_cache_hit_count`,
`transform_cache_miss_count`, and `unique_transform_report_count`; candidate
payloads include the in-run `transform_cache_status` and `transform_report_key`.
This cache is in-memory and scoped to one grid build. It does not change
candidate scoring, sorting, report keys, final-answer gate rules, or promotion
decisions.

Follow-up baseline-backtest reuse:

Profile-grid runs now also reuse baseline final-answer backtests within the
same grid execution. Each profile candidate still runs its adjusted/candidate
backtest, but the unadjusted baseline backtest for a validation slice is
computed once for the shared backtest options and reused by later candidates.

The profile-gate report records `baseline_backtest_cache_hit_count` and
`baseline_backtest_cache_miss_count`; the profile-grid report records those
counts plus `unique_baseline_backtest_count`. Candidate payloads and compact
stdout expose the same per-candidate cache counts. The cache metadata is kept
out of candidate identity calculation, so this remains a non-behavioral
throughput optimization: candidate scoring, sorting, report evidence, quality
gate rules, and promotion decisions are unchanged.

Follow-up profile-grid progress telemetry:

Profile-grid runs now accept `--progress-jsonl-path`. When set, each execution
writes a compact JSONL stream with `grid_started`, `candidate_started`,
`candidate_completed`, and `grid_completed` events. Candidate-completed events
include candidate identity, rejection reasons, transform cache status,
transform report key, gate report key, final-answer gate status, and candidate
elapsed seconds.

The report and compact stdout now also include `elapsed_seconds`,
`candidate_elapsed_seconds`, `slowest_candidate_index`, and
`slowest_candidate_elapsed_seconds`. This makes broad historical searches
observable and batch-friendly instead of a silent long-running process. The
telemetry is diagnostic only and does not affect probability calibration,
candidate acceptance, final-answer arbitration, runtime defaults, or promotion
decisions.

Follow-up expanded A-league batch0 evidence:

With transform-report reuse, baseline-backtest reuse, and progress telemetry in
place, the first broad expanded A-league market-odds-band grid batch was run on
`configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json`.
The batch used `candidate_start_index=0`, `candidate_limit=4`,
`blend_weight=0.10`, all 1X2 outcomes, and decimal-odds bands from `1.01` to
`3.50`. The report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_broad_odds_outcome_profile_grid_batch0_progress_v1.json`
with `report_key=historical_probability_calibration_profile_grid:0b07788778e3a8d8`.

The batch produced one accepted candidate: all 1X2 outcomes in the `2.30:3.50`
decimal-odds band with `blend_weight=0.10`. It adjusted `331` fixtures across
`42` validation slices, changed `5` final answers, kept final hit rate flat,
and improved ROI by `0.10519277777777779` with `profit_loss_delta=17.0244`.
Probability quality also improved:
`brier_score_delta=-0.004209589930242313`,
`log_loss_delta=-0.008692389373464948`, and
`mean_calibration_error_delta=-0.0022002489006500148`.

The accepted profile was then replayed as a full profile-gate artifact:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_all_230_350_blend010_profile_gate_v1.json`
with `report_key=historical_probability_calibration_profile_gate:3b1f56797589ff1e`.
It passed the final-answer quality gate with the same deltas and remains
shadow-only. The sensitivity audit is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_all_230_350_blend010_sensitivity_audit_v1.json`
with `report_key=historical_final_answer_sensitivity_audit:8d4e7fb73f79b1bd`;
runner-up coverage was `1.0`, near-miss rate was `0.9047619047619048`, and
`actionable_near_miss_count=9`.

Current decision: this is the first expanded A-league market-odds-band
calibration profile in this line that both changes final answers and passes
no-harm probability-quality checks. It is still not promoted to default or
runtime behavior. The next step is to continue adjacent batches and then run
cross-scope validation before any staged profile proposal.

Follow-up expanded A-league batch1-batch3 evidence:

The next adjacent broad grid batches were run with the same rolling-window
suite, strict no-harm final-answer gate, `blend_weight=0.10`, and
`candidate_limit=4` windows. Batch1 covered candidates `4` through `7` and
rejected all four candidates:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_broad_odds_outcome_profile_grid_batch1_progress_v1.json`
with `report_key=historical_probability_calibration_profile_grid:5dc39ab514656dce`.
It completed in `207.277695` seconds and mainly rejected candidates for
probability-quality, ROI/profit, and suite-status regressions. Batch2 covered
candidates `8` through `11` and also rejected all four candidates:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_broad_odds_outcome_profile_grid_batch2_progress_v1.json`
with `report_key=historical_probability_calibration_profile_grid:85e3bffc254f055d`.
Its candidates either changed no final answers or had no adjusted fixtures.

Batch3 covered candidates `12` through `15` and produced one accepted
candidate:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_broad_odds_outcome_profile_grid_batch3_progress_v1.json`
with `report_key=historical_probability_calibration_profile_grid:dcb2dd7ab2e7b970`.
The accepted profile is narrower than the batch0 all-outcome profile:
`target_outcomes=[draw]`, decimal odds `2.30:3.50`, and
`blend_weight=0.10`. It adjusted `277` fixtures, changed `5` final answers,
kept final hit rate flat, improved ROI by `0.10519277777777779`, improved
profit/loss by `17.0244`, and improved probability quality with
`brier_score_delta=-0.004209589930242313`,
`log_loss_delta=-0.008692389373464948`, and
`mean_calibration_error_delta=-0.0022002489006500148`.

The draw-only candidate was replayed as a full profile-gate artifact:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_draw_230_350_blend010_profile_gate_v1.json`
with `report_key=historical_probability_calibration_profile_gate:403430b1fcbfef00`.
It passed the final-answer gate with `suite_status=improved`,
`baseline_final_hit_rate=0.6666666666666666`,
`candidate_final_hit_rate=0.6666666666666666`,
`baseline_roi=-0.1833861111111111`, `candidate_roi=-0.07819333333333332`,
`baseline_profit_loss=-26.4076`, and
`candidate_profit_loss=-9.383199999999999`. The transform accepted only
`FRA_LIGUE_2` and `NED_EREDIVISIE` as calibration evidence providers, but the
gate applies the resulting accepted profile across the expanded A-league
validation suite.

The sensitivity audit for the draw-only profile is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_draw_230_350_blend010_sensitivity_audit_v1.json`
with `report_key=historical_final_answer_sensitivity_audit:e32b1c3900d55b1a`.
Runner-up coverage was `1.0`, near-miss rate was
`0.9047619047619048`, `actionable_near_miss_count=9`,
`runner_up_higher_hit_probability_count=5`,
`winner_loss_runner_up_hit_count=6`, and there were no diagnostic codes.

Current decision after batch1-batch3: the draw-only `2.30:3.50` profile is a
second no-harm shadow candidate and a narrower explanation of the same
positive movement seen in batch0. It is still not promoted to runtime/default
behavior. The next useful step is to compare the all-outcome and draw-only
profiles through cross-scope validation and rolling-admission packaging before
considering any staged activation.

Follow-up rolling-admission comparison:

Both positive `2.30:3.50` market-odds-band profiles were replayed through the
probability-calibration rolling-admission gate on the expanded A-league
rolling-window suite. The all-outcome report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_all_230_350_blend010_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:a2d1f57731c12e85`.
The draw-only report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_draw_230_350_blend010_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:a256a40795302d56`.

The admission comparison produced a hard promotion stop: both reports are
`status=shadow_only`, `candidate_profile_allowed=false`, and
`shadow_allowed=true`. Both candidates passed the overall fold and emitted a
runtime profile artifact internally, but both failed `failed_fold_count` with
`11` failed active folds out of `13`. Therefore neither report wrote an active
candidate profile to `configs/recommendations/profiles/`, and neither may be
used as default/runtime behavior.

The overall fold remains positive for both candidates. The all-outcome profile
adjusted `331` fixtures and the draw-only profile adjusted `277` fixtures.
Both kept `final_hit_rate_delta=0.0`, improved ROI by
`0.10519277777777779`, improved profit/loss by `17.0244`, and improved
probability quality with `brier_score_delta=-0.004209589930242313`,
`log_loss_delta=-0.008692389373464948`, and
`mean_calibration_error_delta=-0.0022002489006500148`.

The passing folds were only the latest cumulative season cutoff
`season_cutoff:2024-2025` and the newest rolling window
`rolling_window:3:2022-2023..2024-2025`. Older cutoffs and most individual
competition folds did not emit a runtime profile or failed the final-answer
gate, mainly because fold-local bucket evidence was too sparse or the fold
metrics regressed. In particular, `ESP_SEGUNDA_DIVISION` produced
`final_hit_rate_delta=-0.16666666666666666` and probability-quality regression
in both candidates, while several other competition folds changed no final
answers and emitted no runtime buckets.

Current decision after rolling admission: the `2.30:3.50` calibration signal is
useful as a recent-window shadow signal, but it is not stable enough for staged
activation across folds. The next technical step is not promotion. It is a
fold-aware refinement: either narrow the scope toward the folds where evidence
is active, or build a calibration admission search that explicitly optimizes
per-fold pass counts before generating an active profile proposal.

Follow-up fold-aware rolling-admission refinement:

Probability-calibration rolling admission now supports fold-specific final-answer
quality thresholds. The CLI accepts `--fold-min-final-hit-sample-size`,
`--fold-min-final-hit-rate-delta`, `--fold-min-final-answer-changed-count`,
`--fold-min-roi-delta`, `--fold-min-profit-loss-delta`,
`--fold-max-brier-score-delta`, `--fold-max-log-loss-delta`, and
`--fold-max-mean-calibration-error-delta`. When these options are omitted, fold
gates keep the same quality thresholds as the overall gate. When supplied, the
overall gate can stay strict while competition/season/rolling folds use
thresholds that fit their smaller sample size.

This matters because the previous admission run used
`min_final_hit_sample_size=20` for both the overall suite and each fold, while a
single competition fold in the expanded A-league suite usually has only `6`
validation windows. That made some fold failures diagnostic but not actionable.
The fold-aware run kept the overall profile strict with
`min_final_hit_sample_size=20` and `min_final_answer_changed_count=1`, while the
fold gate used `--fold-min-final-hit-sample-size 1` and
`--fold-min-final-answer-changed-count 0`.

The fold-aware all-outcome admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_all_230_350_blend010_fold_aware_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:1cccb2885baa0421`.
The fold-aware draw-only report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_draw_230_350_blend010_fold_aware_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:b9895d22f1fe8447`.

Both reports are still `status=shadow_only` and
`candidate_profile_allowed=false`, so no active profile is written and default
runtime behavior is unchanged. The important improvement is diagnostic:
`failed_fold_count` dropped from `11` to `5` for both profiles. Passing folds
now include six of seven competition folds plus the latest cumulative and
rolling windows. The remaining failed folds are concentrated in
`competition:ESP_SEGUNDA_DIVISION`, `season_cutoff:2022-2023`,
`season_cutoff:2023-2024`, `rolling_window:1:2020-2021..2022-2023`, and
`rolling_window:2:2021-2022..2023-2024`.

Current decision after fold-aware admission: the block is no longer a generic
fold-threshold problem. The signal is recent-window positive and broad across
most individual competitions, but it still has a clear West/early-window
instability. The next refinement should search scoped profiles that either
exclude the unstable fold driver or learn a time/fold-aware calibration profile
before any active proposal is attempted.

Follow-up scoped no-ESP refinement:

A scoped expanded A-league rolling-window suite was generated by excluding
`ESP_SEGUNDA_DIVISION` from the broader 210-slice suite:
`configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_segunda_suite_v1.json`.
The scoped suite contains `180` rolling-window slices and is used only for
shadow admission diagnostics.

The no-ESP draw-only profile was replayed through the fold-aware rolling
admission gate:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_rolling_window_market_odds_band_draw_230_350_blend010_fold_aware_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:92101c4f13c08001`.
It remains `status=shadow_only` and `candidate_profile_allowed=false`, but it
is a meaningful improvement over the broader profile. Failed folds fell to `1`
out of `12`. The overall fold adjusted `211` fixtures, produced `82` runtime
buckets, improved final hit rate by `0.02777777777777779`, improved ROI by
`0.12504444444444446`, improved profit/loss by `13.504800000000003`, and
improved probability quality with
`brier_score_delta=-0.0056366367028146125`,
`log_loss_delta=-0.011436047358709511`, and
`mean_calibration_error_delta=-0.005677368018753459`.
The only remaining failed fold was
`rolling_window:2:2021-2022..2023-2024`.

The no-ESP all-outcome profile was also replayed:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_rolling_window_market_odds_band_all_230_350_blend010_fold_aware_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:8c67251a04c71a1a`.
It has the same positive overall movement, but is less stable than draw-only:
failed folds remained at `3` out of `12`, specifically
`season_cutoff:2022-2023`, `rolling_window:1:2020-2021..2022-2023`, and
`rolling_window:2:2021-2022..2023-2024`.

Current decision after scoped no-ESP refinement: excluding
`ESP_SEGUNDA_DIVISION` resolves the main competition-level blocker and turns
the draw-only profile into the strongest current shadow candidate. It still
must not be promoted because one rolling-window fold fails. The next step is to
investigate `rolling_window:2:2021-2022..2023-2024` specifically, either with a
time-aware cutoff or an additional odds/outcome scope, before any active
profile proposal is considered.

Follow-up ITA/time-scope diagnostics:

The remaining no-ESP draw-only failed fold was diagnosed with three narrower
admission experiments. A no-ESP-no-ITA suite was generated at
`configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_no_ita_serie_b_suite_v1.json`.
It contains `150` slices and excludes both `ESP_SEGUNDA_DIVISION` and
`ITA_SERIE_B`. Its admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_no_ita_rolling_window_market_odds_band_draw_230_350_blend010_fold_aware_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:0fcf547a14516ec4`.
This run had `failed_fold_count=0`, but it was still `status=rejected` with
`candidate_profile_allowed=false` because the overall final answer did not
change: `final_hit_rate_delta=0.0`, `roi_delta=0.0`,
`profit_loss_delta=0.0`, and the final-answer changed-count gate failed.

A second suite kept ITA except for the problematic `2023-2024` season:
`configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_no_ita_2023_2024_suite_v1.json`.
It contains `174` slices, excludes `ESP_SEGUNDA_DIVISION`, and excludes only
`ITA_SERIE_B` slices tagged `2023_2024`. Its admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_no_ita_2023_2024_rolling_window_market_odds_band_draw_230_350_blend010_fold_aware_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:c86e65db463f3bd0`.
This run was `status=rejected`, `candidate_profile_allowed=false`, and
`failed_fold_count=2` (`competition:ITA_SERIE_B` and
`season_cutoff:2024-2025`). Overall movement also disappeared, with
`final_hit_rate_delta=0.0`, `roi_delta=0.0`, and `profit_loss_delta=0.0`.

A blend sensitivity run lowered the no-ESP draw-only calibration blend from
`0.10` to `0.05`:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_rolling_window_market_odds_band_draw_230_350_blend005_fold_aware_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:132b6dbb2294bb51`.
This also failed to preserve final-answer movement and expanded instability:
`status=rejected`, `candidate_profile_allowed=false`, `failed_fold_count=5`,
`final_hit_rate_delta=0.0`, `roi_delta=0.0`, and `profit_loss_delta=0.0`.

Current decision after ITA/time-scope diagnostics: the remaining signal is not
solved by removing ITA, removing only ITA 2023-2024, or lowering blend weight.
ITA appears to be the source of the only useful final-answer movement, while
the same evidence chain exposes a probability-quality regression in one active
rolling window. The next step should update the profile search objective so
candidate generation directly optimizes zero failed active folds plus
final-answer changed-count, instead of relying on manual post-hoc exclusions.
No active runtime profile was written and default recommendation behavior is
unchanged.

Fold-objective profile grid:

The probability-calibration profile grid can now run an optional fold objective
per candidate. When enabled, the grid still records the ordinary overall
profile-gate metrics, but it also runs the matching rolling-admission fold
checks and stores candidate-level fold fields:
`fold_objective_status`, `fold_objective_failed_fold_count`,
`fold_objective_active_fold_count`, `fold_objective_report_key`, and
`fold_objective_json`. A candidate that passes overall quality but fails active
fold admission is rejected at grid time with `fold_objective:*` decision
reasons. The feature is opt-in through `--enable-fold-objective`; default grid
behavior is unchanged.

A real no-ESP draw-only candidate replay was generated with the new objective:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_230_350_blend010_fold_objective_grid_v1.json`
with `report_key=historical_probability_calibration_profile_grid:0f14d1d816fa0bed`.
The candidate still has positive overall movement
(`final_answer_changed_count=1`,
`final_hit_rate_delta=0.02777777777777779`,
`roi_delta=0.12504444444444446`,
`profit_loss_delta=13.504800000000003`,
`brier_score_delta=-0.0056366367028146125`,
`log_loss_delta=-0.011436047358709511`, and
`mean_calibration_error_delta=-0.005677368018753459`), but the grid now rejects
it immediately because the fold objective reports `status=shadow_only`,
`failed_fold_count=1`, and failed fold
`rolling_window:2:2021-2022..2023-2024`.

Current decision after fold-objective grid hardening: the search layer now has
the missing feedback loop needed for the next candidate search. Instead of
manually running post-hoc rolling admission after a grid candidate looks good,
the grid itself can rank and reject candidates using active fold stability. The
next step is to run a broader fold-objective grid over adjacent odds bands,
target outcomes, and blend weights, looking for the first candidate that has
`accepted_count > 0` with zero failed active folds and a nonzero final-answer
changed count.

Adjacent odds fold-objective search:

A focused adjacent-odds fold-objective grid was run for no-ESP draw-only,
blend `0.10`, and four nearby market-odds bands:
`2.20:3.40`, `2.25:3.45`, `2.30:3.50`, and `2.35:3.55`.
The report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_adjacent_odds_blend010_fold_objective_grid_v1.json`
with `report_key=historical_probability_calibration_profile_grid:89837841f7721e00`.
This produced the first fold-objective accepted candidate in this calibration
line: `accepted_count=1`, `rejected_count=3`.

The accepted candidate is draw-only, market odds `2.25:3.45`, blend `0.10`.
It has `fold_objective_status=accepted`, `fold_objective_failed_fold_count=0`,
`final_answer_changed_count=1`, `final_hit_rate_delta=0.02777777777777779`,
`roi_delta=0.12504444444444446`, `profit_loss_delta=13.504800000000003`,
`brier_score_delta=-0.0055595650171044175`,
`log_loss_delta=-0.011274560301326564`, and
`mean_calibration_error_delta=-0.005579406751200555`.

The accepted grid candidate was then replayed through standalone fold-aware
rolling admission:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_rolling_window_market_odds_band_draw_225_345_blend010_fold_aware_rolling_admission_v1.json`
with `report_key=historical_probability_calibration_profile_rolling_admission:0f7677760aeedac4`.
The admission report is `status=accepted`, `candidate_profile_allowed=true`,
`fold_count=12`, `active_fold_count=12`, `failed_fold_count=0`,
`active_competition_fold_count=6`, `active_season_cutoff_fold_count=3`, and
`active_rolling_fold_count=3`.

The emitted active-mode candidate profile is stored at
`configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_active_candidate_profile_v1.json`.
It has `profile_key=candidate_probability_calibration_profile:e753919b27cb3e62`,
`segment_mode=market_odds_band`, `blend_weight=0.10`, `target_outcomes=["draw"]`,
`min_decimal_odds=2.25`, `max_decimal_odds=3.45`, `bucket_count=82`, and target
competitions `ENG_CHAMPIONSHIP`, `FRA_LIGUE_2`, `GER_2_BUNDESLIGA`,
`ITA_SERIE_B`, `NED_EREDIVISIE`, and `PRT_PRIMEIRA_LIGA`.

Current decision after adjacent odds search: this is a genuine promotion
candidate, but it is not yet the default runtime profile. The next step is to
connect this accepted profile to the existing production proposal / smoke /
benchmark quality gate chain, and then run a runtime shadow replay to confirm
that public response shape and default recommendation behavior remain governed.

Probability calibration production proposal:

The fold-objective accepted profile now has a dedicated production proposal
step. `nutmeg-recommendation-historical-probability-calibration-profile-production-proposal`
consumes a profile-grid report, a fold-aware rolling-admission report, and an
active candidate profile. It checks source/profile linkage, accepted grid
decision, accepted rolling admission, active profile mode, fold counts, bucket
coverage, final-answer movement, ROI/profit deltas, and Brier/log-loss/ECE
no-harm metrics. The output is a governed proposal artifact only; it does not
write or switch the default runtime profile.

The real no-ESP draw-only market-odds-band candidate `2.25:3.45`, blend `0.10`
was promoted to proposal-ready status:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_production_proposal_v1.json`
with `report_key=historical_probability_calibration_profile_production_proposal:832c7c149c76bd`.
The proposal is `status=runtime_profile_proposal_ready`,
`runtime_profile_proposal_allowed=true`, and `holdout_candidate_allowed=true`;
it keeps `production_recommendation_changed=false`.

The staged proposal profile set was written to
`configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_proposal_profile_set_v1.json`.
The existing benchmark quality gate was also run against the rolling admission
evidence with missing benchmark history explicitly allowed for this bootstrap
check:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_benchmark_gate_v1.json`.
It passed with no failed checks.

Current decision after production proposal governance: the profile is now a
proposal-ready candidate, not a default runtime change. The next step is a
runtime shadow replay / smoke step that proves the profile can be staged without
changing public response shape, exposing internal strategy labels, or bypassing
explicit promotion approval.

Probability calibration runtime replay:

`nutmeg-recommendation-historical-probability-calibration-profile-runtime-replay`
now replays a staged probability-calibration profile in shadow. It loads the
proposal profile set, applies the selected profile to a temporary copy of the
historical slices, runs baseline and calibrated backtest suites, and reports
final-answer, ROI/P&L, calibration-quality, production-change, public-response,
and internal-label checks. It is explicit opt-in through
`--enable-shadow-replay`; the default runtime recommendation path is unchanged.

The V3.1-309 proposal-ready profile was replayed against the no-ESP expanded
A-league rolling-window suite:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_runtime_replay_v1.json`
with `report_key=historical_probability_calibration_profile_runtime_replay:3183ab5bca5f7edf`.
The replay exercised `adjusted_fixture_count=1126` and
`adjusted_candidate_count=3378`, changed `4` final answers over `180` final
answers, and improved final-answer outcome metrics:
`final_answer_hit_delta_count=1`, `final_answer_hit_rate_delta=0.005555555555555536`,
`roi_delta=0.018993574297188755`, and `profit_loss_delta=9.4588`.
It also preserved the governance invariants:
`production_recommendation_changed=false`, `public_response_changed=false`, and
`internal_strategy_label_exposed=false`.

The strict shadow replay did not pass because probability-quality no-harm
checks failed: `brier_score_delta=0.004950884450535403`,
`log_loss_delta=0.011755583705955419`, and
`mean_calibration_error_delta=0.005865258907091386`. Current decision: keep the
profile out of runtime/default despite positive hit/ROI/P&L movement. The next
step should refine the profile or replay scope so final-answer gains survive
without probability-quality regression.

Probability calibration runtime diagnostics:

`nutmeg-recommendation-historical-probability-calibration-profile-runtime-diagnostics`
now explains runtime replay probability-quality regressions by slice,
competition, season, and competition-season. It loads the same staged profile set
used by runtime replay, applies the selected profile to temporary historical
slices, runs baseline and calibrated suites, and reports weighted Brier,
log-loss, calibration-error, ROI/P&L, final-answer movement, and top regression
groups. This is a diagnostic artifact only; it does not change the default
runtime path or public response shape.

The V3.1-309 proposal-ready profile was diagnosed against the same no-ESP
expanded A-league rolling-window suite:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_runtime_diagnostics_v1.json`
with `report_key=historical_probability_calibration_profile_runtime_diagnostics:45a42c3e1d699d0e`.
The report covers `slice_count=180`, `fixture_count=2160`,
`prediction_count=6480`, `adjusted_fixture_count=1126`, and
`adjusted_candidate_count=3378`. Its overall deltas match the failed replay:
`final_answer_hit_delta_count=1`, `roi_delta=0.018993574297188755`,
`profit_loss_delta=9.4588`, `brier_score_delta=0.004950884450535403`,
`log_loss_delta=0.011755583705955419`, and
`mean_calibration_error_delta=0.005865258907091386`.

The regression is highly concentrated. The top groups are
`ENG_CHAMPIONSHIP|2021-2022` and `ENG_CHAMPIONSHIP|2020-2021`; combined with the
competition-level `ENG_CHAMPIONSHIP` group, they explain the meaningful
probability-quality drag. The largest slice,
`football_data_co_uk_eng_championship_2021_2022_market_features_v1_rolling_window_v1_001`,
is also the slice that produces the positive final-answer hit and P&L movement,
which means the current profile is not simply bad; it is mixing a profitable
local recommendation change with unacceptable probability calibration damage.
Current decision: do not relax no-harm gates. The next refinement should split or
guard early ENG_CHAMPIONSHIP windows, then rerun runtime replay before any
activation discussion.

Probability calibration runtime refinement:

`CandidateProbabilityCalibrationProfile` now supports guarded application by
season and competition-season context: `target_season_ids`,
`excluded_season_ids`, `min_competition_season_index`,
`max_competition_season_index`,
`min_competition_season_index_by_competition_id`, and
`max_competition_season_index_by_competition_id`. Runtime replay now passes the
historical slice season and computed competition-season index into the temporary
calibration input, so these guards are testable without changing production
recommendations.

`nutmeg-recommendation-historical-probability-calibration-profile-runtime-refinement`
creates a separate guarded profile-set artifact from a staged profile set. It
does not mutate the source proposal, does not preserve runtime proposal flags by
default, and marks the result as `runtime_refinement_candidate`.

The first real refinement applied `ENG_CHAMPIONSHIP:3` as a minimum
competition-season index guard:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_eng_championship_index3_runtime_refinement_v1.json`
with `report_key=historical_probability_calibration_profile_runtime_refinement:de1caa5bca8de7e3`.
It also wrote:
`configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_eng_championship_index3_refined_profile_set_v1.json`.

Replay of that guarded profile produced:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_eng_championship_index3_runtime_replay_v1.json`
with `report_key=historical_probability_calibration_profile_runtime_replay:d4119db9785f7f04`.
The guard reduced calibration reach to `adjusted_fixture_count=1012` and
`adjusted_candidate_count=3036`, changed `2` final answers, but produced no
final-answer gain: `final_answer_hit_delta_count=0`, `roi_delta=0.0`, and
`profit_loss_delta=0.0`. Probability quality was almost neutral but still failed
strict no-harm with `brier_score_delta=0.00002659223155954127` and
`log_loss_delta=0.00007617998045006402`.

The guarded diagnostics report:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_eng_championship_index3_runtime_diagnostics_v1.json`
with `report_key=historical_probability_calibration_profile_runtime_diagnostics:009cedc78fa30059`
shows the earlier ENG_CHAMPIONSHIP drag was removed, but the remaining tiny
regression is scattered across ITA_SERIE_B and FRA_LIGUE_2 slices without
final-answer benefit. Current decision: the ENG_CHAMPIONSHIP index guard is
negative evidence, not an activation candidate. The next step should move from
manual exclusion to a movement-aware refinement/search objective that only keeps
probability adjustments when they create final-answer movement and satisfy
probability-quality no-harm.

Probability calibration movement-aware refinement search:

`nutmeg-recommendation-historical-probability-calibration-profile-runtime-refinement-search`
now turns replay diagnostics into a small governed search. It can read a runtime
diagnostics report, generate candidate competition-season guards from the top
regression groups, run runtime replay for each candidate, and accept only
refinements that simultaneously preserve final-answer movement, final-answer
hit/ROI/P&L no-regression, and Brier/log-loss/calibration-error no-harm. This is
still shadow-only evidence and does not write a default runtime profile.

The first real search used the original no-ESP proposal profile and the V3.1-312
diagnostics report, generating two candidates from the top ENG_CHAMPIONSHIP
competition-season regressions:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_movement_aware_refinement_search_v1.json`
with `report_key=historical_probability_calibration_profile_runtime_refinement_search:195c37602177695c`.
The search evaluated `candidate_count=2`; `accepted_count=0` and
`rejected_count=2`.

Candidate `ENG_CHAMPIONSHIP:2` preserved the original final-answer gain:
`changed_final_answer_count=3`, `final_answer_hit_delta_count=1`,
`roi_delta=0.018993574297188755`, and `profit_loss_delta=9.4588`.
It was correctly rejected because probability quality still regressed:
`brier_score_delta=0.003488830396265241`,
`log_loss_delta=0.008177696224171305`, and
`mean_calibration_error_delta=0.0034554702712749075`.

Candidate `ENG_CHAMPIONSHIP:3` nearly neutralized quality damage but removed the
benefit: `changed_final_answer_count=2`, `final_answer_hit_delta_count=0`,
`roi_delta=0.0`, and `profit_loss_delta=0.0`; it still had small Brier/log-loss
regression. Current decision: no scoped guard candidate should be activated.
The next useful work is to improve the probability adjustment itself, for
example by searching lower blend weights or bucket-level damping for the
movement-preserving `ENG_CHAMPIONSHIP:2` shape, while keeping the same no-harm
runtime replay gate.

Probability calibration movement-preserving damping search:

`nutmeg-recommendation-historical-probability-calibration-profile-runtime-damping-search`
now runs a small shadow-only search over the calibration blend weight for a
selected runtime profile, with optional competition-season guard maps preserved
on each candidate. Each damping candidate is replayed through the same final
answer scenario variant path and is accepted only when it keeps final-answer
movement, final-answer hit/ROI/P&L no-regression, probability-quality no-harm,
and harm-count no-harm. The tool does not write a default runtime profile.

The first real damping search focused on the movement-preserving
`ENG_CHAMPIONSHIP:2` shape from V3.1-314:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_eng_championship_index2_blend_damping_search_v1.json`
with
`report_key=historical_probability_calibration_profile_runtime_damping_search:833bbd3eb9c1b23a`.
It evaluated `candidate_count=3`, with `accepted_count=0` and
`rejected_count=3`.

Blend `0.02` and `0.05` preserved the useful final-answer movement:
`changed_final_answer_count=1`, `final_answer_hit_delta_count=1`,
`final_answer_hit_rate_delta=0.005555555555555536`,
`roi_delta=0.018993574297188755`, and `profit_loss_delta=9.4588`.
Both were correctly rejected because probability quality still regressed:
blend `0.02` had `brier_score_delta=0.0034510020176897194`,
`log_loss_delta=0.008072511550960004`, and
`mean_calibration_error_delta=0.0034477514200900172`; blend `0.05` had
`brier_score_delta=0.0034651736471845163`,
`log_loss_delta=0.008111911415286999`, and
`mean_calibration_error_delta=0.0034506428872355666`.

Blend `0.08` reduced the probability-quality regression to
`brier_score_delta=0.000952731361585718`,
`log_loss_delta=0.002227779715672673`, and
`mean_calibration_error_delta=0.0014482631712380845`, but it lost the
final-answer benefit: `final_answer_hit_delta_count=0`, `roi_delta=0.0`, and
`profit_loss_delta=0.0`. Current decision: plain global blend damping is not an
activation path. The next useful work should move to bucket-level or
selection-aware calibration that can preserve the one profitable final-answer
movement while repairing probability quality.

Probability calibration selection-aware bucket search:

`nutmeg-recommendation-historical-probability-calibration-profile-runtime-bucket-search`
now turns runtime diagnostics into a smaller shadow search over exact
competition-season scopes and single calibration buckets. The tool selects only
diagnostic groups that already show final-answer movement, positive final-answer
hit delta, and positive profit/loss delta, then replays exact-season and
single-bucket variants through the same no-harm gates used by runtime replay. It
does not modify the default runtime profile.

The first real search focused on the only positive diagnostic group from the
failed no-ESP profile, `ENG_CHAMPIONSHIP|2021-2022`, with draw market-odds
buckets:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_selection_bucket_search_v1.json`
with
`report_key=historical_probability_calibration_profile_runtime_bucket_search:08b8e41ae0a557d6`.
It evaluated `candidate_count=6`, with `accepted_count=0` and
`rejected_count=6`.

The informative candidate was the single bucket
`ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000`. At blend `0.05`, it adjusted
`43` fixtures and preserved the useful final-answer movement:
`changed_final_answer_count=1`, `final_answer_hit_delta_count=1`,
`final_answer_hit_rate_delta=0.005555555555555536`,
`roi_delta=0.018993574297188755`, and `profit_loss_delta=9.4588`.
It was still rejected because probability quality regressed:
`brier_score_delta=0.003451320041885586`,
`log_loss_delta=0.008071977702725608`, and
`mean_calibration_error_delta=0.003453172762957424`. Blend `0.10` preserved the
same final-answer benefit but had slightly larger quality regression.

The exact-season candidates adjusted `59` fixtures and produced the same
settlement benefit, but also the same quality failure. The other single bucket,
`ENG_CHAMPIONSHIP:1x2:draw:0.2000-0.3000`, adjusted `16` fixtures and was
quality-neutral, but it did not change any final answer, so it was rejected for
`changed_final_answer_count:below_threshold`.

Current decision: the useful movement is selection/value related, not a clean
probability-calibration improvement. Further narrowing from season to bucket did
not repair Brier/log-loss/ECE. The next useful work should separate probability
calibration from final-answer arbitration by testing a selection-side
quality/value adjustment that can reproduce the profitable movement without
rewriting the probability grid.

Final-answer selection-value signal search:

Historical backtests now support a separate
`final_answer_selection_value_signal` adjustment. Unlike probability
calibration, this signal never rewrites model probabilities or the score grid;
it only adds a bounded boost or penalty in the final-answer sorting layer for
options containing candidates that match competition, outcome, odds,
probability, model-edge, and scored-candidate ranges. This gives Nutmeg a
cleaner way to test value-side selection behavior without pretending it is a
probability improvement.

`nutmeg-recommendation-final-answer-selection-value-signal-search` reads the
selection-aware bucket search report, converts the informative market-implied
probability bucket to an odds range, and runs a small shadow search through the
same historical suite. For the `ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000`
bucket, the odds range is `2.5` to `3.3333333333333335`.

The first low-strength search:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_search_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_search:6d4332b922cc2c08`
evaluated strengths `0.02`, `0.04`, and `0.08`. All three candidates were
rejected because they did not affect the final answer:
`affected_leg_count=0`, `changed_final_answer_count=0`, and all settlement and
probability-quality deltas were `0.0`.

The stronger follow-up search:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_search_stronger_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_search:17bba0f6b95ce867`
evaluated strengths `0.16`, `0.32`, and `0.64`. This confirmed the signal can
move final answers and improve settlement metrics, but still cannot pass
strict no-harm.

Strength `0.32` changed `6` final answers, improved
`final_answer_hit_delta_count` by `1`, moved `roi_delta` by
`0.06038927846216326`, and improved `profit_loss_delta` by `30.565199999999997`.
It was rejected because selected-answer probability quality still regressed:
`brier_score_delta=0.0027818260224740377`,
`log_loss_delta=0.006527136918490939`, and
`mean_calibration_error_delta=0.004262916725076948`; it also had
`profit_loss_harm_count_vs_baseline=1`.

Strength `0.64` produced the strongest settlement gain:
`changed_final_answer_count=11`, `final_answer_hit_delta_count=3`,
`roi_delta=0.10323218763164546`, and
`profit_loss_delta=55.589980000000004`, but was rejected because it had
`final_hit_harm_count_vs_baseline=1`,
`profit_loss_harm_count_vs_baseline=3`, and probability-quality regression.
Current decision: the value signal is real but too blunt. The next useful work
is a harm-aware candidate-pool or scenario-level selector that can keep the
profitable movements while blocking the harmful ones, rather than simply
raising the final-answer boost.

Final-answer selection-value signal guard:

Historical backtests now support scenario-level guard conditions for the
selection-value signal. A value boost can be blocked when the boosted option
falls too far below the non-signal reference option's hit probability, when the
option ROI is below a configured floor, or when option risk exceeds a configured
ceiling. The guard is applied only inside the final-answer arbitration layer and
does not change model probabilities, calibrated probabilities, score grids, or
default production recommendations.

`nutmeg-recommendation-final-answer-selection-value-signal-search` can now vary
`max_hit_probability_deficit`, `min_option_roi`, and
`max_option_risk_score` in candidate specs. The first attempted 16-candidate
full guard grid was intentionally stopped after it ran for more than 25 minutes,
which exposed a replay-cost bottleneck: every guard candidate currently reruns
the complete rolling-window suite instead of reusing baseline/source replay
state.

The focused smoke replay:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_guard_smoke_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_search:e8c82cc325af9e8f`
tested `strength=0.32` with `max_hit_probability_deficit=0.02`. The guard
blocked `3295` completed options and reduced the affected final-answer legs
from the prior unguarded `10` to `6`, while changed final answers moved from
`6` to `4`.

The smoke candidate still preserved some settlement gain:
`final_answer_hit_delta_count=1`, `final_answer_hit_rate_delta=0.005555555555555536`,
`roi_delta=0.03675667266768222`, and
`profit_loss_delta=18.065199999999997`. It was still rejected because
selected-answer probability quality regressed:
`brier_score_delta=0.0023588657722446726`,
`log_loss_delta=0.005673528032113406`, and
`mean_calibration_error_delta=0.0037975410042941915`; one local
profit/loss harm remained, with `profit_loss_harm_count_vs_baseline=1`.

Current decision: the guard is a real improvement over the blunt boost because
it reduced exposure and removed final-hit harm, but it is not sufficient for
activation. The next useful work is not a larger brute-force guard grid; it is
to add replay reuse or a movement-level diagnostic cache so harmful movements
can be isolated before running expensive full-suite candidates.

Final-answer movement diagnostics cache:

`nutmeg-recommendation-final-answer-selection-value-signal-search` now supports
`--include-movement-diagnostics` and `--movement-diagnostics-limit`. Candidate
reports always include movement counts, and diagnostics mode adds bounded
records for changed final-answer movements. Each movement record captures the
baseline answer, candidate answer, settlement deltas, Brier/log-loss/ECE deltas,
movement classification, and selected-leg features such as probability, decimal
odds, market-implied probability, model edge, recommendation score, data
quality, calibration, model confidence, odds stability, and volatility.

The first real diagnostics replay used the V3.1-318 guarded smoke candidate:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_movement_diagnostics_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_search:a7906f69e12b10aa`.
It kept the same aggregate decision as the guarded smoke: `candidate_count=1`,
`accepted_count=0`, `rejected_count=1`.

The movement cache shows the remaining issue clearly: `movement_count=4`,
`positive_movement_count=3`, `harmful_movement_count=1`,
`probability_quality_harm_movement_count=3`, and
`clean_positive_movement_count=1`. The single harmful movement is
`football_data_co_uk_eng_championship_2020_2021_market_features_v1_rolling_window_v1_001`,
where the candidate answer switched into `2x1:multiple#variant1` and lost
`6.0` units with a large probability-quality regression
(`brier_score_delta=0.2953839418881771`,
`log_loss_delta=0.7087932519662377`).

The harmful movement's selected legs all had negative model edge, with draw
legs around probability `0.2762` / `0.2896`, decimal odds `3.43` / `3.27`,
scores around `0.50`, data quality `72.0`, model confidence `0.66`, and one
home-win leg carrying `volatility_penalty=0.14017549150489517`. Current
decision: the next guard should be movement-conditioned and leg-feature-aware,
not a blind boost or blind pass-type block, because some profitable movements
also use multiple-selection answers.

Movement-conditioned selection-value smoke:

`nutmeg-recommendation-final-answer-selection-value-signal-search` can now read
a prior movement diagnostics report through `--movement-diagnostics-report` and
generate narrowly scoped candidate specs from clean-positive movements. The
first implementation extracts selected legs from `clean_positive` records that
match the source value-signal spec, then creates a small score band around that
leg. This lets the next replay test the exact useful movement without blindly
boosting the whole original bucket.

The first real movement-conditioned replay used the V3.1-319 diagnostics report
and generated one score-band spec from the clean-positive draw leg:
`score_min=0.5034391225480457`,
`score_max=0.5064391225480456`, `strength=0.32`, and
`max_hit_probability_deficit=0.02`. The report is:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_movement_conditioned_smoke_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_search:6aef56ade4f16770`.

This is the first accepted candidate in this chain: `candidate_count=1`,
`accepted_count=1`, `rejected_count=0`. The candidate changed exactly one final
answer: `movement_count=1`, `positive_movement_count=1`,
`harmful_movement_count=0`, `probability_quality_harm_movement_count=0`, and
`clean_positive_movement_count=1`. It kept the clean settlement gain from
`football_data_co_uk_eng_championship_2022_2023_market_features_v1_rolling_window_v1_006`
with `profit_loss_delta=4.245799999999999`.

The aggregate no-harm gates passed: `final_answer_hit_delta_count=0`,
`roi_delta=0.008980646395104222`, `profit_loss_delta=4.245799999999999`,
`brier_score_delta=-0.0002751958116523068`,
`log_loss_delta=-0.000555299286751243`, and
`mean_calibration_error_delta=-0.00030225164203084853`, with
`final_hit_harm_count_vs_baseline=0` and
`profit_loss_harm_count_vs_baseline=0`.

Current decision: this is proposal-quality shadow evidence, not a default
activation. The useful pattern is no longer a broad ENG_CHAMPIONSHIP draw
bucket; it is a movement-conditioned narrow score band. The next useful work is
to run rolling/admission validation for this accepted smoke candidate and, if
stable, promote it to a governed runtime proposal rather than turning it on
directly.

Selection-value production proposal gate:

`nutmeg-recommendation-final-answer-selection-value-signal-production-proposal`
now converts an accepted movement-conditioned selection-value search report into
a governed runtime-profile proposal artifact. The gate checks source acceptance,
no decision reasons, probability-grid immutability, movement-conditioned
provenance, coverage, changed-answer count, positive movement count, harmful
movement count, probability-quality harm, final-hit harm, profit/loss harm, ROI,
profit/loss, Brier score, log loss, and calibration error before allowing a
candidate rule into a profile artifact.

The first governed proposal used
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_movement_conditioned_smoke_v1.json`
and produced
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_production_proposal_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_production_proposal:ac7ab4421c1e1a60`.
Status is `runtime_profile_proposal_ready`, with `proposal_count=1`,
`runtime_profile_proposal_allowed=true`, and `holdout_candidate_allowed=true`.
The generated profile artifact is
`configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_proposal_profile_set_v1.json`.

Current decision: this is governed proposal evidence only. The artifact keeps
`default_recommendation_path_changed=false`, `public_default_activation=false`,
and rollback conditions for final-hit harm, profit/loss harm, probability
quality regression, and harmful movements. The next useful work is runtime
shadow replay or rolling/admission validation against this exact proposal
artifact before any default activation discussion.

Selection-value runtime replay:

`nutmeg-recommendation-final-answer-selection-value-signal-runtime-replay` now
loads a selection-value proposal profile or production proposal report and
replays it through the historical recommendation backtest path as a shadow
runtime rule. The loader accepts `final_answer_selection_value_signal_rules`
first, then falls back to generic `rules`, so the same artifact can flow from
proposal to runtime replay without hand-editing defaults.

The first full replay used
`configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_proposal_profile_set_v1.json`
against
`configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_segunda_suite_v1.json`.
The report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_runtime_replay_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_runtime_replay:d7a21b20391cf3c6`.

Runtime replay passed: `status=runtime_replay_passed`,
`runtime_replay_allowed=true`, `holdout_replay_allowed=true`,
`final_answer_count=180`, `changed_final_answer_count=1`,
`affected_leg_count=1`, `movement_count=1`, `positive_movement_count=1`,
`harmful_movement_count=0`, and
`probability_quality_harm_movement_count=0`. Aggregate no-harm also held:
`final_answer_hit_delta_count=0`,
`roi_delta=0.008980646395104222`,
`profit_loss_delta=4.245799999999999`,
`brier_score_delta=-0.0002751958116523068`,
`log_loss_delta=-0.000555299286751243`,
`mean_calibration_error_delta=-0.00030225164203084853`,
`final_hit_harm_count_vs_baseline=0`, and
`profit_loss_harm_count_vs_baseline=0`.

Current decision: runtime-style loading reproduces the proposal evidence without
changing the public/default path. The candidate still has negative absolute
candidate ROI (`candidate_roi=-0.037760317460317466`), so the next useful gate
is rolling/admission validation or a stricter ROI-floor holdout decision before
any activation work.

Selection-value runtime admission gate:

`nutmeg-recommendation-final-answer-selection-value-signal-runtime-admission`
now consumes a selection-value runtime replay report and makes the final
governance decision for this stage: `accepted`, `holdout_only`, or `rejected`.
It does not rerun the solver and it does not write defaults. It verifies replay
status, rule count, selected rule count, final-answer coverage, changed-answer
count, affected leg count, movement health, final-hit no-harm, ROI/P&L no-harm,
Brier/log-loss/calibration no-regression, local harm counts, and no public or
production response changes. Unlike the replay smoke, this gate enforces a
non-negative absolute candidate ROI floor before any production admission.

The first real admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_runtime_admission_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_runtime_admission:ead6016f3db71ba3`.
It consumed
`historical_final_answer_selection_value_signal_runtime_replay:d7a21b20391cf3c6`.

Current decision: `status=holdout_only`,
`production_recommendation_allowed=false`, and `holdout_allowed=true`. The only
failed check is `candidate_roi`: actual
`-0.037760317460317466`, threshold `0.0`. All no-harm and probability-quality
checks remain passed. This keeps the signal as useful research/holdout evidence
while preventing a negative absolute-ROI rule from entering the default
recommendation path.

The same admission gate can now require the V3.2 probability model-quality
guardrail before a selection-value candidate-generation experiment is admitted.
Pass `--probability-calibration-model-quality-gate-report` together with
`--require-probability-calibration-model-quality-gate` to require
`model_quality_ready` evidence, selected-competition coverage, adjusted-fixture
coverage, unchanged final answers in the model-quality shadow gate, and
Brier/log-loss/calibration no-regression. This keeps selection-value experiments
from moving final answers unless the probability model-quality surface is also
green.

The model-quality-guarded admission report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_runtime_admission_model_quality_guarded_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_runtime_admission:efc71df93ded1da2`.
It consumed the same runtime replay and
`historical_probability_calibration_profile_model_quality_gate:7d615dd017fddefb`.
All model-quality checks passed: 4 selected competitions, 96 adjusted fixtures,
0 model-quality final-answer changes, Brier delta
`-0.013140475792027984`, log-loss delta `-0.027925615774599954`, and mean
calibration-error delta `-0.00851611160713972`. The final decision remains
`holdout_only` because the only failed check is still `candidate_roi`
(`-0.037760317460317466 < 0.0`).

Selection-value ROI-floor gap diagnostic:

`nutmeg-recommendation-final-answer-selection-value-signal-roi-floor-gap` now
consumes the strict runtime admission report, optionally links the source
runtime replay report, and quantifies how far a holdout selection-value
candidate is from the non-negative absolute ROI floor. It does not rerun the
solver, change any default profile, or expose internal strategy details to the
public recommendation path.

The first real gap report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_gap_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_roi_floor_gap:99142bc387679132`.
Status is `gap_quantified`. It consumed admission report
`historical_final_answer_selection_value_signal_runtime_admission:ead6016f3db71ba3`
and replay report
`historical_final_answer_selection_value_signal_runtime_replay:d7a21b20391cf3c6`.

The model-quality-guarded gap refresh is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_gap_model_quality_guarded_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_roi_floor_gap:1672e2ef9f54448b`.
It quantifies the remaining ROI gap at `0.037760317460317466`, with
`additional_roi_delta_needed=0.037760317460317466`,
`additional_profit_loss_needed=17.852028553358412`, and an estimated 5
additional clean positive movements needed before this narrow selection-value
lane can clear the non-negative candidate ROI floor. Current decision remains
unchanged: default activation is blocked. The next useful search should find
additional movement-conditioned, no-harm positive candidates or a stronger
same-family candidate that clears absolute ROI without lowering the floor.

Selection-value ROI-floor spec planning:

`nutmeg-recommendation-final-answer-selection-value-signal-search` now accepts
`--movement-conditioned-classes`, keeping the default at `clean_positive` while
allowing controlled research probes such as
`clean_positive,positive_with_probability_harm`. This only changes which
movement records can seed search specs; the acceptance checks still enforce
non-negative candidate ROI and all no-harm gates.

`nutmeg-recommendation-final-answer-selection-value-signal-roi-floor-spec-plan`
now turns a ROI-floor gap report plus movement diagnostics into a bounded search
plan. It is intentionally cheap: it does not run the solver and it does not
activate defaults. It ranks planned specs, records source movement risk tags,
estimates gap coverage, and recommends small-batch strict search.

The first real plan is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_spec_plan_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_roi_floor_spec_plan:6d0adf60352ba505`.
Status is `plan_ready`. It produced `spec_count=5` from `source_record_count=4`,
with `unique_source_record_count=3`,
`unique_planned_record_profit_loss_delta=24.0652`, and
`estimated_gap_coverage_ratio=1.3480372792408926` against the prior
`additional_profit_loss_needed=17.852028553358412`.

Current decision: still no activation. Four planned specs are sourced from
`positive_with_probability_harm` records, so they are only search inputs. The
next step should run the planned specs in batches of at most two under strict
thresholds: `min_candidate_roi=0.0`, no final-hit/profit-loss harm, and no
Brier/log-loss/calibration regression.

Selection-value ROI-floor batch search:

`nutmeg-recommendation-final-answer-selection-value-signal-roi-floor-batch-search`
now consumes a ROI-floor spec plan and runs only one small strict-search batch
at a time. It keeps the planned spec source visible, embeds the nested
selection-value search report, and records the strict thresholds used for
admission-style filtering. This runner exists to keep search work bounded and
auditable; it does not activate defaults.

The first real batch report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_batch0_strict_search_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_roi_floor_batch_search:45e2aa7ccdd924b7`.
It ran `batch_index=0`, `batch_size=2`, and `executed_spec_count=2` from the
five-spec plan. Status is `batch_search_no_acceptance`: `accepted_count=0` and
`rejected_count=2`.

Candidate one improved settlement metrics but failed strict probability-quality
and ROI gates: `final_answer_hit_delta_count=1`,
`profit_loss_delta=7.9193999999999996`,
`candidate_roi=-0.030471428571428573`,
`brier_score_delta=0.0009261576770460134`,
`log_loss_delta=0.0021560358568951665`, and
`mean_calibration_error_delta=0.001448735666278178`.
Candidate two preserved probability quality but still failed the ROI floor:
`candidate_roi=-0.037760317460317466`, `roi_delta=0.008980646395104222`,
`profit_loss_delta=4.245799999999999`, and all probability-quality deltas
improved.

Current decision: no selection-value candidate from batch 0 can enter proposal
or runtime admission. The useful signal is narrower now: positive-with-quality-
harm movements can raise hit/P&L, but the strict probability gate is correctly
blocking them.

Selection-value ROI-floor probability-quality prefilter:

`nutmeg-recommendation-final-answer-selection-value-signal-roi-floor-prefilter`
now consumes a ROI-floor spec plan plus prior batch reports and cheaply decides
which planned specs are worth spending a full strict solver replay on. It blocks
previously executed specs, source movements marked as probability-quality harm,
and source movements whose Brier, log-loss, or calibration deltas regress beyond
the configured threshold. This is a search-cost control gate only: it does not
activate defaults, lower the ROI floor, or expose internal strategy details to
the public recommendation path.

The first real prefilter report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_prefilter_v1.json`
with
`report_key=historical_final_answer_selection_value_signal_roi_floor_prefilter:28729d80a354c595`.
Status is `no_searchable_specs`: `planned_spec_count=5`,
`searchable_spec_count=0`, `blocked_spec_count=5`,
`previously_executed_blocked_count=2`, and
`probability_quality_blocked_count=4`.

Current decision: do not run batch 1 for this ROI-floor spec plan. Plan ranks
1-2 were already executed in batch 0; ranks 2-5 are blocked by source
probability-quality harm and positive Brier/log-loss/calibration deltas. The
recommended next action is `stop_selection_value_roi_floor_batch_search` for
this narrow selection-value bucket and move the core work back to broader
candidate discovery or probability/model quality improvements.

Final-answer core candidate recovery planning:

`nutmeg-recommendation-final-answer-core-candidate-recovery-plan` now consumes
the current quality-signal diagnostics, the exhausted selection-value
prefilter, and optional prior gate evidence to rank the next value-guard
candidate groups. It focuses on competition-specific negative ROI/loss groups,
skips global symptoms by default, emits strict no-harm acceptance floors, and
keeps the next search as an internal quality experiment only.

The first real recovery plan is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v1.json`
with `report_key=final_answer_core_candidate_recovery_plan:c1d50a289bf8312c`.
It consumed the production value-guard diagnostics
`historical_quality_signal_diagnostics:547f4945a10f47db` and the exhausted
selection-value prefilter
`historical_final_answer_selection_value_signal_roi_floor_prefilter:28729d80a354c595`.
Status is `plan_ready` with `candidate_group_count=8`.

The top ranked group is
`competition_model_edge_band:ENG_CHAMPIONSHIP:negative`
(`final_answer_count=30`, `roi=-0.156`, `profit_loss=-9.36`). A bounded
profile-grid smoke was run from that plan:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_eng_championship_negative_edge_value_guard_recovery_grid_v1.json`
with
`report_key=historical_final_answer_quality_signal_profile_grid:36baa2165b192866`.
It tested strengths `0.04`, `0.08`, and `0.12`; all three were rejected with
`quality_signal_profile:objective_improvement_missing`, `accepted_count=0`, and
`watchlist_count=0`.

Current decision: no production/default change. The broad Championship
negative-edge penalty does not move the final answer under this bounded smoke.
The next useful step is to test a narrower recovery item from the plan, starting
with a precise probability/odds segment rather than a broad league-wide
negative-edge penalty.

Final-answer recovery prior-evidence refresh:

`nutmeg-recommendation-final-answer-core-candidate-recovery-plan` now also
reads active `CompetitionRecommendationProfile` value guards as prior evidence.
This prevents already-promoted internal guards, such as Segunda Division and
Championship, from being rediscovered as fresh search targets when older
diagnostics or gate reports omit their embedded profile scope. The planner also
continues to read profile-grid candidate scopes and overlapping prior evidence.

A current-profile quality-signal diagnostic was generated at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_eng_championship_value_guard_quality_signal_diagnostics_v1.json`
with `report_key=historical_quality_signal_diagnostics:430b10c9630551ee`.
Under the bounded recovery-grid replay settings it keeps
`final_answer_hit_rate=0.6952380952380952`, `roi=0.02754542483660149`, and
`profit_loss=16.85780000000011`. This bounded ROI is lower than the production
gate ROI because it uses the profile-grid replay settings; it is used only for
candidate search triage, not as a replacement production gate.

The refreshed recovery plan is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v3.json`
with `report_key=final_answer_core_candidate_recovery_plan:c0914198a5de2add`.
It consumes current profile evidence and moves the top searchable candidate to
`competition_odds_band:ITA_SERIE_B:long_price`. Two bounded ITA Serie B grids
were then run:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ita_serie_b_long_price_value_guard_recovery_grid_v1.json`
(`report_key=historical_final_answer_quality_signal_profile_grid:34a7e489a86e4a7f`)
and
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ita_serie_b_very_low_probability_value_guard_recovery_grid_v1.json`
(`report_key=historical_final_answer_quality_signal_profile_grid:3666a4b7fe90d318`).
Both tested strengths `0.04`, `0.08`, and `0.12`; both returned
`accepted_count=0`, `rejected_count=3`, and `watchlist_count=0`.

The ITA Serie B penalty candidates are rejected for strict no-harm reasons:
each strength moves final hit rate from `0.6952380952380952` down to
`0.680952380952381`, lowers ROI by `0.0013066013071895421`, lowers P&L by
`3.476000000000001`, and exceeds final-hit and profit-loss harm thresholds.
The follow-up plan
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v4.json`
records these two ITA scopes as blocked prior evidence and moves the next
search target to `competition_model_edge_band:FRA_LIGUE_2:negative`.

Current decision: no production/default change. The current ITA Serie B
penalty-guard route is closed under this recovery branch; further improvement
should come from materially different mechanisms such as replacement
candidates, calibration repair, or the next planner target rather than stronger
penalties on the same losing segment.

Final-answer recovery penalty branch closure:

The v4 next target was executed as a bounded FRA Ligue 2 negative-edge
value-guard recovery grid at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ligue2_negative_edge_value_guard_recovery_grid_v1.json`
with
`report_key=historical_final_answer_quality_signal_profile_grid:3255269b6d53e716`.
It tested strengths `0.04`, `0.08`, and `0.12`; all three were rejected with
`quality_signal_profile:objective_improvement_missing`, `accepted_count=0`,
`rejected_count=3`, and `watchlist_count=0`. The guard matched `30` affected
legs, but final answers did not change and hit rate, ROI, P&L, Brier, log loss,
and calibration deltas were all `0.0`.

The follow-up recovery plan v5 is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v5.json`
with `report_key=final_answer_core_candidate_recovery_plan:4c92383d23eec1ad`.
It records `prior_evidence_count=10`,
`blocked_prior_evidence_count=3`, and moves the next target to
`competition_model_edge_band:ITA_SERIE_B:negative`.

The ITA Serie B broad negative-edge value-guard recovery grid was executed at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ita_serie_b_negative_edge_value_guard_recovery_grid_v1.json`
with
`report_key=historical_final_answer_quality_signal_profile_grid:c28ce716d4f98848`.
It also tested strengths `0.04`, `0.08`, and `0.12`; all three were rejected
with `quality_signal_profile:objective_improvement_missing`, `accepted_count=0`,
`rejected_count=3`, and `watchlist_count=0`. The guard matched `81` affected
legs, but final answers again did not change and all quality/objective deltas
were `0.0`.

The follow-up recovery plan v6 is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v6.json`
with `report_key=final_answer_core_candidate_recovery_plan:f218a34f34d11421`.
It records `prior_evidence_count=11`,
`blocked_prior_evidence_count=4`, and moves the next searchable target to
`competition_probability_band:PRT_PRIMEIRA_LIGA:high` with probability
`0.65-0.80`, odds `1.000001-20.0`, `max_model_edge=0.0`, and strengths
`0.04,0.08,0.12`.

Current decision: no production/default change. The latest FRA Ligue 2 and ITA
Serie B penalty-only recovery attempts did not move final answers, so this
branch is now documented as low-yield evidence. The next useful step is either
to test the v6 PRT high-probability target under the same no-harm gates, or to
pivot from penalty-only guards toward replacement ranking or calibration repair.

Final-answer recovery probability-quality guard:

The v6 next target was executed as a bounded PRT Primeira Liga high-probability
value-guard recovery grid at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_prt_primeira_liga_high_probability_value_guard_recovery_grid_v1.json`
with
`report_key=historical_final_answer_quality_signal_profile_grid:631c4603ee61d8f3`.
It tested strengths `0.04`, `0.08`, and `0.12`; all three were rejected,
`accepted_count=0`, `rejected_count=3`, and `watchlist_count=0`.

The `0.04` candidate matched `12` affected legs but did not change the final
answer, so it was rejected with
`quality_signal_profile:objective_improvement_missing`. The `0.08` and `0.12`
candidates each changed one final answer and improved bounded ROI by
`0.0006999999999999992` and P&L by `0.4283999999999999`, while keeping final
hit rate unchanged at `0.6952380952380952`. They were still rejected because
probability quality regressed:
`brier_score_delta=0.00041517877523555846`,
`log_loss_delta=0.001035817954062046`, and
`mean_calibration_error_delta=0.0007437966163081899`.

The follow-up recovery plan v7 is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v7.json`
with `report_key=final_answer_core_candidate_recovery_plan:8ae9e1b26f1ce8dd`.
It records `prior_evidence_count=12`,
`blocked_prior_evidence_count=5`, and moves the next searchable target to
`competition_probability_band:NED_EREDIVISIE:very_high` with probability
`0.80-1.00`, odds `1.000001-20.0`, `max_model_edge=0.0`, and strengths
`0.04,0.08,0.12`.

Current decision: no production/default change. The PRT high-probability branch
is a useful calibration warning: small ROI/P&L gains are not enough when Brier,
log loss, and calibration move backward. The next step can run the v7 NED
very-high-probability grid, but broader accuracy work should also consider
calibration repair or replacement ranking instead of penalty-only promotion.

Final-answer recovery calibration warning, stronger signal:

The v7 next target was executed as a bounded NED Eredivisie very-high-probability
value-guard recovery grid at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ned_eredivisie_very_high_probability_value_guard_recovery_grid_v1.json`
with
`report_key=historical_final_answer_quality_signal_profile_grid:855e117840eb4983`.
It tested strengths `0.04`, `0.08`, and `0.12`; all three were rejected,
`accepted_count=0`, `rejected_count=3`, and `watchlist_count=0`.

The `0.04` and `0.08` candidates matched `23` affected legs but did not change
the final answer, so both were rejected with
`quality_signal_profile:objective_improvement_missing`. The `0.12` candidate
changed `10` final answers and improved bounded ROI by `0.0077013071895424765`
and P&L by `4.713199999999997`, while keeping final hit rate unchanged at
`0.6952380952380952` and producing no final-hit or profit-loss local harm. It
was still rejected because probability quality regressed materially:
`brier_score_delta=0.0031095124025652954`,
`log_loss_delta=0.008277078402702642`, and
`mean_calibration_error_delta=0.007497224747661291`.

The follow-up recovery plan v8 is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v8.json`
with `report_key=final_answer_core_candidate_recovery_plan:3afe4a467bacf603`.
It records `prior_evidence_count=13`,
`blocked_prior_evidence_count=6`, and moves the next searchable target to
`competition_probability_band:GER_2_BUNDESLIGA:medium` with probability
`0.50-0.65`, odds `1.000001-20.0`, `max_model_edge=0.0`, and strengths
`0.04,0.08,0.12`.

Current decision: no production/default change. The NED very-high-probability
branch is stronger than PRT on bounded ROI/P&L movement, but it confirms the
same warning: penalty-only promotion can buy return movement by worsening
probability quality. This evidence should feed calibration repair or
replacement ranking design before any production activation.

Final-answer recovery near-exhaustion:

The v8 next target was executed as a bounded GER 2. Bundesliga
medium-probability value-guard recovery grid at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ger_2_bundesliga_medium_probability_value_guard_recovery_grid_v1.json`
with
`report_key=historical_final_answer_quality_signal_profile_grid:3d8c3d05db2a3bea`.
It tested strengths `0.04`, `0.08`, and `0.12`; all three were rejected,
`accepted_count=0`, `rejected_count=3`, and `watchlist_count=0`.

The `0.04` and `0.08` candidates matched `20` affected legs but did not change
the final answer, so both were rejected with
`quality_signal_profile:objective_improvement_missing`. The `0.12` candidate
changed `2` final answers and improved bounded ROI by `0.014627633415825875`
and P&L by `9.20515`, while keeping final hit rate unchanged at
`0.6952380952380952`. It was still rejected because it produced one local
profit-loss harm and probability quality regressed:
`brier_score_delta=0.0032344704159055215`,
`log_loss_delta=0.009148160944442818`, and
`mean_calibration_error_delta=0.0024208380272566776`.

The follow-up recovery plan v9 is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v9.json`
with `report_key=final_answer_core_candidate_recovery_plan:01b244701f6eedfc`.
It records `prior_evidence_count=14`,
`blocked_prior_evidence_count=7`, and leaves only one searchable target:
`competition_model_edge_band:GER_2_BUNDESLIGA:negative` with probability
`0.00-1.00`, odds `1.000001-20.0`, `max_model_edge=0.0`, and strengths
`0.04,0.08,0.12`.

Current decision: no production/default change. The penalty-only branch is now
nearly exhausted. Its best-looking movements continue to trade probability
quality, and the GER medium candidate also introduces a local P&L harm. The
next step can run the final v9 GER negative-edge target, after which this
recovery branch should likely close and pivot to calibration repair or
replacement ranking.

Final-answer recovery branch closure:

The final v9 target was executed as a bounded GER 2. Bundesliga broad
negative-edge value-guard recovery grid at
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ger_2_bundesliga_negative_edge_value_guard_recovery_grid_v1.json`
with
`report_key=historical_final_answer_quality_signal_profile_grid:dd3f158308c4e608`.
It tested strengths `0.04`, `0.08`, and `0.12`; all three were rejected,
`accepted_count=0`, `rejected_count=3`, and `watchlist_count=0`.

All three candidates matched `30` affected legs, kept final-answer hit rate at
`0.6952380952380952`, bounded ROI at `0.027545424836601308`, and P&L at
`16.8578`. They did not change any final answers versus baseline and produced
zero deltas for final-hit count, ROI, P&L, Brier score, log loss, and ECE, so
each was rejected with
`quality_signal_profile:objective_improvement_missing`.

The follow-up recovery plan v10 is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v10.json`
with `report_key=final_answer_core_candidate_recovery_plan:cc38e4161ad597a1`.
It records `status=no_searchable_candidate_groups`, `prior_evidence_count=15`,
`candidate_group_count=8`, `blocked_prior_evidence_count=8`, and
`searchable_candidate_group_count=0`. The recommended next action is
`review_candidate_surface_or_relax_planner_scope`; warnings include
`core_candidate_recovery:selection_value_prefilter_exhausted` and
`core_candidate_recovery:no_searchable_candidate_groups`.

Current decision: no production/default change. The current-scope penalty-only
recovery branch is closed. Further core improvement should pivot to calibration
repair, replacement ranking, or a reviewed candidate surface instead of adding
more penalty-only profile strength.

Replacement calibration search-plan pivot:

The replacement calibration segment diagnostic now emits governed search plans
instead of only listing under-ranked replacement segments. Each plan records the
source surface, whether the audit was limited to missed legs, whether it is
eligible for runtime-candidate testing, the concrete rerank search arguments, and
the required follow-up gates. Missed-leg-only audits now explicitly require a
full pre-match replacement surface before any runtime gate.

The full pre-match replacement surface calibration segment run is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_calibration_segments_v1.json`
with
`report_key=historical_replacement_calibration_segments:1f6f91b67438cdfa`.
It reads the full pre-match replacement audit
(`source_surface_kind=prematch_replacement_surface`,
`source_surface_missed_legs_only=false`,
`runtime_candidate_surface_allowed=true`), evaluates `63` actual-best
replacement observations across `58` groups, and emits `12` search plans.

The top search plan is
`profile:FRA_LIGUE_2|medium|large_deficit` with
`plan_key=historical_replacement_calibration_search_plan:11d6467b1d97f631`.
It has `11` observations, `+6` simulated actual-hit delta versus model-top
replacement, `+6` replacement-leg-hit delta, average profit/loss delta
`2.52`, and average expected-hit probability delta
`-0.05656614949233058`. Its suggested search args are:
`focus_competition_ids=["FRA_LIGUE_2"]`, `min_replacement_probability=0.35`,
`min_replacement_decimal_odds=1.75`, `max_replacement_decimal_odds=2.30`,
`min_candidate_hit_probability_delta_vs_model_top=-1.0`,
`max_candidate_hit_probability_delta_vs_model_top=-0.02`,
`min_decimal_odds_delta_vs_model_top=0.0`,
`min_actual_best_profit_loss_delta=0.0`, and `min_profit_loss_gap=0.0`.

The first shadow-only rerank from that plan is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_shadow_rerank_v1.json`
with
`report_key=historical_short_odds_shadow_rerank:989979b8757dc933`.
It evaluates `22` eligible FRA Ligue 2 medium-price large-deficit replacement
opportunities. The strongest profile,
`max_model_edge_within_deficit_v1`, changes `20` replacements, captures `10`
hindsight-best replacements, improves simulated actual hits by `+8`, improves
replacement-leg hits by `+8`, and has average profit/loss delta
`1.7118181818181817` versus model-top replacement. It remains only a
`shadow_watchlist` profile because it has `1` harm and `20` expected-hit
probability regressions. No production/default path changed.

Current decision: no production/default change. This branch has a useful
replacement-ranking signal, but it is not yet safe. The next step is to turn the
search-plan output into a final-answer/original no-harm gate for medium-price
replacement candidates, then run competition and suite admission before any
runtime profile proposal.

Medium-price replacement final-answer no-harm gate:

The final-answer replacement gate now supports the same rerank selection rules
used by the shadow reranker plus an optional replacement decimal-odds floor.
This allows the governed search plan from the calibration segment report to be
tested directly at final-answer/original level instead of being forced through a
short-odds-only profile.

The diagnostic competition gate for the FRA Ligue 2 medium large-deficit
profile is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_competition_gate_diagnostic_v1.json`
with `report_key=historical_short_odds_competition_gate:580a550b7f274c8a`.
It evaluates `22` replacement opportunities for
`max_model_edge_within_deficit_v1`, changes `20` replacements, improves
simulated actual hits by `+8`, improves replacement-leg hits by `+8`, captures
`10` hindsight-best replacements, and has average profit/loss delta
`1.7118181818181817` versus model-top replacement. This is still diagnostic:
the source shadow profile was a watchlist profile with one model-top harm and
expected-hit-probability regressions.

The final-answer/original no-harm gate is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_final_answer_original_no_harm_gate_v1.json`
with `report_key=historical_short_odds_final_answer_gate:4ffb28b78572aaf2`.
It changes `20` final answers, moves final-answer hits from `12` to `15`
(`+3`), and improves aggregate profit/loss from `1.64` to `23.44`
(`+21.8`). The gate correctly keeps the profile at `shadow_watchlist` because
it has `2` profit-loss harms versus the original final answer and all `20`
changed answers lower expected hit probability versus the original
(`average_hit_probability_delta_vs_original=-0.10059290325987966`).

Current decision: no production/default change. Medium-price replacement has a
real historical return signal, but the current `max_model_edge_within_deficit`
shape fails original no-harm and probability-quality expectations. The next
search should add an original-safe subset guard before final-answer selection:
exclude replacements that would lower original expected hit probability beyond a
tight tolerance or harm an already-hit original answer, then rerun the same
competition and final-answer gates.

Medium-price replacement original-safe subset gate:

The final-answer gate now has an optional original-safe subset filter before
final-answer selection. It can require each replacement to stay above a
per-item hit-probability delta floor versus the original final answer, and it
can run an evaluation-only guard that excludes replacements which turn a
historically hit original final answer into a miss. The second guard is
hindsight-only evidence for admission diagnostics and is not a runtime
pre-match strategy.

The original-safe subset report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_original_safe_subset_gate_v1.json`
with `report_key=historical_short_odds_final_answer_gate:d50ca154bc07ba33`.
It uses `min_item_hit_probability_delta_vs_original=-0.05` and
`exclude_original_hit_harm=true`.

The guard reduces `20` candidate replacement options to `2` original-safe
options. It excludes `18` options: `17` for falling below the per-item expected
hit-probability tolerance and `2` for original-hit harm. The remaining subset
changes `2` final answers, has zero original profit-loss harm, moves hits from
`0` to `1`, and improves aggregate profit/loss by `+3.6`. It still remains
`shadow_watchlist` because the average hit-probability delta versus the original
is `-0.03792178783287267`, below the report gate threshold of `-0.02`.

Current decision: no production/default change. The subset guard proves the
replacement branch can remove the most damaging historical harms, but the
remaining signal still pays for returns with too much expected-hit-probability
regression. The next search should test a stricter probability-preserving
variant or a different selection rule that can keep the `+hit/+P&L` movement
without average probability degradation.

Medium-price replacement probability-preserving grid:

A reusable grid diagnostic now searches final-answer replacement guard variants
across final-answer selection rules, shadow selection rules, replacement
probability floors, replacement odds ceilings, model-top hit-probability delta
floors, and original item-level hit-probability delta floors. It reuses the
final-answer/original no-harm gate and only emits shadow evidence; it does not
change runtime or default recommendations.

The FRA Ligue 2 medium large-deficit grid report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_probability_preserving_grid_v1.json`
with
`report_key=historical_replacement_probability_preserving_grid:af60bbe4acf517fd`.
It evaluates `1440` variants and finds `accepted_count=0`,
`shadow_watchlist_count=220`, and `rejected_count=1220`.

The best watchlist candidate is
`replacement_probability_preserving_candidate:ffe273b6e0b65a64`. It uses
`selection_rule=highest_decimal_odds_delta`,
`shadow_selection_rule=nearest_model_top_probability`,
`min_replacement_probability=0.35`, `max_replacement_decimal_odds=2.30`,
`min_candidate_hit_probability_delta_vs_model_top=-0.08`, and
`min_item_hit_probability_delta_vs_original=-0.05`. It changes `3` final
answers, keeps `harm_count_vs_original=0`, improves final-answer hits by `+1`,
and improves P/L by `+3.96`. It still remains `shadow_watchlist` because
`average_hit_probability_delta_vs_original=-0.0356615653566232`, below the
`-0.02` probability-quality gate.

Current decision: no production/default change. This grid closes the obvious
threshold-and-selection-rule search space for this FRA Ligue 2 medium
large-deficit replacement branch. The next productive direction is not to relax
the probability gate, but to improve the candidate scoring surface itself: add a
probability-preserving ranking term or calibrate replacement candidate
probabilities before reranking, then rerun the same grid.

Medium-price replacement probability-preserving model-edge reranker:

The shadow reranker now has a `probability_preserving_model_edge` selection rule.
It buckets candidate hit-probability delta versus the model-top replacement and
then ranks by replacement model edge inside each probability-preserving bucket.
This keeps the search focused on candidates that do not give away too much
expected hit probability before chasing edge or payout.

The first direct medium large-deficit grid with this rule is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_probability_preserving_model_edge_grid_v1.json`
with
`report_key=historical_replacement_probability_preserving_grid:e7bd9fa8bb3381ce`.
It evaluates `960` variants and still finds `accepted_count=0`. The best
watchlist candidate is unchanged from the previous grid and remains blocked by
average expected-hit-probability regression. This proved that changing the
tie-breaker alone is not enough while the candidate surface remains constrained
to the large-deficit corridor.

The follow-up broader probability-preserving surface grid is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_probability_preserving_surface_grid_v1.json`
with
`report_key=historical_replacement_probability_preserving_grid:0db04d500486a680`.
It evaluates `720` variants and finds `accepted_count=144` with no rejected
candidate limit. The best accepted candidate is
`replacement_probability_preserving_candidate:fcc73cbbf76917a3`:
`selection_rule=highest_candidate_hit_probability`,
`shadow_selection_rule=probability_preserving_model_edge`,
`min_replacement_probability=0.45`, `max_replacement_decimal_odds=2.10`,
`min_candidate_hit_probability_delta_vs_model_top=-0.02`, and
`min_item_hit_probability_delta_vs_original=-0.02`. It keeps only `2`
original-safe replacement options, changes `2` final answers, improves
final-answer hits by `+1`, improves P/L by `+4.04`, keeps
`harm_count_vs_original=0`, and has
`average_hit_probability_delta_vs_original=-0.010384962864403935`, which passes
the `-0.02` probability-quality gate.

Current decision: no production/default change. This is the first accepted
shadow candidate for the FRA Ligue 2 medium-price replacement branch under the
current final-answer/original no-harm gates. It should next be tested through
rolling/fold admission and cross-surface replay before any runtime proposal.

Probability-preserving replacement rolling admission:

The probability-preserving replacement branch now has a dedicated admission
gate:
`nutmeg-recommendation-replacement-probability-preserving-admission`. It reads a
grid report, selects an accepted candidate, rebuilds the final-answer gate, and
then reruns the same candidate across competition, season, and rolling-window
folds. The gate remains evidence-only and does not write runtime/default
profiles.

The first FRA Ligue 2 admission report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_probability_preserving_admission_v1.json`
with
`report_key=historical_replacement_probability_preserving_admission:4f4020f8ef77ced8`.
It selects
`replacement_probability_preserving_candidate:fcc73cbbf76917a3`, rebuilds the
overall final-answer gate as
`historical_short_odds_final_answer_gate:a4b9cf0cdb037a4b`, and returns
`status=shadow_admission_passed`.

Overall, the candidate changes `2` final answers, improves final-answer hits by
`+1`, improves P/L by `+4.04`, keeps `harm_count_vs_original=0`, and has
`average_hit_probability_delta_vs_original=-0.010384962864403935`. Fold
coverage is small but clean: `1` active competition fold, `2` active season
folds, `2` active rolling folds, and `0` failed folds. The report intentionally
keeps `replacement_probability_preserving_admission:small_changed_sample` as a
warning because only two final answers changed.

Current decision: no production/default change. This is stronger than the prior
grid-only evidence, but still not enough for runtime promotion. The next gate
should replay the same candidate against broader or adjacent replacement
surfaces and require more changed final-answer samples before proposal.

Probability-preserving replacement cross-surface replay:

The cross-surface replay gate is available as
`nutmeg-recommendation-replacement-probability-preserving-surface-replay`. It
selects an accepted probability-preserving grid candidate and replays the same
constraints across source, all-audit, non-source, and per-competition surfaces.
This keeps the test evidence-focused: no runtime/default profile is written.

The first cross-surface replay report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_cross_surface_replay_v1.json`
with
`report_key=historical_replacement_probability_preserving_surface_replay:c2ec3a10d5684c08`.
It selects
`replacement_probability_preserving_candidate:fcc73cbbf76917a3` and returns
`status=cross_surface_passed`.

The replay activates `6` surfaces and has `0` failed surfaces. The all-audit
second-tier surface covers `ENG_CHAMPIONSHIP`, `ESP_SEGUNDA_DIVISION`,
`FRA_LIGUE_2`, `GER_2_BUNDESLIGA`, and `ITA_SERIE_B`; it changes `4` final
answers, improves final-answer hits by `+1`, improves P/L by `+4.18`, keeps
`harm_count_vs_original=0`, and has
`average_hit_probability_delta_vs_original=-0.011887242668340958`. The
non-source surface contributes `2` changed final answers from
`GER_2_BUNDESLIGA` and `ITA_SERIE_B`, with P/L `+0.14`, no harm, and average
hit-probability delta `-0.013389522472277982`.

Current decision: no production/default change. Cross-surface replay shows the
candidate is not purely a one-league artifact, but the total changed sample is
still only `4`, so the report keeps
`replacement_probability_preserving_surface_replay:small_changed_sample`. The
next useful step is an adjacent-threshold expansion grid that searches for the
same no-harm/probability-preserving behavior with more changed final answers.

Probability-preserving adjacent-threshold expansion:

The adjacent-threshold expansion reruns the probability-preserving grid across
nearby probability, odds, model-top hit-probability delta, and original
hit-probability delta thresholds on the five second-tier surfaces. It keeps the
same final-answer no-harm and probability-quality gates, but asks for at least
`4` changed final answers before a candidate can be accepted.

The full expansion grid is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_expansion_grid_v1.json`
with
`report_key=historical_replacement_probability_preserving_grid:eaa49fb01d0e29f6`.
It evaluates all `2880` variants with `candidate_limit_reached=false` and finds
`accepted_count=634`. The best candidate is
`replacement_probability_preserving_candidate:e7211ed048c16bc9`:
`selection_rule=highest_candidate_hit_probability`,
`shadow_selection_rule=probability_preserving_model_edge`,
`min_replacement_probability=0.45`, `min_replacement_decimal_odds=1.65`,
`max_replacement_decimal_odds=2.30`,
`min_candidate_hit_probability_delta_vs_model_top=-0.015`, and
`min_item_hit_probability_delta_vs_original=-0.02`.

That candidate changes `7` final answers, improves final-answer hits by `+2`,
improves P/L by `+7.66`, keeps `harm_count_vs_original=0`, and has
`average_hit_probability_delta_vs_original=-0.010617165781314062`.

The matching cross-surface replay is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_cross_surface_replay_v3.json`
with
`report_key=historical_replacement_probability_preserving_surface_replay:4f805ccf50449079`.
It passes with `active_surface_count=7` and `failed_surface_count=0`. Using
`FRA_LIGUE_2` as the explicit source surface, the all-audit surface changes `7`
final answers with hit delta `+2`, P/L `+7.66`, harm `0`, and average
hit-probability delta `-0.010617165781314062`. The non-source surface changes
`4` final answers from Championship, 2. Bundesliga, and Serie B, with hit delta
`0`, P/L `+0.26`, harm `0`, and average hit-probability delta
`-0.013469299406746349`.

The rolling/fold admission report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_admission_v2.json`
with
`report_key=historical_replacement_probability_preserving_admission:5c88834762079026`.
It passes as `shadow_admission_passed`: `4` active competition folds, `4` active
season folds, `7` active rolling folds, and `0` failed folds.

Current decision: no production/default change. The branch now has stronger
shadow evidence than the earlier 2- and 4-change candidates, but it still keeps
the small-sample warning because only `7` final answers changed. The next step
should either push changed final answers beyond `8` without relaxing no-harm
gates, or start a runtime-proposal dry run that remains explicitly shadow-only.

Probability-preserving 9-change expansion:

The next expansion pass searched for candidates with at least `8` changed final
answers while keeping the same no-harm, non-negative P/L, and bounded
hit-probability loss gates. The broad grid report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_8plus_grid_v1.json`
with
`report_key=historical_replacement_probability_preserving_grid:e3a6c74c036105c2`.
It evaluates `3360` variants with `candidate_limit_reached=false` and finds
`accepted_count=62`. The selected conservative 9-change candidate is
`replacement_probability_preserving_candidate:4fd64bc93a7032c8`:
`selection_rule=highest_candidate_hit_probability`,
`shadow_selection_rule=nearest_model_top_probability`,
`min_replacement_probability=0.45`, `min_replacement_decimal_odds=1.60`,
`max_replacement_decimal_odds=2.20`,
`min_candidate_hit_probability_delta_vs_model_top=-0.04`, and
`min_item_hit_probability_delta_vs_original=-0.02`.

That candidate changes `9` final answers, improves final-answer hits by `+3`,
improves P/L by `+11.40`, keeps `harm_count_vs_original=0`, and has
`average_hit_probability_delta_vs_original=-0.006252199288243949`.

The matching cross-surface replay is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_9plus_cross_surface_replay_v1.json`
with
`report_key=historical_replacement_probability_preserving_surface_replay:f011b65e8f0abbb3`.
It passes with `active_surface_count=7` and `failed_surface_count=0`. Using
`FRA_LIGUE_2` as the explicit source surface, the all-audit surface changes `9`
final answers with hit delta `+3`, P/L `+11.40`, harm `0`, and average
hit-probability delta `-0.006252199288243949`. The non-source surface changes
`6` final answers from Championship, 2. Bundesliga, and Serie B, with hit delta
`+1`, P/L `+4.00`, harm `0`, and average hit-probability delta
`-0.005971138458663751`.

The rolling/fold admission report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_9plus_admission_v2.json`
with
`report_key=historical_replacement_probability_preserving_admission:40ac66036acfe2d2`.
It passes as `shadow_admission_passed`: `4` active competition folds, `4` active
season folds, `9` active rolling folds, and `0` failed folds. A stricter
`5`-season attempt was intentionally left as
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_9plus_admission_v1.json`;
it failed only because the candidate had no 2024/25 changed final answers, not
because any active fold regressed.

Current decision: no production/default change. This is the strongest
probability-preserving replacement shadow evidence so far, but it still remains
below a robust production sample size. The next quality step should continue
increasing changed final-answer coverage or run an explicitly shadow-only
runtime-proposal dry run.

Probability-preserving 13-change expansion:

The next conservative expansion pass searched for at least `10` changed final
answers while keeping no-harm, non-negative P/L, and bounded probability loss.
The grid report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_10plus_conservative_grid_v1.json`
with
`report_key=historical_replacement_probability_preserving_grid:335045bbbf510089`.
It evaluates `2000` variants with `candidate_limit_reached=false` and finds
`accepted_count=700`, including accepted candidates at `10`, `11`, `12`, and
`13` changed final answers.

The selected conservative 13-change candidate is
`replacement_probability_preserving_candidate:3b3f3500fb3873a9`:
`selection_rule=highest_candidate_hit_probability`,
`shadow_selection_rule=nearest_model_top_probability`,
`min_replacement_probability=0.45`, `min_replacement_decimal_odds=1.50`,
`max_replacement_decimal_odds=2.20`,
`min_candidate_hit_probability_delta_vs_model_top=-0.05`, and
`min_item_hit_probability_delta_vs_original=-0.025`.

That candidate changes `13` final answers, improves final-answer hits by `+4`,
improves P/L by `+15.74`, keeps `harm_count_vs_original=0`, and has
`average_hit_probability_delta_vs_original=-0.011268524070761074`.

The first cross-surface replay is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_cross_surface_replay_v1.json`.
It is intentionally retained as a stricter watchlist report: it only fails
because the single active Segunda sample has average hit-probability delta
`-0.020650788094531636`, just below the `-0.02` per-surface threshold, while
keeping P/L flat and harm at `0`.

The accepted cross-surface replay is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_cross_surface_replay_v2.json`
with
`report_key=historical_replacement_probability_preserving_surface_replay:03ffe09f7682fb99`.
It aligns the per-surface probability threshold with the candidate's
`min_item_hit_probability_delta_vs_original=-0.025` and passes with
`active_surface_count=8`, `failed_surface_count=0`,
`all_audit_changed_final_answer_count=13`, and
`non_source_changed_final_answer_count=9`. All five competition surfaces are
active: Championship `4`, Segunda `1`, Ligue 2 `4`, 2. Bundesliga `3`, and
Serie B `1`.

The rolling/fold admission report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_admission_v1.json`
with
`report_key=historical_replacement_probability_preserving_admission:77b920cfab1ab787`.
It passes as `shadow_admission_passed`: `5` active competition folds, `5` active
season folds, `13` active rolling folds, and `0` failed folds, with no
small-sample warning.

Current decision: no production/default change. This is the first
probability-preserving replacement branch in this run with all five
competition folds, all five season folds, and more than `12` changed final
answers active. It is still shadow evidence until a runtime-proposal dry run
and broader quality gate decide whether it should become a candidate for a
governed promotion.

Probability-preserving runtime-proposal dry run:

The runtime-proposal dry run converts the selected 13-change candidate into a
runtime-style rule profile, replays it through the existing short-odds runtime
shadow engine, and writes an audit artifact without changing default profiles
or public responses. The new CLI is
`nutmeg-recommendation-replacement-probability-preserving-runtime-dry-run`.

The first dry-run artifact is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_runtime_dry_run_v1.json`.
It is intentionally retained as a watchlist report. It found that the runtime
rule profile did not yet carry the offline gate's
`exclude_original_hit_harm=true` constraint, so runtime replay changed `14`
final answers and introduced `1` harm despite positive aggregate P/L.

The runtime-shadow selector now carries that constraint. When
`exclude_original_hit_harm=true`, runtime replay excludes replacements that
would turn an originally winning final answer into a miss. The accepted dry-run
artifact is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_runtime_dry_run_v2.json`
with
`report_key=historical_replacement_probability_preserving_runtime_dry_run:26e4b04e79b27100`.
It passes as `runtime_dry_run_passed`: runtime final-answer count `99`,
changed final answers `13`, final-answer hit delta `+4`, P/L delta `+15.74`,
ROI delta `+0.040358974358974356`, harm `0`, final-hit harm `0`, P/L harm `0`,
and average hit-probability delta `-0.011268524070761074`.

The dry-run profile is explicitly marked `dry_run_only=true`,
`production_recommendation_allowed=false`,
`production_recommendation_changed=false`, and `public_response_changed=false`.
It keeps the candidate rule scoped to Championship, Segunda, Ligue 2,
2. Bundesliga, and Serie B, with `min_replacement_probability=0.45`,
`max_replacement_decimal_odds=2.20`,
`min_candidate_hit_probability_delta_vs_model_top=-0.05`, and
`min_candidate_hit_probability_delta_vs_original=-0.025`.

Current decision: no production/default change. The 13-change branch now has
grid, cross-surface, fold admission, and runtime-style dry-run evidence aligned
with no harm. The next step should connect this dry-run report to a broader
quality gate or promotion review artifact, still without exposing internal
strategy details to users.

Probability-preserving promotion review:

The promotion review artifact is the next quality gate above runtime dry run. It
does not write a default profile and does not allow production recommendations;
it only decides whether the dry-run evidence is clean enough to enter a governed
promotion review. The new CLI is
`nutmeg-recommendation-replacement-probability-preserving-promotion-review`.

The review report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_promotion_review_v1.json`
with
`report_key=historical_replacement_probability_preserving_promotion_review:9ebb08687bdba841`.
It is `promotion_review_ready` with `promotion_review_allowed=true`, while
keeping `production_recommendation_allowed=false`,
`production_recommendation_changed=false`, and `public_response_changed=false`.

The review preserves the same source chain:
`historical_replacement_probability_preserving_runtime_dry_run:26e4b04e79b27100`
and generated runtime shadow replay
`historical_short_odds_runtime_shadow_replay:4f08bc08ae552cdc`. It checks
runtime final-answer count `99`, changed final answers `13`, hit delta `+4`,
P/L delta `+15.74`, ROI delta `+0.040358974358974356`, harm `0`, final-hit harm
`0`, P/L harm `0`, average hit-probability delta
`-0.011268524070761074`, active surfaces `8`, active competition folds `5`,
active season folds `5`, active rolling folds `13`, and no failed folds.

The paired review profile artifact is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_promotion_review_profile_v1.json`.
It is marked `dry_run_only=true`, scoped to Championship, Segunda, Ligue 2,
2. Bundesliga, and Serie B, and carries the runtime constraints from the
accepted dry run, including `exclude_original_hit_harm=true`,
`max_harm_count_vs_original=0`, `max_final_hit_harm_count_vs_original=0`, and
`max_profit_loss_harm_count_vs_original=0`.

Current decision: no production/default change. The branch is now ready for a
governed review artifact, not for direct activation. The next step should either
attach this review to the broader benchmark quality gate or build an activation
smoke that remains staged-only.

Probability-preserving strategy promotion gate:

The strategy promotion gate is the final pre-activation quality summary above
promotion review. It aggregates governed review artifacts into a single
`ready` / `watchlist` / `blocked` decision for internal release planning, while
still refusing to write default profiles or change public responses. The new CLI
is `nutmeg-recommendation-strategy-promotion-gate`.

The strategy gate report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_strategy_promotion_gate_v1.json`
with `gate_key=recommendation_strategy_promotion_gate:58d3a07a29184a97`.
It is `status=ready` and `strategy_gate_ready=true`, while keeping
`production_recommendation_allowed=false`,
`production_recommendation_changed=false`, and `public_response_changed=false`.

The gate consumes the promotion review report
`historical_replacement_probability_preserving_promotion_review:9ebb08687bdba841`
and preserves the selected candidate
`replacement_probability_preserving_candidate:3b3f3500fb3873a9`. It checks
`99` final answers, `13` changed final answers, final-answer hit delta `+4`,
P/L delta `+15.74`, minimum ROI delta `+0.040358974358974356`, total harm `0`,
final-hit harm `0`, P/L harm `0`, active surface count `8`, active competition
fold count `5`, active season fold count `5`, active rolling fold count `13`,
and no failed folds or surfaces.

Current decision: no production/default change. The branch is now internally
ready for a staged-only activation smoke or broader benchmark quality-gate
attachment. It is not a user-facing strategy label and must not expose internal
selection details to ordinary users.

Probability-preserving staged activation smoke:

The staged activation smoke verifies that a strategy-gate-ready branch can be
loaded as a runtime-style rule profile while remaining staged-only. It does not
write the default profile and does not expose the internal rule to the public
recommendation response. The new CLI is
`nutmeg-recommendation-strategy-staged-activation-smoke`.

The smoke report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_staged_activation_smoke_v1.json`
with
`report_key=recommendation_strategy_staged_activation_smoke:ccb2bf3ae8bf0c29`.
It is `status=staged_activation_ready` with
`staged_activation_ready=true`, while keeping
`default_profile_write_requested=false`, `default_profile_written=false`,
`production_recommendation_allowed=false`,
`production_recommendation_changed=false`, and `public_response_changed=false`.

The staged profile artifact is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_staged_activation_profile_v1.json`.
It is marked `staged_only=true` and `dry_run_only=true`, contains one internal
short-odds replacement rule, and keeps the candidate scoped to Championship,
Segunda, Ligue 2, 2. Bundesliga, and Serie B. The rule preserves
`exclude_original_hit_harm=true`, all historical no-harm constraints at `0`,
and the same source candidate
`replacement_probability_preserving_candidate:3b3f3500fb3873a9`.

The smoke reuses the strategy gate metrics: `99` final answers, `13` changed
final answers, hit delta `+4`, P/L delta `+15.74`, minimum ROI delta
`+0.040358974358974356`, harm `0`, final-hit harm `0`, P/L harm `0`, active
surfaces `8`, active competition folds `5`, active season folds `5`, active
rolling folds `13`, and no failed folds or surfaces.

Current decision: no production/default change. The branch is now proven
loadable as a staged runtime-style profile, but it is still not activated. The
next useful step is to attach this staged smoke to the broader benchmark quality
gate or run a final default-path isolation check.

Probability-preserving default-path isolation:

The default-path isolation check proves that the staged profile is not consumed
by ordinary recommendation flow. It compares the current default competition
profile with the staged profile, verifies that the default profile does not
contain staged short-odds rules, then runs two deterministic adapter smokes:
default disabled and explicit internal opt-in. The new CLI is
`nutmeg-recommendation-strategy-default-path-isolation`.

The isolation report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_default_path_isolation_v1.json`
with
`report_key=recommendation_strategy_default_path_isolation:618686fa9967187f`.
It is `status=isolated` and `default_path_isolated=true`.

The default path remains unchanged:
`default_adapter_status=disabled`,
`default_adapter_selection_changed=false`,
`default_adapter_default_path_changed=false`,
`default_adapter_public_response_changed=false`, and the current default
profile version remains
`v3_1_competition_profiles_football_data_co_uk_2026_05_15_eng_championship_value_guard_v1`.
The staged profile is a separate artifact:
`v3_1_probability_preserving_13change_staged_activation_smoke_v1`.

The explicit internal opt-in branch is also exercised:
`explicit_opt_in_adapter_status=applied`,
`explicit_opt_in_selection_changed=true`,
`explicit_opt_in_default_path_changed=false`, and
`explicit_opt_in_public_response_changed=false`. This confirms the staged rule
can be used by a controlled internal path without leaking into ordinary user
recommendations.

Current decision: no production/default change. The 13-change branch now has
positive staged evidence and an explicit isolation proof. The next useful step
is to attach these governance artifacts to the broader benchmark quality gate so
future cycles can reject regressions automatically.

Probability-preserving benchmark quality-gate attachment:

The broader recommendation benchmark gate now accepts the three strategy
governance artifacts as first-class evidence: the strategy promotion gate, the
staged activation smoke, and the default-path isolation report. This keeps the
candidate branch inside the same pass/fail quality gate used by benchmark
cycles, instead of relying on a manual checklist.
The benchmark cycle CLI also exposes matching `--gate-recommendation-strategy-*`
arguments and carries the governance status into cycle summaries, so scheduled
quality cycles can reject strategy regressions with the same gate.

The new attached gate report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_benchmark_quality_gate_strategy_governance_v1.json`.
It passes with `gate_key=recommendation_benchmark_quality_gate:all:any`,
`status=passed`, `passed=true`, `failed_checks=[]`, and `warnings=[]`.

The attached strategy promotion evidence is present and ready:
`recommendation_strategy_promotion_gate_present=true`,
`recommendation_strategy_promotion_gate_ready=true`, `99` final answers,
`13` changed final answers, hit delta `+4`, P/L delta `+15.74`, minimum ROI
delta `+0.040358974358974356`, and all original-harm counts at `0`.

The staged activation evidence is also present and ready:
`recommendation_strategy_staged_activation_smoke_present=true`,
`recommendation_strategy_staged_activation_ready=true`,
`recommendation_strategy_staged_rule_count=1`, and
`recommendation_strategy_staged_allowed_competition_count=5`, while preserving
`default_profile_written=false`, `production_recommendation_changed=false`, and
`public_response_changed=false`.

The default-path isolation evidence remains clean:
`recommendation_strategy_default_path_isolation_present=true`,
`recommendation_strategy_default_path_isolated=true`,
`recommendation_strategy_default_adapter_status=disabled`,
`recommendation_strategy_default_adapter_selection_changed=false`, and the
explicit internal opt-in still exercises the strategy with
`recommendation_strategy_explicit_opt_in_selection_changed=true`.

Current decision: no production/default change. The main quality gate can now
reject future candidates that break default-path isolation, write the default
profile, change production/public responses, or introduce final-hit, ROI, P/L,
or original-harm regressions.

Recommendation strategy governance preset:

The three governance artifacts above are now available through a reusable
quality-gate preset:
`probability_preserving_13change_v1`.

Direct gate usage:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --recommendation-strategy-governance-preset probability_preserving_13change_v1
```

Cycle usage:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --gate-recommendation-strategy-governance-preset probability_preserving_13change_v1
```

Shadow cycle preset usage:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --cycle-preset probability_preserving_13change_governance_v1 \
  --output-path configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_benchmark_cycle_governance_preset_smoke_v1.json
```

The preset binds the strategy promotion gate, staged activation smoke, and
default-path isolation report, then applies the same no-regression and
no-production-change thresholds used by the manual gate.

The cycle preset wraps the same gate preset in a dry-run benchmark cycle. It
sets a dedicated schedule name when the default name is used, keeps the run
gated, forces dry-run behavior, and keeps core replay / chain integrity /
successor-chain evaluation enabled. It does not change the default recommendation
profile, production responses, or public response path. `--output-path` writes
the cycle result as a local JSON artifact without requiring a database-backed
cycle report save.

The preset smoke report is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_benchmark_quality_gate_strategy_governance_preset_v1.json`.
It passes with `status=passed`, `passed=true`,
`recommendation_strategy_governance_preset=probability_preserving_13change_v1`,
and `failed_checks=[]`.

The cycle preset smoke artifact is:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_benchmark_cycle_governance_preset_smoke_v1.json`.
It passes with `status=passed`, `gate_status=passed`, 27 completed benchmark
scenarios, and the same `strategy_ready=true`, `staged_ready=true`, and
`default_path_isolated=true` evidence. Current warnings are local data-window
coverage warnings: the latest 24-hour window did not have enough distinct
fixture candidates or persisted recommendation runs for replay.

Candidate coverage gate:

Benchmark summaries now include `global_best_candidate_count` and
`global_best_generated_option_count`. Quality gates can require candidate
coverage with:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --cycle-preset probability_preserving_13change_governance_v1 \
  --run-at-utc 2026-05-12T00:00:00Z \
  --save-report \
  --output-path configs/recommendations/historical_reports/local_seed_probability_preserving_13change_benchmark_cycle_candidate_coverage_smoke_v1.json
```

The governance cycle preset requires at least one selected global-best answer,
one evaluated candidate, and one generated option. The local seed candidate
coverage smoke passes with 27 selected answers, 486 evaluated candidates, 27
generated options, and `failed_checks=[]`.

Core replay seed:

The cycle remains dry-run by default. When a local deterministic smoke needs
non-empty persisted recommendation runs for core replay, explicitly add a
committed seed step:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --cycle-preset probability_preserving_13change_governance_v1 \
  --run-at-utc 2026-05-12T00:00:00Z \
  --commit-core-replay-seed \
  --save-report \
  --output-path configs/recommendations/historical_reports/local_seed_probability_preserving_13change_benchmark_cycle_core_replay_seed_smoke_v1.json
```

`--commit-core-replay-seed` first writes the deterministic baseline fixtures and
one committed replay seed budget per pass type / mode, then the cycle itself
continues to run in dry-run mode across the full benchmark matrix and replays
those persisted runs. The option is explicit because it writes local seed data;
it does not change the default recommendation profile, production response
path, public response path, or user recommendation wording.

The local seeded core replay smoke passes with `core_replay_seed_stored_run_count=9`,
`core_replay_ready_ratio=1.0`, `final_hit_sample_size=27`,
`final_hit_coverage_ratio=1.0`, `gate_status=passed`, and `warnings=[]`.

Successor effective-final-only cycle preset smoke:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --cycle-preset probability_preserving_13change_governance_v1 \
  --run-at-utc 2026-05-12T00:00:00Z \
  --commit-core-replay-seed \
  --save-report \
  --output-path configs/recommendations/historical_reports/local_seed_probability_preserving_13change_benchmark_cycle_budget_adjusted_arbitrator_preset_smoke_v1.json
```

The governance cycle preset now also binds the core+expanded historical
successor effective-final-only suite gate with budget-adjusted final-answer
arbitration by default, unless a caller provides a specific historical suite
gate report path. The local preset smoke passes with `gate_status=passed`,
`core_replay_ready_ratio=1.0`,
`final_hit_coverage_ratio=1.0`, `historical_suite_slice_count=240`,
`historical_suite_candidate_final_hit_sample_size=240`,
`historical_suite_candidate_final_hit_coverage_ratio=1.0`,
`historical_suite_successor_chain_evaluation_passed=true`,
`historical_suite_successor_effective_final_only_ready=true`,
`historical_suite_successor_effective_leaf_count=1`,
`historical_suite_successor_active_edge_count=1`, and `gate_failed_checks=[]`.

Historical final-hit coverage smoke:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/euro_2024_knockout_suite.json \
  --pass-types 1x1,2x1 \
  --modes single \
  --candidate-fixture-limit 8 \
  --max-candidates-per-fixture 2 \
  --final-answer-scenario-variant-count 2 \
  --min-slice-count 1 \
  --min-comparison-count 1 \
  --min-final-hit-sample-size 1 \
  --min-final-hit-coverage-ratio 1.0 \
  --min-final-hit-rate-delta=-1 \
  --max-brier-score-delta 1 \
  --max-log-loss-delta 1 \
  --max-mean-calibration-error-delta 1 \
  --output-path configs/recommendations/historical_reports/local_euro_2024_historical_suite_final_hit_coverage_gate_smoke_v1.json
```

The local historical smoke passes with `candidate_final_hit_coverage_ratio=1.0`,
`candidate_final_hit_sample_size=1`, `failed_checks=[]`, and `warnings=[]`.

Broader historical final-hit coverage smoke:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --min-slice-count 210 \
  --min-comparison-count 210 \
  --min-final-hit-sample-size 210 \
  --min-final-hit-coverage-ratio 1.0 \
  --min-final-hit-rate-delta=-1 \
  --min-roi-delta=-100 \
  --min-profit-loss-delta=-10000 \
  --max-brier-score-delta 10 \
  --max-log-loss-delta 10 \
  --max-mean-calibration-error-delta 10 \
  --max-warning-count 0 \
  --output-path configs/recommendations/historical_reports/local_expanded_a_leagues_rolling_window_full_matrix_final_hit_coverage_gate_smoke_v1.json
```

The broader full-matrix smoke passes on the 210-slice expanded rolling-window
suite with `candidate_final_hit_sample_size=210`,
`candidate_final_hit_coverage_ratio=1.0`,
`candidate_final_hit_rate=0.6952380952380952`,
`candidate_roi=0.027545424836601308`, `candidate_profit_loss=16.8578`,
and `failed_checks=[]`, `warnings=[]`. This is internal governance evidence
for final-answer coverage; it does not change the production/default path.

Broader successor effective-final-only gate:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --successor-chain-evaluation-report-path configs/recommendations/historical_reports/local_successor_chain_evaluation_smoke_v1.json \
  --require-successor-chain-evaluation \
  --min-successor-effective-leaf-count 1 \
  --min-successor-active-edge-count 1 \
  --max-successor-critical-issue-count 0 \
  --max-successor-ambiguous-source-count 0 \
  --max-successor-source-status-sync-required-count 0 \
  --min-slice-count 210 \
  --min-comparison-count 210 \
  --min-final-hit-sample-size 210 \
  --min-final-hit-coverage-ratio 1.0 \
  --min-final-hit-rate-delta=-1 \
  --min-roi-delta=-100 \
  --min-profit-loss-delta=-10000 \
  --max-brier-score-delta 10 \
  --max-log-loss-delta 10 \
  --max-mean-calibration-error-delta 10 \
  --max-warning-count 0 \
  --output-path configs/recommendations/historical_reports/local_expanded_a_leagues_rolling_window_full_matrix_successor_effective_final_only_gate_smoke_v1.json
```

The successor-linked broader gate passes with the same 210/210 settled final-hit
coverage and attaches `successor_chain_evaluation_passed=true`,
`successor_effective_final_only_ready=true`, `successor_effective_leaf_count=1`,
`successor_active_edge_count=1`, `successor_critical_issue_count=0`,
`successor_ambiguous_source_count=0`, and
`successor_source_status_sync_required_count=0`. Benchmark quality gates and
cycle gate options can also require these historical-suite successor fields.
The benchmark-gate consumption smoke is
`configs/recommendations/historical_reports/local_expanded_a_leagues_rolling_window_full_matrix_successor_effective_final_only_benchmark_gate_smoke_v1.json`;
it passes with the same successor fields and no failed checks or warnings.

Core+expanded successor effective-final-only gate:

```bash
uv run nutmeg-recommendation-historical-suite-gate \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json \
  --suite-manifest configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json \
  --pass-types 1x1,2x1,3x1,4x1,5x1,6x1,7x1,8x1 \
  --modes single,multiple \
  --unit-stake 2 \
  --max-budget 20 \
  --min-probability 0.15 \
  --min-data-quality-score 50 \
  --candidate-fixture-limit 12 \
  --max-candidates-per-fixture 3 \
  --scenario-candidate-fixture-buffer 4 \
  --derive-market-context-signals \
  --successor-chain-evaluation-report-path configs/recommendations/historical_reports/local_successor_chain_evaluation_smoke_v1.json \
  --require-successor-chain-evaluation \
  --min-successor-effective-leaf-count 1 \
  --min-successor-active-edge-count 1 \
  --max-successor-critical-issue-count 0 \
  --max-successor-ambiguous-source-count 0 \
  --max-successor-source-status-sync-required-count 0 \
  --min-slice-count 240 \
  --min-comparison-count 240 \
  --min-final-hit-sample-size 240 \
  --min-final-hit-coverage-ratio 1.0 \
  --min-final-hit-rate-delta=-1 \
  --min-roi-delta=-100 \
  --min-profit-loss-delta=-10000 \
  --max-brier-score-delta 10 \
  --max-log-loss-delta 10 \
  --max-mean-calibration-error-delta 10 \
  --max-warning-count 0 \
  --output-path configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_adjusted_arbitrator_successor_effective_final_only_gate_smoke_v1.json
```

The multi-manifest gate passes with `slice_count=240`,
`candidate_final_hit_sample_size=240`,
`candidate_final_hit_coverage_ratio=1.0`,
`candidate_final_hit_rate=0.7041666666666667`,
`candidate_roi=0.0173867918452381`,
`candidate_profit_loss=11.683924120000004`,
`successor_chain_evaluation_passed=true`, and no warnings. The matching
benchmark-gate consumption smoke is
`configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_adjusted_arbitrator_benchmark_gate_smoke_v1.json`.

Budget-adjusted arbitration:

The final-answer arbitrator now reads internal `budget_adjustment` evidence
from multiple-selection optimizers. A multiple ticket that only fits budget
after heavy pruning gets a `budget_adjustment_quality` component and a bounded
`budget_adjustment_penalty`; stable single or naturally budget-safe answers are
unchanged. The 240-slice core+expanded gate above is byte-for-byte identical to
the previous gate metrics, so this change adds protection for future severe
budget clipping without perturbing the current historical final answers.

Current decision: no production/default recommendation profile change. The
preset only makes internal governance checks stricter and easier to reuse in
benchmark cycles.

Budget stability audit:

`nutmeg-recommendation-budget-stability-audit` replays the same historical
slices across user budget tiers and reports final-answer signature changes,
hit/ROI/profit deltas, stake deltas, budget-adjustment evidence, and slice-level
reason codes. It is an offline governance tool only; it does not change the
production recommendation profile or expose internal strategy labels to users.

The core+expanded 240-slice smoke report is
`configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_audit_smoke_v1.json`.
For budgets `10,20` with `20` as the reference, the audit produced
`signature_changed_count=4`, `signature_change_rate=0.016666666666666666`,
`harmful_change_count=2`, `beneficial_change_count=2`,
`hit_delta_count=-1`, and `roi_delta=-0.004065850149331659`. Budget `10`
finished at `final_hit_rate=0.7`, `roi=0.013320941695906441`; budget `20`
finished at `final_hit_rate=0.7041666666666667`,
`roi=0.0173867918452381`.

The current budget-stable arbitrator smoke report is
`configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_multiple_tie_breaker_smoke_v1.json`.
It preserves max-budget context through the multiple optimizer, treats budget
efficiency as an in-budget hard constraint at final arbitration time, and adds a
tiny multiple-coverage tie-breaker only after the core budget/risk constraints
are satisfied. For budgets `10,20` with `20` as the reference, it produced
`signature_changed_count=0`, `signature_change_rate=0.0`,
`harmful_change_count=0`, `hit_delta_count=0`, `profit_loss_delta=0.0`,
and `roi_delta=0.0`. Both budget tiers finished at
`final_hit_rate=0.7083333333333334`, `roi=0.03886684347578348`,
`profit_loss=27.284524120000004`, `total_stake=702.0`, and
`multiple_final_answer_count=37`. This keeps strict budget stability while
recovering positive absolute ROI/profit on the current 240-slice smoke set.

Handicap final-answer path:

The recommendation planner and historical replay path now accept Chinese
handicap 1X2 and European handicap 1X2 candidates as first-class final-answer
inputs. `european_handicap_1x2` is included in the parlay rule engine's market
leg limits, and historical replay settles both handicap markets from final
scores plus the normalized integer line. This keeps handicap recommendations on
the same score-grid-derived market resolver and final-answer arbitration path
as ordinary 1X2.

The current handicap coverage shadow audit report is
`configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_handicap_coverage_shadow_audit_v1.json`.
Across the current core+expanded historical sample it found `240` slices,
`13258` fixtures, and `39774` total stored market predictions, but
`handicap_prediction_count=0`, `handicap_fixture_count=0`, and
`complete_handicap_fixture_count=0`. The shadow replay therefore had
`changed_final_answer_count=0`, `candidate_handicap_final_answer_count=0`,
`final_hit_delta_count=0`, and `profit_loss_delta=0.0`. This is a data coverage
finding, not evidence that handicap markets are ineffective.

To unblock that data gap, `nutmeg-recommendation-historical-handicap-odds-import`
can enrich an existing historical slice from a CSV of complete integer-line
Chinese or European handicap 1X2 odds. It normalizes home/draw/away labels to
`handicap_home_win`, `handicap_draw`, and `handicap_away_win`, computes raw and
no-vig probabilities from decimal odds when explicit probabilities are absent,
and writes the enriched slice back into the existing historical backtest and
coverage-audit contract. This is an import/readiness path only; it does not
change default production recommendation weights.

The local football-data.co.uk archive also contains a large free Asian handicap
sample. `nutmeg-recommendation-football-data-co-uk-asian-handicap-coverage`
audits the `AHh/AHCh` line columns and the matching `*AHH/*AHA` odds columns,
then converts rows into structured `asian_handicap` odds-movement features for
future model work. The current local report is
`configs/recommendations/historical_reports/local_football_data_co_uk_asian_handicap_coverage_v1.json`.
It found `61` CSV sources, `26890` rows, `22360` importable Asian-handicap rows,
coverage of `0.8315358869468203`, and `8268` line-change rows. Japan/J1 remains
uncovered in this archive because its local CSV has no Asian-handicap columns.

Football-data feature samples can now opt into those Asian-handicap features
with `--include-asian-handicap-features`. The option keeps the existing 1X2
baseline predictions unchanged and adds `asian_handicap` movements for
`home_cover` and `away_cover` into the fixture feature snapshot. The Poisson
prematch-feature readout can evaluate those cover-probability movements through
an explicit Asian-handicap movement weight and minimum probability-delta gate,
so handicap movement can be damped or disabled in shadow tests without changing
the rest of the 1X2 market-movement surface. The current local smoke slice is
`configs/recommendations/historical_slices/local_epl_2024_2025_market_features_with_asian_handicap_sample_v1.json`;
all `24` sampled fixtures include two Asian-handicap movements and pass feature
completeness.

Asian-handicap prematch-feature shadow comparison:

`nutmeg-accuracy-prematch-feature-shadow-comparison` compares two historical
Poisson prematch-feature runs with the same walk-forward options, typically
1X2-only market movement versus 1X2 plus Asian-handicap movement. It reports
hit-rate, Brier, log-loss, average actual probability, expected calibration
error deltas, candidate Asian-handicap feature coverage, and a strict
non-regression gate. It is evidence-only and does not change the default
recommendation profile.

The current local smoke report is
`configs/recommendations/historical_reports/local_epl_2024_2025_market_feature_asian_handicap_shadow_comparison_v1.json`.
On the 24-fixture EPL sample, both runs had `3` validation fixtures and
candidate Asian-handicap feature coverage was `1.0`. The 1X2 plus
Asian-handicap run did not pass strict non-regression on this tiny smoke:
hit-rate delta was `0.0`, Brier delta was `+0.005283956301081472`, log-loss
delta was `+0.00840695356008403`, and ECE delta was
`+0.0032663163227492076`. This is a caution signal, not a production removal
decision.

The expanded multi-season candidate suite is
`configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_with_asian_handicap_suite_v1.json`.
It mirrors the existing 25-slice top-five-league market-feature suite and
contains `600` fixtures with `candidate_asian_handicap_feature_coverage=1.0`.
All 25 generated slices and all 25 completeness reports passed generation.

The expanded shadow comparison report is
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_asian_handicap_shadow_comparison_v1.json`
with `report_key=prematch_feature_shadow_comparison:5debd5c8498f7e7c`.
It also does not pass strict non-regression: both runs have `236` validation
fixtures, but adding raw Asian-handicap movement changes hit-rate delta to
`-0.004237288135593209`, Brier delta to `+0.002230011584329672`, log-loss
delta to `+0.004054802489492859`, and average actual probability delta to
`-0.0008742726857767225`. ECE improves by `-0.006689034404863986`, but that is
not enough to offset the hit/Brier/log-loss regressions.

The Poisson walk-forward report key now includes per-slice content digests, so
two suites with the same slice ids but different feature surfaces no longer
collide. The expanded comparison now records distinct baseline and candidate
Poisson keys:
`historical_poisson_walk_forward:1e38bfe855fde877` and
`historical_poisson_walk_forward:8161690615bcd701`.

Current decision: no production/default recommendation change. Raw
Asian-handicap movement is useful coverage evidence, but not a direct
accuracy-improving feature at the current weight.

Asian-handicap role search:

`nutmeg-accuracy-prematch-feature-asian-handicap-role-search` runs a
shadow-only grid over the Asian-handicap movement weight and minimum movement
delta. It compares every candidate against the same 1X2-only baseline and marks
zero-weight candidates as `control_passed`, not as real Asian-handicap
admission evidence.

The first multi-season role-search report is
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_asian_handicap_role_search_v1.json`
with
`report_key=prematch_feature_asian_handicap_role_search:1f291776ee0e0bdb`.
It evaluated `24` candidates. `accepted_nonzero_candidate_count=0`,
`control_passed_candidate_count=4`, and `watchlist_candidate_count=8`. The best
effective nonzero candidate used `asian_handicap_movement_weight=0.05` and
`min_asian_handicap_probability_delta=0.04`, but it still failed strict
non-regression because Brier and log-loss regressed despite preserving hit rate
and improving ECE.

The line-aware follow-up report is
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_asian_handicap_line_aware_role_search_v1.json`
with
`report_key=prematch_feature_asian_handicap_role_search:f95269857fb57f69`.
It evaluated `64` candidates and found
`accepted_nonzero_candidate_count=10`, `control_passed_candidate_count=4`, and
`watchlist_candidate_count=46`. The best accepted shadow candidate used
`asian_handicap_movement_weight=0.05`,
`min_asian_handicap_probability_delta=0.04`,
`asian_handicap_line_movement_weight=0.05`, and
`min_asian_handicap_line_delta=0.0`. It preserved hit rate
(`hit_rate_delta=0.0`) while improving Brier
(`-0.00002420366876010327`), log loss
(`-0.000005631039583953168`), and ECE
(`-0.001345330087407469`). Current decision: this is the first usable
Asian-handicap model-quality shadow signal, but it remains non-production until
it passes a follow-up independent/rolling admission gate and default-path
isolation.

Asian-handicap role admission:

`nutmeg-accuracy-prematch-feature-asian-handicap-role-admission` wraps one or
more role-search reports in an admission decision. It requires an accepted
nonzero candidate, enough validation samples, no hit/Brier/log-loss/ECE
regression, explicit line-movement contribution, and no default/production/public
path changes. The single overall-suite admission report is
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_asian_handicap_line_aware_role_admission_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_role_admission:a03c68b2815fcf7e`.
It is `accepted` as model-quality shadow evidence:
`candidate_model_allowed=true`, `default_path_isolated=true`,
`production_recommendation_changed=false`, and `public_response_changed=false`.

The stricter competition-fold admission report is
`configs/recommendations/historical_reports/football_data_co_uk_market_feature_competition_fold_asian_handicap_line_aware_role_admission_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_role_admission:f5466b63151eb273`.
It is `shadow_only`, not activation-ready: `source_report_count=6`,
`accepted_report_count=1`, and `failed_report_count=5`. The overall fold passes,
but the single-league folds are not stable enough: Bundesliga improves Brier and
log loss but has a small ECE regression; EPL, La Liga, and Ligue 1 regress
Brier/log loss; Serie A improves Brier/log loss but lacks an ECE fold delta under
the current calibration-bucket minimum. Current decision: line-aware
Asian-handicap movement is a promising model-quality signal, but it stays
shadow-only until league-level or segmented admission can pass.

Asian-handicap segmented admission:

`nutmeg-accuracy-prematch-feature-asian-handicap-segmented-admission` evaluates
line-aware Asian-handicap role-search evidence per segment instead of trying to
promote the global role. Accepted segments may enter an internal candidate lane,
while unstable segments explicitly stay on the baseline fallback path. The gate
requires local no-harm for hit rate, Brier score, log loss, calibration, enough
validation samples, explicit line-movement contribution, and default/production/
public path isolation.

The current five-league segmented report is
`configs/recommendations/historical_reports/football_data_co_uk_competition_segmented_asian_handicap_line_aware_admission_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_segmented_admission:46ae03c879690cdf`.
It is `shadow_only`: `accepted_segment_count=0`, `shadow_segment_count=1`, and
`fallback_segment_count=4`. Serie A remains research-only because its local
candidate improves Brier/log loss but lacks calibration delta; EPL, La Liga,
Bundesliga, and Ligue 1 stay on baseline fallback because at least one strict
local no-harm requirement fails. The report records
`default_path_isolated=true`, `production_recommendation_changed=false`, and
`public_response_changed=false`.

Asian-handicap segment refinement:

`nutmeg-accuracy-prematch-feature-asian-handicap-segment-refinement` turns the
segmented admission failure reasons into bounded next experiments without
activating the signal. It separates calibration-sample issues, calibration-scope
issues, and true Brier/log-loss regressions so the next work does not become
another blind parameter-tuning loop.

The current refinement report is
`configs/recommendations/historical_reports/football_data_co_uk_competition_segmented_asian_handicap_line_aware_refinement_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_segment_refinement:c06d871dd3e2e910`.
It is `refinement_ready`, not activation-ready. The top next segment is Serie A
with `recommended_action=calibration_sample_expansion`; Bundesliga is
`calibration_scope_refinement`; EPL, La Liga, and Ligue 1 require
`line_transform_enrichment` because their local Brier/log-loss checks regress.
The report again records no default, production, or public response change.

Asian-handicap calibration sample expansion:

`nutmeg-accuracy-prematch-feature-asian-handicap-calibration-sample-expansion`
compares the strict Serie A line-aware role-search report against a relaxed
calibration-bucket replay. It is a measurement-only wrapper: it can prove that
ECE is now measurable on the local segment, but it cannot activate the signal
or change public/default recommendation paths.

The current Serie A calibration sample expansion report is
`configs/recommendations/historical_reports/football_data_co_uk_serie_a_asian_handicap_line_aware_calibration_sample_expansion_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_calibration_sample_expansion:5456e4510ea17452`.
It is `measurement_ready`, with `activation_allowed=false`,
`default_path_isolated=true`, `production_recommendation_changed=false`, and
`public_response_changed=false`. The strict run used
`min_bucket_sample_size=30` and had no measurable ECE delta; the relaxed replay
uses `min_bucket_sample_size=10`, keeps the same candidate parameters, validates
on `42` samples, and records hit-rate delta `0.0`, Brier delta
`-4.39332631166911e-05`, log-loss delta `-0.00014846667197510044`, and ECE
delta `-6.4529613248418e-05`. This removes the Serie A calibration-measurement
blocker, but it remains shadow evidence until the next segmented admission gate
proves activation safety.

Asian-handicap segmented replay with calibration evidence:

`nutmeg-accuracy-prematch-feature-asian-handicap-segmented-admission` can now
consume `measurement_ready` calibration sample expansion evidence. The evidence
is only allowed to fill a missing ECE delta for the matching strict
role-search candidate; it must keep `activation_allowed=false`, preserve
default/production/public path isolation, and pass the same hit-rate, Brier,
log-loss, and calibration no-harm checks.

The current replay report is
`configs/recommendations/historical_reports/football_data_co_uk_competition_segmented_asian_handicap_line_aware_calibration_sample_expansion_admission_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_segmented_admission:ee4803cba978db18`.
It remains `shadow_only`: Serie A now becomes an accepted local segment with
`calibration_sample_expansion_applied_count=1`, but accepted validation coverage
is only `42` against the `100` sample threshold. The accepted segment preserves
hit rate and improves Brier, log loss, and ECE, while EPL, La Liga, Bundesliga,
and Ligue 1 remain baseline fallback. No default, production, or public response
path changed.

Asian-handicap Bundesliga calibration-scope refinement:

`nutmeg-accuracy-prematch-feature-asian-handicap-calibration-scope-refinement`
compares fixed-parameter line-aware Asian-handicap replays under alternate
calibration scopes. It keeps the same candidate weights and only changes ECE
measurement scope, so it can answer whether a segment is blocked by calibration
bucket geometry rather than by the underlying signal.

The current Bundesliga report is
`configs/recommendations/historical_reports/football_data_co_uk_bundesliga_asian_handicap_line_aware_calibration_scope_refinement_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_calibration_scope_refinement:959f918be943199e`.
It remains `shadow_only`. The source strict run has ECE delta
`2.7318296421746657e-05`; the best replay, `min_bucket_sample_size=20`,
improves the ECE regression to `1.3160470493496501e-05` while preserving hit
rate and improving Brier/log loss, but it still does not clear the `<= 0`
calibration gate. The `min_bucket_sample_size=10` replay worsens ECE to
`0.011934142250085586`, and the `bucket_size=0.20` replay remains positive at
`3.492887468811712e-05`. This means Bundesliga should not be admitted through
calibration-scope adjustment alone; the next bounded work is feature transform
enrichment, still with no default, production, or public response change.

Asian-handicap line-transform enrichment:

`historical_poisson_walk_forward` now keeps the existing `linear`
Asian-handicap line movement transform as the default and adds two shadow-only
candidate transforms: `signed_sqrt` and `quarter_step`. The role-search evidence
chain carries the selected transform through candidate summaries and segmented
admission decisions, so future replays can tell which transform actually moved a
segment.

The top-five transform report is
`configs/recommendations/historical_reports/football_data_co_uk_top5_asian_handicap_line_transform_enrichment_role_search_v1.json`
with `report_key=prematch_feature_asian_handicap_role_search:a1b284bf8fe2ff97`.
It evaluates 24 candidates and accepts 4 nonzero candidates. The best accepted
candidate uses `signed_sqrt` with `asian_handicap_line_movement_weight=0.02`,
preserves hit rate, and improves Brier by `-0.00003710188760208677`, log loss by
`-0.000018118521427190615`, and ECE by `-0.0013521715299190593`.

The segmented replay is
`configs/recommendations/historical_reports/football_data_co_uk_competition_segmented_asian_handicap_line_transform_enrichment_admission_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_segmented_admission:a7afdc45749fe917`.
It remains `shadow_only`: EPL and the previously measured Serie A segment are
accepted with 91 combined validation samples, below the 100-sample threshold.
Ligue 1 is `shadow_only` because ECE is still missing; La Liga and Bundesliga
stay on baseline fallback. No default, production, or public response path
changed.

Asian-handicap Ligue 1 calibration measurement:

`configs/recommendations/historical_reports/football_data_co_uk_ligue_1_asian_handicap_line_transform_calibration_measurement_v1.json`
is a follow-up measurement report for the accepted Ligue 1 line-transform
candidate. It keeps the same candidate parameters, including `quarter_step`,
and changes only the calibration measurement scope to
`min_bucket_sample_size=20` and `bucket_size=0.20`. The report is
`measurement_ready` with
`report_key=historical_prematch_feature_asian_handicap_calibration_sample_expansion:7094db2e5a0f0330`.
It preserves hit rate and improves Brier by `-0.00140031241799643`, log loss by
`-0.0015915107150870078`, and ECE by `-0.0004608749501475162`.

The follow-up segmented replay is
`configs/recommendations/historical_reports/football_data_co_uk_competition_segmented_asian_handicap_line_transform_enrichment_calibration_measurement_admission_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_segmented_admission:73333d16c556ebb2`.
It is `accepted` as internal model-quality evidence: EPL, Ligue 1, and Serie A
are accepted with 138 accepted validation samples. Accepted-segment deltas
preserve hit rate and improve Brier by `-0.0010761099689132964`, log loss by
`-0.0014682563369637206`, ECE by `-0.0002984001368970529`, and actual-outcome
probability by `+0.0002354975969207306`. La Liga and Bundesliga stay on
baseline fallback. This does not change default, production, or public response
paths.

Asian-handicap segmented governance review:

`nutmeg-accuracy-prematch-feature-asian-handicap-segmented-governance-review`
consumes accepted segmented Asian-handicap model-quality admission evidence and
produces an internal-only staged profile. It explicitly requires the source
admission to be accepted, the default path to stay isolated, production and
public response paths to remain unchanged, enough accepted validation coverage,
no aggregate hit/Brier/log-loss/ECE harm, and bounded baseline fallback
segments.

The current governance report is
`configs/recommendations/historical_reports/football_data_co_uk_competition_segmented_asian_handicap_line_transform_enrichment_governance_review_v1.json`
with
`report_key=historical_prematch_feature_asian_handicap_segmented_governance_review:261deacce90b7740`.
It is `governance_ready`: 3 accepted segments, 2 baseline fallback segments, 0
shadow or rejected segments, 138 accepted validation samples, and 2 calibration
measurement applications. Its staged profile is `dry_run_only` and
`internal_review_only`; production recommendation allowance is false, and no
default, production, or public response path changed.

The benchmark quality gate and cycle runner now expose this evidence as
`asian_handicap_segmented_model_quality_*` summary fields. The reusable
`v3_2_core_accuracy_governance_v1` cycle preset attaches the governance report
and requires it to remain ready, internal-only, default-path isolated, and
production/public unchanged. It also requires at least 3 accepted segments, at
most 2 baseline fallback segments, 0 shadow/rejected segments, 100 accepted
validation samples, 2 calibration measurements, and no aggregate hit/Brier/log
loss/ECE/actual-probability harm. This makes the Asian-handicap signal part of
the recurring quality guardrail without activating it.

Derived handicap and correct-score historical candidate suite:

`nutmeg-recommendation-historical-derived-market-candidates` can now run against
a historical suite manifest, not only a single slice. The current expanded
A-league rolling-window derived suite is
`configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_derived_markets_suite_v1.json`,
with derived slices written under
`configs/recommendations/historical_slices/derived_markets/football_data_co_uk_expanded_a_leagues_rolling_windows_v1`.
The build report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_derived_market_candidates_v1.json`.
It covers `210` rolling slices and `2520` fixtures, expanding `7560` original
1X2 predictions into `50400` total predictions by adding `15120`
`cn_handicap_1x2`, `15120` `european_handicap_1x2`, and `12600`
`correct_score` shadow predictions. These odds are fair model-derived replay
odds from a deterministic score-grid heuristic, not paid provider historical
market odds.

The matching coverage audit is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_derived_market_coverage_audit_v1.json`.
It marks the derived suite ready for dynamic mixed candidate coverage, handicap
candidate coverage, and correct-score candidate coverage, with all `2520`
fixtures containing handicap and correct-score candidates. The remaining
coverage warning is `context_signal_not_ready`, meaning lineup/news/rest style
context is still incomplete for this suite.

The current quality-gate smoke is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_derived_market_suite_gate_smoke_v1.json`.
It replayed `1x1` through `8x1`, `single` and `multiple`, with allowed markets
`1x2`, `cn_handicap_1x2`, `european_handicap_1x2`, and `correct_score`.
The smoke passed with `candidate_final_hit_rate=0.819047619047619`,
`candidate_roi=0.006733723401772428`, `final_hit_rate_delta=0.014285714285714235`,
`roi_delta=0.011323874545978725`, and no failed checks. Important limitation:
the final answers were all `cn_handicap_1x2` in this smoke
(`candidate_dynamic_mixed_final_answer_count=0`), so this proves the wider
candidate path and quality gate work, but it does not yet prove the desired
true mixed-market final answer behavior.

Final-answer market concentration audit:

`nutmeg-recommendation-final-answer-market-concentration-audit` replays a
historical slice set or suite manifest and checks whether the final answers are
actually mixed-market or merely concentrated in one market silo. The audit
separates broad market appearances from single-market-exclusive final answers,
then reports the dominant single-market rate, HHI concentration, true
mixed-market answer count/rate, correct-score usage, multiple-choice usage, and
the usual final-answer quality deltas. It is a governance and diagnosis tool;
it does not force user-facing recommendations to show internal strategy labels.

The current expanded A-league derived-market audit report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_final_answer_market_concentration_audit_v1.json`.
It intentionally fails the dynamic-mix admission thresholds while passing the
quality non-regression checks. The report shows `final_answer_count=210`,
`market_type_count=1`, `market_type_counts={cn_handicap_1x2: 210}`,
`dominant_single_market_rate=1.0`, `market_concentration_hhi=1.0`,
`dynamic_mixed_final_answer_count=0`, and
`correct_score_final_answer_count=0`. At the same time, quality remains
improved versus baseline: `final_hit_rate_delta=0.014285714285714235`,
`roi_delta=0.011323874545978725`, `profit_loss_delta=4.756027309311063`, and
Brier/log-loss/ECE deltas all improve. This confirms the next optimization
problem is market concentration, not generic replay failure.

Dynamic-mix final-answer lane:

The historical backtest now has an optional
`dynamic_mix_final_answer_lane` shadow lane. It is intentionally off by
default. When enabled, it keeps the normal compressed candidate path intact,
then builds additional 2x1+ single-parlay final-answer candidates from the
pre-compression candidate pool by replacing one selected leg with another
market on the same fixture or with an alternate fixture that introduces a
second market type. The final-answer ranker can give this lane a small
configured boost, but quality guards can block it when hit probability or
expected ROI falls behind the best non-lane answer. This keeps mixed-market
exploration auditable rather than hard-forced.

The current full derived-suite audit report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_audit_v1.json`.
It replayed `210` derived rolling-window slices with `2x1`, `3x1`, and `4x1`
single-parlay candidates, allowed `1x2`, `cn_handicap_1x2`,
`european_handicap_1x2`, and `correct_score`, and enabled the dynamic-mix lane
with a `0.05` score boost plus strict non-negative expected ROI delta versus
the best non-lane answer. The audit passed with `suite_status=improved`,
`candidate_final_hit_rate=0.7333333333333333`,
`candidate_roi=0.02030518640520881`, `dynamic_mixed_final_answer_count=208`,
`dynamic_mixed_final_answer_rate=0.9904761904761905`,
`candidate_completed_dynamic_mix_final_answer_lane_count=630`,
`candidate_final_answer_dynamic_mix_final_answer_lane_count=208`, and
`candidate_dynamic_mix_final_answer_lane_quality_guard_blocked_option_count=422`.
The selected mixed answers currently combine `cn_handicap_1x2` and
`european_handicap_1x2`; `correct_score` and multiple-choice legs remain
unadmitted until they can clear the same quality evidence.

The wider single-parlay dynamic-mix audit is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_8x1_single_audit_v1.json`.
It replays the same `210` derived slices across `2x1` through `8x1` single
parlays, keeps the dynamic-mix lane solver disabled for bounded runtime, and
passes with `suite_status=improved`, `candidate_final_hit_rate=0.7380952380952381`,
`candidate_roi=0.027776574189284673`,
`dynamic_mixed_final_answer_count=205`, and
`candidate_final_answer_dynamic_mix_final_answer_lane_count=205`.

Multiple-mode support is now wired into the dynamic-mix lane, but full-suite
`multiple` replay is not yet a daily gate because the candidate expansion and
budget pruning cost grows quickly. The bounded smoke report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_smoke_v1.json`.
It uses `--slice-limit 5`, `2x1` through `4x1`, and `multiple` mode. The smoke
passed with `dynamic_mixed_final_answer_count=3` and
`multiple_choice_final_answer_count=2`, but its negative ROI confirms that
multiple-mode admission needs stronger pre-filtering and no-harm gates before
promotion beyond smoke.

The first bounded multiple-mode audit beyond smoke is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_30slice_v1.json`.
It uses the same derived rolling-window suite with `--slice-limit 30`, `2x1`
through `4x1`, `multiple` mode, and the dynamic-mix lane solver search left
off. This report passed with `suite_status=improved`,
`final_answer_count=30`, `dynamic_mixed_final_answer_count=29`,
`dynamic_mixed_final_answer_rate=0.9666666666666667`,
`multiple_choice_final_answer_count=1`,
`candidate_final_hit_rate=0.8333333333333334`,
`candidate_roi=0.33517379939700687`, and
`candidate_profit_loss=22.121470760202453`. The quality deltas were positive:
`final_hit_rate_delta=0.06666666666666665`,
`roi_delta=0.22857536867265948`,
`profit_loss_delta=15.72556491674161`, and Brier/log-loss/calibration deltas all
improved. The implementation fix behind this run was to make the multiple
optimizer respect `enable_solver_search=False` for both the integer solver and
beam search; this keeps shadow multiple audits bounded instead of accidentally
running the heavy global search path.

Current decision: multiple dynamic-mix has graduated from 5-slice smoke to a
30-slice bounded quality gate, but it is not yet a full 210-slice production
gate. The next promotion step is a pass-type segmented 210-slice replay, with
runtime and no-harm thresholds recorded separately for `2x1`, `3x1`, and
`4x1`, before extending multiple mode to `5x1-8x1`.

The first pass-type segmented 210-slice multiple gate produced three reports:
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_multiple_210slice_v1.json`,
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_3x1_multiple_210slice_v1.json`,
and
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_4x1_multiple_210slice_v1.json`.
The segment summary is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_segment_gate_v1.json`.
It promotes only `3x1`: `final_hit_rate_delta=0.023809523809523836`,
`roi_delta=0.0020807466560052792`, `profit_loss_delta=8.34874518452797`,
`dynamic_mixed_final_answer_rate=0.8476190476190476`, and all probability
quality deltas improved. `2x1` and `4x1` are blocked by the ROI/P&L no-harm
gate even though their hit rate and calibration improved:
`2x1` has `roi_delta=-0.011700270724697637` and
`profit_loss_delta=-6.151133077070941`; `4x1` has
`roi_delta=-0.4794364554271857` and
`profit_loss_delta=-127.0786315629419`.

`nutmeg-recommendation-final-answer-market-concentration-segment-gate` now
summarizes segmented audit reports into machine-readable promote/block
decisions. Current decision: do not promote all multiple dynamic-mix segments
together. Admit `3x1` as the first evidence-backed segment, and add ROI/P&L
protection before reconsidering `2x1`, `4x1`, or `5x1-8x1` multiple gates.

The market-concentration audit can now consume that segment gate directly via
`--dynamic-mix-final-answer-lane-segment-gate-report`. The audit converts the
gate into `dynamic_mix_final_answer_lane_admitted_pass_types` and
`dynamic_mix_final_answer_lane_blocked_pass_types`, then only creates
dynamic-mix lane options for the admitted pass types. This is the first
ROI/P&L-protected admission layer for multiple dynamic-mix: blocked segments
may still compete as ordinary multiple candidates, but they are not boosted by
the dynamic-mix lane.

The bounded admission smoke is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_segment_admitted_30slice_v1.json`.
It requested `2x1,3x1,4x1` multiple, consumed the segment gate above, and
therefore ran the dynamic-mix lane with
`dynamic_mix_final_answer_lane_effective_pass_types=["3x1"]`,
`admitted_pass_types=["3x1"]`, and `blocked_pass_types=["2x1","4x1"]`.
The report passed with `suite_status=improved`, `slice_count=30`,
`dynamic_mixed_final_answer_count=17`,
`dynamic_mixed_final_answer_rate=0.5666666666666667`,
`candidate_final_hit_rate=0.7666666666666667`,
`candidate_roi=0.09200844928526968`,
`candidate_profit_loss=8.832811131385888`,
`final_hit_rate_delta=0.06666666666666676`,
`roi_delta=0.10263647053950446`,
`profit_loss_delta=9.725564916741611`, and improved
Brier/log-loss/calibration deltas.

The attempted full combined `2x1,3x1,4x1` 210-slice admission replay was
stopped because it remained a high-CPU run after several minutes; the already
completed per-pass-type 210-slice segment reports remain the authoritative
full-sample admission evidence. Current next step: add cached/batched combined
gate execution before making combined 210-slice replay part of the regular
quality cycle.

The lightweight combined admission gate is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_segment_admission_gate_v1.json`.
It reads the 210-slice pass-type segment gate plus the bounded 30-slice
admission smoke, then emits a reusable quality-gate artifact without rerunning
the heavy combined replay. The gate passed with
`report_key=historical_final_answer_market_concentration_admission_gate:c216c5a021eac85b`,
`requested_pass_types=["2x1","3x1","4x1"]`,
`effective_pass_types=["3x1"]`, `admitted_pass_types=["3x1"]`,
`blocked_pass_types=["2x1","4x1"]`, and no failed checks. This keeps the
dynamic-mix multiple lane on the evidence-backed `3x1` segment while preserving
the `2x1/4x1` ROI/P&L block.

The first blocked-segment recovery probes show that `2x1` and `4x1` fail for
different reasons. Raising the dynamic-mix expected-ROI guard for `2x1` to
`0.02` blocked all mixed answers and still failed ROI/P&L. Requiring a `0.03`
minimum marginal quality gain reduced multiple-choice answers but also failed
ROI/P&L. The successful recovery probe is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_multiple_max_outcomes_1_210slice_v1.json`.
It keeps `2x1` in `multiple` mode but sets `max_outcomes_per_fixture=1`,
so it tests dynamic mixed-market 2x1 without复式 expansion. That report passed
on `210` slices with `dynamic_mixed_final_answer_count=205`,
`dynamic_mixed_final_answer_rate=0.9761904761904762`,
`candidate_final_hit_rate=0.7380952380952381`,
`candidate_roi=0.027776574189284673`,
`candidate_profit_loss=11.666161159499563`,
`final_hit_rate_delta=0.009523809523809601`,
`roi_delta=0.010664937715570106`, and
`profit_loss_delta=4.479273840539445`.

This does not promote default `2x1` multiple-choice expansion. It means `2x1`
is recoverable only under the explicit `max_outcomes_per_fixture=1` constraint.
The matching `4x1` constrained probe,
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_4x1_multiple_max_outcomes_1_210slice_v1.json`,
still failed with `final_hit_rate_delta=-0.01428571428571429`,
`roi_delta=-0.05341060724348718`, and
`profit_loss_delta=-22.432455042264618`, so `4x1` remains blocked.

The constraint-aware segment gate is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_constraint_segment_gate_v1.json`.
It records pass-type decisions together with explicit constraint profiles,
because pass-type-only admission is now ambiguous for `2x1`: default `2x1`
multiple remains blocked, while `2x1` with `max_outcomes_per_fixture=1` is
promoted. The segment gate passed with
`report_key=historical_final_answer_market_concentration_segment_gate:39cdc47e95276ed6`,
`promoted_constraint_profiles=["2x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0","3x1:multiple:max_outcomes_per_fixture=2|min_marginal_quality_gain=0"]`,
and
`blocked_constraint_profiles=["2x1:multiple:max_outcomes_per_fixture=2|min_marginal_quality_gain=0","4x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0"]`.

The matching constraint-aware admission gate is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_constraint_admission_gate_v1.json`.
It was run with `--constraint-profile-admission` and passed with
`report_key=historical_final_answer_market_concentration_admission_gate:80055bf3203a332b`,
`effective_pass_types=["2x1","3x1"]`, and the exact effective profiles
`2x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0` plus
`3x1:multiple:max_outcomes_per_fixture=2|min_marginal_quality_gain=0`.
This keeps default `2x1` multiple-choice expansion blocked, admits only the
single-outcome `2x1` constraint profile, and continues blocking `4x1`.

The historical dynamic-mix runtime can now consume that admission artifact via
`--dynamic-mix-final-answer-lane-admission-gate-report`. When effective
constraint profiles are present, the lane is generated from those exact
profiles instead of pass-type-only admission. The runtime smoke artifact is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_constraint_profile_runtime_smoke_5slice_v1.json`.
It passed on `5` slices with
`dynamic_mix_final_answer_lane_effective_pass_types=["2x1","3x1"]`,
effective profiles
`2x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0` and
`3x1:multiple:max_outcomes_per_fixture=2|min_marginal_quality_gain=0`,
`candidate_completed_dynamic_mix_final_answer_lane_count=10`,
`candidate_final_answer_dynamic_mix_final_answer_lane_count=5`,
`dynamic_mixed_final_answer_count=5`, and no failed checks. A 30-slice combined
profile-runtime smoke was intentionally stopped after exceeding the local smoke
budget; larger-window profile admission still needs cached/batched execution
before becoming routine cycle work.

The persisted benchmark quality gate and benchmark cycle can now consume that
runtime smoke as a lightweight evidence artifact without rerunning the combined
historical backtest. Use
`--final-answer-market-concentration-audit-report-path` with
`--require-final-answer-market-concentration-audit` on
`nutmeg-recommendation-benchmark-gate`, or the matching
`--gate-final-answer-market-concentration-audit-report-path` /
`--gate-require-final-answer-market-concentration-audit` flags on
`nutmeg-recommendation-benchmark-cycle`. The gate summary exposes
`final_answer_market_concentration_dynamic_mixed_final_answer_count`,
`final_answer_market_concentration_effective_pass_types`,
`final_answer_market_concentration_effective_constraint_profiles`, failed-check
count, and warning count. This keeps the profile-level admission evidence in the
same periodic no-regression surface as the benchmark history while avoiding the
known 30-slice combined replay cost.

Budget stability gate:

`nutmeg-recommendation-benchmark-gate` can now require budget-stability evidence
with `--budget-stability-audit-report-path` and
`--require-budget-stability-audit`. The probability-preserving governance cycle
preset binds the 240-slice budget audit by default and checks that the
signature-change rate, harmful changes, hit delta, ROI delta, and warnings stay
inside configured bounds. The current consumption smoke report is
`configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_multiple_tie_breaker_benchmark_gate_smoke_v1.json`
and passed with no failed checks.

Core accuracy governance preset:

`nutmeg-recommendation-benchmark-cycle` now has a composite preset:
`v3_2_core_accuracy_governance_v1`. It combines the probability-preserving
13-change governance chain, successor effective-final-only historical suite
gate, budget stability audit, constraint-aware dynamic-mix runtime smoke, and
the ready market-movement sample-expansion / segment replay-batch gate into one
quality surface.

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --cycle-preset v3_2_core_accuracy_governance_v1
```

The preset is still dry-run/staged by default. It requires the market-movement
sample expansion to be promotion-ready, the segment replay batch to be
`segment_replay_batch_ready`, the strategy governance artifacts to be ready, the
default path to remain isolated, budget-stability deltas to stay non-negative,
and the constraint-aware dynamic-mix smoke to keep its admitted `2x1` /
`3x1` profiles. This is the recommended quality gate for the next core
accuracy slice: new candidate work should pass this combined surface before any
activation discussion.

The first deterministic seeded smoke is:
`configs/recommendations/historical_reports/local_seed_v3_2_core_accuracy_governance_cycle_smoke_v1.json`.
It was run with `--run-at-utc 2026-05-12T00:00:00Z`,
`--commit-core-replay-seed`, and `--save-report`. The cycle passed with
`27` completed scenarios, `9` seeded replay runs, `core_replay_ready_ratio=1.0`,
`final_hit_sample_size=27`, `final_hit_coverage_ratio=1.0`, `240` historical
suite slices, successor effective-final-only evidence ready, budget stability
at `signature_change_rate=0.0` and `harmful_change_count=0`, admitted
dynamic-mix profiles for `2x1` and `3x1`, `sample_expansion_ready`,
`segment_replay_batch_ready`, strategy governance ready, staged activation
ready, default-path isolation clean, `gate_failed_checks=[]`, and `warnings=[]`.

Probability-preserving quality-score replacement candidate:

The short-odds replacement shadow engine now has a
`probability_preserving_quality_score` ranking rule. It first keeps candidates
inside the same model-top expected-hit-probability bucket, then ranks by
pre-match replacement quality score, candidate score, model edge, and price. The
same rule is supported by the runtime shadow replay engine so offline and
runtime dry-run selection stay aligned. It remains an internal shadow/runtime
review path only.

The first quality-score grid report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_grid_v1.json`
with `report_key=historical_replacement_probability_preserving_grid:389aef981229786d`.
It evaluates `1,000` variants, finds `400` accepted candidates, and contains
`200` accepted 13-change candidates. The best grid candidate changes `12`
final answers, improves final-answer hits by `+4`, improves P/L by `+15.74`,
keeps harm at `0`, and keeps average hit-probability delta at
`-0.01048666873544686`.

The selected 13-change quality-score candidate is
`replacement_probability_preserving_candidate:ff587ac5deddab76`. Its
cross-surface replay report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_cross_surface_replay_v1.json`
with `status=cross_surface_passed`, `active_surface_count=8`,
`failed_surface_count=0`, `all_audit_changed_final_answer_count=13`, and
`non_source_changed_final_answer_count=9`. Its fold-admission report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_admission_v1.json`
with `status=shadow_admission_passed`, `5` active competition folds, `5`
active season folds, `13` active rolling folds, and `0` failed folds.

The runtime dry run is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_runtime_dry_run_v1.json`
with
`report_key=historical_replacement_probability_preserving_runtime_dry_run:4aebd5d1dc4d4608`.
It passes as `runtime_dry_run_passed`: `99` final answers, `14` changed final
answers, final-answer hit delta `+4`, P/L delta `+15.96`, ROI delta
`+0.04092307692307692`, harm `0`, final-hit harm `0`, P/L harm `0`, and
average hit-probability delta `-0.012219819458087085`. The paired promotion
review report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_promotion_review_v1.json`
with
`report_key=historical_replacement_probability_preserving_promotion_review:2bc6c3a8d67f6bd5`
and `status=promotion_review_ready`. It still has
`production_recommendation_allowed=false`,
`production_recommendation_changed=false`, and `public_response_changed=false`.

The composite V3.2 governance cycle was rerun after adding this candidate:
`configs/recommendations/historical_reports/local_seed_v3_2_core_accuracy_governance_after_quality_score_candidate_v1.json`.
It passed with `27` completed benchmark scenarios, `core_replay_ready_ratio=1.0`,
`final_hit_sample_size=27`, market-movement segment replay ready, strategy
governance ready, staged activation ready, default-path isolation clean, no
gate failed checks, and no warnings.

The quality-score branch now also has its own strategy-governance evidence:
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_strategy_promotion_gate_v1.json`
is `ready` with 99 final answers, 14 changed final answers, hit delta `+4`,
P/L delta `+15.96`, ROI delta `+0.04092307692307692`, and harm `0`.
The paired staged activation smoke is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_staged_activation_smoke_v1.json`
with `status=staged_activation_ready`, `rule_count=1`,
`selected_rule_count=1`, no production/public response change, and no default
profile write. The default-path isolation report is
`configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_default_path_isolation_v1.json`
with `status=isolated`, `default_adapter_status=disabled`,
`default_adapter_selection_changed=false`, and explicit internal opt-in still
applying the staged rule.

Reusable governance switches:

```bash
uv run nutmeg-recommendation-benchmark-gate \
  --recommendation-strategy-governance-preset probability_preserving_quality_score_v1

uv run nutmeg-recommendation-benchmark-cycle \
  --cycle-preset probability_preserving_quality_score_governance_v1
```

The seeded cycle smoke is
`configs/recommendations/historical_reports/local_seed_probability_preserving_quality_score_benchmark_cycle_governance_preset_smoke_v1.json`.
It was run with `--run-at-utc 2026-05-12T00:00:00Z`,
`--commit-core-replay-seed`, and `--save-report`; it passed with `27`
completed scenarios, `9` seeded replay runs, `core_replay_ready_ratio=1.0`,
`final_hit_sample_size=27`, strategy governance ready, staged activation ready,
default adapter disabled, default-path isolation clean, no gate failed checks,
and no warnings. This remains internal/staged only and does not change the
default recommendation profile, production path, or public response path.

## V3.2 Scientific Execution Plan

The fixed V3.2 plan is documented in
`Nutmeg_docs_v2/12_Nutmeg_V3_2_Scientific_Execution_Plan.md`. Its first rule is
that development must stop optimizing isolated `2x1` experiments and return to
the product objective: one budget-aware best recommendation across single,
multiple, `2x1` through `8x1`, `1X2`, handicap `1X2`, and correct-score
candidates.

The locked baseline is
`configs/recommendations/baselines/baseline_v3_1_locked_2026_05_21.json`. Before
changing the default recommendation path, run:

```bash
uv run nutmeg-recommendation-scientific-baseline-gate \
  --output-path configs/recommendations/historical_reports/baseline_v3_1_locked_scientific_gate_v1.json
```

This gate consumes existing evidence reports only. It is intentionally light:
it verifies the known-good V3.1 baseline, budget stability evidence, derived
market suite evidence, and constrained dynamic-mix smoke without rerunning heavy
historical backtests.

Stage 2 has started with an internal `unified_candidate_pool` summary in the
global planner. It records every generated final-answer family and confirms that
`2x1` is just one candidate family, so future work can compare single, multiple,
`2x1` through `8x1`, handicap, and correct-score answers through the same
arbitration surface.

The benchmark runner now aggregates this into
`unified_candidate_pool_*` metrics, and the benchmark quality gate / cycle can
enforce them with options such as `--require-unified-candidate-pool`,
`--min-unified-candidate-pool-unique-family-count`, and
`--max-unified-candidate-pool-selected-2x1-rate`.

The V3.2 guard preset fixes those thresholds behind one command-line switch:

```bash
uv run nutmeg-recommendation-benchmark-cycle \
  --cycle-preset v3_2_unified_candidate_pool_guard_v1
```

The preset runs a dry-run, persisted benchmark over `1x1` plus `2x1` through
`8x1`, disables replay-heavy side checks, and requires the final-answer surface
to contain more than one candidate family with no selected-family mismatch.
The direct gate equivalent is
`--unified-candidate-pool-guard-preset v3_2_unified_candidate_pool_guard_v1`.

Stage 3 has started with internal multiple-value admission. Every selected
extra outcome inside a multiple recommendation is now scored by removing that
outcome and measuring the marginal quality, hit-probability, EV, ROI, stake, and
atomic-bet deltas. The result is stored under `multiple_value_admission` in the
internal planner explanation and summarized in `unified_candidate_pool`; it does
not add user-facing strategy text.

The benchmark, quality gate, and cycle summaries now carry those
`unified_candidate_pool_multiple_value_*` metrics. Gates can require admitted
multiple-value evidence, set minimum candidate / extra-outcome coverage, and
block any selected final answer whose multiple expansion is rejected by the
marginal-value admission check.

Stage 3 now also has a correct-score admission gate:
`nutmeg-recommendation-historical-correct-score-admission`. It consumes a
derived-market historical suite gate report and checks that correct-score
candidates have enough bounded final-answer coverage while preserving hit rate,
ROI, profit/loss, Brier score, log loss, and calibration. The current local
evidence report is
`configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_correct_score_admission_v1.json`;
it is `holdout_only` because the source suite remained no-harm but selected
zero correct-score final answers.

## Important Paths

- `apps/api/src/nutmeg/main.py`: FastAPI application entrypoint.
- `apps/api/src/nutmeg/domain/`: Pydantic domain models.
- `apps/api/src/nutmeg/modeling/`: lambda estimates, score grid generation,
  tail metrics, and Top N scores.
- `apps/api/src/nutmeg/market_resolver/`: market settlement and probability
  resolvers.
- `apps/api/src/nutmeg/parlay/`: parlay atomic expansion and evaluation.
- `apps/api/src/nutmeg/predictions/`: prediction snapshot building and local
  persistence.
- `apps/web/app/`: Next.js App Router pages for the frontend MVP.
- `apps/web/components/`: reusable frontend presentation components.
- `apps/web/lib/`: frontend mock API, validation schemas, and formatting
  helpers.
- `configs/competitions/`: competition onboarding configuration.
- `configs/rules/`: configurable market and parlay rules.
- `db/migrations/`: database schema migrations.
- `apps/api/tests/`: unit and integration tests.

## V2 Document Source

The implementation follows the V2 document set present in this workspace under
`Nutmeg_docs_v2/`. The requested `docs/nutmeg/` path was not present in the
initial workspace.
