from __future__ import annotations

from typing import Any

from app.memory.redis_checkpoint import RedisCheckpointStore
from app.memory.sqlite_store import SQLiteSessionStore


class SessionService:
    def __init__(
        self,
        sqlite_store: SQLiteSessionStore,
        checkpoint_store: RedisCheckpointStore,
    ) -> None:
        self._sqlite_store = sqlite_store
        self._checkpoint_store = checkpoint_store

    @property
    def checkpoint_backend(self) -> str:
        return self._checkpoint_store.backend_name

    async def initialize(self) -> None:
        await self._sqlite_store.initialize()
        await self._checkpoint_store.connect()

    async def shutdown(self) -> None:
        await self._checkpoint_store.close()

    async def create_session(self) -> dict[str, str]:
        return await self._sqlite_store.create_session()

    async def require_session(self, session_id: str) -> bool:
        return await self._sqlite_store.session_exists(session_id)

    async def add_user_message(self, session_id: str, content: str) -> None:
        await self._sqlite_store.append_message(session_id, "user", content)

    async def add_assistant_message(self, session_id: str, content: str) -> None:
        await self._sqlite_store.append_message(session_id, "assistant", content)

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        return await self._sqlite_store.get_messages(session_id)

    async def save_state(self, session_id: str, state: dict[str, Any]) -> None:
        await self._checkpoint_store.save_checkpoint(session_id, state)

    async def get_checkpoint_state(self, session_id: str) -> dict[str, Any] | None:
        return await self._checkpoint_store.get_checkpoint(session_id)

    async def get_snapshot(self, session_id: str) -> dict[str, Any] | None:
        session = await self._sqlite_store.get_session(session_id)
        if session is None:
            return None

        messages = await self._sqlite_store.get_messages(session_id)
        checkpoint = await self._checkpoint_store.get_checkpoint(session_id)
        return {
            "sessionId": session["sessionId"],
            "createdAt": session["createdAt"],
            "updatedAt": session["updatedAt"],
            "messages": [
                {
                    "role": item["role"],
                    "content": item["content"],
                    "createdAt": item["created_at"],
                }
                for item in messages
            ],
            "checkpointState": checkpoint,
        }
