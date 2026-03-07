from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis


class RedisCheckpointStore:
    def __init__(self, redis_url: str, key_prefix: str) -> None:
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._redis_client: redis.Redis | None = None
        self._fallback_store: dict[str, str] = {}
        self._using_fallback = False
        self._logger = logging.getLogger(self.__class__.__name__)

    @property
    def backend_name(self) -> str:
        return "memory-fallback" if self._using_fallback else "redis"

    async def connect(self) -> None:
        try:
            self._redis_client = redis.Redis.from_url(self._redis_url, decode_responses=True)
            await self._redis_client.ping()
            self._using_fallback = False
        except Exception as exc:  # noqa: BLE001
            self._logger.warning(
                "Redis checkpoint backend unavailable (%r). Falling back to in-memory store.",
                exc,
            )
            self._redis_client = None
            self._using_fallback = True

    async def close(self) -> None:
        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None

    async def save_checkpoint(self, session_id: str, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=True, default=str)
        key = self._checkpoint_key(session_id)

        if self._redis_client is not None:
            try:
                await self._redis_client.set(key, payload)
                return
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "Redis write failed (%r). Switching to in-memory checkpoint.", exc
                )
                self._redis_client = None
                self._using_fallback = True

        self._fallback_store[session_id] = payload

    async def get_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        key = self._checkpoint_key(session_id)
        payload: str | None = None

        if self._redis_client is not None:
            try:
                payload = await self._redis_client.get(key)
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "Redis read failed (%r). Falling back to in-memory checkpoint.", exc
                )
                self._redis_client = None
                self._using_fallback = True

        if payload is None:
            payload = self._fallback_store.get(session_id)
        if payload is None:
            return None

        return json.loads(payload)

    def _checkpoint_key(self, session_id: str) -> str:
        return f"{self._key_prefix}:{session_id}"

