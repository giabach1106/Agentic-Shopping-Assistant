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
import type {
  AssistantMessageMeta,
  ChatResponse,
  NextAction,
  RecommendationResponse,
  SessionMessage,
  SessionProduct,
  SessionSnapshotResponse,
} from "@/lib/contracts";
import { buildReferenceLinks, getCollectionInsights, getReviewInsights } from "@/lib/session-analytics";

type RenderMessage = SessionMessage & {
  optimistic?: boolean;
  clientId?: string;
};

const THINKING_STAGES = [
  "Planner: locking constraints",
  "Coverage auditor: checking DB and cache",
  "Collector: filling missing evidence",
  "Scorer: computing trust and risk",
  "Decision: preparing final recommendation",
];

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

function formatRating(value: number | null | undefined) {
  if (typeof value !== "number" || value <= 0) {
    return "N/A";
  }
  return value.toFixed(1);
}

function tierRank(tier: string | null | undefined) {
  const normalized = (tier || "strict").toLowerCase();
  if (normalized === "strict") return 0;
  if (normalized === "soft_5") return 1;
  if (normalized === "soft_10") return 2;
  if (normalized === "soft_15") return 3;
  return 9;
}

function tierLabel(tier: string | null | undefined) {
  const normalized = (tier || "strict").toLowerCase();
  if (normalized === "soft_5") return "soft +5%";
  if (normalized === "soft_10") return "soft +10%";
  if (normalized === "soft_15") return "soft +15%";
  return "strict";
}

function actionButtonClass(style: NextAction["style"]) {
  if (style === "primary") {
    return "bg-[color:var(--accent)] text-white hover:opacity-90";
  }
  if (style === "secondary") {
    return "border border-[color:var(--border)] bg-[color:var(--surface)] text-[color:var(--text-strong)] hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]";
  }
  return "border border-transparent bg-[color:var(--surface-strong)] text-[color:var(--text-soft)] hover:text-[color:var(--text-strong)]";
}

