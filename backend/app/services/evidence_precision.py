from __future__ import annotations

import hashlib
import html
import re
from collections import Counter, defaultdict
from typing import Any

from app.orchestrator.domain_support import canonicalize_category, infer_domain, normalize_lookup, title_matches_constraints

_FIRST_HAND_MARKERS = (
    " i ",
    " my ",
    " we ",
    " i've ",
    " i’ve ",
    " i've been ",
    " i bought ",
    " i got ",
    " i received ",
    " i've used ",
    " after ",
    " weeks in",
    " month in",
    " day in",
    " two weeks",
    " setup",
    " arrived",
    " sitting in",
    " using it",
    " mixes",
    " tastes",
)
_EXPERIENCE_MARKERS = (
    "comfortable",
    "sturdy",
    "support",
    "mixes",
    "tastes",
    "digest",
    "wobble",
    "arrived",
    "assembly",
    "shipping",
)
_QUESTION_LEADS = (
    "should i",
    "what",
    "why",
    "how",
    "does anyone",
    "anyone else",
    "aitah",
    "help me",
    "looking for",
    "can i",
)
_LISTING_HINTS = (
    "<div",
    "<span",
    "<p",
    "add to cart",
    "supplement facts",
    "nutrition facts",
    "product description",
    "serving size",
    "buy now",
    "shop now",
)
_PROMO_HINTS = ("sponsored", "affiliate", "#ad", "paid promotion")
_BUCKET_ALLOWED_SOURCES: dict[str, dict[str, set[str]]] = {
    "chair": {
        "commerce": {"amazon", "walmart", "ebay", "staples"},
        "review": {"reddit", "amazon"},
        "visual": {"reddit", "amazon"},
    },
    "desk": {
        "commerce": {"amazon", "walmart", "ebay", "staples"},
        "review": {"reddit", "amazon"},
        "visual": {"reddit", "amazon"},
    },
    "supplement": {
        "commerce": {"amazon", "walmart", "ebay", "nutritionfaktory", "dps", "iherb"},
        "review": {"reddit", "amazon", "walmart", "ebay", "nutritionfaktory", "dps", "iherb"},
        "visual": {"amazon", "walmart", "ebay"},
    },
    "generic": {
        "commerce": {"amazon", "walmart", "ebay"},
        "review": {"reddit"},
        "visual": {"reddit"},
    },
}


def _clean_text(value: str) -> str:
    cleaned = html.unescape(value or "")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", cleaned)
    cleaned = re.sub(r"\*+", "", cleaned)
    cleaned = re.sub(r"`+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _signature_from_text(text: str) -> str:
    tokens = [token for token in re.findall(r"[a-z0-9]+", normalize_lookup(text)) if len(token) >= 3]
    return " ".join(tokens[:8])


def _product_signature(url: str, title: str, excerpt: str) -> str:
    signature = _signature_from_text(title) or _signature_from_text(excerpt)
    if signature:
        return signature
    normalized_url = normalize_lookup(url).replace(" ", "")
    return normalized_url[:120]


def _constraint_tokens(constraints: dict[str, Any]) -> set[str]:
    category = canonicalize_category(str(constraints.get("category") or "").strip()) or ""
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", normalize_lookup(category))
        if len(token) >= 3
    }
    for key in ("mustHave", "niceToHave"):
        raw = constraints.get(key) or []
        if not isinstance(raw, list):
            continue
        for item in raw:
            tokens.update(
                token
                for token in re.findall(r"[a-z0-9]+", normalize_lookup(str(item)))
                if len(token) >= 3
            )
    return tokens


def _relevance_score(text: str, constraints: dict[str, Any]) -> float:
    cleaned = _clean_text(text)
    if not cleaned:
        return 0.0
    lowered = f" {normalize_lookup(cleaned)} "
    query_tokens = _constraint_tokens(constraints)
    overlap = sum(1 for token in query_tokens if f" {token} " in lowered)
    if title_matches_constraints(cleaned, constraints):
        overlap += 2
    baseline = max(1, len(query_tokens) or 3)
    return round(min(1.0, overlap / baseline), 3)


