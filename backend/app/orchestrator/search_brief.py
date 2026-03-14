from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.orchestrator.domain_support import canonicalize_category, infer_domain, normalize_lookup

_COMMERCE_SOURCES = ("amazon", "ebay", "walmart", "nutritionfaktory", "dps")
_REVIEW_SOURCES = ("reddit",)
_VISUAL_SOURCES = ("tiktok",)
_SOURCE_HINTS: dict[str, dict[str, tuple[str, ...]]] = {
    "chair": {
        "amazon": ("ergonomic", "office chair"),
        "ebay": ("adjustable", "lumbar"),
        "walmart": ("mesh", "office chair"),
        "reddit": ("review", "office chair"),
        "tiktok": ("setup", "ergonomic chair"),
    },
    "desk": {
        "amazon": ("study desk", "home office"),
        "ebay": ("writing desk", "storage"),
        "walmart": ("desk", "home office"),
        "reddit": ("review", "desk"),
        "tiktok": ("desk setup", "workspace"),
    },
    "supplement": {
        "amazon": ("whey isolate", "protein"),
        "ebay": ("whey isolate",),
        "walmart": ("protein isolate",),
        "nutritionfaktory": ("whey isolate", "protein"),
        "dps": ("whey isolate", "protein"),
        "reddit": ("review", "supplement"),
        "tiktok": ("review", "supplement"),
    },
}
_DELIVERY_HINTS = {
    "fast delivery": ("fast shipping", "prime"),
    "this week": ("this week", "fast shipping"),
    "today": ("same day", "same-day"),
    "tomorrow": ("next day", "overnight"),
}
_STOPWORDS = {
    "for",
    "the",
    "and",
    "with",
    "that",
    "this",
    "best",
    "good",
    "product",
    "products",
    "find",
    "want",
    "need",
    "looking",
    "buy",
    "get",
    "shop",
    "shopping",
}


def _dedupe_phrases(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = normalize_lookup(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _compose_query(values: list[str]) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for token in _tokenize_phrase(raw):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)
    return " ".join(tokens).strip()


def _tokenize_phrase(value: str) -> list[str]:
    tokens: list[str] = []
    for token in normalize_lookup(value).split():
        if len(token) < 3 or token in _STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _delivery_terms(deadline: str | None) -> list[str]:
    normalized = normalize_lookup(deadline or "")
    if not normalized:
        return []
    if normalized in _DELIVERY_HINTS:
        return list(_DELIVERY_HINTS[normalized])
    if normalized.startswith("this ") or normalized.startswith("next "):
        return [normalized]
    if normalized in {"today", "tomorrow", "this week", "fast delivery"}:
        return [normalized]
    return [normalized]


def _domain_specific_preference(domain: str, must_have: list[str]) -> str | None:
    if must_have:
        return None
    if domain == "chair":
        return "lumbar support or adjustable arms"
    if domain == "desk":
        return "size, storage, or standing height"
    if domain == "supplement":
        return "ingredient preference or protein type"
    return None


@dataclass(slots=True)
class SearchBrief:
    category: str
    domain: str
    core_terms: list[str]
    optional_terms: list[str]
    delivery_terms: list[str]
    query_variants: dict[str, str]
    normalized_constraints: dict[str, Any]

    @classmethod
    def from_constraints(cls, constraints: dict[str, Any]) -> "SearchBrief":
        normalized_constraints = dict(constraints)
        category = canonicalize_category(str(constraints.get("category") or "").strip()) or "product"
        normalized_constraints["category"] = category
        domain = infer_domain(category)
        must_have = _dedupe_phrases([str(item) for item in (constraints.get("mustHave") or [])])
        nice_to_have = _dedupe_phrases([str(item) for item in (constraints.get("niceToHave") or [])])
        delivery_terms = _delivery_terms(str(constraints.get("deliveryDeadline") or ""))
        core_terms = _dedupe_phrases([category, *must_have])
        optional_terms = _dedupe_phrases([*nice_to_have[:2], *_SOURCE_HINTS.get(domain, {}).get("amazon", ())[:1]])
        query_variants = cls._build_query_variants(
            domain=domain,
            category=category,
            core_terms=core_terms,
            optional_terms=optional_terms,
            delivery_terms=delivery_terms,
        )
        return cls(
            category=category,
            domain=domain,
            core_terms=core_terms,
            optional_terms=optional_terms,
            delivery_terms=delivery_terms,
            query_variants=query_variants,
            normalized_constraints=normalized_constraints,
        )

    @staticmethod
    def _build_query_variants(
        *,
        domain: str,
        category: str,
        core_terms: list[str],
        optional_terms: list[str],
        delivery_terms: list[str],
    ) -> dict[str, str]:
        base_terms = _dedupe_phrases([category, *core_terms, *optional_terms])
        variants: dict[str, str] = {}
        for source in (*_COMMERCE_SOURCES, *_REVIEW_SOURCES, *_VISUAL_SOURCES):
            source_terms = list(base_terms)
            source_terms.extend(_SOURCE_HINTS.get(domain, {}).get(source, ()))
            if source in _REVIEW_SOURCES:
                source_terms.append("review")
            if source in _VISUAL_SOURCES:
                source_terms.append("review" if domain == "supplement" else "setup")
            if source in _COMMERCE_SOURCES:
                source_terms.extend(delivery_terms[:1])
            variants[source] = _compose_query(source_terms) or category
        variants["default"] = variants.get("amazon") or _compose_query(base_terms) or category
        return variants

    def query_for(self, source: str) -> str:
        return self.query_variants.get(source, self.query_variants.get("default", self.category))

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "domain": self.domain,
            "coreTerms": list(self.core_terms),
            "optionalTerms": list(self.optional_terms),
            "deliveryTerms": list(self.delivery_terms),
            "queryVariants": dict(self.query_variants),
        }

    def optional_clarification(self, constraints: dict[str, Any]) -> dict[str, Any] | None:
        if constraints.get("budgetMax") in (None, ""):
            return {
                "field": "budgetMax",
                "prompt": "Optional: what budget cap should I target while I keep searching?",
                "example": "Budget under $150.",
            }
        if constraints.get("minRating") in (None, ""):
            return {
                "field": "minRating",
                "prompt": "Optional: do you want me to prefer or enforce any minimum star rating?",
                "example": "Minimum rating 4 stars.",
            }
        if str(constraints.get("deliveryDeadline") or "").strip() == "":
            return {
                "field": "deliveryDeadline",
                "prompt": "Optional: is there a delivery window I should bias for?",
                "example": "Need delivery this week.",
            }
        preference = _domain_specific_preference(self.domain, list(constraints.get("mustHave") or []))
        if preference:
            return {
                "field": "mustHave",
                "prompt": f"Optional: tell me one preference, such as {preference}.",
                "example": preference,
            }
        return None
