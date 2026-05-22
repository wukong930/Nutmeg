import type {
  AccuracySummary,
  CorrectScore,
  MatchPrediction,
  ParlayRecommendation,
  ParlayTicket,
  ProviderOps,
  ProviderRuntimeIncidentFilters,
  RecommendationEngineAnswer,
  RecommendationEngineBundle,
  RecommendationAnswerSet,
  RecommendationLifecycleDetail,
  RecommendationStrategyGovernance,
  ScoreGrid,
} from "@/types/api";
import {
  accuracySummaryResponseSchema,
  fixtureListResponseSchema,
  fixturePredictionResponseSchema,
  parlayRecommendResponseSchema,
  providerConflictEvaluationResponseSchema,
  providerConflictEventListResponseSchema,
  providerAuthorizationReviewListResponseSchema,
  providerApiKeyChecklistResponseSchema,
  providerGovernanceResponseSchema,
  providerMappingListResponseSchema,
  providerMappingReviewResponseSchema,
  providerOddsCoverageGapResponseSchema,
  providerOddsCoverageResponseSchema,
  providerOnboardingAssessmentListResponseSchema,
  providerOpsAuditEventListResponseSchema,
  providerOpsRunHistoryListResponseSchema,
  providerRuntimeIncidentReportListResponseSchema,
  providerRuntimeMonitoringResponseSchema,
  providerSportMonksFallbackOddsProbeResponseSchema,
  predictionJobRunListResponseSchema,
  providerRuntimeCredentialResponseSchema,
  recommendationGenerateResponseSchema,
  recommendationGlobalPlannerResponseSchema,
  recommendationLifecycleResponseSchema,
  recommendationStrategyGovernanceOverviewResponseSchema,
  providerSyncWorkflowApprovalListResponseSchema,
  providerSyncWorkflowRunListResponseSchema,
  providerSyncWorkflowTemplateListResponseSchema,
  upsetListResponseSchema,
  type AccuracySummaryResponse,
  type FixturePredictionResponse,
  type ParlayTicketResponse,
  type ProviderConflictEvaluationResponse,
  type ProviderConflictEventListResponse,
  type ProviderAuthorizationReviewListResponse,
  type ProviderApiKeyChecklistResponse,
  type ProviderGovernanceResponse,
  type ProviderMappingListResponse,
  type ProviderMappingReviewResponse,
  type ProviderOddsCoverageGapResponse,
  type ProviderOddsCoverageResponse,
  type ProviderOnboardingAssessmentListResponse,
  type ProviderOpsAuditEventListResponse,
  type ProviderOpsRunHistoryListResponse,
  type ProviderRuntimeIncidentReportListResponse,
  type ProviderRuntimeMonitoringResponse,
  type ProviderSportMonksFallbackOddsProbeResponse,
  type RecommendationAnswerResponse,
  type RecommendationAnswerSetResponse,
  type RecommendationGlobalPlannerResponse,
  type RecommendationLifecycleResponse,
  type RecommendationStrategyGovernanceOverviewResponse,
  type PredictionJobRunListResponse,
  type ProviderRuntimeCredentialResponse,
  type ProviderSyncWorkflowApprovalListResponse,
  type ProviderSyncWorkflowRunListResponse,
  type ProviderSyncWorkflowTemplateListResponse,
  type UpsetListItemResponse,
} from "@/lib/api-contract";
import {
  accuracySummarySchema,
  matchPredictionSchema,
  parlayTicketSchema,
  providerOpsSchema,
  recommendationStrategyGovernanceSchema,
} from "@/lib/schemas";

const API_BASE_URL =
  process.env.NUTMEG_API_BASE_URL ??
  process.env.NEXT_PUBLIC_NUTMEG_API_BASE_URL ??
  "http://localhost:8000/api/v1";

const providerRuntimeIncidentSummaryFallback: ProviderOps["runtimeIncidents"]["summary"] = {
  lookbackDays: 30,
  totalCount: 0,
  openCount: 0,
  acknowledgedCount: 0,
  resolvedCount: 0,
  ignoredCount: 0,
  activeCount: 0,
  p0Count: 0,
  p1Count: 0,
  p2Count: 0,
  notificationFailedCount: 0,
  latestCreatedAtUtc: null,
  meanTimeToResolveMinutes: null,
  trendBuckets: [],
};

const providerRuntimeIncidentDefaultFilters: ProviderRuntimeIncidentFilters = {
  limit: 20,
  offset: 0,
  lookbackDays: 30,
  incidentStatus: "all",
  alertLevel: "all",
  notificationStatus: "all",
  source: null,
};

const API_TIMEOUT_MS = Number(process.env.NUTMEG_API_TIMEOUT_MS ?? 800);
const FRONTEND_DEV_FALLBACKS_ENABLED = parseBooleanEnv(
  process.env.NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS,
);

export type ParlayTicketRequestOptions = {
  passType?: string;
  strategy?: string;
  unitStake?: number;
  maxBudget?: number;
  allowMultiple?: boolean;
  allowedMarkets?: string[];
  excludeBetaCompetitions?: boolean;
  lockedFixtureIds?: string[];
  lockedCandidates?: RecommendationLockedCandidateRequest[];
  recommendationRunId?: number;
  retentionSource?: string;
};

export type RecommendationLockedCandidateRequest = {
  fixtureId: string;
  marketType?: string;
  outcome?: string;
};

const recommendationBackendMarketTypes = new Set([
  "1x2",
  "cn_handicap_1x2",
  "european_handicap_1x2",
  "correct_score",
]);

export type AccuracySummaryRequestOptions = {
  modelVersion?: string;
  competitionId?: string;
  market?: string;
  window?: string;
};

export type RecommendationStrategyGovernanceRequestOptions = {
  candidateStrategies?: string[];
  baselineStrategy?: string;
  passType?: string;
  mode?: "single" | "multiple";
  minimumSampleSize?: number;
  minimumBaselineSampleSize?: number;
};

export type ProviderOpsRequestOptions = {
  includeAdmin?: boolean;
  runtimeIncidentFilters?: Partial<ProviderRuntimeIncidentFilters>;
};

async function fetchApi<T>(
  path: string,
  schema: { parse: (value: unknown) => T },
  init?: RequestInit,
) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        ...init?.headers,
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      return null;
    }
    return schema.parse(await response.json());
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchAdminApi<T>(
  path: string,
  schema: { parse: (value: unknown) => T },
  init?: RequestInit,
) {
  const adminToken = process.env.NUTMEG_ADMIN_API_TOKEN;
  if (!adminToken) {
    return null;
  }
  return fetchApi(path, schema, {
    ...init,
    headers: {
      "X-Nutmeg-Admin-Token": adminToken,
      ...init?.headers,
    },
  });
}

function toProbabilityItems(set: FixturePredictionResponse["odds_comparison"][string]) {
  return set.items.map((item) => ({
    label: item.label,
    probability: item.model_probability,
    marketProbability: item.market_probability ?? undefined,
    isHighlighted: item.highlighted || undefined,
  }));
}

function tailEventsFromResponse(response: FixturePredictionResponse) {
  const tailMetrics = response.prediction_snapshot.explanation_json.tail_metrics;
  if (!isRecord(tailMetrics)) {
    return [];
  }
  return [
    {
      label: "主队 3+ 球大胜",
      probability: numericValue(tailMetrics.home_win_by_3plus),
    },
    {
      label: "客队 3+ 球大胜",
      probability: numericValue(tailMetrics.away_win_by_3plus),
    },
    {
      label: "任一方 4+ 球",
      probability: numericValue(tailMetrics.any_team_4plus_goals),
    },
  ];
}

function matchFromPredictionResponse(response: FixturePredictionResponse): MatchPrediction {
  const fixture = response.fixture;
  const metadata = response.model_metadata;
  const prediction = response.prediction_snapshot;
  const dataFreshness = metadata.data_freshness;

  return matchPredictionSchema.parse({
    fixtureId: fixture.fixture_id,
    competitionId: fixture.competition_id,
    competitionName: fixture.competition_name,
    kickoffTimeUtc: fixture.kickoff_time_utc,
    homeTeam: {
      teamId: fixture.home_team.team_id,
      name: fixture.home_team.name,
    },
    awayTeam: {
      teamId: fixture.away_team.team_id,
      name: fixture.away_team.name,
    },
    status: metadata.stale ? "stale" : fixture.status,
    modelStatus: "beta",
    modelVersion: metadata.model_version,
    featureVersion: metadata.feature_version,
    calibrationVersion: metadata.calibration_version,
    predictionTimeUtc: metadata.prediction_time_utc,
    dataQualityScore: metadata.data_quality_score,
    dataQualityGrade: metadata.data_quality_grade,
    dataFreshness: dataFreshness
      ? {
          stale: metadata.stale,
          fallbackUsed: metadata.fallback_used,
          oddsAvailable: dataFreshness.odds_available,
          oddsFreshEnough: dataFreshness.odds_fresh_enough,
          oddsMarketTypes: dataFreshness.odds_market_types,
          oddsSnapshotTimeUtc: dataFreshness.odds_snapshot_time_utc,
          oddsSnapshotLagHours: dataFreshness.odds_snapshot_lag_hours,
          lineupAvailable: dataFreshness.lineup_available,
          lineupFreshEnough: dataFreshness.lineup_fresh_enough,
          lineupSnapshotTimeUtc: dataFreshness.lineup_snapshot_time_utc,
          lineupSnapshotLagHours: dataFreshness.lineup_snapshot_lag_hours,
          injuryAvailable: dataFreshness.injury_available,
          injuryFreshEnough: dataFreshness.injury_fresh_enough,
          injurySnapshotTimeUtc: dataFreshness.injury_snapshot_time_utc,
          injurySnapshotLagHours: dataFreshness.injury_snapshot_lag_hours,
          messages: dataFreshness.messages,
        }
      : undefined,
    confidence: prediction.uncertainty,
    oneXTwo: toProbabilityItems(response.odds_comparison["1x2"]),
    cnHandicap: {
      label: response.odds_comparison.cn_handicap_1x2.label,
      items: toProbabilityItems(response.odds_comparison.cn_handicap_1x2),
    },
    asianHandicap: {
      label: response.odds_comparison.asian_handicap.label,
      items: toProbabilityItems(response.odds_comparison.asian_handicap),
    },
    europeanHandicap: {
      label: response.odds_comparison.european_handicap_1x2.label,
      items: toProbabilityItems(response.odds_comparison.european_handicap_1x2),
    },
    correctScores: response.score_top_n.map((score) => ({
      score: `${score.home_goals}-${score.away_goals}`,
      probability: score.probability,
      optionKey: score.option_key,
    })),
    scoreGrid: {
      maxGoals: prediction.score_grid.max_goals,
      grid: prediction.score_grid.grid,
      tailMass: prediction.score_grid.tail_mass,
      lambdaHome: prediction.score_grid.lambda_home,
      lambdaAway: prediction.score_grid.lambda_away,
    },
    tailEvents: tailEventsFromResponse(response),
    upsetAlerts: response.upset_alerts.map((alert) => ({
      type: alert.type,
      label: alert.label,
      targetOutcome: alert.target_outcome,
      favorite: alert.favorite,
      favoriteModelProbability: alert.favorite_model_probability,
      favoriteMarketProbability: alert.favorite_market_probability,
      modelProbability: alert.model_probability,
      marketProbability: alert.market_probability,
      probabilityGap: alert.probability_gap,
      favoriteFragilityScore: alert.favorite_fragility_score,
      riskLevel: alert.risk_level,
      explanations: alert.explanations,
      contributions: alert.contributions.map((item) => ({
        key: item.key,
        label: item.label,
        score: item.score,
        description: item.description,
      })),
      explanationGroups: alert.explanation_groups.map((group) => ({
        title: group.title,
        items: group.items,
      })),
    })),
    keyFactors: response.explanations,
  });
}

function scoreGridFromCorrectScores(
  correctScores: CorrectScore[],
  maxGoals = 4,
  tailMass = 0.08,
): ScoreGrid {
  const grid = Array.from({ length: maxGoals + 1 }, () => Array.from({ length: maxGoals + 1 }, () => 0));
  const usedCells = new Set<string>();

  for (const score of correctScores) {
    const [homeGoals, awayGoals] = score.score.split("-").map(Number);
    if (
      Number.isInteger(homeGoals) &&
      Number.isInteger(awayGoals) &&
      homeGoals <= maxGoals &&
      awayGoals <= maxGoals
    ) {
      grid[homeGoals][awayGoals] = score.probability;
      usedCells.add(`${homeGoals}-${awayGoals}`);
    }
  }

  const knownMass = correctScores.reduce((sum, score) => sum + score.probability, 0);
  const fillableCells = (maxGoals + 1) * (maxGoals + 1) - usedCells.size;
  const residualPerCell = fillableCells > 0 ? Math.max(0, 1 - knownMass - tailMass) / fillableCells : 0;

  for (let homeGoals = 0; homeGoals <= maxGoals; homeGoals += 1) {
    for (let awayGoals = 0; awayGoals <= maxGoals; awayGoals += 1) {
      if (!usedCells.has(`${homeGoals}-${awayGoals}`)) {
        grid[homeGoals][awayGoals] = residualPerCell;
      }
    }
  }

  return {
    maxGoals,
    grid,
    tailMass,
    lambdaHome: null,
    lambdaAway: null,
  };
}

function upsetFromResponse(alert: UpsetListItemResponse) {
  return {
    type: alert.type,
    label: alert.label,
    targetOutcome: alert.target_outcome,
    favorite: alert.favorite,
    favoriteModelProbability: alert.favorite_model_probability,
    favoriteMarketProbability: alert.favorite_market_probability,
    modelProbability: alert.model_probability,
    marketProbability: alert.market_probability,
    probabilityGap: alert.probability_gap,
    favoriteFragilityScore: alert.favorite_fragility_score,
    riskLevel: alert.risk_level,
    explanations: alert.explanations,
    contributions: alert.contributions.map((item) => ({
      key: item.key,
      label: item.label,
      score: item.score,
      description: item.description,
    })),
    explanationGroups: alert.explanation_groups.map((group) => ({
      title: group.title,
      items: group.items,
    })),
    fixtureId: alert.fixture_id,
    matchLabel: alert.match_label,
    competitionName: alert.competition_name,
    kickoffTimeUtc: alert.kickoff_time_utc,
    dataQualityScore: alert.data_quality_score,
    dataQualityGrade: alert.data_quality_grade,
    modelVersion: alert.model_version,
    predictionTimeUtc: alert.prediction_time_utc,
  };
}

function parlayFromResponse(ticket: ParlayTicketResponse): ParlayTicket {
  return parlayTicketSchema.parse({
    recommendationId: ticket.recommendation_id,
    strategy: ticket.strategy,
    passType: ticket.pass_type,
    isMultiple: ticket.is_multiple,
    legs: ticket.legs.map((leg) => ({
      fixtureId: leg.fixture_id,
      matchLabel: leg.match_label,
      market: leg.market,
      outcomes: leg.outcomes,
    })),
    atomicBetCount: ticket.atomic_bet_count,
    unitStake: ticket.unit_stake,
    totalStake: ticket.total_stake,
    hitProbability: ticket.hit_probability,
    expectedPayout: ticket.expected_payout,
    ev: ticket.ev,
    roi: ticket.roi,
    riskLevel: ticket.risk_level,
    riskScore: ticket.risk_score,
    correlationPenalty: ticket.correlation_penalty,
    ruleValid: ticket.rule_valid,
    explanations: ticket.explanations,
    explanationJson: ticket.explanation_json,
    atomicBets: ticket.atomic_bets.map((atomicBet) => ({
      legs: atomicBet.legs.map((leg) => ({
        fixtureId: leg.fixture_id,
        marketType: leg.market_type,
        outcome: leg.outcome,
        probability: leg.probability,
        odds: leg.odds,
        line: leg.line,
      })),
      stake: atomicBet.stake,
      probability: atomicBet.probability,
      oddsProduct: atomicBet.odds_product,
      expectedPayout: atomicBet.expected_payout,
      expectedValue: atomicBet.expected_value,
      roi: atomicBet.roi,
    })),
  });
}

function recommendationAnswerFromResponse(
  answer: RecommendationAnswerResponse,
  flags: {
    stale: boolean;
    fallbackUsed: boolean;
  },
): RecommendationEngineAnswer {
  return {
    status: answer.status,
    generatedAtUtc: answer.generated_at_utc,
    passType: answer.pass_type,
    mode: answer.mode,
    isMultiple: answer.is_multiple,
    fixtureCount: answer.fixture_count,
    legs: answer.legs.map((leg) => ({
      fixtureId: leg.fixture_id,
      marketType: leg.market_type,
      outcomes: leg.outcomes,
      probability: leg.probability,
      decimalOdds: leg.decimal_odds,
      line: leg.line,
      side: leg.side,
      dataQualityScore: leg.data_quality_score,
      modelVersion: leg.model_version,
      predictionSnapshotId: leg.prediction_snapshot_id,
      predictionTimeUtc: leg.prediction_time_utc,
      kickoffTimeUtc: leg.kickoff_time_utc,
      recommendationScore: leg.recommendation_score,
    })),
    budget: answer.budget
      ? {
          unitStake: answer.budget.unit_stake,
          totalStake: answer.budget.total_stake,
          maxBudget: answer.budget.max_budget,
          withinBudget: answer.budget.within_budget,
        }
      : null,
    atomicBetCount: answer.atomic_bet_count,
    hitProbability: answer.hit_probability,
    expectedPayout: answer.expected_payout,
    expectedValue: answer.expected_value,
    roi: answer.roi,
    riskScore: answer.risk_score,
    riskLevel: answer.risk_level,
    ruleValid: answer.rule_valid,
    averageDataQualityScore: answer.average_data_quality_score,
    dataQualityGrade: answer.data_quality_grade,
    warnings: answer.warnings,
    stale: flags.stale,
    fallbackUsed: flags.fallbackUsed,
  };
}

function recommendationAnswerFromGlobalResponse(
  answer: RecommendationGlobalPlannerResponse["answer"],
  flags: {
    stale: boolean;
    fallbackUsed: boolean;
  },
): RecommendationEngineAnswer {
  return recommendationAnswerFromResponse(answer, flags);
}

