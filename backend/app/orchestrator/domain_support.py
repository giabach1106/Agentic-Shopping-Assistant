from __future__ import annotations

import re
import unicodedata
from typing import Any

SUPPORTED_LIVE_DOMAINS = {"supplement", "chair", "desk"}
FURNITURE_DOMAINS = {"chair", "desk"}

_SUPPLEMENT_KEYWORDS = (
    "whey",
    "protein",
    "isolate",
    "supplement",
    "creatine",
    "pre workout",
    "pre-workout",
    "casein",
    "collagen",
    "electrolyte",
    "vitamin",
    "omega",
    "probiotic",
    "bcaa",
    "eaa",
    "glutamine",
)
_CHAIR_KEYWORDS = (
    "chair",
    "office chair",
    "desk chair",
    "ergonomic chair",
    "gaming chair",
    "mesh chair",
    "lumbar",
    "armrest",
    "seat",
    "ghe",
)
_DESK_KEYWORDS = (
    "desk",
    "study desk",
    "writing desk",
    "standing desk",
    "computer desk",
    "office desk",
    "workstation",
    "ban hoc",
    "ban lam viec",
)
_OFF_TOPIC_HINTS = (
    "nba",
    "doubleheader",
    "movie",
    "wedding",
    "iphone",
    "politics",
    "news",
)
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
    "rating",
    "budget",
    "price",
}
_GENERIC_CATEGORY_PHRASES = {
    "a product",
    "product",
    "something",
    "something good",
    "help finding a product",
    "finding a product",
    "shopping help",
    "help shopping",
    "recommendation",
}
_CHAIR_NEGATIVE_HINTS = (
    "chair cover",
    "seat cover",
    "wheel set",
    "caster",
    "arm pad",
    "replacement",
    "chair mat",
)
_DESK_NEGATIVE_HINTS = (
    "wire organizer",
    "organizer",
    "power strip holder",
    "tray",
    "mesh net",
    "clamp",
    "desk mat",
    "converter accessory",
)
_DESK_POSITIVE_NOUNS = (
    "desk",
    "workstation",
    "table",
    "frame",
    "sit stand",
    "standing",
)
_DESK_ACCESSORY_PHRASES = (
    "under desk",
    "for desk",
    "desk accessory",
    "desk mount",
)
_WIDTH_PATTERNS = (
    r"([0-9]{2,3}(?:\.[0-9]+)?)\s*(?:\"|inches|inch)\s*(?:wide|width|w)?",
    r"(?:wide|width)\s*(?:of\s*)?([0-9]{2,3}(?:\.[0-9]+)?)\s*(?:\"|inches|inch)?",
)


