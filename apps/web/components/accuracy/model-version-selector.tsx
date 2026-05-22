import { Filter, LineChart, Rows3 } from "lucide-react";

import type { AccuracySummary } from "@/types/api";

export function ModelVersionSelector({ summary }: { summary: AccuracySummary }) {
  return (
    <form className="toolbar accuracy-selector" aria-label="Model version selector">
      <label className="control">
        <span>
          <LineChart size={14} aria-hidden="true" /> 模型版本
        </span>
        <select name="model_version" defaultValue={summary.filters.modelVersion}>
          <option value="active">active</option>
          <option value="poisson-m1.0.0">poisson-m1.0.0</option>
          <option value="dc-v1.5-candidate">dc-v1.5-candidate</option>
        </select>
      </label>

      <label className="control">
        <span>
          <Rows3 size={14} aria-hidden="true" /> 时间窗口
        </span>
        <select name="window" defaultValue={summary.filters.window}>
          <option value="30d">30d</option>
          <option value="90d">90d</option>
          <option value="180d">180d</option>
        </select>
      </label>

      <label className="control">
        <span>
          <Filter size={14} aria-hidden="true" /> 联赛
        </span>
        <select name="competition_id" defaultValue={summary.filters.competitionId}>
          <option value="all">全部联赛</option>
          <option value="EPL">Premier League</option>
          <option value="JPN_J1">J1 League</option>
        </select>
      </label>

      <label className="control">
        <span>
          <Filter size={14} aria-hidden="true" /> 玩法
        </span>
        <select name="market" defaultValue={summary.filters.market}>
          <option value="all">全部玩法</option>
          <option value="1x2">胜平负 1X2</option>
          <option value="cn_handicap_1x2">让球胜平负</option>
          <option value="asian_handicap">亚洲让球</option>
        </select>
      </label>

      <button className="toolbar-button" type="submit">
        <Filter size={15} aria-hidden="true" />
        应用筛选
      </button>
    </form>
  );
}
