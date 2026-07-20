# Tango Task Runtime

Durable coworker execution: objectives, plans, leases, checkpoints, approvals, completion verification.

## States

`queued` → `planning` / `running` → `waiting_approval` | `waiting_external` | `paused` → `verifying` → `completed`

Terminal: `completed`, `failed`, `cancelled`, `suspended`. Restart recovery uses `resume_pending`.

## Tools

- `task_plan`, `task_status`, `task_update`, `task_pause`, `task_resume`, `task_cancel`, `task_complete`
- `task_complete` is rejected while required steps are incomplete or acceptance evidence is missing

## Worker

`tagopen/tasks/worker.py` claims leases, heartbeats, checkpoints after model/tool/approval transitions, posts Slack progress on meaningful changes or every `PROGRESS_INTERVAL_SECONDS`.

Long replies are chunked into ordered thread messages (`tagopen/slack_post.py`). Tool activity uses reactions on the triggering message when `event_ts` is available, otherwise a short status post (`tagopen/slack_status.py`).

Thread commands: `status`, `pause`, `resume`, `cancel`.

## Intake

Quick Q&A stays on the inline runtime (`agent/runtime.py`). Multi-step / write / long work is queued as a durable task (`tasks/service.py::should_queue_durable`).
