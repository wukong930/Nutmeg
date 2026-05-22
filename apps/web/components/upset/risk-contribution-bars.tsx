import type { CSSProperties } from "react";

import type { UpsetContribution } from "@/types/api";

export function RiskContributionBars({ contributions }: { contributions: UpsetContribution[] }) {
  return (
    <div className="risk-contribution-list" aria-label="冷门风险贡献条">
      {contributions.map((item) => {
        const width = `${Math.max(0, Math.min(100, item.score))}%`;
        return (
          <div className="risk-contribution-row" key={item.key}>
            <div className="risk-contribution-label">
              <span>{item.label}</span>
              <strong>{item.score.toFixed(1)}</strong>
            </div>
            <span className="risk-contribution-track" aria-hidden="true">
              <span
                className="risk-contribution-fill"
                style={{ "--risk-contribution-width": width } as CSSProperties}
              />
            </span>
            <p>{item.description}</p>
          </div>
        );
      })}
    </div>
  );
}
