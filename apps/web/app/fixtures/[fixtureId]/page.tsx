import { notFound } from "next/navigation";

import { HandicapResolverPanel } from "@/components/handicap/handicap-resolver-panel";
import { DataFreshnessPanel } from "@/components/match/data-freshness-panel";
import { MatchHeader } from "@/components/match/match-header";
import { MarketGapChart } from "@/components/market/market-gap-chart";
import { MarketMovementTimeline } from "@/components/market/market-movement-timeline";
import { ModelFingerprint } from "@/components/model/model-fingerprint";
import { PredictionTrace } from "@/components/prediction/prediction-trace";
import { ProbabilityTriptych } from "@/components/probability/probability-triptych";
import { ScoreGridHeatmap } from "@/components/score/score-grid-heatmap";
import { TopScoresPanel } from "@/components/score/score-top-list";
import { UpsetCard } from "@/components/upset/upset-card";
import { getMatch, getMatches } from "@/lib/api";

type PageProps = {
  params: Promise<{ fixtureId: string }>;
};

export async function generateStaticParams() {
  const matches = await getMatches();
  return matches.map((match) => ({ fixtureId: match.fixtureId }));
}

export default async function FixtureDetailPage({ params }: PageProps) {
  const { fixtureId } = await params;
  const match = await getMatch(fixtureId);

  if (!match) {
    notFound();
  }

  return (
    <main className="page">
      <MatchHeader match={match} />

      <div className="fixture-detail-grid">
        <div className="fixture-main-column">
          <section>
            <div className="section-header">
              <h2 className="section-title">1X2 胜平负概率</h2>
              <p className="meta">显示模型概率、市场概率、百分点差值、模型版本和预测时间。</p>
            </div>
            <ProbabilityTriptych
              items={match.oneXTwo}
              modelVersion={match.modelVersion}
              predictionTimeUtc={match.predictionTimeUtc}
            />
          </section>

          <MarketGapChart title="1X2 市场分歧" label="胜平负去水概率对比" items={match.oneXTwo} />

          <section>
            <div className="section-header">
              <h2 className="section-title">让球玩法</h2>
              <p className="meta">中国竞彩让球、亚洲让球、欧洲三项让球分开展示。</p>
            </div>
            <HandicapResolverPanel match={match} />
          </section>

          <section>
            <TopScoresPanel match={match} />
          </section>

          <ScoreGridHeatmap match={match} />

          <section>
            <div className="section-header">
              <h2 className="section-title">冷门分析</h2>
              <p className="meta">冷门提示是风险雷达，不是确定性结论。</p>
            </div>
            <div className="grid grid-two">
              {match.upsetAlerts.map((alert) => (
                <UpsetCard key={alert.type} alert={alert} />
              ))}
            </div>
          </section>
        </div>

        <div className="fixture-side-column">
          <DataFreshnessPanel freshness={match.dataFreshness} />
          <PredictionTrace match={match} />
          <ModelFingerprint match={match} />
          <MarketMovementTimeline match={match} />
          <section className="panel">
            <div className="section-header">
              <h2 className="section-title">关键因素</h2>
              <p className="meta">模型贡献估计</p>
            </div>
            <div className="grid">
              <FactorPanel title="模型因素" items={match.keyFactors.model} />
              <FactorPanel title="市场因素" items={match.keyFactors.market} />
              <FactorPanel title="阵容因素" items={match.keyFactors.lineup} />
              <FactorPanel title="赛程因素" items={match.keyFactors.schedule} />
              <FactorPanel title="不确定因素" items={match.keyFactors.uncertainty} />
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}

function FactorPanel({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="key-factor-panel">
      <h3 className="section-title">{title}</h3>
      <ul className="upset-reasons">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
