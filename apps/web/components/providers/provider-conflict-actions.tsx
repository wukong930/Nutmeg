"use client";

import { ClipboardCheck, RefreshCw, ShieldCheck } from "lucide-react";
import { useActionState } from "react";

import {
  evaluateProviderConflictsAction,
  updateProviderConflictResolutionAction,
} from "@/app/providers/actions";
import { Badge } from "@/components/ui/badge";
import type { ProviderPersistedConflictEvent } from "@/types/api";

type ProviderOpsActionState = {
  status: "idle" | "success" | "error";
  message: string;
};

const initialActionState: ProviderOpsActionState = {
  status: "idle",
  message: "",
};

export function ProviderConflictActions({
  persistedEvents,
}: {
  persistedEvents: ProviderPersistedConflictEvent[];
}) {
  const [evaluationState, evaluateAction, evaluationPending] = useActionState(
    evaluateProviderConflictsAction,
    initialActionState,
  );
  const [resolutionState, resolutionAction, resolutionPending] = useActionState(
    updateProviderConflictResolutionAction,
    initialActionState,
  );
  const openEvents = persistedEvents.filter((event) => event.resolutionStatus === "open");
  const resolutionEvents = openEvents.length > 0 ? openEvents : persistedEvents;

  return (
    <div className="provider-action-panel" aria-label="Provider conflict operations">
      <div className="provider-action-summary">
        <span className="provider-action-title">持久化冲突操作</span>
        <Badge tone={openEvents.length > 0 ? "warning" : "success"}>
          open {openEvents.length}
        </Badge>
        <Badge>latest {persistedEvents.length}</Badge>
      </div>

      <div className="provider-action-grid">
        <form action={evaluateAction} className="toolbar provider-action-form">
          <label className="control">
            <span>
              <RefreshCw size={14} aria-hidden="true" /> 检查上限
            </span>
            <input name="limit" type="number" min={1} max={2000} defaultValue={1000} />
          </label>
          <label className="provider-checkbox-control">
            <input name="include_observations" type="checkbox" value="yes" defaultChecked />
            观测冲突
          </label>
          <button className="toolbar-button" type="submit" name="mode" value="dry_run" disabled={evaluationPending}>
            <ClipboardCheck size={15} aria-hidden="true" />
            Dry-run
          </button>
          <label className="provider-checkbox-control">
            <input name="persist_ack" type="checkbox" value="yes" />
            确认写入
          </label>
          <button className="toolbar-button" type="submit" name="mode" value="persist" disabled={evaluationPending}>
            <ShieldCheck size={15} aria-hidden="true" />
            写入事件
          </button>
        </form>
        <ActionMessage state={evaluationState} />

        <form action={resolutionAction} className="toolbar provider-action-form">
          <label className="control provider-conflict-select">
            <span>
              <ShieldCheck size={14} aria-hidden="true" /> Conflict event
            </span>
            <select name="provider_conflict_event_id" disabled={resolutionEvents.length === 0}>
              {resolutionEvents.map((event) => (
                <option value={event.providerConflictEventId} key={event.providerConflictEventId}>
                  #{event.providerConflictEventId} {event.canonicalEntityId}
                </option>
              ))}
            </select>
          </label>
          <label className="control">
            <span>状态</span>
            <select name="resolution_status" defaultValue="resolved" disabled={resolutionEvents.length === 0}>
              <option value="resolved">resolved</option>
              <option value="ignored">ignored</option>
              <option value="open">open</option>
            </select>
          </label>
          <label className="control provider-resolution-note">
            <span>备注</span>
            <input name="resolution_note" maxLength={500} placeholder="review note" />
          </label>
          <button
            className="toolbar-button"
            type="submit"
            disabled={resolutionPending || resolutionEvents.length === 0}
          >
            <ShieldCheck size={15} aria-hidden="true" />
            更新状态
          </button>
        </form>
        <ActionMessage state={resolutionState} />
      </div>
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
