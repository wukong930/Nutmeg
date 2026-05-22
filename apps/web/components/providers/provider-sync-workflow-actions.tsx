"use client";

import {
  AlertCircle,
  Archive,
  Clock3,
  FileJson,
  Pencil,
  PlayCircle,
  Plus,
  RefreshCw,
  Rows3,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Fragment, useActionState, useState } from "react";

import {
  archiveProviderSyncWorkflowTemplateAction,
  preflightProviderSyncWorkflowAction,
  runProviderSyncWorkflowDryRunAction,
  saveProviderSyncWorkflowTemplateAction,
  updateProviderSyncWorkflowTemplateAction,
} from "@/app/providers/actions";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import type {
  ProviderSyncWorkflowRun,
  ProviderSyncWorkflowApproval,
  ProviderSyncWorkflowTemplate,
} from "@/types/api";

type ProviderOpsActionState = {
  status: "idle" | "success" | "error";
  message: string;
};

const initialActionState: ProviderOpsActionState = {
  status: "idle",
  message: "",
};

type OddsTaskState = {
  sportKey: string;
  providerEventId: string;
  canonicalFixtureId: string;
  regions: string;
  markets: string;
  bookmakers: string;
};

type AvailabilityTaskState = {
  providerFixtureId: string;
  canonicalFixtureId: string;
  teamMappings: string;
};

type TemplatePreflightIssue =
  ProviderSyncWorkflowTemplate["preflightResult"]["issues"][number];

type TemplateReviewField = {
  label: string;
  value: unknown;
};

type WorkflowFormState = {
  templateName: string;
  templateDescription: string;
  fixtureProviderCompetitionId: string;
  fixtureSeason: string;
  fixtureCanonicalCompetitionId: string;
  oddsTasks: OddsTaskState[];
  availabilityTasks: AvailabilityTaskState[];
  runConflictDetection: boolean;
  conflictObservationLookbackHours: string;
  conflictLimit: string;
  dryRunAck: boolean;
  dryRunApprovalNote: string;
};

function emptyOddsTask(): OddsTaskState {
  return {
    sportKey: "",
    providerEventId: "",
    canonicalFixtureId: "",
    regions: "eu",
    markets: "h2h,spreads",
    bookmakers: "",
  };
}

function emptyAvailabilityTask(): AvailabilityTaskState {
  return {
    providerFixtureId: "",
    canonicalFixtureId: "",
    teamMappings: "",
  };
}

const initialWorkflowFormState: WorkflowFormState = {
  templateName: "",
  templateDescription: "",
  fixtureProviderCompetitionId: "",
  fixtureSeason: "",
  fixtureCanonicalCompetitionId: "",
  oddsTasks: [emptyOddsTask()],
  availabilityTasks: [emptyAvailabilityTask()],
  runConflictDetection: false,
  conflictObservationLookbackHours: "168",
  conflictLimit: "1000",
  dryRunAck: false,
  dryRunApprovalNote: "",
};

