import type { SessionProduct, SessionSnapshotResponse } from "@/lib/contracts";

export interface RatingSummary {
  avgRating: number;
  ratingCount: number;
  positiveCount: number;
  positiveRate: number;
}

export interface RankedEvidenceItem {
  docId: string;
  source: string;
  kind: string;
  qualityScore: number;
  relevanceScore: number;
  productMatch: number;
  promoSignals: string[];
  positiveSignals: string[];
  negativeSignals: string[];
  sentimentScore: number;
  excerpt: string;
}

export interface ReviewInsights {
  sourceStats: Array<{ source: string; count: number }>;
  absaSignals: Array<{ aspect: string; score: number }>;
  ratingSummary: RatingSummary;
  evidenceQualityScore: number;
  paidPromoLikelihood: number | null;
  promoLikelihoodStatus: "known" | "unknown";
  confidence: number;
  reviewCount: number;
  evidenceRefs: string[];
  riskFlags: string[];
  rankedEvidence: RankedEvidenceItem[];
  duplicateReviewClusters: number;
}

export interface CollectionInsights {
  cacheStatus: string;
  blockedSources: string[];
  missingEvidence: string[];
  sufficiencyMissing: string[];
  isSufficient: boolean;
  sourceCoverage: number;
  reviewCount: number;
  ratingCount: number;
  freshnessSeconds: number;
}

interface CheckpointAgentOutputs {
  collect?: Record<string, unknown>;
  review?: Record<string, unknown>;
}

interface CheckpointStateShape {
  agent_outputs?: CheckpointAgentOutputs;
}

const emptyRatingSummary: RatingSummary = {
  avgRating: 0,
  ratingCount: 0,
  positiveCount: 0,
  positiveRate: 0,
};
function toCheckpointState(snapshot: SessionSnapshotResponse | null) {
  return (snapshot?.checkpointState as CheckpointStateShape | null) ?? null;
}

function getAgentOutputs(snapshot: SessionSnapshotResponse | null) {
  return toCheckpointState(snapshot)?.agent_outputs ?? {};
}

