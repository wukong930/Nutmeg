import type { CSSProperties } from "react";

import { formatPercent } from "@/lib/format";
import type { CalibrationBucket } from "@/types/api";

import "./accuracy.css";

export function CalibrationCurve({ buckets }: { buckets: CalibrationBucket[] }) {
  const points = buckets.map((bucket) => ({
    key: `${bucket.bucketStart}-${bucket.bucketEnd}`,
    label: `${formatPercent(bucket.bucketStart, 0)}-${formatPercent(bucket.bucketEnd, 0)}`,
    predicted: bucket.averagePredictedProbability,
    actual: bucket.actualFrequency,
    sampleSize: bucket.sampleSize,
    error: bucket.actualFrequency - bucket.averagePredictedProbability,
  }));

  return (
    <article className="accuracy-panel calibration-curve-panel" aria-label="CalibrationCurve">
      <div className="accuracy-panel-head">
        <div>
          <h2>CalibrationCurve</h2>
          <p>对比预测概率与实际频率；对角线附近表示校准更好。</p>
        </div>
      </div>

      <div className="calibration-curve-chart" aria-label="校准曲线图">
        <span className="calibration-diagonal" aria-hidden="true" />
        {points.map((point) => (
          <span
            className="calibration-point"
            key={point.key}
            style={
              {
                "--calibration-x": `${point.predicted * 100}%`,
                "--calibration-y": `${(1 - point.actual) * 100}%`,
              } as CSSProperties
            }
            title={`${point.label}：模型 ${formatPercent(point.predicted)}，实际 ${formatPercent(point.actual)}`}
          >
            <span className="sr-only">
              {point.label} 模型 {formatPercent(point.predicted)} 实际 {formatPercent(point.actual)}
            </span>
          </span>
        ))}
      </div>

      <div className="calibration-curve-table">
        {points.map((point) => (
          <div className="calibration-curve-row" key={point.key}>
            <strong>{point.label}</strong>
            <span>模型 {formatPercent(point.predicted)}</span>
            <span>实际 {formatPercent(point.actual)}</span>
            <span>偏差 {formatSignedPp(point.error)}</span>
            <span>{point.sampleSize} 样本</span>
          </div>
        ))}
      </div>
    </article>
  );
}

function formatSignedPp(value: number) {
  const prefix = value >= 0 ? "+" : "";
  return `${prefix}${(value * 100).toFixed(1)}pp`;
}
