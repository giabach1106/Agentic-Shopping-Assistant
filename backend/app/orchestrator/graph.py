from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.concierge import ConciergeAgent
from app.agents.stubs import (
    CoverageAuditorAgent,
    DecisionAgent,
    EvidenceCollectionAgent,
    PlannerAgent,
    PriceLogisticsAgent,
    ReviewIntelligenceAgent,
    VisualVerificationAgent,
)
from app.orchestrator.message_formatter import (
    format_blocked_status_reply,
    format_confirmation_reply,
    format_decision_reply,
    format_follow_up_reply,
    format_need_data_reply,
)
from app.orchestrator.state import ShoppingState
from app.memory.evidence_store import constraint_fingerprint


def _action_history_key(action_type: str, constraints: dict[str, Any]) -> str:
    return f"{action_type}:{constraint_fingerprint(constraints)}"


@dataclass(slots=True)
class OrchestratorResult:
    status: str
    reply: str
    decision: dict[str, Any] | None
    scientific_score: dict[str, Any]
    evidence_stats: dict[str, Any]
    coverage_audit: dict[str, Any]
    trace: list[dict[str, Any]]
    missing_evidence: list[str]
    blocking_agents: list[str]
    conversation_mode: str
    conversation_intent: str
    reply_kind: str
    handled_by: str
    support_level: str
    next_actions: list[dict[str, Any]]
    pending_action: dict[str, Any] | None
    coverage_confidence: str
    checkout_readiness: str
    clarification_pending: dict[str, Any] | None
    source_health: dict[str, Any]
    state: dict[str, Any]


