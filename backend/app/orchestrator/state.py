from __future__ import annotations

from typing import Any, TypedDict


class ShoppingState(TypedDict):
    session_id: str
    user_message: str
    history: list[dict[str, Any]]
    constraints: dict[str, Any]
    collection: dict[str, Any]
    agent_outputs: dict[str, Any]
    follow_up_count: int
    needs_follow_up: bool
    status: str
    missing_evidence: list[str]
    blocking_agents: list[str]
    reply: str
