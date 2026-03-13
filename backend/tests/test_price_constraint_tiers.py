from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from app.agents.stubs import PriceLogisticsAgent
from app.tools.ui_executor import UIExecutionRequest, UIExecutionResult


class _FakeModelRouter:
    async def call(self, task_type: str, payload: dict[str, Any], session_id: str | None = None) -> Any:
        del task_type, payload, session_id
        return SimpleNamespace(
            model_id="test-model",
            fallback_used=False,
            fallback_reason=None,
        )


class _FakeUIExecutor:
    async def execute(self, request: UIExecutionRequest) -> UIExecutionResult:
        del request
        return UIExecutionResult(
            candidates=[],
            execution_trace=[],
            blockers=[],
            consent_autofill=False,
            stop_before_pay=True,
        )


def test_price_agent_applies_strict_then_relaxed_tiers() -> None:
    async def run() -> None:
        agent = PriceLogisticsAgent(
            model_router=_FakeModelRouter(),  # type: ignore[arg-type]
            ui_executor=_FakeUIExecutor(),
            stop_before_pay=True,
            runtime_mode="prod",
            ui_executor_backend="mock",
        )
        constraints = {
            "category": "whey isolate",
            "mustHave": ["whey isolate"],
            "budgetMax": 90,
            "minRating": 4.0,
        }
        collection = {
            "products": [
                {
                    "source": "amazon",
                    "url": "https://www.amazon.com/dp/B000A11111",
                    "title": "Strict Whey Isolate 2lb",
                    "price": 85.0,
                    "avg_rating": 4.6,
                    "shipping_eta": "2 days",
                    "return_policy": "30-day return",
                    "evidence_id": "strict-1",
                },
                {
                    "source": "ebay",
                    "url": "https://www.ebay.com/itm/12345678901",
                    "title": "Soft Five Whey Isolate 2lb",
                    "price": 94.0,
                    "avg_rating": 4.7,
                    "shipping_eta": "3 days",
                    "return_policy": "Seller policy",
                    "evidence_id": "soft-5-1",
                },
                {
                    "source": "dps",
                    "url": "https://www.dpsnutrition.net/i/29230/proven-whey-isolate.htm",
                    "title": "Soft Fifteen Whey Isolate 2lb",
                    "price": 102.0,
                    "avg_rating": 4.8,
                    "shipping_eta": "4 days",
                    "return_policy": "Store return policy",
                    "evidence_id": "soft-15-1",
                },
                {
                    "source": "amazon",
                    "url": "https://www.amazon.com/dp/B000A99999",
                    "title": "Over Budget Whey Isolate 2lb",
                    "price": 120.0,
                    "avg_rating": 4.9,
                    "shipping_eta": "2 days",
                    "return_policy": "30-day return",
                    "evidence_id": "over-budget-1",
                },
            ]
        }

        payload = await agent.run(constraints, collection, session_id="test-session")
        candidates = payload["candidates"]

        assert candidates
        assert candidates[0]["constraintTier"] == "strict"
        assert candidates[0]["price"] <= 90
        assert any(item["constraintTier"] == "soft_5" for item in candidates)
        assert any(item["constraintTier"] == "soft_15" for item in candidates)
        assert all(item["price"] <= 103.5 for item in candidates)
        assert not any(item["price"] > 110 for item in candidates)

    asyncio.run(run())
