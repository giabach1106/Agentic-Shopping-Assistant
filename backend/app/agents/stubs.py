from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from statistics import mean
from typing import Any
from urllib.parse import urlparse

from app.collectors.base import RealtimeCollector
from app.core.config import Settings
from app.core.model_router import ModelRouter
from app.memory.evidence_store import SQLiteEvidenceStore
from app.models.agent_outputs import PriceLogisticsOutput, VisualInsight
from app.models.planner import SearchConstraints
from app.orchestrator.domain_support import (
    canonicalize_category,
    constraint_match_score,
    infer_domain,
    title_matches_constraints,
)
from app.orchestrator.search_brief import SearchBrief
from app.rag.base import RetrievalDocument
from app.rag.providers import HybridRAGService
from app.services.review_analysis import ReviewEvidenceAnalyzer
from app.services.trust_scoring import TrustScoringEngine
from app.services.visual_analysis import VisualEvidenceAnalyzer
from app.tools.ui_executor import UIExecutionRequest, UIExecutor


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


_SUPPLEMENT_TITLE_KEYWORDS = (
    "whey",
    "isolate",
    "protein",
    "supplement",
    "creatine",
    "casein",
    "collagen",
    "pre workout",
    "pre-workout",
    "electrolyte",
    "vitamin",
    "omega",
    "probiotic",
    "bcaa",
    "eaa",
    "glutamine",
)

_OFF_TOPIC_PRODUCT_HINTS = (
    "nba",
    "doubleheader",
    "movie",
    "wedding",
    "iphone",
    "laptop",
)
_COMMERCE_SOURCES = {"amazon", "walmart", "ebay", "nutritionfaktory", "dps"}

_GENERIC_CATEGORY_PHRASES = {
    "another",
    "another one",
    "one",
    "it",
    "this",
    "that",
    "something",
}

_NOISE_TERMS = {
    "under",
    "over",
    "with",
    "without",
    "from",
    "that",
    "this",
    "best",
    "good",
    "days",
    "day",
    "stars",
    "star",
    "delivery",
    "delivered",
}

_TRACE_STATUS_MAP = {
    "ok": "ok",
    "warning": "warning",
    "blocked": "blocked",
    "skipped": "skipped",
    "error": "error",
    "failed": "error",
    "failure": "error",
    "exception": "error",
    "need_data": "warning",
    "needs_data": "warning",
}


def _normalize_trace_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return _TRACE_STATUS_MAP.get(normalized, "warning")


def _normalize_trace_event(item: Any, *, step_prefix: str = "") -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    raw_step = str(item.get("step") or "unknown").strip()
    step = f"{step_prefix}{raw_step}" if step_prefix else raw_step
    if not step:
        step = "unknown"
    detail = str(item.get("detail") or "").strip() or "No detail provided."
    return {
        "step": step,
        "status": _normalize_trace_status(item.get("status")),
        "detail": detail,
    }


def _normalize_url_for_key(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return ""
    parsed = urlparse(trimmed)
    normalized = parsed._replace(query="", fragment="")
    clean_path = re.sub(r"/ref=.*$", "", normalized.path).rstrip("/")
    normalized = normalized._replace(path=clean_path or "/")
    return normalized.geturl()


def _is_search_listing_url(value: str) -> bool:
    lower = value.lower()
    return ("/search?" in lower) or ("/sch/i.html" in lower)


def _canonical_title_signature(title: str) -> str:
    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", title.lower())
        if len(token) >= 3
        and token not in _NOISE_TERMS
        and token
    ]
    if not tokens:
        return ""
    return " ".join(tokens[:8])


def _is_product_title_noise(value: str) -> bool:
    title = re.sub(r"\s+", " ", value).strip().lower()
    if not title:
        return True
    if re.fullmatch(r"[0-9][0-9,]*\s+ratings?", title):
        return True
    if title.startswith("options:"):
        return True
    if title.startswith("sponsored"):
        return True
    if title in {"ratings", "global ratings", "stars", "star"}:
        return True
    return False


def _canonical_product_key(title: str, source_url: str) -> str:
    signature = _canonical_title_signature(title)
    normalized_url = _normalize_url_for_key(source_url)
    if signature:
        return signature
    return normalized_url


def _tokenize_terms(value: str) -> list[str]:
    return [
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) >= 3 and token not in _NOISE_TERMS
    ]


def _constraint_focus_terms(constraints: dict[str, Any]) -> list[str]:
    collected: list[str] = []
    category = str(constraints.get("category") or "").strip()
    if category:
        collected.extend(_tokenize_terms(category))

    for key in ("mustHave", "niceToHave"):
        values = constraints.get(key) or []
        if not isinstance(values, list):
            continue
        for value in values:
            text = str(value).strip()
            if text:
                collected.extend(_tokenize_terms(text))

    deduped: list[str] = []
    for item in collected:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _is_candidate_title_relevant(title: str, constraints: dict[str, Any]) -> bool:
    lower = title.lower()
    if _is_product_title_noise(lower):
        return False
    if any(hint in lower for hint in _OFF_TOPIC_PRODUCT_HINTS):
        return False
    return title_matches_constraints(title, constraints)


def _constraint_match_score(title: str, constraints: dict[str, Any]) -> int:
    return constraint_match_score(title, constraints)


