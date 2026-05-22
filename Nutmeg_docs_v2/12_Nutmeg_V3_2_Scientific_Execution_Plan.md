# Nutmeg V3.2 Scientific Execution Plan

## 1. Core Decision

V3.2 stops treating any single play type, especially 2x1, as the development
center. The product goal is one budget-aware best answer across single, multiple,
2x1 through 8x1, 1X2, Chinese handicap 1X2, European handicap 1X2, and correct
score candidates.

The backend may remain complex, but the user-facing product must stay simple:
one best recommendation, optional backup only when useful, budget, timestamp,
and risk notice. Internal strategies, admission reasons, and diagnostic payloads
must stay out of the normal user answer page.

## 2. Non-Negotiable Rules

1. Do not spend long cycles optimizing 2x1 as an isolated target.
2. Every new experiment must be measured against a locked baseline.
3. No default production recommendation path may change without passing the
   baseline gate and the relevant final-answer quality gate.
4. Correct score and multiple-choice expansion may enter final answers only when
   they pass no-harm evidence.
5. Cold/upset work remains paused unless it is directly required for final-answer
   accuracy.
6. VPS, external APIs, and frontend expansion are secondary tools, not the core
   development path.
7. No auto betting, payment, wallet, or guaranteed-profit language.

## 3. Locked Baseline

The active baseline is `baseline_v3_1_locked_2026_05_21`.

It is fixed in:

```text
configs/recommendations/baselines/baseline_v3_1_locked_2026_05_21.json
```

The first V3.2 executable guard is:

```text
nutmeg-recommendation-scientific-baseline-gate
```

This gate consumes existing evidence artifacts only. It must not rerun heavy
historical backtests. Its job is to verify that the current known-good evidence
still exists, still passes, and still satisfies minimum quality thresholds.

Current locked evidence covers:

1. Core ROI-rebalanced final-answer quality.
2. Derived handicap/correct-score candidate suite quality.
3. Budget stability across the 10 and 20 budget tiers.
4. Constraint-profile dynamic-mix runtime smoke for constrained 2x1 plus 3x1.

## 4. Execution Stages

### Stage 1: Freeze And Guard

Goal: prevent drift and stop local experiments from becoming invisible behavior
changes.

Implementation tasks:

1. Create the V3.2 plan document.
2. Create the locked baseline manifest.
3. Add a lightweight baseline validator CLI.
4. Add deterministic tests for the validator.
5. Run lint, type check, and tests.

Exit criteria:

1. The baseline manifest validates successfully.
2. The validator can fail deterministically when required evidence is missing or
   below threshold.
3. No heavy historical replay is required.

### Stage 2: Unified Final Answer Candidate Pool

Goal: the optimizer evaluates final answers, not isolated play-type projects.

Implementation tasks:

1. Normalize single, multiple, 2x1 through 8x1, 1X2, handicap 1X2, and correct
   score into one final-answer candidate pool.
2. Make 2x1 only one candidate family inside the pool.
3. Keep constrained 2x1 as an allowed profile, but do not promote default 2x1
   multiple-choice expansion.
4. Make final-answer selection compare candidate families by hit probability,
   ROI/profit, budget fit, probability quality, and stability.

Exit criteria:

1. The engine can produce one best answer from mixed play types.
2. It can naturally choose no 2x1 when another candidate is better.
3. Existing baseline gate remains green.
4. The V3.2 unified-candidate-pool guard preset is available for benchmark
   cycles and persisted quality gates:
   `v3_2_unified_candidate_pool_guard_v1`.

### Stage 3: Correct Score And Multiple Value Admission

Goal: correct score and multiple-choice expansion enter final answers only when
they add measurable value.

Implementation tasks:

1. Build correct-score admission checks over the derived-market rolling-window
   suite.
2. Add marginal contribution scoring for every extra multiple-choice leg.
3. Reject multiple expansion when added stake or complexity reduces expected
   final-answer quality.
4. Keep 4x1 and default 2x1 multiple expansion blocked until they pass no-harm
   evidence.

Current implementation note:

1. `multiple_value_admission_v3_2` scores every selected extra outcome inside a
   multiple recommendation by comparing the final selection with that outcome
   removed.
2. The summary remains internal-only and is attached to planner explanation and
   the unified candidate pool.
3. Benchmark, quality-gate, and cycle summaries now aggregate
   `unified_candidate_pool_multiple_value_*` evidence so periodic gates can
   require admitted multiple-value candidates and block selected recommendations
   whose multiple expansion is rejected.
4. `historical_correct_score_admission_v3_2` consumes derived-market historical
   suite gate evidence and admits correct-score final answers only when they have
   enough bounded coverage and no harm to hit rate, ROI, profit/loss, Brier
   score, log loss, or calibration.
5. The bounded lane report,
   `football_data_co_uk_expanded_a_leagues_rolling_window_correct_score_lane_2x1_8x1_single_admission_v1.json`,
   is `rejected`: correct score entered 210 final answers and produced positive
   ROI, but it reduced final-answer hit rate versus the explicit no-correct-score
   profile reference. It must remain out of the production recommendation path.
6. This Stage 3 path is diagnostic/admission evidence; it does not expose
   strategy details to the user-facing answer page.
7. Benchmark quality gate and benchmark cycle now consume
   `correct_score_admission_*` evidence. The periodic gate can require holdout
   evidence for score-market research while still blocking production promotion
   until explicit no-harm and coverage criteria are met.
8. `correct_score_final_answer_lane_v3_2` is a default-off historical holdout
   lane that can seed one bounded correct-score leg into 2x1 through 8x1 final
   answers. It is guarded by hit-probability deficit and ROI-delta controls and
   only contributes production evidence after the no-harm gate admits it.

Exit criteria:

1. Correct score can enter bounded final-answer experiments and be blocked by a
   no-harm gate when hit rate regresses.
2. Multiple-choice recommendations can explain their value internally.
3. User-facing output remains one simple recommendation.

### Stage 4: Probability Model Mainline

Goal: improve prediction quality instead of only tuning the recommendation layer.

Implementation tasks:

