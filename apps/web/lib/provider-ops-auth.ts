import "server-only";

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

import { cookies } from "next/headers";

const COOKIE_NAME = "nutmeg_provider_ops_session";
const SESSION_TTL_SECONDS = 12 * 60 * 60;

export type ProviderOpsAccessState = {
  configured: boolean;
  unlocked: boolean;
  operatorName: string | null;
  expiresAtUtc: string | null;
};

export type ProviderOpsAuthorizedSession = {
  operatorName: string;
};

export type ProviderOpsAccessCheck =
  | { ok: true; operatorName: string }
  | { ok: false; message: string };

export async function getProviderOpsAccessState(): Promise<ProviderOpsAccessState> {
  const configured = Boolean(accessToken());
  const session = await readSession();
  return {
    configured,
    unlocked: session !== null,
    operatorName: session?.operatorName ?? null,
    expiresAtUtc: session ? new Date(session.expiresAt * 1000).toISOString() : null,
  };
}

export async function requireProviderOpsAccess(): Promise<ProviderOpsAccessCheck> {
  if (!accessToken()) {
    return {
      ok: false,
      message: "Provider Ops UI access token is not configured.",
    };
  }
  const session = await readSession();
  if (!session) {
    return {
      ok: false,
      message: "Provider Ops session required. Unlock the admin controls first.",
    };
  }
  return { ok: true, operatorName: session.operatorName };
}

export async function unlockProviderOpsSession({
  token,
  operatorName,
}: {
  token: string;
  operatorName: string;
}): Promise<ProviderOpsAccessCheck> {
  const configuredToken = accessToken();
  if (!configuredToken) {
    return {
      ok: false,
      message: "Provider Ops UI access token is not configured.",
    };
  }
  if (!constantTimeEquals(token, configuredToken)) {
    return { ok: false, message: "Provider Ops access token is invalid." };
  }

  const safeOperatorName = sanitizeOperatorName(operatorName);
  const issuedAt = Math.floor(Date.now() / 1000);
  const expiresAt = issuedAt + SESSION_TTL_SECONDS;
  const payload = JSON.stringify({
    operatorName: safeOperatorName,
    issuedAt,
    expiresAt,
    nonce: randomBytes(12).toString("hex"),
  });
  const encodedPayload = base64UrlEncode(payload);
  const cookieValue = `${encodedPayload}.${signature(encodedPayload, configuredToken)}`;
  const cookieStore = await cookies();
  cookieStore.set({
    name: COOKIE_NAME,
    value: cookieValue,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/providers",
    maxAge: SESSION_TTL_SECONDS,
  });
  return { ok: true, operatorName: safeOperatorName };
}

export async function lockProviderOpsSession(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set({
    name: COOKIE_NAME,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/providers",
    maxAge: 0,
  });
}

function accessToken() {
  return process.env.NUTMEG_PROVIDER_OPS_UI_TOKEN?.trim() || null;
}

async function readSession() {
  const configuredToken = accessToken();
  if (!configuredToken) {
    return null;
  }
  const cookieStore = await cookies();
  const value = cookieStore.get(COOKIE_NAME)?.value;
  if (!value) {
    return null;
  }
  const [encodedPayload, receivedSignature] = value.split(".");
  if (!encodedPayload || !receivedSignature) {
    return null;
  }
  const expectedSignature = signature(encodedPayload, configuredToken);
  if (!constantTimeEquals(receivedSignature, expectedSignature)) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(base64UrlDecode(encodedPayload));
    if (!isSessionPayload(parsed)) {
      return null;
    }
    if (parsed.expiresAt <= Math.floor(Date.now() / 1000)) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function signature(value: string, secret: string) {
  return createHmac("sha256", secret).update(value).digest("base64url");
}

function constantTimeEquals(left: string, right: string) {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  if (leftBuffer.length !== rightBuffer.length) {
    return false;
  }
  return timingSafeEqual(leftBuffer, rightBuffer);
}

function base64UrlEncode(value: string) {
  return Buffer.from(value, "utf8").toString("base64url");
}

function base64UrlDecode(value: string) {
  return Buffer.from(value, "base64url").toString("utf8");
}

function sanitizeOperatorName(value: string) {
  const safe = value.trim().replace(/[^\w .@-]/g, "").slice(0, 80);
  return safe || "provider-ops-operator";
}

function isSessionPayload(
  value: unknown,
): value is { operatorName: string; issuedAt: number; expiresAt: number; nonce: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "operatorName" in value &&
    "issuedAt" in value &&
    "expiresAt" in value &&
    "nonce" in value &&
    typeof value.operatorName === "string" &&
    typeof value.issuedAt === "number" &&
    typeof value.expiresAt === "number" &&
    typeof value.nonce === "string"
  );
}
