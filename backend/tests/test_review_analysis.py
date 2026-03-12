from __future__ import annotations

from app.rag.base import RetrievalDocument
from app.services.review_analysis import ReviewEvidenceAnalyzer


def test_review_evidence_analyzer_dedupes_cross_source_duplicates() -> None:
    analyzer = ReviewEvidenceAnalyzer()
    docs = [
        RetrievalDocument(
            doc_id="amz-1",
            source="amazon",
            content=(
                "This ergonomic chair is comfortable for long study sessions and "
                "assembly takes about thirty minutes."
            ),
        ),
        RetrievalDocument(
            doc_id="reddit-1",
            source="reddit",
            content=(
                "Comfortable ergonomic chair for long study sessions; assembly takes "
                "around thirty minutes."
            ),
        ),
        RetrievalDocument(
            doc_id="tiktok-1",
            source="tiktok",
            content=(
                "Affiliate link included. Great style but check sponsored tag before buying."
            ),
        ),
    ]

    result = analyzer.analyze(docs)
    clusters = result["duplicateClusters"]
    assert len(clusters) == 1
    assert set(clusters[0]["members"]) == {"amz-1", "reddit-1"}

    ranked = result["rankedEvidence"]
    assert ranked[0].doc_id in {"amz-1", "reddit-1"}
    assert result["paidPromoLikelihood"] > 0

