from __future__ import annotations

from fastapi.testclient import TestClient


def test_resume_requires_follow_up_message_when_checkpoint_waits(client: TestClient) -> None:
    created = client.post("/v1/sessions")
    assert created.status_code == 201
    session_id = created.json()["sessionId"]

    first_turn = client.post(
        "/v1/chat",
        json={"sessionId": session_id, "message": "I need a chair"},
    )
    assert first_turn.status_code == 200
    assert first_turn.json()["state"]["needs_follow_up"] is True

    resume_missing = client.post(f"/v1/runs/{session_id}/resume", json={})
    assert resume_missing.status_code == 400

    resume_with_input = client.post(
        f"/v1/runs/{session_id}/resume",
        json={"message": "under $150 and 4 stars delivered by friday"},
    )
    assert resume_with_input.status_code == 200
    payload = resume_with_input.json()
    assert payload["sessionId"] == session_id
    assert "reply" in payload
    assert payload["state"]["needs_follow_up"] in {True, False}

