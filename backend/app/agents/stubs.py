from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from app.collectors.base import RealtimeCollector
from app.core.config import Settings
from app.core.model_router import ModelRouter
from app.memory.evidence_store import SQLiteEvidenceStore
from app.models.agent_outputs import PriceLogisticsOutput, VisualInsight
from app.models.planner import SearchConstraints
from app.rag.base import RetrievalDocument
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
        session_id: str | None = None,
    ) -> dict[str, Any]:
        del history

        llm_result = await self._model_router.call(
            task_type="planner",
            payload={
                "prompt": (
                    "Extract strict shopping constraints as JSON with keys "
                    "category,budgetMax,minRating,deliveryDeadline,mustHave,niceToHave,"
                    "exclude,consentAutofill,visualEvidence. "
                    f"User message: {message}"
                )
            },
            session_id=session_id,
        )

        llm_extracted = self._extract_constraints_from_llm_text(
            str(llm_result.output.get("text") or "")
        )
        regex_extracted = self._extract_constraints_regex(message)
        extracted = self._merge_constraints(regex_extracted, llm_extracted)

        merged = self._merge_constraints(existing_constraints or {}, extracted)
        constraints = SearchConstraints.model_validate(merged)
        constraints_dict = constraints.to_public_dict()

        missing_fields = [
            field
            for field in self._critical_fields
            if constraints_dict.get(field) in (None, "", [])
        ]
        needs_follow_up = len(missing_fields) > 0 and follow_up_count < 4

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

    def _extract_constraints_from_llm_text(self, text: str) -> dict[str, Any]:
        if not text:
            return {}

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return {}
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}

        if not isinstance(payload, dict):
            return {}

        allowed = {
            "category",
            "budgetMax",
            "minRating",
            "deliveryDeadline",
            "mustHave",
            "niceToHave",
            "exclude",
            "consentAutofill",
            "visualEvidence",
        }
        return {key: value for key, value in payload.items() if key in allowed}

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

    def _extract_constraints_regex(self, message: str) -> dict[str, Any]:
        lower = message.lower()
        category = None
        intent_match = re.search(
            r"(?:need|want|looking for|find|buy|get)\s+(?:an?\s+|some\s+)?"
            r"([a-z0-9][a-z0-9\-\s]{2,80}?)"
            r"(?=\s+(?:under|below|with|delivered|by|exclude|for|and)\b|[,.]|$)",
            lower,
        )
        if intent_match:
            candidate = intent_match.group(1).strip()
            candidate = re.sub(r"\s+", " ", candidate)
            candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate)
            if 2 <= len(candidate) <= 80:
                category = candidate

        if category is None:
            stripped = lower.strip()
            generic_category = re.fullmatch(
                r"[a-z][a-z0-9-]{1,30}(?:\s+[a-z0-9-]{1,30})?",
                stripped,
            )
            has_structured_signal = any(
                token in stripped
                for token in (
                    "rating",
                    "star",
                    "under",
                    "below",
                    "budget",
                    "price",
                    "delivered",
                    "delivery",
                    "exclude",
                    "autofill",
                )
            )
            if generic_category and not has_structured_signal and stripped not in {
                "hello",
                "hi",
                "hey",
                "thanks",
                "thank you",
                "ok",
                "okay",
                "continue",
                "today",
                "tomorrow",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            }:
                category = stripped

        budget_match = re.search(r"(?:under|below|<=?)\s*\$?(\d+(?:\.\d+)?)", lower)
        budget_max = float(budget_match.group(1)) if budget_match else None
        single_numeric_match = re.fullmatch(r"\$?\s*(\d+(?:\.\d+)?)", lower.strip())
        single_numeric = float(single_numeric_match.group(1)) if single_numeric_match else None
        if budget_max is None and single_numeric is not None and single_numeric > 5:
            budget_max = single_numeric

        rating_match = re.search(r"(\d(?:\.\d)?)\+?\s*stars?", lower)
        min_rating = float(rating_match.group(1)) if rating_match else None
        if min_rating is None and single_numeric is not None and 0 < single_numeric <= 5:
            min_rating = single_numeric
        if min_rating is not None and min_rating > 5:
            min_rating = None

        deadline_match = re.search(r"delivered by\s+([a-z0-9 ,]+)", lower)
        delivery_deadline = deadline_match.group(1).strip() if deadline_match else None
        if delivery_deadline is None:
            direct_deadline_match = re.fullmatch(
                r"(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                lower.strip(),
            )
            if direct_deadline_match:
                delivery_deadline = direct_deadline_match.group(1)

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
        if any(
            phrase in lower
            for phrase in (
                "uploaded photo",
                "uploaded image",
                "my room photo",
                "image attached",
                "photo attached",
            )
        ):
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


