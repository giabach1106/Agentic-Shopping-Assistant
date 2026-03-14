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
import type { EvidenceRow, SessionProduct, SessionSnapshotResponse } from "@/lib/contracts";
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

function formatRating(value: number | null | undefined) {
  if (typeof value !== "number" || value <= 0) {
    return "N/A";
  }
  return value.toFixed(1);
}

function productKeywords(title: string) {
  return title
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length >= 4)
    .slice(0, 8);
}

function normalizePercentValue(value: number | null | undefined) {
  const numeric = typeof value === "number" ? value : 0;
  const normalized = numeric <= 1 ? numeric * 100 : numeric;
  return Math.max(0, Math.min(100, normalized));
}

function isKnownValue(value: string | null | undefined) {
  const normalized = (value || "").trim().toLowerCase();
  return normalized.length > 0 && normalized !== "unknown" && normalized !== "n/a";
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
  const [selectedSource, setSelectedSource] = useState<string>("all");
  const [titleExpanded, setTitleExpanded] = useState(false);
  const [headlineExpanded, setHeadlineExpanded] = useState(false);

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
  const offers = useMemo(() => {
    if (!product) {
      return [];
    }
    if (product.offers?.length) {
      return product.offers;
    }
    return [
      {
        source: product.source,
        storeName: product.storeName,
        sourceUrl: product.sourceUrl,
        price: product.price,
        rating: product.rating,
        ratingCount: 0,
        shippingETA: product.shippingETA,
        returnPolicy: product.returnPolicy,
        imageUrl: product.imageUrl,
      },
    ];
  }, [product]);

  const sourceTabs = useMemo(() => {
    const unique = [...new Set(offers.map((offer) => offer.source.toLowerCase()))];
    return ["all", ...unique];
  }, [offers]);

  useEffect(() => {
    if (selectedSource !== "all" && !sourceTabs.includes(selectedSource)) {
      setSelectedSource("all");
    }
  }, [selectedSource, sourceTabs]);

  const filteredOffers = useMemo(() => {
    if (selectedSource === "all") {
      return offers;
    }
    return offers.filter((offer) => offer.source.toLowerCase() === selectedSource);
  }, [offers, selectedSource]);

  const ratingCoverage = useMemo(() => {
    if (product?.ratingCoverage) {
      return product.ratingCoverage;
    }
    const ratedOfferCount = offers.filter(
      (offer) => (offer.rating ?? 0) > 0 || (offer.ratingCount ?? 0) > 0
    ).length;
    return {
      ratedOfferCount,
      totalOfferCount: offers.length,
    };
  }, [offers, product?.ratingCoverage]);

  const productRatingSummary = useMemo(() => {
    if (!filteredOffers.length) {
      return { avg: 0, count: 0, hasSignal: false };
    }
    const rated = filteredOffers.filter((offer) => (offer.rating ?? 0) > 0);
    if (!rated.length) {
      return { avg: 0, count: 0, hasSignal: false };
    }
    const weightedCount = rated.reduce(
      (acc, offer) => acc + Math.max(1, offer.ratingCount ?? 0),
      0
    );
    const weightedTotal = rated.reduce(
      (acc, offer) =>
        acc + (offer.rating ?? 0) * Math.max(1, offer.ratingCount ?? 0),
      0
    );
    return {
      avg: weightedCount > 0 ? weightedTotal / weightedCount : 0,
      count: weightedCount,
      hasSignal: true,
    };
  }, [filteredOffers]);

  const filteredRankedEvidence = useMemo(() => {
    const allEvidence = reviewInsights.rankedEvidence;
    if (!allEvidence.length) {
      return [];
    }
    const sourceFiltered =
      selectedSource === "all"
        ? allEvidence
        : allEvidence.filter((item) => item.source.toLowerCase() === selectedSource);
    if (!product) {
      return sourceFiltered;
    }
    const keywords = productKeywords(product.title);
    const scoped = sourceFiltered.filter((item) => {
      const haystack = `${item.excerpt} ${item.docId}`.toLowerCase();
      return keywords.some((token) => haystack.includes(token));
    });
    return scoped.length ? scoped : sourceFiltered;
  }, [product, reviewInsights.rankedEvidence, selectedSource]);

  const productEvidenceRows = useMemo(() => {
    if (!product) {
      return [] as EvidenceRow[];
    }
    const scopedFromProduct = (product.evidenceRows ?? []).filter((row) =>
      selectedSource === "all" ? true : row.source.toLowerCase() === selectedSource
    );
    if (scopedFromProduct.length) {
      return scopedFromProduct.slice(0, 12);
    }
    return filteredRankedEvidence.slice(0, 12).map((item) => ({
      docId: item.docId,
      source: item.source,
      kind: item.kind,
      qualityScore: item.qualityScore,
      relevanceScore: item.relevanceScore,
      productMatch: item.productMatch,
      promoSignals: item.promoSignals,
      excerpt: item.excerpt,
      positiveSignals: item.positiveSignals,
      negativeSignals: item.negativeSignals,
      sentimentScore: item.sentimentScore,
    }));
  }, [filteredRankedEvidence, product, selectedSource]);

  const scopedProsCons = useMemo(() => {
    const pros = productEvidenceRows
      .filter((row) => row.sentimentScore > 0 && row.excerpt)
      .map((row) => row.excerpt)
      .slice(0, 4);
    const cons = productEvidenceRows
      .filter((row) => row.sentimentScore < 0 && row.excerpt)
      .map((row) => row.excerpt)
      .slice(0, 4);
    return {
      pros: pros.length ? pros : (product?.pros ?? []).slice(0, 4),
      cons: cons.length ? cons : (product?.cons ?? []).slice(0, 4),
    };
  }, [product?.cons, product?.pros, productEvidenceRows]);

  const radarData = useMemo(() => {
    if (!product) {
      return [];
    }
    return [
      { metric: "Fit", value: product.scoreBreakdown.productFit ?? 0 },
      { metric: "Evidence", value: product.scoreBreakdown.evidenceConfidence ?? 0 },
      { metric: "Crawl", value: product.scoreBreakdown.crawlHealth ?? 0 },
      { metric: "Decision", value: product.scoreBreakdown.decisionScore ?? 0 },
    ];
  }, [product]);
  const hasRadarSignal = useMemo(
    () => radarData.some((entry) => entry.value > 0),
    [radarData]
  );

  const insightBars = useMemo(() => {
    if (!product) {
      return [];
    }
    if (product.productInsight.analysisMode !== "supplement") {
      return [
        { name: "Strengths", value: product.productInsight.strengths.length },
        { name: "Cautions", value: product.productInsight.cautions.length },
        { name: "Attributes", value: product.productInsight.keyAttributes.length },
      ];
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
    const domain = product.productInsight.analysisMode;
    const coverageTarget = domain === "supplement" ? 4 : 3;
    const reviewTarget = domain === "supplement" ? 24 : 12;
    const ratingTarget = domain === "supplement" ? 400 : 250;
    const raw = [
      { name: "Coverage", value: product.evidenceStats.commerceSourceCoverage || product.evidenceStats.sourceCoverage, target: coverageTarget },
      { name: "Reviews", value: product.evidenceDiagnostics.acceptedReviewCount || product.evidenceStats.reviewCount, target: reviewTarget },
      { name: "Ratings", value: product.evidenceStats.ratingCount, target: ratingTarget },
    ];
    return raw.map((item) => ({
      ...item,
      normalized: Math.min(100, Math.round((item.value / Math.max(1, item.target)) * 100)),
    }));
  }, [product]);

  const sourceBars = useMemo(
    () =>
      reviewInsights.sourceStats.map((item) => ({
        name: item.source,
        value: item.count,
      })),
    [reviewInsights.sourceStats]
  );

  const referenceLinks = useMemo(() => {
    if (!product) {
      return [];
    }
    const allLinks = buildReferenceLinks([product], snapshot);
    if (selectedSource === "all") {
      return allLinks;
    }
    const sourceDomains = new Set(
      offers
        .filter((offer) => offer.source.toLowerCase() === selectedSource)
        .map((offer) => {
          try {
            return new URL(offer.sourceUrl).hostname.replace(/^www\./, "");
          } catch {
            return "";
          }
        })
        .filter(Boolean)
    );
    return allLinks.filter((link) => {
      try {
        const host = new URL(link).hostname.replace(/^www\./, "");
        return sourceDomains.has(host);
      } catch {
        return false;
      }
    });
  }, [offers, product, selectedSource, snapshot]);

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
          <h1
            className={`mt-4 text-2xl font-semibold leading-8 text-[color:var(--text-strong)] md:text-3xl md:leading-10 ${
              titleExpanded ? "" : "line-clamp-3"
            }`}
          >
            {product.title}
          </h1>
          {product.title.length > 140 ? (
            <button
              type="button"
              onClick={() => setTitleExpanded((current) => !current)}
              className="mt-3 rounded-full border border-[color:var(--border)] px-3 py-1 text-xs uppercase tracking-[0.18em] text-[color:var(--text-muted)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
            >
              {titleExpanded ? "Collapse title" : "Expand title"}
            </button>
          ) : null}
          <p
            className={`mt-4 max-w-4xl text-sm leading-7 text-[color:var(--text-soft)] ${
              headlineExpanded ? "" : "line-clamp-3"
            }`}
          >
            {product.productInsight.headline}
          </p>
          {product.productInsight.headline.length > 180 ? (
            <button
              type="button"
              onClick={() => setHeadlineExpanded((current) => !current)}
              className="mt-3 rounded-full border border-[color:var(--border)] px-3 py-1 text-xs uppercase tracking-[0.18em] text-[color:var(--text-muted)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
            >
              {headlineExpanded ? "Read less" : "Read more"}
            </button>
          ) : null}
          {product.decisionSummary ? (
            <p className="mt-3 max-w-4xl text-sm leading-7 text-[color:var(--text-muted)]">
              {product.decisionSummary}
            </p>
          ) : null}

          <div className="mt-8 grid gap-4 md:grid-cols-4">
            <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Price</p>
              <p className="mt-2 text-3xl font-semibold text-[color:var(--text-strong)]">${product.price.toFixed(2)}</p>
            </div>
            <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Decision score</p>
              <p className={`mt-2 text-3xl font-semibold ${scoreTone(product.scoreBreakdown.decisionScore || product.scientificScore.finalTrust)}`}>
                {product.scoreBreakdown.decisionScore || product.scientificScore.finalTrust}
              </p>
            </div>
            <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                {product.productInsight.analysisMode === "supplement" ? "Ingredient score" : "Insight mode"}
              </p>
              <p className={`mt-2 text-3xl font-semibold ${product.productInsight.analysisMode === "supplement" ? scoreTone(product.ingredientAnalysis.score) : "text-[color:var(--text-strong)]"}`}>
                {product.productInsight.analysisMode === "supplement"
                  ? product.ingredientAnalysis.score
                  : product.productInsight.analysisMode}
              </p>
              <ul className="mt-3 space-y-1 text-xs text-[color:var(--text-soft)]">
                {product.productInsight.analysisMode === "supplement"
                  ? product.ingredientAnalysis.beneficialSignals.slice(0, 1).map((signal) => (
                      <li key={`metric-good-${signal.ingredient}`}>+8 {signal.ingredient}</li>
                    ))
                  : product.productInsight.strengths.slice(0, 2).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                {product.productInsight.analysisMode === "supplement"
                  ? product.ingredientAnalysis.redFlags.slice(0, 1).map((signal) => (
                      <li key={`metric-risk-${signal.ingredient}`} className="text-rose-700 dark:text-rose-300">
                        -10 {signal.ingredient}
                      </li>
                    ))
                  : null}
              </ul>
            </div>
            <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                {product.productInsight.analysisMode === "supplement" ? "Protein source" : "Primary focus"}
              </p>
              <p className="mt-2 text-lg font-semibold text-[color:var(--text-strong)]">
                {product.productInsight.analysisMode === "supplement"
                  ? product.ingredientAnalysis.proteinSource
                  : product.productInsight.keyAttributes[0]?.value || "general"}
              </p>
            </div>
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <a
              href={product.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full border border-[color:var(--accent)] bg-[color:var(--accent-soft)] px-5 py-3 text-sm font-medium text-[color:var(--accent)] transition hover:bg-[color:var(--accent)] hover:text-white"
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
            {isKnownValue(product.shippingETA) ? (
              <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-strong)]">
                <BadgeCheck className="h-4 w-4 text-[color:var(--accent)]" />
                {product.shippingETA}
              </div>
            ) : null}
            {isKnownValue(product.returnPolicy) ? (
              <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3 text-sm text-[color:var(--text-strong)]">
                <BadgeCheck className="h-4 w-4 text-[color:var(--accent)]" />
                {product.returnPolicy}
              </div>
            ) : null}
          </div>

          <div className="mt-6 grid gap-3 md:grid-cols-3">
            {product.productInsight.keyAttributes.slice(0, 6).map((item) => (
              <div
                key={`${item.label}-${item.value}`}
                className="rounded-[1.3rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3"
              >
                <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-muted)]">{item.label}</p>
                <p className="mt-2 text-sm font-medium text-[color:var(--text-strong)]">{item.value}</p>
              </div>
            ))}
          </div>

          <div className="mt-8 rounded-[1.8rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-[color:var(--text-muted)]">Offer comparison</p>
                <h3 className="mt-1 text-lg font-semibold text-[color:var(--text-strong)]">
                  {filteredOffers.length} offers across {sourceTabs.length - 1} sources
                </h3>
              </div>
              <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
                Rated offers {ratingCoverage.ratedOfferCount}/{ratingCoverage.totalOfferCount}
              </span>
            </div>
            <div className="mb-4 flex flex-wrap gap-2">
              {sourceTabs.map((source) => (
                <button
                  key={source}
                  type="button"
                  onClick={() => setSelectedSource(source)}
                  className={`rounded-full border px-3 py-1 text-xs transition ${
                    selectedSource === source
                      ? "border-[color:var(--accent)] bg-[color:var(--accent-soft)] text-[color:var(--accent)]"
                      : "border-[color:var(--border)] text-[color:var(--text-muted)] hover:text-[color:var(--text-strong)]"
                  }`}
                >
                  {source === "all" ? "all sources" : source}
                </button>
              ))}
            </div>
            <div className="grid gap-3">
              {filteredOffers.slice(0, 6).map((offer) => (
                <div
                  key={offer.sourceUrl}
                  className="grid gap-2 rounded-[1.2rem] border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-3 md:grid-cols-[1fr_auto_auto_auto]"
                >
                  <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">{offer.source}</p>
                    <p className="mt-1 text-sm font-medium text-[color:var(--text-strong)]">{offer.storeName}</p>
                  </div>
                  <p className="text-sm font-semibold text-[color:var(--text-strong)]">${offer.price.toFixed(2)}</p>
                  <p className="text-sm text-[color:var(--text-soft)]">
                    {formatRating(offer.rating)} ({offer.ratingCount || 0})
                  </p>
                  <a
                    href={offer.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-[color:var(--accent)] transition hover:underline"
                  >
                    Open
                  </a>
                </div>
              ))}
              {!filteredOffers.length ? (
                <p className="rounded-[1.2rem] border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                  No offers matched this source filter.
                </p>
              ) : null}
            </div>
          </div>
        </div>

        <div className="rounded-[2.4rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
          <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Decision scoring</p>
          <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Fit, evidence, and crawl radar</h2>
          {hasRadarSignal ? (
            <div className="mt-6 h-80">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData}>
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: "currentColor", fontSize: 12 }} />
                  <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                  <Radar dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.2} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="mt-6 rounded-[1.4rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
              Insufficient signal for a meaningful radar plot. Use metrics below while more rated offers are collected.
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {radarData.map((entry) => (
              <span
                key={entry.metric}
                className="rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-3 py-1 text-xs text-[color:var(--text-soft)]"
              >
                {entry.metric}: {entry.value.toFixed(1)}
              </span>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-1">
            <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Rating summary</p>
              <p className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">
                {productRatingSummary.hasSignal ? productRatingSummary.avg.toFixed(1) : "N/A"}
              </p>
              <p className="mt-1 text-sm text-[color:var(--text-soft)]">
                {productRatingSummary.hasSignal
                  ? `${productRatingSummary.count} weighted ratings from offers`
                  : "No reliable rating sample yet"}
              </p>
            </div>
            <div className="rounded-[1.4rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">Promo likelihood</p>
              {reviewInsights.promoLikelihoodStatus === "unknown" || reviewInsights.paidPromoLikelihood == null ? (
                <>
                  <p className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Unknown</p>
                  <p className="mt-1 text-sm text-[color:var(--text-soft)]">Waiting for enough matched review evidence.</p>
                </>
              ) : (
                <>
                  <p className={`mt-2 text-2xl font-semibold ${scoreTone(100 - reviewInsights.paidPromoLikelihood)}`}>
                    {reviewInsights.paidPromoLikelihood}%
                  </p>
                  <p className="mt-1 text-sm text-[color:var(--text-soft)]">Lower is better.</p>
                </>
              )}
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
                <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
                  {product.productInsight.analysisMode === "supplement" ? "Ingredients" : "Product insight"}
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">
                  {product.productInsight.analysisMode === "supplement" ? "Signals and flags" : "Strengths and cautions"}
                </h2>
              </div>
              <FlaskConical className="h-5 w-5 text-[color:var(--accent)]" />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-[1.7rem] border border-emerald-500/20 bg-emerald-500/10 p-5">
                <p className="text-xs uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300">
                  {product.productInsight.analysisMode === "supplement" ? "Beneficial" : "Strengths"}
                </p>
                <div className="mt-4 space-y-3">
                  {product.productInsight.analysisMode === "supplement"
                    ? product.ingredientAnalysis.beneficialSignals.map((signal) => (
                        <div key={`${signal.ingredient}-${signal.note}`} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3">
                          <p className="text-sm font-semibold text-[color:var(--text-strong)]">{signal.ingredient}</p>
                          <p className="mt-1 text-sm text-[color:var(--text-soft)]">{signal.note}</p>
                        </div>
                      ))
                    : product.productInsight.strengths.map((item) => (
                        <div key={item} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3">
                          <p className="text-sm text-[color:var(--text-soft)]">{item}</p>
                        </div>
                      ))}
                  {!(product.productInsight.analysisMode === "supplement"
                    ? product.ingredientAnalysis.beneficialSignals.length
                    : product.productInsight.strengths.length) ? (
                    <p className="text-sm text-[color:var(--text-soft)]">No strengths surfaced yet.</p>
                  ) : null}
                </div>
              </div>

              <div className="rounded-[1.7rem] border border-rose-500/20 bg-rose-500/10 p-5">
                <p className="text-xs uppercase tracking-[0.2em] text-rose-700 dark:text-rose-300">
                  {product.productInsight.analysisMode === "supplement" ? "Red flags" : "Cautions"}
                </p>
                <div className="mt-4 space-y-3">
                  {product.productInsight.analysisMode === "supplement"
                    ? product.ingredientAnalysis.redFlags.map((signal) => (
                        <div key={`${signal.ingredient}-${signal.note}`} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3">
                          <p className="text-sm font-semibold text-[color:var(--text-strong)]">{signal.ingredient}</p>
                          <p className="mt-1 text-sm text-[color:var(--text-soft)]">{signal.note}</p>
                        </div>
                      ))
                    : product.productInsight.cautions.map((item) => (
                        <div key={item} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3">
                          <p className="text-sm text-[color:var(--text-soft)]">{item}</p>
                        </div>
                      ))}
                  {!(product.productInsight.analysisMode === "supplement"
                    ? product.ingredientAnalysis.redFlags.length
                    : product.productInsight.cautions.length) ? (
                    <p className="text-sm text-[color:var(--text-soft)]">
                      {product.productInsight.analysisMode === "supplement"
                        ? "No material ingredient flags detected."
                        : "No major cautions surfaced yet."}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Breakdown</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Signal distribution</h2>
            <div className="mt-6 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={insightBars} barSize={42}>
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
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {evidenceBars.map((item) => (
                <div
                  key={`raw-${item.name}`}
                  className="rounded-[1.2rem] border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-4 py-3"
                >
                  <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-muted)]">{item.name}</p>
                  <p className="mt-2 text-xl font-semibold text-[color:var(--text-strong)]">{item.value}</p>
                </div>
              ))}
            </div>
            <div className="mt-6 h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={evidenceBars} barSize={42}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="name" tick={{ fill: "currentColor", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis
                    domain={[0, 100]}
                    allowDecimals={false}
                    tick={{ fill: "currentColor", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip />
                  <Bar dataKey="normalized" fill="#d78c43" radius={[14, 14, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Accepted review coverage</p>
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Source mix</h2>
            <div className="mt-6 h-72">
              <ResponsiveContainer width="100%" height="100%">
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
            {ratingCoverage.ratedOfferCount === 0 ? (
              <p className="mt-4 rounded-[1.2rem] border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
                Insufficient rated reviews for this product scope. Agent confidence relies more on authenticity and ingredient signals.
              </p>
            ) : null}
            <div className="mt-6 grid gap-4">
              <div className="rounded-[1.5rem] border border-emerald-500/20 bg-emerald-500/10 p-5">
                <p className="text-xs uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300">Pros</p>
                <ul className="mt-4 space-y-3">
                  {(scopedProsCons.pros.length
                    ? scopedProsCons.pros
                    : ["No high-confidence pros extracted for this source scope."]).map((pro) => (
                    <li key={pro} className="rounded-[1.2rem] bg-[color:var(--surface)] px-4 py-3 text-sm text-[color:var(--text-soft)]">
                      {pro}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-[1.5rem] border border-rose-500/20 bg-rose-500/10 p-5">
                <p className="text-xs uppercase tracking-[0.2em] text-rose-700 dark:text-rose-300">Cons</p>
                <ul className="mt-4 space-y-3">
                  {(scopedProsCons.cons.length
                    ? scopedProsCons.cons
                    : ["No high-confidence cons extracted for this source scope."]).map((con) => (
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
            <h2 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">Accepted evidence table</h2>
            <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-[color:var(--border)]">
              <div className="grid grid-cols-[minmax(80px,0.18fr)_64px_72px_72px_64px_minmax(0,1fr)] gap-3 bg-[color:var(--surface-strong)] px-4 py-3 text-[11px] uppercase tracking-[0.14em] text-[color:var(--text-muted)]">
                <span>Source</span>
                <span>Kind</span>
                <span>Quality</span>
                <span>Match</span>
                <span>Sent</span>
                <span>Excerpt</span>
              </div>
              {productEvidenceRows.slice(0, 8).map((item) => (
                <div
                  key={`${item.docId}-${item.source}`}
                  className="grid grid-cols-[minmax(80px,0.18fr)_64px_72px_72px_64px_minmax(0,1fr)] gap-3 border-t border-[color:var(--border)] px-4 py-4 text-sm"
                >
                  <span className="font-medium capitalize text-[color:var(--text-strong)]">{item.source}</span>
                  <span className="capitalize text-[color:var(--text-soft)]">{item.kind}</span>
                  <span className={scoreTone(item.qualityScore)}>{item.qualityScore}</span>
                  <span className="text-[color:var(--text-soft)]">{item.productMatch}</span>
                  <span className={item.sentimentScore >= 0 ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300"}>
                    {item.sentimentScore}
                  </span>
                  <span className="line-clamp-3 text-[color:var(--text-soft)]" title={item.excerpt || item.docId}>
                    {item.excerpt || item.docId}
                  </span>
                </div>
              ))}
              {!productEvidenceRows.length ? (
                <div className="px-4 py-5 text-sm text-[color:var(--text-soft)]">
                  No review evidence matched the current source filter.
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

