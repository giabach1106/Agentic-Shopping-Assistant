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


def test_planner_parses_numeric_budget_followup() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        existing = {
            "category": "ergonomic chair",
            "budgetMax": None,
            "minRating": 4,
            "deliveryDeadline": "friday",
            "mustHave": ["ergonomic"],
            "niceToHave": [],
            "exclude": [],
        }

        result = await planner.run(
            message="500",
            history=[],
            existing_constraints=existing,
            follow_up_count=1,
        )
        assert result["constraints"]["budgetMax"] == 500
        assert result["needsFollowUp"] is False

    asyncio.run(run_test())


def test_planner_accepts_generic_category_token() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        existing = {
            "category": None,
            "budgetMax": 150,
            "minRating": 4,
            "deliveryDeadline": "friday",
            "mustHave": [],
            "niceToHave": [],
            "exclude": [],
        }

        result = await planner.run(
            message="sport",
            history=[],
            existing_constraints=existing,
            follow_up_count=1,
        )
        assert result["constraints"]["category"] == "sport"
        assert result["needsFollowUp"] is False

    asyncio.run(run_test())


def test_planner_deadline_token_does_not_override_existing_category() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        existing = {
            "category": "ergonomic chair",
            "budgetMax": 150,
            "minRating": 4,
            "deliveryDeadline": None,
            "mustHave": [],
            "niceToHave": [],
            "exclude": [],
        }

        result = await planner.run(
            message="friday",
            history=[],
            existing_constraints=existing,
            follow_up_count=2,
        )
        assert result["constraints"]["category"] == "ergonomic chair"
        assert result["constraints"]["deliveryDeadline"] == "friday"

    asyncio.run(run_test())


def test_planner_normalizes_find_me_whey_isolate_and_sets_optional_clarification() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        result = await planner.run(
            message="find me whey isolate",
            history=[],
            existing_constraints={},
            follow_up_count=0,
            clarification_asked_count=0,
        )
        assert result["constraints"]["category"] == "whey isolate"
        assert result["needsFollowUp"] is False
        assert result["clarificationPending"]["field"] == "budgetMax"
        assert result["searchReady"] is True

    asyncio.run(run_test())


def test_planner_updates_this_friday_without_overwriting_category() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        existing = {
            "category": "whey isolate",
            "budgetMax": 80,
            "minRating": None,
            "deliveryDeadline": None,
            "mustHave": ["whey isolate"],
            "niceToHave": [],
            "exclude": [],
        }
        result = await planner.run(
            message="by this friday",
            history=[],
            existing_constraints=existing,
            follow_up_count=0,
            clarification_asked_count=1,
        )
        assert result["constraints"]["category"] == "whey isolate"
        assert result["constraints"]["deliveryDeadline"] == "this friday"
        assert result["needsFollowUp"] is False

    asyncio.run(run_test())


def test_planner_treats_clean_ingredients_as_preference_not_category() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        existing = {
            "category": "whey isolate",
            "budgetMax": None,
            "minRating": None,
            "deliveryDeadline": None,
            "mustHave": ["whey isolate"],
            "niceToHave": [],
            "exclude": [],
        }
        result = await planner.run(
            message="need clean ingredients",
            history=[],
            existing_constraints=existing,
            follow_up_count=0,
            clarification_asked_count=1,
        )
        assert result["constraints"]["category"] == "whey isolate"
        assert "clean ingredients" in result["constraints"]["mustHave"]

    asyncio.run(run_test())


def test_planner_extracts_width_constraints_from_follow_up() -> None:
    async def run_test() -> None:
        router = ModelRouter(_settings())
        planner = PlannerAgent(router)
        existing = {
            "category": "standing desk",
            "budgetMax": None,
            "minRating": None,
            "deliveryDeadline": None,
            "mustHave": [],
            "niceToHave": [],
            "exclude": [],
        }
        result = await planner.run(
            message="above 55 inches wide",
            history=[],
            existing_constraints=existing,
            follow_up_count=0,
            clarification_asked_count=1,
        )
        assert result["constraints"]["category"] == "standing desk"
        assert result["constraints"]["widthMinInches"] == 55
        assert result["needsFollowUp"] is False

    asyncio.run(run_test())
