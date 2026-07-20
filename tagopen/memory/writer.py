"""Memory curation + atomic MEMORY.md writes (no circular import with loop)."""

from __future__ import annotations

import json
import logging

from tagopen.config import settings
from tagopen.llm import acompletion
from tagopen.memory.files import memory_append, memory_replace

logger = logging.getLogger(__name__)

_CURATION_PROMPT = """\
You just responded to a message in a Slack channel. Review the exchange below.

Your job: decide if anything should be persisted to the channel's long-term memory (MEMORY.md).
Only save facts that future sessions would genuinely benefit from knowing:
- Team conventions or preferences that came up
- Decisions made ("we decided to use X")
- Important context about the team or project
- Corrections to things you got wrong

Do NOT save:
- Transient task results (code output, search results)
- Things already in MEMORY.md
- Obvious facts that can be looked up

If something is worth saving, call memory_append or memory_replace.
If nothing is worth saving, do nothing — respond with an empty message.
"""

_MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "memory_append",
            "description": "Append a new fact or decision to MEMORY.md",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact to persist (one concise bullet)"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_replace",
            "description": "Replace an outdated fact in MEMORY.md with an updated one",
            "parameters": {
                "type": "object",
                "properties": {
                    "old": {"type": "string", "description": "The exact text to replace"},
                    "new": {"type": "string", "description": "The replacement text"},
                },
                "required": ["old", "new"],
            },
        },
    },
]


def apply_memory_tool(channel_id: str, fn_name: str, args: dict) -> None:
    memory_path = settings.channels_dir / channel_id / "MEMORY.md"
    if fn_name == "memory_append":
        memory_append(memory_path, args.get("content", ""))
    elif fn_name == "memory_replace":
        memory_replace(memory_path, args.get("old", ""), args.get("new", ""))


async def run_memory_curation(
    channel_id: str,
    system_prompt: str,
    messages: list[dict],
    final_reply: str,
    thread_ts: str | None = None,
) -> None:
    try:
        response = await acompletion(
            channel_id=channel_id,
            thread_ts=thread_ts,
            messages=[
                {"role": "system", "content": _CURATION_PROMPT},
                *messages[-6:],
                {"role": "assistant", "content": final_reply},
            ],
            tools=_MEMORY_TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message
        if not msg.tool_calls:
            return

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments or "{}")
            if fn_name in ("memory_append", "memory_replace"):
                apply_memory_tool(channel_id, fn_name, fn_args)
                logger.info("Memory updated via curation: %s in channel=%s", fn_name, channel_id)

    except Exception:
        logger.exception("Memory curation failed for channel=%s", channel_id)
