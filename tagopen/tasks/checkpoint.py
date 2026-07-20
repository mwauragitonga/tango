"""Checkpoint message helpers for durable task resume (esp. post-HITL)."""

from __future__ import annotations

import json
import time
from typing import Any


def load_checkpoint_messages(checkpoint_json: str | None) -> list[dict[str, Any]]:
    try:
        data = json.loads(checkpoint_json or "{}")
    except Exception:
        return []
    msgs = data.get("messages")
    return list(msgs) if isinstance(msgs, list) else []


def dump_checkpoint_messages(messages: list[dict[str, Any]], **extra: Any) -> str:
    slim = messages[-40:]
    payload: dict[str, Any] = {"messages": slim, "at": time.time()}
    payload.update(extra)
    return json.dumps(payload, default=str)


def _tool_call_ids_with_results(messages: list[dict[str, Any]]) -> set[str]:
    done: set[str] = set()
    for m in messages:
        if m.get("role") != "tool":
            continue
        tid = m.get("tool_call_id")
        if tid:
            done.add(str(tid))
    return done


def _iter_unanswered_tool_calls(
    messages: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Return [(tool_call_id, tool_name), ...] for assistant calls lacking a tool result."""
    answered = _tool_call_ids_with_results(messages)
    pending: list[tuple[str, str]] = []
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "")
            if not tid or tid in answered:
                continue
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            pending.append((tid, name))
    return pending


def append_approved_tool_result(
    messages: list[dict[str, Any]],
    *,
    tool_name: str,
    result: Any,
    tool_call_id: str | None = None,
    inject_continue_nudge: bool = True,
) -> list[dict[str, Any]]:
    """
    After HITL approve executes a tool outside the worker loop, stitch the
    result into checkpoint messages so resume does not re-request the same tool.
    """
    out = list(messages)
    pending = _iter_unanswered_tool_calls(out)
    tid = tool_call_id
    if not tid:
        for cand_id, cand_name in reversed(pending):
            if cand_name == tool_name:
                tid = cand_id
                break
    if not tid and pending:
        tid = pending[-1][0]
    if not tid:
        # No open tool_call — still record an explicit user note so the model
        # does not invent another identical HITL request.
        out.append(
            {
                "role": "user",
                "content": (
                    f"[Approval applied] `{tool_name}` was approved and executed.\n"
                    f"Result:\n{result}\n"
                    "Do not re-request the same tool. Continue with task_update / "
                    "task_complete (never task_pause just to finish)."
                ),
            }
        )
        return out

    out.append(
        {
            "role": "tool",
            "tool_call_id": tid,
            "content": str(result),
        }
    )
    if inject_continue_nudge:
        out.append(
            {
                "role": "user",
                "content": (
                    f"[Approval applied] `{tool_name}` already ran with the result above. "
                    "Do not call the same tool again. Update the plan and call "
                    "task_complete when done — do not task_pause for completion."
                ),
            }
        )
    return out


async def stitch_approval_into_task(
    store,
    task,
    *,
    tool_name: str,
    result: Any,
) -> Any:
    """Persist approved tool result into task.checkpoint_json; return updated task."""
    messages = load_checkpoint_messages(task.checkpoint_json)
    messages = append_approved_tool_result(
        messages, tool_name=tool_name, result=result
    )
    task.checkpoint_json = dump_checkpoint_messages(
        messages, last_approved_tool=tool_name
    )
    await store.save(task)
    return task
