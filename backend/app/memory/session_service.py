from __future__ import annotations

from typing import Any

from app.memory.evidence_store import SQLiteEvidenceStore
from app.memory.redis_checkpoint import RedisCheckpointStore
from app.memory.sqlite_store import SQLiteSessionStore


class SessionService:
    def __init__(
        self,
        sqlite_store: SQLiteSessionStore,
        checkpoint_store: RedisCheckpointStore,
        evidence_store: SQLiteEvidenceStore,
    ) -> None:
        self._sqlite_store = sqlite_store
        self._checkpoint_store = checkpoint_store
        self._evidence_store = evidence_store

    @property
    def checkpoint_backend(self) -> str:
        return self._checkpoint_store.backend_name

    async def initialize(self) -> None:
        await self._sqlite_store.initialize()
        await self._evidence_store.initialize()
        await self._checkpoint_store.connect()

    async def shutdown(self) -> None:
        await self._checkpoint_store.close()

    async def create_session(
        self,
        user_sub: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, str]:
        return await self._sqlite_store.create_session(
            user_sub=user_sub,
            user_email=user_email,
        )

    async def require_session(
        self,
        session_id: str,
        user_sub: str | None = None,
    ) -> bool:
        return await self._sqlite_store.session_exists(session_id, user_sub=user_sub)

    async def add_user_message(self, session_id: str, content: str) -> None:
        await self._sqlite_store.append_message(session_id, "user", content)

    async def add_assistant_message(self, session_id: str, content: str) -> None:
        await self._sqlite_store.append_message(session_id, "assistant", content)

    async def get_history(self, session_id: str) -> list[dict[str, Any]]:
        return await self._sqlite_store.get_messages(session_id)

    async def save_state(self, session_id: str, state: dict[str, Any]) -> None:
        await self._checkpoint_store.save_checkpoint(session_id, state)
        await self._sqlite_store.update_session_metadata(
            session_id,
            title=self._build_title(state),
            latest_status=self._build_latest_status(state),
            latest_verdict=self._build_latest_verdict(state),
        )

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

    async def list_sessions(
        self,
        limit: int = 20,
        cursor: str | None = None,
        user_sub: str | None = None,
    ) -> dict[str, Any]:
        return await self._sqlite_store.list_sessions(
            limit=limit,
            cursor=cursor,
            user_sub=user_sub,
        )

    @property
    def evidence_store(self) -> SQLiteEvidenceStore:
        return self._evidence_store

    def _build_title(self, state: dict[str, Any]) -> str | None:
        existing = str(state.get("title") or "").strip()
        if existing:
            return existing[:140]
        constraints = dict(state.get("constraints") or {})
        category = str(constraints.get("category") or "").strip()
        budget = constraints.get("budgetMax")
        rating = constraints.get("minRating")
        deadline = str(constraints.get("deliveryDeadline") or "").strip()
        parts = [category]
        if budget not in (None, ""):
            parts.append(f"under ${budget}")
        if rating not in (None, ""):
            parts.append(f"{rating}+ stars")
        if deadline:
            parts.append(f"by {deadline}")
        title = ", ".join(item for item in parts if item)
        if title:
            return title[:140]
        user_message = str(state.get("user_message") or "").strip()
        return user_message[:140] if user_message else None

    def _build_latest_status(self, state: dict[str, Any]) -> str | None:
        decision = dict((state.get("agent_outputs") or {}).get("decision") or {})
        return str(decision.get("status") or state.get("status") or "").strip() or None

    def _build_latest_verdict(self, state: dict[str, Any]) -> str | None:
        decision = dict((state.get("agent_outputs") or {}).get("decision") or {})
        decision_payload = dict(decision.get("decision") or {})
        verdict = str(decision_payload.get("verdict") or "").strip()
        return verdict or None
