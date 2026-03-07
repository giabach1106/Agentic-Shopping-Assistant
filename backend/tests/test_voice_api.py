from __future__ import annotations

from fastapi.testclient import TestClient


def test_voice_consult_endpoint_returns_answer(client: TestClient) -> None:
    created = client.post("/v1/sessions")
    assert created.status_code == 201
    session_id = created.json()["sessionId"]

    chat = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": "I need an ergonomic chair under $150 with 4 stars delivered by friday",
        },
    )
    assert chat.status_code == 200

    consult = client.post(
        "/v1/voice/consult",
        json={
            "sessionId": session_id,
            "question": "Is this recommendation worth it for daily study?",
        },
    )
    assert consult.status_code == 200
    payload = consult.json()
    assert payload["sessionId"] == session_id
    assert payload["mode"] == "text-simulated-voice"
    assert "answer" in payload
    assert "modelMeta" in payload

