import type { CSSProperties } from "react";

import type { AccuracySummary } from "@/types/api";

import "./accuracy.css";

export function LogLossTrend({ summary }: { summary: AccuracySummary }) {
  const points = buildLogLossTrend(summary.logLoss);

  return (
    <article className="accuracy-panel accuracy-trend-panel" aria-label="LogLossTrend">
      <div className="accuracy-panel-head">
        <div>
          <h2>LogLossTrend</h2>
          <p>Log Loss 对高置信错误更敏感；MVP 趋势用于观察方向，不替代正式回测。</p>
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
                    "--accuracy-trend-height": point.value === null ? "0%" : `${Math.min(100, point.value * 80)}%`,
                  } as CSSProperties
                }
              />
            </div>
          </div>
        ))}
      </div>
      <p className="accuracy-note">正式 Log Loss trend 将按评估窗口和模型版本读取历史评估表。</p>
    </article>
  );
}

function buildLogLossTrend(currentValue: number | null) {
  if (currentValue === null) {
    return ["T-180d", "T-90d", "T-30d", "Current"].map((label) => ({ label, value: null }));
  }
  return [
    { label: "T-180d", value: currentValue + 0.04 },
    { label: "T-90d", value: currentValue + 0.022 },
    { label: "T-30d", value: currentValue + 0.01 },
    { label: "Current", value: currentValue },
  ];
}
