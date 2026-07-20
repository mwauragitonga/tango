# Coworker runtime status

Single source of truth for what exists vs what is ops-proven. Prefer this over README/PLAN checkboxes.

Legend:

| Column | Meaning |
|--------|---------|
| **code** | Source files present in the repo |
| **wired** | Invoked from the Contabo Socket Mode path (`gateway/app.py` → loop/worker) |
| **Contabo-verified** | Exercised on contabo-prod canary (`#all-toshius-klay`) or equivalent |
| **SaaS-ready** | Safe for multi-tenant HTTP/OAuth production |

| Area | code | wired | Contabo-verified | SaaS-ready | Evidence |
|------|:----:|:-----:|:----------------:|:----------:|----------|
| Service seams (`tasks`, `context`, `llm`, `tools`) | yes | yes | yes | partial | `tagopen/{tasks,context,llm,tools}/` |
| SQLite migrations v1–v2 | yes | yes | yes | n/a (Postgres later) | `tagopen/db/migrations.py` |
| Slack event idempotency | yes | yes | yes | yes | `slack_events` + `claim_slack_event`; `test_slack_event_idempotency` |
| Durable task kernel | yes | yes | **yes** | partial | `tasks/{models,service,store,worker,tools}.py`; canary `tsk_0676` / `tsk_1ef7` (2026-07-21) |
| Thread-scoped context | yes | yes | yes | yes | `MessageStore.get_recent_messages(..., thread_ts=)`; `test_thread_scoped_recent_and_order` |
| `search_channel_history` → FTS | yes | yes | yes | yes | `tools/executor.py` → `MessageStore.search` |
| Context compaction (70%) | yes | yes | partial | partial | `context/engine.py` `compact_threshold=0.70`; `test_should_compact` |
| Channel / episodic memory | yes | yes | yes | partial | `memory/{writer,files,layers}.py` + `memories` table |
| Mem0 semantic recall | yes | **optional** | **no** | no | `MEM0_ENABLED` default false; soft-fail hook in `memory/layers.py` |
| Skill match / validate / auto-create | yes | yes | yes | partial | `skill_lifecycle.py`, `skills.py`; NL skill_view canary |
| Weekly skill curator | yes | **no** | no | no | `weekly_curator()` defined; **not** scheduled by APScheduler |
| Tool policy + HITL | yes | yes | yes | partial | `tools/policy.py`; thread `approve\|deny <id>`; canary pause/resume |
| MCP pool + HTTP/SSE | yes | yes | yes (stdio) | partial | `tools/mcp_client.py`; Contabo org_kb / hermes stdio |
| LiteLLM gateway + usage rows | yes | yes | yes | partial | `llm/gateway.py` → `llm_usage`; Contabo still **SDK** not Proxy |
| LiteLLM Proxy deploy | yes | **no** | no | scaffold | `deploy/litellm-proxy/`; image digest still placeholder |
| Ambient enqueue scheduler | yes | yes | partial | partial | `scheduler/service.py` memory job store; SQLite `schedules` |
| SaaS HTTP Events + OAuth | yes | via `SLACK_MODE=http` | no | **scaffold** | `tenancy/http_app.py`; export/delete stubs |
| Temporal adapter | yes | **no** | no | no | `scheduler/temporal_adapter.py`; `start_temporal_worker` **never called** from gateway |
| Unit / integration tests | yes | yes | n/a | n/a | `tests/` — 24 collected locally |

## Contabo canary (durable kernel)

Verified 2026-07-21 in `#all-toshius-klay` (team `T09P6EA3D3N`):

- Multi-step durable ack/progress/complete (`tsk_0676`)
- Thread `@Tango status`
- Pause / resume mid-run (`tsk_1ef7`)

Bare `status` without `@Tango` does **not** route (mentions / `approve|deny` / resume only on `message` events).

## Rollout gates (not all met)

1. Contabo canary channel — durable kernel **done**
2. All Contabo Tango channels — pending
3. Second Slack workspace (HTTP+OAuth) — pending
4. SaaS preview — pending Proxy + tenancy hardening

Still open for “release ready”: tenant isolation suite, Proxy spend reconcile in prod, dashboards on stuck leases/budgets, Temporal only when multi-worker.

## Related docs

- [TASK-RUNTIME.md](./TASK-RUNTIME.md) · [CONTEXT-MEMORY.md](./CONTEXT-MEMORY.md) · [TOOL-POLICY.md](./TOOL-POLICY.md) · [AMBIENT-RUNTIME.md](./AMBIENT-RUNTIME.md)
- [ADR-0001-sqlite-vs-temporal.md](./ADR-0001-sqlite-vs-temporal.md) · [API-CONTRACTS.md](./API-CONTRACTS.md) · [THREAT-MODEL.md](./THREAT-MODEL.md)
- Ops: [../deploy/RUNBOOK-COWORKER.md](../deploy/RUNBOOK-COWORKER.md) · Slack SaaS manifests [SLACK-SAAS-MANIFEST.md](./SLACK-SAAS-MANIFEST.md)
