from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict

from app.rag.base import RetrievalDocument

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}


@dataclass(slots=True)
class RankedEvidence:
    doc_id: str
    source: str
    quality_score: float
    promo_signals: int
    excerpt: str


class DuplicateCluster(TypedDict):
    canonicalDocId: str
    members: list[str]
    sources: list[str]
    size: int


class ReviewAnalysisResult(TypedDict):
    rankedEvidence: list[RankedEvidence]
    duplicateClusters: list[DuplicateCluster]
    paidPromoLikelihood: float
    averageQuality: float
    uniqueEvidenceCount: int
    rawEvidenceCount: int


class ReviewEvidenceAnalyzer:
    _source_weights = {
        "amazon": 0.84,
        "reddit": 0.9,
        "tiktok": 0.65,
        "ebay": 0.76,
        "walmart": 0.8,
        "nutritionfaktory": 0.83,
        "dps": 0.81,
        "bedrock-kb": 0.75,
    }
    _promo_patterns = (
        "affiliate",
        "sponsored",
        "paid promotion",
        "#ad",
        "commission",
    )

    def analyze(self, documents: list[RetrievalDocument]) -> ReviewAnalysisResult:
        clusters = self._cluster_duplicates(documents)
        unique_docs = [cluster[0] for cluster in clusters]
        ranked = sorted(
            (self._score_document(doc) for doc in unique_docs),
            key=lambda item: item.quality_score,
            reverse=True,
        )

        duplicate_groups: list[DuplicateCluster] = [
            {
                "canonicalDocId": cluster[0].doc_id,
                "members": [member.doc_id for member in cluster],
                "sources": sorted({member.source for member in cluster}),
                "size": len(cluster),
            }
            for cluster in clusters
            if len(cluster) > 1
        ]

        promo_signal_docs = sum(1 for item in ranked if item.promo_signals > 0)
        paid_promo_likelihood = 0.0
        if ranked:
            paid_promo_likelihood = round(
                min(1.0, (promo_signal_docs / len(ranked)) * 0.9),
                2,
            )

        average_quality = 0.0
        if ranked:
            average_quality = round(
                sum(item.quality_score for item in ranked) / len(ranked),
                2,
            )

        return {
            "rankedEvidence": ranked,
            "duplicateClusters": duplicate_groups,
            "paidPromoLikelihood": paid_promo_likelihood,
            "averageQuality": average_quality,
            "uniqueEvidenceCount": len(unique_docs),
            "rawEvidenceCount": len(documents),
        }

    def _cluster_duplicates(
        self, documents: list[RetrievalDocument]
    ) -> list[list[RetrievalDocument]]:
        clusters: list[list[RetrievalDocument]] = []
        representative_tokens: list[set[str]] = []

        for document in documents:
            doc_tokens = self._token_set(document.content)
            match_index = self._find_similar_cluster(doc_tokens, representative_tokens)
            if match_index is None:
                clusters.append([document])
                representative_tokens.append(doc_tokens)
            else:
                clusters[match_index].append(document)

        return clusters

    def _find_similar_cluster(
        self,
        doc_tokens: set[str],
        representative_tokens: list[set[str]],
    ) -> int | None:
        for idx, cluster_tokens in enumerate(representative_tokens):
            if self._jaccard_similarity(doc_tokens, cluster_tokens) >= 0.65:
                return idx
        return None

    def _token_set(self, text: str) -> set[str]:
        tokens = [token for token in self._tokenize(text) if token not in _STOPWORDS]
        return set(tokens)

    def _score_document(self, document: RetrievalDocument) -> RankedEvidence:
        lowered = document.content.lower()
        source_weight = self._source_weights.get(document.source.lower(), 0.7)
        length_factor = min(1.0, max(0.35, len(document.content) / 220))
        promo_signals = sum(1 for marker in self._promo_patterns if marker in lowered)
        promo_penalty = min(0.28, promo_signals * 0.09)

        quality = max(0.0, min(1.0, (0.55 * source_weight) + (0.45 * length_factor) - promo_penalty))
        excerpt = document.content.strip()
        if len(excerpt) > 160:
            excerpt = f"{excerpt[:157]}..."

        return RankedEvidence(
            doc_id=document.doc_id,
            source=document.source,
            quality_score=round(quality, 2),
            promo_signals=promo_signals,
            excerpt=excerpt,
        )

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def _jaccard_similarity(self, left: set[str], right: set[str]) -> float:
        if not left and not right:
            return 1.0
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        union = len(left | right)
        if union == 0:
            return 0.0
        return intersection / union
