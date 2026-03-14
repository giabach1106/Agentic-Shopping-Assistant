from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.memory.evidence_store import constraint_fingerprint


def _create_session(client: TestClient) -> str:
    created = client.post("/v1/sessions")
    assert created.status_code == 201
    return created.json()["sessionId"]


def _authorized_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        app_name="Agentic Shopping Assistant API (test)",
        sqlite_path=tmp_path / "agent-memory-test.sqlite3",
        redis_url="redis://localhost:6399/0",
        redis_key_prefix="test:agentic-shopping-assistant:checkpoint",
        aws_region="us-east-1",
        aws_bedrock_kb_id=None,
        default_model_id="us.amazon.nova-2-pro-v1:0",
        fallback_model_id="us.amazon.nova-2-lite-v1:0",
        model_timeout_seconds=1.0,
        latency_threshold_seconds=0.3,
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
        runtime_mode="prod",
        min_review_count=1,
        min_rating_count=1,
        min_source_coverage=5,
        cors_allow_origins=("http://localhost:3000", "http://127.0.0.1:3000"),
        verify_jwt_signature=False,
    )
    app = create_app(settings)
    client = TestClient(app)
    payload = {
        "sub": "test-user-sub",
        "email": "test@example.com",
        "exp": int(time.time()) + 3600,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    client.headers.update({"Authorization": f"Bearer header.{encoded}.sig"})
    return client


def test_capability_query_returns_quick_actions(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.post(
        "/v1/chat",
        json={"sessionId": session_id, "message": "what can you help me with?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["conversationMode"] == "concierge"
    assert payload["conversationIntent"] == "capability_query"
    assert payload["replyKind"] == "answer"
    assert payload["handledBy"] == "concierge"
    assert payload["nextActions"]


def test_unsupported_category_stays_in_discovery_only_mode(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.post(
        "/v1/chat",
        json={"sessionId": session_id, "message": "I want to buy a camera under $500"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["replyKind"] == "discovery"
    assert payload["supportLevel"] == "discovery_only"
    assert payload["state"]["needs_follow_up"] is True


def test_unsupported_category_follow_up_keeps_original_brief(client: TestClient) -> None:
    session_id = _create_session(client)

    first = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": "Recommend a wireless headset with long battery life and low latency.",
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["supportLevel"] == "discovery_only"
    assert first_payload["state"]["constraints"]["category"] == "wireless headset"

    second = client.post(
        "/v1/chat",
        json={"sessionId": session_id, "message": "Main use case: daily study and home office."},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["conversationIntent"] == "shopping_constraints"
    assert second_payload["state"]["constraints"]["category"] == "wireless headset"
    assert "wireless headset" in second_payload["reply"].lower()


def test_resume_confirmation_can_force_collect(client: TestClient) -> None:
    session_id = _create_session(client)

    async def seed_state() -> None:
        await client.app.state.services.session_service.save_state(
            session_id,
            {
                "session_id": session_id,
                "user_message": "seed",
                "history": [],
                "constraints": {
                    "category": "ergonomic chair",
                    "budgetMax": 150,
                    "minRating": 4,
                    "deliveryDeadline": "friday",
                    "mustHave": ["ergonomic"],
                    "niceToHave": [],
                    "exclude": [],
                    "consentAutofill": False,
                    "visualEvidence": [],
                },
                "collection": {},
                "agent_outputs": {},
                "follow_up_count": 0,
                "needs_follow_up": True,
                "status": "NEED_DATA",
                "missing_evidence": ["sourceCoverage"],
                "blocking_agents": ["collect"],
                "reply": "Do you want me to crawl more data now?",
                "conversation_mode": "concierge",
                "conversation_intent": "pending_status",
                "reply_kind": "confirmation_request",
                "handled_by": "concierge",
                "next_actions": [],
                "pending_action": {
                    "type": "crawl_more",
                    "status": "awaiting_user",
                    "prompt": "Do you want me to crawl more data now?",
                    "expiresAfterTurn": 1,
                },
                "support_level": "live_analysis",
                "force_collect": False,
                "domain": "chair",
            },
        )

    asyncio.run(seed_state())

    response = client.post(
        f"/v1/runs/{session_id}/resume",
        json={"message": "yes, do it"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["handledBy"] == "decision"
    assert payload["state"]["agent_outputs"]["collect"]["crawlPerformed"] is True
    assert payload["state"]["pending_action"] is None


def test_session_products_return_furniture_insight_for_desk(client: TestClient) -> None:
    session_id = _create_session(client)
    response = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": "Find a study desk under $220 with 4+ stars delivered by Friday",
        },
    )
    assert response.status_code == 200

    products = client.get(f"/v1/sessions/{session_id}/products")
    assert products.status_code == 200
    item = products.json()["items"][0]
    assert item["productInsight"]["analysisMode"] == "furniture"
    assert item["productInsight"]["keyAttributes"]


def test_post_confirmation_blocked_run_returns_status_update(tmp_path: Path) -> None:
    with _authorized_client(tmp_path) as client:
        session_id = _create_session(client)

        async def seed_state() -> None:
            await client.app.state.services.session_service.save_state(
                session_id,
                {
                    "session_id": session_id,
                    "user_message": "seed",
                    "history": [],
                    "constraints": {
                        "category": "ergonomic chair",
                        "budgetMax": 150,
                        "minRating": 4,
                        "deliveryDeadline": "friday",
                        "mustHave": ["ergonomic"],
                        "niceToHave": [],
                        "exclude": [],
                        "consentAutofill": False,
                        "visualEvidence": [],
                    },
                    "collection": {},
                    "agent_outputs": {},
                    "follow_up_count": 0,
                    "needs_follow_up": True,
                    "status": "NEED_DATA",
                    "missing_evidence": ["sourceCoverage"],
                    "blocking_agents": ["collect"],
                    "reply": "Do you want me to crawl more data now?",
                    "conversation_mode": "concierge",
                    "conversation_intent": "pending_status",
                    "reply_kind": "confirmation_request",
                    "handled_by": "concierge",
                    "next_actions": [],
                    "pending_action": {
                        "type": "crawl_more",
                        "status": "awaiting_user",
                        "prompt": "Do you want me to crawl more data now?",
                        "expiresAfterTurn": 1,
                    },
                    "support_level": "live_analysis",
                    "force_collect": False,
                    "domain": "chair",
                    "action_history": {},
                },
            )

        asyncio.run(seed_state())

        response = client.post(
            f"/v1/runs/{session_id}/resume",
            json={"message": "yes, do it"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["replyKind"] in {"status_update", "analysis_result"}
        assert payload["pendingAction"] is None
        assert payload["state"]["needs_follow_up"] in {True, False}
        assert payload["state"]["action_history"]
        if payload["status"] == "NEED_DATA":
            assert "sourceCoverage" in payload["missingEvidence"]
        else:
            assert payload["decision"] is not None


def test_changed_constraints_reenable_confirmation_flow(tmp_path: Path) -> None:
    with _authorized_client(tmp_path) as client:
        session_id = _create_session(client)
        prior_constraints = {
            "category": "ergonomic chair",
            "budgetMax": 150,
            "minRating": 4,
            "deliveryDeadline": "friday",
            "mustHave": ["ergonomic"],
            "niceToHave": [],
            "exclude": [],
            "consentAutofill": False,
            "visualEvidence": [],
        }
        prior_key = f"crawl_more:{constraint_fingerprint(prior_constraints)}"

        async def seed_state() -> None:
            await client.app.state.services.session_service.save_state(
                session_id,
                {
                    "session_id": session_id,
                    "user_message": "seed",
                    "history": [],
                    "constraints": prior_constraints,
                    "collection": {},
                    "agent_outputs": {},
                    "follow_up_count": 0,
                    "needs_follow_up": True,
                    "status": "NEED_DATA",
                    "missing_evidence": ["sourceCoverage"],
                    "blocking_agents": ["collect"],
                    "reply": "Still blocked.",
                    "conversation_mode": "shopping_analysis",
                    "conversation_intent": "shopping_constraints",
                    "reply_kind": "status_update",
                    "handled_by": "decision",
                    "next_actions": [],
                    "pending_action": None,
                    "support_level": "live_analysis",
                    "force_collect": False,
                    "domain": "chair",
                    "action_history": {
                        prior_key: {"status": "confirmed", "count": 1}
                    },
                },
            )

        asyncio.run(seed_state())

        response = client.post(
            "/v1/chat",
            json={"sessionId": session_id, "message": "Keep it under $120 instead."},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["replyKind"] in {"confirmation_request", "analysis_result"}
        if payload["replyKind"] == "confirmation_request":
            assert payload["pendingAction"]["type"] == "crawl_more"
        else:
            assert payload["decision"] is not None
