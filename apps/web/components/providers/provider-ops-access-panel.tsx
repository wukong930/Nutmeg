"use client";

import { Lock, LogOut, ShieldCheck } from "lucide-react";
import { useActionState } from "react";

import {
  lockProviderOpsAction,
  unlockProviderOpsAction,
} from "@/app/providers/actions";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";

type ProviderOpsActionState = {
  status: "idle" | "success" | "error";
  message: string;
};

type ProviderOpsAccessState = {
  configured: boolean;
  unlocked: boolean;
  operatorName: string | null;
  expiresAtUtc: string | null;
};

const initialActionState: ProviderOpsActionState = {
  status: "idle",
  message: "",
};

export function ProviderOpsAccessPanel({
  access,
}: {
  access: ProviderOpsAccessState;
}) {
  const [state, action, pending] = useActionState(
    unlockProviderOpsAction,
    initialActionState,
  );

  if (access.unlocked) {
    return (
      <section className="section provider-access-section" aria-label="Provider Ops Access">
        <div className="provider-access-card" data-status="unlocked">
          <div className="provider-action-summary">
            <ShieldCheck size={16} aria-hidden="true" />
            <span className="provider-action-title">Provider Ops Access</span>
            <Badge tone="success">Admin controls unlocked</Badge>
            <Badge>{access.operatorName ?? "operator"}</Badge>
            <Badge>
              expires {access.expiresAtUtc ? formatDateTime(access.expiresAtUtc) : "session"}
            </Badge>
          </div>
          <form action={lockProviderOpsAction} className="toolbar provider-action-form">
            <button className="toolbar-button" type="submit">
              <LogOut size={14} aria-hidden="true" />
              Lock Provider Ops
            </button>
          </form>
        </div>
      </section>
    );
  }

  return (
    <section className="section provider-access-section" aria-label="Provider Ops Access">
      <div className="provider-access-card" data-status="locked">
        <div className="provider-action-summary">
          <Lock size={16} aria-hidden="true" />
          <span className="provider-action-title">Provider Ops Access</span>
          <Badge tone={access.configured ? "warning" : "risk"}>Admin controls locked</Badge>
          <Badge tone={access.configured ? "info" : "warning"}>
            {access.configured ? "token configured" : "token missing"}
          </Badge>
        </div>
        <p className="provider-commit-copy">
          Provider Ops 的写入型工具需要先解锁；未解锁时页面只展示只读状态和合规提示。
        </p>
        <form action={action} className="toolbar provider-action-form">
          <label className="control">
            <span>Operator</span>
            <input
              name="provider_ops_operator"
              maxLength={80}
              placeholder="nutmeg-ops"
              disabled={!access.configured}
            />
          </label>
          <label className="control provider-access-token-control">
            <span>Access token</span>
            <input
              name="provider_ops_token"
              type="password"
              autoComplete="current-password"
              disabled={!access.configured}
            />
          </label>
          <button
            className="toolbar-button"
            type="submit"
            disabled={pending || !access.configured}
          >
            <ShieldCheck size={14} aria-hidden="true" />
            Unlock Provider Ops
          </button>
        </form>
        <div className="provider-action-message" data-status={state.status}>
          {state.message || "Access token is never rendered back to the browser."}
        </div>
      </div>
    </section>
  );
}

export function ProviderOpsLockedControls() {
  return (
    <div className="provider-action-message provider-locked-controls" data-status="idle">
      Admin controls locked. Unlock Provider Ops to use this audited operation.
    </div>
  );
}
