from __future__ import annotations

from fastapi.testclient import TestClient


def test_chat_endpoint_persists_session_history(client: TestClient) -> None:
    session_response = client.post("/v1/sessions")
    assert session_response.status_code == 201
    session_id = session_response.json()["sessionId"]

    turn_1 = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": "I need an ergonomic chair under $150",
        },
    )
    assert turn_1.status_code == 200
    payload_1 = turn_1.json()
    assert payload_1["sessionId"] == session_id
    assert "reply" in payload_1
    assert "state" in payload_1

    turn_2 = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": "Minimum rating is 4 stars and delivered by Friday",
        },
    )
    assert turn_2.status_code == 200

    snapshot = client.get(f"/v1/sessions/{session_id}")
    assert snapshot.status_code == 200
    snapshot_payload = snapshot.json()
    assert snapshot_payload["sessionId"] == session_id
    assert len(snapshot_payload["messages"]) == 4
    assert snapshot_payload["checkpointState"] is not None
    decision = snapshot_payload["checkpointState"]["agent_outputs"]["decision"]
    assert decision["status"] in {"OK", "NEED_DATA"}
    assert "scientificScore" in decision
    assert "evidenceStats" in decision
    if decision["status"] == "OK":
        assert decision["decision"] is not None