1. Continue Dixon-Coles-compatible score-grid work.
2. Learn league-level draw/rho or rolling-window parameters.
3. Add recency and home/away attack-defense improvements only through holdout
   gates.
4. Treat lineup, injury, schedule congestion, and odds movement as shadow
   features until sample quality is sufficient.

Current implementation note:

1. `historical_poisson_parameter_admission_v3_2` consumes league-level
   Poisson/Dixon-Coles parameter-learning reports and blocks promotion unless
   held-out hit rate, Brier score, log loss, calibration error, and
   competition-level no-harm checks pass.
2. The current Dixon-Coles/recency/home-away report,
   `football_data_co_uk_core_5_seasons_dixon_recency_homeaway_parameter_admission_v1.json`,
   is `shadow_only`: it has 2062 validation samples across 6 learned
   competitions, but hit rate, Brier score, log loss, calibration error, and
   competition-level no-harm checks regress versus the market baseline.
3. The default prediction path remains unchanged. Learned score-grid parameters
   are research evidence until a future admission report is `accepted`.
4. `historical_poisson_market_anchor_calibration_v3_2` adds a shadow-only
   calibration experiment for score-grid candidates: Poisson/Dixon-Coles 1X2
   probabilities may be blended back toward the historical market-implied
   baseline by a candidate weight. Admission now requires selected candidates to
   retain a minimum score-grid model-signal weight, so a 100% market-anchor
   no-op cannot be promoted as a real model improvement.
5. The targeted market-anchor report,
   `football_data_co_uk_core_5_seasons_market_anchor_targeted_parameter_admission_v1.json`,
   is `shadow_only`: it selected a 0.95 market-anchor weight for all 6 learned
   competitions and improved expected calibration error versus baseline, but it
   still regressed hit rate, Brier score, log loss, and 5 competition-level
   no-harm checks. It remains research evidence only.
6. `historical_poisson_no_harm_selection_score_v3_2` adds an optional
   no-harm-aware parameter selection objective. It penalizes training candidates
   for hit-rate regression, Brier/log-loss regression, calibration regression,
   actual-outcome probability regression, and insufficient score-grid model
   signal before the holdout validation step.
7. The no-harm selection report,
   `football_data_co_uk_core_5_seasons_market_anchor_no_harm_selection_parameter_admission_v1.json`,
   is also `shadow_only`: the selector avoided the 0.95 market-anchor candidate
   and selected 0.8, preserving 20% model signal and improving calibration
   error, but it still regressed hit rate, Brier score, log loss, and 5
   competition-level no-harm checks. The next Stage 4 work should therefore
   improve the underlying score-grid signal rather than only tightening
   calibration.
8. `reliability_weighted_home_away_v3_2` adds a shadow-only score-grid candidate
   that downweights venue-specific attack/defense splits when venue samples are
   unreliable and shrinks team strengths toward league average.
9. The reliability-weighted report,
   `football_data_co_uk_core_5_seasons_reliability_homeaway_parameter_admission_v1.json`,
   is `shadow_only`: it preserved 20% model signal with 0.8 market anchoring, but
   regressed hit rate, Brier score, log loss, actual-outcome probability, and all
   6 competition-level no-harm checks. This narrows the next work away from more
   result-only home/away shrinkage and toward stronger pre-match signal or
   competition-specific segmentation.
10. `historical_poisson_segmented_admission_v3_2` adds competition-level
    parameter admission. It admits a learned candidate only in competitions where
    local held-out no-harm passes and keeps every failed competition on baseline
    fallback; the mixed segmented path must still pass aggregate no-harm.
11. The segmented reports,
    `football_data_co_uk_core_5_seasons_market_anchor_no_harm_selection_segmented_admission_v1.json`
    and
    `football_data_co_uk_core_5_seasons_market_anchor_targeted_segmented_admission_v1.json`,
    are both `shadow_only`: strict local no-harm admitted 0 competitions, so all
    2062 validation samples stayed on fallback. This confirms that the current
    score-grid candidates are not production-ready even as competition-specific
    overrides.
12. `historical_poisson_prematch_lambda_admission_v3_2` adds a dedicated gate
    for prematch-feature lambda adjustments. It combines source parameter
    learning, prematch sample readiness, selected-candidate signal strength, and
    strict no-harm checks before any prematch lambda adjustment can leave shadow
    mode.
13. The current prematch lambda admission report,
    `football_data_co_uk_market_feature_multi_season_prematch_lambda_admission_v1.json`,
    is `shadow_only`: the 600-fixture/25-slice market-movement sample is ready,
    but the learned candidate regressed hit rate, Brier score, log loss,
    actual-outcome probability, calibration measurability, and all 5
    competition-level no-harm checks. Prematch lambda adjustment therefore
    remains research evidence only.
14. `historical_prematch_signal_role_analysis_v3_2` classifies prematch signals
    by role instead of forcing one modeling path: lambda adjustment, broad
    probability adjustment, final-answer filter, market-movement risk filter,
    and research-only evidence.
15. The current role-analysis report,
    `football_data_co_uk_market_feature_prematch_signal_role_analysis_v1.json`,
    recommends the market-movement risk-filter lane as the next shadow candidate:
    lambda adjustment is blocked, broad probability adjustment is blocked,
    final-answer filtering shows local hit/ROI upside but fails Brier/log-loss
    quality checks, and the market-movement segment gate has accepted shadow
    segments with no final-answer hit-rate regression and improved Brier/log-loss
    on the tested slice.
16. `historical_market_movement_risk_filter_rolling_admission_v3_2` adds a
    rolling admission gate for that candidate lane. It treats the market-movement
    segment gate as a risk-filter proposal and validates it across overall,
    competition, cumulative season-cutoff, and rolling-season folds before any
    runtime promotion is allowed.
