import {
  Activity,
  ClipboardCheck,
  DatabaseZap,
  GitCompareArrows,
  Link2,
  ShieldCheck,
  ShieldQuestion,
} from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { ProviderAuthorizationReviewActions } from "@/components/providers/provider-authorization-review-actions";
import { ProviderConflictActions } from "@/components/providers/provider-conflict-actions";
import { ProviderMappedOddsActions } from "@/components/providers/provider-mapped-odds-actions";
import {
  ProviderOpsAccessPanel,
  ProviderOpsLockedControls,
} from "@/components/providers/provider-ops-access-panel";
import { ProviderOpsRunbook } from "@/components/providers/provider-ops-runbook";
import { ProviderPredictionGateActions } from "@/components/providers/provider-prediction-gate-actions";
import { ProviderRuntimeIncidentActions } from "@/components/providers/provider-runtime-incident-actions";
import { ProviderSyncWorkflowActions } from "@/components/providers/provider-sync-workflow-actions";
import { getProviderOps } from "@/lib/api";
import { formatDateTime, formatPercent } from "@/lib/format";
import { getProviderOpsAccessState } from "@/lib/provider-ops-auth";
import type {
  ProviderAuthorization,
  ProviderAuthorizationReview,
  ProviderApiKeyChecklistItem,
  ProviderConflictGovernance,
  ProviderEntityMapping,
  ProviderMappingReview,
  ProviderMappingSummary,
  ProviderOddsCoverageGap,
  ProviderOps,
  ProviderOpsAuditEvent,
  ProviderOpsRunHistoryRecord,
  ProviderReadiness,
  ProviderRuntimeCredential,
  ProviderRuntimeIncidentFilters,
  ProviderRuntimeIncidentReport,
  ProviderRuntimeMonitoringAlert,
  ProviderRuntimeMonitoringSnapshot,
} from "@/types/api";

import "@/components/providers/provider-ops.css";

