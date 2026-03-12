const ID_TOKEN_KEY = "agentcart.id_token";
const ACCESS_TOKEN_KEY = "agentcart.access_token";
const THEME_KEY = "agentcart.theme";
export const AUTH_EVENT_NAME = "agentcart:auth";
export const THEME_EVENT_NAME = "agentcart:theme";

function getCognitoConfig() {
  const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN;
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID;
  const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI;

  if (!domain || !clientId || !redirectUri) {
    return null;
  }

  return { domain, clientId, redirectUri };
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

export function getIdToken() {
  return typeof window === "undefined" ? null : localStorage.getItem(ID_TOKEN_KEY);
}

export function isAuthenticated() {
  return Boolean(getIdToken());
}

export function logoutUrl() {
  const config = getCognitoConfig();
  if (!config) {
    throw new Error("Missing Cognito frontend environment variables.");
  }
  return `https://${config.domain}/logout?client_id=${encodeURIComponent(config.clientId)}&logout_uri=${encodeURIComponent(config.redirectUri)}`;
}

export function themeStorageKey() {
  return THEME_KEY;
}

export function canUseCognitoAuth() {
  return Boolean(getCognitoConfig());
}

export function tryBuildAuthorizeUrl() {
  return getCognitoConfig() ? buildAuthorizeUrl() : null;
}

export function tryLogoutUrl() {
  return getCognitoConfig() ? logoutUrl() : null;
}
