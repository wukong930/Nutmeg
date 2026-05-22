import { CalendarClock, Database, GitBranch, ShieldCheck, type LucideIcon } from "lucide-react";

import { formatDateTime } from "@/lib/format";
import type { AccuracySummary } from "@/types/api";

import "./accuracy.css";

export function EvaluationWindowDisplay({ summary }: { summary: AccuracySummary }) {
  return (
    <section className="accuracy-window-panel" aria-label="Evaluation window display">
      <WindowMetric
        icon={GitBranch}
        label="模型版本"
        value={summary.modelVersion}
        detail={`筛选：${summary.filters.modelVersion}`}
      />
      <WindowMetric
        icon={CalendarClock}
        label="评估窗口"
        value={summary.window}
        detail="Walk-forward / as-of-time 口径预留"
      />
      <WindowMetric
        icon={Database}
        label="赛后样本"
        value={`${summary.sampleSize}`}
        detail="不只展示命中率，优先看概率评分"
      />
      <WindowMetric
        icon={ShieldCheck}
        label="生成时间"
        value={formatDateTime(summary.generatedAtUtc)}
        detail={summary.stale ? "数据可能已过期" : "摘要已生成"}
      />
    </section>
  );
}

function WindowMetric({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="accuracy-window-metric">
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <p>{detail}</p>
      </div>
      <Icon size={18} aria-hidden="true" />
    </article>
  );
}
