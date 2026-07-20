"""Heartbeat — enqueue-only ambient observation tasks."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

from tagopen.config import settings
from tagopen.tasks.service import TaskService

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)

_recent_nudge_hashes: dict[str, float] = {}


def _in_quiet_hours() -> bool:
    spec = (settings.ambient_quiet_hours or "").strip()
    if not spec or "-" not in spec:
        return False
    try:
        start_s, end_s = spec.split("-", 1)
        start, end = int(start_s), int(end_s)
        hour = time.localtime().tm_hour
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end
    except Exception:
        return False


def build_observation(open_tasks: list[Any], stale_hints: list[str]) -> dict[str, Any]:
    items = []
    for t in open_tasks[:10]:
        items.append({"task_id": t.id, "status": t.status.value, "objective": t.objective[:120]})
    for h in stale_hints[:5]:
        items.append({"stale": h})
    return {
        "open_tasks": len(open_tasks),
        "items": items,
        "at": time.time(),
    }


def decide_heartbeat(observation: dict[str, Any]) -> dict[str, Any]:
    if observation["open_tasks"] == 0 and not observation["items"]:
        return {"action": "silent", "reason": "nothing to report", "confidence": 0.9}
    # Deduplicate identical nudges within 6 hours
    blob = str(sorted(str(i) for i in observation["items"]))
    h = hashlib.sha256(blob.encode()).hexdigest()[:16]
    last = _recent_nudge_hashes.get(h, 0)
    if time.time() - last < 6 * 3600:
        return {"action": "silent", "reason": "duplicate nudge", "confidence": 0.8, "hash": h}
    return {
        "action": "post",
        "reason": "open work or stale threads",
        "confidence": 0.7,
        "hash": h,
        "referenced": observation["items"][:5],
    }


async def run_heartbeat_enqueue(app: "AsyncApp", store, workspace_id: str) -> None:
    if _in_quiet_hours():
        return
    # Channel list from schedules + open tasks
    async with store.db.execute(
        """SELECT DISTINCT channel_id FROM tasks
           WHERE workspace_id = ?
             AND status NOT IN ('completed','failed','cancelled','suspended')""",
        (workspace_id,),
    ) as cur:
        channels = [r[0] for r in await cur.fetchall()]
    svc = TaskService(store)
    for channel_id in channels:
        open_tasks = await store.list_open_for_channel(workspace_id, channel_id)
        stale = [
            f"Task {t.id[:8]} stuck in {t.status.value}"
            for t in open_tasks
            if t.status.value in {"waiting_external", "waiting_approval"}
            and (time.time() - t.updated_at) > 3600
        ]
        obs = build_observation(open_tasks, stale)
        decision = decide_heartbeat(obs)
        if decision["action"] != "post":
            continue
        _recent_nudge_hashes[decision["hash"]] = time.time()
        await svc.create_task(
            workspace_id=workspace_id,
            channel_id=channel_id,
            thread_ts=f"heartbeat-{channel_id}-{int(time.time())}",
            requester_user_id="heartbeat",
            objective=(
                "[heartbeat] Review open work and stale threads; "
                "post a brief useful update only if needed. "
                f"Observation: {obs}"
            ),
        )
        logger.info("Enqueued heartbeat for channel %s", channel_id)
