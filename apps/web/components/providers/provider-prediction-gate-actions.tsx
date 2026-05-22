"use client";

import { BrainCircuit, PlayCircle, ShieldCheck } from "lucide-react";
import { Fragment, useActionState, useState } from "react";

import { runPredictionQualityGateDryRunAction } from "@/app/providers/actions";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import type { PredictionJobRun } from "@/types/api";

type ProviderOpsActionState = {
  status: "idle" | "success" | "error";
  message: string;
};

const initialActionState: ProviderOpsActionState = {
  status: "idle",
  message: "",
};

export function ProviderPredictionGateActions({
  fetched,
  runs,
}: {
  fetched: boolean;
  runs: PredictionJobRun[];
}) {
  const [state, action, pending] = useActionState(
    runPredictionQualityGateDryRunAction,
    initialActionState,
  );
  const [qualityGateEnabled, setQualityGateEnabled] = useState(true);

  return (
    <div className="provider-sync-workflow-grid">
      <form
        action={action}
        className="provider-sync-form"
        aria-label="Prediction quality gate dry-run"
      >
        <div className="provider-action-summary">
          <span className="provider-action-title">Prediction Quality Gate</span>
          <Badge tone="info">dry-run only</Badge>
          <Badge>odds gate</Badge>
        </div>

        <div className="provider-sync-task-grid">
          <fieldset className="provider-fieldset">
            <legend>
              <BrainCircuit size={14} aria-hidden="true" /> Canonical prediction
            </legend>
            <label className="control">
              <span>Competition</span>
              <input
                name="prediction_competition_id"
                placeholder="EPL"
                defaultValue="EPL"
              />
            </label>
            <label className="control">
              <span>Window h</span>
              <input
                name="prediction_window_hours"
                type="number"
                min={1}
                max={720}
                defaultValue={720}
              />
            </label>
            <label className="control">
              <span>Max odds lag h</span>
              <input
                name="prediction_max_snapshot_lag_hours"
                type="number"
                min={1}
                max={168}
                defaultValue={168}
              />
            </label>
            <label className="control">
              <span>Fixture limit</span>
              <input
                name="prediction_limit"
                type="number"
                min={1}
                max={500}
                defaultValue={50}
              />
            </label>
          </fieldset>
        </div>

        <div className="toolbar provider-action-form">
          <label className="provider-checkbox-control">
            <input
              name="prediction_enforce_odds_quality_gate"
              type="hidden"
              value="no"
            />
            <input
              name="prediction_enforce_odds_quality_gate"
              type="checkbox"
              value="yes"
              checked={qualityGateEnabled}
              onChange={(event) => setQualityGateEnabled(event.target.checked)}
            />
            enforce odds quality gate
          </label>
          <label className="provider-checkbox-control">
            <input name="prediction_dry_run_ack" type="checkbox" value="yes" />
            quality gate dry-run confirmed
          </label>
          <button className="toolbar-button" type="submit" disabled={pending}>
            <PlayCircle size={15} aria-hidden="true" />
            Prediction dry-run
          </button>
        </div>
        <ActionMessage state={state} />
      </form>

      <div className="provider-review-strip">
        <Badge tone={fetched ? "success" : "warning"}>
          {fetched ? "admin prediction runs" : "fallback prediction runs"}
        </Badge>
        <Badge tone="info">latest {runs.length}</Badge>
        <Badge tone="neutral">no commit</Badge>
      </div>

      <div className="ui-table-wrap">
        <table className="ui-table">
          <caption>Prediction dry-run history, odds quality gate skips, and warnings.</caption>
          <thead>
            <tr>
              <th>Run</th>
              <th>状态</th>
              <th>Started</th>
              <th>Counts</th>
              <th>Skipped</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {runs.length > 0 ? (
              runs.map((run) => (
                <Fragment key={run.predictionJobRunId}>
                  <tr>
                    <td className="mono">#{run.predictionJobRunId}</td>
                    <td>
                      <Badge tone={predictionStatusTone(run.status)}>
                        {run.status}
                      </Badge>
                    </td>
                    <td>{formatDateTime(run.startedAtUtc)}</td>
                    <td className="mono">
                      {`F${run.fixtureCount} G${run.generatedCount} S${run.skippedFixtureIds.length}`}
                    </td>
                    <td className="provider-id-cell">
                      {run.skippedFixtureIds.join(", ") || "N/A"}
                    </td>
                    <td className="provider-id-cell">
                      {run.errorMessage ?? (run.warnings.join(", ") || "N/A")}
                    </td>
                  </tr>
                  <tr className="provider-run-detail-row">
                    <td colSpan={6}>
                      <details className="provider-run-details">
                        <summary>
                          <ShieldCheck size={14} aria-hidden="true" />
                          Prediction gate detail
                        </summary>
                        <dl className="provider-run-detail-list">
                          <DetailItem label="job_type" value={run.jobType} />
                          <DetailItem label="dry_run" value={run.dryRun} />
                          <DetailItem
                            label="completed"
                            value={
                              run.completedAtUtc
                                ? formatDateTime(run.completedAtUtc)
                                : "N/A"
                            }
                          />
                          <DetailItem label="duration_ms" value={run.durationMs ?? "N/A"} />
                          <DetailItem
                            label="data_quality_fixtures"
                            value={Object.keys(run.dataQualityScores)}
                          />
                        </dl>
                      </details>
                    </td>
                  </tr>
                </Fragment>
              ))
            ) : (
              <tr>
                <td className="ui-table-empty" colSpan={6}>
                  {fetched ? "暂无 prediction dry-run" : "Prediction dry-run history unavailable"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: unknown }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{formatDetailValue(value)}</dd>
    </>
  );
}

function ActionMessage({ state }: { state: ProviderOpsActionState }) {
  if (!state.message) {
    return null;
  }
  return (
    <div className="provider-action-message" data-status={state.status}>
      {state.message}
    </div>
  );
}

function predictionStatusTone(status: PredictionJobRun["status"]) {
  if (status === "completed") return "success";
  if (status === "failed") return "risk";
  return "info";
}

function formatDetailValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(", ") : "[]";
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}
