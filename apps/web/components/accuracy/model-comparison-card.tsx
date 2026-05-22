import { GitCompareArrows } from "lucide-react";

import type { ModelComparison } from "@/types/api";

import "./accuracy.css";

const decisionLabels: Record<ModelComparison["decision"], string> = {
  promote_candidate: "候选通过门槛",
  keep_baseline: "保留当前基线",
  needs_review: "候选需复核",
};

export function ModelComparisonCard({ comparison }: { comparison: ModelComparison }) {
  return (
    <article className="accuracy-panel">
      <div className="accuracy-panel-head">
        <div>
          <h2>模型版本对比</h2>
          <p>晋级记录以回测与校准证据为准，当前仅展示候选评估存根。</p>
        </div>
        <GitCompareArrows size={18} aria-hidden="true" />
      </div>
      <div className="comparison-grid">
        <Metric label="基线版本" value={comparison.baselineModelVersion} />
        <Metric label="候选版本" value={comparison.candidateModelVersion} />
        <Metric label="基线 Log Loss" value={formatNumber(comparison.baselineLogLoss)} />
        <Metric label="候选 Log Loss" value={formatNumber(comparison.candidateLogLoss)} />
        <Metric label="基线 Brier" value={formatNumber(comparison.baselineBrierScore)} />
        <Metric label="候选 Brier" value={formatNumber(comparison.candidateBrierScore)} />
      </div>
      <div className="comparison-decision">{decisionLabels[comparison.decision]}</div>
      <ul className="accuracy-reason-list">
        {comparison.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatNumber(value: number | null) {
  return value === null ? "N/A" : value.toFixed(3);
}
