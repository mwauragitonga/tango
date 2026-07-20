#!/usr/bin/env python3
"""Contabo-only: stdio MCP bridge to local Hermes Agent API (OpenAI-compatible).

NOT for multi-tenant SaaS. Exposes a single tool that asks Hermes (skills/tools
on the Hermes side) and returns the answer into Tango's Slack loop.

Env:
  HERMES_API_URL  default http://127.0.0.1:8642
  HERMES_API_KEY  local API_SERVER_KEY bearer

tools.toml:
  [[mcp_server]]
  name = "hermes"
  command = "/opt/apps/open-claude-tag/.venv/bin/python"
  args = ["/opt/apps/open-claude-tag/examples/mcp/hermes_bridge_server.py"]
  allowed_tools = ["hermes_ask"]
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

HERMES_API_URL = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642").rstrip("/")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")

mcp = FastMCP("hermes_bridge")


@mcp.tool()
def hermes_ask(prompt: str) -> str:
    """Ask the local Hermes Agent (Contabo) to use its skills/tools and answer.

    Use for advanced Contabo-only capabilities that Hermes already has.
    Do not use for routine Slack replies Tango can handle itself.
    """
    if not HERMES_API_KEY:
        return "HERMES_API_KEY is not set; cannot call Hermes API."
    text = (prompt or "").strip()
    if not text:
        return "Provide a non-empty prompt."
    try:
        r = httpx.post(
            f"{HERMES_API_URL}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {HERMES_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "hermes-agent",
                "messages": [{"role": "user", "content": text}],
                "temperature": 0.2,
            },
            timeout=120.0,
        )
        r.raise_for_status()
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        return content.strip() or str(data)[:500]
    except Exception as e:
        return f"Hermes API error: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