def normalize_lookup(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def infer_domain(category: str | None) -> str:
    text = normalize_lookup(category or "")
    if not text:
        return "generic"
    if any(token in text for token in _SUPPLEMENT_KEYWORDS):
        return "supplement"
    if any(token in text for token in _CHAIR_KEYWORDS):
        return "chair"
    if any(token in text for token in _DESK_KEYWORDS):
        return "desk"
    return "generic"


def support_level_for_domain(domain: str) -> str:
    return "live_analysis" if domain in SUPPORTED_LIVE_DOMAINS else "discovery_only"


def analysis_mode_for_domain(domain: str) -> str:
    if domain == "supplement":
        return "supplement"
    if domain in FURNITURE_DOMAINS:
        return "furniture"
    return "generic"


def canonicalize_category(value: str | None) -> str | None:
    text = normalize_lookup(value or "")
    if not text:
        return None
    domain = infer_domain(text)
    if domain == "desk":
        if "standing" in text:
            return "standing desk"
        if "study" in text or "ban hoc" in text:
            return "study desk"
        return "desk"
    if domain == "chair":
        if "gaming" in text:
            return "gaming chair"
        if any(token in text for token in ("ergonomic", "lumbar", "desk", "office", "study", "ghe")):
            return "ergonomic chair"
        return "chair"
    return text


def domain_hints_for(domain: str) -> tuple[str, ...]:
    if domain == "supplement":
        return _SUPPLEMENT_KEYWORDS
    if domain == "chair":
        return _CHAIR_KEYWORDS
    if domain == "desk":
        return _DESK_KEYWORDS
    return ()


def category_focus_terms(constraints: dict[str, Any]) -> list[str]:
    values: list[str] = []
    category = canonicalize_category(str(constraints.get("category") or "").strip())
    if category:
        values.extend(_tokenize_terms(category))
    deduped: list[str] = []
    for item in values:
        if item not in deduped:
            deduped.append(item)
    return deduped


def preference_terms(constraints: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("mustHave", "niceToHave"):
        raw = constraints.get(key) or []
        if not isinstance(raw, list):
            continue
        for item in raw:
            values.extend(_tokenize_terms(str(item)))
    deduped: list[str] = []
    for item in values:
        if item not in deduped:
            deduped.append(item)
    return deduped


def width_constraints(constraints: dict[str, Any]) -> tuple[float | None, float | None]:
    minimum = constraints.get("widthMinInches")
    maximum = constraints.get("widthMaxInches")
    try:
        width_min = float(minimum) if minimum not in (None, "") else None
    except (TypeError, ValueError):
        width_min = None
    try:
        width_max = float(maximum) if maximum not in (None, "") else None
    except (TypeError, ValueError):
        width_max = None
    return width_min, width_max


def extract_width_inches(text: str) -> float | None:
    lowered = normalize_lookup(text)
    for pattern in _WIDTH_PATTERNS:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        try:
            return float(match.group(1))
        except ValueError:
            continue
    return None


def title_violates_domain_constraints(title: str, constraints: dict[str, Any]) -> bool:
    lower = normalize_lookup(title)
    domain = infer_domain(str(constraints.get("category") or ""))
    if domain == "chair" and any(token in lower for token in _CHAIR_NEGATIVE_HINTS):
        return True
    if domain == "desk":
        has_core_desk_noun = any(
            token in lower
            for token in ("standing desk", "computer desk", "writing desk", "study desk", "office desk", "desk frame", "workstation", "sit stand", "table")
        )
        has_generic_desk_noun = "desk" in lower and not any(phrase in lower for phrase in _DESK_ACCESSORY_PHRASES)
        has_product_signal = has_core_desk_noun or has_generic_desk_noun
        if any(token in lower for token in _DESK_NEGATIVE_HINTS) and not has_product_signal:
            return True
        category = normalize_lookup(str(constraints.get("category") or ""))
        if "standing desk" in category:
            if not has_product_signal:
                return True
        width_min, width_max = width_constraints(constraints)
        extracted_width = extract_width_inches(lower)
        if extracted_width is not None:
            if width_min is not None and extracted_width < width_min:
                return True
            if width_max is not None and extracted_width > width_max:
                return True
    return False


def title_matches_constraints(title: str, constraints: dict[str, Any]) -> bool:
    lower = normalize_lookup(title)
    if not lower:
        return False
    if any(hint in lower for hint in _OFF_TOPIC_HINTS):
        return False
    if title_violates_domain_constraints(lower, constraints):
        return False

    domain = infer_domain(str(constraints.get("category") or ""))
    hints = domain_hints_for(domain)
    if hints and not any(token in lower for token in hints):
        return False

    focus_terms = category_focus_terms(constraints)
    if focus_terms and not any(term in lower for term in focus_terms):
        if not any(token in lower for token in hints):
            return False

    excludes = constraints.get("exclude") or []
    if isinstance(excludes, list):
        for value in excludes:
            text = normalize_lookup(str(value))
            if text and text in lower:
                return False
    return True


def constraint_match_score(title: str, constraints: dict[str, Any]) -> int:
    lower = normalize_lookup(title)
    if title_violates_domain_constraints(lower, constraints):
        return 0
    domain = infer_domain(str(constraints.get("category") or ""))
    hints = domain_hints_for(domain)
    score = 2 if any(token in lower for token in hints) else 0
    for term in category_focus_terms(constraints):
        if term in lower:
            score += 2
    for term in preference_terms(constraints):
        if term in lower:
            score += 1
    width_min, width_max = width_constraints(constraints)
    extracted_width = extract_width_inches(lower)
    if extracted_width is not None:
        if width_min is not None and extracted_width >= width_min:
            score += 2
        if width_max is not None and extracted_width <= width_max:
            score += 2
    elif width_min is not None or width_max is not None:
        score = max(0, score - 1)
    return score


def extract_category_from_message(message: str) -> str | None:
    text = normalize_lookup(message)
    if not text:
        return None

    direct_map = (
        ("ban hoc", "study desk"),
        ("ban lam viec", "desk"),
        ("standing desk", "standing desk"),
        ("study desk", "study desk"),
        ("desk", "desk"),
        ("ergonomic chair", "ergonomic chair"),
        ("gaming chair", "gaming chair"),
        ("office chair", "ergonomic chair"),
        ("chair", "chair"),
        ("ghe", "ergonomic chair"),
    )
    for token, category in direct_map:
        if token in text:
            return category

    match = re.search(
        r"(?:need|want|looking for|find|buy|get|shop for|compare|recommend|suggest|mua|tim|muon mua)\s+"
        r"(?:me\s+)?(?:an?\s+|some\s+)?([a-z0-9][a-z0-9\-\s]{2,80}?)"
        r"(?=\s+(?:under|below|with|delivered|by|exclude|for|and|that)\b|[,.?!]|$)",
        text,
    )
    if not match:
        return None
    candidate = match.group(1).strip()
    if candidate in _GENERIC_CATEGORY_PHRASES:
        return None
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
        return None
    return canonicalize_category(candidate)


def is_shopping_message(message: str) -> bool:
    text = normalize_lookup(message)
    if not text:
        return False
    shopping_verbs = (
        "need",
        "want",
        "looking for",
        "find",
        "buy",
        "get",
        "shop for",
        "recommend",
        "suggest",
        "mua",
        "tim",
        "muon mua",
    )
    return any(token in text for token in shopping_verbs) or extract_category_from_message(text) is not None


def has_structured_constraint_signal(message: str) -> bool:
    text = normalize_lookup(message)
    if not text:
        return False
    patterns = (
        r"(?:under|below|budget|price|<=?)\s*\$?\d",
        r"\d(?:\.\d)?\+?\s*stars?",
        r"(?:delivered by|by|before|within)\s+(?:(?:this|next)\s+)?(?:today|tomorrow|this week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d)",
        r"\b(?:this week|fast delivery|fast shipping)\b",
        r"\b(?:clean ingredients|low lactose|third[- ]party tested|lumbar support|adjustable arms?)\b",
        r"(?:above|over|under|below|at least|at most)\s+[0-9]{2,3}(?:\.[0-9]+)?\s*(?:\"|inches|inch)\s*(?:wide|width)?",
        r"(?:must have|need|want)\s+",
        r"(?:exclude|without|not)\s+",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _tokenize_terms(value: str) -> list[str]:
    return [
        token
        for token in re.split(r"[^a-z0-9]+", normalize_lookup(value))
        if len(token) >= 3 and token not in _NOISE_TERMS
    ]
