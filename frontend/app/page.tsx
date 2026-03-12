"use client";

import { startTransition, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BadgeCheck,
  DatabaseZap,
  FlaskConical,
  MoonStar,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { useAppShellState } from "@/hooks/use-app-shell-state";
import {
  exchangeCodeForTokens,
  storeTokens,
} from "@/lib/auth";

const presets = [
  "Find whey isolate under $90, third-party tested, low lactose.",
  "Compare creatine monohydrate options with no proprietary blends.",
  "Recommend a protein powder with minimal artificial sweeteners.",
];

const valueRows = [
  ["DB-first gate", "Reuse stored evidence before fresh crawl."],
  ["Ingredient score", "Highlight beneficial compounds and red flags."],
  ["Session memory", "Keep follow-ups and verdicts in one timeline."],
];

function LandingPage() {
  const router = useRouter();
  const shell = useAppShellState();
  const [query, setQuery] = useState("");
  const [authError, setAuthError] = useState("");
  const [isAuthenticating, setIsAuthenticating] = useState(false);

  useEffect(() => {
    const url = new URL(window.location.href);
    const code = url.searchParams.get("code");
    if (!code) {
      return;
    }

    void (async () => {
      try {
        setIsAuthenticating(true);
        setAuthError("");
        const tokens = await exchangeCodeForTokens(code);
        storeTokens(tokens);
        url.searchParams.delete("code");
        window.history.replaceState({}, "", url.toString());
      } catch (error) {
        setAuthError(
          error instanceof Error ? error.message : "Failed to authenticate with Cognito."
        );
      } finally {
        setIsAuthenticating(false);
      }
    })();
  }, []);

  const handleSubmit = (nextQuery: string) => {
    const trimmed = nextQuery.trim();
    if (!trimmed) {
      return;
    }

    if (!shell.authConfigured) {
      setAuthError(shell.authConfigError || "Cognito configuration is required.");
      return;
    }

    if (!shell.hasToken) {
      setAuthError("Login with Cognito before running the agent.");
      return;
    }

    setAuthError("");
    startTransition(() => {
      router.push(`/results?q=${encodeURIComponent(trimmed)}`);
    });
  };

  return (
    <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-7xl flex-col gap-8 px-4 py-8 md:px-8 md:py-14">
      <section className="grid gap-8 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="animate-rise space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-strong)] bg-[color:var(--surface-strong)] px-4 py-2 text-[11px] uppercase tracking-[0.32em] text-[color:var(--text-muted)]">
            <Sparkles className="h-3.5 w-3.5 text-[color:var(--accent)]" />
            Supplements intelligence
          </div>

          <div className="space-y-5">
            <h1 className="max-w-5xl text-5xl font-semibold leading-[0.92] tracking-[-0.05em] text-[color:var(--text-strong)] md:text-7xl">
              Decision-grade supplement shopping.
            </h1>
            <p className="max-w-3xl text-base leading-8 text-[color:var(--text-soft)] md:text-lg">
              One clean flow for trusted picks: evidence coverage, ingredient quality, source links, and session memory.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-5 shadow-[var(--shadow-soft)]">
              <DatabaseZap className="h-5 w-5 text-[color:var(--accent)]" />
              <p className="mt-4 text-sm font-medium text-[color:var(--text-strong)]">DB-first evidence gate</p>
              <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
                Stored evidence is checked first, then crawl expands only when coverage is weak.
              </p>
            </div>
            <div className="rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-5 shadow-[var(--shadow-soft)]">
              <FlaskConical className="h-5 w-5 text-[color:var(--accent)]" />
              <p className="mt-4 text-sm font-medium text-[color:var(--text-strong)]">Ingredient intelligence</p>
              <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
                Products surface protein source, ingredient flags, and reference links.
              </p>
            </div>
            <div className="rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-5 shadow-[var(--shadow-soft)]">
              <ShieldCheck className="h-5 w-5 text-[color:var(--accent)]" />
              <p className="mt-4 text-sm font-medium text-[color:var(--text-strong)]">Structured reasoning</p>
              <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
                Follow timeline, decision factors, and blockers without opaque output.
              </p>
            </div>
          </div>
        </div>

        <div className="animate-rise animate-rise-delay rounded-[2.4rem] border border-[color:var(--border-strong)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-strong)] md:p-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-[color:var(--text-muted)]">Launch console</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[color:var(--text-strong)]">
                Start a session
              </h2>
            </div>
            <span className="rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
              {isAuthenticating
                ? "Signing in"
                : shell.authConfigured
                  ? shell.hasToken
                    ? "Authenticated"
                    : "Login required"
                  : "Auth setup required"}
            </span>
          </div>

          <form
            className="mt-6 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              handleSubmit(query);
            }}
          >
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleSubmit(query);
                }
              }}
              placeholder="Whey isolate under $90, third-party tested, low lactose, and delivered by Friday."
              className="min-h-40 w-full rounded-[1.9rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-5 py-4 text-base leading-7 text-[color:var(--text-strong)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-[color:var(--accent)]"
            />

            {authError ? (
              <p className="rounded-[1.5rem] border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
                {authError}
              </p>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2">
              <button
                type="submit"
                className="inline-flex items-center justify-center gap-2 rounded-full bg-[color:var(--text-strong)] px-5 py-3 text-sm font-medium text-[color:var(--background)] transition hover:bg-[color:var(--accent)]"
              >
                Ask Agent
                <ArrowRight className="h-4 w-4" />
              </button>

              {shell.authConfigured && !shell.hasToken && shell.loginHref ? (
                <a
                  href={shell.loginHref}
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-[color:var(--border)] px-5 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                >
                  Login with Cognito
                </a>
              ) : shell.activeSessionId ? (
                <Link
                  href={`/results?session=${shell.activeSessionId}`}
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-[color:var(--border)] px-5 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                >
                  Resume latest session
                </Link>
              ) : (
                <div className="inline-flex items-center justify-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-5 py-3 text-sm text-amber-700 dark:text-amber-300">
                  <MoonStar className="h-4 w-4" />
                  {shell.authConfigured ? "Start by logging in" : "Configure Cognito env"}
                </div>
              )}
            </div>
          </form>

          <div className="mt-6 grid gap-3">
            {presets.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => handleSubmit(preset)}
                className="rounded-[1.5rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-4 text-left text-sm leading-6 text-[color:var(--text-soft)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--text-strong)]"
              >
                {preset}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <div className="rounded-[2.2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
            <BadgeCheck className="h-3.5 w-3.5 text-[color:var(--accent)]" />
            Product lane
          </div>
          <h2 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-[color:var(--text-strong)]">
            Supplements-first, production-ready.
          </h2>
          <p className="mt-4 text-sm leading-7 text-[color:var(--text-soft)]">
            Whey and supplement workflows are optimized for ingredient scrutiny, trustworthy scoring, and explainable
            evidence diagnostics.
          </p>
        </div>

        <div className="rounded-[2.2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Why it stands out</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[color:var(--text-strong)]">
                Evidence system view
              </h2>
            </div>
            <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">3 signals</span>
          </div>

          <div className="overflow-hidden rounded-[1.7rem] border border-[color:var(--border)]">
            <div className="grid grid-cols-[minmax(0,0.36fr)_1fr] bg-[color:var(--surface-strong)] px-4 py-3 text-[11px] uppercase tracking-[0.24em] text-[color:var(--text-muted)]">
              <span>Layer</span>
              <span>What the judge sees</span>
            </div>
            {valueRows.map(([label, detail], index) => (
              <div
                key={label}
                className={`grid grid-cols-[minmax(0,0.36fr)_1fr] px-4 py-4 text-sm ${
                  index < valueRows.length - 1 ? "border-t border-[color:var(--border)]" : ""
                }`}
              >
                <span className="font-medium text-[color:var(--text-strong)]">{label}</span>
                <span className="leading-7 text-[color:var(--text-soft)]">{detail}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

export default LandingPage;
