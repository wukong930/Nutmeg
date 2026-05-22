import { Clock3, Database, ShieldAlert } from "lucide-react";

import { formatDateTime } from "@/lib/format";
import type { DataFreshness } from "@/types/api";

import "./match.css";

type FreshnessRow = {
  label: string;
  available: boolean;
  freshEnough: boolean;
  snapshotTimeUtc: string | null;
  lagHours: number | null;
};

export function DataFreshnessPanel({ freshness }: { freshness?: DataFreshness }) {
  const rows = freshnessRows(freshness);

  return (
    <section className="data-freshness-panel panel" aria-label="Data Freshness">
      <div className="section-header">
        <div>
          <h2 className="section-title">Data Freshness</h2>
          <p className="meta">赔率、预计首发、伤停快照状态</p>
        </div>
        <Database size={18} aria-hidden="true" />
      </div>
      <div className="data-freshness-list">
        {rows.map((row) => (
          <div className={`data-freshness-row ${statusClass(row)}`} key={row.label}>
            <span>{iconForRow(row)}</span>
            <div>
              <strong>{row.label}</strong>
              <p>{detailForRow(row)}</p>
            </div>
            <em>{statusLabel(row)}</em>
          </div>
        ))}
      </div>
      {freshness?.fallbackUsed ? (
        <p className="match-data-warning">部分数据源暂不可用，当前展示使用降级数据路径。</p>
      ) : null}
    </section>
  );
}

function freshnessRows(freshness?: DataFreshness): FreshnessRow[] {
  return [
    {
      label: "赔率快照",
      available: freshness?.oddsAvailable ?? false,
      freshEnough: freshness?.oddsFreshEnough ?? false,
      snapshotTimeUtc: freshness?.oddsSnapshotTimeUtc ?? null,
      lagHours: freshness?.oddsSnapshotLagHours ?? null,
    },
    {
      label: "预计首发",
      available: freshness?.lineupAvailable ?? false,
      freshEnough: freshness?.lineupFreshEnough ?? false,
      snapshotTimeUtc: freshness?.lineupSnapshotTimeUtc ?? null,
      lagHours: freshness?.lineupSnapshotLagHours ?? null,
    },
    {
      label: "伤停状态",
      available: freshness?.injuryAvailable ?? false,
      freshEnough: freshness?.injuryFreshEnough ?? false,
      snapshotTimeUtc: freshness?.injurySnapshotTimeUtc ?? null,
      lagHours: freshness?.injurySnapshotLagHours ?? null,
    },
  ];
}

function statusClass(row: FreshnessRow) {
  if (!row.available) {
    return "missing";
  }
  return row.freshEnough ? "ready" : "stale";
}

function statusLabel(row: FreshnessRow) {
  if (!row.available) {
    return "missing";
  }
  return row.freshEnough ? "ready" : "stale";
}

function detailForRow(row: FreshnessRow) {
  if (!row.available) {
    return "暂未接入可用快照";
  }
  const time = row.snapshotTimeUtc ? formatDateTime(row.snapshotTimeUtc) : "未知时间";
  const lag = row.lagHours === null ? "" : ` · T-${row.lagHours.toFixed(1)}h`;
  return `${time}${lag}`;
}

function iconForRow(row: FreshnessRow) {
  if (!row.available || !row.freshEnough) {
    return <ShieldAlert size={16} aria-hidden="true" />;
  }
  return <Clock3 size={16} aria-hidden="true" />;
}