function recommendationLifecycleFromResponse(
  response: RecommendationLifecycleResponse,
): RecommendationLifecycleDetail {
  return {
    run: {
      recommendationRunId: response.detail.run.recommendation_run_id,
      runKey: response.detail.run.run_key,
      status: response.detail.run.status,
      selectedFixtureIds: response.detail.run.selected_fixture_ids,
      lockedFixtureIds: response.detail.run.locked_fixture_ids,
      createdAt: response.detail.run.created_at,
    },
    lockedLegs: response.detail.locked_legs.map((leg) => ({
      recommendationLockedLegId: leg.recommendation_locked_leg_id,
      recommendationRunId: leg.recommendation_run_id,
      fixtureId: leg.fixture_id,
      marketType: leg.market_type,
      outcome: leg.outcome,
      lockedAtUtc: leg.locked_at_utc,
      status: leg.status,
      metadataJson: leg.metadata_json,
    })),
    events: response.detail.events.map((event) => ({
      recommendationLifecycleEventId: event.recommendation_lifecycle_event_id,
      recommendationRunId: event.recommendation_run_id,
      recommendationKey: event.recommendation_key,
      fromStatus: event.from_status,
      toStatus: event.to_status,
      reasonCode: event.reason_code,
      eventTimeUtc: event.event_time_utc,
      metadataJson: event.metadata_json,
    })),
    stale: response.stale,
    fallbackUsed: response.fallback_used,
  };
}

function recommendationStrategyEvidenceFromResponse(
  evidence: RecommendationStrategyGovernanceOverviewResponse["overview"]["items"][number]["artifact"]["candidate_evidence"],
) {
  return {
    strategy: evidence.strategy,
    passType: evidence.pass_type,
    mode: evidence.mode,
    sampleSize: evidence.sample_size,
    settledRunCount: evidence.settled_run_count,
    hitCount: evidence.hit_count,
    totalStake: evidence.total_stake,
    grossPayout: evidence.gross_payout,
    profitLoss: evidence.profit_loss,
    roi: evidence.roi,
    hitRate: evidence.hit_rate,
    averageExpectedRoi: evidence.average_expected_roi,
    averageExpectedHitProbability: evidence.average_expected_hit_probability,
    averageHitCalibrationError: evidence.average_hit_calibration_error,
    meanAbsoluteHitCalibrationError: evidence.mean_absolute_hit_calibration_error,
    firstEvaluationTimeUtc: evidence.first_evaluation_time_utc,
    lastEvaluationTimeUtc: evidence.last_evaluation_time_utc,
  };
}

function recommendationStrategyGovernanceFromResponse(
  response: RecommendationStrategyGovernanceOverviewResponse,
): RecommendationStrategyGovernance {
  return recommendationStrategyGovernanceSchema.parse({
    generatedAtUtc: response.overview.generated_at_utc,
    items: response.overview.items.map((item) => {
      const metrics = isRecord(item.artifact.metrics_json)
        ? item.artifact.metrics_json
        : {};
      const deltas = isRecord(metrics.deltas) ? metrics.deltas : {};
      return {
        candidateStrategy: item.candidate_strategy,
        baselineStrategy: item.baseline_strategy,
        passType: item.pass_type,
        mode: item.mode,
        candidateEvidence: recommendationStrategyEvidenceFromResponse(
          item.artifact.candidate_evidence,
        ),
        baselineEvidence: recommendationStrategyEvidenceFromResponse(
          item.artifact.baseline_evidence,
        ),
        decision: item.artifact.promotion_review.decision,
        nextStatus: item.artifact.promotion_review.next_status,
        reasons: item.artifact.promotion_review.reasons,
        shouldRollback: item.artifact.rollback_plan.should_rollback,
        rollbackTargetStrategy: item.artifact.rollback_plan.target_strategy,
        rollbackReasons: item.artifact.rollback_plan.reasons,
        metricDeltas: {
          roiDelta: optionalNumericValue(deltas.roi_delta),
          hitRateDelta: optionalNumericValue(deltas.hit_rate_delta),
          calibrationErrorDelta: optionalNumericValue(
            deltas.mean_absolute_hit_calibration_error_delta,
          ),
          expectedRoiDelta: optionalNumericValue(deltas.expected_roi_delta),
        },
        warnings: item.warnings,
      };
    }),
    stale: response.stale,
    fallbackUsed: response.fallback_used,
  });
}

function accuracyMetricFromResponse(metric: AccuracySummaryResponse["by_market"][string]) {
  return {
    logLoss: metric.log_loss,
    brierScore: metric.brier_score,
    ece: metric.ece,
    sampleSize: metric.sample_size,
  };
}

function accuracyFromResponse(response: AccuracySummaryResponse): AccuracySummary {
  return accuracySummarySchema.parse({
    logLoss: response.log_loss,
    brierScore: response.brier_score,
    ece: response.ece,
    sampleSize: response.sample_size,
    byMarket: Object.fromEntries(
      Object.entries(response.by_market).map(([key, metrics]) => [
        key,
        accuracyMetricFromResponse(metrics),
      ]),
    ),
    byCompetition: response.by_competition.map((item) => ({
      competitionId: item.competition_id,
      competitionName: item.competition_name,
      logLoss: item.log_loss,
      brierScore: item.brier_score,
      ece: item.ece,
      sampleSize: item.sample_size,
    })),
    calibrationBuckets: response.calibration_buckets.map((bucket) => ({
      bucketStart: bucket.bucket_start,
      bucketEnd: bucket.bucket_end,
      averagePredictedProbability: bucket.average_predicted_probability,
      actualFrequency: bucket.actual_frequency,
      sampleSize: bucket.sample_size,
    })),
    errorTypes: response.error_types.map((error) => ({
      tag: error.tag,
      label: error.label,
      count: error.count,
      share: error.share,
      examples: error.examples,
    })),
    modelComparisons: response.model_comparisons.map((comparison) => ({
      baselineModelVersion: comparison.baseline_model_version,
      candidateModelVersion: comparison.candidate_model_version,
      baselineLogLoss: comparison.baseline_log_loss,
      candidateLogLoss: comparison.candidate_log_loss,
      baselineBrierScore: comparison.baseline_brier_score,
      candidateBrierScore: comparison.candidate_brier_score,
      calibrationDelta: comparison.calibration_delta,
      sampleSize: comparison.sample_size,
      decision: comparison.decision,
      reasons: comparison.reasons,
    })),
    modelVersion: response.model_version,
    window: response.window,
    filters: {
      modelVersion: response.filters.model_version,
      competitionId: response.filters.competition_id,
      market: response.filters.market,
      window: response.filters.window,
    },
    generatedAtUtc: response.generated_at_utc,
    stale: response.stale,
  });
}

function providerReadinessFromResponse(
  item: ProviderGovernanceResponse["competition_readiness"][number],
) {
  return {
    competitionId: item.competition_id,
    competitionName: item.competition_name,
    targetStage: item.target_stage,
    decision: item.decision,
    dataQuality: {
      score: item.data_quality.score,
      grade: item.data_quality.grade,
      parlayEligible: item.data_quality.parlay_eligible,
      components: {
        fixtureReliability: item.data_quality.components.fixture_reliability,
        oddsCoverage: item.data_quality.components.odds_coverage,
        lineupInjuryCoverage: item.data_quality.components.lineup_injury_coverage,
        historicalStatsCompleteness:
          item.data_quality.components.historical_stats_completeness,
        providerConsistency: item.data_quality.components.provider_consistency,
        dataFreshness: item.data_quality.components.data_freshness,
      },
      messages: item.data_quality.messages,
    },
    reasons: item.reasons,
    betaReady: item.beta_ready,
    productionReady: item.production_ready,
  };
}

function runtimeCredentialItemsFromResponse(
  runtimeCredentials: ProviderRuntimeCredentialResponse | null,
  governance: ProviderGovernanceResponse,
): ProviderOps["runtimeCredentials"]["items"] {
  if (runtimeCredentials !== null) {
    return runtimeCredentials.items.map((item) => ({
      providerName: item.provider_name,
      capabilities: item.capabilities,
      apiKeyEnvVar: item.api_key_env_var,
      runtimeEnvVar: item.runtime_env_var,
      keyConfigured: item.key_configured,
      dryRunMode: item.dry_run_mode,
      commitMode: item.commit_mode,
      safeToCallRealProvider: item.safe_to_call_real_provider,
      mockDryRunEnabled: item.mock_dry_run_enabled,
      requiresApiKeyForCommit: item.requires_api_key_for_commit,
      nextAction: item.next_action,
      notes: item.notes,
    }));
  }
  return governance.providers.map((provider) => ({
    providerName: provider.provider_name,
    capabilities: provider.capabilities,
    apiKeyEnvVar: provider.api_key_env_var,
    runtimeEnvVar:
      provider.api_key_env_var === null ? null : `NUTMEG_${provider.api_key_env_var}`,
    keyConfigured: provider.api_key_env_var === null,
    dryRunMode:
      provider.api_key_env_var === null ? ("local_only" as const) : ("mock_sample" as const),
    commitMode:
      provider.api_key_env_var === null ? ("not_applicable" as const) : ("blocked" as const),
    safeToCallRealProvider: false,
    mockDryRunEnabled: true,
    requiresApiKeyForCommit: provider.api_key_env_var !== null,
    nextAction:
      provider.api_key_env_var === null
        ? "available_for_deterministic_local_testing"
        : "apply_api_key_before_real_provider_sync",
    notes:
      provider.api_key_env_var === null
        ? ["deterministic_local_provider", "no_external_request"]
        : ["runtime_credentials_unavailable", "secret_value_not_exposed"],
  }));
}

function runtimeMonitoringFromResponse(
  runtimeMonitoring: ProviderRuntimeMonitoringResponse | null,
): ProviderOps["runtimeMonitoring"] {
  if (runtimeMonitoring === null) {
    return providerOpsFallback.runtimeMonitoring;
  }
  return {
    fetched: true,
    generatedAtUtc: runtimeMonitoring.generated_at_utc,
    summary: {
      providerCount: runtimeMonitoring.summary.provider_count,
      healthyCount: runtimeMonitoring.summary.healthy_count,
      degradedCount: runtimeMonitoring.summary.degraded_count,
      rateLimitedCount: runtimeMonitoring.summary.rate_limited_count,
      authFailedCount: runtimeMonitoring.summary.auth_failed_count,
      unavailableCount: runtimeMonitoring.summary.unavailable_count,
      notConfiguredCount: runtimeMonitoring.summary.not_configured_count,
      fallbackProviderCount: runtimeMonitoring.summary.fallback_provider_count,
      averageLatencyMs: runtimeMonitoring.summary.average_latency_ms,
      latestObservedAtUtc: runtimeMonitoring.summary.latest_observed_at_utc,
    },
    alertLevel: runtimeMonitoring.alert_level,
    alerts: runtimeMonitoring.alerts.map((alert) => ({
      alertId: alert.alert_id,
      severity: alert.severity,
      providerName: alert.provider_name,
      capability: alert.capability,
      metric: alert.metric,
      currentValue: alert.current_value,
      threshold: alert.threshold,
      message: alert.message,
      recommendedAction: alert.recommended_action,
    })),
    thresholds: {
      providerLatencyP2Ms: runtimeMonitoring.thresholds.provider_latency_p2_ms,
      providerLatencyP1Ms: runtimeMonitoring.thresholds.provider_latency_p1_ms,
      providerErrorRateP1: runtimeMonitoring.thresholds.provider_error_rate_p1,
      providerPlanLimitP2: runtimeMonitoring.thresholds.provider_plan_limit_p2,
      fallbackUsageRateP1: runtimeMonitoring.thresholds.fallback_usage_rate_p1,
    },
    items: runtimeMonitoring.items.map((item) => ({
      providerRuntimeSnapshotId: item.provider_runtime_snapshot_id,
      providerName: item.provider_name,
      capability: item.capability,
      probeStatus: item.probe_status,
      keyConfigured: item.key_configured,
      liveProbe: item.live_probe,
      safeToCallRealProvider: item.safe_to_call_real_provider,
      latencyMs: item.latency_ms,
      errorRate: item.error_rate,
      successCount: item.success_count,
      failureCount: item.failure_count,
      rateLimitRemaining: item.rate_limit_remaining,
      quotaWindow: item.quota_window,
      fallbackUsed: item.fallback_used,
      message: item.message,
      nextAction: item.next_action,
      metadataJson: item.metadata_json,
      observedAtUtc: item.observed_at_utc,
    })),
    stale: runtimeMonitoring.stale,
    fallbackUsed: runtimeMonitoring.fallback_used,
  };
}

function runtimeIncidentsFromResponse(
  runtimeIncidents: ProviderRuntimeIncidentReportListResponse | null,
  filters: ProviderRuntimeIncidentFilters = providerRuntimeIncidentDefaultFilters,
): ProviderOps["runtimeIncidents"] {
  if (runtimeIncidents === null) {
    return {
      ...providerOpsFallback.runtimeIncidents,
      filters,
      limit: filters.limit,
      offset: filters.offset,
    };
  }
  return {
    fetched: true,
    items: runtimeIncidents.items.map((item) => ({
      providerRuntimeIncidentReportId: item.provider_runtime_incident_report_id,
      alertLevel: item.alert_level,
      alertCount: item.alert_count,
      snapshotCount: item.snapshot_count,
      summaryJson: item.summary_json,
      alertsJson: item.alerts_json,
      thresholdsJson: item.thresholds_json,
      source: item.source,
      createdBy: item.created_by,
      metadataJson: item.metadata_json,
      incidentStatus: item.incident_status,
      acknowledgedBy: item.acknowledged_by,
      acknowledgedAtUtc: item.acknowledged_at_utc,
      resolvedBy: item.resolved_by,
      resolvedAtUtc: item.resolved_at_utc,
      resolutionNote: item.resolution_note,
      notificationStatus: item.notification_status,
      notificationPayloadJson: item.notification_payload_json,
      updatedAtUtc: item.updated_at_utc,
      createdAtUtc: item.created_at_utc,
    })),
    summary: runtimeIncidentSummaryFromResponse(runtimeIncidents.summary),
    filters,
    limit: runtimeIncidents.limit,
    offset: runtimeIncidents.offset,
    totalCount: runtimeIncidents.total_count,
    hasMore: runtimeIncidents.has_more,
    stale: runtimeIncidents.stale,
    fallbackUsed: runtimeIncidents.fallback_used,
  };
}

function runtimeIncidentSummaryFromResponse(
  summary: ProviderRuntimeIncidentReportListResponse["summary"] | null | undefined,
): ProviderOps["runtimeIncidents"]["summary"] {
  if (!summary) {
    return providerRuntimeIncidentSummaryFallback;
  }
  return {
    lookbackDays: summary.lookback_days,
    totalCount: summary.total_count,
    openCount: summary.open_count,
    acknowledgedCount: summary.acknowledged_count,
    resolvedCount: summary.resolved_count,
    ignoredCount: summary.ignored_count,
    activeCount: summary.active_count,
    p0Count: summary.p0_count,
    p1Count: summary.p1_count,
    p2Count: summary.p2_count,
    notificationFailedCount: summary.notification_failed_count,
    latestCreatedAtUtc: summary.latest_created_at_utc,
    meanTimeToResolveMinutes: summary.mean_time_to_resolve_minutes,
    trendBuckets: summary.trend_buckets.map((bucket) => ({
      bucketDate: bucket.bucket_date,
      totalCount: bucket.total_count,
      openCount: bucket.open_count,
      acknowledgedCount: bucket.acknowledged_count,
      resolvedCount: bucket.resolved_count,
      ignoredCount: bucket.ignored_count,
      activeCount: bucket.active_count,
      p0Count: bucket.p0_count,
      p1Count: bucket.p1_count,
      p2Count: bucket.p2_count,
      notificationFailedCount: bucket.notification_failed_count,
    })),
  };
}

function apiKeyChecklistItemsFromResponse(
  checklist: ProviderApiKeyChecklistResponse | null,
): ProviderOps["apiKeyChecklist"]["items"] {
  return (
    checklist?.items.map((item) => ({
      providerName: item.provider_name,
      nutmegRole: item.nutmeg_role,
      priority: item.priority,
      adapterStatus: item.adapter_status,
      requiredEnvVar: item.required_env_var,
      keyConfigured: item.key_configured,
      applyUrl: item.apply_url,
      docsUrl: item.docs_url,
      officialFreeTierNote: item.official_free_tier_note,
      freeTierFit: item.free_tier_fit,
      operatorAction: item.operator_action,
      sourceCheckedAtUtc: item.source_checked_at_utc,
    })) ?? providerOpsFallback.apiKeyChecklist.items
  );
}

