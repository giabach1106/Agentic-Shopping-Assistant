from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.rag.base import RetrievalDocument, Retriever


class InMemoryRetriever:
    def __init__(self, seed_documents: list[RetrievalDocument]) -> None:
        self._seed_documents = seed_documents

    async def search(self, query: str, top_k: int) -> list[RetrievalDocument]:
        query_tokens = {token for token in query.lower().split() if token}
        scored_docs: list[tuple[int, RetrievalDocument]] = []
        for document in self._seed_documents:
            doc_tokens = set(document.content.lower().split())
            overlap = len(query_tokens & doc_tokens)
            scored_docs.append((overlap, document))

        scored_docs.sort(key=lambda item: item[0], reverse=True)
        return [doc for score, doc in scored_docs if score > 0][:top_k]


class BedrockKnowledgeBaseRetriever:
    def __init__(
        self,
        knowledge_base_id: str,
        region_name: str,
        fallback_retriever: Retriever,
    ) -> None:
        self._knowledge_base_id = knowledge_base_id
        self._fallback_retriever = fallback_retriever
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client = boto3.client("bedrock-agent-runtime", region_name=region_name)

    async def search(self, query: str, top_k: int) -> list[RetrievalDocument]:
        try:
            response = await asyncio.to_thread(
                self._client.retrieve,
                knowledgeBaseId=self._knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": top_k}},
            )
        except (BotoCoreError, ClientError, Exception) as exc:  # noqa: BLE001
            self._logger.warning(
                "Bedrock KB retrieval failed (%r). Falling back to local retriever.",
                exc,
            )
            return await self._fallback_retriever.search(query, top_k)

        items = response.get("retrievalResults", [])
        results: list[RetrievalDocument] = []
        for idx, item in enumerate(items):
            content = item.get("content", {}).get("text", "")
            location = item.get("location", {})
            source = (
                location.get("s3Location", {}).get("uri")
                or location.get("webLocation", {}).get("url")
                or "bedrock-kb"
            )
            results.append(
                RetrievalDocument(
                    doc_id=f"kb-{idx+1}",
                    source=str(source),
                    content=content,
                    metadata={"score": item.get("score")},
                )
            )
        return results


class HybridRAGService:
    def __init__(self, retriever: Retriever, top_k: int) -> None:
        self._retriever = retriever
        self._top_k = top_k

    async def retrieve_review_context(self, constraints: dict[str, Any]) -> dict[str, Any]:
        query = self._build_query(constraints)
        documents = await self._retriever.search(query, self._top_k)
        source_counts = Counter(doc.source for doc in documents)
        return {
            "query": query,
            "documents": documents,
            "sourceStats": dict(source_counts),
        }

    def _build_query(self, constraints: dict[str, Any]) -> str:
        category = constraints.get("category", "product")
        must_have = ", ".join(constraints.get("mustHave", []))
        min_rating = constraints.get("minRating")
        deadline = constraints.get("deliveryDeadline")
        return (
            f"reviews for {category}; must-have: {must_have}; "
            f"minimum rating: {min_rating}; delivery by: {deadline}"
        )


def default_seed_documents() -> list[RetrievalDocument]:
    return [
        RetrievalDocument(
            doc_id="amz-1",
            source="amazon",
            content=(
                "Ergonomic chair users report strong comfort and easy posture support. "
                "Several mention assembly takes 25 to 40 minutes."
            ),
        ),
        RetrievalDocument(
            doc_id="reddit-1",
            source="reddit",
            content=(
                "Dorm buyers said cheaper chairs can wobble after 6 months. "
                "Look for reinforced armrest joints and warranty clarity."
            ),
        ),
        RetrievalDocument(
            doc_id="tiktok-1",
            source="tiktok",
            content=(
                "Influencer reviews often include affiliate links. "
                "Check for explicit paid promotion labels before trusting claims."
            ),
        ),
    ]


def build_rag_service(settings: Settings) -> HybridRAGService:
    local_retriever = InMemoryRetriever(default_seed_documents())
    backend = settings.rag_backend.lower().strip()
    if backend == "bedrock_kb" and settings.aws_bedrock_kb_id:
        retriever: Retriever = BedrockKnowledgeBaseRetriever(
            knowledge_base_id=settings.aws_bedrock_kb_id,
            region_name=settings.aws_region,
            fallback_retriever=local_retriever,
        )
    else:
        retriever = local_retriever

    return HybridRAGService(retriever=retriever, top_k=settings.rag_top_k)