17. The current risk-filter rolling admission report,
    `football_data_co_uk_market_feature_market_movement_risk_filter_rolling_admission_v1.json`,
    is `shadow_only`: sample readiness is accepted and the overall segment gate
    has 3 accepted candidates from 6 evaluated candidates, with the best
    `delta_band:0.03:0.06` segment touching 174 fixtures and improving Brier
    score (-0.001025) and log loss (-0.002155) without final-answer hit-rate
    regression. However, 2 of 13 active folds fail (`season_cutoff:2023-2024`
    and `rolling_window:2:2021-2022..2023-2024`) because their best candidates
    regress final-answer quality gates. The lane therefore remains shadow-only
    and should next be narrowed by failed-fold segmentation rather than promoted
    to the default recommendation path.
18. `historical_market_movement_risk_filter_scope_refinement_v3_2` adds the
    failed-fold narrowing step for that lane. It reloads the rolling-admission
    folds, reruns the market-movement segment gate inside each analyzed fold,
    groups candidate segment keys across folds, and emits shadow-only guard
    scopes rather than runtime rules.
19. The current scope-refinement report,
    `football_data_co_uk_market_feature_market_movement_risk_filter_scope_refinement_v1.json`,
    is `guarded_scope_required`: it analyzed 14 folds, found 24 segment-scope
    candidates, and identified 9 stable shadow candidates. The best stable
    candidate is `strongest_movement_direction:probability_shortened`, accepted
    in 6 folds with average Brier delta -0.000928 and average log-loss delta
    -0.002001. It also found 10 guard scopes concentrated in the failing
    `2023-2024` windows, especially `competition:LIGUE_1`,
    `competition_direction:LIGUE_1:probability_drifted`,
    `competition_outcome:LIGUE_1:away_win`, `delta_band:0.03:0.06`, and
    `delta_band:0.06:`. These guards remain evidence only; no default
    recommendation path is changed until a later guarded rolling admission
    passes strict no-harm checks.
20. `historical_market_movement_risk_filter_guarded_admission_v3_2` adds that
    guarded rolling-admission pass. It consumes the scope-refinement guard
    evidence, removes globally blocked segment keys and exact failed-fold
    segment keys from each fold's segment-gate candidates, and treats fully
    guarded non-overall folds as shadow-only skipped folds rather than active
    promotions.
21. The current guarded-admission report,
    `football_data_co_uk_market_feature_market_movement_risk_filter_guarded_admission_v1.json`,
    is `accepted` as historical shadow evidence: sample readiness passes, the
    guarded overall fold still passes with `competition_outcome:LA_LIGA:home_win`
    as its best remaining segment, Brier delta -0.001288 and log-loss delta
    -0.002761; 11 active folds pass, 0 active folds fail, and the 2 previously
    failing folds are guarded skips. The guard removed 25 candidate evaluations,
    using 10 exact failed-fold guards plus 10 globally blocked segment keys.
    This is a stage win for the risk-filter lane, but it is not a production
    runtime change. The next step should convert the accepted guarded evidence
    into a runtime-rule proposal and replay it against the default answer path
    before any user-facing behavior changes.
22. `historical_market_movement_risk_filter_runtime_proposal_v3_2` converts that
    accepted guarded evidence into a shadow runtime-rule profile. The proposal
    keeps `proposed_production_enabled=false`, `production_recommendation_changed=false`,
    and `public_response_changed=false`; it only creates a replayable rule for
    `competition_outcome:LA_LIGA:home_win` with the same movement-weight and
    probability-shift constraints that passed the guarded segment gate.
23. The current runtime proposal and replay reports,
    `football_data_co_uk_market_feature_market_movement_risk_filter_runtime_proposal_v1.json`
    and
    `football_data_co_uk_market_feature_market_movement_risk_filter_runtime_replay_v1.json`,
    are both shadow-pass artifacts. The replay selected 1 rule, accepted 1
    segment, adjusted 120 fixtures / 360 predictions, preserved final-answer hit
    rate, ROI, and profit/loss deltas at 0.0, and improved Brier score
    (-0.001288), log loss (-0.002761), and calibration error (-0.001278).
    This still does not change the default recommendation path; the next step is
    to feed this runtime-shadow evidence into the recurring quality gate before
    any governed activation discussion.
24. `historical_recommendation_suite_quality_gate_v3_1` and the recurring
    benchmark quality gate now consume market-movement runtime replay evidence.
    The new suite gate report,
    `football_data_co_uk_market_feature_market_movement_runtime_replay_suite_gate_v1.json`,
    passed with 25 frozen slices / 25 comparisons, required the shadow replay to
    be present, runtime-allowed, production-unchanged, and public-output
    unchanged, and carried forward the replay no-harm metrics: final-hit, ROI,
    and profit/loss deltas remained 0.0 while Brier score (-0.001288), log loss
    (-0.002761), and calibration error (-0.001278) improved. This is still
    shadow-only evidence; no default recommendation path or user-facing response
    was changed.
25. `historical_market_movement_risk_filter_runtime_activation_v3_2` adds the
    controlled activation preflight for that runtime rule. It consumes the
    runtime profile, runtime replay report, and suite gate report, then checks
    source lineage, rollback conditions, no-harm replay metrics, no default-path
    change, no production recommendation change, and no public response change.
    The generated report,
    `football_data_co_uk_market_feature_market_movement_risk_filter_runtime_activation_preflight_v1.json`,
    is `staged_activation_ready` with 0 blockers, selecting only
    `market_movement_risk_filter_runtime_shadow_candidate_v1` for
    `competition_outcome:LA_LIGA:home_win`. The generated staged profile,
    `football_data_co_uk_market_feature_market_movement_risk_filter_staged_activation_profile_v1.json`,
    remains staged-only: it is not written to the default profile and does not
    change production recommendations or public/user-facing responses.
26. `recommendation_benchmark_quality_gate_v3_1` now consumes the market
    movement runtime activation preflight as explicit external evidence. A
    recurring benchmark gate can require the activation report, staged-ready
    status, selected-rule limits, adjusted fixture/prediction coverage,
    non-regressing final-hit/ROI/profit-loss metrics, non-regressing
    Brier/log-loss/calibration metrics, and no default-profile/default-path,
    production, or public-response changes. This keeps the activation candidate
    in the periodic quality chain without changing the ordinary recommendation
    path.
