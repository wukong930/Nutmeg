import Link from "next/link";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Coins,
  History,
  Layers3,
  LockKeyhole,
  LockOpen,
  ShieldAlert,
  SlidersHorizontal,
  Target,
} from "lucide-react";

import { releaseRecommendationLegAction, retainRecommendationLegAction } from "@/app/recommendations/actions";
import type { ParlayTicketRequestOptions } from "@/lib/api";
import { formatCurrency, formatDateTime, formatPercent, riskLabel } from "@/lib/format";
import type {
  MatchPrediction,
  ParlayRecommendation,
  ParlayTicket,
  RecommendationAnswerLeg,
  RecommendationEngineAnswer,
  RecommendationLifecycleDetail,
  RecommendationLockedLeg,
} from "@/types/api";

import "./recommendation.css";

type RecommendationAnswerBoardProps = {
  matches: MatchPrediction[];
  recommendation: ParlayRecommendation;
  options: ParlayTicketRequestOptions;
  currentPath: "/dashboard" | "/parlays";
  lifecycle?: RecommendationLifecycleDetail | null;
  engineAnswer?: RecommendationEngineAnswer | null;
  engineSingleAnswer?: RecommendationEngineAnswer | null;
  engineUpsetAnswer?: RecommendationEngineAnswer | null;
};

const passTypeOptions = [
  { value: "all", label: "2串1-8串1" },
  { value: "2x1", label: "2串1" },
  { value: "3x1", label: "3串1" },
  { value: "4x1", label: "4串1" },
  { value: "5x1", label: "5串1" },
  { value: "6x1", label: "6串1" },
  { value: "7x1", label: "7串1" },
  { value: "8x1", label: "8串1" },
] as const;

const marketOptions = [
  { value: "1x2", label: "胜平负" },
  { value: "cn_handicap_1x2", label: "中国让球" },
  { value: "european_handicap_1x2", label: "欧洲让球" },
  { value: "correct_score", label: "比分" },
  { value: "asian_handicap", label: "亚洲让球" },
] as const;

