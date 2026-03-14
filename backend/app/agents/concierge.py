from __future__ import annotations

import re
from typing import Any

from app.core.model_router import ModelRouter
from app.orchestrator.domain_support import (
    canonicalize_category,
    extract_category_from_message,
    has_structured_constraint_signal,
    infer_domain,
    is_shopping_message,
    support_level_for_domain,
)

_YES_PATTERN = re.compile(
    r"\b(yes|yep|yeah|sure|ok|okay|go ahead|continue|confirm|crawl it|do it|dong y|duoc)\b",
    re.IGNORECASE,
)
_NO_PATTERN = re.compile(
    r"\b(no|nope|cancel|stop|not now|skip|don't|do not|khong|khong can)\b",
    re.IGNORECASE,
)
_CAPABILITY_PATTERN = re.compile(
    r"(what can you help|what can you do|how can you help|help me with|ban co the giup|ban lam duoc gi)",
    re.IGNORECASE,
)
_PROJECT_PATTERN = re.compile(
    r"(tech stack|technology|technologies|stack|how are you built|how is this project built|"
    r"what does this project use|what is this project using|frontend|backend|fastapi|next\.?js|"
    r"langgraph|cognito|redis|sqlite)",
    re.IGNORECASE,
)
_STATUS_PATTERN = re.compile(
    r"(status|progress|update|what next|what now|pending|blocked|stuck|tiep theo|ke tiep)",
    re.IGNORECASE,
)
_RESUME_PATTERN = re.compile(
    r"^(continue|resume|go ahead|keep going|run it|proceed)$",
    re.IGNORECASE,
)
_CRAWL_PATTERN = re.compile(r"(crawl|fetch more|collect more|get more data|expand evidence)", re.IGNORECASE)
_AUTOFILL_PATTERN = re.compile(r"(autofill|fill checkout|fill the form|use my profile)", re.IGNORECASE)
_SMALL_TALK_PATTERN = re.compile(
    r"^(hi|hello|hey|yo|thanks|thank you|cam on|ok|okay)$",
    re.IGNORECASE,
)


