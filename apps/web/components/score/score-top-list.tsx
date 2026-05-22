import { formatPercent } from "@/lib/format";
import type { MatchPrediction } from "@/types/api";
import { Tooltip } from "@/components/ui/tooltip";

import "./score.css";

export function TopScoresPanel({ match }: { match: MatchPrediction }) {
  return (
    <div className="score-layout">
      <section className="panel">
        <div className="score-panel-head">
          <h3 className="section-title">比分倾向 Top 5</h3>
          <Tooltip label="比分概率是底层模型输出，不代表单一确定预测。">
            <span className="score-help">?</span>
          </Tooltip>
        </div>
        <ol className="score-list">
          {match.correctScores.map((score, index) => (
            <li className={index < 3 ? "score-top-ranked" : undefined} key={score.score}>
              <span className="score-chip">{score.score}</span>
              <span>{formatPercent(score.probability)}</span>
            </li>
          ))}
        </ol>
        <p className="score-risk-copy">精确比分属于低概率事件，Top 5 比分也不代表确定结果。</p>
      </section>
      <section className="panel">
        <h3 className="section-title">尾部比分风险</h3>
        <div className="tail-list">
          {match.tailEvents.map((event) => (
            <div key={event.label}>
              <span>{event.label}</span>
              <strong>{formatPercent(event.probability)}</strong>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function ScoreTopList({ match }: { match: MatchPrediction }) {
  return <TopScoresPanel match={match} />;
}
