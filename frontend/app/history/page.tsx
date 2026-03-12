"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Clock3, History, LoaderCircle, ShieldCheck, Sparkles } from "lucide-react";

import { listSessions } from "@/lib/api-client";
import { isAuthenticated, tryBuildAuthorizeUrl } from "@/lib/auth";
import type { SessionSummary } from "@/lib/contracts";

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function verdictTone(verdict: SessionSummary["verdict"]) {
  if (verdict === "BUY") {
    return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
  if (verdict === "WAIT") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  if (verdict === "AVOID") {
    return "border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-300";
  }
  return "border-[color:var(--border)] bg-[color:var(--surface-strong)] text-[color:var(--text-soft)]";
}

export default function HistoryPage() {
  const [items, setItems] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const loginHref = tryBuildAuthorizeUrl();

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!isAuthenticated()) {
        if (!cancelled) {
          setError("Login with Cognito to load session history.");
          setLoading(false);
        }
        return;
      }

      try {
        const response = await listSessions(24);
        if (!cancelled) {
          setItems(response.items);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Failed to load session history.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-8 md:px-8 md:py-12">
      <section className="rounded-[2.3rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-7 shadow-[var(--shadow-strong)]">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-2 text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
              <History className="h-3.5 w-3.5 text-[color:var(--accent)]" />
              Session archive
            </div>
            <h1 className="mt-5 text-4xl font-semibold tracking-[-0.04em] text-[color:var(--text-strong)] md:text-5xl">
              Re-open previous agent runs.
            </h1>
            <p className="mt-4 max-w-3xl text-sm leading-8 text-[color:var(--text-soft)]">
              Every run stays tied to a session id, message history, and recommendation trace so the demo can resume
              exactly where the agent left off.
            </p>
          </div>

          <div className="grid min-w-56 gap-3">
            <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Stored sessions</p>
              <p className="mt-2 text-3xl font-semibold text-[color:var(--text-strong)]">{items.length}</p>
            </div>
            <div className="rounded-[1.5rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <div className="inline-flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300">
                <ShieldCheck className="h-4 w-4" />
                Auth-bound history
              </div>
            </div>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="flex items-center justify-center rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] px-6 py-16 shadow-[var(--shadow-soft)]">
          <LoaderCircle className="h-8 w-8 animate-spin text-[color:var(--accent)]" />
        </div>
      ) : null}

      {!loading && error ? (
        <div className="rounded-[2rem] border border-amber-500/20 bg-amber-500/10 p-6 shadow-[var(--shadow-soft)]">
          <p className="text-xs uppercase tracking-[0.28em] text-amber-700 dark:text-amber-300">History unavailable</p>
          <p className="mt-3 text-sm leading-7 text-[color:var(--text-soft)]">{error}</p>
          {loginHref ? (
            <a
              href={loginHref}
              className="mt-5 inline-flex items-center gap-2 rounded-full bg-[color:var(--accent)] px-4 py-3 text-sm font-medium text-white transition hover:opacity-90"
            >
              Login with Cognito
              <ArrowRight className="h-4 w-4" />
            </a>
          ) : null}
        </div>
      ) : null}

      {!loading && !error ? (
        <section className="grid gap-4">
          {items.map((session) => (
            <Link
              key={session.sessionId}
              href={`/results?session=${session.sessionId}`}
              className="group rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-strong)]"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className={`rounded-full border px-3 py-1 text-xs ${verdictTone(session.verdict)}`}>
                      {session.verdict ?? session.status}
                    </span>
                    <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
                      {session.sessionId.slice(0, 10)}
                    </span>
                  </div>
                  <h2 className="mt-4 text-2xl font-semibold text-[color:var(--text-strong)]">{session.title}</h2>
                  <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-[color:var(--text-soft)]">
                    <span className="inline-flex items-center gap-2">
                      <Clock3 className="h-4 w-4" />
                      Updated {formatTimestamp(session.updatedAt)}
                    </span>
                    <span>Created {formatTimestamp(session.createdAt)}</span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-right">
                    <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Trace state</p>
                    <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">{session.status}</p>
                  </div>
                  <div className="rounded-full border border-[color:var(--border)] p-3 text-[color:var(--text-muted)] transition group-hover:border-[color:var(--accent)] group-hover:text-[color:var(--accent)]">
                    <ArrowRight className="h-5 w-5" />
                  </div>
                </div>
              </div>
            </Link>
          ))}

          {!items.length ? (
            <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-8 shadow-[var(--shadow-soft)]">
              <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
                <Sparkles className="h-3.5 w-3.5 text-[color:var(--accent)]" />
                Empty archive
              </div>
              <p className="mt-4 text-sm leading-7 text-[color:var(--text-soft)]">
                No sessions are stored yet. Run a supplements query from the landing page to create the first tracked
                session.
              </p>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
