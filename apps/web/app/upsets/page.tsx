import Link from "next/link";
import { SlidersHorizontal } from "lucide-react";

import { DataQualityBadge, TextBadge } from "@/components/ui/badge";
import { UpsetCard } from "@/components/upset/upset-card";
import { formatDateTime } from "@/lib/format";
import { getUpsets } from "@/lib/api";

type UpsetItem = Awaited<ReturnType<typeof getUpsets>>[number];

type UpsetsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

const upsetTypeLabels: Record<string, string> = {
  favorite_fail_to_win: "热门不胜",
  favorite_loss: "热门输球",
  underdog_cover: "弱队受让",
  favorite_fail_to_cover: "热门输盘",
  draw_overlooked: "平局被低估",
  low_score_trap: "低比分陷阱",
  blowout_tail_risk: "大比分尾部",
};

export default async function UpsetsPage({ searchParams }: UpsetsPageProps) {
  const params = await searchParams;
  const typeFilter = firstParam(params?.type) ?? "all";
  const minQuality = firstParam(params?.min_quality) ?? "D";
  const minGap = Number(firstParam(params?.min_gap) ?? "0");
  const alerts = filterUpsets(await getUpsets(), {
    typeFilter,
    minQuality,
    minGap,
  });
  const averageFragility =
    alerts.length > 0
      ? alerts.reduce((sum, alert) => sum + alert.favoriteFragilityScore, 0) / alerts.length
      : 0;
  const elevatedCount = alerts.filter((alert) =>
    ["medium_high", "high"].includes(alert.riskLevel),
  ).length;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">冷门观察</h1>
          <p className="page-copy">
            冷门榜用于提示热门脆弱度、平局低估和让球方向风险；所有条目都保留模型版本和预测时间。
            冷门观察表示模型识别到热门方向风险，不代表冷门一定发生。
          </p>
        </div>
        <div className="metric">
          <span className="metric-label">观察样本</span>
          <div className="metric-value mono">{alerts.length}</div>
        </div>
      </header>

      <section className="metric-row" aria-label="冷门观察摘要">
        <div className="metric">
          <span className="metric-label">平均热门脆弱度</span>
          <div className="metric-value mono">{Math.round(averageFragility * 100)}</div>
        </div>
        <div className="metric">
          <span className="metric-label">中高以上风险</span>
          <div className="metric-value mono">{elevatedCount}</div>
        </div>
        <div className="metric">
          <span className="metric-label">排序依据</span>
          <div className="metric-value">脆弱度</div>
        </div>
      </section>

      <form className="toolbar" aria-label="冷门筛选">
        <label className="control">
          <span>冷门类型</span>
          <select name="type" defaultValue={typeFilter}>
            <option value="all">全部类型</option>
            {Object.entries(upsetTypeLabels).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="control">
          <span>最低数据质量</span>
          <select name="min_quality" defaultValue={minQuality}>
            <option value="A">A</option>
            <option value="B">B</option>
            <option value="C">C</option>
            <option value="D">D</option>
          </select>
        </label>
        <label className="control">
          <span>最低概率差</span>
          <select name="min_gap" defaultValue={String(minGap)}>
            <option value="0">0pp</option>
            <option value="0.02">2pp</option>
            <option value="0.04">4pp</option>
          </select>
        </label>
        <button className="toolbar-button" type="submit">
          <SlidersHorizontal size={15} aria-hidden="true" />
          应用筛选
        </button>
      </form>

      <section className="section">
        {alerts.length > 0 ? (
          <div className="grid">
            {alerts.map((alert) => (
              <div className="panel" key={`${alert.fixtureId}-${alert.type}`}>
                <div className="section-header">
                  <div>
                    <div className="badge-row">
                      <TextBadge>{alert.competitionName}</TextBadge>
                      <TextBadge>{upsetTypeLabels[alert.type] ?? alert.label}</TextBadge>
                      <DataQualityBadge grade={alert.dataQualityGrade} score={alert.dataQualityScore} />
                      <span className="badge mono">{alert.modelVersion}</span>
                      <span className="badge">{formatDateTime(alert.predictionTimeUtc)}</span>
                    </div>
                    <h2 className="section-title upset-match-title">
                      {alert.matchLabel}
                    </h2>
                  </div>
                  <Link href={`/fixtures/${alert.fixtureId}`} className="detail-link">
                    查看比赛
                  </Link>
                </div>
                <UpsetCard alert={alert} />
              </div>
            ))}
          </div>
        ) : (
          <div className="panel empty-state">
            <h2 className="section-title">暂无符合筛选的冷门观察</h2>
            <p className="meta">降低概率差或数据质量门槛后再查看；缺失条目不表示没有比赛风险。</p>
          </div>
        )}
      </section>
    </main>
  );
}

function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function filterUpsets(
  alerts: UpsetItem[],
  filters: {
    typeFilter: string;
    minQuality: string;
    minGap: number;
  },
) {
  return alerts
    .filter((alert) => filters.typeFilter === "all" || alert.type === filters.typeFilter)
    .filter((alert) => qualityRank(alert.dataQualityGrade) >= qualityRank(filters.minQuality))
    .filter((alert) => Math.abs(alert.probabilityGap) >= filters.minGap)
    .sort((left, right) => {
      const fragilityDelta = right.favoriteFragilityScore - left.favoriteFragilityScore;
      if (fragilityDelta !== 0) {
        return fragilityDelta;
      }
      return Math.abs(right.probabilityGap) - Math.abs(left.probabilityGap);
    });
}

function qualityRank(grade: string) {
  const ranks: Record<string, number> = {
    A: 4,
    B: 3,
    C: 2,
    D: 1,
  };
  return ranks[grade] ?? 0;
}
