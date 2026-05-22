import { Clock, Database, GitBranch } from "lucide-react";

import { BetaBadge, DataQualityBadge, RiskBadge, TextBadge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import type { MatchPrediction } from "@/types/api";

import "./match.css";

export function MatchHeader({ match }: { match: MatchPrediction }) {
  const primaryAlert = match.upsetAlerts[0];
  const riskLevel = primaryAlert?.riskLevel ?? "low";

  return (
    <header className="match-header">
      <div className="match-header-main">
        <div className="badge-row">
          <TextBadge>{match.competitionName}</TextBadge>
          {match.modelStatus === "beta" ? <BetaBadge /> : null}
          <DataQualityBadge grade={match.dataQualityGrade} score={match.dataQualityScore} />
          <RiskBadge riskLevel={riskLevel} prefix="冷门观察" />
        </div>
        <h1 className="page-title">
          {match.homeTeam.name} vs {match.awayTeam.name}
        </h1>
        <p className="page-copy">{buildMatchSummary(match)}</p>
        {match.dataFreshness?.stale || match.dataFreshness?.fallbackUsed ? (
          <p className="match-data-warning">{dataFreshnessMessage(match)}</p>
        ) : null}
      </div>
      <aside className="match-header-meta" aria-label="比赛预测上下文">
        <span className="badge">
          <Clock size={14} aria-hidden="true" />
          {formatDateTime(match.kickoffTimeUtc)}
        </span>
        <span className="badge">
          <GitBranch size={14} aria-hidden="true" />
          {match.modelVersion}
        </span>
        <span className="badge">
          <Database size={14} aria-hidden="true" />
          预测 {formatDateTime(match.predictionTimeUtc)}
        </span>
      </aside>
    </header>
  );
}

function dataFreshnessMessage(match: MatchPrediction) {
  const freshness = match.dataFreshness;
  if (!freshness) {
    return "部分数据未及时更新，预测仅供参考。";
  }
  if (freshness.fallbackUsed) {
    return "部分数据源暂不可用，预测仅供参考。";
  }
  if (!freshness.oddsAvailable) {
    return "缺少可用赔率快照，预测仅供参考。";
  }
  if (!freshness.oddsFreshEnough) {
    const lag = freshness.oddsSnapshotLagHours;
    const lagText = lag === null ? "" : `最后快照约 T-${lag.toFixed(1)}h。`;
    return `盘口数据可能已过期，${lagText}预测仅供参考。`;
  }
  if (!freshness.lineupAvailable) {
    return "缺少预计首发快照，预测仅供参考。";
  }
  if (!freshness.lineupFreshEnough) {
    const lag = freshness.lineupSnapshotLagHours;
    const lagText = lag === null ? "" : `最后快照约 T-${lag.toFixed(1)}h。`;
    return `预计首发数据可能已过期，${lagText}预测仅供参考。`;
  }
  if (!freshness.injuryAvailable) {
    return "缺少最新伤停快照，预测仅供参考。";
  }
  if (!freshness.injuryFreshEnough) {
    const lag = freshness.injurySnapshotLagHours;
    const lagText = lag === null ? "" : `最后快照约 T-${lag.toFixed(1)}h。`;
    return `伤停数据可能已过期，${lagText}预测仅供参考。`;
  }
  return "部分数据未及时更新，预测仅供参考。";
}

function buildMatchSummary(match: MatchPrediction) {
  const sorted = [...match.oneXTwo].sort((left, right) => right.probability - left.probability);
  const leader = sorted[0];
  const runnerUp = sorted[1];

  if (!leader || !runnerUp) {
    return "单场详情展示同一比分概率矩阵派生出的胜平负、让球、比分倾向和冷门风险。";
  }

  const gap = leader.probability - runnerUp.probability;
  if (gap < 0.08) {
    return "模型显示三项概率接近，本场不适合表达为单一强结论；请结合让球、比分结构和数据质量解读。";
  }
  return `模型当前倾向 ${leader.label}，但该结论仍来自概率分布，不代表确定赛果；让球与比分结构可能改变风险判断。`;
}
