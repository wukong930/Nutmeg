import { ShieldAlert } from "lucide-react";

import { formatPercent, formatPp, riskLabel } from "@/lib/format";
import type { UpsetAlert, UpsetContribution } from "@/types/api";

import { RiskContributionBars } from "./risk-contribution-bars";

export function FavoriteFragilityPanel({ alert }: { alert: UpsetAlert }) {
  const score = Math.round(alert.favoriteFragilityScore * 100);
  const favorite = alert.favorite ?? "市场热门";
  const favoriteModelProbability = alert.favoriteModelProbability ?? null;
  const favoriteMarketProbability = alert.favoriteMarketProbability ?? null;

  return (
    <section className="favorite-fragility-panel" aria-label="热门脆弱度">
      <div className="favorite-fragility-head">
        <div className="fragility-score" aria-label={`热门脆弱度 ${score} 分`}>
          <ShieldAlert size={18} aria-hidden="true" />
          <strong>{score}</strong>
          <span>/100</span>
        </div>
        <div>
          <h3>热门脆弱度</h3>
          <p>{alert.label}</p>
        </div>
        <span className={`fragility-risk risk-${alert.riskLevel}`}>
          {riskLabel(alert.riskLevel)}
        </span>
      </div>

      <div className="favorite-fragility-grid">
        <MetricCell label="热门" value={favorite} />
        <MetricCell
          label="热门模型概率"
          value={favoriteModelProbability === null ? "待接入" : formatPercent(favoriteModelProbability)}
        />
        <MetricCell
          label="热门市场概率"
          value={favoriteMarketProbability === null ? "待接入" : formatPercent(favoriteMarketProbability)}
        />
        <MetricCell label="观察项差值" value={formatPp(alert.probabilityGap)} />
      </div>

      <RiskContributionBars contributions={resolvedContributions(alert)} />
      <p className="upset-warning">冷门观察表示模型识别到热门方向风险，不代表冷门一定发生。</p>
    </section>
  );
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="fragility-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function resolvedContributions(alert: UpsetAlert): UpsetContribution[] {
  if (alert.contributions?.length) {
    return alert.contributions;
  }

  const gapScore = Math.min(100, Math.abs(alert.probabilityGap) * 1000);
  const fragilityScore = alert.favoriteFragilityScore * 100;
  return [
    {
      key: "market_gap",
      label: "市场分歧",
      score: Number(gapScore.toFixed(1)),
      description: "模型概率与市场隐含概率存在差异。",
    },
    {
      key: "favorite_fragility",
      label: "热门脆弱度",
      score: Number(fragilityScore.toFixed(1)),
      description: "综合平局、让球和低比分风险的占位估计。",
    },
    {
      key: "data_context",
      label: "解释上下文",
      score: 50,
      description: "完整贡献分解需要历史盘口、阵容和赛程数据继续接入。",
    },
  ];
}
