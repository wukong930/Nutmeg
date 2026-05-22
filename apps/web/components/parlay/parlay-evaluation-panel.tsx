import { CircleAlert, Gauge } from "lucide-react";

import { formatCurrency, formatPercent, riskLabel } from "@/lib/format";
import type { ParlayTicket } from "@/types/api";

export function ParlayEvaluationPanel({ ticket }: { ticket: ParlayTicket }) {
  return (
    <section className="parlay-evaluation-panel" aria-label="ParlayEvaluationPanel">
      <div className="parlay-evaluation-head">
        <div>
          <h3 className="section-title">组合评估</h3>
          <p className="meta">独立近似 + 规则型相关性惩罚</p>
        </div>
        <span className={`parlay-risk-pill risk-${ticket.riskLevel}`}>
          <Gauge size={15} aria-hidden="true" />
          {riskLabel(ticket.riskLevel)}
        </span>
      </div>

      <div className="parlay-metrics">
        <Metric label="注数" value={`${ticket.atomicBetCount}`} />
        <Metric label="单注" value={formatCurrency(ticket.unitStake)} />
        <Metric label="总金额" value={formatCurrency(ticket.totalStake)} />
        <Metric label="命中概率" value={formatPercent(ticket.hitProbability)} />
        <Metric label="预期返还" value={formatCurrency(ticket.expectedPayout)} />
        <Metric label="EV" value={formatCurrency(ticket.ev)} />
        <Metric label="ROI" value={formatPercent(ticket.roi)} />
        <Metric label="风险评分" value={`${Math.round(ticket.riskScore * 100)}/100`} />
        <Metric label="相关性惩罚" value={formatPercent(ticket.correlationPenalty)} />
      </div>

      <div className="parlay-warning">
        <CircleAlert size={15} aria-hidden="true" />
        <span>串关会放大波动。组合命中概率通常显著低于单场概率。</span>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
