# Coworker runtime status (verified)

| Area | Status | Acceptance |
|------|--------|------------|
| Service seams (runtime/tasks/context/tools/llm) | **shipped** | modules under `tagopen/{tasks,context,llm,tools}` |
| SQLite migrations | **shipped** | `tagopen/db/migrations.py` v1–v2 |
| Slack idempotency | **shipped** | `slack_events` + `claim_slack_event` |
| Durable task kernel | **shipped** | states, leases, checkpoints, task_* tools, completion guards |
| Thread-scoped context | **shipped** | `MessageStore.get_recent_messages(..., thread_ts=)` |
| `search_channel_history` | **shipped** | ToolExecutor → `MessageStore.search` |
| Context compaction | **shipped** | 70% threshold + durable summaries |
| Layered memory + Mem0 hook | **shipped** | `memory/layers.py` (Mem0 optional) |
| Skill lifecycle | **shipped** | match/validate/stats/weekly curator |
| Tool policy + HITL | **shipped** | approvals via thread `approve|deny <id>` |
| MCP pool + HTTP/SSE | **shipped** | `tools/mcp_client.py` |
| LiteLLM Proxy scaffold | **shipped** | hardened compose + docs; Contabo canary optional |
| Ambient enqueue scheduler | **shipped** | memory tick + SQLite `schedules` (no AsyncApp pickle) |
| SaaS OAuth/HTTP | **shipped** | `tenancy/http_app.py` (`SLACK_MODE=http`) |
| Temporal adapter | **shipped** | optional `TEMPORAL_ENABLED` |
| Unit/integration tests | **shipped** | `tests/unit/`, `tests/integration/` (22+); Contabo canary active |

## Rollout

1. Contabo canary channel  
2. All Contabo Tango channels  
3. Second Slack workspace (HTTP+OAuth)  
4. SaaS preview  

Gates: restart resume without duplicate side effects; no false completion; LLM attribution non-null; mutating tools audited; tenant isolation; dashboards on stuck tasks/leases/budgets.