function providerOpsFromResponses({
  governance,
  mappings,
  mappingReview,
  conflictEvaluation,
  latestConflicts,
  oddsCoverage,
  oddsGapReport,
  fallbackOddsProbe,
  authorizationReviews,
  providerSyncRuns,
  providerSyncTemplates,
  providerSyncApprovals,
  predictionJobRuns,
  runtimeCredentials,
  runtimeMonitoring,
  runtimeIncidents,
  runtimeIncidentFilters,
  apiKeyChecklist,
  providerOpsAuditEvents,
  providerOpsRunHistory,
  latestAssessments,
}: {
  governance: ProviderGovernanceResponse;
  mappings: ProviderMappingListResponse | null;
  mappingReview: ProviderMappingReviewResponse | null;
  conflictEvaluation: ProviderConflictEvaluationResponse | null;
  latestConflicts: ProviderConflictEventListResponse | null;
  oddsCoverage: ProviderOddsCoverageResponse | null;
  oddsGapReport: ProviderOddsCoverageGapResponse | null;
  fallbackOddsProbe: ProviderSportMonksFallbackOddsProbeResponse | null;
  authorizationReviews: ProviderAuthorizationReviewListResponse | null;
  providerSyncRuns: ProviderSyncWorkflowRunListResponse | null;
  providerSyncTemplates: ProviderSyncWorkflowTemplateListResponse | null;
  providerSyncApprovals: ProviderSyncWorkflowApprovalListResponse | null;
  predictionJobRuns: PredictionJobRunListResponse | null;
  runtimeCredentials: ProviderRuntimeCredentialResponse | null;
  runtimeMonitoring: ProviderRuntimeMonitoringResponse | null;
  runtimeIncidents: ProviderRuntimeIncidentReportListResponse | null;
  runtimeIncidentFilters: ProviderRuntimeIncidentFilters;
  apiKeyChecklist: ProviderApiKeyChecklistResponse | null;
  providerOpsAuditEvents: ProviderOpsAuditEventListResponse | null;
  providerOpsRunHistory: ProviderOpsRunHistoryListResponse | null;
  latestAssessments: ProviderOnboardingAssessmentListResponse | null;
}): ProviderOps {
  const readiness =
    latestAssessments?.items.length
      ? latestAssessments.items.map((item) => providerReadinessFromResponse(item.assessment))
      : governance.competition_readiness.map(providerReadinessFromResponse);
  const persistedEvents =
    latestConflicts?.items.map((event) => providerConflictEventFromResponse(event)) ?? [];
  const predictionRuns =
    predictionJobRuns?.items.map((run) => ({
      predictionJobRunId: run.prediction_job_run_id,
      jobType: run.job_type,
      status: run.status,
      dryRun: run.dry_run,
      requestedBy: run.requested_by,
      startedAtUtc: run.started_at_utc,
      completedAtUtc: run.completed_at_utc,
      durationMs: run.duration_ms,
      fixtureCount: run.fixture_count,
      generatedCount: run.generated_count,
      skippedFixtureIds: run.skipped_fixture_ids,
      warnings: run.warnings,
      errorMessage: run.error_message,
      dataQualityScores: run.data_quality_scores,
    })) ?? providerOpsFallback.predictionQualityGate.runs;

  return providerOpsSchema.parse({
    providers: governance.providers.map((provider) => ({
      providerName: provider.provider_name,
      status: provider.status,
      capabilities: provider.capabilities,
      termsCheckedAtUtc: provider.terms_checked_at_utc,
      commercialUseAllowed: provider.commercial_use_allowed,
      retentionAllowed: provider.retention_allowed,
      allowedUse: provider.allowed_use,
      rateLimit: provider.rate_limit,
      historicalDataAllowed: provider.historical_data_allowed,
      redistributionAllowed: provider.redistribution_allowed,
      termsUrl: provider.terms_url,
      lastReviewedAtUtc: provider.last_reviewed_at,
      nextReviewDueAtUtc: provider.next_review_due_at,
      owner: provider.owner,
      apiKeyEnvVar: provider.api_key_env_var,
      notes: provider.notes,
    })),
    authorizationReviews: {
      fetched: authorizationReviews !== null,
      stale: authorizationReviews?.stale ?? false,
      fallbackUsed: authorizationReviews?.fallback_used ?? authorizationReviews === null,
      items:
        authorizationReviews?.items.map((review) => ({
          providerAuthorizationReviewId: review.provider_authorization_review_id,
          providerName: review.provider_name,
          reviewReference: review.review_reference,
          reviewStatus: review.review_status,
          reviewedBy: review.reviewed_by,
          reviewedAtUtc: review.reviewed_at_utc,
          termsUrl: review.terms_url,
          termsVersionHash: review.terms_version_hash,
          allowedUse: review.allowed_use,
          commercialUseAllowed: review.commercial_use_allowed,
          retentionAllowed: review.retention_allowed,
          historicalDataAllowed: review.historical_data_allowed,
          redistributionAllowed: review.redistribution_allowed,
          rateLimit: review.rate_limit,
          nextReviewDueAtUtc: review.next_review_due_at_utc,
          evidenceJson: review.evidence_json,
          notes: review.notes,
          createdAtUtc: review.created_at_utc,
        })) ?? providerOpsFallback.authorizationReviews.items,
    },
    runtimeCredentials: {
      fetched: runtimeCredentials !== null,
      mockDryRunEnabled: runtimeCredentials?.mock_dry_run_enabled ?? true,
      generatedAtUtc: runtimeCredentials?.generated_at_utc ?? governance.generated_at_utc,
      items: runtimeCredentialItemsFromResponse(runtimeCredentials, governance),
      stale: runtimeCredentials?.stale ?? false,
      fallbackUsed: runtimeCredentials?.fallback_used ?? runtimeCredentials === null,
    },
    runtimeMonitoring: runtimeMonitoringFromResponse(runtimeMonitoring),
    runtimeIncidents: runtimeIncidentsFromResponse(runtimeIncidents, runtimeIncidentFilters),
    apiKeyChecklist: {
      fetched: apiKeyChecklist !== null,
      items: apiKeyChecklistItemsFromResponse(apiKeyChecklist),
      generatedAtUtc: apiKeyChecklist?.generated_at_utc ?? governance.generated_at_utc,
      stale: apiKeyChecklist?.stale ?? false,
      fallbackUsed: apiKeyChecklist?.fallback_used ?? apiKeyChecklist === null,
    },
    auditTrail: {
      fetched: providerOpsAuditEvents !== null,
      items:
        providerOpsAuditEvents?.items.map((event) => ({
          providerOpsAuditEventId: event.provider_ops_audit_event_id,
          eventType: event.event_type,
          operatorName: event.operator_name,
          actionSurface: event.action_surface,
          targetType: event.target_type,
          targetId: event.target_id,
          outcome: event.outcome,
          requestPath: event.request_path,
          requestMethod: event.request_method,
          metadataJson: event.metadata_json,
          createdAtUtc: event.created_at_utc,
        })) ?? providerOpsFallback.auditTrail.items,
      stale: providerOpsAuditEvents?.stale ?? false,
      fallbackUsed: providerOpsAuditEvents?.fallback_used ?? providerOpsAuditEvents === null,
    },
    runHistory: {
      fetched: providerOpsRunHistory !== null,
      items:
        providerOpsRunHistory?.items.map((run) => ({
          providerOpsRunId: run.provider_ops_run_id,
          runName: run.run_name,
          runType: run.run_type,
          source: run.source,
          status: run.status,
          operatorName: run.operator_name,
          startedAtUtc: run.started_at_utc,
          completedAtUtc: run.completed_at_utc,
          durationMs: run.duration_ms,
          exitCode: run.exit_code,
          summaryJson: run.summary_json,
          outputExcerpt: run.output_excerpt,
          metadataJson: run.metadata_json,
          createdAtUtc: run.created_at_utc,
        })) ?? providerOpsFallback.runHistory.items,
      stale: providerOpsRunHistory?.stale ?? false,
      fallbackUsed: providerOpsRunHistory?.fallback_used ?? providerOpsRunHistory === null,
    },
    readiness,
    mappings:
      mappings?.items.map((item) => ({
        mappingId: item.mapping_id,
        provider: item.provider,
        entityType: item.entity_type,
        providerEntityId: item.provider_entity_id,
        canonicalEntityId: item.canonical_entity_id,
        confidence: item.confidence,
        createdAtUtc: item.created_at_utc,
        updatedAtUtc: item.updated_at_utc,
      })) ?? [],
    mappingSummary:
      mappings?.summary.map((item) => ({
        provider: item.provider,
        entityType: item.entity_type,
        mappingCount: item.mapping_count,
        averageConfidence: item.average_confidence,
        minimumConfidence: item.minimum_confidence,
        latestUpdatedAtUtc: item.latest_updated_at_utc,
      })) ?? [],
    mappingReview: {
      dryRun: mappingReview?.result.dry_run ?? true,
      asOfTimeUtc: mappingReview?.result.as_of_time_utc ?? governance.generated_at_utc,
      checkedMappingCount: mappingReview?.result.checked_mapping_count ?? 0,
      issueCount: mappingReview?.result.issue_count ?? 0,
      criticalCount: mappingReview?.result.critical_count ?? 0,
      warningCount: mappingReview?.result.warning_count ?? 0,
      infoCount: mappingReview?.result.info_count ?? 0,
      issues:
        mappingReview?.result.issues.map((issue) => ({
          issueId: issue.issue_id,
          issueType: issue.issue_type,
          severity: issue.severity,
          provider: issue.provider,
          entityType: issue.entity_type,
          canonicalEntityId: issue.canonical_entity_id,
          providerEntityIds: issue.provider_entity_ids,
          mappingIds: issue.mapping_ids,
          confidenceMin: issue.confidence_min,
          latestUpdatedAtUtc: issue.latest_updated_at_utc,
          reasons: issue.reasons,
          recommendedAction: issue.recommended_action,
        })) ?? [],
      stale: mappingReview?.stale ?? false,
      fallbackUsed: mappingReview?.fallback_used ?? false,
    },
    conflictGovernance: {
      dryRun: conflictEvaluation?.result.dry_run ?? true,
      asOfTimeUtc: conflictEvaluation?.result.as_of_time_utc ?? governance.generated_at_utc,
      checkedIssueCount: conflictEvaluation?.result.checked_issue_count ?? 0,
      conflictCount: conflictEvaluation?.result.conflict_count ?? 0,
      criticalCount: conflictEvaluation?.result.critical_count ?? 0,
      warningCount: conflictEvaluation?.result.warning_count ?? 0,
      infoCount: conflictEvaluation?.result.info_count ?? 0,
      providerConsistencyAfterConflicts:
        conflictEvaluation?.result.provider_consistency_after_conflicts ?? 1,
      dataQualityScoreDelta: conflictEvaluation?.result.data_quality_score_delta ?? 0,
      trustedPriorities:
        conflictEvaluation?.result.trusted_priorities.map((priority) => ({
          providerName: priority.provider_name,
          capability: priority.capability,
          priorityRank: priority.priority_rank,
          reason: priority.reason,
        })) ?? [],
      events:
        conflictEvaluation?.result.events.map((event) => ({
          sourceIssueId: event.source_issue_id,
          conflictType: event.conflict_type,
          severity: event.severity,
          entityType: event.entity_type,
          canonicalEntityId: event.canonical_entity_id,
          providerNames: event.provider_names,
          providerEntityIds: event.provider_entity_ids,
          trustedProvider: event.trusted_provider,
          dataQualityScoreDelta: event.data_quality_score_delta,
          evidenceJson: event.evidence_json,
          recommendedAction: event.recommended_action,
        })) ?? [],
      persistedEvents,
      persistedOpenCount: persistedEvents.filter((event) => event.resolutionStatus === "open").length,
      persistedResolvedCount: persistedEvents.filter(
        (event) => event.resolutionStatus === "resolved",
      ).length,
      persistedIgnoredCount: persistedEvents.filter(
        (event) => event.resolutionStatus === "ignored",
      ).length,
      stale: conflictEvaluation?.stale ?? false,
      fallbackUsed: (conflictEvaluation?.fallback_used ?? false) || (latestConflicts?.fallback_used ?? false),
    },
    oddsCoverage: {
      fetched: oddsCoverage !== null,
      competitionId:
        oddsCoverage?.report.competition_id ??
        readiness.find((item) => item.competitionId === "EPL")?.competitionId ??
        readiness[0]?.competitionId ??
        "EPL",
      competitionName:
        oddsCoverage?.report.competition_name ??
        readiness.find((item) => item.competitionId === "EPL")?.competitionName ??
        readiness[0]?.competitionName ??
        "Premier League",
      fixtureCount: oddsCoverage?.report.fixture_count ?? 0,
      oddsSnapshotCount: oddsCoverage?.report.odds_snapshot_count ?? 0,
      bookmakerCount: oddsCoverage?.report.bookmaker_count ?? 0,
      oddsCoverage: oddsCoverage?.report.odds_coverage ?? 0,
      oneXTwoCoverage: oddsCoverage?.report.one_x_two_coverage ?? 0,
      handicapCoverage: oddsCoverage?.report.handicap_coverage ?? 0,
      freshOddsCoverage: oddsCoverage?.report.fresh_odds_coverage ?? 0,
      marketTypes: oddsCoverage?.report.market_types ?? [],
      generatedAtUtc: oddsCoverage?.report.generated_at_utc ?? governance.generated_at_utc,
      stale: oddsCoverage?.stale ?? false,
      fallbackUsed: oddsCoverage?.fallback_used ?? oddsCoverage === null,
    },
    oddsGapReport: {
      fetched: oddsGapReport !== null,
      competitionId:
        oddsGapReport?.report.competition_id ??
        oddsCoverage?.report.competition_id ??
        readiness.find((item) => item.competitionId === "EPL")?.competitionId ??
        readiness[0]?.competitionId ??
        "EPL",
      competitionName:
        oddsGapReport?.report.competition_name ??
        oddsCoverage?.report.competition_name ??
        readiness.find((item) => item.competitionId === "EPL")?.competitionName ??
        readiness[0]?.competitionName ??
        "Premier League",
      provider: oddsGapReport?.report.provider ?? "the-odds-api",
      windowStartUtc:
        oddsGapReport?.report.window_start_utc ?? oddsCoverage?.report.generated_at_utc ?? governance.generated_at_utc,
      asOfTimeUtc:
        oddsGapReport?.report.as_of_time_utc ?? oddsCoverage?.report.generated_at_utc ?? governance.generated_at_utc,
      maxSnapshotLagHours: oddsGapReport?.report.max_snapshot_lag_hours ?? 168,
      fixtureCount:
        oddsGapReport?.report.fixture_count ?? oddsCoverage?.report.fixture_count ?? 0,
      gapCount: oddsGapReport?.report.gap_count ?? 0,
      noOddsCount: oddsGapReport?.report.no_odds_count ?? 0,
      staleOddsCount: oddsGapReport?.report.stale_odds_count ?? 0,
      providerEventUnavailableCount:
        oddsGapReport?.report.provider_event_unavailable_count ?? 0,
      missing1x2Count: oddsGapReport?.report.missing_1x2_count ?? 0,
      missingHandicapCount: oddsGapReport?.report.missing_handicap_count ?? 0,
      unmappedFixtureCount: oddsGapReport?.report.unmapped_fixture_count ?? 0,
      mappedGapCount: oddsGapReport?.report.mapped_gap_count ?? 0,
      items: oddsGapReport?.report.items.map(providerOddsGapFromResponse) ?? [],
      generatedAtUtc:
        oddsGapReport?.report.generated_at_utc ?? oddsCoverage?.report.generated_at_utc ?? governance.generated_at_utc,
      stale: oddsGapReport?.stale ?? false,
      fallbackUsed: oddsGapReport?.fallback_used ?? oddsGapReport === null,
    },
    fallbackOddsProbe: fallbackOddsProbeFromResponse(
      fallbackOddsProbe,
      governance.generated_at_utc,
    ),
    providerSyncWorkflow: {
      fetched: providerSyncRuns !== null,
      runs:
        providerSyncRuns?.items.map((run) => ({
          providerSyncWorkflowRunId: run.provider_sync_workflow_run_id,
          status: run.status,
          dryRun: run.dry_run,
          requestedBy: run.requested_by,
          startedAtUtc: run.started_at_utc,
          completedAtUtc: run.completed_at_utc,
          durationMs: run.duration_ms,
          fixtureSyncRunId: run.fixture_sync_run_id,
          oddsSyncRunIds: run.odds_sync_run_ids,
          availabilitySyncRunIds: run.availability_sync_run_ids,
          fixtureCount: run.fixture_count,
          oddsSnapshotCount: run.odds_snapshot_count,
          availabilitySnapshotCount: run.availability_snapshot_count,
          rawPayloadIds: run.raw_payload_ids,
          canonicalFixtureIds: run.canonical_fixture_ids,
          prematchWorkflowRunId: run.prematch_workflow_run_id,
          warnings: run.warnings,
          errorMessage: run.error_message,
          metadataJson: run.metadata_json,
        })) ?? [],
      templatesFetched: providerSyncTemplates !== null,
      templates:
        providerSyncTemplates?.items.map((template) => ({
          providerSyncWorkflowTemplateId:
            template.provider_sync_workflow_template_id,
          templateName: template.template_name,
          description: template.description,
          dryRun: template.dry_run,
          fixtureSync: template.fixture_sync,
          oddsSyncs: template.odds_syncs,
          availabilitySyncs: template.availability_syncs,
          runConflictDetection: template.run_conflict_detection,
          conflictObservationLookbackHours:
            template.conflict_observation_lookback_hours,
          conflictLimit: template.conflict_limit,
          createdBy: template.created_by,
          createdAtUtc: template.created_at_utc,
          updatedAtUtc: template.updated_at_utc,
          archivedAtUtc: template.archived_at_utc,
          archivedBy: template.archived_by,
          archiveReason: template.archive_reason,
          metadataJson: template.metadata_json,
          preflightResult: {
            valid: template.preflight_result.valid,
            taskCount: template.preflight_result.task_count,
            syncTypes: template.preflight_result.sync_types,
            canonicalFixtureIds: template.preflight_result.canonical_fixture_ids,
            issueCount: template.preflight_result.issue_count,
            errorCount: template.preflight_result.error_count,
            warningCount: template.preflight_result.warning_count,
            infoCount: template.preflight_result.info_count,
            issues: template.preflight_result.issues.map((issue) => ({
              severity: issue.severity,
              code: issue.code,
              message: issue.message,
              fieldPath: issue.field_path,
            })),
            metadataJson: template.preflight_result.metadata_json,
          },
        })) ?? [],
      approvalsFetched: providerSyncApprovals !== null,
      approvals:
        providerSyncApprovals?.items.map((approval) => ({
          providerSyncWorkflowApprovalId:
            approval.provider_sync_workflow_approval_id,
          approvalType: approval.approval_type,
          approvalStatus: approval.approval_status,
          providerSyncWorkflowTemplateId:
            approval.provider_sync_workflow_template_id,
          providerSyncWorkflowRunId: approval.provider_sync_workflow_run_id,
          approvedBy: approval.approved_by,
          approvedAtUtc: approval.approved_at_utc,
          approvalNote: approval.approval_note,
          requestPayloadJson: approval.request_payload_json,
          metadataJson: approval.metadata_json,
        })) ?? [],
      stale:
        (providerSyncRuns?.stale ?? false) ||
        (providerSyncApprovals?.stale ?? false),
      fallbackUsed:
        (providerSyncRuns?.fallback_used ?? false) ||
        (providerSyncTemplates?.fallback_used ?? false) ||
        (providerSyncApprovals?.fallback_used ?? false),
    },
    predictionQualityGate: {
      fetched: predictionJobRuns !== null,
      runs: predictionRuns,
      latestRun: predictionRuns[0] ?? null,
      stale: false,
      fallbackUsed: predictionJobRuns === null,
    },
    latestAssessmentCount: latestAssessments?.items.length ?? 0,
    generatedAtUtc: governance.generated_at_utc,
    stale:
      governance.stale ||
      (mappings?.stale ?? false) ||
      (mappingReview?.stale ?? false) ||
      (conflictEvaluation?.stale ?? false) ||
      (latestConflicts?.stale ?? false) ||
      (oddsCoverage?.stale ?? false) ||
      (oddsGapReport?.stale ?? false) ||
      (fallbackOddsProbe?.stale ?? false) ||
      (authorizationReviews?.stale ?? false) ||
      (providerSyncTemplates?.stale ?? false) ||
      (providerSyncApprovals?.stale ?? false) ||
      (runtimeMonitoring?.stale ?? false) ||
      (runtimeIncidents?.stale ?? false) ||
      (providerOpsAuditEvents?.stale ?? false) ||
      (providerOpsRunHistory?.stale ?? false) ||
      (latestAssessments?.stale ?? false),
    fallbackUsed:
      governance.fallback_used ||
      (mappings?.fallback_used ?? false) ||
      (mappingReview?.fallback_used ?? false) ||
      (conflictEvaluation?.fallback_used ?? false) ||
      (latestConflicts?.fallback_used ?? false) ||
      (oddsCoverage?.fallback_used ?? false) ||
      oddsCoverage === null ||
      (oddsGapReport?.fallback_used ?? false) ||
      oddsGapReport === null ||
      (fallbackOddsProbe?.fallback_used ?? false) ||
      fallbackOddsProbe === null ||
      (authorizationReviews?.fallback_used ?? false) ||
      authorizationReviews === null ||
      (providerSyncTemplates?.fallback_used ?? false) ||
      (providerSyncApprovals?.fallback_used ?? false) ||
      predictionJobRuns === null ||
      (runtimeMonitoring?.fallback_used ?? false) ||
      runtimeMonitoring === null ||
      (runtimeIncidents?.fallback_used ?? false) ||
      runtimeIncidents === null ||
      (providerOpsAuditEvents?.fallback_used ?? false) ||
      (providerOpsRunHistory?.fallback_used ?? false) ||
      (latestAssessments?.fallback_used ?? false),
  });
}

