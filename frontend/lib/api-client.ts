import type {
  ChatResponse,
  CreateSessionResponse,
  SessionListResponse,
  SessionProductsResponse,
  SessionSnapshotResponse,
} from "@/lib/contracts";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://localhost:8000";
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

async function request<T>(
  path: string,
  init: RequestInit & { bodyJson?: JsonBody } = {}
): Promise<T> {
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

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      body: init.bodyJson ? JSON.stringify(init.bodyJson) : init.body,
    });
  } catch (error) {
    throw new Error(
      `Failed to reach API at ${API_BASE_URL}. Check that the backend is running and CORS allows the frontend origin.`
    );
  }

  if (!response.ok) {
    const raw = await response.text();
    let message = raw || `Request failed: ${response.status}`;

    try {
      const parsed = JSON.parse(raw) as { detail?: string };
      if (typeof parsed.detail === "string" && parsed.detail.trim()) {
        message = parsed.detail;
      }
    } catch {
      // Keep raw response text when the body is not JSON.
    }

    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
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
