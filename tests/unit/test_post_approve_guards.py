"""Guards against post-approve task_pause / re-HITL loops."""

from __future__ import annotations

from pathlib import Path

import pytest

from tagopen.db.migrations import apply_migrations
from tagopen.tasks.checkpoint import (
    append_approved_tool_result,
    dump_checkpoint_messages,
    load_checkpoint_messages,
)
from tagopen.tasks.models import StepStatus, TaskStatus
from tagopen.tasks.service import TaskService
from tagopen.tasks.store import SqliteTaskStore
from tagopen.tasks.tools import dispatch_task_tool
from tagopen.tools.executor import ApprovalRequired, ToolExecutor
from tagopen.tools.policy import decide


@pytest.fixture
async def store(tmp_path: Path):
    db = tmp_path / "t.db"
    await apply_migrations(db)
    s = SqliteTaskStore(db)
    await s.open()
    yield s
    await s.close()


def test_append_approved_tool_result_stitches_orphan_tool_call():
    messages = [
        {"role": "user", "content": "do it"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_rp1",
                    "type": "function",
                    "function": {
                        "name": "run_python",
                        "arguments": '{"code":"print(1+1)"}',
                    },
                }
            ],
        },
    ]
    out = append_approved_tool_result(
        messages, tool_name="run_python", result="2\n"
    )
    assert out[-2]["role"] == "tool"
    assert out[-2]["tool_call_id"] == "call_rp1"
    assert "2" in out[-2]["content"]
    assert out[-1]["role"] == "user"
    assert "Do not call the same tool again" in out[-1]["content"]
    # round-trip through dump/load
    dumped = dump_checkpoint_messages(out)
    loaded = load_checkpoint_messages(dumped)
    assert loaded[-2]["tool_call_id"] == "call_rp1"


@pytest.mark.asyncio
async def test_task_pause_refused_when_ready_to_complete(store: SqliteTaskStore):
    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W1",
        channel_id="C1",
        thread_ts="10.0",
        requester_user_id="U1",
        objective="finish after approve",
        acceptance_criteria="APPROVE_SHORT_OK",
    )
    task = await svc.set_plan(task, ["run python", "complete"])
    task = await svc.update_step(
        task, "s1", status=StepStatus.COMPLETED, evidence="2"
    )
    task = await svc.update_step(
        task, "s2", status=StepStatus.COMPLETED, evidence="APPROVE_SHORT_OK"
    )
    assert svc.can_complete(task)[0] is True
    before = task.status
    task, text = await dispatch_task_tool(
        svc, task, "task_pause", {"reason": "waiting for task_complete"}
    )
    assert "Refuse task_pause" in text
    assert task.status == before
    assert task.status != TaskStatus.PAUSED


@pytest.mark.asyncio
async def test_task_pause_refused_for_completion_reason(store: SqliteTaskStore):
    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W1",
        channel_id="C1",
        thread_ts="11.0",
        requester_user_id="U1",
        objective="mid work",
    )
    task = await svc.set_plan(task, ["a", "b"])
    task, text = await dispatch_task_tool(
        svc,
        task,
        "task_pause",
        {"reason": "Paused until I can call task_complete with APPROVE_SHORT_OK"},
    )
    assert "Refuse task_pause" in text
    assert task.status != TaskStatus.PAUSED


@pytest.mark.asyncio
async def test_task_pause_allowed_for_real_blocker(store: SqliteTaskStore):
    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W1",
        channel_id="C1",
        thread_ts="12.0",
        requester_user_id="U1",
        objective="need human",
    )
    task = await svc.set_plan(task, ["ask user"])
    task, _text = await dispatch_task_tool(
        svc, task, "task_pause", {"reason": "Need Slack user to pick a date"}
    )
    assert task.status == TaskStatus.PAUSED


@pytest.mark.asyncio
async def test_executor_skips_rehitl_for_recent_same_approval(store: SqliteTaskStore):
    assert decide("run_python").requires_approval
    svc = TaskService(store)
    task = await svc.create_task(
        workspace_id="W1",
        channel_id="C1",
        thread_ts="13.0",
        requester_user_id="U1",
        objective="python once",
    )
    args = {"code": "print(1+1)"}
    import json

    args_json = json.dumps(args)
    aid = await store.create_approval(
        task_id=task.id,
        tool_name="run_python",
        args_json=args_json,
        requester_user_id="U1",
    )
    await store.resolve_approval(aid, "approved", "U1")

    ex = ToolExecutor(
        app=None,
        workspace_id="W1",
        channel_id="C1",
        thread_ts="13.0",
        requester_user_id="U1",
        task_store=store,
        task=task,
    )
    # Different key order must still match
    result = await ex.execute("run_python", {"code": "print(1+1)"})
    assert "already approved" in str(result)
    assert not isinstance(result, ApprovalRequired)

    # A genuinely new call still requires approval
    with pytest.raises(ApprovalRequired):
        await ex.execute("run_python", {"code": "print(2+2)"})
