from __future__ import annotations

import asyncio
import html
import importlib
import json
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from app.collectors.base import (
    CollectionResult,
    CollectorTraceEvent,
    EvidenceRecordData,
    ProductCandidateData,
    RealtimeCollector,
    ReviewRecord,
    SourceName,
    VisualRecord,
)
from app.core.config import Settings
from app.orchestrator.domain_support import infer_domain, title_matches_constraints
from app.orchestrator.search_brief import SearchBrief

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_float(value: str | None, fallback: float) -> float:
    if value is None:
        return fallback
    cleaned = re.sub(r"[^0-9.]", "", value)
    if not cleaned:
        return fallback
    try:
        return float(cleaned)
    except ValueError:
        return fallback


def _safe_int(value: str | None, fallback: int = 0) -> int:
    if value is None:
        return fallback
    cleaned = re.sub(r"[^0-9]", "", value)
    if not cleaned:
        return fallback
    try:
        return int(cleaned)
    except ValueError:
        return fallback


_OFF_TOPIC_HINTS = (
    "nba",
    "doubleheader",
    "wedding",
    "movie",
    "iphone",
    "politics",
    "news",
)

_MARKETPLACE_CHALLENGE_MARKERS: dict[str, tuple[str, ...]] = {
    "amazon": (
        "enter the characters you see below",
        "automated access to amazon data",
        "to discuss automated access",
    ),
    "ebay": (
        "pardon our interruption",
        "please verify yourself to continue",
    ),
    "walmart": (
        "robot or human",
        "px-captcha",
        "verify you are human",
        "please complete the security check",
    ),
    "nutritionfaktory": (
        "attention required",
        "just a moment",
        "/cdn-cgi/challenge-platform",
        "cf_chl_opt",
        "captcha",
    ),
    "dps": (
        "attention required",
        "just a moment",
        "/cdn-cgi/challenge-platform",
        "cf_chl_opt",
        "captcha",
    ),
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _decode_html_text(value: str) -> str:
    return _normalize_text(html.unescape(value))


def _is_relevant_product_text(text: str, query: str) -> bool:
    haystack = f"{text} {query}".lower()
    if any(token in haystack for token in _OFF_TOPIC_HINTS):
        return False
    return title_matches_constraints(text, {"category": query})


def _is_first_hand_reddit_review_text(title: str, body: str) -> bool:
    text = _normalize_text(f"{title} {body}".lower())
    if not text or len(text.split()) < 10:
        return False
    if any(text.startswith(prefix) for prefix in ("what ", "why ", "how ", "should i", "anyone ", "aitah", "help ")):
        return False
    if text.count("?") >= 2:
        return False
    return any(
        marker in f" {text} "
        for marker in (
            " i ",
            " my ",
            " we ",
            " i've ",
            " i bought ",
            " i got ",
            " i received ",
            " after ",
            " weeks in",
            " month in",
            " setup",
            " arrived",
            " using it",
            " sitting in",
            " mixes",
            " tastes",
        )
    )


def _extract_numeric_price(value: str) -> float | None:
    match = re.search(r"([0-9][0-9,]*(?:\.[0-9]{2})?)", value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _title_from_url_slug(value: str) -> str:
    parsed = urlparse(value)
    slug = parsed.path.strip("/").split("/")[-1]
    if not slug:
        return ""
    cleaned = re.sub(r"\.(?:htm|html)$", "", slug, flags=re.IGNORECASE)
    cleaned = cleaned.replace("-", " ")
    return _normalize_text(cleaned)


def _signature_from_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower())[:8]).strip()


def _is_product_label_noise(value: str) -> bool:
    text = _decode_html_text(value).lower()
    if not text:
        return True
    if re.fullmatch(r"[0-9][0-9,]*\s+ratings?", text):
        return True
    if re.fullmatch(r"[0-9]+\s+sizes?,\s+[0-9]+\s+flavors?", text):
        return True
    if re.fullmatch(r"options?:.*", text):
        return True
    if text.startswith("options:"):
        return True
    if text.startswith("sponsored"):
        return True
    if text.startswith("view sponsored information"):
        return True
    if text.startswith("visit the ") and text.endswith(" store"):
        return True
    if "shop on amazon" in text:
        return True
    if text.startswith("in ") and " sports nutrition " in f" {text} ":
        return True
    if text in {"global ratings", "ratings", "stars", "star"}:
        return True
    return False


def _extract_rating_and_count(blob: str) -> tuple[float, int]:
    rating_patterns = [
        r'"averageRating"\s*:\s*([0-5](?:\.[0-9]+)?)',
        r'"rating"\s*:\s*([0-5](?:\.[0-9]+)?)',
        r'aria-label="([0-5](?:\.[0-9]+)?)\s*out of 5 stars"',
        r'([0-5]\.[0-9])\s*out of 5 stars',
        r'([0-5]\.[0-9])\s*out of 5',
    ]
    count_patterns: list[tuple[str, bool]] = [
        (r'"ratingCount"\s*:\s*([0-9,]+)', True),
        (r'"numberOfRatings"\s*:\s*([0-9,]+)', True),
        (r'"numberOfReviews"\s*:\s*([0-9,]+)', True),
        (r'aria-label="([0-9][0-9,]*)\s+ratings?"', False),
        (r'([0-9,]+)\s+global ratings?', False),
        (r'([0-9,]+)\s+ratings?', False),
    ]

    rating = 0.0
    rating_count = 0
    count_from_loose_pattern = False
    for pattern in rating_patterns:
        match = re.search(pattern, blob, re.IGNORECASE)
        if match:
            rating = _safe_float(match.group(1), 0.0)
            break
    for pattern, is_structured in count_patterns:
        match = re.search(pattern, blob, re.IGNORECASE)
        if match:
            rating_count = _safe_int(match.group(1), 0)
            count_from_loose_pattern = not is_structured
            break
    if rating <= 0 and count_from_loose_pattern:
        rating_count = 0
    return rating, rating_count


def _extract_amazon_title(window: str) -> str:
    patterns = [
        r'<a[^>]+href="/[^"]*/dp/[A-Z0-9]{10}[^"]*"[^>]*>[\s\S]{0,500}?<span[^>]*>([^<]{10,420})</span>',
        r'aria-label="(?:Sponsored Ad - )?([^"]{10,420})"',
        r'<h2[^>]*>\s*<a[^>]*>\s*<span[^>]*>([^<]{10,320})</span>',
        r'<span[^>]+class="[^"]*a-size-base-plus[^"]*"[^>]*>([^<]{10,320})</span>',
        r'<span[^>]+class="[^"]*a-size-medium[^"]*"[^>]*>([^<]{10,320})</span>',
        r'aria-label="([^"]{10,320})"',
        r'alt="([^"]{10,320})"',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, window, re.IGNORECASE):
            candidate = _normalize_text(match.group(1))
            if candidate and not _is_product_label_noise(candidate):
                return candidate
    return ""


def _extract_amazon_price(window: str, fallback: float = 99.0) -> float:
    price_patterns = (
        r'"priceToPay"\s*:\s*\{\s*"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        r'"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        r'\$([0-9][0-9,]*(?:\.[0-9]{2})?)',
    )
    for pattern in price_patterns:
        match = re.search(pattern, window, re.IGNORECASE)
        if match:
            extracted = _extract_numeric_price(match.group(1))
            if extracted is not None and extracted > 0:
                return extracted
    return fallback


