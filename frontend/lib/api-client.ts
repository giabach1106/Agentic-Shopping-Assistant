import type {
  CatalogMetricsResponse,
  ChatResponse,
  CreateSessionResponse,
  SessionListResponse,
  SessionProductsResponse,
  SessionSnapshotResponse,
} from "@/lib/contracts";
import { getRuntimeConfigValue } from "@/lib/runtime-config";

const SESSION_KEY = "agentcart.active_session";
export const SESSION_EVENT_NAME = "agentcart:session";

type JsonBody = Record<string, unknown> | undefined;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function addCandidate(candidates: string[], value: string | null | undefined) {
  if (!value) {
    return;
  }
  const normalized = value.replace(/\/+$/, "");
  if (!normalized) {
    return;
  }
  if (!candidates.includes(normalized)) {
    candidates.push(normalized);
  }
}

function inferSiblingApiBase(originOrBase: string) {
  try {
    const parsed = new URL(originOrBase);
    const host = parsed.hostname.toLowerCase();
    if (!host.startsWith("app.")) {
      return null;
    }
    const siblingHost = `api.${host.slice(4)}`;
    const portSegment = parsed.port ? `:${parsed.port}` : "";
    return `${parsed.protocol}//${siblingHost}${portSegment}`;
  } catch {
    return null;
  }
}

function resolveApiBaseCandidates() {
  const configuredBase =
    getRuntimeConfigValue("NEXT_PUBLIC_API_BASE_URL")?.replace(/\/+$/, "") ||
    "http://localhost:8000";
  const candidates: string[] = [];
  addCandidate(candidates, configuredBase);
  addCandidate(candidates, inferSiblingApiBase(configuredBase));

  if (typeof window === "undefined") {
    return candidates;
  }

  const sameOriginBase = `${window.location.origin.replace(/\/+$/, "")}/api`;
  addCandidate(candidates, sameOriginBase);
  addCandidate(candidates, inferSiblingApiBase(window.location.origin));
  return candidates;
}

function looksLikeHtmlResponse(raw: string, contentType: string | null) {
  const normalizedType = (contentType || "").toLowerCase();
  if (normalizedType.includes("text/html")) {
    return true;
  }
  const snippet = raw.trim().slice(0, 80).toLowerCase();
  return snippet.startsWith("<!doctype html") || snippet.startsWith("<html");
}

function buildErrorMessage(
  status: number,
  requestUrl: string,
  raw: string,
  contentType: string | null
) {
  try {
    const parsed = JSON.parse(raw) as { detail?: string };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    // Fallback to plain-text handling below.
  }

  if (looksLikeHtmlResponse(raw, contentType)) {
    return `Unexpected HTML response from ${requestUrl} (HTTP ${status}). API requests are likely routed to the frontend. Verify Caddy /api reverse_proxy.`;
  }

  const trimmed = raw.trim();
  if (!trimmed) {
    return `Request failed: ${status}`;
  }
  if (trimmed.length > 240) {
    return `${trimmed.slice(0, 240)}...`;
  }
  return trimmed;
}

function shouldRetryOnHttpError(status: number, raw: string, contentType: string | null) {
  if (!looksLikeHtmlResponse(raw, contentType)) {
    return false;
  }
  return status === 404 || status === 405 || status >= 500;
}

async function request<T>(
  path: string,
  init: RequestInit & { bodyJson?: JsonBody } = {}
): Promise<T> {
  const apiBaseCandidates = resolveApiBaseCandidates();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (init.bodyJson) {
    headers.set("Content-Type", "application/json");
  }

  if (typeof window !== "undefined") {
    const token = localStorage.getItem("agentcart.id_token");
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  let lastNetworkError: unknown = null;
  for (let index = 0; index < apiBaseCandidates.length; index += 1) {
    const apiBaseUrl = apiBaseCandidates[index];
    const requestUrl = `${apiBaseUrl}${path}`;
    try {
      const response = await fetch(requestUrl, {
        ...init,
        headers,
        body: init.bodyJson ? JSON.stringify(init.bodyJson) : init.body,
      });

      if (!response.ok) {
        const raw = await response.text();
        const contentType = response.headers.get("content-type");
        const message = buildErrorMessage(response.status, requestUrl, raw, contentType);
        const apiError = new ApiError(response.status, message);
        const hasFallback = index < apiBaseCandidates.length - 1;
        if (hasFallback && shouldRetryOnHttpError(response.status, raw, contentType)) {
          lastNetworkError = apiError;
          continue;
        }
        throw apiError;
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      lastNetworkError = error;
    }
  }

  const targetSummary = apiBaseCandidates.join(" or ");
  const reason =
    lastNetworkError instanceof Error && lastNetworkError.message
      ? ` (${lastNetworkError.message})`
      : "";
  throw new Error(
    `Failed to reach API at ${targetSummary}. Check that backend/Caddy is running and browser extensions are not blocking requests${reason}.`
  );
}

export function getStoredSessionId() {
  return typeof window === "undefined" ? null : localStorage.getItem(SESSION_KEY);
}

export function storeSessionId(sessionId: string) {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.setItem(SESSION_KEY, sessionId);
  window.dispatchEvent(new Event(SESSION_EVENT_NAME));
}

export async function createSession() {
  const data = await request<CreateSessionResponse>("/v1/sessions", { method: "POST" });
  storeSessionId(data.sessionId);
  return data;
}

export async function listSessions(limit = 20, cursor?: string) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) {
    params.set("cursor", cursor);
  }
  return request<SessionListResponse>(`/v1/sessions?${params.toString()}`);
}

export async function getSession(sessionId: string) {
  return request<SessionSnapshotResponse>(`/v1/sessions/${sessionId}`);
}

export async function getSessionProducts(sessionId: string) {
  return request<SessionProductsResponse>(`/v1/sessions/${sessionId}/products`);
}

export async function getRecommendation(sessionId: string) {
  return request<ChatResponse>(`/v1/recommendations/${sessionId}`);
}

export async function runChat(sessionId: string, message: string) {
  return request<ChatResponse>("/v1/chat", {
    method: "POST",
    bodyJson: { sessionId, message },
  });
}

export async function resumeRun(sessionId: string, message: string) {
  return request<ChatResponse>(`/v1/runs/${sessionId}/resume`, {
    method: "POST",
    bodyJson: { message },
  });
}

export async function getCatalogMetrics() {
  return request<CatalogMetricsResponse>("/v1/metrics/catalog");
}