class AgentOrchestrator:
    def __init__(
        self,
        concierge: ConciergeAgent,
        planner: PlannerAgent,
        coverage_audit: CoverageAuditorAgent,
        collect: EvidenceCollectionAgent,
        review: ReviewIntelligenceAgent,
        visual: VisualVerificationAgent,
        price: PriceLogisticsAgent,
        decision: DecisionAgent,
    ) -> None:
        self._concierge = concierge
        self._planner = planner
        self._coverage_audit = coverage_audit
        self._collect = collect
        self._review = review
        self._visual = visual
        self._price = price
        self._decision = decision
        self._graph = self._build_graph()

    async def run_turn(
        self,
        session_id: str,
        user_message: str,
        history: list[dict[str, Any]],
        previous_state: dict[str, Any] | None = None,
    ) -> OrchestratorResult:
        previous_state = previous_state or {}
        initial_state: ShoppingState = {
            "session_id": session_id,
            "user_message": user_message,
            "history": history,
            "constraints": previous_state.get("constraints", {}),
            "collection": previous_state.get("collection", {}),
            "agent_outputs": previous_state.get("agent_outputs", {}),
            "follow_up_count": int(previous_state.get("follow_up_count", 0)),
            "needs_follow_up": bool(previous_state.get("needs_follow_up", False)),
            "status": str(previous_state.get("status") or "OK"),
            "missing_evidence": list(previous_state.get("missing_evidence", [])),
            "blocking_agents": list(previous_state.get("blocking_agents", [])),
            "reply": str(previous_state.get("reply") or ""),
            "conversation_mode": str(previous_state.get("conversation_mode") or "concierge"),
            "conversation_intent": str(previous_state.get("conversation_intent") or "unknown"),
            "reply_kind": str(previous_state.get("reply_kind") or "answer"),
            "handled_by": str(previous_state.get("handled_by") or "concierge"),
            "next_actions": list(previous_state.get("next_actions", [])),
            "pending_action": previous_state.get("pending_action"),
            "support_level": str(previous_state.get("support_level") or "unsupported"),
            "force_collect": bool(previous_state.get("force_collect", False)),
            "domain": str(previous_state.get("domain") or "generic"),
            "action_history": dict(previous_state.get("action_history") or {}),
            "clarification_pending": previous_state.get("clarification_pending"),
            "clarification_asked_count": int(previous_state.get("clarification_asked_count", 0)),
            "search_ready": bool(previous_state.get("search_ready", False)),
            "source_health": dict(previous_state.get("source_health") or {}),
            "crawl_meta": dict(previous_state.get("crawl_meta") or {}),
            "coverage_confidence": str(previous_state.get("coverage_confidence") or "weak"),
            "checkout_readiness": str(previous_state.get("checkout_readiness") or "unknown"),
        }
        final_state = await self._graph.ainvoke(initial_state)
        decision_payload = (
            final_state.get("agent_outputs", {})
            .get("decision", {})
        )
        status = str(
            final_state.get("status")
            or decision_payload.get("status")
            or "OK"
        )
        missing = list(final_state.get("missing_evidence", []) or [])
        if not missing and isinstance(decision_payload, dict):
            missing = list(decision_payload.get("missingEvidence") or [])
        blocking = list(final_state.get("blocking_agents", []) or [])
        if not blocking and isinstance(decision_payload, dict):
            blocking = list(decision_payload.get("blockingAgents") or [])
        return OrchestratorResult(
            status=status,
            reply=final_state["reply"],
            decision=decision_payload.get("decision"),
            scientific_score=decision_payload.get("scientificScore", {}),
            evidence_stats=decision_payload.get("evidenceStats", {}),
            coverage_audit=decision_payload.get("coverageAudit", {}),
            trace=decision_payload.get("trace", []),
            missing_evidence=list(missing or []),
            blocking_agents=list(blocking or []),
            conversation_mode=str(final_state.get("conversation_mode") or "concierge"),
            conversation_intent=str(final_state.get("conversation_intent") or "unknown"),
            reply_kind=str(final_state.get("reply_kind") or "answer"),
            handled_by=str(final_state.get("handled_by") or "concierge"),
            support_level=str(final_state.get("support_level") or "unsupported"),
            next_actions=list(final_state.get("next_actions", [])),
            pending_action=final_state.get("pending_action"),
            coverage_confidence=str(decision_payload.get("coverageConfidence") or "weak"),
            checkout_readiness=str(decision_payload.get("checkoutReadiness") or "unknown"),
            clarification_pending=final_state.get("clarification_pending"),
            source_health=dict(final_state.get("source_health") or {}),
            state=dict(final_state),
        )

    def _build_graph(self):
        graph = StateGraph(ShoppingState)
        graph.add_node("concierge", self._concierge_node)
        graph.add_node("planner", self._planner_node)
        graph.add_node("coverage_audit", self._coverage_audit_node)
        graph.add_node("collect", self._collect_node)
        graph.add_node("review", self._review_node)
        graph.add_node("visual", self._visual_node)
        graph.add_node("price", self._price_node)
        graph.add_node("decision", self._decision_node)

        graph.add_edge(START, "concierge")
        graph.add_conditional_edges(
            "concierge",
            self._route_after_concierge,
            {
                "respond_only": END,
                "ask_discovery": END,
                "ask_confirmation": END,
                "continue_planner": "planner",
                "continue_analysis": "coverage_audit",
            },
        )
        graph.add_conditional_edges(
            "planner",
            self._route_after_planner,
            {
                "follow_up": END,
                "continue": "coverage_audit",
            },
        )
        graph.add_conditional_edges(
            "coverage_audit",
            self._route_after_coverage_audit,
            {
                "collect": "collect",
                "review": "review",
            },
        )
        graph.add_edge("collect", "review")
        graph.add_edge("review", "visual")
        graph.add_edge("visual", "price")
        graph.add_edge("price", "decision")
        graph.add_edge("decision", END)
        return graph.compile()

    @staticmethod
    def _route_after_concierge(state: ShoppingState) -> str:
        return str((state.get("agent_outputs") or {}).get("concierge_route") or "respond_only")

    @staticmethod
    def _route_after_planner(state: ShoppingState) -> str:
        if state.get("needs_follow_up", False):
            return "follow_up"
        return "continue"

    @staticmethod
    def _route_after_coverage_audit(state: ShoppingState) -> str:
        if state.get("force_collect"):
            return "collect"
        audit = dict((state.get("agent_outputs") or {}).get("coverage_audit") or {})
        sufficiency = dict(audit.get("sufficiency") or {})
        if sufficiency.get("isSufficient"):
            return "review"
        return "collect"

    async def _concierge_node(self, state: ShoppingState) -> dict[str, Any]:
        previous_state = {
            "constraints": state.get("constraints", {}),
            "collection": state.get("collection", {}),
            "agent_outputs": state.get("agent_outputs", {}),
            "needs_follow_up": state.get("needs_follow_up", False),
            "status": state.get("status", "OK"),
            "missing_evidence": state.get("missing_evidence", []),
            "blocking_agents": state.get("blocking_agents", []),
            "pending_action": state.get("pending_action"),
            "domain": state.get("domain"),
            "support_level": state.get("support_level"),
            "conversation_mode": state.get("conversation_mode"),
            "action_history": state.get("action_history", {}),
            "clarification_pending": state.get("clarification_pending"),
            "clarification_asked_count": state.get("clarification_asked_count", 0),
            "search_ready": state.get("search_ready", False),
        }
        concierge_output = await self._concierge.run(
            message=state["user_message"],
            history=state.get("history", []),
            previous_state=previous_state,
            session_id=state["session_id"],
        )
        route = str(concierge_output.get("route") or "respond_only")
        next_constraints = dict(concierge_output.get("constraints") or state.get("constraints", {}))
        action_history = dict(state.get("action_history", {}))
        confirmed_action_type = str(concierge_output.get("confirmedActionType") or "").strip()
        if confirmed_action_type:
            history_key = _action_history_key(confirmed_action_type, next_constraints)
            record = dict(action_history.get(history_key) or {})
            action_history[history_key] = {
                "status": "confirmed",
                "count": int(record.get("count") or 0) + 1,
            }
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["concierge"] = {
            "intent": concierge_output.get("conversationIntent"),
            "supportLevel": concierge_output.get("supportLevel"),
        }
        updated_outputs["concierge_route"] = route
        if route in {"continue_planner", "continue_analysis"}:
            updated_outputs = {"concierge": updated_outputs["concierge"], "concierge_route": route}
        return {
            "constraints": next_constraints,
            "agent_outputs": updated_outputs,
            "needs_follow_up": bool(concierge_output.get("needsFollowUp", False)),
            "status": str(concierge_output.get("status") or "OK"),
            "missing_evidence": list(concierge_output.get("missingEvidence", state.get("missing_evidence", []))),
            "blocking_agents": list(concierge_output.get("blockingAgents", state.get("blocking_agents", []))),
            "reply": str(concierge_output.get("reply") or ""),
            "conversation_mode": str(concierge_output.get("conversationMode") or "concierge"),
            "conversation_intent": str(concierge_output.get("conversationIntent") or "unknown"),
            "reply_kind": str(concierge_output.get("replyKind") or "answer"),
            "handled_by": str(concierge_output.get("handledBy") or "concierge"),
            "next_actions": list(concierge_output.get("nextActions", [])),
            "pending_action": concierge_output.get("pendingAction"),
            "support_level": str(concierge_output.get("supportLevel") or "unsupported"),
            "force_collect": bool(concierge_output.get("forceCollect", False)),
            "domain": str(concierge_output.get("domain") or state.get("domain") or "generic"),
            "action_history": action_history,
            "clarification_pending": state.get("clarification_pending"),
            "clarification_asked_count": int(state.get("clarification_asked_count", 0)),
            "search_ready": bool(state.get("search_ready", False)),
            "source_health": dict(state.get("source_health") or {}),
            "crawl_meta": dict(state.get("crawl_meta") or {}),
        }

    async def _planner_node(self, state: ShoppingState) -> dict[str, Any]:
        planner_output = await self._planner.run(
            message=state["user_message"],
            history=state.get("history", []),
            existing_constraints=state.get("constraints", {}),
            follow_up_count=state.get("follow_up_count", 0),
            clarification_asked_count=state.get("clarification_asked_count", 0),
            session_id=state["session_id"],
        )

        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["planner"] = planner_output
        needs_follow_up = planner_output["needsFollowUp"]
        reply = (
            format_follow_up_reply(
                planner_output["followUpQuestion"],
                planner_output["missingFields"],
            )
            if needs_follow_up
            else "Great, I have enough constraints. Running analysis now."
        )
        return {
            "constraints": planner_output["constraints"],
            "agent_outputs": updated_outputs,
            "follow_up_count": planner_output["followUpCount"],
            "needs_follow_up": needs_follow_up,
            "status": "NEED_DATA" if needs_follow_up else "OK",
            "missing_evidence": [
                f"planner.{item}" for item in planner_output["missingFields"]
            ]
            if needs_follow_up
            else [],
            "blocking_agents": ["planner"] if needs_follow_up else [],
            "reply": reply,
            "conversation_mode": "shopping_analysis",
            "conversation_intent": "shopping_constraints",
            "reply_kind": "discovery" if needs_follow_up else "status_update",
            "handled_by": "planner",
            "next_actions": [] if needs_follow_up else list(planner_output.get("clarificationActions", [])),
            "pending_action": None,
            "clarification_pending": planner_output.get("clarificationPending"),
            "clarification_asked_count": int(planner_output.get("clarificationAskedCount", 0)),
            "search_ready": bool(planner_output.get("searchReady", False)),
            "crawl_meta": {
                **dict(state.get("crawl_meta") or {}),
                "searchBrief": dict(planner_output.get("searchBrief") or {}),
            },
        }

    async def _coverage_audit_node(self, state: ShoppingState) -> dict[str, Any]:
        audit_output = await self._coverage_audit.run(state.get("constraints", {}))
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["coverage_audit"] = audit_output
        updated_outputs["collect"] = {
            "status": audit_output.get("status", "OK"),
            "sourceCoverage": audit_output.get("sourceCoverage", 0),
            "commerceSourceCoverage": audit_output.get("commerceSourceCoverage", 0),
            "reviewCount": audit_output.get("reviewCount", 0),
            "ratingCount": audit_output.get("ratingCount", 0),
            "ratedCandidateCount": audit_output.get("ratedCandidateCount", 0),
            "ratedCoverageRatio": audit_output.get("ratedCoverageRatio", 0.0),
            "freshnessSeconds": audit_output.get("freshnessSeconds", 999999),
            "missingEvidence": list(
                (audit_output.get("sufficiency") or {}).get("missing", [])
            ),
            "blockedSources": list(audit_output.get("collection", {}).get("blockedSources", [])),
            "blockedCommerceSources": list(audit_output.get("blockedCommerceSources", [])),
            "collection": dict(audit_output.get("collection", {})),
            "cacheStatus": audit_output.get("cacheStatus"),
            "catalogStatus": audit_output.get("catalogStatus"),
            "crawlPerformed": False,
            "sufficiency": audit_output.get("sufficiency", {}),
            "coverageAudit": {
                "isSufficient": bool(
                    (audit_output.get("sufficiency") or {}).get("isSufficient")
                ),
                "missing": list(
                    (audit_output.get("sufficiency") or {}).get("missing", [])
                ),
                "sourceCoverage": audit_output.get("sourceCoverage", 0),
                "commerceSourceCoverage": audit_output.get("commerceSourceCoverage", 0),
                "reviewCount": audit_output.get("reviewCount", 0),
                "ratingCount": audit_output.get("ratingCount", 0),
                "ratedCandidateCount": audit_output.get("ratedCandidateCount", 0),
                "ratedCoverageRatio": audit_output.get("ratedCoverageRatio", 0.0),
                "freshnessSeconds": audit_output.get("freshnessSeconds", 999999),
                "blockedCommerceSources": list(audit_output.get("blockedCommerceSources", [])),
                "cacheStatus": audit_output.get("cacheStatus"),
                "catalogStatus": audit_output.get("catalogStatus"),
                "crawlPerformed": False,
            },
        }
        return {
            "agent_outputs": updated_outputs,
            "collection": dict(audit_output.get("collection", {})),
            "status": audit_output.get("status", "OK"),
            "missing_evidence": list(
                (audit_output.get("sufficiency") or {}).get("missing", [])
            ),
            "conversation_mode": "shopping_analysis",
            "conversation_intent": str(state.get("conversation_intent") or "shopping_constraints"),
            "reply_kind": str(state.get("reply_kind") or "status_update"),
            "handled_by": str(state.get("handled_by") or "planner"),
            "clarification_pending": state.get("clarification_pending"),
            "clarification_asked_count": int(state.get("clarification_asked_count", 0)),
            "search_ready": bool(state.get("search_ready", False)),
            "crawl_meta": dict((audit_output.get("collection") or {}).get("crawlMeta") or state.get("crawl_meta") or {}),
        }

    async def _review_node(self, state: ShoppingState) -> dict[str, Any]:
        review_output = await self._review.run(
            state.get("constraints", {}),
            state.get("collection", {}),
            session_id=state["session_id"],
        )
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["review"] = review_output
        return {"agent_outputs": updated_outputs}

    async def _collect_node(self, state: ShoppingState) -> dict[str, Any]:
        collect_output = await self._collect.run(
            state.get("constraints", {}),
            seed_collection=state.get("collection", {}),
            coverage_audit=(state.get("agent_outputs", {}) or {}).get("coverage_audit"),
            force_collect=bool(state.get("force_collect", False)),
        )
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["collect"] = collect_output
        return {
            "agent_outputs": updated_outputs,
            "collection": collect_output.get("collection", {}),
            "status": collect_output.get("status", "OK"),
            "missing_evidence": collect_output.get("missingEvidence", []),
            "force_collect": False,
            "source_health": dict(collect_output.get("sourceHealth") or {}),
            "crawl_meta": dict(collect_output.get("crawlMeta") or state.get("crawl_meta") or {}),
        }

    async def _visual_node(self, state: ShoppingState) -> dict[str, Any]:
        visual_output = await self._visual.run(
            state.get("constraints", {}),
            state.get("collection", {}),
            session_id=state["session_id"],
        )
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["visual"] = visual_output
        return {"agent_outputs": updated_outputs}

    async def _price_node(self, state: ShoppingState) -> dict[str, Any]:
        price_output = await self._price.run(
            state.get("constraints", {}),
            state.get("collection", {}),
            session_id=state["session_id"],
        )
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["price"] = price_output
        return {"agent_outputs": updated_outputs}

    async def _decision_node(self, state: ShoppingState) -> dict[str, Any]:
        decision_output = await self._decision.run(
            state.get("agent_outputs", {}),
            constraints=state.get("constraints", {}),
            session_id=state["session_id"],
        )
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["decision"] = decision_output
        pending_action = self._build_pending_action_from_need_data(state, decision_output)
        prior_crawl_attempt = self._has_confirmed_action(
            state,
            action_type="crawl_more",
            constraints=state.get("constraints", {}),
        )

        if decision_output.get("status") == "NEED_DATA":
            if pending_action is not None:
                reply = format_confirmation_reply(str(pending_action.get("prompt") or ""))
            elif prior_crawl_attempt:
                reply = format_blocked_status_reply(
                    missing_evidence=list(decision_output.get("missingEvidence", [])),
                    blocking_agents=list(decision_output.get("blockingAgents", [])),
                    coverage_audit=dict(decision_output.get("coverageAudit", {})),
                    evidence_stats=dict(decision_output.get("evidenceStats", {})),
                )
            else:
                reply = format_need_data_reply(
                    decision_output.get("missingEvidence", []),
                    decision_output.get("blockingAgents", []),
                )
        else:
            decision = decision_output.get("decision", {})
            reply = format_decision_reply(
                decision=decision,
                scientific_score=decision_output.get("scientificScore", {}),
            )
        clarification_pending = state.get("clarification_pending")
        if (
            isinstance(clarification_pending, dict)
            and str(clarification_pending.get("prompt") or "").strip()
            and pending_action is None
        ):
            reply = (
                f"{reply} {str(clarification_pending.get('prompt')).strip()}"
                if reply
                else str(clarification_pending.get("prompt")).strip()
            )

        return {
            "agent_outputs": updated_outputs,
            "status": decision_output.get("status", "OK"),
            "missing_evidence": decision_output.get("missingEvidence", []),
            "blocking_agents": decision_output.get("blockingAgents", []),
            "reply": reply,
            "needs_follow_up": decision_output.get("status") == "NEED_DATA",
            "conversation_mode": "shopping_analysis",
            "conversation_intent": str(state.get("conversation_intent") or "shopping_constraints"),
            "reply_kind": (
                "confirmation_request"
                if decision_output.get("status") == "NEED_DATA"
                and pending_action is not None
                else ("status_update" if decision_output.get("status") == "NEED_DATA" else "analysis_result")
            ),
            "handled_by": "decision",
            "next_actions": self._build_next_actions_from_decision(state, decision_output),
            "pending_action": pending_action,
            "clarification_pending": clarification_pending,
            "search_ready": bool(state.get("search_ready", False)),
            "source_health": dict(decision_output.get("sourceHealth") or state.get("source_health") or {}),
            "crawl_meta": dict(state.get("crawl_meta") or {}),
            "coverage_confidence": str(decision_output.get("coverageConfidence") or "weak"),
            "checkout_readiness": str(decision_output.get("checkoutReadiness") or "unknown"),
        }

    def _has_confirmed_action(
        self,
        state: ShoppingState,
        *,
        action_type: str,
        constraints: dict[str, Any],
    ) -> bool:
        history = state.get("action_history", {})
        if not isinstance(history, dict):
            return False
        record = history.get(_action_history_key(action_type, constraints))
        if not isinstance(record, dict):
            return False
        return str(record.get("status") or "").strip() == "confirmed" and int(record.get("count") or 0) > 0

    def _build_pending_action_from_need_data(
        self,
        state: ShoppingState,
        decision_output: dict[str, Any],
    ) -> dict[str, Any] | None:
        if state.get("force_collect"):
            return None
        missing = [str(item) for item in decision_output.get("missingEvidence", []) if str(item).strip()]
        blockers = [str(item) for item in decision_output.get("blockingAgents", []) if str(item).strip()]
        crawl_missing = {"sourceCoverage", "reviewCount", "ratingCount", "freshness"}
        if self._has_confirmed_action(
            state,
            action_type="crawl_more",
            constraints=state.get("constraints", {}),
        ):
            return None
        if crawl_missing.intersection(missing) or {"collect", "review"}.intersection(blockers):
            return {
                "type": "crawl_more",
                "status": "awaiting_user",
                "prompt": (
                    "I still need broader evidence before I can trust the result. "
                    "Do you want me to crawl for more product and review data now?"
                ),
                "expiresAfterTurn": 1,
            }
        return None

    def _build_next_actions_from_decision(
        self,
        state: ShoppingState,
        decision_output: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if decision_output.get("status") == "NEED_DATA":
            pending_action = self._build_pending_action_from_need_data(state, decision_output)
            if pending_action is not None:
                return [
                    {
                        "id": "crawl_more_yes",
                        "label": "Yes, crawl more",
                        "message": "Yes, do it.",
                        "kind": "confirm",
                        "style": "primary",
                        "requiresConfirmation": True,
                    },
                    {
                        "id": "crawl_more_no",
                        "label": "No, keep current state",
                        "message": "No, keep the current state.",
                        "kind": "cancel",
                        "style": "secondary",
                        "requiresConfirmation": False,
                    },
                ]
            actions = [
                {
                    "id": "crawl_again",
                    "label": "Request another crawl",
                    "message": "Please crawl for more data before continuing.",
                    "kind": "reply",
                    "style": "subtle",
                    "requiresConfirmation": False,
                },
                {
                    "id": "refine_constraints",
                    "label": "Refine constraints",
                    "message": "Refine the brief and continue the run.",
                    "kind": "reply",
                    "style": "secondary",
                    "requiresConfirmation": False,
                }
            ]
            clarification_pending = state.get("clarification_pending")
            if isinstance(clarification_pending, dict):
                prompt = str(clarification_pending.get("example") or "").strip()
                field = str(clarification_pending.get("field") or "brief")
                if prompt:
                    actions.insert(
                        0,
                        {
                            "id": f"clarify_{field}",
                            "label": "Add preference",
                            "message": prompt,
                            "kind": "reply",
                            "style": "subtle",
                            "requiresConfirmation": False,
                        },
                    )
            return actions
        clarification_pending = state.get("clarification_pending")
        if isinstance(clarification_pending, dict):
            return list((state.get("next_actions") or [])) or [
                {
                    "id": "clarify_optional",
                    "label": "Add preference",
                    "message": str(clarification_pending.get("example") or "Budget under $150."),
                    "kind": "reply",
                    "style": "secondary",
                    "requiresConfirmation": False,
                }
            ]
        return []
