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
