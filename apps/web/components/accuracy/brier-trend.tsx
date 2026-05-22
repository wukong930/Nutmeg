import type { CSSProperties } from "react";

import type { AccuracySummary } from "@/types/api";

import "./accuracy.css";

export function BrierTrend({ summary }: { summary: AccuracySummary }) {
  const points = buildBrierTrend(summary.brierScore);

  return (
    <article className="accuracy-panel accuracy-trend-panel" aria-label="BrierTrend">
      <div className="accuracy-panel-head">
        <div>
          <h2>BrierTrend</h2>
          <p>Brier Score 越低越好；MVP 使用当前摘要生成稳定趋势占位。</p>
        </div>
      </div>
      <div className="accuracy-trend-bars">
        {points.map((point) => (
          <div className="accuracy-trend-bar" key={point.label}>
            <span>{point.label}</span>
            <strong>{point.value === null ? "N/A" : point.value.toFixed(3)}</strong>
            <div className="accuracy-trend-track">
              <span
                style={
                  {
                    "--accuracy-trend-height": point.value === null ? "0%" : `${Math.min(100, point.value * 260)}%`,
                  } as CSSProperties
                }
              />
            </div>
          </div>
        ))}
      </div>
      <p className="accuracy-note">完整 Brier trend 将由 backtest run 时间序列驱动。</p>
    </article>
  );
}

function buildBrierTrend(currentValue: number | null) {
  if (currentValue === null) {
    return ["T-180d", "T-90d", "T-30d", "Current"].map((label) => ({ label, value: null }));
  }
  return [
    { label: "T-180d", value: currentValue + 0.014 },
    { label: "T-90d", value: currentValue + 0.007 },
    { label: "T-30d", value: currentValue + 0.003 },
    { label: "Current", value: currentValue },
  ];
}
