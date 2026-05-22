import { Database, Fingerprint } from "lucide-react";

import { DataQualityBadge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import type { MatchPrediction } from "@/types/api";

import "./model.css";

export function ModelFingerprint({ match }: { match: MatchPrediction }) {
  const rows = [
    ["Model", match.modelVersion],
    ["Feature", match.featureVersion],
    ["Calibration", match.calibrationVersion],
    ["Prediction", formatDateTime(match.predictionTimeUtc)],
    ["Competition", match.competitionName],
  ] as const;

  return (
    <section className="model-fingerprint panel" aria-label="Model Fingerprint">
      <div className="model-fingerprint-head">
        <div>
          <h2 className="section-title">Model Fingerprint</h2>
          <p className="meta">本次预测的版本、校准和数据上下文。</p>
        </div>
        <Fingerprint size={18} aria-hidden="true" />
      </div>
      <dl className="model-fingerprint-list">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="mono">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="model-fingerprint-quality">
        <DataQualityBadge grade={match.dataQualityGrade} score={match.dataQualityScore} />
        <span className="badge">
          <Database size={14} aria-hidden="true" />
          {match.modelStatus}
        </span>
      </div>
    </section>
  );
}
