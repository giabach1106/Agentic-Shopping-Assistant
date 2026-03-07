from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents.stubs import PlannerAgent
from app.core.config import Settings
from app.core.model_router import ModelRouter


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
    )


def test_planner_merges_existing_constraints() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        existing = {
            "category": "ergonomic chair",
            "budgetMax": 150,
            "minRating": None,
            "deliveryDeadline": None,
            "mustHave": ["ergonomic"],
            "niceToHave": [],
            "exclude": [],
        }

        result = await planner.run(
            message="minimum rating is 4 stars",
            history=[],
            existing_constraints=existing,
            follow_up_count=0,
        )
        assert result["constraints"]["category"] == "ergonomic chair"
        assert result["constraints"]["budgetMax"] == 150
        assert result["constraints"]["minRating"] == 4
        assert "category" in result["inferredFields"]

    asyncio.run(run_test())


def test_planner_stops_followup_after_cap() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        result = await planner.run(
            message="I need something good",
            history=[],
            existing_constraints={},
            follow_up_count=4,
        )
        assert result["needsFollowUp"] is False
        assert result["followUpQuestion"] is None

    asyncio.run(run_test())
