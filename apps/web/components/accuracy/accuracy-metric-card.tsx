import { BarChart3, CircleDot, Hash, type LucideIcon } from "lucide-react";

import { formatPercent } from "@/lib/format";

import "./accuracy.css";

type MetricDisplay = "decimal" | "percent" | "integer";

const iconMap = {
  decimal: BarChart3,
  percent: CircleDot,
  integer: Hash,
} satisfies Record<MetricDisplay, LucideIcon>;

export function AccuracyMetricCard({
  label,
  value,
  display,
  detail,
}: {
  label: string;
  value: number | null;
  display: MetricDisplay;
  detail: string;
}) {
  const Icon = iconMap[display];

  return (
    <article className="accuracy-metric-card">
      <div className="accuracy-metric-head">
        <span>{label}</span>
        <Icon size={16} aria-hidden="true" />
      </div>
      <strong>{formatMetric(value, display)}</strong>
      <p>{detail}</p>
    </article>
  );
}

function formatMetric(value: number | null, display: MetricDisplay) {
  if (value === null) return "N/A";
  if (display === "percent") return formatPercent(value);
  if (display === "integer") return `${value}`;
  return value.toFixed(3);
}
