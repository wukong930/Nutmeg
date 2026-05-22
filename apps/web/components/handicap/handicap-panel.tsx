import { ProbabilityBar } from "@/components/probability/probability-bar";
import type { MatchPrediction } from "@/types/api";
import { HandicapResolverPanel } from "@/components/handicap/handicap-resolver-panel";

export function HandicapPanel({ match }: { match: MatchPrediction }) {
  return (
    <div className="grid grid-three">
      <section className="panel">
        <h3 className="section-title">中国竞彩让球</h3>
        <p className="meta">{match.cnHandicap.label}</p>
        <ProbabilityBar items={match.cnHandicap.items} showMarketComparison />
      </section>
      <section className="panel">
        <h3 className="section-title">亚洲让球</h3>
        <p className="meta">{match.asianHandicap.label}</p>
        <ProbabilityBar items={match.asianHandicap.items} />
      </section>
      <section className="panel">
        <h3 className="section-title">欧洲三项让球</h3>
        <p className="meta">{match.europeanHandicap.label}</p>
        <ProbabilityBar items={match.europeanHandicap.items} />
      </section>
    </div>
  );
}

export { HandicapResolverPanel };
