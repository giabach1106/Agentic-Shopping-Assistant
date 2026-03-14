from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents.concierge import ConciergeAgent
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


def _agent() -> ConciergeAgent:
    profile = {
        "name": "AgentCart",
        "coreCapabilities": ["Session-bound chat", "Explainable scoring"],
        "stack": ["Frontend: Next.js 15, React 19, Tailwind CSS 4", "Backend: FastAPI, LangGraph"],
        "runtime": {
            "runtimeMode": "dev",
            "ragBackend": "inmemory",
            "uiExecutorBackend": "mock",
            "requireAuth": True,
            "stopBeforePay": True,
        },
    }
    return ConciergeAgent(ModelRouter(_settings()), profile)


def test_concierge_handles_capability_query() -> None:
    async def run_test() -> None:
        agent = _agent()
        result = await agent.run(
            message="what can you help me with?",
            history=[],
            previous_state={},
        )
        assert result["route"] == "respond_only"
        assert result["conversationIntent"] == "capability_query"
        assert result["replyKind"] == "answer"
        assert result["nextActions"]

    asyncio.run(run_test())


def test_concierge_handles_project_question() -> None:
    async def run_test() -> None:
        agent = _agent()
        result = await agent.run(
            message="What tech stack does this project use?",
            history=[],
            previous_state={},
        )
        assert result["conversationIntent"] == "project_question"
        assert "FastAPI" in result["reply"] or "Next.js" in result["reply"]

    asyncio.run(run_test())


def test_concierge_routes_broad_desk_request_to_discovery() -> None:
    async def run_test() -> None:
        agent = _agent()
        result = await agent.run(
            message="toi muon mua ban hoc thi nen mua hang gi",
            history=[],
            previous_state={},
        )
        assert result["route"] == "continue_planner"
        assert result["conversationIntent"] == "shopping_discovery"
        assert result["supportLevel"] == "live_analysis"
        assert result["constraints"]["category"] == "study desk"

    asyncio.run(run_test())


def test_concierge_repeats_pending_confirmation_status() -> None:
    async def run_test() -> None:
        agent = _agent()
        result = await agent.run(
            message="what next?",
            history=[],
            previous_state={
                "constraints": {"category": "ergonomic chair"},
                "pending_action": {
                    "type": "crawl_more",
                    "status": "awaiting_user",
                    "prompt": "Do you want me to crawl more data now?",
                    "expiresAfterTurn": 1,
                },
                "missing_evidence": ["sourceCoverage"],
            },
        )
        assert result["route"] == "ask_confirmation"
        assert result["replyKind"] == "confirmation_request"
        assert result["pendingAction"]["type"] == "crawl_more"

    asyncio.run(run_test())


def test_concierge_accepts_yes_for_pending_action() -> None:
    async def run_test() -> None:
        agent = _agent()
        result = await agent.run(
            message="yes, do it",
            history=[],
            previous_state={
                "constraints": {"category": "ergonomic chair"},
                "pending_action": {
                    "type": "crawl_more",
                    "status": "awaiting_user",
                    "prompt": "Do you want me to crawl more data now?",
                },
            },
        )
        assert result["route"] == "continue_analysis"
        assert result["conversationIntent"] == "action_confirmation"
        assert result["forceCollect"] is True

    asyncio.run(run_test())


def test_concierge_accepts_no_for_pending_action() -> None:
    async def run_test() -> None:
        agent = _agent()
        result = await agent.run(
            message="no, keep the current state",
            history=[],
            previous_state={
                "constraints": {"category": "ergonomic chair"},
                "pending_action": {
                    "type": "crawl_more",
                    "status": "awaiting_user",
                    "prompt": "Do you want me to crawl more data now?",
                },
            },
        )
        assert result["route"] == "respond_only"
        assert result["conversationIntent"] == "action_rejection"
        assert result["pendingAction"] is None

    asyncio.run(run_test())


def test_concierge_can_reopen_crawl_confirmation_after_prior_attempt() -> None:
    async def run_test() -> None:
        agent = _agent()
        result = await agent.run(
            message="please crawl for more data",
            history=[],
            previous_state={
                "constraints": {"category": "ergonomic chair"},
                "missing_evidence": ["sourceCoverage"],
                "action_history": {
                    "crawl_more:older-signature": {"status": "confirmed", "count": 1}
                },
            },
        )
        assert result["route"] == "ask_confirmation"
        assert result["replyKind"] == "confirmation_request"
        assert result["pendingAction"]["type"] == "crawl_more"

    asyncio.run(run_test())
