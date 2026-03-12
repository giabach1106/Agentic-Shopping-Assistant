from __future__ import annotations

import asyncio
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.collectors.base import (
    CollectionResult,
    CollectorTraceEvent,
    ProductCandidateData,
    RealtimeCollector,
    ReviewRecord,
    SourceName,
    VisualRecord,
)
from app.core.config import Settings

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

_OFF_TOPIC_HINTS = (
    "nba",
    "doubleheader",
    "wedding",
    "movie",
    "iphone",
    "politics",
    "news",
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _is_relevant_supplement_text(text: str, query: str) -> bool:
    haystack = f"{text} {query}".lower()
    if any(token in haystack for token in _OFF_TOPIC_HINTS):
        return False
    return any(token in haystack for token in _SUPPLEMENT_KEYWORDS)


def _extract_numeric_price(value: str) -> float | None:
    match = re.search(r"([0-9][0-9,]*(?:\.[0-9]{2})?)", value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


class DevRealtimeCollector:
    """Deterministic pseudo-live collector for local development and tests."""

    async def collect(self, constraints: dict[str, Any]) -> CollectionResult:
        now = _now_iso()
        query_id = uuid.uuid4().hex[:8]
        category = str(constraints.get("category") or "supplement").lower()
        is_supplement = any(
            token in category
            for token in ("whey", "protein", "supplement", "creatine", "preworkout")
        )
        if not is_supplement:
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
                url="https://www.tiktok.com/@demo/video/7450000000000000001",
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
                image_url="https://images-na.ssl-images-amazon.com/images/I/demo-whey-tub.jpg",
                caption="Official label image showing whey isolate and nutrition panel.",
                retrieved_at=now,
                evidence_id=f"amz-img-{query_id}-1",
                confidence_source=0.88,
                raw_snapshot_ref=f"dev://amazon/images/{query_id}",
            ),
            VisualRecord(
                source="reddit",
                url="https://www.reddit.com/r/Supplements/comments/xyz123/",
                image_url="https://i.redd.it/demo-whey123.jpg",
                caption="User photo comparing scoop size, ingredient label, and texture.",
                retrieved_at=now,
                evidence_id=f"rdt-img-{query_id}-1",
                confidence_source=0.8,
                raw_snapshot_ref=f"dev://reddit/images/{query_id}",
            ),
            VisualRecord(
                source="tiktok",
                url="https://www.tiktok.com/@demo/video/7450000000000000001",
                image_url="https://p16-sign-va.tiktokcdn.com/demo-chair-cover.jpeg",
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
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=12.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        )

    async def collect(self, constraints: dict[str, Any]) -> CollectionResult:
        query = self._build_query(constraints)
        result = CollectionResult()

        tasks = [
            self._collect_ebay(query, result),
            self._collect_walmart(query, result),
            self._collect_amazon(query, result),
            self._collect_reddit(query, result),
            self._collect_tiktok(query, result),
        ]
        await asyncio.gather(*tasks)
        return result

    async def _collect_amazon(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "amazon"
        try:
            url = f"https://www.amazon.com/s?k={quote_plus(query)}"
            response = await self._client.get(url)
            body = response.text
            product_urls = list(
                dict.fromkeys(
                    re.findall(r'href="(/[^"]*/dp/[A-Z0-9]{10}[^"]*)"', body)
                )
            )
            now = _now_iso()
            added = 0
            for relative_url in product_urls:
                full_url = f"https://www.amazon.com{relative_url.split('?')[0]}"
                href_pos = body.find(relative_url)
                window_start = max(0, href_pos - 700) if href_pos >= 0 else 0
                window_end = min(len(body), href_pos + 1600) if href_pos >= 0 else len(body)
                window = body[window_start:window_end]

                title_match = re.search(
                    r'(?:alt|aria-label)="([^"]{10,280})"',
                    window,
                    re.IGNORECASE,
                )
                price_match = re.search(
                    r'\$([0-9][0-9,]*(?:\.[0-9]{2})?)',
                    window,
                    re.IGNORECASE,
                )
                rating_match = re.search(r'([0-5]\.[0-9])\s*out of 5 stars', window)
                count_match = re.search(r'([0-9,]+)\s+ratings?', window)
                image_match = re.search(
                    r'src="(https://[^"]+\.(?:jpg|jpeg|png))"',
                    window,
                    re.IGNORECASE,
                )

                title = _normalize_text(title_match.group(1)) if title_match else ""
                if not title or not _is_relevant_supplement_text(title, query):
                    continue

                result.products.append(
                    ProductCandidateData(
                        source=source,
                        url=full_url,
                        title=title[:280],
                        price=_safe_float(price_match.group(1) if price_match else None, 99.0),
                        avg_rating=_safe_float(rating_match.group(1) if rating_match else None, 0.0),
                        rating_count=_safe_int(count_match.group(1) if count_match else None, 0),
                        shipping_eta="unknown",
                        return_policy="Amazon policy",
                        seller_info="Amazon marketplace",
                        retrieved_at=now,
                        evidence_id=f"amz-offer-{uuid.uuid4().hex[:10]}",
                        confidence_source=0.66,
                        raw_snapshot_ref=url,
                        image_url=image_match.group(1) if image_match else None,
                    )
                )
                if image_match:
                    result.visuals.append(
                        VisualRecord(
                            source=source,
                            url=full_url,
                            image_url=image_match.group(1),
                            caption=title[:180],
                            retrieved_at=now,
                            evidence_id=f"amz-img-{uuid.uuid4().hex[:10]}",
                            confidence_source=0.6,
                            raw_snapshot_ref=url,
                        )
                    )
                added += 1
                if added >= 6:
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
                if not _is_relevant_supplement_text(text, query):
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
                rating_match = re.search(
                    r'([0-5]\.[0-9])\s*out of 5',
                    block,
                    re.IGNORECASE,
                )
                count_match = re.search(r'\(([0-9,]+)\)', block)

                if not item_url_match:
                    continue
                item_url = item_url_match.group(1)
                title = (
                    _normalize_text(title_match.group(1))
                    if title_match
                    else f"eBay result for {query}"
                )
                if not title or "shop on ebay" in title.lower():
                    continue
                if not _is_relevant_supplement_text(title, query):
                    continue

                raw_price = price_match.group(1) if price_match else None
                shipping_eta = _normalize_text(ship_match.group(1)) if ship_match else "unknown"

                result.products.append(
                    ProductCandidateData(
                        source=source,
                        url=item_url,
                        title=title[:280],
                        price=_safe_float(raw_price.replace(",", "") if raw_price else None, 99.0),
                        avg_rating=_safe_float(rating_match.group(1) if rating_match else None, 0.0),
                        rating_count=_safe_int(count_match.group(1) if count_match else None, 0),
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
                    if not title or not _is_relevant_supplement_text(title, query):
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
                if not clean_title or not _is_relevant_supplement_text(clean_title, query):
                    continue
                item_url = f"https://www.walmart.com{rel_url.split('?')[0]}"
                idx = body.find(rel_url)
                window = body[max(0, idx - 600): min(len(body), idx + 1600)] if idx >= 0 else body
                image_match = re.search(
                    r'src="(https://i5\.walmartimages\.com/[^"]+\.(?:jpg|jpeg|png))"',
                    window,
                    re.IGNORECASE,
                )
                rating_match = re.search(r'"averageRating":([0-9]+(?:\.[0-9]+)?)', window)
                count_match = re.search(r'"numberOfReviews":([0-9]+)', window)

                result.products.append(
                    ProductCandidateData(
                        source=source,
                        url=item_url,
                        title=clean_title[:280],
                        price=_safe_float(raw_price, 95.0),
                        avg_rating=_safe_float(rating_match.group(1) if rating_match else None, 0.0),
                        rating_count=_safe_int(count_match.group(1) if count_match else None, 0),
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
                    if not clean_title or not _is_relevant_supplement_text(clean_title, query):
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

    async def _collect_tiktok(self, query: str, result: CollectionResult) -> None:
        started = time.perf_counter()
        source: SourceName = "tiktok"
        try:
            tag = re.sub(r"[^a-z0-9]+", "", query.lower())[:24] or "shopping"
            url = f"https://www.tiktok.com/tag/{tag}"
            response = await self._client.get(url)
            body = response.text

            title_match = re.search(r"<title>([^<]{8,180})</title>", body, re.IGNORECASE)
            now = _now_iso()
            if title_match:
                title = title_match.group(1).strip()
                result.reviews.append(
                    ReviewRecord(
                        source=source,
                        url=url,
                        review_id=f"tt-rv-{uuid.uuid4().hex[:10]}",
                        rating=3.5,
                        review_text=title,
                        timestamp=now,
                        helpful_votes=0,
                        verified_purchase=None,
                        media_count=1,
                        retrieved_at=now,
                        evidence_id=f"tt-ev-{uuid.uuid4().hex[:10]}",
                        confidence_source=0.52,
                        raw_snapshot_ref=url,
                    )
                )
                result.visuals.append(
                    VisualRecord(
                        source=source,
                        url=url,
                        image_url="https://www.tiktok.com/favicon.ico",
                        caption=title,
                        retrieved_at=now,
                        evidence_id=f"tt-img-{uuid.uuid4().hex[:10]}",
                        confidence_source=0.48,
                        raw_snapshot_ref=url,
                    )
                )
                status = "ok"
                detail = "Collected live TikTok tag metadata."
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
        category = str(constraints.get("category") or "product").strip()
        must_have = constraints.get("mustHave") or []
        clauses = [category]
        if isinstance(must_have, list) and must_have:
            clauses.append(" ".join(str(item) for item in must_have[:3]))
        return " ".join(item for item in clauses if item).strip()


def build_realtime_collector(settings: Settings) -> RealtimeCollector:
    mode = settings.runtime_mode.lower().strip()
    if mode == "prod":
        return LiveRealtimeCollector()
    return DevRealtimeCollector()
