"""MCP client with persistent pooled sessions + stdio/HTTP(SSE) support."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

logger = logging.getLogger(__name__)


def _child_env(extra: dict[str, str] | None) -> dict[str, str]:
    merged = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    if extra:
        merged.update({str(k): str(v) for k, v in extra.items()})
    return merged


def _tool_schema_from_mcp(server_name: str, tool: Any, allowed: set[str] | None) -> dict | None:
    name = tool.name
    if allowed is not None and name not in allowed:
        return None
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


@dataclass
class CircuitState:
    failures: int = 0
    open_until: float = 0.0
    last_error: str = ""

    def allow(self) -> bool:
        return time.time() >= self.open_until

    def record_success(self) -> None:
        self.failures = 0
        self.open_until = 0.0
        self.last_error = ""

    def record_failure(self, err: str, threshold: int = 3, cooldown: float = 60.0) -> None:
        self.failures += 1
        self.last_error = err
        if self.failures >= threshold:
            self.open_until = time.time() + cooldown


@dataclass
class PooledSession:
    server_name: str
    stack: AsyncExitStack
    session: ClientSession
    last_used: float = field(default_factory=time.time)


_pools: dict[str, PooledSession] = {}
_circuits: dict[str, CircuitState] = {}
_pool_lock = asyncio.Lock()


def _server_key(server: dict[str, Any]) -> str:
    name = server.get("name") or "mcp"
    if server.get("url"):
        return f"{name}|url|{server['url']}"
    return f"{name}|stdio|{server.get('command')}|{' '.join(server.get('args') or [])}"


async def _open_stdio(server: dict[str, Any]) -> PooledSession:
    command = server["command"]
    args = server.get("args") or []
    env = _child_env(server.get("env"))
    params = StdioServerParameters(command=command, args=args, env=env)
    stack = AsyncExitStack()
    read, write = await stack.enter_async_context(stdio_client(params))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return PooledSession(server_name=server.get("name") or "mcp", stack=stack, session=session)


async def _open_http(server: dict[str, Any]) -> PooledSession:
    """HTTP/SSE MCP via mcp.client.sse when available."""
    url = server["url"]
    try:
        from mcp.client.sse import sse_client
    except ImportError as e:
        raise RuntimeError("HTTP/SSE MCP requires mcp.client.sse") from e
    headers = server.get("headers") or {}
    stack = AsyncExitStack()
    read, write = await stack.enter_async_context(sse_client(url, headers=headers))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return PooledSession(server_name=server.get("name") or "mcp", stack=stack, session=session)


async def get_session(server: dict[str, Any]) -> ClientSession:
    key = _server_key(server)
    circuit = _circuits.setdefault(key, CircuitState())
    if not circuit.allow():
        raise RuntimeError(f"MCP circuit open for {server.get('name')}: {circuit.last_error}")

    async with _pool_lock:
        pooled = _pools.get(key)
        if pooled is not None:
            pooled.last_used = time.time()
            return pooled.session
        try:
            if server.get("url"):
                pooled = await _open_http(server)
            elif server.get("command"):
                pooled = await _open_stdio(server)
            else:
                raise RuntimeError("MCP server needs command= or url=")
            _pools[key] = pooled
            circuit.record_success()
            return pooled.session
        except Exception as e:
            circuit.record_failure(str(e))
            raise


async def close_all_pools() -> None:
    async with _pool_lock:
        for key, pooled in list(_pools.items()):
            try:
                await pooled.stack.aclose()
            except Exception:
                logger.exception("Error closing MCP pool %s", key)
        _pools.clear()


async def list_mcp_tools(servers: list[dict[str, Any]]) -> list[dict]:
    schemas: list[dict] = []
    for server in servers:
        name = server.get("name") or "mcp"
        if not server.get("command") and not server.get("url"):
            logger.warning("MCP server %s missing command/url", name)
            continue
        allowed_list = server.get("allowed_tools")
        allowed = set(allowed_list) if allowed_list else None
        try:
            session = await get_session(server)
            result = await asyncio.wait_for(session.list_tools(), timeout=30)
            for tool in result.tools or []:
                schema = _tool_schema_from_mcp(name, tool, allowed)
                if schema:
                    schemas.append(schema)
            _circuits.setdefault(_server_key(server), CircuitState()).record_success()
        except Exception:
            logger.exception("Failed to list tools from MCP server %s", name)
            _circuits.setdefault(_server_key(server), CircuitState()).record_failure("list_tools failed")
    return schemas


async def call_mcp_tool(
    servers: list[dict[str, Any]],
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    server = next((s for s in servers if (s.get("name") or "mcp") == server_name), None)
    if not server:
        return f"MCP server '{server_name}' not configured for this channel."
    try:
        session = await get_session(server)
        result = await asyncio.wait_for(
            session.call_tool(tool_name, arguments=arguments),
            timeout=60,
        )
        parts: list[str] = []
        for block in result.content or []:
            if isinstance(block, TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        _circuits.setdefault(_server_key(server), CircuitState()).record_success()
        return "\n".join(parts) if parts else "(empty MCP result)"
    except Exception as e:
        logger.exception("MCP call %s/%s failed", server_name, tool_name)
        _circuits.setdefault(_server_key(server), CircuitState()).record_failure(str(e))
        return f"MCP tool error ({server_name}/{tool_name}): {e}"


def mcp_health() -> dict[str, Any]:
    return {
        name: {
            "failures": c.failures,
            "open_until": c.open_until,
            "last_error": c.last_error,
            "open": not c.allow(),
        }
        for name, c in _circuits.items()
    }
