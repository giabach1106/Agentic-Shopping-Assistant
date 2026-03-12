"use client";

import Image from "next/image";
import Link from "next/link";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  LoaderCircle,
  Send,
  ShieldCheck,
  Sparkles,
  User,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { TracePanel } from "@/components/trace-panel";
import { useAppShellState } from "@/hooks/use-app-shell-state";
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
import type { ChatResponse, SessionMessage, SessionProduct, SessionSnapshotResponse } from "@/lib/contracts";
import { buildReferenceLinks, getCollectionInsights, getReviewInsights } from "@/lib/session-analytics";

type RenderMessage = SessionMessage & {
  optimistic?: boolean;
  clientId?: string;
};

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

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
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

async function loadSessionBundle(
  sessionId: string,
  options: {
    includeRecommendation?: boolean;
    includeProducts?: boolean;
  } = {}
) {
  const includeRecommendation = options.includeRecommendation ?? true;
  const includeProducts = options.includeProducts ?? true;
  const [snapshotResult, recommendationResult, productsResult] = await Promise.allSettled([
    getSession(sessionId),
    includeRecommendation ? getRecommendation(sessionId) : Promise.resolve(null),
    includeProducts ? getSessionProducts(sessionId) : Promise.resolve({ sessionId, items: [] }),
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

  return { snapshot: snapshotResult.value, recommendation, products };
}

function Panel({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
      <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">{title}</h2>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
      <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">{label}</p>
      <p className={`mt-3 text-3xl font-semibold ${tone ?? "text-[color:var(--text-strong)]"}`}>{value}</p>
    </div>
  );
}

function ResultsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const shell = useAppShellState();
  const query = searchParams.get("q")?.trim() ?? "";
  const sessionParam = searchParams.get("session");

  const [activeSessionId, setActiveSessionId] = useState<string | null>(sessionParam);
  const [snapshot, setSnapshot] = useState<SessionSnapshotResponse | null>(null);
  const [recommendation, setRecommendation] = useState<ChatResponse | null>(null);
  const [products, setProducts] = useState<SessionProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [optimisticMessages, setOptimisticMessages] = useState<RenderMessage[]>([]);
  const bootKeyRef = useRef<string | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = chatScrollRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [snapshot?.messages, optimisticMessages, sending]);

  useEffect(() => {
    if (!shell.ready) {
      return;
    }

    const bootKey = `${sessionParam ?? ""}|${query}|${shell.hasToken ? "auth" : "anon"}`;
    if (bootKeyRef.current === bootKey) {
      return;
    }
    bootKeyRef.current = bootKey;

    let cancelled = false;

    async function bootstrap() {
      if (!shell.authConfigured) {
        if (!cancelled) {
          setError(shell.authConfigError || "Cognito configuration is required.");
          setLoading(false);
        }
        return;
      }

      if (!shell.hasToken) {
        if (!cancelled) {
          setError("Login with Cognito before starting or resuming an agent session.");
          setLoading(false);
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
          const firstTurn = await runChat(created.sessionId, query);
          const bundle = await loadSessionBundle(created.sessionId, {
            includeRecommendation: Boolean(firstTurn.decision),
            includeProducts: Boolean(firstTurn.decision),
          });
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
  }, [query, router, sessionParam, shell.authConfigError, shell.authConfigured, shell.hasToken, shell.ready]);

  const currentPrompt = useMemo(() => {
    const firstUserMessage = snapshot?.messages.find((message) => message.role === "user");
    return firstUserMessage?.content || query || "Supplements screening session";
  }, [query, snapshot?.messages]);

  const needsFollowUp =
    recommendation?.status === "NEED_DATA" ||
    Boolean((snapshot?.checkpointState as { needs_follow_up?: boolean } | null)?.needs_follow_up);

  const messages: RenderMessage[] = useMemo(
    () => [...(snapshot?.messages ?? []), ...optimisticMessages],
    [optimisticMessages, snapshot?.messages]
  );
  const reviewInsights = useMemo(() => getReviewInsights(snapshot), [snapshot]);
  const collectionInsights = useMemo(() => getCollectionInsights(snapshot), [snapshot]);
  const referenceLinks = useMemo(() => buildReferenceLinks(products, snapshot), [products, snapshot]);

  const sortedProducts = useMemo(
    () => [...products].sort((left, right) => right.scientificScore.finalTrust - left.scientificScore.finalTrust),
    [products]
  );
  const topProducts = useMemo(() => sortedProducts.slice(0, 10), [sortedProducts]);

  const selectedProduct = useMemo(() => {
    if (!recommendation?.decision?.selectedCandidate) {
      return topProducts[0] ?? null;
    }
    return (
      topProducts.find(
        (product) => product.sourceUrl === recommendation.decision?.selectedCandidate?.sourceUrl
      ) ??
      topProducts[0] ??
      null
    );
  }, [recommendation?.decision, topProducts]);

  const latestAssistantMessage = useMemo(
    () =>
      [...messages]
        .reverse()
        .find((message) => message.role === "assistant" && message.content.trim().length > 0),
    [messages]
  );
  const agentReplyText =
    recommendation?.reply ||
    latestAssistantMessage?.content ||
    "Session is active. Add one follow-up constraint to continue.";

  const trustRadarData = useMemo(
    () => [
      { metric: "Rating", value: recommendation?.scientificScore.ratingReliability ?? 0 },
      { metric: "Authenticity", value: recommendation?.scientificScore.spamAuthenticity ?? 0 },
      { metric: "ABSA", value: recommendation?.scientificScore.absaAlignment ?? 0 },
      { metric: "Visual", value: recommendation?.scientificScore.visualReliability ?? 0 },
      { metric: "Final", value: recommendation?.scientificScore.finalTrust ?? 0 },
    ],
    [recommendation?.scientificScore]
  );

  const sourceMixData = useMemo(
    () => reviewInsights.sourceStats.map((item) => ({ source: item.source, count: item.count })),
    [reviewInsights.sourceStats]
  );

  const absaData = useMemo(
    () => reviewInsights.absaSignals.map((item) => ({ aspect: item.aspect, score: item.score })),
    [reviewInsights.absaSignals]
  );

  async function sendChatMessage() {
    const outgoing = chatInput.trim();
    if (!activeSessionId || !outgoing) {
      return;
    }

    const optimistic: RenderMessage = {
      role: "user",
      content: outgoing,
      createdAt: new Date().toISOString(),
      optimistic: true,
      clientId: `local-${Date.now()}`,
    };

    setOptimisticMessages((current) => [...current, optimistic]);
    setChatInput("");
    setSending(true);
    setError(null);
    try {
      const turn = needsFollowUp
        ? await resumeRun(activeSessionId, outgoing)
        : await runChat(activeSessionId, outgoing);
      const bundle = await loadSessionBundle(activeSessionId, {
        includeRecommendation: Boolean(turn.decision),
        includeProducts: Boolean(turn.decision),
      });
      setOptimisticMessages([]);
      setSnapshot(bundle.snapshot);
      setRecommendation(bundle.recommendation ?? turn);
      setProducts(bundle.products);
    } catch (nextError) {
      setOptimisticMessages((current) => current.filter((item) => item.clientId !== optimistic.clientId));
      setChatInput(outgoing);
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
                {shell.loginHref && shell.authConfigured && !shell.hasToken ? (
                  <a href={shell.loginHref} className="rounded-full bg-[color:var(--accent)] px-5 py-3 text-sm font-medium text-white transition hover:opacity-90">
                    Login with Cognito
                  </a>
                ) : null}
                <Link href="/" className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-5 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]">
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
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_25.5rem]">
        <div className="min-w-0 space-y-8">
          <section className="rounded-[2.5rem] border border-[color:var(--border-strong)] bg-[color:var(--surface)] p-7 shadow-[var(--shadow-strong)]">
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
            <h1 className="mt-5 max-w-4xl text-4xl font-semibold leading-[1.02] tracking-[-0.05em] text-[color:var(--text-strong)] md:text-5xl">
              {currentPrompt}
            </h1>
            <div className="mt-8 grid gap-4 md:grid-cols-4">
              <MetricCard label="Verdict" value={recommendation?.decision?.verdict ?? "Pending"} />
              <MetricCard
                label="Trust score"
                value={recommendation?.scientificScore.finalTrust ?? 0}
                tone={scoreTone(recommendation?.scientificScore.finalTrust ?? 0)}
              />
              <MetricCard
                label="Source coverage"
                value={`${recommendation?.evidenceStats.sourceCoverage ?? 0} sources`}
              />
              <MetricCard
                label="Evidence freshness"
                value={formatFreshness(recommendation?.evidenceStats.freshnessSeconds ?? 0)}
              />
            </div>
            <div className="mt-8 grid gap-4 lg:grid-cols-2">
              <div className="rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Agent response</p>
                <p className="mt-4 text-sm leading-7 text-[color:var(--text-soft)]">{agentReplyText}</p>
                {needsFollowUp ? (
                  <div className="mt-4 rounded-[1.3rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                    The orchestrator needs more detail before finalizing. Reply in the chat panel to continue the run.
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
                </div>
              </div>
            </div>

            <div className="mt-8">
              <div className="mb-4 flex items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Immediate shortlist</p>
                <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
                  {topProducts.length} products
                </span>
              </div>
              {topProducts.length ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {topProducts.map((product) => {
                    const imageUrl =
                      typeof product.imageUrl === "string" && product.imageUrl.startsWith("http")
                        ? product.imageUrl
                        : null;
                    return (
                      <article
                        key={product.productId}
                        className="overflow-hidden rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)]"
                      >
                        <div className="relative h-44 w-full bg-[color:var(--surface-muted)]">
                          {imageUrl ? (
                            <Image src={imageUrl} alt={product.title} fill className="object-cover" />
                          ) : (
                            <div className="flex h-full items-center justify-center text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                              No image
                            </div>
                          )}
                        </div>
                        <div className="space-y-3 p-4">
                          <p className="text-xs uppercase tracking-[0.22em] text-[color:var(--text-muted)]">
                            {product.storeName}
                          </p>
                          <h3 className="line-clamp-2 text-lg font-semibold leading-7 text-[color:var(--text-strong)]">
                            {product.title}
                          </h3>
                          <div className="flex flex-wrap items-center gap-3 text-sm text-[color:var(--text-soft)]">
                            <span className="font-semibold text-[color:var(--text-strong)]">
                              ${product.price.toFixed(2)}
                            </span>
                            <span>{product.rating ? product.rating.toFixed(1) : "n/a"} stars</span>
                          </div>
                          <Link
                            href={`/product/${product.productId}?session=${activeSessionId}`}
                            className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-2 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                          >
                            Analyze product
                            <ChevronRight className="h-4 w-4" />
                          </Link>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                  No product cards available yet. Continue chat to unlock candidate extraction.
                </div>
              )}
            </div>
          </section>

          <Panel eyebrow="Recommendation" title="Best current match">
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
                  <MetricCard
                    label="Ingredient score"
                    value={selectedProduct.ingredientAnalysis.score}
                    tone={scoreTone(selectedProduct.ingredientAnalysis.score)}
                  />
                  <div className="rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
                    <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                      Checkout status
                    </p>
                    <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
                      <ShieldCheck className="h-4 w-4" />
                      {selectedProduct.checkoutReady
                        ? "Ready for checkout handoff"
                        : "Needs extra checkout verification"}
                    </div>
                    <Link
                      href={`/product/${selectedProduct.productId}?session=${activeSessionId}`}
                      className="mt-4 inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-2 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                    >
                      Full analysis
                      <ChevronRight className="h-4 w-4" />
                    </Link>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-sm leading-7 text-[color:var(--text-soft)]">
                No candidate products are available yet for this session.
              </p>
            )}
          </Panel>

          <details className="group rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <summary className="cursor-pointer list-none">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
                    Session diagnostics
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">
                    Expand full reasoning and evidence charts
                  </h2>
                </div>
                <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
                  Optional
                </span>
              </div>
            </summary>

            <div className="mt-6 grid gap-8 xl:grid-cols-[1.1fr_0.9fr]">
              <div className="space-y-8">
                <TracePanel trace={recommendation?.trace ?? []} />

                <Panel eyebrow="Evidence ledger" title="Ranked review evidence">
                  <div className="overflow-hidden rounded-[1.5rem] border border-[color:var(--border)]">
                    <div className="grid grid-cols-[0.24fr_0.18fr_0.18fr_1fr] bg-[color:var(--surface-strong)] px-4 py-3 text-[11px] uppercase tracking-[0.24em] text-[color:var(--text-muted)]">
                      <span>Source</span>
                      <span>Quality</span>
                      <span>Promo</span>
                      <span>Excerpt</span>
                    </div>
                    {reviewInsights.rankedEvidence.slice(0, 5).map((item) => (
                      <div
                        key={`${item.docId}-${item.source}`}
                        className="grid grid-cols-[0.24fr_0.18fr_0.18fr_1fr] gap-3 border-t border-[color:var(--border)] px-4 py-4 text-sm"
                      >
                        <span className="font-medium capitalize text-[color:var(--text-strong)]">{item.source}</span>
                        <span className={scoreTone(item.qualityScore)}>{item.qualityScore}</span>
                        <span className="text-[color:var(--text-soft)]">{item.promoSignals.length}</span>
                        <span className="text-[color:var(--text-soft)]">{item.excerpt || item.docId}</span>
                      </div>
                    ))}
                    {!reviewInsights.rankedEvidence.length ? (
                      <div className="border-t border-[color:var(--border)] px-4 py-4 text-sm text-[color:var(--text-soft)]">
                        Ranked evidence will appear when the review agent has enough context.
                      </div>
                    ) : null}
                  </div>
                </Panel>
              </div>

              <div className="space-y-8">
                <Panel eyebrow="Decision matrix" title="Scientific trust radar">
                  <div className="h-80">
                    <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={280}>
                      <RadarChart data={trustRadarData}>
                        <PolarGrid stroke="var(--border)" />
                        <PolarAngleAxis dataKey="metric" tick={{ fill: "currentColor", fontSize: 12 }} />
                        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                        <Radar dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.18} />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>

                <Panel eyebrow="Evidence posture" title="Collection diagnostics">
                  <div className="grid gap-3 md:grid-cols-2">
                    <MetricCard label="Cache status" value={collectionInsights.cacheStatus} />
                    <MetricCard label="Catalog status" value={recommendation?.coverageAudit?.catalogStatus ?? "unknown"} />
                    <MetricCard label="Evidence quality" value={reviewInsights.evidenceQualityScore} tone={scoreTone(reviewInsights.evidenceQualityScore)} />
                    <MetricCard label="Review confidence" value={reviewInsights.confidence} tone={scoreTone(reviewInsights.confidence)} />
                    <MetricCard label="Duplicate clusters" value={reviewInsights.duplicateReviewClusters} />
                    <MetricCard label="Crawler" value={recommendation?.coverageAudit?.crawlPerformed ? "expanded" : "skipped"} />
                  </div>
                  {!collectionInsights.isSufficient || collectionInsights.sufficiencyMissing.length ? (
                    <div className="mt-4 rounded-[1.4rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                      Missing thresholds: {collectionInsights.sufficiencyMissing.join(", ") || "collector filled the gap"}
                    </div>
                  ) : null}
                </Panel>

                <Panel eyebrow="Review coverage" title="Source mix">
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={240}>
                      <BarChart data={sourceMixData} barSize={38}>
                        <CartesianGrid vertical={false} stroke="var(--border)" />
                        <XAxis dataKey="source" tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                        <YAxis allowDecimals={false} tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                        <Tooltip />
                        <Bar dataKey="count" fill="var(--text-strong)" radius={[14, 14, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>

                <Panel eyebrow="Aspect signals" title="ABSA alignment">
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={240}>
                      <BarChart data={absaData} barSize={30} layout="vertical">
                        <CartesianGrid horizontal={false} stroke="var(--border)" />
                        <XAxis type="number" domain={[0, 100]} tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                        <YAxis dataKey="aspect" type="category" tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} width={84} />
                        <Tooltip />
                        <Bar dataKey="score" fill="var(--accent)" radius={[0, 14, 14, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>

                <Panel eyebrow="Risk log" title="Flags and blockers">
                  <div className="space-y-3">
                    {[...(recommendation?.decision?.riskFlags ?? []), ...reviewInsights.riskFlags].map((riskFlag) => (
                      <div key={riskFlag} className="rounded-[1.4rem] border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
                        {riskFlag}
                      </div>
                    ))}
                    {(recommendation?.blockingAgents ?? []).map((agent) => (
                      <div key={agent} className="rounded-[1.4rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                        Blocked by {agent}
                      </div>
                    ))}
                    {!recommendation?.decision?.riskFlags?.length && !recommendation?.blockingAgents?.length && !reviewInsights.riskFlags.length ? (
                      <div className="rounded-[1.4rem] border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
                        No major blockers detected in the current session state.
                      </div>
                    ) : null}
                  </div>
                </Panel>

                <Panel eyebrow="References" title="Evidence links">
                  <div className="space-y-3">
                    {referenceLinks.map((ref) => (
                      <a key={ref} href={ref} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-4 rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-soft)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--text-strong)]">
                        <span className="truncate">{ref}</span>
                        <ExternalLink className="h-4 w-4 shrink-0" />
                      </a>
                    ))}
                    {!referenceLinks.length ? (
                      <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                        Reference links will appear after evidence is collected.
                      </div>
                    ) : null}
                  </div>
                </Panel>
              </div>
            </div>
          </details>

          <Link href="/history" className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]">
            <CheckCircle2 className="h-4 w-4" />
            Open session history
          </Link>
        </div>

        <aside className="flex flex-col rounded-[2.4rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)] xl:sticky xl:top-24 xl:h-[calc(100vh-7rem)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Live session</p>
              <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Follow-up console</h2>
            </div>
            <div className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
              {messages.length} messages
            </div>
          </div>
          <div ref={chatScrollRef} className="mt-6 flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
            {messages.map((message, index) => {
              const isUser = message.role === "user";
              const meta =
                !isUser && message.meta && typeof message.meta === "object"
                  ? (message.meta as Record<string, unknown>)
                  : null;
              const topReasons = Array.isArray(meta?.topReasons)
                ? meta?.topReasons.map((item) => String(item))
                : [];
              const missingEvidence = Array.isArray(meta?.missingEvidence)
                ? meta?.missingEvidence.map((item) => String(item))
                : [];
              return (
                <div key={`${message.createdAt}-${message.clientId ?? index}`} className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
                  {!isUser ? (
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
                      <Bot className="h-4 w-4" />
                    </div>
                  ) : null}
                  <div className={`max-w-[84%] rounded-[1.5rem] px-4 py-3 text-sm leading-7 ${isUser ? "bg-[color:var(--text-strong)] text-[color:var(--background)]" : "border border-[color:var(--border)] bg-[color:var(--surface-strong)] text-[color:var(--text-soft)]"}`}>
                    <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.24em] opacity-70">
                      {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                      {message.role}
                      <span>{formatTimestamp(message.createdAt)}</span>
                      {message.optimistic ? (
                        <span className="rounded-full border border-[color:var(--border)] px-2 py-0.5 text-[10px]">
                          sending
                        </span>
                      ) : null}
                    </div>
                    <p>{meta?.summary ? String(meta.summary) : message.content}</p>
                    {!isUser && meta ? (
                      <details className="mt-2 rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-2">
                        <summary className="cursor-pointer text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                          Reasoning details
                        </summary>
                        <div className="mt-2 space-y-2 text-xs leading-6">
                          {typeof meta.verdict === "string" || typeof meta.trust === "number" ? (
                            <p>
                              Verdict: {String(meta.verdict || "pending")} | Trust:{" "}
                              {typeof meta.trust === "number" ? meta.trust.toFixed(2) : "n/a"}
                            </p>
                          ) : null}
                          {topReasons.length ? <p>Factors: {topReasons.join(" | ")}</p> : null}
                          {missingEvidence.length ? <p>Missing: {missingEvidence.join(", ")}</p> : null}
                        </div>
                      </details>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-6 space-y-3">
            <label className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
              {needsFollowUp ? "Resume blocked run" : "Refine the brief"}
            </label>
            <textarea
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendChatMessage();
                }
              }}
              placeholder={needsFollowUp ? "Example: prioritize grass-fed isolate with no sucralose." : "Example: keep only whey isolate options that are third-party tested."}
              className="min-h-28 w-full rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm leading-7 text-[color:var(--text-strong)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-[color:var(--accent)]"
            />
            <button type="button" onClick={() => void sendChatMessage()} disabled={!chatInput.trim() || sending || !activeSessionId} className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[color:var(--accent)] px-4 py-3 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">
              {sending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {needsFollowUp ? "Resume agent" : "Send follow-up"}
            </button>
            {error ? (
              <div className="rounded-[1.4rem] border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
                {error}
              </div>
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default function ResultsPage() {
  return (
    <Suspense fallback={<div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-7xl items-center justify-center px-4 py-12 md:px-8"><LoaderCircle className="h-8 w-8 animate-spin text-[color:var(--accent)]" /></div>}>
      <ResultsContent />
    </Suspense>
  );
}
