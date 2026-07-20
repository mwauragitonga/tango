# Borrowed patterns — Hermes & OpenClaw

Tango **borrows product patterns** from Hermes Agent and OpenClaw. It does **not** embed those runtimes.

## Hermes (Contabo: v0.17, `~/.hermes`)

| Pattern | Hermes | Tango |
|---------|--------|-------|
| Org persona | `SOUL.md` | `data/org/SOUL.md` (seed from [`examples/org/SOUL.md`](../examples/org/SOUL.md)) |
| Channel tone overlay | `/personality` | `PERSONALITY.md` |
| Progressive skills | `skills_list` → `skill_view` | same tool names |
| MCP naming | `mcp_<server>_<tool>` | same |
| Model switch | `/model` session | `@Tango model …` (thread) |
| Memory bounds | char-capped MEMORY/USER | channel `MEMORY.md` truncated in prompt |

**Do not copy:** terminal/computer-use/browser as default Slack tools; instance-global SOUL as the only persona; WhatsApp/Telegram gateway coupling.

## OpenClaw (Contabo: nvm Node 22 package)

| Pattern | OpenClaw | Tango |
|---------|----------|-------|
| Session key | Slack channel (+ thread) | `(workspace, channel)` + thread |
| Tool policy | allow/deny profiles | channel `tools.toml` + builtins |
| Failover | turn-local + visible notice | `LLM_FALLBACKS` + notice in reply |
| Private memory | never in shared rooms | no USER.md injection into channels |

**Do not copy:** personal USER/MEMORY into channel context; host `exec`/`fs` full profile; multi-IM personal gateway as product core.

## LiteLLM scale

| Stage | Mode |
|-------|------|
| Contabo / single-tenant | SDK `litellm.acompletion` in-process |
| Multi-tenant SaaS | [LiteLLM Proxy](./LITELLM-PROXY.md) + Postgres (+ Redis) |

Model IDs stay LiteLLM strings so cutover is mostly `base_url` + virtual keys.
