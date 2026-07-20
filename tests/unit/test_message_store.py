"""Message store ordering, thread scope, and search."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagopen.db.migrations import apply_migrations
from tagopen.memory.store import MessageStore


@pytest.mark.asyncio
async def test_thread_scoped_recent_and_order(tmp_path: Path):
    db = tmp_path / "m.db"
    await apply_migrations(db)
    store = MessageStore(db, "C1")
    await store.open()
    await store.add_message("1.0", "user", "U1", "alice", "hello channel", thread_ts="1.0")
    await store.add_message("1.1", "user", "U1", "alice", "thread a", thread_ts="1.0")
    await store.add_message("2.0", "user", "U2", "bob", "other thread", thread_ts="2.0")
    recent = await store.get_recent_messages(limit=10, thread_ts="1.0")
    contents = [r["content"] for r in recent]
    assert "other thread" not in contents
    assert contents == ["hello channel", "thread a"]
    # deterministic id order
    await store.add_message("1.2", "assistant", "agent", "agent", "reply", thread_ts="1.0")
    recent2 = await store.get_recent_messages(limit=10, thread_ts="1.0")
    assert [r["content"] for r in recent2][-1] == "reply"
    hits = await store.search("thread")
    assert len(hits) >= 1
    await store.close()
