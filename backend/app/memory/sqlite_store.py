from __future__ import annotations

import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_cursor(updated_at: str, session_id: str) -> str:
    return f"{updated_at}|{session_id}"


def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
    if not cursor or "|" not in cursor:
        return None
    updated_at, session_id = cursor.split("|", 1)
    if not updated_at or not session_id:
        return None
    return updated_at, session_id


class SQLiteSessionStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    user_sub TEXT,
                    user_email TEXT,
                    title TEXT,
                    latest_status TEXT,
                    latest_verdict TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    meta_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
                """
            )
            await self._ensure_message_columns(db)
            await self._ensure_session_columns(db)
            await db.commit()

    async def create_session(
        self,
        user_sub: str | None = None,
        user_email: str | None = None,
    ) -> dict[str, str]:
        session_id = str(uuid.uuid4())
        now = _now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (
                    session_id,
                    created_at,
                    updated_at,
                    user_sub,
                    user_email,
                    title,
                    latest_status,
                    latest_verdict
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, user_sub, user_email, None, "CREATED", None),
            )
            await db.commit()
        return {"sessionId": session_id, "createdAt": now, "updatedAt": now}

    async def session_exists(
        self,
        session_id: str,
        user_sub: str | None = None,
    ) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT 1
                FROM sessions
                WHERE session_id = ?
                AND (? IS NULL OR user_sub IS NULL OR user_sub = ?)
                LIMIT 1
                """,
                (session_id, user_sub, user_sub),
            )
            row = await cursor.fetchone()
            return row is not None

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO messages (session_id, role, content, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    json.dumps(meta, sort_keys=True) if meta else None,
                    now,
                ),
            )
            await db.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            await db.commit()

    async def update_session_metadata(
        self,
        session_id: str,
        title: str | None = None,
        latest_status: str | None = None,
        latest_verdict: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE sessions
                SET
                    updated_at = ?,
                    title = COALESCE(?, title),
                    latest_status = COALESCE(?, latest_status),
                    latest_verdict = COALESCE(?, latest_verdict)
                WHERE session_id = ?
                """,
                (_now_iso(), title, latest_status, latest_verdict, session_id),
            )
            await db.commit()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT role, content, meta_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_meta = item.get("meta_json")
            meta: dict[str, Any] | None = None
            if isinstance(raw_meta, str) and raw_meta.strip():
                try:
                    loaded = json.loads(raw_meta)
                except json.JSONDecodeError:
                    loaded = None
                if isinstance(loaded, dict):
                    meta = loaded
            payload.append(
                {
                    "role": item["role"],
                    "content": item["content"],
                    "meta": meta,
                    "created_at": item["created_at"],
                }
            )
        return payload

    async def get_session(self, session_id: str) -> dict[str, str | None] | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    session_id,
                    created_at,
                    updated_at,
                    user_sub,
                    user_email,
                    title,
                    latest_status,
                    latest_verdict
                FROM sessions
                WHERE session_id = ?
                LIMIT 1
                """,
                (session_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "sessionId": row["session_id"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "userSub": row["user_sub"],
            "userEmail": row["user_email"],
            "title": row["title"],
            "latestStatus": row["latest_status"],
            "latestVerdict": row["latest_verdict"],
        }

    async def list_sessions(
        self,
        limit: int,
        cursor: str | None,
        user_sub: str | None = None,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(limit, 50))
        cursor_parts = _decode_cursor(cursor)
        params: list[Any] = []
        clauses = ["1 = 1"]
        if user_sub:
            clauses.append("user_sub = ?")
            params.append(user_sub)
        if cursor_parts:
            updated_at, session_id = cursor_parts
            clauses.append("(updated_at < ? OR (updated_at = ? AND session_id < ?))")
            params.extend([updated_at, updated_at, session_id])

        query = f"""
            SELECT
                session_id,
                created_at,
                updated_at,
                title,
                latest_status,
                latest_verdict
            FROM sessions
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at DESC, session_id DESC
            LIMIT ?
        """
        params.append(safe_limit + 1)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor_obj = await db.execute(query, params)
            rows = await cursor_obj.fetchall()

        has_next = len(rows) > safe_limit
        visible_rows = rows[:safe_limit]
        items = [
            {
                "sessionId": row["session_id"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "title": row["title"] or "Untitled session",
                "status": row["latest_status"] or "CREATED",
                "verdict": row["latest_verdict"],
            }
            for row in visible_rows
        ]
        next_cursor = None
        if has_next and visible_rows:
            last = visible_rows[-1]
            next_cursor = _encode_cursor(last["updated_at"], last["session_id"])

        return {"items": items, "nextCursor": next_cursor}

    async def _ensure_session_columns(self, db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA table_info(sessions)")
        rows = await cursor.fetchall()
        existing = {str(row[1]) for row in rows}
        alter_statements = {
            "user_sub": "ALTER TABLE sessions ADD COLUMN user_sub TEXT",
            "user_email": "ALTER TABLE sessions ADD COLUMN user_email TEXT",
            "title": "ALTER TABLE sessions ADD COLUMN title TEXT",
            "latest_status": "ALTER TABLE sessions ADD COLUMN latest_status TEXT",
            "latest_verdict": "ALTER TABLE sessions ADD COLUMN latest_verdict TEXT",
        }
        for column, statement in alter_statements.items():
            if column not in existing:
                await db.execute(statement)

    async def _ensure_message_columns(self, db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA table_info(messages)")
        rows = await cursor.fetchall()
        existing = {str(row[1]) for row in rows}
        if "meta_json" not in existing:
            await db.execute("ALTER TABLE messages ADD COLUMN meta_json TEXT")
