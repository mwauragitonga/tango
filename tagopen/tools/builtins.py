"""Built-in tools always available to the agent: web search, Python runner, channel search."""

from __future__ import annotations

import logging
import sys
from io import StringIO
from typing import Any

from tagopen.agent.skill_catalog import skill_view, skills_list_text
from tagopen.tools.web_search import search_web

logger = logging.getLogger(__name__)

# LiteLLM-compatible tool schemas
BUILTIN_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for up-to-date information (news, docs, facts). Returns titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute a Python snippet and return stdout. Use for calculations, data processing, and quick scripts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_channel_history",
            "description": "Full-text search across this channel's message history",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords to search for"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_append",
            "description": "Append a new fact or decision to channel long-term memory (MEMORY.md)",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The fact to persist (one concise bullet)",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_replace",
            "description": "Replace an outdated fact in channel memory with an updated version",
            "parameters": {
                "type": "object",
                "properties": {
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                },
                "required": ["old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tools",
            "description": "List every callable tool registered for this channel (builtins + MCP). Use when the user asks what tools you have.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skills_list",
            "description": (
                "List channel skills (name + description only). "
                "Prefer matching from the system skills index; call this if you need a refresh. "
                "Then skill_view(name) before following a playbook."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_view",
            "description": (
                "Load a channel skill playbook by name and follow it. "
                "Call proactively when the user task matches a skill description — "
                "do not wait for the user to say skill_view. "
                "Triggers include: humanize/rewrite/natural voice/de-AI → humanizer; "
                "SEO audit/ranking → seo-audit; social posts → social-content; "
                "GitHub PRs/issues → github; standup summary → standup-notes; "
                "prod ops/monitoring → production-operations / production-monitoring."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill name (filename stem or frontmatter name)",
                    },
                },
                "required": ["name"],
            },
        },
    },
]


async def dispatch_builtin(
    fn_name: str,
    args: dict[str, Any],
    channel_id: str | None = None,
) -> Any:
    if fn_name == "web_search":
        return await search_web(args["query"])
    if fn_name == "run_python":
        from tagopen.tools.sandbox import run_python_sandboxed

        return run_python_sandboxed(args["code"])
    if fn_name == "search_channel_history":
        # Prefer ToolExecutor path (has MessageStore). Fallback message if reached here.
        return (
            "search_channel_history must be invoked via ToolExecutor with a message store; "
            f"query={args.get('query')!r}"
        )
    if fn_name == "skills_list":
        if not channel_id:
            return "skills_list requires a channel context."
        return skills_list_text(channel_id)
    if fn_name == "skill_view":
        if not channel_id:
            return "skill_view requires a channel context."
        return skill_view(channel_id, args.get("name", ""))
    return f"Unknown built-in: {fn_name}"
