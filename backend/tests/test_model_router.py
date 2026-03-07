from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import Settings
from app.core.model_router import ModelRouter


def _settings() -> Settings:
    return Settings(
        app_name="test",
        sqlite_path=Path("unused.sqlite3"),
        redis_url="redis://localhost:6399/0",
        redis_key_prefix="test:key",
        aws_region="us-east-1",
        aws_bedrock_kb_id=None,
        default_model_id="pro-model",
        fallback_model_id="lite-model",
        model_timeout_seconds=1.0,
        latency_threshold_seconds=0.5,
        max_retries=1,
        mock_model=True,
        rag_backend="inmemory",
        rag_top_k=5,
        ui_executor_backend="mock",
        stop_before_pay=True,
    )


def test_model_router_falls_back_on_error() -> None:
    async def run_test() -> None:
        calls: list[str] = []

        async def fake_invoke(model_id: str, *_args):
            calls.append(model_id)
            if model_id == "pro-model":
                raise TimeoutError("primary model timeout")
            return {"text": "fallback-ok"}

        router = ModelRouter(_settings(), invoke_fn=fake_invoke)
        result = await router.call(task_type="planner", payload={"prompt": "hello"})

        assert result.model_id == "lite-model"
        assert result.fallback_used is True
        assert result.fallback_reason is not None
        assert calls == ["pro-model", "lite-model"]

    asyncio.run(run_test())
