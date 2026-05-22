import { Clock3 } from "lucide-react";

import { formatPercent } from "@/lib/format";
import type { MatchPrediction } from "@/types/api";

import "./market.css";

const timelineLabels = ["Opening", "T-72h", "T-24h", "T-6h", "T-1h", "Latest"] as const;

export function MarketMovementTimeline({ match }: { match: MatchPrediction }) {
  const freshness = match.dataFreshness;
  return (
    <section className="market-panel" aria-label="Market Movement Timeline">
      <div className="market-panel-head">
        <div>
          <h3 className="section-title">Market Movement Timeline</h3>
          <p className="meta">基础版显示最新快照，并显式标记缺失的历史盘口节点。</p>
        </div>
        <Clock3 size={18} aria-hidden="true" />
      </div>
      <ol className="market-timeline">
        {timelineLabels.map((label) => {
          const isLatest = label === "Latest";
          return (
            <li className={isLatest ? "market-timeline-point current" : "market-timeline-point missing"} key={label}>
              <span>{label}</span>
              {isLatest ? (
                <div>
                  <strong>{match.asianHandicap.label}</strong>
                  <p>
                    {freshness?.oddsSnapshotLagHours !== null &&
                    freshness?.oddsSnapshotLagHours !== undefined
                      ? `赔率快照约 T-${freshness.oddsSnapshotLagHours.toFixed(1)}h · `
                      : ""}
                    {match.oneXTwo
                      .map(
                        (item) =>
                          `${item.label} ${formatPercent(item.marketProbability ?? item.probability)}`,
                      )
                      .join(" · ")}
                  </p>
                </div>
              ) : (
                <div>
                  <strong>历史快照待接入</strong>
                  <p>缺少该时间点的赔率/盘口数据。</p>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {match.status === "stale" || freshness?.stale ? (
        <p className="market-warning">部分数据未及时更新，预测仅供参考。</p>
      ) : (
        <p className="market-warning">当前版本不展示历史盘口变化，避免把缺失数据解释为真实走势。</p>
      )}
    </section>
  );
}
