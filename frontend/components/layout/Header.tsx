"use client";

import Link from "next/link";
import { Fingerprint, History, LogOut, ScanSearch, ShoppingBasket } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { useAppShellState } from "@/hooks/use-app-shell-state";
import { clearTokens } from "@/lib/auth";

export function Header() {
  const shell = useAppShellState();

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
          {shell.activeSessionId ? (
            <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-2 text-xs text-[color:var(--text-muted)]">
              <ScanSearch className="h-3.5 w-3.5" />
              Session {shell.activeSessionId.slice(0, 8)}
            </span>
          ) : null}
        </nav>

        <div className="flex items-center gap-3">
          {shell.ready ? (
            <div className="hidden items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-muted)] px-4 py-2 text-xs text-[color:var(--text-muted)] lg:inline-flex">
              <Fingerprint className="h-3.5 w-3.5" />
              {shell.authConfigured
                ? shell.hasToken
                  ? shell.userEmail || "Authenticated"
                  : "Auth required"
                : "Guest mode"}
            </div>
          ) : null}
          <ThemeToggle />
          {shell.authConfigured && shell.hasToken ? (
            <button
              type="button"
              onClick={() => {
                clearTokens();
                window.location.href = shell.logoutHref || "/";
              }}
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-2 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          ) : shell.authConfigured && shell.loginHref ? (
            <a
              href={shell.loginHref}
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
