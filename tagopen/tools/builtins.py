"""Built-in tools always available to the agent: web search, Python runner, channel search."""

from __future__ import annotations

import logging
import sys
from io import StringIO
from typing import Any

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
]


async def dispatch_builtin(fn_name: str, args: dict[str, Any]) -> Any:
    if fn_name == "web_search":
        return await search_web(args["query"])
    if fn_name == "run_python":
        return _run_python(args["code"])
    if fn_name == "search_channel_history":
        # Actual search happens in dispatch_tool after store lookup; return placeholder
        return args
    return f"Unknown built-in: {fn_name}"


def _run_python(code: str) -> str:
    # Sandboxed Python execution — stdout captured, dangerous builtins removed
    safe_globals: dict[str, Any] = {
        "__builtins__": {
            k: v
            for k, v in __builtins__.items()  # type: ignore[union-attr]
            if k not in ("open", "exec", "eval", "__import__", "compile")
        }
        if isinstance(__builtins__, dict)
        else {},
        "print": print,
    }
    import datetime
    import json
    import math
    import re

    safe_globals.update({"math": math, "json": json, "re": re, "datetime": datetime})

    old_stdout = sys.stdout
    sys.stdout = buffer = StringIO()
    try:
        exec(code, safe_globals)  # noqa: S102
        output = buffer.getvalue()
        return output.strip() or "(no output)"
    except Exception as e:
        return f"Error: {e}"
    finally:
        sys.stdout = old_stdout
