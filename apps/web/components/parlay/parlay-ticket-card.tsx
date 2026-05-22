import { CheckCircle2, CircleAlert } from "lucide-react";

import type { ParlayTicket } from "@/types/api";

import { ParlayEvaluationPanel } from "./parlay-evaluation-panel";
import { ParlayExpansionTree } from "./parlay-expansion-tree";

import "./parlay.css";

export function ParlayTicketCard({ ticket }: { ticket: ParlayTicket }) {
  return (
    <article className="parlay-card">
      <div className="parlay-head">
        <div>
          <div className="badge-row">
            <span className="badge">{ticket.passType}</span>
            <span className="badge">{ticket.isMultiple ? "复式" : "单式"}</span>
          </div>
          <h2>{ticketTitle(ticket)}</h2>
        </div>
        <span className={ticket.ruleValid ? "rule-valid" : "rule-invalid"}>
          {ticket.ruleValid ? (
            <CheckCircle2 size={16} aria-hidden="true" />
          ) : (
            <CircleAlert size={16} aria-hidden="true" />
          )}
          {ticket.ruleValid ? "规则有效" : "规则需调整"}
        </span>
      </div>

      <div className="parlay-leg-list">
        {ticket.legs.map((leg, index) => (
          <div key={`${leg.fixtureId}-${leg.market}-${index}`} className="parlay-leg">
            <span className="mono">{index + 1}</span>
            <div>
              <strong>{leg.matchLabel}</strong>
              <p>
                {leg.market}：{leg.outcomes.join(" / ")}
              </p>
            </div>
          </div>
        ))}
      </div>

      <ParlayEvaluationPanel ticket={ticket} />
      <ParlayExpansionTree ticket={ticket} />
      <ul className="parlay-reasons">
        {ticket.explanations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  );
}

function ticketTitle(ticket: ParlayTicket) {
  if (ticket.recommendationId.startsWith("engine_")) {
    return `${ticket.passType} 备选方案`;
  }
  return ticket.recommendationId;
}