27. `recommendation_benchmark_cycle_v3_1` now forwards the same market movement
    runtime activation evidence into scheduled benchmark cycles. The cycle CLI
    exposes matching `--gate-market-movement-runtime-activation-*` arguments,
    maps them into the benchmark quality gate, and carries activation status,
    selected-rule coverage, adjusted fixture/prediction counts,
    final-hit/ROI/profit-loss deltas, Brier/log-loss/calibration deltas,
    blockers, and default/production/public-change flags into cycle summaries.
    This closes the recurring gate wiring while keeping the staged activation
    profile outside the ordinary user recommendation path.
28. `historical_probability_calibration_profile_model_quality_gate_v3_2`
    separates probability-quality evidence from recommendation activation. It
    consumes a shadow probability-calibration profile gate report and accepts it
    as model-quality evidence only when Brier score, log loss, and calibration
    error improve while final-hit, ROI, and P/L do not regress. The first report,
    `football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_model_quality_gate_v1.json`,
    is `model_quality_ready`: 4 selected competitions, 4 adjusted slices, 96
    adjusted fixtures, 0 changed final answers, final-hit / ROI / P&L deltas at
    `0.0`, Brier delta `-0.013140475792027984`, log-loss delta
    `-0.027925615774599954`, and mean calibration-error delta
    `-0.00851611160713972`. This is a shadow probability-quality win, not a
    default recommendation change.

Exit criteria:

1. Brier, log loss, and calibration do not regress.
2. Final-answer hit rate and ROI do not regress.
3. The feature or model change has enough held-out evidence to stay active.

### Stage 5: Real Sample Expansion

Goal: broaden evidence without letting data-source work consume the product.

Implementation tasks:

1. Expand frozen historical samples for the target leagues.
2. Prefer reusable historical snapshots over live API plumbing.
3. Add paid data only when a specific blocked capability requires it.
4. Keep every sample source inside the same benchmark and quality-gate chain.

Progress:

1. `historical_market_movement_runtime_activation_sample_expansion_v3_2`
   now consumes the market-movement runtime activation preflight, the frozen
   market-movement sample readiness report, and the expanded A-leagues coverage
   audit. The base generated report,
   `football_data_co_uk_market_feature_market_movement_runtime_activation_sample_expansion_v1.json`,
   passes the hard sample checks with 3,120 combined fixtures, 235 frozen
   slices, 12 competitions, and 60 competition-season cells. It remains
   `shadow_only` / not promotion-ready because the activation still covers only
   `competition_outcome:LA_LIGA:home_win` and its adjusted fixture share is
   below the promotion threshold before replay-batch evidence is attached.
2. `recommendation_benchmark_quality_gate_v3_1` can now require that sample
   expansion report as external evidence. This keeps the broader samples inside
   the recurring quality-gate surface while preserving the staged-only default:
   no default profile write, no default recommendation path change, no
   production recommendation change, and no public response change.
3. `historical_market_movement_runtime_activation_segment_expansion_v3_2`
   converts the stable scope-refinement evidence into direct runtime replay
   candidates. The generated report,
   `football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_v1.json`,
   selects four staged-only rules:
   `strongest_movement_direction:probability_shortened`,
   `opening_probability_band:0.25:0.45`, `outcome:home_win`, and
   `competition_direction:LA_LIGA:probability_drifted`. Together they cover 934
   adjusted fixtures / 2,802 adjusted predictions across the five core leagues.
   The generated staged profile is not written to the default path and is not
   production-enabled.
4. The top segment-expansion candidate,
   `strongest_movement_direction:probability_shortened`, now has a direct
   runtime replay report:
   `football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_top_replay_v1.json`.
   It passes the runtime shadow replay gate on the core market-feature suite
   with 248 adjusted fixtures / 744 adjusted predictions, no final-hit/ROI/P&L
   regression, and improved Brier/log-loss/calibration deltas. This is still
   shadow-only evidence.
5. The remaining three segment-expansion candidates now also have direct
   runtime replay reports, and
   `historical_market_movement_runtime_activation_segment_replay_batch_gate_v3_2`
   aggregates all four reports into one recurring quality-gate artifact:
   `football_data_co_uk_market_feature_market_movement_runtime_activation_segment_replay_batch_gate_v1.json`.
   The batch passes with 4/4 replay reports, 1,323 adjusted fixtures / 3,969
   adjusted predictions, no final-hit/ROI/P&L regression, and improved weighted
   Brier/log-loss/calibration deltas. This base batch report stays `watchlist`
   until the upstream sample-expansion gate includes the replay-batch evidence;
   the default recommendation path remains unchanged.
6. `recommendation_benchmark_cycle_v3_1` now forwards the market-movement
   sample-expansion report and the segment replay batch-gate report into
   `RecommendationBenchmarkQualityGateOptions`. Cycle summaries carry
   `market_movement_activation_sample_expansion_*` and
   `market_movement_segment_replay_batch_*` fields, so future periodic runs can
   fail when replay-batch evidence is missing or regresses while still keeping
   these rules out of the user-facing recommendation path.
7. The dedicated cycle preset
   `v3_2_market_movement_segment_replay_batch_gate_v1` now fixes the current
   replay-batch quality floor at 4 reports, 4 passed reports, 1,200 adjusted
   fixtures, and 3,600 adjusted predictions.
8. The sample-expansion gate now accepts segment replay batch-gate reports as
   supplemental effective coverage evidence. The generated ready report,
   `football_data_co_uk_market_feature_market_movement_runtime_activation_sample_expansion_segment_replay_ready_v1.json`,
   is `sample_expansion_ready` / promotion-ready with 1 ready replay-batch
   gate, 1,323 effective adjusted fixtures, 3,969 effective adjusted
   predictions, 5 effective segment keys, and a 42.4% effective
   adjusted/combined fixture ratio. It still reports no default path,
   production recommendation, or public response changes.
9. Re-running segment expansion and the replay batch gate from the ready
   sample-expansion evidence produces
   `football_data_co_uk_market_feature_market_movement_runtime_activation_segment_expansion_sample_ready_v1.json`
   and
   `football_data_co_uk_market_feature_market_movement_runtime_activation_segment_replay_batch_gate_sample_ready_v1.json`.
   The latter is `segment_replay_batch_ready`, production-promotion-ready, and
   has no blockers or watchlist items. The dedicated cycle preset now defaults
   to these ready reports.
