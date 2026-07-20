"""Minimal MCP client — stdio servers declared in channel tools.toml."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

logger = logging.getLogger(__name__)


def _tool_schema_from_mcp(server_name: str, tool: Any, allowed: set[str] | None) -> dict | None:
    name = tool.name
    if allowed is not None and name not in allowed:
        return None
    # Prefix to avoid collisions across servers / builtins
    exposed = f"mcp_{server_name}_{name}"
    desc = tool.description or f"MCP tool {name} from {server_name}"
    params = tool.inputSchema or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": exposed,
            "description": desc,
            "parameters": params,
        },
        "_mcp": {"server": server_name, "tool": name},
    }


async def list_mcp_tools(servers: list[dict[str, Any]]) -> list[dict]:
    """Connect to each stdio MCP server and return LiteLLM tool schemas."""
    schemas: list[dict] = []
    for server in servers:
        name = server.get("name") or "mcp"
        command = server.get("command")
        if not command:
            # HTTP URL servers not implemented yet — skip with log
            if server.get("url"):
                logger.warning(
                    "MCP server %s uses url= but only stdio command= is supported currently",
                    name,
                )
            continue
        args = server.get("args") or []
        env = server.get("env") or None
        allowed_list = server.get("allowed_tools")
        allowed = set(allowed_list) if allowed_list else None
        try:
            tools = await _list_tools_stdio(command, args, env)
            for tool in tools:
                schema = _tool_schema_from_mcp(name, tool, allowed)
                if schema:
                    schemas.append(schema)
        except Exception:
            logger.exception("Failed to list tools from MCP server %s", name)
    return schemas


async def _list_tools_stdio(
    command: str, args: list[str], env: dict[str, str] | None
) -> list[Any]:
    params = StdioServerParameters(command=command, args=args, env=env)
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.list_tools()
        return list(result.tools or [])


async def call_mcp_tool(
    servers: list[dict[str, Any]],
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """Invoke a tool on a named stdio MCP server."""
    server = next((s for s in servers if (s.get("name") or "mcp") == server_name), None)
    if not server:
        return f"MCP server '{server_name}' not configured for this channel."
    command = server.get("command")
    if not command:
        return f"MCP server '{server_name}' has no stdio command."
    args = server.get("args") or []
    env = server.get("env") or None
    try:
        return await _call_tool_stdio(command, args, env, tool_name, arguments)
    except Exception as e:
        logger.exception("MCP call %s/%s failed", server_name, tool_name)
        return f"MCP tool error ({server_name}/{tool_name}): {e}"


async def _call_tool_stdio(
    command: str,
    args: list[str],
    env: dict[str, str] | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    params = StdioServerParameters(command=command, args=args, env=env)
    async with AsyncExitStack() as stack:
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        result = await session.call_tool(tool_name, arguments=arguments)
        parts: list[str] = []
        for block in result.content or []:
            if isinstance(block, TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        text = "\n".join(parts).strip()
        if result.isError:
            return text or "MCP tool returned an error."
        return text or "(empty MCP result)"
