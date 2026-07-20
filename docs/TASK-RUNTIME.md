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

### Mid-run Slack signals

| Signal | When | Source |
|--------|------|--------|
| `thinking_face` | Mention accepted | `gateway/app.py` + `SlackStatus.llm_start` |
| `speech_balloon` | First streamed LLM token (text or tool-call delta) | `llm/gateway.py` `on_first_token` → `SlackStatus.llm_first_token` |
| Tool emoji (`mag` / `snake` / `clipboard` / `gear`) | Tool dispatch start/end | `SlackStatus.tool_start` / `tool_end` |

Agent completions stream by default (`LLM_STREAM=true` → LiteLLM `stream=True`, rebuilt via `stream_chunk_builder`). Set `LLM_STREAM=false` to disable. Callers still receive a full aggregated response.

Thread commands: `status`, `pause`, `resume`, `cancel`.

## Intake

Quick Q&A stays on the inline runtime (`agent/runtime.py`). Multi-step / write / long work is queued as a durable task (`tasks/service.py::should_queue_durable`).

Large multi-file code dumps: system prompt asks for a short plan + one file per message (chunked posts enforce Slack size); prefer durable `task_*` plans for app scaffolds.
