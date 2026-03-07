from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint_returns_model_routing_info(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert "defaultModel" in payload
    assert "fallbackModel" in payload
    assert "checkpointBackend" in payload