def _looks_like_listing_summary(text: str, source: str) -> bool:
    lowered = (text or "").lower()
    if source in {"nutritionfaktory", "dps", "iherb"}:
        return True
    return any(marker in lowered for marker in _LISTING_HINTS)


def _looks_like_first_hand_review(text: str) -> bool:
    lowered = f" {normalize_lookup(text)} "
    if len(lowered.split()) < 10:
        return any(marker in lowered for marker in _EXPERIENCE_MARKERS) and "?" not in lowered
    if any(lowered.strip().startswith(prefix) for prefix in _QUESTION_LEADS):
        return False
    if lowered.count("?") >= 2:
        return False
    return any(marker in lowered for marker in _FIRST_HAND_MARKERS) or any(
        marker in lowered for marker in _EXPERIENCE_MARKERS
    )


def _review_sentiment_markers(text: str) -> tuple[list[str], list[str]]:
    lowered = normalize_lookup(text)
    positive = [marker for marker in ("comfortable", "sturdy", "easy", "support", "value", "mixes", "taste", "clean") if marker in lowered]
    negative = [marker for marker in ("wobble", "late", "clump", "fake", "damaged", "noisy", "hard", "sweet") if marker in lowered]
    return positive[:4], negative[:4]


def source_allowed_for_domain(*, domain: str, source: str, bucket: str) -> bool:
    policy = _BUCKET_ALLOWED_SOURCES.get(domain) or _BUCKET_ALLOWED_SOURCES["generic"]
    return source.lower().strip() in policy.get(bucket, set())


