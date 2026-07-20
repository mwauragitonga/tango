"""Policy-aware tool executor with audit and optional Slack HITL approval."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from tagopen.config import settings
from tagopen.tasks.models import Task, TaskStatus, ToolRisk
from tagopen.tasks.store import SqliteTaskStore
from tagopen.tasks.tools import TASK_TOOL_NAMES, dispatch_task_tool
from tagopen.tasks.service import TaskService
from tagopen.tools.policy import args_hash, decide, result_hash
from tagopen.tools.registry import dispatch_tool, get_channel_tools
from tagopen.tools.sandbox import run_python_sandboxed

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)


class ApprovalRequired(Exception):
    def __init__(self, approval_id: str, tool_name: str, args: dict[str, Any]):
        self.approval_id = approval_id
        self.tool_name = tool_name
        self.args = args
        super().__init__(f"Approval required for {tool_name}")


class ToolExecutor:
    def __init__(
        self,
        *,
        app: "AsyncApp | None",
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
        requester_user_id: str,
        task_store: SqliteTaskStore,
        task: Task | None = None,
        channel_policy: dict[str, Any] | None = None,
        message_store: Any | None = None,
    ) -> None:
        self.app = app
        self.workspace_id = workspace_id
        self.channel_id = channel_id
        self.thread_ts = thread_ts
        self.requester_user_id = requester_user_id
        self.task_store = task_store
        self.task = task
        self.channel_policy = channel_policy or {}
        self.message_store = message_store

    async def execute(self, fn_name: str, args: dict[str, Any]) -> Any:
        started = time.time()
        decision = decide(
            fn_name,
            channel_policy=self.channel_policy,
            saas_mode=settings.saas_mode,
        )
        if not decision.allowed:
            return f"Tool blocked: {decision.reason}"

        if decision.requires_approval and self.task is not None:
            aid = await self.task_store.create_approval(
                task_id=self.task.id,
                tool_name=fn_name,
                args_json=json.dumps(args),
                requester_user_id=self.requester_user_id,
            )
            svc = TaskService(self.task_store)
            self.task = await svc.mark_waiting_approval(
                self.task,
                f"Approve `{fn_name}` (id `{aid}`): reply `approve {aid}` or `deny {aid}`",
            )
            if self.app:
                await self.app.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=self.thread_ts,
                    text=(
                        f"⚠️ Approval needed for `{fn_name}`\n"
                        f"```{json.dumps(args, indent=2)[:1500]}```\n"
                        f"Reply `approve {aid}` or `deny {aid}` in this thread."
                    ),
                )
            raise ApprovalRequired(aid, fn_name, args)

        try:
            result = await asyncio.wait_for(
                self._dispatch(fn_name, args),
                timeout=settings.tool_timeout_seconds,
            )
            success = True
            error_class = ""
        except ApprovalRequired:
            raise
        except Exception as e:
            result = f"Tool error: {e}"
            success = False
            error_class = type(e).__name__
            logger.exception("Tool %s failed", fn_name)

        latency = (time.time() - started) * 1000
        await self.task_store.record_tool_execution(
            task_id=self.task.id if self.task else None,
            workspace_id=self.workspace_id,
            channel_id=self.channel_id,
            thread_ts=self.thread_ts,
            tool_name=fn_name,
            args_hash=args_hash(args),
            result_hash=result_hash(result),
            risk=decision.risk.value,
            success=success,
            latency_ms=latency,
            error_class=error_class,
            requester_user_id=self.requester_user_id,
        )
        return result

    async def _dispatch(self, fn_name: str, args: dict[str, Any]) -> Any:
        if fn_name in TASK_TOOL_NAMES:
            if self.task is None:
                return "No active durable task for task_* tools."
            svc = TaskService(self.task_store)
            self.task, text = await dispatch_task_tool(svc, self.task, fn_name, args)
            return text

        if fn_name == "run_python":
            return await asyncio.to_thread(run_python_sandboxed, args.get("code", ""))

        if fn_name == "search_channel_history":
            if self.message_store is None:
                return "search_channel_history unavailable (no store)"
            rows = await self.message_store.search(args.get("query", ""), limit=int(args.get("limit") or 10))
            if not rows:
                return "No matches."
            lines = []
            for r in rows:
                lines.append(f"- [{r['display_name']}] {r['content'][:300]}")
            return "\n".join(lines)

        if fn_name == "skill_view":
            from tagopen.agent.skill_catalog import skill_view
            from tagopen.agent.skill_lifecycle import record_skill_use

            name = str(args.get("name") or "")
            body = skill_view(self.channel_id, name)
            try:
                await record_skill_use(self.task_store, self.channel_id, name, success=True)
            except Exception:
                logger.exception("skill_stats update failed")
            return body

        if fn_name in ("memory_append", "memory_replace"):
            from tagopen.memory.writer import apply_memory_tool

            apply_memory_tool(self.channel_id, fn_name, args)
            return "Memory updated."

        # schedule tools
        if fn_name in {
            "schedule_task",
            "list_schedules",
            "pause_schedule",
            "resume_schedule",
            "delete_schedule",
        }:
            from tagopen.scheduler.tools import dispatch_schedule_tool

            return await dispatch_schedule_tool(
                self.task_store,
                self.workspace_id,
                self.channel_id,
                self.requester_user_id,
                fn_name,
                args,
            )

        return await dispatch_tool(fn_name, args, channel_id=self.channel_id)