function providerOddsGapFromResponse(
  item: ProviderOddsCoverageGapResponse["report"]["items"][number],
): ProviderOps["oddsGapReport"]["items"][number] {
  return {
    fixtureId: item.fixture_id,
    competitionId: item.competition_id,
    competitionName: item.competition_name,
    kickoffTimeUtc: item.kickoff_time_utc,
    homeTeamName: item.home_team_name,
    awayTeamName: item.away_team_name,
    issueTypes: item.issue_types,
    recommendedAction: item.recommended_action,
    oddsSnapshotCount: item.odds_snapshot_count,
    bookmakerCount: item.bookmaker_count,
    has1x2: item.has_1x2,
    hasHandicap: item.has_handicap,
    freshEnough: item.fresh_enough,
    latestSnapshotTimeUtc: item.latest_snapshot_time_utc,
    latestSnapshotLagHours: item.latest_snapshot_lag_hours,
    marketTypes: item.market_types,
    hasProviderMapping: item.has_provider_mapping,
    provider: item.provider,
    providerEventId: item.provider_event_id,
    providerMappingId: item.provider_mapping_id,
    providerMappingConfidence: item.provider_mapping_confidence,
    providerMappingUpdatedAtUtc: item.provider_mapping_updated_at_utc,
    eventAvailabilityNote: item.event_availability_note,
    fallbackCandidates: item.fallback_candidates.map((candidate) => ({
      providerName: candidate.provider_name,
      coverageRole: candidate.coverage_role,
      adapterStatus: candidate.adapter_status,
      requiredEnvVar: candidate.required_env_var,
      recommendedAction: candidate.recommended_action,
    })),
  };
}

function fallbackOddsProbeFromResponse(
  response: ProviderSportMonksFallbackOddsProbeResponse | null,
  fallbackGeneratedAtUtc: string,
): ProviderOps["fallbackOddsProbe"] {
  if (response === null) {
    return providerOpsFallback.fallbackOddsProbe;
  }
  return {
    fetched: true,
    competitionId: response.result.competition_id,
    primaryProvider: response.result.primary_provider,
    fallbackProvider: response.result.fallback_provider,
    liveProviderProbe: response.result.live_provider_probe,
    providerKeyConfigured: response.result.provider_key_configured,
    checkedGapCount: response.result.checked_gap_count,
    providerEventUnavailableCount:
      response.result.provider_event_unavailable_count,
    mappedFallbackCount: response.result.mapped_fallback_count,
    probedFixtureCount: response.result.probed_fixture_count,
    recoverableFixtureCount: response.result.recoverable_fixture_count,
    normalizedOddsCount: response.result.normalized_odds_count,
    bookmakerCount: response.result.bookmaker_count,
    marketTypes: response.result.market_types,
    items: response.result.items.map((item) => ({
      fixtureId: item.fixture_id,
      competitionId: item.competition_id,
      kickoffTimeUtc: item.kickoff_time_utc,
      homeTeamName: item.home_team_name,
      awayTeamName: item.away_team_name,
      primaryProvider: item.primary_provider,
      fallbackProvider: item.fallback_provider,
      status: item.status,
      canRecoverGap: item.can_recover_gap,
      providerFixtureId: item.provider_fixture_id,
      providerMappingId: item.provider_mapping_id,
      providerMappingConfidence: item.provider_mapping_confidence,
      providerKeyConfigured: item.provider_key_configured,
      liveProviderProbe: item.live_provider_probe,
      normalizedOddsCount: item.normalized_odds_count,
      bookmakerCount: item.bookmaker_count,
      marketTypes: item.market_types,
      warnings: item.warnings,
      recommendedAction: item.recommended_action,
    })),
    warnings: response.result.warnings,
    generatedAtUtc: response.result.generated_at_utc ?? fallbackGeneratedAtUtc,
    stale: response.stale,
    fallbackUsed: response.fallback_used,
  };
}

function providerConflictEventFromResponse(
  event: ProviderConflictEventListResponse["items"][number],
) {
  return {
    providerConflictEventId: event.provider_conflict_event_id,
    sourceReviewRunId: event.source_review_run_id,
    sourceIssueId: event.source_issue_id,
    conflictType: event.conflict_type,
    severity: event.severity,
    entityType: event.entity_type,
    canonicalEntityId: event.canonical_entity_id,
    providerNames: event.provider_names,
    providerEntityIds: event.provider_entity_ids,
    trustedProvider: event.trusted_provider,
    resolutionStatus: event.resolution_status,
    dataQualityScoreDelta: event.data_quality_score_delta,
    evidenceJson: event.evidence_json,
    recommendedAction: event.recommended_action,
    requestedBy: event.requested_by,
    createdAtUtc: event.created_at_utc,
    resolvedAtUtc: event.resolved_at_utc,
  };
}

