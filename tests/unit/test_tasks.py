"""Unit tests for durable task state machine and completion guards."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from tagopen.db.migrations import apply_migrations
from tagopen.tasks.models import StepStatus, TaskStatus
from tagopen.tasks.service import TaskService, looks_like_quick_qa, should_queue_durable
from tagopen.tasks.store import SqliteTaskStore


@pytest.fixture
async def store(tmp_path: Path):
    db = tmp_path / "t.db"
    await apply_migrations(db)
    s = SqliteTaskStore(db)
    await s.open()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_plan_complete_and_guard(store: SqliteTaskStore):
    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W1",
        channel_id="C1",
        thread_ts="1.0",
        requester_user_id="U1",
        objective="Ship the feature",
        acceptance_criteria="PR merged evidence",
    )
    assert task.status == TaskStatus.QUEUED
    task = await svc.set_plan(task, ["research", "implement", "verify"])
    assert task.steps[0].status == StepStatus.IN_PROGRESS
    with pytest.raises(ValueError):
        await svc.complete(task)
    task = await svc.update_step(task, "s1", status=StepStatus.COMPLETED, evidence="notes")
    task = await svc.update_step(task, "s2", status=StepStatus.COMPLETED, evidence="diff")
    task = await svc.update_step(task, "s3", status=StepStatus.COMPLETED, evidence="checks green")
    assert task.status == TaskStatus.VERIFYING
    task = await svc.complete(task, summary="done")
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_lease_requeue(store: SqliteTaskStore):
    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W1",
        channel_id="C1",
        thread_ts="2.0",
        requester_user_id="U1",
        objective="long job",
    )
    task.status = TaskStatus.RUNNING
    task.lease_owner = "dead-worker"
    task.lease_expires_at = 1.0
    await store.save(task)
    n = await store.requeue_expired_leases()
    assert n == 1
    task = await store.get(task.id)
    assert task.status == TaskStatus.RESUME_PENDING


@pytest.mark.asyncio
async def test_slack_event_idempotency(store: SqliteTaskStore):
    assert await store.claim_slack_event("W1", "evt-1", None) is True
    assert await store.claim_slack_event("W1", "evt-1", None) is False


def test_classifier():
    assert looks_like_quick_qa("What is the status?")
    assert should_queue_durable("Please implement the migration then deploy and verify")
    assert not should_queue_durable("What time is standup?")


def test_step_status_done_alias():
    assert StepStatus.from_tool_arg("done") == StepStatus.COMPLETED
    assert StepStatus.from_tool_arg("complete") == StepStatus.COMPLETED
    assert StepStatus.from_tool_arg("COMPLETED") == StepStatus.COMPLETED
    assert StepStatus.from_tool_arg("in_progress") == StepStatus.IN_PROGRESS
    assert StepStatus.from_tool_arg(None) == StepStatus.PENDING
    with pytest.raises(ValueError):
        StepStatus.from_tool_arg("nope")


@pytest.mark.asyncio
async def test_task_update_accepts_done_alias(store: SqliteTaskStore):
    from tagopen.tasks.tools import dispatch_task_tool

    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W1",
        channel_id="C1",
        thread_ts="3.0",
        requester_user_id="U1",
        objective="alias canary",
    )
    task = await svc.set_plan(task, ["run check", "finish"])
    task, text = await dispatch_task_tool(
        svc, task, "task_update", {"step_id": "s1", "status": "done", "evidence": "ok"}
    )
    assert task.steps[0].status == StepStatus.COMPLETED
    assert "Invalid step status" not in text
