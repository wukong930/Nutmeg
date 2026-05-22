import { CheckCircle2, CircleAlert, Clock3, Sigma } from "lucide-react";

import type { MatchPrediction } from "@/types/api";

import "./prediction.css";

type TraceStatus = "ready" | "partial" | "stale" | "estimated";

type TraceStep = {
  label: string;
  detail: string;
  status: TraceStatus;
};

const statusLabels: Record<TraceStatus, string> = {
  ready: "ready",
  partial: "partial",
  stale: "stale",
  estimated: "estimated",
};

export function PredictionTrace({ match }: { match: MatchPrediction }) {
  const steps = buildTraceSteps(match);

  return (
    <section className="prediction-trace panel" aria-label="Prediction Trace">
      <div className="prediction-trace-head">
        <div>
          <h2 className="section-title">Prediction Trace</h2>
          <p className="meta">数据快照 → 特征 → 比分矩阵 → 玩法解析 → 风险 → 解释</p>
        </div>
        <Sigma size={18} aria-hidden="true" />
      </div>
      <ol className="prediction-trace-steps">
        {steps.map((step) => (
          <li className={`trace-step trace-step-${step.status}`} key={step.label}>
            <span className="trace-step-icon">{iconForStatus(step.status)}</span>
            <span>
              <strong>{step.label}</strong>
              <span>{step.detail}</span>
            </span>
            <em>{statusLabels[step.status]}</em>
          </li>
        ))}
      </ol>
    </section>
  );
}

function buildTraceSteps(match: MatchPrediction): TraceStep[] {
  return [
    {
      label: "Data Snapshot",
      detail: `数据质量 ${match.dataQualityGrade} · ${match.dataQualityScore}/100`,
      status: match.status === "stale" ? "stale" : match.dataQualityGrade === "A" ? "ready" : "partial",
    },
    {
      label: "Feature Engine",
      detail: match.featureVersion,
      status: match.modelStatus === "beta" ? "estimated" : "ready",
    },
    {
      label: "Score Grid",
      detail: `${match.correctScores.length} 个 Top score · 尾部风险可见`,
      status: match.correctScores.length > 0 ? "ready" : "partial",
    },
    {
      label: "Market Resolver",
      detail: "1X2 / 让球 / 比分已派生",
      status: marketReady(match) ? "ready" : "partial",
    },
    {
      label: "Risk Analysis",
      detail: match.upsetAlerts.length > 0 ? `${match.upsetAlerts.length} 条冷门观察` : "暂无显著冷门信号",
      status: match.upsetAlerts.length > 0 ? "ready" : "partial",
    },
    {
      label: "Explanation",
      detail: "模型、市场、阵容、赛程、不确定因素",
      status: "ready",
    },
  ];
}

function marketReady(match: MatchPrediction) {
  return (
    match.oneXTwo.length > 0 &&
    match.cnHandicap.items.length > 0 &&
    match.asianHandicap.items.length > 0 &&
    match.europeanHandicap.items.length > 0
  );
}

function iconForStatus(status: TraceStatus) {
  if (status === "ready") return <CheckCircle2 size={16} aria-hidden="true" />;
  if (status === "stale") return <Clock3 size={16} aria-hidden="true" />;
  return <CircleAlert size={16} aria-hidden="true" />;
}
