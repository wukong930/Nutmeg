import type { ReactNode } from "react";
import {
  CheckCircle2,
  Clock,
  Coins,
  Layers3,
  LockKeyhole,
  LockOpen,
  RefreshCw,
  ShieldAlert,
  Target,
} from "lucide-react";

import { releaseRecommendationLegAction, retainRecommendationLegAction } from "@/app/recommendations/actions";
import type { ParlayTicketRequestOptions } from "@/lib/api";
import { formatCurrency, formatDateTime, formatPercent, riskLabel } from "@/lib/format";
import type {
  MatchPrediction,
  RecommendationAnswerSet,
  RecommendationAnswerLeg,
  RecommendationEngineAnswer,
  RecommendationLifecycleDetail,
} from "@/types/api";

import "./recommendation.css";

type FinalAnswerPanelProps = {
  answer: RecommendationEngineAnswer | null;
  alternatives: RecommendationEngineAnswer[];
  answerSet?: RecommendationAnswerSet | null;
  matches: MatchPrediction[];
  options: ParlayTicketRequestOptions;
  currentPath: "/dashboard" | "/parlays";
  lifecycle?: RecommendationLifecycleDetail | null;
};

const passTypeOptions = [
  { value: "all", label: "自动选择" },
  { value: "1x1", label: "单式" },
  { value: "2x1", label: "2 串 1" },
  { value: "3x1", label: "3 串 1" },
  { value: "4x1", label: "4 串 1" },
  { value: "5x1", label: "5 串 1" },
  { value: "6x1", label: "6 串 1" },
  { value: "7x1", label: "7 串 1" },
  { value: "8x1", label: "8 串 1" },
] as const;

