"use client";

import { ClipboardCheck, FileText, Save, ShieldCheck } from "lucide-react";
import { useActionState, useState } from "react";

import { recordProviderAuthorizationReviewAction } from "@/app/providers/actions";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import type {
  ProviderAuthorization,
  ProviderAuthorizationReview,
} from "@/types/api";

type ProviderOpsActionState = {
  status: "idle" | "success" | "error";
  message: string;
};

const initialActionState: ProviderOpsActionState = {
  status: "idle",
  message: "",
};

export function ProviderAuthorizationReviewActions({
  providers,
  reviews,
}: {
  providers: ProviderAuthorization[];
  reviews: ProviderAuthorizationReview[];
}) {
  const sortedProviders = [...providers].sort((left, right) =>
    left.providerName.localeCompare(right.providerName),
  );
  const [selectedProviderName, setSelectedProviderName] = useState(
    sortedProviders[0]?.providerName ?? "",
  );
  const [state, action, pending] = useActionState(
    recordProviderAuthorizationReviewAction,
    initialActionState,
  );
  const provider =
    sortedProviders.find((item) => item.providerName === selectedProviderName) ??
    sortedProviders[0] ??
    null;

  if (!provider) {
    return (
      <div className="provider-action-message" data-status="idle">
        No provider authorization records available.
      </div>
    );
  }

  const latestReview = reviews.find(
    (review) => review.providerName === provider.providerName,
  );

  return (
    <div
      className="provider-sync-workflow-grid provider-terms-review-actions"
      aria-label="Provider authorization review actions"
    >
      <form
        key={provider.providerName}
        action={action}
        className="provider-sync-form provider-terms-review-form"
      >
        <div className="provider-action-summary">
          <ShieldCheck size={16} aria-hidden="true" />
          <span className="provider-action-title">Record Terms Review</span>
          <Badge tone={reviewStatusTone(provider.status)}>
            {provider.status.replace("_", " ")}
          </Badge>
          <Badge tone={provider.nextReviewDueAtUtc ? "info" : "warning"}>
            due{" "}
            {provider.nextReviewDueAtUtc
              ? formatDateTime(provider.nextReviewDueAtUtc)
              : "untracked"}
          </Badge>
          <Badge>
            latest{" "}
            {latestReview ? formatDateTime(latestReview.reviewedAtUtc) : "none"}
          </Badge>
        </div>

        <fieldset className="provider-fieldset provider-terms-review-fieldset">
          <legend>
            <FileText size={13} aria-hidden="true" />
            authorization decision
          </legend>
          <label className="control provider-conflict-select">
            <span>Provider</span>
            <select
              name="provider_name"
              value={provider.providerName}
              onChange={(event) => setSelectedProviderName(event.target.value)}
            >
              {sortedProviders.map((item) => (
                <option key={item.providerName} value={item.providerName}>
                  {item.providerName}
                </option>
              ))}
            </select>
          </label>
          <label className="control">
            <span>Review status</span>
            <select
              name="review_status"
              defaultValue={defaultReviewStatus(provider.status)}
            >
              <option value="needs_review">needs_review</option>
              <option value="research_only">research_only</option>
              <option value="approved">approved</option>
              <option value="blocked">blocked</option>
            </select>
          </label>
          <label className="control">
            <span>Review reference</span>
            <input
              name="review_reference"
              maxLength={120}
              defaultValue={defaultReviewReference(provider.providerName)}
            />
          </label>
          <label className="control">
            <span>Reviewed by</span>
            <input name="reviewed_by" maxLength={120} defaultValue={provider.owner} />
          </label>
          <label className="control">
            <span>Reviewed date</span>
            <input name="reviewed_at_date" type="date" />
          </label>
          <label className="control">
            <span>Next review due</span>
            <input
              name="next_review_due_date"
              type="date"
              defaultValue={dateInputValue(provider.nextReviewDueAtUtc)}
            />
          </label>
          <label className="control provider-terms-review-wide">
            <span>Allowed use</span>
            <input
              name="allowed_use"
              maxLength={240}
              defaultValue={provider.allowedUse}
            />
          </label>
          <label className="control">
            <span>Rate limit</span>
            <input
              name="rate_limit"
              maxLength={240}
              defaultValue={provider.rateLimit ?? ""}
              placeholder="provider-defined"
            />
          </label>
          <label className="control provider-terms-review-wide">
            <span>Terms URL</span>
            <input
              name="terms_url"
              maxLength={500}
              defaultValue={provider.termsUrl ?? ""}
              placeholder="https://..."
            />
          </label>
          <label className="control">
            <span>Terms hash</span>
            <input name="terms_version_hash" maxLength={160} placeholder="optional" />
          </label>
          <label className="control">
            <span>Owner</span>
            <input name="owner" maxLength={120} defaultValue={provider.owner} />
          </label>
        </fieldset>

        <fieldset className="provider-fieldset provider-terms-review-permissions">
          <legend>
            <ClipboardCheck size={13} aria-hidden="true" />
            data permissions
          </legend>
          <label className="provider-checkbox-control">
            <input
              name="commercial_use_allowed"
              type="checkbox"
              value="yes"
              defaultChecked={provider.commercialUseAllowed}
            />
            commercial use allowed
          </label>
          <label className="provider-checkbox-control">
            <input
              name="retention_allowed"
              type="checkbox"
              value="yes"
              defaultChecked={provider.retentionAllowed}
            />
            retain normalized snapshots
          </label>
          <label className="provider-checkbox-control">
            <input
              name="historical_data_allowed"
              type="checkbox"
              value="yes"
              defaultChecked={provider.historicalDataAllowed}
            />
            historical data allowed
          </label>
          <label className="provider-checkbox-control">
            <input
              name="redistribution_allowed"
              type="checkbox"
              value="yes"
              defaultChecked={provider.redistributionAllowed}
            />
            redistribution allowed
          </label>
        </fieldset>

        <label className="control provider-textarea-control provider-terms-review-wide">
          <span>Evidence JSON</span>
          <textarea
            name="evidence_json"
            defaultValue={defaultEvidenceJson(provider, latestReview)}
          />
        </label>
        <label className="control provider-textarea-control provider-terms-review-wide">
          <span>Notes</span>
          <textarea
            name="notes"
            maxLength={1000}
            defaultValue={provider.notes}
          />
        </label>

        <div className="toolbar provider-action-form">
          <label className="provider-checkbox-control">
            <input name="terms_review_ack" type="checkbox" value="yes" />
            operator reviewed provider terms
          </label>
          <button className="toolbar-button" type="submit" disabled={pending}>
            <Save size={14} aria-hidden="true" />
            Record review
          </button>
        </div>

        <div className="provider-action-message" data-status={state.status}>
          {state.message || "Terms review writes are admin-token protected."}
        </div>
      </form>
    </div>
  );
}

function defaultReviewStatus(status: ProviderAuthorization["status"]) {
  if (status === "active") {
    return "approved";
  }
  if (status === "research_only") {
    return "research_only";
  }
  if (status === "blocked" || status === "expired") {
    return "blocked";
  }
  return "needs_review";
}

function defaultReviewReference(providerName: string) {
  const safeProvider = providerName.replace(/[^a-z0-9_.-]/gi, "_").toLowerCase();
  return `${safeProvider}_manual_terms_review`;
}

function defaultEvidenceJson(
  provider: ProviderAuthorization,
  latestReview: ProviderAuthorizationReview | undefined,
) {
  return JSON.stringify(
    {
      source: "provider_ops_manual_terms_review",
      provider_status_before_review: provider.status,
      previous_review_reference: latestReview?.reviewReference ?? null,
      terms_url_checked: Boolean(provider.termsUrl),
    },
    null,
    2,
  );
}

function dateInputValue(value: string | null) {
  return value ? value.slice(0, 10) : "";
}

function reviewStatusTone(status: ProviderAuthorization["status"]) {
  if (status === "active") {
    return "success";
  }
  if (status === "blocked" || status === "expired") {
    return "risk";
  }
  if (status === "research_only") {
    return "info";
  }
  return "warning";
}
