import { formatPercent } from "@/lib/format";
import type { CalibrationBucket } from "@/types/api";

import "./accuracy.css";

export function CalibrationBucketList({ buckets }: { buckets: CalibrationBucket[] }) {
  return (
    <article className="accuracy-panel">
      <div className="accuracy-panel-head">
        <div>
          <h2>校准曲线</h2>
          <p>按预测概率区间对比模型均值与实际频率。</p>
        </div>
      </div>
      <div className="calibration-list">
        {buckets.map((bucket) => (
          <div key={`${bucket.bucketStart}-${bucket.bucketEnd}`} className="calibration-row">
            <div className="calibration-label">
              <strong>
                {formatPercent(bucket.bucketStart, 0)} - {formatPercent(bucket.bucketEnd, 0)}
              </strong>
              <span>{bucket.sampleSize} 场样本</span>
            </div>
            <div className="calibration-bars">
              <CalibrationBar
                label="模型均值"
                value={bucket.averagePredictedProbability}
                className="bar-model"
              />
              <CalibrationBar label="实际频率" value={bucket.actualFrequency} className="bar-actual" />
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function CalibrationBar({
  label,
  value,
  className,
}: {
  label: string;
  value: number;
  className: string;
}) {
  return (
    <div className="calibration-bar-row">
      <span>{label}</span>
      <div className="calibration-track" aria-label={`${label} ${formatPercent(value)}`}>
        <div className={className} style={{ width: formatPercent(value, 2) }} />
      </div>
      <strong>{formatPercent(value)}</strong>
    </div>
  );
}
