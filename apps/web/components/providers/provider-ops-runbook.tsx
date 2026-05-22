import {
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Database,
  GitCompareArrows,
  KeyRound,
  Link2,
  ShieldAlert,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { formatDateTime, formatPercent } from "@/lib/format";
import type { ProviderOps, ProviderReadiness } from "@/types/api";

type RunbookStatus = "ready" | "review" | "blocked" | "pending";

type RunbookStep = {
  id: string;
  title: string;
  status: RunbookStatus;
  icon: ReactNode;
  evidence: string;
  nextAction: string;
  metrics: Array<{ label: string; value: string; tone?: RunbookStatus }>;
};

export function ProviderOpsRunbook({ ops }: { ops: ProviderOps }) {
  const readiness = primaryReadiness(ops.readiness);
  const steps = providerRunbookSteps(ops, readiness);
  const currentStep = steps.find((step) => step.status !== "ready") ?? steps.at(-1);
  const readyCount = steps.filter((step) => step.status === "ready").length;

  return (
    <section className="section provider-runbook-section" aria-labelledby="provider-runbook-title">
      <div className="section-header">
        <div>
          <h2 id="provider-runbook-title" className="section-title">
            Provider Ops Runbook
          </h2>
          <p className="meta">
            从数据源 key、映射审核、赔率覆盖到 prediction gate 的当前链路状态。
          </p>
        </div>
        <div className="provider-review-strip">
          <Badge tone={readyCount === steps.length ? "success" : "info"}>
            ready {readyCount}/{steps.length}
          </Badge>
          <Badge tone={statusTone(currentStep?.status ?? "pending")}>
            current {currentStep?.title ?? "N/A"}
          </Badge>
          <Badge>checked {formatDateTime(ops.generatedAtUtc)}</Badge>
        </div>
      </div>

      <div className="provider-runbook-grid">
        {steps.map((step, index) => (
          <article
            key={step.id}
            className="provider-runbook-card"
            data-status={step.status}
            aria-label={`${step.title} status ${step.status}`}
          >
            <div className="provider-runbook-card-head">
              <span className="provider-runbook-icon">{step.icon}</span>
              <div>
                <h3 className="provider-runbook-title">{step.title}</h3>
                <Badge tone={statusTone(step.status)}>{statusLabel(step.status)}</Badge>
              </div>
            </div>
            <p className="provider-runbook-evidence">{step.evidence}</p>
            <dl className="provider-runbook-metrics">
              {step.metrics.map((metric) => (
                <div key={metric.label}>
                  <dt>{metric.label}</dt>
                  <dd data-tone={metric.tone ?? "pending"}>{metric.value}</dd>
                </div>
              ))}
            </dl>
            <div className="provider-runbook-next">
              <ArrowRight size={14} aria-hidden="true" />
              {step.nextAction}
            </div>
            <span className="provider-runbook-order mono">{String(index + 1).padStart(2, "0")}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function providerRunbookSteps(
  ops: ProviderOps,
  readiness: ProviderReadiness | null,
): RunbookStep[] {
  const externalCredentials = ops.runtimeCredentials.items.filter(
    (item) => item.requiresApiKeyForCommit,
  );
  const readyCredentials = externalCredentials.filter((item) => item.safeToCallRealProvider);
  const credentialStatus = statusFromCounts(
    readyCredentials.length,
    externalCredentials.length,
    ops.runtimeCredentials.mockDryRunEnabled,
  );

  const oddsFixtureMappings = ops.mappingSummary.filter(
    (item) =>
      item.provider === "the-odds-api" &&
      ["fixture", "event", "match"].includes(item.entityType),
  );
  const oddsMappingCount = oddsFixtureMappings.reduce(
    (sum, item) => sum + item.mappingCount,
    0,
  );
  const oddsMappingIssues = ops.mappingReview.issues.filter(
    (issue) =>
      issue.provider === "the-odds-api" &&
      ["fixture", "event", "match"].includes(issue.entityType),
  );
  const oddsMappingCritical = oddsMappingIssues.filter(
    (issue) => issue.severity === "critical",
  ).length;
  const mappingStatus =
    oddsMappingCount === 0
      ? "blocked"
      : oddsMappingCritical > 0
        ? "blocked"
        : oddsMappingIssues.length > 0
          ? "review"
          : "ready";

  const oddsCoverage = ops.oddsCoverage.oneXTwoCoverage;
  const handicapCoverage = ops.oddsCoverage.handicapCoverage;
  const freshness = ops.oddsCoverage.freshOddsCoverage;
  const oddsStatus =
    ops.oddsGapReport.gapCount > 0
      ? "review"
      : oddsCoverage >= 0.6 && handicapCoverage >= 0.6
      ? "ready"
      : oddsCoverage > 0 || handicapCoverage > 0
        ? "review"
        : "blocked";

  const latestPrediction = ops.predictionQualityGate.latestRun;
  const predictionStatus =
    latestPrediction === null
      ? "pending"
      : latestPrediction.status === "failed"
        ? "blocked"
        : latestPrediction.status === "running"
          ? "pending"
          : latestPrediction.generatedCount > 0 &&
              latestPrediction.skippedFixtureIds.length === 0
            ? "ready"
            : latestPrediction.generatedCount > 0
              ? "review"
              : "blocked";

  const conflictStatus =
    ops.conflictGovernance.persistedOpenCount === 0 &&
    ops.conflictGovernance.criticalCount === 0
      ? "ready"
      : ops.conflictGovernance.criticalCount > 0
        ? "blocked"
        : "review";

  return [
    {
      id: "runtime-keys",
      title: "Runtime keys",
      status: credentialStatus,
      icon: <KeyRound size={18} aria-hidden="true" />,
      evidence:
        externalCredentials.length > 0
          ? `${readyCredentials.length} of ${externalCredentials.length} external providers are safe for real dry-run calls.`
          : "No external provider credential is required for the current deterministic path.",
      nextAction:
        credentialStatus === "ready"
          ? "继续使用真实 provider dry-run；secret 值不在页面返回。"
          : ops.runtimeCredentials.mockDryRunEnabled
            ? "可先用 deterministic mock dry-run；提交写入前补齐 provider key。"
            : "补齐缺失 provider key 后再运行真实 dry-run。",
      metrics: [
        {
          label: "real keys",
          value: `${readyCredentials.length}/${externalCredentials.length}`,
          tone: credentialStatus,
        },
        {
          label: "mock dry-run",
          value: ops.runtimeCredentials.mockDryRunEnabled ? "enabled" : "disabled",
          tone: ops.runtimeCredentials.mockDryRunEnabled ? "ready" : "review",
        },
      ],
    },
    {
      id: "fixture-mappings",
      title: "Fixture mappings",
      status: mappingStatus,
      icon: <Link2 size={18} aria-hidden="true" />,
      evidence:
        oddsMappingCount > 0
          ? `${oddsMappingCount} reviewed The Odds API fixture mappings are available for eventIds batch checks.`
          : "The Odds API fixture mappings are not available yet.",
      nextAction:
        mappingStatus === "ready"
          ? "可运行 Mapped Odds Sync dry-run 检查最新赔率覆盖。"
          : "先执行 mapping bootstrap/review，处理低置信度或碰撞映射。",
      metrics: [
        { label: "mappings", value: oddsMappingCount.toString(), tone: mappingStatus },
        {
          label: "review issues",
          value: oddsMappingIssues.length.toString(),
          tone: oddsMappingIssues.length > 0 ? "review" : "ready",
        },
      ],
    },
    {
      id: "odds-coverage",
      title: "Odds coverage",
      status: oddsStatus,
      icon: <Database size={18} aria-hidden="true" />,
      evidence: ops.oddsCoverage.fetched
        ? `${ops.oddsCoverage.competitionId} coverage report has ${ops.oddsCoverage.oddsSnapshotCount} odds snapshots and ${ops.oddsGapReport.gapCount} fixture gaps.`
        : readiness
          ? `${readiness.competitionId} ${readiness.targetStage} gate is available, but live odds coverage report was not fetched.`
          : "No competition readiness or odds coverage record is available.",
      nextAction:
        oddsStatus === "ready"
          ? "可进入 Prediction Quality Gate dry-run。"
          : "先处理 Odds Coverage Gaps；通过审核后再用受保护路径写入 odds snapshots。",
      metrics: [
        { label: "1X2 odds", value: formatPercent(oddsCoverage, 0), tone: oddsStatus },
        {
          label: "handicap",
          value: formatPercent(handicapCoverage, 0),
          tone: oddsStatus,
        },
        {
          label: "freshness",
          value: formatPercent(freshness, 0),
          tone: freshness >= 0.6 ? "ready" : "review",
        },
        {
          label: "gaps",
          value: String(ops.oddsGapReport.gapCount),
          tone: ops.oddsGapReport.gapCount > 0 ? "review" : "ready",
        },
      ],
    },
    {
      id: "prediction-gate",
      title: "Prediction gate",
      status: predictionStatus,
      icon:
        latestPrediction?.status === "running" ? (
          <Clock3 size={18} aria-hidden="true" />
        ) : (
          <CheckCircle2 size={18} aria-hidden="true" />
        ),
      evidence: latestPrediction
        ? `Latest dry-run generated ${latestPrediction.generatedCount} predictions and skipped ${latestPrediction.skippedFixtureIds.length} fixtures.`
        : "No canonical prediction quality dry-run has been recorded yet.",
      nextAction:
        predictionStatus === "ready"
          ? "记录当前质量证据，后续可评估是否进入受控提交流程。"
          : "运行 Prediction Quality Gate dry-run，重点检查 odds gate skips 和 warnings。",
      metrics: [
        {
          label: "generated",
          value: String(latestPrediction?.generatedCount ?? 0),
          tone: predictionStatus,
        },
        {
          label: "skipped",
          value: String(latestPrediction?.skippedFixtureIds.length ?? 0),
          tone:
            latestPrediction && latestPrediction.skippedFixtureIds.length > 0
              ? "review"
              : "ready",
        },
      ],
    },
    {
      id: "conflict-governance",
      title: "Conflict governance",
      status: conflictStatus,
      icon:
        conflictStatus === "ready" ? (
          <CircleDashed size={18} aria-hidden="true" />
        ) : (
          <ShieldAlert size={18} aria-hidden="true" />
        ),
      evidence:
        ops.conflictGovernance.persistedOpenCount > 0
          ? `${ops.conflictGovernance.persistedOpenCount} open provider conflicts still need operator resolution.`
          : "No persisted open provider conflicts are blocking the current chain.",
      nextAction:
        conflictStatus === "ready"
          ? "保持 trusted provider priority 可审计。"
          : "先处理 open conflicts，再让 provider consistency 参与 feature snapshot。",
      metrics: [
        {
          label: "open",
          value: String(ops.conflictGovernance.persistedOpenCount),
          tone: conflictStatus,
        },
        {
          label: "consistency",
          value: formatPercent(
            ops.conflictGovernance.providerConsistencyAfterConflicts,
            0,
          ),
          tone: conflictStatus,
        },
      ],
    },
  ];
}

function primaryReadiness(readiness: ProviderReadiness[]) {
  return (
    readiness.find((item) => item.competitionId === "EPL" && item.targetStage === "beta") ??
    readiness.find((item) => item.targetStage === "beta") ??
    readiness[0] ??
    null
  );
}

function statusFromCounts(
  readyCount: number,
  totalCount: number,
  mockDryRunEnabled: boolean,
): RunbookStatus {
  if (totalCount === 0 || readyCount === totalCount) {
    return "ready";
  }
  if (readyCount > 0 || mockDryRunEnabled) {
    return "review";
  }
  return "blocked";
}

function statusTone(status: RunbookStatus) {
  switch (status) {
    case "ready":
      return "success";
    case "review":
      return "warning";
    case "blocked":
      return "risk";
    case "pending":
      return "info";
  }
}

function statusLabel(status: RunbookStatus) {
  switch (status) {
    case "ready":
      return "ready";
    case "review":
      return "needs review";
    case "blocked":
      return "blocked";
    case "pending":
      return "pending";
  }
}
