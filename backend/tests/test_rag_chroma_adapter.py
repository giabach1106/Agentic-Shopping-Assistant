from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import Settings
from app.rag.base import RetrievalDocument
from app.rag.providers import build_rag_service


def _settings() -> Settings:
    return Settings(
        app_name="test",
        sqlite_path=Path("unused.sqlite3"),
        redis_url="redis://localhost:6399/0",
        redis_key_prefix="test:key",
        aws_region="us-east-1",
        aws_bedrock_kb_id=None,
        default_model_id="pro-model",
        fallback_model_id="lite-model",
        model_timeout_seconds=1.0,
        latency_threshold_seconds=0.5,
        max_retries=1,
        mock_model=True,
        rag_backend="chroma",
        rag_top_k=3,
        rag_chroma_path=Path("./tmp-chroma"),
        rag_collection_name="shopping_reviews_test",
        ui_executor_backend="mock",
        stop_before_pay=True,
    )


def test_chroma_adapter_supports_ingestion_and_query() -> None:
    async def run_test() -> None:
        rag_service = build_rag_service(_settings())
        inserted = await rag_service.ingest_documents(
            [
                RetrievalDocument(
                    doc_id="custom-1",
                    source="reddit",
                    content="Mesh chair has good lumbar support for dorm desks.",
                )
            ]
        )
        assert inserted >= 0

        result = await rag_service.retrieve_review_context(
            {
                "category": "chair",
                "mustHave": ["lumbar support"],
                "minRating": 4,
                "deliveryDeadline": "friday",
            }
        )
        assert "documents" in result
        assert isinstance(result["documents"], list)

    asyncio.run(run_test())

