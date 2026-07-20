## [Unreleased] — Slack stream + chunk UX

- Stream LiteLLM agent completions by default (`LLM_STREAM`); Slack `pencil2` on first token
- Clearer Slack status reactions: `hourglass_flowing_sand` (working), `pencil2` (streaming), `computer` (code), `brain` (memory), `mag` / `clipboard` / `gear` unchanged
- Chunk long Slack replies; per-tool status reactions; multi-file delivery prompt rules
- Contabo canary (`#all-toshius-klay`): `STREAM_OK` / `CHUNK_OK`, `web_search` → `SEARCH_OK` (2026-07-21)

## [Unreleased] — Docs honesty pass

- Rewrite `docs/COWORKER-RUNTIME-STATUS.md` (code / wired / Contabo-verified / SaaS-ready)
- Sync PLAN Phase 1 + README roadmap; fix BUDGET.md marketing claim
- Refresh `docs/ARCHITECTURE.md` for durable path; add ADR-0001, API-CONTRACTS, THREAT-MODEL
- Mem0 namespace + Temporal unwired wording fixes

## [Unreleased] — Coworker runtime (100X)

### Added
- Durable task kernel: states, leases, checkpoints, `task_*` tools, completion verification, worker resume
- Context engine with token-aware compaction and thread-scoped history
- Layered memory (`memories` table + Mem0 hook) with provenance gates; atomic MEMORY.md writes
- Skill lifecycle: semantic match, usage stats, validated auto-create, weekly curator
- Tool policy executor: HITL Slack approvals, audit hashes, MCP session pooling + HTTP/SSE, Python sandbox
- Hardened LiteLLM Proxy deploy scaffold (aliases, Redis, salt key, key provisioning, spend reconcile)
- Ambient enqueue-only APScheduler + heartbeat/stale-thread observation
- SaaS tenancy: HTTP Events + OAuth, encrypted workspace credentials, Temporal adapter stub
- Docs: TASK-RUNTIME, CONTEXT-MEMORY, TOOL-POLICY, AMBIENT-RUNTIME, COWORKER-RUNTIME-STATUS, RUNBOOK
- Unit/integration tests for tasks, store, policy, context, ambient, restart recovery

### Fixed
- `search_channel_history` now searches FTS instead of echoing args
- Deterministic message ordering by autoincrement id
- Strip bot mention before classification; thread replies for approvals/resume
- Remove memory-writer ↔ loop circular import
