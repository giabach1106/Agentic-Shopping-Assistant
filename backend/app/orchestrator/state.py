from __future__ import annotations

from typing import Any, TypedDict


class ShoppingState(TypedDict, total=False):
    session_id: str
    user_message: str
    history: list[dict[str, Any]]
    constraints: dict[str, Any]
    agent_outputs: dict[str, Any]
    needs_follow_up: bool
    reply: str

