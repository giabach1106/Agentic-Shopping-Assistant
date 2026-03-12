from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

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
    format_decision_reply,
    format_follow_up_reply,
    format_need_data_reply,
)
from app.orchestrator.state import ShoppingState


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
    state: dict[str, Any]


class AgentOrchestrator:
    def __init__(
        self,
        planner: PlannerAgent,
        coverage_audit: CoverageAuditorAgent,
        collect: EvidenceCollectionAgent,
        review: ReviewIntelligenceAgent,
        visual: VisualVerificationAgent,
        price: PriceLogisticsAgent,
        decision: DecisionAgent,
    ) -> None:
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
            "agent_outputs": {},
            "follow_up_count": int(previous_state.get("follow_up_count", 0)),
            "needs_follow_up": False,
            "status": "OK",
            "missing_evidence": [],
            "blocking_agents": [],
            "reply": "",
        }
        final_state = await self._graph.ainvoke(initial_state)
        decision_payload = (
            final_state.get("agent_outputs", {})
            .get("decision", {})
        )
        status = str(
            decision_payload.get("status")
            or final_state.get("status")
            or "OK"
        )
        missing = (
            decision_payload.get("missingEvidence")
            if isinstance(decision_payload, dict)
            else []
        )
        if not missing:
            missing = final_state.get("missing_evidence", [])
        blocking = (
            decision_payload.get("blockingAgents")
            if isinstance(decision_payload, dict)
            else []
        )
        if not blocking:
            blocking = final_state.get("blocking_agents", [])
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
            state=dict(final_state),
        )

    def _build_graph(self):
        graph = StateGraph(ShoppingState)
        graph.add_node("planner", self._planner_node)
        graph.add_node("coverage_audit", self._coverage_audit_node)
        graph.add_node("collect", self._collect_node)
        graph.add_node("review", self._review_node)
        graph.add_node("visual", self._visual_node)
        graph.add_node("price", self._price_node)
        graph.add_node("decision", self._decision_node)

        graph.add_edge(START, "planner")
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
    def _route_after_planner(state: ShoppingState) -> str:
        if state.get("needs_follow_up", False):
            return "follow_up"
        return "continue"

    @staticmethod
    def _route_after_coverage_audit(state: ShoppingState) -> str:
        audit = dict((state.get("agent_outputs") or {}).get("coverage_audit") or {})
        sufficiency = dict(audit.get("sufficiency") or {})
        if sufficiency.get("isSufficient"):
            return "review"
        return "collect"

    async def _planner_node(self, state: ShoppingState) -> dict[str, Any]:
        planner_output = await self._planner.run(
            message=state["user_message"],
            history=state.get("history", []),
            existing_constraints=state.get("constraints", {}),
            follow_up_count=state.get("follow_up_count", 0),
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
        }

    async def _coverage_audit_node(self, state: ShoppingState) -> dict[str, Any]:
        audit_output = await self._coverage_audit.run(state.get("constraints", {}))
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["coverage_audit"] = audit_output
        updated_outputs["collect"] = {
            "status": audit_output.get("status", "OK"),
            "sourceCoverage": audit_output.get("sourceCoverage", 0),
            "reviewCount": audit_output.get("reviewCount", 0),
            "ratingCount": audit_output.get("ratingCount", 0),
            "freshnessSeconds": audit_output.get("freshnessSeconds", 999999),
            "missingEvidence": list(
                (audit_output.get("sufficiency") or {}).get("missing", [])
            ),
            "blockedSources": [],
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
                "reviewCount": audit_output.get("reviewCount", 0),
                "ratingCount": audit_output.get("ratingCount", 0),
                "freshnessSeconds": audit_output.get("freshnessSeconds", 999999),
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
        )
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["collect"] = collect_output
        return {
            "agent_outputs": updated_outputs,
            "collection": collect_output.get("collection", {}),
            "status": collect_output.get("status", "OK"),
            "missing_evidence": collect_output.get("missingEvidence", []),
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

        if decision_output.get("status") == "NEED_DATA":
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

        return {
            "agent_outputs": updated_outputs,
            "status": decision_output.get("status", "OK"),
            "missing_evidence": decision_output.get("missingEvidence", []),
            "blocking_agents": decision_output.get("blockingAgents", []),
            "reply": reply,
        }
