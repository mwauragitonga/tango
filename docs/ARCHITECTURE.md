# Architecture diagnosis (Tango fork)

## Verdict

**Tango does not run OpenClaw or Hermes under the hood.**

This codebase is a fork of [Anil-matcha/open-claude-tag](https://github.com/Anil-matcha/open-claude-tag) (`tagopen`), maintained at [mwauragitonga/tango](https://github.com/mwauragitonga/tango). It is a **standalone** Slack Socket Mode bot. Upstream *compares itself to* and *borrows patterns from* OpenClaw, Hermes Agent, and Letta — those are **inspiration / references**, not embedded runtimes or Python dependencies.

On hosts that also run OpenClaw or Hermes (e.g. contabo-prod), Tango is a **separate process** (`open-claude-tag.service`). It may reuse the same Ollama Cloud API key via env vars; it does **not** share OpenClaw gateway state, Hermes `~/.hermes`, WhatsApp bridges, or messaging tokens.

## Stack

| Layer | Implementation | OpenClaw / Hermes? |
|-------|----------------|--------------------|
| Slack I/O | `slack-bolt` async + Socket Mode | No |
| LLM | LiteLLM (`acompletion`) | No |
| Agent | In-repo ReAct loop (`tagopen/agent/loop.py`) | No |
| Memory | SQLite + FTS5 + `MEMORY.md`; org-wide `data/org/ORG.md` | Not Hermes mem0-pg / not OpenClaw `WORKING.md` |
| Skills | Auto `skills/*.md` (Hermes-inspired pattern) | Pattern only |
| Tools | Built-ins + **stdio MCP** via `tools.toml` | Optional Contabo Hermes bridge MCP — see [HERMES-MCP.md](./HERMES-MCP.md) |
| Search | `ddgs` by default; optional Tavily/Brave/Serper/Firecrawl keys | No |
| Ambient | APScheduler heartbeat (partial) | Not Hermes crons |

## Request path

```
Slack @mention (Socket Mode)
  → tagopen/gateway/app.py
  → channel router (workspace_id + channel_id)
  → context (ORG.md + PERSONALITY.md + CHANNEL.md + MEMORY.md + skills)
  → ReAct agent loop + LiteLLM
  → builtins / MCP tools
  → slack_format.to_slack_mrkdwn()
  → chat_postMessage (thread reply)
```

## SaaS direction

See [SAAS-ROADMAP.md](./SAAS-ROADMAP.md). Tenants must never depend on Contabo Hermes/OpenClaw.