class EvidenceCollectionAgent:
    def __init__(
        self,
        settings: Settings,
        collector: RealtimeCollector,
        evidence_store: SQLiteEvidenceStore,
    ) -> None:
        self._settings = settings
        self._collector = collector
        self._evidence_store = evidence_store

    async def run(self, constraints: dict[str, Any]) -> dict[str, Any]:
        cached = await self._evidence_store.get_cached_collection(constraints)
        cached_collection = dict(cached.get("collection") or {}) if cached else None
        cached_stats = dict(cached.get("stats") or {}) if cached else {}

        cache_hit = cached_collection is not None
        collection = dict(cached_collection or {})
        stats = dict(cached_stats)
        sufficiency = self._evaluate_sufficiency(stats)

        if not sufficiency["isSufficient"]:
            result = await self._collector.collect(constraints)
            fresh_payload = result.to_public_dict()
            collection = self._merge_collections(collection, fresh_payload)
            stats = self._build_stats(collection)
            sufficiency = self._evaluate_sufficiency(stats)
            await self._evidence_store.upsert_cached_collection(constraints, collection, stats)
            cache_status = "merged" if cache_hit else "miss"
        else:
            cache_status = "hit"

        source_coverage = self._compute_source_coverage(collection)
        missing_evidence = self._normalize_missing_evidence(collection)
        if not sufficiency["isSufficient"]:
            missing_evidence.extend(str(item) for item in sufficiency["missing"])
        missing_evidence = sorted(set(item for item in missing_evidence if item))
        status = "OK"
        if self._settings.runtime_mode == "prod" and missing_evidence:
            status = "NEED_DATA"
        return {
            "status": status,
            "sourceCoverage": source_coverage,
            "reviewCount": int(stats.get("reviewCount", 0)),
            "ratingCount": int(stats.get("ratingCount", 0)),
            "freshnessSeconds": int(stats.get("freshnessSeconds", 999999)),
            "missingEvidence": missing_evidence,
            "blockedSources": collection.get("blockedSources", []),
            "collection": collection,
            "cacheStatus": cache_status,
            "sufficiency": sufficiency,
        }

    def _compute_source_coverage(self, payload: dict[str, Any]) -> int:
        sources: set[str] = set()
        for key in ("products", "reviews", "visuals"):
            entries = payload.get(key)
            if not isinstance(entries, list):
                continue
            for item in entries:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or "").strip().lower()
                if source:
                    sources.add(source)
        return len(sources)

    def _normalize_missing_evidence(self, payload: dict[str, Any]) -> list[str]:
        missing = list(payload.get("missingEvidence") or [])
        product_sources = {
            str(item.get("source") or "").strip().lower()
            for item in payload.get("products", [])
            if isinstance(item, dict)
        }
        # Product-list requirements are source-agnostic: if at least one
        # commerce source yielded products, don't block on per-source misses.
        if product_sources:
            missing = [item for item in missing if not str(item).endswith(".product_list")]
        return missing

    def _merge_collections(
        self,
        cached: dict[str, Any],
        fresh: dict[str, Any],
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for key in ("products", "reviews", "visuals"):
            cached_entries = cached.get(key) if isinstance(cached.get(key), list) else []
            fresh_entries = fresh.get(key) if isinstance(fresh.get(key), list) else []
            merged[key] = self._merge_entry_list(cached_entries, fresh_entries)

        merged_trace = []
        if isinstance(cached.get("trace"), list):
            merged_trace.extend(item for item in cached["trace"] if isinstance(item, dict))
        if isinstance(fresh.get("trace"), list):
            merged_trace.extend(item for item in fresh["trace"] if isinstance(item, dict))
        merged_trace.insert(
            0,
            {
                "source": "cache",
                "step": "cache_lookup",
                "status": "ok" if cached else "warning",
                "detail": "Merged stored evidence with collector output." if cached else "No cached evidence found.",
                "duration_ms": 0,
            },
        )

        merged["trace"] = merged_trace
        merged["missingEvidence"] = sorted(
            {
                str(item)
                for item in [*(cached.get("missingEvidence") or []), *(fresh.get("missingEvidence") or [])]
                if str(item).strip()
            }
        )
        merged["blockedSources"] = sorted(
            {
                str(item)
                for item in [*(cached.get("blockedSources") or []), *(fresh.get("blockedSources") or [])]
                if str(item).strip()
            }
        )
        return merged

    def _merge_entry_list(
        self,
        cached_entries: list[Any],
        fresh_entries: list[Any],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*fresh_entries, *cached_entries]:
            if not isinstance(item, dict):
                continue
            key = str(
                item.get("evidence_id")
                or item.get("evidenceId")
                or item.get("review_id")
                or item.get("reviewId")
                or item.get("url")
                or item.get("image_url")
                or item.get("imageUrl")
                or item.get("title")
                or ""
            ).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _build_stats(self, payload: dict[str, Any]) -> dict[str, Any]:
        products = payload.get("products", []) if isinstance(payload.get("products"), list) else []
        reviews = payload.get("reviews", []) if isinstance(payload.get("reviews"), list) else []
        review_count = len([item for item in reviews if isinstance(item, dict)])
        rating_count = sum(
            int(item.get("rating_count") or item.get("ratingCount") or 0)
            for item in products
            if isinstance(item, dict)
        )
        freshness_seconds = self._freshness_seconds(payload)
        return {
            "sourceCoverage": self._compute_source_coverage(payload),
            "reviewCount": review_count,
            "ratingCount": rating_count,
            "freshnessSeconds": freshness_seconds,
        }

    def _evaluate_sufficiency(self, stats: dict[str, Any]) -> dict[str, Any]:
        missing: list[str] = []
        if int(stats.get("sourceCoverage", 0)) < self._settings.min_source_coverage:
            missing.append("sourceCoverage")
        if int(stats.get("reviewCount", 0)) < self._settings.min_review_count:
            missing.append("reviewCount")
        if int(stats.get("ratingCount", 0)) < self._settings.min_rating_count:
            missing.append("ratingCount")
        if int(stats.get("freshnessSeconds", 999999)) > (self._settings.evidence_freshness_minutes * 60):
            missing.append("freshness")
        return {"isSufficient": len(missing) == 0, "missing": missing}

    def _freshness_seconds(self, payload: dict[str, Any]) -> int:
        now = datetime.now(UTC)
        newest_age = 999999
        parsed_any = False
        for key in ("products", "reviews", "visuals"):
            entries = payload.get(key)
            if not isinstance(entries, list):
                continue
            for item in entries:
                if not isinstance(item, dict):
                    continue
                raw = str(item.get("retrieved_at") or item.get("retrievedAt") or "").strip()
                if not raw:
                    continue
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    continue
                parsed_any = True
                newest_age = min(newest_age, int((now - dt).total_seconds()))
        if not parsed_any:
            return 999999
        return max(0, newest_age)


class ReviewIntelligenceAgent:
    def __init__(self, model_router: ModelRouter, rag_service: HybridRAGService) -> None:
        self._model_router = model_router
        self._rag_service = rag_service
        self._evidence_analyzer = ReviewEvidenceAnalyzer()

    async def run(
        self,
        constraints: dict[str, Any],
        collection: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        collection = collection or {}
        reviews = collection.get("reviews", []) if isinstance(collection, dict) else []
        products = collection.get("products", []) if isinstance(collection, dict) else []

        docs = [
            RetrievalDocument(
                doc_id=str(item.get("evidence_id") or item.get("review_id") or "review"),
                source=str(item.get("source") or "unknown"),
                content=str(item.get("review_text") or "").strip(),
                metadata={
                    "helpfulVotes": int(item.get("helpful_votes") or 0),
                    "rating": float(item.get("rating") or 0.0),
                },
            )
            for item in reviews
            if str(item.get("review_text") or "").strip()
        ]

        if not docs:
            return {
                "status": "NEED_DATA",
                "pros": [],
                "cons": [],
                "riskFlags": ["No live review corpus available for analysis."],
                "paidPromoLikelihood": 1.0,
                "confidence": 0.0,
                "sourceStats": {},
                "evidenceRefs": [],
                "evidenceQualityScore": 0.0,
                "duplicateReviewClusters": [],
                "rankedEvidence": [],
                "reviewCount": 0,
                "ratingSummary": {
                    "avgRating": 0.0,
                    "ratingCount": 0,
                    "positiveCount": 0,
                    "positiveRate": 0.0,
                },
                "absaSignals": {},
                "modelMeta": {
                    "modelId": "none",
                    "fallbackUsed": False,
                    "fallbackReason": "review corpus unavailable",
                },
            }

        retrieval = await self._rag_service.retrieve_review_context(constraints)
        analysis = self._evidence_analyzer.analyze(docs)
        ranked_evidence = analysis["rankedEvidence"]
        evidence_refs = [item.doc_id for item in ranked_evidence]
        promo_likelihood = float(analysis["paidPromoLikelihood"])
        evidence_quality = float(analysis["averageQuality"])

        llm_result = await self._model_router.call(
            task_type="review_intelligence",
            payload={
                "prompt": (
                    "Summarize review strengths and weaknesses strictly from provided corpus. "
                    f"constraints={constraints}, reviewCount={len(docs)}"
                )
            },
            session_id=session_id,
        )

        positives = [doc for doc in docs if float(doc.metadata.get("rating") or 0) >= 4]
        negatives = [doc for doc in docs if float(doc.metadata.get("rating") or 0) < 4]
        pros = [item.content[:140] for item in positives[:3]]
        cons = [item.content[:140] for item in negatives[:3]]

        source_stats: dict[str, int] = {}
        for review in reviews:
            source = str(review.get("source") or "unknown")
            source_stats[source] = source_stats.get(source, 0) + 1

        rating_count = sum(int(item.get("rating_count") or 0) for item in products)
        avg_rating = 0.0
        if rating_count > 0:
            weighted_sum = sum(
                float(item.get("avg_rating") or 0.0) * int(item.get("rating_count") or 0)
                for item in products
            )
            avg_rating = round(weighted_sum / rating_count, 3)
        else:
            ratings = [
                float(item.get("rating") or 0.0)
                for item in reviews
                if item.get("rating") is not None
            ]
            avg_rating = round(mean(ratings), 3) if ratings else 0.0
            rating_count = len(ratings)

        positive_count = sum(1 for item in reviews if float(item.get("rating") or 0.0) >= 4)
        positive_rate = round((positive_count / max(1, len(reviews))), 4)

        risk_flags: list[str] = []
        if promo_likelihood >= 0.5:
            risk_flags.append("High affiliate/sponsored signal ratio in review corpus.")
        if analysis["duplicateClusters"]:
            risk_flags.append("Duplicate review narratives detected across sources.")
        if len(evidence_refs) < 2:
            risk_flags.append("Low evidence coverage across sources.")

        aspects = {
            "comfort": 0.0,
            "durability": 0.0,
            "assembly": 0.0,
            "price": 0.0,
            "delivery": 0.0,
            "return": 0.0,
        }
        keywords = {
            "comfort": ("comfort", "back", "lumbar", "seat"),
            "durability": ("durable", "wobble", "break", "sturdy"),
            "assembly": ("assembly", "assemble", "screw", "manual"),
            "price": ("price", "value", "expensive", "cheap"),
            "delivery": ("ship", "delivery", "arrive", "late"),
            "return": ("return", "refund", "policy"),
        }
        for aspect, tokens in keywords.items():
            hits = [doc for doc in docs if any(token in doc.content.lower() for token in tokens)]
            if not hits:
                continue
            avg = mean(float(doc.metadata.get("rating") or 0.0) for doc in hits)
            aspects[aspect] = round((avg - 3.0) / 2.0, 3)

        return {
            "status": "OK",
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
            "retrievalContext": {
                "query": retrieval["query"],
                "documents": [doc.doc_id for doc in retrieval["documents"]],
                "sourceStats": retrieval["sourceStats"],
            },
            "reviewCount": len(reviews),
            "ratingSummary": {
                "avgRating": avg_rating,
                "ratingCount": rating_count,
                "positiveCount": positive_count,
                "positiveRate": positive_rate,
            },
            "absaSignals": aspects,
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

    async def run(
        self,
        constraints: dict[str, Any],
        collection: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        llm_result = await self._model_router.call(
            task_type="visual_verification",
            payload={"prompt": f"Evaluate image authenticity for {constraints}"},
            session_id=session_id,
        )
        extra_refs = [str(item) for item in constraints.get("visualEvidence", []) or []]
        visuals = collection.get("visuals", []) if isinstance(collection, dict) else []
        collected_refs = [str(item.get("evidence_id")) for item in visuals if item.get("evidence_id")]
        evidence_refs = [*collected_refs, *extra_refs]

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
        output["visualCount"] = len(visuals)
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
        runtime_mode: str,
        ui_executor_backend: str,
    ) -> None:
        self._model_router = model_router
        self._ui_executor = ui_executor
        self._stop_before_pay = stop_before_pay
        self._runtime_mode = runtime_mode
        self._ui_executor_backend = ui_executor_backend

    async def run(
        self,
        constraints: dict[str, Any],
        collection: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        consent_autofill = bool(constraints.get("consentAutofill", False))
        execution_result = await self._ui_executor.execute(
            UIExecutionRequest(
                constraints=constraints,
                consent_autofill=consent_autofill,
                stop_before_pay=self._stop_before_pay,
                session_id=session_id,
            )
        )

        source_priority = {"ebay": 0, "walmart": 1, "amazon": 2}
        ranked_candidates: list[tuple[int, dict[str, Any]]] = []
        candidates: list[dict[str, Any]] = []
        if isinstance(collection, dict):
            for item in collection.get("products", []):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url.startswith("http"):
                    continue
                source = str(item.get("source") or "").strip().lower()
                candidates.append(
                    {
                        "title": str(item.get("title") or "unknown product"),
                        "sourceUrl": url,
                        "price": float(item.get("price") or 1.0),
                        "rating": float(item.get("avg_rating") or 0.0),
                        "shippingETA": str(item.get("shipping_eta") or "unknown"),
                        "returnPolicy": str(item.get("return_policy") or "unknown"),
                        "checkoutReady": False,
                        "evidenceRefs": [str(item.get("evidence_id") or "")],
                    }
                )
                ranked_candidates.append(
                    (
                        source_priority.get(source, 99),
                        candidates[-1],
                    )
                )

        if ranked_candidates:
            candidates = [
                item
                for _, item in sorted(
                    ranked_candidates,
                    key=lambda entry: (entry[0], float(entry[1].get("price", 0.0))),
                )
            ]

        if self._runtime_mode != "prod" and len(candidates) == 0:
            candidates = execution_result.to_public_dict().get("candidates", [])

        blockers = list(execution_result.blockers)
        if self._runtime_mode == "prod" and self._ui_executor_backend == "mock":
            blockers.append("executor_not_realtime")
        if self._runtime_mode == "prod" and len(candidates) == 0:
            blockers.append("missing_realtime_products")

        trace = execution_result.to_public_dict().get("executionTrace", [])
        if isinstance(collection, dict):
            collect_trace = collection.get("trace", [])
            if isinstance(collect_trace, list):
                trace = [
                    *[
                        {
                            "step": f"collect::{str(item.get('step') or 'unknown')}",
                            "status": str(item.get("status") or "warning"),
                            "detail": str(item.get("detail") or ""),
                        }
                        for item in collect_trace
                        if isinstance(item, dict)
                    ],
                    *trace,
                ]

        validated_output = PriceLogisticsOutput.model_validate(
            {
                "candidates": candidates,
                "executionTrace": trace,
                "blockers": blockers,
                "consentAutofill": consent_autofill,
                "stopBeforePay": self._stop_before_pay,
            }
        )

        llm_result = await self._model_router.call(
            task_type="price_logistics",
            payload={
                "prompt": (
                    "Compare pricing and delivery from realtime executor output. "
                    f"constraints={constraints}, blockers={validated_output.blockers}"
                )
            },
            session_id=session_id,
        )

        response = validated_output.model_dump(by_alias=True)
        response["status"] = "NEED_DATA" if blockers else "OK"
        response["modelMeta"] = {
            "modelId": llm_result.model_id,
            "fallbackUsed": llm_result.fallback_used,
            "fallbackReason": llm_result.fallback_reason,
        }
        return response


class DecisionAgent:
    def __init__(self, model_router: ModelRouter, settings: Settings) -> None:
        self._model_router = model_router
        self._scoring_engine = TrustScoringEngine(settings=settings)

    async def run(
        self,
        agent_outputs: dict[str, Any],
        constraints: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        llm_result = await self._model_router.call(
            task_type="decision",
            payload={"prompt": "Create recommendation from scientific trust signals."},
            session_id=session_id,
        )

        scoring_result = self._scoring_engine.evaluate(
            agent_outputs=agent_outputs,
            constraints=constraints or {},
        )

        output = scoring_result.to_public_dict()
        output["modelMeta"] = {
            "modelId": llm_result.model_id,
            "fallbackUsed": llm_result.fallback_used,
            "fallbackReason": llm_result.fallback_reason,
        }
        return output
