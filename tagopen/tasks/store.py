"""Durable task repository (SQLite Contabo / protocol for Postgres SaaS)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

import aiosqlite

from tagopen.db.connection import open_workspace_db
from tagopen.tasks.models import (
    Task,
    TaskStatus,
    TaskStep,
    UsageRecord,
    new_id,
)


class TaskRepository(Protocol):
    async def get(self, task_id: str) -> Task | None: ...
    async def save(self, task: Task) -> None: ...
    async def get_by_thread(
        self, workspace_id: str, channel_id: str, thread_ts: str
    ) -> Task | None: ...
    async def claim_next(self, worker_id: str, lease_seconds: float = 120.0) -> Task | None: ...
    async def requeue_expired_leases(self) -> int: ...
    async def record_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None: ...
    async def claim_slack_event(
        self, workspace_id: str, event_key: str, task_id: str | None = None
    ) -> bool: ...
    async def record_usage(self, usage: UsageRecord) -> None: ...


class SqliteTaskStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db = await open_workspace_db(self._db_path)

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None
        return self._db

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _row_to_task(self, row: aiosqlite.Row) -> Task:
        steps_raw = json.loads(row["steps_json"] or "[]")
        steps = [TaskStep.from_dict(s) for s in steps_raw]
        return Task(
            id=row["id"],
            workspace_id=row["workspace_id"],
            channel_id=row["channel_id"],
            thread_ts=row["thread_ts"],
            requester_user_id=row["requester_user_id"],
            objective=row["objective"],
            status=TaskStatus(row["status"]),
            acceptance_criteria=row["acceptance_criteria"] or "",
            steps=steps,
            current_step_id=row["current_step_id"],
            next_action=row["next_action"] or "",
            blocker=row["blocker"] or "",
            turns_used=int(row["turns_used"] or 0),
            max_turns=int(row["max_turns"] or 40),
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            checkpoint_json=row["checkpoint_json"] or "{}",
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            completed_at=row["completed_at"],
        )

    async def get(self, task_id: str) -> Task | None:
        async with self.db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
        return self._row_to_task(row) if row else None

    async def get_by_thread(
        self, workspace_id: str, channel_id: str, thread_ts: str
    ) -> Task | None:
        async with self.db.execute(
            """SELECT * FROM tasks
               WHERE workspace_id = ? AND channel_id = ? AND thread_ts = ?
               ORDER BY created_at DESC LIMIT 1""",
            (workspace_id, channel_id, thread_ts),
        ) as cur:
            row = await cur.fetchone()
        return self._row_to_task(row) if row else None

    async def list_open_for_channel(self, workspace_id: str, channel_id: str) -> list[Task]:
        async with self.db.execute(
            """SELECT * FROM tasks
               WHERE workspace_id = ? AND channel_id = ?
                 AND status NOT IN ('completed', 'failed', 'cancelled', 'suspended')
               ORDER BY updated_at DESC""",
            (workspace_id, channel_id),
        ) as cur:
            rows = await cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def save(self, task: Task) -> None:
        now = time.time()
        task.updated_at = now
        if not task.created_at:
            task.created_at = now
        steps_json = json.dumps([s.to_dict() for s in task.steps])
        await self.db.execute(
            """INSERT INTO tasks (
                 id, workspace_id, channel_id, thread_ts, requester_user_id, objective,
                 acceptance_criteria, status, steps_json, current_step_id, next_action,
                 blocker, turns_used, max_turns, lease_owner, lease_expires_at,
                 checkpoint_json, created_at, updated_at, completed_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 acceptance_criteria=excluded.acceptance_criteria,
                 status=excluded.status,
                 steps_json=excluded.steps_json,
                 current_step_id=excluded.current_step_id,
                 next_action=excluded.next_action,
                 blocker=excluded.blocker,
                 turns_used=excluded.turns_used,
                 max_turns=excluded.max_turns,
                 lease_owner=excluded.lease_owner,
                 lease_expires_at=excluded.lease_expires_at,
                 checkpoint_json=excluded.checkpoint_json,
                 updated_at=excluded.updated_at,
                 completed_at=excluded.completed_at
            """,
            (
                task.id,
                task.workspace_id,
                task.channel_id,
                task.thread_ts,
                task.requester_user_id,
                task.objective,
                task.acceptance_criteria,
                task.status.value,
                steps_json,
                task.current_step_id,
                task.next_action,
                task.blocker,
                task.turns_used,
                task.max_turns,
                task.lease_owner,
                task.lease_expires_at,
                task.checkpoint_json,
                task.created_at,
                task.updated_at,
                task.completed_at,
            ),
        )
        await self.db.commit()

    async def claim_next(self, worker_id: str, lease_seconds: float = 120.0) -> Task | None:
        now = time.time()
        async with self.db.execute(
            """SELECT id FROM tasks
               WHERE status IN ('queued', 'resume_pending', 'planning', 'running', 'verifying')
                 AND (lease_owner IS NULL OR lease_expires_at IS NULL OR lease_expires_at < ?)
               ORDER BY updated_at ASC
               LIMIT 1""",
            (now,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        task_id = row["id"]
        expires = now + lease_seconds
        await self.db.execute(
            """UPDATE tasks SET lease_owner = ?, lease_expires_at = ?,
                   status = CASE WHEN status IN ('queued', 'resume_pending') THEN 'running' ELSE status END,
                   updated_at = ?
               WHERE id = ?""",
            (worker_id, expires, now, task_id),
        )
        await self.db.commit()
        return await self.get(task_id)

    async def heartbeat(self, task_id: str, worker_id: str, lease_seconds: float = 120.0) -> bool:
        now = time.time()
        cur = await self.db.execute(
            """UPDATE tasks SET lease_expires_at = ?, updated_at = ?
               WHERE id = ? AND lease_owner = ?""",
            (now + lease_seconds, now, task_id, worker_id),
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def requeue_expired_leases(self) -> int:
        now = time.time()
        cur = await self.db.execute(
            """UPDATE tasks
               SET status = 'resume_pending', lease_owner = NULL, lease_expires_at = NULL, updated_at = ?
               WHERE status IN ('running', 'planning', 'verifying')
                 AND lease_expires_at IS NOT NULL AND lease_expires_at < ?""",
            (now, now),
        )
        await self.db.commit()
        return cur.rowcount

    async def record_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO task_events (task_id, event_type, payload) VALUES (?, ?, ?)",
            (task_id, event_type, json.dumps(payload)),
        )
        await self.db.commit()

    async def claim_slack_event(
        self, workspace_id: str, event_key: str, task_id: str | None = None
    ) -> bool:
        """Return True if this is the first time we see this Slack event."""
        try:
            await self.db.execute(
                "INSERT INTO slack_events (workspace_id, event_key, task_id) VALUES (?, ?, ?)",
                (workspace_id, event_key, task_id),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def record_usage(self, usage: UsageRecord) -> None:
        await self.db.execute(
            """INSERT INTO llm_usage (
                 id, workspace_id, channel_id, thread_ts, task_id, run_id, request_id,
                 litellm_call_id, purpose, model, prompt_tokens, completion_tokens,
                 total_tokens, cost_usd, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                usage.id,
                usage.workspace_id,
                usage.channel_id,
                usage.thread_ts,
                usage.task_id,
                usage.run_id,
                usage.request_id,
                usage.litellm_call_id,
                usage.purpose,
                usage.model,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                usage.cost_usd,
                usage.created_at or time.time(),
            ),
        )
        await self.db.commit()

    async def record_tool_execution(
        self,
        *,
        task_id: str | None,
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
        tool_name: str,
        args_hash: str,
        result_hash: str,
        risk: str,
        success: bool,
        latency_ms: float,
        error_class: str = "",
        requester_user_id: str = "",
        approver_user_id: str = "",
    ) -> None:
        await self.db.execute(
            """INSERT INTO tool_executions (
                 id, task_id, workspace_id, channel_id, thread_ts, tool_name, args_hash,
                 result_hash, risk, success, latency_ms, error_class, requester_user_id,
                 approver_user_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id("tex_"),
                task_id,
                workspace_id,
                channel_id,
                thread_ts,
                tool_name,
                args_hash,
                result_hash,
                risk,
                1 if success else 0,
                latency_ms,
                error_class,
                requester_user_id,
                approver_user_id,
                time.time(),
            ),
        )
        await self.db.commit()

    async def create_approval(
        self,
        *,
        task_id: str,
        tool_name: str,
        args_json: str,
        requester_user_id: str,
    ) -> str:
        aid = new_id("apr_")
        await self.db.execute(
            """INSERT INTO approvals (
                 id, task_id, tool_name, args_json, status, requester_user_id, created_at
               ) VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (aid, task_id, tool_name, args_json, requester_user_id, time.time()),
        )
        await self.db.commit()
        return aid

    async def resolve_approval(
        self, approval_id: str, status: str, approver_user_id: str
    ) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        await self.db.execute(
            """UPDATE approvals SET status = ?, approver_user_id = ?, resolved_at = ?
               WHERE id = ?""",
            (status, approver_user_id, time.time(), approval_id),
        )
        await self.db.commit()
        return dict(row)

    async def get_pending_approval_for_task(self, task_id: str) -> dict[str, Any] | None:
        async with self.db.execute(
            """SELECT * FROM approvals WHERE task_id = ? AND status = 'pending'
               ORDER BY created_at DESC LIMIT 1""",
            (task_id,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


_task_stores: dict[str, SqliteTaskStore] = {}


async def get_task_store(workspace_id: str) -> SqliteTaskStore:
    if workspace_id not in _task_stores:
        from tagopen.config import settings

        db_path = settings.data_dir / "workspaces" / workspace_id / "messages.db"
        store = SqliteTaskStore(db_path)
        await store.open()
        _task_stores[workspace_id] = store
    return _task_stores[workspace_id]