async function getRemoteMatch(fixtureId: string) {
  const response = await fetchApi(
    `/fixtures/${fixtureId}/prediction`,
    fixturePredictionResponseSchema,
  );
  return response ? matchFromPredictionResponse(response) : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function numericValue(value: unknown) {
  return typeof value === "number" ? value : 0;
}

function optionalNumericValue(value: unknown) {
  return typeof value === "number" ? value : null;
}

const matches: MatchPrediction[] = [
  {
    fixtureId: "fix_epl_001",
    competitionId: "EPL",
    competitionName: "Premier League",
    kickoffTimeUtc: "2026-05-06T19:00:00Z",
    homeTeam: { teamId: "ars", name: "Arsenal" },
    awayTeam: { teamId: "liv", name: "Liverpool" },
    status: "beta",
    modelStatus: "beta",
    modelVersion: "poisson-m1.0.0",
    featureVersion: "features-m1.0.0",
    calibrationVersion: "calibration-m1.0.0",
    predictionTimeUtc: "2026-05-06T12:00:00Z",
    dataQualityScore: 82,
    dataQualityGrade: "B",
    confidence: "medium",
    oneXTwo: [
      { label: "主胜", probability: 0.432, marketProbability: 0.401, isHighlighted: true },
      { label: "平局", probability: 0.279, marketProbability: 0.261 },
      { label: "客胜", probability: 0.289, marketProbability: 0.338 },
    ],
    cnHandicap: {
      label: "主队 -1",
      items: [
        { label: "让胜", probability: 0.214, marketProbability: 0.198 },
        { label: "让平", probability: 0.255, marketProbability: 0.244, isHighlighted: true },
        { label: "让负", probability: 0.531, marketProbability: 0.558 },
      ],
    },
    asianHandicap: {
      label: "主队 -0.25",
      items: [
        { label: "全赢", probability: 0.432 },
        { label: "半赢", probability: 0 },
        { label: "走水", probability: 0 },
        { label: "半输", probability: 0.279 },
        { label: "全输", probability: 0.289 },
      ],
    },
    europeanHandicap: {
      label: "主队 -1",
      items: [
        { label: "让胜", probability: 0.214 },
        { label: "让平", probability: 0.255 },
        { label: "让负", probability: 0.531 },
      ],
    },
    correctScores: [
      { score: "1-1", probability: 0.118, optionKey: "1-1" },
      { score: "1-0", probability: 0.103, optionKey: "1-0" },
      { score: "2-1", probability: 0.095, optionKey: "2-1" },
      { score: "0-0", probability: 0.082, optionKey: "0-0" },
      { score: "0-1", probability: 0.076, optionKey: "0-1" },
    ],
    scoreGrid: scoreGridFromCorrectScores([
      { score: "1-1", probability: 0.118, optionKey: "1-1" },
      { score: "1-0", probability: 0.103, optionKey: "1-0" },
      { score: "2-1", probability: 0.095, optionKey: "2-1" },
      { score: "0-0", probability: 0.082, optionKey: "0-0" },
      { score: "0-1", probability: 0.076, optionKey: "0-1" },
    ]),
    tailEvents: [
      { label: "主队 3+ 球大胜", probability: 0.061 },
      { label: "客队 3+ 球大胜", probability: 0.024 },
      { label: "任一方 4+ 球", probability: 0.013 },
    ],
    upsetAlerts: [
      {
        type: "draw_overlooked",
        label: "平局被低估",
        targetOutcome: "平局",
        favorite: "Arsenal",
        favoriteModelProbability: 0.432,
        favoriteMarketProbability: 0.401,
        modelProbability: 0.279,
        marketProbability: 0.261,
        probabilityGap: 0.018,
        favoriteFragilityScore: 0.58,
        riskLevel: "medium",
        explanations: [
          "模型平局概率高于市场隐含概率。",
          "热门方向优势存在，但一球内分布较集中。",
        ],
      },
    ],
    keyFactors: {
      model: ["Poisson baseline 估计主队期望进球略高。", "比分分布在 1-1、1-0、2-1 附近集中。"],
      market: ["市场主胜隐含概率低于模型估计。", "平局差值为正但幅度有限。"],
      lineup: ["阵容数据质量为 B，关键缺阵信息尚未完全确认。"],
      schedule: ["双方赛程压力处于常规区间。"],
      uncertainty: ["Beta 模型状态，概率需要结合后续校准结果解读。"],
    },
  },
  {
    fixtureId: "fix_epl_002",
    competitionId: "EPL",
    competitionName: "Premier League",
    kickoffTimeUtc: "2026-05-06T21:00:00Z",
    homeTeam: { teamId: "mci", name: "Manchester City" },
    awayTeam: { teamId: "tot", name: "Tottenham Hotspur" },
    status: "scheduled",
    modelStatus: "beta",
    modelVersion: "poisson-m1.0.0",
    featureVersion: "features-m1.0.0",
    calibrationVersion: "calibration-m1.0.0",
    predictionTimeUtc: "2026-05-06T12:05:00Z",
    dataQualityScore: 88,
    dataQualityGrade: "A",
    confidence: "medium",
    oneXTwo: [
      { label: "主胜", probability: 0.512, marketProbability: 0.547 },
      { label: "平局", probability: 0.239, marketProbability: 0.221, isHighlighted: true },
      { label: "客胜", probability: 0.249, marketProbability: 0.232 },
    ],
    cnHandicap: {
      label: "主队 -1",
      items: [
        { label: "让胜", probability: 0.293, marketProbability: 0.328 },
        { label: "让平", probability: 0.241, marketProbability: 0.226 },
        { label: "让负", probability: 0.466, marketProbability: 0.446, isHighlighted: true },
      ],
    },
    asianHandicap: {
      label: "主队 -0.75",
      items: [
        { label: "全赢", probability: 0.293 },
        { label: "半赢", probability: 0.219 },
        { label: "走水", probability: 0 },
        { label: "半输", probability: 0 },
        { label: "全输", probability: 0.488 },
      ],
    },
    europeanHandicap: {
      label: "主队 -1",
      items: [
        { label: "让胜", probability: 0.293 },
        { label: "让平", probability: 0.241 },
        { label: "让负", probability: 0.466 },
      ],
    },
    correctScores: [
      { score: "2-1", probability: 0.102, optionKey: "2-1" },
      { score: "1-1", probability: 0.096, optionKey: "1-1" },
      { score: "2-0", probability: 0.091, optionKey: "2-0" },
      { score: "1-0", probability: 0.084, optionKey: "1-0" },
      { score: "3-1", probability: 0.071, optionKey: "3-1" },
    ],
    scoreGrid: scoreGridFromCorrectScores([
      { score: "2-1", probability: 0.102, optionKey: "2-1" },
      { score: "1-1", probability: 0.096, optionKey: "1-1" },
      { score: "2-0", probability: 0.091, optionKey: "2-0" },
      { score: "1-0", probability: 0.084, optionKey: "1-0" },
      { score: "3-1", probability: 0.071, optionKey: "3-1" },
    ]),
    tailEvents: [
      { label: "主队 3+ 球大胜", probability: 0.104 },
      { label: "客队 3+ 球大胜", probability: 0.019 },
      { label: "任一方 4+ 球", probability: 0.041 },
    ],
    upsetAlerts: [
      {
        type: "favorite_fail_to_cover",
        label: "热门输盘",
        targetOutcome: "让负",
        favorite: "Manchester City",
        favoriteModelProbability: 0.512,
        favoriteMarketProbability: 0.547,
        modelProbability: 0.466,
        marketProbability: 0.446,
        probabilityGap: 0.02,
        favoriteFragilityScore: 0.64,
        riskLevel: "medium_high",
        explanations: [
          "主胜概率较高，但模型认为赢盘概率不足。",
          "一球小胜与平局分布会压低深盘表现。",
        ],
      },
    ],
    keyFactors: {
      model: ["主队胜率最高，但让球盘保护空间有限。"],
      market: ["市场对主队方向更积极，模型差异集中在让负。"],
      lineup: ["核心阵容覆盖较完整，数据质量 A。"],
      schedule: ["近期赛程可能影响强队大胜尾部。"],
      uncertainty: ["让球盘口对单球差距敏感。"],
    },
  },
  {
    fixtureId: "fix_j1_001",
    competitionId: "JPN_J1",
    competitionName: "J1 League",
    kickoffTimeUtc: "2026-05-07T10:00:00Z",
    homeTeam: { teamId: "kaw", name: "Kawasaki Frontale" },
    awayTeam: { teamId: "yfm", name: "Yokohama F. Marinos" },
    status: "beta",
    modelStatus: "beta",
    modelVersion: "poisson-m1.0.0",
    featureVersion: "features-m1.0.0",
    calibrationVersion: "calibration-m1.0.0",
    predictionTimeUtc: "2026-05-06T11:30:00Z",
    dataQualityScore: 66,
    dataQualityGrade: "C",
    confidence: "low",
    oneXTwo: [
      { label: "主胜", probability: 0.356, marketProbability: 0.332 },
      { label: "平局", probability: 0.302, marketProbability: 0.268, isHighlighted: true },
      { label: "客胜", probability: 0.342, marketProbability: 0.4 },
    ],
    cnHandicap: {
      label: "竞彩未开放",
      items: [
        { label: "让胜", probability: 0.356 },
        { label: "让平", probability: 0.302 },
        { label: "让负", probability: 0.342 },
      ],
    },
    asianHandicap: {
      label: "主队 0",
      items: [
        { label: "全赢", probability: 0.356 },
        { label: "半赢", probability: 0 },
        { label: "走水", probability: 0.302 },
        { label: "半输", probability: 0 },
        { label: "全输", probability: 0.342 },
      ],
    },
    europeanHandicap: {
      label: "主队 0",
      items: [
        { label: "让胜", probability: 0.356 },
        { label: "让平", probability: 0.302 },
        { label: "让负", probability: 0.342 },
      ],
    },
    correctScores: [
      { score: "1-1", probability: 0.121, optionKey: "1-1" },
      { score: "1-0", probability: 0.089, optionKey: "1-0" },
      { score: "0-1", probability: 0.086, optionKey: "0-1" },
      { score: "2-1", probability: 0.078, optionKey: "2-1" },
      { score: "1-2", probability: 0.075, optionKey: "1-2" },
    ],
    scoreGrid: scoreGridFromCorrectScores([
      { score: "1-1", probability: 0.121, optionKey: "1-1" },
      { score: "1-0", probability: 0.089, optionKey: "1-0" },
      { score: "0-1", probability: 0.086, optionKey: "0-1" },
      { score: "2-1", probability: 0.078, optionKey: "2-1" },
      { score: "1-2", probability: 0.075, optionKey: "1-2" },
    ]),
    tailEvents: [
      { label: "主队 3+ 球大胜", probability: 0.037 },
      { label: "客队 3+ 球大胜", probability: 0.034 },
      { label: "任一方 4+ 球", probability: 0.018 },
    ],
    upsetAlerts: [
      {
        type: "draw_overlooked",
        label: "平局被低估",
        targetOutcome: "平局",
        favorite: "Yokohama F. Marinos",
        favoriteModelProbability: 0.342,
        favoriteMarketProbability: 0.4,
        modelProbability: 0.302,
        marketProbability: 0.268,
        probabilityGap: 0.034,
        favoriteFragilityScore: 0.69,
        riskLevel: "medium_high",
        explanations: [
          "双方基础强度接近，平局概率高于市场。",
          "数据质量为 C，冷门信号需谨慎解读。",
        ],
      },
    ],
    keyFactors: {
      model: ["双方期望进球接近，平局和一球差结果权重较高。"],
      market: ["市场更偏向客队，模型未给出同等幅度。"],
      lineup: ["阵容/伤停覆盖不足，降低置信度。"],
      schedule: ["赛程日历差异可能影响 baseline 参数稳定性。"],
      uncertainty: ["Beta 赛事且数据质量 C，不进入自动串关候选。"],
    },
  },
];

const parlays: ParlayTicket[] = [
  {
    recommendationId: "parlay_balanced_001",
    strategy: "平衡型",
    passType: "2x1",
    isMultiple: false,
    legs: [
      {
        fixtureId: "fix_epl_001",
        matchLabel: "Arsenal vs Liverpool",
        market: "1X2",
        outcomes: ["主胜"],
      },
      {
        fixtureId: "fix_epl_002",
        matchLabel: "Manchester City vs Tottenham Hotspur",
        market: "让球胜平负",
        outcomes: ["让负"],
      },
    ],
    atomicBetCount: 1,
    unitStake: 2,
    totalStake: 2,
    hitProbability: 0.201,
    expectedPayout: 2.18,
    ev: 0.18,
    roi: 0.09,
    riskLevel: "medium",
    riskScore: 0.58,
    correlationPenalty: 0,
    ruleValid: true,
    explanations: [
      "两个选项均来自数据质量 B 以上赛事。",
      "组合命中概率为模型独立近似结果，仍存在不确定性。",
    ],
    explanationJson: {
      calculation_basis: "independent_fixture_approximation",
      selected_probability_by_fixture: {
        fix_epl_001: 0.432,
        fix_epl_002: 0.466,
      },
      rule_reasons: [],
    },
    atomicBets: [
      {
        legs: [
          {
            fixtureId: "fix_epl_001",
            marketType: "1x2",
            outcome: "home_win",
            probability: 0.432,
            odds: 2.49,
            line: null,
          },
          {
            fixtureId: "fix_epl_002",
            marketType: "cn_handicap_1x2",
            outcome: "handicap_away_win",
            probability: 0.466,
            odds: 2.24,
            line: -1,
          },
        ],
        stake: 2,
        probability: 0.201,
        oddsProduct: 5.58,
        expectedPayout: 2.18,
        expectedValue: 0.18,
        roi: 0.09,
      },
    ],
  },
  {
    recommendationId: "parlay_cover_002",
    strategy: "冷门观察型",
    passType: "4x1",
    isMultiple: true,
    legs: [
      {
        fixtureId: "fix_epl_001",
        matchLabel: "Arsenal vs Liverpool",
        market: "1X2",
        outcomes: ["平局", "客胜"],
      },
      {
        fixtureId: "fix_epl_002",
        matchLabel: "Manchester City vs Tottenham Hotspur",
        market: "让球胜平负",
        outcomes: ["让平", "让负"],
      },
      {
        fixtureId: "fix_j1_001",
        matchLabel: "Kawasaki Frontale vs Yokohama F. Marinos",
        market: "1X2",
        outcomes: ["平局"],
      },
      {
        fixtureId: "fix_epl_001",
        matchLabel: "Arsenal vs Liverpool",
        market: "亚洲让球",
        outcomes: ["主队 -0.25 半输/全输方向"],
      },
    ],
    atomicBetCount: 4,
    unitStake: 2,
    totalStake: 8,
    hitProbability: 0.083,
    expectedPayout: 7.52,
    ev: -0.48,
    roi: -0.06,
    riskLevel: "high",
    riskScore: 0.86,
    correlationPenalty: 0.08,
    ruleValid: false,
    explanations: [
      "复式会增加注数和总金额。",
      "包含同场不同玩法，当前规则引擎标记为不合法。",
      "该组合命中概率较低，任一单式注失误都会影响返还。",
    ],
    explanationJson: {
      calculation_basis: "independent_fixture_approximation",
      selected_probability_by_fixture: {
        fix_epl_001: 0.847,
        fix_epl_002: 0.707,
        fix_j1_001: 0.302,
      },
      rule_reasons: ["same_fixture_multiple_markets_not_allowed"],
    },
    atomicBets: [
      {
        legs: [
          { fixtureId: "fix_epl_001", marketType: "1x2", outcome: "draw", probability: 0.279, odds: 3.83, line: null },
          { fixtureId: "fix_epl_002", marketType: "cn_handicap_1x2", outcome: "handicap_draw", probability: 0.241, odds: 4.42, line: -1 },
          { fixtureId: "fix_j1_001", marketType: "1x2", outcome: "draw", probability: 0.302, odds: 3.73, line: null },
          { fixtureId: "fix_epl_001", marketType: "asian_handicap", outcome: "half_loss", probability: 0.279, odds: 1.82, line: -0.25 },
        ],
        stake: 2,
        probability: 0.0057,
        oddsProduct: 114.7,
        expectedPayout: 1.31,
        expectedValue: -0.69,
        roi: -0.345,
      },
      {
        legs: [
          { fixtureId: "fix_epl_001", marketType: "1x2", outcome: "away_win", probability: 0.289, odds: 2.96, line: null },
          { fixtureId: "fix_epl_002", marketType: "cn_handicap_1x2", outcome: "handicap_away_win", probability: 0.466, odds: 2.24, line: -1 },
          { fixtureId: "fix_j1_001", marketType: "1x2", outcome: "draw", probability: 0.302, odds: 3.73, line: null },
          { fixtureId: "fix_epl_001", marketType: "asian_handicap", outcome: "full_loss", probability: 0.289, odds: 1.82, line: -0.25 },
        ],
        stake: 2,
        probability: 0.0118,
        oddsProduct: 45.2,
        expectedPayout: 1.07,
        expectedValue: -0.93,
        roi: -0.465,
      },
    ],
  },
];

const accuracySummaryFallback: AccuracySummary = accuracySummarySchema.parse({
  logLoss: 1.018,
  brierScore: 0.214,
  ece: 0.041,
  sampleSize: 36,
  byMarket: {
    "1x2": { logLoss: 1.018, brierScore: 0.214, ece: 0.037, sampleSize: 36 },
    cn_handicap_1x2: { logLoss: 1.083, brierScore: 0.239, ece: 0.052, sampleSize: 28 },
    asian_handicap: { logLoss: 0.706, brierScore: 0.186, ece: 0.047, sampleSize: 24 },
  },
  byCompetition: [
    {
      competitionId: "EPL",
      competitionName: "Premier League",
      logLoss: 0.996,
      brierScore: 0.207,
      ece: 0.035,
      sampleSize: 24,
    },
    {
      competitionId: "JPN_J1",
      competitionName: "J1 League",
      logLoss: 1.062,
      brierScore: 0.229,
      ece: 0.059,
      sampleSize: 12,
    },
  ],
  calibrationBuckets: [
    {
      bucketStart: 0.2,
      bucketEnd: 0.3,
      averagePredictedProbability: 0.258,
      actualFrequency: 0.286,
      sampleSize: 7,
    },
    {
      bucketStart: 0.3,
      bucketEnd: 0.4,
      averagePredictedProbability: 0.354,
      actualFrequency: 0.333,
      sampleSize: 12,
    },
    {
      bucketStart: 0.4,
      bucketEnd: 0.5,
      averagePredictedProbability: 0.438,
      actualFrequency: 0.412,
      sampleSize: 17,
    },
  ],
  errorTypes: [
    {
      tag: "draw_underestimated",
      label: "平局低估",
      count: 5,
      share: 0.139,
      examples: ["fix_epl_001"],
    },
    {
      tag: "favorite_overestimated",
      label: "热门高估",
      count: 4,
      share: 0.111,
      examples: ["fix_epl_002"],
    },
    {
      tag: "league_calibration_drift",
      label: "联赛校准漂移",
      count: 3,
      share: 0.083,
      examples: ["fix_j1_001"],
    },
  ],
  modelComparisons: [
    {
      baselineModelVersion: "poisson-m1.0.0",
      candidateModelVersion: "dc-v1.5-candidate",
      baselineLogLoss: 1.018,
      candidateLogLoss: 1.006,
      baselineBrierScore: 0.214,
      candidateBrierScore: 0.211,
      calibrationDelta: -0.004,
      sampleSize: 36,
      decision: "needs_review",
      reasons: [
        "候选模型在核心指标上略有改善。",
        "样本量仍偏小，暂不触发自动晋级。",
        "低样本联赛需要继续观察校准漂移。",
      ],
    },
  ],
  modelVersion: "active",
  window: "90d",
  filters: {
    modelVersion: "active",
    competitionId: "all",
    market: "all",
    window: "90d",
  },
  generatedAtUtc: "2026-05-06T12:30:00Z",
  stale: false,
});

const strategyGovernanceFallback: RecommendationStrategyGovernance =
  recommendationStrategyGovernanceSchema.parse({
    generatedAtUtc: "2026-05-09T00:00:00Z",
    stale: false,
    fallbackUsed: true,
    items: [
      {
        candidateStrategy: "upset_protection",
        baselineStrategy: "accuracy_first",
        passType: "2x1",
        mode: "single",
        candidateEvidence: {
          strategy: "upset_protection",
          passType: "2x1",
          mode: "single",
          sampleSize: 90,
          settledRunCount: 90,
          hitCount: 42,
          totalStake: 180,
          grossPayout: 189.9,
          profitLoss: 9.9,
          roi: 0.055,
          hitRate: 0.47,
          averageExpectedRoi: 0.055,
          averageExpectedHitProbability: 0.47,
          averageHitCalibrationError: 0,
          meanAbsoluteHitCalibrationError: 0.06,
          firstEvaluationTimeUtc: "2026-05-01T00:00:00Z",
          lastEvaluationTimeUtc: "2026-05-09T00:00:00Z",
        },
        baselineEvidence: {
          strategy: "accuracy_first",
          passType: "2x1",
          mode: "single",
          sampleSize: 120,
          settledRunCount: 120,
          hitCount: 55,
          totalStake: 240,
          grossPayout: 249.6,
          profitLoss: 9.6,
          roi: 0.04,
          hitRate: 0.46,
          averageExpectedRoi: 0.04,
          averageExpectedHitProbability: 0.46,
          averageHitCalibrationError: 0,
          meanAbsoluteHitCalibrationError: 0.065,
          firstEvaluationTimeUtc: "2026-05-01T00:00:00Z",
          lastEvaluationTimeUtc: "2026-05-09T00:00:00Z",
        },
        decision: "shadow_candidate",
        nextStatus: "shadow",
        reasons: ["strategy_passed_first_governance_gate"],
        shouldRollback: false,
        rollbackTargetStrategy: null,
        rollbackReasons: [],
        metricDeltas: {
          roiDelta: 0.015,
          hitRateDelta: 0.01,
          calibrationErrorDelta: -0.005,
          expectedRoiDelta: 0.015,
        },
        warnings: ["frontend_fallback_strategy_governance_evidence"],
      },
    ],
  });

const providerOpsFallback: ProviderOps = providerOpsSchema.parse({
  providers: [
    {
      providerName: "mock-local",
      status: "active",
      capabilities: ["fixtures", "results", "odds", "lineups", "injuries"],
      termsCheckedAtUtc: "2026-05-06T00:00:00Z",
      commercialUseAllowed: true,
      retentionAllowed: true,
      allowedUse: "local_development_and_test",
      rateLimit: "none",
      historicalDataAllowed: true,
      redistributionAllowed: true,
      termsUrl: null,
      lastReviewedAtUtc: "2026-05-06T00:00:00Z",
      nextReviewDueAtUtc: "2027-05-06T00:00:00Z",
      owner: "nutmeg-ops",
      apiKeyEnvVar: null,
      notes: "Local deterministic fixture provider for development and tests.",
    },
    {
      providerName: "football-data.org",
      status: "pending_review",
      capabilities: ["competitions", "seasons", "fixtures", "results"],
      termsCheckedAtUtc: "2026-05-06T00:00:00Z",
      commercialUseAllowed: false,
      retentionAllowed: false,
      allowedUse: "fixtures_results_research_dry_run",
      rateLimit: "free_plan_provider_defined",
      historicalDataAllowed: false,
      redistributionAllowed: false,
      termsUrl: "https://www.football-data.org/terms",
      lastReviewedAtUtc: "2026-05-06T00:00:00Z",
      nextReviewDueAtUtc: "2026-11-02T00:00:00Z",
      owner: "nutmeg-ops",
      apiKeyEnvVar: "FOOTBALL_DATA_API_KEY",
      notes: "Candidate schedule/result provider; terms and retention review required.",
    },
    {
      providerName: "the-odds-api",
      status: "pending_review",
      capabilities: ["odds"],
      termsCheckedAtUtc: "2026-05-06T00:00:00Z",
      commercialUseAllowed: false,
      retentionAllowed: false,
      allowedUse: "odds_snapshot_research_dry_run",
      rateLimit: "free_plan_provider_defined",
      historicalDataAllowed: false,
      redistributionAllowed: false,
      termsUrl: "https://the-odds-api.com/terms.html",
      lastReviewedAtUtc: "2026-05-06T00:00:00Z",
      nextReviewDueAtUtc: "2026-11-02T00:00:00Z",
      owner: "nutmeg-ops",
      apiKeyEnvVar: "THE_ODDS_API_KEY",
      notes: "Candidate odds provider; historical snapshot retention must be verified.",
    },
    {
      providerName: "sportmonks",
      status: "pending_review",
      capabilities: ["fixtures", "results", "odds", "lineups", "injuries", "team_stats"],
      termsCheckedAtUtc: "2026-05-06T00:00:00Z",
      commercialUseAllowed: false,
      retentionAllowed: false,
      allowedUse: "broad_coverage_trial_research",
      rateLimit: "trial_plan_provider_defined",
      historicalDataAllowed: false,
      redistributionAllowed: false,
      termsUrl: "https://www.sportmonks.com/terms-of-service/",
      lastReviewedAtUtc: "2026-05-06T00:00:00Z",
      nextReviewDueAtUtc: "2026-11-02T00:00:00Z",
      owner: "nutmeg-ops",
      apiKeyEnvVar: "SPORTMONKS_API_KEY",
      notes: "Candidate broad coverage provider; production use requires explicit review.",
    },
    {
      providerName: "api-football",
      status: "pending_review",
      capabilities: ["competitions", "seasons", "fixtures", "results"],
      termsCheckedAtUtc: "2026-05-08T00:00:00Z",
      commercialUseAllowed: false,
      retentionAllowed: false,
      allowedUse: "fixture_result_fallback_research_dry_run",
      rateLimit: "free_plan_provider_defined",
      historicalDataAllowed: false,
      redistributionAllowed: false,
      termsUrl: "https://www.api-football.com/terms",
      lastReviewedAtUtc: "2026-05-08T00:00:00Z",
      nextReviewDueAtUtc: "2026-11-04T00:00:00Z",
      owner: "nutmeg-ops",
      apiKeyEnvVar: "API_FOOTBALL_API_KEY",
      notes: "Candidate broad fixture/result fallback; free plan can be season-limited.",
    },
  ],
  authorizationReviews: {
    fetched: false,
    stale: false,
    fallbackUsed: true,
    items: [
      {
        providerAuthorizationReviewId: 1,
        providerName: "api-football",
        reviewReference: "seed-api-football",
        reviewStatus: "needs_review",
        reviewedBy: "nutmeg-ops",
        reviewedAtUtc: "2026-05-08T00:00:00Z",
        termsUrl: "https://www.api-football.com/terms",
        termsVersionHash: null,
        allowedUse: "fixture_result_fallback_research_dry_run",
        commercialUseAllowed: false,
        retentionAllowed: false,
        historicalDataAllowed: false,
        redistributionAllowed: false,
        rateLimit: "free_plan_provider_defined",
        nextReviewDueAtUtc: "2026-11-04T00:00:00Z",
        evidenceJson: { source: "fallback_provider_ops" },
        notes: "Candidate broad fixture/result fallback; free plan can be season-limited.",
        createdAtUtc: "2026-05-08T00:00:00Z",
      },
      {
        providerAuthorizationReviewId: 2,
        providerName: "the-odds-api",
        reviewReference: "seed-the-odds-api",
        reviewStatus: "needs_review",
        reviewedBy: "nutmeg-ops",
        reviewedAtUtc: "2026-05-06T00:00:00Z",
        termsUrl: "https://the-odds-api.com/terms.html",
        termsVersionHash: null,
        allowedUse: "odds_snapshot_research_dry_run",
        commercialUseAllowed: false,
        retentionAllowed: false,
        historicalDataAllowed: false,
        redistributionAllowed: false,
        rateLimit: "free_plan_provider_defined",
        nextReviewDueAtUtc: "2026-11-02T00:00:00Z",
        evidenceJson: { source: "fallback_provider_ops" },
        notes: "Candidate odds provider; historical snapshot retention must be verified.",
        createdAtUtc: "2026-05-06T00:00:00Z",
      },
    ],
  },
  runtimeCredentials: {
    fetched: false,
    mockDryRunEnabled: true,
    generatedAtUtc: "2026-05-08T03:30:00Z",
    items: [
      {
        providerName: "mock-local",
        capabilities: ["fixtures", "results", "odds", "lineups", "injuries"],
        apiKeyEnvVar: null,
        runtimeEnvVar: null,
        keyConfigured: true,
        dryRunMode: "local_only",
        commitMode: "not_applicable",
        safeToCallRealProvider: false,
        mockDryRunEnabled: true,
        requiresApiKeyForCommit: false,
        nextAction: "available_for_deterministic_local_testing",
        notes: ["deterministic_local_provider", "no_external_request"],
      },
      {
        providerName: "football-data.org",
        capabilities: ["competitions", "seasons", "fixtures", "results"],
        apiKeyEnvVar: "FOOTBALL_DATA_API_KEY",
        runtimeEnvVar: "NUTMEG_FOOTBALL_DATA_API_KEY",
        keyConfigured: false,
        dryRunMode: "mock_sample",
        commitMode: "blocked",
        safeToCallRealProvider: false,
        mockDryRunEnabled: true,
        requiresApiKeyForCommit: true,
        nextAction: "apply_api_key_before_real_provider_sync",
        notes: ["dry_run_uses_deterministic_sample", "commit_sync_requires_api_key"],
      },
      {
        providerName: "the-odds-api",
        capabilities: ["odds"],
        apiKeyEnvVar: "THE_ODDS_API_KEY",
        runtimeEnvVar: "NUTMEG_THE_ODDS_API_KEY",
        keyConfigured: false,
        dryRunMode: "mock_sample",
        commitMode: "blocked",
        safeToCallRealProvider: false,
        mockDryRunEnabled: true,
        requiresApiKeyForCommit: true,
        nextAction: "apply_api_key_before_real_provider_sync",
        notes: ["dry_run_uses_deterministic_sample", "commit_sync_requires_api_key"],
      },
      {
        providerName: "sportmonks",
        capabilities: ["fixtures", "results", "odds", "lineups", "injuries"],
        apiKeyEnvVar: "SPORTMONKS_API_KEY",
        runtimeEnvVar: "NUTMEG_SPORTMONKS_API_KEY",
        keyConfigured: false,
        dryRunMode: "mock_sample",
        commitMode: "blocked",
        safeToCallRealProvider: false,
        mockDryRunEnabled: true,
        requiresApiKeyForCommit: true,
        nextAction: "apply_api_key_before_real_provider_sync",
        notes: ["dry_run_uses_deterministic_sample", "commit_sync_requires_api_key"],
      },
    ],
    stale: false,
    fallbackUsed: true,
  },
  runtimeMonitoring: {
    fetched: false,
    generatedAtUtc: "2026-05-08T03:32:00Z",
    summary: {
      providerCount: 4,
      healthyCount: 1,
      degradedCount: 3,
      rateLimitedCount: 0,
      authFailedCount: 0,
      unavailableCount: 0,
      notConfiguredCount: 3,
      fallbackProviderCount: 3,
      averageLatencyMs: null,
      latestObservedAtUtc: "2026-05-08T03:32:00Z",
    },
    alertLevel: "P1",
    alerts: [
      {
        alertId: "provider_fallback_usage_high",
        severity: "P1",
        providerName: null,
        capability: null,
        metric: "fallback_model_usage_rate",
        currentValue: 0.75,
        threshold: 0.5,
        message: "Provider fallback usage is above the configured threshold.",
        recommendedAction: "review_provider_keys_limits_and_data_coverage",
      },
      {
        alertId: "football-data.org_not_configured",
        severity: "P2",
        providerName: "football-data.org",
        capability: "fixtures_results",
        metric: "provider_runtime_readiness",
        currentValue: "not_configured",
        threshold: "ok_or_key_configured",
        message: "Provider runtime readiness is incomplete.",
        recommendedAction: "configure_runtime_key",
      },
    ],
    thresholds: {
      providerLatencyP2Ms: 1500,
      providerLatencyP1Ms: 5000,
      providerErrorRateP1: 1,
      providerPlanLimitP2: 0.5,
      fallbackUsageRateP1: 0.5,
    },
    items: [
      {
        providerRuntimeSnapshotId: null,
        providerName: "mock-local",
        capability: "deterministic_fixture",
        probeStatus: "key_configured",
        keyConfigured: true,
        liveProbe: false,
        safeToCallRealProvider: false,
        latencyMs: null,
        errorRate: 0,
        successCount: 1,
        failureCount: 0,
        rateLimitRemaining: null,
        quotaWindow: null,
        fallbackUsed: false,
        message: "Local deterministic provider is available for dry-run workflows.",
        nextAction: "no_action",
        metadataJson: { monitoring_source: "fallback_provider_ops" },
        observedAtUtc: "2026-05-08T03:32:00Z",
      },
      {
        providerRuntimeSnapshotId: null,
        providerName: "football-data.org",
        capability: "fixtures_results",
        probeStatus: "not_configured",
        keyConfigured: false,
        liveProbe: false,
        safeToCallRealProvider: false,
        latencyMs: null,
        errorRate: null,
        successCount: 0,
        failureCount: 0,
        rateLimitRemaining: null,
        quotaWindow: null,
        fallbackUsed: true,
        message: "Runtime key is unavailable in fallback Provider Ops data.",
        nextAction: "configure_runtime_key",
        metadataJson: { monitoring_source: "fallback_provider_ops" },
        observedAtUtc: "2026-05-08T03:32:00Z",
      },
      {
        providerRuntimeSnapshotId: null,
        providerName: "the-odds-api",
        capability: "odds",
        probeStatus: "not_configured",
        keyConfigured: false,
        liveProbe: false,
        safeToCallRealProvider: false,
        latencyMs: null,
        errorRate: null,
        successCount: 0,
        failureCount: 0,
        rateLimitRemaining: null,
        quotaWindow: null,
        fallbackUsed: true,
        message: "Runtime key is unavailable in fallback Provider Ops data.",
        nextAction: "configure_runtime_key",
        metadataJson: { monitoring_source: "fallback_provider_ops" },
        observedAtUtc: "2026-05-08T03:32:00Z",
      },
      {
        providerRuntimeSnapshotId: null,
        providerName: "sportmonks",
        capability: "lineups_injuries",
        probeStatus: "not_configured",
        keyConfigured: false,
        liveProbe: false,
        safeToCallRealProvider: false,
        latencyMs: null,
        errorRate: null,
        successCount: 0,
        failureCount: 0,
        rateLimitRemaining: null,
        quotaWindow: null,
        fallbackUsed: true,
        message: "Runtime key is unavailable in fallback Provider Ops data.",
        nextAction: "configure_runtime_key",
        metadataJson: { monitoring_source: "fallback_provider_ops" },
        observedAtUtc: "2026-05-08T03:32:00Z",
      },
    ],
    stale: false,
    fallbackUsed: true,
  },
  runtimeIncidents: {
    fetched: false,
    items: [],
    summary: providerRuntimeIncidentSummaryFallback,
    filters: providerRuntimeIncidentDefaultFilters,
    limit: providerRuntimeIncidentDefaultFilters.limit,
    offset: providerRuntimeIncidentDefaultFilters.offset,
    totalCount: 0,
    hasMore: false,
    stale: false,
    fallbackUsed: true,
  },
  apiKeyChecklist: {
    fetched: false,
    generatedAtUtc: "2026-05-08T03:35:00Z",
    items: [
      {
        providerName: "football-data.org",
        nutmegRole: "fixtures_results_first_real_dry_run",
        priority: 1,
        adapterStatus: "supported_now",
        requiredEnvVar: "NUTMEG_FOOTBALL_DATA_API_KEY",
        keyConfigured: false,
        applyUrl: "https://www.football-data.org/client/register",
        docsUrl: "https://docs.football-data.org/general/v4/policies.html",
        officialFreeTierNote: "Free registered clients are suitable for initial fixtures/results dry-runs.",
        freeTierFit: "good_for_first_dry_run",
        operatorAction: "apply_free_key_then_set_nutmeg_football_data_api_key",
        sourceCheckedAtUtc: "2026-05-07T00:00:00Z",
      },
      {
        providerName: "api-football",
        nutmegRole: "broad_fixture_result_provider_candidate",
        priority: 2,
        adapterStatus: "supported_now",
        requiredEnvVar: "NUTMEG_API_FOOTBALL_API_KEY",
        keyConfigured: false,
        applyUrl: "https://dashboard.api-football.com/register",
        docsUrl: "https://www.api-football.com/documentation-v3",
        officialFreeTierNote:
          "Free API-Football access is useful for fixture coverage research and fallback mapping dry-runs.",
        freeTierFit: "good_for_first_dry_run",
        operatorAction: "apply_free_key_then_set_nutmeg_api_football_api_key",
        sourceCheckedAtUtc: "2026-05-07T00:00:00Z",
      },
      {
        providerName: "sportmonks",
        nutmegRole: "lineups_injuries_broad_coverage_candidate",
        priority: 3,
        adapterStatus: "supported_now",
        requiredEnvVar: "NUTMEG_SPORTMONKS_API_KEY",
        keyConfigured: false,
        applyUrl: "https://my.sportmonks.com/register",
        docsUrl: "https://docs.sportmonks.com/football",
        officialFreeTierNote: "Use a free trial key first for lineup and injury dry-runs.",
        freeTierFit: "trial_required",
        operatorAction: "apply_trial_key_then_set_nutmeg_sportmonks_api_key",
        sourceCheckedAtUtc: "2026-05-07T00:00:00Z",
      },
      {
        providerName: "the-odds-api",
        nutmegRole: "odds_market_snapshot_candidate",
        priority: 4,
        adapterStatus: "supported_now",
        requiredEnvVar: "NUTMEG_THE_ODDS_API_KEY",
        keyConfigured: false,
        applyUrl: "https://the-odds-api.com/",
        docsUrl: "https://the-odds-api.com/liveapi/guides/v4/",
        officialFreeTierNote: "Free tier is useful for key plumbing, but soccer coverage may be limited.",
        freeTierFit: "limited_for_soccer",
        operatorAction: "apply_free_key_but_expect_soccer_odds_limitations",
        sourceCheckedAtUtc: "2026-05-07T00:00:00Z",
      },
    ],
    stale: false,
    fallbackUsed: true,
  },
  auditTrail: {
    fetched: false,
    items: [],
    stale: false,
    fallbackUsed: true,
  },
  runHistory: {
    fetched: false,
    items: [],
    stale: false,
    fallbackUsed: true,
  },
  readiness: [
    {
      competitionId: "EPL",
      competitionName: "Premier League",
      targetStage: "beta",
      decision: "beta_ready",
      dataQuality: {
        score: 80.4,
        grade: "B",
        parlayEligible: true,
        components: {
          fixtureReliability: 0.995,
          oddsCoverage: 0.72,
          lineupInjuryCoverage: 0.7,
          historicalStatsCompleteness: 0.82,
          providerConsistency: 0.93,
          dataFreshness: 0.88,
        },
        messages: ["数据质量 B：主要赛程、赔率和历史数据可用。"],
      },
      reasons: [],
      betaReady: true,
      productionReady: false,
    },
    {
      competitionId: "JPN_J1",
      competitionName: "J1 League",
      targetStage: "beta",
      decision: "not_ready",
      dataQuality: {
        score: 57.1,
        grade: "C",
        parlayEligible: true,
        components: {
          fixtureReliability: 0.96,
          oddsCoverage: 0.48,
          lineupInjuryCoverage: 0.35,
          historicalStatsCompleteness: 0.58,
          providerConsistency: 0.76,
          dataFreshness: 0.64,
        },
        messages: ["数据质量 C：阵容/赔率数据不足，谨慎解读。"],
      },
      reasons: ["schedule_coverage_below_98", "odds_coverage_below_60"],
      betaReady: false,
      productionReady: false,
    },
  ],
  mappings: [
    {
      mappingId: 101,
      provider: "football-data.org",
      entityType: "fixture",
      providerEntityId: "330299",
      canonicalEntityId: "fd_fixture_330299",
      confidence: 1,
      createdAtUtc: "2026-05-08T01:00:00Z",
      updatedAtUtc: "2026-05-08T01:05:00Z",
    },
    {
      mappingId: 102,
      provider: "the-odds-api",
      entityType: "fixture",
      providerEntityId: "event_123",
      canonicalEntityId: "fd_fixture_330299",
      confidence: 1,
      createdAtUtc: "2026-05-08T01:10:00Z",
      updatedAtUtc: "2026-05-08T01:10:00Z",
    },
  ],
  mappingSummary: [
    {
      provider: "football-data.org",
      entityType: "fixture",
      mappingCount: 1,
      averageConfidence: 1,
      minimumConfidence: 1,
      latestUpdatedAtUtc: "2026-05-08T01:05:00Z",
    },
    {
      provider: "the-odds-api",
      entityType: "fixture",
      mappingCount: 1,
      averageConfidence: 1,
      minimumConfidence: 1,
      latestUpdatedAtUtc: "2026-05-08T01:10:00Z",
    },
  ],
  mappingReview: {
    dryRun: true,
    asOfTimeUtc: "2026-05-08T02:00:00Z",
    checkedMappingCount: 2,
    issueCount: 1,
    criticalCount: 0,
    warningCount: 1,
    infoCount: 0,
    issues: [
      {
        issueId: "fallback-review-1",
        issueType: "same_provider_canonical_collision",
        severity: "warning",
        provider: "football-data.org",
        entityType: "fixture",
        canonicalEntityId: "fd_fixture_330299",
        providerEntityIds: ["330299", "330299-alt"],
        mappingIds: [101, 103],
        confidenceMin: 0.91,
        latestUpdatedAtUtc: "2026-05-08T01:05:00Z",
        reasons: ["multiple_provider_ids_for_same_canonical_entity"],
        recommendedAction: "confirm_or_split_canonical_mapping",
      },
    ],
    stale: false,
    fallbackUsed: true,
  },
  conflictGovernance: {
    dryRun: true,
    asOfTimeUtc: "2026-05-08T02:00:00Z",
    checkedIssueCount: 1,
    conflictCount: 1,
    criticalCount: 0,
    warningCount: 1,
    infoCount: 0,
    providerConsistencyAfterConflicts: 0.85,
    dataQualityScoreDelta: -1.5,
    trustedPriorities: [
      {
        providerName: "football-data.org",
        capability: "mapping",
        priorityRank: 10,
        reason: "fixture_mapping_reference",
      },
      {
        providerName: "sportmonks",
        capability: "mapping",
        priorityRank: 20,
        reason: "secondary_mapping_reference",
      },
    ],
    events: [
      {
        sourceIssueId: "fallback-review-1",
        conflictType: "provider_mapping_conflict",
        severity: "warning",
        entityType: "fixture",
        canonicalEntityId: "fd_fixture_330299",
        providerNames: ["football-data.org"],
        providerEntityIds: ["330299", "330299-alt"],
        trustedProvider: "football-data.org",
        dataQualityScoreDelta: -1.5,
        recommendedAction: "confirm_or_split_canonical_mapping",
      },
    ],
    persistedEvents: [
      {
        providerConflictEventId: 601,
        sourceReviewRunId: 501,
        sourceIssueId: "fallback-review-1",
        conflictType: "provider_mapping_conflict",
        severity: "warning",
        entityType: "fixture",
        canonicalEntityId: "fd_fixture_330299",
        providerNames: ["football-data.org"],
        providerEntityIds: ["330299", "330299-alt"],
        trustedProvider: "football-data.org",
        resolutionStatus: "open",
        dataQualityScoreDelta: -1.5,
        evidenceJson: { mapping_issue_type: "same_provider_canonical_collision" },
        recommendedAction: "confirm_or_split_canonical_mapping",
        requestedBy: "admin_api",
        createdAtUtc: "2026-05-08T02:05:00Z",
        resolvedAtUtc: null,
      },
    ],
    persistedOpenCount: 1,
    persistedResolvedCount: 0,
    persistedIgnoredCount: 0,
    stale: false,
    fallbackUsed: true,
  },
  oddsCoverage: {
    fetched: false,
    competitionId: "EPL",
    competitionName: "Premier League",
    fixtureCount: 0,
    oddsSnapshotCount: 0,
    bookmakerCount: 0,
    oddsCoverage: 0,
    oneXTwoCoverage: 0,
    handicapCoverage: 0,
    freshOddsCoverage: 0,
    marketTypes: [],
    generatedAtUtc: "2026-05-08T03:10:00Z",
    stale: false,
    fallbackUsed: true,
  },
  oddsGapReport: {
    fetched: false,
    competitionId: "EPL",
    competitionName: "Premier League",
    provider: "the-odds-api",
    windowStartUtc: "2026-02-07T03:10:00Z",
    asOfTimeUtc: "2026-05-08T03:10:00Z",
    maxSnapshotLagHours: 168,
    fixtureCount: 3,
    gapCount: 2,
    noOddsCount: 1,
    staleOddsCount: 1,
    providerEventUnavailableCount: 1,
    missing1x2Count: 0,
    missingHandicapCount: 1,
    unmappedFixtureCount: 1,
    mappedGapCount: 1,
    items: [
      {
        fixtureId: "fd_fixture_missing_odds",
        competitionId: "EPL",
        competitionName: "Premier League",
        kickoffTimeUtc: "2026-05-10T14:00:00Z",
        homeTeamName: "Arsenal",
        awayTeamName: "Brighton",
        issueTypes: ["unmapped", "provider_event_unavailable", "no_odds"],
        recommendedAction: "try_fallback_provider_event_mapping",
        oddsSnapshotCount: 0,
        bookmakerCount: 0,
        has1x2: false,
        hasHandicap: false,
        freshEnough: false,
        latestSnapshotTimeUtc: null,
        latestSnapshotLagHours: null,
        marketTypes: [],
        hasProviderMapping: false,
        provider: "the-odds-api",
        providerEventId: null,
        providerMappingId: null,
        providerMappingConfidence: null,
        providerMappingUpdatedAtUtc: null,
        eventAvailabilityNote:
          "the-odds-api has no mapped event for this fixture in the current provider-event bootstrap window; check fallback provider coverage.",
        fallbackCandidates: [
          {
            providerName: "api-football",
            coverageRole: "broad_fixture_result_provider_candidate",
            adapterStatus: "supported_now",
            requiredEnvVar: "NUTMEG_API_FOOTBALL_API_KEY",
            recommendedAction: "bootstrap_api_football_fixture_mapping",
          },
          {
            providerName: "sportmonks",
            coverageRole: "odds_fixture_fallback_candidate",
            adapterStatus: "supported_now",
            requiredEnvVar: "NUTMEG_SPORTMONKS_API_KEY",
            recommendedAction: "probe_sportmonks_fixture_odds_coverage",
          },
        ],
      },
      {
        fixtureId: "fd_fixture_stale_odds",
        competitionId: "EPL",
        competitionName: "Premier League",
        kickoffTimeUtc: "2026-05-11T19:00:00Z",
        homeTeamName: "Chelsea",
        awayTeamName: "Everton",
        issueTypes: ["stale_odds", "missing_market"],
        recommendedAction: "refresh_mapped_event_odds",
        oddsSnapshotCount: 3,
        bookmakerCount: 1,
        has1x2: true,
        hasHandicap: false,
        freshEnough: false,
        latestSnapshotTimeUtc: "2026-04-28T12:00:00Z",
        latestSnapshotLagHours: 317,
        marketTypes: ["1x2"],
        hasProviderMapping: true,
        provider: "the-odds-api",
        providerEventId: "fallback-event-2",
        providerMappingId: 102,
        providerMappingConfidence: 0.97,
        providerMappingUpdatedAtUtc: "2026-05-01T08:00:00Z",
        eventAvailabilityNote: null,
        fallbackCandidates: [],
      },
    ],
    generatedAtUtc: "2026-05-08T03:10:00Z",
    stale: false,
    fallbackUsed: true,
  },
  fallbackOddsProbe: {
    fetched: false,
    competitionId: "EPL",
    primaryProvider: "the-odds-api",
    fallbackProvider: "sportmonks",
    liveProviderProbe: false,
    providerKeyConfigured: false,
    checkedGapCount: 1,
    providerEventUnavailableCount: 1,
    mappedFallbackCount: 0,
    probedFixtureCount: 0,
    recoverableFixtureCount: 0,
    normalizedOddsCount: 0,
    bookmakerCount: 0,
    marketTypes: [],
    items: [
      {
        fixtureId: "fd_fixture_missing_odds",
        competitionId: "EPL",
        kickoffTimeUtc: "2026-05-10T14:00:00Z",
        homeTeamName: "Arsenal",
        awayTeamName: "Brighton",
        primaryProvider: "the-odds-api",
        fallbackProvider: "sportmonks",
        status: "mapping_missing",
        canRecoverGap: false,
        providerFixtureId: null,
        providerMappingId: null,
        providerMappingConfidence: null,
        providerKeyConfigured: false,
        liveProviderProbe: false,
        normalizedOddsCount: 0,
        bookmakerCount: 0,
        marketTypes: [],
        warnings: ["missing_sportmonks_fixture_mapping"],
        recommendedAction: "bootstrap_sportmonks_fixture_mapping",
      },
    ],
    warnings: ["sportmonks_fixture_mapping_required"],
    generatedAtUtc: "2026-05-08T03:10:00Z",
    stale: false,
    fallbackUsed: true,
  },
  providerSyncWorkflow: {
    fetched: true,
    runs: [
      {
        providerSyncWorkflowRunId: 501,
        status: "completed",
        dryRun: true,
        requestedBy: "admin_api",
        startedAtUtc: "2026-05-08T03:00:00Z",
        completedAtUtc: "2026-05-08T03:01:00Z",
        durationMs: 1000,
        fixtureSyncRunId: null,
        oddsSyncRunIds: [],
        availabilitySyncRunIds: [],
        fixtureCount: 0,
        oddsSnapshotCount: 0,
        availabilitySnapshotCount: 0,
        rawPayloadIds: [],
        canonicalFixtureIds: ["fd_fixture_330299"],
        prematchWorkflowRunId: null,
        warnings: [],
        errorMessage: null,
        metadataJson: {
          source: "fallback",
          fixture_sync_requested: false,
          odds_sync_count: 0,
          availability_sync_count: 0,
          run_conflict_detection: false,
        },
      },
    ],
    templatesFetched: true,
    templates: [
      {
        providerSyncWorkflowTemplateId: 701,
        templateName: "Fallback EPL dry-run",
        description: "Fallback explicit-ID provider sync template",
        dryRun: true,
        fixtureSync: {
          provider_competition_id: "PL",
          season: "2025",
          canonical_competition_id: "EPL",
        },
        oddsSyncs: [
          {
            sport_key: "soccer_epl",
            provider_event_id: "event-id",
            canonical_fixture_id: "fd_fixture_330299",
          },
        ],
        availabilitySyncs: [],
        runConflictDetection: true,
        conflictObservationLookbackHours: 168,
        conflictLimit: 1000,
        createdBy: "admin_api",
        createdAtUtc: "2026-05-08T03:05:00Z",
        updatedAtUtc: "2026-05-08T03:05:00Z",
        archivedAtUtc: null,
        archivedBy: null,
        archiveReason: null,
        metadataJson: { source: "fallback" },
        preflightResult: {
          valid: true,
          taskCount: 2,
          syncTypes: ["fixture", "odds"],
          canonicalFixtureIds: ["fd_fixture_330299"],
          issueCount: 0,
          errorCount: 0,
          warningCount: 0,
          infoCount: 0,
          issues: [],
          metadataJson: {
            dry_run: true,
            fixture_sync_requested: true,
            odds_sync_count: 1,
            availability_sync_count: 0,
            run_conflict_detection: true,
            run_prematch_workflow: false,
          },
        },
      },
    ],
    approvalsFetched: true,
    approvals: [
      {
        providerSyncWorkflowApprovalId: 801,
        approvalType: "provider_sync_workflow_dry_run",
        approvalStatus: "approved",
        providerSyncWorkflowTemplateId: 701,
        providerSyncWorkflowRunId: 501,
        approvedBy: "admin_api",
        approvedAtUtc: "2026-05-08T03:06:00Z",
        approvalNote: "Fallback approval audit sample",
        requestPayloadJson: {
          dry_run: true,
          operator_approved: true,
          provider_sync_workflow_template_id: 701,
        },
        metadataJson: { source: "fallback" },
      },
      {
        providerSyncWorkflowApprovalId: 800,
        approvalType: "provider_sync_workflow_seed_review",
        approvalStatus: "approved",
        providerSyncWorkflowTemplateId: 701,
        providerSyncWorkflowRunId: null,
        approvedBy: "seed_migration",
        approvedAtUtc: "2026-05-07T14:15:04Z",
        approvalNote: "Fallback seed review audit sample",
        requestPayloadJson: {
          operator_approved: true,
          provider_sync_workflow_template_id: 701,
        },
        metadataJson: { source: "fallback" },
      },
    ],
    stale: false,
    fallbackUsed: true,
  },
  predictionQualityGate: {
    fetched: false,
    runs: [
      {
        predictionJobRunId: 901,
        jobType: "canonical_prematch_predictions",
        status: "completed",
        dryRun: true,
        requestedBy: "admin_api",
        startedAtUtc: "2026-05-08T03:20:00Z",
        completedAtUtc: "2026-05-08T03:21:00Z",
        durationMs: 1200,
        fixtureCount: 3,
        generatedCount: 2,
        skippedFixtureIds: ["fd_fixture_missing_odds"],
        warnings: ["canonical_odds_gate_failed:no_odds:fd_fixture_missing_odds"],
        errorMessage: null,
        dataQualityScores: {
          fd_fixture_330299: 78.5,
          fd_fixture_330300: 72.1,
        },
      },
    ],
    latestRun: {
      predictionJobRunId: 901,
      jobType: "canonical_prematch_predictions",
      status: "completed",
      dryRun: true,
      requestedBy: "admin_api",
      startedAtUtc: "2026-05-08T03:20:00Z",
      completedAtUtc: "2026-05-08T03:21:00Z",
      durationMs: 1200,
      fixtureCount: 3,
      generatedCount: 2,
      skippedFixtureIds: ["fd_fixture_missing_odds"],
      warnings: ["canonical_odds_gate_failed:no_odds:fd_fixture_missing_odds"],
      errorMessage: null,
      dataQualityScores: {
        fd_fixture_330299: 78.5,
        fd_fixture_330300: 72.1,
      },
    },
    stale: false,
    fallbackUsed: true,
  },
  latestAssessmentCount: 0,
  generatedAtUtc: "2026-05-06T12:45:00Z",
  stale: false,
  fallbackUsed: true,
});

export async function getMatches() {
  const response = await fetchApi("/fixtures", fixtureListResponseSchema);
  if (response) {
    const remoteMatches = await Promise.all(
      response.items.map((fixture) => getRemoteMatch(fixture.fixture_id)),
    );
    const parsedMatches = remoteMatches.filter((match): match is MatchPrediction => match !== null);
    if (parsedMatches.length > 0) {
      return parsedMatches;
    }
  }
  return matches.map((match) => matchPredictionSchema.parse(match));
}

export async function getMatch(fixtureId: string) {
  const remoteMatch = await getRemoteMatch(fixtureId);
  if (remoteMatch) {
    return remoteMatch;
  }
  const match = matches.find((item) => item.fixtureId === fixtureId);
  return match ? matchPredictionSchema.parse(match) : null;
}

export async function getUpsets() {
  const response = await fetchApi("/upsets", upsetListResponseSchema);
  if (response) {
    return response.items.map(upsetFromResponse);
  }
  return matches.flatMap((match) =>
    match.upsetAlerts.map((alert) => ({
      ...alert,
      fixtureId: match.fixtureId,
      matchLabel: `${match.homeTeam.name} vs ${match.awayTeam.name}`,
      competitionName: match.competitionName,
      kickoffTimeUtc: match.kickoffTimeUtc,
      dataQualityScore: match.dataQualityScore,
      dataQualityGrade: match.dataQualityGrade,
      modelVersion: match.modelVersion,
      predictionTimeUtc: match.predictionTimeUtc,
    })),
  );
}

export async function getParlayTickets(
  options: ParlayTicketRequestOptions = {},
): Promise<ParlayRecommendation> {
  const passTypes =
    options.passType && options.passType !== "all"
      ? [options.passType]
      : ["2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1"];
  const response = await fetchApi("/parlays/recommend", parlayRecommendResponseSchema, {
    method: "POST",
    body: JSON.stringify({
      date: "2026-05-06",
      pass_types: passTypes,
      strategy: options.strategy ?? "balanced",
      unit_stake: options.unitStake ?? 2,
      max_budget: options.maxBudget ?? 20,
      allow_multiple_outcomes_per_fixture: options.allowMultiple ?? true,
      allowed_markets: options.allowedMarkets?.length
        ? options.allowedMarkets
        : ["1x2", "cn_handicap_1x2"],
      exclude_beta_competitions: options.excludeBetaCompetitions ?? false,
    }),
  });
  if (response) {
    return {
      tickets: response.items.map(parlayFromResponse),
      warnings: response.warnings,
      stale: response.stale,
      fallbackUsed: response.fallback_used,
    };
  }
  if (!FRONTEND_DEV_FALLBACKS_ENABLED) {
    return {
      tickets: [],
      warnings: ["核心串关接口不可用，未启用开发兜底。"],
      stale: true,
      fallbackUsed: false,
    };
  }
  const fallbackTickets = parlays.filter((ticket) => {
    const passTypeAllowed = !options.passType || options.passType === "all" || ticket.passType === options.passType;
    const budgetAllowed = !options.maxBudget || ticket.totalStake <= options.maxBudget;
    const structureAllowed = options.allowMultiple === false ? !ticket.isMultiple : true;
    const lockedFixtureAllowed = (options.lockedFixtureIds ?? []).every((fixtureId) =>
      ticket.legs.some((leg) => leg.fixtureId === fixtureId),
    );
    return passTypeAllowed && budgetAllowed && structureAllowed && lockedFixtureAllowed;
  });
  return {
    tickets: fallbackTickets.map((ticket) => parlayTicketSchema.parse(ticket)),
    warnings: [],
    stale: false,
    fallbackUsed: true,
  };
}

export async function getRecommendationEngineAnswer(
  options: ParlayTicketRequestOptions = {},
): Promise<RecommendationEngineAnswer | null> {
  const response = await fetchApi("/recommendations/generate", recommendationGenerateResponseSchema, {
    method: "POST",
    body: JSON.stringify({
      as_of_time_utc: new Date().toISOString(),
      pass_type: options.passType ?? "all",
      mode: options.allowMultiple === false ? "single" : "multiple",
      strategy: "auto",
      unit_stake: options.unitStake ?? 2,
      max_budget: options.maxBudget ?? 20,
      allowed_markets: recommendationAllowedMarkets(options.allowedMarkets),
      min_probability: 0.2,
      min_data_quality_score: 50,
      candidate_limit: 200,
      require_odds: true,
      max_outcomes_per_fixture: options.allowMultiple === false ? 1 : 2,
      min_marginal_quality_gain: 0,
      dry_run: true,
    }),
  });
  if (!response) {
    return null;
  }
  return recommendationAnswerFromResponse(response.answer, {
    stale: response.stale,
    fallbackUsed: response.fallback_used,
  });
}

export async function getRecommendationEngineBundle(
  options: ParlayTicketRequestOptions = {},
  matchesForLabels: MatchPrediction[] = [],
): Promise<RecommendationEngineBundle> {
  const response = await fetchApi("/recommendations/generate", recommendationGenerateResponseSchema, {
    method: "POST",
    body: JSON.stringify({
      as_of_time_utc: new Date().toISOString(),
      pass_type: options.passType ?? "all",
      mode: options.allowMultiple === false ? "single" : "multiple",
      strategy: "auto",
      unit_stake: options.unitStake ?? 2,
      max_budget: options.maxBudget ?? 20,
      allowed_markets: recommendationAllowedMarkets(options.allowedMarkets),
      min_probability: 0.2,
      min_data_quality_score: 50,
      candidate_limit: 200,
      require_odds: true,
      max_outcomes_per_fixture: options.allowMultiple === false ? 1 : 2,
      min_marginal_quality_gain: 0,
      dry_run: true,
    }),
  });

  if (!response) {
    if (!FRONTEND_DEV_FALLBACKS_ENABLED) {
      return emptyRecommendationEngineBundle(
        "核心推荐接口不可用，未启用开发兜底。",
      );
    }
    return recommendationBundleFromFallbackTickets(
      await getParlayTickets(options),
      matchesForLabels,
    );
  }

  const flags = {
    stale: response.stale,
    fallbackUsed: response.fallback_used,
  };
  const answerSet = recommendationAnswerSetFromResponse(response.answer_set, flags);
  const answer = answerSet?.primaryAnswer ?? recommendationAnswerFromResponse(response.answer, flags);
  const singleAnswer = response.single_answer
    ? recommendationAnswerFromResponse(response.single_answer, flags)
    : null;
  const upsetAnswer = response.upset_answer
    ? recommendationAnswerFromResponse(response.upset_answer, flags)
    : null;
  const alternatives = (
    answerSet?.backupAnswers ??
    response.alternatives.map((item) => recommendationAnswerFromResponse(item, flags))
  ).filter((item) => item.status === "ready");
  const tickets = alternatives.map((item, index) =>
    parlayTicketFromRecommendationAnswer(item, matchesForLabels, index),
  );
  return {
    answer: answer.status === "ready" ? answer : null,
    singleAnswer: singleAnswer?.status === "ready" ? singleAnswer : null,
    upsetAnswer: upsetAnswer?.status === "ready" ? upsetAnswer : null,
    alternatives,
    answerSet,
    recommendation: {
      tickets,
      warnings: [...answer.warnings],
      stale: response.stale,
      fallbackUsed: response.fallback_used,
    },
  };
}

export async function getGlobalBestRecommendationBundle(
  options: ParlayTicketRequestOptions = {},
  matchesForLabels: MatchPrediction[] = [],
): Promise<RecommendationEngineBundle> {
  const response = await fetchApi("/recommendations/global-best", recommendationGlobalPlannerResponseSchema, {
    method: "POST",
    body: JSON.stringify({
      as_of_time_utc: new Date().toISOString(),
      strategy: "auto",
      unit_stake: options.unitStake ?? 2,
      max_budget: options.maxBudget ?? 20,
      allowed_markets: recommendationAllowedMarkets(options.allowedMarkets),
      pass_types: [options.passType ?? "all"],
      modes: options.allowMultiple === false ? ["single"] : ["single", "multiple"],
      locked_fixture_ids: options.lockedFixtureIds ?? [],
      locked_candidates: recommendationLockedCandidates(options.lockedCandidates),
      min_probability: 0.2,
      min_data_quality_score: 50,
      candidate_limit: 300,
      require_odds: true,
      max_outcomes_per_fixture: options.allowMultiple === false ? 1 : 2,
      min_marginal_quality_gain: 0,
      dry_run: true,
    }),
  });

  if (!response) {
    if (!FRONTEND_DEV_FALLBACKS_ENABLED) {
      return emptyRecommendationEngineBundle(
        "全局最佳答案接口不可用，未启用开发兜底。",
      );
    }
    return getRecommendationEngineBundle(options, matchesForLabels);
  }

  const flags = {
    stale: response.stale,
    fallbackUsed: response.fallback_used,
  };
  const answerSet = recommendationAnswerSetFromResponse(response.answer_set, flags);
  const answer =
    answerSet?.primaryAnswer ?? recommendationAnswerFromGlobalResponse(response.answer, flags);
  const alternatives = (
    answerSet?.backupAnswers ??
    response.alternatives.map((item) => recommendationAnswerFromResponse(item, flags))
  ).filter((item) => item.status === "ready");
  const tickets = alternatives.map((item, index) =>
    parlayTicketFromRecommendationAnswer(item, matchesForLabels, index),
  );
  return {
    answer: answer.status === "ready" ? answer : null,
    singleAnswer: null,
    upsetAnswer: null,
    alternatives,
    answerSet,
    recommendation: {
      tickets,
      warnings: [...response.result.warnings, ...answer.warnings],
      stale: response.stale,
      fallbackUsed: response.fallback_used,
    },
  };
}

function recommendationLockedCandidates(
  candidates: RecommendationLockedCandidateRequest[] | undefined,
) {
  return (candidates ?? [])
    .filter((candidate) => candidate.fixtureId)
    .map((candidate) => ({
      fixture_id: candidate.fixtureId,
      market_type: candidate.marketType,
      outcome: candidate.outcome,
    }));
}

function emptyRecommendationEngineBundle(warning: string): RecommendationEngineBundle {
  return {
    answer: null,
    singleAnswer: null,
    upsetAnswer: null,
    alternatives: [],
    answerSet: null,
    recommendation: {
      tickets: [],
      warnings: [warning],
      stale: true,
      fallbackUsed: false,
    },
  };
}

function recommendationAnswerSetFromResponse(
  answerSet: RecommendationAnswerSetResponse | null | undefined,
  flags: {
    stale: boolean;
    fallbackUsed: boolean;
  },
): RecommendationAnswerSet | null {
  if (!answerSet) {
    return null;
  }
  const summary = answerSet.summary_json;
  return {
    primaryAnswer: recommendationAnswerFromResponse(answerSet.primary_answer, flags),
    backupAnswers: answerSet.backup_answers.map((answer) =>
      recommendationAnswerFromResponse(answer, flags),
    ),
    summary: {
      calculationBasis: stringFromRecord(summary, "calculation_basis"),
      primaryStatus: stringFromRecord(summary, "primary_status"),
      primaryPassType: nullableStringFromRecord(summary, "primary_pass_type"),
      primaryMode: nullableStringFromRecord(summary, "primary_mode"),
      primaryFixtureCount: numberFromRecord(summary, "primary_fixture_count"),
      candidateBackupCount: numberFromRecord(summary, "candidate_backup_count"),
      backupCount: numberFromRecord(summary, "backup_count"),
      maxBackupCount: numberFromRecord(summary, "max_backup_count"),
      publicScope: stringFromRecord(summary, "public_scope"),
      raw: summary,
    },
  };
}

function recommendationBundleFromFallbackTickets(
  recommendation: ParlayRecommendation,
  matchesForLabels: MatchPrediction[],
): RecommendationEngineBundle {
  const answers = recommendation.tickets
    .map((ticket) =>
      recommendationAnswerFromFallbackTicket(
        ticket,
        matchesForLabels,
        recommendation.fallbackUsed,
      ),
    )
    .filter((answer) => answer.status === "ready");
  const primaryAnswer = answers[0] ?? null;
  const backupAnswers = answers.slice(1, 3);
  return {
    answer: primaryAnswer,
    singleAnswer: null,
    upsetAnswer: null,
    alternatives: backupAnswers,
    answerSet: primaryAnswer
      ? {
          primaryAnswer,
          backupAnswers,
          summary: {
            calculationBasis: "frontend_public_answer_fallback",
            primaryStatus: primaryAnswer.status,
            primaryPassType: primaryAnswer.passType,
            primaryMode: primaryAnswer.mode,
            primaryFixtureCount: primaryAnswer.fixtureCount,
            candidateBackupCount: Math.max(answers.length - 1, 0),
            backupCount: backupAnswers.length,
            maxBackupCount: 2,
            publicScope: "single_best_answer_with_necessary_backups",
            raw: {},
          },
        }
      : null,
    recommendation,
  };
}

function recommendationAnswerFromFallbackTicket(
  ticket: ParlayTicket,
  matchesForLabels: MatchPrediction[],
  fallbackUsed: boolean,
): RecommendationEngineAnswer {
  const matchByFixtureId = new Map(matchesForLabels.map((match) => [match.fixtureId, match]));
  const legProbability = safeLegProbability(ticket.hitProbability, ticket.legs.length);
  const generatedAtUtc = new Date().toISOString();
  const dataQualityScores = ticket.legs.map(
    (leg) => matchByFixtureId.get(leg.fixtureId)?.dataQualityScore ?? 70,
  );
  const averageDataQualityScore =
    dataQualityScores.reduce((sum, score) => sum + score, 0) /
    Math.max(dataQualityScores.length, 1);
  return {
    status: ticket.ruleValid ? "ready" : "unavailable",
    generatedAtUtc,
    passType: ticket.passType,
    mode: ticket.isMultiple ? "multiple" : "single",
    isMultiple: ticket.isMultiple,
    fixtureCount: ticket.legs.length,
    legs: ticket.legs.map((leg) => {
      const match = matchByFixtureId.get(leg.fixtureId);
      return {
        fixtureId: leg.fixtureId,
        marketType: fallbackMarketType(leg.market),
        outcomes: leg.outcomes.map(fallbackOutcomeKey),
        probability: legProbability,
        decimalOdds: null,
        line: null,
        side: null,
        dataQualityScore: match?.dataQualityScore ?? 70,
        modelVersion: match?.modelVersion ?? null,
        predictionSnapshotId: null,
        predictionTimeUtc: match?.predictionTimeUtc ?? null,
        kickoffTimeUtc: match?.kickoffTimeUtc ?? null,
        recommendationScore: Math.max(0, Math.min(1, ticket.roi > 0 ? 0.72 : 0.58)),
      };
    }),
    budget: {
      unitStake: ticket.unitStake,
      totalStake: ticket.totalStake,
      maxBudget: null,
      withinBudget: true,
    },
    atomicBetCount: ticket.atomicBetCount,
    hitProbability: ticket.hitProbability,
    expectedPayout: ticket.expectedPayout,
    expectedValue: ticket.ev,
    roi: ticket.roi,
    riskScore: ticket.riskScore,
    riskLevel: ticket.riskLevel,
    ruleValid: ticket.ruleValid,
    averageDataQualityScore,
    dataQualityGrade: dataQualityGradeFromScore(averageDataQualityScore),
    warnings: [],
    stale: fallbackUsed,
    fallbackUsed,
  };
}

function safeLegProbability(hitProbability: number, fixtureCount: number) {
  if (fixtureCount <= 0) {
    return Math.max(0.01, Math.min(hitProbability, 0.99));
  }
  return Math.max(0.01, Math.min(hitProbability ** (1 / fixtureCount), 0.99));
}

function fallbackMarketType(label: string) {
  if (label.includes("中国")) return "cn_handicap_1x2";
  if (label.includes("欧洲")) return "european_handicap_1x2";
  if (label.includes("亚洲")) return "asian_handicap";
  if (label.includes("比分")) return "correct_score";
  return "1x2";
}

function fallbackOutcomeKey(outcome: string) {
  const labels: Record<string, string> = {
    主胜: "home_win",
    平: "draw",
    平局: "draw",
    客胜: "away_win",
    让胜: "handicap_home_win",
    让平: "handicap_draw",
    让负: "handicap_away_win",
  };
  return labels[outcome] ?? outcome;
}

function dataQualityGradeFromScore(score: number): RecommendationEngineAnswer["dataQualityGrade"] {
  if (score >= 85) return "A";
  if (score >= 70) return "B";
  if (score >= 55) return "C";
  return "D";
}

function parseBooleanEnv(value: string | undefined) {
  return value === "1" || value === "true" || value === "yes" || value === "on";
}

function stringFromRecord(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === "string" ? value : undefined;
}

function nullableStringFromRecord(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === "string" || value === null ? value : undefined;
}

function numberFromRecord(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === "number" ? value : undefined;
}

function recommendationAllowedMarkets(markets: string[] | undefined) {
  const allowed = (markets ?? []).filter((market) =>
    recommendationBackendMarketTypes.has(market),
  );
  return allowed.length > 0
    ? allowed
    : ["1x2", "cn_handicap_1x2", "european_handicap_1x2", "correct_score"];
}

function parlayTicketFromRecommendationAnswer(
  answer: RecommendationEngineAnswer,
  matchesForLabels: MatchPrediction[],
  index: number,
): ParlayTicket {
  const matchByFixtureId = new Map(matchesForLabels.map((match) => [match.fixtureId, match]));
  const passType = answer.passType ?? "answer";
  return parlayTicketSchema.parse({
    recommendationId: `engine_${passType}_${index + 1}`,
    strategy: "",
    passType,
    isMultiple: answer.isMultiple,
    legs: answer.legs.map((leg) => {
      const match = matchByFixtureId.get(leg.fixtureId);
      return {
        fixtureId: leg.fixtureId,
        matchLabel: match ? `${match.homeTeam.name} vs ${match.awayTeam.name}` : leg.fixtureId,
        market: recommendationMarketLabel(leg.marketType),
        outcomes: leg.outcomes.map(recommendationOutcomeLabel),
      };
    }),
    atomicBetCount: answer.atomicBetCount,
    unitStake: answer.budget?.unitStake ?? 2,
    totalStake: answer.budget?.totalStake ?? 0,
    hitProbability: answer.hitProbability ?? 0,
    expectedPayout: Math.max(answer.expectedPayout ?? 0, 0),
    ev: answer.expectedValue ?? 0,
    roi: answer.roi ?? 0,
    riskLevel: recommendationRiskLevel(answer.riskLevel, answer.riskScore),
    riskScore: answer.riskScore ?? 0,
    correlationPenalty: 0,
    ruleValid: answer.ruleValid,
    explanations: [
      `核心推荐引擎生成的 ${passType} ${answer.isMultiple ? "复式" : "单式"} 候选。`,
    ],
    explanationJson: {},
    atomicBets: [],
  });
}

function recommendationMarketLabel(marketType: string) {
  const labels: Record<string, string> = {
    "1x2": "胜平负",
    cn_handicap_1x2: "中国让球",
    european_handicap_1x2: "欧洲让球",
    correct_score: "比分",
  };
  return labels[marketType] ?? marketType;
}

function recommendationOutcomeLabel(outcome: string) {
  const labels: Record<string, string> = {
    home_win: "主胜",
    draw: "平局",
    away_win: "客胜",
    handicap_home_win: "让胜",
    handicap_draw: "让平",
    handicap_away_win: "让负",
  };
  return labels[outcome] ?? outcome;
}

function recommendationRiskLevel(
  riskLevel: string | null,
  riskScore: number | null,
): ParlayTicket["riskLevel"] {
  if (
    riskLevel === "low" ||
    riskLevel === "medium" ||
    riskLevel === "medium_high" ||
    riskLevel === "high"
  ) {
    return riskLevel;
  }
  const score = riskScore ?? 0.5;
  if (score >= 0.75) return "high";
  if (score >= 0.55) return "medium_high";
  if (score >= 0.35) return "medium";
  return "low";
}

export async function getRecommendationLifecycleDetail(
  recommendationRunId: number | undefined,
): Promise<RecommendationLifecycleDetail | null> {
  if (!recommendationRunId) {
    return null;
  }
  const response = await fetchApi(
    `/recommendations/${recommendationRunId}/lifecycle`,
    recommendationLifecycleResponseSchema,
  );
  return response ? recommendationLifecycleFromResponse(response) : null;
}

export async function getAccuracySummary(options: AccuracySummaryRequestOptions = {}) {
  const searchParams = new URLSearchParams({
    model_version: options.modelVersion ?? "active",
    competition_id: options.competitionId ?? "all",
    market: options.market ?? "all",
    window: options.window ?? "90d",
  });
  const response = await fetchApi(
    `/accuracy/summary?${searchParams.toString()}`,
    accuracySummaryResponseSchema,
  );
  return response ? accuracyFromResponse(response) : accuracySummaryFallback;
}

export async function getRecommendationStrategyGovernance(
  options: RecommendationStrategyGovernanceRequestOptions = {},
) {
  const searchParams = new URLSearchParams({
    baseline_strategy: options.baselineStrategy ?? "accuracy_first",
    pass_type: options.passType ?? "2x1",
    mode: options.mode ?? "single",
    minimum_sample_size: String(options.minimumSampleSize ?? 30),
    minimum_baseline_sample_size: String(options.minimumBaselineSampleSize ?? 30),
  });
  for (const strategy of options.candidateStrategies ?? [
    "value_first",
    "upset_protection",
    "budget_constrained",
  ]) {
    searchParams.append("candidate_strategy", strategy);
  }
  const response = await fetchApi(
    `/recommendations/strategy-governance?${searchParams.toString()}`,
    recommendationStrategyGovernanceOverviewResponseSchema,
  );
  return response
    ? recommendationStrategyGovernanceFromResponse(response)
    : strategyGovernanceFallback;
}

function normalizeRuntimeIncidentFilters(
  filters: Partial<ProviderRuntimeIncidentFilters> | undefined,
): ProviderRuntimeIncidentFilters {
  const source = filters?.source?.trim() || null;
  return {
    limit: boundedNumber(filters?.limit, 20, 1, 100),
    offset: boundedNumber(filters?.offset, 0, 0, 1_000_000),
    lookbackDays: boundedNumber(filters?.lookbackDays, 30, 1, 3650),
    incidentStatus: runtimeIncidentStatusFilter(filters?.incidentStatus),
    alertLevel: runtimeIncidentAlertLevelFilter(filters?.alertLevel),
    notificationStatus: runtimeIncidentNotificationFilter(filters?.notificationStatus),
    source: source ? source.slice(0, 120) : null,
  };
}

function providerRuntimeIncidentPath(filters: ProviderRuntimeIncidentFilters) {
  const searchParams = new URLSearchParams({
    limit: filters.limit.toString(),
    offset: filters.offset.toString(),
    lookback_days: filters.lookbackDays.toString(),
  });
  if (filters.incidentStatus !== "all") {
    searchParams.set("incident_status", filters.incidentStatus);
  }
  if (filters.alertLevel !== "all") {
    searchParams.set("alert_level", filters.alertLevel);
  }
  if (filters.notificationStatus !== "all") {
    searchParams.set("notification_status", filters.notificationStatus);
  }
  if (filters.source) {
    searchParams.set("source", filters.source);
  }
  return `/providers/runtime/monitoring/incidents?${searchParams.toString()}`;
}

function boundedNumber(
  value: number | undefined,
  fallback: number,
  min: number,
  max: number,
) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return fallback;
  }
  return Math.min(Math.max(Math.trunc(value), min), max);
}

