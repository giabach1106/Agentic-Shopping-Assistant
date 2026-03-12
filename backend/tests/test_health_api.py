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


def test_runtime_metrics_endpoint_returns_usage_snapshot(client: TestClient) -> None:
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

    metrics = client.get("/v1/metrics/runtime")
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["totalCalls"] > 0
    assert payload["sessionsTracked"] >= 1
    assert isinstance(payload["tasks"], dict)


def test_cors_preflight_allows_frontend_origin(client: TestClient) -> None:
    response = client.options(
        "/v1/sessions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
