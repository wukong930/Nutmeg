import { CircleAlert } from "lucide-react";

import "./parlay.css";

export function ParlayWarningPanel({
  warnings,
  stale,
  fallbackUsed,
}: {
  warnings: string[];
  stale: boolean;
  fallbackUsed: boolean;
}) {
  const uniqueWarnings = Array.from(new Set(statusWarnings(warnings, stale, fallbackUsed)));
  if (uniqueWarnings.length === 0) {
    return null;
  }

  return (
    <aside className="parlay-warning-panel" role="status" aria-live="polite">
      <CircleAlert size={18} aria-hidden="true" />
      <div>
        <strong>候选池规则提示</strong>
        <ul className="parlay-warning-list">
          {uniqueWarnings.map((warning) => (
            <li key={warning}>{warningMessage(warning)}</li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

function warningMessage(warning: string) {
  const parts = warning.split(":");
  const isSkipped = parts[0].startsWith("skipped_");
  const passType = isSkipped ? parts[0].replace("skipped_", "") : null;
  const reason = isSkipped ? parts[1] : parts[0];
  const context = (isSkipped ? parts.slice(2) : parts.slice(1)).join(":");
  const prefix = passType ? `${passType} 候选` : "候选池";
  const suffix = context ? `：${context}` : "";

  if (reason === "beta_competition_excluded") {
    return `${prefix}已按参数排除 beta 赛事${suffix}`;
  }
  if (reason === "data_quality_below_50") {
    return `${prefix}包含数据质量 D 的赛事，已暂停展示${suffix}`;
  }
  if (reason === "competition_data_quality_d") {
    return `${prefix}关联赛事数据质量为 D，已暂停展示${suffix}`;
  }
  if (reason === "competition_not_ready") {
    return `${prefix}关联赛事尚未达到 beta 准入标准，已暂停展示${suffix}`;
  }
  if (reason === "competition_data_freshness_low") {
    return `${prefix}关联赛事数据新鲜度不足，已暂停展示${suffix}`;
  }
  if (reason === "odds_unavailable") {
    return `${prefix}缺少可用赔率快照，已暂停展示${suffix}`;
  }
  if (reason === "odds_market_unavailable") {
    return `${prefix}缺少所需玩法的赔率快照，已暂停展示${suffix}`;
  }
  if (reason === "odds_stale") {
    return `${prefix}赔率快照超过新鲜度阈值，已暂停展示${suffix}`;
  }
  if (reason === "lineup_unavailable") {
    return `${prefix}缺少预计首发快照，已暂停展示${suffix}`;
  }
  if (reason === "lineup_stale") {
    return `${prefix}预计首发快照超过新鲜度阈值，已暂停展示${suffix}`;
  }
  if (reason === "injury_unavailable") {
    return `${prefix}缺少伤停快照，已暂停展示${suffix}`;
  }
  if (reason === "injury_stale") {
    return `${prefix}伤停快照超过新鲜度阈值，已暂停展示${suffix}`;
  }
  if (reason === "parlay_data_stale") {
    return "部分数据未及时更新，串关候选仅供观察。";
  }
  if (reason === "readiness_repository_unavailable") {
    return "赛事准入状态暂不可用，当前仅按本地数据质量规则筛选。";
  }
  if (reason === "odds_freshness_repository_unavailable") {
    return "赔率新鲜度暂不可用，当前仅按本地数据质量规则筛选。";
  }
  if (reason === "availability_freshness_repository_unavailable") {
    return "阵容与伤停新鲜度暂不可用，当前仅按本地数据质量规则筛选。";
  }
  if (reason === "data_freshness_repository_unavailable") {
    return "数据新鲜度暂不可用，当前仅按本地数据质量规则筛选。";
  }
  if (reason === "parlay_fallback_used") {
    return "部分数据源暂不可用，当前结果使用降级数据路径。";
  }
  return warning;
}

function statusWarnings(warnings: string[], stale: boolean, fallbackUsed: boolean) {
  return [
    ...warnings,
    ...(stale ? ["parlay_data_stale"] : []),
    ...(fallbackUsed ? ["parlay_fallback_used"] : []),
  ];
}
