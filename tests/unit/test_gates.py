"""Completion guard + approval audit shape (no Slack)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagopen.db.migrations import apply_migrations
from tagopen.tasks.models import StepStatus, TaskStatus
from tagopen.tasks.service import TaskService
from tagopen.tasks.store import SqliteTaskStore
from tagopen.tools.policy import decide
from tagopen.tasks.models import ToolRisk


@pytest.mark.asyncio
async def test_no_false_complete_and_approval_row(tmp_path: Path):
    db = tmp_path / "a.db"
    await apply_migrations(db)
    store = SqliteTaskStore(db)
    await store.open()
    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W",
        channel_id="C",
        thread_ts="3.0",
        requester_user_id="U",
        objective="write and deploy",
        acceptance_criteria="deployed",
    )
    task = await svc.set_plan(task, ["write", "deploy"])
    ok, reason = svc.can_complete(task)
    assert not ok and "incomplete" in reason.lower()
    d = decide("memory_append")
    assert d.risk == ToolRisk.WRITE and d.requires_approval
    aid = await store.create_approval(
        task_id=task.id,
        tool_name="memory_append",
        args_json='{"content":"x"}',
        requester_user_id="U",
    )
    row = await store.resolve_approval(aid, "approved", "U2")
    assert row is not None
    assert row["tool_name"] == "memory_append"
    task = await svc.update_step(task, "s1", status=StepStatus.COMPLETED, evidence="diff")
    task = await svc.update_step(task, "s2", status=StepStatus.COMPLETED, evidence="shipped")
    task = await svc.complete(task, summary="ok")
    assert task.status == TaskStatus.COMPLETED
    await store.close()
