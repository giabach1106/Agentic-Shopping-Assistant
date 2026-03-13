from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.stubs import CoverageAuditorAgent
from app.core.config import Settings
from app.main import create_app
from app.memory.evidence_store import SQLiteEvidenceStore
from scripts.warmup_supplements_catalog import _build_records


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


def test_missing_auth_is_rejected(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post("/v1/sessions")
    assert response.status_code == 401


def test_auth_requires_cognito_config_when_signature_verification_is_on(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/v1/sessions",
            headers={"Authorization": "Bearer test.test.test"},
        )
    assert response.status_code == 500
    assert "COGNITO_REGION" in response.json().get("detail", "")


def test_cors_preflight_sessions_endpoint(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.options(
            "/v1/sessions",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_coverage_auditor_uses_catalog_records(tmp_path: Path) -> None:
    async def run() -> None:
        settings = _settings(tmp_path)
        store = SQLiteEvidenceStore(settings.sqlite_path)
        await store.initialize()
        await store.upsert_catalog_records(
            [
                {
                    "source": "amazon",
                    "url": "https://www.amazon.com/dp/B000000001",
                    "title": "Test Whey Isolate Vanilla",
                    "brand": "Test Brand",
                    "price": 49.99,
                    "rating": 4.6,
                    "rating_count": 124,
                    "image_url": "https://example.com/image.jpg",
                    "ingredient_text": "whey isolate third-party tested",
                    "review_snippets": ["Mixes clean and low lactose."],
                    "retrieved_at": "2026-03-12T12:00:00+00:00",
                }
            ]
        )
        auditor = CoverageAuditorAgent(settings, store)
        payload = await auditor.run({"category": "whey isolate"})
        assert payload["catalogStatus"] == "hit"
        assert payload["sourceCoverage"] >= 1
        assert payload["commerceSourceCoverage"] >= 1
        assert "ratedCandidateCount" in payload
        assert "ratedCoverageRatio" in payload
        assert "blockedCommerceSources" in payload
        assert isinstance(payload["sufficiency"]["missing"], list)

    asyncio.run(run())


def test_catalog_metrics_endpoint(client: TestClient) -> None:
    response = client.get("/v1/metrics/catalog")
    assert response.status_code == 200
    payload = response.json()
    assert "totalRecords" in payload
    assert "sourceCounts" in payload


def test_warmup_record_builder_keeps_required_fields() -> None:
    rejection_counts: dict[str, int] = {}
    collection = {
        "products": [
            {
                "source": "ebay",
                "url": "https://www.ebay.com/itm/1234567890",
                "title": "Sample Creatine Monohydrate Powder",
                "price": 19.99,
                "avg_rating": 4.4,
                "rating_count": 88,
                "retrieved_at": "2026-03-12T12:00:00+00:00",
            },
            {
                "source": "ebay",
                "url": "https://www.ebay.com/sch/i.html?_nkw=creatine+powder",
                "title": "Creatine Powder eBay search",
                "price": 0.0,
                "avg_rating": 0.0,
                "rating_count": 0,
                "retrieved_at": "2026-03-12T12:00:00+00:00",
            },
            {
                "source": "amazon",
                "url": "https://www.amazon.com/dp/B000MISSING",
                "title": "Missing rating record",
                "price": 22.0,
                "avg_rating": 0.0,
                "rating_count": 0,
                "retrieved_at": "2026-03-12T12:00:00+00:00",
            },
            {
                "source": "walmart",
                "url": "https://www.walmart.com/ip/123456",
                "title": "Valid Walmart Whey Isolate Product",
                "price": 29.99,
                "avg_rating": 4.2,
                "rating_count": 120,
                "retrieved_at": "2026-03-12T12:00:00+00:00",
            },
        ],
        "reviews": [
            {
                "source": "ebay",
                "url": "https://www.ebay.com/itm/1234567890",
                "review_text": "Good texture and no flavor issues.",
            },
            {
                "source": "walmart",
                "url": "https://www.walmart.com/ip/123456",
                "review_text": "Good whey isolate profile.",
            }
        ],
        "visuals": [
            {
                "source": "ebay",
                "url": "https://www.ebay.com/itm/1234567890",
                "image_url": "https://example.com/product.jpg",
            },
            {
                "source": "walmart",
                "url": "https://www.walmart.com/ip/123456",
                "image_url": "https://example.com/walmart.jpg",
            }
        ],
    }
    rows = _build_records(collection, rejection_counts=rejection_counts)
    assert len(rows) == 1
    row = rows[0]
    assert row["title"]
    assert row["url"].startswith("http")
    assert isinstance(row["review_snippets"], list)
    assert row["ingredient_text"]
    assert rejection_counts.get("unsupported_source_walmart", 0) >= 1


def test_catalog_store_normalizes_url_and_rejects_search_pages(tmp_path: Path) -> None:
    async def run() -> None:
        settings = _settings(tmp_path)
        store = SQLiteEvidenceStore(settings.sqlite_path)
        await store.initialize()
        await store.upsert_catalog_records(
            [
                {
                    "source": "amazon",
                    "url": "https://www.amazon.com/dp/B000TEST01/ref=sr_1_1?th=1",
                    "title": "Canonical URL test product",
                    "brand": "Canonical Brand",
                    "price": 49.0,
                    "rating": 4.5,
                    "rating_count": 120,
                    "image_url": "https://images.example.com/p.png",
                    "ingredient_text": "whey isolate, low lactose",
                    "review_snippets": ["Mixes well and tastes good."],
                    "retrieved_at": "2026-03-12T12:00:00+00:00",
                },
                {
                    "source": "walmart",
                    "url": "https://www.walmart.com/search?q=whey+isolate",
                    "title": "Walmart search listing",
                    "price": 0.0,
                    "rating": 0.0,
                    "rating_count": 0,
                    "image_url": "",
                    "ingredient_text": "",
                    "review_snippets": [],
                    "retrieved_at": "",
                },
            ]
        )
        rows = await store.list_catalog_records(query="canonical", limit=20)
        assert len(rows) == 1
        assert rows[0]["url"] == "https://www.amazon.com/dp/B000TEST01"

    asyncio.run(run())
