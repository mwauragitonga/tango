"""Task lifecycle: create, plan, complete, pause, cancel, verify."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from tagopen.tasks.models import (
    StepStatus,
    Task,
    TaskStatus,
    TaskStep,
    TERMINAL_STATUSES,
    new_id,
)
from tagopen.tasks.store import SqliteTaskStore

logger = logging.getLogger(__name__)

_QUICK_PATTERNS = (
    re.compile(r"^(what|who|when|where|why|how|is|are|can|does|do)\b", re.I),
    re.compile(r"\?$"),
)


def looks_like_quick_qa(text: str) -> bool:
    t = text.strip()
    if len(t) < 180 and any(p.search(t) for p in _QUICK_PATTERNS):
        # Long multi-step requests still go durable even with a ?
        if re.search(r"\b(steps?|plan|then|after that|and then)\b", t, re.I):
            return False
        return True
    return False


def should_queue_durable(text: str) -> bool:
    """Queue when multi-step, writes, external waits, or expected long runtime."""
    if looks_like_quick_qa(text):
        return False
    t = text.lower()
    signals = (
        "step",
        "plan",
        "then ",
        "and then",
        "deploy",
        "migrate",
        "research",
        "write a",
        "create a",
        "implement",
        "fix",
        "audit",
        "over the next",
        "wait for",
        "schedule",
    )
    if any(s in t for s in signals):
        return True
    if len(text) > 280:
        return True
    # numbered list
    if re.search(r"(^|\n)\s*\d+[\.\)]\s+", text):
        return True
    return False


class TaskService:
    def __init__(self, store: SqliteTaskStore) -> None:
        self.store = store

    async def create_task(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
        requester_user_id: str,
        objective: str,
        acceptance_criteria: str = "",
        max_turns: int = 40,
    ) -> Task:
        task = Task(
            id=new_id("tsk_"),
            workspace_id=workspace_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            requester_user_id=requester_user_id,
            objective=objective.strip(),
            acceptance_criteria=acceptance_criteria.strip(),
            status=TaskStatus.QUEUED,
            next_action="plan",
            max_turns=max_turns,
            created_at=time.time(),
            updated_at=time.time(),
        )
        await self.store.save(task)
        await self.store.record_event(task.id, "created", {"objective": task.objective})
        return task

    async def set_plan(self, task: Task, steps: list[str]) -> Task:
        if task.status in TERMINAL_STATUSES:
            raise ValueError(f"Cannot plan terminal task {task.status}")
        task.steps = [
            TaskStep(id=f"s{i+1}", content=content.strip(), status=StepStatus.PENDING)
            for i, content in enumerate(steps)
            if content.strip()
        ]
        if not task.steps:
            raise ValueError("Plan requires at least one step")
        task.steps[0].status = StepStatus.IN_PROGRESS
        task.current_step_id = task.steps[0].id
        task.status = TaskStatus.RUNNING
        task.next_action = task.steps[0].content
        task.checkpoint_json = json.dumps({"plan_set_at": time.time()})
        await self.store.save(task)
        await self.store.record_event(
            task.id, "plan_set", {"steps": [s.to_dict() for s in task.steps]}
        )
        return task

    async def update_step(
        self,
        task: Task,
        step_id: str,
        *,
        status: StepStatus,
        evidence: str = "",
        error: str = "",
    ) -> Task:
        step = next((s for s in task.steps if s.id == step_id), None)
        if not step:
            raise ValueError(f"Unknown step {step_id}")
        step.status = status
        if evidence:
            step.evidence = evidence
        if error:
            step.error = error

        if status == StepStatus.IN_PROGRESS:
            for s in task.steps:
                if s.id != step_id and s.status == StepStatus.IN_PROGRESS:
                    s.status = StepStatus.PENDING
            task.current_step_id = step_id
            task.next_action = step.content
            task.status = TaskStatus.RUNNING

        if status == StepStatus.COMPLETED:
            nxt = next(
                (s for s in task.steps if s.status == StepStatus.PENDING),
                None,
            )
            if nxt:
                nxt.status = StepStatus.IN_PROGRESS
                task.current_step_id = nxt.id
                task.next_action = nxt.content
            else:
                task.current_step_id = None
                task.next_action = "verify completion"
                task.status = TaskStatus.VERIFYING

        if status == StepStatus.FAILED:
            task.blocker = error or f"Step {step_id} failed"
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()

        task.checkpoint_json = json.dumps(
            {"step": step_id, "status": status.value, "at": time.time()}
        )
        await self.store.save(task)
        await self.store.record_event(
            task.id,
            "step_update",
            {"step_id": step_id, "status": status.value, "evidence": evidence, "error": error},
        )
        return task

    async def pause(self, task: Task, reason: str = "") -> Task:
        if task.status in TERMINAL_STATUSES:
            return task
        task.status = TaskStatus.PAUSED
        task.blocker = reason or task.blocker
        task.lease_owner = None
        task.lease_expires_at = None
        await self.store.save(task)
        await self.store.record_event(task.id, "paused", {"reason": reason})
        return task

    async def resume(self, task: Task) -> Task:
        if task.status not in {TaskStatus.PAUSED, TaskStatus.WAITING_APPROVAL, TaskStatus.WAITING_EXTERNAL}:
            if task.status in TERMINAL_STATUSES:
                raise ValueError("Cannot resume terminal task")
        task.status = TaskStatus.RESUME_PENDING
        task.blocker = ""
        task.lease_owner = None
        task.lease_expires_at = None
        await self.store.save(task)
        await self.store.record_event(task.id, "resume_requested", {})
        return task

    async def cancel(self, task: Task, reason: str = "") -> Task:
        task.status = TaskStatus.CANCELLED
        task.blocker = reason
        task.completed_at = time.time()
        task.lease_owner = None
        task.lease_expires_at = None
        await self.store.save(task)
        await self.store.record_event(task.id, "cancelled", {"reason": reason})
        return task

    async def mark_waiting_approval(self, task: Task, detail: str) -> Task:
        task.status = TaskStatus.WAITING_APPROVAL
        task.blocker = detail
        task.next_action = "await approval"
        task.lease_owner = None
        task.lease_expires_at = None
        await self.store.save(task)
        await self.store.record_event(task.id, "waiting_approval", {"detail": detail})
        return task

    def can_complete(self, task: Task) -> tuple[bool, str]:
        incomplete = task.required_incomplete()
        if incomplete:
            ids = ", ".join(s.id for s in incomplete)
            return False, f"Required steps incomplete: {ids}"
        if task.acceptance_criteria and not any(
            s.evidence for s in task.steps if s.status == StepStatus.COMPLETED
        ):
            return False, "Acceptance criteria set but no step evidence recorded"
        return True, ""

    async def complete(self, task: Task, summary: str = "") -> Task:
        ok, reason = self.can_complete(task)
        if not ok:
            raise ValueError(f"Cannot complete: {reason}")
        task.status = TaskStatus.COMPLETED
        task.next_action = ""
        task.blocker = ""
        task.completed_at = time.time()
        task.lease_owner = None
        task.lease_expires_at = None
        if summary:
            task.checkpoint_json = json.dumps({"summary": summary, "at": time.time()})
        await self.store.save(task)
        await self.store.record_event(task.id, "completed", {"summary": summary})
        return task

    async def fail(self, task: Task, reason: str) -> Task:
        task.status = TaskStatus.FAILED
        task.blocker = reason
        task.completed_at = time.time()
        task.lease_owner = None
        task.lease_expires_at = None
        await self.store.save(task)
        await self.store.record_event(task.id, "failed", {"reason": reason})
        return task

    def progress_text(self, task: Task) -> str:
        return task.to_summary()
