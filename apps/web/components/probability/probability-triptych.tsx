import { formatDateTime, formatPercent, formatPp } from "@/lib/format";
import type { ProbabilityItem } from "@/types/api";

import "./probability.css";

type ProbabilityTriptychProps = {
  items: ProbabilityItem[];
  modelVersion?: string;
  predictionTimeUtc?: string;
  compact?: boolean;
};

export function ProbabilityTriptych({
  items,
  modelVersion,
  predictionTimeUtc,
  compact = false,
}: ProbabilityTriptychProps) {
  const total = items.reduce((sum, item) => sum + item.probability, 0) || 1;

  return (
    <section
      className={compact ? "probability-triptych probability-triptych-compact" : "probability-triptych"}
      aria-label="1X2 概率三联展示"
    >
      <div className="probability-triptych-strip" aria-hidden="true">
        {items.map((item) => (
          <span
            className="probability-triptych-segment"
            key={item.label}
            style={{ width: `${Math.max((item.probability / total) * 100, 3)}%` }}
          />
        ))}
      </div>
      <div className="probability-triptych-grid">
        {items.map((item) => {
          const edge =
            item.marketProbability === undefined ? undefined : item.probability - item.marketProbability;
          return (
            <div className="probability-triptych-item" key={item.label}>
              <span className="probability-triptych-label">{item.label}</span>
              <strong>{formatPercent(item.probability)}</strong>
              {item.marketProbability !== undefined ? (
                <span className="probability-triptych-market">
                  市场 {formatPercent(item.marketProbability)}
                </span>
              ) : null}
              {edge !== undefined ? (
                <span className={edge >= 0 ? "edge-positive" : "edge-negative"}>
                  差异 {formatPp(edge)}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
      {modelVersion || predictionTimeUtc ? (
        <div className="probability-triptych-meta">
          {modelVersion ? <span>model {modelVersion}</span> : null}
          {predictionTimeUtc ? <span>更新 {formatDateTime(predictionTimeUtc)}</span> : null}
        </div>
      ) : null}
    </section>
  );
}
