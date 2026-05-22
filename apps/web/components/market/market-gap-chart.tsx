import { BarChart3 } from "lucide-react";

import { formatPercent, formatPp } from "@/lib/format";
import type { ProbabilityItem } from "@/types/api";
import { Tooltip } from "@/components/ui/tooltip";

import "./market.css";

type MarketGapChartProps = {
  title: string;
  label: string;
  items: ProbabilityItem[];
};

export function MarketGapChart({ title, label, items }: MarketGapChartProps) {
  const gaps = items
    .map((item) => ({
      ...item,
      gap: item.marketProbability === undefined ? null : item.probability - item.marketProbability,
    }))
    .filter((item) => item.gap !== null);
  const maxGap = Math.max(0.01, ...gaps.map((item) => Math.abs(item.gap ?? 0)));

  return (
    <section className="market-panel" aria-label={title}>
      <div className="market-panel-head">
        <div>
          <h3 className="section-title">{title}</h3>
          <p className="meta">{label}</p>
        </div>
        <Tooltip label="市场分歧不是自动投注价值，只表示模型概率与市场隐含概率不同。">
          <BarChart3 size={18} aria-hidden="true" />
        </Tooltip>
      </div>
      <div className="market-gap-list">
        {items.map((item) => {
          const gap = item.marketProbability === undefined ? null : item.probability - item.marketProbability;
          const width = gap === null ? 0 : Math.max(4, Math.abs(gap / maxGap) * 100);
          return (
            <div className="market-gap-row" key={item.label}>
              <div className="market-gap-label">
                <strong>{item.label}</strong>
                <span>
                  模型 {formatPercent(item.probability)}
                  {item.marketProbability === undefined ? "" : ` · 市场 ${formatPercent(item.marketProbability)}`}
                </span>
              </div>
              <div className="market-gap-track" aria-label={`${item.label} 市场差异`}>
                <span className="market-gap-half market-gap-negative">
                  {gap !== null && gap < 0 ? <i style={{ width: `${width}%` }} /> : null}
                </span>
                <span className="market-gap-zero" aria-hidden="true" />
                <span className="market-gap-half market-gap-positive">
                  {gap !== null && gap >= 0 ? <i style={{ width: `${width}%` }} /> : null}
                </span>
              </div>
              <span className={gap !== null && gap >= 0 ? "edge-positive mono" : "edge-negative mono"}>
                {gap === null ? "N/A" : formatPp(gap)}
              </span>
            </div>
          );
        })}
      </div>
      <p className="market-warning">市场分歧只表示模型与市场观点不同，不代表结果必然发生。</p>
    </section>
  );
}
