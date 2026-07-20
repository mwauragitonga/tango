"""Slack Bolt gateway — Socket Mode (Contabo) + optional HTTP Events (SaaS)."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from tagopen.agent.loop import strip_bot_mention
from tagopen.config import settings
from tagopen.gateway.router import route_message
from tagopen.memory.store import get_store
from tagopen.scheduler.service import start_scheduler
from tagopen.slack_status import SlackStatus
from tagopen.tasks.service import TaskService
from tagopen.tasks.store import get_task_store
from tagopen.tasks.worker import get_worker
from tagopen.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)

app = AsyncApp(token=settings.slack_bot_token)

_APPROVE = re.compile(r"^\s*(approve|deny)\s+(\S+)\s*$", re.I)


@app.event("app_mention")
async def handle_mention(event: dict, say, client) -> None:
    channel_id = event["channel"]
    workspace_id = (await client.auth_test())["team_id"]
    user_id = event["user"]
    text = event["text"]
    thread_ts = event.get("thread_ts") or event["ts"]

    await client.reactions_add(channel=channel_id, timestamp=event["ts"], name="thinking_face")

    try:
        await route_message(
            app=app,
            workspace_id=workspace_id,
            channel_id=channel_id,
            user_id=user_id,
            text=text,
            thread_ts=thread_ts,
            event_ts=event["ts"],
            event_id=event.get("client_msg_id") or event.get("event_ts") or event["ts"],
        )
    except Exception:
        logger.exception("Error handling mention in %s", channel_id)
        await say(
            text="Sorry, I ran into an error processing that. Check the logs.",
            thread_ts=thread_ts,
        )
    finally:
        # SlackStatus.finish() may already have cleared thinking_face — treat
        # no_reaction as success; only log unexpected Slack errors.
        try:
            await client.reactions_remove(
                channel=channel_id, timestamp=event["ts"], name="thinking_face"
            )
        except Exception as e:
            err = ""
            resp = getattr(e, "response", None)
            if resp is not None:
                data = getattr(resp, "data", None) or {}
                if isinstance(data, dict):
                    err = str(data.get("error") or "")
            if err == "no_reaction" or "no_reaction" in str(e):
                logger.debug("thinking_face already removed in %s", channel_id)
            else:
                logger.exception("Failed to remove thinking_face reaction in %s", channel_id)


@app.event("message")
async def handle_message(event: dict, client) -> None:
    """Handle thread replies for approvals / resume — ignore channel noise."""
    if event.get("subtype") or event.get("bot_id"):
        return
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return  # top-level channel messages still require @mention

    text = strip_bot_mention(event.get("text") or "")
    channel_id = event["channel"]
    user_id = event["user"]
    workspace_id = (await client.auth_test())["team_id"]

    m = _APPROVE.match(text)
    if m:
        action, approval_id = m.group(1).lower(), m.group(2)
        store = await get_task_store(workspace_id)
        row = await store.resolve_approval(
            approval_id,
            "approved" if action == "approve" else "denied",
            user_id,
        )
        if not row:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"No pending approval `{approval_id}`.",
            )
            return
        task = await store.get(row["task_id"])
        if not task:
            return
        svc = TaskService(store)
        if action == "approve":
            args = json.loads(row["args_json"])
            task = await svc.resume(task)
            msg_store = await get_store(workspace_id, channel_id)
            executor = ToolExecutor(
                app=app,
                workspace_id=workspace_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                requester_user_id=user_id,
                task_store=store,
                task=task,
                channel_policy={"auto_approve_writes": True},
                message_store=msg_store,
            )
            status = SlackStatus(
                client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                event_ts=event["ts"],
            )
            executor.status = status
            await status.llm_start()
            result = await executor.execute(row["tool_name"], args)
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"Approved `{row['tool_name']}`.\n{result}",
            )
            get_worker(app).start()
            await get_worker(app).run_task(
                executor.task or task, store, event_ts=event["ts"]
            )
        else:
            task = await svc.pause(task, f"Denied approval {approval_id}")
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"Denied `{row['tool_name']}`. Task paused.",
            )
        return

    # If active waiting task and user @mentions or says resume
    if re.search(r"\bresume\b", text, re.I) or "<@" in (event.get("text") or ""):
        store = await get_task_store(workspace_id)
        task = await store.get_by_thread(workspace_id, channel_id, thread_ts)
        if task and task.status.value in {"paused", "waiting_approval", "waiting_external"}:
            if re.search(r"\bresume\b", text, re.I):
                svc = TaskService(store)
                task = await svc.resume(task)
                get_worker(app).start()
                await get_worker(app).run_task(task, store, event_ts=event["ts"])
                return
        # Mentions inside threads: route as normal agent turn
        if "<@" in (event.get("text") or ""):
            await route_message(
                app=app,
                workspace_id=workspace_id,
                channel_id=channel_id,
                user_id=user_id,
                text=event.get("text") or "",
                thread_ts=thread_ts,
                event_ts=event["ts"],
                event_id=event.get("client_msg_id") or event["ts"],
            )


async def start() -> None:
    get_worker(app).start()
    await start_scheduler(app)
    if settings.slack_mode == "http":
        from tagopen.tenancy.http_app import start_http

        await start_http(app)
        return

    handler = AsyncSocketModeHandler(app, settings.slack_app_token)
    logger.info("Tango gateway starting (Socket Mode)…")
    await handler.start_async()
