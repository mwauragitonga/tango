# Ambient Runtime

APScheduler (`scheduler/service.py`) is **enqueue-only**. It never runs the agent loop directly.

The process tick uses an **in-memory** APScheduler job store (do not pickle `AsyncApp` into SQLAlchemy). Durable per-channel schedules live in Tango’s own SQLite `schedules` table.

## Schedules

Tools: `schedule_task`, `list_schedules`, `pause_schedule`, `resume_schedule`, `delete_schedule` → `schedules` table → tick enqueues durable tasks.

## Heartbeat

`ambient/heartbeat.py` is **post-only**: it never creates durable tasks and never competes in `claim_next` with user work.

Flow: build observations (open **user** tasks only — heartbeat rows excluded), decide `silent|post` with dedupe, respect quiet hours (`AMBIENT_QUIET_HOURS=22-07`). If the channel has any active non-heartbeat user task (`queued` / `planning` / `running` / `verifying` / `waiting_approval` / `waiting_external` / `resume_pending`), stay **silent**. Otherwise post a short nudge via `chat_postMessage` (prefer a real Slack `thread_ts` from an open user task; else channel root).

## Temporal

`scheduler/temporal_adapter.py` is an **unwired stub**. Setting `TEMPORAL_ENABLED=true` alone does nothing — `start_temporal_worker()` is not called from `gateway/app.py`. Contabo runs without Temporal (SQLite leases + APScheduler enqueue). See [ADR-0001-sqlite-vs-temporal.md](./ADR-0001-sqlite-vs-temporal.md).
