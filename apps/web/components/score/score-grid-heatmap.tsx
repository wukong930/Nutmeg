import { formatPercent } from "@/lib/format";
import type { MatchPrediction } from "@/types/api";
import { Tooltip } from "@/components/ui/tooltip";

import "./score.css";

const maxVisibleGoals = 4;

export function ScoreGridHeatmap({ match }: { match: MatchPrediction }) {
  const visibleMax = Math.min(match.scoreGrid.maxGoals, maxVisibleGoals);
  const topScores = new Set(match.correctScores.slice(0, 3).map((score) => score.score));
  const maxCellProbability = Math.max(
    0.01,
    ...match.scoreGrid.grid
      .slice(0, visibleMax + 1)
      .flatMap((row) => row.slice(0, visibleMax + 1)),
  );

  return (
    <section className="panel score-grid-panel" aria-label="Score Grid Heatmap">
      <div className="score-panel-head">
        <div>
          <h3 className="section-title">Score Grid Heatmap</h3>
          <p className="meta">
            λ_home {formatLambda(match.scoreGrid.lambdaHome)} · λ_away {formatLambda(match.scoreGrid.lambdaAway)}
          </p>
        </div>
        <Tooltip label="比分概率是底层模型输出，不代表单一确定预测。">
          <span className="score-help">?</span>
        </Tooltip>
      </div>

      <div className="score-grid-compact">
        <span>Top 5</span>
        {match.correctScores.map((score) => (
          <strong key={score.score}>
            {score.score} {formatPercent(score.probability)}
          </strong>
        ))}
      </div>

      <details className="score-grid-advanced">
        <summary>Advanced matrix</summary>
        <div className="score-grid-table-wrap">
          <table className="score-grid-table">
            <caption>
              比分概率矩阵：行表示主队进球，列表示客队进球，Top 3 比分会被高亮。
            </caption>
            <thead>
              <tr>
                <th>Home \ Away</th>
                {Array.from({ length: visibleMax + 1 }, (_, awayGoals) => (
                  <th key={awayGoals}>Away {awayGoals}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: visibleMax + 1 }, (_, homeGoals) => (
                <tr key={homeGoals}>
                  <th>Home {homeGoals}</th>
                  {Array.from({ length: visibleMax + 1 }, (_, awayGoals) => {
                    const probability = match.scoreGrid.grid[homeGoals]?.[awayGoals] ?? 0;
                    const scoreKey = `${homeGoals}-${awayGoals}`;
                    const width = Math.max(4, (probability / maxCellProbability) * 100);
                    return (
                      <td className={topScores.has(scoreKey) ? "score-grid-cell top-score" : "score-grid-cell"} key={scoreKey}>
                        <span className="score-grid-cell-fill" style={{ width: `${width}%` }} />
                        <strong>{formatPercent(probability)}</strong>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className="meta">尾部概率质量：{formatPercent(match.scoreGrid.tailMass)}。</p>
    </section>
  );
}

function formatLambda(value: number | null) {
  return value === null ? "N/A" : value.toFixed(2);
}
