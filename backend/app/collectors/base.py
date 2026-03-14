from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

SourceName = Literal[
    "amazon",
    "reddit",
    "tiktok",
    "ebay",
    "walmart",
    "nutritionfaktory",
    "dps",
    "staples",
    "iherb",
]


@dataclass(slots=True)
class ProductCandidateData:
    source: SourceName
    url: str
    title: str
    price: float
    avg_rating: float
    rating_count: int
    shipping_eta: str
    return_policy: str
    seller_info: str
    retrieved_at: str
    evidence_id: str
    confidence_source: float
    raw_snapshot_ref: str
    image_url: str | None = None
    spec_text: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewRecord:
    source: SourceName
    url: str
    review_id: str
    rating: float
    review_text: str
    timestamp: str
    helpful_votes: int
    verified_purchase: bool | None
    media_count: int
    retrieved_at: str
    evidence_id: str
    confidence_source: float
    raw_snapshot_ref: str

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VisualRecord:
    source: SourceName
    url: str
    image_url: str
    caption: str
    retrieved_at: str
    evidence_id: str
    confidence_source: float
    raw_snapshot_ref: str

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidenceRecordData:
    source: str
    source_bucket: Literal["commerce", "review", "visual"]
    content_kind: Literal["offer", "review", "discussion", "listing_summary", "visual_meta"]
    domain: str
    url: str
    evidence_id: str
    product_signature: str
    product_title: str
    review_like: bool
    accepted_in_review_corpus: bool
    relevance_score: float
    rejection_reasons: list[str]
    extraction_method: str
    clean_excerpt: str
    rating: float | None
    helpful_votes: int
    retrieved_at: str
    confidence_source: float
    raw_snapshot_ref: str

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CollectorTraceEvent:
    source: str
    step: str
    status: Literal["ok", "warning", "blocked", "error"]
    detail: str
    duration_ms: int

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CollectionResult:
    products: list[ProductCandidateData] = field(default_factory=list)
    reviews: list[ReviewRecord] = field(default_factory=list)
    visuals: list[VisualRecord] = field(default_factory=list)
    evidence_records: list[EvidenceRecordData] = field(default_factory=list)
    trace: list[CollectorTraceEvent] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    blocked_sources: list[str] = field(default_factory=list)
    source_health: dict[str, Any] = field(default_factory=dict)
    crawl_meta: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "products": [item.to_public_dict() for item in self.products],
            "reviews": [item.to_public_dict() for item in self.reviews],
            "visuals": [item.to_public_dict() for item in self.visuals],
            "evidenceRecords": [item.to_public_dict() for item in self.evidence_records],
            "trace": [item.to_public_dict() for item in self.trace],
            "missingEvidence": list(self.missing_evidence),
            "blockedSources": list(self.blocked_sources),
            "sourceHealth": dict(self.source_health),
            "crawlMeta": dict(self.crawl_meta),
        }


class RealtimeCollector(Protocol):
    async def collect(self, constraints: dict[str, Any]) -> CollectionResult:
        """Collect realtime product/review/visual evidence from supported sources."""
