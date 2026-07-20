"""Agent loop — ReAct-style: think → tool call → observe → repeat → reply → memory curation."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from tagopen.agent.context import build_messages, build_system_prompt
from tagopen.agent.meta_commands import (
    format_skills_reply,
    format_tools_reply,
    is_skills_question,
    is_tools_question,
)
from tagopen.agent.model_commands import parse_model_command
from tagopen.agent.skills import maybe_create_skill
from tagopen.config import settings
from tagopen.llm import (
    acompletion_with_failover,
    cache_thread_model,
    clear_channel_model,
    describe_model_stack,
    model_allowed,
    set_channel_model,
)
from tagopen.memory.store import MessageStore
from tagopen.memory.writer import run_memory_curation
from tagopen.slack_format import to_slack_mrkdwn
from tagopen.tools.registry import dispatch_tool, get_channel_tools

if TYPE_CHECKING:
    from slack_bolt.async_app import AsyncApp

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10  # prevent runaway loops


async def run_agent_loop(
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
    # Persist the incoming user message
    await store.add_message(
        ts=event_ts,
        role="user",
        user_id=user_id,
        display_name=display_name,
        content=text,
        thread_ts=thread_ts,
    )

    # Hydrate thread model cache from SQLite
    thread_model = await store.get_thread_model(thread_ts)
    cache_thread_model(channel_id, thread_ts, thread_model)

    # Hermes-style /model — thread-scoped for Slack multiplayer
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

    # Deterministic tools/skills inventory — LLM often omit MCP from free-form answers
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

    # Fetch Slack user map for attribution (best-effort)
    try:
        members = await app.client.conversations_members(channel=channel_id)
        user_map: dict[str, str] = {}
        for uid in (members.get("members") or [])[:50]:
            info = await app.client.users_info(user=uid)
            profile = info["user"].get("profile", {})
            user_map[uid] = profile.get("display_name") or info["user"].get("real_name") or uid
    except Exception:
        user_map = {user_id: display_name}

    tools = await get_channel_tools(channel_id)
    system_prompt = build_system_prompt(channel_id, user_map, tool_schemas=tools)
    messages = await build_messages(channel_id, user_id, display_name, text, thread_ts, store)

    tool_call_count = 0
    final_text = ""
    failover_notice: str | None = None

    for _round in range(MAX_TOOL_ROUNDS):
        response, notice = await acompletion_with_failover(
            channel_id=channel_id,
            thread_ts=thread_ts,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
        )
        if notice and not failover_notice:
            failover_notice = notice

        choice = response.choices[0]
        msg = choice.message

        # Pure text response — we're done
        if not msg.tool_calls:
            final_text = msg.content or ""
            break

        # Execute each tool call
        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            tool_call_count += 1
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments or "{}")

            logger.info("Tool call: %s(%s) in channel=%s", fn_name, fn_args, channel_id)
            result = await dispatch_tool(fn_name, fn_args, channel_id=channel_id)

            # Handle memory write tools inline
            if fn_name in ("memory_append", "memory_replace"):
                _handle_memory_tool(channel_id, fn_name, fn_args)
                result = "Memory updated."

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })
    else:
        final_text = "I reached my tool call limit. Here's what I found so far."

    if not final_text:
        final_text = "Done."

    if failover_notice:
        final_text = f"{failover_notice}\n\n{final_text}"

    await _post_reply(app, channel_id, thread_ts, final_text)

    # Persist assistant reply
    await store.add_message(
        ts=str(time.time()),
        role="assistant",
        user_id="agent",
        display_name="agent",
        content=final_text,
        thread_ts=thread_ts,
    )

    # Inner loop: memory curation turn (Letta-inspired)
    await run_memory_curation(channel_id, system_prompt, messages, final_text)

    # Skill auto-creation if task was complex (Hermes-inspired)
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
            allow = ", ".join(f"`{m}`" for m in settings.model_allowlist)
            return f"Model `{model}` is not on the allowlist. Allowed: {allow}"
        set_channel_model(channel_id, model)
        return f"Pinned channel default model to `{model}` (tools.toml). Threads may still override."

    if cmd.kind == "set":
        model = (cmd.model or "").strip()
        if not model:
            return describe_model_stack(channel_id, thread_ts)
        if not model_allowed(model):
            allow = ", ".join(f"`{m}`" for m in settings.model_allowlist)
            return f"Model `{model}` is not on the allowlist. Allowed: {allow}"
        await store.set_thread_model(thread_ts, model)
        cache_thread_model(channel_id, thread_ts, model)
        return f"Thread model set to `{model}` for this thread only."

    return describe_model_stack(channel_id, thread_ts)


async def _post_reply(app: "AsyncApp", channel_id: str, thread_ts: str, text: str) -> None:
    slack_text = to_slack_mrkdwn(text)
    await app.client.chat_postMessage(
        channel=channel_id,
        text=slack_text,
        thread_ts=thread_ts,
        mrkdwn=True,
        unfurl_links=False,
        unfurl_media=False,
    )


def _handle_memory_tool(channel_id: str, fn_name: str, args: dict[str, Any]) -> None:
    memory_path = settings.channels_dir / channel_id / "MEMORY.md"
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    current = memory_path.read_text() if memory_path.exists() else ""

    if fn_name == "memory_append":
        entry = args.get("content", "").strip()
        if entry:
            memory_path.write_text(current.rstrip() + f"\n- {entry}\n")

    elif fn_name == "memory_replace":
        old = args.get("old", "")
        new = args.get("new", "")
        memory_path.write_text(current.replace(old, new))
