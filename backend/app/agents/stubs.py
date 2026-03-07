from __future__ import annotations

import re
from typing import Any

from app.core.model_router import ModelRouter


class PlannerAgent:
    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router

    async def run(
        self,
        message: str,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        constraints = self._extract_constraints(message)
        missing_fields = [
            field
            for field in ("category", "budgetMax", "minRating", "deliveryDeadline")
            if constraints.get(field) in (None, "", [])
        ]
        needs_follow_up = len(missing_fields) > 0

        llm_result = await self._model_router.call(
            task_type="planner",
            payload={
                "prompt": (
                    "Convert shopping intent into structured constraints. "
                    f"User message: {message}"
                )
            },
        )

        follow_up_question = None
        if needs_follow_up:
            missing_field = missing_fields[0]
            follow_up_question = (
                f"I still need your {missing_field}. "
                "Can you provide it so I can continue?"
            )

        return {
            "constraints": constraints,
            "missingFields": missing_fields,
            "needsFollowUp": needs_follow_up,
            "followUpQuestion": follow_up_question,
            "modelMeta": {
                "modelId": llm_result.model_id,
                "fallbackUsed": llm_result.fallback_used,
                "fallbackReason": llm_result.fallback_reason,
                "latencySeconds": llm_result.latency_seconds,
            },
        }

    def _extract_constraints(self, message: str) -> dict[str, Any]:
        lower = message.lower()
        category = None
        if "chair" in lower:
            category = "ergonomic chair"
        elif "desk" in lower:
            category = "desk"
        elif "headphone" in lower:
            category = "headphones"

        budget_match = re.search(r"(?:under|below|<=?)\s*\$?(\d+(?:\.\d+)?)", lower)
        budget_max = float(budget_match.group(1)) if budget_match else None

        rating_match = re.search(r"(\d(?:\.\d)?)\+?\s*stars?", lower)
        min_rating = float(rating_match.group(1)) if rating_match else None

        deadline_match = re.search(r"delivered by\s+([a-z0-9 ,]+)", lower)
        delivery_deadline = deadline_match.group(1).strip() if deadline_match else None

        must_have: list[str] = []
        if "ergonomic" in lower:
            must_have.append("ergonomic")
        if "dorm" in lower:
            must_have.append("dorm-friendly size")

        return {
            "category": category,
            "budgetMax": budget_max,
            "minRating": min_rating,
            "deliveryDeadline": delivery_deadline,
            "mustHave": must_have,
            "niceToHave": [],
            "exclude": [],
        }


class ReviewIntelligenceAgent:
    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router

    async def run(self, constraints: dict[str, Any]) -> dict[str, Any]:
        llm_result = await self._model_router.call(
            task_type="review_intelligence",
            payload={"prompt": f"Analyze review quality for {constraints}"},
        )
        return {
            "pros": ["Comfortable for long study sessions", "Good value for price"],
            "cons": ["Assembly time can be long", "Armrest durability varies"],
            "riskFlags": ["Some reviews mention paid promotion disclaimers"],
            "paidPromoLikelihood": 0.28,
            "confidence": 0.77,
            "modelMeta": {
                "modelId": llm_result.model_id,
                "fallbackUsed": llm_result.fallback_used,
                "fallbackReason": llm_result.fallback_reason,
            },
        }


class VisualVerificationAgent:
    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router

    async def run(self, constraints: dict[str, Any]) -> dict[str, Any]:
        llm_result = await self._model_router.call(
            task_type="visual_verification",
            payload={"prompt": f"Evaluate image authenticity for {constraints}"},
        )
        return {
            "authenticityScore": 71,
            "mismatchFlags": ["Color differs between listing and user-uploaded photos"],
            "confidence": 0.65,
            "modelMeta": {
                "modelId": llm_result.model_id,
                "fallbackUsed": llm_result.fallback_used,
                "fallbackReason": llm_result.fallback_reason,
            },
        }


class PriceLogisticsAgent:
    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router

    async def run(self, constraints: dict[str, Any]) -> dict[str, Any]:
        llm_result = await self._model_router.call(
            task_type="price_logistics",
            payload={"prompt": f"Compare pricing and delivery for {constraints}"},
        )
        return {
            "candidates": [
                {
                    "title": "ErgoFlex Dorm Chair",
                    "sourceUrl": "https://example.com/product/ergoflex-chair",
                    "price": 139.99,
                    "shippingETA": "2-4 days",
                    "returnPolicy": "30-day return",
                    "checkoutReady": False,
                }
            ],
            "executionTrace": [
                "Opened storefront",
                "Compared shipping options",
                "Stopped before payment step",
            ],
            "modelMeta": {
                "modelId": llm_result.model_id,
                "fallbackUsed": llm_result.fallback_used,
                "fallbackReason": llm_result.fallback_reason,
            },
        }


class DecisionAgent:
    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router

    async def run(self, agent_outputs: dict[str, Any]) -> dict[str, Any]:
        llm_result = await self._model_router.call(
            task_type="decision",
            payload={"prompt": "Create BUY/WAIT/AVOID recommendation from input signals."},
        )

        review_score = 30 * agent_outputs["review"]["confidence"]
        visual_score = 20 * (agent_outputs["visual"]["authenticityScore"] / 100)
        price_score = 25 * 0.78
        delivery_score = 15 * 0.72
        return_score = 10 * 0.80
        trust_score = round(review_score + visual_score + price_score + delivery_score + return_score, 2)

        if trust_score >= 75:
            verdict = "BUY"
        elif trust_score >= 55:
            verdict = "WAIT"
        else:
            verdict = "AVOID"

        return {
            "trustScore": trust_score,
            "verdict": verdict,
            "topReasons": [
                "Price is within budget and shipping is acceptable",
                "Review sentiment is mostly positive with moderate risk flags",
            ],
            "confidence": 0.74,
            "modelMeta": {
                "modelId": llm_result.model_id,
                "fallbackUsed": llm_result.fallback_used,
                "fallbackReason": llm_result.fallback_reason,
            },
        }