export function ProviderSyncWorkflowActions({
  fetched,
  runs,
  templatesFetched,
  templates,
  approvalsFetched,
  approvals,
}: {
  fetched: boolean;
  runs: ProviderSyncWorkflowRun[];
  templatesFetched: boolean;
  templates: ProviderSyncWorkflowTemplate[];
  approvalsFetched: boolean;
  approvals: ProviderSyncWorkflowApproval[];
}) {
  const [state, action, pending] = useActionState(
    runProviderSyncWorkflowDryRunAction,
    initialActionState,
  );
  const [preflightState, preflightAction, preflightPending] = useActionState(
    preflightProviderSyncWorkflowAction,
    initialActionState,
  );
  const [templateState, templateAction, templatePending] = useActionState(
    saveProviderSyncWorkflowTemplateAction,
    initialActionState,
  );
  const [updateTemplateState, updateTemplateAction, updateTemplatePending] =
    useActionState(updateProviderSyncWorkflowTemplateAction, initialActionState);
  const [archiveTemplateState, archiveTemplateAction, archiveTemplatePending] =
    useActionState(archiveProviderSyncWorkflowTemplateAction, initialActionState);
  const [formState, setFormState] = useState<WorkflowFormState>(
    initialWorkflowFormState,
  );
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const selectedTemplate =
    templates.find(
      (template) =>
        String(template.providerSyncWorkflowTemplateId) === selectedTemplateId,
    ) ?? null;

  function updateField<Key extends keyof WorkflowFormState>(
    key: Key,
    value: WorkflowFormState[Key],
  ) {
    setFormState((current) => ({ ...current, [key]: value }));
  }

  function updateOddsTask<Key extends keyof OddsTaskState>(
    index: number,
    key: Key,
    value: OddsTaskState[Key],
  ) {
    setFormState((current) => ({
      ...current,
      oddsTasks: current.oddsTasks.map((task, taskIndex) =>
        taskIndex === index ? { ...task, [key]: value } : task,
      ),
    }));
  }

  function addOddsTask() {
    setFormState((current) => ({
      ...current,
      oddsTasks: [...current.oddsTasks, emptyOddsTask()],
    }));
  }

  function removeOddsTask(index: number) {
    setFormState((current) => {
      const remaining = current.oddsTasks.filter((_, taskIndex) => taskIndex !== index);
      return {
        ...current,
        oddsTasks: remaining.length > 0 ? remaining : [emptyOddsTask()],
      };
    });
  }

  function updateAvailabilityTask<Key extends keyof AvailabilityTaskState>(
    index: number,
    key: Key,
    value: AvailabilityTaskState[Key],
  ) {
    setFormState((current) => ({
      ...current,
      availabilityTasks: current.availabilityTasks.map((task, taskIndex) =>
        taskIndex === index ? { ...task, [key]: value } : task,
      ),
    }));
  }

  function addAvailabilityTask() {
    setFormState((current) => ({
      ...current,
      availabilityTasks: [...current.availabilityTasks, emptyAvailabilityTask()],
    }));
  }

  function removeAvailabilityTask(index: number) {
    setFormState((current) => {
      const remaining = current.availabilityTasks.filter(
        (_, taskIndex) => taskIndex !== index,
      );
      return {
        ...current,
        availabilityTasks:
          remaining.length > 0 ? remaining : [emptyAvailabilityTask()],
      };
    });
  }

  function loadTemplate(template: ProviderSyncWorkflowTemplate) {
    setSelectedTemplateId(String(template.providerSyncWorkflowTemplateId));
    setFormState(formStateFromTemplate(template));
  }

  function loadSelectedTemplate() {
    if (selectedTemplate) {
      loadTemplate(selectedTemplate);
    }
  }

  return (
    <div className="provider-sync-workflow-grid">
      <form
        action={action}
        className="provider-sync-form"
        aria-label="Provider Sync Workflow dry-run"
      >
        <input name="selected_template_id" type="hidden" value={selectedTemplateId} />
        <div className="provider-action-summary">
          <span className="provider-action-title">Provider Sync Workflow</span>
          <Badge tone="info">dry-run only</Badge>
          <Badge>exact IDs</Badge>
        </div>

        <fieldset className="provider-fieldset provider-template-fieldset">
          <legend>
            <Save size={14} aria-hidden="true" /> Run template
          </legend>
          <div className="provider-template-load-row">
            <label className="control">
              <span>Saved template</span>
              <select
                value={selectedTemplateId}
                onChange={(event) => setSelectedTemplateId(event.target.value)}
              >
                <option value="">Select saved template</option>
                {templates.map((template) => (
                  <option
                    key={template.providerSyncWorkflowTemplateId}
                    value={template.providerSyncWorkflowTemplateId}
                  >
                    {template.templateName}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="toolbar-button"
              type="button"
              onClick={loadSelectedTemplate}
              disabled={!selectedTemplate}
            >
              <FileJson size={15} aria-hidden="true" />
              Load template
            </button>
          </div>
          <label className="control">
            <span>Template name</span>
            <input
              name="template_name"
              placeholder="EPL explicit IDs dry-run"
              value={formState.templateName}
              onChange={(event) => updateField("templateName", event.target.value)}
            />
          </label>
          <label className="control">
            <span>Description</span>
            <input
              name="template_description"
              placeholder="operator-reviewed IDs"
              value={formState.templateDescription}
              onChange={(event) =>
                updateField("templateDescription", event.target.value)
              }
            />
          </label>
        </fieldset>

        <div className="provider-sync-task-grid">
          <fieldset className="provider-fieldset">
            <legend>
              <RefreshCw size={14} aria-hidden="true" /> Fixture
            </legend>
            <label className="control">
              <span>Provider competition</span>
              <input
                name="fixture_provider_competition_id"
                placeholder="PL"
                value={formState.fixtureProviderCompetitionId}
                onChange={(event) =>
                  updateField("fixtureProviderCompetitionId", event.target.value)
                }
              />
            </label>
            <label className="control">
              <span>Season</span>
              <input
                name="fixture_season"
                placeholder="2025"
                value={formState.fixtureSeason}
                onChange={(event) => updateField("fixtureSeason", event.target.value)}
              />
            </label>
            <label className="control">
              <span>Canonical competition</span>
              <input
                name="fixture_canonical_competition_id"
                placeholder="EPL"
                value={formState.fixtureCanonicalCompetitionId}
                onChange={(event) =>
                  updateField("fixtureCanonicalCompetitionId", event.target.value)
                }
              />
            </label>
          </fieldset>

          <fieldset className="provider-fieldset">
            <legend>
              <Rows3 size={14} aria-hidden="true" /> Odds
            </legend>
            <input
              name="odds_task_count"
              type="hidden"
              value={formState.oddsTasks.length}
            />
            <div className="provider-task-list">
              {formState.oddsTasks.map((task, index) => (
                <div className="provider-task-card" key={`odds-${index}`}>
                  <div className="provider-task-card-header">
                    <span className="provider-task-title">Odds task {index + 1}</span>
                    <button
                      aria-label={`Remove odds task ${index + 1}`}
                      className="toolbar-button provider-task-remove"
                      type="button"
                      onClick={() => removeOddsTask(index)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      Remove odds task
                    </button>
                  </div>
                  <label className="control">
                    <span>Sport key {index + 1}</span>
                    <input
                      name={`odds_${index}_sport_key`}
                      placeholder="soccer_epl"
                      value={task.sportKey}
                      onChange={(event) =>
                        updateOddsTask(index, "sportKey", event.target.value)
                      }
                    />
                  </label>
                  <label className="control">
                    <span>Provider event {index + 1}</span>
                    <input
                      name={`odds_${index}_provider_event_id`}
                      placeholder="event-id"
                      value={task.providerEventId}
                      onChange={(event) =>
                        updateOddsTask(index, "providerEventId", event.target.value)
                      }
                    />
                  </label>
                  <label className="control">
                    <span>Canonical fixture {index + 1}</span>
                    <input
                      name={`odds_${index}_canonical_fixture_id`}
                      placeholder="fd_fixture_123"
                      value={task.canonicalFixtureId}
                      onChange={(event) =>
                        updateOddsTask(index, "canonicalFixtureId", event.target.value)
                      }
                    />
                  </label>
                  <label className="control">
                    <span>Regions {index + 1}</span>
                    <input
                      name={`odds_${index}_regions`}
                      placeholder="eu"
                      value={task.regions}
                      onChange={(event) =>
                        updateOddsTask(index, "regions", event.target.value)
                      }
                    />
                  </label>
                  <label className="control">
                    <span>Markets {index + 1}</span>
                    <input
                      name={`odds_${index}_markets`}
                      value={task.markets}
                      onChange={(event) =>
                        updateOddsTask(index, "markets", event.target.value)
                      }
                    />
                  </label>
                  <label className="control">
                    <span>Bookmakers {index + 1}</span>
                    <input
                      name={`odds_${index}_bookmakers`}
                      placeholder="optional"
                      value={task.bookmakers}
                      onChange={(event) =>
                        updateOddsTask(index, "bookmakers", event.target.value)
                      }
                    />
                  </label>
                </div>
              ))}
            </div>
            <div className="provider-task-add-row">
              <button className="toolbar-button" type="button" onClick={addOddsTask}>
                <Plus size={15} aria-hidden="true" />
                Add odds task
              </button>
            </div>
          </fieldset>

          <fieldset className="provider-fieldset">
            <legend>
              <Clock3 size={14} aria-hidden="true" /> Availability
            </legend>
            <input
              name="availability_task_count"
              type="hidden"
              value={formState.availabilityTasks.length}
            />
            <div className="provider-task-list">
              {formState.availabilityTasks.map((task, index) => (
                <div className="provider-task-card" key={`availability-${index}`}>
                  <div className="provider-task-card-header">
                    <span className="provider-task-title">
                      Availability task {index + 1}
                    </span>
                    <button
                      aria-label={`Remove availability task ${index + 1}`}
                      className="toolbar-button provider-task-remove"
                      type="button"
                      onClick={() => removeAvailabilityTask(index)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      Remove availability task
                    </button>
                  </div>
                  <label className="control">
                    <span>Provider fixture {index + 1}</span>
                    <input
                      name={`availability_${index}_provider_fixture_id`}
                      placeholder="sportmonks-fixture-id"
                      value={task.providerFixtureId}
                      onChange={(event) =>
                        updateAvailabilityTask(
                          index,
                          "providerFixtureId",
                          event.target.value,
                        )
                      }
                    />
                  </label>
                  <label className="control">
                    <span>Availability canonical fixture {index + 1}</span>
                    <input
                      name={`availability_${index}_canonical_fixture_id`}
                      placeholder="fd_fixture_123"
                      value={task.canonicalFixtureId}
                      onChange={(event) =>
                        updateAvailabilityTask(
                          index,
                          "canonicalFixtureId",
                          event.target.value,
                        )
                      }
                    />
                  </label>
                  <label className="control provider-textarea-control">
                    <span>Team mappings {index + 1}</span>
                    <textarea
                      name={`availability_${index}_team_mappings`}
                      placeholder={"57=fd_team_57\n64=fd_team_64"}
                      rows={3}
                      value={task.teamMappings}
                      onChange={(event) =>
                        updateAvailabilityTask(
                          index,
                          "teamMappings",
                          event.target.value,
                        )
                      }
                    />
                  </label>
                </div>
              ))}
            </div>
            <div className="provider-task-add-row">
              <button
                className="toolbar-button"
                type="button"
                onClick={addAvailabilityTask}
              >
                <Plus size={15} aria-hidden="true" />
                Add availability task
              </button>
            </div>
          </fieldset>
        </div>

        <div className="toolbar provider-action-form">
          <label className="provider-checkbox-control">
            <input
              name="run_conflict_detection"
              type="checkbox"
              value="yes"
              checked={formState.runConflictDetection}
              onChange={(event) =>
                updateField("runConflictDetection", event.target.checked)
              }
            />
            conflict detection
          </label>
          <label className="control">
            <span>Lookback h</span>
            <input
              name="conflict_observation_lookback_hours"
              type="number"
              min={1}
              max={8760}
              value={formState.conflictObservationLookbackHours}
              onChange={(event) =>
                updateField("conflictObservationLookbackHours", event.target.value)
              }
            />
          </label>
          <label className="control">
            <span>Conflict limit</span>
            <input
              name="conflict_limit"
              type="number"
              min={1}
              max={5000}
              value={formState.conflictLimit}
              onChange={(event) => updateField("conflictLimit", event.target.value)}
            />
          </label>
          <label className="provider-checkbox-control">
            <input
              name="dry_run_ack"
              type="checkbox"
              value="yes"
              checked={formState.dryRunAck}
              onChange={(event) => updateField("dryRunAck", event.target.checked)}
            />
            operator approved dry-run
          </label>
          <label className="control provider-approval-note-control">
            <span>Approval note</span>
            <input
              name="dry_run_approval_note"
              placeholder="operator-reviewed IDs"
              value={formState.dryRunApprovalNote}
              onChange={(event) =>
                updateField("dryRunApprovalNote", event.target.value)
              }
            />
          </label>
          <button
            className="toolbar-button"
            type="submit"
            formAction={preflightAction}
            disabled={preflightPending}
          >
            <ShieldCheck size={15} aria-hidden="true" />
            Preflight
          </button>
          <button
            className="toolbar-button"
            type="submit"
            formAction={templateAction}
            disabled={templatePending}
          >
            <Save size={15} aria-hidden="true" />
            Save template
          </button>
          <button
            className="toolbar-button"
            type="submit"
            formAction={updateTemplateAction}
            disabled={!selectedTemplate || updateTemplatePending}
          >
            <Pencil size={15} aria-hidden="true" />
            Update selected
          </button>
          <button className="toolbar-button" type="submit" disabled={pending}>
            <PlayCircle size={15} aria-hidden="true" />
            Dry-run workflow
          </button>
        </div>
        <ActionMessage state={preflightState} />
        <ActionMessage state={templateState} />
        <ActionMessage state={updateTemplateState} />
        <ActionMessage state={archiveTemplateState} />
        <ActionMessage state={state} />
      </form>

      <TemplateList
        fetched={templatesFetched}
        templates={templates}
        onLoadTemplate={loadTemplate}
        archiveAction={archiveTemplateAction}
        archivePending={archiveTemplatePending}
      />

      <ApprovalList fetched={approvalsFetched} approvals={approvals} />

      <div className="ui-table-wrap">
        <table className="ui-table">
          <caption>Workflow run history and Run detail / error payload.</caption>
          <thead>
            <tr>
              <th>Run</th>
              <th>状态</th>
              <th>Dry</th>
              <th>Started</th>
              <th>Counts</th>
              <th>Fixtures</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {runs.length > 0 ? (
              runs.map((run) => (
                <Fragment key={run.providerSyncWorkflowRunId}>
                  <tr>
                    <td className="mono">#{run.providerSyncWorkflowRunId}</td>
                    <td>
                      <Badge tone={workflowStatusTone(run.status)}>{run.status}</Badge>
                    </td>
                    <td>{run.dryRun ? "yes" : "no"}</td>
                    <td>{formatDateTime(run.startedAtUtc)}</td>
                    <td className="mono">{workflowRunCounts(run)}</td>
                    <td className="provider-id-cell">
                      {run.canonicalFixtureIds.join(", ") || "N/A"}
                    </td>
                    <td className="provider-id-cell">
                      {run.errorMessage ?? (run.warnings.join(", ") || "N/A")}
                    </td>
                  </tr>
                  <tr className="provider-run-detail-row">
                    <td colSpan={7}>
                      <RunDetail run={run} />
                    </td>
                  </tr>
                </Fragment>
              ))
            ) : (
              <tr>
                <td className="ui-table-empty" colSpan={7}>
                  {fetched ? "暂无 workflow run" : "Workflow run history unavailable"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TemplateList({
  fetched,
  templates,
  onLoadTemplate,
  archiveAction,
  archivePending,
}: {
  fetched: boolean;
  templates: ProviderSyncWorkflowTemplate[];
  onLoadTemplate: (template: ProviderSyncWorkflowTemplate) => void;
  archiveAction: (payload: FormData) => void;
  archivePending: boolean;
}) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>
          Provider sync run templates, Archive controls, Template task review matrix,
          and scoped preflight issues.
        </caption>
        <thead>
          <tr>
            <th>Template</th>
            <th>Preflight</th>
            <th>Tasks</th>
            <th>Fixtures</th>
            <th>Updated</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {templates.length > 0 ? (
            templates.map((template) => (
              <Fragment key={template.providerSyncWorkflowTemplateId}>
                <tr>
                  <td>
                    <span className="provider-action-title">{template.templateName}</span>
                    <div className="meta">{template.description ?? "No description"}</div>
                  </td>
                  <td>
                    <Badge tone={template.preflightResult.valid ? "success" : "risk"}>
                      {template.preflightResult.valid ? "valid" : "needs review"}
                    </Badge>
                    <div className="provider-template-issue-strip">
                      <Badge tone="neutral">tasks {template.preflightResult.taskCount}</Badge>
                      <Badge tone={template.preflightResult.errorCount > 0 ? "risk" : "neutral"}>
                        errors {template.preflightResult.errorCount}
                      </Badge>
                      <Badge
                        tone={
                          template.preflightResult.warningCount > 0
                            ? "warning"
                            : "neutral"
                        }
                      >
                        warnings {template.preflightResult.warningCount}
                      </Badge>
                      <Badge tone="neutral">info {template.preflightResult.infoCount}</Badge>
                    </div>
                  </td>
                  <td className="mono">
                    <div className="provider-task-counts">
                      <span>odds {template.oddsSyncs.length}</span>
                      <span>availability {template.availabilitySyncs.length}</span>
                    </div>
                    <div>{template.preflightResult.syncTypes.join(", ") || "N/A"}</div>
                  </td>
                  <td className="provider-id-cell">
                    {template.preflightResult.canonicalFixtureIds.join(", ") || "N/A"}
                  </td>
                  <td>{formatDateTime(template.updatedAtUtc)}</td>
                  <td>
                    <div className="provider-template-actions">
                      <button
                        className="toolbar-button"
                        type="button"
                        onClick={() => onLoadTemplate(template)}
                      >
                        <FileJson size={15} aria-hidden="true" />
                        Load template
                      </button>
                      <form action={archiveAction} className="provider-template-archive-form">
                        <input
                          name="archive_template_id"
                          type="hidden"
                          value={template.providerSyncWorkflowTemplateId}
                        />
                        <label className="provider-checkbox-control">
                          <input
                            name="archive_template_ack"
                            type="checkbox"
                            value="yes"
                          />
                          archive approved
                        </label>
                        <input
                          name="archive_reason"
                          placeholder="reason"
                          aria-label="Archive reason"
                        />
                        <button
                          className="toolbar-button"
                          type="submit"
                          disabled={archivePending}
                        >
                          <Archive size={15} aria-hidden="true" />
                          Archive
                        </button>
                      </form>
                    </div>
                  </td>
                </tr>
                <tr className="provider-run-detail-row">
                  <td colSpan={6}>
                    <details className="provider-run-details">
                      <summary>
                        <FileJson size={14} aria-hidden="true" />
                        Template payload
                      </summary>
                      <TemplateTaskReview template={template} />
                      <div className="provider-run-detail-grid">
                        <div className="provider-run-detail-block">
                          <span className="provider-run-detail-title">Fixture</span>
                          <JsonPreview value={template.fixtureSync} />
                        </div>
                        <div className="provider-run-detail-block">
                          <span className="provider-run-detail-title">Odds</span>
                          <JsonPreview value={template.oddsSyncs} />
                        </div>
                        <div className="provider-run-detail-block">
                          <span className="provider-run-detail-title">Availability</span>
                          <JsonPreview value={template.availabilitySyncs} />
                        </div>
                        <div className="provider-run-detail-block">
                          <span className="provider-run-detail-title">Preflight issues</span>
                          {template.preflightResult.issues.length > 0 ? (
                            <ul className="provider-run-warning-list">
                              {template.preflightResult.issues.map((issue) => (
                                <li key={`${issue.code}:${issue.fieldPath ?? ""}`}>
                                  {issue.severity}:{issue.code}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="provider-run-empty">No issues recorded.</p>
                          )}
                        </div>
                      </div>
                    </details>
                  </td>
                </tr>
              </Fragment>
            ))
          ) : (
            <tr>
              <td className="ui-table-empty" colSpan={6}>
                {fetched ? "暂无 provider sync template" : "Provider sync templates unavailable"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function TemplateTaskReview({
  template,
}: {
  template: ProviderSyncWorkflowTemplate;
}) {
  const taskScopes = templateTaskScopes(template);
  const workflowIssues = template.preflightResult.issues.filter(
    (issue) =>
      !issue.fieldPath ||
      !taskScopes.some((scope) => issue.fieldPath?.startsWith(scope)),
  );
  return (
    <div
      className="provider-template-review"
      aria-label="Template task review matrix"
    >
      <div className="provider-template-review-header">
        <span className="provider-run-detail-title">Template task review matrix</span>
        <div className="provider-review-strip">
          <Badge tone={template.preflightResult.valid ? "success" : "risk"}>
            preflight {template.preflightResult.valid ? "valid" : "needs review"}
          </Badge>
          <Badge>task count {template.preflightResult.taskCount}</Badge>
          <Badge>fixture IDs {template.preflightResult.canonicalFixtureIds.length}</Badge>
        </div>
      </div>
      <div className="provider-template-review-grid">
        {template.fixtureSync ? (
          <TemplateTaskReviewBlock
            title="Fixture sync"
            scope="fixture_sync"
            fields={fixtureReviewFields(template.fixtureSync)}
            issues={templateIssuesForScope(
              template.preflightResult.issues,
              "fixture_sync",
            )}
          />
        ) : null}
        {template.oddsSyncs.map((task, index) => (
          <TemplateTaskReviewBlock
            key={`template-odds-${index}`}
            title={`Odds sync ${index + 1}`}
            scope={`odds_syncs[${index}]`}
            fields={oddsReviewFields(task)}
            issues={templateIssuesForScope(
              template.preflightResult.issues,
              `odds_syncs[${index}]`,
            )}
          />
        ))}
        {template.availabilitySyncs.map((task, index) => (
          <TemplateTaskReviewBlock
            key={`template-availability-${index}`}
            title={`Availability sync ${index + 1}`}
            scope={`availability_syncs[${index}]`}
            fields={availabilityReviewFields(task)}
            issues={templateIssuesForScope(
              template.preflightResult.issues,
              `availability_syncs[${index}]`,
            )}
          />
        ))}
        <TemplateTaskReviewBlock
          title="Workflow preflight summary"
          scope="workflow"
          fields={workflowReviewFields(template)}
          issues={workflowIssues}
          emptyIssueText="No workflow-level issues recorded."
        />
      </div>
    </div>
  );
}

function TemplateTaskReviewBlock({
  title,
  scope,
  fields,
  issues,
  emptyIssueText = "No task issues recorded.",
}: {
  title: string;
  scope: string;
  fields: TemplateReviewField[];
  issues: TemplatePreflightIssue[];
  emptyIssueText?: string;
}) {
  return (
    <section className="provider-template-review-block" aria-label={title}>
      <div className="provider-task-card-header">
        <span className="provider-task-title">{title}</span>
        <Badge tone={issues.length > 0 ? "warning" : "success"}>
          Task preflight issues {issues.length}
        </Badge>
      </div>
      <dl className="provider-template-review-list">
        <DetailItem label="scope" value={scope} />
        {fields.map((field) => (
          <DetailItem key={field.label} label={field.label} value={field.value} />
        ))}
      </dl>
      <TemplateIssueList issues={issues} emptyText={emptyIssueText} />
    </section>
  );
}

function TemplateIssueList({
  issues,
  emptyText,
}: {
  issues: TemplatePreflightIssue[];
  emptyText: string;
}) {
  if (issues.length === 0) {
    return <p className="provider-run-empty">{emptyText}</p>;
  }
  return (
    <ul className="provider-template-issue-list">
      {issues.map((issue, index) => (
        <li key={`${issue.code}:${issue.fieldPath ?? "global"}:${index}`}>
          <Badge tone={preflightIssueTone(issue.severity)}>{issue.severity}</Badge>
          <span className="provider-template-issue-text">
            {issue.code}
            {issue.fieldPath ? ` @ ${issue.fieldPath}` : ""}: {issue.message}
          </span>
        </li>
      ))}
    </ul>
  );
}

function preflightIssueTone(issueSeverity: TemplatePreflightIssue["severity"]) {
  if (issueSeverity === "error") return "risk";
  if (issueSeverity === "warning") return "warning";
  return "info";
}

function fixtureReviewFields(record: Record<string, unknown>): TemplateReviewField[] {
  return [
    {
      label: "provider_competition_id",
      value: recordString(record, "provider_competition_id") || "N/A",
    },
    { label: "season", value: recordString(record, "season") || "N/A" },
    {
      label: "canonical_competition_id",
      value: recordString(record, "canonical_competition_id") || "N/A",
    },
  ];
}

function oddsReviewFields(record: Record<string, unknown>): TemplateReviewField[] {
  return [
    { label: "sport_key", value: recordString(record, "sport_key") || "N/A" },
    {
      label: "provider_event_id",
      value: recordString(record, "provider_event_id") || "N/A",
    },
    {
      label: "canonical_fixture_id",
      value: recordString(record, "canonical_fixture_id") || "N/A",
    },
    { label: "regions", value: recordString(record, "regions", "eu") },
    { label: "markets", value: recordString(record, "markets", "h2h,spreads") },
    { label: "bookmakers", value: recordString(record, "bookmakers") || "N/A" },
  ];
}

function availabilityReviewFields(
  record: Record<string, unknown>,
): TemplateReviewField[] {
  return [
    {
      label: "provider_fixture_id",
      value: recordString(record, "provider_fixture_id") || "N/A",
    },
    {
      label: "canonical_fixture_id",
      value: recordString(record, "canonical_fixture_id") || "N/A",
    },
    {
      label: "team_mappings_count",
      value: teamMappingsCount(record["team_mappings"]),
    },
  ];
}

function workflowReviewFields(
  template: ProviderSyncWorkflowTemplate,
): TemplateReviewField[] {
  return [
    { label: "sync_types", value: template.preflightResult.syncTypes },
    {
      label: "canonical_fixture_ids",
      value: template.preflightResult.canonicalFixtureIds,
    },
    {
      label: "run_conflict_detection",
      value: template.runConflictDetection,
    },
    {
      label: "conflict_lookback_h",
      value: template.conflictObservationLookbackHours,
    },
    { label: "conflict_limit", value: template.conflictLimit },
  ];
}

function templateTaskScopes(template: ProviderSyncWorkflowTemplate) {
  return [
    ...(template.fixtureSync ? ["fixture_sync"] : []),
    ...template.oddsSyncs.map((_, index) => `odds_syncs[${index}]`),
    ...template.availabilitySyncs.map(
      (_, index) => `availability_syncs[${index}]`,
    ),
  ];
}

function templateIssuesForScope(
  issues: TemplatePreflightIssue[],
  scope: string,
) {
  return issues.filter((issue) => issue.fieldPath?.startsWith(scope));
}

function teamMappingsCount(value: unknown) {
  if (Array.isArray(value)) {
    return value.length;
  }
  if (isRecord(value)) {
    return Object.keys(value).length;
  }
  return 0;
}

function ApprovalList({
  fetched,
  approvals,
}: {
  fetched: boolean;
  approvals: ProviderSyncWorkflowApproval[];
}) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>Provider sync dry-run approval audit.</caption>
        <thead>
          <tr>
            <th>Approval</th>
            <th>Status</th>
            <th>Template</th>
            <th>Run</th>
            <th>Approved</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {approvals.length > 0 ? (
            approvals.map((approval) => (
              <tr key={approval.providerSyncWorkflowApprovalId}>
                <td className="mono">#{approval.providerSyncWorkflowApprovalId}</td>
                <td>
                  <Badge tone={approval.approvalStatus === "approved" ? "success" : "warning"}>
                    {approval.approvalStatus}
                  </Badge>
                </td>
                <td className="mono">
                  {approval.providerSyncWorkflowTemplateId
                    ? `#${approval.providerSyncWorkflowTemplateId}`
                    : "N/A"}
                </td>
                <td className="mono">
                  {approval.providerSyncWorkflowRunId
                    ? `#${approval.providerSyncWorkflowRunId}`
                    : "N/A"}
                </td>
                <td>{formatDateTime(approval.approvedAtUtc)}</td>
                <td className="provider-id-cell">
                  {approval.approvalNote ?? approval.approvedBy ?? "N/A"}
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="ui-table-empty" colSpan={6}>
                {fetched ? "暂无 dry-run approval audit" : "Approval audit unavailable"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function formStateFromTemplate(
  template: ProviderSyncWorkflowTemplate,
): WorkflowFormState {
  return {
    templateName: template.templateName,
    templateDescription: template.description ?? "",
    fixtureProviderCompetitionId: recordString(
      template.fixtureSync,
      "provider_competition_id",
    ),
    fixtureSeason: recordString(template.fixtureSync, "season"),
    fixtureCanonicalCompetitionId: recordString(
      template.fixtureSync,
      "canonical_competition_id",
    ),
    oddsTasks:
      template.oddsSyncs.length > 0
        ? template.oddsSyncs.map(oddsTaskStateFromRecord)
        : [emptyOddsTask()],
    availabilityTasks:
      template.availabilitySyncs.length > 0
        ? template.availabilitySyncs.map(availabilityTaskStateFromRecord)
        : [emptyAvailabilityTask()],
    runConflictDetection: template.runConflictDetection,
    conflictObservationLookbackHours: String(
      template.conflictObservationLookbackHours,
    ),
    conflictLimit: String(template.conflictLimit),
    dryRunAck: false,
    dryRunApprovalNote: "",
  };
}

function oddsTaskStateFromRecord(record: Record<string, unknown>): OddsTaskState {
  return {
    sportKey: recordString(record, "sport_key"),
    providerEventId: recordString(record, "provider_event_id"),
    canonicalFixtureId: recordString(record, "canonical_fixture_id"),
    regions: recordString(record, "regions", "eu"),
    markets: recordString(record, "markets", "h2h,spreads"),
    bookmakers: recordString(record, "bookmakers"),
  };
}

function availabilityTaskStateFromRecord(
  record: Record<string, unknown>,
): AvailabilityTaskState {
  return {
    providerFixtureId: recordString(record, "provider_fixture_id"),
    canonicalFixtureId: recordString(record, "canonical_fixture_id"),
    teamMappings: teamMappingsText(record["team_mappings"]),
  };
}

function recordString(
  record: Record<string, unknown> | null | undefined,
  key: string,
  fallback = "",
) {
  const value = record?.[key];
  if (value === null || value === undefined) {
    return fallback;
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function teamMappingsText(value: unknown) {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (!isRecord(item)) {
          return "";
        }
        const providerTeamId = recordString(item, "provider_team_id");
        const canonicalTeamId = recordString(item, "canonical_team_id");
        return providerTeamId && canonicalTeamId
          ? `${providerTeamId}=${canonicalTeamId}`
          : "";
      })
      .filter(Boolean)
      .join("\n");
  }
  if (isRecord(value)) {
    return Object.entries(value)
      .map(([providerTeamId, canonicalTeamId]) => {
        const canonicalValue =
          typeof canonicalTeamId === "string" || typeof canonicalTeamId === "number"
            ? String(canonicalTeamId)
            : "";
        return canonicalValue ? `${providerTeamId}=${canonicalValue}` : "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function RunDetail({ run }: { run: ProviderSyncWorkflowRun }) {
  const metadataEntries = workflowMetadataEntries(run.metadataJson);
  return (
    <details className="provider-run-details">
      <summary>
        <FileJson size={14} aria-hidden="true" />
        Run detail / error payload
      </summary>
      <div className="provider-run-detail-grid">
        <div className="provider-run-detail-block">
          <span className="provider-run-detail-title">Execution</span>
          <dl className="provider-run-detail-list">
            <DetailItem label="requested_by" value={run.requestedBy ?? "N/A"} />
            <DetailItem
              label="completed"
              value={run.completedAtUtc ? formatDateTime(run.completedAtUtc) : "N/A"}
            />
            <DetailItem label="duration_ms" value={run.durationMs ?? "N/A"} />
            <DetailItem label="fixture_sync_run_id" value={run.fixtureSyncRunId ?? "N/A"} />
            <DetailItem label="odds_sync_run_ids" value={run.oddsSyncRunIds} />
            <DetailItem
              label="availability_sync_run_ids"
              value={run.availabilitySyncRunIds}
            />
            <DetailItem label="raw_payload_ids" value={run.rawPayloadIds} />
            <DetailItem
              label="prematch_workflow_run_id"
              value={run.prematchWorkflowRunId ?? "N/A"}
            />
          </dl>
        </div>

        <div className="provider-run-detail-block">
          <span className="provider-run-detail-title">Audit metadata</span>
          {metadataEntries.length > 0 ? (
            <dl className="provider-run-detail-list">
              {metadataEntries.map(([key, value]) => (
                <DetailItem key={key} label={metadataLabel(key)} value={value} />
              ))}
            </dl>
          ) : (
            <p className="provider-run-empty">No metadata recorded.</p>
          )}
        </div>

        <div className="provider-run-detail-block">
          <span className="provider-run-detail-title">Warnings and errors</span>
          {run.errorMessage ? (
            <p className="provider-run-error">
              <AlertCircle size={14} aria-hidden="true" />
              {run.errorMessage}
            </p>
          ) : null}
          {run.warnings.length > 0 ? (
            <ul className="provider-run-warning-list">
              {run.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : (
            <p className="provider-run-empty">No warnings recorded.</p>
          )}
        </div>
      </div>
    </details>
  );
}

function JsonPreview({ value }: { value: unknown }) {
  return <pre className="provider-json-preview">{formatDetailValue("payload", value)}</pre>;
}

function DetailItem({ label, value }: { label: string; value: unknown }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{formatDetailValue(label, value)}</dd>
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

function workflowStatusTone(status: ProviderSyncWorkflowRun["status"]) {
  if (status === "completed") return "success";
  if (status === "failed") return "risk";
  return "info";
}

function workflowRunCounts(run: ProviderSyncWorkflowRun) {
  return `F${run.fixtureCount} O${run.oddsSnapshotCount} A${run.availabilitySnapshotCount}`;
}

function workflowMetadataEntries(metadata: Record<string, unknown>) {
  return Object.entries(metadata).sort(([left], [right]) => left.localeCompare(right));
}

function metadataLabel(key: string) {
  const labels: Record<string, string> = {
    source: "source",
    fixture_sync_requested: "fixture_sync_requested",
    odds_sync_count: "odds_sync_count",
    availability_sync_count: "availability_sync_count",
    run_prematch_workflow: "run_prematch_workflow",
    run_conflict_detection: "run_conflict_detection",
    conflict_observation_lookback_hours: "conflict_lookback_h",
    conflict_limit: "conflict_limit",
  };
  return labels[key] ?? key;
}

function formatDetailValue(label: string, value: unknown) {
  if (/token|secret|password|api[_-]?key/i.test(label)) {
    return "[redacted]";
  }
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
  if (value === null || value === undefined) {
    return "N/A";
  }
  return JSON.stringify(value);
}