10. `recommendation_benchmark_cycle_v3_1` now also exposes
    `v3_2_core_accuracy_governance_v1`, a composite dry-run governance preset
    that combines the probability-preserving 13-change strategy governance
    chain, successor effective-final-only historical suite gate, budget
    stability audit, constraint-aware dynamic-mix runtime smoke, and the ready
    market-movement sample-expansion / segment replay-batch gate. This is the
    recommended quality surface for the next core accuracy slice because it
    blocks default-path leaks, production/public-response changes, budget
    regressions, strategy-governance regressions, dynamic-mix constraint
    regressions, and market-movement evidence regressions in one place.
11. The first deterministic seeded smoke for that composite preset is
    `local_seed_v3_2_core_accuracy_governance_cycle_smoke_v1.json`. It passes
    with 27 completed benchmark scenarios, 9 seeded replay runs,
    `core_replay_ready_ratio=1.0`, `final_hit_coverage_ratio=1.0`, 240
    historical-suite slices, successor effective-final-only evidence ready,
    budget stability at `signature_change_rate=0.0`, admitted dynamic-mix
    constraint profiles for `2x1` and `3x1`, ready market-movement
    sample-expansion and segment replay-batch evidence, ready strategy
    governance, clean staged activation, clean default-path isolation, no gate
    failed checks, and no warnings.
12. The next replacement-ranking slice adds a shadow/runtime
    `probability_preserving_quality_score` rule. It preserves the model-top
    expected-hit-probability bucket, then ranks by pre-match replacement quality
    score, candidate score, edge, and price. The first grid report,
    `football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_grid_v1.json`,
    finds 400 accepted candidates and 200 accepted 13-change candidates. The
    selected 13-change candidate
    `replacement_probability_preserving_candidate:ff587ac5deddab76` passes
    cross-surface replay and fold admission, then passes a runtime dry run with
    99 final answers, 14 changed final answers, hit delta `+4`, P/L delta
    `+15.96`, ROI delta `+0.04092307692307692`, harm `0`, final-hit harm `0`,
    P/L harm `0`, and average hit-probability delta
    `-0.012219819458087085`. The promotion review is
    `promotion_review_ready` while preserving
    `production_recommendation_allowed=false`,
    `production_recommendation_changed=false`, and
    `public_response_changed=false`. The follow-up composite cycle
    `local_seed_v3_2_core_accuracy_governance_after_quality_score_candidate_v1.json`
    passes the same V3.2 governance preset with no failed checks or warnings.
13. The same quality-score branch now has its own strategy-governance chain:
    `football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_quality_score_strategy_promotion_gate_v1.json`
    is `ready`, the paired staged activation smoke is
    `staged_activation_ready`, and the default-path isolation report is
    `isolated`. The reusable quality-gate preset is
    `probability_preserving_quality_score_v1`, and the dry-run cycle preset is
    `probability_preserving_quality_score_governance_v1`. The seeded cycle
    smoke
    `local_seed_probability_preserving_quality_score_benchmark_cycle_governance_preset_smoke_v1.json`
    passes with 27 completed benchmark scenarios, 9 seeded core-replay runs,
    `core_replay_ready_ratio=1.0`, `final_hit_sample_size=27`, strategy
    governance ready, staged activation ready, default adapter disabled,
    default-path isolation clean, no gate failed checks, and no warnings. This
    remains staged/internal only and does not change default, production, or
    public recommendation paths.
14. The raw Asian-handicap prematch-feature path has been expanded from the
    24-fixture EPL smoke to the 25-slice top-five-league multi-season suite.
    The generated candidate suite
    `football_data_co_uk_market_feature_multi_season_with_asian_handicap_suite_v1.json`
    covers 600 fixtures with complete Asian-handicap feature coverage. The
    comparison report
    `football_data_co_uk_market_feature_multi_season_asian_handicap_shadow_comparison_v1.json`
    is shadow-only and fails strict non-regression: validation count 236,
    hit-rate delta `-0.004237288135593209`, Brier delta
    `+0.002230011584329672`, log-loss delta `+0.004054802489492859`, average
    actual-probability delta `-0.0008742726857767225`, and ECE delta
    `-0.006689034404863986`. The ECE improvement is not enough to admit the raw
    feature because hit/Brier/log-loss regress. `historical_poisson_walk_forward`
    report keys now include slice-content digests so identical slice ids with
    different feature surfaces cannot collide in evidence chains.
15. `historical_prematch_feature_asian_handicap_role_search_v3_2` now searches
    Asian-handicap prematch movement as a gated/damped shadow role instead of a
    fixed feature promotion. The current report,
    `football_data_co_uk_market_feature_multi_season_asian_handicap_role_search_v1.json`,
    evaluated 24 candidates across movement weights and minimum movement
    deltas. Zero-weight candidates passed only as controls. No nonzero
    Asian-handicap role passed strict non-regression
    (`accepted_nonzero_candidate_count=0`, `control_passed_candidate_count=4`,
    `watchlist_candidate_count=8`). The best effective candidate was
    `asian_handicap_movement_weight=0.05` with
    `min_asian_handicap_probability_delta=0.04`; it preserved hit rate and
    improved ECE but still regressed Brier and log loss. Asian-handicap movement
    must therefore stay shadow-only until a richer feature transform or a larger
    independent sample clears the same gate.
16. The first richer transform, line-aware Asian-handicap movement, now consumes
    the existing `opening_line`, `closing_line`, and `line_delta` metadata. The
    follow-up report,
    `football_data_co_uk_market_feature_multi_season_asian_handicap_line_aware_role_search_v1.json`,
    evaluated 64 candidates and found 10 accepted nonzero shadow candidates.
    The best accepted candidate combined cover-probability gating
    (`asian_handicap_movement_weight=0.05`,
    `min_asian_handicap_probability_delta=0.04`) with a line-movement signal
    (`asian_handicap_line_movement_weight=0.05`,
    `min_asian_handicap_line_delta=0.0`). It preserved hit rate while improving
    Brier score, log loss, and ECE on the 236-validation-sample multi-season
    comparison. This is model-quality shadow evidence only; it is not a default
    or production activation until an independent/rolling admission gate and
    default-path isolation pass.
