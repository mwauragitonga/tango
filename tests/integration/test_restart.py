"""Integration: restart recovery via expired lease requeue."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagopen.db.migrations import apply_migrations
from tagopen.tasks.models import TaskStatus
from tagopen.tasks.service import TaskService
from tagopen.tasks.store import SqliteTaskStore


@pytest.mark.asyncio
async def test_restart_resume(tmp_path: Path):
    db = tmp_path / "i.db"
    await apply_migrations(db)
    store = SqliteTaskStore(db)
    await store.open()
    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W",
        channel_id="C",
        thread_ts="9.0",
        requester_user_id="U",
        objective="multi step research then write report then verify",
    )
    task = await svc.set_plan(task, ["a", "b", "c"])
    task.lease_owner = "old"
    task.lease_expires_at = 0
    task.checkpoint_json = '{"messages":[{"role":"user","content":"hi"}]}'
    await store.save(task)
    assert await store.requeue_expired_leases() == 1
    claimed = await store.claim_next("new-worker")
    assert claimed is not None
    assert claimed.id == task.id
    assert claimed.status == TaskStatus.RUNNING
    await store.close()
