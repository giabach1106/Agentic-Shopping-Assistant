from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.stubs import (
    DecisionAgent,
    PlannerAgent,
    PriceLogisticsAgent,
    ReviewIntelligenceAgent,
    VisualVerificationAgent,
)
from app.orchestrator.state import ShoppingState


@dataclass(slots=True)
class OrchestratorResult:
    reply: str
    state: dict[str, Any]


class AgentOrchestrator:
    def __init__(
        self,
        planner: PlannerAgent,
        review: ReviewIntelligenceAgent,
        visual: VisualVerificationAgent,
        price: PriceLogisticsAgent,
        decision: DecisionAgent,
    ) -> None:
        self._planner = planner
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
            "agent_outputs": {},
            "follow_up_count": int(previous_state.get("follow_up_count", 0)),
            "needs_follow_up": False,
            "reply": "",
        }
        final_state = await self._graph.ainvoke(initial_state)
        return OrchestratorResult(reply=final_state["reply"], state=dict(final_state))

    def _build_graph(self):
        graph = StateGraph(ShoppingState)
        graph.add_node("planner", self._planner_node)
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
                "continue": "review",
            },
        )
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
            planner_output["followUpQuestion"]
            if needs_follow_up
            else "Great, I have enough constraints. Running analysis now."
        )
        return {
            "constraints": planner_output["constraints"],
            "agent_outputs": updated_outputs,
            "follow_up_count": planner_output["followUpCount"],
            "needs_follow_up": needs_follow_up,
            "reply": reply,
        }

    async def _review_node(self, state: ShoppingState) -> dict[str, Any]:
        review_output = await self._review.run(
            state.get("constraints", {}),
            session_id=state["session_id"],
        )
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["review"] = review_output
        return {"agent_outputs": updated_outputs}

    async def _visual_node(self, state: ShoppingState) -> dict[str, Any]:
        visual_output = await self._visual.run(
            state.get("constraints", {}),
            session_id=state["session_id"],
        )
        updated_outputs = dict(state.get("agent_outputs", {}))
        updated_outputs["visual"] = visual_output
        return {"agent_outputs": updated_outputs}

    async def _price_node(self, state: ShoppingState) -> dict[str, Any]:
        price_output = await self._price.run(
            state.get("constraints", {}),
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

        recommendation = (
            f"Verdict: {decision_output['verdict']} | "
            f"Trust Score: {decision_output['trustScore']}. "
            "Top reason: "
            f"{decision_output['topReasons'][0]}"
        )
        return {"agent_outputs": updated_outputs, "reply": recommendation}