17. `historical_prematch_feature_asian_handicap_role_admission_v3_2` now wraps
    line-aware role-search reports in an explicit admission decision. The
    overall-suite admission report,
    `football_data_co_uk_market_feature_multi_season_asian_handicap_line_aware_role_admission_v1.json`,
    is `accepted` as shadow model-quality evidence and records
    `default_path_isolated=true`, `production_recommendation_changed=false`, and
    `public_response_changed=false`. The stricter competition-fold admission
    report,
    `football_data_co_uk_market_feature_competition_fold_asian_handicap_line_aware_role_admission_v1.json`,
    is `shadow_only`: only the overall source report passes the same no-harm
    checks while the five single-league folds are not stable enough. This blocks
    activation and points the next work toward league-level segmentation or a
    narrower line-aware profile rather than a global promotion.
18. `historical_prematch_feature_asian_handicap_segmented_admission_v3_2`
    evaluates the line-aware role segment by segment. The current five-league
    report,
    `football_data_co_uk_competition_segmented_asian_handicap_line_aware_admission_v1.json`,
    is `shadow_only`: `accepted_segment_count=0`, `shadow_segment_count=1`,
    and `fallback_segment_count=4`. Serie A remains research-only because it
    lacks a measurable calibration delta despite Brier/log-loss improvement;
    EPL, La Liga, Bundesliga, and Ligue 1 remain on baseline fallback because
    local no-harm or accepted-candidate requirements fail. This confirms the
    current line-aware Asian-handicap signal is promising but still too narrow
    for activation. Default, production, and public paths remain unchanged.
19. `historical_prematch_feature_asian_handicap_segment_refinement_v3_2`
    turns the segmented blockers into bounded next experiments. The current
    refinement report,
    `football_data_co_uk_competition_segmented_asian_handicap_line_aware_refinement_v1.json`,
    is `refinement_ready`: Serie A is the top calibration-sample expansion
    target, Bundesliga needs calibration-scope refinement, and EPL, La Liga, and
    Ligue 1 require line-transform enrichment before another admission attempt.
    This is a planning/evidence artifact only; it does not activate the
    line-aware Asian-handicap signal.
20. `historical_prematch_feature_asian_handicap_calibration_sample_expansion_v3_2`
    now turns the Serie A calibration blocker into measurable shadow evidence.
    The current report,
    `football_data_co_uk_serie_a_asian_handicap_line_aware_calibration_sample_expansion_v1.json`,
    is `measurement_ready` with
    `report_key=historical_prematch_feature_asian_handicap_calibration_sample_expansion:5456e4510ea17452`.
    It compares the strict `min_bucket_sample_size=30` run, whose ECE delta is
    missing, with a relaxed `min_bucket_sample_size=10` replay that keeps the
    same candidate parameters. On 42 validation samples, the relaxed replay
    preserves hit rate and improves Brier, log loss, and ECE. This removes a
    measurement blocker only; `activation_allowed=false`, and default,
    production, and public recommendation paths remain unchanged.
21. `historical_prematch_feature_asian_handicap_segmented_admission_v3_2` can
    now consume `measurement_ready` calibration sample expansion evidence. The
    current replay report,
    `football_data_co_uk_competition_segmented_asian_handicap_line_aware_calibration_sample_expansion_admission_v1.json`,
    is still `shadow_only` with
    `report_key=historical_prematch_feature_asian_handicap_segmented_admission:ee4803cba978db18`.
    Serie A becomes one accepted local segment after the measured ECE delta is
    applied, but the accepted validation count is 42 against the 100-sample
    admission threshold. This proves the blocker was correctly narrowed without
    activating the signal; all default, production, and public paths remain
    unchanged.
22. `historical_prematch_feature_asian_handicap_calibration_scope_refinement_v3_2`
    now evaluates Bundesliga calibration-scope alternatives without changing
    the line-aware candidate parameters. The current report,
    `football_data_co_uk_bundesliga_asian_handicap_line_aware_calibration_scope_refinement_v1.json`,
    is `shadow_only` with
    `report_key=historical_prematch_feature_asian_handicap_calibration_scope_refinement:959f918be943199e`.
    The best replay lowers the ECE regression from
    `2.7318296421746657e-05` to `1.3160470493496501e-05`, while preserving hit
    rate and improving Brier/log loss, but it still does not clear the
    calibration no-harm gate. A lower bucket floor of 10 makes ECE materially
    worse, and a wider 0.20 bucket also remains positive. Bundesliga therefore
    stays out of admission; the next bounded work should be feature-transform
    enrichment, not threshold relaxation.
23. The first line-transform enrichment branch is now implemented and measured.
    `historical_poisson_walk_forward` supports default-preserving
    `linear`, `signed_sqrt`, and `quarter_step` Asian-handicap line-movement
    transforms, and role-search candidates now carry the transform through the
    shadow evidence chain. The top-five report,
    `football_data_co_uk_top5_asian_handicap_line_transform_enrichment_role_search_v1.json`,
    evaluated 24 fixed-weight transform candidates and accepted 4 nonzero
    candidates. The best overall candidate uses `signed_sqrt` with
    `asian_handicap_line_movement_weight=0.02`, preserving hit rate while
    improving Brier (`-0.00003710188760208677`), log loss
    (`-0.000018118521427190615`), and ECE
    (`-0.0013521715299190593`). Segment replay then accepts EPL and the
    previously measured Serie A segment, keeps Ligue 1 `shadow_only` for
    missing ECE, and keeps La Liga/Bundesliga on baseline fallback. The
    segmented admission report,
    `football_data_co_uk_competition_segmented_asian_handicap_line_transform_enrichment_admission_v1.json`,
    remains `shadow_only`: accepted validation coverage is `91` against the
    `100` threshold. Default, production, and public recommendation paths remain
    unchanged.
