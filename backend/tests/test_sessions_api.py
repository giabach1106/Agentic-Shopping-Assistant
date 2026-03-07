from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_create_session_returns_uuid(client: TestClient) -> None:
    response = client.post("/v1/sessions")
    assert response.status_code == 201

    payload = response.json()
    assert "sessionId" in payload
    uuid.UUID(payload["sessionId"])
    assert "createdAt" in payload

