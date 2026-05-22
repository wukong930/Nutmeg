import type { ParlayTicketRequestOptions } from "@/lib/api";

export function parlayOptionsFromParams(
  params: Record<string, string | string[] | undefined> | undefined,
): ParlayTicketRequestOptions {
  return {
    passType: firstParam(params?.pass_type) ?? "all",
    strategy: firstParam(params?.strategy) ?? "budget_optimized",
    unitStake: positiveNumber(firstParam(params?.unit_stake), 2),
    maxBudget: positiveNumber(firstParam(params?.max_budget), 20),
    allowMultiple: firstParam(params?.allow_multiple) !== "false",
    allowedMarkets: arrayParam(params?.allowed_market),
    excludeBetaCompetitions: firstParam(params?.exclude_beta) === "true",
    lockedFixtureIds: arrayParam(params?.locked_fixture),
    recommendationRunId: positiveInteger(firstParam(params?.recommendation_run_id)),
    retentionSource: firstParam(params?.retention_source),
  };
}

export function firstParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function arrayParam(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value;
  }
  return value ? [value] : undefined;
}

function positiveNumber(value: string | undefined, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function positiveInteger(value: string | undefined) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}
