import { MatchPredictionCard } from "@/components/match/match-card";
import { MatchListFilters } from "@/components/match/match-list-filters";
import { FinalAnswerPanel } from "@/components/recommendation/final-answer-panel";
import { UpsetCard } from "@/components/upset/upset-card";
import {
  getMatches,
  getGlobalBestRecommendationBundle,
  getRecommendationLifecycleDetail,
} from "@/lib/api";
import { parlayOptionsFromParams } from "@/lib/recommendation-options";
import type { RecommendationLifecycleDetail } from "@/types/api";

type DashboardPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function DashboardPage({ searchParams }: DashboardPageProps) {
  const params = await searchParams;
  const options = parlayOptionsFromParams(params);
  const [matches, lifecycle] = await Promise.all([
    getMatches(),
    getRecommendationLifecycleDetail(options.recommendationRunId),
  ]);
  const globalBundle = await getGlobalBestRecommendationBundle(
    {
      ...options,
      lockedCandidates: lockedCandidatesFromLifecycle(lifecycle),
    },
    matches,
  );
  const { answer: finalAnswer, alternatives, answerSet } = globalBundle;
  const upsets = matches.flatMap((match) => match.upsetAlerts).slice(0, 2);
  const competitions = Array.from(
    new Map(
      matches.map((match) => [
        match.competitionId,
        {
          competitionId: match.competitionId,
          competitionName: match.competitionName,
        },
      ]),
    ).values(),
  );
  const defaultDate = matches[0]?.kickoffTimeUtc.slice(0, 10) ?? "2026-05-09";

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">今日最佳答案</h1>
          <p className="page-copy">
            当前预算 {options.maxBudget ?? 20}，单位金额 {options.unitStake ?? 2}，
            {options.allowMultiple === false ? "只看单式" : "允许复式"}。
          </p>
        </div>
      </header>

      <FinalAnswerPanel
        answer={finalAnswer}
        alternatives={alternatives}
        answerSet={answerSet}
        matches={matches}
        options={options}
        currentPath="/dashboard"
        lifecycle={lifecycle}
      />

      <details className="section detail-disclosure">
        <summary>查看候选比赛与冷门摘要</summary>
        <div className="detail-disclosure-body">
          <section>
            <div className="section-header">
              <h2 className="section-title">候选比赛</h2>
              <p className="meta">用于复核模型版本、预测时间和数据质量。</p>
            </div>
            <MatchListFilters competitions={competitions} defaultDate={defaultDate} />
            <div className="grid">
              {matches.map((match) => (
                <MatchPredictionCard key={match.fixtureId} match={match} />
              ))}
            </div>
          </section>

          <section>
            <div className="section-header">
              <h2 className="section-title">冷门摘要</h2>
              <p className="meta">只保留可能影响最终答案的风险信号。</p>
            </div>
            <div className="grid grid-two">
              {upsets.map((alert) => (
                <UpsetCard key={`${alert.type}-${alert.targetOutcome}`} alert={alert} variant="compact" />
              ))}
            </div>
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
