"""Heartbeat — post-only ambient nudges (never durable tasks)."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from tagopen.config import settings

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)

_recent_nudge_hashes: dict[str, float] = {}

_SLACK_TS = re.compile(r"^\d+\.\d+$")

# User work that means heartbeats must stay silent (no enqueue, no steal).
_ACTIVE_USER_STATUSES = frozenset(
    {
        "running",
        "planning",
        "verifying",
        "waiting_approval",
        "waiting_external",
        "resume_pending",
        "queued",
    }
)


def _is_slack_ts(ts: str | None) -> bool:
    if not ts:
        return False
    return bool(_SLACK_TS.match(str(ts)))


def _is_heartbeat_task(task: Any) -> bool:
    if getattr(task, "requester_user_id", "") == "heartbeat":
        return True
    obj = getattr(task, "objective", "") or ""
    return str(obj).startswith("[heartbeat]")


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
    user_tasks = [t for t in open_tasks if not _is_heartbeat_task(t)]
    items = []
    for t in user_tasks[:10]:
        items.append({"task_id": t.id, "status": t.status.value, "objective": t.objective[:120]})
    for h in stale_hints[:5]:
        items.append({"stale": h})
    return {
        "open_tasks": len(user_tasks),
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


def _has_active_user_work(open_tasks: list[Any]) -> bool:
    for t in open_tasks:
        if _is_heartbeat_task(t):
            continue
        status = t.status.value if hasattr(t.status, "value") else str(t.status)
        if status in _ACTIVE_USER_STATUSES:
            return True
    return False


def _prefer_thread_ts(open_tasks: list[Any]) -> str | None:
    for t in open_tasks:
        if _is_heartbeat_task(t):
            continue
        if _is_slack_ts(t.thread_ts):
            return t.thread_ts
    return None


def _nudge_text(observation: dict[str, Any]) -> str:
    n = observation.get("open_tasks") or 0
    if n == 1:
        return "Quick check-in: there's still open work in this channel."
    if n > 1:
        return f"Quick check-in: {n} open items still need attention in this channel."
    return "Quick check-in: a few threads look stale — ping me if you want help."


async def run_heartbeat_enqueue(app: "AsyncApp", store, workspace_id: str) -> None:
    if _in_quiet_hours():
        return
    async with store.db.execute(
        """SELECT DISTINCT channel_id FROM tasks
           WHERE workspace_id = ?
             AND status NOT IN ('completed','failed','cancelled','suspended')""",
        (workspace_id,),
    ) as cur:
        channels = [r[0] for r in await cur.fetchall()]
    for channel_id in channels:
        open_tasks = await store.list_open_for_channel(workspace_id, channel_id)
        if _has_active_user_work(open_tasks):
            logger.debug(
                "Heartbeat silent for %s: active user work", channel_id
            )
            continue
        user_tasks = [t for t in open_tasks if not _is_heartbeat_task(t)]
        stale = [
            f"Task {t.id[:8]} stuck in {t.status.value}"
            for t in user_tasks
            if t.status.value in {"waiting_external", "waiting_approval"}
            and (time.time() - t.updated_at) > 3600
        ]
        obs = build_observation(open_tasks, stale)
        decision = decide_heartbeat(obs)
        if decision["action"] != "post":
            continue
        _recent_nudge_hashes[decision["hash"]] = time.time()
        thread_ts = _prefer_thread_ts(open_tasks)
        text = _nudge_text(obs)
        kwargs: dict[str, Any] = {"channel": channel_id, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        try:
            await app.client.chat_postMessage(**kwargs)
            logger.info(
                "Posted heartbeat nudge for channel %s thread_ts=%s",
                channel_id,
                thread_ts or "(channel root)",
            )
        except Exception:
            logger.exception("Heartbeat post failed for channel %s", channel_id)
