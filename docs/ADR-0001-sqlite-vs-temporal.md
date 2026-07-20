# ADR-0001 — SQLite task store first; Temporal later

## Status

Accepted (2026-07). Contabo production runs **without** Temporal.

## Context

Tango needs durable multi-step work: survive restarts, Slack retries, and provider blips without losing objectives/plans. Options considered:

1. In-process only (no persistence) — fails restart/resume gates.
2. SQLite (+ WAL) task store with leases/checkpoints on one host.
3. Temporal (or similar) as the primary orchestrator from day one.

## Decision

Use **SQLite task domain state** (`tasks`, leases, checkpoints, approvals) as the source of truth. APScheduler only **enqueues** durable tasks. Keep a thin Temporal adapter module for a future multi-worker SaaS cutover — **do not wire it** until multiple workers or long-wait workflows require it.

## Consequences

- Contabo: one worker, `TEMPORAL_ENABLED=false`, no Temporal cluster ops.
- Restart recovery: requeue expired leases → `resume_pending` → worker claim.
- Multi-replica SaaS: introduce Temporal (or Postgres + distributed leases) when 2+ workers share in-flight tasks or waits span hours/days across processes.
- Adapter file `tagopen/scheduler/temporal_adapter.py` exists but `start_temporal_worker()` is **not** called from `gateway/app.py` — enabling the env flag alone is insufficient.

## Rejected for Contabo MVP

- Temporal-first: ops cost and two failure domains before the task kernel was proven.
- Channel-wide asyncio locks as the only concurrency control for long work (replaced by task leases for durable path).
