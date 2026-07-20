"""SQLite + FTS5 message store — one DB per workspace."""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

from tagopen.config import settings
from tagopen.db.connection import open_workspace_db

logger = logging.getLogger(__name__)


class MessageStore:
    def __init__(self, db_path: Path, channel_id: str) -> None:
        self._db_path = db_path
        self._channel_id = channel_id
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db = await open_workspace_db(self._db_path)

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None
        return self._db

    async def add_message(
        self,
        ts: str,
        role: str,
        user_id: str,
        display_name: str,
        content: str,
        thread_ts: str | None = None,
        tool_calls: int = 0,
    ) -> None:
        await self.db.execute(
            """INSERT INTO messages (ts, thread_ts, channel_id, role, user_id, display_name, content, tool_calls)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, thread_ts, self._channel_id, role, user_id, display_name, content, tool_calls),
        )
        await self.db.commit()

    async def get_recent_messages(
        self, limit: int = 50, thread_ts: str | None = None
    ) -> list[aiosqlite.Row]:
        """Recent messages ordered by autoincrement id (deterministic).

        When thread_ts is set, scope to that thread (parent + replies).
        """
        if thread_ts:
            async with self.db.execute(
                """SELECT ts, role, user_id, display_name, content, thread_ts
                   FROM messages
                   WHERE channel_id = ?
                     AND (thread_ts = ? OR ts = ?)
                   ORDER BY id DESC
                   LIMIT ?""",
                (self._channel_id, thread_ts, thread_ts, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self.db.execute(
                """SELECT ts, role, user_id, display_name, content, thread_ts
                   FROM messages
                   WHERE channel_id = ?
                   ORDER BY id DESC
                   LIMIT ?""",
                (self._channel_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return list(reversed(rows))

    async def search(self, query: str, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.db.execute(
            """SELECT m.ts, m.role, m.display_name, m.content
               FROM messages_fts f
               JOIN messages m ON m.id = f.rowid
               WHERE messages_fts MATCH ? AND m.channel_id = ?
               ORDER BY rank
               LIMIT ?""",
            (query, self._channel_id, limit),
        ) as cursor:
            return await cursor.fetchall()

    async def get_thread_model(self, thread_ts: str) -> str | None:
        async with self.db.execute(
            """SELECT model FROM thread_models
               WHERE channel_id = ? AND thread_ts = ?""",
            (self._channel_id, thread_ts),
        ) as cursor:
            row = await cursor.fetchone()
        return row["model"] if row else None

    async def set_thread_model(self, thread_ts: str, model: str) -> None:
        await self.db.execute(
            """INSERT INTO thread_models (channel_id, thread_ts, model)
               VALUES (?, ?, ?)
               ON CONFLICT(channel_id, thread_ts) DO UPDATE SET
                 model = excluded.model,
                 updated_at = unixepoch('now', 'subsec')""",
            (self._channel_id, thread_ts, model),
        )
        await self.db.commit()

    async def clear_thread_model(self, thread_ts: str) -> None:
        await self.db.execute(
            """DELETE FROM thread_models WHERE channel_id = ? AND thread_ts = ?""",
            (self._channel_id, thread_ts),
        )
        await self.db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None


_stores: dict[tuple[str, str], MessageStore] = {}


async def get_store(workspace_id: str, channel_id: str) -> MessageStore:
    key = (workspace_id, channel_id)
    if key not in _stores:
        db_path = settings.data_dir / "workspaces" / workspace_id / "messages.db"
        store = MessageStore(db_path=db_path, channel_id=channel_id)
        await store.open()
        _stores[key] = store
    return _stores[key]
