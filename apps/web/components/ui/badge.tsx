import type { ReactNode } from "react";

import { qualityLabel, riskLabel } from "@/lib/format";
import type { DataQualityGrade, RiskLevel } from "@/types/api";

type BadgeTone = "neutral" | "brand" | "info" | "warning" | "risk" | "success" | "beta";

export function Badge({
  children,
  tone = "neutral",
  className,
  title,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  title?: string;
}) {
  const classes = ["badge", tone !== "neutral" ? `badge-${tone}` : "", className].filter(Boolean).join(" ");
  return (
    <span className={classes} title={title}>
      {children}
    </span>
  );
}

export function DataQualityBadge({
  grade,
  score,
}: {
  grade: DataQualityGrade;
  score: number;
}) {
  const className = `badge badge-quality-${grade.toLowerCase()}`;
  return (
    <span className={className} title={`${qualityLabel(score)}：${score}`}>
      {qualityLabel(score)}
    </span>
  );
}

export function RiskBadge({
  riskLevel,
  prefix = "风险",
}: {
  riskLevel: RiskLevel;
  prefix?: string;
}) {
  const className = `badge badge-risk-${riskLevel.replace("_", "-")}`;
  return <span className={className}>{prefix}：{riskLabel(riskLevel)}</span>;
}

export function BetaBadge() {
  return <Badge tone="beta">Beta</Badge>;
}

export function TextBadge({ children }: { children: ReactNode }) {
  return <Badge>{children}</Badge>;
}
