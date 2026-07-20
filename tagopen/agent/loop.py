"""Agent loop entry — classifies quick vs durable tasks and dispatches."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from tagopen.agent.runtime import run_inline_turn
from tagopen.memory.store import MessageStore
from tagopen.tasks.service import TaskService, should_queue_durable
from tagopen.tasks.store import get_task_store
from tagopen.tasks.worker import get_worker

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)

_BOT_MENTION = re.compile(r"<@[A-Z0-9]+>")
_STATUS_CMD = re.compile(r"^\s*(status|pause|resume|cancel)(?:\s+(.*))?$", re.I)


def strip_bot_mention(text: str) -> str:
    """Remove Slack bot mention tokens while preserving the requester text."""
    cleaned = _BOT_MENTION.sub("", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


async def run_agent_loop(
    app: "AsyncApp",
    workspace_id: str,
    channel_id: str,
    user_id: str,
    display_name: str,
    text: str,
    thread_ts: str,
    event_ts: str,
    store: MessageStore,
) -> None:
    text = strip_bot_mention(text)
    task_store = await get_task_store(workspace_id)
    svc = TaskService(task_store)

    # Thread commands against existing durable task
    existing = await task_store.get_by_thread(workspace_id, channel_id, thread_ts)
    m = _STATUS_CMD.match(text)
    if m and existing:
        verb = m.group(1).lower()
        reason = (m.group(2) or "").strip()
        if verb == "status":
            await app.client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts, text=svc.progress_text(existing)
            )
            return
        if verb == "pause":
            existing = await svc.pause(existing, reason)
            await app.client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts, text=svc.progress_text(existing)
            )
            return
        if verb == "resume":
            existing = await svc.resume(existing)
            await app.client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts, text="Resuming…\n" + svc.progress_text(existing)
            )
            get_worker(app).start()
            return
        if verb == "cancel":
            existing = await svc.cancel(existing, reason)
            await app.client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts, text=svc.progress_text(existing)
            )
            return

    if should_queue_durable(text):
        import time

        from tagopen.tasks.models import TaskStatus
        from tagopen.tasks.worker import WORKER_ID

        task = await svc.create_task(
            workspace_id=workspace_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            requester_user_id=user_id,
            objective=text,
        )
        await store.add_message(
            ts=event_ts,
            role="user",
            user_id=user_id,
            display_name=display_name,
            content=text,
            thread_ts=thread_ts,
        )
        # Take lease immediately so the background worker cannot double-run
        task.status = TaskStatus.RUNNING
        task.lease_owner = WORKER_ID
        task.lease_expires_at = time.time() + 120
        await task_store.save(task)
        get_worker(app).start()
        await get_worker(app).run_task(task, task_store)
        return

    await run_inline_turn(
        app=app,
        workspace_id=workspace_id,
        channel_id=channel_id,
        user_id=user_id,
        display_name=display_name,
        text=text,
        thread_ts=thread_ts,
        event_ts=event_ts,
        store=store,
    )


# Back-compat for memory writer / tests
def _handle_memory_tool(channel_id: str, fn_name: str, args: dict) -> None:
    from tagopen.memory.writer import apply_memory_tool

    apply_memory_tool(channel_id, fn_name, args)
