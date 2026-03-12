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
    try:
        return float(value)
    except ValueError:
        return fallback


class DevRealtimeCollector:
    """Deterministic pseudo-live collector for local development and tests."""

    async def collect(self, constraints: dict[str, Any]) -> CollectionResult:
        del constraints
        now = _now_iso()
        query_id = uuid.uuid4().hex[:8]
        products = [
            ProductCandidateData(
                source="ebay",
                url="https://www.ebay.com/itm/266909800001",
                title="Ergonomic Task Chair Adjustable Lumbar",
                price=129.0,
                avg_rating=0.0,
                rating_count=0,
                shipping_eta="3-6 days",
                return_policy="Seller return policy",
                seller_info="eBay seller",
                retrieved_at=now,
                evidence_id=f"eby-offer-{query_id}-1",
                confidence_source=0.72,
                raw_snapshot_ref=f"dev://ebay/search/{query_id}",
            ),
            ProductCandidateData(
                source="walmart",
                url="https://www.walmart.com/ip/123456789",
                title="Ergonomic Mesh Office Chair, Adjustable Arms",
                price=118.0,
                avg_rating=4.2,
                rating_count=210,
                shipping_eta="2-5 days",
                return_policy="30-day return",
                seller_info="Walmart",
                retrieved_at=now,
                evidence_id=f"wmt-offer-{query_id}-1",
                confidence_source=0.74,
                raw_snapshot_ref=f"dev://walmart/search/{query_id}",
            ),
            ProductCandidateData(
                source="amazon",
                url="https://www.amazon.com/dp/B0CMFQ7Y7Q",
                title="Ergonomic Mesh Office Chair with Adjustable Lumbar Support",
                price=139.99,
                avg_rating=4.4,
                rating_count=1287,
                shipping_eta="2-4 days",
                return_policy="30-day return",
                seller_info="Amazon.com Services LLC",
                retrieved_at=now,
                evidence_id=f"amz-offer-{query_id}-1",
                confidence_source=0.88,
                raw_snapshot_ref=f"dev://amazon/search/{query_id}",
            ),
            ProductCandidateData(
                source="amazon",
                url="https://www.amazon.com/dp/B0CBV2M2N6",
                title="Compact Dorm Ergonomic Chair with Flip-Up Arms",
                price=124.99,
                avg_rating=4.1,
                rating_count=734,
                shipping_eta="4-6 days",
                return_policy="14-day return",
                seller_info="CampusFurniture Direct",
                retrieved_at=now,
                evidence_id=f"amz-offer-{query_id}-2",
                confidence_source=0.83,
                raw_snapshot_ref=f"dev://amazon/search/{query_id}",
            ),
        ]
        reviews = [
            ReviewRecord(
                source="amazon",
                url="https://www.amazon.com/dp/B0CMFQ7Y7Q",
                review_id=f"amz-rv-{query_id}-1",
                rating=5.0,
                review_text=(
                    "Great back support for long coding sessions. Assembly took around "
                    "35 minutes but instructions were clear."
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
                url="https://www.reddit.com/r/OfficeChairs/comments/xyz123/",
                review_id=f"rdt-rv-{query_id}-1",
                rating=4.0,
                review_text=(
                    "Used in a dorm for 8 months. Good comfort, but tighten armrest "
                    "screws every few weeks."
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
                rating=3.5,
                review_text=(
                    "Looks stylish for small room setup; check description for affiliate "
                    "link disclosure."
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
                image_url="https://images-na.ssl-images-amazon.com/images/I/demo-chair.jpg",
                caption="Official listing image with dimensions chart.",
                retrieved_at=now,
                evidence_id=f"amz-img-{query_id}-1",
                confidence_source=0.88,
                raw_snapshot_ref=f"dev://amazon/images/{query_id}",
            ),
            VisualRecord(
                source="reddit",
                url="https://www.reddit.com/r/OfficeChairs/comments/xyz123/",
                image_url="https://i.redd.it/demochair123.jpg",
                caption="User-posted room photo showing chair scale in dorm layout.",
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
                detail="Collected creator-sourced review/video metadata from development dataset.",
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
            product_match = re.search(r'href="(/dp/[A-Z0-9]{10})', body)
            title_match = re.search(r'alt="([^"]{10,200})"', body)
            rating_match = re.search(r'([0-5]\.[0-9]) out of 5 stars', body)
            count_match = re.search(r'([0-9,]+)\s+ratings', body)

            if not product_match:
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

            full_url = f"https://www.amazon.com{product_match.group(1)}"
            now = _now_iso()
            result.products.append(
                ProductCandidateData(
                    source=source,
                    url=full_url,
                    title=(title_match.group(1) if title_match else f"Amazon result for {query}")[:280],
                    price=99.0,
                    avg_rating=_safe_float(rating_match.group(1) if rating_match else None, 4.0),
                    rating_count=int((count_match.group(1) if count_match else "0").replace(",", "")),
                    shipping_eta="unknown",
                    return_policy="unknown",
                    seller_info="unknown",
                    retrieved_at=now,
                    evidence_id=f"amz-offer-{uuid.uuid4().hex[:10]}",
                    confidence_source=0.62,
                    raw_snapshot_ref=url,
                )
            )
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="ok",
                    detail="Collected live Amazon product candidate.",
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

            item_url_match = re.search(
                r'href="(https://www\.ebay\.com/itm/[^"?\s<]+)',
                body,
            )
            title_match = re.search(
                r'class="s-item__title"[^>]*>([^<]{8,240})<',
                body,
                re.IGNORECASE,
            )
            price_match = re.search(
                r'class="s-item__price"[^>]*>\$([0-9][0-9,]*(?:\.[0-9]{2})?)',
                body,
                re.IGNORECASE,
            )
            ship_match = re.search(
                r'class="s-item__shipping[^"]*"[^>]*>([^<]{3,120})<',
                body,
                re.IGNORECASE,
            )
            image_match = re.search(
                r'class="s-item__image-img"[^>]*src="([^"]+)"',
                body,
                re.IGNORECASE,
            )

            if not item_url_match:
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

            now = _now_iso()
            item_url = item_url_match.group(1)
            raw_price = price_match.group(1) if price_match else None
            title = (
                title_match.group(1).strip()
                if title_match
                else f"eBay result for {query}"
            )
            shipping_eta = ship_match.group(1).strip() if ship_match else "unknown"

            result.products.append(
                ProductCandidateData(
                    source=source,
                    url=item_url,
                    title=title[:280],
                    price=_safe_float(raw_price.replace(",", "") if raw_price else None, 99.0),
                    avg_rating=0.0,
                    rating_count=0,
                    shipping_eta=shipping_eta[:100],
                    return_policy="See seller listing",
                    seller_info="eBay seller",
                    retrieved_at=now,
                    evidence_id=f"eby-offer-{uuid.uuid4().hex[:10]}",
                    confidence_source=0.66,
                    raw_snapshot_ref=url,
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

            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="ok",
                    detail="Collected live eBay product candidate.",
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

            item_url_match = re.search(r'href="(/ip/[^"?\s<]+)', body)
            title_match = re.search(
                r'data-automation-id="product-title"[^>]*>([^<]{8,240})<',
                body,
                re.IGNORECASE,
            )
            price_match = re.search(
                r'itemprop="price"[^>]*content="([0-9]+(?:\.[0-9]{1,2})?)"',
                body,
                re.IGNORECASE,
            )
            image_match = re.search(
                r'class="[^"]*absolute[^"]*"[^>]*src="([^"]+)"',
                body,
                re.IGNORECASE,
            )

            if not item_url_match:
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

            item_url = f"https://www.walmart.com{item_url_match.group(1)}"
            now = _now_iso()
            title = (
                title_match.group(1).strip()
                if title_match
                else f"Walmart result for {query}"
            )
            result.products.append(
                ProductCandidateData(
                    source=source,
                    url=item_url,
                    title=title[:280],
                    price=_safe_float(price_match.group(1) if price_match else None, 95.0),
                    avg_rating=0.0,
                    rating_count=0,
                    shipping_eta="unknown",
                    return_policy="See Walmart listing",
                    seller_info="Walmart marketplace",
                    retrieved_at=now,
                    evidence_id=f"wmt-offer-{uuid.uuid4().hex[:10]}",
                    confidence_source=0.64,
                    raw_snapshot_ref=url,
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
                        evidence_id=f"wmt-img-{uuid.uuid4().hex[:10]}",
                        confidence_source=0.57,
                        raw_snapshot_ref=url,
                    )
                )
            result.trace.append(
                CollectorTraceEvent(
                    source=source,
                    step="collect_products",
                    status="ok",
                    detail="Collected live Walmart product candidate.",
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
