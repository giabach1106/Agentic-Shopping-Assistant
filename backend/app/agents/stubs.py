from __future__ import annotations

import re
from typing import Any

from app.core.model_router import ModelRouter
from app.models.agent_outputs import PriceLogisticsOutput, VisualInsight
from app.models.planner import SearchConstraints
from app.rag.providers import HybridRAGService
from app.services.review_analysis import ReviewEvidenceAnalyzer
from app.services.trust_scoring import TrustScoringEngine
from app.services.visual_analysis import VisualEvidenceAnalyzer
from app.tools.ui_executor import UIExecutionRequest, UIExecutor


class PlannerAgent:
    _critical_fields = ("category", "budgetMax", "minRating", "deliveryDeadline")

    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router

    async def run(
        self,
        message: str,
        history: list[dict[str, Any]],
        existing_constraints: dict[str, Any] | None = None,
        follow_up_count: int = 0,
    ) -> dict[str, Any]:
        del history  # history is wired for future planner upgrades.
        extracted = self._extract_constraints(message)
        merged = self._merge_constraints(existing_constraints or {}, extracted)
        constraints = SearchConstraints.model_validate(merged)
        constraints_dict = constraints.to_public_dict()

        missing_fields = [
            field
            for field in self._critical_fields
            if constraints_dict.get(field) in (None, "", [])
        ]
        needs_follow_up = len(missing_fields) > 0 and follow_up_count < 4

        llm_result = await self._model_router.call(
            task_type="planner",
            payload={
                "prompt": (
                    "Convert shopping intent into structured constraints. "
                    f"User message: {message}"
                )
            },
        )

        inferred_fields = [
            field
            for field in self._critical_fields
            if extracted.get(field) in (None, "", [])
            and (existing_constraints or {}).get(field) not in (None, "", [])
        ]

        follow_up_question = None
        if needs_follow_up:
            missing_field = missing_fields[0]
            follow_up_question = self._build_follow_up_question(missing_field)
            next_follow_up_count = follow_up_count + 1
        elif len(missing_fields) == 0:
            next_follow_up_count = 0
        else:
            next_follow_up_count = follow_up_count

        return {
            "constraints": constraints_dict,
            "missingFields": missing_fields,
            "inferredFields": inferred_fields,
            "needsFollowUp": needs_follow_up,
            "followUpQuestion": follow_up_question,
            "followUpCount": next_follow_up_count,
            "modelMeta": {
                "modelId": llm_result.model_id,
                "fallbackUsed": llm_result.fallback_used,
                "fallbackReason": llm_result.fallback_reason,
                "latencySeconds": llm_result.latency_seconds,
            },
        }

    def _build_follow_up_question(self, missing_field: str) -> str:
        question_map = {
            "category": "What product category do you want me to search?",
            "budgetMax": "What is your maximum budget?",
            "minRating": "What minimum rating should I enforce (for example, 4 stars)?",
            "deliveryDeadline": "By what date or day do you need the item delivered?",
        }
        return question_map.get(
            missing_field,
            f"I still need your {missing_field}. Can you provide it so I can continue?",
        )

    def _merge_constraints(
        self,
        existing: dict[str, Any],
        extracted: dict[str, Any],
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        all_keys = set(existing.keys()) | set(extracted.keys())
        for key in all_keys:
            existing_value = existing.get(key)
            new_value = extracted.get(key)
            if isinstance(existing_value, list) or isinstance(new_value, list):
                merged[key] = self._merge_list_values(existing_value, new_value)
                continue
            merged[key] = new_value if new_value not in (None, "", []) else existing_value
        return merged

    def _merge_list_values(self, existing: Any, new: Any) -> list[str]:
        existing_list = existing if isinstance(existing, list) else []
        new_list = new if isinstance(new, list) else []
        merged: list[str] = []
        for item in [*existing_list, *new_list]:
            text = str(item).strip()
            if text and text not in merged:
                merged.append(text)
        return merged

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
        if min_rating is not None and min_rating > 5:
            min_rating = None

        deadline_match = re.search(r"delivered by\s+([a-z0-9 ,]+)", lower)
        delivery_deadline = deadline_match.group(1).strip() if deadline_match else None

        must_have: list[str] = []
        if "ergonomic" in lower:
            must_have.append("ergonomic")
        if "dorm" in lower:
            must_have.append("dorm-friendly size")

        exclude: list[str] = []
        exclude_match = re.findall(r"(?:not|exclude)\s+([a-z0-9 -]+)", lower)
        for value in exclude_match:
            cleaned = value.strip()
            if cleaned:
                exclude.append(cleaned)

        consent_autofill: bool | None = None
        if any(
            phrase in lower
            for phrase in ("autofill", "auto fill", "fill checkout", "fill form")
        ):
            consent_autofill = not any(
                phrase in lower
                for phrase in ("do not autofill", "don't autofill", "no autofill")
            )

        visual_evidence: list[str] = []
        if any(phrase in lower for phrase in ("uploaded photo", "uploaded image", "my room photo", "image attached", "photo attached")):
            visual_evidence.append("user-upload-1")
        if "blurry" in lower:
            visual_evidence.append("blurry-evidence")
        if any(token in lower for token in ("ai image", "ai-generated image", "synthetic image")):
            visual_evidence.append("ai-generated-signal")
        if "color mismatch" in lower or "different color" in lower:
            visual_evidence.append("color-mismatch")
        if "scale issue" in lower or "size looks off" in lower:
            visual_evidence.append("scale-issue")

        return {
            "category": category,
            "budgetMax": budget_max,
            "minRating": min_rating,
            "deliveryDeadline": delivery_deadline,
            "mustHave": must_have,
            "niceToHave": [],
            "exclude": exclude,
            "consentAutofill": consent_autofill,
            "visualEvidence": visual_evidence,
        }


class ReviewIntelligenceAgent:
    def __init__(self, model_router: ModelRouter, rag_service: HybridRAGService) -> None:
        self._model_router = model_router
        self._rag_service = rag_service
        self._evidence_analyzer = ReviewEvidenceAnalyzer()

    async def run(self, constraints: dict[str, Any]) -> dict[str, Any]:
        retrieval = await self._rag_service.retrieve_review_context(constraints)
        documents = retrieval["documents"]
        source_stats = retrieval["sourceStats"]
        analysis = self._evidence_analyzer.analyze(documents)
        ranked_evidence = analysis["rankedEvidence"]
        evidence_refs = [item.doc_id for item in ranked_evidence]
        promo_likelihood = float(analysis["paidPromoLikelihood"])
        evidence_quality = float(analysis["averageQuality"])

        llm_result = await self._model_router.call(
            task_type="review_intelligence",
            payload={
                "prompt": (
                    f"Analyze review quality for {constraints}. "
                    f"Use evidence: {[doc.content for doc in documents]}"
                )
            },
        )

        pros = ["Comfortable for long study sessions", "Good value for price"]
        if any("warranty" in item.excerpt.lower() for item in ranked_evidence):
            pros.append("Community feedback includes practical durability checks.")

        cons = ["Assembly time can be long", "Armrest durability varies"]
        if any("wobble" in item.excerpt.lower() for item in ranked_evidence):
            cons.append("Lower-end variants may wobble after long-term use.")

        risk_flags = []
        if "tiktok" in source_stats:
            risk_flags.append("Contains creator-sourced opinions; verify sponsorship tags.")
        if promo_likelihood >= 0.5:
            risk_flags.append("High affiliate/sponsored signal ratio in retrieved evidence.")
        if analysis["duplicateClusters"]:
            risk_flags.append("Duplicate review narratives detected across sources.")
        if len(evidence_refs) == 0:
            risk_flags.append("Low evidence coverage across sources.")

        return {
            "pros": pros,
            "cons": cons,
            "riskFlags": risk_flags,
            "paidPromoLikelihood": promo_likelihood,
            "confidence": round((0.5 * evidence_quality) + (0.5 * (1 - promo_likelihood)), 2),
            "sourceStats": source_stats,
            "evidenceRefs": evidence_refs,
            "evidenceQualityScore": evidence_quality,
            "duplicateReviewClusters": analysis["duplicateClusters"],
            "rankedEvidence": [
                {
                    "docId": item.doc_id,
                    "source": item.source,
                    "qualityScore": item.quality_score,
                    "promoSignals": item.promo_signals,
                    "excerpt": item.excerpt,
                }
                for item in ranked_evidence
            ],
            "modelMeta": {
                "modelId": llm_result.model_id,
                "fallbackUsed": llm_result.fallback_used,
                "fallbackReason": llm_result.fallback_reason,
            },
        }


class VisualVerificationAgent:
    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router
        self._visual_analyzer = VisualEvidenceAnalyzer()

    async def run(self, constraints: dict[str, Any]) -> dict[str, Any]:
        llm_result = await self._model_router.call(
            task_type="visual_verification",
            payload={"prompt": f"Evaluate image authenticity for {constraints}"},
        )
        evidence_refs = [str(item) for item in constraints.get("visualEvidence", []) or []]
        analysis = self._visual_analyzer.analyze(evidence_refs)
        payload = VisualInsight(
            status=analysis.status,
            authenticityScore=analysis.authenticity_score,
            mismatchFlags=analysis.mismatch_flags,
            visualRisks=analysis.visual_risks,
            confidence=analysis.confidence,
            requiredEvidence=analysis.required_evidence,
            evidenceRefs=analysis.evidence_refs,
        )

        output = payload.model_dump(by_alias=True)
        output["modelMeta"] = {
            "modelId": llm_result.model_id,
            "fallbackUsed": llm_result.fallback_used,
            "fallbackReason": llm_result.fallback_reason,
        }
        return output


class PriceLogisticsAgent:
    def __init__(
        self,
        model_router: ModelRouter,
        ui_executor: UIExecutor,
        stop_before_pay: bool,
    ) -> None:
        self._model_router = model_router
        self._ui_executor = ui_executor
        self._stop_before_pay = stop_before_pay

    async def run(self, constraints: dict[str, Any]) -> dict[str, Any]:
        consent_autofill = bool(constraints.get("consentAutofill", False))
        execution_result = await self._ui_executor.execute(
            UIExecutionRequest(
                constraints=constraints,
                consent_autofill=consent_autofill,
                stop_before_pay=self._stop_before_pay,
            )
        )
        validated_output = PriceLogisticsOutput.model_validate(
            execution_result.to_public_dict()
        )

        llm_result = await self._model_router.call(
            task_type="price_logistics",
            payload={
                "prompt": (
                    "Compare pricing and delivery from executor output. "
                    f"constraints={constraints}, blockers={validated_output.blockers}"
                )
            },
        )

        response = validated_output.model_dump(by_alias=True)
        response["modelMeta"] = {
            "modelId": llm_result.model_id,
            "fallbackUsed": llm_result.fallback_used,
            "fallbackReason": llm_result.fallback_reason,
        }
        return response


class DecisionAgent:
    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router
        self._scoring_engine = TrustScoringEngine()

    async def run(
        self,
        agent_outputs: dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        llm_result = await self._model_router.call(
            task_type="decision",
            payload={"prompt": "Create BUY/WAIT/AVOID recommendation from input signals."},
        )

        scoring_result = self._scoring_engine.evaluate(
            agent_outputs=agent_outputs,
            constraints=constraints or {},
        )

        return {
            "trustScore": scoring_result.trust_score,
            "verdict": scoring_result.verdict,
            "topReasons": scoring_result.top_reasons,
            "riskFlags": scoring_result.risk_flags,
            "confidence": scoring_result.confidence,
            "whyRankedHere": scoring_result.why_ranked_here,
            "scoreBreakdown": scoring_result.score_breakdown,
            "selectedCandidate": scoring_result.selected_candidate,
            "modelMeta": {
                "modelId": llm_result.model_id,
                "fallbackUsed": llm_result.fallback_used,
                "fallbackReason": llm_result.fallback_reason,
            },
        }
