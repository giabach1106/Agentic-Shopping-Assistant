from __future__ import annotations

import asyncio
from pathlib import Path

from app.collectors.realtime import LiveRealtimeCollector
from app.core.config import Settings


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
        rag_top_k=5,
        rag_chroma_path=Path("./tmp-chroma"),
        rag_collection_name="shopping_reviews_test",
        ui_executor_backend="mock",
        stop_before_pay=True,
        max_model_calls_per_session=50,
        max_estimated_cost_per_session_usd=1.0,
        estimated_cost_per_call_pro_usd=0.01,
        estimated_cost_per_call_lite_usd=0.004,
        runtime_mode="prod",
    )


def test_live_collector_uses_browser_fallback_for_marketplace_challenge(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, text: str) -> None:
            self.text = text

        def json(self) -> dict:
            return {"data": {"children": []}}

    async def run_test() -> None:
        collector = LiveRealtimeCollector(_settings())

        async def fake_get(url: str):
            if "amazon.com" in url:
                return FakeResponse("Enter the characters you see below")
            if "reddit.com" in url:
                return FakeResponse("")
            return FakeResponse("")

        async def fake_browser_fetch(_url: str) -> str:
            return """
            <div data-component-type="s-search-result">
              <a href="/Desk-Chair/dp/B0TEST1234">
                <span>Ergonomic Office Chair with Adjustable Lumbar Support</span>
              </a>
              <span aria-label="4.5 out of 5 stars"></span>
              <span aria-label="210 ratings"></span>
              $129.99
              <img src="https://m.media-amazon.com/images/I/test-chair.jpg" />
            </div>
            """

        monkeypatch.setattr(collector._client, "get", fake_get)
        monkeypatch.setattr(collector, "_browser_fetch", fake_browser_fetch)
        result = await collector.collect(
            {
                "category": "ergonomic chair",
                "mustHave": ["ergonomic"],
                "deliveryDeadline": "fast delivery",
            }
        )
        assert result.products
        assert result.source_health["amazon"]["fallbackUsed"] is True

    asyncio.run(run_test())
