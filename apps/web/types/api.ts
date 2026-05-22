export type DataQualityGrade = "A" | "B" | "C" | "D";
export type RiskLevel = "low" | "medium" | "medium_high" | "high";

export type ProbabilityItem = {
  label: string;
  probability: number;
  marketProbability?: number;
  isHighlighted?: boolean;
};

export type Team = {
  teamId: string;
  name: string;
};

export type MarketProbabilitySet = {
  label: string;
  items: ProbabilityItem[];
};

export type CorrectScore = {
  score: string;
  probability: number;
  optionKey: string;
};

export type ScoreGrid = {
  maxGoals: number;
  grid: number[][];
  tailMass: number;
  lambdaHome: number | null;
  lambdaAway: number | null;
};

export type DataFreshness = {
  stale: boolean;
  fallbackUsed: boolean;
  oddsAvailable: boolean;
  oddsFreshEnough: boolean;
  oddsMarketTypes: string[];
  oddsSnapshotTimeUtc: string | null;
  oddsSnapshotLagHours: number | null;
  lineupAvailable: boolean;
  lineupFreshEnough: boolean;
  lineupSnapshotTimeUtc: string | null;
  lineupSnapshotLagHours: number | null;
  injuryAvailable: boolean;
  injuryFreshEnough: boolean;
  injurySnapshotTimeUtc: string | null;
  injurySnapshotLagHours: number | null;
  messages: string[];
};

export type UpsetAlert = {
  type: string;
  label: string;
  targetOutcome: string;
  favorite?: string;
  favoriteModelProbability?: number;
  favoriteMarketProbability?: number;
  modelProbability: number;
  marketProbability: number;
  probabilityGap: number;
  favoriteFragilityScore: number;
  riskLevel: RiskLevel;
  explanations: string[];
  contributions?: UpsetContribution[];
  explanationGroups?: UpsetExplanationGroup[];
};

export type UpsetContribution = {
  key: string;
  label: string;
  score: number;
  description: string;
};

export type UpsetExplanationGroup = {
  title: string;
  items: string[];
};

export type MatchPrediction = {
  fixtureId: string;
  competitionId: string;
  competitionName: string;
  kickoffTimeUtc: string;
  homeTeam: Team;
  awayTeam: Team;
  status: "scheduled" | "stale" | "beta";
  modelStatus: "beta" | "production";
  modelVersion: string;
  featureVersion: string;
  calibrationVersion: string;
  predictionTimeUtc: string;
  dataQualityScore: number;
  dataQualityGrade: DataQualityGrade;
  dataFreshness?: DataFreshness;
  confidence: "low" | "medium" | "high";
  oneXTwo: ProbabilityItem[];
  cnHandicap: MarketProbabilitySet;
  asianHandicap: MarketProbabilitySet;
  europeanHandicap: MarketProbabilitySet;
  correctScores: CorrectScore[];
  scoreGrid: ScoreGrid;
  tailEvents: ProbabilityItem[];
  upsetAlerts: UpsetAlert[];
  keyFactors: {
    model: string[];
    market: string[];
    lineup: string[];
    schedule: string[];
    uncertainty: string[];
  };
};

export type ParlayLeg = {
  fixtureId: string;
  matchLabel: string;
  market: string;
  outcomes: string[];
};

export type AtomicParlayLeg = {
  fixtureId: string;
  marketType: string;
  outcome: string;
  probability: number;
  odds: number;
  line: number | null;
};

export type AtomicParlayBet = {
  legs: AtomicParlayLeg[];
  stake: number;
  probability: number;
  oddsProduct: number;
  expectedPayout: number;
  expectedValue: number;
  roi: number;
};

export type ParlayTicket = {
  recommendationId: string;
  strategy: string;
  passType: string;
  isMultiple: boolean;
  legs: ParlayLeg[];
  atomicBetCount: number;
  unitStake: number;
  totalStake: number;
  hitProbability: number;
  expectedPayout: number;
  ev: number;
  roi: number;
  riskLevel: RiskLevel;
  riskScore: number;
  correlationPenalty: number;
  ruleValid: boolean;
  explanations: string[];
  explanationJson: Record<string, unknown>;
  atomicBets: AtomicParlayBet[];
};