def _normalize_delivery_preference(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _delivery_rank_penalty(
    shipping_eta: str,
    delivery_deadline: str | None,
) -> int:
    preference = _normalize_delivery_preference(delivery_deadline)
    if not preference:
        return 0
    shipping = str(shipping_eta or "").strip().lower()
    if not shipping or shipping == "unknown":
        return 2
    if preference in {"fast delivery", "today", "tomorrow"}:
        if any(token in shipping for token in ("same day", "same-day", "next day", "overnight", "1 day", "2 day", "2-day")):
            return 0
        if any(token in shipping for token in ("2-4 days", "3-4 days", "3-5 days")):
            return 1
        return 2
    if preference in {"this week", "this friday", "next friday"} or preference.startswith("this ") or preference.startswith("next "):
        if any(token in shipping for token in ("1-2 days", "2-4 days", "3-4 days", "3-5 days", "4-6 days", "this week")):
            return 0
        if any(token in shipping for token in ("5-7 days", "6-8 days")):
            return 1
        return 2
    return 0 if preference in shipping else 1


def _sanitize_collection_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    sanitized: dict[str, Any] = {}
    products: list[dict[str, Any]] = []
    for item in payload.get("products", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or _is_product_title_noise(title):
            continue
        if not url.startswith("http") or _is_search_listing_url(url):
            continue
        source = str(item.get("source") or "").strip().lower()
        if not source:
            continue

        avg_rating = float(item.get("avg_rating") or item.get("avgRating") or 0.0)
        if avg_rating < 0 or avg_rating > 5:
            avg_rating = 0.0
        rating_count = int(item.get("rating_count") or item.get("ratingCount") or 0)
        rating_count = max(0, rating_count)
        if avg_rating <= 0:
            rating_count = 0

        normalized = dict(item)
        normalized["source"] = source
        normalized["url"] = _normalize_url_for_key(url)
        normalized["title"] = title
        normalized["avg_rating"] = avg_rating
        normalized["rating_count"] = rating_count
        products.append(normalized)

    reviews = [
        dict(item)
        for item in payload.get("reviews", [])
        if isinstance(item, dict) and str(item.get("review_text") or "").strip()
    ]
    visuals = [
        dict(item)
        for item in payload.get("visuals", [])
        if isinstance(item, dict)
        and str(item.get("image_url") or item.get("imageUrl") or "").strip()
    ]
    trace = [
        dict(item)
        for item in payload.get("trace", [])
        if isinstance(item, dict)
    ]
    missing = sorted(
        {
            str(item).strip()
            for item in payload.get("missingEvidence", [])
            if str(item).strip()
        }
    )
    blocked = sorted(
        {
            str(item).strip().lower()
            for item in payload.get("blockedSources", [])
            if str(item).strip()
        }
    )
    source_health = dict(payload.get("sourceHealth") or {})
    crawl_meta = dict(payload.get("crawlMeta") or {})

    sanitized["products"] = products
    sanitized["reviews"] = reviews
    sanitized["visuals"] = visuals
    sanitized["trace"] = trace
    sanitized["missingEvidence"] = missing
    sanitized["blockedSources"] = blocked
    if source_health:
        sanitized["sourceHealth"] = source_health
    if crawl_meta:
        sanitized["crawlMeta"] = crawl_meta
    if not any([products, reviews, visuals, trace, missing, blocked, source_health, crawl_meta]):
        return {}
    return sanitized


def _strip_run_local_collection(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    stripped = dict(payload)
    stripped["trace"] = []
    stripped.pop("sourceHealth", None)
    stripped.pop("crawlMeta", None)
    return stripped


def _cache_trace_event(has_cache: bool) -> dict[str, Any]:
    return {
        "source": "cache",
        "step": "cache_lookup",
        "status": "ok" if has_cache else "warning",
        "detail": "Loaded stored evidence for this constraint set." if has_cache else "No cached evidence found.",
        "duration_ms": 0,
    }


class PlannerAgent:
    _critical_fields = ("category",)

    def __init__(self, model_router: ModelRouter) -> None:
        self._model_router = model_router

    async def run(
        self,
        message: str,
        history: list[dict[str, Any]],
        existing_constraints: dict[str, Any] | None = None,
        follow_up_count: int = 0,
        clarification_asked_count: int = 0,
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
        search_brief = SearchBrief.from_constraints(constraints_dict)
        search_ready = bool(constraints_dict.get("category"))

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
        clarification_pending = None
        clarification_actions: list[dict[str, Any]] = []
        next_clarification_count = clarification_asked_count
        existing_category = canonicalize_category(str((existing_constraints or {}).get("category") or "").strip())
        if search_ready and search_brief.category != existing_category:
            next_clarification_count = 0
        if needs_follow_up:
            missing_field = missing_fields[0]
            follow_up_question = self._build_follow_up_question(missing_field)
            next_follow_up_count = follow_up_count + 1
        elif len(missing_fields) == 0:
            next_follow_up_count = 0
            if next_clarification_count < 1:
                clarification_pending = search_brief.optional_clarification(constraints_dict)
                if clarification_pending:
                    next_clarification_count += 1
                    clarification_actions = self._clarification_actions(
                        field=str(clarification_pending.get("field") or ""),
                        domain=search_brief.domain,
                    )
        else:
            next_follow_up_count = follow_up_count

        return {
            "constraints": constraints_dict,
            "missingFields": missing_fields,
            "inferredFields": inferred_fields,
            "needsFollowUp": needs_follow_up,
            "followUpQuestion": follow_up_question,
            "followUpCount": next_follow_up_count,
            "clarificationPending": clarification_pending,
            "clarificationAskedCount": next_clarification_count,
            "clarificationActions": clarification_actions,
            "searchReady": search_ready,
            "searchBrief": search_brief.to_public_dict(),
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
            r"(?:need|want|looking for|find|buy|get)\s+(?:me\s+)?(?:an?\s+|some\s+)?"
            r"([a-z0-9][a-z0-9\-\s]{2,80}?)"
            r"(?=\s+(?:under|below|with|delivered|by|exclude|for|and)\b|[,.]|$)",
            lower,
        )
        if intent_match:
            candidate = intent_match.group(1).strip()
            candidate = re.sub(r"\s+", " ", candidate)
            candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate)
            if candidate in {
                "clean ingredients",
                "fast delivery",
                "delivery this week",
                "delivery window",
                "lumbar support",
                "adjustable armrests",
                "adjustable arms",
                "low lactose",
                "third party tested",
                "third-party tested",
            } or candidate.startswith("delivery "):
                candidate = ""
            if candidate in _GENERIC_CATEGORY_PHRASES:
                candidate = ""
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
                if stripped not in _GENERIC_CATEGORY_PHRASES:
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
            by_day_match = re.search(
                r"(?:by|before)\s+((?:this|next)\s+)?(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                lower,
            )
            if by_day_match:
                delivery_deadline = " ".join(
                    part.strip()
                    for part in (by_day_match.group(1) or "", by_day_match.group(2) or "")
                    if part and part.strip()
                )
        if delivery_deadline is None:
            in_days_match = re.search(r"(?:in|within)\s+(\d{1,2})\s+days?", lower)
            if in_days_match:
                delivery_deadline = f"in {int(in_days_match.group(1))} days"
        if delivery_deadline is None:
            direct_deadline_match = re.fullmatch(
                r"((?:this|next)\s+)?(today|tomorrow|this week|fast delivery|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                lower.strip(),
            )
            if direct_deadline_match:
                delivery_deadline = " ".join(
                    part.strip()
                    for part in (direct_deadline_match.group(1) or "", direct_deadline_match.group(2) or "")
                    if part and part.strip()
                )
        if delivery_deadline is None:
            if "this week" in lower:
                delivery_deadline = "this week"
            elif "fast delivery" in lower or "fast shipping" in lower:
                delivery_deadline = "fast delivery"

        must_have: list[str] = []
        if "ergonomic" in lower:
            must_have.append("ergonomic")
        if "dorm" in lower:
            must_have.append("dorm-friendly size")
        if "clean ingredients" in lower and "clean ingredients" not in must_have:
            must_have.append("clean ingredients")
        if "fast delivery" in lower and "fast delivery" not in must_have:
            must_have.append("fast delivery")
        supplement_signals = [
            ("third-party tested", "third-party tested"),
            ("third party tested", "third-party tested"),
            ("third party testing", "third-party tested"),
            ("low lactose", "low lactose"),
            ("lactose free", "low lactose"),
            ("whey isolate", "whey isolate"),
            ("grass fed", "grass-fed"),
            ("no sucralose", "no sucralose"),
            ("no artificial sweetener", "no artificial sweeteners"),
            ("no proprietary blend", "no proprietary blends"),
        ]
        for phrase, normalized in supplement_signals:
            if phrase in lower and normalized not in must_have:
                must_have.append(normalized)
        if "whey" in lower and "whey" not in must_have:
            must_have.append("whey")
        if "protein" in lower and "protein" not in must_have:
            must_have.append("protein")

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

    def _clarification_actions(self, *, field: str, domain: str) -> list[dict[str, Any]]:
        if field == "budgetMax":
            if domain == "chair":
                return [
                    {"id": "clarify_budget_150", "label": "Budget under $150", "message": "Budget under $150.", "kind": "reply", "style": "primary", "requiresConfirmation": False},
                    {"id": "clarify_budget_200", "label": "Budget under $200", "message": "Budget under $200.", "kind": "reply", "style": "secondary", "requiresConfirmation": False},
                ]
            if domain == "desk":
                return [
                    {"id": "clarify_budget_200", "label": "Budget under $200", "message": "Budget under $200.", "kind": "reply", "style": "primary", "requiresConfirmation": False},
                    {"id": "clarify_budget_300", "label": "Budget under $300", "message": "Budget under $300.", "kind": "reply", "style": "secondary", "requiresConfirmation": False},
                ]
            return [
                {"id": "clarify_budget_80", "label": "Budget under $80", "message": "Budget under $80.", "kind": "reply", "style": "primary", "requiresConfirmation": False},
                {"id": "clarify_budget_120", "label": "Budget under $120", "message": "Budget under $120.", "kind": "reply", "style": "secondary", "requiresConfirmation": False},
            ]
        if field == "minRating":
            return [
                {"id": "clarify_rating_4", "label": "Need 4+ stars", "message": "Minimum rating 4 stars.", "kind": "reply", "style": "secondary", "requiresConfirmation": False},
                {"id": "clarify_rating_45", "label": "Need 4.5+ stars", "message": "Minimum rating 4.5 stars.", "kind": "reply", "style": "subtle", "requiresConfirmation": False},
            ]
        if field == "deliveryDeadline":
            return [
                {"id": "clarify_delivery_week", "label": "Need it this week", "message": "Need delivery this week.", "kind": "reply", "style": "secondary", "requiresConfirmation": False},
                {"id": "clarify_delivery_fast", "label": "Need fast delivery", "message": "Need fast delivery.", "kind": "reply", "style": "subtle", "requiresConfirmation": False},
            ]
        if field == "mustHave" and domain == "chair":
            return [
                {"id": "clarify_chair_lumbar", "label": "Need lumbar support", "message": "Must have lumbar support.", "kind": "reply", "style": "secondary", "requiresConfirmation": False},
            ]
        if field == "mustHave" and domain == "desk":
            return [
                {"id": "clarify_desk_size", "label": "Need under 55 inches", "message": "Need a desk under 55 inches wide.", "kind": "reply", "style": "secondary", "requiresConfirmation": False},
            ]
        if field == "mustHave":
            return [
                {"id": "clarify_clean_ingredients", "label": "Need clean ingredients", "message": "Need clean ingredients.", "kind": "reply", "style": "secondary", "requiresConfirmation": False},
            ]
        return []


class CoverageAuditorAgent:
    def __init__(
        self,
        settings: Settings,
        evidence_store: SQLiteEvidenceStore,
    ) -> None:
        self._settings = settings
        self._evidence_store = evidence_store

    async def run(self, constraints: dict[str, Any]) -> dict[str, Any]:
        cached = await self._evidence_store.get_cached_collection(constraints)
        raw_cached_collection = dict(cached.get("collection") or {}) if cached else {}
        cached_collection = _strip_run_local_collection(
            _sanitize_collection_payload(raw_cached_collection)
        )
        cache_status = "hit" if cached_collection else "miss"
        if cached and cached_collection != raw_cached_collection:
            await self._evidence_store.upsert_cached_collection(
                constraints,
                cached_collection,
                self._build_stats(cached_collection),
            )

        search_brief = SearchBrief.from_constraints(constraints)
        query = search_brief.query_for("amazon")
        catalog_records = await self._evidence_store.list_catalog_records(
            query=query or None,
            limit=180,
        )
        catalog_collection = self._catalog_records_to_collection(catalog_records)
        catalog_status = "hit" if catalog_records else "miss"

        collection = _sanitize_collection_payload(
            self._merge_collections(cached_collection, catalog_collection)
        )
        collection["trace"] = [
            _cache_trace_event(bool(cached_collection)),
            *[
                item
                for item in collection.get("trace", [])
                if isinstance(item, dict)
            ],
        ]
        collection["crawlMeta"] = {
            "searchBrief": search_brief.to_public_dict(),
        }
        stats = self._build_stats(collection)
        sufficiency = self._evaluate_sufficiency(stats)
        source_coverage = self._compute_source_coverage(collection)
        blocked_commerce_sources = self._blocked_commerce_sources(collection)
        return {
            "status": "OK" if sufficiency["isSufficient"] else "NEED_DATA",
            "cacheStatus": cache_status,
            "catalogStatus": catalog_status,
            "sufficiency": sufficiency,
            "sourceCoverage": source_coverage,
            "commerceSourceCoverage": int(stats.get("commerceSourceCoverage", 0)),
            "reviewCount": int(stats.get("reviewCount", 0)),
            "ratingCount": int(stats.get("ratingCount", 0)),
            "ratedCandidateCount": int(stats.get("ratedCandidateCount", 0)),
            "ratedCoverageRatio": float(stats.get("ratedCoverageRatio", 0.0)),
            "freshnessSeconds": int(stats.get("freshnessSeconds", 999999)),
            "blockedCommerceSources": blocked_commerce_sources,
            "collection": collection,
        }

    def _catalog_records_to_collection(
        self,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        products: list[dict[str, Any]] = []
        reviews: list[dict[str, Any]] = []
        visuals: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = [
            {
                "source": "catalog",
                "step": "catalog_lookup",
                "status": "ok" if records else "warning",
                "detail": (
                    f"Loaded {len(records)} records from stored catalog."
                    if records
                    else "No matching catalog records found."
                ),
                "duration_ms": 0,
            }
        ]
        for item in records:
            source = str(item.get("source") or "unknown").strip().lower()
            url = _normalize_url_for_key(str(item.get("url") or "").strip())
            title = str(item.get("title") or "").strip()
            if not url or not title or _is_product_title_noise(title):
                continue
            retrieved_at = str(item.get("retrieved_at") or _now_iso())
            evidence_id = f"catalog::{hash(url)}"
            products.append(
                {
                    "source": source,
                    "url": url,
                    "title": title,
                    "price": float(item.get("price") or 0.0),
                    "avg_rating": float(item.get("rating") or 0.0),
                    "rating_count": int(item.get("rating_count") or 0),
                    "image_url": str(item.get("image_url") or "").strip() or None,
                    "shipping_eta": "unknown",
                    "return_policy": "unknown",
                    "seller_info": str(item.get("brand") or source).strip() or source,
                    "retrieved_at": retrieved_at,
                    "evidence_id": evidence_id,
                    "confidence_source": 0.86,
                    "raw_snapshot_ref": "catalog://record",
                }
            )
            snippets = item.get("review_snippets") or []
            if not snippets:
                fallback_snippet = str(item.get("ingredient_text") or "").strip()
                if not fallback_snippet:
                    fallback_snippet = f"Listing summary: {title}"
                snippets = [fallback_snippet[:320]]
            if isinstance(snippets, list):
                for index, snippet in enumerate(snippets[:2]):
                    text = str(snippet).strip()
                    if not text:
                        continue
                    reviews.append(
                        {
                            "source": source,
                            "url": url,
                            "review_id": f"{evidence_id}::review::{index}",
                            "rating": float(item.get("rating") or 0.0),
                            "review_text": text,
                            "timestamp": retrieved_at,
                            "helpful_votes": 0,
                            "verified_purchase": None,
                            "media_count": 0,
                            "retrieved_at": retrieved_at,
                            "evidence_id": f"{evidence_id}::review::{index}",
                            "confidence_source": 0.79,
                            "raw_snapshot_ref": "catalog://review",
                        }
                    )
            image_url = str(item.get("image_url") or "").strip()
            if image_url:
                visuals.append(
                    {
                        "source": source,
                        "url": url,
                        "image_url": image_url,
                        "caption": title[:180],
                        "retrieved_at": retrieved_at,
                        "evidence_id": f"{evidence_id}::image",
                        "confidence_source": 0.74,
                        "raw_snapshot_ref": "catalog://image",
                    }
                )
        return {
            "products": products,
            "reviews": reviews,
            "visuals": visuals,
            "trace": trace,
            "missingEvidence": [],
            "blockedSources": [],
        }

    def _merge_collections(
        self,
        left: dict[str, Any],
        right: dict[str, Any],
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for key in ("products", "reviews", "visuals"):
            merged[key] = self._merge_entry_list(
                left.get(key) if isinstance(left.get(key), list) else [],
                right.get(key) if isinstance(right.get(key), list) else [],
            )

        merged_trace = []
        if isinstance(left.get("trace"), list):
            merged_trace.extend(item for item in left["trace"] if isinstance(item, dict))
        if isinstance(right.get("trace"), list):
            merged_trace.extend(item for item in right["trace"] if isinstance(item, dict))
        merged["trace"] = merged_trace
        merged["missingEvidence"] = sorted(
            {
                str(item)
                for item in [*(left.get("missingEvidence") or []), *(right.get("missingEvidence") or [])]
                if str(item).strip()
            }
        )
        merged["blockedSources"] = sorted(
            {
                str(item)
                for item in [*(left.get("blockedSources") or []), *(right.get("blockedSources") or [])]
                if str(item).strip()
            }
        )
        return merged

    def _merge_entry_list(
        self,
        left_entries: list[Any],
        right_entries: list[Any],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*left_entries, *right_entries]:
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

    def _compute_commerce_source_coverage(self, payload: dict[str, Any]) -> int:
        sources: set[str] = set()
        entries = payload.get("products")
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or "").strip().lower()
                if source in _COMMERCE_SOURCES:
                    sources.add(source)
        return len(sources)

    def _blocked_commerce_sources(self, payload: dict[str, Any]) -> list[str]:
        blocked = payload.get("blockedSources")
        if not isinstance(blocked, list):
            return []
        return sorted(
            {
                str(item).strip().lower()
                for item in blocked
                if str(item).strip().lower() in _COMMERCE_SOURCES
            }
        )

    def _build_stats(self, payload: dict[str, Any]) -> dict[str, Any]:
        products = payload.get("products", []) if isinstance(payload.get("products"), list) else []
        reviews = payload.get("reviews", []) if isinstance(payload.get("reviews"), list) else []
        blocked_commerce_sources = self._blocked_commerce_sources(payload)
        product_count = len([item for item in products if isinstance(item, dict)])
        review_count = len([item for item in reviews if isinstance(item, dict)])
        rating_count = sum(
            int(item.get("rating_count") or item.get("ratingCount") or 0)
            for item in products
            if isinstance(item, dict)
        )
        rated_candidate_count = sum(
            1
            for item in products
            if isinstance(item, dict)
            and (
                float(item.get("avg_rating") or item.get("avgRating") or 0.0) > 0
                or int(item.get("rating_count") or item.get("ratingCount") or 0) > 0
            )
        )
        commerce_source_coverage = self._compute_commerce_source_coverage(payload)
        rated_coverage_ratio = (
            round(rated_candidate_count / product_count, 4)
            if product_count > 0
            else 0.0
        )
        freshness_seconds = self._freshness_seconds(payload)
        return {
            "sourceCoverage": self._compute_source_coverage(payload),
            "commerceSourceCoverage": commerce_source_coverage,
            "productCount": product_count,
            "reviewCount": review_count,
            "ratingCount": rating_count,
            "ratedCandidateCount": rated_candidate_count,
            "ratedCoverageRatio": rated_coverage_ratio,
            "freshnessSeconds": freshness_seconds,
            "blockedCommerceSources": blocked_commerce_sources,
        }

    def _evaluate_sufficiency(self, stats: dict[str, Any]) -> dict[str, Any]:
        missing: list[str] = []
        source_coverage = int(stats.get("commerceSourceCoverage", 0))
        product_count = int(stats.get("productCount", 0))
        review_count = int(stats.get("reviewCount", 0))
        rating_count = int(stats.get("ratingCount", 0))
        rated_coverage_ratio = float(stats.get("ratedCoverageRatio", 0.0))
        blocked_commerce_sources = [
            str(item).strip().lower()
            for item in (stats.get("blockedCommerceSources") or [])
            if str(item).strip().lower() in _COMMERCE_SOURCES
        ]
        effective_source_coverage = source_coverage + len(blocked_commerce_sources)
        has_catalog_depth = (
            product_count >= 10
            and rated_coverage_ratio >= 0.6
        )

        if source_coverage < 1:
            missing.append("sourceCoverage")
        elif (
            source_coverage == 1
            and product_count < 10
            and self._settings.min_source_coverage > 1
        ):
            missing.append("sourceCoverage")
        elif effective_source_coverage < self._settings.min_source_coverage and not has_catalog_depth:
            missing.append("sourceCoverage")
        if not has_catalog_depth and review_count < self._settings.min_review_count:
            missing.append("reviewCount")
        if not has_catalog_depth and rating_count < self._settings.min_rating_count:
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

    async def run(
        self,
        constraints: dict[str, Any],
        *,
        seed_collection: dict[str, Any] | None = None,
        coverage_audit: dict[str, Any] | None = None,
        force_collect: bool = False,
    ) -> dict[str, Any]:
        cached = await self._evidence_store.get_cached_collection(constraints)
        raw_cached_collection = dict(cached.get("collection") or {}) if cached else {}
        cached_collection = _strip_run_local_collection(
            _sanitize_collection_payload(raw_cached_collection)
        )
        cached_stats = dict(cached.get("stats") or {}) if cached else {}
        if cached and cached_collection != raw_cached_collection:
            await self._evidence_store.upsert_cached_collection(
                constraints,
                cached_collection,
                self._build_stats(cached_collection),
            )

        search_brief = SearchBrief.from_constraints(constraints)
        collection = _sanitize_collection_payload(
            self._merge_collections(
                _sanitize_collection_payload(dict(seed_collection or {})),
                dict(cached_collection or {}),
            )
        )
        crawl_meta = dict(collection.get("crawlMeta") or {})
        crawl_meta["searchBrief"] = search_brief.to_public_dict()
        collection["crawlMeta"] = crawl_meta
        stats = self._build_stats(collection) if collection else dict(cached_stats)
        sufficiency = dict((coverage_audit or {}).get("sufficiency") or {})
        if not sufficiency:
            sufficiency = self._evaluate_sufficiency(stats)

        cache_status = str((coverage_audit or {}).get("cacheStatus") or ("hit" if cached_collection else "miss"))
        catalog_status = str((coverage_audit or {}).get("catalogStatus") or "unknown")
        crawl_performed = False

        if force_collect or not sufficiency["isSufficient"]:
            result = await self._collector.collect(constraints)
            fresh_payload = _sanitize_collection_payload(result.to_public_dict())
            collection = _sanitize_collection_payload(self._merge_collections(collection, fresh_payload))
            crawl_meta = dict(collection.get("crawlMeta") or {})
            crawl_meta["searchBrief"] = search_brief.to_public_dict()
            collection["crawlMeta"] = crawl_meta
            stats = self._build_stats(collection)
            sufficiency = self._evaluate_sufficiency(stats)
            await self._evidence_store.upsert_cached_collection(
                constraints,
                _strip_run_local_collection(collection),
                stats,
            )
            cache_status = "forced_refresh" if force_collect else ("merged" if cached_collection else "miss")
            crawl_performed = True

        source_coverage = self._compute_source_coverage(collection)
        blocked_commerce_sources = self._blocked_commerce_sources(collection)
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
            "commerceSourceCoverage": int(stats.get("commerceSourceCoverage", 0)),
            "reviewCount": int(stats.get("reviewCount", 0)),
            "ratingCount": int(stats.get("ratingCount", 0)),
            "ratedCandidateCount": int(stats.get("ratedCandidateCount", 0)),
            "ratedCoverageRatio": float(stats.get("ratedCoverageRatio", 0.0)),
            "freshnessSeconds": int(stats.get("freshnessSeconds", 999999)),
            "missingEvidence": missing_evidence,
            "blockedSources": collection.get("blockedSources", []),
            "blockedCommerceSources": blocked_commerce_sources,
            "sourceHealth": dict(collection.get("sourceHealth") or {}),
            "crawlMeta": dict(collection.get("crawlMeta") or {}),
            "collection": collection,
            "cacheStatus": cache_status,
            "catalogStatus": catalog_status,
            "crawlPerformed": crawl_performed,
            "sufficiency": sufficiency,
            "coverageAudit": {
                "isSufficient": bool(sufficiency.get("isSufficient")),
                "missing": [str(item) for item in sufficiency.get("missing", [])],
                "sourceCoverage": source_coverage,
                "commerceSourceCoverage": int(stats.get("commerceSourceCoverage", 0)),
                "reviewCount": int(stats.get("reviewCount", 0)),
                "ratingCount": int(stats.get("ratingCount", 0)),
                "ratedCandidateCount": int(stats.get("ratedCandidateCount", 0)),
                "ratedCoverageRatio": float(stats.get("ratedCoverageRatio", 0.0)),
                "freshnessSeconds": int(stats.get("freshnessSeconds", 999999)),
                "blockedCommerceSources": blocked_commerce_sources,
                "cacheStatus": cache_status,
                "catalogStatus": catalog_status,
                "crawlPerformed": crawl_performed,
            },
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

    def _compute_commerce_source_coverage(self, payload: dict[str, Any]) -> int:
        sources: set[str] = set()
        entries = payload.get("products")
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or "").strip().lower()
                if source in _COMMERCE_SOURCES:
                    sources.add(source)
        return len(sources)

    def _blocked_commerce_sources(self, payload: dict[str, Any]) -> list[str]:
        blocked = payload.get("blockedSources")
        if not isinstance(blocked, list):
            return []
        return sorted(
            {
                str(item).strip().lower()
                for item in blocked
                if str(item).strip().lower() in _COMMERCE_SOURCES
            }
        )

    def _normalize_missing_evidence(self, payload: dict[str, Any]) -> list[str]:
        missing = list(payload.get("missingEvidence") or [])
        product_sources = {
            str(item.get("source") or "").strip().lower()
            for item in payload.get("products", [])
            if isinstance(item, dict)
        }
        # Product-list requirements are source-agnostic: if at least one
        # commerce source yielded products, don't block on per-source misses.
        if product_sources.intersection(_COMMERCE_SOURCES):
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
        source_health = dict(cached.get("sourceHealth") or {})
        source_health.update(dict(fresh.get("sourceHealth") or {}))
        if source_health:
            merged["sourceHealth"] = source_health
        crawl_meta = dict(cached.get("crawlMeta") or {})
        crawl_meta.update(dict(fresh.get("crawlMeta") or {}))
        if crawl_meta:
            merged["crawlMeta"] = crawl_meta
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
        blocked_commerce_sources = self._blocked_commerce_sources(payload)
        product_count = len([item for item in products if isinstance(item, dict)])
        review_count = len([item for item in reviews if isinstance(item, dict)])
        rating_count = sum(
            int(item.get("rating_count") or item.get("ratingCount") or 0)
            for item in products
            if isinstance(item, dict)
        )
        rated_candidate_count = sum(
            1
            for item in products
            if isinstance(item, dict)
            and (
                float(item.get("avg_rating") or item.get("avgRating") or 0.0) > 0
                or int(item.get("rating_count") or item.get("ratingCount") or 0) > 0
            )
        )
        rated_coverage_ratio = (
            round(rated_candidate_count / product_count, 4)
            if product_count > 0
            else 0.0
        )
        freshness_seconds = self._freshness_seconds(payload)
        return {
            "sourceCoverage": self._compute_source_coverage(payload),
            "commerceSourceCoverage": self._compute_commerce_source_coverage(payload),
            "productCount": product_count,
            "reviewCount": review_count,
            "ratingCount": rating_count,
            "ratedCandidateCount": rated_candidate_count,
            "ratedCoverageRatio": rated_coverage_ratio,
            "freshnessSeconds": freshness_seconds,
            "blockedCommerceSources": blocked_commerce_sources,
        }

    def _evaluate_sufficiency(self, stats: dict[str, Any]) -> dict[str, Any]:
        missing: list[str] = []
        source_coverage = int(stats.get("commerceSourceCoverage", 0))
        product_count = int(stats.get("productCount", 0))
        rated_coverage_ratio = float(stats.get("ratedCoverageRatio", 0.0))
        blocked_commerce_sources = [
            str(item).strip().lower()
            for item in (stats.get("blockedCommerceSources") or [])
            if str(item).strip().lower() in _COMMERCE_SOURCES
        ]
        effective_source_coverage = source_coverage + len(blocked_commerce_sources)
        has_catalog_depth = product_count >= 10 and rated_coverage_ratio >= 0.6
        if source_coverage < 1:
            missing.append("sourceCoverage")
        elif (
            source_coverage == 1
            and product_count < 10
            and self._settings.min_source_coverage > 1
        ):
            missing.append("sourceCoverage")
        elif effective_source_coverage < self._settings.min_source_coverage and not has_catalog_depth:
            missing.append("sourceCoverage")
        if not has_catalog_depth and int(stats.get("reviewCount", 0)) < self._settings.min_review_count:
            missing.append("reviewCount")
        if not has_catalog_depth and int(stats.get("ratingCount", 0)) < self._settings.min_rating_count:
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

        domain = infer_domain(str(constraints.get("category") or ""))
        if domain in {"chair", "desk"}:
            aspects = {
                "comfort": 0.0,
                "assembly": 0.0,
                "durability": 0.0,
                "price": 0.0,
                "delivery": 0.0,
            }
            keywords = {
                "comfort": ("comfort", "ergonomic", "lumbar", "support", "posture", "stable"),
                "assembly": ("assembly", "assemble", "instructions", "screws", "setup"),
                "durability": ("durable", "sturdy", "wobble", "solid", "material", "frame"),
                "price": ("price", "value", "expensive", "cheap", "cost"),
                "delivery": ("ship", "delivery", "arrive", "late"),
            }
        else:
            aspects = {
                "digestibility": 0.0,
                "mixability": 0.0,
                "taste": 0.0,
                "ingredientQuality": 0.0,
                "priceValue": 0.0,
                "delivery": 0.0,
            }
            keywords = {
                "digestibility": ("digest", "bloat", "stomach", "lactose", "tolerate"),
                "mixability": ("mix", "clump", "texture", "shaker", "foam"),
                "taste": ("taste", "flavor", "sweet", "aftertaste"),
                "ingredientQuality": ("ingredient", "third-party", "tested", "clean label", "sucralose", "additive"),
                "priceValue": ("price", "value", "expensive", "cheap", "cost"),
                "delivery": ("ship", "delivery", "arrive", "late"),
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

        source_priority = {"amazon": 0, "walmart": 1, "ebay": 2, "nutritionfaktory": 3, "dps": 4}
        tier_rules: list[tuple[str, float]] = [
            ("strict", 1.0),
            ("soft_5", 1.05),
            ("soft_10", 1.10),
            ("soft_15", 1.15),
        ]
        tier_priority = {name: index for index, (name, _) in enumerate(tier_rules)}
        ranked_candidates: list[tuple[tuple[int, int, int, float, float, int], dict[str, Any]]] = []
        candidates: list[dict[str, Any]] = []
        best_candidate_by_key: dict[str, tuple[tuple[int, int, int, float, float, int], dict[str, Any]]] = {}
        budget_max = constraints.get("budgetMax")
        try:
            budget_limit = float(budget_max) if budget_max is not None else None
        except (TypeError, ValueError):
            budget_limit = None
        min_rating_raw = constraints.get("minRating")
        try:
            min_rating = float(min_rating_raw) if min_rating_raw is not None else None
        except (TypeError, ValueError):
            min_rating = None
        if isinstance(collection, dict):
            for item in collection.get("products", []):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url.startswith("http"):
                    continue
                if _is_search_listing_url(url):
                    continue
                title = str(item.get("title") or "").strip()
                if not title or title.lower().startswith("unknown"):
                    continue
                if not _is_candidate_title_relevant(title, constraints):
                    continue
                source = str(item.get("source") or "").strip().lower()
                rating = float(item.get("avg_rating") or 0.0)
                price = float(item.get("price") or 0.0)
                if price <= 0:
                    continue
                if min_rating is not None and (rating <= 0 or rating < min_rating):
                    continue
                match_score = _constraint_match_score(title, constraints)
                if match_score <= 0:
                    continue
                constraint_tier = "strict"
                if budget_limit is not None:
                    matched_tier = next(
                        (
                            tier_name
                            for tier_name, multiplier in tier_rules
                            if price <= (budget_limit * multiplier)
                        ),
                        None,
                    )
                    if matched_tier is None:
                        continue
                    constraint_tier = matched_tier
                shipping_eta = str(item.get("shipping_eta") or "unknown")
                delivery_penalty = _delivery_rank_penalty(
                    shipping_eta=shipping_eta,
                    delivery_deadline=str(constraints.get("deliveryDeadline") or ""),
                )
                normalized_url = _normalize_url_for_key(url)
                canonical_key = _canonical_product_key(title, normalized_url)
                rating_for_sort = rating if rating > 0 else 0.0
                rank_key = (
                    tier_priority.get(constraint_tier, 99),
                    -match_score,
                    delivery_penalty,
                    -rating_for_sort,
                    price,
                    source_priority.get(source, 99),
                )
                candidate = {
                    "title": title,
                    "sourceUrl": normalized_url or url,
                    "price": price,
                    "rating": rating if rating > 0 else None,
                    "shippingETA": shipping_eta,
                    "returnPolicy": str(item.get("return_policy") or "unknown"),
                    "checkoutReady": False,
                    "evidenceRefs": [str(item.get("evidence_id") or "").strip()],
                    "constraintTier": constraint_tier,
                    "constraintRelaxed": constraint_tier != "strict",
                }
                existing = best_candidate_by_key.get(canonical_key)
                if existing is None or rank_key < existing[0]:
                    if existing is not None:
                        existing_refs = existing[1].get("evidenceRefs", [])
                        merged_refs = [
                            *[
                                ref
                                for ref in candidate["evidenceRefs"]
                                if ref and ref not in existing_refs
                            ],
                            *[ref for ref in existing_refs if ref],
                        ]
                        candidate["evidenceRefs"] = merged_refs
                    best_candidate_by_key[canonical_key] = (rank_key, candidate)
                elif existing is not None:
                    existing_refs = existing[1].get("evidenceRefs", [])
                    for ref in candidate["evidenceRefs"]:
                        if ref and ref not in existing_refs:
                            existing_refs.append(ref)
                    existing[1]["evidenceRefs"] = existing_refs

        if best_candidate_by_key:
            ranked_candidates = sorted(
                best_candidate_by_key.values(),
                key=lambda entry: entry[0],
            )
            candidates = [item for _, item in ranked_candidates][:10]

        if self._runtime_mode != "prod" and len(candidates) == 0:
            fallback_candidates = execution_result.to_public_dict().get("candidates", [])
            deduped_fallback: dict[str, dict[str, Any]] = {}
            for item in fallback_candidates:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                source_url = str(item.get("sourceUrl") or "").strip()
                if not title or not source_url:
                    continue
                key = _canonical_product_key(title, source_url)
                if key not in deduped_fallback:
                    fallback = dict(item)
                    fallback["constraintTier"] = str(fallback.get("constraintTier") or "strict")
                    fallback["constraintRelaxed"] = bool(fallback.get("constraintRelaxed") or False)
                    deduped_fallback[key] = fallback
            candidates = list(deduped_fallback.values())[:10]

        blockers = list(execution_result.blockers)
        checkout_readiness = (
            "live"
            if self._ui_executor_backend != "mock"
            else "mock"
        )
        if self._runtime_mode == "prod" and len(candidates) == 0:
            blockers.append("missing_realtime_products")

        raw_trace = execution_result.to_public_dict().get("executionTrace", [])
        trace = [
            event
            for event in (
                _normalize_trace_event(item)
                for item in (raw_trace if isinstance(raw_trace, list) else [])
            )
            if event is not None
        ]
        if isinstance(collection, dict):
            collect_trace = collection.get("trace", [])
            if isinstance(collect_trace, list):
                trace = [
                    *[
                        event
                        for item in collect_trace
                        for event in [_normalize_trace_event(item, step_prefix="collect::")]
                        if event is not None
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
        response["checkoutReadiness"] = checkout_readiness
        response["candidateCount"] = len(candidates)
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
