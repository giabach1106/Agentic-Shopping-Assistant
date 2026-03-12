"use client";

import { useEffect, useState } from "react";

import { getStoredSessionId, SESSION_EVENT_NAME } from "@/lib/api-client";
import {
  AUTH_EVENT_NAME,
  canUseCognitoAuth,
  getIdToken,
  getTokenClaims,
  tryBuildAuthorizeUrl,
  tryLogoutUrl,
} from "@/lib/auth";

export interface AppShellState {
  ready: boolean;
  authConfigured: boolean;
  hasToken: boolean;
  isAuthenticated: boolean;
  activeSessionId: string | null;
  loginHref: string | null;
  logoutHref: string | null;
  userEmail: string | null;
  userSub: string | null;
}

function readSnapshot(): AppShellState {
  if (typeof window === "undefined") {
    return {
      ready: false,
      authConfigured: false,
      hasToken: false,
      isAuthenticated: false,
      activeSessionId: null,
      loginHref: null,
      logoutHref: null,
      userEmail: null,
      userSub: null,
    };
  }

  const authConfigured = canUseCognitoAuth();
  const token = getIdToken();
  const claims = getTokenClaims();

  return {
    ready: true,
    authConfigured,
    hasToken: Boolean(token),
    isAuthenticated: authConfigured ? Boolean(token) : true,
    activeSessionId: getStoredSessionId(),
    loginHref: tryBuildAuthorizeUrl(),
    logoutHref: tryLogoutUrl(),
    userEmail: typeof claims?.email === "string" ? claims.email : null,
    userSub: typeof claims?.sub === "string" ? claims.sub : null,
  };
}

export function useAppShellState() {
  const [state, setState] = useState<AppShellState>({
    ready: false,
    authConfigured: false,
    hasToken: false,
    isAuthenticated: false,
    activeSessionId: null,
    loginHref: null,
    logoutHref: null,
    userEmail: null,
    userSub: null,
  });

  useEffect(() => {
    const syncState = () => {
      setState(readSnapshot());
    };

    syncState();
    window.addEventListener("storage", syncState);
    window.addEventListener(AUTH_EVENT_NAME, syncState);
    window.addEventListener(SESSION_EVENT_NAME, syncState);

    return () => {
      window.removeEventListener("storage", syncState);
      window.removeEventListener(AUTH_EVENT_NAME, syncState);
      window.removeEventListener(SESSION_EVENT_NAME, syncState);
    };
  }, []);

  return state;
}
