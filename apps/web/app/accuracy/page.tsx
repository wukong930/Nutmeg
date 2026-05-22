import { AccuracyMetricCard } from "@/components/accuracy/accuracy-metric-card";
import { BrierTrend } from "@/components/accuracy/brier-trend";
import { CalibrationBucketList } from "@/components/accuracy/calibration-bucket-list";
import { CalibrationCurve } from "@/components/accuracy/calibration-curve";
import { ErrorTypeList } from "@/components/accuracy/error-type-list";
import { EvaluationWindowDisplay } from "@/components/accuracy/evaluation-window-display";
import { LogLossTrend } from "@/components/accuracy/log-loss-trend";
import { ModelComparisonCard } from "@/components/accuracy/model-comparison-card";
import { ModelVersionSelector } from "@/components/accuracy/model-version-selector";
import { getAccuracySummary, type AccuracySummaryRequestOptions } from "@/lib/api";
import { formatDateTime, formatPercent } from "@/lib/format";
import type { AccuracyMetricSet } from "@/types/api";

const marketLabels: Record<string, string> = {
  "1x2": "胜平负 1X2",
  cn_handicap_1x2: "让球胜平负",
  asian_handicap: "亚洲让球",
};

type AccuracyPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AccuracyPage({ searchParams }: AccuracyPageProps) {
  const params = await searchParams;
  const summary = await getAccuracySummary(accuracyOptionsFromParams(params));

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Accuracy Lab</h1>
          <p className="page-copy">
            这里按模型版本、时间窗口、联赛和玩法查看 Log Loss、Brier Score、校准误差、错误类型和模型对比。
            该页面用于复盘概率质量，不把单场结果作为唯一判断依据。
          </p>
        </div>
        <div className="badge-row">
          <span className="badge">模型 {summary.modelVersion}</span>
          <span className="badge">窗口 {summary.window}</span>
          <span className="badge">生成 {formatDateTime(summary.generatedAtUtc)}</span>
        </div>
      </header>

      <ModelVersionSelector summary={summary} />
      <EvaluationWindowDisplay summary={summary} />

      <section className="section">
        <div className="grid grid-four">
          <AccuracyMetricCard
            label="Log Loss"
            value={summary.logLoss}
            display="decimal"
            detail="越低表示概率分布对实际赛果惩罚越小。"
          />
          <AccuracyMetricCard
            label="Brier Score"
            value={summary.brierScore}
            display="decimal"
            detail="越低表示分类概率误差越小。"
          />
          <AccuracyMetricCard
            label="Calibration Error"
            value={summary.ece}
            display="percent"
            detail="预测概率与实际频率的平均偏差。"
          />
          <AccuracyMetricCard
            label="Sample Size"
            value={summary.sampleSize}
            display="integer"
            detail="当前筛选窗口内的赛后评估样本。"
          />
        </div>
      </section>

      <section className="section grid grid-two">
        <CalibrationCurve buckets={summary.calibrationBuckets} />
        <div className="grid">
          <BrierTrend summary={summary} />
          <LogLossTrend summary={summary} />
        </div>
      </section>

      <section className="section grid grid-two">
        <MarketBreakdown metrics={summary.byMarket} />
        <CompetitionBreakdown competitions={summary.byCompetition} />
      </section>

      <section className="section grid grid-two">
        <CalibrationBucketList buckets={summary.calibrationBuckets} />
        <ErrorTypeList errorTypes={summary.errorTypes} />
      </section>

      <section className="section">
        {summary.modelComparisons.map((comparison) => (
          <ModelComparisonCard
            key={`${comparison.baselineModelVersion}-${comparison.candidateModelVersion}`}
            comparison={comparison}
          />
        ))}
      </section>
    </main>
  );
}

function accuracyOptionsFromParams(
  params: Record<string, string | string[] | undefined> | undefined,
): AccuracySummaryRequestOptions {
  return {
    modelVersion: firstParam(params?.model_version) ?? "active",
    competitionId: firstParam(params?.competition_id) ?? "all",
    market: firstParam(params?.market) ?? "all",
    window: firstParam(params?.window) ?? "90d",
  };
}

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function MarketBreakdown({ metrics }: { metrics: Record<string, AccuracyMetricSet> }) {
  return (
    <article className="accuracy-panel">
      <div className="accuracy-panel-head">
        <div>
          <h2>玩法指标</h2>
          <p>按市场拆分概率评分，便于发现某类规则结算的偏差。</p>
        </div>
      </div>
      <table className="accuracy-table">
        <caption>按玩法拆分 Log Loss、Brier、ECE 和样本量。</caption>
        <thead>
          <tr>
            <th>玩法</th>
            <th>Log Loss</th>
            <th>Brier</th>
            <th>ECE</th>
            <th>样本</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(metrics).map(([market, metric]) => (
            <tr key={market}>
              <td>{marketLabels[market] ?? market}</td>
              <td>{formatDecimal(metric.logLoss)}</td>
              <td>{formatDecimal(metric.brierScore)}</td>
              <td>{formatMaybePercent(metric.ece)}</td>
              <td>{metric.sampleSize}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </article>
  );
}

function CompetitionBreakdown({
  competitions,
}: {
  competitions: Array<AccuracyMetricSet & { competitionId: string; competitionName: string }>;
}) {
  return (
    <article className="accuracy-panel">
      <div className="accuracy-panel-head">
        <div>
          <h2>联赛指标</h2>
          <p>低样本联赛需要单独观察，避免整体指标掩盖漂移。</p>
        </div>
      </div>
      <table className="accuracy-table">
        <caption>按联赛拆分概率评分和低样本漂移风险。</caption>
        <thead>
          <tr>
            <th>联赛</th>
            <th>Log Loss</th>
            <th>Brier</th>
            <th>ECE</th>
            <th>样本</th>
          </tr>
        </thead>
        <tbody>
          {competitions.map((competition) => (
            <tr key={competition.competitionId}>
              <td>{competition.competitionName}</td>
              <td>{formatDecimal(competition.logLoss)}</td>
              <td>{formatDecimal(competition.brierScore)}</td>
              <td>{formatMaybePercent(competition.ece)}</td>
              <td>{competition.sampleSize}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </article>
  );
}

function formatDecimal(value: number | null) {
  return value === null ? "N/A" : value.toFixed(3);
}

function formatMaybePercent(value: number | null) {
  return value === null ? "N/A" : formatPercent(value);
}
