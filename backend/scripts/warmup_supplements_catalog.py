from __future__ import annotations

import argparse
import asyncio
import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from app.collectors.realtime import LiveRealtimeCollector
from app.core.config import Settings
from app.memory.evidence_store import SQLiteEvidenceStore

QUERY_BANK = [
    "whey isolate",
    "whey protein powder",
    "grass fed whey isolate",
    "hydrolyzed whey isolate",
    "lactose free whey",
    "clean protein powder",
    "third party tested whey",
    "whey no sucralose",
    "casein protein",
    "micellar casein",
    "plant protein powder",
    "pea protein isolate",
    "vegan protein powder",
    "collagen peptides powder",
    "creatine monohydrate",
    "micronized creatine",
    "electrolyte powder",
    "pre workout supplement",
    "stimulant free pre workout",
    "post workout recovery supplement",
    "bcaa powder",
    "eaas supplement",
    "glutamine powder",
    "omega 3 fish oil",
    "multivitamin men",
    "multivitamin women",
    "magnesium glycinate",
    "vitamin d3 k2",
    "zinc supplement",
    "probiotic capsules",
    "digestive enzymes supplement",
    "l-theanine supplement",
    "ashwagandha supplement",
    "electrolytes no sugar",
    "mass gainer protein",
    "meal replacement shake",
    "protein isolate vanilla",
    "protein isolate chocolate",
    "creatine gummies",
    "pre workout no artificial sweetener",
]

QUERY_MODIFIERS = [
    "powder",
    "capsules",
    "vanilla",
    "chocolate",
    "unflavored",
    "third party tested",
    "low lactose",
]

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
_TARGET_COMMERCE_SOURCES = {"amazon", "ebay", "nutritionfaktory", "dps"}


def _normalize_url(value: str) -> str:
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


def _brand_from_title(title: str) -> str:
    parts = [item for item in title.strip().split() if item]
    if not parts:
        return "unknown"
    return " ".join(parts[:2]).strip()


def _is_relevant_supplement_text(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in _SUPPLEMENT_KEYWORDS)


