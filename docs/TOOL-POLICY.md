# Tool Policy

`tagopen/tools/policy.py` + `tools/executor.py`:

1. Safe Slack defaults (reads auto)
2. Workspace / channel policy (`deny_tools`, `auto_approve_writes`, `tool_risk`, `read_tools`)
3. Task approval for writes; destructive always requires approval
4. SaaS disables `run_python` until sandbox is healthy (`SAAS_MODE` / `disable_run_python`)

Every execution records args/result hashes, latency, risk, requester/approver in `tool_executions`.

## MCP

`tools/mcp_client.py` pools stdio sessions and supports HTTP/SSE via `url=`. Circuit breakers per server; `mcp_health()` for admin.

## Sandbox

`tools/sandbox.py` — no `open`/`__import__`, soft CPU limit. Prefer stronger isolation before enabling SaaS Python.
