import { CalendarDays, Database, Filter, Gauge, Radar, TrendingUp } from "lucide-react";

import "./match.css";

type CompetitionOption = {
  competitionId: string;
  competitionName: string;
};

type MatchListFiltersProps = {
  competitions: CompetitionOption[];
  defaultDate: string;
};

export function MatchListFilters({ competitions, defaultDate }: MatchListFiltersProps) {
  return (
    <section className="toolbar match-filter-toolbar" aria-label="赛事筛选">
      <label className="control">
        <span>
          <CalendarDays size={14} aria-hidden="true" /> 日期
        </span>
        <input type="date" defaultValue={defaultDate} />
      </label>
      <label className="control">
        <span>
          <Filter size={14} aria-hidden="true" /> 赛事
        </span>
        <select defaultValue="all">
          <option value="all">全部赛事</option>
          {competitions.map((competition) => (
            <option value={competition.competitionId} key={competition.competitionId}>
              {competition.competitionName}
            </option>
          ))}
        </select>
      </label>
      <label className="control">
        <span>
          <Gauge size={14} aria-hidden="true" /> 预测状态
        </span>
        <select defaultValue="all">
          <option value="all">全部状态</option>
          <option value="production">Production</option>
          <option value="beta">Beta</option>
          <option value="stale">可能过期</option>
        </select>
      </label>
      <label className="control">
        <span>
          <Database size={14} aria-hidden="true" /> 数据质量
        </span>
        <select defaultValue="all">
          <option value="all">全部质量</option>
          <option value="A">A 级</option>
          <option value="B">B 级以上</option>
          <option value="C">包含 C 级</option>
        </select>
      </label>
      <label className="control">
        <span>
          <Radar size={14} aria-hidden="true" /> 冷门风险
        </span>
        <select defaultValue="all">
          <option value="all">全部风险</option>
          <option value="medium_high">中高以上</option>
          <option value="medium">中等以上</option>
          <option value="low">低风险</option>
        </select>
      </label>
      <label className="control">
        <span>
          <TrendingUp size={14} aria-hidden="true" /> 市场差异
        </span>
        <select defaultValue="all">
          <option value="all">全部差异</option>
          <option value="positive">模型高于市场</option>
          <option value="negative">模型低于市场</option>
          <option value="large">差异较大</option>
        </select>
      </label>
    </section>
  );
}
