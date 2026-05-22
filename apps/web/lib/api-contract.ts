import { z } from "zod";

const teamSchema = z.object({
  team_id: z.string(),
  name: z.string(),
});

const dataQualityGradeSchema = z.enum(["A", "B", "C", "D"]);
const riskLevelSchema = z.enum(["low", "medium", "medium_high", "high"]);

const upsetContributionSchema = z.object({
  key: z.string(),
  label: z.string(),
  score: z.number().min(0).max(100),
  description: z.string(),
});

const upsetExplanationGroupSchema = z.object({
  title: z.string(),
  items: z.array(z.string()),
});

const fixtureFreshnessSchema = z.object({
  odds_available: z.boolean(),
  odds_fresh_enough: z.boolean(),
  odds_market_types: z.array(z.string()).default([]),
  odds_snapshot_time_utc: z.string().nullable().default(null),
  odds_snapshot_lag_hours: z.number().nullable().default(null),
  lineup_available: z.boolean().default(false),
  lineup_fresh_enough: z.boolean().default(false),
  lineup_snapshot_time_utc: z.string().nullable().default(null),
  lineup_snapshot_lag_hours: z.number().nullable().default(null),
  injury_available: z.boolean().default(false),
  injury_fresh_enough: z.boolean().default(false),
  injury_snapshot_time_utc: z.string().nullable().default(null),
  injury_snapshot_lag_hours: z.number().nullable().default(null),
  messages: z.array(z.string()).default([]),
});

export const fixtureListResponseSchema = z.object({
  items: z.array(
    z.object({
      fixture_id: z.string(),
      competition_id: z.string(),
      competition: z.string(),
      kickoff_time_utc: z.string(),
      home_team: teamSchema,
      away_team: teamSchema,
      prediction: z.object({
        p_home: z.number().min(0).max(1),
        p_draw: z.number().min(0).max(1),
        p_away: z.number().min(0).max(1),
        confidence: z.enum(["low", "medium", "high"]),
        model_version: z.string(),
        feature_version: z.string(),
        calibration_version: z.string(),
        prediction_time_utc: z.string(),
        data_quality_score: z.number().min(0).max(100),
        stale: z.boolean(),
        fallback_used: z.boolean(),
        data_freshness: fixtureFreshnessSchema.nullable().default(null),
      }),
      badges: z.array(z.string()),
    }),
  ),
});

const marketProbabilityComparisonSchema = z.object({
  label: z.string(),
  outcome_key: z.string(),
  model_probability: z.number().min(0).max(1),
  market_probability: z.number().min(0).max(1).nullable(),
  probability_gap: z.number().nullable(),
  highlighted: z.boolean(),
});

const marketComparisonSetSchema = z.object({
  label: z.string(),
  items: z.array(marketProbabilityComparisonSchema),
});

const upsetAlertSchema = z.object({
  fixture_id: z.string(),
  type: z.string(),
  label: z.string(),
  target_outcome: z.string(),
  favorite: z.string().default("市场热门"),
  favorite_model_probability: z.number().min(0).max(1).default(0),
  favorite_market_probability: z.number().min(0).max(1).default(0),
  model_probability: z.number().min(0).max(1),
  market_probability: z.number().min(0).max(1),
  probability_gap: z.number(),
  favorite_fragility_score: z.number().min(0).max(1),
  risk_level: riskLevelSchema,
  explanations: z.array(z.string()),
  contributions: z.array(upsetContributionSchema).default([]),
  explanation_groups: z.array(upsetExplanationGroupSchema).default([]),
});

