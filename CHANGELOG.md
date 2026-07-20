# Changelog (Tango fork)

## 2026-07-20

Fork lineage: [Anil-matcha/open-claude-tag](https://github.com/Anil-matcha/open-claude-tag) → maintained at [mwauragitonga/tango](https://github.com/mwauragitonga/tango).

### Fixes

- **Crash:** import `asyncio` in `tagopen/gateway/router.py`.
- **Slack mrkdwn:** `tagopen/slack_format.py` + convert in `agent/loop.py`; strip `[ts @agent]` prefixes.
- **Web search:** replace DuckDuckGo Instant Answer with multi-provider search (`ddgs` default; optional Tavily/Brave/Serper/Firecrawl).

### Features

- **MCP client:** stdio MCP servers from channel `tools.toml` (list + call).
- **Org KB example:** `examples/mcp/org_kb_server.py` + `data/org/ORG.md`.
- **ORG.md / PERSONALITY.md** in system prompt.
- **Contabo-only Hermes bridge:** `examples/mcp/hermes_bridge_server.py` + [docs/HERMES-MCP.md](docs/HERMES-MCP.md).
- **SaaS roadmap:** [docs/SAAS-ROADMAP.md](docs/SAAS-ROADMAP.md).
