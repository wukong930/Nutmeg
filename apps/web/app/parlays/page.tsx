import { ParlayBuilder } from "@/components/parlay/parlay-builder";
import { ParlayTicketCard } from "@/components/parlay/parlay-ticket-card";
import { ParlayWarningPanel } from "@/components/parlay/parlay-warning-panel";
import { FinalAnswerPanel } from "@/components/recommendation/final-answer-panel";
import {
  getMatches,
  getGlobalBestRecommendationBundle,
  getRecommendationLifecycleDetail,
} from "@/lib/api";
import { parlayOptionsFromParams } from "@/lib/recommendation-options";
import type { RecommendationLifecycleDetail } from "@/types/api";

type ParlaysPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ParlaysPage({ searchParams }: ParlaysPageProps) {
  const params = await searchParams;
  const options = parlayOptionsFromParams(params);
  const [matches, lifecycle] = await Promise.all([
    getMatches(),
    getRecommendationLifecycleDetail(options.recommendationRunId),
  ]);
  const engineBundle = await getGlobalBestRecommendationBundle(
    {
      ...options,
      lockedCandidates: lockedCandidatesFromLifecycle(lifecycle),
    },
    matches,
  );
  const { answer: engineAnswer, alternatives, answerSet, recommendation } = engineBundle;
  const tickets = recommendation.tickets;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">串关最佳答案</h1>
          <p className="page-copy">
            当前预算 {options.maxBudget ?? 20}，单位金额 {options.unitStake ?? 2}，
            {options.allowMultiple === false ? "只看单式" : "允许复式"}。金额字段仅用于成本与期望值计算，
            不构成投注建议。
          </p>
        </div>
      </header>

      <FinalAnswerPanel
        answer={engineAnswer}
        alternatives={alternatives}
        answerSet={answerSet}
        matches={matches}
        options={options}
        currentPath="/parlays"
        lifecycle={lifecycle}
      />

      <details className="section detail-disclosure">
        <summary>查看参数与备选方案</summary>
        <div className="detail-disclosure-body">
          <ParlayBuilder options={options} tickets={tickets} />
          <ParlayWarningPanel
            warnings={recommendation.warnings}
            stale={recommendation.stale}
            fallbackUsed={recommendation.fallbackUsed}
          />

          <section>
            <div className="section-header">
              <h2 className="section-title">备选方案</h2>
              <p className="meta">复式会增加注数和总金额；规则无效的组合只作为排除依据。</p>
            </div>
            {tickets.length > 0 ? (
              <div className="grid">
                {tickets.map((ticket) => (
                  <ParlayTicketCard key={ticket.recommendationId} ticket={ticket} />
                ))}
              </div>
            ) : (
              <div className="parlay-empty-state">
                <strong>暂无符合当前规则的候选组合</strong>
                <p>请查看候选池规则提示，或调整玩法范围、预算和 beta 赛事参数后重新评估。</p>
              </div>
            )}
          </section>
        </div>
      </details>
    </main>
  );
}

function lockedCandidatesFromLifecycle(lifecycle: RecommendationLifecycleDetail | null) {
  return (lifecycle?.lockedLegs ?? [])
    .filter((leg) => leg.status === "locked")
    .map((leg) => ({
      fixtureId: leg.fixtureId,
      marketType: leg.marketType,
      outcome: leg.outcome,
    }));
}