def _index_reviews(collection: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    lookup: dict[tuple[str, str], list[str]] = defaultdict(list)
    reviews = collection.get("reviews", []) if isinstance(collection.get("reviews"), list) else []
    for item in reviews:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        text = str(item.get("review_text") or "").strip()
        if not source or not url or not text:
            continue
        if len(lookup[(source, url)]) < 3:
            lookup[(source, url)].append(text[:320])
    return lookup


def _index_visuals(collection: dict[str, Any]) -> dict[tuple[str, str], str]:
    lookup: dict[tuple[str, str], str] = {}
    visuals = collection.get("visuals", []) if isinstance(collection.get("visuals"), list) else []
    for item in visuals:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        image_url = str(item.get("image_url") or item.get("imageUrl") or "").strip()
        if source and url and image_url and (source, url) not in lookup:
            lookup[(source, url)] = image_url
    return lookup


def _track_reject(counter: dict[str, int] | None, reason: str) -> None:
    if counter is None:
        return
    counter[reason] = int(counter.get(reason, 0)) + 1


def _is_complete_record(record: dict[str, Any]) -> tuple[bool, str]:
    required_text_fields = [
        ("source", str(record.get("source") or "").strip()),
        ("url", str(record.get("url") or "").strip()),
        ("title", str(record.get("title") or "").strip()),
        ("brand", str(record.get("brand") or "").strip()),
        ("image_url", str(record.get("image_url") or "").strip()),
        ("ingredient_text", str(record.get("ingredient_text") or "").strip()),
        ("retrieved_at", str(record.get("retrieved_at") or "").strip()),
    ]
    for field_name, value in required_text_fields:
        if not value:
            return False, f"missing_{field_name}"

    if not isinstance(record.get("review_snippets"), list) or not record["review_snippets"]:
        return False, "missing_review_snippets"
    if float(record.get("price") or 0.0) <= 0:
        return False, "invalid_price"
    if float(record.get("rating") or 0.0) <= 0:
        return False, "invalid_rating"
    if int(record.get("rating_count") or 0) <= 0:
        return False, "invalid_rating_count"
    return True, ""


def _build_records(
    collection: dict[str, Any],
    rejection_counts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    products = collection.get("products", []) if isinstance(collection.get("products"), list) else []
    review_lookup = _index_reviews(collection)
    visual_lookup = _index_visuals(collection)
    global_reviews = [
        str(item.get("review_text") or "").strip()
        for item in (collection.get("reviews", []) if isinstance(collection.get("reviews"), list) else [])
        if isinstance(item, dict) and str(item.get("review_text") or "").strip()
    ][:8]

    records: list[dict[str, Any]] = []
    for item in products:
        if not isinstance(item, dict):
            _track_reject(rejection_counts, "invalid_product_payload")
            continue
        source = str(item.get("source") or "").strip().lower()
        url = _normalize_url(str(item.get("url") or ""))
        title = str(item.get("title") or "").strip()
        if not source or not url.startswith("http") or not title:
            _track_reject(rejection_counts, "missing_core_fields")
            continue
        if source not in _TARGET_COMMERCE_SOURCES:
            _track_reject(rejection_counts, f"unsupported_source_{source or 'unknown'}")
            continue
        if _is_search_listing_url(url):
            _track_reject(rejection_counts, "search_url")
            continue
        if not _is_relevant_supplement_text(title):
            _track_reject(rejection_counts, "off_topic")
            continue
        reviews = review_lookup.get((source, url), [])
        if not reviews:
            reviews = list(global_reviews[:2])
        ingredient_text = " ".join(
            [
                title,
                " ".join(reviews[:2]),
            ]
        ).strip()[:640]
        brand = _brand_from_title(title)
        image_url = (
            str(item.get("image_url") or item.get("imageUrl") or "").strip()
            or visual_lookup.get((source, url))
        )
        retrieved_at = str(item.get("retrieved_at") or item.get("retrievedAt") or "").strip()
        record = {
            "source": source,
            "url": url,
            "title": title,
            "brand": brand,
            "price": float(item.get("price") or 0.0),
            "rating": float(item.get("avg_rating") or item.get("rating") or 0.0),
            "rating_count": int(item.get("rating_count") or item.get("ratingCount") or 0),
            "image_url": image_url or "",
            "ingredient_text": ingredient_text,
            "review_snippets": reviews,
            "retrieved_at": retrieved_at,
            "payload": item,
        }
        is_complete, reason = _is_complete_record(record)
        if not is_complete:
            _track_reject(rejection_counts, reason)
            continue
        records.append(
            {
                **record,
                "image_url": image_url,
            }
        )
    return records


async def warmup_catalog(target_records: int) -> dict[str, Any]:
    settings = Settings.from_env()
    collector = LiveRealtimeCollector()
    store = SQLiteEvidenceStore(settings.sqlite_path)
    await store.initialize()
    pruned_legacy = await store.prune_search_catalog_records()

    deduped: dict[str, dict[str, Any]] = {}
    queries_attempted = 0
    rejection_counts: dict[str, int] = defaultdict(int)
    try:
        expanded_queries: list[str] = []
        for base in QUERY_BANK:
            expanded_queries.append(base)
            for modifier in QUERY_MODIFIERS:
                expanded_queries.append(f"{base} {modifier}")

        for query in expanded_queries:
            if len(deduped) >= target_records:
                break
            queries_attempted += 1
            collected = await collector.collect(
                {
                    "category": query,
                    "mustHave": ["supplement"],
                }
            )
            public_payload = collected.to_public_dict()
            records = _build_records(public_payload, rejection_counts=rejection_counts)
            for record in records:
                deduped[str(record["url"])] = record
                if len(deduped) >= target_records:
                    break
            await asyncio.sleep(0.15)
    finally:
        await collector._client.aclose()

    await store.upsert_catalog_records(list(deduped.values()))
    metrics = await store.catalog_metrics()
    metrics["targetRecords"] = target_records
    metrics["seededRecords"] = len(deduped)
    metrics["queriesAttempted"] = queries_attempted
    metrics["prunedLegacySearchRecords"] = pruned_legacy
    metrics["ratedRecords"] = sum(
        1
        for item in deduped.values()
        if float(item.get("rating") or 0.0) > 0 and int(item.get("rating_count") or 0) > 0
    )
    metrics["ratedCoverageRatio"] = round(
        (metrics["ratedRecords"] / max(1, metrics["seededRecords"])),
        4,
    )
    metrics["sourcesTargeted"] = sorted(_TARGET_COMMERCE_SOURCES)
    metrics["rejectedCounts"] = dict(sorted(rejection_counts.items(), key=lambda entry: entry[0]))
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Warm up supplements catalog for DB-first coverage before demo.",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=1600,
        help="Target number of unique product URLs to seed.",
    )
    args = parser.parse_args()

    metrics = asyncio.run(warmup_catalog(max(10, args.target)))
    print("Warmup completed.")
    print(f"Target records: {metrics['targetRecords']}")
    print(f"Sources targeted: {metrics['sourcesTargeted']}")
    print(f"Seeded records: {metrics['seededRecords']}")
    print(f"Queries attempted: {metrics['queriesAttempted']}")
    print(f"Pruned legacy search records: {metrics['prunedLegacySearchRecords']}")
    print(f"Total catalog records: {metrics['totalRecords']}")
    print(f"Source counts: {metrics['sourceCounts']}")
    print(f"Rated records: {metrics['ratedRecords']}")
    print(f"Rated coverage ratio: {metrics['ratedCoverageRatio']}")
    print(f"Rejected counts: {metrics['rejectedCounts']}")
    print(f"Latest retrieved at: {metrics['latestRetrievedAt']}")
    print(f"Freshness seconds: {metrics['freshnessSeconds']}")


if __name__ == "__main__":
    main()
