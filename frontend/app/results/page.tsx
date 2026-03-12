"use client";

import Link from "next/link";
import { type FormEvent, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  LoaderCircle,
  MessageSquare,
  Send,
  ShieldCheck,
  Sparkles,
  User,
} from "lucide-react";

import { ProductCard } from "@/components/product-card";
import { TracePanel } from "@/components/trace-panel";
import {
  ApiError,
  createSession,
  getRecommendation,
  getSession,
  getSessionProducts,
  getStoredSessionId,
  resumeRun,
  runChat,
  storeSessionId,
} from "@/lib/api-client";
import { isAuthenticated, tryBuildAuthorizeUrl } from "@/lib/auth";
import type {
  ChatResponse,
  SessionMessage,
  SessionProduct,
  SessionSnapshotResponse,
} from "@/lib/contracts";

function formatPercent(value: number) {
  return `${Math.round(value)}%`;
}

function formatFreshness(seconds: number) {
  if (!seconds) {
    return "fresh";
  }
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)}m ago`;
  }
  if (seconds < 86400) {
    return `${Math.round(seconds / 3600)}h ago`;
  }
  return `${Math.round(seconds / 86400)}d ago`;
}

function isNotFound(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}

function scoreTone(score: number) {
  if (score >= 80) {
    return "text-emerald-600 dark:text-emerald-300";
  }
  if (score >= 60) {
    return "text-amber-600 dark:text-amber-300";
  }
  return "text-rose-600 dark:text-rose-300";
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

async function loadSessionBundle(sessionId: string) {
  const [snapshotResult, recommendationResult, productsResult] = await Promise.allSettled([
    getSession(sessionId),
    getRecommendation(sessionId),
    getSessionProducts(sessionId),
  ]);

  if (snapshotResult.status === "rejected") {
    throw snapshotResult.reason;
  }

  let recommendation: ChatResponse | null = null;
  if (recommendationResult.status === "fulfilled") {
    recommendation = recommendationResult.value;
  } else if (!isNotFound(recommendationResult.reason)) {
    throw recommendationResult.reason;
  }

  let products: SessionProduct[] = [];
  if (productsResult.status === "fulfilled") {
    products = productsResult.value.items;
  } else if (!isNotFound(productsResult.reason)) {
    throw productsResult.reason;
  }

  return {
    snapshot: snapshotResult.value,
    recommendation,
    products,
  };
}

function ResultsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const query = searchParams.get("q")?.trim() ?? "";
  const sessionParam = searchParams.get("session");
  const loginHref = tryBuildAuthorizeUrl();

  const [activeSessionId, setActiveSessionId] = useState<string | null>(sessionParam);
  const [snapshot, setSnapshot] = useState<SessionSnapshotResponse | null>(null);
  const [recommendation, setRecommendation] = useState<ChatResponse | null>(null);
  const [products, setProducts] = useState<SessionProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const bootKeyRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [snapshot?.messages, sending]);

  useEffect(() => {
    const bootKey = `${sessionParam ?? ""}|${query}`;
    if (bootKeyRef.current === bootKey) {
      return;
    }
    bootKeyRef.current = bootKey;

    let cancelled = false;

    async function bootstrap() {
      if (!isAuthenticated()) {
        if (!cancelled) {
          setLoading(false);
          setError("Login with Cognito before starting or resuming an agent session.");
        }
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const existingSession = sessionParam || getStoredSessionId();

        if (sessionParam) {
          const bundle = await loadSessionBundle(sessionParam);
          if (cancelled) {
            return;
          }
          storeSessionId(sessionParam);
          setActiveSessionId(sessionParam);
          setSnapshot(bundle.snapshot);
          setRecommendation(bundle.recommendation);
          setProducts(bundle.products);
          return;
        }

        if (query) {
          const created = await createSession();
          if (cancelled) {
            return;
          }
          const firstTurn = await runChat(created.sessionId, query);
          if (cancelled) {
            return;
          }
          const bundle = await loadSessionBundle(created.sessionId);
          if (cancelled) {
            return;
          }
          setActiveSessionId(created.sessionId);
          setSnapshot(bundle.snapshot);
          setRecommendation(bundle.recommendation ?? firstTurn);
          setProducts(bundle.products);
          router.replace(`/results?session=${created.sessionId}&q=${encodeURIComponent(query)}`);
          return;
        }

        if (existingSession) {
          const bundle = await loadSessionBundle(existingSession);
          if (cancelled) {
            return;
          }
          storeSessionId(existingSession);
          setActiveSessionId(existingSession);
          setSnapshot(bundle.snapshot);
          setRecommendation(bundle.recommendation);
          setProducts(bundle.products);
          router.replace(`/results?session=${existingSession}`);
          return;
        }

        setError("No active session found. Start a new query from the home page.");
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Failed to load the session.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, [query, router, sessionParam]);

  const currentPrompt = useMemo(() => {
    const firstUserMessage = snapshot?.messages.find((message) => message.role === "user");
    return firstUserMessage?.content || query || "Supplements screening session";
  }, [query, snapshot?.messages]);

  const needsFollowUp =
    recommendation?.status === "NEED_DATA" ||
    Boolean((snapshot?.checkpointState as { needs_follow_up?: boolean } | null)?.needs_follow_up);

  const messages: SessionMessage[] = snapshot?.messages ?? [];

  const referenceLinks = useMemo(() => {
    return [...new Set(products.flatMap((product) => [...product.evidenceRefs, ...product.ingredientAnalysis.references]))];
  }, [products]);

  const sortedProducts = useMemo(() => {
    return [...products].sort(
      (left, right) => right.scientificScore.finalTrust - left.scientificScore.finalTrust
    );
  }, [products]);

  const selectedProduct = useMemo(() => {
    if (!recommendation?.decision?.selectedCandidate) {
      return sortedProducts[0] ?? null;
    }

    return (
      sortedProducts.find(
        (product) => product.sourceUrl === recommendation.decision?.selectedCandidate?.sourceUrl
      ) ??
      sortedProducts[0] ??
      null
    );
  }, [recommendation?.decision, sortedProducts]);

  async function submitChatMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!activeSessionId || !chatInput.trim()) {
      return;
    }

    setSending(true);
    setError(null);

    try {
      if (needsFollowUp) {
        await resumeRun(activeSessionId, chatInput.trim());
      } else {
        await runChat(activeSessionId, chatInput.trim());
      }
      const bundle = await loadSessionBundle(activeSessionId);
      setSnapshot(bundle.snapshot);
      setRecommendation(bundle.recommendation);
      setProducts(bundle.products);
      setChatInput("");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Chat update failed.");
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-7xl items-center justify-center px-4 py-12 md:px-8">
        <div className="w-full max-w-2xl rounded-[2.2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-10 text-center shadow-[var(--shadow-strong)]">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
            <LoaderCircle className="h-7 w-7 animate-spin" />
          </div>
          <h1 className="mt-6 text-3xl font-semibold text-[color:var(--text-strong)]">Agent session booting</h1>
          <p className="mt-3 text-sm leading-7 text-[color:var(--text-soft)]">
            Initializing evidence cache, session memory, and recommendation pipeline.
          </p>
        </div>
      </div>
    );
  }

  if (error && !snapshot) {
    return (
      <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-4xl items-center justify-center px-4 py-12 md:px-8">
        <div className="w-full rounded-[2.2rem] border border-rose-500/20 bg-rose-500/10 p-8 shadow-[var(--shadow-soft)]">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-500/10 text-rose-600 dark:text-rose-300">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div className="flex-1">
              <p className="text-xs uppercase tracking-[0.28em] text-rose-700 dark:text-rose-300">Access blocked</p>
              <h1 className="mt-2 text-3xl font-semibold text-[color:var(--text-strong)]">This session is not ready.</h1>
              <p className="mt-3 text-sm leading-7 text-[color:var(--text-soft)]">{error}</p>
              <div className="mt-6 flex flex-wrap gap-3">
                {loginHref ? (
                  <a
                    href={loginHref}
                    className="rounded-full bg-[color:var(--accent)] px-5 py-3 text-sm font-medium text-white transition hover:opacity-90"
                  >
                    Login with Cognito
                  </a>
                ) : null}
                <Link
                  href="/"
                  className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-5 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back to search
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-8 md:px-8 md:py-12">
      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-[2.4rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-7 shadow-[var(--shadow-strong)]">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-2 text-xs uppercase tracking-[0.3em] text-[color:var(--text-muted)]">
              <Sparkles className="h-3.5 w-3.5 text-[color:var(--accent)]" />
              Session-bound analysis
            </span>
            {activeSessionId ? (
              <span className="rounded-full border border-[color:var(--border)] px-4 py-2 text-xs text-[color:var(--text-muted)]">
                Session {activeSessionId.slice(0, 10)}
              </span>
            ) : null}
          </div>

          <h1 className="mt-5 max-w-4xl text-4xl font-semibold leading-[1.02] tracking-[-0.04em] text-[color:var(--text-strong)] md:text-5xl">
            {currentPrompt}
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-8 text-[color:var(--text-soft)]">
            The agent compares cached evidence, review authenticity, ingredient signals, and checkout viability before
            recommending an action.
          </p>

          <div className="mt-8 grid gap-4 md:grid-cols-4">
            <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Verdict</p>
              <p className="mt-3 text-3xl font-semibold text-[color:var(--text-strong)]">
                {recommendation?.decision?.verdict ?? "Pending"}
              </p>
            </div>
            <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Trust score</p>
              <p className={`mt-3 text-3xl font-semibold ${scoreTone(recommendation?.scientificScore.finalTrust ?? 0)}`}>
                {recommendation?.scientificScore.finalTrust ?? 0}
              </p>
            </div>
            <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Source coverage</p>
              <p className="mt-3 text-3xl font-semibold text-[color:var(--text-strong)]">
                {formatPercent(recommendation?.evidenceStats.sourceCoverage ?? 0)}
              </p>
            </div>
            <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Evidence freshness</p>
              <p className="mt-3 text-3xl font-semibold text-[color:var(--text-strong)]">
                {formatFreshness(recommendation?.evidenceStats.freshnessSeconds ?? 0)}
              </p>
            </div>
          </div>

          <div className="mt-8 grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
            <div className="rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
              <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Agent response</p>
              <p className="mt-4 text-sm leading-7 text-[color:var(--text-soft)]">
                {recommendation?.reply ?? "Waiting for the first decision payload."}
              </p>
              {needsFollowUp ? (
                <div className="mt-4 rounded-[1.3rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                  The orchestrator needs more detail before finalizing. Reply in the chat panel to continue the same run.
                </div>
              ) : null}
            </div>

            <div className="rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
              <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Decision factors</p>
              <div className="mt-4 grid gap-3">
                {(recommendation?.decision?.topReasons ?? []).slice(0, 3).map((reason) => (
                  <div
                    key={reason}
                    className="rounded-[1.2rem] border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-3 text-sm text-[color:var(--text-soft)]"
                  >
                    {reason}
                  </div>
                ))}
                {!recommendation?.decision?.topReasons?.length ? (
                  <p className="text-sm leading-7 text-[color:var(--text-soft)]">
                    No decision factors yet. The chat panel can continue the current session.
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        <aside className="rounded-[2.4rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Live session</p>
              <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Follow-up console</h2>
            </div>
            <div className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
              {messages.length} messages
            </div>
          </div>

          <div className="mt-6 flex max-h-[32rem] flex-col gap-3 overflow-y-auto pr-1">
            {messages.map((message, index) => {
              const isUser = message.role === "user";
              return (
                <div
                  key={`${message.createdAt}-${index}`}
                  className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
                >
                  {!isUser ? (
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
                      <Bot className="h-4 w-4" />
                    </div>
                  ) : null}
                  <div
                    className={`max-w-[84%] rounded-[1.5rem] px-4 py-3 text-sm leading-7 ${
                      isUser
                        ? "bg-[color:var(--text-strong)] text-[color:var(--background)]"
                        : "border border-[color:var(--border)] bg-[color:var(--surface-strong)] text-[color:var(--text-soft)]"
                    }`}
                  >
                    <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.24em] opacity-70">
                      {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                      {message.role}
                      <span>{formatTimestamp(message.createdAt)}</span>
                    </div>
                    {message.content}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={submitChatMessage} className="mt-6 space-y-3">
            <label className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
              {needsFollowUp ? "Resume blocked run" : "Refine the brief"}
            </label>
            <textarea
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder={
                needsFollowUp
                  ? "Example: prioritize grass-fed isolate with no sucralose."
                  : "Example: keep only whey isolate options that are third-party tested."
              }
              className="min-h-28 w-full rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm leading-7 text-[color:var(--text-strong)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-[color:var(--accent)]"
            />
            <button
              type="submit"
              disabled={!chatInput.trim() || sending || !activeSessionId}
              className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[color:var(--accent)] px-4 py-3 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {needsFollowUp ? "Resume agent" : "Send follow-up"}
            </button>
            {error ? (
              <div className="rounded-[1.4rem] border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
                {error}
              </div>
            ) : null}
          </form>
        </aside>
      </section>

      <section className="grid gap-8 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-8">
          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Recommendation</p>
                <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Best current match</h2>
              </div>
              {selectedProduct ? (
                <Link
                  href={`/product/${selectedProduct.productId}?session=${activeSessionId}`}
                  className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-2 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                >
                  Full analysis
                  <ChevronRight className="h-4 w-4" />
                </Link>
              ) : null}
            </div>

            {selectedProduct ? (
              <div className="grid gap-5 lg:grid-cols-[1fr_0.9fr]">
                <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                    {selectedProduct.storeName}
                  </p>
                  <h3 className="mt-3 text-3xl font-semibold text-[color:var(--text-strong)]">
                    {selectedProduct.title}
                  </h3>
                  <p className="mt-4 text-sm leading-7 text-[color:var(--text-soft)]">
                    {selectedProduct.ingredientAnalysis.summary}
                  </p>
                  <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-[color:var(--text-soft)]">
                    <span className="text-lg font-semibold text-[color:var(--text-strong)]">
                      ${selectedProduct.price.toFixed(2)}
                    </span>
                    <span>{selectedProduct.shippingETA}</span>
                    <span>{selectedProduct.returnPolicy}</span>
                  </div>
                </div>

                <div className="grid gap-4">
                  <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
                    <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Ingredient score</p>
                    <p className={`mt-3 text-4xl font-semibold ${scoreTone(selectedProduct.ingredientAnalysis.score)}`}>
                      {selectedProduct.ingredientAnalysis.score}
                    </p>
                    <p className="mt-2 text-sm text-[color:var(--text-soft)]">
                      Protein source: {selectedProduct.ingredientAnalysis.proteinSource}
                    </p>
                  </div>
                  <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
                    <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Checkout status</p>
                    <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
                      <ShieldCheck className="h-4 w-4" />
                      {selectedProduct.checkoutReady ? "Ready for checkout handoff" : "Needs extra checkout verification"}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm leading-7 text-[color:var(--text-soft)]">
                No candidate products are available yet for this session.
              </p>
            )}
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Shortlist</p>
                <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Candidate products</h2>
              </div>
              <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
                {sortedProducts.length} items
              </span>
            </div>

            <div className="space-y-5">
              {sortedProducts.map((product) => (
                <ProductCard key={product.productId} product={product} sessionId={activeSessionId ?? ""} />
              ))}
              {!sortedProducts.length ? (
                <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-5 py-6 text-sm text-[color:var(--text-soft)]">
                  No products yet. Continue the session in the chat console to gather enough evidence.
                </div>
              ) : null}
            </div>
          </div>

          <TracePanel trace={recommendation?.trace ?? []} />
        </div>

        <div className="space-y-8">
          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Metrics</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Evidence diagnostics</h2>
            <div className="mt-5 grid gap-3">
              {[
                ["Rating reliability", recommendation?.scientificScore.ratingReliability ?? 0],
                ["Spam authenticity", recommendation?.scientificScore.spamAuthenticity ?? 0],
                ["ABSA alignment", recommendation?.scientificScore.absaAlignment ?? 0],
                ["Visual reliability", recommendation?.scientificScore.visualReliability ?? 0],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4"
                >
                  <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                    <span className="text-[color:var(--text-soft)]">{label}</span>
                    <span className={`font-semibold ${scoreTone(Number(value))}`}>{value}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-[color:var(--background-elevated)]">
                    <div
                      className="h-full rounded-full bg-[color:var(--accent)]"
                      style={{ width: `${Number(value)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-1">
              <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Review volume</p>
                <p className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">
                  {recommendation?.evidenceStats.reviewCount ?? 0}
                </p>
              </div>
              <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Ratings captured</p>
                <p className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">
                  {recommendation?.evidenceStats.ratingCount ?? 0}
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Risk log</p>
                <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Flags and blockers</h2>
              </div>
            </div>

            <div className="space-y-3">
              {(recommendation?.decision?.riskFlags ?? []).map((riskFlag) => (
                <div
                  key={riskFlag}
                  className="rounded-[1.4rem] border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300"
                >
                  {riskFlag}
                </div>
              ))}
              {(recommendation?.blockingAgents ?? []).map((agent) => (
                <div
                  key={agent}
                  className="rounded-[1.4rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300"
                >
                  Blocked by {agent}
                </div>
              ))}
              {!recommendation?.decision?.riskFlags?.length && !recommendation?.blockingAgents?.length ? (
                <div className="rounded-[1.4rem] border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
                  No major blockers detected in the current session state.
                </div>
              ) : null}
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">References</p>
                <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Evidence links</h2>
              </div>
              <MessageSquare className="h-5 w-5 text-[color:var(--accent)]" />
            </div>

            <div className="space-y-3">
              {referenceLinks.map((ref) => (
                <a
                  key={ref}
                  href={ref}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between gap-4 rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-soft)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--text-strong)]"
                >
                  <span className="truncate">{ref}</span>
                  <ExternalLink className="h-4 w-4 shrink-0" />
                </a>
              ))}
              {!referenceLinks.length ? (
                <p className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                  Reference links will appear when evidence has been collected.
                </p>
              ) : null}
            </div>
          </div>

          <Link
            href="/history"
            className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
          >
            <CheckCircle2 className="h-4 w-4" />
            Open session history
          </Link>
        </div>
      </section>
    </div>
  );
}

export default function ResultsPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-7xl items-center justify-center px-4 py-12 md:px-8">
          <LoaderCircle className="h-8 w-8 animate-spin text-[color:var(--accent)]" />
        </div>
      }
    >
      <ResultsContent />
    </Suspense>
  );
}
