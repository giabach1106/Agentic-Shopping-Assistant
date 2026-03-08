from __future__ import annotations

from fastapi.testclient import TestClient


def test_recommendation_endpoint_returns_decision_payload(client: TestClient) -> None:
    created = client.post("/v1/sessions")
    assert created.status_code == 201
    session_id = created.json()["sessionId"]

    chat = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": (
                "I need an ergonomic chair under $150 with 4+ stars "
                "delivered by Friday"
            ),
        },
    )
    assert chat.status_code == 200

    recommendation = client.get(f"/v1/recommendations/{session_id}")
    assert recommendation.status_code == 200
    payload = recommendation.json()

    assert payload["sessionId"] == session_id
    assert payload["status"] in {"OK", "NEED_DATA"}
    assert "scientificScore" in payload
    assert "evidenceStats" in payload
    assert isinstance(payload["scientificScore"].get("finalTrust"), float | int)
    if payload["decision"] is not None:
        assert payload["decision"]["verdict"] in {"BUY", "WAIT", "AVOID"}
