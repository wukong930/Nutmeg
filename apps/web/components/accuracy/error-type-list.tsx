import { AlertTriangle } from "lucide-react";

import { formatPercent } from "@/lib/format";
import type { ErrorTypeSummary } from "@/types/api";

import "./accuracy.css";

export function ErrorTypeList({ errorTypes }: { errorTypes: ErrorTypeSummary[] }) {
  return (
    <article className="accuracy-panel">
      <div className="accuracy-panel-head">
        <div>
          <h2>错误类型分布</h2>
          <p>赛后评估将偏差归入可追踪标签，供后续校准与训练复盘使用。</p>
        </div>
        <AlertTriangle size={18} aria-hidden="true" />
      </div>
      <div className="error-type-list">
        {errorTypes.map((item) => (
          <div key={item.tag} className="error-type-row">
            <div>
              <strong>{item.label}</strong>
              <span className="mono">{item.tag}</span>
            </div>
            <div className="error-type-count">
              <strong>{item.count}</strong>
              <span>{formatPercent(item.share)}</span>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
