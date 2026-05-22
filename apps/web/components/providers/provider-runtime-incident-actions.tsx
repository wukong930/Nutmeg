"use client";

import { ClipboardCheck, ShieldCheck } from "lucide-react";
import { useActionState } from "react";

import { updateProviderRuntimeIncidentStatusAction } from "@/app/providers/actions";
import { Badge } from "@/components/ui/badge";
import type { ProviderRuntimeIncidentReport } from "@/types/api";

type ProviderOpsActionState = {
  status: "idle" | "success" | "error";
  message: string;
};

const initialActionState: ProviderOpsActionState = {
  status: "idle",
  message: "",
};

export function ProviderRuntimeIncidentActions({
  incidents,
}: {
  incidents: ProviderRuntimeIncidentReport[];
}) {
  const [state, action, pending] = useActionState(
    updateProviderRuntimeIncidentStatusAction,
    initialActionState,
  );
  const activeIncidents = incidents.filter(
    (incident) =>
      incident.incidentStatus === "open" ||
      incident.incidentStatus === "acknowledged",
  );
  const selectableIncidents = activeIncidents.length > 0 ? activeIncidents : incidents;

  return (
    <div className="provider-action-panel" aria-label="Provider runtime incident operations">
      <div className="provider-action-summary">
        <ShieldCheck size={16} aria-hidden="true" />
        <span className="provider-action-title">Runtime Incident Lifecycle</span>
        <Badge tone={activeIncidents.length > 0 ? "warning" : "success"}>
          active {activeIncidents.length}
        </Badge>
        <Badge>latest {incidents.length}</Badge>
      </div>

      <form action={action} className="toolbar provider-action-form">
        <label className="control provider-conflict-select">
          <span>
            <ClipboardCheck size={14} aria-hidden="true" /> Incident
          </span>
          <select
            name="provider_runtime_incident_report_id"
            disabled={selectableIncidents.length === 0}
          >
            {selectableIncidents.map((incident) => (
              <option
                value={incident.providerRuntimeIncidentReportId}
                key={incident.providerRuntimeIncidentReportId}
              >
                #{incident.providerRuntimeIncidentReportId} {incident.alertLevel}{" "}
                {incident.incidentStatus}
              </option>
            ))}
          </select>
        </label>
        <label className="control">
          <span>状态</span>
          <select
            name="incident_status"
            defaultValue="acknowledged"
            disabled={selectableIncidents.length === 0}
          >
            <option value="acknowledged">acknowledged</option>
            <option value="resolved">resolved</option>
            <option value="ignored">ignored</option>
            <option value="open">open</option>
          </select>
        </label>
        <label className="control provider-resolution-note">
          <span>处置备注</span>
          <input name="resolution_note" maxLength={500} placeholder="review note" />
        </label>
        <button
          className="toolbar-button"
          type="submit"
          disabled={pending || selectableIncidents.length === 0}
        >
          <ShieldCheck size={15} aria-hidden="true" />
          更新状态
        </button>
      </form>
      <ActionMessage state={state} />
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
