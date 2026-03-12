from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.stubs import EvidenceCollectionAgent
from app.collectors.base import (
    CollectionResult,
    CollectorTraceEvent,
    ProductCandidateData,
    ReviewRecord,
    VisualRecord,
)
from app.core.config import Settings
from app.memory.evidence_store import SQLiteEvidenceStore


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="test",
        sqlite_path=tmp_path / "agent-memory.sqlite3",
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
        rag_top_k=5,
        rag_chroma_path=tmp_path / "chroma",
        rag_collection_name="shopping_reviews_test",
        ui_executor_backend="mock",
        stop_before_pay=True,
        max_model_calls_per_session=50,
        max_estimated_cost_per_session_usd=1.0,
        estimated_cost_per_call_pro_usd=0.01,
        estimated_cost_per_call_lite_usd=0.004,
        min_review_count=1,
        min_rating_count=1,
        min_source_coverage=1,
    )


def test_evidence_collection_agent_reuses_cached_collection(tmp_path: Path) -> None:
    async def run_test() -> None:
        calls = 0
        now = datetime.now(UTC).isoformat()

        class FakeCollector:
            async def collect(self, constraints: dict[str, object]) -> CollectionResult:
                del constraints
                nonlocal calls
                calls += 1
                return CollectionResult(
                    products=[
                        ProductCandidateData(
                            source="amazon",
                            url="https://example.com/whey",
                            title="Test Whey Isolate",
                            price=59.0,
                            avg_rating=4.8,
                            rating_count=120,
                            shipping_eta="2 days",
                            return_policy="30-day return",
                            seller_info="Example",
                            retrieved_at=now,
                            evidence_id="prod-1",
                            confidence_source=0.9,
                            raw_snapshot_ref="test://product",
                        )
                    ],
                    reviews=[
                        ReviewRecord(
                            source="reddit",
                            url="https://reddit.com/r/supplements/test",
                            review_id="review-1",
                            rating=4.0,
                            review_text="Whey isolate mixes well and tastes clean.",
                            timestamp=now,
                            helpful_votes=12,
                            verified_purchase=None,
                            media_count=0,
                            retrieved_at=now,
                            evidence_id="review-1",
                            confidence_source=0.8,
                            raw_snapshot_ref="test://review",
                        )
                    ],
                    visuals=[
                        VisualRecord(
                            source="amazon",
                            url="https://example.com/whey",
                            image_url="https://example.com/whey.jpg",
                            caption="Front label.",
                            retrieved_at=now,
                            evidence_id="visual-1",
                            confidence_source=0.75,
                            raw_snapshot_ref="test://visual",
                        )
                    ],
                    trace=[
                        CollectorTraceEvent(
                            source="amazon",
                            step="collect_products",
                            status="ok",
                            detail="Collected synthetic product.",
                            duration_ms=1,
                        )
                    ],
                )

        store = SQLiteEvidenceStore(tmp_path / "agent-memory.sqlite3")
        await store.initialize()
        agent = EvidenceCollectionAgent(_settings(tmp_path), FakeCollector(), store)

        first = await agent.run({"category": "whey protein"})
        second = await agent.run({"category": "whey protein"})

        assert calls == 1
        assert first["cacheStatus"] == "miss"
        assert second["cacheStatus"] == "hit"
        assert second["sourceCoverage"] == 2

    asyncio.run(run_test())


def test_list_sessions_endpoint_returns_latest_first(client: TestClient) -> None:
    first = client.post("/v1/sessions")
    second = client.post("/v1/sessions")
    assert first.status_code == 201
    assert second.status_code == 201

    first_id = first.json()["sessionId"]
    chat = client.post(
        "/v1/chat",
        json={
            "sessionId": first_id,
            "message": "I need whey protein under $80 with 4+ stars delivered by Friday",
        },
    )
    assert chat.status_code == 200

    listed = client.get("/v1/sessions?limit=10")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["items"][0]["sessionId"] == first_id
    assert payload["items"][0]["title"] != "Untitled session"
    assert payload["items"][0]["status"] in {"OK", "NEED_DATA"}


def test_session_products_endpoint_returns_ingredient_analysis(client: TestClient) -> None:
    created = client.post("/v1/sessions")
    assert created.status_code == 201
    session_id = created.json()["sessionId"]

    chat = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": "Find a whey protein isolate under $90 with 4+ stars delivered by Friday",
        },
    )
    assert chat.status_code == 200

    products = client.get(f"/v1/sessions/{session_id}/products")
    assert products.status_code == 200
    payload = products.json()

    assert payload["sessionId"] == session_id
    assert len(payload["items"]) > 0
    first = payload["items"][0]
    assert "ingredientAnalysis" in first
    assert isinstance(first["ingredientAnalysis"]["score"], int)
    assert first["ingredientAnalysis"]["references"]
    assert any(
        item["ingredient"] == "whey isolate"
        for product in payload["items"]
        for item in product["ingredientAnalysis"]["beneficialSignals"]
    )
