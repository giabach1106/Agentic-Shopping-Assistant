"use client";

import Link from "next/link";
import { History, LogOut, ScanSearch, ShoppingBasket } from "lucide-react";
import { useEffect, useState } from "react";

import { AUTH_EVENT_NAME, clearTokens, getIdToken, tryBuildAuthorizeUrl, tryLogoutUrl } from "@/lib/auth";
import { getStoredSessionId, SESSION_EVENT_NAME } from "@/lib/api-client";
import { ThemeToggle } from "@/components/theme-toggle";

function readHeaderState() {
  if (typeof window === "undefined") {
    return {
      isAuthed: false,
      activeSession: null as string | null,
    };
  }

  return {
    isAuthed: Boolean(getIdToken()),
    activeSession: getStoredSessionId(),
  };
}

export function Header() {
  const [headerState, setHeaderState] = useState(readHeaderState);
  const loginHref = tryBuildAuthorizeUrl();

  useEffect(() => {
    const syncState = () => {
      setHeaderState(readHeaderState());
    };

    window.addEventListener("storage", syncState);
    window.addEventListener(AUTH_EVENT_NAME, syncState);
    window.addEventListener(SESSION_EVENT_NAME, syncState);

    return () => {
      window.removeEventListener("storage", syncState);
      window.removeEventListener(AUTH_EVENT_NAME, syncState);
      window.removeEventListener(SESSION_EVENT_NAME, syncState);
    };
  }, []);

  return (
    <header className="sticky top-0 z-50 border-b border-[color:var(--border)] bg-[color:var(--surface)]/88 backdrop-blur-xl">
      <div className="mx-auto flex h-20 w-full max-w-7xl items-center justify-between gap-4 px-4 md:px-8">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[color:var(--accent)] text-white shadow-[var(--shadow-soft)]">
            <ShoppingBasket className="h-5 w-5" />
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-[0.35em] text-[color:var(--text-muted)]">AgentCart</p>
            <p className="text-base font-semibold text-[color:var(--text-strong)]">Decision-first shopping</p>
          </div>
        </Link>

        <nav className="hidden items-center gap-2 md:flex">
          <Link
            href="/"
            className="rounded-full px-4 py-2 text-sm text-[color:var(--text-soft)] transition hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text-strong)]"
          >
            New search
          </Link>
          <Link
            href="/history"
            className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm text-[color:var(--text-soft)] transition hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text-strong)]"
          >
            <History className="h-4 w-4" />
            History
          </Link>
          {headerState.activeSession ? (
            <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-2 text-xs text-[color:var(--text-muted)]">
              <ScanSearch className="h-3.5 w-3.5" />
              Session {headerState.activeSession.slice(0, 8)}
            </span>
          ) : null}
        </nav>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          {headerState.isAuthed ? (
            <button
              type="button"
              onClick={() => {
                clearTokens();
                const nextLogoutUrl = tryLogoutUrl();
                window.location.href = nextLogoutUrl || "/";
              }}
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-2 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          ) : loginHref ? (
            <a
              href={loginHref}
              className="rounded-full bg-[color:var(--accent)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
            >
              Login with Cognito
            </a>
          ) : null}
        </div>
      </div>
    </header>
  );
}
