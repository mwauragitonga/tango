"""Deterministic handlers for “what tools/skills?” — avoid incomplete LLM summaries."""

from __future__ import annotations

import re

from tagopen.agent.skill_catalog import skills_list_text
from tagopen.tools.catalog import format_tools_catalog

_MENTION = re.compile(r"<@[^>]+>|@\w+")
_TOOLS_Q = re.compile(
    r"\b((what|which|list)\s+tools|tools\s+(do\s+you\s+have|available)|your\s+tools|"
    r"use\s+list_tools)\b",
    re.I,
)
_SKILLS_Q = re.compile(
    r"\b((what|which|list)\s+skills|skills\s+(do\s+you\s+have|available)|your\s+skills|"
    r"use\s+skills_list|call\s+skills_list)\b",
    re.I,
)


def _clean(text: str) -> str:
    return _MENTION.sub("", text or "").strip()


def is_tools_question(text: str) -> bool:
    return bool(_TOOLS_Q.search(_clean(text)))


def is_skills_question(text: str) -> bool:
    return bool(_SKILLS_Q.search(_clean(text)))


def format_tools_reply(tool_schemas: list[dict]) -> str:
    catalog = format_tools_catalog(tool_schemas)
    return (
        "*Callable tools for this channel:*\n"
        f"{catalog}\n\n"
        "*Skills* (playbooks) are separate — ask “what skills?” or use `skills_list` / `skill_view`.\n"
        "*Hermes:* `mcp_hermes_hermes_ask` (if listed) is for Contabo power tasks after confirm — not routine Q&A."
    )


def format_skills_reply(channel_id: str) -> str:
    body = skills_list_text(channel_id)
    return (
        "*Channel skills* (progressive playbooks — load with `skill_view`):\n"
        f"{body}\n\n"
        "These are not tools. For callable tools, ask “what tools?”."
    )
