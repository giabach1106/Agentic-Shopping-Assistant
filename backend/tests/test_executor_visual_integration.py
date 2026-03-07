from __future__ import annotations

from fastapi.testclient import TestClient


def _new_session(client: TestClient) -> str:
    created = client.post("/v1/sessions")
    assert created.status_code == 201
    return created.json()["sessionId"]


def test_price_logistics_autofill_flag_false_by_default(client: TestClient) -> None:
    session_id = _new_session(client)
    response = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": "I need an ergonomic chair under $150 with 4 stars delivered by friday",
        },
    )
    assert response.status_code == 200
    state = response.json()["state"]
    price_output = state["agent_outputs"]["price"]
    assert price_output["consentAutofill"] is False
    assert price_output["stopBeforePay"] is True


def test_price_logistics_autofill_flag_true_when_user_consents(client: TestClient) -> None:
    session_id = _new_session(client)
    response = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": (
                "I need an ergonomic chair under $150 with 4 stars delivered by friday "
                "and autofill checkout details"
            ),
        },
    )
    assert response.status_code == 200
    state = response.json()["state"]
    price_output = state["agent_outputs"]["price"]
    assert price_output["consentAutofill"] is True
    assert any(
        step["step"] == "autofill_checkout" and step["status"] == "ok"
        for step in price_output["executionTrace"]
    )


def test_visual_returns_need_more_evidence_when_no_images(client: TestClient) -> None:
    session_id = _new_session(client)
    response = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": "I need an ergonomic chair under $150 with 4 stars delivered by friday",
        },
    )
    assert response.status_code == 200
    visual_output = response.json()["state"]["agent_outputs"]["visual"]
    assert visual_output["status"] == "NEED_MORE_EVIDENCE"
    assert len(visual_output["requiredEvidence"]) > 0


def test_visual_returns_ok_when_user_photo_is_available(client: TestClient) -> None:
    session_id = _new_session(client)
    response = client.post(
        "/v1/chat",
        json={
            "sessionId": session_id,
            "message": (
                "I need an ergonomic chair under $150 with 4 stars delivered by friday "
                "and uploaded photo from my room"
            ),
        },
    )
    assert response.status_code == 200
    visual_output = response.json()["state"]["agent_outputs"]["visual"]
    assert visual_output["status"] == "OK"
    assert len(visual_output["evidenceRefs"]) > 0
