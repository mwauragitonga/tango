"""Schedule management tools (channel policy + approvals via executor)."""

from __future__ import annotations

import time
from typing import Any

from tagopen.tasks.models import new_id
from tagopen.tasks.store import SqliteTaskStore

SCHEDULE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "schedule_task",
            "description": "Create a recurring schedule that enqueues durable tasks (cron expression).",
            "parameters": {
                "type": "object",
                "properties": {
                    "cron": {"type": "string", "description": "Cron expression, e.g. 0 9 * * 1-5"},
                    "description": {"type": "string"},
                },
                "required": ["cron", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_schedules",
            "description": "List schedules for this channel.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause_schedule",
            "description": "Pause a schedule by id.",
            "parameters": {
                "type": "object",
                "properties": {"schedule_id": {"type": "string"}},
                "required": ["schedule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resume_schedule",
            "description": "Resume a paused schedule.",
            "parameters": {
                "type": "object",
                "properties": {"schedule_id": {"type": "string"}},
                "required": ["schedule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_schedule",
            "description": "Delete a schedule.",
            "parameters": {
                "type": "object",
                "properties": {"schedule_id": {"type": "string"}},
                "required": ["schedule_id"],
            },
        },
    },
]


def _next_run_from_cron(cron: str) -> float:
    """Best-effort next run; falls back to +1 hour if croniter missing."""
    try:
        from croniter import croniter
        from datetime import datetime

        base = datetime.now()
        return croniter(cron, base).get_next(float)
    except Exception:
        return time.time() + 3600


async def dispatch_schedule_tool(
    store: SqliteTaskStore,
    workspace_id: str,
    channel_id: str,
    user_id: str,
    fn_name: str,
    args: dict[str, Any],
) -> str:
    if fn_name == "schedule_task":
        sid = new_id("sch_")
        now = time.time()
        cron = str(args.get("cron") or "")
        desc = str(args.get("description") or "")
        await store.db.execute(
            """INSERT INTO schedules (
                 id, workspace_id, channel_id, cron, description, enabled,
                 next_run_at, created_by, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (
                sid,
                workspace_id,
                channel_id,
                cron,
                desc,
                _next_run_from_cron(cron),
                user_id,
                now,
                now,
            ),
        )
        await store.db.commit()
        return f"Scheduled `{sid}` cron=`{cron}` — {desc}"

    if fn_name == "list_schedules":
        async with store.db.execute(
            """SELECT id, cron, description, enabled, next_run_at, last_run_at
               FROM schedules WHERE workspace_id = ? AND channel_id = ?
               ORDER BY created_at DESC""",
            (workspace_id, channel_id),
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            return "No schedules."
        lines = []
        for r in rows:
            state = "on" if r["enabled"] else "paused"
            lines.append(f"- `{r['id']}` [{state}] `{r['cron']}` — {r['description']}")
        return "\n".join(lines)

    sid = str(args.get("schedule_id") or "")
    if fn_name == "pause_schedule":
        await store.db.execute(
            "UPDATE schedules SET enabled = 0, updated_at = ? WHERE id = ? AND channel_id = ?",
            (time.time(), sid, channel_id),
        )
        await store.db.commit()
        return f"Paused `{sid}`"
    if fn_name == "resume_schedule":
        await store.db.execute(
            "UPDATE schedules SET enabled = 1, updated_at = ? WHERE id = ? AND channel_id = ?",
            (time.time(), sid, channel_id),
        )
        await store.db.commit()
        return f"Resumed `{sid}`"
    if fn_name == "delete_schedule":
        await store.db.execute(
            "DELETE FROM schedules WHERE id = ? AND channel_id = ?",
            (sid, channel_id),
        )
        await store.db.commit()
        return f"Deleted `{sid}`"
    return f"Unknown schedule tool {fn_name}"
