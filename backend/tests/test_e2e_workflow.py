from __future__ import annotations

from fastapi.testclient import TestClient


def _create_session(client: TestClient) -> str:
    created = client.post("/v1/sessions")
    assert created.status_code == 201
    return created.json()["sessionId"]


def test_e2e_complete_flow_with_full_query(client: TestClient) -> None:
    session_id = _create_session(client)
    chat = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": (
                "I need an ergonomic chair under $150 with 4+ stars delivered by Friday"
            ),
        },
    )
    assert chat.status_code == 200
    state = chat.json()["state"]
    assert state["needs_follow_up"] is False
    assert "decision" in state["agent_outputs"]

    recommendation = client.get(f"/v1/recommendations/{session_id}")
    assert recommendation.status_code == 200
    payload = recommendation.json()
    assert payload["sessionId"] == session_id
    assert payload["verdict"] in {"BUY", "WAIT", "AVOID"}
    assert "scoreBreakdown" in payload


def test_e2e_missing_info_then_resume_to_decision(client: TestClient) -> None:
    session_id = _create_session(client)
    turn_1 = client.post(
        "/v1/chat",
        json={"sessionId": session_id, "message": "I need a chair"},
    )
    assert turn_1.status_code == 200
    assert turn_1.json()["state"]["needs_follow_up"] is True

    turn_2 = client.post(
        f"/v1/runs/{session_id}/resume",
        json={"message": "under $150, min 4 stars, delivered by friday"},
    )
    assert turn_2.status_code == 200
    assert "decision" in turn_2.json()["state"]["agent_outputs"]

    recommendation = client.get(f"/v1/recommendations/{session_id}")
    assert recommendation.status_code == 200
    assert recommendation.json()["verdict"] in {"BUY", "WAIT", "AVOID"}


def test_e2e_automation_blocked_returns_graceful_risk_flag(client: TestClient) -> None:
    session_id = _create_session(client)
    chat = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": (
                "I need an ergonomic chair under $150 with 4 stars delivered by friday "
                "exclude captcha"
            ),
        },
    )
    assert chat.status_code == 200

    recommendation = client.get(f"/v1/recommendations/{session_id}")
    assert recommendation.status_code == 200
    payload = recommendation.json()
    assert payload["verdict"] in {"WAIT", "AVOID"}
    assert any("automation" in item.lower() for item in payload["riskFlags"])

