import type { ParlayTicket } from "@/types/api";

export function MultiSelectionLegPreview({ tickets }: { tickets: ParlayTicket[] }) {
  const previewTickets = tickets.slice(0, 2);

  return (
    <div className="parlay-leg-selector" aria-label="Multi-selection leg UI">
      <div>
        <h2 className="section-title">多选腿预览</h2>
        <p className="meta">同一场多结果会展开为多个 atomic bet；总注额按注数乘以单注金额计算。</p>
      </div>
      <div className="parlay-leg-selector-grid">
        {previewTickets.map((ticket) => (
          <section className="parlay-leg-selector-ticket" key={ticket.recommendationId}>
            <div className="badge-row">
              <span className="badge">{ticket.passType}</span>
              <span className="badge">{ticket.isMultiple ? "复式" : "单式"}</span>
              <span className="badge mono">{ticket.atomicBetCount} 注</span>
            </div>
            {ticket.legs.map((leg) => (
              <fieldset className="parlay-leg-choice" key={`${ticket.recommendationId}-${leg.fixtureId}-${leg.market}`}>
                <legend>{leg.matchLabel}</legend>
                <p>{leg.market}</p>
                <div className="parlay-leg-choice-options">
                  {leg.outcomes.map((outcome) => (
                    <label key={outcome}>
                      <input
                        type="checkbox"
                        name="preview_selection"
                        value={`${ticket.recommendationId}:${leg.fixtureId}:${outcome}`}
                        defaultChecked
                      />
                      <span>{outcome}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