export function RecommendationAnswerBoard({
  matches,
  recommendation,
  options,
  currentPath,
  lifecycle,
  engineAnswer,
  engineSingleAnswer,
  engineUpsetAnswer,
}: RecommendationAnswerBoardProps) {
  const maxBudget = options.maxBudget ?? 20;
  const coreAnswer = engineAnswer?.status === "ready" ? engineAnswer : null;
  const singleAnswer = engineSingleAnswer?.status === "ready" ? engineSingleAnswer : null;
  const upsetAnswer = engineUpsetAnswer?.status === "ready" ? engineUpsetAnswer : null;
  const activeLifecycleLegs = activeRetainedLifecycleLegs(lifecycle);
  const retainedLegByFixtureId = new Map(activeLifecycleLegs.map((leg) => [leg.fixtureId, leg]));
  const lockedFixtureIds = new Set([
    ...(options.lockedFixtureIds ?? []),
    ...activeLifecycleLegs.map((leg) => leg.fixtureId),
  ]);
  const lockedItems = lockedFixtureSummaries(
    matches,
    recommendation.tickets,
    lockedFixtureIds,
    retainedLegByFixtureId,
  );
  const bestTicket = selectBestTicket(recommendation.tickets, maxBudget, "any", lockedFixtureIds);
  const protectionTicket = selectBestTicket(recommendation.tickets, maxBudget, "multiple", lockedFixtureIds);
  const warningCount =
    recommendation.warnings.length +
    (recommendation.stale ? 1 : 0) +
    (recommendation.fallbackUsed ? 1 : 0) +
    (engineAnswer?.warnings.length ?? 0) +
    (engineAnswer?.stale ? 1 : 0) +
    (engineAnswer?.fallbackUsed ? 1 : 0) +
    (engineSingleAnswer?.warnings.length ?? 0) +
    (engineUpsetAnswer?.warnings.length ?? 0);

  return (
    <section className="answer-board" aria-label="今日推荐答案">
      <div className="answer-board-head">
        <div>
          <p className="answer-kicker">Recommendation Engine</p>
          <h2>今日最佳答案</h2>
          <p>
            默认只展示决策需要的信息：单式首选、预算内串关、复式保护、冷门信号与开赛前状态。
          </p>
        </div>
        <span className={warningCount > 0 ? "answer-status answer-status-warning" : "answer-status"}>
          {warningCount > 0 ? <AlertTriangle size={16} aria-hidden="true" /> : <CheckCircle2 size={16} aria-hidden="true" />}
          {warningCount > 0 ? `${warningCount} 条数据提示` : "候选池可用"}
        </span>
      </div>

      <div className="answer-grid">
        <EngineFocusAnswerCard
          title="单式首选"
          emptyTitle="暂无有效单式"
          emptyCopy="候选池暂未形成足够清晰的单式答案。"
          icon={<Target size={18} aria-hidden="true" />}
          answer={singleAnswer}
          matches={matches}
          options={options}
          lockedFixtureIds={lockedFixtureIds}
          retainedLegByFixtureId={retainedLegByFixtureId}
          currentPath={currentPath}
          primary
        />

        {coreAnswer ? (
          <EngineAnswerCard
            answer={coreAnswer}
            matches={matches}
            options={options}
            lockedFixtureIds={lockedFixtureIds}
            retainedLegByFixtureId={retainedLegByFixtureId}
            currentPath={currentPath}
          />
        ) : (
          <TicketAnswerCard
            title="预算内串关"
            label="预算内串关"
            icon={<Layers3 size={18} aria-hidden="true" />}
            ticket={bestTicket}
            options={options}
            lockedFixtureIds={lockedFixtureIds}
            retainedLegByFixtureId={retainedLegByFixtureId}
            currentPath={currentPath}
            emptyCopy="当前预算与玩法范围内暂无规则有效串关。"
          />
        )}

        <TicketAnswerCard
          title="复式保护"
          label="预算约束"
          icon={<ShieldAlert size={18} aria-hidden="true" />}
          ticket={protectionTicket}
          options={options}
          lockedFixtureIds={lockedFixtureIds}
          retainedLegByFixtureId={retainedLegByFixtureId}
          currentPath={currentPath}
          emptyCopy="当前预算内没有形成规则有效复式，建议先保留单式或降低过关场次。"
        />

        <EngineFocusAnswerCard
          title="冷门保护"
          emptyTitle="暂无高优先级信号"
          emptyCopy="候选池没有触发需要优先保护的冷门信号。"
          icon={<ShieldAlert size={18} aria-hidden="true" />}
          answer={upsetAnswer}
          matches={matches}
          options={options}
          lockedFixtureIds={lockedFixtureIds}
          retainedLegByFixtureId={retainedLegByFixtureId}
          currentPath={currentPath}
          warning
        />

        <article className="answer-card">
          <div className="answer-card-head">
            <span className="answer-icon answer-icon-muted">
              <LockKeyhole size={18} aria-hidden="true" />
            </span>
            <div>
              <span className="answer-label">赛前保留</span>
              <h3>{lockedItems.length > 0 ? `已保留 ${lockedItems.length} 场` : "未保留"}</h3>
            </div>
          </div>
          {lockedItems.length > 0 ? (
            <div className="answer-lock-list">
              {lockedItems.map((item) => (
                <div key={item.fixtureId} className="answer-lock-item">
                  <span>{item.label}</span>
                  <ReleaseOrFallback
                    options={options}
                    currentPath={currentPath}
                    fixtureId={item.fixtureId}
                    marketType={item.marketType}
                    outcome={item.outcome}
                    label="取消"
                  />
                </div>
              ))}
            </div>
          ) : (
            <p className="answer-note">
              开赛前推荐会随新赔率、阵容、伤停和数据质量变化重新计算；用户确认后应进入保留态并从后续场次继续优化。
            </p>
          )}
          <div className="answer-meta-row">
            <span>已保留 {lockedItems.length} 场</span>
            <span>剩余候选 {Math.max(matches.length - lockedItems.length, 0)} 场</span>
            <span>来源：{lifecycleSourceLabel(lifecycle, options.retentionSource)}</span>
          </div>
          {lifecycle?.events.length ? <LifecycleTimeline lifecycle={lifecycle} /> : null}
        </article>
      </div>

      <RecommendationControls options={options} />

      {warningCount > 0 ? (
        <div className="answer-warnings" role="status">
          <strong>候选池提示</strong>
          <ul>
            {recommendation.stale ? <li>推荐数据存在过期风险，需要在开赛前重新计算。</li> : null}
            {recommendation.fallbackUsed ? <li>当前使用本地兜底数据，真实数据接入后需要重新评估。</li> : null}
            {engineAnswer?.stale ? <li>核心推荐数据存在过期风险，需要在开赛前重新计算。</li> : null}
            {engineAnswer?.fallbackUsed ? <li>核心推荐接口暂不可用，当前使用页面兜底候选。</li> : null}
            {engineAnswer?.warnings.map((warning) => (
              <li key={`engine-${warning}`}>{warning}</li>
            ))}
            {engineSingleAnswer?.warnings.map((warning) => (
              <li key={`engine-single-${warning}`}>{warning}</li>
            ))}
            {engineUpsetAnswer?.warnings.map((warning) => (
              <li key={`engine-upset-${warning}`}>{warning}</li>
            ))}
            {recommendation.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function EngineFocusAnswerCard({
  title,
  emptyTitle,
  emptyCopy,
  icon,
  answer,
  matches,
  options,
  lockedFixtureIds,
  retainedLegByFixtureId,
  currentPath,
  primary = false,
  warning = false,
}: {
  title: string;
  emptyTitle: string;
  emptyCopy: string;
  icon: ReactNode;
  answer: RecommendationEngineAnswer | null;
  matches: MatchPrediction[];
  options: ParlayTicketRequestOptions;
  lockedFixtureIds: Set<string>;
  retainedLegByFixtureId: Map<string, RecommendationLockedLeg>;
  currentPath: "/dashboard" | "/parlays";
  primary?: boolean;
  warning?: boolean;
}) {
  const leg = answer?.legs[0] ?? null;
  const match = leg ? matches.find((item) => item.fixtureId === leg.fixtureId) : undefined;
  const retainedLeg = leg ? retainedLegByFixtureId.get(leg.fixtureId) : undefined;

  return (
    <article className={primary ? "answer-card answer-card-primary" : "answer-card"}>
      <div className="answer-card-head">
        <span className={warning ? "answer-icon answer-icon-warning" : "answer-icon"}>{icon}</span>
        <div>
          <span className="answer-label">{title}</span>
          <h3>{leg ? answerLegOutcomeLabel(leg) : emptyTitle}</h3>
        </div>
      </div>
      {answer && leg ? (
        <>
          <p className="answer-match">{match ? matchLabel(match) : leg.fixtureId}</p>
          <div className="answer-metrics">
            <span>
              <strong>{formatPercent(leg.probability)}</strong>
              <small>模型概率</small>
            </span>
            <span>
              <strong>{marketTypeLabel(leg.marketType)}</strong>
              <small>玩法</small>
            </span>
            <span>
              <strong>{answer.dataQualityGrade ?? dataQualityGradeFromScore(leg.dataQualityScore)}</strong>
              <small>数据质量</small>
            </span>
          </div>
          <div className="answer-meta-row">
            {leg.kickoffTimeUtc ? (
              <span>
                <Clock size={14} aria-hidden="true" />
                {formatDateTime(leg.kickoffTimeUtc)}
              </span>
            ) : null}
            {leg.modelVersion ? <span>{leg.modelVersion}</span> : null}
            {leg.predictionTimeUtc ? <span>预测 {formatDateTime(leg.predictionTimeUtc)}</span> : null}
            {answer.riskLevel ? <span>{riskLabel(answer.riskLevel)}</span> : null}
          </div>
          <Link href={`/fixtures/${leg.fixtureId}`} className="answer-link">
            查看比赛
          </Link>
          {lockedFixtureIds.has(leg.fixtureId) ? (
            <ReleaseOrFallback
              options={options}
              currentPath={currentPath}
              fixtureId={leg.fixtureId}
              marketType={retainedLeg?.marketType ?? leg.marketType}
              outcome={retainedLeg?.outcome ?? leg.outcomes.join(" / ")}
              label="取消保留"
            />
          ) : (
            <RetainLegForm
              options={options}
              currentPath={currentPath}
              fixtureId={leg.fixtureId}
              marketType={leg.marketType}
              outcome={leg.outcomes.join(" / ")}
              label={primary ? "保留单式" : "保留"}
            />
          )}
        </>
      ) : (
        <EmptyAnswer copy={emptyCopy} />
      )}
    </article>
  );
}

function EngineAnswerCard({
  answer,
  matches,
  options,
  lockedFixtureIds,
  retainedLegByFixtureId,
  currentPath,
}: {
  answer: RecommendationEngineAnswer;
  matches: MatchPrediction[];
  options: ParlayTicketRequestOptions;
  lockedFixtureIds: Set<string>;
  retainedLegByFixtureId: Map<string, RecommendationLockedLeg>;
  currentPath: "/dashboard" | "/parlays";
}) {
  return (
    <article className="answer-card">
      <div className="answer-card-head">
        <span className="answer-icon">
          <Layers3 size={18} aria-hidden="true" />
        </span>
        <div>
          <span className="answer-label">预算内最终答案</span>
          <h3>
            {answer.passType ?? "串关"} · {answer.isMultiple ? "复式" : "单式"}
          </h3>
        </div>
      </div>

      <div className="answer-leg-list">
        {answer.legs.slice(0, 4).map((leg, index) => {
          const retainedLeg = retainedLegByFixtureId.get(leg.fixtureId);
          const match = matches.find((item) => item.fixtureId === leg.fixtureId);
          return (
            <div
              key={`${leg.fixtureId}-${leg.marketType}-${leg.outcomes.join("/")}-${index}`}
              className="answer-leg"
            >
              <strong>{match ? matchLabel(match) : leg.fixtureId}</strong>
              <span>
                {marketTypeLabel(leg.marketType)}：{answerLegOutcomeLabel(leg)}
              </span>
              {lockedFixtureIds.has(leg.fixtureId) ? (
                <ReleaseOrFallback
                  options={options}
                  currentPath={currentPath}
                  fixtureId={leg.fixtureId}
                  marketType={retainedLeg?.marketType ?? leg.marketType}
                  outcome={retainedLeg?.outcome ?? leg.outcomes.join(" / ")}
                  label="取消"
                />
              ) : (
                <RetainLegForm
                  options={options}
                  currentPath={currentPath}
                  fixtureId={leg.fixtureId}
                  marketType={leg.marketType}
                  outcome={leg.outcomes.join(" / ")}
                  label="保留"
                />
              )}
            </div>
          );
        })}
        {answer.legs.length > 4 ? <span className="answer-more">另有 {answer.legs.length - 4} 场</span> : null}
      </div>

      <div className="answer-metrics">
        <span>
          <strong>{formatCurrency(answer.budget?.totalStake ?? 0)}</strong>
          <small>总金额</small>
        </span>
        <span>
          <strong>{answer.hitProbability === null ? "待评估" : formatPercent(answer.hitProbability)}</strong>
          <small>命中概率</small>
        </span>
        <span>
          <strong>{answer.roi === null ? "待评估" : formatPercent(answer.roi)}</strong>
          <small>ROI</small>
        </span>
      </div>
      <div className="answer-meta-row">
        <span>{answer.atomicBetCount} 注</span>
        <span>{answer.dataQualityGrade ? `数据质量 ${answer.dataQualityGrade}` : "数据质量待评估"}</span>
        <span>{answer.riskLevel ? riskLabel(answer.riskLevel) : "风险待评估"}</span>
      </div>
      <p className="answer-note">
        更新时间 {formatDateTime(answer.generatedAtUtc)}；该答案来自当前候选池的预算约束计算。
      </p>
    </article>
  );
}

function TicketAnswerCard({
  title,
  label,
  icon,
  ticket,
  options,
  lockedFixtureIds,
  retainedLegByFixtureId,
  currentPath,
  emptyCopy,
}: {
  title: string;
  label: string;
  icon: ReactNode;
  ticket: ParlayTicket | null;
  options: ParlayTicketRequestOptions;
  lockedFixtureIds: Set<string>;
  retainedLegByFixtureId: Map<string, RecommendationLockedLeg>;
  currentPath: "/dashboard" | "/parlays";
  emptyCopy: string;
}) {
  return (
    <article className="answer-card">
      <div className="answer-card-head">
        <span className="answer-icon">{icon}</span>
        <div>
          <span className="answer-label">{label}</span>
          <h3>{ticket ? `${ticket.passType} · ${ticket.isMultiple ? "复式" : "单式"}` : title}</h3>
        </div>
      </div>
      {ticket ? (
        <>
          <div className="answer-leg-list">
            {ticket.legs.slice(0, 4).map((leg, index) => (
              <div
                key={`${ticket.recommendationId}-${leg.fixtureId}-${leg.market}-${leg.outcomes.join("/")}`}
                className="answer-leg"
              >
                <strong>{leg.matchLabel}</strong>
                <span>
                  {leg.market}：{leg.outcomes.join(" / ")}
                </span>
                {lockedFixtureIds.has(leg.fixtureId) ? (
                  <ReleaseOrFallback
                    options={options}
                    currentPath={currentPath}
                    fixtureId={leg.fixtureId}
                    marketType={retainedLegByFixtureId.get(leg.fixtureId)?.marketType ?? marketTypeFromTicketLeg(leg.market)}
                    outcome={retainedLegByFixtureId.get(leg.fixtureId)?.outcome ?? leg.outcomes.join(" / ")}
                    label="取消"
                  />
                ) : (
                  <RetainLegForm
                    options={options}
                    currentPath={currentPath}
                    fixtureId={leg.fixtureId}
                    marketType={marketTypeFromTicketLeg(leg.market)}
                    outcome={leg.outcomes.join(" / ")}
                    label="保留"
                  />
                )}
              </div>
            ))}
            {ticket.legs.length > 4 ? <span className="answer-more">另有 {ticket.legs.length - 4} 场</span> : null}
          </div>
          <div className="answer-metrics">
            <span>
              <strong>{formatCurrency(ticket.totalStake)}</strong>
              <small>总金额</small>
            </span>
            <span>
              <strong>{formatPercent(ticket.hitProbability)}</strong>
              <small>命中概率</small>
            </span>
            <span>
              <strong>{formatPercent(ticket.roi)}</strong>
              <small>ROI</small>
            </span>
          </div>
          <p className="answer-note">
            {ticket.explanations[0] ?? `风险评分 ${ticket.riskScore.toFixed(2)}，EV ${formatCurrency(ticket.ev)}。`}
          </p>
        </>
      ) : (
        <EmptyAnswer copy={emptyCopy} />
      )}
    </article>
  );
}

function ReleaseOrFallback({
  options,
  currentPath,
  fixtureId,
  marketType,
  outcome,
  label,
}: {
  options: ParlayTicketRequestOptions;
  currentPath: "/dashboard" | "/parlays";
  fixtureId: string;
  marketType: string;
  outcome: string;
  label: string;
}) {
  if (options.recommendationRunId) {
    return (
      <ReleaseLegForm
        options={options}
        currentPath={currentPath}
        fixtureId={fixtureId}
        marketType={marketType}
        outcome={outcome}
        label={label}
      />
    );
  }
  return (
    <a href={toggleLockedFixtureHref(options, fixtureId)} className="answer-lock-link is-locked">
      <LockOpen size={14} aria-hidden="true" />
      {label}
    </a>
  );
}

function RetainLegForm({
  options,
  currentPath,
  fixtureId,
  marketType,
  outcome,
  label,
}: {
  options: ParlayTicketRequestOptions;
  currentPath: "/dashboard" | "/parlays";
  fixtureId: string;
  marketType: string;
  outcome: string;
  label: string;
}) {
  return (
    <form action={retainRecommendationLegAction} className="answer-retain-form">
      <input type="hidden" name="current_path" value={currentPath} />
      <input type="hidden" name="fixture_id" value={fixtureId} />
      <input type="hidden" name="market_type" value={marketType} />
      <input type="hidden" name="outcome" value={outcome} />
      <RecommendationHiddenInputs options={options} />
      <button type="submit" className="answer-lock-link">
        <LockKeyhole size={14} aria-hidden="true" />
        {label}
      </button>
    </form>
  );
}

function ReleaseLegForm({
  options,
  currentPath,
  fixtureId,
  marketType,
  outcome,
  label,
}: {
  options: ParlayTicketRequestOptions;
  currentPath: "/dashboard" | "/parlays";
  fixtureId: string;
  marketType: string;
  outcome: string;
  label: string;
}) {
  return (
    <form action={releaseRecommendationLegAction} className="answer-retain-form">
      <input type="hidden" name="current_path" value={currentPath} />
      <input type="hidden" name="fixture_id" value={fixtureId} />
      <input type="hidden" name="market_type" value={marketType} />
      <input type="hidden" name="outcome" value={outcome} />
      <RecommendationHiddenInputs options={options} />
      <button type="submit" className="answer-lock-link is-locked">
        <LockOpen size={14} aria-hidden="true" />
        {label}
      </button>
    </form>
  );
}

function RecommendationHiddenInputs({ options }: { options: ParlayTicketRequestOptions }) {
  return (
    <>
      <input type="hidden" name="pass_type" value={options.passType ?? "all"} />
      <input type="hidden" name="unit_stake" value={options.unitStake ?? 2} />
      <input type="hidden" name="max_budget" value={options.maxBudget ?? 20} />
      <input type="hidden" name="allow_multiple" value={String(options.allowMultiple !== false)} />
      {options.excludeBetaCompetitions ? <input type="hidden" name="exclude_beta" value="true" /> : null}
      {(options.allowedMarkets ?? []).map((market) => (
        <input key={market} type="hidden" name="allowed_market" value={market} />
      ))}
      {(options.lockedFixtureIds ?? []).map((fixtureId) => (
        <input key={fixtureId} type="hidden" name="locked_fixture" value={fixtureId} />
      ))}
      {options.recommendationRunId ? (
        <input type="hidden" name="recommendation_run_id" value={options.recommendationRunId} />
      ) : null}
      {options.retentionSource ? <input type="hidden" name="retention_source" value={options.retentionSource} /> : null}
    </>
  );
}

function RecommendationControls({ options }: { options: ParlayTicketRequestOptions }) {
  const allowedMarkets = new Set(options.allowedMarkets ?? ["1x2", "cn_handicap_1x2", "european_handicap_1x2"]);

  return (
    <form className="answer-controls" aria-label="推荐参数">
      <label className="control">
        <span>
          <Layers3 size={14} aria-hidden="true" /> 串关类型
        </span>
        <select name="pass_type" defaultValue={options.passType ?? "all"}>
          {passTypeOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="control">
        <span>
          <Coins size={14} aria-hidden="true" /> 单位金额
        </span>
        <input name="unit_stake" type="number" min={1} step={1} defaultValue={options.unitStake ?? 2} />
      </label>

      <label className="control">
        <span>
          <Coins size={14} aria-hidden="true" /> 总预算
        </span>
        <input name="max_budget" type="number" min={1} step={1} defaultValue={options.maxBudget ?? 20} />
      </label>

      <label className="control">
        <span>结构</span>
        <select name="allow_multiple" defaultValue={options.allowMultiple === false ? "false" : "true"}>
          <option value="true">允许复式</option>
          <option value="false">只看单式</option>
        </select>
      </label>

      <fieldset className="answer-market-fieldset">
        <legend>玩法</legend>
        {marketOptions.map((option) => (
          <label key={option.value}>
            <input
              name="allowed_market"
              value={option.value}
              type="checkbox"
              defaultChecked={allowedMarkets.has(option.value)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </fieldset>

      {(options.lockedFixtureIds ?? []).map((fixtureId) => (
        <input key={fixtureId} type="hidden" name="locked_fixture" value={fixtureId} />
      ))}
      {options.recommendationRunId ? (
        <input type="hidden" name="recommendation_run_id" value={options.recommendationRunId} />
      ) : null}
      {options.retentionSource ? <input type="hidden" name="retention_source" value={options.retentionSource} /> : null}

      <button className="toolbar-button" type="submit">
        <SlidersHorizontal size={15} aria-hidden="true" />
        重新计算
      </button>
    </form>
  );
}

function EmptyAnswer({ copy }: { copy: string }) {
  return <p className="answer-empty">{copy}</p>;
}

function selectBestTicket(
  tickets: ParlayTicket[],
  maxBudget: number,
  mode: "any" | "multiple" = "any",
  lockedFixtureIds: Set<string> = new Set(),
) {
  const candidates = tickets.filter((ticket) => {
    if (!ticket.ruleValid || ticket.totalStake > maxBudget) return false;
    if (mode === "multiple") return ticket.isMultiple;
    if (![...lockedFixtureIds].every((fixtureId) => ticket.legs.some((leg) => leg.fixtureId === fixtureId))) {
      return false;
    }
    return true;
  });

  return candidates.sort((left, right) => ticketScore(right, lockedFixtureIds) - ticketScore(left, lockedFixtureIds))[0] ?? null;
}

function ticketScore(ticket: ParlayTicket, lockedFixtureIds: Set<string>) {
  const roiContribution = Math.max(Math.min(ticket.roi, 0.5), -0.5) * 0.18;
  const evContribution = ticket.ev > 0 ? 0.04 : -0.04;
  const lockedCoverage = [...lockedFixtureIds].filter((fixtureId) =>
    ticket.legs.some((leg) => leg.fixtureId === fixtureId),
  ).length;
  return ticket.hitProbability + roiContribution + evContribution + lockedCoverage * 0.12 - ticket.riskScore * 0.06;
}

function matchLabel(match: MatchPrediction) {
  return `${match.homeTeam.name} vs ${match.awayTeam.name}`;
}

function marketTypeLabel(marketType: string) {
  const labels: Record<string, string> = {
    "1x2": "胜平负",
    cn_handicap_1x2: "中国让球",
    european_handicap_1x2: "欧洲让球",
    correct_score: "比分",
    asian_handicap: "亚洲让球",
  };
  return labels[marketType] ?? marketType;
}

function answerLegOutcomeLabel(leg: RecommendationAnswerLeg) {
  return leg.outcomes.map((outcome) => outcomeLabel(outcome)).join(" / ");
}

function dataQualityGradeFromScore(score: number) {
  if (score >= 85) return "A";
  if (score >= 70) return "B";
  if (score >= 55) return "C";
  return "D";
}

function outcomeLabel(outcome: string) {
  const labels: Record<string, string> = {
    home_win: "主胜",
    draw: "平局",
    away_win: "客胜",
    handicap_home_win: "让胜",
    handicap_draw: "让平",
    handicap_away_win: "让负",
  };
  return labels[outcome] ?? outcome;
}

function lockedFixtureSummaries(
  matches: MatchPrediction[],
  tickets: ParlayTicket[],
  lockedFixtureIds: Set<string>,
  retainedLegByFixtureId: Map<string, RecommendationLockedLeg> = new Map(),
) {
  return [...lockedFixtureIds].map((fixtureId) => {
    const match = matches.find((item) => item.fixtureId === fixtureId);
    const ticketLeg = tickets.flatMap((ticket) => ticket.legs).find((leg) => leg.fixtureId === fixtureId);
    const retainedLeg = retainedLegByFixtureId.get(fixtureId);
    return {
      fixtureId,
      label: match ? matchLabel(match) : ticketLeg?.matchLabel ?? fixtureId,
      marketType: retainedLeg?.marketType ?? marketTypeFromTicketLeg(ticketLeg?.market ?? "1X2"),
      outcome: retainedLeg?.outcome ?? ticketLeg?.outcomes.join(" / ") ?? "home_win",
    };
  });
}

function activeRetainedLifecycleLegs(lifecycle: RecommendationLifecycleDetail | null | undefined) {
  return lifecycle?.lockedLegs.filter((leg) => leg.status === "locked") ?? [];
}

function LifecycleTimeline({ lifecycle }: { lifecycle: RecommendationLifecycleDetail }) {
  const recentEvents = lifecycle.events.slice(-3).reverse();
  return (
    <div className="answer-lifecycle-panel" aria-label="推荐生命周期">
      <span className="answer-lifecycle-title">
        <History size={14} aria-hidden="true" />
        最近事件
      </span>
      <div className="answer-lifecycle-list">
        {recentEvents.map((event) => (
          <div key={event.recommendationLifecycleEventId} className="answer-lifecycle-event">
            <strong>{lifecycleEventLabel(event.reasonCode)}</strong>
            <span>
              {statusLabel(event.fromStatus)} → {statusLabel(event.toStatus)}
            </span>
            <small>{formatDateTime(event.eventTimeUtc)}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function lifecycleEventLabel(reasonCode: string) {
  const labels: Record<string, string> = {
    recommendation_generated: "生成推荐",
    user_locked_leg: "已保留",
    user_retained_leg: "已保留",
    user_released_leg: "已取消保留",
    user_confirmed_ticket: "用户确认",
  };
  return labels[reasonCode] ?? reasonCode.replaceAll("_", " ");
}

function statusLabel(status: RecommendationLifecycleDetail["run"]["status"]) {
  const labels: Record<RecommendationLifecycleDetail["run"]["status"], string> = {
    candidate: "候选",
    current: "当前推荐",
    superseded: "已替换",
    locked: "保留态",
    confirmed_manual: "用户确认",
    live: "比赛中",
    settled: "已结算",
    invalidated: "已失效",
  };
  return labels[status];
}

function lifecycleSourceLabel(
  lifecycle: RecommendationLifecycleDetail | null | undefined,
  retentionSource: string | undefined,
) {
  if (lifecycle || retentionSource === "lifecycle_api") {
    return "生命周期 API";
  }
  return "本页参数";
}

function toggleLockedFixtureHref(options: ParlayTicketRequestOptions, fixtureId: string) {
  const lockedFixtureIds = new Set(options.lockedFixtureIds ?? []);
  if (lockedFixtureIds.has(fixtureId)) {
    lockedFixtureIds.delete(fixtureId);
  } else {
    lockedFixtureIds.add(fixtureId);
  }
  return recommendationHref(options, [...lockedFixtureIds]);
}

function recommendationHref(options: ParlayTicketRequestOptions, lockedFixtureIds: string[]) {
  const params = new URLSearchParams();
  params.set("pass_type", options.passType ?? "all");
  params.set("unit_stake", String(options.unitStake ?? 2));
  params.set("max_budget", String(options.maxBudget ?? 20));
  params.set("allow_multiple", String(options.allowMultiple !== false));
  if (options.excludeBetaCompetitions) {
    params.set("exclude_beta", "true");
  }
  for (const market of options.allowedMarkets ?? []) {
    params.append("allowed_market", market);
  }
  for (const lockedFixtureId of lockedFixtureIds) {
    params.append("locked_fixture", lockedFixtureId);
  }
  if (options.recommendationRunId !== undefined) {
    params.set("recommendation_run_id", String(options.recommendationRunId));
  }
  if (options.retentionSource) {
    params.set("retention_source", options.retentionSource);
  }
  return `?${params.toString()}`;
}

function marketTypeFromTicketLeg(market: string) {
  const map: Record<string, string> = {
    "1X2": "1x2",
    "胜平负": "1x2",
    "让球胜平负": "cn_handicap_1x2",
    "中国让球": "cn_handicap_1x2",
    "欧洲让球": "european_handicap_1x2",
    "比分": "correct_score",
  };
  return map[market] ?? "1x2";
}
