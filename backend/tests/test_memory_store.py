from __future__ import annotations

import asyncio
from pathlib import Path

from app.memory.sqlite_store import SQLiteSessionStore


def test_sqlite_memory_read_write(tmp_path: Path) -> None:
    async def run_test() -> None:
        store = SQLiteSessionStore(tmp_path / "memory.sqlite3")
        await store.initialize()

        created = await store.create_session()
        session_id = created["sessionId"]
        await store.append_message(session_id, "user", "hello")
        await store.append_message(session_id, "assistant", "hi there")

        messages = await store.get_messages(session_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    asyncio.run(run_test())

