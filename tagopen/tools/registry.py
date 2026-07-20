"""Tool registry — loads allowed tools per channel from tools.toml.

Built-in tools are always available. Channel admins can add MCP servers via tools.toml
using stdio `command` + `args` (see examples/mcp/).
"""

from __future__ import annotations

import logging
from typing import Any

import toml

from tagopen.config import settings
from tagopen.tools.builtins import BUILTIN_TOOLS, dispatch_builtin
from tagopen.tools.mcp_client import call_mcp_tool, list_mcp_tools

logger = logging.getLogger(__name__)

# Cache: channel_id -> {servers, schemas, by_name}
_channel_tool_cache: dict[str, dict[str, Any]] = {}


def _load_servers(channel_id: str) -> list[dict[str, Any]]:
    tools_toml_path = settings.channels_dir / channel_id / "tools.toml"
    if not tools_toml_path.exists():
        return []
    try:
        config = toml.loads(tools_toml_path.read_text())
        return list(config.get("mcp_server") or [])
    except Exception:
        logger.exception("Failed to parse tools.toml for channel=%s", channel_id)
        return []


async def get_channel_tools(channel_id: str) -> list[dict]:
    """Return LiteLLM-compatible tool schemas for this channel (builtins + MCP)."""
    cache = _channel_tool_cache.get(channel_id)
    if cache and cache.get("schemas") is not None:
        # Return LiteLLM-safe schemas (strip internal _mcp)
        return [_public_schema(s) for s in cache["schemas"]]

    servers = _load_servers(channel_id)
    mcp_schemas = await list_mcp_tools(servers) if servers else []
    schemas = list(BUILTIN_TOOLS) + mcp_schemas
    by_name = {s["function"]["name"]: s for s in schemas}
    _channel_tool_cache[channel_id] = {
        "servers": servers,
        "schemas": schemas,
        "by_name": by_name,
    }
    return [_public_schema(s) for s in schemas]


def _public_schema(schema: dict) -> dict:
    return {
        "type": schema["type"],
        "function": schema["function"],
    }


def invalidate_channel_tools(channel_id: str) -> None:
    _channel_tool_cache.pop(channel_id, None)


async def dispatch_tool(fn_name: str, args: dict[str, Any], channel_id: str) -> Any:
    """Dispatch a tool call to built-ins or MCP servers."""
    builtin_names = {t["function"]["name"] for t in BUILTIN_TOOLS}
    if fn_name in builtin_names:
        return await dispatch_builtin(fn_name, args)

    if fn_name in ("memory_append", "memory_replace"):
        return None

    # Ensure cache warm
    await get_channel_tools(channel_id)
    cache = _channel_tool_cache.get(channel_id) or {}
    meta_schema = (cache.get("by_name") or {}).get(fn_name)
    if not meta_schema or "_mcp" not in meta_schema:
        logger.warning("Unknown tool: %s in channel=%s", fn_name, channel_id)
        return f"Tool '{fn_name}' not found."

    mcp_meta = meta_schema["_mcp"]
    return await call_mcp_tool(
        cache.get("servers") or [],
        mcp_meta["server"],
        mcp_meta["tool"],
        args,
    )
