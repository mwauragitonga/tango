# Context & Memory

## ContextEngine

`tagopen/context/engine.py` implements:

- `update_usage` / `should_compact` (70% of model window) / `compact` / `build_context` / `status`
- Protected: system prompt, objective, acceptance criteria, active plan, last six exchanges, unresolved tools, approvals, latest checkpoint
- Compaction summaries persisted in `compaction_summaries` with optional source ranges

Context is **thread/task scoped** via `MessageStore.get_recent_messages(..., thread_ts=)`.

## Memory layers

| Layer | Store | Notes |
|-------|--------|------|
| Working | `tasks` + checkpoint JSON | plan, blockers, next action |
| Channel | `MEMORY.md` (projection) + `memories` table | provenance required for authoritative facts |
| Episodic | `memories` kind=episodic | completed task lessons |
| Semantic | optional Mem0 (`MEM0_ENABLED`, `MEM0_DSN`) | namespace `org/workspace/channel`; never Hermes `USER.md` |

Curation runs asynchronously after replies (`memory/writer.py`) using atomic locked writes (`memory/files.py`).
