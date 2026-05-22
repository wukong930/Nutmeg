"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  providerAuthorizationReviewResponseSchema,
  providerConflictEvaluationResponseSchema,
  providerConflictResolutionResponseSchema,
  providerMappedEventOddsSyncResponseSchema,
  providerOpsAuditEventResponseSchema,
  providerRuntimeIncidentStatusUpdateResponseSchema,
  predictionJobRunResponseSchema,
  providerSyncWorkflowPreflightResponseSchema,
  providerSyncWorkflowRunResponseSchema,
  providerSyncWorkflowTemplateResponseSchema,
} from "@/lib/api-contract";
import {
  lockProviderOpsSession,
  getProviderOpsAccessState,
  requireProviderOpsAccess,
  unlockProviderOpsSession,
  type ProviderOpsAuthorizedSession,
} from "@/lib/provider-ops-auth";

type ProviderOpsActionState = {
  status: "idle" | "success" | "error";
  message: string;
};

const API_BASE_URL =
  process.env.NUTMEG_API_BASE_URL ??
  process.env.NEXT_PUBLIC_NUTMEG_API_BASE_URL ??
  "http://localhost:8000/api/v1";

const API_TIMEOUT_MS = Number(process.env.NUTMEG_API_TIMEOUT_MS ?? 30000);

export async function unlockProviderOpsAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const operatorName = stringValue(formData.get("provider_ops_operator"));
  const result = await unlockProviderOpsSession({
    token: stringValue(formData.get("provider_ops_token")),
    operatorName,
  });
  if (!result.ok) {
    await recordProviderOpsAuditEvent({
      eventType: "provider_ops_unlock",
      operatorName,
      outcome: "blocked",
      metadataJson: { reason: result.message },
    });
    return { status: "error", message: result.message };
  }
  await recordProviderOpsAuditEvent({
    eventType: "provider_ops_unlock",
    operatorName: result.operatorName,
    outcome: "success",
  });
  revalidatePath("/providers");
  redirect("/providers");
}

export async function lockProviderOpsAction(): Promise<void> {
  const access = await getProviderOpsAccessState();
  await lockProviderOpsSession();
  await recordProviderOpsAuditEvent({
    eventType: "provider_ops_lock",
    operatorName: access.operatorName ?? "unknown-provider-ops-operator",
    outcome: "success",
  });
  revalidatePath("/providers");
  redirect("/providers");
}

export async function recordProviderAuthorizationReviewAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const access = await requireProviderOpsAccess();
  if (!access.ok) {
    return { status: "error", message: access.message };
  }
  if (stringValue(formData.get("terms_review_ack")) !== "yes") {
    return { status: "error", message: "提交前需要确认条款复核已经完成。" };
  }

  const providerName = stringValue(formData.get("provider_name")).slice(0, 120);
  const reviewReference = stringValue(formData.get("review_reference")).slice(0, 120);
  const reviewStatus = stringValue(formData.get("review_status"));
  const reviewedBy =
    stringValue(formData.get("reviewed_by")).slice(0, 120) || access.operatorName;
  const allowedUse = stringValue(formData.get("allowed_use")).slice(0, 240);
  if (!providerName || !reviewReference || !allowedUse) {
    return {
      status: "error",
      message: "Provider、review reference 和 allowed use 为必填项。",
    };
  }
  if (!["approved", "research_only", "needs_review", "blocked"].includes(reviewStatus)) {
    return { status: "error", message: "请选择有效的 review status。" };
  }

  const evidenceJson = parseEvidenceJson(formData.get("evidence_json"));
  if (!evidenceJson.ok) {
    return { status: "error", message: evidenceJson.message };
  }

  const result = await adminApiRequest(
    "/providers/authorizations/reviews",
    {
      provider_name: providerName,
      review_reference: reviewReference,
      review_status: reviewStatus,
      reviewed_by: reviewedBy,
      reviewed_at_utc: dateInputToUtc(formData.get("reviewed_at_date")),
      terms_url: optionalString(formData.get("terms_url"), 500),
      terms_version_hash: optionalString(formData.get("terms_version_hash"), 160),
      allowed_use: allowedUse,
      commercial_use_allowed: checked(formData.get("commercial_use_allowed")),
      retention_allowed: checked(formData.get("retention_allowed")),
      historical_data_allowed: checked(formData.get("historical_data_allowed")),
      redistribution_allowed: checked(formData.get("redistribution_allowed")),
      rate_limit: optionalString(formData.get("rate_limit"), 240),
      next_review_due_at_utc: dateInputToUtc(formData.get("next_review_due_date")),
      owner: stringValue(formData.get("owner")).slice(0, 120) || "nutmeg-ops",
      evidence_json: {
        ...evidenceJson.value,
        provider_ops_operator: access.operatorName,
        provider_ops_access: "ui_session",
      },
      notes: operatorStampedNote(stringValue(formData.get("notes")), access.operatorName),
    },
    providerAuthorizationReviewResponseSchema,
    "POST",
    access,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  return {
    status: "success",
    message: `Terms review 已记录：${result.data.item.provider_name} / ${result.data.item.review_status}。`,
  };
}

