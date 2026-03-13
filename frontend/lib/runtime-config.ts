export type RuntimeConfigKey =
  | "NEXT_PUBLIC_API_BASE_URL"
  | "NEXT_PUBLIC_COGNITO_DOMAIN"
  | "NEXT_PUBLIC_COGNITO_CLIENT_ID"
  | "NEXT_PUBLIC_COGNITO_REDIRECT_URI"
  | "NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT"
  | "NEXT_PUBLIC_COGNITO_LOGOUT_URI";

type RuntimeConfig = Partial<Record<RuntimeConfigKey, string>>;

declare global {
  interface Window {
    __AGENTCART_RUNTIME_CONFIG__?: RuntimeConfig;
  }
}

function sanitize(value: string | undefined) {
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length ? trimmed : undefined;
}

export function getRuntimeConfigValue(key: RuntimeConfigKey) {
  if (typeof window !== "undefined") {
    const runtimeValue = sanitize(window.__AGENTCART_RUNTIME_CONFIG__?.[key]);
    if (runtimeValue !== undefined) {
      return runtimeValue;
    }
  }

  const buildValue = process.env[key];
  return sanitize(buildValue);
}
