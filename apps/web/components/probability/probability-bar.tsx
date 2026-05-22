import { formatPercent, formatPp } from "@/lib/format";
import type { ProbabilityItem } from "@/types/api";

import "./probability.css";

export function ProbabilityBar({
  items,
  showMarketComparison = false,
}: {
  items: ProbabilityItem[];
  showMarketComparison?: boolean;
}) {
  return (
    <div className="probability-bar" role="list">
      {items.map((item) => {
        const edge =
          item.marketProbability === undefined ? undefined : item.probability - item.marketProbability;
        return (
          <div
            className={item.isHighlighted ? "probability-item highlighted" : "probability-item"}
            key={item.label}
            role="listitem"
          >
            <div className="probability-head">
              <span className="probability-label">{item.label}</span>
              <span className="probability-value">{formatPercent(item.probability)}</span>
            </div>
            <div
              className="probability-track"
              aria-label={`${item.label} ${formatPercent(item.probability)}`}
            >
              <span style={{ width: `${Math.max(item.probability * 100, 2)}%` }} />
            </div>
            {showMarketComparison && item.marketProbability !== undefined ? (
              <div className="probability-meta">
                <span>市场 {formatPercent(item.marketProbability)}</span>
                <span className={edge !== undefined && edge >= 0 ? "edge-positive" : "edge-negative"}>
                  {edge === undefined ? "" : formatPp(edge)}
                </span>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
