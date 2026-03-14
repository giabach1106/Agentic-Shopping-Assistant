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


def test_live_collector_enriches_amazon_pdp_reviews(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, text: str) -> None:
            self.text = text

        def json(self) -> dict:
            return {"data": {"children": []}}

    async def run_test() -> None:
        collector = LiveRealtimeCollector(_settings())

        search_html = """
        <div data-component-type="s-search-result">
          <a href="/Executive-Standing-Desk/dp/B0DESK5555">
            <span>Executive Standing Desk 60 inch with Cable Management Tray</span>
          </a>
          <span aria-label="4.6 out of 5 stars"></span>
          <span aria-label="754 ratings"></span>
          $299.99
          <img src="https://m.media-amazon.com/images/I/test-desk.jpg" />
        </div>
        """
        pdp_html = """
        <html>
          <span id="productTitle">Executive Standing Desk 60 inch with Cable Management Tray</span>
          <span class="a-price"><span class="a-offscreen">$289.99</span></span>
          <span aria-label="4.6 out of 5 stars"></span>
          <span aria-label="754 ratings"></span>
          <div>Product Dimensions 60 inches</div>
          <div>Ships from</span><span>Amazon.com</span>Sold by</span><span>DeskCo</span></div>
          <div data-hook="review" id="customer_review-R1">
            <a data-hook="review-title"><span>Stable for dual monitors</span></a>
            <i data-hook="review-star-rating"><span>5.0 out of 5 stars</span></i>
            <span data-hook="review-body"><span>The frame feels sturdy and the cable tray keeps the setup clean.</span></span>
            <span>12 people found this helpful</span>
          </div>
        </html>
        """

        async def fake_get(url: str):
            if "/s?" in url:
                return FakeResponse(search_html)
            if "/dp/B0DESK5555" in url:
                return FakeResponse(pdp_html)
            if "reddit.com" in url:
                return FakeResponse("")
            return FakeResponse("")

        monkeypatch.setattr(collector._client, "get", fake_get)
        result = await collector.collect(
            {
                "category": "standing desk",
                "mustHave": ["cable management"],
            }
        )
        amazon_products = [item for item in result.products if item.source == "amazon"]
        amazon_reviews = [item for item in result.reviews if item.source == "amazon"]

        assert amazon_products
        assert amazon_products[0].rating_count == 754
        assert amazon_products[0].spec_text and "60 inches" in amazon_products[0].spec_text
        assert amazon_reviews
        assert "stable for dual monitors" in amazon_reviews[0].review_text.lower()
        assert result.source_health["amazonPdp"]["status"] == "ok"

    asyncio.run(run_test())
