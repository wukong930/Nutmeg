"use server";

import { redirect } from "next/navigation";
import type { Route } from "next";

import {
  recommendationGlobalPlannerResponseSchema,
  recommendationLifecycleMutationResponseSchema,
} from "@/lib/api-contract";

const API_BASE_URL =
  process.env.NUTMEG_API_BASE_URL ??
  process.env.NEXT_PUBLIC_NUTMEG_API_BASE_URL ??
  "http://localhost:8000/api/v1";

const API_TIMEOUT_MS = Number(process.env.NUTMEG_API_TIMEOUT_MS ?? 30000);

const backendMarketTypes = new Set([
  "1x2",
  "cn_handicap_1x2",
  "european_handicap_1x2",
  "correct_score",
]);

export async function retainRecommendationLegAction(formData: FormData): Promise<void> {
  const currentPath = safePath(stringValue(formData.get("current_path")));
  const fixtureId = stringValue(formData.get("fixture_id"));
  const marketType = backendMarketType(stringValue(formData.get("market_type")));
  const outcome = stringValue(formData.get("outcome"));
  const nextRetainedFixtureIds = addRetainedFixture(
    stringValues(formData.getAll("locked_fixture")),
    fixtureId,
  );
  let recommendationRunId = positiveInteger(stringValue(formData.get("recommendation_run_id")));
  let retentionSource = "url_constraint";

  if (fixtureId && marketType && outcome) {
    const generatedRunId = await createPersistentRecommendationRun(formData);
    if (generatedRunId !== null) {
      recommendationRunId = generatedRunId;
      const retained = await retainLegInLifecycle({
        recommendationRunId: generatedRunId,
        fixtureId,
        marketType,
        outcome,
      });
      if (retained) {
        retentionSource = "lifecycle_api";
      }
    }
  }

  redirect(
    recommendationRedirectUrl(currentPath, formData, {
      retainedFixtureIds: nextRetainedFixtureIds,
      recommendationRunId,
      retentionSource,
    }) as Route,
  );
}

export async function releaseRecommendationLegAction(formData: FormData): Promise<void> {
  const currentPath = safePath(stringValue(formData.get("current_path")));
  const fixtureId = stringValue(formData.get("fixture_id"));
  const marketType = backendMarketType(stringValue(formData.get("market_type")));
  const outcome = stringValue(formData.get("outcome"));
  const recommendationRunId = positiveInteger(stringValue(formData.get("recommendation_run_id")));
  let retentionSource = "url_constraint";

  if (recommendationRunId !== undefined && fixtureId && marketType && outcome) {
    const released = await releaseLegInLifecycle({
      recommendationRunId,
      fixtureId,
      marketType,
      outcome,
    });
    if (released) {
      retentionSource = "lifecycle_api";
    }
  }

  redirect(
    recommendationRedirectUrl(currentPath, formData, {
      retainedFixtureIds: removeRetainedFixture(
        stringValues(formData.getAll("locked_fixture")),
        fixtureId,
      ),
      recommendationRunId,
      retentionSource,
    }) as Route,
  );
}

async function createPersistentRecommendationRun(formData: FormData) {
  const adminToken = process.env.NUTMEG_ADMIN_API_TOKEN;
  if (!adminToken) {
    return null;
  }
  const response = await adminApiRequest(
    "/recommendations/global-best",
    {
      as_of_time_utc: new Date().toISOString(),
      strategy: backendStrategy(stringValue(formData.get("strategy"))),
      unit_stake: positiveNumber(stringValue(formData.get("unit_stake")), 2),
      max_budget: positiveNumber(stringValue(formData.get("max_budget")), 20),
      allowed_markets: backendAllowedMarkets(stringValues(formData.getAll("allowed_market"))),
      pass_types: [backendPassType(stringValue(formData.get("pass_type")))],
      modes: stringValue(formData.get("allow_multiple")) === "false"
        ? ["single"]
        : ["single", "multiple"],
      locked_fixture_ids: stringValues(formData.getAll("locked_fixture")),
      min_probability: 0.2,
      min_data_quality_score: 50,
      candidate_limit: 300,
      require_odds: true,
      max_outcomes_per_fixture: 2,
      min_marginal_quality_gain: 0,
      dry_run: false,
    },
    recommendationGlobalPlannerResponseSchema,
    adminToken,
  );
  return response?.result.stored_run?.recommendation_run_id ?? null;
}

