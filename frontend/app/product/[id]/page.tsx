"use client";

import Image from "next/image";
import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowUpRight,
  BadgeCheck,
  ExternalLink,
  FlaskConical,
  LoaderCircle,
  ShieldAlert,
  ShieldCheck,
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
import { getSession, getSessionProducts, getStoredSessionId } from "@/lib/api-client";
import type { SessionProduct, SessionSnapshotResponse } from "@/lib/contracts";
import {
  buildReferenceLinks,
  getCollectionInsights,
  getReviewInsights,
} from "@/lib/session-analytics";

function scoreTone(score: number) {
  if (score >= 80) {
    return "text-emerald-600 dark:text-emerald-300";
  }
  if (score >= 60) {
    return "text-amber-600 dark:text-amber-300";
  }
  return "text-rose-600 dark:text-rose-300";
}

function ProductDetailContent() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session") || getStoredSessionId();
  const shell = useAppShellState();

  const [product, setProduct] = useState<SessionProduct | null>(null);
  const [snapshot, setSnapshot] = useState<SessionSnapshotResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!shell.ready) {
        return;
      }

      if (!shell.authConfigured) {
        if (!cancelled) {
          setError(shell.authConfigError || "Cognito configuration is required.");
          setLoading(false);
        }
        return;
      }

      if (!shell.hasToken) {
        if (!cancelled) {
          setError("Login with Cognito before opening product detail.");
          setLoading(false);
        }
        return;
      }

      if (!sessionId) {
        if (!cancelled) {
          setError("Missing session id for this product detail view.");
          setLoading(false);
        }
        return;
      }

      try {
        const [productsResponse, sessionSnapshot] = await Promise.all([
          getSessionProducts(sessionId),
          getSession(sessionId),
        ]);
        const match = productsResponse.items.find((item) => item.productId === params.id) ?? null;
        if (!cancelled) {
          setProduct(match);
          setSnapshot(sessionSnapshot);
          if (!match) {
            setError("Product not found in the selected session.");
          }
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Failed to load product detail.");
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
  }, [params.id, sessionId, shell.authConfigError, shell.authConfigured, shell.hasToken, shell.ready]);

  const reviewInsights = useMemo(() => getReviewInsights(snapshot), [snapshot]);
  const collectionInsights = useMemo(() => getCollectionInsights(snapshot), [snapshot]);

  const radarData = useMemo(() => {
    if (!product) {
      return [];
    }
    return [
      { metric: "Rating", value: product.scientificScore.ratingReliability },
      { metric: "Authenticity", value: product.scientificScore.spamAuthenticity },
      { metric: "ABSA", value: product.scientificScore.absaAlignment },
      { metric: "Visual", value: product.scientificScore.visualReliability },
      { metric: "Final", value: product.scientificScore.finalTrust },
    ];
  }, [product]);

  const ingredientBars = useMemo(() => {
    if (!product) {
      return [];
    }
    return [
      { name: "Beneficial", value: product.ingredientAnalysis.beneficialSignals.length },
      { name: "Red flags", value: product.ingredientAnalysis.redFlags.length },
      { name: "References", value: product.ingredientAnalysis.references.length },
    ];
  }, [product]);

  const evidenceBars = useMemo(() => {
    if (!product) {
      return [];
    }
    return [
      { name: "Coverage", value: product.evidenceStats.sourceCoverage },
      { name: "Reviews", value: product.evidenceStats.reviewCount },
      { name: "Ratings", value: product.evidenceStats.ratingCount },
    ];
  }, [product]);

  const sourceBars = useMemo(
    () =>
      reviewInsights.sourceStats.map((item) => ({
        name: item.source,
        value: item.count,
      })),
    [reviewInsights.sourceStats]
  );

  const referenceLinks = useMemo(
    () => (product ? buildReferenceLinks([product], snapshot) : []),
    [product, snapshot]
  );

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-7xl items-center justify-center px-4 py-12 md:px-8">
        <LoaderCircle className="h-8 w-8 animate-spin text-[color:var(--accent)]" />
      </div>
    );
  }

  if (!product) {
    return (
      <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-4xl items-center justify-center px-4 py-12 md:px-8">
        <div className="w-full rounded-[2rem] border border-amber-500/20 bg-amber-500/10 p-8 shadow-[var(--shadow-soft)]">
          <p className="text-xs uppercase tracking-[0.28em] text-amber-700 dark:text-amber-300">Detail unavailable</p>
          <p className="mt-4 text-sm leading-7 text-[color:var(--text-soft)]">
            {error ?? "No product detail available."}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            {shell.loginHref && shell.authConfigured && !shell.hasToken ? (
              <a
                href={shell.loginHref}
                className="rounded-full bg-[color:var(--accent)] px-4 py-3 text-sm font-medium text-white transition hover:opacity-90"
              >
                Login with Cognito
              </a>
            ) : null}
            <Link
              href={sessionId ? `/results?session=${sessionId}` : "/results"}
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to results
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-8 md:px-8 md:py-12">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href={sessionId ? `/results?session=${sessionId}` : "/results"}
          className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-2 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to session
        </Link>
        <span className="rounded-full border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-2 text-xs uppercase tracking-[0.24em] text-[color:var(--text-muted)]">
          Product analysis
        </span>
      </div>

      <section className="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
        <div className="rounded-[2.5rem] border border-[color:var(--border-strong)] bg-[color:var(--surface)] p-7 shadow-[var(--shadow-strong)]">
          {product.imageUrl ? (
            <div className="mb-6 overflow-hidden rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-muted)]">
              <Image
                src={product.imageUrl}
                alt={product.title}
                width={1200}
                height={560}
                className="h-64 w-full object-cover"
              />
            </div>
          ) : null}
          <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">{product.storeName}</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-[-0.05em] text-[color:var(--text-strong)] md:text-5xl">
            {product.title}
          </h1>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[color:var(--text-soft)]">
            {product.ingredientAnalysis.summary}
          </p>

          <div className="mt-8 grid gap-4 md:grid-cols-4">
            <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Price</p>
              <p className="mt-2 text-3xl font-semibold text-[color:var(--text-strong)]">${product.price.toFixed(2)}</p>
            </div>
            <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Trust</p>
              <p className={`mt-2 text-3xl font-semibold ${scoreTone(product.scientificScore.finalTrust)}`}>
                {product.scientificScore.finalTrust}
              </p>
            </div>
            <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Ingredient score</p>
              <p className={`mt-2 text-3xl font-semibold ${scoreTone(product.ingredientAnalysis.score)}`}>
                {product.ingredientAnalysis.score}
              </p>
            </div>
            <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Protein source</p>
              <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">
                {product.ingredientAnalysis.proteinSource}
              </p>
            </div>
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <a
              href={product.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full bg-[color:var(--text-strong)] px-5 py-3 text-sm font-medium text-[color:var(--background)] transition hover:bg-[color:var(--accent)]"
            >
              Open merchant
              <ExternalLink className="h-4 w-4" />
            </a>
            <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-strong)]">
              {product.checkoutReady ? (
                <ShieldCheck className="h-4 w-4 text-emerald-500" />
              ) : (
                <ShieldAlert className="h-4 w-4 text-amber-500" />
              )}
              {product.checkoutReady ? "Checkout-ready handoff" : "Needs extra checkout checks"}
            </div>
            <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-strong)]">
              <BadgeCheck className="h-4 w-4 text-[color:var(--accent)]" />
              {product.shippingETA}
            </div>
          </div>
        </div>

        <div className="rounded-[2.4rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
          <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Scientific scoring</p>
          <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Trust profile radar</h2>
          <div className="mt-6 h-80">
            <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={280}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="var(--border)" />
                <PolarAngleAxis dataKey="metric" tick={{ fill: "currentColor", fontSize: 12 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                <Radar dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.18} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-1">
            <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Rating summary</p>
              <p className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">
                {reviewInsights.ratingSummary.avgRating.toFixed(1)}
              </p>
              <p className="mt-1 text-sm text-[color:var(--text-soft)]">
                {reviewInsights.ratingSummary.ratingCount} ratings captured
              </p>
            </div>
            <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Promo likelihood</p>
              <p className={`mt-2 text-2xl font-semibold ${scoreTone(100 - reviewInsights.paidPromoLikelihood)}`}>
                {reviewInsights.paidPromoLikelihood}%
              </p>
              <p className="mt-1 text-sm text-[color:var(--text-soft)]">Lower is better.</p>
            </div>
            <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Cache posture</p>
              <p className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">
                {collectionInsights.cacheStatus}
              </p>
              <p className="mt-1 text-sm text-[color:var(--text-soft)]">
                {collectionInsights.isSufficient ? "Evidence threshold passed." : "Collector filled missing coverage."}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-8 xl:grid-cols-[1.08fr_0.92fr]">
        <div className="space-y-8">
          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Ingredients</p>
                <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Signals and flags</h2>
              </div>
              <FlaskConical className="h-5 w-5 text-[color:var(--accent)]" />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-[1.7rem] border border-emerald-500/20 bg-emerald-500/10 p-5">
                <p className="text-xs uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300">Beneficial</p>
                <div className="mt-4 space-y-3">
                  {product.ingredientAnalysis.beneficialSignals.map((signal) => (
                    <div key={`${signal.ingredient}-${signal.note}`} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3">
                      <p className="text-sm font-semibold text-[color:var(--text-strong)]">{signal.ingredient}</p>
                      <p className="mt-1 text-sm text-[color:var(--text-soft)]">{signal.note}</p>
                    </div>
                  ))}
                  {!product.ingredientAnalysis.beneficialSignals.length ? (
                    <p className="text-sm text-[color:var(--text-soft)]">No beneficial signals detected.</p>
                  ) : null}
                </div>
              </div>

              <div className="rounded-[1.7rem] border border-rose-500/20 bg-rose-500/10 p-5">
                <p className="text-xs uppercase tracking-[0.2em] text-rose-700 dark:text-rose-300">Red flags</p>
                <div className="mt-4 space-y-3">
                  {product.ingredientAnalysis.redFlags.map((signal) => (
                    <div key={`${signal.ingredient}-${signal.note}`} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3">
                      <p className="text-sm font-semibold text-[color:var(--text-strong)]">{signal.ingredient}</p>
                      <p className="mt-1 text-sm text-[color:var(--text-soft)]">{signal.note}</p>
                    </div>
                  ))}
                  {!product.ingredientAnalysis.redFlags.length ? (
                    <p className="text-sm text-[color:var(--text-soft)]">No material ingredient flags detected.</p>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Breakdown</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Signal distribution</h2>
            <div className="mt-6 h-72">
              <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={240}>
                <BarChart data={ingredientBars} barSize={42}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="name" tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="var(--accent)" radius={[14, 14, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <TracePanel trace={product.trace} />
        </div>

        <div className="space-y-8">
          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Evidence stats</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Coverage chart</h2>
            <div className="mt-6 h-72">
              <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={240}>
                <BarChart data={evidenceBars} barSize={42}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="name" tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#d78c43" radius={[14, 14, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Review coverage</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Source mix</h2>
            <div className="mt-6 h-72">
              <ResponsiveContainer width="100%" height="100%" minWidth={280} minHeight={240}>
                <BarChart data={sourceBars} barSize={36}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="name" tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="var(--text-strong)" radius={[14, 14, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Pros / cons</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Review summary</h2>
            <div className="mt-6 grid gap-4">
              <div className="rounded-[1.5rem] border border-emerald-500/20 bg-emerald-500/10 p-5">
                <p className="text-xs uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300">Pros</p>
                <ul className="mt-4 space-y-3">
                  {product.pros.map((pro) => (
                    <li key={pro} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                      {pro}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-[1.5rem] border border-rose-500/20 bg-rose-500/10 p-5">
                <p className="text-xs uppercase tracking-[0.2em] text-rose-700 dark:text-rose-300">Cons</p>
                <ul className="mt-4 space-y-3">
                  {product.cons.map((con) => (
                    <li key={con} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                      {con}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Evidence ledger</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Source quality table</h2>
            <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-[color:var(--border)]">
              <div className="grid grid-cols-[0.22fr_0.2fr_0.2fr_1fr] bg-[color:var(--surface-strong)] px-4 py-3 text-[11px] uppercase tracking-[0.24em] text-[color:var(--text-muted)]">
                <span>Source</span>
                <span>Quality</span>
                <span>Promo</span>
                <span>Excerpt</span>
              </div>
              {reviewInsights.rankedEvidence.slice(0, 5).map((item) => (
                <div
                  key={`${item.docId}-${item.source}`}
                  className="grid grid-cols-[0.22fr_0.2fr_0.2fr_1fr] gap-3 border-t border-[color:var(--border)] px-4 py-4 text-sm"
                >
                  <span className="font-medium capitalize text-[color:var(--text-strong)]">{item.source}</span>
                  <span className={scoreTone(item.qualityScore)}>{item.qualityScore}</span>
                  <span className="text-[color:var(--text-soft)]">{item.promoSignals.length}</span>
                  <span className="max-h-12 overflow-hidden text-[color:var(--text-soft)]">{item.excerpt || item.docId}</span>
                </div>
              ))}
              {!reviewInsights.rankedEvidence.length ? (
                <div className="px-4 py-5 text-sm text-[color:var(--text-soft)]">
                  Ranked evidence will appear after review analysis is available.
                </div>
              ) : null}
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">References</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Source links</h2>
            <div className="mt-6 space-y-3">
              {referenceLinks.map((ref) => (
                <a
                  key={ref}
                  href={ref}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between gap-4 rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-soft)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--text-strong)]"
                >
                  <span className="truncate">{ref}</span>
                  <ArrowUpRight className="h-4 w-4 shrink-0" />
                </a>
              ))}
              {!referenceLinks.length ? (
                <p className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                  No external references were captured for this product yet.
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

export default function ProductDetailPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto flex min-h-[calc(100vh-10rem)] w-full max-w-7xl items-center justify-center px-4 py-12 md:px-8">
          <LoaderCircle className="h-8 w-8 animate-spin text-[color:var(--accent)]" />
        </div>
      }
    >
      <ProductDetailContent />
    </Suspense>
  );
}