def normalize_collection_evidence(
    payload: dict[str, Any],
    *,
    constraints: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(payload or {})
    domain = infer_domain(str(constraints.get("category") or ""))
    evidence_records: list[dict[str, Any]] = []
    accepted_reviews: list[dict[str, Any]] = []
    seen_evidence_ids: set[str] = set()

    for item in normalized.get("products", []) if isinstance(normalized.get("products"), list) else []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown").strip().lower()
        title = _clean_text(str(item.get("title") or ""))
        url = str(item.get("url") or "").strip()
        evidence_id = str(item.get("evidence_id") or item.get("evidenceId") or f"offer::{source}::{url or title}")
        if evidence_id in seen_evidence_ids:
            continue
        seen_evidence_ids.add(evidence_id)
        evidence_records.append(
            {
                "source": source,
                "sourceBucket": "commerce",
                "contentKind": "offer",
                "domain": domain,
                "url": url,
                "evidenceId": evidence_id,
                "productSignature": _product_signature(url, title, title),
                "productTitle": title,
                "reviewLike": False,
                "acceptedInReviewCorpus": False,
                "relevanceScore": _relevance_score(title, constraints),
                "rejectionReasons": [],
                "extractionMethod": "collector_product",
                "cleanExcerpt": title,
                "rating": float(item.get("avg_rating") or item.get("avgRating") or 0.0) or None,
                "helpfulVotes": int(item.get("rating_count") or item.get("ratingCount") or 0),
                "retrievedAt": str(item.get("retrieved_at") or item.get("retrievedAt") or ""),
                "confidenceSource": float(item.get("confidence_source") or item.get("confidenceSource") or 0.0),
                "rawSnapshotRef": str(item.get("raw_snapshot_ref") or item.get("rawSnapshotRef") or ""),
            }
        )

    for item in normalized.get("reviews", []) if isinstance(normalized.get("reviews"), list) else []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown").strip().lower()
        url = str(item.get("url") or "").strip()
        title = _clean_text(str(item.get("title") or ""))
        raw_text = _clean_text(str(item.get("review_text") or item.get("reviewText") or ""))
        if not raw_text:
            continue
        evidence_id = str(item.get("evidence_id") or item.get("evidenceId") or item.get("review_id") or item.get("reviewId") or f"review::{source}::{hashlib.sha1((url + raw_text).encode('utf-8')).hexdigest()[:12]}")
        if evidence_id in seen_evidence_ids:
            continue
        seen_evidence_ids.add(evidence_id)
        rejection_reasons: list[str] = []
        review_like = _looks_like_first_hand_review(raw_text)
        content_kind = "review"
        source_bucket = "review"
        if source == "tiktok":
            content_kind = "visual_meta"
            source_bucket = "visual"
            review_like = False
            rejection_reasons.append("tag_page_not_review")
        elif _looks_like_listing_summary(raw_text, source):
            content_kind = "listing_summary"
            source_bucket = "commerce"
            review_like = False
            rejection_reasons.append("listing_summary_not_review")
        elif source == "reddit" and not review_like:
            content_kind = "discussion"
            rejection_reasons.append("not_first_hand_review")

        if not source_allowed_for_domain(domain=domain or "generic", source=source, bucket=source_bucket):
            rejection_reasons.append("source_not_allowed_for_domain")

        relevance = _relevance_score(f"{title} {raw_text}".strip(), constraints)
        if relevance < 0.34:
            rejection_reasons.append("low_relevance")
        if source == "amazon" and content_kind == "review":
            review_like = review_like or (
                len(raw_text.split()) >= 8 and float(item.get("rating") or 0.0) > 0
            )

        accepted = (
            content_kind == "review"
            and review_like
            and relevance >= 0.34
            and not rejection_reasons
        )
        record = {
            "source": source,
            "sourceBucket": source_bucket,
            "contentKind": content_kind,
            "domain": domain,
            "url": url,
            "evidenceId": evidence_id,
            "productSignature": _product_signature(url, title, raw_text),
            "productTitle": title or _signature_from_text(raw_text),
            "reviewLike": review_like,
            "acceptedInReviewCorpus": accepted,
            "relevanceScore": relevance,
            "rejectionReasons": rejection_reasons,
            "extractionMethod": "collector_review",
            "cleanExcerpt": raw_text[:500],
            "rating": float(item.get("rating") or 0.0) or None,
            "helpfulVotes": int(item.get("helpful_votes") or item.get("helpfulVotes") or 0),
            "retrievedAt": str(item.get("retrieved_at") or item.get("retrievedAt") or ""),
            "confidenceSource": float(item.get("confidence_source") or item.get("confidenceSource") or 0.0),
            "rawSnapshotRef": str(item.get("raw_snapshot_ref") or item.get("rawSnapshotRef") or ""),
        }
        evidence_records.append(record)
        if accepted:
            accepted_reviews.append(
                {
                    "source": source,
                    "url": url,
                    "review_id": str(item.get("review_id") or item.get("reviewId") or evidence_id),
                    "rating": float(item.get("rating") or 0.0),
                    "review_text": raw_text[:600],
                    "timestamp": str(item.get("timestamp") or item.get("retrieved_at") or item.get("retrievedAt") or ""),
                    "helpful_votes": int(item.get("helpful_votes") or item.get("helpfulVotes") or 0),
                    "verified_purchase": item.get("verified_purchase"),
                    "media_count": int(item.get("media_count") or item.get("mediaCount") or 0),
                    "retrieved_at": str(item.get("retrieved_at") or item.get("retrievedAt") or ""),
                    "evidence_id": evidence_id,
                    "confidence_source": float(item.get("confidence_source") or item.get("confidenceSource") or 0.0),
                    "raw_snapshot_ref": str(item.get("raw_snapshot_ref") or item.get("rawSnapshotRef") or ""),
                }
            )

    for item in normalized.get("visuals", []) if isinstance(normalized.get("visuals"), list) else []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown").strip().lower()
        url = str(item.get("url") or "").strip()
        image_url = str(item.get("image_url") or item.get("imageUrl") or "").strip()
        caption = _clean_text(str(item.get("caption") or ""))
        if not image_url:
            continue
        evidence_id = str(item.get("evidence_id") or item.get("evidenceId") or f"visual::{source}::{image_url}")
        if evidence_id in seen_evidence_ids:
            continue
        seen_evidence_ids.add(evidence_id)
        rejection_reasons: list[str] = []
        if source == "tiktok":
            rejection_reasons.append("social_tag_visual")
        if not source_allowed_for_domain(domain=domain or "generic", source=source, bucket="visual"):
            rejection_reasons.append("source_not_allowed_for_domain")
        evidence_records.append(
            {
                "source": source,
                "sourceBucket": "visual",
                "contentKind": "visual_meta",
                "domain": domain,
                "url": url,
                "evidenceId": evidence_id,
                "productSignature": _product_signature(url, caption, caption),
                "productTitle": caption,
                "reviewLike": False,
                "acceptedInReviewCorpus": False,
                "relevanceScore": _relevance_score(caption, constraints),
                "rejectionReasons": rejection_reasons,
                "extractionMethod": "collector_visual",
                "cleanExcerpt": caption or image_url,
                "rating": None,
                "helpfulVotes": 0,
                "retrievedAt": str(item.get("retrieved_at") or item.get("retrievedAt") or ""),
                "confidenceSource": float(item.get("confidence_source") or item.get("confidenceSource") or 0.0),
                "rawSnapshotRef": str(item.get("raw_snapshot_ref") or item.get("rawSnapshotRef") or ""),
            }
        )

    normalized["reviews"] = accepted_reviews
    normalized["evidenceRecords"] = evidence_records
    return normalized


def build_collection_from_persisted_evidence(records: list[dict[str, Any]]) -> dict[str, Any]:
    reviews: list[dict[str, Any]] = []
    visuals: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        evidence_records.append(dict(item))
        if bool(item.get("acceptedInReviewCorpus")) and str(item.get("contentKind") or "") == "review":
            reviews.append(
                {
                    "source": str(item.get("source") or ""),
                    "url": str(item.get("url") or ""),
                    "review_id": str(item.get("evidenceId") or ""),
                    "rating": float(item.get("rating") or 0.0),
                    "review_text": str(item.get("cleanExcerpt") or ""),
                    "timestamp": str(item.get("retrievedAt") or ""),
                    "helpful_votes": int(item.get("helpfulVotes") or 0),
                    "verified_purchase": None,
                    "media_count": 0,
                    "retrieved_at": str(item.get("retrievedAt") or ""),
                    "evidence_id": str(item.get("evidenceId") or ""),
                    "confidence_source": float(item.get("confidenceSource") or 0.0),
                    "raw_snapshot_ref": str(item.get("rawSnapshotRef") or ""),
                }
            )
        elif str(item.get("contentKind") or "") == "visual_meta":
            visuals.append(
                {
                    "source": str(item.get("source") or ""),
                    "url": str(item.get("url") or ""),
                    "image_url": str(item.get("rawSnapshotRef") or item.get("url") or ""),
                    "caption": str(item.get("cleanExcerpt") or ""),
                    "retrieved_at": str(item.get("retrievedAt") or ""),
                    "evidence_id": str(item.get("evidenceId") or ""),
                    "confidence_source": float(item.get("confidenceSource") or 0.0),
                    "raw_snapshot_ref": str(item.get("rawSnapshotRef") or ""),
                }
            )
    return {
        "products": [],
        "reviews": reviews,
        "visuals": visuals,
        "evidenceRecords": evidence_records,
        "trace": [],
        "missingEvidence": [],
        "blockedSources": [],
    }


def evidence_diagnostics(records: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts = Counter()
    accepted_source_counts = Counter()
    content_kind_counts = Counter()
    rejected_reason_counts = Counter()
    bucket_counts = Counter()
    for item in records:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown").strip().lower()
        source_counts[source] += 1
        bucket_counts[str(item.get("sourceBucket") or "unknown")] += 1
        content_kind = str(item.get("contentKind") or "unknown")
        content_kind_counts[content_kind] += 1
        if bool(item.get("acceptedInReviewCorpus")):
            accepted_source_counts[source] += 1
        for reason in item.get("rejectionReasons") or []:
            rejected_reason_counts[str(reason)] += 1
    return {
        "sourceCounts": dict(source_counts),
        "acceptedReviewSources": dict(accepted_source_counts),
        "contentKindCounts": dict(content_kind_counts),
        "sourceBucketCounts": dict(bucket_counts),
        "rejectionReasons": dict(rejected_reason_counts),
        "acceptedReviewCount": sum(accepted_source_counts.values()),
        "totalEvidenceCount": len(records),
    }


def summarize_review_bullets(
    reviews: list[dict[str, Any]],
    *,
    domain: str,
) -> dict[str, list[str] | str]:
    if not reviews:
        return {
            "strengths": [],
            "cautions": [],
            "commonComplaints": [],
            "fitSummary": "Evidence is still too thin to summarize real-world usage.",
        }

    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    positive_keywords = {
        "chair": {
            "comfort": ("comfort", "comfortable", "lumbar", "support", "ergonomic"),
            "assembly": ("assembly", "assemble", "setup", "instructions"),
            "stability": ("sturdy", "stable", "solid", "frame"),
            "delivery": ("shipping", "arrived", "delivery", "fast"),
        },
        "desk": {
            "space": ("size", "wide", "workspace", "surface"),
            "assembly": ("assembly", "assemble", "setup", "instructions"),
            "stability": ("sturdy", "stable", "solid", "wobble"),
            "delivery": ("shipping", "arrived", "delivery", "fast"),
        },
        "supplement": {
            "digestibility": ("digest", "bloat", "stomach", "light"),
            "mixability": ("mix", "smooth", "clump", "foam"),
            "taste": ("taste", "flavor", "sweet", "aftertaste"),
            "quality": ("clean", "tested", "ingredient", "label"),
        },
    }
    negative_keywords = {
        "chair": {
            "wobble": ("wobble", "loose", "squeak"),
            "assembly": ("hard", "assembly", "instructions"),
            "fit": ("small", "narrow", "firm"),
            "delivery": ("late", "damage", "shipping"),
        },
        "desk": {
            "wobble": ("wobble", "unstable", "shake"),
            "assembly": ("hard", "assembly", "instructions"),
            "size": ("small", "tight", "short"),
            "delivery": ("late", "damage", "shipping"),
        },
        "supplement": {
            "taste": ("bad taste", "sweet", "aftertaste"),
            "digestion": ("bloat", "stomach", "digest"),
            "mixing": ("clump", "foam", "chalky"),
            "value": ("expensive", "price"),
        },
    }
    domain_positive = positive_keywords.get(domain, positive_keywords["chair"])
    domain_negative = negative_keywords.get(domain, negative_keywords["chair"])
    for item in reviews:
        text = normalize_lookup(str(item.get("review_text") or ""))
        if not text:
            continue
        positive_markers, negative_markers = _review_sentiment_markers(text)
        for label, tokens in domain_positive.items():
            if any(token in text for token in tokens) and (positive_markers or float(item.get("rating") or 0.0) >= 4):
                buckets["strengths"][label] += 1
        for label, tokens in domain_negative.items():
            if any(token in text for token in tokens) and (negative_markers or 0 < float(item.get("rating") or 0.0) < 4):
                buckets["cautions"][label] += 1
                buckets["commonComplaints"][label] += 1

    strengths = [label.replace("_", " ") for label, _ in buckets["strengths"].most_common(4)]
    cautions = [label.replace("_", " ") for label, _ in buckets["cautions"].most_common(4)]
    complaints = [label.replace("_", " ") for label, _ in buckets["commonComplaints"].most_common(3)]
    if domain in {"chair", "desk"}:
        fit_summary = "Most matched reviews focus on comfort, setup quality, and stability rather than pure promo copy."
    else:
        fit_summary = "Most matched reviews focus on mixability, digestibility, and formula quality rather than listing copy."
    return {
        "strengths": strengths,
        "cautions": cautions,
        "commonComplaints": complaints,
        "fitSummary": fit_summary,
    }