export const fixturePredictionResponseSchema = z.object({
  fixture: z.object({
    fixture_id: z.string(),
    competition_id: z.string(),
    competition_name: z.string(),
    kickoff_time_utc: z.string(),
    home_team: teamSchema,
    away_team: teamSchema,
    status: z.enum(["scheduled", "stale", "beta"]),
    data_quality_score: z.number().min(0).max(100),
    data_quality_grade: dataQualityGradeSchema,
  }),
  prediction_snapshot: z.object({
    fixture_id: z.string(),
    prediction_time_utc: z.string(),
    model_version: z.string(),
    feature_version: z.string(),
    calibration_version: z.string(),
    p_home: z.number().min(0).max(1),
    p_draw: z.number().min(0).max(1),
    p_away: z.number().min(0).max(1),
    uncertainty: z.enum(["low", "medium", "high"]),
    data_quality_score: z.number().min(0).max(100),
    score_grid: z.object({
      max_goals: z.number(),
      grid: z.array(z.array(z.number())),
      tail_mass: z.number(),
      lambda_home: z.number().nullable(),
      lambda_away: z.number().nullable(),
    }),
    market_probabilities: z.record(z.string(), z.unknown()),
    explanation_json: z.record(z.string(), z.unknown()),
  }),
  score_top_n: z.array(
    z.object({
      home_goals: z.number(),
      away_goals: z.number(),
      probability: z.number().min(0).max(1),
      option_key: z.string(),
    }),
  ),
  market_predictions: z.record(z.string(), z.unknown()),
  odds_comparison: z.record(z.string(), marketComparisonSetSchema),
  upset_alerts: z.array(upsetAlertSchema),
  explanations: z.object({
    model: z.array(z.string()),
    market: z.array(z.string()),
    lineup: z.array(z.string()),
    schedule: z.array(z.string()),
    uncertainty: z.array(z.string()),
  }),
  model_metadata: z.object({
    model_version: z.string(),
    feature_version: z.string(),
    calibration_version: z.string(),
    prediction_time_utc: z.string(),
    data_quality_score: z.number().min(0).max(100),
    data_quality_grade: dataQualityGradeSchema,
    stale: z.boolean(),
    fallback_used: z.boolean(),
    data_freshness: fixtureFreshnessSchema.nullable().default(null),
  }),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const upsetListResponseSchema = z.object({
  items: z.array(
    upsetAlertSchema.extend({
      match_label: z.string(),
      competition_name: z.string(),
      kickoff_time_utc: z.string(),
      data_quality_score: z.number().min(0).max(100),
      data_quality_grade: dataQualityGradeSchema,
      model_version: z.string(),
      prediction_time_utc: z.string(),
    }),
  ),
});

const parlayAtomicLegResponseSchema = z.object({
  fixture_id: z.string(),
  market_type: z.string(),
  outcome: z.string(),
  probability: z.number().min(0).max(1),
  odds: z.number().gt(1),
  line: z.number().nullable(),
});

const parlayAtomicBetResponseSchema = z.object({
  legs: z.array(parlayAtomicLegResponseSchema),
  stake: z.number().positive(),
  probability: z.number().min(0).max(1),
  odds_product: z.number().gt(1),
  expected_payout: z.number(),
  expected_value: z.number(),
  roi: z.number(),
});

export const parlayRecommendResponseSchema = z.object({
  items: z.array(
    z.object({
      recommendation_id: z.string(),
      strategy: z.string(),
      pass_type: z.string(),
      is_multiple: z.boolean(),
      legs: z.array(
        z.object({
          fixture_id: z.string(),
          match_label: z.string(),
          market: z.string(),
          outcomes: z.array(z.string()),
        }),
      ),
      atomic_bet_count: z.number().int().nonnegative(),
      unit_stake: z.number().positive(),
      total_stake: z.number().nonnegative(),
      hit_probability: z.number().min(0).max(1),
      expected_payout: z.number(),
      ev: z.number(),
      roi: z.number(),
      risk_level: riskLevelSchema,
      risk_score: z.number().min(0).max(1).default(0),
      correlation_penalty: z.number().min(0).max(1).default(0),
      rule_valid: z.boolean(),
      explanations: z.array(z.string()),
      explanation_json: z.record(z.string(), z.unknown()).default({}),
      atomic_bets: z.array(parlayAtomicBetResponseSchema).default([]),
    }),
  ),
  warnings: z.array(z.string()).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const recommendationLifecycleStatusResponseSchema = z.enum([
  "candidate",
  "current",
  "superseded",
  "locked",
  "confirmed_manual",
  "live",
  "settled",
  "invalidated",
]);

const recommendationRunLifecycleRecordResponseSchema = z.object({
  recommendation_run_id: z.number().int().positive(),
  run_key: z.string(),
  status: recommendationLifecycleStatusResponseSchema,
  selected_fixture_ids: z.array(z.string()).default([]),
  locked_fixture_ids: z.array(z.string()).default([]),
  created_at: z.string(),
});

const recommendationStoredRunResponseSchema = z.object({
  recommendation_run_id: z.number().int().positive(),
  recommendation_candidate_ids: z.array(z.number().int().positive()).default([]),
  recommendation_lifecycle_event_ids: z.array(z.number().int().positive()).default([]),
  created_at: z.string(),
});

const recommendationGenerationResultResponseSchema = z.object({
  dry_run: z.boolean(),
  as_of_time_utc: z.string(),
  candidate_count: z.number().int().nonnegative(),
  generated_count: z.number().int().nonnegative(),
  selection: z.unknown().nullable().default(null),
  stored_run: recommendationStoredRunResponseSchema.nullable().default(null),
  warnings: z.array(z.string()).default([]),
});

const recommendationAnswerLegResponseSchema = z.object({
  fixture_id: z.string(),
  market_type: z.string(),
  outcomes: z.array(z.string()).min(1),
  probability: z.number().min(0).max(1),
  decimal_odds: z.number().gt(1).nullable().default(null),
  line: z.number().nullable().default(null),
  side: z.string().nullable().default(null),
  data_quality_score: z.number().min(0).max(100),
  model_version: z.string().nullable().default(null),
  prediction_snapshot_id: z.number().int().positive().nullable().default(null),
  prediction_time_utc: z.string().nullable().default(null),
  kickoff_time_utc: z.string().nullable().default(null),
  recommendation_score: z.number().min(0).max(1),
});

const recommendationAnswerResponseSchema = z.object({
  status: z.enum(["ready", "unavailable"]),
  generated_at_utc: z.string(),
  pass_type: z.string().nullable().default(null),
  mode: z.enum(["single", "multiple"]).nullable().default(null),
  is_multiple: z.boolean().default(false),
  fixture_count: z.number().int().nonnegative().default(0),
  legs: z.array(recommendationAnswerLegResponseSchema).default([]),
  budget: z
    .object({
      unit_stake: z.number().positive(),
      total_stake: z.number().nonnegative(),
      max_budget: z.number().positive().nullable().default(null),
      within_budget: z.boolean(),
    })
    .nullable()
    .default(null),
  atomic_bet_count: z.number().int().nonnegative().default(0),
  hit_probability: z.number().min(0).max(1).nullable().default(null),
  expected_payout: z.number().nullable().default(null),
  expected_value: z.number().nullable().default(null),
  roi: z.number().nullable().default(null),
  risk_score: z.number().min(0).max(1).nullable().default(null),
  risk_level: z.string().nullable().default(null),
  rule_valid: z.boolean().default(false),
  average_data_quality_score: z.number().min(0).max(100).nullable().default(null),
  data_quality_grade: dataQualityGradeSchema.nullable().default(null),
  warnings: z.array(z.string()).default([]),
});

const recommendationAnswerSetResponseSchema = z.object({
  primary_answer: recommendationAnswerResponseSchema,
  backup_answers: z.array(recommendationAnswerResponseSchema).default([]),
  summary_json: z.record(z.string(), z.unknown()).default({}),
});

export const recommendationGenerateResponseSchema = z.object({
  result: recommendationGenerationResultResponseSchema,
  answer: recommendationAnswerResponseSchema,
  alternatives: z.array(recommendationAnswerResponseSchema).default([]),
  answer_set: recommendationAnswerSetResponseSchema.nullable().default(null),
  single_answer: recommendationAnswerResponseSchema.nullable().default(null),
  upset_answer: recommendationAnswerResponseSchema.nullable().default(null),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const recommendationGlobalPlannerResultResponseSchema = z.object({
  dry_run: z.boolean(),
  as_of_time_utc: z.string(),
  candidate_count: z.number().int().nonnegative(),
  evaluated_option_count: z.number().int().nonnegative(),
  generated_option_count: z.number().int().nonnegative(),
  best_option: z.unknown().nullable().default(null),
  alternatives: z.array(z.unknown()).default([]),
  attempts: z.array(z.unknown()).default([]),
  stored_run: recommendationStoredRunResponseSchema.nullable().default(null),
  warnings: z.array(z.string()).default([]),
});

export const recommendationGlobalPlannerResponseSchema = z.object({
  result: recommendationGlobalPlannerResultResponseSchema,
  answer: recommendationAnswerResponseSchema,
  alternatives: z.array(recommendationAnswerResponseSchema).default([]),
  answer_set: recommendationAnswerSetResponseSchema.nullable().default(null),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const recommendationLockedLegRecordResponseSchema = z.object({
  recommendation_locked_leg_id: z.number().int().positive(),
  recommendation_run_id: z.number().int().positive(),
  fixture_id: z.string(),
  market_type: z.string(),
  outcome: z.string(),
  locked_at_utc: z.string(),
  status: z.string(),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

const recommendationLifecycleEventRecordResponseSchema = z.object({
  recommendation_lifecycle_event_id: z.number().int().positive(),
  recommendation_run_id: z.number().int().positive(),
  recommendation_key: z.string(),
  from_status: recommendationLifecycleStatusResponseSchema,
  to_status: recommendationLifecycleStatusResponseSchema,
  reason_code: z.string(),
  event_time_utc: z.string(),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

export const recommendationLifecycleResponseSchema = z.object({
  detail: z.object({
    run: recommendationRunLifecycleRecordResponseSchema,
    locked_legs: z.array(recommendationLockedLegRecordResponseSchema).default([]),
    events: z.array(recommendationLifecycleEventRecordResponseSchema).default([]),
  }),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const recommendationLifecycleMutationResponseSchema = z.object({
  result: z.object({
    run: recommendationRunLifecycleRecordResponseSchema,
    event: recommendationLifecycleEventRecordResponseSchema,
    locked_leg: recommendationLockedLegRecordResponseSchema.nullable().default(null),
  }),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const recommendationStrategyEvidenceResponseSchema = z.object({
  strategy: z.string(),
  pass_type: z.string(),
  mode: z.string(),
  sample_size: z.number().int().nonnegative(),
  settled_run_count: z.number().int().nonnegative(),
  hit_count: z.number().int().nonnegative(),
  total_stake: z.number().nonnegative(),
  gross_payout: z.number().nonnegative(),
  profit_loss: z.number(),
  roi: z.number().nullable().default(null),
  hit_rate: z.number().min(0).max(1).nullable().default(null),
  average_expected_roi: z.number().nullable().default(null),
  average_expected_hit_probability: z.number().min(0).max(1).nullable().default(null),
  average_hit_calibration_error: z.number().nullable().default(null),
  mean_absolute_hit_calibration_error: z.number().nonnegative().nullable().default(null),
  first_evaluation_time_utc: z.string().nullable().default(null),
  last_evaluation_time_utc: z.string().nullable().default(null),
});

const recommendationStrategyReviewArtifactResponseSchema = z.object({
  review_key: z.string(),
  candidate_evidence: recommendationStrategyEvidenceResponseSchema,
  baseline_evidence: recommendationStrategyEvidenceResponseSchema,
  promotion_review: z.object({
    candidate_strategy: z.string(),
    baseline_strategy: z.string(),
    pass_type: z.string(),
    mode: z.string(),
    decision: z.enum(["shadow_candidate", "keep_experiment"]),
    next_status: z.enum(["shadow", "experiment"]),
    reasons: z.array(z.string()).default([]),
  }),
  rollback_plan: z.object({
    should_rollback: z.boolean(),
    target_strategy: z.string().nullable().default(null),
    reasons: z.array(z.string()).default([]),
    steps: z.array(z.string()).default([]),
  }),
  metrics_json: z.record(z.string(), z.unknown()).default({}),
  window_start_utc: z.string().nullable().default(null),
  window_end_utc: z.string().nullable().default(null),
});

export const recommendationStrategyGovernanceOverviewResponseSchema = z.object({
  overview: z.object({
    generated_at_utc: z.string(),
    items: z.array(
      z.object({
        candidate_strategy: z.string(),
        baseline_strategy: z.string(),
        pass_type: z.string(),
        mode: z.string(),
        artifact: recommendationStrategyReviewArtifactResponseSchema,
        warnings: z.array(z.string()).default([]),
      }),
    ),
  }),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const accuracyMetricResponseSchema = z.object({
  log_loss: z.number().nullable(),
  brier_score: z.number().nullable(),
  ece: z.number().nullable(),
  sample_size: z.number().int().nonnegative(),
});

export const accuracySummaryResponseSchema = z.object({
  log_loss: z.number().nullable(),
  brier_score: z.number().nullable(),
  ece: z.number().nullable(),
  sample_size: z.number().int().nonnegative(),
  by_market: z.record(z.string(), accuracyMetricResponseSchema),
  by_competition: z.array(
    accuracyMetricResponseSchema.extend({
      competition_id: z.string(),
      competition_name: z.string(),
    }),
  ),
  calibration_buckets: z.array(
    z.object({
      bucket_start: z.number().min(0).max(1),
      bucket_end: z.number().min(0).max(1),
      average_predicted_probability: z.number().min(0).max(1),
      actual_frequency: z.number().min(0).max(1),
      sample_size: z.number().int().nonnegative(),
    }),
  ),
  error_types: z.array(
    z.object({
      tag: z.string(),
      label: z.string(),
      count: z.number().int().nonnegative(),
      share: z.number().min(0).max(1),
      examples: z.array(z.string()),
    }),
  ),
  model_comparisons: z.array(
    z.object({
      baseline_model_version: z.string(),
      candidate_model_version: z.string(),
      baseline_log_loss: z.number().nullable(),
      candidate_log_loss: z.number().nullable(),
      baseline_brier_score: z.number().nullable(),
      candidate_brier_score: z.number().nullable(),
      calibration_delta: z.number().nullable(),
      sample_size: z.number().int().nonnegative(),
      decision: z.enum(["promote_candidate", "keep_baseline", "needs_review"]),
      reasons: z.array(z.string()),
    }),
  ),
  model_version: z.string(),
  window: z.string(),
  filters: z.object({
    model_version: z.string(),
    competition_id: z.string(),
    market: z.string(),
    window: z.string(),
  }),
  generated_at_utc: z.string(),
  stale: z.boolean(),
});

const providerAuthorizationResponseSchema = z.object({
  provider_name: z.string(),
  status: z.enum(["active", "pending_review", "research_only", "blocked", "expired"]),
  capabilities: z.array(z.string()),
  terms_checked_at_utc: z.string().nullable().default(null),
  commercial_use_allowed: z.boolean(),
  retention_allowed: z.boolean(),
  allowed_use: z.string().default("research_and_development"),
  rate_limit: z.string().nullable().default(null),
  historical_data_allowed: z.boolean().default(false),
  redistribution_allowed: z.boolean().default(false),
  terms_url: z.string().nullable().default(null),
  last_reviewed_at: z.string().nullable().default(null),
  next_review_due_at: z.string().nullable().default(null),
  owner: z.string().default("nutmeg-ops"),
  api_key_env_var: z.string().nullable().default(null),
  notes: z.string().default(""),
});

const providerReadinessResponseSchema = z.object({
  competition_id: z.string(),
  competition_name: z.string(),
  target_stage: z.enum(["beta", "production"]),
  decision: z.enum(["beta_ready", "production_ready", "not_ready"]),
  data_quality: z.object({
    score: z.number().min(0).max(100),
    grade: dataQualityGradeSchema,
    parlay_eligible: z.boolean(),
    components: z.object({
      fixture_reliability: z.number().min(0).max(1),
      odds_coverage: z.number().min(0).max(1),
      lineup_injury_coverage: z.number().min(0).max(1),
      historical_stats_completeness: z.number().min(0).max(1),
      provider_consistency: z.number().min(0).max(1),
      data_freshness: z.number().min(0).max(1),
    }),
    messages: z.array(z.string()).default([]),
  }),
  reasons: z.array(z.string()).default([]),
  beta_ready: z.boolean(),
  production_ready: z.boolean(),
});

export const providerGovernanceResponseSchema = z.object({
  providers: z.array(providerAuthorizationResponseSchema),
  competition_readiness: z.array(providerReadinessResponseSchema),
  model_promotion_review: z.record(z.string(), z.unknown()),
  rollback_plan: z.record(z.string(), z.unknown()),
  generated_at_utc: z.string(),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerRuntimeCredentialResponseSchema = z.object({
  items: z.array(
    z.object({
      provider_name: z.string(),
      capabilities: z.array(z.string()).default([]),
      api_key_env_var: z.string().nullable().default(null),
      runtime_env_var: z.string().nullable().default(null),
      key_configured: z.boolean(),
      dry_run_mode: z.enum(["local_only", "mock_sample", "real_provider", "blocked"]),
      commit_mode: z.enum(["not_applicable", "ready", "blocked"]),
      safe_to_call_real_provider: z.boolean(),
      mock_dry_run_enabled: z.boolean(),
      requires_api_key_for_commit: z.boolean(),
      next_action: z.string(),
      notes: z.array(z.string()).default([]),
    }),
  ),
  mock_dry_run_enabled: z.boolean(),
  generated_at_utc: z.string(),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerRuntimeProbeStatusSchema = z.enum([
  "not_configured",
  "key_configured",
  "ok",
  "limited",
  "auth_failed",
  "rate_limited",
  "unavailable",
  "adapter_planned",
]);

const providerRuntimeMonitorNextActionSchema = z.enum([
  "no_action",
  "configure_runtime_key",
  "review_provider_plan_limit",
  "check_provider_credentials",
  "retry_after_provider_recovery",
  "adapter_not_ready",
]);

const providerRuntimeAlertSeveritySchema = z.enum(["P0", "P1", "P2"]);
const providerRuntimeAlertLevelSchema = z.enum(["ok", "P0", "P1", "P2"]);
const providerRuntimeIncidentStatusSchema = z.enum([
  "open",
  "acknowledged",
  "resolved",
  "ignored",
]);
const providerRuntimeIncidentNotificationStatusSchema = z.enum([
  "not_configured",
  "queued",
  "sent",
  "skipped",
  "failed",
]);

const providerRuntimeMonitoringSnapshotRecordSchema = z.object({
  provider_runtime_snapshot_id: z.number().int().positive().nullable().default(null),
  provider_name: z.string(),
  capability: z.string(),
  probe_status: providerRuntimeProbeStatusSchema,
  key_configured: z.boolean(),
  live_probe: z.boolean(),
  safe_to_call_real_provider: z.boolean(),
  latency_ms: z.number().int().nonnegative().nullable().default(null),
  error_rate: z.number().min(0).max(1).nullable().default(null),
  success_count: z.number().int().nonnegative(),
  failure_count: z.number().int().nonnegative(),
  rate_limit_remaining: z.number().int().nonnegative().nullable().default(null),
  quota_window: z.string().nullable().default(null),
  fallback_used: z.boolean(),
  message: z.string(),
  next_action: providerRuntimeMonitorNextActionSchema,
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  observed_at_utc: z.string(),
});

export const providerRuntimeMonitoringResponseSchema = z.object({
  items: z.array(providerRuntimeMonitoringSnapshotRecordSchema).default([]),
  summary: z.object({
    provider_count: z.number().int().nonnegative(),
    healthy_count: z.number().int().nonnegative(),
    degraded_count: z.number().int().nonnegative(),
    rate_limited_count: z.number().int().nonnegative(),
    auth_failed_count: z.number().int().nonnegative(),
    unavailable_count: z.number().int().nonnegative(),
    not_configured_count: z.number().int().nonnegative(),
    fallback_provider_count: z.number().int().nonnegative(),
    average_latency_ms: z.number().nonnegative().nullable().default(null),
    latest_observed_at_utc: z.string().nullable().default(null),
  }),
  alert_level: providerRuntimeAlertLevelSchema,
  alerts: z
    .array(
      z.object({
        alert_id: z.string(),
        severity: providerRuntimeAlertSeveritySchema,
        provider_name: z.string().nullable().default(null),
        capability: z.string().nullable().default(null),
        metric: z.string(),
        current_value: z.union([z.number(), z.string()]).nullable().default(null),
        threshold: z.union([z.number(), z.string()]).nullable().default(null),
        message: z.string(),
        recommended_action: z.string(),
      }),
    )
    .default([]),
  thresholds: z.object({
    provider_latency_p2_ms: z.number().int().nonnegative(),
    provider_latency_p1_ms: z.number().int().nonnegative(),
    provider_error_rate_p1: z.number().min(0).max(1),
    provider_plan_limit_p2: z.number().min(0).max(1),
    fallback_usage_rate_p1: z.number().min(0).max(1),
  }),
  generated_at_utc: z.string(),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerRuntimeIncidentReportRecordSchema = z.object({
  provider_runtime_incident_report_id: z.number().int().positive(),
  alert_level: providerRuntimeAlertLevelSchema,
  alert_count: z.number().int().nonnegative(),
  snapshot_count: z.number().int().nonnegative(),
  summary_json: z.record(z.string(), z.unknown()).default({}),
  alerts_json: z.array(z.record(z.string(), z.unknown())).default([]),
  thresholds_json: z.record(z.string(), z.unknown()).default({}),
  source: z.string(),
  created_by: z.string(),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  incident_status: providerRuntimeIncidentStatusSchema.default("open"),
  acknowledged_by: z.string().nullable().default(null),
  acknowledged_at_utc: z.string().nullable().default(null),
  resolved_by: z.string().nullable().default(null),
  resolved_at_utc: z.string().nullable().default(null),
  resolution_note: z.string().nullable().default(null),
  notification_status:
    providerRuntimeIncidentNotificationStatusSchema.default("not_configured"),
  notification_payload_json: z.record(z.string(), z.unknown()).default({}),
  updated_at_utc: z.string().nullable().default(null),
  created_at_utc: z.string(),
});

const providerRuntimeIncidentTrendBucketSchema = z.object({
  bucket_date: z.string(),
  total_count: z.number().int().nonnegative().default(0),
  open_count: z.number().int().nonnegative().default(0),
  acknowledged_count: z.number().int().nonnegative().default(0),
  resolved_count: z.number().int().nonnegative().default(0),
  ignored_count: z.number().int().nonnegative().default(0),
  active_count: z.number().int().nonnegative().default(0),
  p0_count: z.number().int().nonnegative().default(0),
  p1_count: z.number().int().nonnegative().default(0),
  p2_count: z.number().int().nonnegative().default(0),
  notification_failed_count: z.number().int().nonnegative().default(0),
});

const providerRuntimeIncidentSummaryResponseDefault = {
  lookback_days: 30,
  total_count: 0,
  open_count: 0,
  acknowledged_count: 0,
  resolved_count: 0,
  ignored_count: 0,
  active_count: 0,
  p0_count: 0,
  p1_count: 0,
  p2_count: 0,
  notification_failed_count: 0,
  latest_created_at_utc: null,
  mean_time_to_resolve_minutes: null,
  trend_buckets: [],
};

const providerRuntimeIncidentSummarySchema = z.object({
  lookback_days: z.number().int().positive().default(30),
  total_count: z.number().int().nonnegative().default(0),
  open_count: z.number().int().nonnegative().default(0),
  acknowledged_count: z.number().int().nonnegative().default(0),
  resolved_count: z.number().int().nonnegative().default(0),
  ignored_count: z.number().int().nonnegative().default(0),
  active_count: z.number().int().nonnegative().default(0),
  p0_count: z.number().int().nonnegative().default(0),
  p1_count: z.number().int().nonnegative().default(0),
  p2_count: z.number().int().nonnegative().default(0),
  notification_failed_count: z.number().int().nonnegative().default(0),
  latest_created_at_utc: z.string().nullable().default(null),
  mean_time_to_resolve_minutes: z.number().nonnegative().nullable().default(null),
  trend_buckets: z.array(providerRuntimeIncidentTrendBucketSchema).default([]),
});

export const providerRuntimeIncidentReportListResponseSchema = z.object({
  items: z.array(providerRuntimeIncidentReportRecordSchema).default([]),
  summary: providerRuntimeIncidentSummarySchema.default(
    providerRuntimeIncidentSummaryResponseDefault,
  ),
  limit: z.number().int().positive().default(10),
  offset: z.number().int().nonnegative().default(0),
  total_count: z.number().int().nonnegative().default(0),
  has_more: z.boolean().default(false),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerRuntimeIncidentStatusUpdateResponseSchema = z.object({
  item: providerRuntimeIncidentReportRecordSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerAuthorizationReviewRecordResponseSchema = z.object({
  provider_authorization_review_id: z.number().int().positive(),
  provider_name: z.string(),
  review_reference: z.string(),
  review_status: z.enum(["approved", "research_only", "needs_review", "blocked"]),
  reviewed_by: z.string(),
  reviewed_at_utc: z.string(),
  terms_url: z.string().nullable().default(null),
  terms_version_hash: z.string().nullable().default(null),
  allowed_use: z.string(),
  commercial_use_allowed: z.boolean(),
  retention_allowed: z.boolean(),
  historical_data_allowed: z.boolean(),
  redistribution_allowed: z.boolean(),
  rate_limit: z.string().nullable().default(null),
  next_review_due_at_utc: z.string().nullable().default(null),
  evidence_json: z.record(z.string(), z.unknown()).default({}),
  notes: z.string().default(""),
  created_at_utc: z.string(),
});

export const providerAuthorizationReviewResponseSchema = z.object({
  item: providerAuthorizationReviewRecordResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerAuthorizationReviewListResponseSchema = z.object({
  items: z.array(providerAuthorizationReviewRecordResponseSchema).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerOpsAuditOutcomeResponseSchema = z.enum(["success", "failure", "blocked"]);

const providerOpsAuditEventRecordResponseSchema = z.object({
  provider_ops_audit_event_id: z.number().int().positive(),
  event_type: z.string(),
  operator_name: z.string().nullable().default(null),
  action_surface: z.string(),
  target_type: z.string().nullable().default(null),
  target_id: z.string().nullable().default(null),
  outcome: providerOpsAuditOutcomeResponseSchema,
  request_path: z.string().nullable().default(null),
  request_method: z.string().nullable().default(null),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  created_at_utc: z.string(),
});

export const providerOpsAuditEventResponseSchema = z.object({
  item: providerOpsAuditEventRecordResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerOpsAuditEventListResponseSchema = z.object({
  items: z.array(providerOpsAuditEventRecordResponseSchema).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerOpsRunStatusResponseSchema = z.enum(["success", "failure", "skipped"]);

const providerOpsRunHistoryRecordResponseSchema = z.object({
  provider_ops_run_id: z.number().int().positive(),
  run_name: z.string(),
  run_type: z.string(),
  source: z.string(),
  status: providerOpsRunStatusResponseSchema,
  operator_name: z.string().nullable().default(null),
  started_at_utc: z.string().nullable().default(null),
  completed_at_utc: z.string().nullable().default(null),
  duration_ms: z.number().int().nonnegative().nullable().default(null),
  exit_code: z.number().int().nullable().default(null),
  summary_json: z.record(z.string(), z.unknown()).default({}),
  output_excerpt: z.string().nullable().default(null),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  created_at_utc: z.string(),
});

export const providerOpsRunHistoryResponseSchema = z.object({
  item: providerOpsRunHistoryRecordResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerOpsRunHistoryListResponseSchema = z.object({
  items: z.array(providerOpsRunHistoryRecordResponseSchema).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerApiKeyChecklistResponseSchema = z.object({
  items: z.array(
    z.object({
      provider_name: z.string(),
      nutmeg_role: z.string(),
      priority: z.number().int().positive(),
      adapter_status: z.enum(["supported_now", "adapter_planned"]),
      required_env_var: z.string(),
      key_configured: z.boolean(),
      apply_url: z.string(),
      docs_url: z.string(),
      official_free_tier_note: z.string(),
      free_tier_fit: z.enum([
        "good_for_first_dry_run",
        "trial_required",
        "limited_for_soccer",
      ]),
      operator_action: z.string(),
      source_checked_at_utc: z.string(),
    }),
  ),
  generated_at_utc: z.string(),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerEntityMappingResponseSchema = z.object({
  mapping_id: z.number().int().positive(),
  provider: z.string(),
  entity_type: z.string(),
  provider_entity_id: z.string(),
  canonical_entity_id: z.string(),
  confidence: z.number().min(0).max(1),
  created_at_utc: z.string(),
  updated_at_utc: z.string(),
});

const providerMappingSummaryResponseSchema = z.object({
  provider: z.string(),
  entity_type: z.string(),
  mapping_count: z.number().int().nonnegative(),
  average_confidence: z.number().min(0).max(1),
  minimum_confidence: z.number().min(0).max(1),
  latest_updated_at_utc: z.string(),
});

export const providerMappingListResponseSchema = z.object({
  items: z.array(providerEntityMappingResponseSchema).default([]),
  summary: z.array(providerMappingSummaryResponseSchema).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerMappingReviewIssueResponseSchema = z.object({
  issue_id: z.string(),
  issue_type: z.enum([
    "low_confidence",
    "same_provider_canonical_collision",
    "stale_mapping",
  ]),
  severity: z.enum(["info", "warning", "critical"]),
  provider: z.string(),
  entity_type: z.string(),
  canonical_entity_id: z.string(),
  provider_entity_ids: z.array(z.string()).default([]),
  mapping_ids: z.array(z.number().int().positive()).default([]),
  confidence_min: z.number().min(0).max(1).nullable().default(null),
  latest_updated_at_utc: z.string().nullable().default(null),
  reasons: z.array(z.string()).default([]),
  recommended_action: z.string(),
});

export const providerMappingReviewResponseSchema = z.object({
  result: z.object({
    dry_run: z.boolean(),
    as_of_time_utc: z.string(),
    checked_mapping_count: z.number().int().nonnegative(),
    issue_count: z.number().int().nonnegative(),
    critical_count: z.number().int().nonnegative(),
    warning_count: z.number().int().nonnegative(),
    info_count: z.number().int().nonnegative(),
    issues: z.array(providerMappingReviewIssueResponseSchema).default([]),
    metadata_json: z.record(z.string(), z.unknown()).default({}),
  }),
  stored_review: z.record(z.string(), z.unknown()).nullable().default(null),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerTrustedPriorityResponseSchema = z.object({
  provider_name: z.string(),
  capability: z.string(),
  priority_rank: z.number().int().positive(),
  reason: z.string(),
});

const providerConflictStatusResponseSchema = z.enum(["open", "resolved", "ignored"]);

const providerConflictEventResponseSchema = z.object({
  source_issue_id: z.string().nullable().default(null),
  conflict_type: z.enum([
    "provider_mapping_conflict",
    "provider_observation_conflict",
  ]),
  severity: z.enum(["info", "warning", "critical"]),
  entity_type: z.string(),
  canonical_entity_id: z.string(),
  provider_names: z.array(z.string()).default([]),
  provider_entity_ids: z.array(z.string()).default([]),
  trusted_provider: z.string().nullable().default(null),
  data_quality_score_delta: z.number().max(0),
  evidence_json: z.record(z.string(), z.unknown()).default({}),
  recommended_action: z.string(),
});

const providerConflictEventRecordResponseSchema =
  providerConflictEventResponseSchema.extend({
    provider_conflict_event_id: z.number().int().positive(),
    source_review_run_id: z.number().int().positive().nullable().default(null),
    resolution_status: providerConflictStatusResponseSchema,
    requested_by: z.string().nullable().default(null),
    created_at_utc: z.string(),
    resolved_at_utc: z.string().nullable().default(null),
  });

export const providerConflictEvaluationResponseSchema = z.object({
  result: z.object({
    dry_run: z.boolean(),
    as_of_time_utc: z.string(),
    source_review_run_id: z.number().int().positive().nullable().default(null),
    checked_issue_count: z.number().int().nonnegative(),
    conflict_count: z.number().int().nonnegative(),
    critical_count: z.number().int().nonnegative(),
    warning_count: z.number().int().nonnegative(),
    info_count: z.number().int().nonnegative(),
    provider_consistency_after_conflicts: z.number().min(0).max(1),
    data_quality_score_delta: z.number().max(0),
    trusted_priorities: z.array(providerTrustedPriorityResponseSchema).default([]),
    events: z.array(providerConflictEventResponseSchema).default([]),
    metadata_json: z.record(z.string(), z.unknown()).default({}),
  }),
  stored_events: z.array(z.record(z.string(), z.unknown())).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerConflictEventListResponseSchema = z.object({
  items: z.array(providerConflictEventRecordResponseSchema).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerConflictResolutionResponseSchema = z.object({
  item: providerConflictEventRecordResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerSyncWorkflowRunRecordResponseSchema = z.object({
  provider_sync_workflow_run_id: z.number().int().positive(),
  status: z.enum(["running", "completed", "failed"]),
  dry_run: z.boolean(),
  requested_by: z.string().nullable().default(null),
  started_at_utc: z.string(),
  completed_at_utc: z.string().nullable().default(null),
  duration_ms: z.number().int().nonnegative().nullable().default(null),
  fixture_sync_run_id: z.number().int().positive().nullable().default(null),
  odds_sync_run_ids: z.array(z.number().int().positive()).default([]),
  availability_sync_run_ids: z.array(z.number().int().positive()).default([]),
  fixture_count: z.number().int().nonnegative(),
  odds_snapshot_count: z.number().int().nonnegative(),
  availability_snapshot_count: z.number().int().nonnegative(),
  raw_payload_ids: z.array(z.number().int().positive()).default([]),
  canonical_fixture_ids: z.array(z.string()).default([]),
  prematch_workflow_run_id: z.number().int().positive().nullable().default(null),
  warnings: z.array(z.string()).default([]),
  error_message: z.string().nullable().default(null),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

const providerSyncWorkflowPreflightIssueResponseSchema = z.object({
  severity: z.enum(["error", "warning", "info"]),
  code: z.string(),
  message: z.string(),
  field_path: z.string().nullable().default(null),
});

const providerSyncWorkflowPreflightResultResponseSchema = z.object({
  valid: z.boolean(),
  task_count: z.number().int().nonnegative(),
  sync_types: z.array(z.string()).default([]),
  canonical_fixture_ids: z.array(z.string()).default([]),
  issue_count: z.number().int().nonnegative(),
  error_count: z.number().int().nonnegative(),
  warning_count: z.number().int().nonnegative(),
  info_count: z.number().int().nonnegative(),
  issues: z.array(providerSyncWorkflowPreflightIssueResponseSchema).default([]),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

export const providerSyncWorkflowRunListResponseSchema = z.object({
  items: z.array(providerSyncWorkflowRunRecordResponseSchema).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerSyncWorkflowRunDetailResponseSchema = z.object({
  item: providerSyncWorkflowRunRecordResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerSyncWorkflowPreflightResponseSchema = z.object({
  result: providerSyncWorkflowPreflightResultResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerSyncWorkflowRunResponseSchema = z.object({
  result: z.object({
    provider_sync_workflow_run_id: z.number().int().positive().nullable().default(null),
    operator_approval_id: z.number().int().positive().nullable().default(null),
    dry_run: z.boolean(),
    requested_by: z.string().nullable().default(null),
    fixture_count: z.number().int().nonnegative(),
    odds_snapshot_count: z.number().int().nonnegative(),
    availability_snapshot_count: z.number().int().nonnegative(),
    raw_payload_ids: z.array(z.number().int().positive()).default([]),
    canonical_fixture_ids: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
  }),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerSyncWorkflowTemplateRecordResponseSchema = z.object({
  provider_sync_workflow_template_id: z.number().int().positive(),
  template_name: z.string(),
  description: z.string().nullable().default(null),
  dry_run: z.boolean(),
  fixture_sync: z.record(z.string(), z.unknown()).nullable().default(null),
  odds_syncs: z.array(z.record(z.string(), z.unknown())).default([]),
  availability_syncs: z.array(z.record(z.string(), z.unknown())).default([]),
  run_conflict_detection: z.boolean(),
  conflict_observation_lookback_hours: z.number().int().positive(),
  conflict_limit: z.number().int().positive(),
  created_by: z.string().nullable().default(null),
  created_at_utc: z.string(),
  updated_at_utc: z.string(),
  archived_at_utc: z.string().nullable().default(null),
  archived_by: z.string().nullable().default(null),
  archive_reason: z.string().nullable().default(null),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  preflight_result: providerSyncWorkflowPreflightResultResponseSchema,
});

export const providerSyncWorkflowTemplateListResponseSchema = z.object({
  items: z.array(providerSyncWorkflowTemplateRecordResponseSchema).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerSyncWorkflowTemplateResponseSchema = z.object({
  item: providerSyncWorkflowTemplateRecordResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerSyncWorkflowApprovalRecordResponseSchema = z.object({
  provider_sync_workflow_approval_id: z.number().int().positive(),
  approval_type: z.string(),
  approval_status: z.enum(["approved", "superseded", "revoked"]),
  provider_sync_workflow_template_id: z.number().int().positive().nullable().default(null),
  provider_sync_workflow_run_id: z.number().int().positive().nullable().default(null),
  approved_by: z.string().nullable().default(null),
  approved_at_utc: z.string(),
  approval_note: z.string().nullable().default(null),
  request_payload_json: z.record(z.string(), z.unknown()).default({}),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

export const providerSyncWorkflowApprovalListResponseSchema = z.object({
  items: z.array(providerSyncWorkflowApprovalRecordResponseSchema).default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerSyncRunPayloadResponseSchema = z.object({
  provider_sync_run_id: z.number().int().positive(),
  provider_name: z.string(),
  capability: z.string(),
  status: z.enum(["running", "completed", "failed"]),
  started_at: z.string(),
  completed_at: z.string().nullable().default(null),
  duration_ms: z.number().int().nonnegative().nullable().default(null),
  entity_count: z.number().int().nonnegative(),
  error_message: z.string().nullable().default(null),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

export const providerOddsCoverageReportResponseSchema = z.object({
  competition_id: z.string(),
  competition_name: z.string(),
  fixture_count: z.number().int().nonnegative(),
  odds_snapshot_count: z.number().int().nonnegative(),
  bookmaker_count: z.number().int().nonnegative(),
  odds_coverage: z.number().min(0).max(1),
  one_x_two_coverage: z.number().min(0).max(1),
  handicap_coverage: z.number().min(0).max(1),
  fresh_odds_coverage: z.number().min(0).max(1),
  market_types: z.array(z.string()).default([]),
  generated_at_utc: z.string(),
});

export const providerOddsCoverageResponseSchema = z.object({
  report: providerOddsCoverageReportResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerOddsCoverageGapIssueResponseSchema = z.enum([
  "no_odds",
  "missing_market",
  "stale_odds",
  "unmapped",
  "provider_event_unavailable",
]);

const providerOddsCoverageFallbackCandidateResponseSchema = z.object({
  provider_name: z.string(),
  coverage_role: z.string(),
  adapter_status: z.enum(["supported_now", "adapter_planned"]),
  required_env_var: z.string(),
  recommended_action: z.string(),
});

export const providerOddsCoverageGapItemResponseSchema = z.object({
  fixture_id: z.string(),
  competition_id: z.string(),
  competition_name: z.string(),
  kickoff_time_utc: z.string(),
  home_team_name: z.string(),
  away_team_name: z.string(),
  issue_types: z.array(providerOddsCoverageGapIssueResponseSchema).default([]),
  recommended_action: z.string(),
  odds_snapshot_count: z.number().int().nonnegative(),
  bookmaker_count: z.number().int().nonnegative(),
  has_1x2: z.boolean(),
  has_handicap: z.boolean(),
  fresh_enough: z.boolean(),
  latest_snapshot_time_utc: z.string().nullable().default(null),
  latest_snapshot_lag_hours: z.number().nonnegative().nullable().default(null),
  market_types: z.array(z.string()).default([]),
  has_provider_mapping: z.boolean(),
  provider: z.string(),
  provider_event_id: z.string().nullable().default(null),
  provider_mapping_id: z.number().int().positive().nullable().default(null),
  provider_mapping_confidence: z.number().min(0).max(1).nullable().default(null),
  provider_mapping_updated_at_utc: z.string().nullable().default(null),
  event_availability_note: z.string().nullable().default(null),
  fallback_candidates: z
    .array(providerOddsCoverageFallbackCandidateResponseSchema)
    .default([]),
});

export const providerOddsCoverageGapReportResponseSchema = z.object({
  competition_id: z.string(),
  competition_name: z.string(),
  provider: z.string(),
  window_start_utc: z.string(),
  as_of_time_utc: z.string(),
  max_snapshot_lag_hours: z.number().int().positive(),
  fixture_count: z.number().int().nonnegative(),
  gap_count: z.number().int().nonnegative(),
  no_odds_count: z.number().int().nonnegative(),
  stale_odds_count: z.number().int().nonnegative(),
  provider_event_unavailable_count: z.number().int().nonnegative().default(0),
  missing_1x2_count: z.number().int().nonnegative(),
  missing_handicap_count: z.number().int().nonnegative(),
  unmapped_fixture_count: z.number().int().nonnegative(),
  mapped_gap_count: z.number().int().nonnegative(),
  items: z.array(providerOddsCoverageGapItemResponseSchema).default([]),
  generated_at_utc: z.string(),
});

export const providerOddsCoverageGapResponseSchema = z.object({
  report: providerOddsCoverageGapReportResponseSchema,
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const providerFallbackOddsProbeStatusResponseSchema = z.enum([
  "mapping_missing",
  "mapped_probe_ready",
  "covered",
  "mapped_no_supported_odds",
  "not_configured",
  "provider_auth_failed",
  "provider_limited",
  "provider_rate_limited",
  "provider_unavailable",
  "adapter_planned",
]);

const providerSportMonksFallbackOddsProbeItemResponseSchema = z.object({
  fixture_id: z.string(),
  competition_id: z.string(),
  kickoff_time_utc: z.string(),
  home_team_name: z.string(),
  away_team_name: z.string(),
  primary_provider: z.string(),
  fallback_provider: z.string(),
  status: providerFallbackOddsProbeStatusResponseSchema,
  can_recover_gap: z.boolean(),
  provider_fixture_id: z.string().nullable().default(null),
  provider_mapping_id: z.number().int().positive().nullable().default(null),
  provider_mapping_confidence: z.number().min(0).max(1).nullable().default(null),
  provider_key_configured: z.boolean(),
  live_provider_probe: z.boolean(),
  normalized_odds_count: z.number().int().nonnegative(),
  bookmaker_count: z.number().int().nonnegative(),
  market_types: z.array(z.string()).default([]),
  warnings: z.array(z.string()).default([]),
  recommended_action: z.string(),
});

export const providerSportMonksFallbackOddsProbeResponseSchema = z.object({
  result: z.object({
    competition_id: z.string(),
    primary_provider: z.string(),
    fallback_provider: z.string(),
    live_provider_probe: z.boolean(),
    provider_key_configured: z.boolean(),
    checked_gap_count: z.number().int().nonnegative(),
    provider_event_unavailable_count: z.number().int().nonnegative(),
    mapped_fallback_count: z.number().int().nonnegative(),
    probed_fixture_count: z.number().int().nonnegative(),
    recoverable_fixture_count: z.number().int().nonnegative(),
    normalized_odds_count: z.number().int().nonnegative(),
    bookmaker_count: z.number().int().nonnegative(),
    market_types: z.array(z.string()).default([]),
    items: z.array(providerSportMonksFallbackOddsProbeItemResponseSchema).default([]),
    warnings: z.array(z.string()).default([]),
    generated_at_utc: z.string(),
  }),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export const providerMappedEventOddsSyncResponseSchema = z.object({
  result: z.object({
    provider_name: z.string(),
    sport_key: z.string(),
    canonical_competition_id: z.string(),
    dry_run: z.boolean(),
    mapping_count: z.number().int().nonnegative(),
    fetched_event_count: z.number().int().nonnegative(),
    synced_event_count: z.number().int().nonnegative(),
    normalized_odds_count: z.number().int().nonnegative(),
    odds_snapshot_count: z.number().int().nonnegative(),
    inserted_snapshot_count: z.number().int().nonnegative().default(0),
    updated_snapshot_count: z.number().int().nonnegative().default(0),
    bookmaker_count: z.number().int().nonnegative(),
    market_types: z.array(z.string()).default([]),
    sync_run: providerSyncRunPayloadResponseSchema.nullable().default(null),
    warnings: z.array(z.string()).default([]),
  }),
  coverage: providerOddsCoverageReportResponseSchema.nullable().default(null),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

const predictionJobTypeSchema = z.enum([
  "mock_prematch_predictions",
  "canonical_prematch_predictions",
]);

const predictionJobRunStatusSchema = z.enum(["running", "completed", "failed"]);

const predictionJobRunRecordResponseSchema = z.object({
  prediction_job_run_id: z.number().int().positive(),
  job_type: predictionJobTypeSchema,
  status: predictionJobRunStatusSchema,
  dry_run: z.boolean(),
  requested_by: z.string().nullable().default(null),
  started_at_utc: z.string(),
  completed_at_utc: z.string().nullable().default(null),
  duration_ms: z.number().int().nonnegative().nullable().default(null),
  fixture_count: z.number().int().nonnegative(),
  generated_count: z.number().int().nonnegative(),
  feature_snapshot_ids: z.record(z.string(), z.number().int().positive()).default({}),
  prediction_snapshot_ids: z.record(z.string(), z.number().int().positive()).default({}),
  score_grid_ids: z.record(z.string(), z.number().int().positive()).default({}),
  data_quality_scores: z.record(z.string(), z.number().min(0).max(100)).default({}),
  skipped_fixture_ids: z.array(z.string()).default([]),
  warnings: z.array(z.string()).default([]),
  error_message: z.string().nullable().default(null),
});

export const predictionJobRunListResponseSchema = z.object({
  items: z.array(predictionJobRunRecordResponseSchema).default([]),
});

export const predictionJobRunResponseSchema = z.object({
  prediction_job_run_id: z.number().int().positive().nullable().default(null),
  job_type: predictionJobTypeSchema,
  status: z.literal("completed"),
  dry_run: z.boolean(),
  requested_by: z.string().nullable().default(null),
  started_at_utc: z.string().nullable().default(null),
  completed_at_utc: z.string().nullable().default(null),
  duration_ms: z.number().int().nonnegative().nullable().default(null),
  prediction_time_utc: z.string(),
  fixture_count: z.number().int().nonnegative(),
  generated_count: z.number().int().nonnegative(),
  feature_snapshot_ids: z.record(z.string(), z.number().int().positive()).default({}),
  prediction_snapshot_ids: z.record(z.string(), z.number().int().positive()).default({}),
  score_grid_ids: z.record(z.string(), z.number().int().positive()).default({}),
  data_quality_scores: z.record(z.string(), z.number().min(0).max(100)).default({}),
  skipped_fixture_ids: z.array(z.string()).default([]),
  warnings: z.array(z.string()).default([]),
});

export const providerOnboardingAssessmentListResponseSchema = z.object({
  items: z
    .array(
      z.object({
        assessment: providerReadinessResponseSchema,
        stored_assessment: z.object({
          assessment_id: z.number().int().positive(),
          created_at_utc: z.string(),
        }),
      }),
    )
    .default([]),
  stale: z.boolean(),
  fallback_used: z.boolean(),
});

export type FixturePredictionResponse = z.infer<typeof fixturePredictionResponseSchema>;
export type UpsetListItemResponse = z.infer<typeof upsetListResponseSchema>["items"][number];
export type ParlayTicketResponse = z.infer<typeof parlayRecommendResponseSchema>["items"][number];
export type RecommendationGenerateResponse = z.infer<
  typeof recommendationGenerateResponseSchema
>;
export type RecommendationGlobalPlannerResponse = z.infer<
  typeof recommendationGlobalPlannerResponseSchema
>;
export type RecommendationAnswerResponse = RecommendationGenerateResponse["answer"];
export type RecommendationAnswerSetResponse = NonNullable<
  RecommendationGenerateResponse["answer_set"]
>;
export type RecommendationLifecycleResponse = z.infer<typeof recommendationLifecycleResponseSchema>;
export type RecommendationStrategyGovernanceOverviewResponse = z.infer<
  typeof recommendationStrategyGovernanceOverviewResponseSchema
>;
export type AccuracySummaryResponse = z.infer<typeof accuracySummaryResponseSchema>;
export type ProviderGovernanceResponse = z.infer<typeof providerGovernanceResponseSchema>;
export type ProviderAuthorizationReviewResponse = z.infer<
  typeof providerAuthorizationReviewResponseSchema
>;
export type ProviderAuthorizationReviewListResponse = z.infer<
  typeof providerAuthorizationReviewListResponseSchema
>;
export type ProviderOpsAuditEventResponse = z.infer<
  typeof providerOpsAuditEventResponseSchema
>;
export type ProviderOpsAuditEventListResponse = z.infer<
  typeof providerOpsAuditEventListResponseSchema
>;
export type ProviderOpsRunHistoryResponse = z.infer<
  typeof providerOpsRunHistoryResponseSchema
>;
export type ProviderOpsRunHistoryListResponse = z.infer<
  typeof providerOpsRunHistoryListResponseSchema
>;
export type ProviderRuntimeCredentialResponse = z.infer<
  typeof providerRuntimeCredentialResponseSchema
>;
export type ProviderRuntimeMonitoringResponse = z.infer<
  typeof providerRuntimeMonitoringResponseSchema
>;
export type ProviderRuntimeIncidentReportListResponse = z.infer<
  typeof providerRuntimeIncidentReportListResponseSchema
>;
export type ProviderRuntimeIncidentStatusUpdateResponse = z.infer<
  typeof providerRuntimeIncidentStatusUpdateResponseSchema
>;
export type ProviderApiKeyChecklistResponse = z.infer<
  typeof providerApiKeyChecklistResponseSchema
>;
export type ProviderMappingListResponse = z.infer<typeof providerMappingListResponseSchema>;
export type ProviderMappingReviewResponse = z.infer<
  typeof providerMappingReviewResponseSchema
>;
export type ProviderConflictEvaluationResponse = z.infer<
  typeof providerConflictEvaluationResponseSchema
>;
export type ProviderConflictEventListResponse = z.infer<
  typeof providerConflictEventListResponseSchema
>;
export type ProviderConflictResolutionResponse = z.infer<
  typeof providerConflictResolutionResponseSchema
>;
export type ProviderSyncWorkflowRunListResponse = z.infer<
  typeof providerSyncWorkflowRunListResponseSchema
>;
export type ProviderSyncWorkflowRunDetailResponse = z.infer<
  typeof providerSyncWorkflowRunDetailResponseSchema
>;
export type ProviderSyncWorkflowPreflightResponse = z.infer<
  typeof providerSyncWorkflowPreflightResponseSchema
>;
export type ProviderSyncWorkflowRunResponse = z.infer<
  typeof providerSyncWorkflowRunResponseSchema
>;
export type ProviderSyncWorkflowTemplateListResponse = z.infer<
  typeof providerSyncWorkflowTemplateListResponseSchema
>;
export type ProviderSyncWorkflowTemplateResponse = z.infer<
  typeof providerSyncWorkflowTemplateResponseSchema
>;
export type ProviderSyncWorkflowApprovalListResponse = z.infer<
  typeof providerSyncWorkflowApprovalListResponseSchema
>;
export type ProviderMappedEventOddsSyncResponse = z.infer<
  typeof providerMappedEventOddsSyncResponseSchema
>;
export type ProviderOddsCoverageResponse = z.infer<
  typeof providerOddsCoverageResponseSchema
>;
export type ProviderOddsCoverageGapResponse = z.infer<
  typeof providerOddsCoverageGapResponseSchema
>;
export type ProviderSportMonksFallbackOddsProbeResponse = z.infer<
  typeof providerSportMonksFallbackOddsProbeResponseSchema
>;
export type PredictionJobRunListResponse = z.infer<
  typeof predictionJobRunListResponseSchema
>;
export type PredictionJobRunResponse = z.infer<typeof predictionJobRunResponseSchema>;
export type ProviderOnboardingAssessmentListResponse = z.infer<
  typeof providerOnboardingAssessmentListResponseSchema
>;
