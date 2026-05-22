"use client";

import { DatabaseZap, Radar, ShieldCheck } from "lucide-react";
import { useActionState } from "react";

import {
  commitMappedOddsSyncAction,
  runMappedOddsSyncDryRunAction,
} from "@/app/providers/actions";
import { Badge } from "@/components/ui/badge";

type ProviderOpsActionState = {
  status: "idle" | "success" | "error";
  message: string;
};

const initialActionState: ProviderOpsActionState = {
  status: "idle",
  message: "",
};

export function ProviderMappedOddsActions() {
  const [state, action, pending] = useActionState(
    runMappedOddsSyncDryRunAction,
    initialActionState,
  );
  const [commitState, commitAction, commitPending] = useActionState(
    commitMappedOddsSyncAction,
    initialActionState,
  );

  return (
    <div className="provider-sync-workflow-grid">
      <form
        action={action}
        className="provider-sync-form"
        aria-label="Mapped odds sync dry-run"
      >
        <div className="provider-action-summary">
          <span className="provider-action-title">Mapped Odds Sync</span>
          <Badge tone="info">dry-run only</Badge>
          <Badge>eventIds batch</Badge>
          <Badge tone="neutral">no snapshot write</Badge>
        </div>

        <MappedOddsFields />

        <div className="toolbar provider-action-form">
          <label className="provider-checkbox-control">
            <input name="mapped_odds_dry_run_ack" type="checkbox" value="yes" />
            reviewed fixture mappings
          </label>
          <button className="toolbar-button" type="submit" disabled={pending}>
            <ShieldCheck size={15} aria-hidden="true" />
            Mapped odds dry-run
          </button>
        </div>
        <ActionMessage state={state} />
      </form>

      <form
        action={commitAction}
        className="provider-sync-form provider-commit-form"
        aria-label="Mapped odds commit"
      >
        <div className="provider-action-summary">
          <span className="provider-action-title">Commit Mapped Odds</span>
          <Badge tone="warning">writes odds snapshots</Badge>
          <Badge>operator approval</Badge>
          <Badge tone="neutral">audited sync run</Badge>
        </div>

        <p className="provider-commit-copy">
          仅在 dry-run 覆盖率和 fixture mappings 已复核后使用；写入动作会保存 raw payload、
          odds snapshots 与 provider observations。
        </p>

        <MappedOddsFields />

        <label className="control provider-approval-note-control">
          <span>Approval note</span>
          <input
            name="mapped_odds_operator_approval_note"
            placeholder="reviewed dry-run coverage and mappings"
          />
        </label>

        <div className="toolbar provider-action-form">
          <label className="provider-checkbox-control">
            <input
              name="mapped_odds_commit_review_ack"
              type="checkbox"
              value="yes"
            />
            dry-run and mappings reviewed
          </label>
          <label className="provider-checkbox-control">
            <input
              name="mapped_odds_commit_write_ack"
              type="checkbox"
              value="yes"
            />
            approve odds snapshot write
          </label>
          <button className="toolbar-button" type="submit" disabled={commitPending}>
            <DatabaseZap size={15} aria-hidden="true" />
            Commit mapped odds
          </button>
        </div>
        <ActionMessage state={commitState} />
      </form>
    </div>
  );
}

function MappedOddsFields() {
  return (
    <div className="provider-sync-task-grid">
      <fieldset className="provider-fieldset">
        <legend>
          <Radar size={14} aria-hidden="true" /> The Odds API
        </legend>
        <label className="control">
          <span>Competition</span>
          <input
            name="mapped_odds_competition_id"
            placeholder="EPL"
            defaultValue="EPL"
          />
        </label>
        <label className="control">
          <span>Sport key</span>
          <input
            name="mapped_odds_sport_key"
            placeholder="soccer_epl"
            defaultValue="soccer_epl"
          />
        </label>
        <label className="control">
          <span>Regions</span>
          <input name="mapped_odds_regions" placeholder="eu" defaultValue="eu" />
        </label>
        <label className="control">
          <span>Markets</span>
          <input
            name="mapped_odds_markets"
            placeholder="h2h,spreads"
            defaultValue="h2h,spreads"
          />
        </label>
        <label className="control">
          <span>Bookmakers</span>
          <input name="mapped_odds_bookmakers" placeholder="optional" />
        </label>
        <label className="control">
          <span>Min confidence</span>
          <input
            name="mapped_odds_min_mapping_confidence"
            type="number"
            min={0}
            max={1}
            step={0.01}
            defaultValue={0.82}
          />
        </label>
        <label className="control">
          <span>Max mappings</span>
          <input
            name="mapped_odds_max_mappings"
            type="number"
            min={1}
            max={100}
            defaultValue={50}
          />
        </label>
        <label className="control">
          <span>Max odds lag h</span>
          <input
            name="mapped_odds_max_snapshot_lag_hours"
            type="number"
            min={1}
            max={168}
            defaultValue={24}
          />
        </label>
      </fieldset>
    </div>
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