type BadgeTone = ComponentProps<typeof Badge>["tone"];
type ProviderOpsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ProviderOpsPage({ searchParams }: ProviderOpsPageProps) {
  const params = await searchParams;
  const runtimeIncidentFilters = runtimeIncidentFiltersFromSearchParams(params);
  const access = await getProviderOpsAccessState();
  const ops = await getProviderOps({
    includeAdmin: access.unlocked,
    runtimeIncidentFilters,
  });
  const activeProviders = ops.providers.filter((provider) => provider.status === "active").length;
  const reviewProviders = ops.providers.filter((provider) => provider.status === "pending_review").length;
  const mappedEntities = ops.mappingSummary.reduce((sum, item) => sum + item.mappingCount, 0);
  const reviewIssueCount = ops.mappingReview.issueCount;
  const conflictCount = ops.conflictGovernance.conflictCount;
  const persistedOpenConflicts = ops.conflictGovernance.persistedOpenCount;
  const betaReady = ops.readiness.filter((item) => item.betaReady).length;
  const realProviderReady = ops.runtimeCredentials.items.filter(
    (item) => item.safeToCallRealProvider,
  ).length;
  const externalProviderCount = ops.runtimeCredentials.items.filter(
    (item) => item.requiresApiKeyForCommit,
  ).length;
  const reviewDueCount = ops.providers.filter((provider) => isReviewDue(provider)).length;
  const runtimeDegraded = ops.runtimeMonitoring.summary.degradedCount;
  const latestRuntimeIncident = ops.runtimeIncidents.items[0] ?? null;
  const runtimeIncidentSummary = ops.runtimeIncidents.summary;
  const activeRuntimeIncidents = runtimeIncidentSummary.activeCount;
  const latestAuthorizationReview = ops.authorizationReviews.items[0] ?? null;
  const latestAuditEvent = ops.auditTrail.items[0] ?? null;
  const latestOpsRun = ops.runHistory.items[0] ?? null;

  return (
    <main className="page provider-ops-page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Provider Ops</h1>
          <p className="page-copy">
            数据源状态、赛事准入、ID 映射和快照覆盖率用于支撑赛前预测链路的可追踪性。
            这里不执行同步任务，也不包含自动投注能力。
          </p>
        </div>
        <div className="badge-row">
          <Badge tone={ops.fallbackUsed ? "warning" : "success"}>
            {ops.fallbackUsed ? "Fallback data" : "Live API"}
          </Badge>
          <Badge tone={ops.stale ? "warning" : "info"}>{ops.stale ? "Stale" : "Fresh"}</Badge>
          <Badge>生成 {formatDateTime(ops.generatedAtUtc)}</Badge>
        </div>
      </header>

      <section className="section metric-row">
        <MetricCard label="已激活数据源" value={activeProviders.toString()} icon={<ShieldCheck size={18} />} />
        <MetricCard label="待审核数据源" value={reviewProviders.toString()} icon={<ShieldQuestion size={18} />} />
        <MetricCard label="映射实体" value={mappedEntities.toString()} icon={<Link2 size={18} />} />
        <MetricCard label="映射审核问题" value={reviewIssueCount.toString()} icon={<ClipboardCheck size={18} />} />
        <MetricCard label="冲突事件" value={conflictCount.toString()} icon={<GitCompareArrows size={18} />} />
        <MetricCard label="Open 冲突" value={persistedOpenConflicts.toString()} icon={<GitCompareArrows size={18} />} />
        <MetricCard label="Beta Ready" value={betaReady.toString()} icon={<DatabaseZap size={18} />} />
        <MetricCard
          label="真实 Key"
          value={`${realProviderReady}/${externalProviderCount}`}
          icon={<ShieldQuestion size={18} />}
        />
        <MetricCard label="授权复核到期" value={reviewDueCount.toString()} icon={<ShieldCheck size={18} />} />
        <MetricCard
          label="Ops 审计事件"
          value={ops.auditTrail.items.length.toString()}
          icon={<ClipboardCheck size={18} />}
        />
        <MetricCard
          label="Helper Runs"
          value={ops.runHistory.items.length.toString()}
          icon={<ClipboardCheck size={18} />}
        />
        <MetricCard
          label="Runtime 异常"
          value={runtimeDegraded.toString()}
          icon={<Activity size={18} />}
        />
      </section>

      <ProviderOpsAccessPanel access={access} />

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider Helper Run History</h2>
          <p className="meta">
            VPS helper 和 cron 的运行摘要；只记录状态、耗时和非敏感输出片段。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.runHistory.fetched ? "success" : "warning"}>
            {ops.runHistory.fetched ? "admin run log" : "locked run log"}
          </Badge>
          <Badge tone={latestOpsRun ? providerOpsRunStatusTone(latestOpsRun.status) : "info"}>
            latest {latestOpsRun ? latestOpsRun.status : "none"}
          </Badge>
          <Badge>
            latest {latestOpsRun ? formatDateTime(latestOpsRun.createdAtUtc) : "none"}
          </Badge>
        </div>
        {access.unlocked ? (
          <ProviderOpsRunHistoryTable runs={ops.runHistory.items} />
        ) : (
          <p className="provider-locked-controls">
            Admin controls locked. Unlock Provider Ops to view helper run history.
          </p>
        )}
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider Ops Audit Trail</h2>
          <p className="meta">
            记录 Provider Ops unlock、lock 和管理动作入口；不记录 API key、token 或 secret 值。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.auditTrail.fetched ? "success" : "warning"}>
            {ops.auditTrail.fetched ? "admin audit log" : "locked audit log"}
          </Badge>
          <Badge tone={latestAuditEvent?.outcome === "blocked" ? "warning" : "info"}>
            latest {latestAuditEvent ? formatDateTime(latestAuditEvent.createdAtUtc) : "none"}
          </Badge>
        </div>
        {access.unlocked ? (
          <ProviderOpsAuditTrailTable events={ops.auditTrail.items} />
        ) : (
          <p className="provider-locked-controls">
            Admin controls locked. Unlock Provider Ops to view the audited operation log.
          </p>
        )}
      </section>

      <ProviderOpsRunbook ops={ops} />

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider 授权状态</h2>
          <p className="meta">不显示 API key 值，仅显示环境变量引用与能力范围。</p>
        </div>
        <ProviderAuthorizationTable providers={ops.providers} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider Terms Review</h2>
          <p className="meta">
            Admin 审计链；记录条款复核、数据保留、历史数据和再分发许可，不显示任何 secret 值。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.authorizationReviews.fetched ? "success" : "warning"}>
            {ops.authorizationReviews.fetched ? "admin review log" : "fallback review log"}
          </Badge>
          <Badge tone={reviewDueCount > 0 ? "warning" : "success"}>due {reviewDueCount}</Badge>
          <Badge>
            latest{" "}
            {latestAuthorizationReview
              ? formatDateTime(latestAuthorizationReview.reviewedAtUtc)
              : "none"}
          </Badge>
        </div>
        {access.unlocked ? (
          <ProviderAuthorizationReviewActions
            providers={ops.providers}
            reviews={ops.authorizationReviews.items}
          />
        ) : (
          <ProviderOpsLockedControls />
        )}
        <ProviderAuthorizationReviewTable reviews={ops.authorizationReviews.items} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Runtime key readiness</h2>
          <p className="meta">
            受 admin token 保护；只显示 key 是否配置和 dry-run 路径，不显示任何 secret 值。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.runtimeCredentials.fetched ? "success" : "warning"}>
            {ops.runtimeCredentials.fetched ? "admin runtime view" : "fallback runtime view"}
          </Badge>
          <Badge tone={ops.runtimeCredentials.mockDryRunEnabled ? "info" : "warning"}>
            mock dry-run {ops.runtimeCredentials.mockDryRunEnabled ? "enabled" : "disabled"}
          </Badge>
          <Badge>checked {formatDateTime(ops.runtimeCredentials.generatedAtUtc)}</Badge>
        </div>
        <ProviderRuntimeCredentialTable credentials={ops.runtimeCredentials.items} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider Runtime Monitor</h2>
          <p className="meta">
            只读运行快照：provider probe 状态、延迟、错误率和限流信号；不显示任何 secret 值。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.runtimeMonitoring.fetched ? "success" : "warning"}>
            {ops.runtimeMonitoring.fetched ? "admin monitor" : "fallback monitor"}
          </Badge>
          <Badge tone={runtimeDegraded > 0 ? "warning" : "success"}>
            degraded {runtimeDegraded}
          </Badge>
          <Badge tone={ops.runtimeMonitoring.summary.rateLimitedCount > 0 ? "warning" : "info"}>
            rate limited {ops.runtimeMonitoring.summary.rateLimitedCount}
          </Badge>
          <Badge tone={runtimeAlertLevelTone(ops.runtimeMonitoring.alertLevel)}>
            alert {ops.runtimeMonitoring.alertLevel}
          </Badge>
          <Badge>
            avg latency{" "}
            {ops.runtimeMonitoring.summary.averageLatencyMs === null
              ? "N/A"
              : `${ops.runtimeMonitoring.summary.averageLatencyMs}ms`}
          </Badge>
          <Badge>checked {formatDateTime(ops.runtimeMonitoring.generatedAtUtc)}</Badge>
        </div>
        <ProviderRuntimeAlertList alerts={ops.runtimeMonitoring.alerts} />
        <ProviderRuntimeMonitoringTable snapshots={ops.runtimeMonitoring.items} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider Runtime Incidents</h2>
          <p className="meta">
            Admin 只读 incident reports；保存 runtime alert 摘要、阈值和来源，不保存 provider secret。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.runtimeIncidents.fetched ? "success" : "warning"}>
            {ops.runtimeIncidents.fetched ? "admin incidents" : "fallback incidents"}
          </Badge>
          <Badge tone={latestRuntimeIncident ? runtimeAlertLevelTone(latestRuntimeIncident.alertLevel) : "info"}>
            latest {latestRuntimeIncident ? latestRuntimeIncident.alertLevel : "none"}
          </Badge>
          <Badge tone={activeRuntimeIncidents > 0 ? "warning" : "success"}>
            active {activeRuntimeIncidents}
          </Badge>
          <Badge tone={runtimeIncidentSummary.p1Count > 0 ? "risk" : "info"}>
            P1 {runtimeIncidentSummary.p1Count}
          </Badge>
          <Badge tone={runtimeIncidentSummary.p2Count > 0 ? "warning" : "info"}>
            P2 {runtimeIncidentSummary.p2Count}
          </Badge>
          <Badge>MTTR {formatRuntimeMinutes(runtimeIncidentSummary.meanTimeToResolveMinutes)}</Badge>
          <Badge>reports {runtimeIncidentSummary.totalCount}</Badge>
          <Badge>lookback {runtimeIncidentSummary.lookbackDays}d</Badge>
        </div>
        <ProviderRuntimeIncidentTrendPanel summary={runtimeIncidentSummary} />
        <ProviderRuntimeIncidentRunbook
          incidents={ops.runtimeIncidents.items}
          summary={runtimeIncidentSummary}
        />
        <ProviderRuntimeIncidentFilterPanel incidents={ops.runtimeIncidents} />
        {access.unlocked ? (
          <ProviderRuntimeIncidentActions incidents={ops.runtimeIncidents.items} />
        ) : (
          <ProviderOpsLockedControls />
        )}
        <ProviderRuntimeIncidentTable incidents={ops.runtimeIncidents.items} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Free API application checklist</h2>
          <p className="meta">
            先申请免费或试用 key；足球赔率 free tier 可能不足，页面会标出限制。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.apiKeyChecklist.fetched ? "success" : "warning"}>
            {ops.apiKeyChecklist.fetched ? "admin checklist" : "fallback checklist"}
          </Badge>
          <Badge>checked {formatDateTime(ops.apiKeyChecklist.generatedAtUtc)}</Badge>
        </div>
        <ProviderApiKeyChecklistTable items={ops.apiKeyChecklist.items} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">赛事准入状态</h2>
          <p className="meta">准入结果来自数据质量、覆盖率、样本量和规则测试证据。</p>
        </div>
        <ProviderReadinessTable readiness={ops.readiness} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider 映射摘要</h2>
          <p className="meta">用于核对 provider ID 与 Nutmeg canonical ID 的关联覆盖。</p>
        </div>
        <ProviderMappingSummaryTable summary={ops.mappingSummary} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider 映射审核</h2>
          <p className="meta">
            低置信度、同 provider canonical 碰撞与陈旧映射进入人工复核队列；页面只展示审核证据。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone="info">dry run {ops.mappingReview.dryRun ? "yes" : "no"}</Badge>
          <Badge>检查 {ops.mappingReview.checkedMappingCount}</Badge>
          <Badge tone={ops.mappingReview.criticalCount > 0 ? "risk" : "neutral"}>
            critical {ops.mappingReview.criticalCount}
          </Badge>
          <Badge tone={ops.mappingReview.warningCount > 0 ? "warning" : "neutral"}>
            warning {ops.mappingReview.warningCount}
          </Badge>
          <Badge>as of {formatDateTime(ops.mappingReview.asOfTimeUtc)}</Badge>
        </div>
        <ProviderMappingReviewTable review={ops.mappingReview} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider Sync Workflow</h2>
          <p className="meta">只运行 dry-run，所有 provider IDs 由 operator 显式填写。</p>
        </div>
        {access.unlocked ? (
          <ProviderSyncWorkflowActions
            fetched={ops.providerSyncWorkflow.fetched}
            runs={ops.providerSyncWorkflow.runs}
            templatesFetched={ops.providerSyncWorkflow.templatesFetched}
            templates={ops.providerSyncWorkflow.templates}
            approvalsFetched={ops.providerSyncWorkflow.approvalsFetched}
            approvals={ops.providerSyncWorkflow.approvals}
          />
        ) : (
          <ProviderOpsLockedControls />
        )}
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Mapped Odds Sync</h2>
          <p className="meta">
            基于已审核的 fixture mappings 批量检查 The Odds API 赔率，不写入 odds snapshots。
          </p>
        </div>
        {access.unlocked ? <ProviderMappedOddsActions /> : <ProviderOpsLockedControls />}
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Prediction Quality Gate</h2>
          <p className="meta">
            使用已存储赔率快照做 canonical prediction dry-run，暴露 odds gate skips 与 warning。
          </p>
        </div>
        {access.unlocked ? (
          <ProviderPredictionGateActions
            fetched={ops.predictionQualityGate.fetched}
            runs={ops.predictionQualityGate.runs}
          />
        ) : (
          <ProviderOpsLockedControls />
        )}
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Odds Coverage Gaps</h2>
          <p className="meta">
            只读报告：把 fixture 覆盖、The Odds API 映射和快照新鲜度合并，定位 no odds 与 stale odds 缺口。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.oddsGapReport.fetched ? "success" : "warning"}>
            {ops.oddsGapReport.fetched ? "live gap report" : "fallback gap report"}
          </Badge>
          <Badge tone={ops.oddsGapReport.gapCount > 0 ? "warning" : "success"}>
            gap fixtures {ops.oddsGapReport.gapCount}
          </Badge>
          <Badge tone={ops.oddsGapReport.noOddsCount > 0 ? "warning" : "success"}>
            no odds {ops.oddsGapReport.noOddsCount}
          </Badge>
          <Badge tone={ops.oddsGapReport.staleOddsCount > 0 ? "warning" : "success"}>
            stale {ops.oddsGapReport.staleOddsCount}
          </Badge>
          <Badge tone={ops.oddsGapReport.providerEventUnavailableCount > 0 ? "warning" : "success"}>
            event unavailable {ops.oddsGapReport.providerEventUnavailableCount}
          </Badge>
          <Badge tone={ops.oddsGapReport.unmappedFixtureCount > 0 ? "warning" : "info"}>
            unmapped {ops.oddsGapReport.unmappedFixtureCount}
          </Badge>
          <Badge>max lag {ops.oddsGapReport.maxSnapshotLagHours}h</Badge>
        </div>
        <ProviderOddsGapTable report={ops.oddsGapReport} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Fallback Odds Probe</h2>
          <p className="meta">
            只读探测：检查 SportMonks 是否具备修复 provider event unavailable 缺口的映射与赔率覆盖。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={ops.fallbackOddsProbe.fetched ? "success" : "warning"}>
            {ops.fallbackOddsProbe.fetched ? "admin probe" : "fallback probe"}
          </Badge>
          <Badge tone={ops.fallbackOddsProbe.providerKeyConfigured ? "success" : "warning"}>
            key {ops.fallbackOddsProbe.providerKeyConfigured ? "ready" : "missing"}
          </Badge>
          <Badge tone={ops.fallbackOddsProbe.mappedFallbackCount > 0 ? "info" : "warning"}>
            mapped {ops.fallbackOddsProbe.mappedFallbackCount}
          </Badge>
          <Badge tone={ops.fallbackOddsProbe.recoverableFixtureCount > 0 ? "success" : "warning"}>
            recoverable {ops.fallbackOddsProbe.recoverableFixtureCount}
          </Badge>
          <Badge>checked {ops.fallbackOddsProbe.checkedGapCount}</Badge>
        </div>
        <ProviderFallbackOddsProbeTable probe={ops.fallbackOddsProbe} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">Provider 冲突治理</h2>
          <p className="meta">
            trusted provider priority 用于解释冲突归因，并给出 provider consistency 对数据质量的影响。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone="info">dry run {ops.conflictGovernance.dryRun ? "yes" : "no"}</Badge>
          <Badge>检查 issue {ops.conflictGovernance.checkedIssueCount}</Badge>
          <Badge tone={ops.conflictGovernance.conflictCount > 0 ? "warning" : "success"}>
            conflict {ops.conflictGovernance.conflictCount}
          </Badge>
          <Badge tone={ops.conflictGovernance.dataQualityScoreDelta < 0 ? "warning" : "neutral"}>
            quality {ops.conflictGovernance.dataQualityScoreDelta.toFixed(1)}
          </Badge>
          <Badge>
            consistency {formatPercent(ops.conflictGovernance.providerConsistencyAfterConflicts, 0)}
          </Badge>
          <Badge tone={ops.conflictGovernance.persistedOpenCount > 0 ? "warning" : "success"}>
            persisted open {ops.conflictGovernance.persistedOpenCount}
          </Badge>
          <Badge>resolved {ops.conflictGovernance.persistedResolvedCount}</Badge>
        </div>
        {access.unlocked ? (
          <ProviderConflictActions persistedEvents={ops.conflictGovernance.persistedEvents} />
        ) : (
          <ProviderOpsLockedControls />
        )}
        <ProviderConflictGovernanceTable governance={ops.conflictGovernance} />
      </section>

      <section className="section provider-table-section">
        <div className="section-header">
          <h2 className="section-title">最近映射关系</h2>
          <p className="meta">映射写入来自受控 provider sync 流程。</p>
        </div>
        <ProviderMappingTable mappings={ops.mappings} />
      </section>
    </main>
  );
}

function MetricCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: ReactNode;
}) {
  return (
    <div className="metric">
      <span className="metric-label">
        {icon}
        {label}
      </span>
      <div className="metric-value mono">{value}</div>
    </div>
  );
}

function ProviderOpsAuditTrailTable({ events }: { events: ProviderOpsAuditEvent[] }) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Provider Ops 操作审计事件，不包含 secret 值。</caption>
        <thead>
          <tr>
            <th>时间</th>
            <th>事件</th>
            <th>Operator</th>
            <th>结果</th>
            <th>请求</th>
            <th>Target</th>
            <th>证据</th>
          </tr>
        </thead>
        <tbody>
          {events.length ? (
            events.map((event) => (
              <tr key={event.providerOpsAuditEventId}>
                <td>{formatDateTime(event.createdAtUtc)}</td>
                <td>
                  <div className="provider-status-name">
                    <strong>{providerOpsAuditEventLabel(event.eventType)}</strong>
                    <span className="meta">{event.actionSurface}</span>
                  </div>
                </td>
                <td className="provider-id-cell">{event.operatorName ?? "unknown"}</td>
                <td>
                  <Badge tone={providerOpsAuditOutcomeTone(event.outcome)}>
                    {event.outcome}
                  </Badge>
                </td>
                <td className="provider-id-cell">
                  {event.requestMethod ?? "N/A"} {event.requestPath ?? ""}
                </td>
                <td className="provider-id-cell">
                  {event.targetType ? `${event.targetType}:${event.targetId ?? "N/A"}` : "N/A"}
                </td>
                <td className="provider-note">{auditMetadataSummary(event.metadataJson)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={7}>暂无 Provider Ops 审计事件。</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ProviderOpsRunHistoryTable({ runs }: { runs: ProviderOpsRunHistoryRecord[] }) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Provider helper and cron run history without secret values.</caption>
        <thead>
          <tr>
            <th>Created</th>
            <th>Run</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Exit</th>
            <th>Operator</th>
            <th>Summary</th>
            <th>Output</th>
          </tr>
        </thead>
        <tbody>
          {runs.length ? (
            runs.map((run) => (
              <tr key={run.providerOpsRunId}>
                <td>{formatDateTime(run.createdAtUtc)}</td>
                <td>
                  <div className="provider-status-name">
                    <strong>{run.runName}</strong>
                    <span className="meta">
                      {run.runType} / {run.source}
                    </span>
                  </div>
                </td>
                <td>
                  <Badge tone={providerOpsRunStatusTone(run.status)}>
                    {run.status}
                  </Badge>
                </td>
                <td className="provider-id-cell">{formatDuration(run.durationMs)}</td>
                <td className="mono">{run.exitCode ?? "N/A"}</td>
                <td className="provider-id-cell">{run.operatorName ?? "unknown"}</td>
                <td className="provider-note">{providerOpsRunSummary(run.summaryJson)}</td>
                <td className="provider-note">{run.outputExcerpt ?? "N/A"}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={8}>暂无 Provider helper run history。</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ProviderAuthorizationTable({ providers }: { providers: ProviderAuthorization[] }) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Provider 授权、能力与数据保留状态。</caption>
        <thead>
          <tr>
            <th>Provider</th>
            <th>状态</th>
            <th>能力</th>
            <th>商业使用</th>
            <th>保留快照</th>
            <th>使用策略</th>
            <th>复核</th>
            <th>历史/再分发</th>
            <th>Key 引用</th>
            <th>Owner</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody>
          {providers.map((provider) => (
            <tr key={provider.providerName}>
              <td>
                <div className="provider-status-name">
                  <strong>{provider.providerName}</strong>
                  <span className="meta">
                    {provider.termsCheckedAtUtc
                      ? formatDateTime(provider.termsCheckedAtUtc)
                      : "未记录"}
                  </span>
                </div>
              </td>
              <td>
                <Badge tone={statusTone(provider.status)}>{statusLabel(provider.status)}</Badge>
              </td>
              <td>
                <div className="provider-chip-list">
                  {provider.capabilities.map((capability) => (
                    <Badge key={capability}>{capability}</Badge>
                  ))}
                </div>
              </td>
              <td>{booleanBadge(provider.commercialUseAllowed)}</td>
              <td>{booleanBadge(provider.retentionAllowed)}</td>
              <td>
                <div className="provider-status-name">
                  <span>{provider.allowedUse}</span>
                  <span className="meta">{provider.rateLimit ?? "rate not recorded"}</span>
                </div>
              </td>
              <td>
                <div className="provider-status-name">
                  <span>{provider.lastReviewedAtUtc ? formatDateTime(provider.lastReviewedAtUtc) : "未记录"}</span>
                  <span className="meta">
                    due {provider.nextReviewDueAtUtc ? formatDateTime(provider.nextReviewDueAtUtc) : "未记录"}
                  </span>
                </div>
              </td>
              <td>
                <div className="provider-chip-list">
                  <Badge tone={provider.historicalDataAllowed ? "success" : "warning"}>
                    history {provider.historicalDataAllowed ? "yes" : "no"}
                  </Badge>
                  <Badge tone={provider.redistributionAllowed ? "success" : "warning"}>
                    redistribute {provider.redistributionAllowed ? "yes" : "no"}
                  </Badge>
                </div>
              </td>
              <td className="provider-id-cell">{provider.apiKeyEnvVar ?? "N/A"}</td>
              <td className="provider-id-cell">{provider.owner}</td>
              <td className="provider-note">{provider.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProviderAuthorizationReviewTable({
  reviews,
}: {
  reviews: ProviderAuthorizationReview[];
}) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Provider 条款复核、授权决策和证据载荷。</caption>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Review</th>
            <th>Reviewed</th>
            <th>使用策略</th>
            <th>数据权限</th>
            <th>下次复核</th>
            <th>证据</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody>
          {reviews.map((review) => (
            <tr key={review.providerAuthorizationReviewId}>
              <td>
                <div className="provider-status-name">
                  <strong>{review.providerName}</strong>
                  <span className="meta">{review.reviewReference}</span>
                </div>
              </td>
              <td>
                <Badge tone={reviewStatusTone(review.reviewStatus)}>
                  {reviewStatusLabel(review.reviewStatus)}
                </Badge>
              </td>
              <td>
                <div className="provider-status-name">
                  <span>{formatDateTime(review.reviewedAtUtc)}</span>
                  <span className="meta">{review.reviewedBy}</span>
                </div>
              </td>
              <td>
                <div className="provider-status-name">
                  <span>{review.allowedUse}</span>
                  <span className="meta">{review.rateLimit ?? "rate not recorded"}</span>
                </div>
              </td>
              <td>
                <div className="provider-chip-list">
                  <Badge tone={review.commercialUseAllowed ? "success" : "warning"}>
                    commercial {review.commercialUseAllowed ? "yes" : "no"}
                  </Badge>
                  <Badge tone={review.retentionAllowed ? "success" : "warning"}>
                    retain {review.retentionAllowed ? "yes" : "no"}
                  </Badge>
                  <Badge tone={review.historicalDataAllowed ? "success" : "warning"}>
                    history {review.historicalDataAllowed ? "yes" : "no"}
                  </Badge>
                  <Badge tone={review.redistributionAllowed ? "success" : "warning"}>
                    redistribute {review.redistributionAllowed ? "yes" : "no"}
                  </Badge>
                </div>
              </td>
              <td>
                {review.nextReviewDueAtUtc ? formatDateTime(review.nextReviewDueAtUtc) : "未记录"}
              </td>
              <td className="provider-id-cell">
                {Object.keys(review.evidenceJson).join(", ") || "none"}
              </td>
              <td className="provider-note">{review.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProviderRuntimeCredentialTable({
  credentials,
}: {
  credentials: ProviderRuntimeCredential[];
}) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Runtime key readiness for explicit provider sync operations.</caption>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Key</th>
            <th>Dry-run</th>
            <th>Commit</th>
            <th>真实请求</th>
            <th>Runtime env</th>
            <th>下一步</th>
          </tr>
        </thead>
        <tbody>
          {credentials.map((credential) => (
            <tr key={credential.providerName}>
              <td>
                <div className="provider-status-name">
                  <strong>{credential.providerName}</strong>
                  <span className="provider-id-cell">
                    {credential.capabilities.slice(0, 4).join(", ")}
                  </span>
                </div>
              </td>
              <td>{booleanBadge(credential.keyConfigured)}</td>
              <td>
                <Badge tone={dryRunModeTone(credential.dryRunMode)}>
                  {dryRunModeLabel(credential.dryRunMode)}
                </Badge>
              </td>
              <td>
                <Badge tone={commitModeTone(credential.commitMode)}>
                  {commitModeLabel(credential.commitMode)}
                </Badge>
              </td>
              <td>{booleanBadge(credential.safeToCallRealProvider)}</td>
              <td className="provider-id-cell">{credential.runtimeEnvVar ?? "N/A"}</td>
              <td>
                <div className="provider-status-name">
                  <span>{nextActionLabel(credential.nextAction)}</span>
                  <span className="meta">{credential.notes.slice(0, 2).join(" · ")}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProviderRuntimeMonitoringTable({
  snapshots,
}: {
  snapshots: ProviderRuntimeMonitoringSnapshot[];
}) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Provider runtime monitoring snapshots for read-only operations.</caption>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Status</th>
            <th>Latency</th>
            <th>Error rate</th>
            <th>Quota</th>
            <th>Fallback</th>
            <th>Observed</th>
            <th>Next action</th>
          </tr>
        </thead>
        <tbody>
          {snapshots.map((snapshot) => (
            <tr key={`${snapshot.providerName}-${snapshot.capability}`}>
              <td>
                <div className="provider-status-name">
                  <strong>{snapshot.providerName}</strong>
                  <span className="provider-id-cell">{snapshot.capability}</span>
                </div>
              </td>
              <td>
                <div className="provider-status-name">
                  <Badge tone={runtimeProbeStatusTone(snapshot.probeStatus)}>
                    {runtimeProbeStatusLabel(snapshot.probeStatus)}
                  </Badge>
                  <span className="meta">{snapshot.message}</span>
                </div>
              </td>
              <td className="mono">
                {snapshot.latencyMs === null ? "N/A" : `${snapshot.latencyMs}ms`}
              </td>
              <td>
                {snapshot.errorRate === null ? (
                  <Badge tone="info">N/A</Badge>
                ) : (
                  <Badge tone={snapshot.errorRate > 0 ? "warning" : "success"}>
                    {formatPercent(snapshot.errorRate)}
                  </Badge>
                )}
              </td>
              <td className="provider-id-cell">
                {snapshot.rateLimitRemaining === null
                  ? snapshot.quotaWindow ?? "provider defined"
                  : `${snapshot.rateLimitRemaining} remaining`}
              </td>
              <td>{booleanBadge(snapshot.fallbackUsed)}</td>
              <td>{formatDateTime(snapshot.observedAtUtc)}</td>
              <td>{runtimeMonitorNextActionLabel(snapshot.nextAction)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProviderRuntimeAlertList({ alerts }: { alerts: ProviderRuntimeMonitoringAlert[] }) {
  if (alerts.length === 0) {
    return (
      <div className="provider-review-strip">
        <Badge tone="success">runtime alerts clear</Badge>
      </div>
    );
  }
  return (
    <div className="provider-review-strip">
      {alerts.slice(0, 4).map((alert) => (
        <Badge key={alert.alertId} tone={runtimeAlertSeverityTone(alert.severity)}>
          {alert.severity} {runtimeAlertMetricLabel(alert.metric)}
          {alert.providerName ? ` / ${alert.providerName}` : ""}
        </Badge>
      ))}
      {alerts.length > 4 ? <Badge tone="warning">+{alerts.length - 4} more</Badge> : null}
    </div>
  );
}

function ProviderRuntimeIncidentTrendPanel({
  summary,
}: {
  summary: ProviderOps["runtimeIncidents"]["summary"];
}) {
  const maxCount = Math.max(1, ...summary.trendBuckets.map((bucket) => bucket.totalCount));

  return (
    <div className="provider-incident-trend-panel" aria-label="Runtime incident trend">
      <div className="provider-review-strip">
        <Badge tone={summary.activeCount > 0 ? "warning" : "success"}>
          active window {summary.activeCount}
        </Badge>
        <Badge>open {summary.openCount}</Badge>
        <Badge>ack {summary.acknowledgedCount}</Badge>
        <Badge>resolved {summary.resolvedCount}</Badge>
        <Badge>ignored {summary.ignoredCount}</Badge>
        <Badge tone={summary.notificationFailedCount > 0 ? "risk" : "info"}>
          notify failed {summary.notificationFailedCount}
        </Badge>
      </div>
      {summary.trendBuckets.length === 0 ? (
        <p className="meta">
          No runtime incident trend buckets in the last {summary.lookbackDays} days.
        </p>
      ) : (
        <div className="runtime-incident-trend-grid">
          {summary.trendBuckets.map((bucket) => {
            const barHeight = Math.max(8, Math.round((bucket.totalCount / maxCount) * 100));
            return (
              <div className="runtime-incident-trend-bucket" key={bucket.bucketDate}>
                <div className="runtime-incident-trend-meter" aria-hidden="true">
                  <span style={{ height: `${barHeight}%` }} />
                </div>
                <span className="provider-id-cell">{bucket.bucketDate.slice(5)}</span>
                <span className="mono">{bucket.totalCount}</span>
                <span className="meta">active {bucket.activeCount}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ProviderRuntimeIncidentRunbook({
  incidents,
  summary,
}: {
  incidents: ProviderRuntimeIncidentReport[];
  summary: ProviderOps["runtimeIncidents"]["summary"];
}) {
  const actions = runtimeIncidentRunbookActions(incidents, summary);

  return (
    <div className="provider-incident-runbook" aria-label="Runtime incident runbook">
      <div className="provider-action-summary">
        <ClipboardCheck size={16} aria-hidden="true" />
        <span className="provider-action-title">Runtime Incident Runbook</span>
        <Badge tone={summary.activeCount > 0 ? "warning" : "success"}>
          {summary.activeCount > 0 ? "review" : "clear"}
        </Badge>
      </div>
      <ol>
        {actions.map((action) => (
          <li key={action}>{action}</li>
        ))}
      </ol>
    </div>
  );
}

function ProviderRuntimeIncidentFilterPanel({
  incidents,
}: {
  incidents: ProviderOps["runtimeIncidents"];
}) {
  const filters = incidents.filters;
  const previousOffset = Math.max(0, filters.offset - filters.limit);
  const nextOffset = filters.offset + filters.limit;

  return (
    <div className="provider-incident-filter-panel" aria-label="Runtime incident filters">
      <div className="provider-action-summary">
        <ShieldQuestion size={16} aria-hidden="true" />
        <span className="provider-action-title">Incident filters</span>
        <Badge>
          showing {incidents.items.length}/{incidents.totalCount}
        </Badge>
        <Badge>offset {incidents.offset}</Badge>
      </div>
      <div className="provider-review-strip">
        {(["all", "open", "acknowledged", "resolved", "ignored"] as const).map((status) => (
          <a
            className="provider-filter-link"
            data-active={filters.incidentStatus === status}
            href={runtimeIncidentFilterHref(filters, {
              incidentStatus: status,
              offset: 0,
            })}
            key={status}
          >
            {status}
          </a>
        ))}
      </div>
      <div className="provider-review-strip">
        {(["all", "P1", "P2", "P0", "ok"] as const).map((level) => (
          <a
            className="provider-filter-link"
            data-active={filters.alertLevel === level}
            href={runtimeIncidentFilterHref(filters, { alertLevel: level, offset: 0 })}
            key={level}
          >
            alert {level}
          </a>
        ))}
        {(["all", "failed", "sent", "skipped", "queued", "not_configured"] as const).map(
          (status) => (
            <a
              className="provider-filter-link"
              data-active={filters.notificationStatus === status}
              href={runtimeIncidentFilterHref(filters, {
                notificationStatus: status,
                offset: 0,
              })}
              key={status}
            >
              notify {status}
            </a>
          ),
        )}
      </div>
      <div className="provider-review-strip">
        <a
          className="provider-filter-link"
          data-active={false}
          href={runtimeIncidentFilterHref(filters, { offset: previousOffset })}
        >
          Previous incidents
        </a>
        <a
          className="provider-filter-link"
          data-active={incidents.hasMore}
          href={runtimeIncidentFilterHref(filters, { offset: nextOffset })}
        >
          Next incidents
        </a>
        <a className="provider-filter-link" data-active={false} href="/providers">
          Reset incident filters
        </a>
      </div>
    </div>
  );
}

function ProviderRuntimeIncidentTable({
  incidents,
}: {
  incidents: ProviderRuntimeIncidentReport[];
}) {
  if (incidents.length === 0) {
    return <p className="meta">No runtime incident reports recorded.</p>;
  }
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Provider runtime incident reports generated from monitoring snapshots.</caption>
        <thead>
          <tr>
            <th>Created</th>
            <th>Level</th>
            <th>Status</th>
            <th>Alerts</th>
            <th>Snapshots</th>
            <th>Ack</th>
            <th>Resolved</th>
            <th>Detail</th>
            <th>Source</th>
            <th>Created by</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr key={incident.providerRuntimeIncidentReportId}>
              <td>{formatDateTime(incident.createdAtUtc)}</td>
              <td>
                <Badge tone={runtimeAlertLevelTone(incident.alertLevel)}>
                  {incident.alertLevel}
                </Badge>
              </td>
              <td>
                <Badge tone={runtimeIncidentStatusTone(incident.incidentStatus)}>
                  {incident.incidentStatus}
                </Badge>
              </td>
              <td className="mono">{incident.alertCount}</td>
              <td className="mono">{incident.snapshotCount}</td>
              <td className="provider-id-cell">
                {incident.acknowledgedBy && incident.acknowledgedAtUtc
                  ? `${incident.acknowledgedBy} / ${formatDateTime(incident.acknowledgedAtUtc)}`
                  : "N/A"}
              </td>
              <td className="provider-id-cell">
                {incident.resolvedBy && incident.resolvedAtUtc
                  ? `${incident.resolvedBy} / ${formatDateTime(incident.resolvedAtUtc)}`
                  : "N/A"}
              </td>
              <td className="provider-note">
                <details className="provider-incident-detail">
                  <summary>Alert payload</summary>
                  <dl>
                    <div>
                      <dt>Alerts</dt>
                      <dd>{incidentAlertSummary(incident)}</dd>
                    </div>
                    <div>
                      <dt>Thresholds</dt>
                      <dd>{incidentThresholdSummary(incident)}</dd>
                    </div>
                    <div>
                      <dt>Notification</dt>
                      <dd>{incidentNotificationSummary(incident)}</dd>
                    </div>
                    <div>
                      <dt>Resolution</dt>
                      <dd>{incident.resolutionNote ?? "N/A"}</dd>
                    </div>
                  </dl>
                </details>
              </td>
              <td className="provider-id-cell">{incident.source}</td>
              <td className="provider-id-cell">{incident.createdBy}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProviderApiKeyChecklistTable({ items }: { items: ProviderApiKeyChecklistItem[] }) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Free or trial data-source API application checklist.</caption>
        <thead>
          <tr>
            <th>优先级</th>
            <th>Provider</th>
            <th>Adapter</th>
            <th>Free fit</th>
            <th>Key</th>
            <th>Env</th>
            <th>申请</th>
            <th>下一步</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.providerName}>
              <td className="mono">{item.priority}</td>
              <td>
                <div className="provider-status-name">
                  <strong>{item.providerName}</strong>
                  <span className="meta">{roleLabel(item.nutmegRole)}</span>
                </div>
              </td>
              <td>
                <Badge tone={item.adapterStatus === "supported_now" ? "success" : "warning"}>
                  {adapterStatusLabel(item.adapterStatus)}
                </Badge>
              </td>
              <td>
                <Badge tone={freeTierFitTone(item.freeTierFit)}>
                  {freeTierFitLabel(item.freeTierFit)}
                </Badge>
              </td>
              <td>{booleanBadge(item.keyConfigured)}</td>
              <td className="provider-id-cell">{item.requiredEnvVar}</td>
              <td>
                <div className="provider-chip-list">
                  <a href={item.applyUrl} rel="noreferrer" target="_blank">
                    Apply
                  </a>
                  <a href={item.docsUrl} rel="noreferrer" target="_blank">
                    Docs
                  </a>
                </div>
              </td>
              <td>
                <div className="provider-status-name">
                  <span>{operatorActionLabel(item.operatorAction)}</span>
                  <span className="meta">{item.officialFreeTierNote}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProviderReadinessTable({ readiness }: { readiness: ProviderReadiness[] }) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>赛事准入状态与关键覆盖率。</caption>
        <thead>
          <tr>
            <th>赛事</th>
            <th>阶段</th>
            <th>结果</th>
            <th>质量</th>
            <th>赛程</th>
            <th>赔率</th>
            <th>阵容/伤停</th>
            <th>新鲜度</th>
            <th>阻塞项</th>
          </tr>
        </thead>
        <tbody>
          {readiness.map((item) => (
            <tr key={`${item.competitionId}-${item.targetStage}`}>
              <td>
                <div className="provider-status-name">
                  <strong>{item.competitionName}</strong>
                  <span className="provider-id-cell">{item.competitionId}</span>
                </div>
              </td>
              <td>
                <Badge tone={item.targetStage === "production" ? "brand" : "beta"}>
                  {item.targetStage}
                </Badge>
              </td>
              <td>
                <Badge tone={decisionTone(item.decision)}>{decisionLabel(item.decision)}</Badge>
              </td>
              <td>
                <span className="provider-score">{item.dataQuality.score.toFixed(1)}</span>
                <Badge tone={qualityTone(item.dataQuality.grade)}>Q{item.dataQuality.grade}</Badge>
              </td>
              <td>{formatPercent(item.dataQuality.components.fixtureReliability, 0)}</td>
              <td>{formatPercent(item.dataQuality.components.oddsCoverage, 0)}</td>
              <td>{formatPercent(item.dataQuality.components.lineupInjuryCoverage, 0)}</td>
              <td>{formatPercent(item.dataQuality.components.dataFreshness, 0)}</td>
              <td>
                {item.reasons.length > 0 ? (
                  <ul className="provider-reason-list">
                    {item.reasons.slice(0, 3).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                ) : (
                  <Badge tone="success">clear</Badge>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProviderMappingSummaryTable({ summary }: { summary: ProviderMappingSummary[] }) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>按 provider 和实体类型聚合的映射统计。</caption>
        <thead>
          <tr>
            <th>Provider</th>
            <th>实体类型</th>
            <th>数量</th>
            <th>平均置信度</th>
            <th>最低置信度</th>
            <th>最近更新</th>
          </tr>
        </thead>
        <tbody>
          {summary.length > 0 ? (
            summary.map((item) => (
              <tr key={`${item.provider}-${item.entityType}`}>
                <td>{item.provider}</td>
                <td>{item.entityType}</td>
                <td>{item.mappingCount}</td>
                <td>{formatPercent(item.averageConfidence, 0)}</td>
                <td>{formatPercent(item.minimumConfidence, 0)}</td>
                <td>{formatDateTime(item.latestUpdatedAtUtc)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="ui-table-empty" colSpan={6}>
                暂无 provider 映射摘要
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ProviderOddsGapTable({
  report,
}: {
  report: ProviderOps["oddsGapReport"];
}) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Fixture odds coverage gaps.</caption>
        <thead>
          <tr>
            <th>Fixture</th>
            <th>Kickoff</th>
            <th>Issues</th>
            <th>Mapping</th>
            <th>Odds</th>
            <th>Latest</th>
            <th>Next</th>
          </tr>
        </thead>
        <tbody>
          {report.items.length > 0 ? (
            report.items.slice(0, 20).map((item) => (
              <tr key={`${item.fixtureId}-${item.issueTypes.join("-")}`}>
                <td>
                  <div className="provider-review-action">
                    <span>{item.homeTeamName} vs {item.awayTeamName}</span>
                    <span className="provider-id-cell">{item.fixtureId}</span>
                  </div>
                </td>
                <td>{formatDateTime(item.kickoffTimeUtc)}</td>
                <td>
                  <div className="provider-chip-list">
                    {item.issueTypes.map((issue) => (
                      <Badge key={issue} tone={gapIssueTone(issue)}>
                        {gapIssueLabel(issue)}
                      </Badge>
                    ))}
                  </div>
                </td>
                <td>
                  <div className="provider-review-action">
                    <Badge tone={item.hasProviderMapping ? "success" : "warning"}>
                      {item.hasProviderMapping ? "mapped" : "unmapped"}
                    </Badge>
                    <span className="provider-id-cell">
                      {item.providerEventId ?? item.provider}
                    </span>
                    {item.providerMappingConfidence !== null ? (
                      <span className="meta">
                        {formatPercent(item.providerMappingConfidence, 0)}
                      </span>
                    ) : null}
                  </div>
                </td>
                <td>
                  <div className="provider-review-action">
                    <span className="mono">{item.oddsSnapshotCount}</span>
                    <span className="meta">
                      {item.bookmakerCount} books / {item.marketTypes.join(", ") || "none"}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="provider-review-action">
                    <Badge tone={item.freshEnough ? "success" : "warning"}>
                      {item.freshEnough ? "fresh" : "stale"}
                    </Badge>
                    <span className="meta">
                      {item.latestSnapshotLagHours === null
                        ? "N/A"
                        : `${item.latestSnapshotLagHours.toFixed(1)}h`}
                    </span>
                  </div>
                </td>
                <td className="provider-review-action">
                  <span>{gapActionLabel(item.recommendedAction)}</span>
                  {item.eventAvailabilityNote ? (
                    <span className="meta">{item.eventAvailabilityNote}</span>
                  ) : null}
                  {item.fallbackCandidates.length > 0 ? (
                    <span className="provider-id-cell">
                      fallback: {item.fallbackCandidates.map((candidate) => (
                        `${candidate.providerName} (${gapFallbackStatusLabel(candidate.adapterStatus)})`
                      )).join(", ")}
                    </span>
                  ) : null}
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="ui-table-empty" colSpan={7}>
                当前窗口没有赔率覆盖缺口
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ProviderFallbackOddsProbeTable({
  probe,
}: {
  probe: ProviderOps["fallbackOddsProbe"];
}) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>SportMonks fallback odds probe.</caption>
        <thead>
          <tr>
            <th>Fixture</th>
            <th>Status</th>
            <th>Mapping</th>
            <th>Probe</th>
            <th>Odds</th>
            <th>Next</th>
          </tr>
        </thead>
        <tbody>
          {probe.items.length > 0 ? (
            probe.items.slice(0, 20).map((item) => (
              <tr key={`${item.fixtureId}-${item.status}`}>
                <td>
                  <div className="provider-review-action">
                    <span>{item.homeTeamName} vs {item.awayTeamName}</span>
                    <span className="provider-id-cell">{item.fixtureId}</span>
                  </div>
                </td>
                <td>
                  <Badge tone={fallbackProbeStatusTone(item.status)}>
                    {fallbackProbeStatusLabel(item.status)}
                  </Badge>
                </td>
                <td>
                  <div className="provider-review-action">
                    <span className="provider-id-cell">
                      {item.providerFixtureId ?? "mapping required"}
                    </span>
                    {item.providerMappingConfidence !== null ? (
                      <span className="meta">
                        {formatPercent(item.providerMappingConfidence, 0)}
                      </span>
                    ) : null}
                  </div>
                </td>
                <td>
                  <div className="provider-review-action">
                    <Badge tone={item.liveProviderProbe ? "info" : "warning"}>
                      live {item.liveProviderProbe ? "yes" : "no"}
                    </Badge>
                    <span className="meta">
                      {item.providerKeyConfigured ? "key configured" : "key missing"}
                    </span>
                  </div>
                </td>
                <td>
                  <div className="provider-review-action">
                    <span className="mono">{item.normalizedOddsCount}</span>
                    <span className="meta">
                      {item.bookmakerCount} books / {item.marketTypes.join(", ") || "none"}
                    </span>
                  </div>
                </td>
                <td className="provider-review-action">
                  <span>{fallbackProbeActionLabel(item.recommendedAction)}</span>
                  {item.warnings.length > 0 ? (
                    <span className="provider-id-cell">
                      {item.warnings.slice(0, 3).join(", ")}
                    </span>
                  ) : null}
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="ui-table-empty" colSpan={6}>
                当前没有需要 fallback 探测的赔率覆盖缺口
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ProviderConflictGovernanceTable({
  governance,
}: {
  governance: ProviderConflictGovernance;
}) {
  return (
    <div className="provider-conflict-grid">
      <div className="ui-table-wrap provider-conflict-status-table">
        <table className="ui-table">
          <caption>Persisted provider conflict event status.</caption>
          <thead>
            <tr>
              <th>ID</th>
              <th>状态</th>
              <th>严重度</th>
              <th>类型</th>
              <th>Canonical ID</th>
              <th>Providers</th>
              <th>创建</th>
              <th>解决</th>
            </tr>
          </thead>
          <tbody>
            {governance.persistedEvents.length > 0 ? (
              governance.persistedEvents.slice(0, 10).map((event) => (
                <tr key={event.providerConflictEventId}>
                  <td className="mono">{event.providerConflictEventId}</td>
                  <td>
                    <Badge tone={conflictStatusTone(event.resolutionStatus)}>
                      {event.resolutionStatus}
                    </Badge>
                  </td>
                  <td>
                    <Badge tone={reviewSeverityTone(event.severity)}>
                      {event.severity}
                    </Badge>
                  </td>
                  <td>{conflictTypeLabel(event.conflictType)}</td>
                  <td className="provider-id-cell">{event.canonicalEntityId}</td>
                  <td className="provider-id-cell">{event.providerNames.join(", ")}</td>
                  <td>{formatDateTime(event.createdAtUtc)}</td>
                  <td>{event.resolvedAtUtc ? formatDateTime(event.resolvedAtUtc) : "N/A"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="ui-table-empty" colSpan={8}>
                  暂无持久化 provider conflict event
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="ui-table-wrap">
        <table className="ui-table">
          <caption>Dry-run provider conflict events derived from current review evidence.</caption>
          <thead>
            <tr>
              <th>严重度</th>
              <th>类型</th>
              <th>实体</th>
              <th>Canonical ID</th>
              <th>Providers</th>
              <th>Trusted</th>
              <th>质量影响</th>
              <th>证据</th>
              <th>动作</th>
            </tr>
          </thead>
          <tbody>
            {governance.events.length > 0 ? (
              governance.events.slice(0, 10).map((event) => (
                <tr key={`${event.conflictType}-${event.canonicalEntityId}-${event.sourceIssueId}`}>
                  <td>
                    <Badge tone={reviewSeverityTone(event.severity)}>
                      {event.severity}
                    </Badge>
                  </td>
                  <td>{conflictTypeLabel(event.conflictType)}</td>
                  <td>{event.entityType}</td>
                  <td className="provider-id-cell">{event.canonicalEntityId}</td>
                  <td className="provider-id-cell">{event.providerNames.join(", ")}</td>
                  <td>{event.trustedProvider ?? "N/A"}</td>
                  <td className="mono">{event.dataQualityScoreDelta.toFixed(1)}</td>
                  <td className="provider-review-action">{conflictEvidenceLabel(event)}</td>
                  <td className="provider-review-action">{event.recommendedAction}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="ui-table-empty" colSpan={9}>
                  当前未发现需要记录的 provider 冲突事件
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="ui-table-wrap">
        <table className="ui-table">
          <caption>Trusted provider priority policy used for conflict interpretation.</caption>
          <thead>
            <tr>
              <th>Capability</th>
              <th>Provider</th>
              <th>Rank</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {governance.trustedPriorities.slice(0, 8).map((priority) => (
              <tr key={`${priority.capability}-${priority.providerName}`}>
                <td>{priority.capability}</td>
                <td>{priority.providerName}</td>
                <td className="mono">{priority.priorityRank}</td>
                <td className="provider-note">{priority.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProviderMappingReviewTable({ review }: { review: ProviderMappingReview }) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Provider mapping review issues for manual reconciliation.</caption>
        <thead>
          <tr>
            <th>严重度</th>
            <th>类型</th>
            <th>Provider</th>
            <th>实体</th>
            <th>Canonical ID</th>
            <th>Provider IDs</th>
            <th>最低置信度</th>
            <th>建议动作</th>
          </tr>
        </thead>
        <tbody>
          {review.issues.length > 0 ? (
            review.issues.slice(0, 12).map((issue) => (
              <tr key={issue.issueId}>
                <td>
                  <Badge tone={reviewSeverityTone(issue.severity)}>
                    {issue.severity}
                  </Badge>
                </td>
                <td>{reviewIssueLabel(issue.issueType)}</td>
                <td>{issue.provider}</td>
                <td>{issue.entityType}</td>
                <td className="provider-id-cell">{issue.canonicalEntityId}</td>
                <td className="provider-id-cell">{issue.providerEntityIds.join(", ")}</td>
                <td>
                  {issue.confidenceMin === null ? "N/A" : formatPercent(issue.confidenceMin, 0)}
                </td>
                <td>
                  <div className="provider-review-action">
                    <span>{issue.recommendedAction}</span>
                    {issue.latestUpdatedAtUtc ? (
                      <span className="meta">{formatDateTime(issue.latestUpdatedAtUtc)}</span>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="ui-table-empty" colSpan={8}>
                当前审核未发现映射问题
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ProviderMappingTable({ mappings }: { mappings: ProviderEntityMapping[] }) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>最近 provider entity mapping 记录。</caption>
        <thead>
          <tr>
            <th>ID</th>
            <th>Provider</th>
            <th>类型</th>
            <th>Provider ID</th>
            <th>Canonical ID</th>
            <th>置信度</th>
            <th>更新</th>
          </tr>
        </thead>
        <tbody>
          {mappings.length > 0 ? (
            mappings.map((mapping) => (
              <tr key={mapping.mappingId}>
                <td className="mono">{mapping.mappingId}</td>
                <td>{mapping.provider}</td>
                <td>{mapping.entityType}</td>
                <td className="provider-id-cell">{mapping.providerEntityId}</td>
                <td className="provider-id-cell">{mapping.canonicalEntityId}</td>
                <td>{formatPercent(mapping.confidence, 0)}</td>
                <td>{formatDateTime(mapping.updatedAtUtc)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="ui-table-empty" colSpan={7}>
                暂无 provider 映射记录
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function booleanBadge(value: boolean) {
  return <Badge tone={value ? "success" : "warning"}>{value ? "yes" : "review"}</Badge>;
}

function providerOpsAuditEventLabel(eventType: string) {
  const labels: Record<string, string> = {
    provider_ops_unlock: "Unlock Provider Ops",
    provider_ops_lock: "Lock Provider Ops",
    provider_ops_admin_action: "Provider Ops Admin Action",
  };
  return labels[eventType] ?? eventType;
}

function providerOpsAuditOutcomeTone(outcome: ProviderOpsAuditEvent["outcome"]): BadgeTone {
  if (outcome === "success") return "success";
  if (outcome === "blocked") return "warning";
  return "risk";
}

function providerOpsRunStatusTone(status: ProviderOpsRunHistoryRecord["status"]): BadgeTone {
  if (status === "success") return "success";
  if (status === "skipped") return "warning";
  return "risk";
}

function providerOpsRunSummary(summary: Record<string, unknown>) {
  const entries = Object.entries(summary).filter(([key]) => {
    const lower = key.toLowerCase();
    return !lower.includes("secret") && !lower.includes("token") && !lower.includes("key");
  });
  if (entries.length === 0) {
    return "summary empty";
  }
  return entries
    .slice(0, 5)
    .map(([key, value]) => `${key}=${metadataValueLabel(value)}`)
    .join("; ");
}

function formatDuration(value: number | null) {
  if (value === null) {
    return "N/A";
  }
  if (value < 1000) {
    return `${value}ms`;
  }
  return `${(value / 1000).toFixed(1)}s`;
}

function auditMetadataSummary(metadata: Record<string, unknown>) {
  const keys = Object.keys(metadata).filter((key) => {
    const lower = key.toLowerCase();
    return !lower.includes("secret") && !lower.includes("token") && !lower.includes("key");
  });
  if (!keys.length) {
    return "metadata empty";
  }
  return keys
    .slice(0, 4)
    .map((key) => `${key}=${metadataValueLabel(metadata[key])}`)
    .join("; ");
}

function metadataValueLabel(value: unknown) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value).slice(0, 80);
  }
  if (Array.isArray(value)) return `list(${value.length})`;
  if (typeof value === "object") return "object";
  return String(value).slice(0, 80);
}

function incidentAlertSummary(incident: ProviderRuntimeIncidentReport) {
  if (incident.alertsJson.length === 0) {
    return "No alert payload";
  }
  const labels = incident.alertsJson.slice(0, 3).map((alert) => {
    const severity = metadataValueLabel(alert.severity);
    const metric = metadataValueLabel(alert.metric);
    const provider = metadataValueLabel(alert.provider_name ?? alert.providerName);
    return [severity, metric, provider === "null" ? null : provider]
      .filter(Boolean)
      .join(" / ");
  });
  return labels.join("; ");
}

function incidentThresholdSummary(incident: ProviderRuntimeIncidentReport) {
  const entries = Object.entries(incident.thresholdsJson).filter(([key]) => {
    const lower = key.toLowerCase();
    return !lower.includes("secret") && !lower.includes("token") && !lower.includes("api_key");
  });
  if (entries.length === 0) {
    return "Threshold payload empty";
  }
  return entries
    .slice(0, 4)
    .map(([key, value]) => `${key}=${metadataValueLabel(value)}`)
    .join("; ");
}

function incidentNotificationSummary(incident: ProviderRuntimeIncidentReport) {
  const payload = incident.notificationPayloadJson;
  const entries = [
    ["status", incident.notificationStatus],
    ["adapter", payload.adapter],
    ["reason", payload.reason],
    ["dry_run", payload.dry_run],
    ["external_delivery", payload.external_delivery],
  ].filter(([, value]) => value !== undefined && value !== null);
  if (entries.length === 0) {
    return incident.notificationStatus;
  }
  return entries
    .slice(0, 5)
    .map(([key, value]) => `${key}=${metadataValueLabel(value)}`)
    .join("; ");
}

function formatRuntimeMinutes(value: number | null) {
  if (value === null) {
    return "N/A";
  }
  if (value < 1) {
    return "<1m";
  }
  if (value < 60) {
    return `${Math.round(value)}m`;
  }
  return `${(value / 60).toFixed(1)}h`;
}

function runtimeIncidentRunbookActions(
  incidents: ProviderRuntimeIncidentReport[],
  summary: ProviderOps["runtimeIncidents"]["summary"],
) {
  if (summary.activeCount === 0) {
    return [
      "保持 30 分钟 runtime monitor cron；下一次 provider 降级时自动生成 incident 证据。",
      "复核最近一条 resolved/ignored incident 的处置备注与 notification payload，确认没有 provider secret 泄露。",
      "继续观察趋势窗口，若连续多个日期出现 P1/P2，再进入 provider coverage 排查。",
    ];
  }
  const actions = [
    "先 acknowledge open incident，记录 operator 和非敏感处置备注。",
    "查看 alert payload 中的 provider、metric、threshold，定位是 key、限流、延迟还是 fallback 使用率。",
    "检查 notification adapter 的 status、reason 和 dry-run 标记；默认不执行外部发送。",
  ];
  if (summary.p1Count > 0 || summary.p0Count > 0) {
    actions.push("暂停真实 provider 写入型操作，先检查 key 配置、plan limit 和 provider 恢复状态。");
  }
  if (summary.notificationFailedCount > 0) {
    actions.push("检查 notification 状态存根；外部通知仍未启用时只保留 Provider Ops 内部记录。");
  }
  if (incidents.some((incident) => incident.source === "vps_cron")) {
    actions.push("核对 VPS cron 最近一次运行日志，确认 incident 来源与 runtime snapshot 一致。");
  }
  actions.push("解决后标记为 resolved；无法复现或不需动作时标记 ignored 并说明原因。");
  return actions;
}

function runtimeIncidentFiltersFromSearchParams(
  params: Record<string, string | string[] | undefined> | undefined,
): ProviderRuntimeIncidentFilters {
  return {
    limit: boundedInteger(firstSearchParam(params, "incident_limit"), 20, 1, 100),
    offset: boundedInteger(firstSearchParam(params, "incident_offset"), 0, 0, 1_000_000),
    lookbackDays: boundedInteger(
      firstSearchParam(params, "incident_lookback_days"),
      30,
      1,
      3650,
    ),
    incidentStatus: runtimeIncidentStatusSearchParam(
      firstSearchParam(params, "incident_status"),
    ),
    alertLevel: runtimeIncidentAlertLevelSearchParam(
      firstSearchParam(params, "incident_alert_level"),
    ),
    notificationStatus: runtimeIncidentNotificationSearchParam(
      firstSearchParam(params, "incident_notification_status"),
    ),
    source: nullableSearchParam(firstSearchParam(params, "incident_source")),
  };
}

function runtimeIncidentFilterHref(
  filters: ProviderRuntimeIncidentFilters,
  overrides: Partial<ProviderRuntimeIncidentFilters>,
) {
  const next = { ...filters, ...overrides };
  const params = new URLSearchParams();
  if (next.limit !== 20) params.set("incident_limit", next.limit.toString());
  if (next.offset > 0) params.set("incident_offset", next.offset.toString());
  if (next.lookbackDays !== 30) {
    params.set("incident_lookback_days", next.lookbackDays.toString());
  }
  if (next.incidentStatus !== "all") {
    params.set("incident_status", next.incidentStatus);
  }
  if (next.alertLevel !== "all") {
    params.set("incident_alert_level", next.alertLevel);
  }
  if (next.notificationStatus !== "all") {
    params.set("incident_notification_status", next.notificationStatus);
  }
  if (next.source) {
    params.set("incident_source", next.source);
  }
  const query = params.toString();
  return query ? `/providers?${query}` : "/providers";
}

function firstSearchParam(
  params: Record<string, string | string[] | undefined> | undefined,
  key: string,
) {
  const value = params?.[key];
  return Array.isArray(value) ? value[0] : value;
}

function nullableSearchParam(value: string | undefined) {
  const text = value?.trim();
  return text ? text.slice(0, 120) : null;
}

function boundedInteger(
  value: string | undefined,
  fallback: number,
  min: number,
  max: number,
) {
  const parsed = Number.parseInt(value ?? "", 10);
  if (Number.isNaN(parsed)) {
    return fallback;
  }
  return Math.min(Math.max(parsed, min), max);
}

function runtimeIncidentStatusSearchParam(
  value: string | undefined,
): ProviderRuntimeIncidentFilters["incidentStatus"] {
  if (["open", "acknowledged", "resolved", "ignored"].includes(value ?? "")) {
    return value as ProviderRuntimeIncidentFilters["incidentStatus"];
  }
  return "all";
}

function runtimeIncidentAlertLevelSearchParam(
  value: string | undefined,
): ProviderRuntimeIncidentFilters["alertLevel"] {
  if (["ok", "P0", "P1", "P2"].includes(value ?? "")) {
    return value as ProviderRuntimeIncidentFilters["alertLevel"];
  }
  return "all";
}

function runtimeIncidentNotificationSearchParam(
  value: string | undefined,
): ProviderRuntimeIncidentFilters["notificationStatus"] {
  if (["not_configured", "queued", "sent", "skipped", "failed"].includes(value ?? "")) {
    return value as ProviderRuntimeIncidentFilters["notificationStatus"];
  }
  return "all";
}

function statusLabel(status: ProviderAuthorization["status"]) {
  const labels: Record<ProviderAuthorization["status"], string> = {
    active: "active",
    pending_review: "review",
    research_only: "research",
    blocked: "blocked",
    expired: "expired",
  };
  return labels[status];
}

function statusTone(status: ProviderAuthorization["status"]): BadgeTone {
  if (status === "active") return "success";
  if (status === "blocked" || status === "expired") return "risk";
  if (status === "research_only") return "info";
  return "warning";
}

function reviewStatusLabel(status: ProviderAuthorizationReview["reviewStatus"]) {
  const labels: Record<ProviderAuthorizationReview["reviewStatus"], string> = {
    approved: "approved",
    research_only: "research",
    needs_review: "review",
    blocked: "blocked",
  };
  return labels[status];
}

function reviewStatusTone(status: ProviderAuthorizationReview["reviewStatus"]): BadgeTone {
  if (status === "approved") return "success";
  if (status === "research_only") return "info";
  if (status === "blocked") return "risk";
  return "warning";
}

function isReviewDue(provider: ProviderAuthorization) {
  if (!provider.nextReviewDueAtUtc) {
    return true;
  }
  return Date.parse(provider.nextReviewDueAtUtc) <= Date.now();
}

function dryRunModeLabel(mode: ProviderRuntimeCredential["dryRunMode"]) {
  const labels: Record<ProviderRuntimeCredential["dryRunMode"], string> = {
    local_only: "local only",
    mock_sample: "mock sample",
    real_provider: "real provider",
    blocked: "blocked",
  };
  return labels[mode];
}

function dryRunModeTone(mode: ProviderRuntimeCredential["dryRunMode"]): BadgeTone {
  if (mode === "real_provider") return "success";
  if (mode === "mock_sample" || mode === "local_only") return "info";
  return "risk";
}

function commitModeLabel(mode: ProviderRuntimeCredential["commitMode"]) {
  const labels: Record<ProviderRuntimeCredential["commitMode"], string> = {
    not_applicable: "N/A",
    ready: "ready",
    blocked: "blocked",
  };
  return labels[mode];
}

function commitModeTone(mode: ProviderRuntimeCredential["commitMode"]): BadgeTone {
  if (mode === "ready") return "success";
  if (mode === "not_applicable") return "neutral";
  return "warning";
}

function nextActionLabel(action: string) {
  const labels: Record<string, string> = {
    available_for_deterministic_local_testing: "本地确定性测试可用",
    ready_for_real_provider_dry_run: "可执行真实 provider dry-run",
    apply_api_key_before_real_provider_sync: "真实同步前需配置 API key",
    apply_api_key_before_provider_dry_run: "provider dry-run 前需配置 API key",
  };
  return labels[action] ?? action;
}

function runtimeProbeStatusLabel(
  status: ProviderRuntimeMonitoringSnapshot["probeStatus"],
) {
  const labels: Record<ProviderRuntimeMonitoringSnapshot["probeStatus"], string> = {
    not_configured: "not configured",
    key_configured: "key configured",
    ok: "ok",
    limited: "limited",
    auth_failed: "auth failed",
    rate_limited: "rate limited",
    unavailable: "unavailable",
    adapter_planned: "adapter planned",
  };
  return labels[status];
}

function runtimeProbeStatusTone(
  status: ProviderRuntimeMonitoringSnapshot["probeStatus"],
): BadgeTone {
  if (status === "ok" || status === "key_configured") return "success";
  if (status === "limited" || status === "rate_limited") return "warning";
  if (status === "auth_failed" || status === "unavailable") return "risk";
  return "info";
}

function runtimeMonitorNextActionLabel(
  action: ProviderRuntimeMonitoringSnapshot["nextAction"],
) {
  const labels: Record<ProviderRuntimeMonitoringSnapshot["nextAction"], string> = {
    no_action: "无需动作",
    configure_runtime_key: "配置 runtime key",
    review_provider_plan_limit: "复核 provider plan / limit",
    check_provider_credentials: "检查 provider credential",
    retry_after_provider_recovery: "稍后重试 provider",
    adapter_not_ready: "adapter 待接入",
  };
  return labels[action];
}

function runtimeAlertLevelTone(level: ProviderOps["runtimeMonitoring"]["alertLevel"]): BadgeTone {
  if (level === "ok") return "success";
  if (level === "P2") return "warning";
  return "risk";
}

function runtimeIncidentStatusTone(
  status: ProviderRuntimeIncidentReport["incidentStatus"],
): BadgeTone {
  if (status === "resolved" || status === "ignored") return "success";
  if (status === "acknowledged") return "warning";
  return "risk";
}

function runtimeAlertSeverityTone(
  severity: ProviderRuntimeMonitoringAlert["severity"],
): BadgeTone {
  if (severity === "P2") return "warning";
  return "risk";
}

function runtimeAlertMetricLabel(metric: string) {
  const labels: Record<string, string> = {
    provider_error_rate: "provider error",
    provider_latency: "provider latency",
    provider_runtime_readiness: "runtime readiness",
    fallback_model_usage_rate: "fallback usage",
  };
  return labels[metric] ?? metric;
}

function adapterStatusLabel(status: ProviderApiKeyChecklistItem["adapterStatus"]) {
  return status === "supported_now" ? "supported" : "planned";
}

function freeTierFitLabel(fit: ProviderApiKeyChecklistItem["freeTierFit"]) {
  const labels: Record<ProviderApiKeyChecklistItem["freeTierFit"], string> = {
    good_for_first_dry_run: "free ok",
    trial_required: "trial",
    limited_for_soccer: "soccer limited",
  };
  return labels[fit];
}

function freeTierFitTone(fit: ProviderApiKeyChecklistItem["freeTierFit"]): BadgeTone {
  if (fit === "good_for_first_dry_run") return "success";
  if (fit === "trial_required") return "info";
  return "warning";
}

function roleLabel(role: string) {
  const labels: Record<string, string> = {
    fixtures_results_first_real_dry_run: "fixtures/results dry-run",
    broad_fixture_result_provider_candidate: "broad fixtures candidate",
    lineups_injuries_broad_coverage_candidate: "lineups/injuries",
    odds_market_snapshot_candidate: "odds snapshots",
  };
  return labels[role] ?? role;
}

function operatorActionLabel(action: string) {
  const labels: Record<string, string> = {
    apply_free_key_then_set_nutmeg_football_data_api_key: "先申请 football-data.org free key",
    apply_free_key_then_set_nutmeg_api_football_api_key: "配置 API-Football free key",
    apply_trial_key_then_set_nutmeg_sportmonks_api_key: "申请 SportMonks trial key",
    apply_free_key_but_expect_soccer_odds_limitations: "可先申请 The Odds API free key",
  };
  return labels[action] ?? action;
}

function decisionLabel(decision: ProviderReadiness["decision"]) {
  const labels: Record<ProviderReadiness["decision"], string> = {
    beta_ready: "beta ready",
    production_ready: "production ready",
    not_ready: "not ready",
  };
  return labels[decision];
}

function decisionTone(decision: ProviderReadiness["decision"]): BadgeTone {
  if (decision === "production_ready") return "success";
  if (decision === "beta_ready") return "info";
  return "warning";
}

function qualityTone(grade: ProviderReadiness["dataQuality"]["grade"]): BadgeTone {
  if (grade === "A") return "success";
  if (grade === "B") return "info";
  if (grade === "C") return "warning";
  return "risk";
}

function reviewSeverityTone(severity: ProviderMappingReview["issues"][number]["severity"]): BadgeTone {
  if (severity === "critical") return "risk";
  if (severity === "warning") return "warning";
  return "info";
}

function gapIssueTone(issue: ProviderOddsCoverageGap["issueTypes"][number]): BadgeTone {
  if (issue === "provider_event_unavailable") return "warning";
  if (issue === "no_odds" || issue === "unmapped") return "warning";
  if (issue === "stale_odds") return "info";
  return "neutral";
}

function gapIssueLabel(issue: ProviderOddsCoverageGap["issueTypes"][number]) {
  const labels: Record<ProviderOddsCoverageGap["issueTypes"][number], string> = {
    no_odds: "No odds",
    missing_market: "Missing market",
    stale_odds: "Stale odds",
    unmapped: "Unmapped",
    provider_event_unavailable: "Provider event unavailable",
  };
  return labels[issue];
}

function gapActionLabel(action: string) {
  const labels: Record<string, string> = {
    bootstrap_or_review_fixture_mapping: "补齐或复核 fixture mapping",
    sync_mapped_event_odds: "同步 mapped event odds",
    refresh_mapped_event_odds: "刷新 mapped event odds",
    try_fallback_provider_event_mapping: "检查 fallback provider event mapping",
    review_provider_markets: "复核 provider market 配置",
    review_gap: "复核覆盖缺口",
  };
  return labels[action] ?? action;
}

function gapFallbackStatusLabel(
  status: ProviderOddsCoverageGap["fallbackCandidates"][number]["adapterStatus"],
) {
  return status === "supported_now" ? "supported" : "planned";
}

function fallbackProbeStatusTone(
  status: ProviderOps["fallbackOddsProbe"]["items"][number]["status"],
): BadgeTone {
  if (status === "covered") return "success";
  if (status === "mapped_probe_ready") return "info";
  if (status === "adapter_planned") return "neutral";
  return "warning";
}

function fallbackProbeStatusLabel(
  status: ProviderOps["fallbackOddsProbe"]["items"][number]["status"],
) {
  const labels: Record<ProviderOps["fallbackOddsProbe"]["items"][number]["status"], string> = {
    mapping_missing: "Mapping missing",
    mapped_probe_ready: "Probe ready",
    covered: "Covered",
    mapped_no_supported_odds: "No supported odds",
    not_configured: "Key missing",
    provider_auth_failed: "Auth failed",
    provider_limited: "Plan limited",
    provider_rate_limited: "Rate limited",
    provider_unavailable: "Unavailable",
    adapter_planned: "Adapter planned",
  };
  return labels[status];
}

function fallbackProbeActionLabel(action: string) {
  const labels: Record<string, string> = {
    bootstrap_sportmonks_fixture_mapping: "补齐 SportMonks fixture mapping",
    run_live_sportmonks_odds_probe: "执行 SportMonks live odds probe",
    configure_nutmeg_sportmonks_api_key: "配置 SportMonks runtime key",
    review_sportmonks_key_or_plan_limits: "检查 SportMonks key 或套餐限制",
    retry_sportmonks_fallback_probe_later: "稍后重试 SportMonks probe",
    review_sportmonks_market_payload: "复核 SportMonks market payload",
    queue_sportmonks_odds_snapshot_sync_after_operator_review:
      "审核后排入 SportMonks odds snapshot sync",
  };
  return labels[action] ?? action;
}

function conflictStatusTone(
  status: ProviderConflictGovernance["persistedEvents"][number]["resolutionStatus"],
): BadgeTone {
  if (status === "open") return "warning";
  if (status === "resolved") return "success";
  return "neutral";
}

function reviewIssueLabel(issueType: ProviderMappingReview["issues"][number]["issueType"]) {
  const labels: Record<ProviderMappingReview["issues"][number]["issueType"], string> = {
    low_confidence: "低置信度",
    same_provider_canonical_collision: "Canonical 碰撞",
    stale_mapping: "陈旧映射",
  };
  return labels[issueType];
}

function conflictTypeLabel(issueType: ProviderConflictGovernance["events"][number]["conflictType"]) {
  const labels: Record<ProviderConflictGovernance["events"][number]["conflictType"], string> = {
    provider_mapping_conflict: "映射冲突",
    provider_observation_conflict: "观测冲突",
  };
  return labels[issueType];
}

function conflictEvidenceLabel(event: ProviderConflictGovernance["events"][number]) {
  const evidence = event.evidenceJson;
  if (event.conflictType === "provider_observation_conflict") {
    const fieldName =
      typeof evidence.field_name === "string" ? evidence.field_name : "field";
    const valuesByProvider = evidence.values_by_provider;
    const sourceCount =
      valuesByProvider !== null &&
      typeof valuesByProvider === "object" &&
      !Array.isArray(valuesByProvider)
        ? Object.keys(valuesByProvider).length
        : event.providerNames.length;
    return `${fieldName} / ${sourceCount} sources`;
  }
  if (typeof evidence.mapping_issue_type === "string") {
    return evidence.mapping_issue_type;
  }
  return event.sourceIssueId ?? "review_evidence";
}
