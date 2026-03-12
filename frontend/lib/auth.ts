const ID_TOKEN_KEY = "agentcart.id_token";
const ACCESS_TOKEN_KEY = "agentcart.access_token";
const THEME_KEY = "agentcart.theme";
export const AUTH_EVENT_NAME = "agentcart:auth";
export const THEME_EVENT_NAME = "agentcart:theme";

export interface TokenClaims {
  sub?: string;
  email?: string;
  exp?: number;
  [key: string]: unknown;
}

function getCognitoConfig() {
  const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN?.trim();
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID?.trim();
  const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI?.trim();
  const logoutUri =
    process.env.NEXT_PUBLIC_COGNITO_LOGOUT_URI?.trim() || redirectUri;

  if (!domain || !clientId || !redirectUri) {
    return null;
  }

  return { domain, clientId, redirectUri, logoutUri };
}

export function getAuthConfigurationError() {
  const missing: string[] = [];
  if (!process.env.NEXT_PUBLIC_COGNITO_DOMAIN?.trim()) {
    missing.push("NEXT_PUBLIC_COGNITO_DOMAIN");
  }
  if (!process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID?.trim()) {
    missing.push("NEXT_PUBLIC_COGNITO_CLIENT_ID");
  }
  if (!process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI?.trim()) {
    missing.push("NEXT_PUBLIC_COGNITO_REDIRECT_URI");
  }
  if (!missing.length) {
    return null;
  }
  return `Missing Cognito env: ${missing.join(", ")}`;
}

export function buildAuthorizeUrl() {
  const config = getCognitoConfig();
  if (!config) {
    throw new Error("Missing Cognito frontend environment variables.");
  }

  const params = new URLSearchParams({
    client_id: config.clientId,
    response_type: "code",
    scope: "openid email",
    redirect_uri: config.redirectUri,
  });

  return `https://${config.domain}/oauth2/authorize?${params.toString()}`;
}

export async function exchangeCodeForTokens(code: string) {
  const config = getCognitoConfig();
  if (!config) {
    throw new Error("Missing Cognito frontend environment variables.");
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.clientId,
    code,
    redirect_uri: config.redirectUri,
  });

  const response = await fetch(`https://${config.domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!response.ok) {
    throw new Error(`Token exchange failed: ${response.status}`);
  }

  return (await response.json()) as {
    id_token: string;
    access_token: string;
  };
}

export function storeTokens(tokens: { id_token: string; access_token: string }) {
  localStorage.setItem(ID_TOKEN_KEY, tokens.id_token);
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  window.dispatchEvent(new Event(AUTH_EVENT_NAME));
}

export function clearTokens() {
  localStorage.removeItem(ID_TOKEN_KEY);
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_EVENT_NAME));
}

function clearTokensSilently() {
  localStorage.removeItem(ID_TOKEN_KEY);
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function getIdToken() {
  if (typeof window === "undefined") {
    return null;
  }
  const token = localStorage.getItem(ID_TOKEN_KEY);
  if (!token) {
    return null;
  }
  const claims = decodeTokenClaims(token);
  if (!claims) {
    clearTokensSilently();
    return null;
  }
  if (typeof claims.exp === "number" && claims.exp <= Math.floor(Date.now() / 1000)) {
    clearTokensSilently();
    return null;
  }
  return token;
}

export function isAuthenticated() {
  return canUseCognitoAuth() && Boolean(getIdToken());
}

export function logoutUrl() {
  const config = getCognitoConfig();
  if (!config) {
    throw new Error("Missing Cognito frontend environment variables.");
  }
  const logoutUri = config.logoutUri || config.redirectUri;
  return `https://${config.domain}/logout?client_id=${encodeURIComponent(config.clientId)}&logout_uri=${encodeURIComponent(logoutUri)}`;
}

export function themeStorageKey() {
  return THEME_KEY;
}

export function canUseCognitoAuth() {
  return getAuthConfigurationError() === null;
}

function decodeTokenClaims(token: string): TokenClaims | null {
  const parts = token.split(".");
  if (parts.length < 2) {
    return null;
  }

  try {
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload.padEnd(Math.ceil(payload.length / 4) * 4, "=");
    const decoded = window.atob(padded);
    const claims = JSON.parse(decoded) as TokenClaims;
    return claims && typeof claims === "object" ? claims : null;
  } catch {
    return null;
  }
}

export function getTokenClaims() {
  const token = getIdToken();
  if (!token) {
    return null;
  }
  return decodeTokenClaims(token);
}

export function tryBuildAuthorizeUrl() {
  return getCognitoConfig() ? buildAuthorizeUrl() : null;
}

export function tryLogoutUrl() {
  if (process.env.NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT?.trim() !== "true") {
    return null;
  }
  return getCognitoConfig() ? logoutUrl() : null;
}
