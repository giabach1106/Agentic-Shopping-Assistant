from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        async with aiosqlite.connect(self._db_path) as db:
            for item in records:
                source = str(item.get("source") or "unknown").strip().lower()
                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or "").strip()
                if not source or not url or not title:
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
                        float(price) if price is not None else None,
                        float(rating) if rating is not None else None,
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
            await db.commit()
        return len(records)

    async def list_catalog_records(
        self,
        *,
        query: str | None = None,
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        clauses = ["1 = 1"]
        params: list[Any] = []
        if query and query.strip():
            terms = [part.strip().lower() for part in query.split() if part.strip()]
            for term in terms[:6]:
                clauses.append("(lower(title) LIKE ? OR lower(COALESCE(ingredient_text,'')) LIKE ?)")
                like = f"%{term}%"
                params.extend([like, like])

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
            ORDER BY retrieved_at DESC, updated_at DESC
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
