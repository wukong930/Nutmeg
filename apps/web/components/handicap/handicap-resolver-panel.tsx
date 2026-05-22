import { MarketGapChart } from "@/components/market/market-gap-chart";
import { ProbabilityBar } from "@/components/probability/probability-bar";
import type { MatchPrediction, MarketProbabilitySet } from "@/types/api";

export function HandicapResolverPanel({ match }: { match: MatchPrediction }) {
  return (
    <div className="grid grid-three">
      <HandicapMarketCard title="中国竞彩让球" market={match.cnHandicap} showMarketGap />
      <HandicapMarketCard title="亚洲让球" market={match.asianHandicap} />
      <HandicapMarketCard title="欧洲三项让球" market={match.europeanHandicap} />
    </div>
  );
}

function HandicapMarketCard({
  title,
  market,
  showMarketGap = false,
}: {
  title: string;
  market: MarketProbabilitySet;
  showMarketGap?: boolean;
}) {
  return (
    <section className="panel">
      <h3 className="section-title">{title}</h3>
      <p className="meta">{market.label}</p>
      <ProbabilityBar items={market.items} showMarketComparison={showMarketGap} />
      {showMarketGap ? (
        <div className="handicap-market-gap">
          <MarketGapChart title={`${title}市场分歧`} label={market.label} items={market.items} />
        </div>
      ) : null}
    </section>
  );
}
