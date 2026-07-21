"""Channel router — task-lease oriented; channel lock only for inline turns."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tagopen.agent.loop import run_agent_loop
from tagopen.gateway.users import get_display_name
from tagopen.memory.store import get_store
from tagopen.tasks.store import get_task_store

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)

_sessions: dict[tuple[str, str], "AgentSession"] = {}


@dataclass
class AgentSession:
    workspace_id: str
    channel_id: str
    # Inline Q&A still serialized lightly; durable tasks use DB leases instead.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def get_or_create_session(workspace_id: str, channel_id: str) -> AgentSession:
    key = (workspace_id, channel_id)
    if key not in _sessions:
        _sessions[key] = AgentSession(workspace_id=workspace_id, channel_id=channel_id)
        logger.info("New session: workspace=%s channel=%s", workspace_id, channel_id)
    return _sessions[key]


async def route_message(
    app: "AsyncApp",
    workspace_id: str,
    channel_id: str,
    user_id: str,
    text: str,
    thread_ts: str,
    event_ts: str,
    event_id: str | None = None,
    files: list | None = None,
) -> None:
    from tagopen.config import settings
    from tagopen.media.prepare import prepare_slack_files

    task_store = await get_task_store(workspace_id)
    event_key = event_id or f"{channel_id}:{event_ts}"
    first = await task_store.claim_slack_event(workspace_id, event_key)
    if not first:
        logger.info("Duplicate Slack event ignored: %s", event_key)
        return

    session = get_or_create_session(workspace_id, channel_id)
    store = await get_store(workspace_id, channel_id)
    display_name = await get_display_name(app, user_id)

    prepared = await prepare_slack_files(
        files=files or None,
        bot_token=settings.slack_bot_token or getattr(app.client, "token", "") or "",
        workspace_id=workspace_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
    )

    # Durable path releases quickly; lock only wraps dispatch start
    async with session._lock:
        await run_agent_loop(
            app=app,
            workspace_id=workspace_id,
            channel_id=channel_id,
            user_id=user_id,
            display_name=display_name,
            text=text,
            thread_ts=thread_ts,
            event_ts=event_ts,
            store=store,
            prepared=prepared,
        )