export async function evaluateProviderConflictsAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const mode = stringValue(formData.get("mode"));
  const persist = mode === "persist";
  if (persist && stringValue(formData.get("persist_ack")) !== "yes") {
    return {
      status: "error",
      message: "写入前需要勾选确认。",
    };
  }

  const result = await adminApiRequest(
    "/providers/conflicts/evaluate",
    {
      dry_run: !persist,
      include_observations: stringValue(formData.get("include_observations")) === "yes",
      limit: boundedInt(formData.get("limit"), 1000, 1, 2000),
    },
    providerConflictEvaluationResponseSchema,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  const conflicts = result.data.result.conflict_count;
  const stored = result.data.stored_events.length;
  return {
    status: "success",
    message: persist
      ? `写入完成：${stored} 条 open conflict event 已写入或复用。`
      : `Dry-run 完成：发现 ${conflicts} 条候选 conflict event。`,
  };
}

export async function updateProviderConflictResolutionAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const access = await requireProviderOpsAccess();
  if (!access.ok) {
    return { status: "error", message: access.message };
  }
  const eventId = boundedInt(formData.get("provider_conflict_event_id"), 0, 1, 1_000_000_000);
  if (eventId <= 0) {
    return { status: "error", message: "请选择 conflict event。" };
  }
  const resolutionStatus = stringValue(formData.get("resolution_status"));
  if (!["open", "resolved", "ignored"].includes(resolutionStatus)) {
    return { status: "error", message: "请选择有效状态。" };
  }

  const result = await adminApiRequest(
    `/providers/conflicts/${eventId}/resolution`,
    {
      resolution_status: resolutionStatus,
      resolution_note: operatorStampedNote(
        stringValue(formData.get("resolution_note")),
        access.operatorName,
      ),
    },
    providerConflictResolutionResponseSchema,
    "PATCH",
    access,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  return {
    status: "success",
    message: `Conflict ${result.data.item.provider_conflict_event_id} 已更新为 ${result.data.item.resolution_status}。`,
  };
}

export async function runProviderSyncWorkflowDryRunAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const access = await requireProviderOpsAccess();
  if (!access.ok) {
    return { status: "error", message: access.message };
  }
  if (stringValue(formData.get("dry_run_ack")) !== "yes") {
    return { status: "error", message: "Dry-run 前需要勾选 operator approval。" };
  }
  const payload = providerSyncWorkflowRequestPayload(formData);
  if (!payload.ok) {
    return { status: "error", message: payload.message };
  }

  const result = await adminApiRequest(
    "/ops/provider-sync/run",
    {
      ...payload.value,
      operator_approved: true,
      operator_approval_note: operatorStampedNote(
        stringValue(formData.get("dry_run_approval_note")),
        access.operatorName,
      ),
      provider_sync_workflow_template_id: positiveIntOrNull(
        formData.get("selected_template_id"),
      ),
    },
    providerSyncWorkflowRunResponseSchema,
    "POST",
    access,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  return {
    status: "success",
    message:
      `Workflow dry-run 完成：run #${result.data.result.provider_sync_workflow_run_id ?? "N/A"}，` +
      `approval #${result.data.result.operator_approval_id ?? "N/A"}，` +
      `fixtures ${result.data.result.fixture_count}，odds ${result.data.result.odds_snapshot_count}，` +
      `availability ${result.data.result.availability_snapshot_count}。`,
  };
}

export async function preflightProviderSyncWorkflowAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const payload = providerSyncWorkflowRequestPayload(formData);
  if (!payload.ok) {
    return { status: "error", message: payload.message };
  }

  const result = await adminApiRequest(
    "/ops/provider-sync/preflight",
    payload.value,
    providerSyncWorkflowPreflightResponseSchema,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  const preflight = result.data.result;
  const issueSummary =
    preflight.issue_count > 0
      ? `errors ${preflight.error_count}，warnings ${preflight.warning_count}，info ${preflight.info_count}`
      : "无结构性问题";
  return {
    status: preflight.valid ? "success" : "error",
    message: `Preflight 完成：${preflight.task_count} 个 task，${issueSummary}。`,
  };
}

export async function saveProviderSyncWorkflowTemplateAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const templateName = stringValue(formData.get("template_name")).slice(0, 120);
  if (!templateName) {
    return { status: "error", message: "保存模板需要 template name。" };
  }
  const payload = providerSyncWorkflowRequestPayload(formData);
  if (!payload.ok) {
    return { status: "error", message: payload.message };
  }

  const result = await adminApiRequest(
    "/ops/provider-sync/templates",
    {
      template_name: templateName,
      description: stringValue(formData.get("template_description")).slice(0, 500) || null,
      ...payload.value,
    },
    providerSyncWorkflowTemplateResponseSchema,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  return {
    status: "success",
    message: `模板已保存：${result.data.item.template_name}。`,
  };
}

export async function updateProviderSyncWorkflowTemplateAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const templateId = positiveIntOrNull(formData.get("selected_template_id"));
  if (!templateId) {
    return { status: "error", message: "请先加载一个 template。" };
  }
  const templateName = stringValue(formData.get("template_name")).slice(0, 120);
  if (!templateName) {
    return { status: "error", message: "更新模板需要 template name。" };
  }
  const payload = providerSyncWorkflowRequestPayload(formData);
  if (!payload.ok) {
    return { status: "error", message: payload.message };
  }

  const result = await adminApiRequest(
    `/ops/provider-sync/templates/${templateId}`,
    {
      template_name: templateName,
      description: stringValue(formData.get("template_description")).slice(0, 500) || null,
      ...payload.value,
    },
    providerSyncWorkflowTemplateResponseSchema,
    "PATCH",
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  return {
    status: "success",
    message: `模板已更新：${result.data.item.template_name}。`,
  };
}

export async function archiveProviderSyncWorkflowTemplateAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const access = await requireProviderOpsAccess();
  if (!access.ok) {
    return { status: "error", message: access.message };
  }
  const templateId = positiveIntOrNull(formData.get("archive_template_id"));
  if (!templateId) {
    return { status: "error", message: "请选择要归档的 template。" };
  }
  if (stringValue(formData.get("archive_template_ack")) !== "yes") {
    return { status: "error", message: "归档模板前需要勾选 archive approved。" };
  }

  const result = await adminApiRequest(
    `/ops/provider-sync/templates/${templateId}`,
    {
      archive_reason: operatorStampedNote(
        stringValue(formData.get("archive_reason")),
        access.operatorName,
      ),
    },
    providerSyncWorkflowTemplateResponseSchema,
    "DELETE",
    access,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  return {
    status: "success",
    message: `模板已归档：${result.data.item.template_name}。`,
  };
}

export async function runMappedOddsSyncDryRunAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  if (stringValue(formData.get("mapped_odds_dry_run_ack")) !== "yes") {
    return { status: "error", message: "Mapped odds dry-run 前需要勾选映射已审核。" };
  }

  const result = await adminApiRequest(
    "/providers/the-odds-api/sync/mapped-event-odds",
    mappedOddsSyncPayload(formData, true),
    providerMappedEventOddsSyncResponseSchema,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  const sync = result.data.result;
  const coverage = result.data.coverage;
  const coverageText = coverage
    ? `，coverage 1X2 ${(coverage.one_x_two_coverage * 100).toFixed(0)}% / handicap ${(coverage.handicap_coverage * 100).toFixed(0)}%`
    : "";
  return {
    status: "success",
    message:
      `Mapped odds dry-run 完成：mappings ${sync.mapping_count}，` +
      `events ${sync.fetched_event_count}，normalized ${sync.normalized_odds_count}` +
      `${coverageText}。`,
  };
}

export async function commitMappedOddsSyncAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const access = await requireProviderOpsAccess();
  if (!access.ok) {
    return { status: "error", message: access.message };
  }
  if (stringValue(formData.get("mapped_odds_commit_review_ack")) !== "yes") {
    return {
      status: "error",
      message: "Mapped odds commit 前需要确认 dry-run 和映射审核结果。",
    };
  }
  if (stringValue(formData.get("mapped_odds_commit_write_ack")) !== "yes") {
    return {
      status: "error",
      message: "Mapped odds commit 会写入 odds snapshots，需要勾选写入确认。",
    };
  }

  const result = await adminApiRequest(
    "/providers/the-odds-api/sync/mapped-event-odds",
    {
      ...mappedOddsSyncPayload(formData, false),
      operator_approved: true,
      operator_approval_note: operatorStampedNote(
        stringValue(formData.get("mapped_odds_operator_approval_note")),
        access.operatorName,
      ),
    },
    providerMappedEventOddsSyncResponseSchema,
    "POST",
    access,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  const sync = result.data.result;
  const coverage = result.data.coverage;
  const runText = sync.sync_run
    ? `run #${sync.sync_run.provider_sync_run_id}，`
    : "";
  const coverageText = coverage
    ? `，coverage 1X2 ${(coverage.one_x_two_coverage * 100).toFixed(0)}% / handicap ${(coverage.handicap_coverage * 100).toFixed(0)}%`
    : "";
  return {
    status: "success",
    message:
      `Mapped odds commit 完成：${runText}persisted ${sync.odds_snapshot_count}，` +
      `inserted ${sync.inserted_snapshot_count}，updated ${sync.updated_snapshot_count}` +
      `${coverageText}。`,
  };
}

export async function runPredictionQualityGateDryRunAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  if (stringValue(formData.get("prediction_dry_run_ack")) !== "yes") {
    return { status: "error", message: "Prediction dry-run 前需要勾选质量门禁确认。" };
  }

  const result = await adminApiRequest(
    "/predictions/jobs/run",
    {
      job_type: "canonical_prematch_predictions",
      competition_id: stringValue(formData.get("prediction_competition_id")) || "EPL",
      dry_run: true,
      window_hours: boundedInt(formData.get("prediction_window_hours"), 720, 1, 720),
      max_snapshot_lag_hours: boundedInt(
        formData.get("prediction_max_snapshot_lag_hours"),
        168,
        1,
        168,
      ),
      limit: boundedInt(formData.get("prediction_limit"), 50, 1, 500),
      enforce_odds_quality_gate:
        formData.getAll("prediction_enforce_odds_quality_gate").includes("yes"),
    },
    predictionJobRunResponseSchema,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  return {
    status: "success",
    message:
      `Prediction dry-run 完成：fixtures ${result.data.fixture_count}，` +
      `generated ${result.data.generated_count}，` +
      `skipped ${result.data.skipped_fixture_ids.length}，` +
      `warnings ${result.data.warnings.length}。`,
  };
}

