import { ChevronDown } from "lucide-react";

import { formatCurrency, formatPercent } from "@/lib/format";
import type { AtomicParlayLeg, ParlayTicket } from "@/types/api";

export function ParlayExpansionTree({ ticket }: { ticket: ParlayTicket }) {
  return (
    <details className="parlay-expansion-tree" open={ticket.atomicBets.length <= 4}>
      <summary>
        <span>ParlayExpansionTree · {ticket.atomicBets.length || ticket.atomicBetCount} 注</span>
        <ChevronDown size={15} aria-hidden="true" />
      </summary>
      <ol className="parlay-atomic-list">
        {ticket.atomicBets.map((atomicBet, index) => (
          <li className="parlay-atomic-bet" key={`${ticket.recommendationId}-atomic-${index + 1}`}>
            <div className="parlay-atomic-head">
              <strong>Atomic {index + 1}</strong>
              <span>
                {formatPercent(atomicBet.probability)} · {formatCurrency(atomicBet.stake)}
              </span>
            </div>
            <div className="parlay-atomic-legs">
              {atomicBet.legs.map((leg) => (
                <span key={`${leg.fixtureId}-${leg.marketType}-${leg.outcome}`}>
                  {marketLabel(leg.marketType)} · {outcomeLabel(leg)}
                </span>
              ))}
            </div>
            <div className="parlay-atomic-metrics">
              <span>组合赔率 {atomicBet.oddsProduct.toFixed(2)}</span>
              <span>预期返还 {formatCurrency(atomicBet.expectedPayout)}</span>
              <span>EV {formatCurrency(atomicBet.expectedValue)}</span>
              <span>ROI {formatPercent(atomicBet.roi)}</span>
            </div>
          </li>
        ))}
      </ol>
    </details>
  );
}

function marketLabel(marketType: string) {
  const labels: Record<string, string> = {
    "1x2": "1X2",
    cn_handicap_1x2: "让球胜平负",
    asian_handicap: "亚洲让球",
    european_handicap_1x2: "欧洲三项让球",
    correct_score: "比分",
  };
  return labels[marketType] ?? marketType;
}

function outcomeLabel(leg: AtomicParlayLeg) {
  const labels: Record<string, string> = {
    home_win: "主胜",
    draw: "平局",
    away_win: "客胜",
    handicap_home_win: "让胜",
    handicap_draw: "让平",
    handicap_away_win: "让负",
    full_win: "全赢",
    half_win: "半赢",
    push: "走水",
    half_loss: "半输",
    full_loss: "全输",
  };
  const line = leg.line === null ? "" : ` ${leg.line > 0 ? "+" : ""}${leg.line}`;
  return `${labels[leg.outcome] ?? leg.outcome}${line}`;
}
