from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    created_at: str = Field(alias="createdAt")


class ChatRequest(BaseModel):
    session_id: str = Field(alias="sessionId")
    message: str = Field(min_length=1, max_length=4_000)


class ChatResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: str
    reply: str
    decision: dict[str, Any] | None = None
    scientific_score: dict[str, Any] = Field(alias="scientificScore")
    evidence_stats: dict[str, Any] = Field(alias="evidenceStats")
    coverage_audit: dict[str, Any] = Field(alias="coverageAudit")
    trace: list[dict[str, Any]]
    missing_evidence: list[str] = Field(alias="missingEvidence")
    blocking_agents: list[str] = Field(alias="blockingAgents")
    state: dict[str, Any]


class ResumeRunRequest(BaseModel):
    message: str | None = Field(
        default=None,
        description="Optional follow-up response to continue the previous run.",
    )


class MessageItem(BaseModel):
    role: str
    content: str
    created_at: str = Field(alias="createdAt")
    meta: dict[str, Any] | None = None


class SessionSnapshotResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    messages: list[MessageItem]
    checkpoint_state: dict[str, Any] | None = Field(alias="checkpointState")


class SessionSummaryResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    title: str
    status: str
    verdict: str | None = None


class SessionListResponse(BaseModel):
    items: list[SessionSummaryResponse]
    next_cursor: str | None = Field(alias="nextCursor")


class IngredientSignalResponse(BaseModel):
    ingredient: str
    note: str


class IngredientAnalysisResponse(BaseModel):
    score: int
    summary: str
    protein_source: str = Field(alias="proteinSource")
    beneficial_signals: list[IngredientSignalResponse] = Field(alias="beneficialSignals")
    red_flags: list[IngredientSignalResponse] = Field(alias="redFlags")
    confidence: float
    references: list[str]


class OfferResponse(BaseModel):
    source: str
    store_name: str = Field(alias="storeName")
    source_url: str = Field(alias="sourceUrl")
    price: float
    rating: float | None = None
    rating_count: int = Field(alias="ratingCount")
    shipping_eta: str = Field(alias="shippingETA")
    return_policy: str = Field(alias="returnPolicy")
    image_url: str | None = Field(default=None, alias="imageUrl")


class SourceBreakdownItemResponse(BaseModel):
    source: str
    count: int


class RatingCoverageResponse(BaseModel):
    rated_offer_count: int = Field(alias="ratedOfferCount")
    total_offer_count: int = Field(alias="totalOfferCount")


class SessionProductResponse(BaseModel):
    product_id: str = Field(alias="productId")
    canonical_product_id: str = Field(alias="canonicalProductId")
    title: str
    store_name: str = Field(alias="storeName")
    source: str
    source_url: str = Field(alias="sourceUrl")
    image_url: str | None = Field(default=None, alias="imageUrl")
    price: float
    rating: float | None = None
    shipping_eta: str = Field(alias="shippingETA")
    return_policy: str = Field(alias="returnPolicy")
    checkout_ready: bool = Field(alias="checkoutReady")
    evidence_refs: list[str] = Field(alias="evidenceRefs")
    primary_offer: OfferResponse = Field(alias="primaryOffer")
    offers: list[OfferResponse]
    source_breakdown: list[SourceBreakdownItemResponse] = Field(alias="sourceBreakdown")
    rating_coverage: RatingCoverageResponse = Field(alias="ratingCoverage")
    pros: list[str]
    cons: list[str]
    ingredient_analysis: IngredientAnalysisResponse = Field(alias="ingredientAnalysis")
    scientific_score: dict[str, Any] = Field(alias="scientificScore")
    evidence_stats: dict[str, Any] = Field(alias="evidenceStats")
    trace: list[dict[str, Any]]


class SessionProductsEnvelopeResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    items: list[SessionProductResponse]


class RecommendationResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: str
    decision: dict[str, Any] | None
    scientific_score: dict[str, Any] = Field(alias="scientificScore")
    evidence_stats: dict[str, Any] = Field(alias="evidenceStats")
    coverage_audit: dict[str, Any] = Field(alias="coverageAudit")
    trace: list[dict[str, Any]]
    missing_evidence: list[str] = Field(alias="missingEvidence")
    blocking_agents: list[str] = Field(alias="blockingAgents")


class HealthResponse(BaseModel):
    status: str
    app: str
    checkpoint_backend: str = Field(alias="checkpointBackend")
    default_model: str = Field(alias="defaultModel")
    fallback_model: str = Field(alias="fallbackModel")


class RuntimeMetricsResponse(BaseModel):
    total_calls: int = Field(alias="totalCalls")
    total_fallback_calls: int = Field(alias="totalFallbackCalls")
    total_estimated_cost_usd: float = Field(alias="totalEstimatedCostUsd")
    tasks: dict[str, Any]
    sessions_tracked: int = Field(alias="sessionsTracked")


class CatalogMetricsResponse(BaseModel):
    total_records: int = Field(alias="totalRecords")
    source_counts: dict[str, int] = Field(alias="sourceCounts")
    latest_retrieved_at: str | None = Field(alias="latestRetrievedAt")
    freshness_seconds: int = Field(alias="freshnessSeconds")


class VoiceConsultRequest(BaseModel):
    session_id: str = Field(alias="sessionId")
    question: str = Field(min_length=1, max_length=2_000)


class VoiceConsultResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    answer: str
    mode: str
    model_meta: dict[str, Any] = Field(alias="modelMeta")