class ConciergeAgent:
    def __init__(
        self,
        model_router: ModelRouter,
        project_profile: dict[str, Any],
    ) -> None:
        self._model_router = model_router
        self._project_profile = project_profile

    async def run(
        self,
        *,
        message: str,
        history: list[dict[str, Any]],
        previous_state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        previous_state = previous_state or {}

        constraints = dict(previous_state.get("constraints") or {})
        pending_action = self._normalize_pending_action(previous_state.get("pending_action"))
        existing_category = self._sanitize_category(str(constraints.get("category") or "").strip() or None)
        history_category = self._recent_user_category(history)
        category_hint = (
            self._sanitize_category(extract_category_from_message(message))
            or existing_category
            or history_category
        )
        if category_hint and not constraints.get("category"):
            constraints["category"] = canonicalize_category(category_hint)

        domain = infer_domain(category_hint or existing_category)
        support_level = self._support_level(domain, category_hint or existing_category)
        if constraints.get("category") and support_level != "live_analysis":
            constraints = self._apply_discovery_updates(message, constraints)
        search_ready = bool(previous_state.get("search_ready") or constraints.get("category"))
        clarification_pending = previous_state.get("clarification_pending")
        missing_evidence = [
            str(item).strip()
            for item in previous_state.get("missing_evidence", [])
            if str(item).strip()
        ]
        blocking_agents = [
            str(item).strip()
            for item in previous_state.get("blocking_agents", [])
            if str(item).strip()
        ]

        if pending_action:
            if _YES_PATTERN.search(message):
                return self._confirm_pending_action(
                    pending_action=pending_action,
                    constraints=constraints,
                    domain=domain,
                    support_level=support_level,
                )
            if _NO_PATTERN.search(message):
                return self._reject_pending_action(
                    pending_action=pending_action,
                    constraints=constraints,
                    domain=domain,
                    support_level=support_level,
                )

        intent = await self._classify_intent(
            message=message,
            existing_category=existing_category,
            history_category=history_category,
            pending_action=pending_action,
            missing_evidence=missing_evidence,
            search_ready=search_ready,
            clarification_pending=clarification_pending,
        )

        if _CRAWL_PATTERN.search(message) and any(not item.startswith("planner.") for item in missing_evidence):
            return self._ask_for_confirmation(
                action_type="crawl_more",
                prompt=(
                    "I can expand the evidence set before I continue. "
                    "Do you want me to crawl for more product and review data now?"
                ),
                constraints=constraints,
                domain=domain,
                support_level=support_level,
            )

        if _AUTOFILL_PATTERN.search(message) and not is_shopping_message(message):
            return self._ask_for_confirmation(
                action_type="enable_autofill",
                prompt=(
                    "I can enable checkout autofill for later store handoff, but I will still stop "
                    "before payment. Do you want me to enable that?"
                ),
                constraints=constraints,
                domain=domain,
                support_level=support_level,
            )

        if intent == "capability_query":
            return self._capability_response()
        if intent == "project_question":
            return self._project_response(message=message)
        if intent == "small_talk":
            return self._small_talk_response()
        if intent == "pending_status":
            return self._pending_status_response(
                constraints=constraints,
                pending_action=pending_action,
                missing_evidence=missing_evidence,
                blocking_agents=blocking_agents,
                domain=domain,
                support_level=support_level,
            )
        if intent == "resume_request":
            if previous_state.get("needs_follow_up") and any(
                item.startswith("planner.") for item in missing_evidence
            ):
                return self._discovery_response(
                    constraints=constraints,
                    domain=domain,
                    support_level=support_level,
                    explicit_follow_up=True,
                )
            if support_level == "live_analysis" and constraints.get("category"):
                return self._continue_analysis_response(
                    constraints=constraints,
                    domain=domain,
                    support_level=support_level,
                )
        if intent == "shopping_discovery":
            if support_level == "live_analysis" and constraints.get("category"):
                return self._continue_planner_response(
                    constraints=constraints,
                    domain=domain,
                    support_level=support_level,
                    conversation_intent="shopping_discovery",
                )
            return self._discovery_response(
                constraints=constraints,
                domain=domain,
                support_level=support_level,
                explicit_follow_up=False,
            )
        if intent == "shopping_constraints":
            if support_level != "live_analysis":
                return self._discovery_response(
                    constraints=constraints,
                    domain=domain,
                    support_level=support_level,
                    explicit_follow_up=True,
                    conversation_intent="shopping_constraints",
                )
            return self._continue_planner_response(
                constraints=constraints,
                domain=domain,
                support_level=support_level,
            )
        return self._fallback_response()

    async def _classify_intent(
        self,
        *,
        message: str,
        existing_category: str | None,
        history_category: str | None,
        pending_action: dict[str, Any] | None,
        missing_evidence: list[str],
        search_ready: bool,
        clarification_pending: dict[str, Any] | None,
    ) -> str:
        if pending_action:
            return "pending_status"
        if _CAPABILITY_PATTERN.search(message):
            return "capability_query"
        if _PROJECT_PATTERN.search(message):
            return "project_question"
        if _SMALL_TALK_PATTERN.search(message.strip()):
            return "small_talk"
        if _STATUS_PATTERN.search(message) and (missing_evidence or existing_category):
            return "pending_status"
        if _RESUME_PATTERN.fullmatch(message.strip()) and existing_category:
            return "resume_request"
        if (existing_category or history_category) and self._looks_like_shopping_follow_up(message):
            return "shopping_constraints"
        if search_ready and has_structured_constraint_signal(message):
            return "shopping_constraints"
        if clarification_pending and search_ready and existing_category:
            if has_structured_constraint_signal(message):
                return "shopping_constraints"
        if existing_category and has_structured_constraint_signal(message):
            return "shopping_constraints"
        if is_shopping_message(message):
            if has_structured_constraint_signal(message) or existing_category:
                return "shopping_constraints"
            return "shopping_discovery"

        model_guess = await self._classify_with_model(message)
        return model_guess or "unknown"

    async def _classify_with_model(self, message: str) -> str | None:
        try:
            result = await self._model_router.call(
                task_type="concierge_router",
                payload={
                    "prompt": (
                        "Classify this message into one label only: capability_query, project_question, "
                        "small_talk, shopping_discovery, shopping_constraints, pending_status, "
                        "action_confirmation, action_rejection, resume_request, unknown. "
                        f"Message: {message}"
                    )
                },
            )
        except Exception:  # noqa: BLE001
            return None
        text = str(result.output.get("text") or "").strip().lower()
        for label in (
            "capability_query",
            "project_question",
            "small_talk",
            "shopping_discovery",
            "shopping_constraints",
            "pending_status",
            "action_confirmation",
            "action_rejection",
            "resume_request",
            "unknown",
        ):
            if label in text:
                return label
        return None

    def _capability_response(self) -> dict[str, Any]:
        reply = (
            "I can help you turn a shopping idea into a structured search, compare current results, "
            "explain what is blocking a session, and answer repo-grounded questions about how this "
            "project is built."
        )
        return {
            "route": "respond_only",
            "reply": reply,
            "status": "OK",
            "needsFollowUp": False,
            "conversationMode": "concierge",
            "conversationIntent": "capability_query",
            "replyKind": "answer",
            "handledBy": "concierge",
            "nextActions": [
                _action("find_product", "Find a product", "I want help finding a product.", "reply", "primary"),
                _action("compare_results", "Compare results", "Compare the current results for me.", "continue", "secondary"),
                _action("explain_session", "Explain this session", "Explain this session and what is pending.", "reply", "secondary"),
                _action("project_stack", "Show project tech stack", "What tech stack does this project use?", "reply", "subtle"),
            ],
            "pendingAction": None,
            "supportLevel": "unsupported",
            "forceCollect": False,
            "domain": "generic",
        }

    def _project_response(self, *, message: str) -> dict[str, Any]:
        stack = "; ".join(self._project_profile.get("stack", [])[:3])
        capabilities = "; ".join(self._project_profile.get("coreCapabilities", [])[:4])
        runtime = dict(self._project_profile.get("runtime") or {})
        if re.search(r"(frontend|backend|stack|technology|technologies)", message, re.IGNORECASE):
            reply = (
                f"{self._project_profile['name']} uses {stack}. "
                f"Runtime mode is {runtime.get('runtimeMode')}, RAG backend is {runtime.get('ragBackend')}, "
                f"and UI executor backend is {runtime.get('uiExecutorBackend')}."
            )
        else:
            reply = (
                f"{self._project_profile['name']} is a session-based shopping assistant. "
                f"It currently supports {capabilities}. "
                f"Auth required: {runtime.get('requireAuth')}. Stop before pay: {runtime.get('stopBeforePay')}."
            )
        return {
            "route": "respond_only",
            "reply": reply,
            "status": "OK",
            "needsFollowUp": False,
            "conversationMode": "concierge",
            "conversationIntent": "project_question",
            "replyKind": "answer",
            "handledBy": "concierge",
            "nextActions": [
                _action("project_capabilities", "Show capabilities", "What can you help me with?", "reply", "secondary"),
                _action("shopping_start", "Start shopping", "I want help finding a product.", "reply", "primary"),
            ],
            "pendingAction": None,
            "supportLevel": "unsupported",
            "forceCollect": False,
            "domain": "generic",
        }

    def _small_talk_response(self) -> dict[str, Any]:
        return {
            "route": "respond_only",
            "reply": (
                "I can help. Tell me what you want to buy, or ask what this project can do and I will route you."
            ),
            "status": "OK",
            "needsFollowUp": False,
            "conversationMode": "concierge",
            "conversationIntent": "small_talk",
            "replyKind": "answer",
            "handledBy": "concierge",
            "nextActions": [
                _action("find_product", "Find a product", "I want help finding a product.", "reply", "primary"),
                _action("project_stack", "Project tech stack", "What tech stack does this project use?", "reply", "subtle"),
            ],
            "pendingAction": None,
            "supportLevel": "unsupported",
            "forceCollect": False,
            "domain": "generic",
        }

    def _pending_status_response(
        self,
        *,
        constraints: dict[str, Any],
        pending_action: dict[str, Any] | None,
        missing_evidence: list[str],
        blocking_agents: list[str],
        domain: str,
        support_level: str,
    ) -> dict[str, Any]:
        if pending_action:
            return {
                "route": "ask_confirmation",
                "reply": str(pending_action.get("prompt") or "I am waiting for your confirmation."),
                "status": "NEED_DATA",
                "needsFollowUp": True,
                "conversationMode": "concierge",
                "conversationIntent": "pending_status",
                "replyKind": "confirmation_request",
                "handledBy": "concierge",
                "nextActions": [
                    _action("confirm_action", "Yes, continue", "Yes, do it.", "confirm", "primary", True),
                    _action("cancel_action", "No, keep current state", "No, keep the current state.", "cancel", "secondary"),
                ],
                "pendingAction": pending_action,
                "supportLevel": support_level,
                "forceCollect": False,
                "domain": domain,
                "constraints": constraints,
            }

        if missing_evidence or blocking_agents:
            reply = (
                "The current session is still blocked. "
                f"Missing evidence: {', '.join(missing_evidence[:4]) or 'none listed'}. "
                f"Blocking agents: {', '.join(blocking_agents[:3]) or 'none listed'}."
            )
            next_actions = [
                _action("refine_brief", "Refine constraints", "Refine the brief and continue the run.", "reply", "secondary"),
            ]
            if support_level == "live_analysis":
                next_actions.insert(
                    0,
                    _action("crawl_more", "Crawl more data", "Please crawl for more data before continuing.", "reply", "primary"),
                )
            return {
                "route": "respond_only",
                "reply": reply,
                "status": "OK",
                "needsFollowUp": False,
                "conversationMode": "concierge",
                "conversationIntent": "pending_status",
                "replyKind": "status_update",
                "handledBy": "concierge",
                "nextActions": next_actions,
                "pendingAction": None,
                "supportLevel": support_level,
                "forceCollect": False,
                "domain": domain,
                "constraints": constraints,
            }

        return self._fallback_response()

    def _discovery_response(
        self,
        *,
        constraints: dict[str, Any],
        domain: str,
        support_level: str,
        explicit_follow_up: bool,
        conversation_intent: str = "shopping_discovery",
    ) -> dict[str, Any]:
        category = str(constraints.get("category") or "that product").strip()
        brief_summary = self._discovery_brief_summary(constraints)
        if domain == "chair":
            reply = (
                f"I can narrow down {category}. Before I search, tell me your budget and one or two priorities "
                "like ergonomics, mesh vs cushion, armrests, or delivery window."
            )
            actions = [
                _action("chair_budget", "Budget under $150", "Budget under $150.", "reply", "primary"),
                _action("chair_ergonomic", "Need lumbar support", "Must have lumbar support and adjustable armrests.", "reply", "secondary"),
                _action("chair_delivery", "Need it this week", "Delivery this week.", "reply", "secondary"),
            ]
        elif domain == "desk":
            reply = (
                f"I can help narrow down {category}. Before I search, tell me your budget and one or two priorities "
                "like width, storage, material, standing vs fixed height, or delivery window."
            )
            actions = [
                _action("desk_budget", "Budget under $200", "Budget under $200.", "reply", "primary"),
                _action("desk_size", "Need under 55 inches", "Need a desk under 55 inches wide.", "reply", "secondary"),
                _action("desk_storage", "Need shelves or drawers", "Prefer shelves or drawers for storage.", "reply", "secondary"),
            ]
        elif domain == "supplement":
            reply = (
                f"I can help search {category}. Before I run analysis, tell me your budget and one or two priorities "
                "like protein type, ingredient preferences, rating floor, or delivery window."
            )
            actions = [
                _action("supp_budget", "Budget under $80", "Budget under $80.", "reply", "primary"),
                _action("supp_rating", "Need 4.5+ stars", "Minimum rating 4.5 stars.", "reply", "secondary"),
                _action("supp_ingredients", "Need clean ingredients", "Must have clean ingredients and no sucralose.", "reply", "secondary"),
            ]
        else:
            if brief_summary:
                reply = (
                    f"I am structuring the brief for {category}. So far I have {brief_summary}. "
                    "Live evidence comparison is not ready for this category yet, but I can keep refining the brief."
                )
            else:
                reply = (
                    f"I can help you refine {category}, but live evidence comparison is only ready for supplements, "
                    "chairs, and desks right now. Tell me your budget and your top priorities, and I will structure the brief."
                )
            actions = [
                _action("generic_budget", "Share budget", "Budget under $200.", "reply", "primary"),
                _action("generic_use_case", "Share use case", "Main use case: daily study and home office.", "reply", "secondary"),
                _action("generic_delivery", "Share delivery window", "Need delivery this week.", "reply", "secondary"),
            ]

        if explicit_follow_up:
            if brief_summary and domain not in {"chair", "desk", "supplement"}:
                reply = "I captured that update. " + reply
            else:
                reply = "I still need a bit more detail. " + reply

        return {
            "route": "ask_discovery",
            "reply": reply,
            "status": "NEED_DATA",
            "needsFollowUp": True,
            "conversationMode": "concierge",
            "conversationIntent": conversation_intent,
            "replyKind": "discovery",
            "handledBy": "concierge",
            "nextActions": actions,
            "pendingAction": None,
            "supportLevel": support_level,
            "forceCollect": False,
            "domain": domain,
            "constraints": constraints,
        }

    def _ask_for_confirmation(
        self,
        *,
        action_type: str,
        prompt: str,
        constraints: dict[str, Any],
        domain: str,
        support_level: str,
    ) -> dict[str, Any]:
        pending_action = {
            "type": action_type,
            "status": "awaiting_user",
            "prompt": prompt,
            "expiresAfterTurn": 1,
        }
        return {
            "route": "ask_confirmation",
            "reply": prompt,
            "status": "NEED_DATA",
            "needsFollowUp": True,
            "conversationMode": "concierge",
            "conversationIntent": "pending_status",
            "replyKind": "confirmation_request",
            "handledBy": "concierge",
            "nextActions": [
                _action("confirm_yes", "Yes", "Yes, do it.", "confirm", "primary", True),
                _action("confirm_no", "No", "No, keep the current state.", "cancel", "secondary"),
            ],
            "pendingAction": pending_action,
            "supportLevel": support_level,
            "forceCollect": False,
            "domain": domain,
            "constraints": constraints,
        }

    def _confirm_pending_action(
        self,
        *,
        pending_action: dict[str, Any],
        constraints: dict[str, Any],
        domain: str,
        support_level: str,
    ) -> dict[str, Any]:
        action_type = str(pending_action.get("type") or "").strip()
        next_constraints = dict(constraints)
        force_collect = False
        if action_type == "enable_autofill":
            next_constraints["consentAutofill"] = True
        if action_type == "crawl_more":
            force_collect = True

        return {
            "route": "continue_analysis",
            "reply": "",
            "status": "OK",
            "needsFollowUp": False,
            "conversationMode": "shopping_analysis",
            "conversationIntent": "action_confirmation",
            "replyKind": "status_update",
            "handledBy": "concierge",
            "nextActions": [],
            "pendingAction": None,
            "supportLevel": support_level,
            "forceCollect": force_collect,
            "domain": domain,
            "constraints": next_constraints,
            "confirmedActionType": action_type,
        }

    def _reject_pending_action(
        self,
        *,
        pending_action: dict[str, Any],
        constraints: dict[str, Any],
        domain: str,
        support_level: str,
    ) -> dict[str, Any]:
        del pending_action
        return {
            "route": "respond_only",
            "reply": (
                "Understood. I will keep the current state. If you want, add another preference and I will continue "
                "without that extra action."
            ),
            "status": "OK",
            "needsFollowUp": False,
            "conversationMode": "concierge",
            "conversationIntent": "action_rejection",
            "replyKind": "status_update",
            "handledBy": "concierge",
            "nextActions": [
                _action("refine", "Refine brief", "Refine the brief and continue the run.", "reply", "primary"),
                _action("status", "Show pending state", "Explain this session and what is pending.", "reply", "secondary"),
            ],
            "pendingAction": None,
            "supportLevel": support_level,
            "forceCollect": False,
            "domain": domain,
            "constraints": constraints,
        }

    def _continue_planner_response(
        self,
        *,
        constraints: dict[str, Any],
        domain: str,
        support_level: str,
        conversation_intent: str = "shopping_constraints",
    ) -> dict[str, Any]:
        return {
            "route": "continue_planner",
            "reply": "",
            "status": "OK",
            "needsFollowUp": False,
            "conversationMode": "shopping_analysis",
            "conversationIntent": conversation_intent,
            "replyKind": "status_update",
            "handledBy": "concierge",
            "nextActions": [],
            "pendingAction": None,
            "supportLevel": support_level,
            "forceCollect": False,
            "domain": domain,
            "constraints": constraints,
        }

    def _continue_analysis_response(
        self,
        *,
        constraints: dict[str, Any],
        domain: str,
        support_level: str,
    ) -> dict[str, Any]:
        return {
            "route": "continue_analysis",
            "reply": "",
            "status": "OK",
            "needsFollowUp": False,
            "conversationMode": "shopping_analysis",
            "conversationIntent": "resume_request",
            "replyKind": "status_update",
            "handledBy": "concierge",
            "nextActions": [],
            "pendingAction": None,
            "supportLevel": support_level,
            "forceCollect": False,
            "domain": domain,
            "constraints": constraints,
        }

    def _fallback_response(self) -> dict[str, Any]:
        return {
            "route": "respond_only",
            "reply": (
                "I can help with shopping discovery, session follow-up, or project questions. "
                "Tell me what you want to buy, or ask what I can help with."
            ),
            "status": "OK",
            "needsFollowUp": False,
            "conversationMode": "concierge",
            "conversationIntent": "unknown",
            "replyKind": "answer",
            "handledBy": "concierge",
            "nextActions": [
                _action("find_product", "Find a product", "I want help finding a product.", "reply", "primary"),
                _action("project_stack", "Project tech stack", "What tech stack does this project use?", "reply", "secondary"),
            ],
            "pendingAction": None,
            "supportLevel": "unsupported",
            "forceCollect": False,
            "domain": "generic",
        }

    def _recent_user_category(self, history: list[dict[str, Any]]) -> str | None:
        for item in reversed(history):
            if str(item.get("role") or "").strip().lower() != "user":
                continue
            candidate = self._sanitize_category(extract_category_from_message(str(item.get("content") or "")))
            if candidate:
                return candidate
        return None

    def _sanitize_category(self, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.lower() in {
            "a product",
            "product",
            "something",
            "help finding a product",
            "finding a product",
            "shopping help",
            "help shopping",
        }:
            return None
        return text

    def _looks_like_shopping_follow_up(self, message: str) -> bool:
        normalized = message.strip().lower()
        if has_structured_constraint_signal(message):
            return True
        if ":" in message:
            return True
        return bool(
            re.search(
                r"\b(use case|main use case|priority|priorities|battery|latency|comfort|gaming|study|home office|work)\b",
                normalized,
                re.IGNORECASE,
            )
        )

    def _apply_discovery_updates(self, message: str, constraints: dict[str, Any]) -> dict[str, Any]:
        updated = dict(constraints)
        normalized = message.strip()
        budget_match = re.search(
            r"(?:under|below|budget(?:\s+under)?|max)\s*\$?\s*([0-9][0-9,]*)",
            normalized,
            re.IGNORECASE,
        )
        if budget_match:
            updated["budgetMax"] = int(budget_match.group(1).replace(",", ""))

        preference_chunks: list[str] = []
        use_case_match = re.search(r"(?:main\s+)?use case\s*:\s*(.+)$", normalized, re.IGNORECASE)
        if use_case_match:
            preference_chunks.append(f"use case: {use_case_match.group(1).strip()}")

        with_match = re.search(r"\bwith\s+(.+)$", normalized, re.IGNORECASE)
        if with_match:
            tail = with_match.group(1).strip().rstrip(".")
            for chunk in re.split(r",| and ", tail):
                text = chunk.strip()
                if len(text) >= 3:
                    preference_chunks.append(text)

        if not preference_chunks and ":" in normalized:
            label_match = re.search(r"([A-Za-z ]{3,30})\s*:\s*(.+)$", normalized)
            if label_match:
                label = label_match.group(1).strip().lower()
                value = label_match.group(2).strip()
                if label not in {"session", "status"} and value:
                    preference_chunks.append(f"{label}: {value}")

        must_have = [
            str(item).strip()
            for item in (updated.get("mustHave") or [])
            if str(item).strip()
        ]
        for chunk in preference_chunks:
            if chunk not in must_have:
                must_have.append(chunk)
        if must_have:
            updated["mustHave"] = must_have
        return updated

    def _discovery_brief_summary(self, constraints: dict[str, Any]) -> str:
        parts: list[str] = []
        budget = constraints.get("budgetMax")
        if isinstance(budget, (int, float)) and budget > 0:
            parts.append(f"a budget under ${int(budget)}")
        preferences = [
            str(item).strip()
            for item in (constraints.get("mustHave") or [])
            if str(item).strip()
        ][:2]
        if preferences:
            parts.append("priorities like " + ", ".join(preferences))
        return ", ".join(parts)

    def _support_level(self, domain: str, category: str | None) -> str:
        if not category:
            return "unsupported"
        return support_level_for_domain(domain)

    def _normalize_pending_action(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        action_type = str(value.get("type") or "").strip()
        status = str(value.get("status") or "").strip()
        prompt = str(value.get("prompt") or "").strip()
        if not action_type or not status:
            return None
        payload = {
            "type": action_type,
            "status": status,
            "prompt": prompt,
        }
        expires = value.get("expiresAfterTurn")
        if isinstance(expires, int):
            payload["expiresAfterTurn"] = expires
        return payload


def _action(
    action_id: str,
    label: str,
    message: str,
    kind: str,
    style: str,
    requires_confirmation: bool = False,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "message": message,
        "kind": kind,
        "style": style,
        "requiresConfirmation": requires_confirmation,
    }
