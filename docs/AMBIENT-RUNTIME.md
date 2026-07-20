# Ambient Runtime

APScheduler (`scheduler/service.py`) is **enqueue-only**. It never runs the agent loop directly.

The process tick uses an **in-memory** APScheduler job store (do not pickle `AsyncApp` into SQLAlchemy). Durable per-channel schedules live in Tango’s own SQLite `schedules` table.

## Schedules

Tools: `schedule_task`, `list_schedules`, `pause_schedule`, `resume_schedule`, `delete_schedule` → `schedules` table → tick enqueues durable tasks.

## Heartbeat

`ambient/heartbeat.py` builds observations (open tasks, stale waiting threads), decides `silent|post` with dedupe, respects quiet hours (`AMBIENT_QUIET_HOURS=22-07`) and monthly budget settings.

## Temporal

`scheduler/temporal_adapter.py` is an **unwired stub**. Setting `TEMPORAL_ENABLED=true` alone does nothing — `start_temporal_worker()` is not called from `gateway/app.py`. Contabo runs without Temporal (SQLite leases + APScheduler enqueue). See [ADR-0001-sqlite-vs-temporal.md](./ADR-0001-sqlite-vs-temporal.md).