export type ParlayRecommendation = {
  tickets: ParlayTicket[];
  warnings: string[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type RecommendationAnswerLeg = {
  fixtureId: string;
  marketType: string;
  outcomes: string[];
  probability: number;
  decimalOdds: number | null;
  line: number | null;
  side: string | null;
  dataQualityScore: number;
  modelVersion: string | null;
  predictionSnapshotId: number | null;
  predictionTimeUtc: string | null;
  kickoffTimeUtc: string | null;
  recommendationScore: number;
};

export type RecommendationAnswerBudget = {
  unitStake: number;
  totalStake: number;
  maxBudget: number | null;
  withinBudget: boolean;
};

export type RecommendationEngineAnswer = {
  status: "ready" | "unavailable";
  generatedAtUtc: string;
  passType: string | null;
  mode: "single" | "multiple" | null;
  isMultiple: boolean;
  fixtureCount: number;
  legs: RecommendationAnswerLeg[];
  budget: RecommendationAnswerBudget | null;
  atomicBetCount: number;
  hitProbability: number | null;
  expectedPayout: number | null;
  expectedValue: number | null;
  roi: number | null;
  riskScore: number | null;
  riskLevel: string | null;
  ruleValid: boolean;
  averageDataQualityScore: number | null;
  dataQualityGrade: DataQualityGrade | null;
  warnings: string[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type RecommendationAnswerSetSummary = {
  calculationBasis?: string;
  primaryStatus?: string;
  primaryPassType?: string | null;
  primaryMode?: string | null;
  primaryFixtureCount?: number;
  candidateBackupCount?: number;
  backupCount?: number;
  maxBackupCount?: number;
  publicScope?: string;
  raw: Record<string, unknown>;
};

export type RecommendationAnswerSet = {
  primaryAnswer: RecommendationEngineAnswer;
  backupAnswers: RecommendationEngineAnswer[];
  summary: RecommendationAnswerSetSummary;
};

export type RecommendationEngineBundle = {
  answer: RecommendationEngineAnswer | null;
  singleAnswer: RecommendationEngineAnswer | null;
  upsetAnswer: RecommendationEngineAnswer | null;
  alternatives: RecommendationEngineAnswer[];
  answerSet: RecommendationAnswerSet | null;
  recommendation: ParlayRecommendation;
};

export type RecommendationLifecycleStatus =
  | "candidate"
  | "current"
  | "superseded"
  | "locked"
  | "confirmed_manual"
  | "live"
  | "settled"
  | "invalidated";

export type RecommendationRunLifecycle = {
  recommendationRunId: number;
  runKey: string;
  status: RecommendationLifecycleStatus;
  selectedFixtureIds: string[];
  lockedFixtureIds: string[];
  createdAt: string;
};

export type RecommendationLockedLeg = {
  recommendationLockedLegId: number;
  recommendationRunId: number;
  fixtureId: string;
  marketType: string;
  outcome: string;
  lockedAtUtc: string;
  status: string;
  metadataJson: Record<string, unknown>;
};

export type RecommendationLifecycleEvent = {
  recommendationLifecycleEventId: number;
  recommendationRunId: number;
  recommendationKey: string;
  fromStatus: RecommendationLifecycleStatus;
  toStatus: RecommendationLifecycleStatus;
  reasonCode: string;
  eventTimeUtc: string;
  metadataJson: Record<string, unknown>;
};

export type RecommendationLifecycleDetail = {
  run: RecommendationRunLifecycle;
  lockedLegs: RecommendationLockedLeg[];
  events: RecommendationLifecycleEvent[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type RecommendationStrategyEvidence = {
  strategy: string;
  passType: string;
  mode: string;
  sampleSize: number;
  settledRunCount: number;
  hitCount: number;
  totalStake: number;
  grossPayout: number;
  profitLoss: number;
  roi: number | null;
  hitRate: number | null;
  averageExpectedRoi: number | null;
  averageExpectedHitProbability: number | null;
  averageHitCalibrationError: number | null;
  meanAbsoluteHitCalibrationError: number | null;
  firstEvaluationTimeUtc: string | null;
  lastEvaluationTimeUtc: string | null;
};

export type RecommendationStrategyGovernanceItem = {
  candidateStrategy: string;
  baselineStrategy: string;
  passType: string;
  mode: string;
  candidateEvidence: RecommendationStrategyEvidence;
  baselineEvidence: RecommendationStrategyEvidence;
  decision: "shadow_candidate" | "keep_experiment";
  nextStatus: "shadow" | "experiment";
  reasons: string[];
  shouldRollback: boolean;
  rollbackTargetStrategy: string | null;
  rollbackReasons: string[];
  metricDeltas: {
    roiDelta: number | null;
    hitRateDelta: number | null;
    calibrationErrorDelta: number | null;
    expectedRoiDelta: number | null;
  };
  warnings: string[];
};

export type RecommendationStrategyGovernance = {
  generatedAtUtc: string;
  items: RecommendationStrategyGovernanceItem[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type AccuracyMetricSet = {
  logLoss: number | null;
  brierScore: number | null;
  ece: number | null;
  sampleSize: number;
};

export type AccuracyCompetitionMetric = AccuracyMetricSet & {
  competitionId: string;
  competitionName: string;
};

export type CalibrationBucket = {
  bucketStart: number;
  bucketEnd: number;
  averagePredictedProbability: number;
  actualFrequency: number;
  sampleSize: number;
};

export type ErrorTypeSummary = {
  tag: string;
  label: string;
  count: number;
  share: number;
  examples: string[];
};

export type ModelComparison = {
  baselineModelVersion: string;
  candidateModelVersion: string;
  baselineLogLoss: number | null;
  candidateLogLoss: number | null;
  baselineBrierScore: number | null;
  candidateBrierScore: number | null;
  calibrationDelta: number | null;
  sampleSize: number;
  decision: "promote_candidate" | "keep_baseline" | "needs_review";
  reasons: string[];
};

export type AccuracySummary = {
  logLoss: number | null;
  brierScore: number | null;
  ece: number | null;
  sampleSize: number;
  byMarket: Record<string, AccuracyMetricSet>;
  byCompetition: AccuracyCompetitionMetric[];
  calibrationBuckets: CalibrationBucket[];
  errorTypes: ErrorTypeSummary[];
  modelComparisons: ModelComparison[];
  modelVersion: string;
  window: string;
  filters: {
    modelVersion: string;
    competitionId: string;
    market: string;
    window: string;
  };
  generatedAtUtc: string;
  stale: boolean;
};

export type ProviderAuthorization = {
  providerName: string;
  status: "active" | "pending_review" | "research_only" | "blocked" | "expired";
  capabilities: string[];
  termsCheckedAtUtc: string | null;
  commercialUseAllowed: boolean;
  retentionAllowed: boolean;
  allowedUse: string;
  rateLimit: string | null;
  historicalDataAllowed: boolean;
  redistributionAllowed: boolean;
  termsUrl: string | null;
  lastReviewedAtUtc: string | null;
  nextReviewDueAtUtc: string | null;
  owner: string;
  apiKeyEnvVar: string | null;
  notes: string;
};

export type ProviderAuthorizationReview = {
  providerAuthorizationReviewId: number;
  providerName: string;
  reviewReference: string;
  reviewStatus: "approved" | "research_only" | "needs_review" | "blocked";
  reviewedBy: string;
  reviewedAtUtc: string;
  termsUrl: string | null;
  termsVersionHash: string | null;
  allowedUse: string;
  commercialUseAllowed: boolean;
  retentionAllowed: boolean;
  historicalDataAllowed: boolean;
  redistributionAllowed: boolean;
  rateLimit: string | null;
  nextReviewDueAtUtc: string | null;
  evidenceJson: Record<string, unknown>;
  notes: string;
  createdAtUtc: string;
};

export type ProviderRuntimeCredential = {
  providerName: string;
  capabilities: string[];
  apiKeyEnvVar: string | null;
  runtimeEnvVar: string | null;
  keyConfigured: boolean;
  dryRunMode: "local_only" | "mock_sample" | "real_provider" | "blocked";
  commitMode: "not_applicable" | "ready" | "blocked";
  safeToCallRealProvider: boolean;
  mockDryRunEnabled: boolean;
  requiresApiKeyForCommit: boolean;
  nextAction: string;
  notes: string[];
};

export type ProviderRuntimeCredentials = {
  fetched: boolean;
  mockDryRunEnabled: boolean;
  generatedAtUtc: string;
  items: ProviderRuntimeCredential[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderRuntimeProbeStatus =
  | "not_configured"
  | "key_configured"
  | "ok"
  | "limited"
  | "auth_failed"
  | "rate_limited"
  | "unavailable"
  | "adapter_planned";

export type ProviderRuntimeMonitorNextAction =
  | "no_action"
  | "configure_runtime_key"
  | "review_provider_plan_limit"
  | "check_provider_credentials"
  | "retry_after_provider_recovery"
  | "adapter_not_ready";

export type ProviderRuntimeAlertSeverity = "P0" | "P1" | "P2";
export type ProviderRuntimeAlertLevel = "ok" | ProviderRuntimeAlertSeverity;
export type ProviderRuntimeIncidentStatus =
  | "open"
  | "acknowledged"
  | "resolved"
  | "ignored";
export type ProviderRuntimeIncidentNotificationStatus =
  | "not_configured"
  | "queued"
  | "sent"
  | "skipped"
  | "failed";

export type ProviderRuntimeMonitoringAlert = {
  alertId: string;
  severity: ProviderRuntimeAlertSeverity;
  providerName: string | null;
  capability: string | null;
  metric: string;
  currentValue: number | string | null;
  threshold: number | string | null;
  message: string;
  recommendedAction: string;
};

export type ProviderRuntimeMonitoringSnapshot = {
  providerRuntimeSnapshotId: number | null;
  providerName: string;
  capability: string;
  probeStatus: ProviderRuntimeProbeStatus;
  keyConfigured: boolean;
  liveProbe: boolean;
  safeToCallRealProvider: boolean;
  latencyMs: number | null;
  errorRate: number | null;
  successCount: number;
  failureCount: number;
  rateLimitRemaining: number | null;
  quotaWindow: string | null;
  fallbackUsed: boolean;
  message: string;
  nextAction: ProviderRuntimeMonitorNextAction;
  metadataJson: Record<string, unknown>;
  observedAtUtc: string;
};

export type ProviderRuntimeMonitoring = {
  fetched: boolean;
  generatedAtUtc: string;
  summary: {
    providerCount: number;
    healthyCount: number;
    degradedCount: number;
    rateLimitedCount: number;
    authFailedCount: number;
    unavailableCount: number;
    notConfiguredCount: number;
    fallbackProviderCount: number;
    averageLatencyMs: number | null;
    latestObservedAtUtc: string | null;
  };
  alertLevel: ProviderRuntimeAlertLevel;
  alerts: ProviderRuntimeMonitoringAlert[];
  thresholds: {
    providerLatencyP2Ms: number;
    providerLatencyP1Ms: number;
    providerErrorRateP1: number;
    providerPlanLimitP2: number;
    fallbackUsageRateP1: number;
  };
  items: ProviderRuntimeMonitoringSnapshot[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderRuntimeIncidentReport = {
  providerRuntimeIncidentReportId: number;
  alertLevel: ProviderRuntimeAlertLevel;
  alertCount: number;
  snapshotCount: number;
  summaryJson: Record<string, unknown>;
  alertsJson: Record<string, unknown>[];
  thresholdsJson: Record<string, unknown>;
  source: string;
  createdBy: string;
  metadataJson: Record<string, unknown>;
  incidentStatus: ProviderRuntimeIncidentStatus;
  acknowledgedBy: string | null;
  acknowledgedAtUtc: string | null;
  resolvedBy: string | null;
  resolvedAtUtc: string | null;
  resolutionNote: string | null;
  notificationStatus: ProviderRuntimeIncidentNotificationStatus;
  notificationPayloadJson: Record<string, unknown>;
  updatedAtUtc: string | null;
  createdAtUtc: string;
};

export type ProviderRuntimeIncidentTrendBucket = {
  bucketDate: string;
  totalCount: number;
  openCount: number;
  acknowledgedCount: number;
  resolvedCount: number;
  ignoredCount: number;
  activeCount: number;
  p0Count: number;
  p1Count: number;
  p2Count: number;
  notificationFailedCount: number;
};

export type ProviderRuntimeIncidentSummary = {
  lookbackDays: number;
  totalCount: number;
  openCount: number;
  acknowledgedCount: number;
  resolvedCount: number;
  ignoredCount: number;
  activeCount: number;
  p0Count: number;
  p1Count: number;
  p2Count: number;
  notificationFailedCount: number;
  latestCreatedAtUtc: string | null;
  meanTimeToResolveMinutes: number | null;
  trendBuckets: ProviderRuntimeIncidentTrendBucket[];
};

export type ProviderRuntimeIncidentFilters = {
  limit: number;
  offset: number;
  lookbackDays: number;
  incidentStatus: ProviderRuntimeIncidentStatus | "all";
  alertLevel: ProviderRuntimeAlertLevel | "all";
  notificationStatus: ProviderRuntimeIncidentNotificationStatus | "all";
  source: string | null;
};

export type ProviderRuntimeIncidents = {
  fetched: boolean;
  items: ProviderRuntimeIncidentReport[];
  summary: ProviderRuntimeIncidentSummary;
  filters: ProviderRuntimeIncidentFilters;
  limit: number;
  offset: number;
  totalCount: number;
  hasMore: boolean;
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderApiKeyChecklistItem = {
  providerName: string;
  nutmegRole: string;
  priority: number;
  adapterStatus: "supported_now" | "adapter_planned";
  requiredEnvVar: string;
  keyConfigured: boolean;
  applyUrl: string;
  docsUrl: string;
  officialFreeTierNote: string;
  freeTierFit: "good_for_first_dry_run" | "trial_required" | "limited_for_soccer";
  operatorAction: string;
  sourceCheckedAtUtc: string;
};

export type ProviderApiKeyChecklist = {
  fetched: boolean;
  items: ProviderApiKeyChecklistItem[];
  generatedAtUtc: string;
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderOpsAuditEvent = {
  providerOpsAuditEventId: number;
  eventType: string;
  operatorName: string | null;
  actionSurface: string;
  targetType: string | null;
  targetId: string | null;
  outcome: "success" | "failure" | "blocked";
  requestPath: string | null;
  requestMethod: string | null;
  metadataJson: Record<string, unknown>;
  createdAtUtc: string;
};

export type ProviderOpsAuditTrail = {
  fetched: boolean;
  items: ProviderOpsAuditEvent[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderOpsRunHistoryRecord = {
  providerOpsRunId: number;
  runName: string;
  runType: string;
  source: string;
  status: "success" | "failure" | "skipped";
  operatorName: string | null;
  startedAtUtc: string | null;
  completedAtUtc: string | null;
  durationMs: number | null;
  exitCode: number | null;
  summaryJson: Record<string, unknown>;
  outputExcerpt: string | null;
  metadataJson: Record<string, unknown>;
  createdAtUtc: string;
};

export type ProviderOpsRunHistory = {
  fetched: boolean;
  items: ProviderOpsRunHistoryRecord[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderReadiness = {
  competitionId: string;
  competitionName: string;
  targetStage: "beta" | "production";
  decision: "beta_ready" | "production_ready" | "not_ready";
  dataQuality: {
    score: number;
    grade: DataQualityGrade;
    parlayEligible: boolean;
    components: {
      fixtureReliability: number;
      oddsCoverage: number;
      lineupInjuryCoverage: number;
      historicalStatsCompleteness: number;
      providerConsistency: number;
      dataFreshness: number;
    };
    messages: string[];
  };
  reasons: string[];
  betaReady: boolean;
  productionReady: boolean;
};

export type ProviderEntityMapping = {
  mappingId: number;
  provider: string;
  entityType: string;
  providerEntityId: string;
  canonicalEntityId: string;
  confidence: number;
  createdAtUtc: string;
  updatedAtUtc: string;
};

export type ProviderMappingSummary = {
  provider: string;
  entityType: string;
  mappingCount: number;
  averageConfidence: number;
  minimumConfidence: number;
  latestUpdatedAtUtc: string;
};

export type ProviderMappingReviewIssue = {
  issueId: string;
  issueType: "low_confidence" | "same_provider_canonical_collision" | "stale_mapping";
  severity: "info" | "warning" | "critical";
  provider: string;
  entityType: string;
  canonicalEntityId: string;
  providerEntityIds: string[];
  mappingIds: number[];
  confidenceMin: number | null;
  latestUpdatedAtUtc: string | null;
  reasons: string[];
  recommendedAction: string;
};

export type ProviderMappingReview = {
  dryRun: boolean;
  asOfTimeUtc: string;
  checkedMappingCount: number;
  issueCount: number;
  criticalCount: number;
  warningCount: number;
  infoCount: number;
  issues: ProviderMappingReviewIssue[];
  stale: boolean;
  fallbackUsed: boolean;
};

export type TrustedProviderPriority = {
  providerName: string;
  capability: string;
  priorityRank: number;
  reason: string;
};

export type ProviderConflictEvent = {
  sourceIssueId: string | null;
  conflictType: "provider_mapping_conflict" | "provider_observation_conflict";
  severity: "info" | "warning" | "critical";
  entityType: string;
  canonicalEntityId: string;
  providerNames: string[];
  providerEntityIds: string[];
  trustedProvider: string | null;
  dataQualityScoreDelta: number;
  evidenceJson: Record<string, unknown>;
  recommendedAction: string;
};

export type ProviderPersistedConflictEvent = ProviderConflictEvent & {
  providerConflictEventId: number;
  sourceReviewRunId: number | null;
  resolutionStatus: "open" | "resolved" | "ignored";
  requestedBy: string | null;
  createdAtUtc: string;
  resolvedAtUtc: string | null;
};

export type ProviderConflictGovernance = {
  dryRun: boolean;
  asOfTimeUtc: string;
  checkedIssueCount: number;
  conflictCount: number;
  criticalCount: number;
  warningCount: number;
  infoCount: number;
  providerConsistencyAfterConflicts: number;
  dataQualityScoreDelta: number;
  trustedPriorities: TrustedProviderPriority[];
  events: ProviderConflictEvent[];
  persistedEvents: ProviderPersistedConflictEvent[];
  persistedOpenCount: number;
  persistedResolvedCount: number;
  persistedIgnoredCount: number;
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderOddsCoverage = {
  fetched: boolean;
  competitionId: string;
  competitionName: string;
  fixtureCount: number;
  oddsSnapshotCount: number;
  bookmakerCount: number;
  oddsCoverage: number;
  oneXTwoCoverage: number;
  handicapCoverage: number;
  freshOddsCoverage: number;
  marketTypes: string[];
  generatedAtUtc: string;
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderOddsCoverageGapIssue =
  | "no_odds"
  | "missing_market"
  | "stale_odds"
  | "unmapped"
  | "provider_event_unavailable";

export type ProviderOddsCoverageFallbackCandidate = {
  providerName: string;
  coverageRole: string;
  adapterStatus: "supported_now" | "adapter_planned";
  requiredEnvVar: string;
  recommendedAction: string;
};

export type ProviderOddsCoverageGap = {
  fixtureId: string;
  competitionId: string;
  competitionName: string;
  kickoffTimeUtc: string;
  homeTeamName: string;
  awayTeamName: string;
  issueTypes: ProviderOddsCoverageGapIssue[];
  recommendedAction: string;
  oddsSnapshotCount: number;
  bookmakerCount: number;
  has1x2: boolean;
  hasHandicap: boolean;
  freshEnough: boolean;
  latestSnapshotTimeUtc: string | null;
  latestSnapshotLagHours: number | null;
  marketTypes: string[];
  hasProviderMapping: boolean;
  provider: string;
  providerEventId: string | null;
  providerMappingId: number | null;
  providerMappingConfidence: number | null;
  providerMappingUpdatedAtUtc: string | null;
  eventAvailabilityNote: string | null;
  fallbackCandidates: ProviderOddsCoverageFallbackCandidate[];
};

export type ProviderOddsGapReport = {
  fetched: boolean;
  competitionId: string;
  competitionName: string;
  provider: string;
  windowStartUtc: string;
  asOfTimeUtc: string;
  maxSnapshotLagHours: number;
  fixtureCount: number;
  gapCount: number;
  noOddsCount: number;
  staleOddsCount: number;
  providerEventUnavailableCount: number;
  missing1x2Count: number;
  missingHandicapCount: number;
  unmappedFixtureCount: number;
  mappedGapCount: number;
  items: ProviderOddsCoverageGap[];
  generatedAtUtc: string;
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderFallbackOddsProbeStatus =
  | "mapping_missing"
  | "mapped_probe_ready"
  | "covered"
  | "mapped_no_supported_odds"
  | "not_configured"
  | "provider_auth_failed"
  | "provider_limited"
  | "provider_rate_limited"
  | "provider_unavailable"
  | "adapter_planned";

export type ProviderFallbackOddsProbeItem = {
  fixtureId: string;
  competitionId: string;
  kickoffTimeUtc: string;
  homeTeamName: string;
  awayTeamName: string;
  primaryProvider: string;
  fallbackProvider: string;
  status: ProviderFallbackOddsProbeStatus;
  canRecoverGap: boolean;
  providerFixtureId: string | null;
  providerMappingId: number | null;
  providerMappingConfidence: number | null;
  providerKeyConfigured: boolean;
  liveProviderProbe: boolean;
  normalizedOddsCount: number;
  bookmakerCount: number;
  marketTypes: string[];
  warnings: string[];
  recommendedAction: string;
};

export type ProviderFallbackOddsProbe = {
  fetched: boolean;
  competitionId: string;
  primaryProvider: string;
  fallbackProvider: string;
  liveProviderProbe: boolean;
  providerKeyConfigured: boolean;
  checkedGapCount: number;
  providerEventUnavailableCount: number;
  mappedFallbackCount: number;
  probedFixtureCount: number;
  recoverableFixtureCount: number;
  normalizedOddsCount: number;
  bookmakerCount: number;
  marketTypes: string[];
  items: ProviderFallbackOddsProbeItem[];
  warnings: string[];
  generatedAtUtc: string;
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderSyncWorkflowRun = {
  providerSyncWorkflowRunId: number;
  status: "running" | "completed" | "failed";
  dryRun: boolean;
  requestedBy: string | null;
  startedAtUtc: string;
  completedAtUtc: string | null;
  durationMs: number | null;
  fixtureSyncRunId: number | null;
  oddsSyncRunIds: number[];
  availabilitySyncRunIds: number[];
  fixtureCount: number;
  oddsSnapshotCount: number;
  availabilitySnapshotCount: number;
  rawPayloadIds: number[];
  canonicalFixtureIds: string[];
  prematchWorkflowRunId: number | null;
  warnings: string[];
  errorMessage: string | null;
  metadataJson: Record<string, unknown>;
};

export type ProviderSyncWorkflowPreflightIssue = {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
  fieldPath: string | null;
};

export type ProviderSyncWorkflowPreflightResult = {
  valid: boolean;
  taskCount: number;
  syncTypes: string[];
  canonicalFixtureIds: string[];
  issueCount: number;
  errorCount: number;
  warningCount: number;
  infoCount: number;
  issues: ProviderSyncWorkflowPreflightIssue[];
  metadataJson: Record<string, unknown>;
};

export type ProviderSyncWorkflowTemplate = {
  providerSyncWorkflowTemplateId: number;
  templateName: string;
  description: string | null;
  dryRun: boolean;
  fixtureSync: Record<string, unknown> | null;
  oddsSyncs: Record<string, unknown>[];
  availabilitySyncs: Record<string, unknown>[];
  runConflictDetection: boolean;
  conflictObservationLookbackHours: number;
  conflictLimit: number;
  createdBy: string | null;
  createdAtUtc: string;
  updatedAtUtc: string;
  archivedAtUtc: string | null;
  archivedBy: string | null;
  archiveReason: string | null;
  metadataJson: Record<string, unknown>;
  preflightResult: ProviderSyncWorkflowPreflightResult;
};

export type ProviderSyncWorkflowApproval = {
  providerSyncWorkflowApprovalId: number;
  approvalType: string;
  approvalStatus: "approved" | "superseded" | "revoked";
  providerSyncWorkflowTemplateId: number | null;
  providerSyncWorkflowRunId: number | null;
  approvedBy: string | null;
  approvedAtUtc: string;
  approvalNote: string | null;
  requestPayloadJson: Record<string, unknown>;
  metadataJson: Record<string, unknown>;
};

export type PredictionJobRun = {
  predictionJobRunId: number;
  jobType: "mock_prematch_predictions" | "canonical_prematch_predictions";
  status: "running" | "completed" | "failed";
  dryRun: boolean;
  requestedBy: string | null;
  startedAtUtc: string;
  completedAtUtc: string | null;
  durationMs: number | null;
  fixtureCount: number;
  generatedCount: number;
  skippedFixtureIds: string[];
  warnings: string[];
  errorMessage: string | null;
  dataQualityScores: Record<string, number>;
};

export type ProviderSyncWorkflowOps = {
  fetched: boolean;
  runs: ProviderSyncWorkflowRun[];
  templates: ProviderSyncWorkflowTemplate[];
  templatesFetched: boolean;
  approvals: ProviderSyncWorkflowApproval[];
  approvalsFetched: boolean;
  stale: boolean;
  fallbackUsed: boolean;
};

export type PredictionQualityGateOps = {
  fetched: boolean;
  runs: PredictionJobRun[];
  latestRun: PredictionJobRun | null;
  stale: boolean;
  fallbackUsed: boolean;
};

export type ProviderOps = {
  providers: ProviderAuthorization[];
  authorizationReviews: {
    fetched: boolean;
    stale: boolean;
    fallbackUsed: boolean;
    items: ProviderAuthorizationReview[];
  };
  runtimeCredentials: ProviderRuntimeCredentials;
  runtimeMonitoring: ProviderRuntimeMonitoring;
  runtimeIncidents: ProviderRuntimeIncidents;
  apiKeyChecklist: ProviderApiKeyChecklist;
  auditTrail: ProviderOpsAuditTrail;
  runHistory: ProviderOpsRunHistory;
  readiness: ProviderReadiness[];
  mappings: ProviderEntityMapping[];
  mappingSummary: ProviderMappingSummary[];
  mappingReview: ProviderMappingReview;
  conflictGovernance: ProviderConflictGovernance;
  oddsCoverage: ProviderOddsCoverage;
  oddsGapReport: ProviderOddsGapReport;
  fallbackOddsProbe: ProviderFallbackOddsProbe;
  providerSyncWorkflow: ProviderSyncWorkflowOps;
  predictionQualityGate: PredictionQualityGateOps;
  latestAssessmentCount: number;
  generatedAtUtc: string;
  stale: boolean;
  fallbackUsed: boolean;
};
