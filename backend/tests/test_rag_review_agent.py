from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents.stubs import ReviewIntelligenceAgent
from app.core.config import Settings
from app.core.model_router import ModelRouter
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
        rag_backend="inmemory",
        rag_top_k=3,
        rag_chroma_path=Path("./tmp-chroma"),
        rag_collection_name="shopping_reviews_test",
        ui_executor_backend="mock",
        stop_before_pay=True,
        max_model_calls_per_session=50,
        max_estimated_cost_per_session_usd=1.0,
        estimated_cost_per_call_pro_usd=0.01,
        estimated_cost_per_call_lite_usd=0.004,
    )


def test_review_agent_returns_evidence_refs_from_rag() -> None:
    async def run_test() -> None:
        settings = _settings()
        router = ModelRouter(settings)
        rag_service = build_rag_service(settings)
        agent = ReviewIntelligenceAgent(router, rag_service)

        output = await agent.run(
            {
                "category": "ergonomic chair",
                "mustHave": ["ergonomic"],
                "minRating": 4,
                "deliveryDeadline": "friday",
            }
        )
        assert len(output["evidenceRefs"]) > 0
        assert isinstance(output["sourceStats"], dict)
        assert "evidenceQualityScore" in output
        assert "duplicateReviewClusters" in output
        assert "rankedEvidence" in output
        assert output["confidence"] <= 1
        assert output["confidence"] >= 0
        assert "pros" in output
        assert "cons" in output

    asyncio.run(run_test())
