from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

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
        rag_chroma_path=Path("./tmp-chroma"),
        rag_collection_name="shopping_reviews_test",
        ui_executor_backend="mock",
        stop_before_pay=True,
        max_model_calls_per_session=50,
        max_estimated_cost_per_session_usd=1.0,
        estimated_cost_per_call_pro_usd=0.01,
        estimated_cost_per_call_lite_usd=0.004,
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


def test_model_router_enforces_session_call_budget() -> None:
    async def run_test() -> None:
        settings = _settings()
        settings.max_model_calls_per_session = 1

        router = ModelRouter(settings)
        await router.call(
            task_type="planner",
            payload={"prompt": "first"},
            session_id="session-1",
        )
        with pytest.raises(RuntimeError):
            await router.call(
                task_type="planner",
                payload={"prompt": "second"},
                session_id="session-1",
            )

    asyncio.run(run_test())


def test_model_router_uses_task_specific_latency_threshold() -> None:
    async def run_test() -> None:
        calls: list[str] = []

        async def fake_invoke(model_id: str, *_args):
            calls.append(model_id)
            await asyncio.sleep(0.6)
            return {"text": "ok"}

        router = ModelRouter(_settings(), invoke_fn=fake_invoke)
        result = await router.call(task_type="decision", payload={"prompt": "hello"})

        assert result.model_id == "pro-model"
        assert result.fallback_used is False
        assert calls == ["pro-model"]

    asyncio.run(run_test())
