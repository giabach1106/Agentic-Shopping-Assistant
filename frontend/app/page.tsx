"use client";

import { startTransition, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, BadgeCheck, DatabaseZap, FlaskConical, ShieldCheck, Sparkles } from "lucide-react";

import {
  exchangeCodeForTokens,
  getIdToken,
  isAuthenticated,
  storeTokens,
  tryBuildAuthorizeUrl,
} from "@/lib/auth";

const presets = [
  "Find a whey protein isolate under $90 with 4+ stars delivered by Friday",
  "Best creatine monohydrate with third-party testing and no proprietary blend",
  "Protein powder for lactose-sensitive users with low artificial sweeteners",
];

export default function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"idle" | "authenticating" | "ready" | "error">(
    () => (isAuthenticated() ? "ready" : "idle")
  );
  const [error, setError] = useState("");
  const loginHref = tryBuildAuthorizeUrl();

  useEffect(() => {
    const url = new URL(window.location.href);
    const code = url.searchParams.get("code");
    if (!code) {
      return;
    }

    void (async () => {
      try {
        setStatus("authenticating");
        const tokens = await exchangeCodeForTokens(code);
        storeTokens(tokens);
        url.searchParams.delete("code");
        window.history.replaceState({}, "", url.toString());
        setStatus("ready");
      } catch (nextError) {
        setStatus("error");
        setError(nextError instanceof Error ? nextError.message : "Failed to authenticate.");
      }
    })();
  }, []);

  const handleSubmit = (nextQuery: string) => {
    if (!getIdToken()) {
      setStatus("error");
      setError("Login with Cognito before running the agent.");
      return;
    }
    if (!nextQuery.trim()) {
      return;
    }
    startTransition(() => {
      router.push(`/results?q=${encodeURIComponent(nextQuery.trim())}`);
    });
  };

  return (
    <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-7xl flex-col gap-10 px-4 py-10 md:px-8 md:py-16">
      <section className="grid gap-8 lg:grid-cols-[1.25fr_0.9fr] lg:items-end">
        <div className="space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-2 text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
            <Sparkles className="h-3.5 w-3.5 text-[color:var(--accent)]" />
            Amazon Nova Hackathon demo
          </div>

          <div className="space-y-4">
            <h1 className="max-w-4xl text-5xl font-semibold leading-[0.95] tracking-[-0.04em] text-[color:var(--text-strong)] md:text-7xl">
              Agentic shopping that shows the work, not just the answer.
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-[color:var(--text-soft)] md:text-xl">
              Supplements-first workflow for whey and performance nutrition. The agent tracks evidence coverage,
              ingredient risk, authenticity signals, and checkout safety in one session-bound flow.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-[1.75rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-5 shadow-[var(--shadow-soft)]">
              <FlaskConical className="h-5 w-5 text-[color:var(--accent)]" />
              <p className="mt-4 text-sm font-medium text-[color:var(--text-strong)]">Ingredient-first scoring</p>
              <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
                Surfaces protein source, red flags, beneficial signals, and reference links.
              </p>
            </div>
            <div className="rounded-[1.75rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-5 shadow-[var(--shadow-soft)]">
              <DatabaseZap className="h-5 w-5 text-[color:var(--accent)]" />
              <p className="mt-4 text-sm font-medium text-[color:var(--text-strong)]">DB-first evidence gate</p>
              <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
                Reuses stored evidence before crawling and only expands when coverage is weak.
              </p>
            </div>
            <div className="rounded-[1.75rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-5 shadow-[var(--shadow-soft)]">
              <ShieldCheck className="h-5 w-5 text-[color:var(--accent)]" />
              <p className="mt-4 text-sm font-medium text-[color:var(--text-strong)]">Structured reasoning</p>
              <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
                Timeline, blockers, trust score, and source references instead of opaque one-shot output.
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-[2.25rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-strong)] md:p-8">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-[color:var(--text-muted)]">Session gateway</p>
              <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Run the agent</h2>
            </div>
            <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
              {status === "ready" ? "Authenticated" : status === "authenticating" ? "Signing in" : "Login required"}
            </span>
          </div>

          <div className="mt-6 space-y-4">
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Example: Whey isolate under $90, low lactose, third-party tested, by Friday."
              className="min-h-36 w-full rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-5 py-4 text-base leading-7 text-[color:var(--text-strong)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-[color:var(--accent)]"
            />
            {status === "error" ? (
              <p className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
                {error}
              </p>
            ) : null}
            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={() => handleSubmit(query)}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-[color:var(--accent)] px-5 py-3 text-sm font-medium text-white transition hover:opacity-90"
              >
                Ask Agent
                <ArrowRight className="h-4 w-4" />
              </button>
              {loginHref ? (
                <a
                  href={loginHref}
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-[color:var(--border)] px-5 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                >
                  Login with Cognito
                </a>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
          <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Demo lane</p>
          <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Supplements / whey-first</h2>
          <p className="mt-3 text-sm leading-7 text-[color:var(--text-soft)]">
            This build prioritizes score transparency for protein powders and supplements: review reliability,
            ingredient flags, authenticity hints, and action-safe purchase links.
          </p>
        </div>

        <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Fast prompts</p>
              <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Launch a strong demo run</h2>
            </div>
            <BadgeCheck className="h-5 w-5 text-[color:var(--accent)]" />
          </div>
          <div className="grid gap-3">
            {presets.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => handleSubmit(preset)}
                className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-4 text-left text-sm leading-6 text-[color:var(--text-soft)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--text-strong)]"
              >
                {preset}
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