export async function updateProviderRuntimeIncidentStatusAction(
  _previousState: ProviderOpsActionState,
  formData: FormData,
): Promise<ProviderOpsActionState> {
  const access = await requireProviderOpsAccess();
  if (!access.ok) {
    return { status: "error", message: access.message };
  }
  const incidentId = boundedInt(
    formData.get("provider_runtime_incident_report_id"),
    0,
    1,
    1_000_000_000,
  );
  if (incidentId <= 0) {
    return { status: "error", message: "请选择 runtime incident。" };
  }
  const incidentStatus = stringValue(formData.get("incident_status"));
  if (!["open", "acknowledged", "resolved", "ignored"].includes(incidentStatus)) {
    return { status: "error", message: "请选择有效的 incident 状态。" };
  }
  const resolutionNote = stringValue(formData.get("resolution_note")).slice(0, 500);
  if (["resolved", "ignored"].includes(incidentStatus) && !resolutionNote) {
    return { status: "error", message: "关闭或忽略 incident 需要填写处置备注。" };
  }

  const result = await adminApiRequest(
    `/providers/runtime/monitoring/incidents/${incidentId}/status`,
    {
      incident_status: incidentStatus,
      updated_by: access.operatorName,
      resolution_note: operatorStampedNote(resolutionNote, access.operatorName),
    },
    providerRuntimeIncidentStatusUpdateResponseSchema,
    "PATCH",
    access,
  );
  if (!result.ok) {
    return { status: "error", message: result.message };
  }

  revalidatePath("/providers");
  return {
    status: "success",
    message:
      `Runtime incident #${result.data.item.provider_runtime_incident_report_id} ` +
      `已更新为 ${result.data.item.incident_status}。`,
  };
}

function mappedOddsSyncPayload(formData: FormData, dryRun: boolean) {
  return {
    canonical_competition_id:
      stringValue(formData.get("mapped_odds_competition_id")) || "EPL",
    sport_key: stringValue(formData.get("mapped_odds_sport_key")) || "soccer_epl",
    regions: stringValue(formData.get("mapped_odds_regions")) || "eu",
    markets: stringValue(formData.get("mapped_odds_markets")) || "h2h,spreads",
    bookmakers: stringValue(formData.get("mapped_odds_bookmakers")) || null,
    min_mapping_confidence: boundedFloat(
      formData.get("mapped_odds_min_mapping_confidence"),
      0.82,
      0,
      1,
    ),
    max_mappings: boundedInt(formData.get("mapped_odds_max_mappings"), 50, 1, 100),
    max_snapshot_lag_hours: boundedInt(
      formData.get("mapped_odds_max_snapshot_lag_hours"),
      24,
      1,
      168,
    ),
    include_coverage: true,
    dry_run: dryRun,
  };
}

async function adminApiRequest<T>(
  path: string,
  payload: Record<string, unknown>,
  schema: { parse: (value: unknown) => T },
  method: "POST" | "PATCH" | "DELETE" = "POST",
  session?: ProviderOpsAuthorizedSession,
): Promise<{ ok: true; data: T } | { ok: false; message: string }> {
  let operatorName = session?.operatorName ?? null;
  if (!operatorName) {
    const access = await requireProviderOpsAccess();
    if (!access.ok) {
      return { ok: false, message: access.message };
    }
    operatorName = access.operatorName;
  }
  const adminToken = process.env.NUTMEG_ADMIN_API_TOKEN;
  if (!adminToken) {
    return { ok: false, message: "服务端未配置 admin token。" };
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        "X-Nutmeg-Admin-Token": adminToken,
        "X-Nutmeg-Operator": operatorName,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const body: unknown = await response.json().catch(() => ({}));
    if (!response.ok) {
      await recordProviderOpsAuditEvent({
        eventType: "provider_ops_admin_action",
        operatorName,
        outcome: response.status === 403 ? "blocked" : "failure",
        requestPath: path,
        requestMethod: method,
        metadataJson: {
          http_status: response.status,
          action_surface: "provider_ops",
        },
      });
      return { ok: false, message: errorMessage(body, response.status) };
    }
    await recordProviderOpsAuditEvent({
      eventType: "provider_ops_admin_action",
      operatorName,
      outcome: "success",
      requestPath: path,
      requestMethod: method,
      metadataJson: {
        http_status: response.status,
        action_surface: "provider_ops",
      },
    });
    return { ok: true, data: schema.parse(body) };
  } catch (error) {
    await recordProviderOpsAuditEvent({
      eventType: "provider_ops_admin_action",
      operatorName,
      outcome: "failure",
      requestPath: path,
      requestMethod: method,
      metadataJson: {
        error_type: error instanceof Error ? error.name : "unknown",
      },
    });
    return {
      ok: false,
      message: error instanceof Error ? error.message : "provider operation failed",
    };
  } finally {
    clearTimeout(timeout);
  }
}