function asNumber(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asStringArray(value: unknown) {
  return Array.isArray(value)
    ? value
        .map((item) => (typeof item === "string" ? item.trim() : ""))
        .filter(Boolean)
    : [];
}

function isHttpUrl(value: string) {
  return /^https?:\/\//i.test(value);
}

export function getReviewInsights(snapshot: SessionSnapshotResponse | null): ReviewInsights {
  const review = getAgentOutputs(snapshot).review ?? {};
  const rawSourceStats = review.sourceStats;
  const rawEvidenceDiagnostics = review.evidenceDiagnostics;
  const rawAbsaSignals = review.absaSignals;
  const rawRatingSummary = review.ratingSummary;
  const rawRankedEvidence = review.rankedEvidence;
  const rawDuplicateClusters = review.duplicateReviewClusters;

  const sourceStats =
    rawEvidenceDiagnostics &&
    typeof rawEvidenceDiagnostics === "object" &&
    (rawEvidenceDiagnostics as Record<string, unknown>).acceptedReviewSources &&
    typeof (rawEvidenceDiagnostics as Record<string, unknown>).acceptedReviewSources === "object"
      ? Object.entries(
          (rawEvidenceDiagnostics as Record<string, unknown>).acceptedReviewSources as Record<string, unknown>
        )
          .map(([source, count]) => ({
            source,
            count: asNumber(count),
          }))
          .sort((left, right) => right.count - left.count)
      : rawSourceStats && typeof rawSourceStats === "object"
      ? Object.entries(rawSourceStats as Record<string, unknown>)
          .map(([source, count]) => ({
            source,
            count: asNumber(count),
          }))
          .sort((left, right) => right.count - left.count)
      : [];

  const absaSignals =
    rawAbsaSignals && typeof rawAbsaSignals === "object"
      ? Object.entries(rawAbsaSignals as Record<string, unknown>).map(([aspect, score]) => ({
          aspect,
          score: Math.round((asNumber(score) + 1) * 50),
        }))
      : [];

  const ratingSummary =
    rawRatingSummary && typeof rawRatingSummary === "object"
      ? {
          avgRating: asNumber((rawRatingSummary as Record<string, unknown>).avgRating),
          ratingCount: asNumber((rawRatingSummary as Record<string, unknown>).ratingCount),
          positiveCount: asNumber((rawRatingSummary as Record<string, unknown>).positiveCount),
          positiveRate: asNumber((rawRatingSummary as Record<string, unknown>).positiveRate),
        }
      : emptyRatingSummary;

  const rankedEvidence = Array.isArray(rawRankedEvidence)
    ? rawRankedEvidence
        .map((item) => {
          if (!item || typeof item !== "object") {
            return null;
          }

          const entry = item as Record<string, unknown>;
          const source = typeof entry.source === "string" ? entry.source : "unknown";
          const rawQuality = asNumber(entry.qualityScore);
          const qualityScore = rawQuality <= 1 ? Math.round(rawQuality * 100) : Math.round(rawQuality);
          const rawRelevance = asNumber(entry.relevanceScore);
          const relevanceScore = rawRelevance <= 1 ? Math.round(rawRelevance * 100) : Math.round(rawRelevance);
          const rawProductMatch = asNumber(entry.productMatch);
          const productMatch = rawProductMatch <= 1 ? Math.round(rawProductMatch * 100) : Math.round(rawProductMatch);
          return {
            docId: typeof entry.docId === "string" ? entry.docId : "unknown",
            source,
            kind: typeof entry.kind === "string" ? entry.kind : "review",
            qualityScore,
            relevanceScore,
            productMatch,
            promoSignals: asStringArray(entry.promoSignals),
            positiveSignals: asStringArray(entry.positiveSignals),
            negativeSignals: asStringArray(entry.negativeSignals),
            sentimentScore: asNumber(entry.sentimentScore),
            excerpt: typeof entry.excerpt === "string" ? entry.excerpt : "",
          };
        })
        .filter((item): item is RankedEvidenceItem => item !== null)
    : [];

  return {
    sourceStats,
    absaSignals,
    ratingSummary,
    evidenceQualityScore: Math.round(asNumber(review.evidenceQualityScore) * 100),
    paidPromoLikelihood:
      review.promoLikelihoodStatus === "unknown" || review.paidPromoLikelihood == null
        ? null
        : Math.round(asNumber(review.paidPromoLikelihood) * 100),
    promoLikelihoodStatus:
      typeof review.promoLikelihoodStatus === "string" && review.promoLikelihoodStatus === "unknown"
        ? "unknown"
        : "known",
    confidence: Math.round(asNumber(review.confidence) * 100),
    reviewCount: asNumber(review.reviewCount),
    evidenceRefs: asStringArray(review.evidenceRefs),
    riskFlags: asStringArray(review.riskFlags),
    rankedEvidence,
    duplicateReviewClusters: Array.isArray(rawDuplicateClusters) ? rawDuplicateClusters.length : 0,
  };
}

export function getCollectionInsights(snapshot: SessionSnapshotResponse | null): CollectionInsights {
  const collect = getAgentOutputs(snapshot).collect ?? {};
  const sufficiency =
    collect.sufficiency && typeof collect.sufficiency === "object"
      ? (collect.sufficiency as Record<string, unknown>)
      : {};

  return {
    cacheStatus: typeof collect.cacheStatus === "string" ? collect.cacheStatus : "unknown",
    blockedSources: asStringArray(collect.blockedSources),
    missingEvidence: asStringArray(collect.missingEvidence),
    sufficiencyMissing: asStringArray(sufficiency.missing),
    isSufficient: Boolean(sufficiency.isSufficient),
    sourceCoverage: asNumber(collect.sourceCoverage),
    reviewCount: asNumber(collect.reviewCount),
    ratingCount: asNumber(collect.ratingCount),
    freshnessSeconds: asNumber(collect.freshnessSeconds),
  };
}

export function buildReferenceLinks(
  products: SessionProduct[],
  snapshot: SessionSnapshotResponse | null
) {
  const reviewInsights = getReviewInsights(snapshot);
  return [
    ...new Set(
      [
        ...products.map((product) => product.sourceUrl),
        ...products.flatMap((product) =>
          (product.offers ?? []).map((offer) => offer.sourceUrl)
        ),
        ...products.flatMap((product) => [
          ...product.evidenceRefs,
          ...product.ingredientAnalysis.references,
        ]),
        ...reviewInsights.evidenceRefs,
      ]
        .map((item) => item.trim())
        .filter((item) => item && isHttpUrl(item))
    ),
  ];
}