function coverageConfidenceClass(confidence: string) {
  if (confidence === "strong") {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
  if (confidence === "limited") {
    return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300";
}

function evidenceSentiment(excerpt: string) {
  const lowered = excerpt.toLowerCase();
  const positive = [
    "third-party",
    "grass-fed",
    "mixes well",
    "good value",
    "fast shipping",
    "lactose free",
  ].filter((token) => lowered.includes(token));
  const negative = [
    "fake",
    "bad taste",
    "overpriced",
    "late delivery",
    "stomach",
    "clump",
  ].filter((token) => lowered.includes(token));
  return { positive, negative };
}

function ingredientDelta(index: number, type: "good" | "risk") {
  if (type === "good") {
    return Math.max(3, 8 - index);
  }
  return Math.max(4, 11 - index * 2);
}

function canonicalProductKey(product: SessionProduct) {
  if (product.canonicalProductId) {
    return product.canonicalProductId;
  }
  const normalizedTitle = product.title.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  return normalizedTitle || product.sourceUrl;
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

  let recommendation: RecommendationResponse | null = null;
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
  const [recommendation, setRecommendation] = useState<RecommendationResponse | ChatResponse | null>(null);
  const [products, setProducts] = useState<SessionProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [optimisticMessages, setOptimisticMessages] = useState<RenderMessage[]>([]);
  const [thinkingStageIndex, setThinkingStageIndex] = useState(0);
  const [desktopRailOpen, setDesktopRailOpen] = useState(true);
  const [mobileRailOpen, setMobileRailOpen] = useState(false);
  const bootKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!sending) {
      return;
    }
    setThinkingStageIndex(0);
    const timer = window.setInterval(() => {
      setThinkingStageIndex((current) => Math.min(current + 1, THINKING_STAGES.length - 1));
    }, 1200);
    return () => {
      window.clearInterval(timer);
    };
  }, [sending]);

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
            includeRecommendation: true,
            includeProducts: true,
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
    return firstUserMessage?.content || query || "Shopping analysis session";
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

  const sortedProducts = useMemo(() => {
    const deduped = new Map<string, SessionProduct>();
    for (const product of products) {
      const key = canonicalProductKey(product);
      const current = deduped.get(key);
      const currentTier = tierRank(current?.constraintTier);
      const nextTier = tierRank(product.constraintTier);
      const currentRating = typeof current?.rating === "number" ? current.rating : 0;
      const nextRating = typeof product.rating === "number" ? product.rating : 0;
      if (
        !current ||
        nextTier < currentTier ||
        (nextTier === currentTier && nextRating > currentRating) ||
        (nextTier === currentTier && nextRating === currentRating && product.price < current.price)
      ) {
        deduped.set(key, product);
      }
    }
    return [...deduped.values()].sort((left, right) => {
      const leftTier = tierRank(left.constraintTier);
      const rightTier = tierRank(right.constraintTier);
      if (leftTier !== rightTier) return leftTier - rightTier;
      const leftRating = typeof left.rating === "number" ? left.rating : 0;
      const rightRating = typeof right.rating === "number" ? right.rating : 0;
      if (leftRating !== rightRating) return rightRating - leftRating;
      if (left.price !== right.price) return left.price - right.price;
      return left.title.localeCompare(right.title);
    });
  }, [products]);
  const topProducts = useMemo(() => sortedProducts.slice(0, 10), [sortedProducts]);
  const strictProducts = useMemo(
    () => topProducts.filter((product) => !product.constraintRelaxed),
    [topProducts]
  );

  const selectedProduct = useMemo(() => {
    const hasStrict = strictProducts.length > 0;
    const scope = hasStrict ? strictProducts : topProducts;
    if (!recommendation?.decision?.selectedCandidate) {
      return scope[0] ?? null;
    }
    const selected = scope.find(
      (product) => product.sourceUrl === recommendation.decision?.selectedCandidate?.sourceUrl
    );
    return selected ?? scope[0] ?? null;
  }, [recommendation?.decision, strictProducts, topProducts]);

  const latestAssistantMessage = useMemo(
    () =>
      [...messages]
        .reverse()
        .find((message) => message.role === "assistant" && message.content.trim().length > 0),
    [messages]
  );
  const latestAssistantMeta = useMemo(
    () => (latestAssistantMessage?.meta as AssistantMessageMeta | null) ?? null,
    [latestAssistantMessage?.meta]
  );
  const checkpointConversation = useMemo(
    () =>
      ((snapshot?.checkpointState as {
        reply_kind?: string;
        support_level?: string;
        conversation_mode?: string;
        conversation_intent?: string;
        pending_action?: unknown;
        clarification_pending?: unknown;
        next_actions?: NextAction[];
      } | null) ?? null),
    [snapshot?.checkpointState]
  );
  const activeReplyKind =
    recommendation?.replyKind ||
    latestAssistantMeta?.replyKind ||
    checkpointConversation?.reply_kind ||
    "answer";
  const activeSupportLevel =
    recommendation?.supportLevel ||
    latestAssistantMeta?.supportLevel ||
    checkpointConversation?.support_level ||
    "unsupported";
  const activePendingAction =
    recommendation?.pendingAction ||
    latestAssistantMeta?.pendingAction ||
    null;
  const activeClarificationPending =
    recommendation?.clarificationPending ||
    latestAssistantMeta?.clarificationPending ||
    ((checkpointConversation?.clarification_pending as
      | { field?: string; prompt?: string; example?: string | null }
      | null) ??
      null);
  const quickActions: NextAction[] =
    recommendation?.nextActions?.length
      ? recommendation.nextActions
      : latestAssistantMeta?.nextActions?.length
        ? latestAssistantMeta.nextActions
        : checkpointConversation?.next_actions?.length
          ? checkpointConversation.next_actions
          : [];
  const activeCoverageConfidence =
    recommendation?.coverageConfidence ||
    latestAssistantMeta?.coverageConfidence ||
    "weak";
  const activeCheckoutReadiness =
    recommendation?.checkoutReadiness ||
    latestAssistantMeta?.checkoutReadiness ||
    "unknown";
  const commerceCoverage =
    recommendation?.evidenceStats.commerceSourceCoverage ??
    recommendation?.coverageAudit?.commerceSourceCoverage ??
    0;
  const totalSourceCoverage =
    recommendation?.evidenceStats.sourceCoverage ??
    recommendation?.coverageAudit?.sourceCoverage ??
    0;
  const agentReplyText =
    recommendation?.reply ||
    latestAssistantMessage?.content ||
    "Session is active. Add one follow-up constraint to continue.";

  const trustRadarData = useMemo(
    () => [
      { metric: "Rating", value: (recommendation?.scientificScore.ratingReliability ?? 0) * 100 },
      { metric: "Authenticity", value: (recommendation?.scientificScore.spamAuthenticity ?? 0) * 100 },
      { metric: "ABSA", value: (recommendation?.scientificScore.absaAlignment ?? 0) * 100 },
      { metric: "Visual", value: (recommendation?.scientificScore.visualReliability ?? 0) * 100 },
      { metric: "Final", value: recommendation?.scientificScore.finalTrust ?? 0 },
    ],
    [recommendation?.scientificScore]
  );
  const hasTrustRadarSignal = useMemo(
    () => trustRadarData.some((entry) => entry.value > 0),
    [trustRadarData]
  );

  const sourceMixData = useMemo(
    () => reviewInsights.sourceStats.map((item) => ({ source: item.source, count: item.count })),
    [reviewInsights.sourceStats]
  );

  const absaData = useMemo(
    () => reviewInsights.absaSignals.map((item) => ({ aspect: item.aspect, score: item.score })),
    [reviewInsights.absaSignals]
  );

  const evidenceRows = useMemo(
    () =>
      reviewInsights.rankedEvidence.slice(0, 8).map((item) => {
        const sentiment = evidenceSentiment(item.excerpt || item.docId);
        return {
          ...item,
          positiveCount: sentiment.positive.length,
          negativeCount: sentiment.negative.length,
        };
      }),
    [reviewInsights.rankedEvidence]
  );

  function renderLiveSessionRail(mode: "desktop" | "mobile") {
    const isMobile = mode === "mobile";

    return (
      <div className="flex h-full min-h-0 flex-col">
        <div className="border-b border-[color:var(--border)] px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Live session</p>
              <h2 className="mt-2 text-xl font-semibold text-[color:var(--text-strong)]">Shopping copilot</h2>
              <p className="mt-2 text-sm leading-6 text-[color:var(--text-soft)]">
                Clarifications, crawl confirmations, and session follow-up live here.
              </p>
            </div>
            <button
              type="button"
              onClick={() => (isMobile ? setMobileRailOpen(false) : setDesktopRailOpen(false))}
              className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
            >
              {isMobile ? "Close" : "Collapse"}
            </button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2 text-[11px]">
            <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-[color:var(--text-muted)]">
              {messages.length} messages
            </span>
            <span className={`rounded-full border px-3 py-1 ${coverageConfidenceClass(activeCoverageConfidence)}`}>
              Coverage: {activeCoverageConfidence}
            </span>
            <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-[color:var(--text-muted)]">
              Checkout: {activeCheckoutReadiness}
            </span>
          </div>
        </div>

        {sending ? (
          <div className="border-b border-[color:var(--border)] px-5 py-4">
            <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-[color:var(--text-strong)]">
                <LoaderCircle className="h-4 w-4 animate-spin text-[color:var(--accent)]" />
                {THINKING_STAGES[thinkingStageIndex]}
              </div>
              <p className="mt-2 text-xs leading-6 text-[color:var(--text-muted)]">
                Reasoning continues while the main analysis refreshes.
              </p>
            </div>
          </div>
        ) : null}

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <div className="space-y-3">
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
              const messageActions = Array.isArray(meta?.nextActions)
                ? (meta.nextActions as NextAction[])
                : [];
              return (
                <div key={`${message.createdAt}-${message.clientId ?? index}`} className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
                  {!isUser ? (
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
                      <Bot className="h-4 w-4" />
                    </div>
                  ) : null}
                  <div className={`max-w-[88%] rounded-[1.5rem] px-4 py-3 text-sm leading-7 ${isUser ? "bg-[color:var(--text-strong)] text-[color:var(--background)]" : "border border-[color:var(--border)] bg-[color:var(--surface-strong)] text-[color:var(--text-soft)]"}`}>
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
                    {!isUser && messageActions.length ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {messageActions.slice(0, 3).map((action) => (
                          <span
                            key={action.id}
                            className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-medium opacity-80 ${actionButtonClass(action.style)}`}
                          >
                            {action.label}
                          </span>
                        ))}
                      </div>
                    ) : null}
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
                          {typeof meta.handledBy === "string" || typeof meta.replyKind === "string" ? (
                            <p>
                              Handled by: {String(meta.handledBy || "unknown")} | Reply kind:{" "}
                              {String(meta.replyKind || "answer")}
                            </p>
                          ) : null}
                          {typeof meta.conversationIntent === "string" || typeof meta.supportLevel === "string" ? (
                            <p>
                              Intent: {String(meta.conversationIntent || "unknown")} | Support:{" "}
                              {String(meta.supportLevel || "unsupported")}
                            </p>
                          ) : null}
                          {topReasons.length ? <p>Factors: {topReasons.join(" | ")}</p> : null}
                          {missingEvidence.length ? <p>Missing: {missingEvidence.join(", ")}</p> : null}
                          {meta.pendingAction && typeof meta.pendingAction === "object" ? (
                            <p>Pending action: {String((meta.pendingAction as { type?: string }).type || "none")}</p>
                          ) : null}
                        </div>
                      </details>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-t border-[color:var(--border)] px-5 py-4">
          {activePendingAction ? (
            <div className="mb-3 rounded-[1.3rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
              Awaiting confirmation: {activePendingAction.prompt}
            </div>
          ) : null}
          {!activePendingAction && activeClarificationPending ? (
            <div className="mb-3 rounded-[1.3rem] border border-sky-500/20 bg-sky-500/10 px-4 py-3 text-sm text-sky-700 dark:text-sky-300">
              {activeClarificationPending.prompt}
            </div>
          ) : null}
          {quickActions.length ? (
            <div className="mb-3 flex flex-wrap gap-2">
              {quickActions.slice(0, 4).map((action) => (
                <button
                  key={action.id}
                  type="button"
                  onClick={() => void sendChatMessage(action.message)}
                  disabled={sending || !activeSessionId}
                  className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${actionButtonClass(action.style)}`}
                >
                  {action.label}
                </button>
              ))}
            </div>
          ) : null}
          <label className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
            {activeReplyKind === "confirmation_request"
              ? "Confirm next action"
              : activeClarificationPending
                ? "Optional preference"
                : needsFollowUp
                  ? "Resume blocked run"
                  : activeReplyKind === "discovery"
                    ? "Add key requirements"
                    : "Refine the brief"}
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
            placeholder={
              activeReplyKind === "confirmation_request"
                ? "Example: yes, do it. Or: no, keep the current state."
                : activeClarificationPending?.example
                  ? `Example: ${activeClarificationPending.example}`
                  : activeReplyKind === "discovery"
                    ? "Example: budget under $200, under 55 inches wide, and delivery this week."
                    : needsFollowUp
                      ? "Example: prioritize verified sellers with free returns."
                      : "Example: keep only options with 4.5+ stars and delivery this week."
            }
            className="mt-3 min-h-28 w-full rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm leading-7 text-[color:var(--text-strong)] outline-none transition placeholder:text-[color:var(--text-muted)] focus:border-[color:var(--accent)]"
          />
          <button type="button" onClick={() => void sendChatMessage()} disabled={!chatInput.trim() || sending || !activeSessionId} className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-full bg-[color:var(--accent)] px-4 py-3 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">
            {sending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {activeReplyKind === "confirmation_request"
              ? "Send confirmation"
              : activeClarificationPending
                ? "Add preference"
                : needsFollowUp
                  ? "Resume agent"
                  : activeReplyKind === "discovery"
                    ? "Send requirements"
                    : "Send follow-up"}
          </button>
          {error ? (
            <div className="mt-3 rounded-[1.4rem] border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
              {error}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  async function sendChatMessage(presetMessage?: string) {
    const outgoing = (presetMessage ?? chatInput).trim();
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
    if (!presetMessage) {
      setChatInput("");
    } else {
      setChatInput("");
    }
    setSending(true);
    setError(null);
    try {
      const turn = needsFollowUp
        ? await resumeRun(activeSessionId, outgoing)
        : await runChat(activeSessionId, outgoing);
      const bundle = await loadSessionBundle(activeSessionId, {
        includeRecommendation: true,
        includeProducts: true,
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
    <div className={`mx-auto flex w-full max-w-[110rem] flex-col gap-8 px-4 py-8 transition-[padding] duration-300 md:px-8 md:py-12 ${desktopRailOpen ? "xl:pr-[27rem]" : "xl:pr-24"}`}>
      <div className="flex items-center justify-between gap-3 xl:hidden">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Session tools</p>
          <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Live session rail</h2>
        </div>
        <button
          type="button"
          onClick={() => setMobileRailOpen(true)}
          className="rounded-full border border-[color:var(--border)] px-4 py-2 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
        >
          Open chat
        </button>
      </div>

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)] xl:items-start">
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
                label="Commerce coverage"
                value={`${commerceCoverage} sources`}
              />
              <MetricCard
                label="Evidence freshness"
                value={formatFreshness(recommendation?.evidenceStats.freshnessSeconds ?? 0)}
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className={`rounded-full border px-3 py-1 text-xs ${coverageConfidenceClass(activeCoverageConfidence)}`}>
                Coverage confidence: {activeCoverageConfidence}
              </span>
              <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
                Checkout readiness: {activeCheckoutReadiness}
              </span>
              <button
                type="button"
                onClick={() => setDesktopRailOpen((current) => !current)}
                className="hidden rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)] xl:inline-flex"
              >
                {desktopRailOpen ? "Collapse live rail" : "Expand live rail"}
              </button>
            </div>
            <div className="mt-8 grid gap-4 lg:grid-cols-2">
              <div className="rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Agent response</p>
                <p className="mt-4 text-sm leading-7 text-[color:var(--text-soft)]">{agentReplyText}</p>
                {activeReplyKind === "confirmation_request" && activePendingAction ? (
                  <div className="mt-4 rounded-[1.3rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                    Awaiting confirmation: {activePendingAction.prompt}
                  </div>
                ) : null}
                {activeReplyKind === "discovery" ? (
                  <div className="mt-4 rounded-[1.3rem] border border-sky-500/20 bg-sky-500/10 px-4 py-3 text-sm text-sky-700 dark:text-sky-300">
                    Discovery mode is active. Share the most important requirements and I will route the next step.
                  </div>
                ) : null}
                {activeSupportLevel === "discovery_only" ? (
                  <div className="mt-4 rounded-[1.3rem] border border-slate-500/20 bg-slate-500/10 px-4 py-3 text-sm text-slate-700 dark:text-slate-300">
                    This category is currently in discovery-only mode, so the assistant will refine the brief before any live evidence run.
                  </div>
                ) : null}
                {needsFollowUp && activeReplyKind !== "confirmation_request" ? (
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

            <div className="mt-8 rounded-[1.9rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Recommendation</p>
                <span className="rounded-full border border-emerald-500/35 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-700 dark:text-emerald-300">
                  Best current match
                </span>
              </div>
              {selectedProduct ? (
                <div className="mt-4 grid gap-4 md:grid-cols-[10rem_minmax(0,1fr)_12rem]">
                  <div className="relative h-40 overflow-hidden rounded-[1.3rem] border border-[color:var(--border)] bg-[color:var(--surface-muted)]">
                    {typeof selectedProduct.imageUrl === "string" && selectedProduct.imageUrl.startsWith("http") ? (
                      <Image src={selectedProduct.imageUrl} alt={selectedProduct.title} fill className="object-cover" />
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                        No image
                      </div>
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">{selectedProduct.storeName}</p>
                    <h3 className="mt-2 line-clamp-2 text-xl font-semibold leading-8 text-[color:var(--text-strong)]">
                      {selectedProduct.title}
                    </h3>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-[color:var(--text-soft)]">
                      {selectedProduct.productInsight.headline}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-[color:var(--text-soft)]">
                      <span className="text-lg font-semibold text-[color:var(--text-strong)]">
                        ${selectedProduct.price.toFixed(2)}
                      </span>
                      <span>{formatRating(selectedProduct.rating)} stars</span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-xs ${
                          selectedProduct.constraintRelaxed
                            ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                            : "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                        }`}
                      >
                        {tierLabel(selectedProduct.constraintTier)}
                      </span>
                    </div>
                  </div>
                  <div className="grid gap-3">
                    <div className="rounded-[1.2rem] border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                        {selectedProduct.productInsight.analysisMode === "supplement" ? "Ingredient score" : "Analysis mode"}
                      </p>
                      <p className={`mt-2 text-2xl font-semibold ${selectedProduct.productInsight.analysisMode === "supplement" ? scoreTone(selectedProduct.ingredientAnalysis.score) : "text-[color:var(--text-strong)]"}`}>
                        {selectedProduct.productInsight.analysisMode === "supplement"
                          ? selectedProduct.ingredientAnalysis.score
                          : selectedProduct.productInsight.analysisMode}
                      </p>
                    </div>
                    <ul className="space-y-2 text-xs leading-6 text-[color:var(--text-soft)]">
                      {selectedProduct.productInsight.analysisMode === "supplement"
                        ? selectedProduct.ingredientAnalysis.beneficialSignals.slice(0, 2).map((signal, index) => (
                            <li key={`${signal.ingredient}-${signal.note}`} className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-2">
                              +{ingredientDelta(index, "good")} {signal.ingredient}
                            </li>
                          ))
                        : selectedProduct.productInsight.strengths.slice(0, 2).map((item) => (
                            <li key={item} className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-2">
                              {item}
                            </li>
                          ))}
                      {selectedProduct.productInsight.analysisMode === "supplement"
                        ? selectedProduct.ingredientAnalysis.redFlags.slice(0, 1).map((signal, index) => (
                            <li
                              key={`${signal.ingredient}-${signal.note}`}
                              className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-rose-700 dark:text-rose-300"
                            >
                              -{ingredientDelta(index, "risk")} risk: {signal.ingredient}
                            </li>
                          ))
                        : selectedProduct.productInsight.cautions.slice(0, 1).map((item) => (
                            <li
                              key={item}
                              className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-rose-700 dark:text-rose-300"
                            >
                              {item}
                            </li>
                          ))}
                    </ul>
                    <Link
                      href={`/product/${selectedProduct.productId}?session=${activeSessionId}`}
                      className="inline-flex items-center justify-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-2 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                    >
                      Full analysis
                      <ChevronRight className="h-4 w-4" />
                    </Link>
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-sm leading-7 text-[color:var(--text-soft)]">
                  No candidate products are available yet for this session.
                </p>
              )}
            </div>

            <div className="mt-8 w-full">
              <div className="mb-4 flex items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Immediate shortlist</p>
                <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
                  {topProducts.length} unique products
                </span>
              </div>
              {topProducts.length ? (
                <div className="overflow-x-auto pb-2">
                  <div className="flex min-w-max gap-4">
                  {topProducts.map((product) => {
                    const imageUrl =
                      typeof product.imageUrl === "string" && product.imageUrl.startsWith("http")
                        ? product.imageUrl
                        : null;
                    const isTopPick = selectedProduct?.productId === product.productId;
                    return (
                      <article
                        key={product.productId}
                        className={`w-[250px] overflow-hidden rounded-[1.6rem] border bg-[color:var(--surface-strong)] ${
                          isTopPick
                            ? "border-[color:var(--accent)] shadow-[0_12px_24px_rgba(0,0,0,0.08)]"
                            : "border-[color:var(--border)]"
                        }`}
                      >
                        <div className="relative h-36 w-full bg-[color:var(--surface-muted)]">
                          {imageUrl ? (
                            <Image src={imageUrl} alt={product.title} fill className="object-cover" />
                          ) : (
                            <div className="flex h-full items-center justify-center text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                              No image
                            </div>
                          )}
                          {isTopPick ? (
                            <span className="absolute left-3 top-3 rounded-full bg-[color:var(--text-strong)] px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-[color:var(--background)]">
                              Top pick
                            </span>
                          ) : null}
                        </div>
                        <div className="space-y-3 p-4">
                          <p className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--text-muted)]">
                            {product.storeName}
                          </p>
                          <h3 className="line-clamp-2 text-base font-semibold leading-6 text-[color:var(--text-strong)]">
                            {product.title}
                          </h3>
                          <div className="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-soft)]">
                            <span className="text-sm font-semibold text-[color:var(--text-strong)]">
                              ${product.price.toFixed(2)}
                            </span>
                            <span>{formatRating(product.rating)} stars</span>
                            <span
                              className={`rounded-full border px-2 py-0.5 ${
                                product.constraintRelaxed
                                  ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                                  : "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                              }`}
                            >
                              {tierLabel(product.constraintTier)}
                            </span>
                            {(product.offers?.length ?? 0) > 1 ? (
                              <span className="rounded-full border border-[color:var(--border)] px-2 py-0.5 text-[10px] text-[color:var(--text-muted)]">
                                {product.offers?.length} offers
                              </span>
                            ) : null}
                          </div>
                          <Link
                            href={`/product/${product.productId}?session=${activeSessionId}`}
                            className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-3 py-2 text-xs text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
                          >
                            Analyze product
                            <ChevronRight className="h-3.5 w-3.5" />
                          </Link>
                        </div>
                      </article>
                    );
                  })}
                  </div>
                </div>
              ) : (
                <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                  No product cards available yet. Continue chat to unlock candidate extraction.
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      <div className="hidden xl:block">
        {desktopRailOpen ? (
          <aside className="fixed inset-y-0 right-0 z-40 hidden w-[26rem] border-l border-[color:var(--border)] bg-[color:var(--surface)]/98 shadow-[-16px_0_40px_rgba(0,0,0,0.08)] backdrop-blur-xl xl:block">
            <div className="flex h-full min-h-0 flex-col pt-24">
              {renderLiveSessionRail("desktop")}
            </div>
          </aside>
        ) : (
          <button
            type="button"
            onClick={() => setDesktopRailOpen(true)}
            className="fixed right-5 top-28 z-40 hidden rounded-full border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-3 text-sm text-[color:var(--text-strong)] shadow-[var(--shadow-soft)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)] xl:inline-flex"
          >
            Open live rail
          </button>
        )}
      </div>

      {mobileRailOpen ? (
        <div className="fixed inset-0 z-50 xl:hidden">
          <button
            type="button"
            onClick={() => setMobileRailOpen(false)}
            className="absolute inset-0 bg-black/30"
            aria-label="Close live session rail"
          />
          <aside className="absolute inset-y-0 right-0 flex w-full max-w-[28rem] flex-col border-l border-[color:var(--border)] bg-[color:var(--surface)] shadow-[-12px_0_32px_rgba(0,0,0,0.18)]">
            <div className="pt-6">{renderLiveSessionRail("mobile")}</div>
          </aside>
        </div>
      ) : null}

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

            <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div className="min-w-0 space-y-8">
                <TracePanel trace={recommendation?.trace ?? []} />

                <Panel eyebrow="Evidence ledger" title="Ranked review evidence">
                  <div className="overflow-hidden rounded-[1.5rem] border border-[color:var(--border)]">
                    <div className="grid grid-cols-[minmax(80px,0.2fr)_64px_64px_64px_64px_minmax(0,1fr)] gap-3 bg-[color:var(--surface-strong)] px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
                      <span>Source</span>
                      <span>Quality</span>
                      <span>Promo</span>
                      <span>Pos</span>
                      <span>Neg</span>
                      <span>Excerpt</span>
                    </div>
                    {evidenceRows.map((item) => (
                      <div
                        key={`${item.docId}-${item.source}`}
                        className="grid grid-cols-[minmax(80px,0.2fr)_64px_64px_64px_64px_minmax(0,1fr)] gap-3 border-t border-[color:var(--border)] px-4 py-4 text-sm"
                      >
                        <span className="font-medium capitalize text-[color:var(--text-strong)]">{item.source}</span>
                        <span className={scoreTone(item.qualityScore)}>{item.qualityScore}</span>
                        <span className="text-[color:var(--text-soft)]">{item.promoSignals.length}</span>
                        <span className="text-emerald-700 dark:text-emerald-300">{item.positiveCount}</span>
                        <span className="text-rose-700 dark:text-rose-300">{item.negativeCount}</span>
                        <span className="line-clamp-2 text-[color:var(--text-soft)]" title={item.excerpt || item.docId}>
                          {item.excerpt || item.docId}
                        </span>
                      </div>
                    ))}
                    {!evidenceRows.length ? (
                      <div className="border-t border-[color:var(--border)] px-4 py-4 text-sm text-[color:var(--text-soft)]">
                        Ranked evidence will appear when the review agent has enough context.
                      </div>
                    ) : null}
                  </div>
                </Panel>
              </div>

              <div className="min-w-0 space-y-8">
                <Panel eyebrow="Decision matrix" title="Scientific trust radar">
                  {hasTrustRadarSignal ? (
                    <div className="h-80">
                      <ResponsiveContainer width="100%" height="100%">
                        <RadarChart data={trustRadarData}>
                          <PolarGrid stroke="var(--border)" />
                          <PolarAngleAxis dataKey="metric" tick={{ fill: "currentColor", fontSize: 12 }} />
                          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                          <Radar dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.2} />
                        </RadarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="rounded-[1.4rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                      Insufficient signal for a meaningful radar profile in this turn.
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap gap-2">
                    {trustRadarData.map((item) => (
                      <span
                        key={item.metric}
                        className="rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-3 py-1 text-xs text-[color:var(--text-soft)]"
                      >
                        {item.metric}: {item.value.toFixed(1)}
                      </span>
                    ))}
                  </div>
                </Panel>

                <Panel eyebrow="Evidence posture" title="Collection diagnostics">
                  <div className="grid gap-3 md:grid-cols-2">
                    <MetricCard label="Cache status" value={collectionInsights.cacheStatus} />
                    <MetricCard label="Catalog status" value={recommendation?.coverageAudit?.catalogStatus ?? "unknown"} />
                    <MetricCard label="Commerce coverage" value={commerceCoverage} />
                    <MetricCard label="Total sources" value={totalSourceCoverage} />
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
                    <ResponsiveContainer width="100%" height="100%">
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
                    <ResponsiveContainer width="100%" height="100%">
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
  );
}

export default function ResultsPage() {
  return (
    <Suspense fallback={<div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-7xl items-center justify-center px-4 py-12 md:px-8"><LoaderCircle className="h-8 w-8 animate-spin text-[color:var(--accent)]" /></div>}>
      <ResultsContent />
    </Suspense>
  );
}