def _extract_amazon_image_url(window: str) -> str | None:
    patterns = (
        r'(https://m\.media-amazon\.com/images/I/[^"]+\.(?:jpg|jpeg|png))',
        r'src="(https://[^"]+\.(?:jpg|jpeg|png))"',
    )
    for pattern in patterns:
        match = re.search(pattern, window, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_amazon_result_windows(body: str) -> list[str]:
    positions = [match.start() for match in re.finditer(r'data-component-type="s-search-result"', body)]
    windows: list[str] = []
    if not positions:
        return windows
    for idx, start in enumerate(positions):
        end = positions[idx + 1] if idx + 1 < len(positions) else min(len(body), start + 24000)
        windows.append(body[start:end])
    return windows


def _extract_amazon_card_href(window: str) -> str:
    patterns = (
        r'<a[^>]+href="(/[^"]*/dp/[A-Z0-9]{10}[^"]*)"[^>]*>[\s\S]{0,500}?<span[^>]*>[^<]{10,420}</span>',
        r'href="(/[^"]*/dp/[A-Z0-9]{10}[^"]*)"',
    )
    for pattern in patterns:
        match = re.search(pattern, window, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _detect_marketplace_challenge(source: str, body: str) -> str | None:
    lowered = body.lower()
    markers = _MARKETPLACE_CHALLENGE_MARKERS.get(source, ())
    for marker in markers:
        if marker in lowered:
            return marker
    return None


def _extract_json_ld_payloads(body: str) -> list[Any]:
    payloads: list[Any] = []
    script_matches = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        body,
        re.IGNORECASE,
    )
    for raw in script_matches:
        text = raw.strip()
        if not text:
            continue
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            continue
        payloads.append(loaded)
    return payloads


def _iter_json_ld_products(node: Any) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            item_type = str(value.get("@type") or "").strip().lower()
            if item_type == "product":
                products.append(value)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(node)
    return products


def _first_offer(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def _first_image_url(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith("http"):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.startswith("http"):
                return item
    return None


def _extract_amazon_asin(value: str) -> str | None:
    match = re.search(r"/dp/([A-Z0-9]{10})", value, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def _extract_amazon_detail_title(body: str) -> str:
    patterns = (
        r'<span[^>]+id="productTitle"[^>]*>([\s\S]*?)</span>',
        r'<meta[^>]+property="og:title"[^>]+content="([^"]{10,420})"',
        r'"title"\s*:\s*"([^"]{10,420})"',
    )
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if not match:
            continue
        candidate = _decode_html_text(match.group(1))
        if candidate and not _is_product_label_noise(candidate):
            return candidate
    for payload in _extract_json_ld_payloads(body):
        for product in _iter_json_ld_products(payload):
            candidate = _decode_html_text(str(product.get("name") or ""))
            if candidate and not _is_product_label_noise(candidate):
                return candidate
    return ""


def _extract_amazon_detail_image_url(body: str) -> str | None:
    patterns = (
        r'"hiRes":"(https://[^"]+)"',
        r'"large":"(https://[^"]+)"',
        r'<img[^>]+id="landingImage"[^>]+src="(https://[^"]+)"',
    )
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return match.group(1).replace("\\u002F", "/").replace("\\/", "/")
    return _extract_amazon_image_url(body)


def _extract_amazon_shipping_eta(body: str) -> str:
    patterns = (
        r'FREE delivery\s*([^<]{6,80})<',
        r'Get it\s*([^<]{6,80})<',
        r'Delivery\s*([^<]{6,80})<',
    )
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if not match:
            continue
        candidate = _decode_html_text(match.group(1))
        candidate = candidate.replace("Details", "").strip(" .,:;-")
        if candidate and len(candidate) >= 3:
            return candidate[:80]
    return "unknown"


def _extract_amazon_seller_info(body: str) -> str:
    patterns = (
        r'Ships from\s*</span>\s*<span[^>]*>([^<]{3,120})</span>[\s\S]{0,240}?Sold by\s*</span>\s*<span[^>]*>([^<]{3,120})</span>',
        r'Sold by\s*</span>\s*<span[^>]*>([^<]{3,120})</span>',
        r'"merchantName":"([^"]{3,120})"',
    )
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if not match:
            continue
        if len(match.groups()) == 2:
            ships_from = _decode_html_text(match.group(1))
            sold_by = _decode_html_text(match.group(2))
            return f"{ships_from} / {sold_by}"[:140]
        return _decode_html_text(match.group(1))[:140]
    return "Amazon marketplace"


def _extract_amazon_spec_text(body: str) -> str:
    snippets: list[str] = []
    bullet_matches = re.findall(
        r'<span[^>]+class="[^"]*a-list-item[^"]*"[^>]*>([\s\S]*?)</span>',
        body,
        re.IGNORECASE,
    )
    for raw in bullet_matches[:10]:
        cleaned = _decode_html_text(raw)
        if cleaned and len(cleaned) >= 12 and not _is_product_label_noise(cleaned):
            snippets.append(cleaned)
    dimension_matches = re.findall(
        r'(?:Product Dimensions|Item Width|Top Width|Desktop Width)[\s\S]{0,120}?([0-9]{2,3}(?:\.[0-9]+)?\s*(?:inches|inch|"))',
        body,
        re.IGNORECASE,
    )
    for raw in dimension_matches[:3]:
        cleaned = _decode_html_text(raw)
        if cleaned:
            snippets.append(cleaned)
    deduped: list[str] = []
    for item in snippets:
        if item not in deduped:
            deduped.append(item)
    return " ".join(deduped[:6])[:720]


def _extract_amazon_review_previews(body: str, *, url: str, now: str) -> list[ReviewRecord]:
    starts = [match.start() for match in re.finditer(r'id="customer_review-[^"]+"', body, re.IGNORECASE)]
    reviews: list[ReviewRecord] = []
    if not starts:
        return reviews
    for idx, start in enumerate(starts[:6]):
        end = starts[idx + 1] if idx + 1 < len(starts) else min(len(body), start + 12000)
        block = body[start:end]
        title_match = re.search(
            r'data-hook="review-title"[^>]*>[\s\S]*?<span[^>]*>([\s\S]*?)</span>',
            block,
            re.IGNORECASE,
        )
        body_match = re.search(
            r'data-hook="review-body"[^>]*>[\s\S]*?<span[^>]*>([\s\S]*?)</span>',
            block,
            re.IGNORECASE,
        )
        rating_match = re.search(
            r'data-hook="review-star-rating"[^>]*>[\s\S]*?([0-5](?:\.[0-9])?)\s*out of 5 stars',
            block,
            re.IGNORECASE,
        )
        helpful_match = re.search(
            r'([0-9][0-9,]*)\s+people found this helpful',
            block,
            re.IGNORECASE,
        )
        if not body_match:
            continue
        title = _decode_html_text(title_match.group(1)) if title_match else ""
        review_body = _decode_html_text(body_match.group(1))
        if not review_body or len(review_body.split()) < 6:
            continue
        review_text = f"{title}. {review_body}".strip(". ")
        reviews.append(
            ReviewRecord(
                source="amazon",
                url=url,
                review_id=f"amz-pdp-rv-{uuid.uuid4().hex[:10]}",
                rating=_safe_float(rating_match.group(1), 0.0) if rating_match else 0.0,
                review_text=review_text[:600],
                timestamp=now,
                helpful_votes=_safe_int(helpful_match.group(1), 0) if helpful_match else 0,
                verified_purchase="verified purchase" in block.lower(),
                media_count=1 if "video-thumbnail-container" in block.lower() or "cr-media-rich" in block.lower() else 0,
                retrieved_at=now,
                evidence_id=f"amz-pdp-ev-{uuid.uuid4().hex[:10]}",
                confidence_source=0.88,
                raw_snapshot_ref=url,
            )
        )
    return reviews


class DevRealtimeCollector:
    """Deterministic pseudo-live collector for local development and tests."""

    async def collect(self, constraints: dict[str, Any]) -> CollectionResult:
        now = _now_iso()
        query_id = uuid.uuid4().hex[:8]
        category = str(constraints.get("category") or "supplement").lower()
        domain = infer_domain(category)
        if domain == "chair":
            return CollectionResult(
                products=[
                    ProductCandidateData(
                        source="amazon",
                        url="https://www.amazon.com/dp/B0CHAIR001",
                        title="FlexiPosture Ergonomic Mesh Chair with Adjustable Lumbar Support",
                        price=149.99,
                        avg_rating=4.5,
                        rating_count=812,
                        shipping_eta="2-4 days",
                        return_policy="30-day return",
                        seller_info="Amazon.com Services LLC",
                        retrieved_at=now,
                        evidence_id=f"amz-chair-{query_id}-1",
                        confidence_source=0.86,
                        raw_snapshot_ref=f"dev://amazon/chair/{query_id}",
                        image_url="https://images-na.ssl-images-amazon.com/images/I/chair-ergonomic-mesh.jpg",
                    ),
                    ProductCandidateData(
                        source="walmart",
                        url="https://www.walmart.com/ip/987650001",
                        title="CampusMesh Study Chair with Flip-Up Arms and Breathable Back",
                        price=129.0,
                        avg_rating=4.2,
                        rating_count=241,
                        shipping_eta="3-5 days",
                        return_policy="30-day return",
                        seller_info="Walmart",
                        retrieved_at=now,
                        evidence_id=f"wmt-chair-{query_id}-1",
                        confidence_source=0.8,
                        raw_snapshot_ref=f"dev://walmart/chair/{query_id}",
                        image_url="https://i5.walmartimages.com/seo/campusmesh-chair.jpg",
                    ),
                    ProductCandidateData(
                        source="ebay",
                        url="https://www.ebay.com/itm/366900000001",
                        title="StudyPro Ergonomic Desk Chair with Padded Seat and Wheels",
                        price=118.5,
                        avg_rating=4.1,
                        rating_count=96,
                        shipping_eta="4-6 days",
                        return_policy="Seller return policy",
                        seller_info="eBay seller",
                        retrieved_at=now,
                        evidence_id=f"eby-chair-{query_id}-1",
                        confidence_source=0.74,
                        raw_snapshot_ref=f"dev://ebay/chair/{query_id}",
                        image_url="https://i.ebayimg.com/images/g/chair-studypro/s-l1600.jpg",
                    ),
                ],
                reviews=[
                    ReviewRecord(
                        source="amazon",
                        url="https://www.amazon.com/dp/B0CHAIR001",
                        review_id=f"amz-chair-rv-{query_id}-1",
                        rating=5.0,
                        review_text=(
                            "Strong lumbar support, breathable mesh, and stable base for long study sessions."
                        ),
                        timestamp=now,
                        helpful_votes=51,
                        verified_purchase=True,
                        media_count=2,
                        retrieved_at=now,
                        evidence_id=f"amz-chair-ev-{query_id}-1",
                        confidence_source=0.9,
                        raw_snapshot_ref=f"dev://amazon/chair/reviews/{query_id}",
                    ),
                    ReviewRecord(
                        source="reddit",
                        url="https://www.reddit.com/r/OfficeChairs/comments/devchair/",
                        review_id=f"rdt-chair-rv-{query_id}-1",
                        rating=4.0,
                        review_text=(
                            "Assembly is manageable in about 30 minutes, but cheaper chairs still wobble if the frame is thin."
                        ),
                        timestamp=now,
                        helpful_votes=27,
                        verified_purchase=None,
                        media_count=1,
                        retrieved_at=now,
                        evidence_id=f"rdt-chair-ev-{query_id}-1",
                        confidence_source=0.82,
                        raw_snapshot_ref=f"dev://reddit/chair/{query_id}",
                    ),
                    ReviewRecord(
                        source="tiktok",
                        url="https://www.tiktok.com/@desksetup/video/7450000000000000011",
                        review_id=f"tt-chair-rv-{query_id}-1",
                        rating=4.0,
                        review_text=(
                            "Paid promotion disclosed. The chair looks clean on camera, but the seat cushion compresses a bit after long use."
                        ),
                        timestamp=now,
                        helpful_votes=9,
                        verified_purchase=None,
                        media_count=1,
                        retrieved_at=now,
                        evidence_id=f"tt-chair-ev-{query_id}-1",
                        confidence_source=0.68,
                        raw_snapshot_ref=f"dev://tiktok/chair/{query_id}",
                    ),
                ],
                visuals=[
                    VisualRecord(
                        source="amazon",
                        url="https://www.amazon.com/dp/B0CHAIR001",
                        image_url="https://images-na.ssl-images-amazon.com/images/I/chair-side-profile.jpg",
                        caption="Product photo showing adjustable lumbar support and mesh back.",
                        retrieved_at=now,
                        evidence_id=f"amz-chair-img-{query_id}-1",
                        confidence_source=0.88,
                        raw_snapshot_ref=f"dev://amazon/chair/images/{query_id}",
                    ),
                    VisualRecord(
                        source="reddit",
                        url="https://www.reddit.com/r/OfficeChairs/comments/devchair/",
                        image_url="https://i.redd.it/chair-user-photo.jpg",
                        caption="User photo showing seat depth and armrest position at a study desk.",
                        retrieved_at=now,
                        evidence_id=f"rdt-chair-img-{query_id}-1",
                        confidence_source=0.8,
                        raw_snapshot_ref=f"dev://reddit/chair/images/{query_id}",
                    ),
                ],
                trace=[
                    CollectorTraceEvent(
                        source="amazon",
                        step="collect_products",
                        status="ok",
                        detail=f"Collected dev chair candidates for {category}.",
                        duration_ms=20,
                    ),
                    CollectorTraceEvent(
                        source="reddit",
                        step="collect_reviews",
                        status="ok",
                        detail="Collected chair review snippets from development dataset.",
                        duration_ms=18,
                    ),
                    CollectorTraceEvent(
                        source="tiktok",
                        step="collect_visuals",
                        status="ok",
                        detail="Collected creator-sourced chair metadata from development dataset.",
                        duration_ms=16,
                    ),
                ],
            )
        if domain == "desk":
            return CollectionResult(
                products=[
                    ProductCandidateData(
                        source="amazon",
                        url="https://www.amazon.com/dp/B0DESK0001",
                        title="Northfield Study Desk 47 Inch with Cable Slot and Storage Shelf",
                        price=179.99,
                        avg_rating=4.4,
                        rating_count=518,
                        shipping_eta="2-4 days",
                        return_policy="30-day return",
                        seller_info="Amazon.com Services LLC",
                        retrieved_at=now,
                        evidence_id=f"amz-desk-{query_id}-1",
                        confidence_source=0.85,
                        raw_snapshot_ref=f"dev://amazon/desk/{query_id}",
                        image_url="https://images-na.ssl-images-amazon.com/images/I/desk-northfield.jpg",
                    ),
                    ProductCandidateData(
                        source="walmart",
                        url="https://www.walmart.com/ip/456780001",
                        title="CampusOak Writing Desk with Drawer and Lower Shelf",
                        price=159.0,
                        avg_rating=4.2,
                        rating_count=187,
                        shipping_eta="3-5 days",
                        return_policy="30-day return",
                        seller_info="Walmart",
                        retrieved_at=now,
                        evidence_id=f"wmt-desk-{query_id}-1",
                        confidence_source=0.79,
                        raw_snapshot_ref=f"dev://walmart/desk/{query_id}",
                        image_url="https://i5.walmartimages.com/seo/campusoak-desk.jpg",
                    ),
                    ProductCandidateData(
                        source="ebay",
                        url="https://www.ebay.com/itm/366900000777",
                        title="LiftFrame Standing Desk 48 Inch Home Office Workstation",
                        price=219.99,
                        avg_rating=4.3,
                        rating_count=114,
                        shipping_eta="4-6 days",
                        return_policy="Seller return policy",
                        seller_info="eBay seller",
                        retrieved_at=now,
                        evidence_id=f"eby-desk-{query_id}-1",
                        confidence_source=0.73,
                        raw_snapshot_ref=f"dev://ebay/desk/{query_id}",
                        image_url="https://i.ebayimg.com/images/g/desk-standing/s-l1600.jpg",
                    ),
                ],
                reviews=[
                    ReviewRecord(
                        source="amazon",
                        url="https://www.amazon.com/dp/B0DESK0001",
                        review_id=f"amz-desk-rv-{query_id}-1",
                        rating=5.0,
                        review_text=(
                            "The desk feels sturdy, the top is wide enough for a laptop plus monitor, and assembly is straightforward."
                        ),
                        timestamp=now,
                        helpful_votes=37,
                        verified_purchase=True,
                        media_count=2,
                        retrieved_at=now,
                        evidence_id=f"amz-desk-ev-{query_id}-1",
                        confidence_source=0.9,
                        raw_snapshot_ref=f"dev://amazon/desk/reviews/{query_id}",
                    ),
                    ReviewRecord(
                        source="reddit",
                        url="https://www.reddit.com/r/battlestations/comments/devdesk/",
                        review_id=f"rdt-desk-rv-{query_id}-1",
                        rating=4.0,
                        review_text=(
                            "Good value and stable frame, but particleboard tops scratch faster than solid wood if you move gear a lot."
                        ),
                        timestamp=now,
                        helpful_votes=19,
                        verified_purchase=None,
                        media_count=1,
                        retrieved_at=now,
                        evidence_id=f"rdt-desk-ev-{query_id}-1",
                        confidence_source=0.81,
                        raw_snapshot_ref=f"dev://reddit/desk/{query_id}",
                    ),
                    ReviewRecord(
                        source="tiktok",
                        url="https://www.tiktok.com/@workspace/video/7450000000000000033",
                        review_id=f"tt-desk-rv-{query_id}-1",
                        rating=4.0,
                        review_text=(
                            "Paid promotion disclosed. Cable management looks clean, but wider desks need more careful assembly than the ad suggests."
                        ),
                        timestamp=now,
                        helpful_votes=8,
                        verified_purchase=None,
                        media_count=1,
                        retrieved_at=now,
                        evidence_id=f"tt-desk-ev-{query_id}-1",
                        confidence_source=0.66,
                        raw_snapshot_ref=f"dev://tiktok/desk/{query_id}",
                    ),
                ],
                visuals=[
                    VisualRecord(
                        source="amazon",
                        url="https://www.amazon.com/dp/B0DESK0001",
                        image_url="https://images-na.ssl-images-amazon.com/images/I/desk-cable-slot.jpg",
                        caption="Desk product photo showing cable slot and lower shelf.",
                        retrieved_at=now,
                        evidence_id=f"amz-desk-img-{query_id}-1",
                        confidence_source=0.88,
                        raw_snapshot_ref=f"dev://amazon/desk/images/{query_id}",
                    ),
                    VisualRecord(
                        source="reddit",
                        url="https://www.reddit.com/r/battlestations/comments/devdesk/",
                        image_url="https://i.redd.it/desk-user-setup.jpg",
                        caption="User setup photo showing depth, width, and monitor fit.",
                        retrieved_at=now,
                        evidence_id=f"rdt-desk-img-{query_id}-1",
                        confidence_source=0.8,
                        raw_snapshot_ref=f"dev://reddit/desk/images/{query_id}",
                    ),
                ],
                trace=[
                    CollectorTraceEvent(
                        source="amazon",
                        step="collect_products",
                        status="ok",
                        detail=f"Collected dev desk candidates for {category}.",
                        duration_ms=20,
                    ),
                    CollectorTraceEvent(
                        source="reddit",
                        step="collect_reviews",
                        status="ok",
                        detail="Collected desk review snippets from development dataset.",
                        duration_ms=18,
                    ),
                    CollectorTraceEvent(
                        source="tiktok",
                        step="collect_visuals",
                        status="ok",
                        detail="Collected creator-sourced desk metadata from development dataset.",
                        duration_ms=16,
                    ),
                ],
            )
        if domain != "supplement":
            category = "protein supplement"
        products = [
            ProductCandidateData(
                source="ebay",
                url="https://www.ebay.com/itm/266909800001",
                title="Optimum Nutrition Gold Standard 100% Whey, Double Rich Chocolate, 24g Protein",
                price=61.99,
                avg_rating=4.7,
                rating_count=642,
                shipping_eta="3-5 days",
                return_policy="Seller return policy",
                seller_info="eBay seller",
                retrieved_at=now,
                evidence_id=f"eby-offer-{query_id}-1",
                confidence_source=0.72,
                raw_snapshot_ref=f"dev://ebay/search/{query_id}",
                image_url="https://i.ebayimg.com/images/g/3foAAOSw1AlmPVDf/s-l1600.jpg",
            ),
            ProductCandidateData(
                source="walmart",
                url="https://www.walmart.com/ip/123456789",
                title="Dymatize ISO100 Hydrolyzed Whey Isolate, Gourmet Vanilla, 25g Protein",
                price=74.98,
                avg_rating=4.6,
                rating_count=418,
                shipping_eta="2-4 days",
                return_policy="30-day return",
                seller_info="Walmart",
                retrieved_at=now,
                evidence_id=f"wmt-offer-{query_id}-1",
                confidence_source=0.74,
                raw_snapshot_ref=f"dev://walmart/search/{query_id}",
                image_url="https://i5.walmartimages.com/seo/Dymatize-ISO100-Hydrolyzed-100-Whey-Protein-Isolate-Powder-Gourmet-Vanilla-20-Servings_3af4f9f8-4b08-4f4d-aaf4-2284fcb8f066.0f6d4ca2f0f2f8f95b8d3f0d18f9c7d6.jpeg",
            ),
            ProductCandidateData(
                source="amazon",
                url="https://www.amazon.com/dp/B0CMFQ7Y7Q",
                title="Transparent Labs Grass-Fed Whey Isolate, Milk Chocolate, 28g Protein, Stevia-Sweetened",
                price=64.99,
                avg_rating=4.5,
                rating_count=1287,
                shipping_eta="2-4 days",
                return_policy="30-day return",
                seller_info="Amazon.com Services LLC",
                retrieved_at=now,
                evidence_id=f"amz-offer-{query_id}-1",
                confidence_source=0.88,
                raw_snapshot_ref=f"dev://amazon/search/{query_id}",
                image_url="https://images-na.ssl-images-amazon.com/images/I/71E+QxP6AUL._SL1500_.jpg",
            ),
            ProductCandidateData(
                source="amazon",
                url="https://www.amazon.com/dp/B0CBV2M2N6",
                title="Legion Whey+ Isolate, Cinnamon Cereal, Third-Party Tested, Digestive Enzymes",
                price=59.99,
                avg_rating=4.4,
                rating_count=734,
                shipping_eta="3-4 days",
                return_policy="14-day return",
                seller_info="Legion Athletics",
                retrieved_at=now,
                evidence_id=f"amz-offer-{query_id}-2",
                confidence_source=0.83,
                raw_snapshot_ref=f"dev://amazon/search/{query_id}",
                image_url="https://images-na.ssl-images-amazon.com/images/I/71y-8zIafSL._SL1500_.jpg",
            ),
            ProductCandidateData(
                source="nutritionfaktory",
                url="https://nutritionfaktory.com/products/transparent-labs-grass-fed-isolate-30srv",
                title="Transparent Labs Grass-Fed Isolate 30 Servings",
                price=59.0,
                avg_rating=5.0,
                rating_count=21,
                shipping_eta="3-6 days",
                return_policy="Store return policy",
                seller_info="NutritionFaktory",
                retrieved_at=now,
                evidence_id=f"nf-offer-{query_id}-1",
                confidence_source=0.82,
                raw_snapshot_ref=f"dev://nutritionfaktory/search/{query_id}",
                image_url="https://cdn.shopify.com/s/files/1/2640/1510/files/MintChocolateChip.webp?v=1705419159",
            ),
            ProductCandidateData(
                source="dps",
                url="https://www.dpsnutrition.net/i/29230/gaspari-proven-whey-100-hydrolized-isolate.htm",
                title="Gaspari Nutrition Proven Whey 100% Hydrolyzed Isolate Blueberry Cobbler - 4 Lb",
                price=33.74,
                avg_rating=4.5,
                rating_count=84,
                shipping_eta="3-6 days",
                return_policy="Store return policy",
                seller_info="DPS Nutrition",
                retrieved_at=now,
                evidence_id=f"dps-offer-{query_id}-1",
                confidence_source=0.79,
                raw_snapshot_ref=f"dev://dps/search/{query_id}",
                image_url="https://siteimgs.com/10017/item/proven-whey.jpg",
            ),
        ]
        reviews = [
            ReviewRecord(
                source="amazon",
                url="https://www.amazon.com/dp/B0CMFQ7Y7Q",
                review_id=f"amz-rv-{query_id}-1",
                rating=5.0,
                review_text=(
                    "Transparent Labs isolate mixes clean, no bloating, and the stevia-only "
                    "sweetening tastes less artificial than sucralose-heavy blends."
                ),
                timestamp=now,
                helpful_votes=42,
                verified_purchase=True,
                media_count=2,
                retrieved_at=now,
                evidence_id=f"amz-ev-{query_id}-1",
                confidence_source=0.9,
                raw_snapshot_ref=f"dev://amazon/reviews/{query_id}",
            ),
            ReviewRecord(
                source="reddit",
                url="https://www.reddit.com/r/Supplements/comments/xyz123/",
                review_id=f"rdt-rv-{query_id}-1",
                rating=4.0,
                review_text=(
                    "ISO100 is easy on digestion because hydrolyzed whey isolate absorbs fast, "
                    "but some people still dislike the sucralose aftertaste."
                ),
                timestamp=now,
                helpful_votes=29,
                verified_purchase=None,
                media_count=1,
                retrieved_at=now,
                evidence_id=f"rdt-ev-{query_id}-1",
                confidence_source=0.81,
                raw_snapshot_ref=f"dev://reddit/search/{query_id}",
            ),
            ReviewRecord(
                source="tiktok",
                url="https://www.tiktok.com/@wellness_lab/video/7450000000000000001",
                review_id=f"tt-rv-{query_id}-1",
                rating=4.0,
                review_text=(
                    "Paid promotion disclosed. Legion Whey+ has third-party tested label and "
                    "digestive enzymes, but the cinnamon flavor runs sweet for some buyers."
                ),
                timestamp=now,
                helpful_votes=11,
                verified_purchase=None,
                media_count=1,
                retrieved_at=now,
                evidence_id=f"tt-ev-{query_id}-1",
                confidence_source=0.68,
                raw_snapshot_ref=f"dev://tiktok/tag/{query_id}",
            ),
        ]
        visuals = [
            VisualRecord(
                source="amazon",
                url="https://www.amazon.com/dp/B0CMFQ7Y7Q",
                image_url="https://images-na.ssl-images-amazon.com/images/I/whey-isolate-tub.jpg",
                caption="Official label image showing whey isolate and nutrition panel.",
                retrieved_at=now,
                evidence_id=f"amz-img-{query_id}-1",
                confidence_source=0.88,
                raw_snapshot_ref=f"dev://amazon/images/{query_id}",
            ),
            VisualRecord(
                source="reddit",
                url="https://www.reddit.com/r/Supplements/comments/xyz123/",
                image_url="https://i.redd.it/whey-product-compare.jpg",
                caption="User photo comparing scoop size, ingredient label, and texture.",
                retrieved_at=now,
                evidence_id=f"rdt-img-{query_id}-1",
                confidence_source=0.8,
                raw_snapshot_ref=f"dev://reddit/images/{query_id}",
            ),
            VisualRecord(
                source="tiktok",
                url="https://www.tiktok.com/@wellness_lab/video/7450000000000000001",
                image_url="https://p16-sign-va.tiktokcdn.com/product-review-cover.jpeg",
                caption="TikTok video cover frame for product showcase.",
                retrieved_at=now,
                evidence_id=f"tt-img-{query_id}-1",
                confidence_source=0.65,
                raw_snapshot_ref=f"dev://tiktok/images/{query_id}",
            ),
        ]
        trace = [
            CollectorTraceEvent(
                source="ebay",
                step="collect_products",
                status="ok",
                detail="Collected product cards from development dataset.",
                duration_ms=19,
            ),
            CollectorTraceEvent(
                source="walmart",
                step="collect_products",
                status="ok",
                detail="Collected product cards from development dataset.",
                duration_ms=20,
            ),
            CollectorTraceEvent(
                source="amazon",
                step="collect_products",
                status="ok",
                detail="Collected product cards and rating metadata from development dataset.",
                duration_ms=22,
            ),
            CollectorTraceEvent(
                source="nutritionfaktory",
                step="collect_products",
                status="ok",
                detail="Collected product cards from development dataset.",
                duration_ms=21,
            ),
            CollectorTraceEvent(
                source="dps",
                step="collect_products",
                status="ok",
                detail="Collected product cards from development dataset.",
                duration_ms=21,
            ),
            CollectorTraceEvent(
                source="reddit",
                step="collect_reviews",
                status="ok",
                detail="Collected community review snippets from development dataset.",
                duration_ms=18,
            ),
            CollectorTraceEvent(
                source="tiktok",
                step="collect_visuals",
                status="ok",
                detail=f"Collected creator-sourced review/video metadata for {category}.",
                duration_ms=16,
            ),
        ]
        return CollectionResult(products=products, reviews=reviews, visuals=visuals, trace=trace)


class LiveRealtimeCollector:
    def __init__(self, settings: Settings) -> None:
        self._client = httpx.AsyncClient(
            timeout=12.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        )
        self._settings = settings

    async def collect(self, constraints: dict[str, Any]) -> CollectionResult:
        brief = SearchBrief.from_constraints(constraints)
        result = CollectionResult(
            crawl_meta={
                "searchBrief": brief.to_public_dict(),
                "queryVariants": dict(brief.query_variants),
            }
        )
        domain = infer_domain(str(constraints.get("category") or brief.category))

        tasks = [
            self._collect_ebay(brief.query_for("ebay"), result),
            self._collect_walmart(brief.query_for("walmart"), result),
            self._collect_amazon(brief.query_for("amazon"), result),
            self._collect_reddit(brief.query_for("reddit"), result),
            self._collect_tiktok(brief.query_for("tiktok"), result),
        ]
        if domain == "supplement":
            tasks.extend(
                [
                    self._collect_nutritionfaktory(brief.query_for("nutritionfaktory"), result),
                    self._collect_dps(brief.query_for("dps"), result),
                ]
            )
        await asyncio.gather(*tasks)
        result.source_health = self._build_source_health(result)
        return result

    def _build_source_health(self, result: CollectionResult) -> dict[str, Any]:
        source_health: dict[str, Any] = {}
        for event in result.trace:
            keys = [event.source]
            if event.source == "amazon" and event.step == "collect_products":
                keys.append("amazonSearch")
            elif event.source == "amazon" and event.step == "collect_pdp":
                keys.append("amazonPdp")
            for key in keys:
                entry = source_health.setdefault(
                    key,
                    {
                        "source": key,
                        "status": event.status,
                        "step": event.step,
                        "detail": event.detail,
                        "fallbackUsed": False,
                    },
                )
                entry["status"] = event.status
                entry["step"] = event.step
                entry["detail"] = event.detail
                if "browser fallback" in event.detail.lower():
                    entry["fallbackUsed"] = True
        for source in result.blocked_sources:
            entry = source_health.setdefault(source, {"source": source})
            entry.setdefault("status", "blocked")
            entry.setdefault("fallbackUsed", False)
        return source_health

    async def _enrich_amazon_pdp(
        self,
        candidate: ProductCandidateData,
        result: CollectionResult,
    ) -> tuple[str, bool]:
        try:
            response = await self._client.get(candidate.url)
            body = response.text
            challenge_marker = _detect_marketplace_challenge("amazon", body)
            fallback_used = False
            if challenge_marker:
                fallback_body = await self._maybe_browser_fallback(
                    source="amazon",
                    url=candidate.url,
                    body=body,
                    reason="challenge",
                )
                if fallback_body:
                    body = fallback_body
                    fallback_used = True
                    challenge_marker = _detect_marketplace_challenge("amazon", body)
                if challenge_marker:
                    return "blocked", fallback_used

            detail_title = _extract_amazon_detail_title(body)
            detail_price = _extract_amazon_price(body, candidate.price)
            detail_rating, detail_rating_count = _extract_rating_and_count(body)
            detail_image = _extract_amazon_detail_image_url(body)
            seller_info = _extract_amazon_seller_info(body)
            shipping_eta = _extract_amazon_shipping_eta(body)
            spec_text = _extract_amazon_spec_text(body)
            review_previews = _extract_amazon_review_previews(
                body,
                url=candidate.url,
                now=_now_iso(),
            )

            if detail_title:
                candidate.title = detail_title[:320]
            if detail_price > 0:
                candidate.price = detail_price
            if detail_rating > 0:
                candidate.avg_rating = detail_rating
            if detail_rating_count > 0:
                candidate.rating_count = detail_rating_count
            if detail_image:
                candidate.image_url = detail_image
            if seller_info:
                candidate.seller_info = seller_info
            if shipping_eta and shipping_eta != "unknown":
                candidate.shipping_eta = shipping_eta
            if spec_text:
                candidate.spec_text = spec_text

            existing_review_signatures = {
                f"{item.url}::{item.review_text[:120]}"
                for item in result.reviews
                if item.source == "amazon"
            }
            added_reviews = 0
            for review in review_previews:
                signature = f"{review.url}::{review.review_text[:120]}"
                if signature in existing_review_signatures:
                    continue
                result.reviews.append(review)
                existing_review_signatures.add(signature)
                added_reviews += 1

            if detail_title or detail_rating_count > 0 or spec_text or added_reviews > 0:
                if detail_rating_count > 0 or added_reviews > 0:
                    return "ok", fallback_used
                return "partial", fallback_used
            return "parser_failed", fallback_used
        except Exception:  # noqa: BLE001
            return "parser_failed", False

    async def _browser_fetch(self, url: str) -> str | None:
        try:
            playwright_async = importlib.import_module("playwright.async_api")
        except ImportError:
            return None
        async_playwright = getattr(playwright_async, "async_playwright", None)
        if async_playwright is None:
            return None
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1200)
                return await page.content()
            finally:
                await browser.close()

    async def _maybe_browser_fallback(
        self,
        *,
        source: str,
        url: str,
        body: str,
        reason: str,
    ) -> str | None:
        if source not in {"amazon", "ebay", "walmart", "nutritionfaktory", "dps"}:
            return None
        challenge_marker = _detect_marketplace_challenge(source, body)
        if not challenge_marker and reason == "challenge":
            return None
        fallback_body = await self._browser_fetch(url)
        if not fallback_body:
            return None
        return fallback_body

    async def _collect_amazon(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "amazon"
        try:
            url = f"https://www.amazon.com/s?k={quote_plus(query)}"
            response = await self._client.get(url)
            body = response.text
            challenge_marker = _detect_marketplace_challenge(source, body)
            if challenge_marker:
                fallback_body = await self._maybe_browser_fallback(
                    source=source,
                    url=url,
                    body=body,
                    reason="challenge",
                )
                if fallback_body:
                    body = fallback_body
                    challenge_marker = _detect_marketplace_challenge(source, body)
                    if not challenge_marker:
                        result.trace.append(
                            CollectorTraceEvent(
                                source=source,
                                step="collect_products",
                                status="warning",
                                detail="Browser fallback cleared Amazon anti-bot challenge.",
                                duration_ms=int((time.perf_counter() - started) * 1000),
                            )
                        )
                if challenge_marker:
                    result.missing_evidence.append("amazon.product_list")
                    result.blocked_sources.append(source)
                    result.trace.append(
                        CollectorTraceEvent(
                            source=source,
                            step="collect_products",
                            status="blocked",
                            detail=f"Amazon anti-bot challenge detected ({challenge_marker}).",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    return
            windows = _extract_amazon_result_windows(body)
            now = _now_iso()
            added = 0
            seen_urls: set[str] = set()
            for window in windows:
                if "s-sponsored-label-marker" in window or "s-sponsored-label-info-icon" in window:
                    continue
                relative_url = _extract_amazon_card_href(window)
                if not relative_url:
                    continue
                normalized_relative = relative_url.split("?", 1)[0]
                normalized_relative = re.sub(r"/ref=.*$", "", normalized_relative).strip()
                full_url = f"https://www.amazon.com{normalized_relative}"
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                title = _extract_amazon_title(window)
                rating_value, rating_count_value = _extract_rating_and_count(window)
                image_url = _extract_amazon_image_url(window)

                if not title or not _is_relevant_product_text(title, query):
                    continue

                result.products.append(
                    ProductCandidateData(
                        source=source,
                        url=full_url,
                        title=_decode_html_text(title)[:280],
                        price=_extract_amazon_price(window, 99.0),
                        avg_rating=rating_value,
                        rating_count=rating_count_value,
                        shipping_eta="unknown",
                        return_policy="Amazon policy",
                        seller_info="Amazon marketplace",
                        retrieved_at=now,
                        evidence_id=f"amz-offer-{uuid.uuid4().hex[:10]}",
                        confidence_source=0.66,
                        raw_snapshot_ref=url,
                        image_url=image_url,
                        spec_text=None,
                    )
                )
                if image_url:
                    result.visuals.append(
                        VisualRecord(
                            source=source,
                            url=full_url,
                            image_url=image_url,
                            caption=title[:180],
                            retrieved_at=now,
                            evidence_id=f"amz-img-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.6,
                            raw_snapshot_ref=url,
                        )
                    )
                added += 1
                if added >= 12:
                    break

            if added == 0:
                result.missing_evidence.append("amazon.product_list")
                result.blocked_sources.append(source)
                result.trace.append(
                    CollectorTraceEvent(
                        source=source,
                        step="collect_products",
                        status="blocked",
                        detail="Unable to parse product cards from Amazon page.",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                return

            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="ok",
                    detail=f"Collected {added} live Amazon product candidates.",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            pdp_started = time.perf_counter()
            amazon_candidates = [item for item in result.products if item.source == source][:6]
            if amazon_candidates:
                enrichment_results = await asyncio.gather(
                    *(self._enrich_amazon_pdp(item, result) for item in amazon_candidates)
                )
                ok_count = sum(1 for status, _ in enrichment_results if status == "ok")
                partial_count = sum(1 for status, _ in enrichment_results if status == "partial")
                blocked_count = sum(1 for status, _ in enrichment_results if status == "blocked")
                parser_failed_count = sum(1 for status, _ in enrichment_results if status == "parser_failed")
                fallback_used = any(fallback for _, fallback in enrichment_results)
                pdp_status = "ok" if ok_count > 0 else ("warning" if partial_count > 0 else "blocked")
                pdp_detail = (
                    f"Amazon PDP enriched {ok_count} candidates, partial={partial_count}, "
                    f"parser_failed={parser_failed_count}, blocked={blocked_count}."
                )
                if fallback_used:
                    pdp_detail = f"{pdp_detail} Browser fallback used on at least one PDP."
                result.trace.append(
                    CollectorTraceEvent(
                        source=source,
                        step="collect_pdp",
                        status=pdp_status,
                        detail=pdp_detail,
                        duration_ms=int((time.perf_counter() - pdp_started) * 1000),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            result.missing_evidence.append("amazon.product_list")
            result.blocked_sources.append(source)
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="error",
                    detail=f"Amazon collection error: {exc!r}",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )

    async def _collect_reddit(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "reddit"
        try:
            url = (
                "https://www.reddit.com/search.json?"
                f"q={quote_plus(query)}&limit=8&sort=relevance&t=year"
            )
            response = await self._client.get(url)
            payload = response.json()
            children = (
                payload.get("data", {})
                .get("children", [])
            )
            now = _now_iso()
            added = 0
            for item in children:
                data = item.get("data", {})
                title = str(data.get("title", "")).strip()
                body = str(data.get("selftext", "")).strip()
                permalink = str(data.get("permalink", "")).strip()
                if not title:
                    continue
                text = (title + " " + body).strip()
                if not _is_relevant_product_text(text, query):
                    continue
                if not _is_first_hand_reddit_review_text(title, body):
                    continue
                result.reviews.append(
                    ReviewRecord(
                        source=source,
                        url=f"https://www.reddit.com{permalink}" if permalink else "https://www.reddit.com",
                        review_id=f"rdt-rv-{uuid.uuid4().hex[:10]}",
                        rating=4.0 if "good" in text.lower() else 3.5,
                        review_text=text[:600],
                        timestamp=now,
                        helpful_votes=int(data.get("ups") or 0),
                        verified_purchase=None,
                        media_count=1 if data.get("thumbnail") not in {"", "self", "default", "nsfw"} else 0,
                        retrieved_at=now,
                        evidence_id=f"rdt-ev-{uuid.uuid4().hex[:10]}",
                        confidence_source=0.76,
                        raw_snapshot_ref=url,
                    )
                )
                if data.get("thumbnail") and str(data.get("thumbnail")).startswith("http"):
                    result.visuals.append(
                        VisualRecord(
                            source=source,
                            url=f"https://www.reddit.com{permalink}" if permalink else "https://www.reddit.com",
                            image_url=str(data.get("thumbnail")),
                            caption=title[:200],
                            retrieved_at=now,
                            evidence_id=f"rdt-img-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.7,
                            raw_snapshot_ref=url,
                        )
                    )
                added += 1
                if added >= 12:
                    break

            if added == 0:
                result.missing_evidence.append("reddit.reviews")
                status = "warning"
                detail = "Reddit search returned no usable review posts."
            else:
                status = "ok"
                detail = f"Collected {added} live Reddit review records."

            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_reviews",
                    status=status,
                    detail=detail,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
        except Exception as exc:  # noqa: BLE001
            result.missing_evidence.append("reddit.reviews")
            result.blocked_sources.append(source)
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_reviews",
                    status="error",
                    detail=f"Reddit collection error: {exc!r}",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )

    async def _collect_ebay(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "ebay"
        try:
            url = f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(query)}"
            response = await self._client.get(url)
            body = response.text
            challenge_marker = _detect_marketplace_challenge(source, body)
            if challenge_marker:
                fallback_body = await self._maybe_browser_fallback(
                    source=source,
                    url=url,
                    body=body,
                    reason="challenge",
                )
                if fallback_body:
                    body = fallback_body
                    challenge_marker = _detect_marketplace_challenge(source, body)
                    if not challenge_marker:
                        result.trace.append(
                            CollectorTraceEvent(
                                source=source,
                                step="collect_products",
                                status="warning",
                                detail="Browser fallback cleared eBay anti-bot challenge.",
                                duration_ms=int((time.perf_counter() - started) * 1000),
                            )
                        )
                if challenge_marker:
                    result.missing_evidence.append("ebay.product_list")
                    result.blocked_sources.append(source)
                    result.trace.append(
                        CollectorTraceEvent(
                            source=source,
                            step="collect_products",
                            status="blocked",
                            detail=f"eBay anti-bot challenge detected ({challenge_marker}).",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    return
            item_blocks = re.findall(
                r'(<li[^>]+class="s-item[^"]*"[\s\S]*?</li>)',
                body,
                re.IGNORECASE,
            )
            now = _now_iso()
            added = 0
            for block in item_blocks:
                item_url_match = re.search(
                    r'href="(https://www\.ebay\.com/itm/[^"?\s<]+)',
                    block,
                    re.IGNORECASE,
                )
                title_match = re.search(
                    r'class="s-item__title"[^>]*>([^<]{8,280})<',
                    block,
                    re.IGNORECASE,
                )
                price_match = re.search(
                    r'class="s-item__price"[^>]*>\$([0-9][0-9,]*(?:\.[0-9]{2})?)',
                    block,
                    re.IGNORECASE,
                )
                ship_match = re.search(
                    r'class="s-item__shipping[^"]*"[^>]*>([^<]{3,120})<',
                    block,
                    re.IGNORECASE,
                )
                image_match = re.search(
                    r'class="s-item__image-img"[^>]*src="([^"]+)"',
                    block,
                    re.IGNORECASE,
                )
                rating_value, rating_count_value = _extract_rating_and_count(block)

                if not item_url_match:
                    continue
                item_url = item_url_match.group(1).split("?")[0]
                title = (
                    _normalize_text(title_match.group(1))
                    if title_match
                    else f"eBay result for {query}"
                )
                if not title or "shop on ebay" in title.lower() or _is_product_label_noise(title):
                    continue
                if not _is_relevant_product_text(title, query):
                    continue

                raw_price = price_match.group(1) if price_match else None
                shipping_eta = _normalize_text(ship_match.group(1)) if ship_match else "unknown"

                result.products.append(
                    ProductCandidateData(
                        source=source,
                        url=item_url,
                        title=title[:280],
                        price=_safe_float(raw_price.replace(",", "") if raw_price else None, 99.0),
                        avg_rating=rating_value,
                        rating_count=rating_count_value,
                        shipping_eta=shipping_eta[:100],
                        return_policy="See seller listing",
                        seller_info="eBay seller",
                        retrieved_at=now,
                        evidence_id=f"eby-offer-{uuid.uuid4().hex[:10]}",
                        confidence_source=0.66,
                        raw_snapshot_ref=url,
                        image_url=image_match.group(1) if image_match else None,
                    )
                )
                if image_match:
                    result.visuals.append(
                        VisualRecord(
                            source=source,
                            url=item_url,
                            image_url=image_match.group(1),
                            caption=title[:200],
                            retrieved_at=now,
                            evidence_id=f"eby-img-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.6,
                            raw_snapshot_ref=url,
                        )
                    )
                added += 1
                if added >= 8:
                    break

            if added == 0:
                item_urls = list(
                    dict.fromkeys(
                        re.findall(
                            r'(https://www\.ebay\.com/itm/[^"?\s<]+)',
                            body,
                            re.IGNORECASE,
                        )
                    )
                )
                for item_url in item_urls:
                    item_url = item_url.split("?")[0]
                    idx = body.find(item_url)
                    window = body[max(0, idx - 900): min(len(body), idx + 1700)] if idx >= 0 else body
                    title_match = re.search(
                        r'(?:aria-label|title|alt)="([^"]{10,260})"',
                        window,
                        re.IGNORECASE,
                    )
                    price_match = re.search(
                        r'\$([0-9][0-9,]*(?:\.[0-9]{2})?)',
                        window,
                        re.IGNORECASE,
                    )
                    image_match = re.search(
                        r'src="(https://[^"]+\.(?:jpg|jpeg|png))"',
                        window,
                        re.IGNORECASE,
                    )
                    title = _normalize_text(title_match.group(1)) if title_match else ""
                    if (
                        not title
                        or _is_product_label_noise(title)
                        or not _is_relevant_product_text(title, query)
                    ):
                        continue
                    result.products.append(
                        ProductCandidateData(
                            source=source,
                            url=item_url,
                            title=title[:280],
                            price=_safe_float(price_match.group(1) if price_match else None, 99.0),
                            avg_rating=0.0,
                            rating_count=0,
                            shipping_eta="unknown",
                            return_policy="See seller listing",
                            seller_info="eBay seller",
                            retrieved_at=now,
                            evidence_id=f"eby-offer-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.58,
                            raw_snapshot_ref=url,
                            image_url=image_match.group(1) if image_match else None,
                        )
                    )
                    if image_match:
                        result.visuals.append(
                            VisualRecord(
                                source=source,
                                url=item_url,
                                image_url=image_match.group(1),
                                caption=title[:200],
                                retrieved_at=now,
                                evidence_id=f"eby-img-{uuid.uuid4().hex[:10]}",
                                confidence_source=0.52,
                                raw_snapshot_ref=url,
                            )
                        )
                    added += 1
                    if added >= 6:
                        break

            if added == 0:
                result.missing_evidence.append("ebay.product_list")
                result.blocked_sources.append(source)
                result.trace.append(
                    CollectorTraceEvent(
                        source=source,
                        step="collect_products",
                        status="blocked",
                        detail="Unable to parse product cards from eBay page.",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                return

            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="ok",
                    detail=f"Collected {added} live eBay product candidates.",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
        except Exception as exc:  # noqa: BLE001
            result.missing_evidence.append("ebay.product_list")
            result.blocked_sources.append(source)
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="error",
                    detail=f"eBay collection error: {exc!r}",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )

    async def _collect_walmart(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "walmart"
        try:
            url = f"https://www.walmart.com/search?q={quote_plus(query)}"
            response = await self._client.get(url)
            body = response.text
            challenge_marker = _detect_marketplace_challenge(source, body)
            if challenge_marker:
                fallback_body = await self._maybe_browser_fallback(
                    source=source,
                    url=url,
                    body=body,
                    reason="challenge",
                )
                if fallback_body:
                    body = fallback_body
                    challenge_marker = _detect_marketplace_challenge(source, body)
                    if not challenge_marker:
                        result.trace.append(
                            CollectorTraceEvent(
                                source=source,
                                step="collect_products",
                                status="warning",
                                detail="Browser fallback cleared Walmart anti-bot challenge.",
                                duration_ms=int((time.perf_counter() - started) * 1000),
                            )
                        )
                if challenge_marker:
                    result.missing_evidence.append("walmart.product_list")
                    result.blocked_sources.append(source)
                    result.trace.append(
                        CollectorTraceEvent(
                            source=source,
                            step="collect_products",
                            status="blocked",
                            detail=f"Walmart anti-bot challenge detected ({challenge_marker}).",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    return
            candidate_matches = re.findall(
                r'"name":"([^"]{8,220})"[\s\S]{0,500}?"canonicalUrl":"(/ip/[^"]+)"[\s\S]{0,500}?"price":([0-9]+(?:\.[0-9]+)?)',
                body,
                re.IGNORECASE,
            )
            if not candidate_matches:
                candidate_matches = re.findall(
                    r'href="(/ip/[^"?\s<]+)"[\s\S]{0,400}?\$([0-9][0-9,]*(?:\.[0-9]{2})?)',
                    body,
                    re.IGNORECASE,
                )

            now = _now_iso()
            added = 0

            # Structured JSON block path.
            for match in candidate_matches:
                if len(match) == 3:
                    title, rel_url, raw_price = match
                else:
                    rel_url, raw_price = match
                    title = f"Walmart result for {query}"
                clean_title = _normalize_text(title)
                if (
                    not clean_title
                    or _is_product_label_noise(clean_title)
                    or not _is_relevant_product_text(clean_title, query)
                ):
                    continue
                item_url = f"https://www.walmart.com{rel_url.split('?')[0]}"
                idx = body.find(rel_url)
                window = body[max(0, idx - 600): min(len(body), idx + 1600)] if idx >= 0 else body
                image_match = re.search(
                    r'src="(https://i5\.walmartimages\.com/[^"]+\.(?:jpg|jpeg|png))"',
                    window,
                    re.IGNORECASE,
                )
                rating_value, rating_count_value = _extract_rating_and_count(window)

                result.products.append(
                    ProductCandidateData(
                        source=source,
                        url=item_url,
                        title=clean_title[:280],
                        price=_safe_float(raw_price, 95.0),
                        avg_rating=rating_value,
                        rating_count=rating_count_value,
                        shipping_eta="unknown",
                        return_policy="See Walmart listing",
                        seller_info="Walmart marketplace",
                        retrieved_at=now,
                        evidence_id=f"wmt-offer-{uuid.uuid4().hex[:10]}",
                        confidence_source=0.64,
                        raw_snapshot_ref=url,
                        image_url=image_match.group(1) if image_match else None,
                    )
                )
                if image_match:
                    result.visuals.append(
                        VisualRecord(
                            source=source,
                            url=item_url,
                            image_url=image_match.group(1),
                            caption=clean_title[:200],
                            retrieved_at=now,
                            evidence_id=f"wmt-img-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.57,
                            raw_snapshot_ref=url,
                        )
                    )
                added += 1
                if added >= 8:
                    break

            if added == 0:
                item_urls = list(
                    dict.fromkeys(
                        re.findall(
                            r'href="(/ip/[^"?\s<]+)"',
                            body,
                            re.IGNORECASE,
                        )
                    )
                )
                for rel_url in item_urls:
                    idx = body.find(rel_url)
                    window = body[max(0, idx - 900): min(len(body), idx + 1900)] if idx >= 0 else body
                    title_match = re.search(
                        r'(?:aria-label|title)="([^"]{10,260})"',
                        window,
                        re.IGNORECASE,
                    )
                    price_match = re.search(
                        r'\$([0-9][0-9,]*(?:\.[0-9]{2})?)',
                        window,
                        re.IGNORECASE,
                    )
                    image_match = re.search(
                        r'src="(https://i5\.walmartimages\.com/[^"]+\.(?:jpg|jpeg|png))"',
                        window,
                        re.IGNORECASE,
                    )
                    clean_title = _normalize_text(title_match.group(1)) if title_match else ""
                    if (
                        not clean_title
                        or _is_product_label_noise(clean_title)
                        or not _is_relevant_product_text(clean_title, query)
                    ):
                        continue
                    item_url = f"https://www.walmart.com{rel_url.split('?')[0]}"
                    result.products.append(
                        ProductCandidateData(
                            source=source,
                            url=item_url,
                            title=clean_title[:280],
                            price=_safe_float(price_match.group(1) if price_match else None, 95.0),
                            avg_rating=0.0,
                            rating_count=0,
                            shipping_eta="unknown",
                            return_policy="See Walmart listing",
                            seller_info="Walmart marketplace",
                            retrieved_at=now,
                            evidence_id=f"wmt-offer-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.56,
                            raw_snapshot_ref=url,
                            image_url=image_match.group(1) if image_match else None,
                        )
                    )
                    if image_match:
                        result.visuals.append(
                            VisualRecord(
                                source=source,
                                url=item_url,
                                image_url=image_match.group(1),
                                caption=clean_title[:200],
                                retrieved_at=now,
                                evidence_id=f"wmt-img-{uuid.uuid4().hex[:10]}",
                                confidence_source=0.5,
                                raw_snapshot_ref=url,
                            )
                        )
                    added += 1
                    if added >= 6:
                        break

            if added == 0:
                result.missing_evidence.append("walmart.product_list")
                result.blocked_sources.append(source)
                result.trace.append(
                    CollectorTraceEvent(
                        source=source,
                        step="collect_products",
                        status="blocked",
                        detail="Unable to parse product cards from Walmart page.",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                return

            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="ok",
                    detail=f"Collected {added} live Walmart product candidates.",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
        except Exception as exc:  # noqa: BLE001
            result.missing_evidence.append("walmart.product_list")
            result.blocked_sources.append(source)
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="error",
                    detail=f"Walmart collection error: {exc!r}",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )

    async def _collect_nutritionfaktory(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "nutritionfaktory"
        try:
            url = f"https://nutritionfaktory.com/search?q={quote_plus(query)}"
            response = await self._client.get(url)
            body = response.text
            challenge_marker = _detect_marketplace_challenge(source, body)
            if challenge_marker:
                fallback_body = await self._maybe_browser_fallback(
                    source=source,
                    url=url,
                    body=body,
                    reason="challenge",
                )
                if fallback_body:
                    body = fallback_body
                    challenge_marker = _detect_marketplace_challenge(source, body)
                    if not challenge_marker:
                        result.trace.append(
                            CollectorTraceEvent(
                                source=source,
                                step="collect_products",
                                status="warning",
                                detail="Browser fallback cleared NutritionFaktory anti-bot challenge.",
                                duration_ms=int((time.perf_counter() - started) * 1000),
                            )
                        )
                if challenge_marker:
                    result.missing_evidence.append("nutritionfaktory.product_list")
                    result.blocked_sources.append(source)
                    result.trace.append(
                        CollectorTraceEvent(
                            source=source,
                            step="collect_products",
                            status="blocked",
                            detail=f"NutritionFaktory anti-bot challenge detected ({challenge_marker}).",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    return

            payloads = _extract_json_ld_payloads(body)
            now = _now_iso()
            added = 0
            seen_urls: set[str] = set()
            for payload in payloads:
                if added >= 16:
                    break
                for product in _iter_json_ld_products(payload):
                    if added >= 16:
                        break
                    offer = _first_offer(product.get("offers"))
                    raw_url = str(offer.get("url") or product.get("url") or "").strip()
                    if not raw_url.startswith("http"):
                        continue
                    item_url = raw_url.split("?", 1)[0]
                    if item_url in seen_urls:
                        continue
                    seen_urls.add(item_url)

                    title = _decode_html_text(str(product.get("name") or ""))
                    slug_title = _title_from_url_slug(item_url)
                    if not _is_relevant_product_text(title, query):
                        title = f"{slug_title} {title}".strip()
                    if (
                        not title
                        or _is_product_label_noise(title)
                        or not _is_relevant_product_text(title, query)
                    ):
                        continue

                    aggregate = product.get("aggregateRating")
                    aggregate_dict = aggregate if isinstance(aggregate, dict) else {}
                    rating_value = _safe_float(
                        str(aggregate_dict.get("ratingValue")) if aggregate_dict else None,
                        0.0,
                    )
                    rating_count_value = max(
                        _safe_int(str(aggregate_dict.get("ratingCount")) if aggregate_dict else None, 0),
                        _safe_int(str(aggregate_dict.get("reviewCount")) if aggregate_dict else None, 0),
                    )
                    price_value = _safe_float(str(offer.get("price") or product.get("price") or ""), 0.0)
                    if price_value <= 0:
                        continue
                    image_url = _first_image_url(product.get("image"))
                    description = _decode_html_text(str(product.get("description") or ""))
                    review_text = description[:520] if description else f"{title} review summary."

                    result.products.append(
                        ProductCandidateData(
                            source=source,
                            url=item_url,
                            title=title[:280],
                            price=price_value,
                            avg_rating=rating_value,
                            rating_count=rating_count_value,
                            shipping_eta="unknown",
                            return_policy="Store return policy",
                            seller_info="NutritionFaktory",
                            retrieved_at=now,
                            evidence_id=f"nf-offer-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.71,
                            raw_snapshot_ref=url,
                            image_url=image_url,
                        )
                    )
                    result.evidence_records.append(
                        EvidenceRecordData(
                            source=source,
                            source_bucket="commerce",
                            content_kind="listing_summary",
                            domain="supplement",
                            url=item_url,
                            evidence_id=f"nf-ev-{uuid.uuid4().hex[:10]}",
                            product_signature=_signature_from_title(title),
                            product_title=title[:280],
                            review_like=False,
                            accepted_in_review_corpus=False,
                            relevance_score=0.84,
                            rejection_reasons=["listing_summary_not_review"],
                            extraction_method="json_ld_product_description",
                            clean_excerpt=review_text,
                            rating=rating_value if rating_value > 0 else None,
                            helpful_votes=rating_count_value,
                            retrieved_at=now,
                            confidence_source=0.68,
                            raw_snapshot_ref=url,
                        )
                    )
                    if image_url:
                        result.visuals.append(
                            VisualRecord(
                                source=source,
                                url=item_url,
                                image_url=image_url,
                                caption=title[:200],
                                retrieved_at=now,
                                evidence_id=f"nf-img-{uuid.uuid4().hex[:10]}",
                                confidence_source=0.65,
                                raw_snapshot_ref=url,
                            )
                        )
                    added += 1

            if added == 0:
                result.missing_evidence.append("nutritionfaktory.product_list")
                result.blocked_sources.append(source)
                result.trace.append(
                    CollectorTraceEvent(
                        source=source,
                        step="collect_products",
                        status="blocked",
                        detail="Unable to parse product cards from NutritionFaktory page.",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                return

            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="ok",
                    detail=f"Collected {added} live NutritionFaktory product candidates.",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
        except Exception as exc:  # noqa: BLE001
            result.missing_evidence.append("nutritionfaktory.product_list")
            result.blocked_sources.append(source)
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="error",
                    detail=f"NutritionFaktory collection error: {exc!r}",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )

    async def _collect_dps(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "dps"
        try:
            url = f"https://www.dpsnutrition.net/search?type=product&q={quote_plus(query)}"
            response = await self._client.get(url)
            body = response.text
            challenge_marker = _detect_marketplace_challenge(source, body)
            if challenge_marker:
                fallback_body = await self._maybe_browser_fallback(
                    source=source,
                    url=url,
                    body=body,
                    reason="challenge",
                )
                if fallback_body:
                    body = fallback_body
                    challenge_marker = _detect_marketplace_challenge(source, body)
                    if not challenge_marker:
                        result.trace.append(
                            CollectorTraceEvent(
                                source=source,
                                step="collect_products",
                                status="warning",
                                detail="Browser fallback cleared DPS anti-bot challenge.",
                                duration_ms=int((time.perf_counter() - started) * 1000),
                            )
                        )
                if challenge_marker:
                    result.missing_evidence.append("dps.product_list")
                    result.blocked_sources.append(source)
                    result.trace.append(
                        CollectorTraceEvent(
                            source=source,
                            step="collect_products",
                            status="blocked",
                            detail=f"DPS anti-bot challenge detected ({challenge_marker}).",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    return

            payloads = _extract_json_ld_payloads(body)
            now = _now_iso()
            added = 0
            seen_urls: set[str] = set()
            for payload in payloads:
                if added >= 16:
                    break
                for product in _iter_json_ld_products(payload):
                    if added >= 16:
                        break
                    offer = _first_offer(product.get("offers"))
                    raw_url = str(offer.get("url") or product.get("url") or "").replace("\\/", "/").strip()
                    if not raw_url.startswith("http"):
                        continue
                    item_url = raw_url.split("?", 1)[0]
                    if item_url in seen_urls:
                        continue
                    seen_urls.add(item_url)

                    title = _decode_html_text(str(product.get("name") or ""))
                    if not _is_relevant_product_text(title, query):
                        title = _title_from_url_slug(item_url)
                    if (
                        not title
                        or _is_product_label_noise(title)
                        or not _is_relevant_product_text(title, query)
                    ):
                        continue

                    aggregate = product.get("aggregateRating")
                    aggregate_dict = aggregate if isinstance(aggregate, dict) else {}
                    rating_value = _safe_float(
                        str(aggregate_dict.get("ratingValue")) if aggregate_dict else None,
                        0.0,
                    )
                    rating_count_value = max(
                        _safe_int(str(aggregate_dict.get("ratingCount")) if aggregate_dict else None, 0),
                        _safe_int(str(aggregate_dict.get("reviewCount")) if aggregate_dict else None, 0),
                    )
                    price_value = _safe_float(str(offer.get("price") or product.get("price") or ""), 0.0)
                    if price_value <= 0:
                        continue
                    image_url = _first_image_url(product.get("image"))
                    description = _decode_html_text(str(product.get("description") or ""))
                    review_text = description[:520] if description else f"{title} listing summary."

                    result.products.append(
                        ProductCandidateData(
                            source=source,
                            url=item_url,
                            title=title[:280],
                            price=price_value,
                            avg_rating=rating_value,
                            rating_count=rating_count_value,
                            shipping_eta="unknown",
                            return_policy="Store return policy",
                            seller_info="DPS Nutrition",
                            retrieved_at=now,
                            evidence_id=f"dps-offer-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.67,
                            raw_snapshot_ref=url,
                            image_url=image_url,
                        )
                    )
                    result.evidence_records.append(
                        EvidenceRecordData(
                            source=source,
                            source_bucket="commerce",
                            content_kind="listing_summary",
                            domain="supplement",
                            url=item_url,
                            evidence_id=f"dps-ev-{uuid.uuid4().hex[:10]}",
                            product_signature=_signature_from_title(title),
                            product_title=title[:280],
                            review_like=False,
                            accepted_in_review_corpus=False,
                            relevance_score=0.82,
                            rejection_reasons=["listing_summary_not_review"],
                            extraction_method="json_ld_product_description",
                            clean_excerpt=review_text,
                            rating=rating_value if rating_value > 0 else None,
                            helpful_votes=rating_count_value,
                            retrieved_at=now,
                            confidence_source=0.63,
                            raw_snapshot_ref=url,
                        )
                    )
                    if image_url:
                        result.visuals.append(
                            VisualRecord(
                                source=source,
                                url=item_url,
                                image_url=image_url,
                                caption=title[:200],
                                retrieved_at=now,
                                evidence_id=f"dps-img-{uuid.uuid4().hex[:10]}",
                                confidence_source=0.6,
                                raw_snapshot_ref=url,
                            )
                        )
                    added += 1

            if added == 0:
                result.missing_evidence.append("dps.product_list")
                result.blocked_sources.append(source)
                result.trace.append(
                    CollectorTraceEvent(
                        source=source,
                        step="collect_products",
                        status="blocked",
                        detail="Unable to parse product cards from DPS page.",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                return

            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="ok",
                    detail=f"Collected {added} live DPS product candidates.",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
        except Exception as exc:  # noqa: BLE001
            result.missing_evidence.append("dps.product_list")
            result.blocked_sources.append(source)
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="error",
                    detail=f"DPS collection error: {exc!r}",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )

    async def _collect_tiktok(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "tiktok"
        try:
            tag = re.sub(r"[^a-z0-9]+", "", query.lower())[:24] or "shopping"
            url = f"https://www.tiktok.com/tag/{tag}"
            response = await self._client.get(url)
            body = response.text

            title_match = re.search(r"<title>([^<]{8,180})</title>", body, re.IGNORECASE)
            if title_match:
                status = "warning"
                detail = "Skipped TikTok tag page because it is not product-review evidence."
            else:
                result.missing_evidence.append("tiktok.reviews")
                result.blocked_sources.append(source)
                status = "blocked"
                detail = "TikTok content unavailable or blocked for scraping."

            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_reviews",
                    status=status,
                    detail=detail,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
        except Exception as exc:  # noqa: BLE001
            result.missing_evidence.append("tiktok.reviews")
            result.blocked_sources.append(source)
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_reviews",
                    status="error",
                    detail=f"TikTok collection error: {exc!r}",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )

    def _build_query(self, constraints: dict[str, Any]) -> str:
        return SearchBrief.from_constraints(constraints).query_for("default")


def build_realtime_collector(settings: Settings) -> RealtimeCollector:
    mode = settings.runtime_mode.lower().strip()
    if mode == "prod":
        return LiveRealtimeCollector(settings)
    return DevRealtimeCollector()
