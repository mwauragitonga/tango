"""Typed domain models for the durable coworker runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


def new_id(prefix: str = "") -> str:
    uid = uuid4().hex
    return f"{prefix}{uid}" if prefix else uid


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_EXTERNAL = "waiting_external"
    PAUSED = "paused"
    RESUME_PENDING = "resume_pending"
    SUSPENDED = "suspended"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class ToolRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.SUSPENDED,
}


@dataclass
class TaskStep:
    id: str
    content: str
    status: StepStatus = StepStatus.PENDING
    evidence: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskStep":
        return cls(
            id=str(data["id"]),
            content=str(data.get("content") or ""),
            status=StepStatus(data.get("status") or StepStatus.PENDING.value),
            evidence=str(data.get("evidence") or ""),
            error=str(data.get("error") or ""),
        )


@dataclass
class Task:
    id: str
    workspace_id: str
    channel_id: str
    thread_ts: str
    requester_user_id: str
    objective: str
    status: TaskStatus = TaskStatus.QUEUED
    acceptance_criteria: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    current_step_id: str | None = None
    next_action: str = ""
    blocker: str = ""
    turns_used: int = 0
    max_turns: int = 40
    lease_owner: str | None = None
    lease_expires_at: float | None = None
    checkpoint_json: str = "{}"
    created_at: float = 0.0
    updated_at: float = 0.0
    completed_at: float | None = None

    def active_steps(self) -> list[TaskStep]:
        return [s for s in self.steps if s.status in {StepStatus.PENDING, StepStatus.IN_PROGRESS}]

    def required_incomplete(self) -> list[TaskStep]:
        return [
            s
            for s in self.steps
            if s.status not in {StepStatus.COMPLETED, StepStatus.CANCELLED}
        ]

    def to_summary(self) -> str:
        markers = {
            StepStatus.COMPLETED: "[x]",
            StepStatus.IN_PROGRESS: "[>]",
            StepStatus.PENDING: "[ ]",
            StepStatus.CANCELLED: "[~]",
            StepStatus.FAILED: "[!]",
            StepStatus.BLOCKED: "[#]",
        }
        lines = [
            f"*Task* `{self.id[:8]}` — `{self.status.value}`",
            f"*Objective:* {self.objective}",
        ]
        if self.acceptance_criteria:
            lines.append(f"*Done when:* {self.acceptance_criteria}")
        if self.steps:
            lines.append("*Plan:*")
            for s in self.steps:
                lines.append(f"- {markers.get(s.status, '[?]')} `{s.id}` {s.content} ({s.status.value})")
        if self.next_action:
            lines.append(f"*Next:* {self.next_action}")
        if self.blocker:
            lines.append(f"*Blocker:* {self.blocker}")
        lines.append(f"*Turns:* {self.turns_used}/{self.max_turns}")
        return "\n".join(lines)


@dataclass
class ToolExecution:
    id: str
    task_id: str | None
    workspace_id: str
    channel_id: str
    thread_ts: str
    tool_name: str
    args_hash: str
    result_hash: str
    risk: ToolRisk
    success: bool
    latency_ms: float
    error_class: str = ""
    requester_user_id: str = ""
    approver_user_id: str = ""
    created_at: float = 0.0


@dataclass
class UsageRecord:
    id: str
    workspace_id: str
    channel_id: str
    thread_ts: str
    task_id: str | None
    run_id: str | None
    request_id: str
    litellm_call_id: str
    purpose: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    created_at: float = 0.0


@dataclass
class Approval:
    id: str
    task_id: str
    tool_name: str
    args_json: str
    status: str = "pending"  # pending|approved|denied|expired
    requester_user_id: str = ""
    approver_user_id: str = ""
    created_at: float = 0.0
    resolved_at: float | None = None
