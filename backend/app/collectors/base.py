from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

SourceName = Literal["amazon", "reddit", "tiktok", "ebay", "walmart"]


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
    trace: list[CollectorTraceEvent] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    blocked_sources: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "products": [item.to_public_dict() for item in self.products],
            "reviews": [item.to_public_dict() for item in self.reviews],
            "visuals": [item.to_public_dict() for item in self.visuals],
            "trace": [item.to_public_dict() for item in self.trace],
            "missingEvidence": list(self.missing_evidence),
            "blockedSources": list(self.blocked_sources),
        }


class RealtimeCollector(Protocol):
    async def collect(self, constraints: dict[str, Any]) -> CollectionResult:
        """Collect realtime product/review/visual evidence from supported sources."""
