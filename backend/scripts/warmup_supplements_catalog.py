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


def _brand_from_title(title: str) -> str:
    parts = [item for item in title.strip().split() if item]
    if not parts:
        return "unknown"
    return " ".join(parts[:2]).strip()


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
        reviews = review_lookup.get((source, url), [])
        ingredient_text = " ".join(
            [
                title,
                " ".join(reviews[:2]),
            ]
        ).strip()[:640]
        records.append(
            {
                "source": source,
                "url": url,
                "title": title,
                "brand": _brand_from_title(title),
                "price": float(item.get("price") or 0.0),
                "rating": float(item.get("avg_rating") or item.get("rating") or 0.0),
                "rating_count": int(item.get("rating_count") or item.get("ratingCount") or 0),
                "image_url": visual_lookup.get((source, url)),
                "ingredient_text": ingredient_text,
                "review_snippets": reviews,
                "retrieved_at": str(item.get("retrieved_at") or item.get("retrievedAt") or ""),
                "payload": item,
            }
        )
    return records


async def warmup_catalog(target_records: int) -> dict[str, Any]:
    settings = Settings.from_env()
    collector = LiveRealtimeCollector()
    store = SQLiteEvidenceStore(settings.sqlite_path)
    await store.initialize()

    deduped: dict[str, dict[str, Any]] = {}
    queries_attempted = 0
    try:
        for query in QUERY_BANK:
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
            for record in _build_records(public_payload):
                deduped[str(record["url"])] = record
                if len(deduped) >= target_records:
                    break
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
