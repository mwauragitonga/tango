"""Enqueue-only APScheduler service — never runs agent logic directly."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from tagopen.config import settings
from tagopen.tasks.service import TaskService
from tagopen.tasks.store import get_task_store
from tagopen.tasks.worker import get_worker

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)

_scheduler = None


async def start_scheduler(app: "AsyncApp") -> None:
    global _scheduler
    if not settings.ambient_enabled:
        logger.info("Ambient scheduler disabled")
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    except ImportError:
        logger.warning("APScheduler not installed — ambient schedules disabled")
        return

    db_url = f"sqlite:///{settings.data_dir / 'scheduler.db'}"
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    jobstores = {"default": SQLAlchemyJobStore(url=db_url)}
    _scheduler = AsyncIOScheduler(jobstores=jobstores)
    _scheduler.start()

    # Tick every minute: enqueue due schedules + heartbeat observations
    _scheduler.add_job(
        _tick,
        "interval",
        minutes=1,
        id="tango_scheduler_tick",
        replace_existing=True,
        kwargs={"app": app},
    )
    logger.info("Ambient scheduler started (enqueue-only)")


async def _tick(app: "AsyncApp") -> None:
    from pathlib import Path

    from tagopen.ambient.heartbeat import run_heartbeat_enqueue

    root = settings.data_dir / "workspaces"
    if not root.exists():
        return
    for ws_dir in root.iterdir():
        if not ws_dir.is_dir():
            continue
        store = await get_task_store(ws_dir.name)
        await _enqueue_due_schedules(app, store, ws_dir.name)
        await run_heartbeat_enqueue(app, store, ws_dir.name)


async def _enqueue_due_schedules(app: "AsyncApp", store, workspace_id: str) -> None:
    now = time.time()
    async with store.db.execute(
        """SELECT * FROM schedules
           WHERE workspace_id = ? AND enabled = 1
             AND (next_run_at IS NULL OR next_run_at <= ?)""",
        (workspace_id, now),
    ) as cur:
        rows = await cur.fetchall()
    svc = TaskService(store)
    for row in rows:
        task = await svc.create_task(
            workspace_id=workspace_id,
            channel_id=row["channel_id"],
            thread_ts=f"schedule-{row['id']}-{int(now)}",
            requester_user_id=row["created_by"] or "scheduler",
            objective=f"[scheduled] {row['description']}",
        )
        await store.db.execute(
            "UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?",
            (now, now + 3600, row["id"]),  # simple hourly bump; cron parsed in tools
        )
        await store.db.commit()
        logger.info("Enqueued schedule %s as task %s", row["id"], task.id)
    if rows:
        get_worker(app).start()


def get_scheduler():
    return _scheduler
