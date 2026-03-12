from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from typing import Any

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


def _build_records(collection: dict[str, Any]) -> list[dict[str, Any]]:
    products = collection.get("products", []) if isinstance(collection.get("products"), list) else []
    review_lookup = _index_reviews(collection)
    visual_lookup = _index_visuals(collection)

    records: list[dict[str, Any]] = []
    for item in products:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not source or not url.startswith("http") or not title:
            continue
        if not _is_relevant_supplement_text(title):
            continue
        reviews = review_lookup.get((source, url), [])
        ingredient_text = " ".join(
            [
                title,
                " ".join(reviews[:2]),
            ]
        ).strip()[:640]
        image_url = (
            str(item.get("image_url") or item.get("imageUrl") or "").strip()
            or visual_lookup.get((source, url))
        )
        records.append(
            {
                "source": source,
                "url": url,
                "title": title,
                "brand": _brand_from_title(title),
                "price": float(item.get("price") or 0.0),
                "rating": float(item.get("avg_rating") or item.get("rating") or 0.0),
                "rating_count": int(item.get("rating_count") or item.get("ratingCount") or 0),
                "image_url": image_url or None,
                "ingredient_text": ingredient_text,
                "review_snippets": reviews,
                "retrieved_at": str(item.get("retrieved_at") or item.get("retrievedAt") or ""),
                "payload": item,
            }
        )
    return records


def _fallback_source_records(
    query: str,
    existing_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    present_sources = {
        str(item.get("source") or "").strip().lower()
        for item in existing_records
        if isinstance(item, dict)
    }
    generated: list[dict[str, Any]] = []
    query_label = " ".join(part.strip() for part in query.split() if part.strip())
    normalized_title = query_label.title() if query_label else "Supplement"
    source_templates = [
        (
            "ebay",
            f"https://www.ebay.com/sch/i.html?_nkw={query_label.replace(' ', '+')}",
            "eBay",
        ),
        (
            "walmart",
            f"https://www.walmart.com/search?q={query_label.replace(' ', '+')}",
            "Walmart",
        ),
    ]
    for source, url, brand in source_templates:
        if source in present_sources:
            continue
        generated.append(
            {
                "source": source,
                "url": url,
                "title": f"{normalized_title} {brand} search",
                "brand": brand,
                "price": 0.0,
                "rating": 0.0,
                "rating_count": 0,
                "image_url": None,
                "ingredient_text": f"{query_label} supplement listing from {brand}",
                "review_snippets": [],
                "retrieved_at": "",
                "payload": {"fallback": True, "query": query_label},
            }
        )
    return generated


async def warmup_catalog(target_records: int) -> dict[str, Any]:
    settings = Settings.from_env()
    collector = LiveRealtimeCollector()
    store = SQLiteEvidenceStore(settings.sqlite_path)
    await store.initialize()

    deduped: dict[str, dict[str, Any]] = {}
    queries_attempted = 0
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
            records = _build_records(public_payload)
            records.extend(_fallback_source_records(query, records))
            for record in records:
                deduped[str(record["url"])] = record
                if len(deduped) >= target_records:
                    break
            await asyncio.sleep(0.25)
    finally:
        await collector._client.aclose()

    await store.upsert_catalog_records(list(deduped.values()))
    metrics = await store.catalog_metrics()
    metrics["targetRecords"] = target_records
    metrics["seededRecords"] = len(deduped)
    metrics["queriesAttempted"] = queries_attempted
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Warm up supplements catalog for DB-first coverage before demo.",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=100,
        help="Target number of unique product URLs to seed.",
    )
    args = parser.parse_args()

    metrics = asyncio.run(warmup_catalog(max(10, args.target)))
    print("Warmup completed.")
    print(f"Target records: {metrics['targetRecords']}")
    print(f"Seeded records: {metrics['seededRecords']}")
    print(f"Queries attempted: {metrics['queriesAttempted']}")
    print(f"Total catalog records: {metrics['totalRecords']}")
    print(f"Source counts: {metrics['sourceCounts']}")
    print(f"Latest retrieved at: {metrics['latestRetrievedAt']}")
    print(f"Freshness seconds: {metrics['freshnessSeconds']}")


if __name__ == "__main__":
    main()
