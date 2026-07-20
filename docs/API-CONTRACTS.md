# API contracts (coworker surface)

Thin contracts for operators and integrators. Not OpenAPI — Slack + tool JSON only.

## Task states

`queued` | `planning` | `running` | `waiting_approval` | `waiting_external` | `paused` | `resume_pending` | `suspended` | `verifying` | `completed` | `failed` | `cancelled`

Terminal: `completed`, `failed`, `cancelled`, `suspended`.

Step statuses (tool `task_update`): `pending` | `in_progress` | `completed` | `failed` | `blocked` | `cancelled`  
(Models sometimes send `done` — invalid; use `completed`.)

## Slack thread commands

| Input | When | Effect |
|-------|------|--------|
| `@Tango status` | Active or recent task on thread | Post durable summary |
| `@Tango pause [reason]` | Non-terminal task | `paused` |
| `@Tango resume` | paused / waiting_* | `resume_pending` then worker |
| `@Tango cancel [reason]` | Non-terminal | `cancelled` |
| `approve <approval_id>` | Pending tool HITL | Run tool (preauth) + resume |
| `deny <approval_id>` | Pending tool HITL | Pause with denial |

Bare `status` / `pause` without `@Tango` are **not** handled on plain `message` events (only approvals, `resume`, or mentions). Prefer `@Tango …`.

## Task tools (LLM)

`task_plan`, `task_status`, `task_update`, `task_pause`, `task_resume`, `task_cancel`, `task_complete`  
`task_complete` rejected while required steps incomplete or acceptance evidence missing.

## Schedule tools

`schedule_task` (cron + description), `list_schedules`, `pause_schedule`, `resume_schedule`, `delete_schedule`  
Scheduler enqueues normal durable tasks; never runs the agent loop itself.

## LLM attribution metadata

Every gateway call should carry: `workspace_id`, `channel_id`, `thread_ts`, `slack_user_id`, `task_id`, `run_id`, `step_id`, `request_id`, `purpose` (`agent|summary|memory|skill|heartbeat|planner`). Persisted in `llm_usage`.

## SaaS HTTP routes (scaffold)

| Method | Path | Role |
|--------|------|------|
| POST | `/slack/events` | Events API |
| GET | `/slack/oauth/start` | Install |
| GET | `/slack/oauth/callback` | Token exchange → encrypted store |
| GET | `/admin/health` | MCP circuit snapshot |

See [SLACK-SAAS-MANIFEST.md](./SLACK-SAAS-MANIFEST.md) for scopes.
