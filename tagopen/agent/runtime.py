"""Bounded inline agent runtime for quick Q&A (non-durable)."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from tagopen.agent.meta_commands import (
    format_skills_reply,
    format_tools_reply,
    is_skills_question,
    is_tools_question,
)
from tagopen.agent.model_commands import parse_model_command
from tagopen.agent.skills import maybe_create_skill
from tagopen.config import settings
from tagopen.context.engine import ContextEngine
from tagopen.llm import (
    cache_thread_model,
    clear_channel_model,
    describe_model_stack,
    model_allowed,
    set_channel_model,
)
from tagopen.llm.gateway import LLMRequestContext, complete
from tagopen.memory.store import MessageStore
from tagopen.memory.writer import run_memory_curation
from tagopen.slack_format import to_slack_mrkdwn
from tagopen.tasks.store import get_task_store
from tagopen.tools.executor import ToolExecutor
from tagopen.tools.registry import get_channel_tools
from tagopen.gateway.users import get_user_map

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)


async def run_inline_turn(
    app: "AsyncApp",
    workspace_id: str,
    channel_id: str,
    user_id: str,
    display_name: str,
    text: str,
    thread_ts: str,
    event_ts: str,
    store: MessageStore,
) -> None:
    await store.add_message(
        ts=event_ts,
        role="user",
        user_id=user_id,
        display_name=display_name,
        content=text,
        thread_ts=thread_ts,
    )

    thread_model = await store.get_thread_model(thread_ts)
    cache_thread_model(channel_id, thread_ts, thread_model)

    cmd = parse_model_command(text)
    if cmd is not None:
        reply = await _handle_model_command(cmd, channel_id, thread_ts, store)
        await _post_reply(app, channel_id, thread_ts, reply)
        await store.add_message(
            ts=str(time.time()),
            role="assistant",
            user_id="agent",
            display_name="agent",
            content=reply,
            thread_ts=thread_ts,
        )
        return

    if is_tools_question(text):
        tools = await get_channel_tools(channel_id)
        reply = format_tools_reply(tools)
        await _post_reply(app, channel_id, thread_ts, reply)
        await store.add_message(
            ts=str(time.time()),
            role="assistant",
            user_id="agent",
            display_name="agent",
            content=reply,
            thread_ts=thread_ts,
        )
        return

    if is_skills_question(text):
        reply = format_skills_reply(channel_id)
        await _post_reply(app, channel_id, thread_ts, reply)
        await store.add_message(
            ts=str(time.time()),
            role="assistant",
            user_id="agent",
            display_name="agent",
            content=reply,
            thread_ts=thread_ts,
        )
        return

    user_map = await get_user_map(app, channel_id, fallback={user_id: display_name})
    tools = await get_channel_tools(channel_id)
    engine = ContextEngine()
    system_prompt, messages = await engine.build_context(
        channel_id=channel_id,
        user_map=user_map,
        tool_schemas=tools,
        store=store,
        thread_ts=thread_ts,
        current_user=display_name,
        current_text=text,
    )

    task_store = await get_task_store(workspace_id)
    executor = ToolExecutor(
        app=app,
        workspace_id=workspace_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        requester_user_id=user_id,
        task_store=task_store,
        task=None,
        message_store=store,
    )

    tool_call_count = 0
    final_text = ""
    failover_notice: str | None = None
    ctx = LLMRequestContext(
        workspace_id=workspace_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        slack_user_id=user_id,
        purpose="agent",
    )

    for _round in range(settings.max_tool_rounds_inline):
        response, notice = await complete(
            ctx,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
            task_store=task_store,
        )
        if notice and not failover_notice:
            failover_notice = notice

        choice = response.choices[0]
        msg = choice.message
        if not msg.tool_calls:
            final_text = msg.content or ""
            break

        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            tool_call_count += 1
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments or "{}")
            logger.info("Tool call: %s(%s) in channel=%s", fn_name, fn_args, channel_id)
            result = await executor.execute(fn_name, fn_args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})
    else:
        final_text = "I reached my tool call limit. Here's what I found so far."

    if not final_text:
        final_text = "Done."
    if failover_notice:
        final_text = f"{failover_notice}\n\n{final_text}"

    await _post_reply(app, channel_id, thread_ts, final_text)
    await store.add_message(
        ts=str(time.time()),
        role="assistant",
        user_id="agent",
        display_name="agent",
        content=final_text,
        thread_ts=thread_ts,
    )

    # Async memory curation — non-blocking for the Slack turn
    asyncio_create = __import__("asyncio").create_task
    asyncio_create(run_memory_curation(channel_id, system_prompt, messages, final_text, thread_ts=thread_ts))

    if tool_call_count >= 5:
        await maybe_create_skill(channel_id, messages, final_text, tool_call_count)


async def _handle_model_command(cmd, channel_id: str, thread_ts: str, store: MessageStore) -> str:
    if cmd.kind == "list":
        return describe_model_stack(channel_id, thread_ts)
    if cmd.kind == "reset":
        await store.clear_thread_model(thread_ts)
        cache_thread_model(channel_id, thread_ts, None)
        return "Thread model reset.\n" + describe_model_stack(channel_id, thread_ts)
    if cmd.kind == "channel":
        model = (cmd.model or "").strip()
        if not model:
            return "Usage: `model channel <model-id>`"
        if model.lower() in ("reset", "clear", "default"):
            clear_channel_model(channel_id)
            return "Cleared channel model pin. Falling back to env / thread override."
        if not model_allowed(model):
            return f"Model `{model}` is not on the allowlist."
        set_channel_model(channel_id, model)
        return f"Pinned channel default model to `{model}` (tools.toml)."
    if cmd.kind == "set":
        model = (cmd.model or "").strip()
        if not model:
            return describe_model_stack(channel_id, thread_ts)
        if not model_allowed(model):
            return f"Model `{model}` is not on the allowlist."
        await store.set_thread_model(thread_ts, model)
        cache_thread_model(channel_id, thread_ts, model)
        return f"Thread model set to `{model}` for this thread only."
    return describe_model_stack(channel_id, thread_ts)


async def _post_reply(app: "AsyncApp", channel_id: str, thread_ts: str, text: str) -> None:
    import asyncio

    await asyncio.wait_for(
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=to_slack_mrkdwn(text),
        ),
        timeout=settings.slack_timeout_seconds,
    )
