"""Durable task worker — leases, retries, progress, resume from checkpoint."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from typing import TYPE_CHECKING, Any

from tagopen.config import settings
from tagopen.context.engine import ContextEngine
from tagopen.llm.gateway import LLMRequestContext, complete
from tagopen.memory.store import MessageStore, get_store
from tagopen.tasks.models import Task, TaskStatus, TERMINAL_STATUSES
from tagopen.tasks.service import TaskService
from tagopen.tasks.store import SqliteTaskStore, get_task_store
from tagopen.tasks.tools import TASK_TOOL_SCHEMAS
from tagopen.tools.executor import ApprovalRequired, ToolExecutor
from tagopen.tools.registry import get_channel_tools
from tagopen.slack_format import to_slack_mrkdwn

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)

WORKER_ID = f"{socket.gethostname()}-{id(object())}"


class TaskWorker:
    def __init__(self, app: "AsyncApp") -> None:
        self.app = app
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._last_progress: dict[str, float] = {}

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            logger.info("Task worker started id=%s", WORKER_ID)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                root = settings.data_dir / "workspaces"
                if root.exists():
                    for ws_dir in root.iterdir():
                        if not ws_dir.is_dir():
                            continue
                        store = await get_task_store(ws_dir.name)
                        n = await store.requeue_expired_leases()
                        if n:
                            logger.info("Requeued %s expired leases in %s", n, ws_dir.name)
                        claimed = await store.claim_next(WORKER_ID)
                        if claimed:
                            await self.run_task(claimed, store)
                            continue
            except Exception:
                logger.exception("Worker loop error")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    async def run_task(self, task: Task, store: SqliteTaskStore) -> None:
        if task.status in TERMINAL_STATUSES:
            return
        svc = TaskService(store)
        msg_store = await get_store(task.workspace_id, task.channel_id)
        engine = ContextEngine()
        engine.usage.context_window = settings.model_context_window

        tools = await get_channel_tools(task.channel_id)
        tools = list(tools) + TASK_TOOL_SCHEMAS

        # Immediate ack on first claim from queued
        if task.turns_used == 0:
            await self._post(
                task,
                f"Got it — working on this as a durable task (`{task.id[:8]}`). "
                "I'll post progress as I go.",
            )

        user_map = {task.requester_user_id: task.requester_user_id}
        messages: list[dict] = []
        try:
            checkpoint = json.loads(task.checkpoint_json or "{}")
            if checkpoint.get("messages"):
                messages = checkpoint["messages"]
        except Exception:
            messages = []

        executor = ToolExecutor(
            app=self.app,
            workspace_id=task.workspace_id,
            channel_id=task.channel_id,
            thread_ts=task.thread_ts,
            requester_user_id=task.requester_user_id,
            task_store=store,
            task=task,
            message_store=msg_store,
        )

        failover_notice = None
        final_text = ""
        max_rounds = min(task.max_turns - task.turns_used, settings.max_tool_rounds)

        for _ in range(max(1, max_rounds)):
            await store.heartbeat(task.id, WORKER_ID)
            task = await store.get(task.id) or task
            if task.status in {
                TaskStatus.PAUSED,
                TaskStatus.WAITING_APPROVAL,
                TaskStatus.WAITING_EXTERNAL,
                TaskStatus.CANCELLED,
            }:
                return
            if task.status in TERMINAL_STATUSES:
                return

            system, built = await engine.build_context(
                channel_id=task.channel_id,
                user_map=user_map,
                tool_schemas=tools,
                store=msg_store,
                thread_ts=task.thread_ts,
                current_user=task.requester_user_id,
                current_text=task.objective,
                task=task,
            )
            if not messages:
                messages = built

            ctx = LLMRequestContext(
                workspace_id=task.workspace_id,
                channel_id=task.channel_id,
                thread_ts=task.thread_ts,
                slack_user_id=task.requester_user_id,
                task_id=task.id,
                purpose="agent",
            )
            try:
                response, notice = await complete(
                    ctx,
                    messages=[{"role": "system", "content": system}] + messages,
                    tools=tools,
                    tool_choice="auto",
                    task_store=store,
                )
            except Exception as e:
                # transient → leave resume_pending for retry
                logger.warning("LLM error on task %s: %s", task.id, e)
                task.status = TaskStatus.RESUME_PENDING
                task.blocker = f"LLM error: {e}"
                task.lease_owner = None
                task.lease_expires_at = None
                await store.save(task)
                await self._maybe_progress(task, svc, force=True)
                return

            if notice and not failover_notice:
                failover_notice = notice
            usage = getattr(response, "usage", None)
            if usage:
                engine.update_usage(
                    int(getattr(usage, "prompt_tokens", 0) or 0),
                    int(getattr(usage, "completion_tokens", 0) or 0),
                    int(getattr(usage, "total_tokens", 0) or 0),
                )
                if engine.should_compact():
                    messages, summary = await engine.compact(
                        messages=messages,
                        task=task,
                        llm_complete=lambda c, messages: complete(
                            c,
                            messages=messages,
                            task_store=store,
                        ),
                        ctx=ctx,
                        task_store=store,
                    )
                    if summary:
                        messages = [
                            {"role": "user", "content": f"[Earlier context summary]\n{summary}"}
                        ] + messages

            choice = response.choices[0]
            msg = choice.message
            task.turns_used += 1
            if not msg.tool_calls:
                final_text = msg.content or ""
                break

            messages.append(msg.model_dump(exclude_none=True))
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments or "{}")
                try:
                    result = await executor.execute(fn_name, fn_args)
                    task = executor.task or task
                except ApprovalRequired as ar:
                    await self._checkpoint(store, task, messages)
                    await self._post(
                        task,
                        f"Paused for approval of `{ar.tool_name}` (`{ar.approval_id}`).",
                    )
                    return
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": str(result)}
                )
            await self._checkpoint(store, task, messages)
            await self._maybe_progress(task, svc)
            if task.status in TERMINAL_STATUSES | {
                TaskStatus.PAUSED,
                TaskStatus.WAITING_APPROVAL,
            }:
                if task.status == TaskStatus.COMPLETED:
                    await self._post(task, final_text or task.to_summary())
                return
        else:
            final_text = final_text or "Still working — hit turn budget for this slice; will resume."
            task.status = TaskStatus.RESUME_PENDING
            task.lease_owner = None
            task.lease_expires_at = None

        if failover_notice:
            final_text = f"{failover_notice}\n\n{final_text}"
        await self._checkpoint(store, task, messages)
        await store.save(task)
        if final_text:
            await self._post(task, final_text)
            await msg_store.add_message(
                ts=str(time.time()),
                role="assistant",
                user_id="agent",
                display_name="agent",
                content=final_text,
                thread_ts=task.thread_ts,
            )

    async def _checkpoint(self, store: SqliteTaskStore, task: Task, messages: list[dict]) -> None:
        # Keep last 40 messages in checkpoint to bound size
        slim = messages[-40:]
        task.checkpoint_json = json.dumps({"messages": slim, "at": time.time()}, default=str)
        await store.save(task)
        await store.record_event(task.id, "checkpoint", {"turns": task.turns_used})

    async def _maybe_progress(self, task: Task, svc: TaskService, force: bool = False) -> None:
        now = time.time()
        last = self._last_progress.get(task.id, 0)
        if not force and now - last < settings.progress_interval_seconds:
            return
        self._last_progress[task.id] = now
        await self._post(task, svc.progress_text(task))

    async def _post(self, task: Task, text: str) -> None:
        try:
            await asyncio.wait_for(
                self.app.client.chat_postMessage(
                    channel=task.channel_id,
                    thread_ts=task.thread_ts,
                    text=to_slack_mrkdwn(text),
                ),
                timeout=settings.slack_timeout_seconds,
            )
        except Exception:
            logger.exception("Failed to post progress for task %s", task.id)


_worker: TaskWorker | None = None


def get_worker(app: "AsyncApp") -> TaskWorker:
    global _worker
    if _worker is None:
        _worker = TaskWorker(app)
    return _worker
