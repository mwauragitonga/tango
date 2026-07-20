# Architecture diagnosis (Tango fork)

## Verdict

**Tango does not run OpenClaw or Hermes under the hood.**

This codebase is a fork of [Anil-matcha/open-claude-tag](https://github.com/Anil-matcha/open-claude-tag) (`tagopen`). It is a **standalone** Slack Socket Mode bot. Upstream *compares itself to* and *borrows patterns from* OpenClaw, Hermes Agent, and Letta — those are **inspiration / references**, not embedded runtimes or Python dependencies.

On hosts that also run OpenClaw or Hermes (e.g. contabo-prod), Tango is a **separate process** (`open-claude-tag.service`). It may reuse the same Ollama Cloud API key via env vars; it does **not** share OpenClaw gateway state, Hermes `~/.hermes`, WhatsApp bridges, or messaging tokens.

## Stack

| Layer | Implementation | OpenClaw / Hermes? |
|-------|----------------|--------------------|
| Slack I/O | `slack-bolt` async + Socket Mode | No |
| LLM | LiteLLM (`acompletion`) | No (own gateways elsewhere) |
| Agent | In-repo ReAct loop (`tagopen/agent/loop.py`) | No |
| Memory | SQLite + FTS5 + `MEMORY.md` curation (Letta-inspired) | Not Hermes mem0-pg / not OpenClaw `WORKING.md` |
| Skills | Auto `skills/*.md` after complex tool use (Hermes-inspired) | Pattern only |
| Tools | Built-ins + optional MCP via `tools.toml` | Not OpenClaw tool host |
| Ambient | APScheduler heartbeat (partial / upstream roadmap) | Not Hermes crons |
| Deps | `slack-bolt`, `litellm`, `mem0ai`, `mcp`, `aiosqlite`, … | No `openclaw` / `hermes` packages |

## Request path

```
Slack @mention (Socket Mode)
  → tagopen/gateway/app.py
  → channel router (workspace_id + channel_id)
  → context (CHANNEL.md + MEMORY.md + skills + recent messages)
  → ReAct agent loop + LiteLLM
  → slack_format.to_slack_mrkdwn()
  → chat_postMessage (thread reply)
  → optional memory curation / skill write
```

## Why the comparison table mentions OpenClaw / Hermes

Upstream positions Open Claude Tag as a **channel-scoped** alternative to personal-assistant bots (including OpenClaw/Hermes-style per-user agents). That is a product comparison, not a claim that those binaries run inside this process.
