from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.services.observability import RuntimeTelemetry

InvokeFn = Callable[[str, str, dict[str, Any], float], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class ModelCallResult:
    model_id: str
    output: dict[str, Any]
    fallback_used: bool
    fallback_reason: str | None
    latency_seconds: float


class ModelRouter:
    def __init__(
        self,
        settings: Settings,
        invoke_fn: InvokeFn | None = None,
        telemetry: RuntimeTelemetry | None = None,
    ) -> None:
        self._settings = settings
        self._invoke_fn = invoke_fn or self._invoke_model
        self._logger = logging.getLogger(self.__class__.__name__)
        self._failure_counts: dict[str, int] = defaultdict(int)
        self._telemetry = telemetry or RuntimeTelemetry()
        self._bedrock_client = None

        if not settings.mock_model:
            self._bedrock_client = boto3.client(
                "bedrock-runtime", region_name=settings.aws_region
            )

    async def call(
        self,
        task_type: str,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> ModelCallResult:
        session_key = session_id or "global"
        usage = self._telemetry.session_usage(session_key)
        if usage["calls"] >= self._settings.max_model_calls_per_session:
            raise RuntimeError(
                f"Session model call cap exceeded ({self._settings.max_model_calls_per_session})."
            )
        if usage["estimatedCostUsd"] >= self._settings.max_estimated_cost_per_session_usd:
            raise RuntimeError(
                "Session estimated cost cap exceeded "
                f"({self._settings.max_estimated_cost_per_session_usd})."
            )

        reason: str | None = None

        try:
            primary_result = await self._attempt_with_retries(
                model_id=self._settings.default_model_id,
                task_type=task_type,
                payload=payload,
            )
            if primary_result.latency_seconds <= self._settings.latency_threshold_seconds:
                self._failure_counts[task_type] = 0
                self._record_metrics(task_type, session_key, primary_result)
                return primary_result

            reason = (
                f"latency {primary_result.latency_seconds:.2f}s exceeded threshold "
                f"{self._settings.latency_threshold_seconds:.2f}s"
            )
            self._logger.warning(
                "Switching from default model to fallback model for task '%s': %s",
                task_type,
                reason,
            )
        except Exception as exc:  # noqa: BLE001
            self._failure_counts[task_type] += 1
            reason = (
                f"default model failed after retries ({self._failure_counts[task_type]} "
                f"consecutive failures): {exc!r}"
            )
            self._logger.warning(
                "Switching from default model to fallback model for task '%s': %s",
                task_type,
                reason,
            )

        fallback_result = await self._attempt_with_retries(
            model_id=self._settings.fallback_model_id,
            task_type=task_type,
            payload=payload,
        )
        fallback_result.fallback_used = True
        fallback_result.fallback_reason = reason
        self._record_metrics(task_type, session_key, fallback_result)
        return fallback_result

    def snapshot_metrics(self) -> dict[str, Any]:
        return self._telemetry.snapshot()

    async def _attempt_with_retries(
        self,
        model_id: str,
        task_type: str,
        payload: dict[str, Any],
    ) -> ModelCallResult:
        last_error: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                return await self._invoke_with_timing(model_id, task_type, payload)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self._logger.warning(
                    "Model invocation attempt %d/%d failed for %s (%s): %r",
                    attempt,
                    self._settings.max_retries,
                    task_type,
                    model_id,
                    exc,
                )
        assert last_error is not None
        raise last_error

    async def _invoke_with_timing(
        self,
        model_id: str,
        task_type: str,
        payload: dict[str, Any],
    ) -> ModelCallResult:
        started = time.perf_counter()
        output = await asyncio.wait_for(
            self._invoke_fn(
                model_id,
                task_type,
                payload,
                self._settings.model_timeout_seconds,
            ),
            timeout=self._settings.model_timeout_seconds,
        )
        elapsed = time.perf_counter() - started
        return ModelCallResult(
            model_id=model_id,
            output=output,
            fallback_used=False,
            fallback_reason=None,
            latency_seconds=elapsed,
        )

    async def _invoke_model(
        self,
        model_id: str,
        task_type: str,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if self._settings.mock_model:
            return {
                "text": f"[mock:{model_id}] handled task '{task_type}'",
                "echo": payload,
            }

        if self._bedrock_client is None:
            raise RuntimeError("Bedrock client was not initialized.")

        prompt = payload.get("prompt") or json.dumps(payload, ensure_ascii=True)
        try:
            response = await asyncio.to_thread(
                self._bedrock_client.converse,
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 512, "temperature": 0.2},
            )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"Bedrock invocation failed for {model_id}: {exc}") from exc

        text_output = ""
        content_items = (
            response.get("output", {})
            .get("message", {})
            .get("content", [])
        )
        for item in content_items:
            if "text" in item:
                text_output += item["text"]

        if not text_output:
            text_output = "[empty model response]"

        return {
            "text": text_output,
            "raw": response,
            "timeoutSeconds": timeout_seconds,
        }

    def _record_metrics(
        self,
        task_type: str,
        session_id: str,
        result: ModelCallResult,
    ) -> None:
        estimated_cost = self._estimate_cost(result.model_id)
        self._telemetry.record(
            task_type=task_type,
            session_id=session_id,
            latency_seconds=result.latency_seconds,
            fallback_used=result.fallback_used,
            estimated_cost_usd=estimated_cost,
        )

    def _estimate_cost(self, model_id: str) -> float:
        if "lite" in model_id.lower():
            return self._settings.estimated_cost_per_call_lite_usd
        return self._settings.estimated_cost_per_call_pro_usd