async function recordProviderOpsAuditEvent({
  eventType,
  operatorName,
  outcome,
  requestPath = null,
  requestMethod = null,
  targetType = null,
  targetId = null,
  metadataJson = {},
}: {
  eventType: string;
  operatorName: string | null;
  outcome: "success" | "failure" | "blocked";
  requestPath?: string | null;
  requestMethod?: string | null;
  targetType?: string | null;
  targetId?: string | null;
  metadataJson?: Record<string, unknown>;
}) {
  const adminToken = process.env.NUTMEG_ADMIN_API_TOKEN;
  if (!adminToken) {
    return;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}/ops/provider-audit/events`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        "X-Nutmeg-Admin-Token": adminToken,
        ...(operatorName ? { "X-Nutmeg-Operator": operatorName } : {}),
      },
      body: JSON.stringify({
        event_type: eventType,
        operator_name: operatorName,
        action_surface: "provider_ops",
        target_type: targetType,
        target_id: targetId,
        outcome,
        request_path: requestPath,
        request_method: requestMethod,
        metadata_json: metadataJson,
      }),
      signal: controller.signal,
    });
    if (response.ok) {
      providerOpsAuditEventResponseSchema.parse(await response.json());
    }
  } catch {
    // Provider Ops audit is best-effort from the UI layer; concrete write APIs still return their own result.
  } finally {
    clearTimeout(timeout);
  }
}

function providerSyncWorkflowRequestPayload(
  formData: FormData,
):
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; message: string } {
  const fixtureSync = providerFixtureSyncPayload(formData);
  if (!fixtureSync.ok) {
    return { ok: false, message: fixtureSync.message };
  }
  const oddsSyncs = providerOddsSyncPayloads(formData);
  if (!oddsSyncs.ok) {
    return { ok: false, message: oddsSyncs.message };
  }
  const availabilitySyncs = providerAvailabilitySyncPayloads(formData);
  if (!availabilitySyncs.ok) {
    return { ok: false, message: availabilitySyncs.message };
  }

  const taskCount =
    (fixtureSync.value ? 1 : 0) +
    oddsSyncs.value.length +
    availabilitySyncs.value.length;
  if (taskCount === 0) {
    return { ok: false, message: "至少填写一个明确的 provider sync task。" };
  }

  return {
    ok: true,
    value: {
      dry_run: true,
      fixture_sync: fixtureSync.value,
      odds_syncs: oddsSyncs.value,
      availability_syncs: availabilitySyncs.value,
      run_conflict_detection: stringValue(formData.get("run_conflict_detection")) === "yes",
      conflict_observation_lookback_hours: boundedInt(
        formData.get("conflict_observation_lookback_hours"),
        168,
        1,
        8760,
      ),
      conflict_limit: boundedInt(formData.get("conflict_limit"), 1000, 1, 5000),
      run_prematch_workflow: false,
    },
  };
}

function providerFixtureSyncPayload(
  formData: FormData,
):
  | { ok: true; value: Record<string, string> | null }
  | { ok: false; message: string } {
  const providerCompetitionId = stringValue(formData.get("fixture_provider_competition_id"));
  const season = stringValue(formData.get("fixture_season"));
  const canonicalCompetitionId = stringValue(formData.get("fixture_canonical_competition_id"));
  if (!providerCompetitionId && !season && !canonicalCompetitionId) {
    return { ok: true, value: null };
  }
  if (!providerCompetitionId || !season) {
    return {
      ok: false,
      message: "Fixture sync 需要 provider competition ID 和 season。",
    };
  }
  return {
    ok: true,
    value: {
      provider_competition_id: providerCompetitionId,
      season,
      ...(canonicalCompetitionId ? { canonical_competition_id: canonicalCompetitionId } : {}),
    },
  };
}

function providerOddsSyncPayloads(
  formData: FormData,
):
  | { ok: true; value: Array<Record<string, string>> }
  | { ok: false; message: string } {
  const count = boundedInt(formData.get("odds_task_count"), 0, 0, 50);
  if (count === 0) {
    const legacy = providerOddsSyncPayload(formData, "odds", 1);
    return legacy.ok
      ? { ok: true, value: legacy.value ? [legacy.value] : [] }
      : legacy;
  }

  const payloads: Array<Record<string, string>> = [];
  for (let index = 0; index < count; index += 1) {
    const result = providerOddsSyncPayload(formData, `odds_${index}`, index + 1);
    if (!result.ok) {
      return result;
    }
    if (result.value) {
      payloads.push(result.value);
    }
  }
  return { ok: true, value: payloads };
}

function providerOddsSyncPayload(
  formData: FormData,
  prefix: string,
  position: number,
):
  | { ok: true; value: Record<string, string> | null }
  | { ok: false; message: string } {
  const sportKey = stringValue(formData.get(`${prefix}_sport_key`));
  const providerEventId = stringValue(formData.get(`${prefix}_provider_event_id`));
  const canonicalFixtureId = stringValue(
    formData.get(`${prefix}_canonical_fixture_id`),
  );
  const regions = stringValue(formData.get(`${prefix}_regions`)) || "eu";
  const markets = stringValue(formData.get(`${prefix}_markets`)) || "h2h,spreads";
  const bookmakers = stringValue(formData.get(`${prefix}_bookmakers`));
  const hasIdentity = Boolean(sportKey || providerEventId || canonicalFixtureId);
  const hasCustomOptions = Boolean(
    bookmakers || regions !== "eu" || markets !== "h2h,spreads",
  );
  if (!hasIdentity && !hasCustomOptions) {
    return { ok: true, value: null };
  }
  if (!sportKey || !providerEventId || !canonicalFixtureId) {
    return {
      ok: false,
      message: `Odds sync ${position} 需要 sport key、provider event ID 和 canonical fixture ID。`,
    };
  }
  return {
    ok: true,
    value: {
      sport_key: sportKey,
      provider_event_id: providerEventId,
      canonical_fixture_id: canonicalFixtureId,
      regions,
      markets,
      ...(bookmakers ? { bookmakers } : {}),
    },
  };
}

function providerAvailabilitySyncPayloads(
  formData: FormData,
):
  | { ok: true; value: Array<Record<string, unknown>> }
  | { ok: false; message: string } {
  const count = boundedInt(formData.get("availability_task_count"), 0, 0, 50);
  if (count === 0) {
    const legacy = providerAvailabilitySyncPayload(formData, "availability", 1);
    return legacy.ok
      ? { ok: true, value: legacy.value ? [legacy.value] : [] }
      : legacy;
  }

  const payloads: Array<Record<string, unknown>> = [];
  for (let index = 0; index < count; index += 1) {
    const result = providerAvailabilitySyncPayload(
      formData,
      `availability_${index}`,
      index + 1,
    );
    if (!result.ok) {
      return result;
    }
    if (result.value) {
      payloads.push(result.value);
    }
  }
  return { ok: true, value: payloads };
}

function providerAvailabilitySyncPayload(
  formData: FormData,
  prefix: string,
  position: number,
):
  | { ok: true; value: Record<string, unknown> | null }
  | { ok: false; message: string } {
  const providerFixtureId = stringValue(formData.get(`${prefix}_provider_fixture_id`));
  const canonicalFixtureId = stringValue(
    formData.get(`${prefix}_canonical_fixture_id`),
  );
  const teamMappingsText = stringValue(formData.get(`${prefix}_team_mappings`));
  if (!providerFixtureId && !canonicalFixtureId && !teamMappingsText) {
    return { ok: true, value: null };
  }
  if (!providerFixtureId || !canonicalFixtureId) {
    return {
      ok: false,
      message: `Availability sync ${position} 需要 provider fixture ID 和 canonical fixture ID。`,
    };
  }
  const mappings = providerTeamMappings(teamMappingsText);
  if (!mappings.ok) {
    return { ok: false, message: `Availability sync ${position}: ${mappings.message}` };
  }
  return {
    ok: true,
    value: {
      provider_fixture_id: providerFixtureId,
      canonical_fixture_id: canonicalFixtureId,
      team_mappings: mappings.value,
    },
  };
}

function providerTeamMappings(
  value: string,
): { ok: true; value: Array<{ provider_team_id: string; canonical_team_id: string }> } | {
  ok: false;
  message: string;
} {
  const lines = value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    return {
      ok: false,
      message: "Availability sync 需要至少一条 team mapping。",
    };
  }
  const mappings: Array<{ provider_team_id: string; canonical_team_id: string }> = [];
  for (const line of lines) {
    const [providerTeamId, canonicalTeamId] = line.split(/[=,]/).map((part) => part.trim());
    if (!providerTeamId || !canonicalTeamId) {
      return {
        ok: false,
        message: "Team mapping 格式为 provider_team_id=canonical_team_id，每行一条。",
      };
    }
    mappings.push({
      provider_team_id: providerTeamId,
      canonical_team_id: canonicalTeamId,
    });
  }
  return { ok: true, value: mappings };
}

function errorMessage(body: unknown, status: number) {
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }
  return `provider operation failed: ${status}`;
}

function stringValue(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value : "";
}

function optionalString(value: FormDataEntryValue | null, maxLength: number) {
  const text = stringValue(value).trim().slice(0, maxLength);
  return text || null;
}

function checked(value: FormDataEntryValue | null) {
  return stringValue(value) === "yes";
}

function operatorStampedNote(value: string, operatorName: string) {
  const note = value.trim().slice(0, 420);
  const stamped = note ? `operator=${operatorName}; ${note}` : `operator=${operatorName}`;
  return stamped.slice(0, 500);
}

function dateInputToUtc(value: FormDataEntryValue | null) {
  const text = stringValue(value).trim();
  if (!text) {
    return null;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return `${text}T00:00:00Z`;
  }
  return text;
}

function parseEvidenceJson(
  value: FormDataEntryValue | null,
): { ok: true; value: Record<string, unknown> } | { ok: false; message: string } {
  const text = stringValue(value).trim();
  if (!text) {
    return { ok: true, value: {} };
  }
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return { ok: true, value: parsed as Record<string, unknown> };
    }
  } catch {
    return { ok: false, message: "Evidence JSON 格式无效。" };
  }
  return { ok: false, message: "Evidence JSON 必须是 object。" };
}

function positiveIntOrNull(value: FormDataEntryValue | null) {
  const parsed = Number.parseInt(stringValue(value), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return parsed;
}

function boundedInt(
  value: FormDataEntryValue | null,
  fallback: number,
  min: number,
  max: number,
) {
  const parsed = Number.parseInt(stringValue(value), 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(min, Math.min(parsed, max));
}

function boundedFloat(
  value: FormDataEntryValue | null,
  fallback: number,
  min: number,
  max: number,
) {
  const parsed = Number.parseFloat(stringValue(value));
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(min, Math.min(parsed, max));
}
