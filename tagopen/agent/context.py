"""Context assembler — builds the system prompt and message list for the LLM."""

from __future__ import annotations

import logging

from tagopen.agent.skill_catalog import format_skills_index
from tagopen.config import settings
from tagopen.memory.store import MessageStore
from tagopen.tools.catalog import format_tools_catalog

logger = logging.getLogger(__name__)

_DEFAULT_CHANNEL_MD = """\
# Channel Agent

You are a helpful AI teammate in this Slack channel.
Be concise, direct, and technical. Ask clarifying questions before taking big actions.
"""

_DEFAULT_ORG_MD = ""


def _read_channel_file(channel_id: str, filename: str, default: str = "") -> str:
    path = settings.channels_dir / channel_id / filename
    if path.exists():
        return path.read_text()
    return default


def _read_org_file(filename: str, default: str = "") -> str:
    path = settings.org_dir / filename
    if path.exists():
        return path.read_text()
    return default


def _bound_memory(text: str) -> str:
    """Hermes-style char bound so MEMORY.md cannot blow the prompt."""
    text = text.strip()
    max_chars = settings.memory_max_chars
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 80].rstrip() + "\n\n…(MEMORY.md truncated for prompt size)"


def build_system_prompt(
    channel_id: str,
    user_map: dict[str, str],
    tool_schemas: list[dict] | None = None,
) -> str:
    """Assemble: ORG → SOUL → PERSONALITY → CHANNEL → MEMORY → skills index → tools."""
    org_md = _read_org_file("ORG.md", _DEFAULT_ORG_MD)
    soul_md = _read_org_file("SOUL.md", "")
    personality = _read_channel_file(channel_id, "PERSONALITY.md", "")
    channel_md = _read_channel_file(channel_id, "CHANNEL.md", _DEFAULT_CHANNEL_MD)
    memory_md = _bound_memory(_read_channel_file(channel_id, "MEMORY.md", ""))
    skills_index = format_skills_index(channel_id)

    parts: list[str] = []

    if org_md.strip():
        parts.append(f"## Organization context\n\n{org_md.strip()}")

    if soul_md.strip():
        parts.append(f"## Soul (org persona)\n\n{soul_md.strip()}")

    if personality.strip():
        parts.append(
            "## Personality (channel overlay)\n\n"
            "This overlays tone for this room only; it does not replace org SOUL.\n\n"
            f"{personality.strip()}"
        )

    parts.append(channel_md.strip())

    if memory_md:
        parts.append(
            "## What I know about this channel\n\n"
            "Channel-scoped only — never invent private personal USER facts.\n\n"
            f"{memory_md}"
        )

    if skills_index:
        parts.append(skills_index)

    if user_map:
        roster = ", ".join(f"@{name}" for name in sorted(set(user_map.values()))[:40])
        parts.append(f"## Channel roster\n{roster}")

    parts.append(
        "## Multi-user context\n"
        "Incoming user messages may be prefixed with [timestamp @username] for attribution. "
        "You are a shared teammate — anyone in the channel can see this conversation. "
        "When following up, address the relevant person by @username. "
        "Never include [timestamp @name] or [@name] prefixes in your own replies — "
        "reply with clean Slack message text only."
    )

    parts.append(
        "## Slack formatting\n"
        "Replies are posted as Slack mrkdwn. Prefer *bold* (single asterisks), "
        "_italic_, `code`, and bullet lists with - or •. "
        "Do not use Markdown **double asterisks** or # headings. "
        "When citing web search results, include the URL on its own line."
    )

    if tool_schemas is not None:
        catalog = format_tools_catalog(tool_schemas)
        parts.append(
            "## Available tools\n\n"
            "These are the callable tools for this channel (builtins + MCP). "
            "When users ask what tools or capabilities you have, list this catalog "
            "**completely** — do not omit MCP tools or `list_tools` / `skills_list` / `skill_view`.\n\n"
            f"{catalog}\n\n"
            "**Tools vs skills vs Hermes:**\n"
            "- Tools = callable functions above (`list_tools` refreshes this list).\n"
            "- Skills = markdown playbooks — use `skills_list` / `skill_view` (not the same as tools).\n"
            "- `hermes_ask` (if listed) = Contabo Hermes power tasks only after confirm; "
            "not for routine Q&A. Host exec/DB/computer-use stay on Hermes."
        )
    else:
        parts.append(
            "## Tools\n"
            "Use tools when they improve accuracy (web_search for current events, "
            "MCP tools for org systems, skills_list/skill_view for playbooks). "
            "Prefer tools over guessing. "
            "For write actions against external systems, confirm with the requester first "
            "unless the channel CHANNEL.md explicitly allows autonomous writes. "
            "Escalate to hermes_ask (if available) only for Contabo-power tasks Hermes already owns — "
            "not routine Q&A."
        )

    parts.append(
        "## Memory tools\n"
        "After responding you may call `memory_append` or `memory_replace` to persist "
        "important facts, decisions, or conventions to MEMORY.md. Only save what future "
        "sessions would genuinely benefit from knowing."
    )

    parts.append(
        "## Model switching\n"
        "Users may set a thread model with `@Tango model <id>`, list with `@Tango model`, "
        "or reset with `@Tango model reset`. Channel pin: `@Tango model channel <id>`."
    )

    return "\n\n---\n\n".join(parts)


async def build_messages(
    channel_id: str,
    user_id: str,
    display_name: str,
    text: str,
    thread_ts: str,
    store: MessageStore,
) -> list[dict]:
    """Build the messages list: recent channel history + current message."""
    recent = await store.get_recent_messages(limit=settings.context_window_messages)

    messages: list[dict] = []
    for row in recent:
        role = "assistant" if row["role"] == "assistant" else "user"
        content = row["content"] or ""
        # Only attribute user turns. Prefixing assistant history as [@agent]
        # teaches the model to echo that junk into Slack replies.
        if role == "user":
            ts_str = str(row["ts"])[:16].replace("T", " ")
            name = row["display_name"] or row["user_id"] or "user"
            content = f"[{ts_str} @{name}] {content}"
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": f"[@{display_name}] {text}"})
    return messages
