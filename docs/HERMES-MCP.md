# Contabo-only: Hermes as an MCP capability provider

Tango remains the Slack co-worker brain. Hermes is **optional** and **local-only**.

## When to use

- You already run Hermes on Contabo with skills/tools you do not want to reimplement yet.
- A channel needs an escape hatch (`hermes_ask`) for complex Contabo-side work.

## When not to use

- Multi-tenant SaaS (never point customer workspaces at your Hermes).
- Routine Slack Q&A Tango can answer with web_search / org MCP.

## Setup

1. Hermes API must be up (`API_SERVER_ENABLED=true`, `127.0.0.1:8642`).
2. Put the local bearer in Tango `.env` as `HERMES_API_KEY` (same value as Hermes `API_SERVER_KEY`). Optional: `HERMES_API_URL=http://127.0.0.1:8642`.
3. Export those env vars into the MCP child process (systemd already loads Tango `.env`; the bridge reads `HERMES_*` from the environment — pass via tools.toml `env` if needed):

```toml
[[mcp_server]]
name = "hermes"
command = "/opt/apps/open-claude-tag/.venv/bin/python"
args = ["/opt/apps/open-claude-tag/examples/mcp/hermes_bridge_server.py"]
allowed_tools = ["hermes_ask"]
```

4. Restart `open-claude-tag`. In Slack: ask Tango to use Hermes for a Contabo-only task.

## Boundary

| | Tango | Hermes |
|--|-------|--------|
| Slack events | Yes | No (for this product) |
| Channel memory | Yes | No |
| Contabo skills/computer-use | Via MCP bridge only | Native |
