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
    conversation_mode: str
    conversation_intent: str
    reply_kind: str
    handled_by: str
    next_actions: list[dict[str, Any]]
    pending_action: dict[str, Any] | None
    support_level: str
    force_collect: bool
    domain: str
    action_history: dict[str, dict[str, Any]]
    clarification_pending: dict[str, Any] | None
    clarification_asked_count: int
    search_ready: bool
    source_health: dict[str, Any]
    crawl_meta: dict[str, Any]
    coverage_confidence: str
    checkout_readiness: str
    score_breakdown: dict[str, Any]
    decision_summary: str
    decision_diagnostics: dict[str, Any]
    evidence_diagnostics: dict[str, Any]