24. Ligue 1 follow-up calibration measurement now resolves the missing-ECE
    blocker for the accepted line-transform candidate without weakening the
    admission gate. A same-parameter replay with `min_bucket_sample_size=20` and
    `bucket_size=0.20` produces
    `football_data_co_uk_ligue_1_asian_handicap_line_transform_calibration_measurement_v1.json`
    with
    `report_key=historical_prematch_feature_asian_handicap_calibration_sample_expansion:7094db2e5a0f0330`.
    The measurement is `measurement_ready`, preserves hit rate, and improves
    Brier (`-0.00140031241799643`), log loss
    (`-0.0015915107150870078`), and ECE
    (`-0.0004608749501475162`). The replay also tightens the calibration
    measurement wrapper so follow-up targets can be measured when they were not
    part of the original refinement decision, while still requiring
    same-candidate parameters including line transform.
25. The segmented Asian-handicap line-transform admission replay now consumes
    both Serie A and Ligue 1 measurement evidence. The current report,
    `football_data_co_uk_competition_segmented_asian_handicap_line_transform_enrichment_calibration_measurement_admission_v1.json`,
    is `accepted` with
    `report_key=historical_prematch_feature_asian_handicap_segmented_admission:73333d16c556ebb2`.
    Accepted segments are EPL, Ligue 1, and Serie A with 138 accepted validation
    samples against the 100-sample threshold. Accepted-segment deltas preserve
    hit rate (`0.0`) and improve Brier (`-0.0010761099689132964`), log loss
    (`-0.0014682563369637206`), ECE (`-0.0002984001368970529`), and actual
    outcome probability (`+0.0002354975969207306`). La Liga and Bundesliga stay
    on baseline fallback. This is internal model-quality admission evidence
    only; default, production, and public recommendation paths remain unchanged.
26. The segmented Asian-handicap governance review now consumes that accepted
    admission report without promoting it to default or public recommendation
    paths. The current report,
    `football_data_co_uk_competition_segmented_asian_handicap_line_transform_enrichment_governance_review_v1.json`,
    is `governance_ready` with
    `report_key=historical_prematch_feature_asian_handicap_segmented_governance_review:261deacce90b7740`.
    It keeps the staged profile `dry_run_only` and `internal_review_only`,
    requires two calibration-measurement applications, verifies 3 accepted
    segments, 2 baseline fallback segments, 0 shadow/rejected segments, 138
    accepted validation samples, no aggregate hit/Brier/log-loss/ECE harm, and
    no default, production, or public response changes.
27. The benchmark quality gate and benchmark cycle now consume this segmented
    Asian-handicap governance evidence as first-class model-quality guardrail
    fields. `recommendation_benchmark_quality_gate_v3_1` exposes
    `asian_handicap_segmented_model_quality_*` checks and summary fields, and
    `v3_2_core_accuracy_governance_v1` now requires the current governance
    report to be ready, internal-only, default-path isolated, production/public
    unchanged, backed by at least 3 accepted segments, no shadow/rejected
    segments, at most 2 fallback segments, 100 accepted validation samples, 2
    calibration measurements, and no aggregate hit/Brier/log-loss/ECE or
    actual-probability harm. This keeps the signal in recurring governance
    without activating it.

Exit criteria:

1. New samples increase coverage and are reproducible.
2. They feed existing gates instead of creating one-off analysis islands.

### Stage 6: Minimal Answer Page

Goal: product clarity.

Implementation tasks:

1. Keep the answer page focused on today's best recommendation.
2. Show single/multiple, pass type, budget, update time, and risk notice.
3. Hide internal strategy, admission, and diagnostic details from normal users.
4. Remove remaining mock or fallback recommendation paths from public UX.

Exit criteria:

1. The first viewport answers what to buy, not why the backend chose it.
2. No guaranteed-profit language appears.

## 5. Current Next Action

Stage 1 and Stage 2 are green. Stage 3 has internal multiple-value admission,
periodic multiple-value guard metrics, a correct-score lane admission chain,
and a constraint-aware dynamic-mix multiple lane that admits only the protected
`2x1` / `3x1` profiles. Stage 4 has a Poisson/Dixon-Coles parameter admission
gate plus market-anchor calibration candidate paths; the model-quality shadow
gate now records a real calibration-quality improvement without treating it as
final-answer promotion, and the recurring benchmark gate/cycle can consume that
evidence as a probability-quality guardrail. Stage 5 now has a ready
market-movement
sample-expansion and segment replay-batch governance chain with no
default/production/public path changes. The composite
`v3_2_core_accuracy_governance_v1` smoke is green. The stronger
quality-score replacement-ranking surface has entered strategy governance,
staged activation, default-path isolation, and its own seeded governance cycle
while remaining internal-only. The selection-value runtime admission path now
uses the probability model-quality guardrail and remains holdout-only because
absolute candidate ROI is still negative. The raw Asian-handicap feature path
has strong coverage. The raw movement path failed strict non-regression, and
the line-aware richer transform now has accepted overall-suite shadow evidence
but failed competition-fold admission. The next execution target should stay in
Stage 4/5 model-quality work: the first segmented line-aware Asian-handicap
admission is complete and blocks activation with 0 accepted segments. The
follow-up refinement report is complete, and the first bounded Serie A
calibration sample expansion is now `measurement_ready` without activation. The
segmented admission replay consumed that evidence and moved Serie A to a local
accepted segment, but the overall report remains `shadow_only` because 42
accepted validation samples do not clear the 100-sample threshold. Bundesliga
calibration-scope refinement is also complete and remains `shadow_only`: scope
changes narrow but do not clear the ECE regression. Line-transform enrichment
is now implemented, and the Ligue 1 follow-up calibration measurement resolves
the remaining missing-ECE blocker for that accepted candidate. The segmented
admission replay now accepts EPL, Ligue 1, and Serie A with 138 accepted
validation samples, while La Liga and Bundesliga remain baseline fallback. The
segmented governance review is now `governance_ready` and produces only a
dry-run internal staged profile. The benchmark quality gate and
`v3_2_core_accuracy_governance_v1` cycle preset now consume this evidence as a
required internal model-quality guardrail. The next bounded work should run the
updated governance preset in a seed smoke and then use the resulting summary to
decide whether to add another internal replay surface, still with no default,
production, or public recommendation change. It must keep passing the
governance surfaces rather than returning to isolated `2x1` tuning,
penalty-only recovery, direct feature promotion, or live data plumbing.

