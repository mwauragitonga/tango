# Ambient Runtime

APScheduler (`scheduler/service.py`) is **enqueue-only**. It never runs the agent loop directly.

## Schedules

Tools: `schedule_task`, `list_schedules`, `pause_schedule`, `resume_schedule`, `delete_schedule` → `schedules` table → tick enqueues durable tasks.

## Heartbeat

`ambient/heartbeat.py` builds observations (open tasks, stale waiting threads), decides `silent|post` with dedupe, respects quiet hours (`AMBIENT_QUIET_HOURS=22-07`) and monthly budget settings.

## Temporal

When `TEMPORAL_ENABLED=true`, `scheduler/temporal_adapter.py` wraps the same task worker as activities. Domain state remains in SQLite/Postgres task store.
