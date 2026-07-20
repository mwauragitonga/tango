# SaaS roadmap — model-agnostic Slack co-worker

Product north star: Claude Tag–shaped multiplayer Slack teammate, **model-agnostic** (LiteLLM), capabilities via **MCP**, no Hermes/OpenClaw dependency for tenants.

## Feature list (buyer-facing)

1. Install to Slack (OAuth) — pick channels; `@Tango` multiplayer teammate
2. Model router — org/channel defaults + fallbacks; cost vs quality profiles
3. Org brain — `ORG.md` + `SOUL.md` + per-channel `CHANNEL.md` / `PERSONALITY.md` + curated `MEMORY.md`
4. Personality packs — sales vs eng vs support identities (memories/tools don’t cross)
5. Tools marketplace (MCP) — CRM, Postgres, Notion, GitHub, Linear, internal APIs; per-channel allowlists
6. Built-in coworker tools — real web search, sandboxed Python, channel search
7. Skills — progressive playbooks (`skills_list` / `skill_view`); auto-create after complex tasks
8. Async work — thread progress; scheduled follow-ups
9. Ambient mode — opt-in digests (SILENT if nothing useful)
10. Admin console — ACL, spend caps, audit log
11. Human-in-the-loop — confirm before writes
12. Compliance — residency, retention, no training on customer data

## Platform requirements

- Multi-tenant DB (installations, channel configs, audit)
- **HTTP Events + OAuth** (Socket Mode is fine for single-tenant Contabo; Marketplace needs HTTP)
- Per-workspace token store (`team_id` → `xoxb`)
- Durable jobs; secrets vault; Stripe metering; observability
- **LiteLLM Proxy** (+ Postgres/Redis) for virtual keys and per-tenant budgets — see [LITELLM-PROXY.md](./LITELLM-PROXY.md)

## Phases

| Phase | Scope |
|-------|--------|
| Now (Contabo) | Socket Mode, progressive skills, org SOUL, thread `@Tango model`, turn-local `LLM_FALLBACKS`, MCP stdio, **LiteLLM SDK** in-process |
| P1 must-borrows | Progressive skills; SOUL + personality overlay; in-chat model switch + failover notices; stricter tool profiles + HITL for writes |
| SaaS preview | Second workspace via OAuth + HTTP; **LiteLLM Proxy** + virtual keys/spend caps; per-tenant secrets/models |
| Marketplace | Review, billing, admin UI, ambient + async |

## LiteLLM SDK → Proxy milestone

| Stage | Mode | Why |
|-------|------|-----|
| Contabo + P1 coworker | SDK `litellm.acompletion` in Tango | One Python service; Ollama Cloud / multi-provider strings |
| SaaS multi-tenant (P3+) | LiteLLM Proxy sidecar | Virtual keys, budgets, audit, rate limits |

Keep model IDs as LiteLLM strings so cutover is mostly `OPENAI_API_BASE` + virtual keys. Scaffolding: [`deploy/litellm-proxy/`](../deploy/litellm-proxy/).

Defer until P3+: Hermes computer-use surface, OpenClaw host exec, Mem0 (unless Contabo-only experiment).

## Architecture boundary

- **Tango** owns Slack UX + agent loop + tenancy
- **MCP** owns CRM/DB/custom tools
- **Hermes/OpenClaw** are Contabo personal agents — optional MCP providers only, never SaaS control plane

See also [ARCHITECTURE.md](./ARCHITECTURE.md), [BORROWED-PATTERNS.md](./BORROWED-PATTERNS.md), [HERMES-MCP.md](./HERMES-MCP.md), [LITELLM-PROXY.md](./LITELLM-PROXY.md).
