from __future__ import annotations

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
        default_model_id="us.amazon.nova-2-pro-v1:0",
        fallback_model_id="us.amazon.nova-2-lite-v1:0",
        model_timeout_seconds=1.0,
        latency_threshold_seconds=0.3,
        max_retries=1,
        mock_model=True,
    )


@pytest.fixture()
def client(test_settings: Settings) -> TestClient:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        yield test_client

