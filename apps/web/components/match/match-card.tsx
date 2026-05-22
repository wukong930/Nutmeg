import Link from "next/link";
import { Clock, ShieldCheck } from "lucide-react";

import { ProbabilityTriptych } from "@/components/probability/probability-triptych";
import { DataQualityBadge, BetaBadge, RiskBadge, TextBadge } from "@/components/ui/badge";
import { formatDateTime, formatPercent } from "@/lib/format";
import type { MatchPrediction } from "@/types/api";

import "./match.css";

export function MatchPredictionCard({ match }: { match: MatchPrediction }) {
  const topScore = match.correctScores[0];
  const primaryAlert = match.upsetAlerts[0];
  const riskLevel = primaryAlert?.riskLevel ?? "low";

  return (
    <article className="match-card">
      <div className="match-card-main">
        <div>
          <div className="badge-row">
            <TextBadge>{match.competitionName}</TextBadge>
            {match.modelStatus === "beta" ? <BetaBadge /> : null}
            <DataQualityBadge grade={match.dataQualityGrade} score={match.dataQualityScore} />
            <RiskBadge riskLevel={riskLevel} prefix="冷门观察" />
          </div>
          <h2 className="match-title">
            {match.homeTeam.name} <span>vs</span> {match.awayTeam.name}
          </h2>
          <div className="match-meta">
            <span>
              <Clock size={14} aria-hidden="true" />
              {formatDateTime(match.kickoffTimeUtc)}
            </span>
            <span>
              <ShieldCheck size={14} aria-hidden="true" />
              {match.modelVersion}
            </span>
            <span>预测 {formatDateTime(match.predictionTimeUtc)}</span>
          </div>
        </div>
        <Link href={`/fixtures/${match.fixtureId}`} className="detail-link">
          查看详情
        </Link>
      </div>
      <ProbabilityTriptych
        items={match.oneXTwo}
        modelVersion={match.modelVersion}
        predictionTimeUtc={match.predictionTimeUtc}
        compact
      />
      <div className="match-card-insights" aria-label="比赛摘要">
        <div className="match-mini-panel">
          <span className="match-mini-label">主盘口</span>
          <strong>{match.asianHandicap.label}</strong>
        </div>
        <div className="match-mini-panel">
          <span className="match-mini-label">比分 Top 1</span>
          <strong>{topScore ? `${topScore.score} · ${formatPercent(topScore.probability)}` : "待生成"}</strong>
        </div>
        <div className="match-mini-panel">
          <span className="match-mini-label">模型置信度</span>
          <strong>{confidenceLabel(match.confidence)}</strong>
        </div>
      </div>
      {primaryAlert ? (
        <div className="match-alert">
          <strong>{primaryAlert.label}</strong>
          <span>
            {primaryAlert.targetOutcome} 模型 {formatPercent(primaryAlert.modelProbability)}，市场{" "}
            {formatPercent(primaryAlert.marketProbability)}
          </span>
        </div>
      ) : null}
    </article>
  );
}

function confidenceLabel(confidence: MatchPrediction["confidence"]) {
  const labels: Record<MatchPrediction["confidence"], string> = {
    high: "高",
    medium: "中",
    low: "低",
  };
  return labels[confidence];
}