Latest implementation note:

1. `recommendation_benchmark_quality_gate_v3_1` now accepts
   `probability_calibration_profile_model_quality_gate_report_path` and can
   require `model_quality_ready` evidence with selected-competition,
   adjusted-slice, adjusted-fixture, skipped-fixture, unchanged-final-answer,
   final-hit, ROI, profit/loss, Brier, log-loss, and calibration-error
   thresholds.
2. `recommendation_benchmark_cycle_v3_1` forwards the same options with
   `--gate-` prefixes and carries the model-quality summary fields into cycle
   output.
3. This is still shadow evidence only. It must not write a default profile,
   enable production recommendations, or expose internal strategy details to the
   user-facing answer page.
4. `historical_final_answer_selection_value_signal_runtime_admission_v3_1` now
   has an optional hard dependency on this model-quality evidence. When enabled,
   selection-value candidate-generation experiments must pass the same
   probability-quality guardrail before they can be admitted as final-answer
   movement evidence.
5. The first guarded real admission report is
   `football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_runtime_admission_model_quality_guarded_v1.json`
   with
   `report_key=historical_final_answer_selection_value_signal_runtime_admission:efc71df93ded1da2`.
   It passed the probability model-quality guardrail with 4 selected
   competitions, 96 adjusted fixtures, 0 model-quality final-answer changes,
   negative Brier/log-loss/calibration deltas, and no public or production
   response changes.
6. The guarded admission remains `holdout_only` because
   `candidate_roi=-0.037760317460317466` is below the `0.0` floor. The paired
   ROI-floor gap report
   `football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_gap_model_quality_guarded_v1.json`
   quantifies a `0.037760317460317466` remaining ROI gap and estimates that 5
   additional clean positive movements are needed before this narrow lane can
   clear the production admission floor.
7. The multi-season Asian-handicap shadow comparison is complete and blocked:
   `candidate_asian_handicap_feature_coverage=1.0`, but
   `passed_non_regression_gate=false`. This evidence should feed a gated/damped
   feature experiment only; it is not activation evidence.
8. The gated/damped Asian-handicap role search is also complete and blocked for
   activation. It found only zero-weight control passes and no accepted nonzero
   candidate. The next useful Asian-handicap work should change the feature
   transform itself, not simply tune the same raw cover-movement multiplier.
9. The line-aware transform has now produced the first accepted nonzero
   Asian-handicap shadow candidate. This is a stage win, but the next step is a
   real admission wrapper, not direct activation.
10. The admission wrapper is complete. Overall-suite admission accepts the
    candidate as shadow evidence, while competition-fold admission keeps it
    `shadow_only`. The next useful step is segmented admission, not activation.
11. The segmented admission wrapper is complete. The five-league segmented
    report keeps all competition segments out of activation: Serie A is
    research-only due missing calibration delta, and the other four segments use
    baseline fallback. The next useful step is feature enrichment or narrower
    segment/fold evidence, not activation.
12. The segment refinement wrapper is complete. It ranks Serie A as the cleanest
    next calibration-sample target, Bundesliga as a calibration-scope target,
    and EPL, La Liga, and Ligue 1 as line-transform enrichment targets. The next
    useful step is to implement one of those bounded experiments, still without
    activating the signal.
13. The Serie A calibration sample expansion wrapper is complete. It lowers the
    calibration bucket floor from 30 to 10 for measurement only, keeps the same
    line-aware candidate parameters, and produces measurable non-regressing ECE
    evidence on 42 validation samples. The next useful step is another segmented
    admission replay that can consume this measurement evidence without exposing
    or activating the signal.
14. The segmented admission replay with calibration evidence is complete. Serie
    A is now accepted locally, but the overall admission report remains
    `shadow_only` because accepted validation coverage is only 42 against the
    100-sample threshold. The next useful step is to add clean validation
    coverage through Bundesliga calibration-scope refinement and other bounded
    segment improvements, not to lower the threshold.
15. The Bundesliga calibration-scope refinement wrapper is complete. Alternate
    ECE scopes preserve hit rate and Brier/log-loss gains, but none clears the
    calibration gate. The best scope is `min_bucket_sample_size=20`, which only
    narrows the ECE regression. The next useful step is line-transform
    enrichment across the remaining blocked segments, not another scope-only
    replay.
16. The line-transform enrichment branch is complete for the current top-five
    sample. It improves the overall no-harm role-search result and promotes EPL
    into accepted shadow evidence.
17. The Ligue 1 follow-up calibration measurement is complete. It converts the
    missing-ECE blocker into a non-regressing measurement-ready report without
    changing candidate parameters.
18. The segmented admission replay with Serie A and Ligue 1 measurement
    evidence is now `accepted`: 3 accepted segments, 138 accepted validation
    samples, and no hit/Brier/log-loss/ECE harm. The next useful step is a
    staged internal promotion/governance review for this segmented model-quality
    evidence, not a default or public recommendation change.
19. The staged internal segmented governance review is complete and
    `governance_ready`. It requires the accepted segmented admission, 2
    calibration-measurement applications, 3 accepted segments, 138 accepted
    validation samples, no aggregate non-regression harm, and a
    `dry_run_only` / `internal_review_only` staged profile. It does not enable
    production recommendations, write a default profile, or change public
    responses. The next useful step is to wire this evidence into benchmark or
    cycle-level model-quality guardrails, not to activate the Asian-handicap
    feature directly.
20. The benchmark/cycle model-quality guardrail wiring is complete. The quality
    gate can require `asian_handicap_segmented_model_quality_governance`, and
    the `v3_2_core_accuracy_governance_v1` preset now attaches the current
    governance report with strict internal-only, no-production-change,
    no-public-change, segment-count, validation-count, calibration-count, and
    aggregate no-harm checks. The next useful step is a seeded cycle smoke that
    proves the full preset remains green with this extra guardrail.
