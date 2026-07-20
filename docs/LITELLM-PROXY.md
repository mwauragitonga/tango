# LiteLLM Proxy governance (Tango)

LiteLLM Proxy is the **LLM accounting layer** only. Task state, tools, approvals, and memory remain in Tango’s audit store and correlate via `request_id` / `task_id`.

## Contabo proving ground

Run Proxy + Postgres + Redis on localhost (`127.0.0.1:4000`):

```bash
cd deploy/litellm-proxy
cp .env.example .env   # set MASTER, SALT, POSTGRES, REDIS passwords
# Set LITELLM_SALT_KEY once before storing provider credentials — never rotate
docker compose --profile migrate up litellm-migrate   # one-shot schema
docker compose up -d postgres redis litellm
```

Tango workers:

```bash
LITELLM_PROXY_URL=http://127.0.0.1:4000
LITELLM_PROXY_KEY=<workspace-virtual-key>   # NOT the master key
LLM_USE_APP_FALLBACKS=false                 # Proxy owns routing/fallbacks
LLM_MODEL=tango-primary
```

## Tenancy model (OSS)

| Concept | Mapping |
|---------|---------|
| Team | One Slack workspace |
| Service-account virtual key | Workspace/environment worker credential |
| `user` / `end_user` | Pseudonymous Slack user id |
| Key metadata | Authoritative `workspace_id`, `environment`, `plan` |

Organizations / delegated org admin / key-scoped Enterprise guardrails are **not** product dependencies unless you buy Enterprise.

## Request attribution

Every call via `tagopen/llm/gateway.py` attaches: `workspace_id`, `channel_id`, `thread_ts`, `slack_user_id`, `task_id`, `run_id`, `step_id`, `request_id`, `purpose` (`planner|agent|summary|memory|skill|heartbeat`).

Reject client-supplied authoritative tenant tags; derive from the virtual key. Do not use workspace/channel/user ids as Prometheus labels.

## Budgets & reliability

- Workspace monthly budget, soft alert, per-key max, model allowlist, RPM/TPM, max parallel, expiry
- Aliases: `tango-primary`, `tango-fast`, `tango-reasoning`, `tango-summary`
- Fallbacks: same-deployment retry + explicit cooldowns; **no** `gpt-4o-mini`
- Custom pricing for models LiteLLM cannot price — spend must not be silently zero
- Daily reconcile: `deploy/litellm-proxy/reconcile-spend.sh` vs Tango `llm_usage`

## Ops

- Pin image digest (compose uses `v1.74.3-stable` placeholder — replace with digest)
- Replicas: `DISABLE_SCHEMA_UPDATE=true`; one-shot migrate job owns upgrades
- Prometheus callbacks are best-effort telemetry; Tango `llm_usage` + task audit are the compliance ledger
- Provision keys: `deploy/litellm-proxy/provision-workspace-key.sh`
- Keep Hermes off this Proxy for SaaS tenants
