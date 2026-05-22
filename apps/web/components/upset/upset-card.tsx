import { AlertTriangle } from "lucide-react";

import { formatPercent, formatPp, riskLabel } from "@/lib/format";
import type { UpsetAlert } from "@/types/api";

import { FavoriteFragilityPanel } from "./favorite-fragility-panel";
import { UpsetExplanationDrawer } from "./upset-explanation-drawer";

import "./upset.css";

export function UpsetCard({
  alert,
  variant = "full",
}: {
  alert: UpsetAlert;
  variant?: "compact" | "full";
}) {
  return (
    <article className={`upset-card upset-card-${variant}`}>
      <div className="upset-head">
        <span className={`upset-icon risk-${alert.riskLevel}`}>
          <AlertTriangle size={16} aria-hidden="true" />
        </span>
        <div>
          <h3>{alert.label}</h3>
          <p>{alert.targetOutcome}</p>
        </div>
      </div>
      <div className="upset-metrics">
        <span>模型 {formatPercent(alert.modelProbability)}</span>
        <span>市场 {formatPercent(alert.marketProbability)}</span>
        <span>差值 {formatPp(alert.probabilityGap)}</span>
          <span>{riskLabel(alert.riskLevel)}</span>
      </div>
      <ul className="upset-reasons">
        {alert.explanations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {variant === "full" ? (
        <>
          <FavoriteFragilityPanel alert={alert} />
          <UpsetExplanationDrawer alert={alert} />
        </>
      ) : null}
    </article>
  );
}
