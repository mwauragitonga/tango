# SaaS roadmap — model-agnostic Slack co-worker

Product north star: Claude Tag–shaped multiplayer Slack teammate, **model-agnostic** (LiteLLM), capabilities via **MCP**, no Hermes/OpenClaw dependency for tenants.

## Feature list (buyer-facing)

1. Install to Slack (OAuth) — pick channels; `@Tango` multiplayer teammate
2. Model router — org/channel defaults + fallbacks; cost vs quality profiles
3. Org brain — `ORG.md` + per-channel `CHANNEL.md` / `PERSONALITY.md` + curated `MEMORY.md`
4. Personality packs — sales vs eng vs support identities (memories/tools don’t cross)
5. Tools marketplace (MCP) — CRM, Postgres, Notion, GitHub, Linear, internal APIs; per-channel allowlists
6. Built-in coworker tools — real web search, sandboxed Python, channel search
7. Skills — reusable playbooks; auto-create after complex tasks
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

## Phases

| Phase | Scope |
|-------|--------|
| Now (Contabo) | Socket Mode, fixed search, real MCP stdio, ORG.md, optional Hermes MCP |
| SaaS preview | Second workspace via OAuth + HTTP; per-tenant secrets/models; spend caps |
| Marketplace | Review, billing, admin UI, ambient + async |

## Architecture boundary

- **Tango** owns Slack UX + agent loop + tenancy
- **MCP** owns CRM/DB/custom tools
- **Hermes/OpenClaw** are Contabo personal agents — optional MCP providers only, never SaaS control plane

See also [ARCHITECTURE.md](./ARCHITECTURE.md) and [HERMES-MCP.md](./HERMES-MCP.md).