function runtimeIncidentStatusFilter(
  value: ProviderRuntimeIncidentFilters["incidentStatus"] | undefined,
): ProviderRuntimeIncidentFilters["incidentStatus"] {
  if (["open", "acknowledged", "resolved", "ignored"].includes(value ?? "")) {
    return value as ProviderRuntimeIncidentFilters["incidentStatus"];
  }
  return "all";
}

function runtimeIncidentAlertLevelFilter(
  value: ProviderRuntimeIncidentFilters["alertLevel"] | undefined,
): ProviderRuntimeIncidentFilters["alertLevel"] {
  if (["ok", "P0", "P1", "P2"].includes(value ?? "")) {
    return value as ProviderRuntimeIncidentFilters["alertLevel"];
  }
  return "all";
}

function runtimeIncidentNotificationFilter(
  value: ProviderRuntimeIncidentFilters["notificationStatus"] | undefined,
): ProviderRuntimeIncidentFilters["notificationStatus"] {
  if (["not_configured", "queued", "sent", "skipped", "failed"].includes(value ?? "")) {
    return value as ProviderRuntimeIncidentFilters["notificationStatus"];
  }
  return "all";
}

export async function getProviderOps(options: ProviderOpsRequestOptions = {}) {
  const includeAdmin = options.includeAdmin ?? true;
  const runtimeIncidentFilters = normalizeRuntimeIncidentFilters(
    options.runtimeIncidentFilters,
  );
  const providerOpsCoverageAsOf = new Date(
    Date.now() + 90 * 24 * 60 * 60 * 1000,
  ).toISOString();
  const [
    governance,
    mappings,
    mappingReview,
    conflictEvaluation,
    latestConflicts,
    oddsCoverage,
    oddsGapReport,
    fallbackOddsProbe,
    authorizationReviews,
    providerSyncRuns,
    providerSyncTemplates,
    providerSyncApprovals,
    predictionJobRuns,
    runtimeCredentials,
    runtimeMonitoring,
    runtimeIncidents,
    apiKeyChecklist,
    providerOpsAuditEvents,
    providerOpsRunHistory,
    latestAssessments,
  ] = await Promise.all([
    fetchApi("/providers/status", providerGovernanceResponseSchema),
    fetchApi("/providers/mappings?limit=100", providerMappingListResponseSchema),
    fetchApi("/providers/mappings/review", providerMappingReviewResponseSchema, {
      method: "POST",
      body: JSON.stringify({ dry_run: true, limit: 1000 }),
    }),
    fetchApi("/providers/conflicts/evaluate", providerConflictEvaluationResponseSchema, {
      method: "POST",
      body: JSON.stringify({ dry_run: true, limit: 1000 }),
    }),
    fetchApi(
      "/providers/conflicts/latest?limit=20",
      providerConflictEventListResponseSchema,
    ),
    fetchApi(
      "/providers/odds/coverage?competition_id=EPL&window_days=90" +
        "&max_snapshot_lag_hours=24" +
        `&as_of_time_utc=${encodeURIComponent(providerOpsCoverageAsOf)}`,
      providerOddsCoverageResponseSchema,
    ),
    fetchApi(
      "/providers/odds/gaps?competition_id=EPL&provider=the-odds-api&window_days=90" +
        "&max_snapshot_lag_hours=168&limit=50" +
        `&as_of_time_utc=${encodeURIComponent(providerOpsCoverageAsOf)}`,
      providerOddsCoverageGapResponseSchema,
    ),
    includeAdmin
      ? fetchAdminApi(
          "/providers/odds/fallback-probe/sportmonks",
          providerSportMonksFallbackOddsProbeResponseSchema,
          {
            method: "POST",
            body: JSON.stringify({
              competition_id: "EPL",
              primary_provider: "the-odds-api",
              window_days: 90,
              max_snapshot_lag_hours: 168,
              limit: 50,
              as_of_time_utc: providerOpsCoverageAsOf,
              live_provider_probe: false,
            }),
          },
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/providers/authorizations/reviews?limit=10",
          providerAuthorizationReviewListResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/ops/provider-sync/runs?limit=10",
          providerSyncWorkflowRunListResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/ops/provider-sync/templates?limit=10",
          providerSyncWorkflowTemplateListResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/ops/provider-sync/approvals?limit=100",
          providerSyncWorkflowApprovalListResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/predictions/jobs/runs?limit=8",
          predictionJobRunListResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/providers/runtime/credentials",
          providerRuntimeCredentialResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/providers/runtime/monitoring?limit=20",
          providerRuntimeMonitoringResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          providerRuntimeIncidentPath(runtimeIncidentFilters),
          providerRuntimeIncidentReportListResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/providers/runtime/api-key-checklist",
          providerApiKeyChecklistResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/ops/provider-audit/events?limit=20",
          providerOpsAuditEventListResponseSchema,
        )
      : null,
    includeAdmin
      ? fetchAdminApi(
          "/ops/provider-runs?limit=20",
          providerOpsRunHistoryListResponseSchema,
        )
      : null,
    fetchApi(
      "/providers/onboarding/assessments/latest?limit=20",
      providerOnboardingAssessmentListResponseSchema,
    ),
  ]);
  if (!governance) {
    return providerOpsFallback;
  }
  return providerOpsFromResponses({
    governance,
    mappings,
    mappingReview,
    conflictEvaluation,
    latestConflicts,
    oddsCoverage,
    oddsGapReport,
    fallbackOddsProbe,
    authorizationReviews,
    providerSyncRuns,
    providerSyncTemplates,
    providerSyncApprovals,
    predictionJobRuns,
    runtimeCredentials,
    runtimeMonitoring,
    runtimeIncidents,
    runtimeIncidentFilters,
    apiKeyChecklist,
    providerOpsAuditEvents,
    providerOpsRunHistory,
    latestAssessments,
  });
}
