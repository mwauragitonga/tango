"""Temporal orchestration adapter — optional; domain state stays in TaskStore."""

from __future__ import annotations

import logging
from datetime import timedelta

from tagopen.config import settings

logger = logging.getLogger(__name__)


async def start_temporal_worker() -> None:
    if not settings.temporal_enabled:
        return
    try:
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError:
        logger.warning("temporalio not installed")
        return

    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)

    # Activities wrap existing TaskWorker / TaskService — business logic stays out of Temporal
    async def run_task_activity(task_id: str, workspace_id: str) -> str:
        from tagopen.tasks.store import get_task_store
        from tagopen.tasks.worker import get_worker
        from tagopen.gateway.app import app

        store = await get_task_store(workspace_id)
        task = await store.get(task_id)
        if not task:
            return "missing"
        await get_worker(app).run_task(task, store)
        return "ok"

    # Register minimal worker; workflows defined inline for SaaS multi-replica
    from temporalio import activity, workflow

    @activity.defn(name="tango_run_task")
    async def tango_run_task(task_id: str, workspace_id: str) -> str:
        return await run_task_activity(task_id, workspace_id)

    @workflow.defn(name="TangoTaskWorkflow")
    class TangoTaskWorkflow:
        def __init__(self) -> None:
            self._approved = False

        @workflow.signal
        def approval(self, approved: bool) -> None:
            self._approved = approved

        @workflow.run
        async def run(self, task_id: str, workspace_id: str) -> str:
            return await workflow.execute_activity(
                tango_run_task,
                args=[task_id, workspace_id],
                start_to_close_timeout=timedelta(hours=2),
            )

    worker = Worker(
        client,
        task_queue="tango-tasks",
        workflows=[TangoTaskWorkflow],
        activities=[tango_run_task],
    )
    logger.info("Temporal worker starting on tango-tasks")
    await worker.run()


async def signal_approval(workflow_id: str, approved: bool) -> None:
    if not settings.temporal_enabled:
        return
    from temporalio.client import Client

    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal("approval", approved)
