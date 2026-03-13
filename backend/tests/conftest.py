from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
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
        cors_allow_origins=("http://localhost:3000", "http://127.0.0.1:3000"),
        verify_jwt_signature=False,
    )


@pytest.fixture()
def client(test_settings: Settings) -> TestClient:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        payload = {
            "sub": "test-user-sub",
            "email": "test@example.com",
            "exp": int(time.time()) + 3600,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload).encode("utf-8")
        ).decode("utf-8").rstrip("=")
        token = f"header.{encoded}.sig"
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client
