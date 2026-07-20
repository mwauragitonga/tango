# Threat model (thin)

Scope: Contabo Socket Mode coworker + SaaS HTTP scaffold. Not a full STRIDE report.

## Assets

- Slack bot tokens (`xoxb` / `xapp`) and SaaS OAuth credentials
- Channel Markdown + SQLite (`MEMORY.md`, skills, task checkpoints, message FTS)
- Provider API keys / LiteLLM virtual keys
- Optional Hermes MCP bridge (Contabo only)

## Trust boundaries

| Boundary | Rule |
|----------|------|
| Contabo vs SaaS tenants | Never index Hermes `USER.md` / OpenClaw state into shared channels |
| Channel isolation | Repository queries scoped by `workspace_id` + `channel_id` |
| Write tools | HITL `approve\|deny` unless channel `auto_approve_writes` |
| Hermes MCP | Contabo-only; disable for SaaS tenants |
| LiteLLM master key | Control plane only — not in Tango workers |

## Socket Mode (Contabo)

- Outbound WebSocket; no public ingress for Slack.
- Compromised host ⇒ full bot token + channel data. Protect `.env` mode 600; dedicated Slack app (never reuse OpenClaw/Hermes tokens).

## HTTP Events + OAuth (SaaS scaffold)

- Verify Slack signing secret on `/slack/events`.
- Store per-workspace bot tokens encrypted (`CREDENTIAL_FERNET_KEY`); never in channel files.
- Redirect URLs must be HTTPS; separate apps for preview vs Directory ([SLACK-SAAS-MANIFEST.md](./SLACK-SAAS-MANIFEST.md)).

## Abuse / misuse

- Prompt injection via channel history → tool calls: mitigated by policy + HITL on writes; not eliminated.
- `run_python`: sandbox strips FS/network builtins; **disabled in `SAAS_MODE`** until stronger isolation.
- Ambient posts: quiet hours + dedupe; still can spam if mis-scheduled — pause schedules.

## Non-goals (yet)

- Formal pen-test report, Enterprise Slack compliance pack, PII redaction pipeline for all logs.