async function retainLegInLifecycle({
  recommendationRunId,
  fixtureId,
  marketType,
  outcome,
}: {
  recommendationRunId: number;
  fixtureId: string;
  marketType: string;
  outcome: string;
}) {
  const adminToken = process.env.NUTMEG_ADMIN_API_TOKEN;
  if (!adminToken) {
    return false;
  }
  const response = await adminApiRequest(
    `/recommendations/${recommendationRunId}/lock-leg`,
    {
      fixture_id: fixtureId,
      market_type: marketType,
      outcome,
      reason_code: "user_retained_leg",
      metadata_json: {
        source: "answer_board",
        copy_surface: "retain",
      },
    },
    recommendationLifecycleMutationResponseSchema,
    adminToken,
  );
  return response !== null;
}

async function releaseLegInLifecycle({
  recommendationRunId,
  fixtureId,
  marketType,
  outcome,
}: {
  recommendationRunId: number;
  fixtureId: string;
  marketType: string;
  outcome: string;
}) {
  const adminToken = process.env.NUTMEG_ADMIN_API_TOKEN;
  if (!adminToken) {
    return false;
  }
  const response = await adminApiRequest(
    `/recommendations/${recommendationRunId}/release-leg`,
    {
      fixture_id: fixtureId,
      market_type: marketType,
      outcome,
      reason_code: "user_released_leg",
      metadata_json: {
        source: "answer_board",
        copy_surface: "release",
      },
    },
    recommendationLifecycleMutationResponseSchema,
    adminToken,
  );
  return response !== null;
}

async function adminApiRequest<T>(
  path: string,
  body: Record<string, unknown>,
  schema: { parse: (value: unknown) => T },
  adminToken: string,
) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        "X-Nutmeg-Admin-Token": adminToken,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      return null;
    }
    return schema.parse(await response.json());
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function recommendationRedirectUrl(
  currentPath: string,
  formData: FormData,
  {
    retainedFixtureIds,
    recommendationRunId,
    retentionSource,
  }: {
    retainedFixtureIds: string[];
    recommendationRunId?: number;
    retentionSource: string;
  },
) {
  const params = new URLSearchParams();
  params.set("pass_type", stringValue(formData.get("pass_type")) || "all");
  params.set("unit_stake", String(positiveNumber(stringValue(formData.get("unit_stake")), 2)));
  params.set("max_budget", String(positiveNumber(stringValue(formData.get("max_budget")), 20)));
  params.set("allow_multiple", stringValue(formData.get("allow_multiple")) || "true");
  for (const market of stringValues(formData.getAll("allowed_market"))) {
    params.append("allowed_market", market);
  }
  for (const fixtureId of retainedFixtureIds) {
    params.append("locked_fixture", fixtureId);
  }
  if (recommendationRunId !== undefined) {
    params.set("recommendation_run_id", String(recommendationRunId));
  }
  params.set("retention_source", retentionSource);
  return `${currentPath}?${params.toString()}`;
}

function addRetainedFixture(currentFixtureIds: string[], fixtureId: string) {
  return [...new Set([...currentFixtureIds, fixtureId].filter(Boolean))];
}

function removeRetainedFixture(currentFixtureIds: string[], fixtureId: string) {
  return currentFixtureIds.filter((currentFixtureId) => currentFixtureId !== fixtureId);
}

function backendStrategy(strategy: string) {
  const strategies: Record<string, string> = {
    budget_optimized: "budget_constrained",
    hit_rate_first: "accuracy_first",
    value_first: "value_first",
    upset_protection: "upset_protection",
    balanced: "auto",
  };
  return strategies[strategy] ?? "auto";
}

function backendPassType(passType: string) {
  if (passType === "all" || /^[1-8]x1$/.test(passType)) {
    return passType;
  }
  return "all";
}

function backendAllowedMarkets(markets: string[]) {
  const allowed = markets.filter((market) => backendMarketTypes.has(market));
  return allowed.length > 0 ? allowed : ["1x2", "cn_handicap_1x2"];
}

function backendMarketType(value: string) {
  if (backendMarketTypes.has(value)) {
    return value;
  }
  const map: Record<string, string> = {
    "1X2": "1x2",
    "胜平负": "1x2",
    "让球胜平负": "cn_handicap_1x2",
    "中国让球": "cn_handicap_1x2",
    "欧洲让球": "european_handicap_1x2",
    "比分": "correct_score",
  };
  return map[value] ?? "1x2";
}

function safePath(value: string) {
  if (value === "/parlays" || value === "/dashboard") {
    return value;
  }
  return "/dashboard";
}

function stringValue(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value : "";
}

function stringValues(values: FormDataEntryValue[]) {
  return values.filter((value): value is string => typeof value === "string" && value.length > 0);
}

function positiveNumber(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function positiveInteger(value: string) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}
