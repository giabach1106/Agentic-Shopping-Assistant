from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiosqlite

from app.orchestrator.domain_support import infer_domain, normalize_lookup


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def constraint_fingerprint(constraints: dict[str, Any]) -> str:
    normalized = json.dumps(constraints, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class SQLiteEvidenceStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_cache (
                    fingerprint TEXT PRIMARY KEY,
                    constraints_json TEXT NOT NULL,
                    collection_json TEXT NOT NULL,
                    stats_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS catalog_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    brand TEXT,
                    price REAL,
                    rating REAL,
                    rating_count INTEGER,
                    image_url TEXT,
                    ingredient_text TEXT,
                    review_snippets_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_records (
                    fingerprint TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_bucket TEXT NOT NULL,
                    content_kind TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    url TEXT NOT NULL,
                    product_signature TEXT,
                    product_title TEXT,
                    review_like INTEGER NOT NULL,
                    accepted_in_review_corpus INTEGER NOT NULL,
                    relevance_score REAL NOT NULL,
                    rejection_reasons_json TEXT NOT NULL,
                    extraction_method TEXT NOT NULL,
                    clean_excerpt TEXT NOT NULL,
                    rating REAL,
                    helpful_votes INTEGER NOT NULL,
                    confidence_source REAL NOT NULL,
                    raw_snapshot_ref TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def get_cached_collection(
        self,
        constraints: dict[str, Any],
    ) -> dict[str, Any] | None:
        fingerprint = constraint_fingerprint(constraints)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT collection_json, stats_json, created_at, updated_at
                FROM evidence_cache
                WHERE fingerprint = ?
                LIMIT 1
                """,
                (fingerprint,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "fingerprint": fingerprint,
            "collection": json.loads(row["collection_json"]),
            "stats": json.loads(row["stats_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    async def upsert_cached_collection(
        self,
        constraints: dict[str, Any],
        collection: dict[str, Any],
        stats: dict[str, Any],
    ) -> None:
        fingerprint = constraint_fingerprint(constraints)
        now = _now_iso()
        payload = (
            fingerprint,
            json.dumps(constraints, sort_keys=True),
            json.dumps(collection, sort_keys=True),
            json.dumps(stats, sort_keys=True),
            now,
            now,
        )
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO evidence_cache (
                    fingerprint,
                    constraints_json,
                    collection_json,
                    stats_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    constraints_json = excluded.constraints_json,
                    collection_json = excluded.collection_json,
                    stats_json = excluded.stats_json,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
            await db.commit()

    async def upsert_catalog_records(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        now = _now_iso()
        inserted = 0
        async with aiosqlite.connect(self._db_path) as db:
            for item in records:
                source = str(item.get("source") or "unknown").strip().lower()
                raw_url = str(item.get("url") or "").strip()
                url = _normalize_url(raw_url)
                title = str(item.get("title") or "").strip()
                if not source or not url or not title:
                    continue
                if _is_search_listing_url(url):
                    continue
                brand = str(item.get("brand") or "").strip() or None
                price = item.get("price")
                rating = item.get("rating")
                rating_count = int(item.get("rating_count") or item.get("ratingCount") or 0)
                image_url = str(item.get("image_url") or item.get("imageUrl") or "").strip() or None
                ingredient_text = str(item.get("ingredient_text") or item.get("ingredientText") or "").strip() or None
                snippets = item.get("review_snippets") or item.get("reviewSnippets") or []
                normalized_snippets = [
                    str(snippet).strip()
                    for snippet in snippets
                    if str(snippet).strip()
                ][:5]
                payload = dict(item)
                retrieved_at = str(item.get("retrieved_at") or item.get("retrievedAt") or now)
                price_value = float(price) if price is not None else 0.0
                rating_value = float(rating) if rating is not None else 0.0
                if (
                    not brand
                    or price_value <= 0
                    or rating_value <= 0
                    or rating_count <= 0
                    or not image_url
                    or not ingredient_text
                    or not normalized_snippets
                    or not retrieved_at.strip()
                ):
                    continue
                await db.execute(
                    """
                    INSERT INTO catalog_records (
                        source,
                        url,
                        title,
                        brand,
                        price,
                        rating,
                        rating_count,
                        image_url,
                        ingredient_text,
                        review_snippets_json,
                        payload_json,
                        created_at,
                        updated_at,
                        retrieved_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        source = excluded.source,
                        title = excluded.title,
                        brand = excluded.brand,
                        price = excluded.price,
                        rating = excluded.rating,
                        rating_count = excluded.rating_count,
                        image_url = excluded.image_url,
                        ingredient_text = excluded.ingredient_text,
                        review_snippets_json = excluded.review_snippets_json,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at,
                        retrieved_at = excluded.retrieved_at
                    """,
                    (
                        source,
                        url,
                        title,
                        brand,
                        price_value,
                        rating_value,
                        rating_count,
                        image_url,
                        ingredient_text,
                        json.dumps(normalized_snippets, sort_keys=True),
                        json.dumps(payload, sort_keys=True),
                        now,
                        now,
                        retrieved_at,
                    ),
                )
                inserted += 1
            await db.commit()
        return inserted

    async def upsert_evidence_records(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        now = _now_iso()
        inserted = 0
        async with aiosqlite.connect(self._db_path) as db:
            for item in records:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or "unknown").strip().lower()
                source_bucket = str(item.get("sourceBucket") or "").strip().lower()
                content_kind = str(item.get("contentKind") or "").strip().lower()
                domain = str(item.get("domain") or "").strip().lower() or "generic"
                url = _normalize_url(str(item.get("url") or "").strip())
                clean_excerpt = str(item.get("cleanExcerpt") or "").strip()
                evidence_id = str(item.get("evidenceId") or "").strip()
                if not source or not source_bucket or not content_kind or not clean_excerpt:
                    continue
                fingerprint = evidence_id or hashlib.sha1(
                    json.dumps(
                        {
                            "source": source,
                            "bucket": source_bucket,
                            "kind": content_kind,
                            "domain": domain,
                            "url": url,
                            "excerpt": clean_excerpt,
                        },
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                payload = dict(item)
                product_signature = str(item.get("productSignature") or "").strip()
                product_title = str(item.get("productTitle") or "").strip()
                review_like = 1 if bool(item.get("reviewLike")) else 0
                accepted_in_review_corpus = 1 if bool(item.get("acceptedInReviewCorpus")) else 0
                relevance_score = float(item.get("relevanceScore") or 0.0)
                rejection_reasons = [
                    str(reason).strip()
                    for reason in (item.get("rejectionReasons") or [])
                    if str(reason).strip()
                ]
                extraction_method = str(item.get("extractionMethod") or "unknown").strip()
                rating = item.get("rating")
                helpful_votes = int(item.get("helpfulVotes") or 0)
                confidence_source = float(item.get("confidenceSource") or 0.0)
                raw_snapshot_ref = str(item.get("rawSnapshotRef") or "").strip()
                retrieved_at = str(item.get("retrievedAt") or item.get("retrieved_at") or now).strip() or now
                await db.execute(
                    """
                    INSERT INTO evidence_records (
                        fingerprint,
                        source,
                        source_bucket,
                        content_kind,
                        domain,
                        url,
                        product_signature,
                        product_title,
                        review_like,
                        accepted_in_review_corpus,
                        relevance_score,
                        rejection_reasons_json,
                        extraction_method,
                        clean_excerpt,
                        rating,
                        helpful_votes,
                        confidence_source,
                        raw_snapshot_ref,
                        payload_json,
                        created_at,
                        updated_at,
                        retrieved_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        source = excluded.source,
                        source_bucket = excluded.source_bucket,
                        content_kind = excluded.content_kind,
                        domain = excluded.domain,
                        url = excluded.url,
                        product_signature = excluded.product_signature,
                        product_title = excluded.product_title,
                        review_like = excluded.review_like,
                        accepted_in_review_corpus = excluded.accepted_in_review_corpus,
                        relevance_score = excluded.relevance_score,
                        rejection_reasons_json = excluded.rejection_reasons_json,
                        extraction_method = excluded.extraction_method,
                        clean_excerpt = excluded.clean_excerpt,
                        rating = excluded.rating,
                        helpful_votes = excluded.helpful_votes,
                        confidence_source = excluded.confidence_source,
                        raw_snapshot_ref = excluded.raw_snapshot_ref,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at,
                        retrieved_at = excluded.retrieved_at
                    """,
                    (
                        fingerprint,
                        source,
                        source_bucket,
                        content_kind,
                        domain,
                        url,
                        product_signature,
                        product_title,
                        review_like,
                        accepted_in_review_corpus,
                        relevance_score,
                        json.dumps(rejection_reasons, sort_keys=True),
                        extraction_method,
                        clean_excerpt,
                        float(rating) if rating is not None else None,
                        helpful_votes,
                        confidence_source,
                        raw_snapshot_ref,
                        json.dumps(payload, sort_keys=True),
                        now,
                        now,
                        retrieved_at,
                    ),
                )
                inserted += 1
            await db.commit()
        return inserted

    async def list_catalog_records(
        self,
        *,
        query: str | None = None,
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        clauses = ["1 = 1"]
        clauses.append("lower(url) NOT LIKE '%/search?%'")
        clauses.append("lower(url) NOT LIKE '%/sch/i.html%'")
        params: list[Any] = []
        if query and query.strip():
            terms = [part.strip().lower() for part in query.split() if part.strip()]
            if terms:
                term_clauses: list[str] = []
                for term in terms[:8]:
                    term_clauses.append(
                        "(lower(title) LIKE ? OR lower(COALESCE(ingredient_text,'')) LIKE ?)"
                    )
                    like = f"%{term}%"
                    params.extend([like, like])
                clauses.append("(" + " OR ".join(term_clauses) + ")")

        sql = f"""
            SELECT
                source,
                url,
                title,
                brand,
                price,
                rating,
                rating_count,
                image_url,
                ingredient_text,
                review_snippets_json,
                payload_json,
                retrieved_at
            FROM catalog_records
            WHERE {" AND ".join(clauses)}
            ORDER BY
                CASE WHEN lower(title) LIKE '% search' THEN 1 ELSE 0 END ASC,
                CASE WHEN COALESCE(price, 0) > 0 THEN 0 ELSE 1 END ASC,
                CASE WHEN review_snippets_json IS NOT NULL AND review_snippets_json <> '[]' THEN 0 ELSE 1 END ASC,
                COALESCE(rating_count, 0) DESC,
                CASE source
                    WHEN 'amazon' THEN 0
                    WHEN 'ebay' THEN 1
                    WHEN 'nutritionfaktory' THEN 2
                    WHEN 'dps' THEN 3
                    WHEN 'walmart' THEN 4
                    ELSE 5
                END ASC,
                retrieved_at DESC,
                updated_at DESC
            LIMIT ?
        """
        params.append(safe_limit)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            snippets: list[str] = []
            raw_snippets = row["review_snippets_json"]
            if isinstance(raw_snippets, str) and raw_snippets:
                try:
                    loaded = json.loads(raw_snippets)
                except json.JSONDecodeError:
                    loaded = []
                if isinstance(loaded, list):
                    snippets = [
                        str(item).strip()
                        for item in loaded
                        if str(item).strip()
                    ]
            raw_payload = row["payload_json"]
            payload: dict[str, Any] = {}
            if isinstance(raw_payload, str) and raw_payload:
                try:
                    loaded_payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    loaded_payload = {}
                if isinstance(loaded_payload, dict):
                    payload = loaded_payload
            items.append(
                {
                    "source": row["source"],
                    "url": row["url"],
                    "title": row["title"],
                    "brand": row["brand"],
                    "price": row["price"],
                    "rating": row["rating"],
                    "rating_count": row["rating_count"],
                    "image_url": row["image_url"],
                    "ingredient_text": row["ingredient_text"],
                    "review_snippets": snippets,
                    "retrieved_at": row["retrieved_at"],
                    "payload": payload,
                }
            )
        return items

    async def list_evidence_records(
        self,
        *,
        domain: str,
        query: str | None = None,
        limit: int = 120,
        accepted_only: bool = False,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        params: list[Any] = [domain.strip().lower() or "generic"]
        clauses = ["domain = ?"]
        if accepted_only:
            clauses.append("accepted_in_review_corpus = 1")
        if query and query.strip():
            query_terms = [
                term
                for term in re.findall(r"[a-z0-9]+", normalize_lookup(query))
                if len(term) >= 3
            ][:8]
            if query_terms:
                subclauses: list[str] = []
                for term in query_terms:
                    like = f"%{term}%"
                    subclauses.append(
                        "(lower(clean_excerpt) LIKE ? OR lower(COALESCE(product_title,'')) LIKE ? OR lower(COALESCE(product_signature,'')) LIKE ?)"
                    )
                    params.extend([like, like, like])
                clauses.append("(" + " OR ".join(subclauses) + ")")
        sql = f"""
            SELECT
                fingerprint,
                source,
                source_bucket,
                content_kind,
                domain,
                url,
                product_signature,
                product_title,
                review_like,
                accepted_in_review_corpus,
                relevance_score,
                rejection_reasons_json,
                extraction_method,
                clean_excerpt,
                rating,
                helpful_votes,
                confidence_source,
                raw_snapshot_ref,
                payload_json,
                retrieved_at
            FROM evidence_records
            WHERE {" AND ".join(clauses)}
            ORDER BY accepted_in_review_corpus DESC, relevance_score DESC, helpful_votes DESC, retrieved_at DESC
            LIMIT ?
        """
        params.append(safe_limit)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload: dict[str, Any] = {}
            raw_payload = row["payload_json"]
            if isinstance(raw_payload, str) and raw_payload:
                try:
                    loaded_payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    loaded_payload = {}
                if isinstance(loaded_payload, dict):
                    payload = loaded_payload
            raw_reasons = row["rejection_reasons_json"]
            reasons: list[str] = []
            if isinstance(raw_reasons, str) and raw_reasons:
                try:
                    loaded_reasons = json.loads(raw_reasons)
                except json.JSONDecodeError:
                    loaded_reasons = []
                if isinstance(loaded_reasons, list):
                    reasons = [str(item).strip() for item in loaded_reasons if str(item).strip()]
            items.append(
                {
                    "evidenceId": row["fingerprint"],
                    "source": row["source"],
                    "sourceBucket": row["source_bucket"],
                    "contentKind": row["content_kind"],
                    "domain": row["domain"],
                    "url": row["url"],
                    "productSignature": row["product_signature"],
                    "productTitle": row["product_title"],
                    "reviewLike": bool(row["review_like"]),
                    "acceptedInReviewCorpus": bool(row["accepted_in_review_corpus"]),
                    "relevanceScore": float(row["relevance_score"]),
                    "rejectionReasons": reasons,
                    "extractionMethod": row["extraction_method"],
                    "cleanExcerpt": row["clean_excerpt"],
                    "rating": row["rating"],
                    "helpfulVotes": int(row["helpful_votes"] or 0),
                    "confidenceSource": float(row["confidence_source"] or 0.0),
                    "rawSnapshotRef": row["raw_snapshot_ref"],
                    "retrievedAt": row["retrieved_at"],
                    "payload": payload,
                }
            )
        return items

    async def catalog_metrics(self) -> dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            total_cursor = await db.execute("SELECT COUNT(*) AS count FROM catalog_records")
            total_row = await total_cursor.fetchone()
            total_records = int(total_row["count"]) if total_row else 0

            source_cursor = await db.execute(
                """
                SELECT source, COUNT(*) AS count
                FROM catalog_records
                GROUP BY source
                ORDER BY source ASC
                """
            )
            source_rows = await source_cursor.fetchall()

            latest_cursor = await db.execute(
                """
                SELECT retrieved_at
                FROM catalog_records
                ORDER BY retrieved_at DESC
                LIMIT 1
                """
            )
            latest_row = await latest_cursor.fetchone()

        source_counts = {
            str(row["source"]): int(row["count"])
            for row in source_rows
        }
        latest_retrieved_at = str(latest_row["retrieved_at"]) if latest_row else None
        freshness_seconds = 999999
        if latest_retrieved_at:
            try:
                parsed = datetime.fromisoformat(latest_retrieved_at.replace("Z", "+00:00"))
                freshness_seconds = max(
                    0,
                    int((datetime.now(timezone.utc) - parsed).total_seconds()),
                )
            except ValueError:
                freshness_seconds = 999999
        return {
            "totalRecords": total_records,
            "sourceCounts": source_counts,
            "latestRetrievedAt": latest_retrieved_at,
            "freshnessSeconds": freshness_seconds,
        }

    async def prune_search_catalog_records(self) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                DELETE FROM catalog_records
                WHERE lower(url) LIKE '%/search?%'
                   OR lower(url) LIKE '%/sch/i.html%'
                   OR lower(url) LIKE '%/ref=%'
                """
            )
            await db.commit()
            return int(cursor.rowcount or 0)