export function FinalAnswerPanel({
  answer,
  alternatives,
  answerSet,
  matches,
  options,
  currentPath,
  lifecycle,
}: FinalAnswerPanelProps) {
  const publicAlternatives = answerSet?.backupAnswers ?? alternatives;
  const lifecycleLegs = activeRetainedLifecycleLegs(lifecycle);
  const retainedLegByFixtureId = new Map(lifecycleLegs.map((leg) => [leg.fixtureId, leg]));
  const lockedFixtureIds = new Set([
    ...(options.lockedFixtureIds ?? []),
    ...lifecycleLegs.map((leg) => leg.fixtureId),
  ]);

  if (!answer) {
    return (
      <section className="final-answer final-answer-empty" aria-label="全局最佳推荐">
        <div className="final-answer-head">
          <span className="final-answer-icon">
            <ShieldAlert size={22} aria-hidden="true" />
          </span>
          <div>
            <p className="answer-kicker">当前答案</p>
            <h2>暂无预算内答案</h2>
            <p>当前候选池没有形成规则有效的推荐。</p>
          </div>
        </div>
        <details className="final-controls-disclosure">
          <summary>调整预算/关数</summary>
          <FinalAnswerControls options={options} />
        </details>
      </section>
    );
  }

  const selectedUpsets = selectedAnswerUpsets(answer, matches);
  const modelVersion = answerModelVersion(answer);
  const latestPredictionTime = latestAnswerPredictionTime(answer);
  const backupCount = answerSet?.summary.backupCount ?? publicAlternatives.length;

  return (
    <section className="final-answer" aria-label="全局最佳推荐">
      <div className="final-answer-head">
        <span className="final-answer-icon">
          <Target size={22} aria-hidden="true" />
        </span>
        <div>
          <p className="answer-kicker">当前答案</p>
          <h2>今日最佳答案</h2>
          <p className="final-answer-type">{answerTitle(answer)}</p>
        </div>
        <span className="final-answer-state">
          <CheckCircle2 size={16} aria-hidden="true" />
          {answer.budget?.withinBudget ? "预算内" : "需调整预算"}
        </span>
      </div>

      <div className="final-answer-body">
        <div className="final-answer-main">
          <div className="final-answer-summary">
            <Metric
              icon={<Coins size={16} aria-hidden="true" />}
              label="总金额"
              value={formatCurrency(answer.budget?.totalStake ?? 0)}
            />
            <Metric
              icon={<Target size={16} aria-hidden="true" />}
              label="命中概率"
              value={answer.hitProbability === null ? "待评估" : formatPercent(answer.hitProbability)}
            />
            <Metric
              icon={<Layers3 size={16} aria-hidden="true" />}
              label="结构"
              value={`${answer.passType ?? "答案"} · ${answer.isMultiple ? "复式" : "单式"}`}
            />
            <Metric
              icon={<ShieldAlert size={16} aria-hidden="true" />}
              label="风险"
              value={answer.riskLevel ? riskLabel(answer.riskLevel) : "待评估"}
            />
          </div>

          <div className="final-leg-list">
            {answer.legs.map((leg, index) => {
              const match = matches.find((item) => item.fixtureId === leg.fixtureId);
              const retainedLeg = retainedLegByFixtureId.get(leg.fixtureId);
              const locked = lockedFixtureIds.has(leg.fixtureId);
              return (
                <article
                  className={locked ? "final-leg final-leg-locked" : "final-leg"}
                  key={`${leg.fixtureId}-${leg.marketType}-${leg.outcomes.join("/")}-${index}`}
                >
                  <div>
                    <strong>{match ? matchLabel(match) : leg.fixtureId}</strong>
                    <span>
                      {marketTypeLabel(leg.marketType)}：{answerLegOutcomeLabel(leg)}
                    </span>
                  </div>
                  <div className="final-leg-meta">
                    <span>{formatPercent(leg.probability)}</span>
                    <span>{dataQualityGradeFromScore(leg.dataQualityScore)}</span>
                    {leg.kickoffTimeUtc ? <span>{formatDateTime(leg.kickoffTimeUtc)}</span> : null}
                  </div>
                  {locked ? (
                    <ReleaseLegControl
                      options={options}
                      currentPath={currentPath}
                      fixtureId={leg.fixtureId}
                      marketType={retainedLeg?.marketType ?? leg.marketType}
                      outcome={retainedLeg?.outcome ?? leg.outcomes[0]}
                    />
                  ) : (
                    <RetainLegControl
                      options={options}
                      currentPath={currentPath}
                      fixtureId={leg.fixtureId}
                      marketType={leg.marketType}
                      outcome={leg.outcomes[0]}
                    />
                  )}
                </article>
              );
            })}
          </div>
        </div>

        <aside className="final-answer-side">
          <div className="final-side-block">
            <span className="answer-label">更新时间</span>
            <strong>
              <Clock size={15} aria-hidden="true" />
              {formatDateTime(answer.generatedAtUtc)}
            </strong>
          </div>
          <div className="final-side-block">
            <span className="answer-label">模型版本</span>
            <strong>{modelVersion}</strong>
            {latestPredictionTime ? <p>预测 {formatDateTime(latestPredictionTime)}</p> : null}
          </div>
          <div className="final-side-block">
            <span className="answer-label">数据质量</span>
            <strong>{answer.dataQualityGrade ?? "待评估"}</strong>
          </div>
          {lockedFixtureIds.size > 0 ? (
            <div className="final-side-block">
              <span className="answer-label">已保留</span>
              <strong>{lockedFixtureIds.size} 场</strong>
            </div>
          ) : null}
          <div className="final-side-block">
            <span className="answer-label">冷门提醒</span>
            {selectedUpsets.length > 0 ? (
              <div className="final-upset-list">
                {selectedUpsets.map((item) => (
                  <span key={`${item.fixtureId}-${item.type}-${item.targetOutcome}`}>
                    {item.label} · {riskLabel(item.riskLevel)}
                  </span>
                ))}
              </div>
            ) : (
              <p>所选比赛暂无高优先级冷门提醒。</p>
            )}
          </div>
          {answer.warnings.length > 0 ? (
            <div className="final-side-block final-side-warning">
              <span className="answer-label">提示</span>
              <p>{answer.warnings[0]}</p>
            </div>
          ) : null}
          <details className="final-controls-disclosure">
            <summary>调整预算/关数</summary>
            <FinalAnswerControls options={options} compact />
          </details>
        </aside>
      </div>

      {publicAlternatives.length > 0 ? (
        <div className="final-alternatives">
          <span className="answer-label">必要备选 {backupCount}</span>
          <div>
            {publicAlternatives.slice(0, 2).map((item) => (
              <span key={`${item.passType}-${item.mode}-${item.atomicBetCount}`}>
                {item.passType} · {item.isMultiple ? "复式" : "单式"} ·{" "}
                {formatCurrency(item.budget?.totalStake ?? 0)}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <span className="final-metric">
      {icon}
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}

function FinalAnswerControls({
  options,
  compact = false,
}: {
  options: ParlayTicketRequestOptions;
  compact?: boolean;
}) {
  return (
    <form className={compact ? "final-controls final-controls-compact" : "final-controls"}>
      {(options.allowedMarkets ?? []).map((market) => (
        <input key={market} type="hidden" name="allowed_market" value={market} />
      ))}
      {(options.lockedFixtureIds ?? []).map((fixtureId) => (
        <input key={fixtureId} type="hidden" name="locked_fixture" value={fixtureId} />
      ))}
      {options.recommendationRunId ? (
        <input type="hidden" name="recommendation_run_id" value={options.recommendationRunId} />
      ) : null}
      {options.retentionSource ? (
        <input type="hidden" name="retention_source" value={options.retentionSource} />
      ) : null}
      <label>
        <span>类型</span>
        <select name="pass_type" defaultValue={options.passType ?? "all"}>
          {passTypeOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>预算</span>
        <input name="max_budget" type="number" min={1} step={1} defaultValue={options.maxBudget ?? 20} />
      </label>
      <label>
        <span>单位金额</span>
        <input name="unit_stake" type="number" min={1} step={1} defaultValue={options.unitStake ?? 2} />
      </label>
      <label>
        <span>结构</span>
        <select name="allow_multiple" defaultValue={options.allowMultiple === false ? "false" : "true"}>
          <option value="true">允许复式</option>
          <option value="false">只看单式</option>
        </select>
      </label>
      <button className="toolbar-button" type="submit">
        <RefreshCw size={15} aria-hidden="true" />
        刷新答案
      </button>
    </form>
  );
}

function RetainLegControl({
  options,
  currentPath,
  fixtureId,
  marketType,
  outcome,
}: {
  options: ParlayTicketRequestOptions;
  currentPath: "/dashboard" | "/parlays";
  fixtureId: string;
  marketType: string;
  outcome: string;
}) {
  return (
    <form action={retainRecommendationLegAction} className="answer-retain-form">
      <input type="hidden" name="current_path" value={currentPath} />
      <input type="hidden" name="fixture_id" value={fixtureId} />
      <input type="hidden" name="market_type" value={marketType} />
      <input type="hidden" name="outcome" value={outcome} />
      <HiddenRecommendationInputs options={options} />
      <button type="submit" className="answer-lock-link">
        <LockKeyhole size={14} aria-hidden="true" />
        保留
      </button>
    </form>
  );
}

function ReleaseLegControl({
  options,
  currentPath,
  fixtureId,
  marketType,
  outcome,
}: {
  options: ParlayTicketRequestOptions;
  currentPath: "/dashboard" | "/parlays";
  fixtureId: string;
  marketType: string;
  outcome: string;
}) {
  if (!options.recommendationRunId) {
    return (
      <a href={toggleLockedFixtureHref(options, fixtureId)} className="answer-lock-link is-locked">
        <LockOpen size={14} aria-hidden="true" />
        取消
      </a>
    );
  }
  return (
    <form action={releaseRecommendationLegAction} className="answer-retain-form">
      <input type="hidden" name="current_path" value={currentPath} />
      <input type="hidden" name="fixture_id" value={fixtureId} />
      <input type="hidden" name="market_type" value={marketType} />
      <input type="hidden" name="outcome" value={outcome} />
      <HiddenRecommendationInputs options={options} />
      <button type="submit" className="answer-lock-link is-locked">
        <LockOpen size={14} aria-hidden="true" />
        取消
      </button>
    </form>
  );
}

function HiddenRecommendationInputs({ options }: { options: ParlayTicketRequestOptions }) {
  return (
    <>
      <input type="hidden" name="pass_type" value={options.passType ?? "all"} />
      <input type="hidden" name="unit_stake" value={options.unitStake ?? 2} />
      <input type="hidden" name="max_budget" value={options.maxBudget ?? 20} />
      <input type="hidden" name="allow_multiple" value={String(options.allowMultiple !== false)} />
      {(options.allowedMarkets ?? []).map((market) => (
        <input key={market} type="hidden" name="allowed_market" value={market} />
      ))}
      {(options.lockedFixtureIds ?? []).map((fixtureId) => (
        <input key={fixtureId} type="hidden" name="locked_fixture" value={fixtureId} />
      ))}
      {options.recommendationRunId ? (
        <input type="hidden" name="recommendation_run_id" value={options.recommendationRunId} />
      ) : null}
      {options.retentionSource ? (
        <input type="hidden" name="retention_source" value={options.retentionSource} />
      ) : null}
    </>
  );
}

function answerTitle(answer: RecommendationEngineAnswer) {
  if (answer.passType === "1x1") {
    return "单式";
  }
  return `${formatPassType(answer.passType)} · ${answer.isMultiple ? "复式" : "单式"}`;
}

function formatPassType(passType: string | null) {
  if (!passType) {
    return "串关";
  }
  return passType.replace("x", " 串 ");
}

function matchLabel(match: MatchPrediction) {
  return `${match.homeTeam.name} vs ${match.awayTeam.name}`;
}

function answerLegOutcomeLabel(leg: RecommendationAnswerLeg) {
  return leg.outcomes.map(outcomeLabel).join(" / ");
}

function outcomeLabel(outcome: string) {
  const labels: Record<string, string> = {
    home_win: "主胜",
    draw: "平",
    away_win: "客胜",
    handicap_home_win: "让胜",
    handicap_draw: "让平",
    handicap_away_win: "让负",
  };
  return labels[outcome] ?? outcome;
}

function marketTypeLabel(marketType: string) {
  const labels: Record<string, string> = {
    "1x2": "胜平负",
    cn_handicap_1x2: "中国让球",
    european_handicap_1x2: "欧洲让球",
    correct_score: "比分",
  };
  return labels[marketType] ?? marketType;
}

function dataQualityGradeFromScore(score: number) {
  if (score >= 85) return "A";
  if (score >= 70) return "B";
  if (score >= 55) return "C";
  return "D";
}

function activeRetainedLifecycleLegs(
  lifecycle: RecommendationLifecycleDetail | null | undefined,
) {
  return (lifecycle?.lockedLegs ?? []).filter((leg) => leg.status === "locked");
}

function selectedAnswerUpsets(answer: RecommendationEngineAnswer, matches: MatchPrediction[]) {
  const answerFixtureIds = new Set(answer.legs.map((leg) => leg.fixtureId));
  return matches
    .filter((match) => answerFixtureIds.has(match.fixtureId))
    .flatMap((match) =>
      match.upsetAlerts.map((alert) => ({
        ...alert,
        fixtureId: match.fixtureId,
      })),
    )
    .slice(0, 2);
}

function answerModelVersion(answer: RecommendationEngineAnswer) {
  const versions = Array.from(
    new Set(answer.legs.map((leg) => leg.modelVersion).filter(Boolean)),
  );
  if (versions.length === 0) {
    return "待评估";
  }
  if (versions.length === 1) {
    return versions[0];
  }
  return `${versions[0]} +${versions.length - 1}`;
}

function latestAnswerPredictionTime(answer: RecommendationEngineAnswer) {
  const times = answer.legs
    .map((leg) => leg.predictionTimeUtc)
    .filter((value): value is string => Boolean(value))
    .sort();
  return times.at(-1) ?? null;
}

function toggleLockedFixtureHref(options: ParlayTicketRequestOptions, fixtureId: string) {
  const params = new URLSearchParams();
  params.set("pass_type", options.passType ?? "all");
  params.set("unit_stake", String(options.unitStake ?? 2));
  params.set("max_budget", String(options.maxBudget ?? 20));
  params.set("allow_multiple", String(options.allowMultiple !== false));
  for (const market of options.allowedMarkets ?? []) {
    params.append("allowed_market", market);
  }
  for (const currentFixtureId of options.lockedFixtureIds ?? []) {
    if (currentFixtureId !== fixtureId) {
      params.append("locked_fixture", currentFixtureId);
    }
  }
  if (options.recommendationRunId) {
    params.set("recommendation_run_id", String(options.recommendationRunId));
  }
  if (options.retentionSource) {
    params.set("retention_source", options.retentionSource);
  }
  return `?${params.toString()}`;
}
