"""Task tools exposed to the LLM (Hermes todo_tool inspired)."""

from __future__ import annotations

from typing import Any

from tagopen.tasks.models import StepStatus, Task
from tagopen.tasks.service import TaskService

TASK_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "task_plan",
            "description": (
                "Create or replace the ordered plan for the current durable task. "
                "Exactly one step will be marked in_progress. Call early for multi-step work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered list of concrete steps",
                    },
                    "acceptance_criteria": {
                        "type": "string",
                        "description": "Optional done-when criteria",
                    },
                },
                "required": ["steps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_status",
            "description": "Show durable task state, plan, next action, and blockers.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_update",
            "description": "Complete, fail, or revise a plan step with evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": [
                            "pending",
                            "in_progress",
                            "completed",
                            "failed",
                            "blocked",
                            "cancelled",
                        ],
                        "description": (
                            "Step status. Use completed (not done) when a step finishes."
                        ),
                    },
                    "evidence": {"type": "string"},
                    "error": {"type": "string"},
                },
                "required": ["step_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_pause",
            "description": "Pause the durable task until resume.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_resume",
            "description": "Resume a paused / waiting task.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_cancel",
            "description": "Cancel the durable task.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": (
                "Mark the task completed. Rejected unless every required step is done "
                "and verification evidence exists when acceptance criteria are set."
            ),
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
            },
        },
    },
]

TASK_TOOL_NAMES = {s["function"]["name"] for s in TASK_TOOL_SCHEMAS}


async def dispatch_task_tool(
    service: TaskService,
    task: Task,
    fn_name: str,
    args: dict[str, Any],
) -> tuple[Task, str]:
    if fn_name == "task_plan":
        steps = args.get("steps") or []
        if not isinstance(steps, list) or not steps:
            return task, "task_plan requires a non-empty steps array"
        if args.get("acceptance_criteria"):
            task.acceptance_criteria = str(args["acceptance_criteria"])
        task = await service.set_plan(task, [str(s) for s in steps])
        return task, service.progress_text(task)

    if fn_name == "task_status":
        return task, service.progress_text(task)

    if fn_name == "task_update":
        step_id = str(args.get("step_id") or "")
        try:
            status = StepStatus.from_tool_arg(args.get("status"))
        except ValueError:
            allowed = ", ".join(s.value for s in StepStatus)
            return task, (
                f"Invalid step status {args.get('status')!r}. "
                f"Use one of: {allowed} (alias: done→completed)."
            )
        task = await service.update_step(
            task,
            step_id,
            status=status,
            evidence=str(args.get("evidence") or ""),
            error=str(args.get("error") or ""),
        )
        return task, service.progress_text(task)

    if fn_name == "task_pause":
        task = await service.pause(task, str(args.get("reason") or ""))
        return task, service.progress_text(task)

    if fn_name == "task_resume":
        task = await service.resume(task)
        return task, service.progress_text(task)

    if fn_name == "task_cancel":
        task = await service.cancel(task, str(args.get("reason") or ""))
        return task, service.progress_text(task)

    if fn_name == "task_complete":
        try:
            task = await service.complete(task, str(args.get("summary") or ""))
            return task, f"Task completed.\n{service.progress_text(task)}"
        except ValueError as e:
            return task, str(e)

    return task, f"Unknown task tool: {fn_name}"
